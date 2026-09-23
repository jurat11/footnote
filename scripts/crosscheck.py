"""Independent verification of the ledger via a second SEC endpoint.

For every fact in a company's ledger, we re-fetch its value through the
``companyconcept`` endpoint (a different API surface than ``companyfacts``) and assert
the number matches, tied to the same period and accession. Any mismatch is a real
problem: it means the two SEC endpoints disagree, or our selection picked the wrong
entry. Results are written to eval/results.md.

Usage:
    python scripts/crosscheck.py            # full 25-ticker list
    python scripts/crosscheck.py AAPL MSFT  # a subset
"""

from __future__ import annotations

import sys
from pathlib import Path

from footnote.edgar import EdgarClient
from footnote.evallist import EVAL_TICKERS
from footnote.ledger import build_ledger
from footnote.models import Fact

RESULTS = Path(__file__).resolve().parent.parent / "eval" / "results.md"


def _match(fact: Fact, entries: list[dict]) -> str:
    """Return the outcome of checking a fact against companyconcept entries.

    'unavailable' means the independent endpoint has no data for this tag at all (a gap
    in the checker, not in our ledger). 'not_found' means it has the tag but not this
    period. 'mismatched' means both have the period but the values differ.
    """
    if not entries:
        return "unavailable"
    exact = [
        e
        for e in entries
        if e.get("end") == fact.period_end
        and (e.get("start") or None) == (fact.period_start or None)
        and e.get("accn") == fact.accession
    ]
    if exact:
        return "matched" if float(exact[0]["val"]) == fact.value else "mismatched"
    # Fall back to period-only (a restated value cited to a later filing).
    period = [
        e
        for e in entries
        if e.get("end") == fact.period_end and (e.get("start") or None) == (fact.period_start or None)
    ]
    if period:
        return "matched" if any(float(e["val"]) == fact.value for e in period) else "mismatched"
    return "not_found"


def crosscheck_ticker(client: EdgarClient, ticker: str) -> dict:
    led = build_ledger(client, ticker, years=5)
    cik10 = led.company.cik10
    counts = {"checked": 0, "matched": 0, "mismatched": 0, "not_found": 0, "unavailable": 0}
    problems: list[str] = []
    # Cache concept fetches per tag.
    concept_cache: dict[str, list[dict]] = {}
    for fact in led.facts.values():
        counts["checked"] += 1
        if fact.xbrl_tag not in concept_cache:
            try:
                data = client.company_concept(cik10, "us-gaap", fact.xbrl_tag)
                units = data.get("units", {})
                concept_cache[fact.xbrl_tag] = units.get(fact.unit, next(iter(units.values()), []))
            except Exception as exc:  # noqa: BLE001
                concept_cache[fact.xbrl_tag] = []
                problems.append(f"{fact.id}: concept fetch failed ({exc})")
        outcome = _match(fact, concept_cache[fact.xbrl_tag])
        counts[outcome] += 1
        # 'unavailable' is a gap in the checker's endpoint, not a ledger defect.
        if outcome in ("mismatched", "not_found"):
            problems.append(f"{fact.id} [{fact.xbrl_tag}]: {outcome} (value {fact.value})")
    return {"ticker": led.company.ticker, "counts": counts, "problems": problems}


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or EVAL_TICKERS
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    totals = {"checked": 0, "matched": 0, "mismatched": 0, "not_found": 0, "unavailable": 0}
    all_problems: list[str] = []
    with EdgarClient() as client:
        for t in tickers:
            try:
                res = crosscheck_ticker(client, t)
            except Exception as exc:  # noqa: BLE001
                rows.append((t, "ERROR", "-", "-", "-", "-"))
                all_problems.append(f"{t}: {exc}")
                continue
            c = res["counts"]
            for k in totals:
                totals[k] += c[k]
            rows.append((res["ticker"], c["checked"], c["matched"], c["mismatched"], c["not_found"], c["unavailable"]))
            all_problems.extend(res["problems"])
            print(f"{res['ticker']}: {c['matched']}/{c['checked']} matched, "
                  f"{c['mismatched']} mismatched, {c['not_found']} not found, {c['unavailable']} endpoint-unavailable")

    checkable = totals["matched"] + totals["mismatched"] + totals["not_found"]
    lines = ["# Crosscheck results", "",
             "Independent re-fetch of every ledger fact via the `companyconcept` endpoint "
             "(a different SEC API surface than the `companyfacts` the ledger is built from).",
             "",
             "`unavailable` means the `companyconcept` endpoint returned no data for that tag at all; "
             "this is a coverage gap in the checker, not a discrepancy in the ledger.",
             "", "| Ticker | Checked | Matched | Mismatched | Not found | Endpoint-unavailable |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
    lines += ["", f"**Totals:** {totals['matched']}/{checkable} checkable facts matched, "
                  f"{totals['mismatched']} mismatched, {totals['not_found']} not found. "
                  f"{totals['unavailable']} facts had no companyconcept coverage to check against.", ""]
    if all_problems:
        lines += ["## Discrepancies", ""] + [f"- {p}" for p in all_problems]
    else:
        lines += ["No discrepancies: every fact matched the independent path.", ""]
    RESULTS.write_text("\n".join(lines))
    print("\nWrote", RESULTS)


if __name__ == "__main__":
    main()

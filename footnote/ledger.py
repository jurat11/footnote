"""Assemble a full :class:`Ledger` for a company: facts + ratios + gaps.

This is the deterministic heart of Footnote. No language model is involved; the
output here is the ground truth every report token resolves against.
"""

from __future__ import annotations

from typing import Any

from .edgar import EdgarClient, resolve_cik
from .facts import build_facts
from .models import Company, Ledger
from .ratios import build_ratios


def _company_from_submissions(cik: int, ticker: str, name: str, submissions: dict[str, Any]) -> Company:
    return Company(
        ticker=ticker,
        cik=cik,
        name=submissions.get("name") or name,
        sic=str(submissions.get("sic")) if submissions.get("sic") else None,
        sic_description=submissions.get("sicDescription"),
    )

def combine_ledgers(leds: dict[str, Ledger]) -> Ledger:
    """Merge several single-company ledgers into one whose ids are ticker-namespaced.

    Used only for rendering and verifying a comparison report, where a bare
    ``revenue:FY2025`` would be ambiguous between companies. Each fact/ratio is copied
    with a ``TICKER:`` prefix on its id (and its label) so tokens resolve unambiguously.
    """
    facts: dict[str, object] = {}
    ratios: dict[str, object] = {}
    years: set[int] = set()
    missing = []
    reports_gm = True
    tickers = list(leds.keys())
    for ticker, led in leds.items():
        years.update(led.years)
        reports_gm = reports_gm and led.reports_gross_margin
        missing.extend(led.missing)
        for fid, f in led.facts.items():
            facts[f"{ticker}:{fid}"] = f.model_copy(update={"id": f"{ticker}:{fid}", "label": f"{ticker} {f.label}"})
        for rid, r in led.ratios.items():
            new_inputs = [i.model_copy(update={"fact_id": f"{ticker}:{i.fact_id}"}) for i in r.inputs]
            ratios[f"{ticker}:{rid}"] = r.model_copy(
                update={"id": f"{ticker}:{rid}", "label": f"{ticker} {r.label}", "inputs": new_inputs}
            )
    primary = leds[tickers[0]].company
    combined_company = primary.model_copy(update={"name": "Comparison: " + ", ".join(tickers)})
    return Ledger(
        company=combined_company,
        years=sorted(years, reverse=True),
        facts=facts,
        ratios=ratios,
        missing=missing,
        reports_gross_margin=reports_gm,
    )

def build_ledger(client: EdgarClient, query: str, years: int = 5) -> Ledger:
    """Resolve ``query`` to a company and build its ledger for the last ``years`` years."""
    cik, ticker, name = resolve_cik(client, query)
    cik10 = f"{cik:010d}"

    submissions = client.submissions(cik10)
    company = _company_from_submissions(cik, ticker, name, submissions)

    companyfacts = client.company_facts(cik10)
    fb = build_facts(company, companyfacts, years=years)

    ratios = build_ratios(fb.facts, fb.fiscal_years, reports_gross_margin=fb.reports_gross_margin)

    return Ledger(
        company=company,
        years=fb.fiscal_years,
        facts=fb.facts,
        ratios=ratios,
        missing=fb.missing,
        reports_gross_margin=fb.reports_gross_margin,
    )

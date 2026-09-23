"""Fetch real companyfacts, trim to the tags Footnote uses, and save as test fixtures.

Run once (needs network + SEC_CONTACT_EMAIL) to (re)generate tests/fixtures/*.json.
Tests themselves never touch the network; they read these committed files.
"""

from __future__ import annotations

import json
from pathlib import Path

from footnote.edgar import EdgarClient, resolve_cik
from footnote.facts import CONCEPTS

FIXtures_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TICKERS = ["AAPL", "MSFT", "JPM", "KO", "NKE"]
MIN_END_YEAR = 2018

def wanted_tags() -> set[str]:
    tags: set[str] = set()
    for spec in CONCEPTS.values():
        tags.update(spec.tags)
    return tags

def trim(companyfacts: dict, keep_tags: set[str]) -> dict:
    out = {
        "cik": companyfacts.get("cik"),
        "entityName": companyfacts.get("entityName"),
        "facts": {"us-gaap": {}},
    }
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in keep_tags:
        node = usgaap.get(tag)
        if not node:
            continue
        trimmed_units = {}
        for unit, entries in node.get("units", {}).items():
            kept = [e for e in entries if str(e.get("end", "0"))[:4].isdigit()
                    and int(str(e.get("end"))[:4]) >= MIN_END_YEAR]
            if kept:
                trimmed_units[unit] = kept
        if trimmed_units:
            out["facts"]["us-gaap"][tag] = {
                "label": node.get("label"),
                "description": node.get("description"),
                "units": trimmed_units,
            }
    return out

def main() -> None:
    FIXtures_DIR.mkdir(parents=True, exist_ok=True)
    keep = wanted_tags()
    client = EdgarClient()
    index = {}
    for ticker in TICKERS:
        cik, tk, name = resolve_cik(client, ticker)
        facts = client.company_facts(f"{cik:010d}")
        trimmed = trim(facts, keep)
        path = FIXtures_DIR / f"{tk}_companyfacts.json"
        path.write_text(json.dumps(trimmed, separators=(",", ":")))
        index[tk] = {"cik": cik, "name": name, "file": path.name}
        size_kb = path.stat().st_size / 1024
        print(f"{tk}: cik={cik} tags={len(trimmed['facts']['us-gaap'])} size={size_kb:.0f}KB")
    (FIXtures_DIR / "index.json").write_text(json.dumps(index, indent=2))
    client.close()
    print("wrote", FIXtures_DIR / "index.json")

if __name__ == "__main__":
    main()

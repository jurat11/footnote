"""Shared test helpers. No network: everything reads committed fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_index() -> dict:
    return json.loads((FIXTURES / "index.json").read_text())


@pytest.fixture(scope="session")
def fixtures_index() -> dict:
    return load_index()


def load_companyfacts(ticker: str) -> dict:
    return json.loads((FIXTURES / f"{ticker}_companyfacts.json").read_text())


def offline_ledger(ticker: str, years: int = 5):
    """Build a full Ledger from a committed fixture, with no network access."""
    from footnote.facts import build_facts
    from footnote.models import Company, Ledger
    from footnote.ratios import build_ratios

    meta = load_index()[ticker]
    company = Company(ticker=ticker, cik=meta["cik"], name=meta["name"])
    cf = load_companyfacts(ticker)
    fb = build_facts(company, cf, years=years)
    ratios = build_ratios(fb.facts, fb.fiscal_years, reports_gross_margin=fb.reports_gross_margin)
    return Ledger(
        company=company,
        years=fb.fiscal_years,
        facts=fb.facts,
        ratios=ratios,
        missing=fb.missing,
        reports_gross_margin=fb.reports_gross_margin,
    )


def mkfact(concept: str, year: int, value: float, unit: str = "USD"):
    """Build a minimal Fact for ratio unit tests."""
    from footnote.models import Fact

    return Fact(
        id=f"{concept}:FY{year}",
        concept=concept,
        xbrl_tag="TestTag",
        label=concept,
        value=value,
        unit=unit,
        period_start=f"{year}-01-01",
        period_end=f"{year}-12-31",
        fiscal_year=year,
        accession="0000000000-00-000000",
        form="10-K",
        filed=f"{year + 1}-02-01",
        source_url="https://example.test/index.htm",
    )

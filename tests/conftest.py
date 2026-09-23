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

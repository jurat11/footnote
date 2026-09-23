"""Fact-selection tests against recorded fixtures. No network."""

from __future__ import annotations

from footnote.facts import build_facts
from footnote.models import Company
from tests.conftest import load_companyfacts, load_index


def _company(ticker: str) -> Company:
    idx = load_index()[ticker]
    return Company(ticker=ticker, cik=idx["cik"], name=idx["name"])

def test_apple_stable_annual_values():
    r = build_facts(_company("AAPL"), load_companyfacts("AAPL"), years=8)
    assert r.facts["revenue:FY2023"].value == 383_285_000_000
    assert r.facts["net_income:FY2023"].value == 96_995_000_000
    assert r.facts["revenue:FY2022"].value == 394_328_000_000

def test_fiscal_year_derived_from_period_end_not_fy_field():
    r = build_facts(_company("AAPL"), load_companyfacts("AAPL"), years=8)
    rev = r.facts["revenue:FY2023"]
    assert rev.fiscal_year == 2023
    assert rev.period_end.endswith("-09-30") or rev.period_end.startswith("2023-09")

def test_apple_records_tag_used_and_source_url():
    r = build_facts(_company("AAPL"), load_companyfacts("AAPL"), years=8)
    rev = r.facts["revenue:FY2023"]
    assert rev.xbrl_tag in {
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    }
    assert rev.source_url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
    assert rev.source_url.endswith("-index.htm")
    assert rev.form in {"10-K", "10-K/A"}

def test_nike_non_december_fiscal_year():
    r = build_facts(_company("NKE"), load_companyfacts("NKE"), years=5)
    any_year = r.fiscal_years[0]
    assert r.fy_end[any_year].month == 5
    assert f"revenue:FY{any_year}" in r.facts

def test_bank_has_no_cost_of_revenue_and_flags_gross_margin_off():
    r = build_facts(_company("JPM"), load_companyfacts("JPM"), years=3)
    assert r.reports_gross_margin is False
    missing_concepts = {m.concept for m in r.missing}
    assert "cost_of_revenue" in missing_concepts
    cor = next(m for m in r.missing if m.concept == "cost_of_revenue")
    assert "CostOfRevenue" in cor.tags_tried

def test_latest_filed_wins_for_restatement():
    """A synthetic companyfacts with two filings of the same period keeps the later one."""
    facts_json = {
        "cik": 1,
        "entityName": "Test Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 100,
                                "accn": "0000000000-24-000001",
                                "form": "10-K",
                                "filed": "2024-02-01",
                                "fy": 2023,
                            },
                            {
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 111,
                                "accn": "0000000000-25-000001",
                                "form": "10-K",
                                "filed": "2025-02-01",
                                "fy": 2024,
                            },
                        ]
                    }
                }
            }
        },
    }
    co = Company(ticker="TST", cik=1, name="Test Co")
    r = build_facts(co, facts_json, years=1)
    rev = r.facts["revenue:FY2023"]
    assert rev.value == 111
    assert rev.accession == "0000000000-25-000001"

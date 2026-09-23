"""Unit tests for every ratio, including the None (uncomputable) cases."""

from __future__ import annotations

import math

from footnote import ratios as R
from tests.conftest import mkfact


def approx(a, b, tol=1e-9):
    return a is not None and math.isclose(a, b, rel_tol=tol, abs_tol=tol)

def test_gross_margin():
    r = R.gross_margin(mkfact("revenue", 2024, 1000), mkfact("cost_of_revenue", 2024, 600), 2024)
    assert approx(r.value, 0.4)
    assert {i.role for i in r.inputs} == {"revenue", "cost_of_revenue"}
    assert "Revenue" in r.formula

def test_operating_and_net_margin():
    assert approx(R.operating_margin(mkfact("operating_income", 2024, 300), mkfact("revenue", 2024, 1000), 2024).value, 0.3)
    assert approx(R.net_margin(mkfact("net_income", 2024, 250), mkfact("revenue", 2024, 1000), 2024).value, 0.25)

def test_revenue_growth():
    r = R.revenue_growth(mkfact("revenue", 2024, 1200), mkfact("revenue", 2023, 1000), 2024)
    assert approx(r.value, 0.2)

def test_roe_and_roa():
    assert approx(R.roe(mkfact("net_income", 2024, 200), mkfact("stockholders_equity", 2024, 1000), 2024).value, 0.2)
    assert approx(R.roa(mkfact("net_income", 2024, 200), mkfact("total_assets", 2024, 4000), 2024).value, 0.05)

def test_current_ratio_and_asset_turnover():
    assert approx(R.current_ratio(mkfact("current_assets", 2024, 150), mkfact("current_liabilities", 2024, 100), 2024).value, 1.5)
    assert approx(R.asset_turnover(mkfact("revenue", 2024, 2000), mkfact("total_assets", 2024, 4000), 2024).value, 0.5)

def test_debt_to_equity_sums_components():
    r = R.debt_to_equity(mkfact("long_term_debt", 2024, 300), mkfact("current_debt", 2024, 100), mkfact("stockholders_equity", 2024, 800), 2024)
    assert approx(r.value, 0.5)
    assert r.reason is None
    assert {i.role for i in r.inputs} == {"long_term_debt", "current_debt", "stockholders_equity"}

def test_debt_to_equity_one_component_notes_omission():
    r = R.debt_to_equity(mkfact("long_term_debt", 2024, 400), None, mkfact("stockholders_equity", 2024, 800), 2024)
    assert approx(r.value, 0.5)
    assert r.reason is not None and "current debt" in r.reason

def test_free_cash_flow_and_margin():
    fcf = R.free_cash_flow(mkfact("operating_cash_flow", 2024, 500), mkfact("capex", 2024, 120), 2024)
    assert approx(fcf.value, 380)
    m = R.fcf_margin(fcf, mkfact("revenue", 2024, 1000), 2024)
    assert approx(m.value, 0.38)
    assert any(i.role == "free_cash_flow" for i in m.inputs)

def test_interest_coverage():
    r = R.interest_coverage(mkfact("operating_income", 2024, 900), mkfact("interest_expense", 2024, 100), 2024)
    assert approx(r.value, 9.0)

def test_missing_input_returns_none_with_reason():
    r = R.net_margin(None, mkfact("revenue", 2024, 1000), 2024)
    assert r.value is None
    assert "Missing" in r.reason

def test_division_by_zero_returns_none():
    r = R.operating_margin(mkfact("operating_income", 2024, 300), mkfact("revenue", 2024, 0), 2024)
    assert r.value is None
    assert "zero" in r.reason.lower()

def test_negative_equity_roe_returns_none():
    r = R.roe(mkfact("net_income", 2024, 200), mkfact("stockholders_equity", 2024, -50), 2024)
    assert r.value is None
    assert "equity" in r.reason.lower()

def test_zero_interest_expense_returns_none():
    r = R.interest_coverage(mkfact("operating_income", 2024, 900), mkfact("interest_expense", 2024, 0), 2024)
    assert r.value is None

def test_debt_to_equity_no_debt_returns_none():
    r = R.debt_to_equity(None, None, mkfact("stockholders_equity", 2024, 800), 2024)
    assert r.value is None
    assert "debt" in r.reason.lower()

def test_debt_to_equity_negative_equity_returns_none():
    r = R.debt_to_equity(mkfact("long_term_debt", 2024, 300), None, mkfact("stockholders_equity", 2024, -10), 2024)
    assert r.value is None

def test_revenue_growth_zero_prior_returns_none():
    r = R.revenue_growth(mkfact("revenue", 2024, 1000), mkfact("revenue", 2023, 0), 2024)
    assert r.value is None

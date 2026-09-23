"""Deterministic ratio calculations.

Pure functions, no I/O. Every ratio returns a ``Ratio`` that carries its formula
string and the ids of the facts it used, so its citation can list every filing it
depends on. A ratio that cannot be computed (division by zero, non-positive equity,
a missing input) returns a ``Ratio`` with ``value=None`` and a ``reason`` instead of a
number. Nothing here ever estimates.
"""

from __future__ import annotations

from .models import Fact, Ratio, RatioInput

PCT = "%"
X = "x"
USD = "USD"


def _inputs(**facts: Fact | None) -> list[RatioInput]:
    return [
        RatioInput(role=role, fact_id=f.id) for role, f in facts.items() if f is not None
    ]


def _missing(concept: str, label: str, unit: str, year: int, formula: str, which: str) -> Ratio:
    return Ratio(
        id=f"{concept}:FY{year}",
        concept=concept,
        label=label,
        fiscal_year=year,
        value=None,
        unit=unit,
        formula=formula,
        inputs=[],
        reason=f"Missing input(s): {which}.",
    )


def _ratio(
    concept: str,
    label: str,
    unit: str,
    year: int,
    value: float | None,
    formula: str,
    inputs: list[RatioInput],
    reason: str | None = None,
) -> Ratio:
    return Ratio(
        id=f"{concept}:FY{year}",
        concept=concept,
        label=label,
        fiscal_year=year,
        value=value,
        unit=unit,
        formula=formula,
        inputs=inputs,
        reason=reason,
    )


# --- margins ---------------------------------------------------------------
def gross_margin(revenue: Fact | None, cost_of_revenue: Fact | None, year: int) -> Ratio:
    label, concept = "Gross margin", "gross_margin"
    formula = "(Revenue - Cost of revenue) / Revenue"
    if revenue is None or cost_of_revenue is None:
        which = ", ".join(n for n, f in [("revenue", revenue), ("cost_of_revenue", cost_of_revenue)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if revenue.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(revenue=revenue, cost_of_revenue=cost_of_revenue),
                      reason="Revenue is zero.")
    value = (revenue.value - cost_of_revenue.value) / revenue.value
    return _ratio(concept, label, PCT, year, value, formula,
                  _inputs(revenue=revenue, cost_of_revenue=cost_of_revenue))


def operating_margin(operating_income: Fact | None, revenue: Fact | None, year: int) -> Ratio:
    label, concept = "Operating margin", "operating_margin"
    formula = "Operating income / Revenue"
    if operating_income is None or revenue is None:
        which = ", ".join(n for n, f in [("operating_income", operating_income), ("revenue", revenue)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if revenue.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(operating_income=operating_income, revenue=revenue),
                      reason="Revenue is zero.")
    return _ratio(concept, label, PCT, year, operating_income.value / revenue.value, formula,
                  _inputs(operating_income=operating_income, revenue=revenue))


def net_margin(net_income: Fact | None, revenue: Fact | None, year: int) -> Ratio:
    label, concept = "Net margin", "net_margin"
    formula = "Net income / Revenue"
    if net_income is None or revenue is None:
        which = ", ".join(n for n, f in [("net_income", net_income), ("revenue", revenue)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if revenue.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(net_income=net_income, revenue=revenue), reason="Revenue is zero.")
    return _ratio(concept, label, PCT, year, net_income.value / revenue.value, formula,
                  _inputs(net_income=net_income, revenue=revenue))


# --- growth ----------------------------------------------------------------
def revenue_growth(revenue: Fact | None, revenue_prior: Fact | None, year: int) -> Ratio:
    label, concept = "Revenue growth", "revenue_growth"
    formula = "(Revenue_FY - Revenue_prior) / Revenue_prior"
    if revenue is None or revenue_prior is None:
        which = ", ".join(n for n, f in [("revenue", revenue), ("revenue_prior", revenue_prior)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if revenue_prior.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(revenue=revenue, revenue_prior=revenue_prior),
                      reason="Prior-year revenue is zero.")
    value = (revenue.value - revenue_prior.value) / revenue_prior.value
    return _ratio(concept, label, PCT, year, value, formula,
                  _inputs(revenue=revenue, revenue_prior=revenue_prior))


# --- returns ---------------------------------------------------------------
def roe(net_income: Fact | None, equity: Fact | None, year: int) -> Ratio:
    label, concept = "Return on equity", "roe"
    formula = "Net income / Stockholders' equity"
    if net_income is None or equity is None:
        which = ", ".join(n for n, f in [("net_income", net_income), ("stockholders_equity", equity)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if equity.value <= 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(net_income=net_income, stockholders_equity=equity),
                      reason="Non-positive equity makes ROE meaningless.")
    return _ratio(concept, label, PCT, year, net_income.value / equity.value, formula,
                  _inputs(net_income=net_income, stockholders_equity=equity))


def roa(net_income: Fact | None, assets: Fact | None, year: int) -> Ratio:
    label, concept = "Return on assets", "roa"
    formula = "Net income / Total assets"
    if net_income is None or assets is None:
        which = ", ".join(n for n, f in [("net_income", net_income), ("total_assets", assets)] if f is None)
        return _missing(concept, label, PCT, year, formula, which)
    if assets.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      _inputs(net_income=net_income, total_assets=assets), reason="Total assets is zero.")
    return _ratio(concept, label, PCT, year, net_income.value / assets.value, formula,
                  _inputs(net_income=net_income, total_assets=assets))


# --- liquidity / leverage --------------------------------------------------
def current_ratio(current_assets: Fact | None, current_liabilities: Fact | None, year: int) -> Ratio:
    label, concept = "Current ratio", "current_ratio"
    formula = "Current assets / Current liabilities"
    if current_assets is None or current_liabilities is None:
        which = ", ".join(n for n, f in [("current_assets", current_assets), ("current_liabilities", current_liabilities)] if f is None)
        return _missing(concept, label, X, year, formula, which)
    if current_liabilities.value == 0:
        return _ratio(concept, label, X, year, None, formula,
                      _inputs(current_assets=current_assets, current_liabilities=current_liabilities),
                      reason="Current liabilities is zero.")
    return _ratio(concept, label, X, year, current_assets.value / current_liabilities.value, formula,
                  _inputs(current_assets=current_assets, current_liabilities=current_liabilities))


def debt_to_equity(
    long_term_debt: Fact | None, current_debt: Fact | None, equity: Fact | None, year: int
) -> Ratio:
    label, concept = "Debt to equity", "debt_to_equity"
    formula = "(Long-term debt + Current debt) / Stockholders' equity"
    if equity is None:
        return _missing(concept, label, X, year, formula, "stockholders_equity")
    debt_parts = {"long_term_debt": long_term_debt, "current_debt": current_debt}
    present = {k: v for k, v in debt_parts.items() if v is not None}
    if not present:
        return _ratio(concept, label, X, year, None, formula, _inputs(stockholders_equity=equity),
                      reason="No interest-bearing debt reported.")
    if equity.value <= 0:
        return _ratio(concept, label, X, year, None, formula,
                      _inputs(stockholders_equity=equity, **present),
                      reason="Non-positive equity makes debt-to-equity meaningless.")
    total_debt = sum(f.value for f in present.values())
    reason = None
    if len(present) < 2:
        omitted = "current debt" if "current_debt" not in present else "long-term debt"
        reason = f"Only part of debt reported; {omitted} component not separately tagged."
    return _ratio(concept, label, X, year, total_debt / equity.value, formula,
                  _inputs(stockholders_equity=equity, **present), reason=reason)


# --- cash generation -------------------------------------------------------
def free_cash_flow(operating_cash_flow: Fact | None, capex: Fact | None, year: int) -> Ratio:
    label, concept = "Free cash flow", "free_cash_flow"
    formula = "Cash from operations - Capital expenditures"
    if operating_cash_flow is None or capex is None:
        which = ", ".join(n for n, f in [("operating_cash_flow", operating_cash_flow), ("capex", capex)] if f is None)
        return _missing(concept, label, USD, year, formula, which)
    # capex is reported as a positive cash outflow, so we subtract it.
    value = operating_cash_flow.value - capex.value
    return _ratio(concept, label, USD, year, value, formula,
                  _inputs(operating_cash_flow=operating_cash_flow, capex=capex))


def fcf_margin(fcf: Ratio | None, revenue: Fact | None, year: int) -> Ratio:
    label, concept = "Free cash flow margin", "fcf_margin"
    formula = "Free cash flow / Revenue"
    if fcf is None or fcf.value is None or revenue is None:
        which = ", ".join(n for n, ok in [("free_cash_flow", fcf is not None and fcf.value is not None), ("revenue", revenue is not None)] if not ok)
        return _missing(concept, label, PCT, year, formula, which)
    if revenue.value == 0:
        return _ratio(concept, label, PCT, year, None, formula,
                      [RatioInput(role="free_cash_flow", fact_id=fcf.id), *_inputs(revenue=revenue)],
                      reason="Revenue is zero.")
    inputs = [RatioInput(role="free_cash_flow", fact_id=fcf.id), *_inputs(revenue=revenue)]
    return _ratio(concept, label, PCT, year, fcf.value / revenue.value, formula, inputs)


def interest_coverage(operating_income: Fact | None, interest_expense: Fact | None, year: int) -> Ratio:
    label, concept = "Interest coverage", "interest_coverage"
    formula = "Operating income / Interest expense"
    if operating_income is None or interest_expense is None:
        which = ", ".join(n for n, f in [("operating_income", operating_income), ("interest_expense", interest_expense)] if f is None)
        return _missing(concept, label, X, year, formula, which)
    if interest_expense.value == 0:
        return _ratio(concept, label, X, year, None, formula,
                      _inputs(operating_income=operating_income, interest_expense=interest_expense),
                      reason="Interest expense is zero.")
    return _ratio(concept, label, X, year, operating_income.value / interest_expense.value, formula,
                  _inputs(operating_income=operating_income, interest_expense=interest_expense))


def asset_turnover(revenue: Fact | None, assets: Fact | None, year: int) -> Ratio:
    label, concept = "Asset turnover", "asset_turnover"
    formula = "Revenue / Total assets"
    if revenue is None or assets is None:
        which = ", ".join(n for n, f in [("revenue", revenue), ("total_assets", assets)] if f is None)
        return _missing(concept, label, X, year, formula, which)
    if assets.value == 0:
        return _ratio(concept, label, X, year, None, formula,
                      _inputs(revenue=revenue, total_assets=assets), reason="Total assets is zero.")
    return _ratio(concept, label, X, year, revenue.value / assets.value, formula,
                  _inputs(revenue=revenue, total_assets=assets))


def build_ratios(
    facts: dict[str, Fact], fiscal_years: list[int], reports_gross_margin: bool = True
) -> dict[str, Ratio]:
    """Compute every ratio for every fiscal year. Returns ``{ratio_id: Ratio}``.

    Ratios that cannot be computed are still returned (with ``value=None`` and a
    reason) so the report can be honest about gaps.
    """
    ratios: dict[str, Ratio] = {}

    def f(concept: str, year: int) -> Fact | None:
        return facts.get(f"{concept}:FY{year}")

    for year in fiscal_years:
        if reports_gross_margin:
            r = gross_margin(f("revenue", year), f("cost_of_revenue", year), year)
            ratios[r.id] = r
        ratios_this = [
            operating_margin(f("operating_income", year), f("revenue", year), year),
            net_margin(f("net_income", year), f("revenue", year), year),
            revenue_growth(f("revenue", year), f("revenue", year - 1), year),
            roe(f("net_income", year), f("stockholders_equity", year), year),
            roa(f("net_income", year), f("total_assets", year), year),
            current_ratio(f("current_assets", year), f("current_liabilities", year), year),
            debt_to_equity(f("long_term_debt", year), f("current_debt", year), f("stockholders_equity", year), year),
        ]
        fcf = free_cash_flow(f("operating_cash_flow", year), f("capex", year), year)
        ratios_this.append(fcf)
        ratios_this.append(fcf_margin(fcf, f("revenue", year), year))
        ratios_this.append(interest_coverage(f("operating_income", year), f("interest_expense", year), year))
        ratios_this.append(asset_turnover(f("revenue", year), f("total_assets", year), year))
        for r in ratios_this:
            ratios[r.id] = r
    return ratios

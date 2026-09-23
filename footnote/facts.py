"""Turn a raw SEC companyfacts payload into a clean, deterministic fact ledger.

The rules here matter more than any cleverness downstream:

* Concept fallback map: each canonical concept tries several XBRL tags in order and
  records which one actually produced the number.
* Annual flow items (income statement, cash flow) come only from 10-K / 10-K/A
  filings whose period spans 350-380 days.
* Balance-sheet items are instant facts (no ``start``) whose ``end`` matches a fiscal
  year-end we discovered from the flow items.
* The fiscal year is derived from the period ``end`` date, never from the ``fy`` field
  (which is the fiscal year of the *reporting* filing, so comparatives are mislabeled).
* When several facts share a concept and period, the one with the latest ``filed`` date
  wins, which is how restatements are captured; that filing is the one we cite.
* A metric that cannot be found is recorded as missing with the tags we tried. We never
  estimate or fill a value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import config
from .models import Company, Fact, MissingMetric

FLOW = "flow"
INSTANT = "instant"

MIN_ANNUAL_DAYS = 350
MAX_ANNUAL_DAYS = 380
ANNUAL_FORMS = {"10-K", "10-K/A"}


@dataclass(frozen=True)
class ConceptSpec:
    """One canonical concept and the ordered XBRL tags it will try."""

    key: str
    label: str
    kind: str  # FLOW or INSTANT
    tags: tuple[str, ...]
    taxonomy: str = "us-gaap"


# Ordered fallback map. First tag that yields a value for a period wins.
CONCEPTS: dict[str, ConceptSpec] = {
    "revenue": ConceptSpec(
        "revenue",
        "Revenue",
        FLOW,
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        ),
    ),
    "cost_of_revenue": ConceptSpec(
        "cost_of_revenue",
        "Cost of revenue",
        FLOW,
        (
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
        ),
    ),
    "operating_income": ConceptSpec(
        "operating_income",
        "Operating income",
        FLOW,
        ("OperatingIncomeLoss",),
    ),
    "net_income": ConceptSpec(
        "net_income",
        "Net income",
        FLOW,
        ("NetIncomeLoss", "ProfitLoss"),
    ),
    "interest_expense": ConceptSpec(
        "interest_expense",
        "Interest expense",
        FLOW,
        (
            "InterestExpense",
            "InterestExpenseNonoperating",
            "InterestAndDebtExpense",
        ),
    ),
    "operating_cash_flow": ConceptSpec(
        "operating_cash_flow",
        "Cash from operations",
        FLOW,
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
    ),
    "capex": ConceptSpec(
        "capex",
        "Capital expenditures",
        FLOW,
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
    ),
    "total_assets": ConceptSpec(
        "total_assets", "Total assets", INSTANT, ("Assets",)
    ),
    "total_liabilities": ConceptSpec(
        "total_liabilities", "Total liabilities", INSTANT, ("Liabilities",)
    ),
    "stockholders_equity": ConceptSpec(
        "stockholders_equity",
        "Stockholders' equity",
        INSTANT,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
    ),
    "current_assets": ConceptSpec(
        "current_assets", "Current assets", INSTANT, ("AssetsCurrent",)
    ),
    "current_liabilities": ConceptSpec(
        "current_liabilities", "Current liabilities", INSTANT, ("LiabilitiesCurrent",)
    ),
    "long_term_debt": ConceptSpec(
        "long_term_debt",
        "Long-term debt",
        INSTANT,
        (
            "LongTermDebtNoncurrent",
            "LongTermDebt",
            "LongTermDebtAndCapitalLeaseObligations",
        ),
    ),
    "current_debt": ConceptSpec(
        "current_debt",
        "Current debt",
        INSTANT,
        (
            "LongTermDebtCurrent",
            "DebtCurrent",
            "ShortTermBorrowings",
        ),
    ),
}


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def _source_url(cik: int, accession: str) -> str:
    return config.FILING_INDEX_URL.format(
        cik=cik,
        accession_nodash=accession.replace("-", ""),
        accession=accession,
    )


def _units_for_tag(companyfacts: dict[str, Any], taxonomy: str, tag: str) -> dict[str, list[dict]]:
    return (
        companyfacts.get("facts", {})
        .get(taxonomy, {})
        .get(tag, {})
        .get("units", {})
    )


def _pick_unit(units: dict[str, list[dict]]) -> str | None:
    if not units:
        return None
    if "USD" in units:
        return "USD"
    return next(iter(units))


@dataclass
class _Selection:
    entry: dict
    tag: str
    unit: str


@dataclass
class FactBuildResult:
    facts: dict[str, Fact] = field(default_factory=dict)
    missing: list[MissingMetric] = field(default_factory=list)
    fiscal_years: list[int] = field(default_factory=list)
    fy_end: dict[int, date] = field(default_factory=dict)
    reports_gross_margin: bool = True


def _discover_fiscal_year_ends(companyfacts: dict[str, Any]) -> dict[int, date]:
    """Find fiscal year-end dates from annual (350-380 day) 10-K flow facts.

    Returns ``{fiscal_year: fiscal_year_end_date}``. The fiscal year is the calendar
    year of the period ``end`` date. When a year has several candidate end dates
    (rare), the most frequently reported one wins, ties broken by the latest date.
    """
    from collections import Counter

    per_year: dict[int, Counter] = {}
    for spec in CONCEPTS.values():
        if spec.kind != FLOW:
            continue
        for tag in spec.tags:
            units = _units_for_tag(companyfacts, spec.taxonomy, tag)
            unit = _pick_unit(units)
            if unit is None:
                continue
            for e in units[unit]:
                start = e.get("start")
                end = e.get("end")
                form = e.get("form")
                if not start or not end or form not in ANNUAL_FORMS:
                    continue
                span = (_parse(end) - _parse(start)).days
                if not (MIN_ANNUAL_DAYS <= span <= MAX_ANNUAL_DAYS):
                    continue
                end_d = _parse(end)
                per_year.setdefault(end_d.year, Counter())[end_d] += 1

    fy_end: dict[int, date] = {}
    for year, counter in per_year.items():
        # most_common breaks ties by insertion order, so sort for determinism.
        best = sorted(counter.items(), key=lambda kv: (kv[1], kv[0]))[-1][0]
        fy_end[year] = best
    return fy_end


def _select_flow(
    companyfacts: dict[str, Any], spec: ConceptSpec, year: int, fy_end: date
) -> _Selection | None:
    for tag in spec.tags:
        units = _units_for_tag(companyfacts, spec.taxonomy, tag)
        unit = _pick_unit(units)
        if unit is None:
            continue
        candidates = []
        for e in units[unit]:
            start, end, form = e.get("start"), e.get("end"), e.get("form")
            if not start or not end or form not in ANNUAL_FORMS:
                continue
            if _parse(end) != fy_end:
                continue
            span = (_parse(end) - _parse(start)).days
            if not (MIN_ANNUAL_DAYS <= span <= MAX_ANNUAL_DAYS):
                continue
            candidates.append(e)
        if candidates:
            best = max(candidates, key=lambda e: e.get("filed", ""))
            return _Selection(best, tag, unit)
    return None


def _select_instant(
    companyfacts: dict[str, Any], spec: ConceptSpec, fy_end: date
) -> _Selection | None:
    for tag in spec.tags:
        units = _units_for_tag(companyfacts, spec.taxonomy, tag)
        unit = _pick_unit(units)
        if unit is None:
            continue
        candidates = [
            e
            for e in units[unit]
            if not e.get("start") and e.get("end") and _parse(e["end"]) == fy_end
        ]
        if candidates:
            best = max(candidates, key=lambda e: e.get("filed", ""))
            return _Selection(best, tag, unit)
    return None


def build_facts(
    company: Company, companyfacts: dict[str, Any], years: int = 5
) -> FactBuildResult:
    """Build the fact set for the most recent ``years`` fiscal years."""
    result = FactBuildResult()
    fy_end = _discover_fiscal_year_ends(companyfacts)
    if not fy_end:
        return result

    target_years = sorted(fy_end, reverse=True)[:years]
    result.fiscal_years = target_years
    result.fy_end = {y: fy_end[y] for y in target_years}

    has_cost_of_revenue = False
    for year in target_years:
        end_d = fy_end[year]
        for spec in CONCEPTS.values():
            sel = (
                _select_flow(companyfacts, spec, year, end_d)
                if spec.kind == FLOW
                else _select_instant(companyfacts, spec, end_d)
            )
            fact_id = f"{spec.key}:FY{year}"
            if sel is None:
                result.missing.append(
                    MissingMetric(
                        concept=spec.key,
                        label=spec.label,
                        fiscal_year=year,
                        tags_tried=list(spec.tags),
                        note="No matching XBRL fact for this fiscal year.",
                    )
                )
                continue
            e = sel.entry
            result.facts[fact_id] = Fact(
                id=fact_id,
                concept=spec.key,
                xbrl_tag=sel.tag,
                label=spec.label,
                value=float(e["val"]),
                unit=sel.unit,
                period_start=e.get("start"),
                period_end=e["end"],
                fiscal_year=year,
                accession=e["accn"],
                form=e["form"],
                filed=e["filed"],
                source_url=_source_url(company.cik, e["accn"]),
            )
            if spec.key == "cost_of_revenue":
                has_cost_of_revenue = True

    result.reports_gross_margin = has_cost_of_revenue
    return result

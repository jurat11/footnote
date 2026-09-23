"""The agent's tools.

Each tool is a plain Python function over a shared :class:`ToolContext`. The template
engine calls them directly; the LLM engines expose them via their native tool-use APIs.
Either way the same code builds the ledger, so numbers can only ever come from here.
"""

from __future__ import annotations

from typing import Any

from .edgar import EdgarClient
from .ledger import build_ledger
from .models import Ledger
from .runlog import RunLogger


class ToolContext:
    """Holds the SEC client, the requested horizon, a per-ticker ledger cache and the log."""

    def __init__(self, client: EdgarClient, years: int, logger: RunLogger) -> None:
        self.client = client
        self.years = years
        self.logger = logger
        self._ledgers: dict[str, Ledger] = {}

    def ledger(self, ticker: str) -> Ledger:
        key = ticker.upper()
        if key not in self._ledgers:
            self._ledgers[key] = build_ledger(self.client, key, years=self.years)
        return self._ledgers[key]

def resolve_company(ctx: ToolContext, query: str) -> dict[str, Any]:
    led = ctx.ledger(query)
    c = led.company
    out = {
        "ticker": c.ticker,
        "cik": c.cik,
        "name": c.name,
        "sic": c.sic,
        "industry": c.sic_description,
    }
    ctx.logger.log("tool", name="resolve_company", args={"query": query}, result=out)
    return out

def get_financials(ctx: ToolContext, ticker: str, years: int | None = None) -> dict[str, Any]:
    led = ctx.ledger(ticker)
    facts = [
        {
            "id": f.id,
            "concept": f.concept,
            "label": f.label,
            "value": f.value,
            "unit": f.unit,
            "fiscal_year": f.fiscal_year,
            "period_end": f.period_end,
            "form": f.form,
        }
        for f in sorted(led.facts.values(), key=lambda x: (x.concept, -x.fiscal_year))
    ]
    out = {
        "ticker": led.company.ticker,
        "fiscal_years": led.years,
        "reports_gross_margin": led.reports_gross_margin,
        "facts": facts,
    }
    ctx.logger.log("tool", name="get_financials", args={"ticker": ticker}, result_summary={"n_facts": len(facts)})
    return out

def compute_ratios(ctx: ToolContext, ticker: str) -> dict[str, Any]:
    led = ctx.ledger(ticker)
    ratios = [
        {
            "id": r.id,
            "concept": r.concept,
            "label": r.label,
            "fiscal_year": r.fiscal_year,
            "value": r.value,
            "unit": r.unit,
            "formula": r.formula,
            "inputs": [i.fact_id for i in r.inputs],
            "reason": r.reason,
        }
        for r in sorted(led.ratios.values(), key=lambda x: (x.concept, -x.fiscal_year))
    ]
    out = {"ticker": led.company.ticker, "ratios": ratios}
    ctx.logger.log("tool", name="compute_ratios", args={"ticker": ticker}, result_summary={"n_ratios": len(ratios)})
    return out

def compare_companies(
    ctx: ToolContext, tickers: list[str], metric_ids: list[str] | None = None
) -> dict[str, Any]:
    """Align metrics across companies at each company's most recent fiscal year.

    ``metric_ids`` are concept keys (e.g. ["revenue", "net_margin"]). The table maps
    each metric to the ledger id (fact or ratio) for that concept per company, so the
    report cites real filings, never a recomputed cross-company number.
    """
    default_metrics = ["revenue", "net_margin", "revenue_growth", "roe", "free_cash_flow", "debt_to_equity"]
    metrics = metric_ids or default_metrics
    table: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        table[metric] = {}
        for t in tickers:
            led = ctx.ledger(t)
            year = led.years[0] if led.years else None
            token_id = f"{metric}:FY{year}" if year is not None else None
            kind = "F" if token_id in led.facts else ("R" if token_id in led.ratios else None)
            entry = None
            if kind == "F":
                f = led.facts[token_id]
                entry = {"id": token_id, "token": f"{{{{F:{t.upper()}:{token_id}}}}}",
                         "kind": "F", "value": f.value, "unit": f.unit, "fiscal_year": year}
            elif kind == "R":
                r = led.ratios[token_id]
                entry = {"id": token_id, "token": f"{{{{R:{t.upper()}:{token_id}}}}}",
                         "kind": "R", "value": r.value, "unit": r.unit, "fiscal_year": year, "reason": r.reason}
            table[metric][t.upper()] = entry
    out = {"tickers": [t.upper() for t in tickers], "metrics": metrics, "table": table}
    ctx.logger.log("tool", name="compare_companies", args={"tickers": tickers, "metric_ids": metrics})
    return out

def list_missing(ctx: ToolContext, ticker: str) -> dict[str, Any]:
    led = ctx.ledger(ticker)
    missing = [
        {"concept": m.concept, "label": m.label, "fiscal_year": m.fiscal_year, "tags_tried": m.tags_tried, "note": m.note}
        for m in led.missing
    ]
    out = {"ticker": led.company.ticker, "missing": missing}
    ctx.logger.log("tool", name="list_missing", args={"ticker": ticker}, result_summary={"n_missing": len(missing)})
    return out

TOOL_FUNCTIONS = {
    "resolve_company": resolve_company,
    "get_financials": get_financials,
    "compute_ratios": compute_ratios,
    "compare_companies": compare_companies,
    "list_missing": list_missing,
}

def dispatch(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(ctx, **arguments)
    except Exception as exc:
        ctx.logger.log("tool_error", name=name, args=arguments, error=str(exc))
        return {"error": str(exc)}

TOOL_SCHEMAS = [
    {
        "name": "resolve_company",
        "description": "Resolve a ticker or company name to ticker, CIK, name, SIC code and industry.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Ticker or company name"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_financials",
        "description": "Build the fact ledger for a company and return fact ids with values, units and periods.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "years": {"type": "integer", "description": "Number of fiscal years (optional)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "compute_ratios",
        "description": "Return ratio ids with values, formulas and input fact ids for a company.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "compare_companies",
        "description": "Return an aligned table of ledger ids across companies for the given metric concepts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}},
                "metric_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "list_missing",
        "description": "List metrics that could not be found, with the XBRL tags that were tried.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
]

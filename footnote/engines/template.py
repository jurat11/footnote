"""The default writer: a deterministic, rule-based engine that costs nothing.

It is not a language model. It selects facts and ratios from the ledger and composes
the six report sections using only ``{{F:...}}`` / ``{{R:...}}`` tokens for every
number, plus comparative words (\"rose\", \"declined\") that the code derives from the
underlying values. Because it never emits a raw digit, it passes the identical verifier
the LLM engines are held to. Swap in an LLM engine and nothing else in the pipeline
changes.
"""

from __future__ import annotations

from ..models import Ledger
from ..tools import (
    ToolContext,
    compute_ratios,
    get_financials,
    list_missing,
    resolve_company,
)
from .base import Engine, ReportRequest


def _tf(led: Ledger, concept: str, year: int, ns: str | None = None) -> str | None:
    if f"{concept}:FY{year}" not in led.facts:
        return None
    prefix = f"{ns}:" if ns else ""
    return f"{{{{F:{prefix}{concept}:FY{year}}}}}"

def _tr(led: Ledger, concept: str, year: int, require_value: bool = True, ns: str | None = None) -> str | None:
    r = led.ratios.get(f"{concept}:FY{year}")
    if r is None:
        return None
    if require_value and r.value is None:
        return None
    prefix = f"{ns}:" if ns else ""
    return f"{{{{R:{prefix}{concept}:FY{year}}}}}"

def _rval(led: Ledger, concept: str, year: int) -> float | None:
    r = led.ratios.get(f"{concept}:FY{year}")
    return r.value if r else None

def _fval(led: Ledger, concept: str, year: int) -> float | None:
    f = led.facts.get(f"{concept}:FY{year}")
    return f.value if f else None

def _direction(cur: float | None, prev: float | None) -> str:
    if cur is None or prev is None:
        return "changed"
    if prev == 0:
        return "changed"
    ratio = cur / prev
    if ratio > 1.02:
        return "rose"
    if ratio < 0.98:
        return "declined"
    return "was little changed"

def _trend(led: Ledger, concept: str, is_ratio: bool = False) -> str:
    years = sorted(led.years)
    getter = _rval if is_ratio else _fval
    vals = [getter(led, concept, y) for y in years]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return "held steady"
    first, last = vals[0], vals[-1]
    if last > first * 1.05:
        return "trended higher over the period"
    if last < first * 0.95:
        return "trended lower over the period"
    return "stayed broadly flat over the period"

class TemplateEngine(Engine):
    name = "template"

    def generate(self, ctx: ToolContext, request: ReportRequest) -> str:
        for t in request.tickers:
            resolve_company(ctx, t)
            get_financials(ctx, t)
            compute_ratios(ctx, t)
            list_missing(ctx, t)
        ctx.logger.log("engine", name=self.name, mode=request.mode, tickers=request.tickers)

        if request.mode == "compare":
            return self._compose_comparison(ctx, request)
        return self._compose_analysis(ctx.ledger(request.primary))

    def repair(self, ctx: ToolContext, request: ReportRequest, previous: str, violations: str) -> str:
        ctx.logger.log("engine_repair", name=self.name, note="regenerate (deterministic)")
        return self.generate(ctx, request)

    def _compose_analysis(self, led: Ledger) -> str:
        name = led.company.name
        industry = led.company.sic_description or "an unclassified industry"
        y = led.years[0]
        prior = y - 1
        p: list[str] = [f"# {name} ({led.company.ticker}) — SEC filing analysis", ""]

        p.append("## Summary")
        s = [f"{name} operates in {industry}."]
        rev, ni = _tf(led, "revenue", y), _tf(led, "net_income", y)
        if rev and ni:
            s.append(f"In FY{y} it reported revenue of {rev} and net income of {ni}.")
        elif rev:
            s.append(f"In FY{y} it reported revenue of {rev}.")
        nm = _tr(led, "net_margin", y)
        if nm:
            s.append(f"That is a net margin of {nm}.")
        rg = _tr(led, "revenue_growth", y)
        if rg:
            d = _direction(_fval(led, "revenue", y), _fval(led, "revenue", prior))
            s.append(f"Revenue {d} versus FY{prior} ({rg}).")
        p.append(" ".join(s))
        p.append("")

        p.append("## Profitability")
        s = []
        if led.reports_gross_margin:
            gm = _tr(led, "gross_margin", y)
            if gm:
                s.append(f"Gross margin was {gm} in FY{y}; it {_trend(led, 'gross_margin', True)}.")
        else:
            s.append("The company reports no cost of revenue (typical of banks and insurers), so gross margin is not applicable.")
        om, nmg = _tr(led, "operating_margin", y), _tr(led, "net_margin", y)
        if om:
            s.append(f"Operating margin stood at {om}.")
        if nmg:
            s.append(f"Net margin was {nmg}.")
        roe, roa = _tr(led, "roe", y), _tr(led, "roa", y)
        if roe:
            s.append(f"Return on equity was {roe}")
            if roa:
                s.append(f"and return on assets {roa}.")
            else:
                s[-1] += "."
        elif roa:
            s.append(f"Return on assets was {roa}.")
        p.append(" ".join(s) if s else "Profitability metrics were not available for this filer.")
        p.append("")

        p.append("## Growth")
        s = []
        rg_tokens = [(_tr(led, "revenue_growth", yr), yr) for yr in led.years]
        rg_tokens = [(tk, yr) for tk, yr in rg_tokens if tk]
        if rg_tokens:
            latest_tok = rg_tokens[0][0]
            s.append(f"Year-over-year revenue growth was {latest_tok} in FY{y}.")
            s.append(f"Across the reported years, revenue {_trend(led, 'revenue')}.")
            rev_old = _tf(led, "revenue", led.years[-1])
            if rev_old and rev:
                s.append(f"Revenue moved from {rev_old} in FY{led.years[-1]} to {rev} in FY{y}.")
        else:
            s.append("Not enough consecutive years were available to state a revenue growth rate.")
        p.append(" ".join(s))
        p.append("")

        p.append("## Balance sheet strength")
        s = []
        cr = _tr(led, "current_ratio", y)
        if cr:
            crv = _rval(led, "current_ratio", y)
            liquidity = "current assets exceed current liabilities" if crv and crv >= 1 else "current liabilities exceed current assets"
            s.append(f"The current ratio was {cr}, meaning {liquidity}.")
        de = _tr(led, "debt_to_equity", y)
        if de:
            s.append(f"Debt to equity was {de}; leverage {_trend(led, 'debt_to_equity', True)}.")
        else:
            de_ratio = led.ratios.get(f"debt_to_equity:FY{y}")
            if de_ratio and de_ratio.reason:
                s.append(f"Debt to equity could not be computed ({de_ratio.reason.lower()}).")
        eq, assets = _tf(led, "stockholders_equity", y), _tf(led, "total_assets", y)
        if eq and assets:
            s.append(f"Total assets were {assets} against stockholders' equity of {eq}.")
        p.append(" ".join(s) if s else "Balance-sheet detail was limited for this filer.")
        p.append("")

        p.append("## Cash generation")
        s = []
        ocf, capex, fcf = _tf(led, "operating_cash_flow", y), _tf(led, "capex", y), _tr(led, "free_cash_flow", y)
        if ocf:
            s.append(f"Cash from operations was {ocf} in FY{y}.")
        if capex and fcf:
            s.append(f"After capital expenditures of {capex}, free cash flow was {fcf}.")
        elif fcf:
            s.append(f"Free cash flow was {fcf}.")
        fm = _tr(led, "fcf_margin", y)
        if fm:
            s.append(f"That is a free cash flow margin of {fm}.")
        ic = _tr(led, "interest_coverage", y)
        if ic:
            s.append(f"Operating income covered interest expense {ic} over.")
        else:
            ic_ratio = led.ratios.get(f"interest_coverage:FY{y}")
            if ic_ratio and ic_ratio.reason:
                s.append(f"Interest coverage was not available ({ic_ratio.reason.lower()}).")
        p.append(" ".join(s) if s else "Cash-flow detail was limited for this filer.")
        p.append("")

        p.append("## What the data cannot tell you")
        s = self._gaps_prose(led)
        p.append(" ".join(s))
        p.append("")
        return "\n".join(p)

    def _gaps_prose(self, led: Ledger) -> list[str]:
        s = []
        missing_concepts = sorted({m.concept.replace("_", " ") for m in led.missing})
        if missing_concepts:
            s.append(
                "Some metrics were not separately tagged in this company's XBRL filings and are omitted rather than estimated: "
                + ", ".join(missing_concepts)
                + "."
            )
        if not led.reports_gross_margin:
            s.append("As a financial-sector filer it reports no cost of revenue, so the gross-margin-based view is unavailable.")
        s.append(
            "These filings also cannot speak to forward guidance, segment-level economics, unit volumes, pricing power, "
            "competitive position, or management quality. They are a backward-looking, GAAP view of what was reported, "
            "and every figure above is cited to the exact 10-K it came from."
        )
        return s

    def _compose_comparison(self, ctx: ToolContext, request: ReportRequest) -> str:
        tickers = [t.upper() for t in request.tickers]
        leds = {t: ctx.ledger(t) for t in tickers}
        p: list[str] = [f"# Comparison: {', '.join(tickers)}", ""]

        p.append("## Summary")
        s = ["This report compares " + ", ".join(tickers) + " on their most recent reported fiscal years."]
        for t in tickers:
            led = leds[t]
            y = led.years[0]
            rev = _tf(led, "revenue", y, ns=t)
            if rev:
                s.append(f"{led.company.name} ({t}) had FY{y} revenue of {rev}.")
        p.append(" ".join(s))
        p.append("")

        p.append("## Profitability")
        s = []
        for t in tickers:
            led = leds[t]
            y = led.years[0]
            nm = _tr(led, "net_margin", y, ns=t)
            om = _tr(led, "operating_margin", y, ns=t)
            bits = [f"{t}:"]
            if om:
                bits.append(f"operating margin {om}")
            if nm:
                bits.append(f"and net margin {nm}")
            if len(bits) > 1:
                s.append(" ".join(bits) + f" (FY{y}).")
        p.append(" ".join(s) if s else "Profitability metrics were unavailable.")
        p.append("")

        p.append("## Growth")
        s = []
        for t in tickers:
            led = leds[t]
            y = led.years[0]
            rg = _tr(led, "revenue_growth", y, ns=t)
            if rg:
                s.append(f"{t} grew revenue {rg} in FY{y}.")
        p.append(" ".join(s) if s else "Growth rates were unavailable.")
        p.append("")

        p.append("## Balance sheet strength")
        s = []
        for t in tickers:
            led = leds[t]
            y = led.years[0]
            cr, de = _tr(led, "current_ratio", y, ns=t), _tr(led, "debt_to_equity", y, ns=t)
            bits = [f"{t}:"]
            if cr:
                bits.append(f"current ratio {cr}")
            if de:
                bits.append(f"debt to equity {de}")
            if len(bits) > 1:
                s.append(" ".join(bits) + f" (FY{y}).")
        p.append(" ".join(s) if s else "Balance-sheet metrics were unavailable.")
        p.append("")

        p.append("## Cash generation")
        s = []
        for t in tickers:
            led = leds[t]
            y = led.years[0]
            fcf, fm = _tr(led, "free_cash_flow", y, ns=t), _tr(led, "fcf_margin", y, ns=t)
            bits = [f"{t}:"]
            if fcf:
                bits.append(f"free cash flow {fcf}")
            if fm:
                bits.append(f"at a margin of {fm}")
            if len(bits) > 1:
                s.append(" ".join(bits) + f" (FY{y}).")
        p.append(" ".join(s) if s else "Cash-flow metrics were unavailable.")
        p.append("")

        p.append("## What the data cannot tell you")
        s = ["Cross-company comparison from XBRL has real limits: fiscal years differ, tag choices vary by filer, "
             "and banks report a reduced set of ratios."]
        for t in tickers:
            led = leds[t]
            if not led.reports_gross_margin:
                s.append(f"{t} is a financial-sector filer with no cost of revenue, so gross margin is omitted for it.")
        s.append("None of these filings reveal guidance, segment economics or competitive dynamics. Every number above is cited to a specific 10-K.")
        p.append(" ".join(s))
        p.append("")
        return "\n".join(p)

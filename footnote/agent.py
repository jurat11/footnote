"""Orchestration: pick an engine, run it, verify the output, repair on failure, and
write the report bundle. This is the whole agent loop, written out so every line is
inspectable; there is no framework hiding control flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from .edgar import EdgarClient
from .engines import get_engine
from .engines.base import ReportRequest
from .ledger import build_ledger, combine_ledgers
from .models import Ledger
from .render import render
from .runlog import RunLogger
from .tools import ToolContext
from .verify import VerificationResult, format_violations, verify


@dataclass
class RunOutput:
    ledger: Ledger
    markdown: str
    html: str
    verification: VerificationResult
    out_dir: Path
    retries: int
    tool_calls: int
    engine: str

class VerificationFailed(RuntimeError):
    """Raised when a report still contains uncited numbers after all retries."""

class NoDataError(RuntimeError):
    """Raised when a company has no usable annual XBRL facts to analyze."""

def _run(request: ReportRequest, out_dir: str, engine_name: str) -> RunOutput:
    logger = RunLogger()
    logger.log("run_start", mode=request.mode, tickers=request.tickers, years=request.years,
               engine=engine_name)
    engine = get_engine(engine_name)

    with EdgarClient() as client:
        ctx = ToolContext(client, years=request.years, logger=logger)

        for t in request.tickers:
            led = ctx.ledger(t)
            if not led.facts:
                logger.log("no_data", ticker=t)
                raise NoDataError(
                    f"No usable annual XBRL facts found for {t} "
                    f"(CIK {led.company.cik}). The ticker may map to a holding or shell "
                    f"entity, or the filer does not report US-GAAP 10-K XBRL."
                )

        text = engine.generate(ctx, request)
        if request.mode == "compare":
            primary = combine_ledgers({t.upper(): ctx.ledger(t) for t in request.tickers})
        else:
            primary = ctx.ledger(request.primary)

        result = verify(text, primary)
        retries = 0
        while not result.ok and retries < config.MAX_VERIFY_RETRIES:
            retries += 1
            logger.log("verify_retry", attempt=retries, violations=result.to_dict())
            violations = format_violations(result)
            text = engine.repair(ctx, request, text, violations)
            result = verify(text, primary)

        if not result.ok:
            logger.log("verify_failed", violations=result.to_dict())
            raise VerificationFailed(
                f"Report still had uncited numbers after {retries} retries:\n"
                f"{format_violations(result)}"
            )

        rendered = render(text, primary)
        out = _write_bundle(request, primary, rendered, result, out_dir)
        tool_calls = engine_tool_call_count(logger)
        logger.log("run_done", ok=result.ok, retries=retries, tool_calls=tool_calls,
                   out_dir=str(out))
        return RunOutput(
            ledger=primary,
            markdown=rendered.markdown,
            html=rendered.html,
            verification=result,
            out_dir=out,
            retries=retries,
            tool_calls=tool_calls,
            engine=engine.name,
        )

def engine_tool_call_count(logger: RunLogger) -> int:
    try:
        n = 0
        for line in logger.path.read_text().splitlines():
            if json.loads(line).get("kind") == "tool":
                n += 1
        return n
    except OSError:
        return 0

def _write_bundle(
    request: ReportRequest, ledger: Ledger, rendered, verification, out_dir: str
) -> Path:
    base = Path(out_dir)
    slug = request.primary.upper() if request.mode == "analyze" else "-".join(t.upper() for t in request.tickers)
    dest = base / slug
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "report.md").write_text(rendered.markdown, encoding="utf-8")
    (dest / "report.html").write_text(rendered.html, encoding="utf-8")
    (dest / "ledger.json").write_text(ledger.model_dump_json(indent=2), encoding="utf-8")
    (dest / "verification.json").write_text(
        json.dumps(verification.to_dict(), indent=2), encoding="utf-8"
    )
    footnotes = [
        {"number": fn.number, "token_id": fn.token_id, "kind": fn.kind, "value": fn.value_text}
        for fn in rendered.footnotes
    ]
    (dest / "footnotes.json").write_text(json.dumps(footnotes, indent=2), encoding="utf-8")
    return dest

def run_analysis(query: str, years: int = 5, out_dir: str = "reports/", engine: str | None = None) -> RunOutput:
    with EdgarClient() as client:
        led = build_ledger(client, query, years=years)
    ticker = led.company.ticker
    request = ReportRequest(mode="analyze", primary=ticker, tickers=[ticker], years=years)
    out = _run(request, out_dir, engine or config.engine_name())
    _print_summary(out)
    return out

def run_comparison(tickers: list[str], years: int = 5, out_dir: str = "reports/", engine: str | None = None) -> RunOutput:
    with EdgarClient() as client:
        resolved = [build_ledger(client, t, years=years).company.ticker for t in tickers]
    request = ReportRequest(mode="compare", primary=resolved[0], tickers=resolved, years=years)
    out = _run(request, out_dir, engine or config.engine_name())
    _print_summary(out)
    return out

def _print_summary(out: RunOutput) -> None:
    print(f"\nEngine: {out.engine}")
    print(f"Verification: {'PASS' if out.verification.ok else 'FAIL'} "
          f"({out.verification.token_count} tokens, {out.retries} retries)")
    print(f"Wrote: {out.out_dir}/report.md, report.html, ledger.json, verification.json\n")

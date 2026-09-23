"""Run the full agent over the eval universe and record quality metrics.

For each ticker: uncited numbers (target 0), verifier retries, tool calls, token
usage, cost and runtime. With the default template engine token usage and cost are 0,
so the eval runs for free; point it at an LLM engine to measure that path.

Usage:
    python scripts/eval.py                       # 25 tickers, template engine
    python scripts/eval.py --engine anthropic    # measure the paid path
    python scripts/eval.py AAPL MSFT             # a subset
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from footnote import config
from footnote.agent import VerificationFailed, run_analysis
from footnote.evallist import EVAL_TICKERS

OUT = Path(__file__).resolve().parent.parent / "eval"

def _token_usage(run_path: Path) -> tuple[int, int]:
    """Sum input/output tokens from a run log (0 for the template engine)."""
    inp = outp = 0
    try:
        for line in run_path.read_text().splitlines():
            rec = json.loads(line)
            usage = rec.get("usage")
            if isinstance(usage, dict):
                inp += usage.get("input", 0) or 0
                outp += usage.get("output", 0) or 0
    except OSError:
        pass
    return inp, outp

def main() -> None:
    args = [a for a in sys.argv[1:]]
    engine = config.engine_name()
    if "--engine" in args:
        i = args.index("--engine")
        engine = args[i + 1]
        del args[i : i + 2]
    tickers = [t.upper() for t in args] or EVAL_TICKERS

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in tickers:
        start = time.time()
        try:
            out = run_analysis(t, years=5, out_dir=str(OUT / "reports"), engine=engine)
            elapsed = time.time() - start
            uncited = sum(1 for v in out.verification.violations if v.kind == "uncited_number")
            logs = sorted(config.RUNS_DIR.glob("*.jsonl"))
            inp, outp = _token_usage(logs[-1]) if logs else (0, 0)
            rows.append({
                "ticker": t, "ok": out.verification.ok, "uncited": uncited,
                "retries": out.retries, "tool_calls": out.tool_calls,
                "tokens_in": inp, "tokens_out": outp, "seconds": round(elapsed, 1),
                "engine": out.engine,
            })
            print(f"{t}: ok={out.verification.ok} uncited={uncited} retries={out.retries} "
                  f"tools={out.tool_calls} {elapsed:.1f}s")
        except (VerificationFailed, Exception) as exc:
            rows.append({"ticker": t, "ok": False, "uncited": "-", "retries": "-",
                         "tool_calls": "-", "tokens_in": "-", "tokens_out": "-",
                         "seconds": round(time.time() - start, 1), "engine": engine, "error": str(exc)})
            print(f"{t}: ERROR {exc}")

    lines = ["# Eval results", "",
             f"Engine: `{engine}`  ·  Tickers: {len(tickers)}", "",
             "| Ticker | OK | Uncited | Retries | Tool calls | Tokens in | Tokens out | Seconds |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['ticker']} | {'yes' if r['ok'] else 'NO'} | {r['uncited']} | {r['retries']} | "
            f"{r['tool_calls']} | {r['tokens_in']} | {r['tokens_out']} | {r['seconds']} |"
        )
    total_uncited = sum(r["uncited"] for r in rows if isinstance(r["uncited"], int))
    passed = sum(1 for r in rows if r["ok"])
    first_draft = sum(1 for r in rows if r["ok"] and r["retries"] == 0)
    retried = sum(1 for r in rows if isinstance(r["retries"], int) and r["retries"] > 0)
    total_in = sum(r["tokens_in"] for r in rows if isinstance(r["tokens_in"], int))
    total_out = sum(r["tokens_out"] for r in rows if isinstance(r["tokens_out"], int))
    lines += [
        "",
        f"**{passed}/{len(rows)} reports passed verification.**",
        "",
        f"- Passed on the first draft: {first_draft}/{len(rows)}",
        f"- Needed at least one verifier repair: {retried}/{len(rows)}",
        f"- Uncited numbers after repair: {total_uncited} (target 0)",
        f"- Model tokens used: {total_in:,} in / {total_out:,} out",
        "",
    ]
    out_path = OUT / (f"eval_{engine}.md" if engine != "template" else "eval.md")
    out_path.write_text("\n".join(lines))
    print("\nWrote", out_path)

if __name__ == "__main__":
    main()

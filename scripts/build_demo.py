"""Generate the committed demo report bundles the public Streamlit app loads.

Runs the free template engine over ten diverse tickers and writes each bundle into
demo/<TICKER>/. Commit the output so the demo works with no API key and no live SEC
calls. Re-run to refresh.

Usage:
    python scripts/build_demo.py
"""

from __future__ import annotations

from pathlib import Path

from footnote.agent import run_analysis

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
DEMO_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "KO", "JNJ", "WMT", "NKE"]

def main() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for t in DEMO_TICKERS:
        out = run_analysis(t, years=5, out_dir=str(DEMO_DIR), engine="template")
        print(f"demo: {t} -> {out.out_dir} (verified {out.verification.ok})")
    (DEMO_DIR / "index.json").write_text(__import__("json").dumps(DEMO_TICKERS, indent=2))
    print("wrote", DEMO_DIR / "index.json")

if __name__ == "__main__":
    main()

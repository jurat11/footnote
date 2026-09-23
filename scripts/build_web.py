"""Stage the committed demo report bundles into web/data/ for the static site.

The Vercel deployment is a pure static frontend: it loads these pre-computed, verified
report bundles (report.md, ledger.json, footnotes.json) and renders them client-side.
No server, no API key, no live SEC calls needed for the demo.

Usage:
    python scripts/build_web.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
WEB_DATA = ROOT / "web" / "data"

FILES = ["report.md", "ledger.json", "footnotes.json", "verification.json"]

def main() -> None:
    tickers = json.loads((DEMO / "index.json").read_text())
    if WEB_DATA.exists():
        shutil.rmtree(WEB_DATA)
    WEB_DATA.mkdir(parents=True)
    (WEB_DATA / "index.json").write_text(json.dumps(tickers, indent=2))
    for t in tickers:
        dest = WEB_DATA / t
        dest.mkdir()
        for name in FILES:
            src = DEMO / t / name
            if src.exists():
                shutil.copy(src, dest / name)
        print(f"staged {t}")
    print("wrote", WEB_DATA)

if __name__ == "__main__":
    main()

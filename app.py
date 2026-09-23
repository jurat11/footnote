"""Footnote — Streamlit app.

Report on the left, ledger table on the right. Selecting a footnote highlights the
ledger row it cites. Two modes:

* Cached demo (default): loads committed report bundles from demo/ for ten tickers, so
  the public demo works with no API key and no live SEC calls.
* Live: builds a fresh report. It uses the free template engine by default (no key
  needed); if ANTHROPIC_API_KEY is set in secrets it can use the paid engine. Live runs
  are capped at 3 per session to be polite to the SEC.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from footnote.formatting import format_value

DEMO_DIR = Path(__file__).resolve().parent / "demo"
LIVE_RUN_CAP = 3
# Fallback SEC contact for the hosted demo. Override with a SEC_CONTACT_EMAIL secret.
DEFAULT_SEC_CONTACT = "footnote-app@example.com"

st.set_page_config(page_title="Footnote", layout="wide")


def secret(key: str):
    """Read a Streamlit secret without raising when no secrets file is configured."""
    try:
        return st.secrets.get(key, None)
    except Exception:  # noqa: BLE001 - no secrets.toml present on the runner
        return None


# --- data loading ----------------------------------------------------------
def load_bundle(dirpath: Path) -> dict:
    return {
        "markdown": (dirpath / "report.md").read_text(encoding="utf-8"),
        "ledger": json.loads((dirpath / "ledger.json").read_text(encoding="utf-8")),
        "verification": json.loads((dirpath / "verification.json").read_text(encoding="utf-8")),
        "footnotes": json.loads((dirpath / "footnotes.json").read_text(encoding="utf-8"))
        if (dirpath / "footnotes.json").exists()
        else [],
    }


def ledger_rows(ledger: dict) -> pd.DataFrame:
    rows = []
    for f in ledger["facts"].values():
        rows.append({
            "id": f["id"], "kind": "fact", "metric": f["label"], "FY": f["fiscal_year"],
            "value": format_value(f["value"], f["unit"]), "form": f["form"],
            "tag / formula": f"us-gaap:{f['xbrl_tag']}",
        })
    for r in ledger["ratios"].values():
        rows.append({
            "id": r["id"], "kind": "ratio", "metric": r["label"], "FY": r["fiscal_year"],
            "value": format_value(r["value"], r["unit"]) if r["value"] is not None else "n/a",
            "form": "", "tag / formula": r["formula"],
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["kind", "metric", "FY"], ascending=[True, True, False]).reset_index(drop=True)


def highlight_row(df: pd.DataFrame, focus_id: str | None):
    def style(row):
        if focus_id and row["id"] == focus_id:
            return ["background-color: #ffe08a; color: #000"] * len(row)
        return [""] * len(row)
    return df.style.apply(style, axis=1)


# --- sidebar ---------------------------------------------------------------
st.sidebar.title("Footnote")
st.sidebar.caption("Every number is cited to the exact SEC filing and machine-verified.")

demo_tickers = json.loads((DEMO_DIR / "index.json").read_text()) if (DEMO_DIR / "index.json").exists() else []
mode = st.sidebar.radio("Mode", ["Cached demo", "Live"], index=0)

bundle = None
title = ""

if mode == "Cached demo":
    if not demo_tickers:
        st.error("No demo bundles found. Run: python scripts/build_demo.py")
        st.stop()
    ticker = st.sidebar.selectbox("Company", demo_tickers)
    bundle = load_bundle(DEMO_DIR / ticker)
    title = ticker
else:
    st.sidebar.info(
        "Live mode fetches from SEC EDGAR and writes a fresh, verified report. "
        "It uses the free template engine unless an ANTHROPIC_API_KEY is configured."
    )
    ticker = st.sidebar.text_input("Ticker", value="AAPL").strip().upper()
    years = st.sidebar.slider("Years", 2, 6, 5)
    engine_options = ["template"]
    if os.environ.get("ANTHROPIC_API_KEY") or secret("ANTHROPIC_API_KEY"):
        engine_options.append("anthropic")
    engine = st.sidebar.selectbox("Engine", engine_options)
    runs = st.session_state.get("live_runs", 0)
    st.sidebar.caption(f"Live runs this session: {runs}/{LIVE_RUN_CAP}")
    if st.sidebar.button("Run analysis", disabled=runs >= LIVE_RUN_CAP):
        # SEC requires a contact email; prefer env, then a secret, then a demo default.
        if not os.environ.get("SEC_CONTACT_EMAIL"):
            os.environ["SEC_CONTACT_EMAIL"] = secret("SEC_CONTACT_EMAIL") or DEFAULT_SEC_CONTACT
        if secret("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = secret("ANTHROPIC_API_KEY")
        try:
            from footnote.agent import NoDataError, run_analysis

            with st.spinner(f"Building verified report for {ticker}..."):
                out = run_analysis(ticker, years=years, out_dir="reports/", engine=engine)
            st.session_state["live_runs"] = runs + 1
            st.session_state["live_bundle_dir"] = str(out.out_dir)
        except NoDataError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Run failed: {exc}")
    if st.session_state.get("live_bundle_dir"):
        bundle = load_bundle(Path(st.session_state["live_bundle_dir"]))
        title = Path(st.session_state["live_bundle_dir"]).name

if bundle is None:
    st.title("Footnote")
    st.write("Choose a company in the sidebar to see a cited analysis, or run a live one.")
    st.stop()


# --- main layout -----------------------------------------------------------
ver = bundle["verification"]
badge = "✅ verified — every number cited" if ver["ok"] else "❌ verification failed"
st.markdown(f"### {title} &nbsp; <span style='font-size:0.7em'>{badge} ({ver['token_count']} tokens)</span>",
            unsafe_allow_html=True)

left, right = st.columns([3, 2])

with right:
    st.subheader("Ledger")
    df = ledger_rows(bundle["ledger"])
    fn_options = ["(none)"] + [f"[{fn['number']}] {fn['value']} → {fn['token_id']}" for fn in bundle["footnotes"]]
    picked = st.selectbox("Highlight a footnote's ledger row", fn_options, index=0)
    focus_id = None
    if picked != "(none)":
        idx = fn_options.index(picked) - 1
        focus_id = bundle["footnotes"][idx]["token_id"]
    st.dataframe(highlight_row(df, focus_id), use_container_width=True, height=560, hide_index=True)

with left:
    st.subheader("Report")
    # Escape '$' so Streamlit does not treat dollar amounts as LaTeX math delimiters.
    st.markdown(bundle["markdown"].replace("$", "\\$"))

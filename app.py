"""Footnote Streamlit app: cited SEC filing analysis with a machine-verified guarantee."""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from footnote.formatting import format_value

DEMO_DIR = Path(__file__).resolve().parent / "demo"
LIVE_RUN_CAP = 3
DEFAULT_SEC_CONTACT = "footnote-app@example.com"

st.set_page_config(page_title="Footnote", page_icon="▉", layout="wide")

def secret(key: str):
    try:
        return st.secrets.get(key, None)
    except Exception:
        return None

def load_bundle(dirpath: Path) -> dict:
    return {
        "markdown": (dirpath / "report.md").read_text(encoding="utf-8"),
        "ledger": json.loads((dirpath / "ledger.json").read_text(encoding="utf-8")),
        "verification": json.loads((dirpath / "verification.json").read_text(encoding="utf-8")),
        "footnotes": json.loads((dirpath / "footnotes.json").read_text(encoding="utf-8"))
        if (dirpath / "footnotes.json").exists()
        else [],
    }

def kpis(ledger: dict) -> list[dict]:
    years = ledger.get("years") or []
    if not years:
        return []
    y = years[0]
    out = []
    specs = [
        ("revenue", "fact", "Revenue"),
        ("net_margin", "ratio", "Net margin"),
        ("free_cash_flow", "ratio", "Free cash flow"),
        ("roe", "ratio", "Return on equity"),
    ]
    for concept, kind, label in specs:
        node = ledger["facts" if kind == "fact" else "ratios"].get(f"{concept}:FY{y}")
        if node and node.get("value") is not None:
            out.append({"label": label, "value": format_value(node["value"], node["unit"]), "fy": f"FY{y}"})
    return out

PALETTE = {
    "bg": "#0e1014", "panel": "#161922", "panel2": "#1e222c", "line": "#2a2f3b",
    "text": "#e7e9ee", "muted": "#98a2b3", "accent": "#5b8cff", "hl": "#ffd44d",
    "ok": "#3ad07f", "grad1": "#5b8cff", "grad2": "#a06bff",
}

_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: {{bg}}; color: {{text}};
    font: 15px/1.65 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .hero { background: linear-gradient(120deg, {{grad1}}22, {{grad2}}22);
    border: 1px solid {{line}}; border-radius: 16px; padding: 18px 22px; margin-bottom: 16px; }
  .hero-top { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  .hero h1 { margin: 0; font-size: 22px; letter-spacing:.2px; }
  .badge { font-size: 12.5px; padding: 5px 11px; border-radius: 999px; white-space: nowrap; font-weight:600; }
  .badge.ok { background: {{ok}}22; color: {{ok}}; border: 1px solid {{ok}}55; }
  .badge.bad { background: #ff5c5c22; color:#ff7a7a; border:1px solid #ff5c5c55; }
  .kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:12px; margin-top:14px; }
  .kpi { background: {{bg}}; border:1px solid {{line}}; border-radius:12px; padding:12px 14px; }
  .kpi-label { color: {{muted}}; font-size:12px; display:flex; justify-content:space-between; }
  .kpi-label span { color: {{accent}}; }
  .kpi-value { font-size:22px; font-weight:700; margin-top:4px; font-variant-numeric: tabular-nums; }
  .grid { display:grid; grid-template-columns: 1.4fr 1fr; gap:16px; align-items:start; }
  @media (max-width: 860px){ .grid { grid-template-columns:1fr; } }
  .panel { background: {{panel}}; border:1px solid {{line}}; border-radius:14px; padding:18px 20px; min-width:0; }
  .panel h2.sec { margin:0 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:.7px; color:{{muted}}; }
  .report h1 { font-size:23px; margin:4px 0 16px; }
  .report h2 { font-size:16px; margin:22px 0 6px; padding-top:14px; border-top:1px solid {{line}}; }
  .report p { margin:9px 0; }
  .report hr { border:none; border-top:1px solid {{line}}; margin:20px 0; }
  .report ol { padding-left:20px; font-size:13px; color:{{muted}}; }
  .report ol li { margin-bottom:6px; }
  .report a { color:{{accent}}; word-break:break-all; }
  .fn { cursor:pointer; color:{{accent}}; font-weight:700; font-size:.8em; vertical-align:super; padding:0 1px; }
  .fn:hover { text-decoration:underline; }
  .fn.active { background:{{hl}}; color:#000; border-radius:4px; }
  .ledger-wrap { position: sticky; top: 0; }
  .table-scroll { max-height: 78vh; overflow:auto; border-radius:10px; border:1px solid {{line}}; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  thead th { position:sticky; top:0; background:{{panel2}}; text-align:left; padding:9px 11px;
    color:{{muted}}; border-bottom:1px solid {{line}}; z-index:1; }
  tbody td { padding:8px 11px; border-bottom:1px solid {{line}}; vertical-align:top; }
  tbody tr.ratio td:first-child { color:{{muted}}; }
  tbody tr.hl td { background:{{hl}}; color:#000; }
  tbody tr.hl td a { color:#123; }
  td.val { font-variant-numeric:tabular-nums; white-space:nowrap; font-weight:600; }
  td.src { color:{{muted}}; font-size:11.5px; }
  td.src a { color:{{accent}}; }
  .hint { color:{{muted}}; font-size:12px; font-weight:400; }
</style></head>
<body>
  <div class="hero">
    <div class="hero-top"><h1>__TITLE__</h1>__BADGE__</div>
    <div class="kpis">__KPIS__</div>
  </div>
  <div class="grid">
    <div class="panel report-panel">
      <h2 class="sec">Report <span class="hint">&middot; click any [n] to trace its source</span></h2>
      <article id="report" class="report"></article>
    </div>
    <div class="ledger-wrap">
      <div class="panel">
        <h2 class="sec">Ledger <span class="hint">&middot; the only place numbers live</span></h2>
        <div class="table-scroll"><table id="ledger">
          <thead><tr><th>Metric</th><th>FY</th><th>Value</th><th>Source</th></tr></thead>
          <tbody></tbody></table></div>
      </div>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
  <script>
    const DATA = __DATA__;
    marked.setOptions({ gfm: true });
    function fmtMoney(v){const s=v<0?"-":"";const a=Math.abs(v);
      if(a>=1e12)return `${s}$${(a/1e12).toFixed(1)}T`;
      if(a>=1e9)return `${s}$${(a/1e9).toFixed(1)}B`;
      if(a>=1e6)return `${s}$${(a/1e6).toFixed(1)}M`;
      if(a>=1e3)return `${s}$${(a/1e3).toFixed(1)}K`;return `${s}$${a.toFixed(0)}`;}
    function fmtValue(v,u){if(v===null||v===undefined)return "n/a";u=(u||"").toLowerCase();
      if(u==="%")return (v*100).toFixed(1)+"%";
      if(u==="x"||u==="ratio")return v.toFixed(2)+"x";
      if(u==="usd")return fmtMoney(v);
      if(u.startsWith("usd/"))return "$"+v.toFixed(2);
      return v.toLocaleString();}
    const idByNum={}; DATA.footnotes.forEach(f=>idByNum[f.number]=f.token_id);
    let html = marked.parse(DATA.md);
    html = html.replace(/\[(\d+)\]/g,(m,n)=> idByNum[n]
      ? `<span class="fn" data-id="${idByNum[n]}">[${n}]</span>` : m);
    document.getElementById("report").innerHTML = html;
    const tb = document.querySelector("#ledger tbody");
    function addRow(id,kind,metric,fy,val,src,href){
      const tr=document.createElement("tr");tr.className=kind;tr.dataset.id=id;
      const s = href ? `<a href="${href}" target="_blank" rel="noopener">${src}</a>` : src;
      tr.innerHTML=`<td>${metric}</td><td>${fy}</td><td class="val">${val}</td><td class="src">${s}</td>`;
      tb.appendChild(tr);}
    Object.values(DATA.ledger.facts).sort((a,b)=>a.label.localeCompare(b.label)||b.fiscal_year-a.fiscal_year)
      .forEach(f=>addRow(f.id,"fact",f.label,"FY"+f.fiscal_year,fmtValue(f.value,f.unit),
        f.form+" &middot; us-gaap:"+f.xbrl_tag,f.source_url));
    Object.values(DATA.ledger.ratios).sort((a,b)=>a.label.localeCompare(b.label)||b.fiscal_year-a.fiscal_year)
      .forEach(r=>addRow(r.id,"ratio",r.label,"FY"+r.fiscal_year,
        r.value===null?"n/a":fmtValue(r.value,r.unit),r.formula,null));
    document.querySelectorAll(".fn").forEach(el=>el.addEventListener("click",()=>{
      document.querySelectorAll("#ledger tbody tr.hl").forEach(r=>r.classList.remove("hl"));
      document.querySelectorAll(".fn.active").forEach(f=>f.classList.remove("active"));
      const row=document.querySelector(`#ledger tbody tr[data-id="${CSS.escape(el.dataset.id)}"]`);
      if(row){row.classList.add("hl");row.scrollIntoView({behavior:"smooth",block:"center"});}
      el.classList.add("active");
    }));
  </script>
</body></html>
"""

def build_component(bundle: dict, title: str) -> str:
    ver = bundle["verification"]
    badge = (
        f'<span class="badge ok">&#10003; verified &middot; {ver["token_count"]} numbers cited</span>'
        if ver["ok"]
        else '<span class="badge bad">&#10007; verification failed</span>'
    )
    kpi_cards = "".join(
        f'<div class="kpi"><div class="kpi-label">{k["label"]} <span>{k["fy"]}</span></div>'
        f'<div class="kpi-value">{k["value"]}</div></div>'
        for k in kpis(bundle["ledger"])
    )
    data = {
        "md": bundle["markdown"],
        "ledger": bundle["ledger"],
        "footnotes": bundle["footnotes"],
    }
    html = _TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__BADGE__", badge)
    html = html.replace("__KPIS__", kpi_cards)
    html = html.replace("__DATA__", json.dumps(data))
    for key, val in PALETTE.items():
        html = html.replace("{{" + key + "}}", val)
    return html

st.markdown(
    """
    <style>
      #MainMenu, footer, header {visibility: hidden;}
      .block-container {padding-top: 1.2rem; padding-bottom: 0; max-width: 1400px;}
      section[data-testid="stSidebar"] {background: #12141a; border-right: 1px solid #2a2f3b;}
      section[data-testid="stSidebar"] .stRadio label, section[data-testid="stSidebar"] label {color: #cdd3de;}
    </style>
    """,
    unsafe_allow_html=True,
)

demo_tickers = json.loads((DEMO_DIR / "index.json").read_text()) if (DEMO_DIR / "index.json").exists() else []

with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:.55rem;margin-bottom:.2rem">'
        '<span style="font-size:1.5rem;color:#5b8cff">&#9609;</span>'
        '<span style="font-size:1.3rem;font-weight:700;letter-spacing:.3px">Footnote</span></div>'
        '<div style="color:#98a2b3;font-size:.82rem;line-height:1.4;margin-bottom:1rem">'
        "Every number is cited to the exact SEC filing, and machine-verified.</div>",
        unsafe_allow_html=True,
    )
    mode = st.radio("Mode", ["Cached demo", "Live analysis"], index=0, label_visibility="collapsed")
    st.divider()

bundle = None
title = ""

if mode == "Cached demo":
    if not demo_tickers:
        st.error("No demo bundles found. Run: python scripts/build_demo.py")
        st.stop()
    with st.sidebar:
        ticker = st.selectbox("Company", demo_tickers)
        st.caption("Ten pre-computed, verified reports. No API key needed.")
    bundle = load_bundle(DEMO_DIR / ticker)
    title = f"{bundle['ledger']['company']['name']} ({ticker})"
else:
    with st.sidebar:
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        years = st.slider("Fiscal years", 2, 6, 5)
        engine_options = ["template"]
        if os.environ.get("ANTHROPIC_API_KEY") or secret("ANTHROPIC_API_KEY"):
            engine_options.append("anthropic")
        engine = st.selectbox("Writer engine", engine_options)
        runs = st.session_state.get("live_runs", 0)
        st.caption(f"Live runs this session: {runs}/{LIVE_RUN_CAP}")
        go = st.button("Analyze", type="primary", disabled=runs >= LIVE_RUN_CAP, use_container_width=True)
    if go:
        if not os.environ.get("SEC_CONTACT_EMAIL"):
            os.environ["SEC_CONTACT_EMAIL"] = secret("SEC_CONTACT_EMAIL") or DEFAULT_SEC_CONTACT
        if secret("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = secret("ANTHROPIC_API_KEY")
        try:
            from footnote.agent import NoDataError, run_analysis

            with st.spinner(f"Building a verified report for {ticker}..."):
                out = run_analysis(ticker, years=years, out_dir="reports/", engine=engine)
            st.session_state["live_runs"] = runs + 1
            st.session_state["live_bundle_dir"] = str(out.out_dir)
            st.session_state["live_title"] = f"{out.ledger.company.name} ({out.ledger.company.ticker})"
        except NoDataError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Run failed: {exc}")
    if st.session_state.get("live_bundle_dir"):
        bundle = load_bundle(Path(st.session_state["live_bundle_dir"]))
        title = st.session_state.get("live_title", "")

if bundle is None:
    st.markdown(
        '<div style="text-align:center;padding:4rem 1rem;color:#98a2b3">'
        '<h1 style="color:#e7e9ee">Footnote</h1>'
        "<p>Enter a ticker in the sidebar and press Analyze, or browse a cached report.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

components.html(build_component(bundle, title), height=1500, scrolling=True)

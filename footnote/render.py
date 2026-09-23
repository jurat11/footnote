"""Render token-bearing report text into formatted values plus numbered footnotes.

The model writes prose containing tokens like ``{{F:revenue:FY2024}}`` and
``{{R:gross_margin:FY2024}}``. This module is the only place those tokens become
actual numbers. Each token resolves to a formatted value and a footnote that gives the
form, fiscal year, period end, filed date, XBRL tag and a link to the filing. For a
ratio, the footnote also shows the formula and every input's filing.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from .formatting import format_value
from .models import Ledger

TOKEN_RE = re.compile(
    r"\{\{(?P<kind>[FR]):(?:(?P<ticker>[A-Z][A-Z0-9.\-]*):)?(?P<concept>[a-z_]+):FY(?P<year>\d{4})\}\}"
)

def token_id_from_match(m: re.Match) -> str:
    """Reconstruct the ledger id (optionally ticker-namespaced) from a token match."""
    base = f"{m.group('concept')}:FY{m.group('year')}"
    ticker = m.group("ticker")
    return f"{ticker}:{base}" if ticker else base

def token_text_from_match(m: re.Match) -> str:
    return m.group(0)

@dataclass
class Footnote:
    number: int
    token_id: str
    kind: str
    value_text: str
    description: str
    urls: list[str] = field(default_factory=list)

@dataclass
class RenderResult:
    markdown: str
    html: str
    footnotes: list[Footnote]
    unknown_tokens: list[str] = field(default_factory=list)

def _dedupe(urls: list[str]) -> list[str]:
    """Order-preserving de-duplication; several inputs often share one filing."""
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def _fact_description(ledger: Ledger, fact_id: str) -> tuple[str, list[str]]:
    f = ledger.facts[fact_id]
    desc = (
        f"{f.label}, FY{f.fiscal_year}. {f.form}, period ended {f.period_end}, "
        f"filed {f.filed}. XBRL tag us-gaap:{f.xbrl_tag}."
    )
    return desc, [f.source_url]

def _ratio_description(ledger: Ledger, ratio_id: str) -> tuple[str, list[str]]:
    r = ledger.ratios[ratio_id]
    parts = [f"{r.label}, FY{r.fiscal_year}. Formula: {r.formula}."]
    urls: list[str] = []
    if r.value is None:
        parts.append(f"Not computed: {r.reason}")
    input_bits = []
    for inp in r.inputs:
        f = ledger.facts.get(inp.fact_id)
        if f is None:
            input_bits.append(f"{inp.role} ({inp.fact_id}: missing)")
            continue
        input_bits.append(
            f"{f.label} FY{f.fiscal_year} [{f.form} filed {f.filed}, us-gaap:{f.xbrl_tag}]"
        )
        urls.append(f.source_url)
    if input_bits:
        parts.append("Inputs: " + "; ".join(input_bits) + ".")
    return " ".join(parts), urls

def _resolve(ledger: Ledger, kind: str, token_id: str) -> tuple[str, str, list[str]] | None:
    """Return (value_text, description, urls) or None if the token id is unknown."""
    if kind == "F":
        f = ledger.facts.get(token_id)
        if f is None:
            return None
        desc, urls = _fact_description(ledger, token_id)
        return format_value(f.value, f.unit), desc, urls
    else:
        r = ledger.ratios.get(token_id)
        if r is None:
            return None
        desc, urls = _ratio_description(ledger, token_id)
        return format_value(r.value, r.unit), desc, urls

def render(text: str, ledger: Ledger) -> RenderResult:
    """Replace tokens in ``text`` and build the footnote apparatus."""
    numbers: dict[str, int] = {}
    footnotes: list[Footnote] = []
    unknown: list[str] = []

    placeholders: dict[str, tuple[str, int]] = {}

    def repl(m: re.Match) -> str:
        kind = m.group("kind")
        token_id = token_id_from_match(m)
        resolved = _resolve(ledger, kind, token_id)
        if resolved is None:
            unknown.append(m.group(0))
            return f"[UNKNOWN:{token_id}]"
        value_text, desc, urls = resolved
        if token_id not in numbers:
            n = len(numbers) + 1
            numbers[token_id] = n
            footnotes.append(Footnote(n, token_id, kind, value_text, desc, _dedupe(urls)))
        n = numbers[token_id]
        ph = f"\x00PH{n}\x00"
        placeholders[ph] = (value_text, n)
        return ph

    prose_with_ph = TOKEN_RE.sub(repl, text)

    md_body = prose_with_ph
    for ph, (value_text, n) in placeholders.items():
        md_body = md_body.replace(ph, f"{value_text} [{n}]")
    md = md_body.rstrip() + "\n\n---\n\n## Sources\n\n"
    for fn in footnotes:
        link = f" {fn.urls[0]}" if fn.urls else ""
        extra = ""
        if len(fn.urls) > 1:
            extra = " Additional filings: " + ", ".join(fn.urls[1:])
        md += f"{fn.number}. **{fn.value_text}** — {fn.description}{link}{extra}\n"

    html_out = _to_html(prose_with_ph, placeholders, footnotes, ledger.company.name)

    return RenderResult(markdown=md, html=html_out, footnotes=footnotes, unknown_tokens=unknown)

def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    return text

def _to_html(prose_with_ph: str, placeholders, footnotes, company_name: str) -> str:
    lines = prose_with_ph.split("\n")
    out: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        if line.startswith("### "):
            close_list()
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_list()
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.lstrip().startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line.lstrip()[2:])}</li>")
        else:
            close_list()
            out.append(f"<p>{_inline(line)}</p>")
    close_list()
    body = "\n".join(out)

    for ph, (value_text, n) in placeholders.items():
        marker = (
            f'{html.escape(value_text)}'
            f'<sup><a href="#fn{n}" id="ref{n}" class="fnref">[{n}]</a></sup>'
        )
        body = body.replace(ph, marker)

    fn_items = []
    for fn in footnotes:
        links = " ".join(
            f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{html.escape(u)}</a>'
            for u in fn.urls
        )
        fn_items.append(
            f'<li id="fn{fn.number}"><strong>{html.escape(fn.value_text)}</strong> — '
            f'{html.escape(fn.description)} {links} '
            f'<a href="#ref{fn.number}" class="back">&#8617;</a></li>'
        )
    sources = "<h2>Sources</h2>\n<ol class=\"sources\">\n" + "\n".join(fn_items) + "\n</ol>"

    return _HTML_TEMPLATE.format(
        title=html.escape(f"Footnote — {company_name}"),
        body=body,
        sources=sources,
    )

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
         font: 16px/1.65 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }}
  h1,h2,h3 {{ line-height: 1.25; }}
  sup a.fnref {{ text-decoration: none; font-weight: 600; }}
  .sources {{ font-size: 0.9rem; }}
  .sources li {{ margin-bottom: 0.5rem; }}
  .sources a {{ word-break: break-all; }}
  a.back {{ text-decoration: none; }}
  hr {{ border: none; border-top: 1px solid #8884; margin: 2rem 0; }}
</style>
</head>
<body>
{body}
<hr>
{sources}
</body>
</html>
"""

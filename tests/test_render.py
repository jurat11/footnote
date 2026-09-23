"""Renderer tests: tokens become formatted values with footnotes carrying the
filing details, ratios cite every input, and unknown tokens are reported."""

from __future__ import annotations

from footnote.render import render
from tests.conftest import offline_ledger


def test_fact_token_renders_value_and_footnote():
    led = offline_ledger("AAPL")
    y = led.years[0]
    fact = led.facts[f"revenue:FY{y}"]
    result = render(f"Revenue was {{{{F:revenue:FY{y}}}}}.", led)
    from footnote.formatting import format_value

    assert format_value(fact.value, fact.unit) in result.markdown
    assert "[1]" in result.markdown
    assert "## Sources" in result.markdown
    fn = result.footnotes[0]
    assert fn.token_id == f"revenue:FY{y}"
    assert fact.xbrl_tag in fn.description
    assert fact.source_url in fn.urls
    assert fact.form in fn.description


def test_ratio_footnote_lists_formula_and_inputs():
    led = offline_ledger("AAPL")
    y = led.years[0]
    result = render(f"Gross margin was {{{{R:gross_margin:FY{y}}}}}.", led)
    fn = result.footnotes[0]
    assert "Formula:" in fn.description
    assert "Inputs:" in fn.description
    # Ratio citation must include the filings of its inputs.
    assert len(fn.urls) >= 1


def test_repeated_token_shares_one_footnote_number():
    led = offline_ledger("AAPL")
    y = led.years[0]
    text = f"{{{{F:revenue:FY{y}}}}} ... again {{{{F:revenue:FY{y}}}}}."
    result = render(text, led)
    assert len(result.footnotes) == 1
    assert result.markdown.count("[1]") == 2


def test_unknown_token_is_reported():
    led = offline_ledger("AAPL")
    result = render("Value {{F:ebitda:FY2024}}.", led)
    assert result.unknown_tokens == ["{{F:ebitda:FY2024}}"]
    assert "[UNKNOWN:ebitda:FY2024]" in result.markdown


def test_html_is_self_contained_with_links():
    led = offline_ledger("AAPL")
    y = led.years[0]
    result = render(f"Revenue {{{{F:revenue:FY{y}}}}}.", led)
    assert result.html.startswith("<!doctype html>")
    assert 'href="https://www.sec.gov/Archives/edgar/data/320193/' in result.html
    assert 'id="fn1"' in result.html

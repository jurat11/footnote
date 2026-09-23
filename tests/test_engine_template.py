"""The template engine's output must pass verification offline, for a normal filer,
a bank, and a namespaced multi-company comparison."""

from __future__ import annotations

from footnote.engines.template import TemplateEngine
from footnote.ledger import combine_ledgers
from footnote.render import render
from footnote.verify import verify
from tests.conftest import offline_ledger


def test_template_analysis_passes_verification():
    led = offline_ledger("AAPL")
    text = TemplateEngine()._compose_analysis(led)
    result = verify(text, led)
    assert result.ok, result.violations
    assert result.token_count > 5
    assert not render(text, led).unknown_tokens

def test_template_bank_report_passes_and_notes_no_gross_margin():
    led = offline_ledger("JPM")
    text = TemplateEngine()._compose_analysis(led)
    assert "gross margin is not applicable" in text
    assert verify(text, led).ok

def test_combined_ledger_namespaces_ids():
    aapl = offline_ledger("AAPL")
    msft = offline_ledger("MSFT")
    combined = combine_ledgers({"AAPL": aapl, "MSFT": msft})
    ay = aapl.years[0]
    my = msft.years[0]
    assert f"AAPL:revenue:FY{ay}" in combined.facts
    assert f"MSFT:revenue:FY{my}" in combined.facts
    assert set(combined.years) >= set(aapl.years) | set(msft.years)

def test_namespaced_comparison_token_resolves_to_right_company():
    aapl = offline_ledger("AAPL")
    msft = offline_ledger("MSFT")
    combined = combine_ledgers({"AAPL": aapl, "MSFT": msft})
    ay = aapl.years[0]
    text = f"Apple revenue {{{{F:AAPL:revenue:FY{ay}}}}}."
    result = render(text, combined)
    from footnote.formatting import format_value

    assert format_value(aapl.facts[f"revenue:FY{ay}"].value, "USD") in result.markdown
    assert verify(text, combined).ok

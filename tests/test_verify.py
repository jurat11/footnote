"""Verifier tests: a clean report passes, an injected number is caught, and the
allowed exceptions (fiscal years, 10-K/10-Q, footnote markers) do not trip it."""

from __future__ import annotations

from footnote.verify import verify
from tests.conftest import offline_ledger


def _year(ledger) -> int:
    return ledger.years[0]

def test_clean_report_with_only_tokens_passes():
    led = offline_ledger("AAPL")
    y = _year(led)
    text = (
        f"Revenue was {{{{F:revenue:FY{y}}}}} and net income was {{{{F:net_income:FY{y}}}}}. "
        f"Gross margin came in at {{{{R:gross_margin:FY{y}}}}}."
    )
    r = verify(text, led)
    assert r.ok, r.violations
    assert r.token_count == 3

def test_injected_number_is_caught():
    led = offline_ledger("AAPL")
    y = _year(led)
    text = f"Revenue was {{{{F:revenue:FY{y}}}}}, up about 5.2% from last year."
    r = verify(text, led)
    assert not r.ok
    assert any(v.kind == "uncited_number" and "5.2" in v.text for v in r.violations)

def test_bare_integer_in_prose_is_caught():
    led = offline_ledger("AAPL")
    y = _year(led)
    text = f"The company runs 42 factories. Revenue was {{{{F:revenue:FY{y}}}}}."
    r = verify(text, led)
    assert not r.ok
    assert any(v.text == "42" for v in r.violations)

def test_allowed_exceptions_do_not_trip_verifier():
    led = offline_ledger("AAPL")
    y = _year(led)
    text = (
        f"In its FY{y} 10-K (and interim 10-Q filings), the {y} results held up [1]. "
        f"Revenue was {{{{F:revenue:FY{y}}}}}."
    )
    r = verify(text, led)
    assert r.ok, r.violations

def test_unknown_token_fails():
    led = offline_ledger("AAPL")
    text = "Mystery metric: {{F:ebitda:FY2024}}."
    r = verify(text, led)
    assert not r.ok
    assert r.unknown_tokens == ["{{F:ebitda:FY2024}}"]
    assert any(v.kind == "unknown_token" for v in r.violations)

def test_prior_year_for_growth_is_allowed():
    led = offline_ledger("AAPL")
    prior = min(led.years) - 1
    text = f"Compared with {prior}, revenue {{{{F:revenue:FY{led.years[0]}}}}} rose."
    r = verify(text, led)
    assert r.ok, r.violations

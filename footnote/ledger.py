"""Assemble a full :class:`Ledger` for a company: facts + ratios + gaps.

This is the deterministic heart of Footnote. No language model is involved; the
output here is the ground truth every report token resolves against.
"""

from __future__ import annotations

from typing import Any

from .edgar import EdgarClient, resolve_cik
from .facts import build_facts
from .models import Company, Ledger
from .ratios import build_ratios


def _company_from_submissions(cik: int, ticker: str, name: str, submissions: dict[str, Any]) -> Company:
    return Company(
        ticker=ticker,
        cik=cik,
        name=submissions.get("name") or name,
        sic=str(submissions.get("sic")) if submissions.get("sic") else None,
        sic_description=submissions.get("sicDescription"),
    )


def build_ledger(client: EdgarClient, query: str, years: int = 5) -> Ledger:
    """Resolve ``query`` to a company and build its ledger for the last ``years`` years."""
    cik, ticker, name = resolve_cik(client, query)
    cik10 = f"{cik:010d}"

    submissions = client.submissions(cik10)
    company = _company_from_submissions(cik, ticker, name, submissions)

    companyfacts = client.company_facts(cik10)
    fb = build_facts(company, companyfacts, years=years)

    ratios = build_ratios(fb.facts, fb.fiscal_years, reports_gross_margin=fb.reports_gross_margin)

    return Ledger(
        company=company,
        years=fb.fiscal_years,
        facts=fb.facts,
        ratios=ratios,
        missing=fb.missing,
        reports_gross_margin=fb.reports_gross_margin,
    )

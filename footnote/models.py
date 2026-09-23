"""Pydantic models for the fact ledger.

These are the only place numbers live. Everything downstream (ratios, render,
verify) refers to facts by their ``id``; the language model never sees or emits a
raw value, only tokens like ``{{F:revenue:FY2024}}``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """A single numeric fact pulled from one XBRL filing."""

    id: str
    concept: str
    xbrl_tag: str
    label: str
    value: float
    unit: str
    period_start: str | None
    period_end: str
    fiscal_year: int
    accession: str
    form: str
    filed: str
    source_url: str

    @property
    def fy_label(self) -> str:
        return f"FY{self.fiscal_year}"

class RatioInput(BaseModel):
    """One input to a ratio, naming both the role and the fact it came from."""

    role: str
    fact_id: str

class Ratio(BaseModel):
    """A derived metric. Stores its formula and every fact it depends on, so its
    citation can list all underlying filings."""

    id: str
    concept: str
    label: str
    fiscal_year: int
    value: float | None
    unit: str
    formula: str
    inputs: list[RatioInput] = Field(default_factory=list)
    reason: str | None = None

    @property
    def fy_label(self) -> str:
        return f"FY{self.fiscal_year}"

class MissingMetric(BaseModel):
    """A metric we looked for but could not find, with the tags we tried."""

    concept: str
    label: str
    fiscal_year: int | None = None
    tags_tried: list[str] = Field(default_factory=list)
    note: str = ""

class Company(BaseModel):
    ticker: str
    cik: int
    name: str
    sic: str | None = None
    sic_description: str | None = None

    @property
    def cik10(self) -> str:
        return f"{self.cik:010d}"

class Ledger(BaseModel):
    """The full deterministic result for one company: facts, ratios, gaps."""

    company: Company
    years: list[int]
    facts: dict[str, Fact] = Field(default_factory=dict)
    ratios: dict[str, Ratio] = Field(default_factory=dict)
    missing: list[MissingMetric] = Field(default_factory=list)
    reports_gross_margin: bool = True

    def token_ids(self) -> set[str]:
        """Every id the verifier is allowed to see referenced."""
        return set(self.facts) | set(self.ratios)

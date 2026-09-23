"""Pydantic models for the fact ledger.

These are the only place numbers live. Everything downstream (ratios, render,
verify) refers to facts by their ``id``; the language model never sees or emits a
raw value, only tokens like ``{{F:revenue:FY2024}}``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """A single numeric fact pulled from one XBRL filing."""

    id: str  # e.g. "revenue:FY2024"
    concept: str  # our canonical concept key, e.g. "revenue"
    xbrl_tag: str  # the us-gaap tag actually used, e.g. "RevenueFromContract..."
    label: str  # human label, e.g. "Revenue"
    value: float
    unit: str  # e.g. "USD", "USD/shares", "shares"
    period_start: str | None  # ISO date; None for instant (balance-sheet) facts
    period_end: str  # ISO date
    fiscal_year: int  # derived from period_end, NOT from the filing's fy field
    accession: str  # e.g. "0000320193-24-000123"
    form: str  # e.g. "10-K"
    filed: str  # ISO date the filing was filed
    source_url: str  # filing index page

    @property
    def fy_label(self) -> str:
        return f"FY{self.fiscal_year}"


class RatioInput(BaseModel):
    """One input to a ratio, naming both the role and the fact it came from."""

    role: str  # e.g. "numerator", "gross_profit", "revenue"
    fact_id: str


class Ratio(BaseModel):
    """A derived metric. Stores its formula and every fact it depends on, so its
    citation can list all underlying filings."""

    id: str  # e.g. "gross_margin:FY2024"
    concept: str  # e.g. "gross_margin"
    label: str
    fiscal_year: int
    value: float | None  # None when it cannot be computed
    unit: str  # "%", "x", "USD", "ratio"
    formula: str  # human-readable formula string
    inputs: list[RatioInput] = Field(default_factory=list)
    reason: str | None = None  # why value is None, when applicable

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
    cik: int  # integer form (no leading zeros)
    name: str
    sic: str | None = None
    sic_description: str | None = None

    @property
    def cik10(self) -> str:
        return f"{self.cik:010d}"


class Ledger(BaseModel):
    """The full deterministic result for one company: facts, ratios, gaps."""

    company: Company
    years: list[int]  # fiscal years covered, descending
    facts: dict[str, Fact] = Field(default_factory=dict)  # id -> Fact
    ratios: dict[str, Ratio] = Field(default_factory=dict)  # id -> Ratio
    missing: list[MissingMetric] = Field(default_factory=list)
    reports_gross_margin: bool = True  # False for banks/insurers with no cost of revenue

    def token_ids(self) -> set[str]:
        """Every id the verifier is allowed to see referenced."""
        return set(self.facts) | set(self.ratios)

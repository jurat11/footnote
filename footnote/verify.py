"""Verify that every number in the model's report came from a token.

The check runs on the model's raw text (before rendering). We remove the valid
``{{...}}`` tokens and a small set of allowed digit-bearing strings, then scan what is
left. Any surviving digit is an uncited number and fails verification. A token whose id
is not in the ledger also fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Ledger
from .render import TOKEN_RE

# A run of digits, optionally with thousands separators / decimals / a trailing %.
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


@dataclass
class Violation:
    kind: str  # "uncited_number" | "unknown_token"
    text: str
    context: str


@dataclass
class VerificationResult:
    ok: bool
    violations: list[Violation] = field(default_factory=list)
    token_count: int = 0
    unknown_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "token_count": self.token_count,
            "unknown_tokens": self.unknown_tokens,
            "violations": [
                {"kind": v.kind, "text": v.text, "context": v.context} for v in self.violations
            ],
        }


def _allowed_year_strings(ledger: Ledger) -> set[str]:
    allowed: set[str] = set()
    for y in ledger.years:
        allowed.add(str(y))
        allowed.add(f"FY{y}")
    # revenue_growth references the year before the first, so allow the immediate prior year.
    if ledger.years:
        allowed.add(str(min(ledger.years) - 1))
    return allowed


def verify(text: str, ledger: Ledger) -> VerificationResult:
    """Scan ``text`` for numbers that did not come from a ledger token."""
    result = VerificationResult(ok=True)

    # 1) Validate every token id and count them.
    valid_ids = ledger.token_ids()
    for m in TOKEN_RE.finditer(text):
        result.token_count += 1
        token_id = f"{m.group('concept')}:FY{m.group('year')}"
        if token_id not in valid_ids:
            tok = f"{{{{{m.group('kind')}:{token_id}}}}}"
            result.unknown_tokens.append(tok)
            result.violations.append(
                Violation("unknown_token", tok, _context(text, m.start(), m.end()))
            )

    # 2) Strip the token spans, then the allowed digit-bearing strings.
    cleaned = TOKEN_RE.sub(" ", text)

    allowed_years = _allowed_year_strings(ledger)
    # Remove year strings as whole words so "2024" inside a larger number is not lost.
    for ys in sorted(allowed_years, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(ys)}\b", " ", cleaned)
    # Allowed form identifiers.
    for form in ("10-K/A", "10-K", "10-Q"):
        cleaned = cleaned.replace(form, " ")
    # Footnote markers like [1], [12].
    cleaned = re.sub(r"\[\d+\]", " ", cleaned)

    # 3) Anything with a digit left is uncited.
    for m in NUMBER_RE.finditer(cleaned):
        result.violations.append(
            Violation("uncited_number", m.group(0), _context(cleaned, m.start(), m.end()))
        )

    result.ok = not result.violations
    return result


def _context(text: str, start: int, end: int, width: int = 40) -> str:
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    snippet = text[lo:hi].replace("\n", " ").strip()
    return f"...{snippet}..."


def format_violations(result: VerificationResult) -> str:
    """A compact, model-facing description of what failed, for the repair prompt."""
    lines = []
    for v in result.violations:
        if v.kind == "unknown_token":
            lines.append(f"- Unknown token {v.text}: no such fact/ratio in the ledger. Context: {v.context}")
        else:
            lines.append(f"- Uncited number '{v.text}' found in prose. Context: {v.context}")
    return "\n".join(lines)

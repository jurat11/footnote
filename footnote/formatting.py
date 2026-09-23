"""Deterministic value formatting shared by the CLI, renderer and app.

Kept separate so the exact string a number turns into (``$391.0B``, ``46.2%``,
``1.07x``) is defined in one place and never re-implemented by the model.
"""

from __future__ import annotations


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e12:
        return f"{sign}${v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{sign}${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{sign}${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{sign}${v / 1e3:.1f}K"
    return f"{sign}${v:,.0f}"


def _plain_big(value: float) -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e12:
        return f"{sign}{v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{sign}{v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{sign}{v / 1e6:.1f}M"
    return f"{sign}{v:,.0f}"


def format_value(value: float | None, unit: str) -> str:
    """Format a ledger value for display according to its unit."""
    if value is None:
        return "n/a"
    u = unit.lower()
    if u == "%":
        return f"{value * 100:.1f}%"
    if u in ("x", "ratio"):
        return f"{value:.2f}x"
    if u == "usd":
        return _money(value)
    if u in ("usd/shares", "usd/share"):
        return f"${value:,.2f}"
    if u == "shares":
        return _plain_big(value)
    # Unknown unit: show the number plainly with its unit appended.
    return f"{value:,.2f} {unit}"

"""Footnote command-line interface.

    footnote ledger AAPL              # raw deterministic ledger, no LLM
    footnote analyze AAPL --years 5   # full cited report
    footnote compare AAPL MSFT GOOGL  # aligned comparison
"""

from __future__ import annotations

import typer

from . import config
from .edgar import EdgarClient
from .formatting import format_value
from .ledger import build_ledger
from .models import Ledger

app = typer.Typer(add_completion=False, help="Analyze SEC filings with every number cited.")


def _print_ledger(ledger: Ledger) -> None:
    c = ledger.company
    typer.echo(f"\n{c.name}  ({c.ticker})   CIK {c.cik}")
    if c.sic_description:
        typer.echo(f"Industry: {c.sic_description} (SIC {c.sic})")
    typer.echo(f"Fiscal years: {', '.join('FY' + str(y) for y in ledger.years)}")
    if not ledger.reports_gross_margin:
        typer.echo("Note: no cost of revenue reported (bank/insurer); gross margin skipped.")

    years = ledger.years
    concept_order = [
        "revenue", "cost_of_revenue", "operating_income", "net_income",
        "interest_expense", "operating_cash_flow", "capex",
        "total_assets", "total_liabilities", "stockholders_equity",
        "current_assets", "current_liabilities", "long_term_debt", "current_debt",
    ]

    def row(label: str, cells: list[str]) -> str:
        return f"  {label:24}" + "".join(f"{c:>16}" for c in cells)

    typer.echo("\nFACTS")
    typer.echo(row("", [f"FY{y}" for y in years]))
    seen_labels: dict[str, str] = {}
    for concept in concept_order:
        cells = []
        label = concept.replace("_", " ").title()
        for y in years:
            f = ledger.facts.get(f"{concept}:FY{y}")
            if f:
                label = f.label
                cells.append(format_value(f.value, f.unit))
            else:
                cells.append("--")
        seen_labels[concept] = label
        typer.echo(row(label, cells))

    typer.echo("\nRATIOS")
    typer.echo(row("", [f"FY{y}" for y in years]))
    ratio_order = [
        "gross_margin", "operating_margin", "net_margin", "revenue_growth",
        "roe", "roa", "current_ratio", "debt_to_equity",
        "free_cash_flow", "fcf_margin", "interest_coverage", "asset_turnover",
    ]
    for concept in ratio_order:
        cells = []
        label = concept.replace("_", " ").title()
        for y in years:
            r = ledger.ratios.get(f"{concept}:FY{y}")
            if r is None:
                cells.append("--")
            elif r.value is None:
                cells.append("n/a")
            else:
                label = r.label
                cells.append(format_value(r.value, r.unit))
        typer.echo(row(label, cells))

    if ledger.missing:
        typer.echo("\nMISSING METRICS")
        by_concept: dict[str, list[int]] = {}
        for m in ledger.missing:
            by_concept.setdefault(m.concept, []).append(m.fiscal_year or 0)
        for concept, yrs in by_concept.items():
            yrs_s = ", ".join("FY" + str(y) for y in sorted(yrs, reverse=True))
            typer.echo(f"  {concept:24} {yrs_s}")
    typer.echo("")


@app.command()
def ledger(
    query: str = typer.Argument(..., help="Ticker or company name, e.g. AAPL"),
    years: int = typer.Option(5, "--years", "-y", help="Number of fiscal years"),
    as_json: bool = typer.Option(False, "--json", help="Print the ledger as JSON"),
) -> None:
    """Print the raw deterministic ledger. No language model is involved."""
    with EdgarClient() as client:
        led = build_ledger(client, query, years=years)
    if as_json:
        typer.echo(led.model_dump_json(indent=2))
    else:
        _print_ledger(led)


@app.command()
def analyze(
    query: str = typer.Argument(...),
    years: int = typer.Option(5, "--years", "-y"),
    out: str = typer.Option("reports/", "--out", "-o"),
    engine: str = typer.Option(None, "--engine", help="template | ollama | anthropic"),
) -> None:
    """Write a full cited report (report.md/html, ledger.json, verification.json)."""
    from .agent import NoDataError, run_analysis

    try:
        run_analysis(query, years=years, out_dir=out, engine=engine or config.engine_name())
    except (NoDataError, LookupError) as exc:
        typer.secho(f"Cannot analyze {query}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@app.command()
def compare(
    tickers: list[str] = typer.Argument(..., help="Two or more tickers"),
    years: int = typer.Option(5, "--years", "-y"),
    out: str = typer.Option("reports/", "--out", "-o"),
    engine: str = typer.Option(None, "--engine"),
) -> None:
    """Compare several companies on aligned, cited metrics."""
    from .agent import NoDataError, run_comparison

    try:
        run_comparison(tickers, years=years, out_dir=out, engine=engine or config.engine_name())
    except (NoDataError, LookupError) as exc:
        typer.secho(f"Cannot compare: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()

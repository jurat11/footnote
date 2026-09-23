# Decisions

Ambiguous XBRL and modeling choices, recorded so they can be revisited. Each entry
says what was ambiguous, what was chosen, and why.

## Fiscal year is derived from the period end date's calendar year

`fiscal_year = period_end.year`. The SEC `fy` field is the fiscal year of the *filing*
that reported the number, so a prior-year comparative inside a 10-K carries the wrong
`fy`. Deriving from the period end is stable and self-consistent. Edge case: a retailer
whose year ends in early January/February will get the January year (e.g. an end of
2024-02-03 becomes FY2024) even if the company labels it FY2023. This is deterministic
and documented; it only shifts the label, never the value or the citation.

## Revenue tag priority

Order: `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`,
`SalesRevenueNet`, `RevenueFromContractWithCustomerIncludingAssessedTax`. Post-ASC-606
filers use the contract-revenue tag; older filings and some financials use `Revenues`.
We take the first that yields a value for the period and record which one was used on
each fact.

## Cost of revenue and gross margin

Tags: `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfGoodsSold`. Banks and
insurers do not report a cost of revenue, so no fact is produced, gross margin is
skipped, and the report says so (`reports_gross_margin = False`).

## Debt to equity uses interest-bearing debt, summed from components

There is no single universal "total debt" tag. We sum `long_term_debt`
(`LongTermDebtNoncurrent` / `LongTermDebt` / `LongTermDebtAndCapitalLeaseObligations`)
and `current_debt` (`LongTermDebtCurrent` / `DebtCurrent` / `ShortTermBorrowings`). The
ratio's citation lists every debt fact included. If only one component is reported, the
ratio is computed from what exists and the footnote notes the omitted component; we do
not estimate the missing piece. If neither is reported (common for banks that tag debt
differently), the ratio is returned as `None` with a reason.

## Balance-sheet facts may be cited to a later 10-Q

An instant balance (e.g. equity at the fiscal year-end) is restated/re-reported as a
comparative column in later filings. Per the "latest filed wins" rule we keep the most
recently filed instance of that exact date and cite that filing. The value is unchanged;
the citation simply points at the most recent filing that carried it.

## Interest coverage uses operating income over interest expense

`interest_coverage = operating_income / interest_expense`. When interest expense is zero
or not reported, the ratio is `None` with a reason rather than a divide-by-zero or an
infinite value.

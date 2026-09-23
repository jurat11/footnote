# Crosscheck results

Independent re-fetch of every ledger fact via the `companyconcept` endpoint (a different SEC API surface than the `companyfacts` the ledger is built from).

`unavailable` means the `companyconcept` endpoint returned no data for that tag at all; this is a coverage gap in the checker, not a discrepancy in the ledger.

| Ticker | Checked | Matched | Mismatched | Not found | Endpoint-unavailable |
|---|---|---|---|---|---|
| AAPL | 68 | 68 | 0 | 0 | 0 |
| MSFT | 70 | 70 | 0 | 0 | 0 |
| GOOGL | 70 | 70 | 0 | 0 | 0 |
| AMZN | 65 | 65 | 0 | 0 | 0 |
| META | 65 | 65 | 0 | 0 | 0 |
| NVDA | 70 | 70 | 0 | 0 | 0 |
| TSLA | 70 | 70 | 0 | 0 | 0 |
| ORCL | 56 | 56 | 0 | 0 | 0 |
| CSCO | 70 | 70 | 0 | 0 | 0 |
| INTC | 65 | 65 | 0 | 0 | 0 |
| JPM | 38 | 38 | 0 | 0 | 0 |
| BAC | 38 | 38 | 0 | 0 | 0 |
| WFC | 38 | 38 | 0 | 0 | 0 |
| KO | 63 | 6 | 0 | 0 | 57 |
| PEP | 70 | 70 | 0 | 0 | 0 |
| PG | 70 | 70 | 0 | 0 | 0 |
| JNJ | 65 | 65 | 0 | 0 | 0 |
| PFE | 65 | 65 | 0 | 0 | 0 |
| COP | 62 | 62 | 0 | 0 | 0 |
| CVX | 60 | 60 | 0 | 0 | 0 |
| WMT | 60 | 60 | 0 | 0 | 0 |
| HD | 66 | 66 | 0 | 0 | 0 |
| DIS | 60 | 60 | 0 | 0 | 0 |
| NKE | 55 | 55 | 0 | 0 | 0 |
| CRM | 65 | 65 | 0 | 0 | 0 |

**Totals:** 1487/1487 checkable facts matched, 0 mismatched, 0 not found. 57 facts had no companyconcept coverage to check against.

No discrepancies: every fact matched the independent path.

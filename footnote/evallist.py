"""The 25-ticker evaluation universe used by the crosscheck and eval scripts.

Spans large-cap tech, banks (reduced ratio set), consumer staples, healthcare,
energy and retail so the pipeline is exercised across very different XBRL tagging.
"""

EVAL_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ORCL", "CSCO", "INTC",
    "JPM", "BAC", "WFC", "KO", "PEP", "PG", "JNJ", "PFE", "COP", "CVX",
    "WMT", "HD", "DIS", "NKE", "CRM",
]

assert len(EVAL_TICKERS) == 25

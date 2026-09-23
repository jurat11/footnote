"""Central configuration read from the environment.

Nothing here reaches the network; it only holds constants and small helpers so the
rest of the package has a single source of truth for URLs, rate limits and paths.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".cache" / "edgar"
RUNS_DIR = PROJECT_ROOT / "runs"
REPORTS_DIR = PROJECT_ROOT / "reports"

def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a project-root .env into the environment.

    Kept dependency-free and non-destructive: a variable already set in the real
    environment always wins, so .env is only a convenience for local runs.
    """
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass

_load_dotenv()

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
COMPANYCONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json"
)
FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{accession}-index.htm"
)

RATE_LIMIT_PER_SEC = 8.0
CACHE_TTL_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 4

DEFAULT_ENGINE = "template"
DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOOL_CALLS = 12
MAX_VERIFY_RETRIES = 2

def sec_contact_email() -> str:
    """Return the operator contact email, or raise if it is missing.

    The SEC requires a descriptive User-Agent with a contact address and blocks
    requests without one, so we refuse to start rather than get silently banned.
    """
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "SEC_CONTACT_EMAIL is not set. The SEC requires a contact email in the "
            "User-Agent header. Set it, for example: export SEC_CONTACT_EMAIL=you@example.com"
        )
    return email

def user_agent() -> str:
    """The exact User-Agent string every SEC request must carry."""
    return f"Footnote/0.1 ({sec_contact_email()})"

def engine_name() -> str:
    return os.environ.get("FOOTNOTE_ENGINE", DEFAULT_ENGINE).strip().lower()

def model_id() -> str:
    return os.environ.get("FOOTNOTE_MODEL", DEFAULT_MODEL).strip()

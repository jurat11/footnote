"""SEC EDGAR HTTP client.

Responsibilities kept deliberately narrow: fetch JSON from the three SEC endpoints
(plus companyconcept for the cross-check), enforce a global rate limit, retry on
429/503 with backoff, and cache every response on disk for 24h so tests and demos do
not hammer the SEC. All parsing lives in facts.py, not here.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from . import config


class RateLimiter:
    """A simple global token-bucket-ish limiter: at most N requests per second.

    Thread-safe because the Streamlit app and any future concurrency share one client.
    """

    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self._min_interval:
                time.sleep(self._min_interval - delta)
            self._last = time.monotonic()

class EdgarClient:
    """Fetches and caches SEC JSON. Construct once and reuse."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        rate_limit: float = config.RATE_LIMIT_PER_SEC,
        ttl_seconds: int = config.CACHE_TTL_SECONDS,
    ) -> None:
        self.cache_dir = cache_dir or config.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds
        self._limiter = RateLimiter(rate_limit)
        self._client = httpx.Client(
            headers={
                "User-Agent": config.user_agent(),
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
        )

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, url: str) -> Any | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        if self.ttl >= 0 and (time.time() - path.stat().st_mtime) > self.ttl:
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                envelope = json.load(fh)
            return envelope["body"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _write_cache(self, url: str, body: Any) -> None:
        path = self._cache_path(url)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump({"url": url, "body": body}, fh)
        tmp.replace(path)

    def get_json(self, url: str, use_cache: bool = True) -> Any:
        """GET a URL, returning parsed JSON. Uses the disk cache when fresh."""
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                return cached

        body = self._fetch_with_retry(url)
        self._write_cache(url, body)
        return body

    def _fetch_with_retry(self, url: str) -> Any:
        backoff = 1.0
        last_exc: Exception | None = None
        for _attempt in range(config.MAX_RETRIES):
            self._limiter.wait()
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code in (429, 503):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff
                time.sleep(delay)
                backoff *= 2
                continue

            resp.raise_for_status()
            return resp.json()

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"SEC request failed after {config.MAX_RETRIES} retries: {url}")

    def company_tickers(self) -> dict[str, Any]:
        return self.get_json(config.TICKERS_URL)

    def company_facts(self, cik10: str) -> dict[str, Any]:
        return self.get_json(config.COMPANYFACTS_URL.format(cik10=cik10))

    def submissions(self, cik10: str) -> dict[str, Any]:
        return self.get_json(config.SUBMISSIONS_URL.format(cik10=cik10))

    def company_concept(self, cik10: str, taxonomy: str, tag: str) -> dict[str, Any]:
        return self.get_json(
            config.COMPANYCONCEPT_URL.format(cik10=cik10, taxonomy=taxonomy, tag=tag)
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EdgarClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

def resolve_cik(client: EdgarClient, query: str) -> tuple[int, str, str]:
    """Resolve a ticker (or company-name substring) to (cik, ticker, name).

    Ticker match is exact and case-insensitive; failing that we try a name substring.
    Raises LookupError if nothing matches.
    """
    data = client.company_tickers()
    q = query.strip().upper()
    rows = list(data.values()) if isinstance(data, dict) else list(data)

    for row in rows:
        if str(row.get("ticker", "")).upper() == q:
            return int(row["cik_str"]), str(row["ticker"]).upper(), str(row["title"])

    ql = query.strip().lower()
    for row in rows:
        if ql and ql in str(row.get("title", "")).lower():
            return int(row["cik_str"]), str(row["ticker"]).upper(), str(row["title"])

    raise LookupError(f"No SEC company matched query: {query!r}")

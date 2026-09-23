"""Shared test helpers. No network: everything reads committed fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_index() -> dict:
    return json.loads((FIXTURES / "index.json").read_text())


@pytest.fixture(scope="session")
def fixtures_index() -> dict:
    return load_index()


def load_companyfacts(ticker: str) -> dict:
    return json.loads((FIXTURES / f"{ticker}_companyfacts.json").read_text())

"""Free-tier Gemini engine: a real tool-use loop over the Gemini API."""

from __future__ import annotations

import os
import re
import threading
import time

import httpx

from .. import config
from ..tools import TOOL_SCHEMAS, ToolContext, dispatch
from .base import SYSTEM_PROMPT, Engine, ReportRequest

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_MIN_INTERVAL = float(os.environ.get("GEMINI_MIN_INTERVAL", "7.0"))
_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "6"))
_rate_lock = threading.Lock()
_last_call = [0.0]


def _pace() -> None:
    with _rate_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _retry_delay(body: str, default: float) -> float:
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    return float(m.group(1)) + 1.0 if m else default


def gemini_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def _tools() -> list[dict]:
    return [
        {
            "functionDeclarations": [
                {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
                for t in TOOL_SCHEMAS
            ]
        }
    ]


def _user_prompt(request: ReportRequest) -> str:
    if request.mode == "compare":
        return (
            f"Compare {', '.join(request.tickers)} using the tools, then write the cited "
            f"report using only token references for numbers."
        )
    return (
        f"Analyze {request.primary} for its last {request.years} fiscal years using the tools, "
        f"then write the cited report using only token references for numbers."
    )


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self) -> None:
        self.key = os.environ["GEMINI_API_KEY"]
        self.model = _model()
        self.client = httpx.Client(timeout=180)

    def _call(self, contents: list[dict], use_tools: bool = True) -> dict:
        body: dict = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        }
        if use_tools:
            body["tools"] = _tools()
        backoff = 5.0
        for _ in range(_MAX_ATTEMPTS):
            _pace()
            resp = self.client.post(
                API.format(model=self.model),
                headers={"x-goog-api-key": self.key, "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code in (429, 503):
                time.sleep(_retry_delay(resp.text, backoff))
                backoff = min(backoff * 2, 90.0)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def _run(self, ctx: ToolContext, contents: list[dict]) -> str:
        for _ in range(config.MAX_TOOL_CALLS + 1):
            data = self._call(contents)
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            usage = data.get("usageMetadata", {})
            ctx.logger.log(
                "model",
                engine=self.name,
                model=self.model,
                usage={
                    "input": usage.get("promptTokenCount", 0),
                    "output": usage.get("candidatesTokenCount", 0),
                },
            )
            fcalls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not fcalls:
                return "".join(p.get("text", "") for p in parts if "text" in p)
            contents.append({"role": "model", "parts": parts})
            resp_parts = []
            for fc in fcalls:
                result = dispatch(ctx, fc.get("name", ""), dict(fc.get("args", {}) or {}))
                resp_parts.append(
                    {"functionResponse": {"name": fc.get("name", ""), "response": {"result": result}}}
                )
            contents.append({"role": "user", "parts": resp_parts})
        contents.append({"role": "user", "parts": [{"text": "Now write the final report."}]})
        data = self._call(contents, use_tools=False)
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if "text" in p)

    def generate(self, ctx: ToolContext, request: ReportRequest) -> str:
        return self._run(ctx, [{"role": "user", "parts": [{"text": _user_prompt(request)}]}])

    def repair(self, ctx: ToolContext, request: ReportRequest, previous: str, violations: str) -> str:
        msg = (
            "Your previous report failed verification. These spans contain numbers that "
            "were not tokens, or tokens that do not exist in the ledger:\n\n"
            f"{violations}\n\n"
            "Rewrite the full report. Replace every offending number with the correct token "
            "from the tool results, or with words. Do not introduce new numbers.\n\n"
            f"Previous report:\n{previous}"
        )
        return self._run(ctx, [{"role": "user", "parts": [{"text": msg}]}])

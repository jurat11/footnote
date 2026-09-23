"""Optional free local engine: a real tool-use loop against a local Ollama server.

Enabled only when a local Ollama server and model are reachable. Lets Footnote run as a
true LLM agent at zero cost. If Ollama is not running, the template engine is used.
"""

from __future__ import annotations

import json
import os

import httpx

from .. import config
from ..tools import TOOL_SCHEMAS, ToolContext, dispatch
from .base import SYSTEM_PROMPT, Engine, ReportRequest


def _host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

def _model() -> str:
    return os.environ.get("OLLAMA_MODEL", "llama3.1")

def ollama_available() -> bool:
    try:
        r = httpx.get(f"{_host()}/api/tags", timeout=1.5)
        r.raise_for_status()
        names = {m.get("name", "").split(":")[0] for m in r.json().get("models", [])}
        return _model().split(":")[0] in names or bool(names)
    except (httpx.HTTPError, ValueError):
        return False

def _ollama_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in TOOL_SCHEMAS
    ]

def _user_prompt(request: ReportRequest) -> str:
    if request.mode == "compare":
        return f"Compare {', '.join(request.tickers)} using the tools, then write the cited report with token numbers only."
    return f"Analyze {request.primary} for its last {request.years} fiscal years using the tools, then write the cited report with token numbers only."

class OllamaEngine(Engine):
    name = "ollama"

    def __init__(self) -> None:
        self.host = _host()
        self.model = _model()

    def _chat(self, messages: list[dict], use_tools: bool = True) -> dict:
        payload = {"model": self.model, "messages": messages, "stream": False}
        if use_tools:
            payload["tools"] = _ollama_tools()
        r = httpx.post(f"{self.host}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()

    def _run(self, ctx: ToolContext, messages: list[dict]) -> str:
        for _ in range(config.MAX_TOOL_CALLS + 1):
            data = self._chat(messages)
            msg = data.get("message", {})
            ctx.logger.log("model", engine=self.name, model=self.model,
                           eval_count=data.get("eval_count"), prompt_eval_count=data.get("prompt_eval_count"))
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return msg.get("content", "")
            messages.append(msg)
            for call in tool_calls:
                fn = call.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = dispatch(ctx, fn.get("name", ""), args)
                messages.append({"role": "tool", "content": json.dumps(result, default=str)})
        messages.append({"role": "user", "content": "Now write the final report."})
        return self._chat(messages, use_tools=False).get("message", {}).get("content", "")

    def generate(self, ctx: ToolContext, request: ReportRequest) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": _user_prompt(request)}]
        return self._run(ctx, messages)

    def repair(self, ctx: ToolContext, request: ReportRequest, previous: str, violations: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Your previous report failed verification. Offending spans:\n"
                f"{violations}\n\nRewrite the full report using only ledger tokens for numbers.\n\n"
                f"Previous report:\n{previous}"
            )},
        ]
        return self._run(ctx, messages, )

"""Optional paid engine: the real native tool-use loop, used only if a key is set.

This is here so Footnote is a genuine agent when an API key exists. With no key the
template engine runs instead and the project costs nothing.
"""

from __future__ import annotations

import importlib.util
import os

from .. import config
from ..tools import TOOL_SCHEMAS, ToolContext, dispatch
from .base import SYSTEM_PROMPT, Engine, ReportRequest


def anthropic_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    return importlib.util.find_spec("anthropic") is not None


def _user_prompt(request: ReportRequest) -> str:
    if request.mode == "compare":
        return (
            f"Compare these companies on aligned, cited metrics for their most recent fiscal years: "
            f"{', '.join(request.tickers)}. Use the tools to gather ledger ids, then write the report "
            f"using only token references for numbers."
        )
    return (
        f"Write the cited analysis of {request.primary} for its last {request.years} fiscal years. "
        f"Use the tools to gather ledger ids, then write the report using only token references for numbers."
    )

class AnthropicEngine(Engine):
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = config.model_id()

    def _run(self, ctx: ToolContext, messages: list[dict]) -> str:
        for _ in range(config.MAX_TOOL_CALLS + 1):
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
            ctx.logger.log(
                "model",
                engine=self.name,
                model=self.model,
                stop_reason=resp.stop_reason,
                usage={"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
            )
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = dispatch(ctx, block.name, dict(block.input))
                    import json

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
        messages.append({"role": "user", "content": "Now write the final report."})
        resp = self.client.messages.create(
            model=self.model, max_tokens=4096, system=SYSTEM_PROMPT, messages=messages
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def generate(self, ctx: ToolContext, request: ReportRequest) -> str:
        return self._run(ctx, [{"role": "user", "content": _user_prompt(request)}])

    def repair(self, ctx: ToolContext, request: ReportRequest, previous: str, violations: str) -> str:
        msg = (
            "Your previous report failed verification. These spans contain numbers that "
            "were not tokens, or tokens that do not exist in the ledger:\n\n"
            f"{violations}\n\n"
            "Rewrite the full report. Replace every offending number with the correct "
            "token from the tool results, or with words. Do not introduce new numbers.\n\n"
            f"Previous report:\n{previous}"
        )
        return self._run(ctx, [{"role": "user", "content": msg}])

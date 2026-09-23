"""Report-writer engines. The default (``template``) needs no API key."""

from __future__ import annotations

from .base import Engine, ReportRequest


def get_engine(name: str) -> Engine:
    """Return an engine by name, falling back to the template engine when a paid or
    local engine is unavailable (with a printed note)."""
    name = (name or "template").lower()
    if name == "template":
        from .template import TemplateEngine

        return TemplateEngine()
    if name == "anthropic":
        from .anthropic import AnthropicEngine, anthropic_available

        if anthropic_available():
            return AnthropicEngine()
        print("[footnote] anthropic engine unavailable (no ANTHROPIC_API_KEY or SDK); "
              "falling back to the free template engine.")
        from .template import TemplateEngine

        return TemplateEngine()
    if name == "ollama":
        from .ollama import OllamaEngine, ollama_available

        if ollama_available():
            return OllamaEngine()
        print("[footnote] ollama engine unavailable (no local server/model); "
              "falling back to the free template engine.")
        from .template import TemplateEngine

        return TemplateEngine()
    raise ValueError(f"unknown engine: {name!r}")


__all__ = ["Engine", "ReportRequest", "get_engine"]

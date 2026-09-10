"""Shared Claude chart analyst instance."""

from __future__ import annotations

from functools import lru_cache

from app.ai.claude_analyst import ClaudeChartAnalyst
from app.core.config import Settings, get_settings


@lru_cache
def get_claude_analyst() -> ClaudeChartAnalyst:
    s = get_settings()
    return ClaudeChartAnalyst(
        api_key=s.anthropic_api_key,
        model=s.claude_model,
        enabled=s.claude_chart_enabled,
    )


def reset_claude_analyst() -> None:
    get_claude_analyst.cache_clear()

"""Tests for Claude chart analyst (mocked API)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.claude_analyst import ClaudeChartAnalyst, summarize_candles


def test_summarize_candles_basic():
    candles = [
        {"time": 1000 + i * 300, "open": 2500 + i, "high": 2502 + i, "low": 2498 + i, "close": 2501 + i}
        for i in range(30)
    ]
    out = summarize_candles(candles)
    assert out["bars_total"] == 30
    assert out["last_ohlc"]["close"] > 2500
    assert out["ema20"] is not None
    assert out["rsi14"] is not None


@pytest.mark.asyncio
async def test_analyze_chart_mocked():
    analyst = ClaudeChartAnalyst(api_key="test-key", enabled=True)
    fake = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "bias": "WAIT",
                        "summary": "Range chop near EMA20.",
                        "structure": "Sideways",
                        "levels": {"support": 2470, "resistance": 2485, "invalidation": 2465},
                        "confluence": ["Flat EMAs"],
                        "risk_notes": ["Wait for break"],
                    }
                ),
            }
        ]
    }
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: fake
    mock_resp.text = ""

    candles = [
        {"time": 1000, "open": 2470, "high": 2475, "low": 2468, "close": 2472},
        {"time": 1300, "open": 2472, "high": 2478, "low": 2470, "close": 2476},
    ]

    with patch("app.ai.claude_analyst.httpx.AsyncClient") as mock_client:
        inst = mock_client.return_value.__aenter__.return_value
        inst.post = AsyncMock(return_value=mock_resp)
        result = await analyst.analyze_chart(candles=candles, timeframe="M5")
    assert result.ok is True
    assert result.bias == "WAIT"
    assert "Range" in result.summary


@pytest.mark.asyncio
async def test_analyze_chart_not_configured():
    analyst = ClaudeChartAnalyst(api_key="", enabled=False)
    result = await analyst.analyze_chart(candles=[])
    assert result.ok is False
    assert "not configured" in (result.error or "").lower()

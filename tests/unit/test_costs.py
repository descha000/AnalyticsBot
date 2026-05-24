"""Unit tests for costs/tracker.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import costs.tracker as tracker


@pytest.fixture(autouse=True)
def isolated_costs(tmp_path, monkeypatch):
    """Redirect _COSTS_DIR to a temp path for every test."""
    monkeypatch.setattr(tracker, "_COSTS_DIR", tmp_path)
    return tmp_path


class TestLogClaude:
    def test_creates_jsonl_file(self, isolated_costs):
        tracker.log_claude("test_call", "claude-sonnet-4-20250514", 1000, 200)
        files = list(isolated_costs.glob("usage_*.jsonl"))
        assert len(files) == 1

    def test_record_fields(self, isolated_costs):
        tracker.log_claude("test_call", "claude-sonnet-4-20250514", 1000, 200)
        lines = (isolated_costs / next(isolated_costs.glob("usage_*.jsonl")).name).read_text().splitlines()
        record = json.loads(lines[0])
        assert record["service"] == "claude"
        assert record["call"] == "test_call"
        assert record["model"] == "claude-sonnet-4-20250514"
        assert record["input_tokens"] == 1000
        assert record["output_tokens"] == 200
        assert "cost_usd" in record
        assert "ts" in record

    def test_cost_calculation_sonnet(self, isolated_costs):
        # Sonnet: $3/MTok input, $15/MTok output
        tracker.log_claude("test", "claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        files = list(isolated_costs.glob("usage_*.jsonl"))
        record = json.loads(files[0].read_text().splitlines()[0])
        assert record["cost_usd"] == pytest.approx(18.0, rel=1e-4)

    def test_unknown_model_uses_default_pricing(self, isolated_costs):
        tracker.log_claude("test", "unknown-model", 1_000_000, 0)
        files = list(isolated_costs.glob("usage_*.jsonl"))
        record = json.loads(files[0].read_text().splitlines()[0])
        assert record["cost_usd"] == pytest.approx(3.0, rel=1e-4)

    def test_appends_multiple_records(self, isolated_costs):
        tracker.log_claude("call1", "claude-sonnet-4-20250514", 100, 50)
        tracker.log_claude("call2", "claude-sonnet-4-20250514", 200, 80)
        files = list(isolated_costs.glob("usage_*.jsonl"))
        lines = files[0].read_text().splitlines()
        assert len(lines) == 2


class TestDailySummary:
    def test_returns_zero_when_no_file(self, isolated_costs):
        result = tracker.daily_summary("2026-01-01")
        assert result["total_usd"] == 0.0
        assert result["calls"] == []

    def test_sums_costs_correctly(self, isolated_costs):
        tracker.log_claude("call1", "claude-sonnet-4-20250514", 1_000_000, 0)
        tracker.log_claude("call2", "claude-sonnet-4-20250514", 0, 1_000_000)
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        result = tracker.daily_summary(today)
        assert result["total_usd"] == pytest.approx(18.0, rel=1e-4)
        assert len(result["calls"]) == 2

    def test_includes_date_in_result(self, isolated_costs):
        result = tracker.daily_summary("2026-03-15")
        assert result["date"] == "2026-03-15"

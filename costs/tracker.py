"""
Lightweight usage + cost logger for AnalyticsBot.

Appends one JSON line per API call to costs/usage_YYYY-MM-DD.jsonl (gitignored).
Mirrors the pattern in ShortsBot/costs/tracker.py — same API, same file format.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_COSTS_DIR = Path(__file__).parent

_CLAUDE_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-sonnet-4-6":        {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.80 / 1_000_000, "output":  4.00 / 1_000_000},
}
_DEFAULT_PRICING = {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000}


def log_claude(call: str, model: str, input_tokens: int, output_tokens: int) -> None:
    pricing = _CLAUDE_PRICING.get(model, _DEFAULT_PRICING)
    cost = input_tokens * pricing["input"] + output_tokens * pricing["output"]
    _append({
        "service": "claude",
        "call": call,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    })
    print(f"[costs] {call} -- {input_tokens}in / {output_tokens}out tokens -> ${cost:.4f}")


def daily_summary(date_str: str | None = None) -> dict:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    log_file = _COSTS_DIR / f"usage_{date_str}.jsonl"
    if not log_file.exists():
        return {"date": date_str, "total_usd": 0.0, "calls": []}

    calls = []
    total = 0.0
    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        calls.append(r)
        total += r.get("cost_usd", 0.0)

    return {"date": date_str, "total_usd": round(total, 4), "calls": calls}


def _append(record: dict) -> None:
    record["ts"] = datetime.now(timezone.utc).isoformat()
    log_file = _COSTS_DIR / f"usage_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

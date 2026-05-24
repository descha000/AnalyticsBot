"""
Per-game slot-completion tracking and model snapshot storage.

Persists to history/game_state.json. Entries older than 7 days are pruned on
every write to keep the file small.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_STATE_FILE = Path(__file__).parent / "game_state.json"
_RETENTION_DAYS = 7


def mark_slot_done(game_id: str, slot: str) -> None:
    """Record that *slot* has been processed for *game_id*."""
    state = _load()
    if game_id not in state:
        state[game_id] = {"created_at": _now_iso()}
    state[game_id][slot] = True
    _save(_prune(state))


def is_slot_done(game_id: str, slot: str) -> bool:
    return _load().get(game_id, {}).get(slot, False)


def save_model_snapshot(game_id: str, snapshot: dict) -> None:
    """Persist the pre-event Poisson result for use in the post-event script."""
    state = _load()
    if game_id not in state:
        state[game_id] = {"created_at": _now_iso()}
    state[game_id]["model_snapshot"] = snapshot
    _save(_prune(state))


def get_model_snapshot(game_id: str) -> dict | None:
    return _load().get(game_id, {}).get("model_snapshot")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _prune(state: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
    result = {}
    for gid, v in state.items():
        try:
            created = datetime.fromisoformat(v.get("created_at", "2000-01-01T00:00:00+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created > cutoff:
                result[gid] = v
        except (ValueError, TypeError):
            result[gid] = v  # keep entries we can't parse rather than silently drop
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

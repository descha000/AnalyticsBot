"""Unit tests for history/game_state.py."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import history.game_state as gs


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Redirect _STATE_FILE to a temp path for every test."""
    state_file = tmp_path / "game_state.json"
    monkeypatch.setattr(gs, "_STATE_FILE", state_file)
    return state_file


class TestMarkSlotDone:
    def test_mark_and_check(self):
        gs.mark_slot_done("game_1", "pre")
        assert gs.is_slot_done("game_1", "pre") is True

    def test_other_slot_not_marked(self):
        gs.mark_slot_done("game_1", "pre")
        assert gs.is_slot_done("game_1", "post") is False

    def test_other_game_not_marked(self):
        gs.mark_slot_done("game_1", "pre")
        assert gs.is_slot_done("game_2", "pre") is False

    def test_idempotent(self):
        gs.mark_slot_done("game_1", "pre")
        gs.mark_slot_done("game_1", "pre")
        assert gs.is_slot_done("game_1", "pre") is True

    def test_multiple_slots_same_game(self):
        gs.mark_slot_done("game_1", "pre")
        gs.mark_slot_done("game_1", "post")
        assert gs.is_slot_done("game_1", "pre") is True
        assert gs.is_slot_done("game_1", "post") is True


class TestIsSlotDone:
    def test_returns_false_for_missing_game(self):
        assert gs.is_slot_done("nonexistent", "pre") is False

    def test_returns_false_when_state_file_absent(self, isolated_state):
        assert not isolated_state.exists()
        assert gs.is_slot_done("game_1", "pre") is False


class TestModelSnapshot:
    def test_save_and_retrieve(self):
        snapshot = {"home_win_prob": 0.52, "expected_total": 5.4}
        gs.save_model_snapshot("game_1", snapshot)
        retrieved = gs.get_model_snapshot("game_1")
        assert retrieved == snapshot

    def test_returns_none_for_missing_game(self):
        assert gs.get_model_snapshot("nonexistent") is None

    def test_snapshot_survives_mark_slot_done(self):
        snapshot = {"home_win_prob": 0.52}
        gs.save_model_snapshot("game_1", snapshot)
        gs.mark_slot_done("game_1", "pre")
        assert gs.get_model_snapshot("game_1") == snapshot


class TestPrune:
    def test_old_entries_pruned(self, isolated_state):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        state = {"old_game": {"created_at": old_ts, "pre": True}}
        isolated_state.write_text(json.dumps(state), encoding="utf-8")

        gs.mark_slot_done("new_game", "pre")

        assert gs.is_slot_done("old_game", "pre") is False
        assert gs.is_slot_done("new_game", "pre") is True

    def test_recent_entries_kept(self, isolated_state):
        recent_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        state = {"recent_game": {"created_at": recent_ts, "pre": True}}
        isolated_state.write_text(json.dumps(state), encoding="utf-8")

        gs.mark_slot_done("another_game", "post")

        assert gs.is_slot_done("recent_game", "pre") is True


class TestCorruptStateFile:
    def test_handles_corrupt_json(self, isolated_state):
        isolated_state.write_text("NOT JSON", encoding="utf-8")
        assert gs.is_slot_done("game_1", "pre") is False

    def test_handles_corrupt_json_on_write(self, isolated_state):
        isolated_state.write_text("NOT JSON", encoding="utf-8")
        gs.mark_slot_done("game_1", "pre")
        assert gs.is_slot_done("game_1", "pre") is True

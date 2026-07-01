"""Tests for the local assignee-history state file."""

from __future__ import annotations

from openproject_cli import state


def test_history_roundtrip_and_merge(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    monkeypatch.setenv("OPENPROJECT_STATE", str(path))

    assert state.load_assignee_history("https://op.test", 7) == []

    state.save_assignee_history("https://op.test", 7, [3, 1, 2, 1])
    assert state.load_assignee_history("https://op.test", 7) == [1, 2, 3]

    # A different user / host is isolated.
    assert state.load_assignee_history("https://op.test", 8) == []
    assert state.load_assignee_history("https://other.test", 7) == []

    # Merging preserves prior ids.
    prior = set(state.load_assignee_history("https://op.test", 7))
    state.save_assignee_history("https://op.test", 7, prior | {10})
    assert state.load_assignee_history("https://op.test", 7) == [1, 2, 3, 10]


def test_corrupt_file_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("OPENPROJECT_STATE", str(path))
    assert state.load_assignee_history("https://op.test", 7) == []

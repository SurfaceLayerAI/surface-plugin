"""Tests for index_builder utilities."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _write_index(surface_dir, entries):
    surface_dir.mkdir(parents=True, exist_ok=True)
    with open(surface_dir / "session-index.jsonl", "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


class TestGetLinkedSessions:
    def test_get_linked_sessions_forward(self, tmp_path):
        """Forward link: impl-sess continues plan-sess, queried from impl-sess."""
        surface_dir = tmp_path / ".surface"
        _write_index(surface_dir, [
            {"session_id": "plan-sess", "plan_mode": True, "plan_paths": ["/path/plan.md"], "timestamp": "2024-01-01T00:00:00Z", "summary": "Plan"},
            {"session_id": "impl-sess", "continues_session": "plan-sess", "timestamp": "2024-01-01T01:00:00Z", "summary": "Impl"},
        ])
        from lib.index_builder import get_linked_sessions
        result = get_linked_sessions(surface_dir, "impl-sess")
        assert result == ["impl-sess", "plan-sess"]

    def test_get_linked_sessions_reverse(self, tmp_path):
        """Reverse link: querying plan-sess finds impl-sess that continues it."""
        surface_dir = tmp_path / ".surface"
        _write_index(surface_dir, [
            {"session_id": "plan-sess", "plan_mode": True, "plan_paths": ["/path/plan.md"], "timestamp": "2024-01-01T00:00:00Z", "summary": "Plan"},
            {"session_id": "impl-sess", "continues_session": "plan-sess", "timestamp": "2024-01-01T01:00:00Z", "summary": "Impl"},
        ])
        from lib.index_builder import get_linked_sessions
        result = get_linked_sessions(surface_dir, "plan-sess")
        assert result == ["impl-sess", "plan-sess"]

    def test_get_linked_sessions_unlinked(self, tmp_path):
        """Standalone session with no links returns only itself."""
        surface_dir = tmp_path / ".surface"
        _write_index(surface_dir, [
            {"session_id": "standalone", "timestamp": "2024-01-01T00:00:00Z", "summary": "Solo"},
        ])
        from lib.index_builder import get_linked_sessions
        result = get_linked_sessions(surface_dir, "standalone")
        assert result == ["standalone"]

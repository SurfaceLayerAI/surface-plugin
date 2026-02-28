"""Tests for the interactive pager module."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.pager import format_row, _print_plain, _PREFIX_WIDTH
import index_session


class TestFormatRow:
    def test_short_summary_single_line(self):
        """Summary shorter than width produces exactly one line."""
        lines = format_row("Feb 25 01:38", "sess-abc-123", "Yes", "No", "Short summary", 40)
        assert len(lines) == 1
        assert "Feb 25 01:38" in lines[0]
        assert "sess-abc-123" in lines[0]
        assert "Yes" in lines[0]
        assert "No" in lines[0]
        assert "Short summary" in lines[0]

    def test_long_summary_wraps(self):
        """Summary longer than width produces continuation lines."""
        long_summary = "This is a very long summary that should wrap " * 3
        lines = format_row("Feb 25 01:38", "sess-abc-123", "No", "Yes", long_summary, 30)
        assert len(lines) > 1

    def test_continuation_indent(self):
        """Continuation lines are indented to the summary column."""
        long_summary = "word " * 40
        lines = format_row("Feb 25 01:38", "sess-abc-123", "Yes", "Yes", long_summary, 20)
        assert len(lines) > 1
        for continuation in lines[1:]:
            assert continuation.startswith(" " * _PREFIX_WIDTH)

    def test_empty_summary(self):
        """Empty summary produces exactly one line."""
        lines = format_row("-", "sess-xyz-789", "-", "-", "", 40)
        assert len(lines) == 1
        assert "sess-xyz-789" in lines[0]

    def test_timestamp_appears_in_output(self):
        """Timestamp column appears at the start of the row."""
        lines = format_row("Mar 01 14:22", "sess-abc-123", "Yes", "No", "Summary", 40)
        assert lines[0].startswith("Mar 01 14:22")

    def test_dash_timestamp_for_unindexed(self):
        """Unindexed sessions show '-' for timestamp."""
        lines = format_row("-", "sess-abc-123", "-", "-", "-", 40)
        assert lines[0].startswith("-")


class TestPrintPlain:
    def test_prints_header_and_rows(self, capsys):
        """Plain output includes header, separator, and all rows."""
        rows = [
            {"timestamp": "Feb 25 01:38", "session_id": "sess-001", "summary": "First", "plan_mode": "Yes", "made_edits": "No"},
            {"timestamp": "-", "session_id": "sess-002", "summary": "-", "plan_mode": "-", "made_edits": "-"},
        ]
        _print_plain(rows)
        captured = capsys.readouterr()
        assert "TIMESTAMP" in captured.out
        assert "SESSION ID" in captured.out
        assert "PLAN" in captured.out
        assert "EDITS" in captured.out
        assert "SUMMARY" in captured.out
        assert "---" in captured.out
        assert "sess-001" in captured.out
        assert "First" in captured.out
        assert "Yes" in captured.out
        assert "Feb 25 01:38" in captured.out
        assert "sess-002" in captured.out

    def test_dash_for_missing_fields(self, capsys):
        """Unindexed sessions display '-' for plan, edits, and timestamp columns."""
        rows = [
            {"timestamp": "-", "session_id": "sess-003", "summary": "-", "plan_mode": "-", "made_edits": "-"},
        ]
        _print_plain(rows)
        captured = capsys.readouterr()
        assert "-" in captured.out
        assert "sess-003" in captured.out


class TestListSessionsFiltering:
    """Tests for empty/no-change session filtering in _list_sessions_with_status."""

    def _run(self, sessions, index_entries):
        """Run _list_sessions_with_status with mocked data, return plain output."""
        with patch.object(index_session, "list_sessions", return_value=sessions), \
             patch.object(index_session, "load_index", return_value=index_entries):
            index_session._list_sessions_with_status("/fake/project", Path("/fake/surface"))

    def test_filters_indexed_no_edits_no_plan(self, capsys):
        """Indexed sessions with made_edits=false and plan_mode=false are excluded."""
        sessions = [
            {"session_id": "sess-active"},
            {"session_id": "sess-empty"},
            {"session_id": "sess-unindexed"},
        ]
        index_entries = [
            {"session_id": "sess-active", "summary": "Did work", "made_edits": True, "plan_mode": False, "timestamp": "2026-01-01T00:00:00Z"},
            {"session_id": "sess-empty", "summary": "Nothing", "made_edits": False, "plan_mode": False, "timestamp": "2026-01-01T00:00:00Z"},
        ]
        self._run(sessions, index_entries)
        captured = capsys.readouterr()
        assert "sess-active" in captured.out
        assert "sess-empty" not in captured.out
        # Unindexed sessions are still shown
        assert "sess-unindexed" in captured.out

    def test_keeps_indexed_with_plan_mode(self, capsys):
        """Indexed sessions with plan_mode=true are kept even without edits."""
        sessions = [{"session_id": "sess-plan"}]
        index_entries = [
            {"session_id": "sess-plan", "summary": "Planned", "made_edits": False, "plan_mode": True, "timestamp": "2026-01-01T00:00:00Z"},
        ]
        self._run(sessions, index_entries)
        captured = capsys.readouterr()
        assert "sess-plan" in captured.out

    def test_keeps_indexed_with_edits(self, capsys):
        """Indexed sessions with made_edits=true are kept even without plan mode."""
        sessions = [{"session_id": "sess-edit"}]
        index_entries = [
            {"session_id": "sess-edit", "summary": "Edited", "made_edits": True, "plan_mode": False, "timestamp": "2026-01-01T00:00:00Z"},
        ]
        self._run(sessions, index_entries)
        captured = capsys.readouterr()
        assert "sess-edit" in captured.out

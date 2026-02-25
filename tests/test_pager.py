"""Tests for the interactive pager module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.pager import format_row, _print_plain, _PREFIX_WIDTH


class TestFormatRow:
    def test_short_summary_single_line(self):
        """Summary shorter than width produces exactly one line."""
        lines = format_row("sess-abc-123", "Short summary", 40)
        assert len(lines) == 1
        assert "sess-abc-123" in lines[0]
        assert "Short summary" in lines[0]

    def test_long_summary_wraps(self):
        """Summary longer than width produces continuation lines."""
        long_summary = "This is a very long summary that should wrap " * 3
        lines = format_row("sess-abc-123", long_summary, 30)
        assert len(lines) > 1

    def test_continuation_indent(self):
        """Continuation lines are indented to the summary column."""
        long_summary = "word " * 40
        lines = format_row("sess-abc-123", long_summary, 20)
        assert len(lines) > 1
        for continuation in lines[1:]:
            assert continuation.startswith(" " * _PREFIX_WIDTH)

    def test_empty_summary(self):
        """Empty summary produces exactly one line."""
        lines = format_row("sess-xyz-789", "", 40)
        assert len(lines) == 1
        assert "sess-xyz-789" in lines[0]


class TestPrintPlain:
    def test_prints_header_and_rows(self, capsys):
        """Plain output includes header, separator, and all rows."""
        rows = [
            {"session_id": "sess-001", "summary": "First"},
            {"session_id": "sess-002", "summary": "Not Indexed"},
        ]
        _print_plain(rows)
        captured = capsys.readouterr()
        assert "SESSION ID" in captured.out
        assert "SUMMARY" in captured.out
        assert "---" in captured.out
        assert "sess-001" in captured.out
        assert "First" in captured.out
        assert "sess-002" in captured.out
        assert "Not Indexed" in captured.out

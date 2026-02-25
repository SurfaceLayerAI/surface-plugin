"""Tests for transcript_reader module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry


def test_iter_entries_parses_jsonl(write_jsonl):
    entries = [{"type": "user", "n": 1}, {"type": "assistant", "n": 2}, {"type": "user", "n": 3}]
    path = write_jsonl("basic.jsonl", entries)
    result = list(iter_entries(path))
    assert result == entries


def test_iter_entries_skips_blank_lines(tmp_path):
    path = tmp_path / "blanks.jsonl"
    path.write_text('{"a": 1}\n\n\n{"b": 2}\n\n')
    result = list(iter_entries(path))
    assert result == [{"a": 1}, {"b": 2}]


def test_iter_entries_skips_malformed_json(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": true}\nNOT JSON\n{"also_ok": true}\n')
    result = list(iter_entries(path))
    assert result == [{"ok": True}, {"also_ok": True}]


def test_get_content_blocks_list():
    blocks = [{"type": "text", "text": "hello"}, {"type": "tool_use", "id": "t1"}]
    entry = {"message": {"role": "assistant", "content": blocks}}
    assert get_content_blocks(entry) == blocks


def test_get_content_blocks_string():
    entry = {"message": {"role": "assistant", "content": "hello world"}}
    assert get_content_blocks(entry) == [{"type": "text", "text": "hello world"}]


def test_get_content_blocks_missing():
    assert get_content_blocks({}) == []
    assert get_content_blocks({"message": {}}) == []
    assert get_content_blocks({"message": {"content": None}}) == []


def test_is_system_entry_meta():
    assert is_system_entry({"isMeta": True, "type": "user"}) is True


def test_is_system_entry_caveat():
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Some text <local-command-caveat> more text"}],
        },
    }
    assert is_system_entry(entry) is True


def test_is_system_entry_normal():
    entry = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Just a normal message"}],
        },
    }
    assert is_system_entry(entry) is False

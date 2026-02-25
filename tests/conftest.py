"""Shared pytest fixtures for surface plugin tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_session_dir(tmp_path):
    """Create a temp dir structure mimicking ~/.claude/projects/slug/ with a subagents/ subdirectory."""
    subagents = tmp_path / "subagents"
    subagents.mkdir()
    return tmp_path


@pytest.fixture
def write_jsonl(tmp_path):
    """Return a helper function that writes a list of dicts as JSONL."""

    def write(filename, entries):
        path = tmp_path / filename
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return path

    return write

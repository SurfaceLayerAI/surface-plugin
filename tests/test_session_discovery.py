"""Tests for session_discovery module."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.session_discovery import (
    get_project_slug,
    get_session_transcript_path,
    discover_plan_subagents,
    list_sessions,
)


def test_get_project_slug():
    assert get_project_slug("/Users/foo/bar") == "-Users-foo-bar"
    assert get_project_slug("/a/b/c") == "-a-b-c"


def test_get_session_transcript_path():
    path = get_session_transcript_path("ses123", "/Users/foo/bar")
    expected = Path.home() / ".claude" / "projects" / "-Users-foo-bar" / "ses123.jsonl"
    assert path == expected


def test_discover_plan_subagents(tmp_session_dir):
    # Write a transcript with a Plan Task and matching progress entry
    transcript = tmp_session_dir / "session.jsonl"
    entries = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_plan_001",
                        "name": "Task",
                        "input": {"subagent_type": "Plan", "description": "Make a plan"},
                    }
                ],
            },
        },
        {
            "type": "progress",
            "parentToolUseID": "toolu_plan_001",
            "data": {"agentId": "agent_xyz"},
        },
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    # Create the subagent file on disk
    subagent_file = tmp_session_dir / "subagents" / "agent-agent_xyz.jsonl"
    subagent_file.write_text("")

    result = discover_plan_subagents(transcript)
    assert len(result) == 1
    assert result[0]["agent_id"] == "agent_xyz"
    assert result[0]["subagent_path"] == subagent_file


def test_discover_plan_subagents_missing_file(tmp_session_dir):
    transcript = tmp_session_dir / "session.jsonl"
    entries = [
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_plan_002",
                        "name": "Task",
                        "input": {"subagent_type": "Plan", "description": "Plan"},
                    }
                ],
            },
        },
        {
            "type": "progress",
            "parentToolUseID": "toolu_plan_002",
            "data": {"agentId": "missing_agent"},
        },
    ]
    with open(transcript, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    # Do NOT create the subagent file
    result = discover_plan_subagents(transcript)
    assert result == []


def test_list_sessions(tmp_path, monkeypatch):
    # Create a fake project directory structure under tmp_path as ~/.claude/projects/slug/
    slug = "-Users-test-project"
    sessions_dir = tmp_path / ".claude" / "projects" / slug
    sessions_dir.mkdir(parents=True)

    # Create session files with different mtimes
    (sessions_dir / "old_session.jsonl").write_text("{}")
    time.sleep(0.05)
    (sessions_dir / "new_session.jsonl").write_text("{}")

    # Create a subdirectory that should be ignored
    sub = sessions_dir / "subagents"
    sub.mkdir()
    (sub / "agent-foo.jsonl").write_text("{}")

    # Monkeypatch Path.home() to point to tmp_path
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = list_sessions("/Users/test/project")
    assert len(result) == 2
    assert result[0]["session_id"] == "new_session"
    assert result[1]["session_id"] == "old_session"
    assert result[0]["mtime"] >= result[1]["mtime"]
    assert result[0]["path"] == sessions_dir / "new_session.jsonl"

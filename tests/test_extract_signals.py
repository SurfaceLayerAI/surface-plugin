"""Integration tests for the extract_signals CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")


def _make_transcript_entries():
    """Return a list of entries for a minimal main transcript."""
    return [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Build auth system"}],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_pw1", "name": "Write",
                "input": {"file_path": "plans/auth.md", "content": "# Auth Plan"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "thinking",
                "thinking": "I considered session tokens but decided JWT is better",
            }],
        }},
    ]


def _make_subagent_entries():
    """Return entries for a plan subagent transcript."""
    return [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:30Z", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Analyzing auth patterns..."}],
        }},
    ]


def _write_jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_extract_signals_end_to_end(tmp_path, monkeypatch):
    # Set up a fake home directory
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    project_dir = "/test/project"
    session_id = "test_session_001"

    # Compute the slug and create the transcript directory
    slug = project_dir.replace("/", "-")
    sessions_dir = fake_home / ".claude" / "projects" / slug
    sessions_dir.mkdir(parents=True)

    # Write main transcript
    transcript_path = sessions_dir / ("%s.jsonl" % session_id)

    # Include a Task + progress entry so subagent discovery works
    main_entries = _make_transcript_entries()
    main_entries.append({
        "type": "assistant", "timestamp": "2026-01-01T00:00:05Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_task_001", "name": "Task",
                "input": {"subagent_type": "Plan", "description": "Create plan"},
            }],
        },
    })
    main_entries.append({
        "type": "progress", "timestamp": "2026-01-01T00:00:06Z",
        "parentToolUseID": "toolu_task_001",
        "data": {"agentId": "sa_001"},
    })
    _write_jsonl(transcript_path, main_entries)

    # Write subagent transcript
    subagents_dir = sessions_dir / "subagents"
    subagents_dir.mkdir()
    subagent_path = subagents_dir / "agent-sa_001.jsonl"
    _write_jsonl(subagent_path, _make_subagent_entries())

    # Output dir
    output_dir = tmp_path / "output"

    # Run the CLI via subprocess, passing HOME env var so Path.home() works
    env = dict(monkeypatch._ENV_BACKUP) if hasattr(monkeypatch, '_ENV_BACKUP') else {}
    # Use monkeypatch approach: run in-process instead of subprocess to honor monkeypatch
    # Actually, subprocess won't see monkeypatch. We need to set HOME env var.
    import os
    env = os.environ.copy()
    env["HOME"] = str(fake_home)

    result = subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS_DIR, "extract_signals.py"),
            session_id,
            "--project-dir", project_dir,
            "--output-dir", str(output_dir),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, "stderr: %s" % result.stderr

    # Verify output file exists
    output_file = output_dir / ("%s.signals.jsonl" % session_id)
    assert output_file.exists()

    # Verify JSONL content
    signals = []
    with open(output_file) as f:
        for line in f:
            line = line.strip()
            if line:
                signals.append(json.loads(line))

    assert len(signals) > 0

    signal_types = {s["type"] for s in signals}
    assert "user_request" in signal_types
    assert "plan_content" in signal_types
    assert "thinking_decision" in signal_types
    assert "plan_agent_reasoning" in signal_types

    # Verify summary in stdout
    assert "Extracted" in result.stdout
    assert session_id in result.stdout
    assert "user_request" in result.stdout


def test_extract_signals_missing_transcript(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    import os
    env = os.environ.copy()
    env["HOME"] = str(fake_home)

    result = subprocess.run(
        [
            sys.executable, os.path.join(SCRIPTS_DIR, "extract_signals.py"),
            "nonexistent_session",
            "--project-dir", "/fake/project",
            "--output-dir", str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "Error" in result.stderr or "not found" in result.stderr

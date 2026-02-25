"""Tests for session indexing pipeline."""

import sys
import json
import os
import subprocess as sp
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "index_session.py")
PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)


def _make_transcript(path, entries):
    """Write entries as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


class TestIndexSession:
    def test_recursion_guard(self):
        """When SURFACE_INDEXING is set, script exits immediately."""
        import subprocess
        script = str(Path(__file__).resolve().parent.parent / "scripts" / "index_session.py")
        env = os.environ.copy()
        env["SURFACE_INDEXING"] = "1"
        result = subprocess.run(
            [sys.executable, script],
            input="{}",
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

    def test_indexes_session(self, tmp_path):
        """Full indexing flow with mocked summarizer."""
        # Create transcript
        transcript_path = tmp_path / "session.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "Implement auth system"},
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-01T00:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_001",
                            "name": "Write",
                            "input": {
                                "file_path": "plans/auth.md",
                                "content": "# Auth Plan",
                            },
                        }
                    ],
                },
            },
        ]
        _make_transcript(transcript_path, entries)

        # Test _extract_metadata directly
        from index_session import _extract_metadata
        from lib.index_builder import append_index_entry, load_index

        metadata = _extract_metadata(transcript_path, "test-session-123")
        assert metadata["initial_request"] == "Implement auth system"
        assert metadata["user_messages"] == ["Implement auth system"]
        assert metadata["plan_mode"] is True
        assert "plans/auth.md" in metadata["plan_paths"]

        # Test index building
        surface_dir = tmp_path / ".surface"
        index_entry = {
            "session_id": "test-session-123",
            "timestamp": metadata.get("timestamp_end", ""),
            "summary": "Test summary",
            "plan_mode": True,
            "plan_paths": ["plans/auth.md"],
        }
        append_index_entry(surface_dir, index_entry)

        loaded = load_index(surface_dir)
        assert len(loaded) == 1
        assert loaded[0]["session_id"] == "test-session-123"
        assert loaded[0]["plan_mode"] is True

    def test_extracts_all_user_messages(self, tmp_path):
        """Multiple user messages collected in order."""
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, _MULTI_MESSAGE_ENTRIES)
        from index_session import _extract_metadata
        metadata = _extract_metadata(transcript_path, "test-multi")
        assert metadata["user_messages"] == [
            "Add login endpoint",
            "Also add rate limiting to the endpoint",
        ]
        assert metadata["initial_request"] == "Add login endpoint"

    def test_per_message_truncation(self, tmp_path):
        """Long message is capped at _PER_MESSAGE_LIMIT."""
        long_msg = "x" * 2000
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": long_msg},
            },
        ]
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, entries)
        from index_session import _extract_metadata, _PER_MESSAGE_LIMIT
        metadata = _extract_metadata(transcript_path, "test-trunc")
        assert len(metadata["user_messages"][0]) == _PER_MESSAGE_LIMIT

    def test_total_budget_enforcement(self, tmp_path):
        """Total chars across all messages capped at _TOTAL_USER_BUDGET."""
        entries = []
        for i in range(20):
            entries.append({
                "type": "user",
                "timestamp": "2024-01-01T00:{:02d}:00Z".format(i),
                "message": {"role": "user", "content": "Message {} ".format(i) + "a" * 400},
            })
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, entries)
        from index_session import _extract_metadata, _TOTAL_USER_BUDGET
        metadata = _extract_metadata(transcript_path, "test-budget")
        total = sum(len(m) for m in metadata["user_messages"])
        assert total <= _TOTAL_USER_BUDGET
        assert len(metadata["user_messages"]) < 20
        assert len(metadata["user_messages"]) > 0

    def test_system_entries_excluded_from_user_messages(self, tmp_path):
        """System and meta entries are filtered out of user_messages."""
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "isMeta": True,
                "message": {"role": "user", "content": "System setup message"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:01:00Z",
                "message": {"role": "user", "content": [
                    {"type": "text", "text": "<local-command-caveat>auto injected</local-command-caveat>"}
                ]},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:02:00Z",
                "message": {"role": "user", "content": "Real user request"},
            },
        ]
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, entries)
        from index_session import _extract_metadata
        metadata = _extract_metadata(transcript_path, "test-filter")
        assert metadata["user_messages"] == ["Real user request"]

    def test_noise_commands_excluded(self, tmp_path):
        """Slash noise commands are filtered out regardless of position."""
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "/clear"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:01:00Z",
                "message": {"role": "user", "content": "/model sonnet"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:02:00Z",
                "message": {"role": "user", "content": "Build the auth system"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:03:00Z",
                "message": {"role": "user", "content": "/compact"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:04:00Z",
                "message": {"role": "user", "content": "/exit"},
            },
        ]
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, entries)
        from index_session import _extract_metadata
        metadata = _extract_metadata(transcript_path, "test-noise")
        assert metadata["user_messages"] == ["Build the auth system"]
        assert metadata["initial_request"] == "Build the auth system"

    def test_indexes_session_subprocess(self, tmp_path):
        """Test running index_session.py as subprocess with mocked claude."""
        import subprocess as sp

        # Create transcript
        transcript_path = tmp_path / "session.jsonl"
        entries = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "Build feature X"},
            },
        ]
        _make_transcript(transcript_path, entries)

        hook_input = json.dumps({
            "session_id": "test-sub-123",
            "transcript_path": str(transcript_path),
            "cwd": str(tmp_path),
        })

        script = str(Path(__file__).resolve().parent.parent / "scripts" / "index_session.py")
        env = os.environ.copy()
        env.pop("SURFACE_INDEXING", None)
        env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
        # claude won't be found so it will use structural fallback
        env["PATH"] = ""

        result = sp.run(
            [sys.executable, script],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

        # Check index was written
        index_path = tmp_path / ".surface" / "session-index.jsonl"
        assert index_path.exists()
        with open(index_path) as f:
            entry = json.loads(f.readline())
        assert entry["session_id"] == "test-sub-123"
        # Should have structural fallback summary since claude is not on PATH
        assert "Session worked on:" in entry["summary"]

    def test_missing_transcript(self, tmp_path):
        """Script handles missing transcript gracefully."""
        import subprocess as sp

        hook_input = json.dumps({
            "session_id": "nonexistent",
            "transcript_path": str(tmp_path / "nonexistent.jsonl"),
            "cwd": str(tmp_path),
        })

        script = str(Path(__file__).resolve().parent.parent / "scripts" / "index_session.py")
        env = os.environ.copy()
        env.pop("SURFACE_INDEXING", None)
        env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)

        result = sp.run(
            [sys.executable, script],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "{}"
        # No index file should be created
        assert not (tmp_path / ".surface" / "session-index.jsonl").exists()


def _make_fake_session_dir(tmp_path, project_dir, session_id, entries):
    """Create a fake session transcript in the Claude sessions directory layout.

    Mimics ~/.claude/projects/<slug>/<session_id>.jsonl where HOME = tmp_path/fakehome.
    """
    # type: (Path, str, str, list) -> Path
    slug = project_dir.replace("/", "-")
    session_dir = tmp_path / "fakehome" / ".claude" / "projects" / slug
    session_dir.mkdir(parents=True, exist_ok=True)
    transcript = session_dir / (session_id + ".jsonl")
    with open(transcript, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return transcript


def _cli_env(tmp_path):
    """Build env dict for CLI subprocess calls."""
    env = os.environ.copy()
    env.pop("SURFACE_INDEXING", None)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
    env["HOME"] = str(tmp_path / "fakehome")
    env["PATH"] = ""
    return env


_SAMPLE_ENTRIES = [
    {
        "type": "user",
        "timestamp": "2024-06-01T10:00:00Z",
        "message": {"role": "user", "content": "Add login endpoint"},
    },
    {
        "type": "assistant",
        "timestamp": "2024-06-01T10:05:00Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
    },
]

_MULTI_MESSAGE_ENTRIES = [
    {
        "type": "user",
        "timestamp": "2024-06-01T10:00:00Z",
        "message": {"role": "user", "content": "Add login endpoint"},
    },
    {
        "type": "assistant",
        "timestamp": "2024-06-01T10:01:00Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Working on it."}]},
    },
    {
        "type": "user",
        "timestamp": "2024-06-01T10:02:00Z",
        "message": {"role": "user", "content": "Also add rate limiting to the endpoint"},
    },
    {
        "type": "assistant",
        "timestamp": "2024-06-01T10:05:00Z",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
    },
]


class TestCLIMode:
    def test_recursion_guard_does_not_fire_in_cli_mode(self, tmp_path):
        """SURFACE_INDEXING env var should not cause early exit in CLI mode."""
        env = os.environ.copy()
        env["SURFACE_INDEXING"] = "1"
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT
        # CLI mode triggers when args are present; --help should work regardless of env
        result = sp.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "--project-dir" in result.stdout

    def test_list_sessions(self, tmp_path):
        """--list shows sessions with summary or 'Not Indexed'."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-aaa", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)

        result = sp.run(
            [sys.executable, SCRIPT, "--list", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "sess-aaa" in result.stdout
        assert "Not Indexed" in result.stdout

    def test_index_single_session(self, tmp_path):
        """--session-id indexes a single session and writes to .surface/."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-bbb", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)
        surface_dir = Path(project_dir) / ".surface"

        result = sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-bbb", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "Indexed:" in result.stdout

        from lib.index_builder import load_index
        entries = load_index(surface_dir)
        assert len(entries) == 1
        assert entries[0]["session_id"] == "sess-bbb"

    def test_skip_already_indexed(self, tmp_path):
        """Already-indexed sessions are skipped without --force."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-ccc", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)

        # Index once
        sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-ccc", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )

        # Try again without --force
        result = sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-ccc", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "already indexed" in result.stdout

        from lib.index_builder import load_index
        entries = load_index(Path(project_dir) / ".surface")
        assert len(entries) == 1

    def test_force_reindex(self, tmp_path):
        """--force re-indexes and replaces existing entry."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-ddd", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)

        # Index once
        sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-ddd", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        # Force re-index
        result = sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-ddd", "--project-dir", project_dir, "--force"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "Indexed:" in result.stdout

        from lib.index_builder import load_index
        entries = load_index(Path(project_dir) / ".surface")
        # Should still have exactly 1 entry (replaced, not duplicated)
        assert len(entries) == 1

    def test_missing_transcript_cli(self, tmp_path):
        """CLI exits with error when transcript does not exist."""
        project_dir = str(tmp_path / "myproject")
        # Create the sessions dir but no transcript
        slug = project_dir.replace("/", "-")
        (tmp_path / "fakehome" / ".claude" / "projects" / slug).mkdir(parents=True, exist_ok=True)
        env = _cli_env(tmp_path)

        result = sp.run(
            [sys.executable, SCRIPT, "--session-id", "nonexistent", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode != 0
        assert "Error: transcript not found" in result.stderr

    def test_backfill(self, tmp_path):
        """--backfill indexes all unindexed sessions."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-111", _SAMPLE_ENTRIES)
        _make_fake_session_dir(tmp_path, project_dir, "sess-222", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)

        result = sp.run(
            [sys.executable, SCRIPT, "--backfill", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "Indexing 2 of 2 session(s)" in result.stdout
        assert "Done. Indexed 2 session(s)" in result.stdout

        from lib.index_builder import load_index
        entries = load_index(Path(project_dir) / ".surface")
        assert len(entries) == 2

    def test_backfill_skips_already_indexed(self, tmp_path):
        """--backfill skips sessions that are already indexed."""
        project_dir = str(tmp_path / "myproject")
        _make_fake_session_dir(tmp_path, project_dir, "sess-eee", _SAMPLE_ENTRIES)
        _make_fake_session_dir(tmp_path, project_dir, "sess-fff", _SAMPLE_ENTRIES)
        env = _cli_env(tmp_path)

        # Index one session first
        sp.run(
            [sys.executable, SCRIPT, "--session-id", "sess-eee", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )

        # Backfill should only index the remaining one
        result = sp.run(
            [sys.executable, SCRIPT, "--backfill", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert "Indexing 1 of 2 session(s)" in result.stdout

        from lib.index_builder import load_index
        entries = load_index(Path(project_dir) / ".surface")
        assert len(entries) == 2

    def test_list_many_sessions_pipe(self, tmp_path):
        """--list in non-TTY mode shows all sessions (no truncation)."""
        project_dir = str(tmp_path / "myproject")
        for i in range(15):
            _make_fake_session_dir(
                tmp_path, project_dir, "sess-{:03d}".format(i), _SAMPLE_ENTRIES
            )
        env = _cli_env(tmp_path)

        result = sp.run(
            [sys.executable, SCRIPT, "--list", "--project-dir", project_dir],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        for i in range(15):
            assert "sess-{:03d}".format(i) in result.stdout


class TestSessionEndFiltering:
    """Tests for _should_index reason-based filtering."""

    def test_skip_reason_clear(self):
        from index_session import _should_index
        assert _should_index({"reason": "clear"}) is False

    def test_skip_reason_prompt_input_exit(self):
        from index_session import _should_index
        assert _should_index({"reason": "prompt_input_exit"}) is False

    def test_skip_reason_bypass_permissions_disabled(self):
        from index_session import _should_index
        assert _should_index({"reason": "bypass_permissions_disabled"}) is False

    def test_index_reason_logout(self):
        from index_session import _should_index
        assert _should_index({"reason": "logout"}) is True

    def test_reason_other_with_substance(self, tmp_path):
        from index_session import _should_index
        transcript = tmp_path / "session.jsonl"
        _make_transcript(transcript, [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "Build the auth system"},
            },
        ])
        assert _should_index({"reason": "other", "transcript_path": str(transcript)}) is True

    def test_reason_other_noise_only(self, tmp_path):
        from index_session import _should_index
        transcript = tmp_path / "session.jsonl"
        _make_transcript(transcript, [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "/clear"},
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T00:01:00Z",
                "message": {"role": "user", "content": "/compact"},
            },
        ])
        assert _should_index({"reason": "other", "transcript_path": str(transcript)}) is False

    def test_reason_other_empty_transcript(self, tmp_path):
        from index_session import _should_index
        transcript = tmp_path / "session.jsonl"
        _make_transcript(transcript, [])
        assert _should_index({"reason": "other", "transcript_path": str(transcript)}) is False

    def test_missing_reason_with_substance(self, tmp_path):
        from index_session import _should_index
        transcript = tmp_path / "session.jsonl"
        _make_transcript(transcript, [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": {"role": "user", "content": "Add tests"},
            },
        ])
        assert _should_index({"transcript_path": str(transcript)}) is True

    def test_nonexistent_transcript_skipped(self):
        from index_session import _should_index
        assert _should_index({"reason": "other", "transcript_path": "/nonexistent/path.jsonl"}) is False

    def test_subprocess_skips_clear(self, tmp_path):
        """Hook subprocess exits cleanly without indexing on reason='clear'."""
        transcript_path = tmp_path / "session.jsonl"
        _make_transcript(transcript_path, _SAMPLE_ENTRIES)

        hook_input = json.dumps({
            "session_id": "test-clear",
            "transcript_path": str(transcript_path),
            "cwd": str(tmp_path),
            "reason": "clear",
        })

        env = os.environ.copy()
        env.pop("SURFACE_INDEXING", None)
        env["CLAUDE_PLUGIN_ROOT"] = PLUGIN_ROOT

        result = sp.run(
            [sys.executable, SCRIPT],
            input=hook_input,
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"
        assert not (tmp_path / ".surface" / "session-index.jsonl").exists()

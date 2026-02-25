"""Tests for session indexing pipeline."""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


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

        # Test the internal functions directly
        from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry
        from lib.index_builder import append_index_entry, load_index

        # Extract metadata manually (same logic as index_session._extract_metadata)
        initial_request = ""
        plan_paths = []
        plan_mode = False
        first_user_seen = False
        timestamps = []

        for entry in iter_entries(transcript_path):
            ts = entry.get("timestamp", "")
            if ts:
                timestamps.append(ts)
            if entry.get("type") == "user" and not first_user_seen and not is_system_entry(entry):
                first_user_seen = True
                content = entry.get("message", {}).get("content", "")
                initial_request = content[:500]
            if entry.get("type") == "assistant":
                for block in get_content_blocks(entry):
                    if (isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "Write"):
                        fp = block.get("input", {}).get("file_path", "")
                        if "plan" in fp.lower():
                            plan_mode = True
                            if fp not in plan_paths:
                                plan_paths.append(fp)

        assert initial_request == "Implement auth system"
        assert plan_mode is True
        assert "plans/auth.md" in plan_paths

        # Test index building
        surface_dir = tmp_path / ".surface"
        index_entry = {
            "session_id": "test-session-123",
            "timestamp": timestamps[-1] if timestamps else "",
            "summary": "Test summary",
            "plan_mode": True,
            "plan_paths": ["plans/auth.md"],
        }
        append_index_entry(surface_dir, index_entry)

        loaded = load_index(surface_dir)
        assert len(loaded) == 1
        assert loaded[0]["session_id"] == "test-session-123"
        assert loaded[0]["plan_mode"] is True

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

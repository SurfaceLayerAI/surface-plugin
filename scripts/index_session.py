#!/usr/bin/env python3
"""SessionEnd hook: index a completed Claude Code session."""
import sys
import os
import json
from pathlib import Path

# Recursion guard
if os.environ.get("SURFACE_INDEXING"):
    print("{}")
    sys.exit(0)

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry
from lib.summarizer import summarize_session
from lib.index_builder import append_index_entry


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("{}")
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")

    if not transcript_path or not Path(transcript_path).exists():
        print("{}")
        sys.exit(0)

    # Extract metadata from transcript
    metadata = _extract_metadata(Path(transcript_path), session_id)

    # Get Claude-powered summary
    metadata["summary"] = summarize_session(metadata, PLUGIN_ROOT)

    # Build index entry
    entry = {
        "session_id": session_id,
        "timestamp": metadata.get("timestamp_end", ""),
        "summary": metadata["summary"],
        "plan_mode": metadata.get("plan_mode", False),
        "plan_paths": metadata.get("plan_paths", []),
    }

    # Append to index
    surface_dir = Path(cwd) / ".surface"
    append_index_entry(surface_dir, entry)

    print("{}")


def _extract_metadata(transcript_path, session_id):
    # type: (Path, str) -> dict
    """Extract structural metadata from a transcript."""
    initial_request = ""
    plan_paths = []
    timestamps = []
    plan_mode = False
    first_user_seen = False

    for entry in iter_entries(transcript_path):
        ts = entry.get("timestamp", "")
        if ts:
            timestamps.append(ts)

        entry_type = entry.get("type", "")

        # Get initial user request
        if entry_type == "user" and not first_user_seen and not is_system_entry(entry):
            first_user_seen = True
            content = entry.get("message", {}).get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = " ".join(parts)
            initial_request = content[:500]

        # Detect plan writes
        if entry_type == "assistant":
            for block in get_content_blocks(entry):
                if (isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Write"):
                    file_path = block.get("input", {}).get("file_path", "")
                    if "plan" in file_path.lower():
                        plan_mode = True
                        if file_path not in plan_paths:
                            plan_paths.append(file_path)

    return {
        "session_id": session_id,
        "initial_request": initial_request,
        "plan_paths": plan_paths,
        "plan_mode": plan_mode,
        "timestamp_start": timestamps[0] if timestamps else "",
        "timestamp_end": timestamps[-1] if timestamps else "",
    }


if __name__ == "__main__":
    main()

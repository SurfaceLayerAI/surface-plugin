#!/usr/bin/env python3
"""SessionEnd hook: index a completed Claude Code session."""
import sys
import os
import json
import argparse
from pathlib import Path

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry
from lib.summarizer import summarize_session
from lib.session_discovery import get_session_transcript_path, list_sessions
from lib.index_builder import append_index_entry, load_index, replace_index_entry


def main():
    if len(sys.argv) > 1:
        return _cli_main()
    # Hook mode: check recursion guard
    if os.environ.get("SURFACE_INDEXING"):
        print("{}")
        sys.exit(0)
    return _hook_main()


def _hook_main():
    """Hook mode: read session data from stdin and index it."""
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


def _cli_main():
    """CLI mode for retroactive session indexing."""
    parser = argparse.ArgumentParser(description="Index Claude Code sessions")
    parser.add_argument("--session-id", help="Session ID to index")
    parser.add_argument("--backfill", action="store_true", help="Index all unindexed sessions")
    parser.add_argument("--list", action="store_true", dest="list_sessions", help="List sessions with index status")
    parser.add_argument("--project-dir", required=True, help="Project directory")
    parser.add_argument("--force", action="store_true", help="Re-index already-indexed sessions")
    args = parser.parse_args()

    surface_dir = Path(args.project_dir) / ".surface"

    if args.list_sessions:
        return _list_sessions_with_status(args.project_dir, surface_dir)

    if args.backfill:
        return _backfill(args.project_dir, surface_dir, args.force)

    if args.session_id:
        return _index_single(args.session_id, args.project_dir, surface_dir, args.force)

    parser.print_help()
    sys.exit(1)


def _index_single(session_id, project_dir, surface_dir, force):
    # type: (str, str, Path, bool) -> None
    """Index a single session by ID."""
    # Check if already indexed
    if not force:
        existing = load_index(surface_dir)
        if any(e.get("session_id") == session_id for e in existing):
            print("Session {} is already indexed. Use --force to re-index.".format(session_id))
            return

    # Resolve transcript path
    transcript_path = get_session_transcript_path(session_id, project_dir)
    if not transcript_path.exists():
        print("Error: transcript not found at {}".format(transcript_path), file=sys.stderr)
        sys.exit(1)

    # Extract metadata and summarize
    metadata = _extract_metadata(transcript_path, session_id)
    metadata["summary"] = summarize_session(metadata, PLUGIN_ROOT)

    entry = {
        "session_id": session_id,
        "timestamp": metadata.get("timestamp_end", ""),
        "summary": metadata["summary"],
        "plan_mode": metadata.get("plan_mode", False),
        "plan_paths": metadata.get("plan_paths", []),
    }

    if force:
        replace_index_entry(surface_dir, entry)
    else:
        append_index_entry(surface_dir, entry)

    print("Indexed: {} - {}".format(session_id, entry["summary"][:80]))


def _backfill(project_dir, surface_dir, force):
    # type: (str, Path, bool) -> None
    """Index all unindexed sessions for the project."""
    sessions = list_sessions(project_dir)
    if not sessions:
        print("No sessions found for this project.")
        return

    existing = load_index(surface_dir)
    indexed_ids = {e.get("session_id") for e in existing}

    to_index = sessions if force else [s for s in sessions if s["session_id"] not in indexed_ids]

    if not to_index:
        print("All {} session(s) are already indexed.".format(len(sessions)))
        return

    print("Indexing {} of {} session(s)...".format(len(to_index), len(sessions)))
    indexed_count = 0

    for i, session in enumerate(to_index, 1):
        sid = session["session_id"]
        transcript_path = session["path"]
        print("  [{}/{}] {}...".format(i, len(to_index), sid[:12]))

        try:
            metadata = _extract_metadata(transcript_path, sid)
            metadata["summary"] = summarize_session(metadata, PLUGIN_ROOT)

            entry = {
                "session_id": sid,
                "timestamp": metadata.get("timestamp_end", ""),
                "summary": metadata["summary"],
                "plan_mode": metadata.get("plan_mode", False),
                "plan_paths": metadata.get("plan_paths", []),
            }

            if force:
                replace_index_entry(surface_dir, entry)
            else:
                append_index_entry(surface_dir, entry)

            indexed_count += 1
        except Exception as exc:
            print("    Warning: failed to index {}: {}".format(sid, exc), file=sys.stderr)

    print("Done. Indexed {} session(s).".format(indexed_count))


def _list_sessions_with_status(project_dir, surface_dir):
    # type: (str, Path) -> None
    """List all sessions with their index status."""
    sessions = list_sessions(project_dir)
    if not sessions:
        print("No sessions found for this project.")
        return

    existing = load_index(surface_dir)
    index_map = {e.get("session_id"): e for e in existing}

    print("{:<12} {:<38} {}".format("STATUS", "SESSION ID", "SUMMARY"))
    print("-" * 90)

    for session in sessions:
        sid = session["session_id"]
        indexed_entry = index_map.get(sid)

        if indexed_entry:
            status = "[indexed]"
            summary = indexed_entry.get("summary", "")[:60]
        else:
            status = "[unindexed]"
            # Quick peek at initial request from transcript
            try:
                metadata = _extract_metadata(session["path"], sid)
                summary = metadata.get("initial_request", "")[:60]
            except Exception:
                summary = "(unable to read transcript)"

        print("{:<12} {:<38} {}".format(status, sid, summary))


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

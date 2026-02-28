#!/usr/bin/env python3
"""SessionEnd hook: index a completed Claude Code session."""
import sys
import os
import json
import re
import argparse
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))

from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry, extract_user_text
from lib.summarizer import summarize_session, kill_all as _kill_summarizers
from lib.session_discovery import get_session_transcript_path, list_sessions
from lib.index_builder import append_index_entry, load_index, replace_index_entry


def _log(msg):
    # type: (str) -> None
    """Log a diagnostic message to stderr with [surface] prefix."""
    print("[surface] {}".format(msg), file=sys.stderr)


@functools.lru_cache(maxsize=1)
def _is_hook_mode():
    # type: () -> bool
    """True when running as a SessionEnd hook (no CLI args)."""
    return len(sys.argv) <= 1


def main():
    if len(sys.argv) > 1:
        return _cli_main()
    # Hook mode: check recursion guard
    if os.environ.get("SURFACE_INDEXING"):
        _log("skipped session — already indexing in another process")
        print("{}")
        sys.exit(0)
    return _hook_main()


def _hook_main():
    """Hook mode: read session data from stdin and index it."""
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _log("skipped session — could not read session data")
        print("{}")
        sys.exit(0)

    # Filter non-terminal events before doing any expensive work
    if not _should_index(hook_input):
        print("{}")
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    cwd = hook_input.get("cwd", "")

    if not transcript_path or not Path(transcript_path).exists():
        _log("skipped session {} — transcript file not found".format(session_id))
        print("{}")
        sys.exit(0)

    # Extract metadata from transcript
    metadata = _extract_metadata(Path(transcript_path), session_id)

    # Get Claude-powered summary
    metadata["summary"] = summarize_session(metadata, PLUGIN_ROOT)

    # Build index entry
    surface_dir = Path(cwd) / ".surface"
    entry = {
        "session_id": session_id,
        "timestamp": metadata.get("timestamp_end", ""),
        "summary": metadata["summary"],
        "plan_mode": metadata.get("plan_mode", False),
        "plan_paths": metadata.get("plan_paths", []),
        "made_edits": metadata.get("made_edits", False),
    }

    # Resolve session linkage
    continues_session = _resolve_continues_session(
        surface_dir, metadata.get("referenced_plan_paths", []), metadata.get("slug")
    )
    entry["continues_session"] = continues_session

    # Append to index
    append_index_entry(surface_dir, entry)

    _log("indexed session {}".format(session_id))
    print("{}")


def _cli_main():
    """CLI mode for retroactive session indexing."""
    parser = argparse.ArgumentParser(
        description="Index Claude Code sessions for the Surface plugin. "
        "Supports single-session indexing, batch backfill, and listing.",
        epilog="Examples:\n"
        "  %(prog)s --list --project-dir /path/to/repo\n"
        "  %(prog)s --backfill --limit 10 --project-dir /path/to/repo\n"
        "  %(prog)s --backfill --project-dir /path/to/repo          # all unindexed\n"
        "  %(prog)s --session-id abc123 --project-dir /path/to/repo\n"
        "  %(prog)s --session-id abc123 --force --project-dir /path/to/repo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--session-id",
        help="Index a single session by its ID. The session transcript must exist "
        "in the Claude Code sessions directory for the given --project-dir.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Index all unindexed sessions for the project. Combine with --limit "
        "to cap how many sessions are indexed (most recent first).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to index during --backfill. Sessions are "
        "ordered by recency, so --limit 10 indexes the 10 most recent unindexed "
        "sessions. Omit to index all unindexed sessions.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_sessions",
        help="List all discovered sessions with their index status (indexed or not). "
        "Output is paged in a TTY, plain text otherwise.",
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        help="Absolute path to the project directory. Used to locate session "
        "transcripts and the .surface/ output directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index sessions that are already in the index. Works with both "
        "--session-id and --backfill.",
    )
    args = parser.parse_args()

    surface_dir = Path(args.project_dir) / ".surface"

    if args.list_sessions:
        return _list_sessions_with_status(args.project_dir, surface_dir)

    if args.backfill:
        return _backfill(args.project_dir, surface_dir, args.force, args.limit)

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
        "made_edits": metadata.get("made_edits", False),
    }

    # Resolve session linkage
    continues_session = _resolve_continues_session(
        surface_dir, metadata.get("referenced_plan_paths", []), metadata.get("slug")
    )
    entry["continues_session"] = continues_session

    if force:
        replace_index_entry(surface_dir, entry)
    else:
        append_index_entry(surface_dir, entry)

    print("Indexed: {} - {}".format(session_id, entry["summary"][:80]))


_MAX_WORKERS = 10


def _process_session(session, surface_dir, plugin_root):
    # type: (dict, Path, str) -> dict
    """Process a single session: extract metadata, summarize, resolve linkage."""
    sid = session["session_id"]
    transcript_path = session["path"]
    metadata = _extract_metadata(transcript_path, sid)
    metadata["summary"] = summarize_session(metadata, plugin_root)
    entry = {
        "session_id": sid,
        "timestamp": metadata.get("timestamp_end", ""),
        "summary": metadata["summary"],
        "plan_mode": metadata.get("plan_mode", False),
        "plan_paths": metadata.get("plan_paths", []),
        "made_edits": metadata.get("made_edits", False),
    }
    continues_session = _resolve_continues_session(
        surface_dir, metadata.get("referenced_plan_paths", []), metadata.get("slug")
    )
    entry["continues_session"] = continues_session
    return entry


def _backfill(project_dir, surface_dir, force, limit=None):
    # type: (str, Path, bool, int) -> None
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

    total_unindexed = len(to_index)
    if limit is not None and limit < len(to_index):
        to_index = to_index[:limit]
        print("Indexing {} of {} unindexed session(s) (limited to {} most recent)...".format(
            len(to_index), total_unindexed, limit))
    else:
        print("Indexing {} of {} session(s)...".format(len(to_index), len(sessions)))
    indexed_count = 0

    try:
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(to_index))) as pool:
            futures = {
                pool.submit(_process_session, session, surface_dir, PLUGIN_ROOT): session
                for session in to_index
            }
            for future in as_completed(futures):
                session = futures[future]
                sid = session["session_id"]
                indexed_count += 1
                print("  [{}/{}] {}...".format(indexed_count, len(to_index), sid[:12]))
                try:
                    entry = future.result()
                    if force:
                        replace_index_entry(surface_dir, entry)
                    else:
                        append_index_entry(surface_dir, entry)
                except Exception as exc:
                    indexed_count -= 1
                    print("    Warning: failed to index {}: {}".format(sid, exc), file=sys.stderr)
    except KeyboardInterrupt:
        _kill_summarizers()
        pool.shutdown(wait=False, cancel_futures=True)
        print("\nInterrupted. Indexed {} session(s) before cancellation.".format(indexed_count))
        return

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

    # Coalesce linked sessions: child sessions (those with continues_session
    # pointing to a valid parent in the index) are merged into their parent row.
    children_of = {}  # parent_id -> [child_entry, ...]
    skip_ids = set()
    for entry in existing:
        parent_id = entry.get("continues_session")
        sid = entry.get("session_id")
        if parent_id and parent_id != sid and parent_id in index_map:
            children_of.setdefault(parent_id, []).append(entry)
            skip_ids.add(sid)

    rows = []
    for session in sessions:
        sid = session["session_id"]
        if sid in skip_ids:
            continue
        indexed_entry = index_map.get(sid)
        summary = indexed_entry.get("summary", "-") if indexed_entry else "-"

        plan_mode = indexed_entry.get("plan_mode") if indexed_entry else None
        made_edits = indexed_entry.get("made_edits") if indexed_entry else None

        # Merge flags from children (OR logic)
        for child in children_of.get(sid, []):
            if plan_mode is not True and child.get("plan_mode"):
                plan_mode = True
            if made_edits is not True and child.get("made_edits"):
                made_edits = True

        # Skip indexed sessions that produced no edits and no plan writes
        if indexed_entry and not made_edits and not plan_mode:
            continue

        if plan_mode is not None:
            plan_str = "Yes" if plan_mode else "No"
        else:
            plan_str = "-"

        if made_edits is not None:
            edits_str = "Yes" if made_edits else "No"
        else:
            edits_str = "-"

        if indexed_entry and indexed_entry.get("timestamp"):
            ts_raw = indexed_entry["timestamp"]
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                ts_str = dt.strftime("%b %d %H:%M")
            except (ValueError, AttributeError):
                ts_str = "-"
        else:
            ts_str = "-"

        rows.append({
            "timestamp": ts_str,
            "session_id": sid,
            "summary": summary,
            "plan_mode": plan_str,
            "made_edits": edits_str,
        })

    if sys.stdout.isatty():
        from lib.pager import run_pager
        run_pager(rows)
    else:
        from lib.pager import _print_plain
        _print_plain(rows)


# --- SessionEnd reason filtering ---

_SKIP_REASONS = frozenset(["prompt_input_exit", "bypass_permissions_disabled"])
_PLAN_CHECK_REASONS = frozenset(["clear"])
_INDEX_REASONS = frozenset(["logout"])


def _should_index(hook_input):
    # type: (dict) -> bool
    """Decide whether this SessionEnd event warrants indexing.

    Returns False for non-terminal events (permission changes).
    Returns True for definitive termination (logout).
    For plan-check reasons ('clear'), checks transcript for plan file writes.
    For ambiguous reasons ('other', missing), checks transcript for substance.
    """
    reason = hook_input.get("reason", "")
    session_id = hook_input.get("session_id", "")

    if reason in _SKIP_REASONS:
        if _is_hook_mode():
            _log("skipped session {} — not a terminal event".format(session_id))
        return False

    if reason in _INDEX_REASONS:
        return True

    if reason in _PLAN_CHECK_REASONS:
        transcript_path = hook_input.get("transcript_path", "")
        if not transcript_path or not Path(transcript_path).exists():
            if _is_hook_mode():
                _log("skipped session {} — /clear with no transcript".format(session_id))
            return False
        if _has_plan_content(Path(transcript_path)):
            return True
        if _is_hook_mode():
            _log("skipped session {} — /clear with no plan activity".format(session_id))
        return False

    # Ambiguous reason: check transcript for substance
    transcript_path = hook_input.get("transcript_path", "")
    if not transcript_path or not Path(transcript_path).exists():
        if _is_hook_mode():
            _log("skipped session {} — no transcript available".format(session_id))
        return False

    if _has_substantive_content(Path(transcript_path)):
        return True
    if _is_hook_mode():
        _log("skipped session {} — no substantive user messages".format(session_id))
    return False


def _has_substantive_content(transcript_path):
    # type: (Path) -> bool
    """True if the transcript contains at least one non-noise user message."""
    for entry in iter_entries(transcript_path):
        if entry.get("type") != "user":
            continue
        if is_system_entry(entry):
            continue
        text = extract_user_text(entry).strip()
        if text and not _is_noise_command(text):
            return True
    return False


def _has_plan_content(transcript_path):
    # type: (Path) -> bool
    """True if the transcript writes to plan files (plan-mode session)."""
    for entry in iter_entries(transcript_path):
        if entry.get("type") != "assistant":
            continue
        for block in get_content_blocks(entry):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") == "Write":
                file_path = block.get("input", {}).get("file_path", "")
                if "plan" in file_path.lower():
                    return True
    return False


_TOTAL_USER_BUDGET = 4000
_PER_MESSAGE_LIMIT = 800
_NOISE_COMMANDS = ("/clear", "/compact", "/model", "/cost", "/help", "/exit")


def _is_noise_command(text):
    # type: (str) -> bool
    """True if text is a slash command with no task content."""
    stripped = text.strip()
    for cmd in _NOISE_COMMANDS:
        if stripped == cmd or stripped.startswith(cmd + " "):
            return True
    return False


_PLAN_REF_RE = re.compile(r'[^\s"\'<>]*\.claude/plans/[^\s"\'<>]+\.md')


def _extract_metadata(transcript_path, session_id):
    # type: (Path, str) -> dict
    """Extract structural metadata from a transcript."""
    user_messages = []
    plan_paths = []
    referenced_plan_paths = []
    timestamps = []
    plan_mode = False
    made_edits = False
    slug = None
    budget_remaining = _TOTAL_USER_BUDGET

    for entry in iter_entries(transcript_path):
        ts = entry.get("timestamp", "")
        if ts:
            timestamps.append(ts)

        if not slug:
            slug = entry.get("slug")

        entry_type = entry.get("type", "")

        # Scan ALL user entries for plan path references (including system entries)
        if entry_type == "user":
            content = entry.get("message", {}).get("content", "")
            raw_text = content if isinstance(content, str) else " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            for match in _PLAN_REF_RE.findall(raw_text):
                if match not in referenced_plan_paths:
                    referenced_plan_paths.append(match)

        # Collect non-system user messages within budget
        if entry_type == "user" and not is_system_entry(entry) and budget_remaining > 0:
            text = extract_user_text(entry).strip()
            if text and not _is_noise_command(text):
                truncated = text[:_PER_MESSAGE_LIMIT]
                if len(truncated) > budget_remaining:
                    if budget_remaining > 50:
                        user_messages.append(truncated[:budget_remaining])
                    budget_remaining = 0
                else:
                    user_messages.append(truncated)
                    budget_remaining -= len(truncated)

        # Detect plan writes and code edits
        if entry_type == "assistant":
            for block in get_content_blocks(entry):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                if name == "Write":
                    file_path = block.get("input", {}).get("file_path", "")
                    if "plan" in file_path.lower():
                        plan_mode = True
                        if file_path not in plan_paths:
                            plan_paths.append(file_path)
                    else:
                        made_edits = True
                elif name == "Edit":
                    file_path = block.get("input", {}).get("file_path", "")
                    if "plan" not in file_path.lower():
                        made_edits = True
                elif name == "Read":
                    file_path = block.get("input", {}).get("file_path", "")
                    if ".claude/plans/" in file_path and file_path.endswith(".md"):
                        if file_path not in referenced_plan_paths:
                            referenced_plan_paths.append(file_path)

    # Fallback: check subagent transcripts for edits
    if not made_edits:
        subagents_dir = transcript_path.parent / "subagents"
        if subagents_dir.is_dir():
            for agent_file in sorted(subagents_dir.glob("agent-*.jsonl")):
                for entry in iter_entries(agent_file):
                    if entry.get("type") != "assistant":
                        continue
                    for block in get_content_blocks(entry):
                        if (isinstance(block, dict)
                            and block.get("type") == "tool_use"
                            and block.get("name") in ("Write", "Edit")):
                            file_path = block.get("input", {}).get("file_path", "")
                            if "plan" not in file_path.lower():
                                made_edits = True
                                break
                    if made_edits:
                        break
                if made_edits:
                    break

    initial_request = user_messages[0][:500] if user_messages else ""

    return {
        "session_id": session_id,
        "initial_request": initial_request,
        "user_messages": user_messages,
        "plan_paths": plan_paths,
        "referenced_plan_paths": referenced_plan_paths,
        "plan_mode": plan_mode,
        "made_edits": made_edits,
        "slug": slug,
        "timestamp_start": timestamps[0] if timestamps else "",
        "timestamp_end": timestamps[-1] if timestamps else "",
    }


def _resolve_continues_session(surface_dir, referenced_plan_paths, slug=None):
    # type: (Path, list, str) -> str
    """Find a plan-mode session whose plan_paths overlap with referenced_plan_paths or slug."""
    if not referenced_plan_paths and not slug:
        return None
    entries = load_index(surface_dir)
    plan_entries = [e for e in entries if e.get("plan_mode")]
    plan_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    # Primary: plan path overlap
    if referenced_plan_paths:
        ref_set = set(referenced_plan_paths)
        for entry in plan_entries:
            entry_plan_paths = set(entry.get("plan_paths", []))
            if ref_set & entry_plan_paths:
                return entry.get("session_id")

    # Fallback: match slug against plan_paths basenames
    if slug:
        slug_suffix = "/" + slug + ".md"
        for entry in plan_entries:
            for pp in entry.get("plan_paths", []):
                if pp.endswith(slug_suffix):
                    return entry.get("session_id")

    return None


if __name__ == "__main__":
    main()

"""Index file I/O for session-index.jsonl."""

import json
from pathlib import Path
from typing import List


def append_index_entry(surface_dir, entry):
    # type: (Path, dict) -> None
    """Append a single JSON line to surface_dir/session-index.jsonl."""
    surface_dir.mkdir(parents=True, exist_ok=True)
    index_path = surface_dir / "session-index.jsonl"
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_index(surface_dir):
    # type: (Path) -> List[dict]
    """Read all lines from session-index.jsonl, return list of dicts."""
    index_path = surface_dir / "session-index.jsonl"
    if not index_path.exists():
        return []
    entries = []
    with open(index_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
    return entries


def replace_index_entry(surface_dir, entry):
    # type: (Path, dict) -> None
    """Replace an existing entry with the same session_id, or append if not found."""
    entries = load_index(surface_dir)
    session_id = entry.get("session_id")
    entries = [e for e in entries if e.get("session_id") != session_id]
    entries.append(entry)
    _write_index(surface_dir, entries)


def _write_index(surface_dir, entries):
    # type: (Path, list) -> None
    """Overwrite session-index.jsonl with the given entries."""
    surface_dir.mkdir(parents=True, exist_ok=True)
    index_path = surface_dir / "session-index.jsonl"
    with open(index_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def get_recent_plan_sessions(surface_dir, limit=4):
    # type: (Path, int) -> List[dict]
    """Return the most recent plan sessions from the index."""
    entries = load_index(surface_dir)
    plan_entries = [e for e in entries if e.get("plan_mode")]
    plan_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return plan_entries[:limit]


def get_linked_sessions(surface_dir, session_id):
    # type: (Path, str) -> List[str]
    """Return all session IDs linked to session_id via continues_session.

    Follows links in both directions:
    - Forward: session_id has continues_session pointing to a parent
    - Reverse: other sessions have continues_session pointing to session_id
    Returns the full set of linked IDs including session_id itself.
    """
    entries = load_index(surface_dir)
    entry_map = {e.get("session_id"): e for e in entries}

    linked = {session_id}
    queue = [session_id]

    while queue:
        current = queue.pop()
        current_entry = entry_map.get(current, {})

        # Forward: this session continues another
        parent = current_entry.get("continues_session")
        if parent and parent not in linked:
            linked.add(parent)
            queue.append(parent)

        # Reverse: other sessions continue this one
        for entry in entries:
            if entry.get("continues_session") == current:
                child = entry.get("session_id")
                if child and child not in linked:
                    linked.add(child)
                    queue.append(child)

    return sorted(linked)

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


def get_recent_plan_sessions(surface_dir, limit=4):
    # type: (Path, int) -> List[dict]
    """Return the most recent plan sessions from the index."""
    entries = load_index(surface_dir)
    plan_entries = [e for e in entries if e.get("plan_mode")]
    plan_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return plan_entries[:limit]

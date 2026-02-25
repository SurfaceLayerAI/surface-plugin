"""Session and subagent location utilities."""

import os
from pathlib import Path
from typing import List, Dict, Any

from lib.transcript_reader import iter_entries


def get_project_slug(project_path: str) -> str:
    """Convert a filesystem path to a Claude Code project slug.

    Replaces '/' with '-'. E.g., '/Users/foo/bar' -> '-Users-foo-bar'.
    """
    return project_path.replace("/", "-")


def get_session_transcript_path(session_id: str, project_path: str) -> Path:
    """Return the path to a session transcript JSONL file."""
    slug = get_project_slug(project_path)
    return Path.home() / ".claude" / "projects" / slug / (session_id + ".jsonl")


def discover_plan_subagents(transcript_path: Path) -> List[Dict[str, Any]]:
    """Find Task tool_use blocks with subagent_type == 'Plan' and match to progress entries.

    Returns list of dicts with keys 'agent_id' (str) and 'subagent_path' (Path).
    Only includes entries where the subagent JSONL file actually exists on disk.
    """
    # First pass: collect Task tool_use block IDs with subagent_type == "Plan"
    plan_task_ids = set()
    for entry in iter_entries(transcript_path):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                block.get("type") == "tool_use"
                and block.get("name") == "Task"
                and isinstance(block.get("input"), dict)
                and block["input"].get("subagent_type") == "Plan"
            ):
                block_id = block.get("id")
                if block_id:
                    plan_task_ids.add(block_id)

    if not plan_task_ids:
        return []

    # Second pass: find progress entries matching collected Task IDs
    agent_ids = []
    for entry in iter_entries(transcript_path):
        if entry.get("type") != "progress":
            continue
        parent_id = entry.get("parentToolUseID")
        if parent_id not in plan_task_ids:
            continue
        data = entry.get("data", {})
        if isinstance(data, dict):
            agent_id = data.get("agentId")
            if agent_id:
                agent_ids.append(agent_id)

    # Build results, filtering to only existing subagent files
    results = []
    subagents_dir = transcript_path.parent / "subagents"
    for agent_id in agent_ids:
        subagent_path = subagents_dir / ("agent-%s.jsonl" % agent_id)
        if subagent_path.exists():
            results.append({"agent_id": agent_id, "subagent_path": subagent_path})

    return results


def list_sessions(project_path: str) -> List[Dict[str, Any]]:
    """List all .jsonl session files in the project's Claude session directory.

    Returns list of dicts with keys 'session_id' (str), 'path' (Path), 'mtime' (float).
    Sorted by mtime descending (most recent first).
    Only lists files directly in the project directory (not subdirectories).
    """
    slug = get_project_slug(project_path)
    sessions_dir = Path.home() / ".claude" / "projects" / slug

    if not sessions_dir.is_dir():
        return []

    results = []
    for entry in os.scandir(str(sessions_dir)):
        if not entry.is_file():
            continue
        if not entry.name.endswith(".jsonl"):
            continue
        p = Path(entry.path)
        results.append({
            "session_id": p.stem,
            "path": p,
            "mtime": entry.stat().st_mtime,
        })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results

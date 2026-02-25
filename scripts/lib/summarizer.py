"""Session summarization via Claude subshell."""

import subprocess
import os
import json
import re
from pathlib import Path


def summarize_session(metadata, plugin_root):
    # type: (dict, str) -> str
    """Summarize session metadata using Claude, with structural fallback."""
    prompt = _build_prompt(metadata, plugin_root)

    try:
        env = os.environ.copy()
        env["SURFACE_INDEXING"] = "1"

        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku", "--no-session-persistence"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return _structural_fallback(metadata)


def _build_prompt(metadata, plugin_root):
    # type: (dict, str) -> str
    """Read agent template and inject metadata."""
    agent_path = Path(plugin_root) / "agents" / "indexer.md"

    try:
        template = agent_path.read_text()
        # Strip YAML frontmatter
        template = re.sub(r'^---\n.*?\n---\n', '', template, flags=re.DOTALL)
    except (FileNotFoundError, OSError):
        template = "Summarize this session metadata in 2-3 sentences:\n\n{metadata}"

    metadata_str = json.dumps(metadata, indent=2)
    return template.replace("{metadata}", metadata_str)


def _structural_fallback(metadata):
    # type: (dict) -> str
    """Produce a structural summary without LLM."""
    request = metadata.get("initial_request", "unknown task")[:100]
    plan_paths = metadata.get("plan_paths", [])
    paths_str = ", ".join(plan_paths) if plan_paths else "none"
    return "Session worked on: {}. Plan files: {}.".format(request, paths_str)

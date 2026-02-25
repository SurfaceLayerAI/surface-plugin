"""Low-level JSONL transcript parsing."""

import json
import sys
from pathlib import Path
from typing import Iterator, List


def iter_entries(path: Path) -> Iterator[dict]:
    """Yield parsed JSON entries line-by-line from a JSONL file.

    Skips blank lines and lines that fail JSON parsing.
    """
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                print(
                    "WARNING: skipping malformed JSON at line %d in %s"
                    % (line_num, path),
                    file=sys.stderr,
                )


def get_content_blocks(entry: dict) -> List[dict]:
    """Extract message.content from an entry as a list of content blocks.

    If message.content is a string, wraps it in [{"type": "text", "text": content}].
    If it's a list, returns it directly.
    If entry has no message or message.content, returns [].
    """
    message = entry.get("message")
    if not message:
        return []

    content = message.get("content")
    if content is None:
        return []

    if isinstance(content, str):
        return [{"type": "text", "text": content}]

    if isinstance(content, list):
        return content

    return []


def extract_user_text(entry):
    # type: (dict) -> str
    """Extract concatenated text content from a user entry.

    Content may be a string or a list of content blocks.
    Returns the joined text of all text-type blocks, or empty string.
    """
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


_SYSTEM_TAGS = ("<local-command-caveat>", "<local-command-stdout>", "<command-name>")


def is_system_entry(entry: dict) -> bool:
    """True for meta/system entries.

    An entry is a system entry if:
    - entry.get("isMeta") is truthy, OR
    - The entry type is "user" and any text content block contains
      a CLI-generated tag (local-command-caveat, local-command-stdout,
      or command-name for slash commands like /clear).
    """
    if entry.get("isMeta"):
        return True

    if entry.get("type") == "user":
        for block in get_content_blocks(entry):
            text = block.get("text", "") if block.get("type") == "text" else ""
            for tag in _SYSTEM_TAGS:
                if tag in text:
                    return True

    return False

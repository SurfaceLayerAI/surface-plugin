"""Signal extraction from transcripts."""

import difflib
import json
import re

from lib.transcript_reader import iter_entries, get_content_blocks, is_system_entry
from lib.signal_types import (
    make_signal,
    USER_REQUEST,
    PLAN_SNAPSHOT,
    PLAN_DELTA,
    USER_FEEDBACK,
    DESIGN_REASONING,
    TRADEOFF,
    UNCERTAINTY,
    FILES_CHANGED,
    SUBAGENT_SUMMARY,
)

DESIGN_RE = re.compile(
    r"(should|will|need to)\s+(use|create|implement|structure|organize|design)"
    r"|architecture|pattern|module|component|interface"
    r"|approach.*(because|since|given)",
    re.IGNORECASE | re.DOTALL,
)

TRADEOFF_RE = re.compile(
    r"instead of|rather than|versus|vs\."
    r"|rejected|discarded|ruled out"
    r"|considered.*(but|however)"
    r"|tradeoff|trade-off|downside|drawback"
    r"|pros and cons|advantages|disadvantages",
    re.IGNORECASE | re.DOTALL,
)

UNCERTAINTY_RE = re.compile(
    r"not sure|uncertain|unclear"
    r"|might (not |cause |break )"
    r"|risk|concern|worry|caveat"
    r"|TODO|FIXME|hack|workaround"
    r"|revisit|reconsider",
    re.IGNORECASE,
)

MIN_THINKING_LENGTH = 200

CODE_WRITE_TOOLS = ("Write", "Edit")


def _extract_user_text(entry):
    """Extract text content from a user entry.

    Content may be a string or a list of blocks.
    """
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _get_timestamp(entry):
    """Return the timestamp from an entry, or empty string."""
    return entry.get("timestamp", "")


class MainTranscriptExtractor:
    """Extracts signals from the main session transcript."""

    def __init__(self):
        self._plan_writes = {}  # path -> list of {content, timestamp, tool_use_id}
        self.first_user_seen = False
        self.last_plan_tool_use_id = None
        self._last_plan_path = None
        self._file_changes = {}  # path -> operation ("Write" or "Edit")

    def extract(self, transcript_path):
        """Process entries from a transcript and return a list of signal dicts."""
        signals = []

        for entry in iter_entries(transcript_path):
            entry_type = entry.get("type")
            ts = _get_timestamp(entry)

            if entry_type == "user" and not is_system_entry(entry):
                if not self.first_user_seen:
                    self.first_user_seen = True
                    text = _extract_user_text(entry)
                    signals.append(make_signal(USER_REQUEST, ts, content=text))
                elif self.last_plan_tool_use_id is not None:
                    text = _extract_user_text(entry)
                    if text.strip():
                        signals.append(make_signal(
                            USER_FEEDBACK,
                            ts,
                            content=text,
                            preceding_plan_path=self._last_plan_path,
                        ))

            if entry_type == "assistant":
                blocks = get_content_blocks(entry)
                for block in blocks:
                    block_type = block.get("type")

                    # Buffer plan writes for post-processing
                    if block_type == "tool_use" and block.get("name") == "Write":
                        file_path = block.get("input", {}).get("file_path", "")
                        if "plan" in file_path.lower():
                            block_id = block.get("id")
                            content = block.get("input", {}).get("content", "")

                            if file_path not in self._plan_writes:
                                self._plan_writes[file_path] = []
                            self._plan_writes[file_path].append({
                                "content": content,
                                "timestamp": ts,
                                "tool_use_id": block_id,
                            })

                            self.last_plan_tool_use_id = block_id
                            self._last_plan_path = file_path

                    # Track file changes (Write/Edit to non-plan files)
                    if block_type == "tool_use" and block.get("name") in CODE_WRITE_TOOLS:
                        file_path = block.get("input", {}).get("file_path", "")
                        if "plan" not in file_path.lower() and file_path:
                            self._file_changes[file_path] = block.get("name")

                    # Thinking block classification
                    if block_type == "thinking":
                        thinking_text = block.get("thinking", "")
                        if len(thinking_text) >= MIN_THINKING_LENGTH:
                            if DESIGN_RE.search(thinking_text):
                                signals.append(make_signal(
                                    DESIGN_REASONING,
                                    ts,
                                    content=thinking_text,
                                ))
                            if TRADEOFF_RE.search(thinking_text):
                                signals.append(make_signal(
                                    TRADEOFF,
                                    ts,
                                    content=thinking_text,
                                ))
                            if UNCERTAINTY_RE.search(thinking_text):
                                signals.append(make_signal(
                                    UNCERTAINTY,
                                    ts,
                                    content=thinking_text,
                                ))

                    # Assistant text block classification
                    if block_type == "text":
                        text_content = block.get("text", "")
                        if len(text_content) >= MIN_THINKING_LENGTH:
                            if DESIGN_RE.search(text_content):
                                signals.append(make_signal(
                                    DESIGN_REASONING,
                                    ts,
                                    content=text_content,
                                ))
                            if TRADEOFF_RE.search(text_content):
                                signals.append(make_signal(
                                    TRADEOFF,
                                    ts,
                                    content=text_content,
                                ))
                            if UNCERTAINTY_RE.search(text_content):
                                signals.append(make_signal(
                                    UNCERTAINTY,
                                    ts,
                                    content=text_content,
                                ))

        signals.extend(self._finalize_signals())
        return signals

    def _finalize_signals(self):
        """Emit plan_snapshot, plan_delta, and files_changed signals."""
        signals = []
        for path, writes in self._plan_writes.items():
            # Emit one snapshot with the last write's data
            last = writes[-1]
            signals.append(make_signal(
                PLAN_SNAPSHOT,
                last["timestamp"],
                path=path,
                content=last["content"],
                tool_use_id=last["tool_use_id"],
            ))

            # Emit deltas for consecutive pairs
            for i in range(1, len(writes)):
                old_content = writes[i - 1]["content"]
                new_content = writes[i]["content"]
                diff_lines = list(difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    n=1,
                ))
                if diff_lines:
                    signals.append(make_signal(
                        PLAN_DELTA,
                        writes[i]["timestamp"],
                        path=path,
                        diff="".join(diff_lines),
                        revision_number=i,
                        tool_use_id=writes[i]["tool_use_id"],
                    ))

        # Emit files_changed signal
        if self._file_changes:
            files = [
                {"path": p, "operation": op}
                for p, op in sorted(self._file_changes.items())
            ]
            signals.append(make_signal(
                FILES_CHANGED,
                "",
                files=files,
            ))

        return signals


class SubagentExtractor:
    """Extracts signals from any subagent transcript."""

    def extract(self, subagent_path, agent_id, subagent_type):
        """Process entries from a subagent transcript and return signal dicts."""
        signals = []

        for entry in iter_entries(subagent_path):
            if entry.get("type") != "assistant":
                continue

            ts = _get_timestamp(entry)
            blocks = get_content_blocks(entry)

            for block in blocks:
                if block.get("type") == "text":
                    signals.append(make_signal(
                        SUBAGENT_SUMMARY,
                        ts,
                        agent_id=agent_id,
                        subagent_type=subagent_type,
                        content=block.get("text", ""),
                    ))

        return signals

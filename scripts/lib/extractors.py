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
    THINKING_DECISION,
    EXPLORATION_CONTEXT,
    PLAN_AGENT_REASONING,
    PLAN_AGENT_EXPLORATION,
)

DECISION_RE = re.compile(
    r"alternative|tradeoff|instead|option|chose|decided|rejected|considered|approach",
    re.IGNORECASE,
)

EXPLORATION_TOOLS = ("Read", "Grep", "Glob", "Bash")
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
        self.code_writing_started = False
        self.first_user_seen = False
        self.last_plan_tool_use_id = None
        self._last_plan_path = None

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
                elif self.last_plan_tool_use_id is not None and not self.code_writing_started:
                    text = _extract_user_text(entry)
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

                    # Thinking decisions
                    if block_type == "thinking" and not self.code_writing_started:
                        thinking_text = block.get("thinking", "")
                        if DECISION_RE.search(thinking_text):
                            signals.append(make_signal(
                                THINKING_DECISION,
                                ts,
                                content=thinking_text,
                            ))

                    # Exploration context (only before code writing starts)
                    if block_type == "tool_use" and not self.code_writing_started:
                        tool_name = block.get("name", "")
                        if tool_name in EXPLORATION_TOOLS:
                            input_summary = json.dumps(block.get("input", {}))[:200]
                            signals.append(make_signal(
                                EXPLORATION_CONTEXT,
                                ts,
                                tool_name=tool_name,
                                input_summary=input_summary,
                            ))
                        elif tool_name in CODE_WRITE_TOOLS:
                            file_path = block.get("input", {}).get("file_path", "")
                            if "plan" not in file_path.lower():
                                self.code_writing_started = True

        signals.extend(self._finalize_plan_signals())
        return signals

    def _finalize_plan_signals(self):
        """Emit plan_snapshot and plan_delta signals from buffered plan writes."""
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

        return signals


class PlanSubagentExtractor:
    """Extracts signals from a plan subagent transcript."""

    def extract(self, subagent_path, agent_id):
        """Process entries from a subagent transcript and return signal dicts."""
        signals = []

        for entry in iter_entries(subagent_path):
            if entry.get("type") != "assistant":
                continue

            ts = _get_timestamp(entry)
            blocks = get_content_blocks(entry)

            for block in blocks:
                block_type = block.get("type")

                if block_type == "text":
                    signals.append(make_signal(
                        PLAN_AGENT_REASONING,
                        ts,
                        agent_id=agent_id,
                        content=block.get("text", ""),
                    ))
                elif block_type == "tool_use" and block.get("name") in EXPLORATION_TOOLS:
                    input_summary = json.dumps(block.get("input", {}))[:200]
                    signals.append(make_signal(
                        PLAN_AGENT_EXPLORATION,
                        ts,
                        agent_id=agent_id,
                        tool_name=block.get("name"),
                        input_summary=input_summary,
                    ))

        return signals

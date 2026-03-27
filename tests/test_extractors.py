"""Tests for signal extraction from transcripts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.extractors import MainTranscriptExtractor, SubagentExtractor
from lib.signal_types import (
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


def _pad_thinking(text):
    """Pad a short thinking string to exceed MIN_THINKING_LENGTH (200 chars)."""
    filler = (
        " This is additional context to ensure the thinking block meets the"
        " minimum length threshold for signal extraction processing."
    )
    while len(text) < 200:
        text += filler
    return text


# --- MainTranscriptExtractor ---


def test_extracts_user_request(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Build a REST API"}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    assert len(signals) == 1
    assert signals[0]["type"] == USER_REQUEST
    assert signals[0]["content"] == "Build a REST API"
    assert signals[0]["timestamp"] == "2026-01-01T00:00:00Z"


def test_extracts_plan_snapshot(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "# Design Plan"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    plan_signals = [s for s in signals if s["type"] == PLAN_SNAPSHOT]
    assert len(plan_signals) == 1
    assert plan_signals[0]["path"] == "plans/design.md"
    assert plan_signals[0]["content"] == "# Design Plan"
    assert plan_signals[0]["tool_use_id"] == "toolu_001"


def test_extracts_plan_delta(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v1"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_002", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v2"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    snapshots = [s for s in signals if s["type"] == PLAN_SNAPSHOT]
    assert len(snapshots) == 1
    assert snapshots[0]["content"] == "v2"
    assert snapshots[0]["tool_use_id"] == "toolu_002"

    deltas = [s for s in signals if s["type"] == PLAN_DELTA]
    assert len(deltas) == 1
    assert deltas[0]["revision_number"] == 1
    assert deltas[0]["tool_use_id"] == "toolu_002"
    assert "v1" in deltas[0]["diff"]
    assert "v2" in deltas[0]["diff"]


def test_plan_snapshot_uses_final_timestamp(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v1"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_002", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v2"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:03:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_003", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v3"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    snapshots = [s for s in signals if s["type"] == PLAN_SNAPSHOT]
    assert len(snapshots) == 1
    assert snapshots[0]["timestamp"] == "2026-01-01T00:03:00Z"
    assert snapshots[0]["content"] == "v3"
    assert snapshots[0]["tool_use_id"] == "toolu_003"


def test_multiple_plan_deltas(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v1"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_002", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v2"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:03:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_003", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "v3"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    deltas = [s for s in signals if s["type"] == PLAN_DELTA]
    assert len(deltas) == 2
    assert deltas[0]["revision_number"] == 1
    assert deltas[1]["revision_number"] == 2


def test_extracts_user_feedback(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Initial request"}],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "plan"},
            }],
        }},
        {"type": "user", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Use TypeScript instead"}],
        }},
        # Code write happens here
        {"type": "assistant", "timestamp": "2026-01-01T00:03:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_w1", "name": "Write",
                "input": {"file_path": "src/handler.ts", "content": "code"},
            }],
        }},
        # Feedback AFTER code write should still be captured (no code_writing_started gate)
        {"type": "user", "timestamp": "2026-01-01T00:04:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Fix the import path"}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    feedback = [s for s in signals if s["type"] == USER_FEEDBACK]
    assert len(feedback) == 2
    assert feedback[0]["content"] == "Use TypeScript instead"
    assert feedback[0]["preceding_plan_path"] == "plans/design.md"
    assert feedback[1]["content"] == "Fix the import path"


def test_user_feedback_filters_empty_content(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Initial request"}],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_001", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "plan"},
            }],
        }},
        {"type": "user", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "   "}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    feedback = [s for s in signals if s["type"] == USER_FEEDBACK]
    assert len(feedback) == 0


def test_extracts_design_reasoning(write_jsonl):
    thinking = _pad_thinking(
        "We should use a modular architecture for the plugin system."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    design = [s for s in signals if s["type"] == DESIGN_REASONING]
    assert len(design) == 1
    assert "should use" in design[0]["content"]


def test_extracts_tradeoff(write_jsonl):
    thinking = _pad_thinking(
        "I considered using a monorepo layout but decided against it because"
        " of the build complexity. Instead of a shared package, each service"
        " will bundle its own dependencies."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    tradeoffs = [s for s in signals if s["type"] == TRADEOFF]
    assert len(tradeoffs) == 1
    assert "instead of" in tradeoffs[0]["content"].lower()


def test_extracts_uncertainty(write_jsonl):
    thinking = _pad_thinking(
        "I'm not sure whether the downstream consumers can handle the new"
        " payload format. There is a risk that older clients will break if"
        " we change the schema without a migration period."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    uncertainties = [s for s in signals if s["type"] == UNCERTAINTY]
    assert len(uncertainties) == 1
    assert "not sure" in uncertainties[0]["content"]


def test_thinking_below_min_length_skipped(write_jsonl):
    # Under 200 chars but matches DESIGN_RE
    short_thinking = "We should use a modular architecture."
    assert len(short_thinking) < 200
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": short_thinking}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    thinking_signals = [
        s for s in signals
        if s["type"] in (DESIGN_REASONING, TRADEOFF, UNCERTAINTY)
    ]
    assert len(thinking_signals) == 0


def test_thinking_emits_multiple_signals(write_jsonl):
    thinking = _pad_thinking(
        "The architecture should use a plugin pattern for extensibility."
        " I considered using inheritance instead of composition but rejected"
        " that approach due to tight coupling."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    types = {s["type"] for s in signals}
    assert DESIGN_REASONING in types
    assert TRADEOFF in types


def test_thinking_not_gated_by_code_write(write_jsonl):
    thinking_before = _pad_thinking(
        "We need to implement the handler using a factory pattern."
    )
    thinking_after = _pad_thinking(
        "We should use connection pooling for the database module."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking_before}],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_w1", "name": "Write",
                "input": {"file_path": "src/handler.ts", "content": "code"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:03:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": thinking_after}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    design = [s for s in signals if s["type"] == DESIGN_REASONING]
    assert len(design) == 2


def test_extracts_files_changed(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_w1", "name": "Write",
                "input": {"file_path": "src/handler.ts", "content": "code"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_e1", "name": "Edit",
                "input": {"file_path": "src/utils.ts", "old_string": "a", "new_string": "b"},
            }],
        }},
        # Duplicate Write to same file should be deduplicated
        {"type": "assistant", "timestamp": "2026-01-01T00:03:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_w2", "name": "Write",
                "input": {"file_path": "src/handler.ts", "content": "code v2"},
            }],
        }},
        # Plan file should be excluded
        {"type": "assistant", "timestamp": "2026-01-01T00:04:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_pw1", "name": "Write",
                "input": {"file_path": "plans/design.md", "content": "plan"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    fc = [s for s in signals if s["type"] == FILES_CHANGED]
    assert len(fc) == 1
    paths = [f["path"] for f in fc[0]["files"]]
    assert "src/handler.ts" in paths
    assert "src/utils.ts" in paths
    assert len(paths) == 2
    # Plan files should not appear
    assert all("plan" not in p.lower() for p in paths)


def test_skips_system_entries_for_user_request(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "isMeta": True, "message": {
            "role": "user",
            "content": [{"type": "text", "text": "system init"}],
        }},
        {"type": "user", "timestamp": "2026-01-01T00:00:01Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "<local-command-caveat> system stuff"}],
        }},
        {"type": "user", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Real user request"}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    user_reqs = [s for s in signals if s["type"] == USER_REQUEST]
    assert len(user_reqs) == 1
    assert user_reqs[0]["content"] == "Real user request"


def test_extracts_reasoning_from_text_blocks(write_jsonl):
    text = _pad_thinking(
        "We should use a factory pattern to implement the plugin loader."
    )
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    design = [s for s in signals if s["type"] == DESIGN_REASONING]
    assert len(design) == 1
    assert "should use" in design[0]["content"]


def test_text_block_below_min_length_skipped(write_jsonl):
    short_text = "We should use a modular architecture."
    assert len(short_text) < 200
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": short_text}],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    reasoning_signals = [
        s for s in signals
        if s["type"] in (DESIGN_REASONING, TRADEOFF, UNCERTAINTY)
    ]
    assert len(reasoning_signals) == 0


# --- SubagentExtractor ---


def test_extracts_subagent_summary(write_jsonl):
    path = write_jsonl("sa.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:10Z", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Analyzing the codebase patterns..."}],
        }},
    ])
    signals = SubagentExtractor().extract(path, "agent_001", "Plan")
    assert len(signals) == 1
    assert signals[0]["type"] == SUBAGENT_SUMMARY
    assert signals[0]["agent_id"] == "agent_001"
    assert signals[0]["subagent_type"] == "Plan"
    assert signals[0]["content"] == "Analyzing the codebase patterns..."

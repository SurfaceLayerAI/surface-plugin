"""Tests for signal extraction from transcripts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.extractors import MainTranscriptExtractor, PlanSubagentExtractor
from lib.signal_types import (
    USER_REQUEST,
    PLAN_CONTENT,
    PLAN_REVISION,
    USER_FEEDBACK,
    THINKING_DECISION,
    EXPLORATION_CONTEXT,
    PLAN_AGENT_REASONING,
    PLAN_AGENT_EXPLORATION,
)


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


def test_extracts_plan_content(write_jsonl):
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
    plan_signals = [s for s in signals if s["type"] == PLAN_CONTENT]
    assert len(plan_signals) == 1
    assert plan_signals[0]["path"] == "plans/design.md"
    assert plan_signals[0]["content"] == "# Design Plan"
    assert plan_signals[0]["tool_use_id"] == "toolu_001"


def test_extracts_plan_revision(write_jsonl):
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
    revisions = [s for s in signals if s["type"] == PLAN_REVISION]
    assert len(revisions) == 1
    assert revisions[0]["revision_number"] == 1
    assert revisions[0]["content"] == "v2"
    assert revisions[0]["tool_use_id"] == "toolu_002"


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
    ])
    signals = MainTranscriptExtractor().extract(path)
    feedback = [s for s in signals if s["type"] == USER_FEEDBACK]
    assert len(feedback) == 1
    assert feedback[0]["content"] == "Use TypeScript instead"
    assert feedback[0]["preceding_plan_path"] == "plans/design.md"


def test_extracts_thinking_decision(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "thinking",
                "thinking": "I considered using REST but decided GraphQL is better",
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    decisions = [s for s in signals if s["type"] == THINKING_DECISION]
    assert len(decisions) == 1
    assert "considered" in decisions[0]["content"]


def test_extracts_exploration_context(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_r1", "name": "Read",
                "input": {"file_path": "src/config.ts"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:02:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_g1", "name": "Grep",
                "input": {"pattern": "export", "path": "src/"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    exploration = [s for s in signals if s["type"] == EXPLORATION_CONTEXT]
    assert len(exploration) == 2
    assert exploration[0]["tool_name"] == "Read"
    assert exploration[1]["tool_name"] == "Grep"


def test_stops_exploration_after_code_write(write_jsonl):
    path = write_jsonl("t.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:01:00Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_r1", "name": "Read",
                "input": {"file_path": "src/config.ts"},
            }],
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
            "content": [{
                "type": "tool_use", "id": "toolu_r2", "name": "Read",
                "input": {"file_path": "src/other.ts"},
            }],
        }},
    ])
    signals = MainTranscriptExtractor().extract(path)
    exploration = [s for s in signals if s["type"] == EXPLORATION_CONTEXT]
    assert len(exploration) == 1
    assert exploration[0]["tool_name"] == "Read"


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


# --- PlanSubagentExtractor ---


def test_extracts_plan_agent_reasoning(write_jsonl):
    path = write_jsonl("sa.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:10Z", "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Analyzing the codebase patterns..."}],
        }},
    ])
    signals = PlanSubagentExtractor().extract(path, "agent_001")
    assert len(signals) == 1
    assert signals[0]["type"] == PLAN_AGENT_REASONING
    assert signals[0]["agent_id"] == "agent_001"
    assert signals[0]["content"] == "Analyzing the codebase patterns..."


def test_extracts_plan_agent_exploration(write_jsonl):
    path = write_jsonl("sa.jsonl", [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:20Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_sa_r1", "name": "Read",
                "input": {"file_path": "src/middleware.ts"},
            }],
        }},
        {"type": "assistant", "timestamp": "2026-01-01T00:00:30Z", "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_sa_g1", "name": "Grep",
                "input": {"pattern": "auth", "path": "src/"},
            }],
        }},
    ])
    signals = PlanSubagentExtractor().extract(path, "agent_002")
    assert len(signals) == 2
    assert signals[0]["type"] == PLAN_AGENT_EXPLORATION
    assert signals[0]["tool_name"] == "Read"
    assert signals[0]["agent_id"] == "agent_002"
    assert signals[1]["tool_name"] == "Grep"

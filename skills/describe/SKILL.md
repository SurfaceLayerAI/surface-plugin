---
name: surface:describe
description: This skill should be used when the user asks to "generate PR description", "describe sessions", "surface describe", "write PR context", or "summarize development sessions". Extracts reasoning signals from Claude Code session transcripts and synthesizes a structured PR description.
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# Generate PR Description from Session Transcripts

You extract reasoning signals from Claude Code development sessions and synthesize a structured PR description that gives reviewers the context of a walkthrough.

## Input

`$ARGUMENTS` contains one or more session IDs separated by spaces.

If no session IDs are provided, inform the user:

> No session IDs provided. Run `/surface:browse` to select from recent sessions, or provide session IDs directly:
> `/surface:describe <session-id> [session-id...]`

## Steps

### 0. Expand linked sessions

Before extraction, read `.surface/session-index.jsonl` and expand each provided session ID to include any linked sessions. Two sessions are linked when one has a `continues_session` field pointing to the other (plan session ended with "Clear Context and Implement Plan"). Follow links in both directions and deduplicate. Proceed with the expanded list.

### 1. Extract signals

For each session ID in `$ARGUMENTS`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_signals.py <session_id> --project-dir $PWD --output-dir $PWD/.surface
```

If extraction fails for a session, report the error and continue with remaining sessions.

### 2. Read signals

Read each `.surface/<session_id>.signals.jsonl` file produced by the extraction step.

### 3. Estimate token count

Sum the character counts of all signals files and divide by 4 for a rough token estimate. If the estimate exceeds 100,000 tokens, warn the user:

> The combined signals contain approximately N tokens. Performance may degrade above 100K tokens. Consider selecting fewer sessions or a narrower scope.

Ask whether to proceed or select different sessions.

### 4. Synthesize PR description

Analyze all signals and produce a four-section PR description:

**Overview**: What changed and why, in 1-3 sentences. Ground this in the `user_request` signals and final plan state.

**Approach**: Key design decisions and what informed them. Draw from `plan_content`, `thinking_decision`, `plan_agent_reasoning`, and `exploration_context` signals. Focus on decisions a reviewer needs to understand, not implementation mechanics.

**Tradeoffs**: Alternatives the agent considered and rejected, especially where user feedback changed direction. This section has the highest value for reviewers. Draw from `plan_revision`, `user_feedback`, and `thinking_decision` signals. If no tradeoffs exist, omit this section rather than fabricating content.

**Review Focus**: Areas of uncertainty or complexity that deserve close attention. Identify from `thinking_decision` signals that express uncertainty, complex multi-step changes, or areas where the agent explored extensively before deciding.

For multi-session descriptions, narrate the reasoning arc across sessions chronologically. Bias toward the final session as authoritative since later sessions reflect the most current decisions.

### 5. Writing rules

Follow these rules for the PR description text:
- No contractions
- Active voice
- No em dashes
- Present tense
- No weak openers ("There is", "It is", etc.)

### 6. Present result

Display the generated PR description to the user.

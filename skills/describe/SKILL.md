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

#### Examples

The following examples illustrate the target output. The first includes all four sections; the second omits Tradeoffs because the development history contains no rejected alternatives or user-driven course corrections.

<example>
## Overview

This PR adds rate limiting to the `/api/upload` endpoint. Unthrottled uploads caused memory pressure during traffic spikes, triggering OOM kills on two production instances last week.

## Approach

The rate limiter uses an in-memory sliding window keyed by authenticated user ID. Each request records a timestamp, and the window function counts requests within the trailing 60-second interval. Requests exceeding the threshold receive a 429 response with a `Retry-After` header.

Authentication already runs as router-level middleware, so the user ID is available on the request context before the rate limiter executes. This avoids a second database lookup.

## Tradeoffs

The initial approach used a Redis-backed token bucket to support distributed rate limiting across instances. The developer rejected this direction because the application currently runs on a single instance and adding a Redis dependency increases infrastructure cost without immediate benefit.

The revised approach uses in-memory tracking, which means rate limits do not synchronize across instances. If the application scales to multiple instances, a shared backing store becomes necessary. For the current single-instance deployment, in-memory tracking provides accurate limiting with zero external dependencies.

## Review Focus

The sliding window cleanup runs on every request rather than on a background timer. Under sustained high traffic, the cleanup loop iterates over a growing timestamp list. Verify that the pruning logic in `rate_limiter.py:48-62` bounds memory growth acceptably for the expected request volume.
</example>

<example>
## Overview

This PR consolidates form validation logic into a single `FormValidator` module. Five controllers previously duplicated field-level validation with slight inconsistencies, causing different error messages for the same invalid input depending on which form the user submitted.

## Approach

The `FormValidator` module defines a rule registry where each field name maps to a validation function and an error template. Controllers call `FormValidator.validate(params, :profile)` with a schema name instead of inlining checks. The schema name selects the relevant subset of rules, so controllers that share fields (email, phone) enforce identical constraints.

Exploration of the existing controllers confirmed that all five use the same parameter naming conventions, making a shared registry feasible without renaming fields or adjusting form markup.

## Review Focus

The migration removes validation code from five controllers and replaces it with single-line `FormValidator` calls. Confirm that the test suite in `tests/test_form_validator.py` covers the edge cases each controller previously handled inline, particularly the postal code format variations in `AddressController`.
</example>

### 5. Writing rules

Follow these rules for the PR description text:
- No contractions
- Active voice
- No em dashes
- Present tense
- No weak openers ("There is", "It is", etc.)

### 6. Present result

Display the generated PR description to the user.

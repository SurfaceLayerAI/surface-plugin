# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Claude Code plugin for reducing the surface area of code review.

## Instructions

Each directory with a `CLAUDE.md` has one to help agents navigate the codebase. When you make changes, keep the relevant `CLAUDE.md` files current:

- **When to update**: Adding/removing routes, services, directories, pipeline nodes, models, or constraints. Changing patterns that other code depends on.
- **Quality > quantity**: Only document what an agent *must* know to work correctly in that directory. If something is obvious from the code, don't write it down.
- **Each file answers three questions**: What is here? What are the constraints? Where to look next?
- **No duplication**: Don't repeat what a parent `CLAUDE.md` already covers. Child files add specifics, not summaries of the parent.
- **No CLAUDE.md for trivial directories**: Single-file or self-evident directories are covered by their parent.

## Plugin Structure

- `.claude-plugin/plugin.json` — Plugin metadata
- `skills/describe/SKILL.md` — `/surface:describe` skill: extracts signals and synthesizes PR descriptions
- `skills/browse/SKILL.md` — `/surface:browse` skill: interactive session browser
- `hooks/hooks.json` — SessionEnd hook for automatic session indexing
- `agents/indexer.md` — Summarizer prompt template for session indexing
- `scripts/` — Python extraction and indexing pipeline (see `scripts/CLAUDE.md`)
- `.surface/` — Runtime output directory (gitignored). Contains signals files and session index.

## Constraints

- Python scripts use stdlib only. No pip dependencies.
- Python 3.9+ compatibility: no match statements, no `X | Y` union types.
- All user-facing prose follows `docs/guides/WRITING_STYLE.md`.
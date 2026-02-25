#!/usr/bin/env python3
"""CLI entry point for signal extraction from Claude Code transcripts."""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    str(Path(__file__).resolve().parent.parent),
)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.session_discovery import get_session_transcript_path, discover_plan_subagents
from lib.extractors import MainTranscriptExtractor, PlanSubagentExtractor


def main():
    parser = argparse.ArgumentParser(
        description="Extract review signals from a Claude Code session transcript.",
    )
    parser.add_argument("session_id", help="Session ID to extract signals from")
    parser.add_argument(
        "--project-dir",
        default=os.getcwd(),
        help="Project directory (default: current working directory)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <project-dir>/.surface)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(args.project_dir, ".surface")

    # Resolve transcript path
    transcript_path = get_session_transcript_path(args.session_id, args.project_dir)
    if not transcript_path.exists():
        print(
            "Error: transcript not found at %s" % transcript_path,
            file=sys.stderr,
        )
        sys.exit(1)

    # Discover plan subagents
    subagents = discover_plan_subagents(transcript_path)

    # Extract signals from main transcript
    main_signals = MainTranscriptExtractor().extract(transcript_path)

    # Extract signals from plan subagents
    subagent_signals = []
    for sa in subagents:
        sa_signals = PlanSubagentExtractor().extract(
            sa["subagent_path"], sa["agent_id"]
        )
        subagent_signals.extend(sa_signals)

    # Merge and sort by timestamp
    all_signals = main_signals + subagent_signals
    all_signals.sort(key=lambda s: s.get("timestamp", ""))

    # Write output
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "%s.signals.jsonl" % args.session_id)
    with open(output_path, "w", encoding="utf-8") as f:
        for signal in all_signals:
            f.write(json.dumps(signal) + "\n")

    # Print summary
    counts = Counter(s["type"] for s in all_signals)
    total_chars = sum(len(json.dumps(s)) for s in all_signals)

    print("Extracted %d signals from session %s" % (len(all_signals), args.session_id))
    for signal_type, count in sorted(counts.items()):
        print("  %s: %d" % (signal_type, count))
    print("Output: %s" % output_path)
    print("Estimated tokens: ~%d (chars/4)" % (total_chars // 4))


if __name__ == "__main__":
    main()

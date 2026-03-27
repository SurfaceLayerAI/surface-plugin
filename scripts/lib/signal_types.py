"""Signal type constants and factory function."""

USER_REQUEST = "user_request"
PLAN_SNAPSHOT = "plan_snapshot"
PLAN_DELTA = "plan_delta"
USER_FEEDBACK = "user_feedback"
DESIGN_REASONING = "design_reasoning"
TRADEOFF = "tradeoff"
UNCERTAINTY = "uncertainty"
FILES_CHANGED = "files_changed"
SUBAGENT_SUMMARY = "subagent_summary"


def make_signal(signal_type, timestamp, **kwargs):
    """Create a signal dict with type, timestamp, and additional fields.

    Args:
        signal_type: One of the signal type constants.
        timestamp: ISO 8601 timestamp string.
        **kwargs: Additional signal-specific fields.

    Returns:
        dict with "type", "timestamp", and any extra fields.
    """
    return {"type": signal_type, "timestamp": timestamp, **kwargs}

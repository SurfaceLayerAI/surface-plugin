"""Signal type constants and factory function."""

USER_REQUEST = "user_request"
PLAN_SNAPSHOT = "plan_snapshot"
PLAN_DELTA = "plan_delta"
USER_FEEDBACK = "user_feedback"
THINKING_DECISION = "thinking_decision"
EXPLORATION_CONTEXT = "exploration_context"
PLAN_AGENT_REASONING = "plan_agent_reasoning"
PLAN_AGENT_EXPLORATION = "plan_agent_exploration"


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

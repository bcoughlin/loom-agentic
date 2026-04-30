"""Tests for loom_agentic.policy.barrier."""

from __future__ import annotations

from loom_agentic.policy import policy_update_barrier_message


def test_barrier_message_includes_all_fields():
    msg = policy_update_barrier_message(
        agent_name="kepler_director",
        old_version="v2",
        old_sha="180cdc02deadbeef",
        new_version="v3",
        new_sha="abc12345f00d",
    )
    assert "kepler_director@v2" in msg
    assert "kepler_director@v3" in msg
    # Long sha truncated to 8
    assert "180cdc02" in msg
    assert "abc12345" in msg
    assert "180cdc02deadbeef" not in msg
    assert "[policy update]" in msg
    assert "Re-read the invariants" in msg


def test_barrier_handles_missing_sha():
    msg = policy_update_barrier_message(
        agent_name="x",
        old_version="v1",
        old_sha="",
        new_version="v2",
        new_sha="",
    )
    assert "(unknown)" in msg

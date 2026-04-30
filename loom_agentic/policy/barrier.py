"""Policy-update barrier message synthesis.

When a thread resumes under a newer policy than its last turn ran under,
the runtime injects a synthetic user message at the head of the current
turn's message list. The model sees: "your old patterns might be wrong;
re-read the invariants in your current system prompt."

Pure string templating — no IO, no SDK dependencies. Caller is responsible
for actually inserting the returned message into its provider-specific
message array.
"""

from __future__ import annotations


def policy_update_barrier_message(
    *,
    agent_name: str,
    old_version: str,
    old_sha: str,
    new_version: str,
    new_sha: str,
) -> str:
    """Return the verbatim barrier message body. The caller wraps it as a
    user/human message in whatever provider format it's using.

    Sha values can be passed at any length; only the first 8 chars are
    rendered (matches the format used by `Policy.sha`).
    """
    old_sha_short = (old_sha or "")[:8] or "(unknown)"
    new_sha_short = (new_sha or "")[:8] or "(unknown)"
    return (
        f"[policy update] This thread was previously running under "
        f"{agent_name}@{old_version} (sha {old_sha_short}). The policy has "
        f"changed to {agent_name}@{new_version} (sha {new_sha_short}). "
        f"The invariants and flowchart in your current system prompt take "
        f"precedence over any patterns from your earlier turns on this "
        f"thread. Re-read the invariants, then proceed."
    )

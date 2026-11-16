#!/usr/bin/env python3
"""Which transcript holds the tool history of the agent making this call.

The hook event's `transcript_path` is the SESSION transcript. A subagent's
tool calls are recorded in its own file,
`<session transcript without .jsonl>/subagents/agent-<agent_id>.jsonl`, and
the host adds `agent_id` to the event only for subagent calls. Measured
2026-10-24: a subagent's tool_use id appears in its own file and 0 times in
the session transcript. Judging a subagent by the session transcript credits
it with the parent's reads and pytest runs and hides its own.

Three outcomes; the caller decides what UNRESOLVED means:

- MAIN: no `agent_id`; the session transcript.
- SUBAGENT: a well-formed `agent_id` whose transcript exists.
- UNRESOLVED: `agent_id` present but malformed, or its file not found. No path
  is returned.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAIN = "main"
SUBAGENT = "subagent"
UNRESOLVED = "subagent_unresolved"

# Observed ids are 17 lowercase hex characters. Wider on purpose so a host
# format change does not make every subagent unresolved; narrow enough to rule
# out path separators and `..`, since the id becomes part of a filename.
_AGENT_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")


def session_transcript(event: dict[str, Any]) -> Path | None:
    raw = event.get("transcript_path") if isinstance(event, dict) else None
    if isinstance(raw, str) and raw:
        return Path(raw)
    return None


def acting_transcript(event: dict[str, Any]) -> tuple[Path | None, str]:
    """(transcript of the agent making this call, MAIN | SUBAGENT | UNRESOLVED)."""
    session = session_transcript(event)
    if not isinstance(event, dict) or "agent_id" not in event:
        return session, MAIN
    # The host omits the key for the main thread, so a present-but-unusable
    # id is a subagent call whose evidence cannot be located.
    agent_id = event.get("agent_id")
    if not isinstance(agent_id, str) or not _AGENT_ID_RE.match(agent_id) or session is None:
        return None, UNRESOLVED
    root = session.with_suffix("") / "subagents"
    name = f"agent-{agent_id}.jsonl"
    try:
        direct = root / name
        if direct.is_file():
            return direct, SUBAGENT
        if root.is_dir():
            for found in sorted(root.rglob(name)):
                if found.is_file():
                    return found, SUBAGENT
    except OSError:
        pass
    return None, UNRESOLVED

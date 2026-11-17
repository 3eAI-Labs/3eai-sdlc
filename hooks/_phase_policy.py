"""Phase-aware activation policy for 3eai-sdlc runtime hooks.

Reads `<cwd>/.sentinel/runtime/current_phase` (single line, e.g. "phase5",
"maintenance", "incident") and decides whether a given hook should run.

Design
------
- The matrix below is the single source of truth. Edit it to change behavior.
- Unknown phase (file missing/empty) ⇒ hook does NOT run. 3eAI SDLC's identity
  is "phase-gated"; without a declared phase there is no gate to enforce, and
  silently denying tool calls in a fresh install would be hostile. The plan
  anchor's route (`_project_state.hook_route`) is the one output outside this:
  in a project with deliverables it names the skill to enter.
- Errors ⇒ fail open (hook does NOT run). A broken policy must never trap the
  user out of their session.

The phase string is written by the phase or stage skill the user invokes
(e.g. `/phase5`, `/3eai-sdlc:build`). Operational modes (maintenance/incident)
write their own value.
"""

from __future__ import annotations

import os
from pathlib import Path

CURRENT_PHASE_FILE = Path(".sentinel") / "runtime" / "current_phase"

# Hook name → set of Enterprise phases and modes in which the hook is active.
_ENTERPRISE_POLICY: dict[str, frozenset[str]] = {
    "pivot_interceptor":    frozenset({"phase35", "phase5", "phase55", "maintenance", "incident", "track0"}),
    "forced_rule_set_gate": frozenset({"phase3", "phase35", "phase4", "phase5", "phase55", "phase6", "maintenance", "incident", "track0"}),
    "inject_plan_anchor":   frozenset({"phase1", "phase2", "phase3", "phase35", "phase4", "phase5", "phase55", "phase6", "maintenance", "incident", "track0"}),
    "auto_audit":           frozenset({"phase2", "phase3", "phase35", "phase4", "phase5", "phase55", "phase6", "maintenance", "incident", "track0"}),
    "side_effect_check":    frozenset({"phase35", "phase5", "phase55", "maintenance", "incident", "track0"}),
}

# A Core stage runs every hook of the Enterprise phases it stands for.
CORE_STANDS_FOR: dict[str, tuple[str, ...]] = {
    "define": ("phase1", "phase2"),
    "design": ("phase3", "phase4"),
    "build": ("phase5", "phase55"),
    "release": ("phase6",),
}

# Keep the hook-by-phase table in .claude-plugin/runtime/INSTALL.md equal to
# this matrix (tests/test_side_effect_check.py compares them).
PHASE_POLICY: dict[str, frozenset[str]] = {
    hook: phases | {stage for stage, stands_for in CORE_STANDS_FOR.items()
                    if any(p in phases for p in stands_for)}
    for hook, phases in _ENTERPRISE_POLICY.items()
}


def read_current_phase(cwd: Path) -> str:
    """Return the current phase string, or '' if unset/unreadable."""
    try:
        path = cwd / CURRENT_PHASE_FILE
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def is_active(hook_name: str, cwd: Path) -> bool:
    """Return True if `hook_name` should run for the current phase."""
    try:
        allowed = PHASE_POLICY.get(hook_name)
        if not allowed:
            return False
        phase = read_current_phase(cwd)
        if not phase:
            return False
        return phase in allowed
    except Exception:
        return False


def _holds_state(d: Path) -> bool:
    # `.sentinel-control` is rule_layers.CONTROL_DIR (not imported: every hook loads this)
    return (d / CURRENT_PHASE_FILE.parent).is_dir() or (d / ".sentinel-control").is_dir()


def project_root(cwd: Path) -> Path:
    """`$CLAUDE_PROJECT_DIR` when it holds `.sentinel/runtime` or
    `.sentinel-control`, else the nearest of `cwd` and its parents that does,
    else `cwd`.

    The session cwd follows the agent's `cd`; reading state from `cwd` alone
    switched the gate off after `cd src` (measured 2026-10-14). The project dir
    comes first: the agent can create either directory below it, and a nearer
    one switched the gate off (measured 2026-10-14)."""
    try:
        env = os.environ.get("CLAUDE_PROJECT_DIR")
        if env and _holds_state(Path(env)):
            return Path(env)
        here = Path(cwd).resolve()
        for d in (here, *here.parents):
            if _holds_state(d):
                return d
    except (OSError, RuntimeError, ValueError):
        pass
    return Path(cwd)

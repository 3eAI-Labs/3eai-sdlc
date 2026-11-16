#!/usr/bin/env python3
"""UserPromptSubmit hook: plan anchor + audit findings re-injection (sentinel).

Long conversations decay. Rules and commitments stated at the top of a session
lose weight as context fills. By the 50th turn, a model that opened with
"PostgreSQL only" can drift into MongoDB without ever being challenged. The
model cannot re-anchor itself because the forgetting is what prevents it from
noticing the drift. External re-injection is required.

Sources (any/all may be missing):
  1. `<project root>/.sentinel/runtime/active_plan.md` — the one plan file
  2. `<project root>/.sentinel/runtime/audit_log.json` — Stop-hook unresolved findings
  3. `<project root>/.sentinel/runtime/audit_findings_pending.json` — gate-flagged calls
  4. `plan_review.advisory` — a PLAN REVIEW block while `active_plan.md` has no
     converged or accepted /plan-review stamp for its current text (not in
     incident); for a plan edited after its review it lists what changed
  5. `_project_state.hook_route` — a SENTINEL ROUTE block, first, when the
     marker is missing, unknown or ahead of the project's derived phase in a
     project with deliverables (not on a `/` command prompt)

A plan larger than its room is condensed (`_plan_text.condense_plan`): the
header with its `**Constraints:**` block, the first phase with an open row,
and a notice naming the file.

Sources 1 and 4 and the skill-discipline reminder are Pro-only: they need
`_plan_prompt.py` and `plan_review.py`, imported at the point of use; without
them the hook prints the route and the audit blocks only.

If all sources empty → silent no-op.

Phase-gated: only runs in phases listed in `_phase_policy.PHASE_POLICY`; the
route (source 5) is the one output outside them.
Failure mode: any error inside main() → no output, exit 0; the failure is logged to `.sentinel/runtime/hook_errors.jsonl` and flagged on the next prompt (`_hook_log`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import _phase_policy  # noqa: E402

HOOK_NAME = "inject_plan_anchor"

_RUNTIME = Path(".sentinel") / "runtime"
AUDIT_LOG_RELATIVE_PATH = _RUNTIME / "audit_log.json"
AUDIT_PENDING_RELATIVE_PATH = _RUNTIME / "audit_findings_pending.json"
# The same file forced_rule_set_gate.py reads, and by the same rule: the flag is
# on when the file exists. This hook announced the gate as ON without ever
# reading it, so any prompt containing a trigger word ("fix", "add", "yap")
# produced a banner claiming a gate that was not armed, telling the reader that
# Edit/Write/Bash would be denied when nothing would deny them.
FORCED_RULE_SET_RELATIVE_PATH = Path(".sentinel-control") / "forced_rule_set"
HOOK_EVENT_NAME = "UserPromptSubmit"
PLAN_REVIEW_HEADER = "PLAN REVIEW (sentinel):"
ROUTE_HEADER = "SENTINEL ROUTE:"
AUDIT_HEADER = (
    "PRIOR-TURN AUDIT (auto-flagged by sentinel Stop hook — "
    "address each item or explicitly defer with reason):"
)
PENDING_HEADER = (
    "ACTION-TIME AUDIT FLAGS (flagged at action time in the prior turn — "
    "address each or explicitly defer with reason):"
)
# The host moves hook additionalContext above ~10,000 characters to a file and
# shows the model a ~2KB preview (measured). 8,000 leaves
# room for the JSON envelope. Findings and flags have fixed ceilings; the plan
# gets what is left after them and the skill reminder.
INLINE_BUDGET_CHARS = 8000
FINDINGS_MAX_CHARS = 1500
PENDING_MAX_CHARS = 1500
MAX_TARGETS_PER_FLAG = 5


def _read_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _resolve_cwd(event: dict[str, Any]) -> Path | None:
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        return Path(cwd)
    except (TypeError, ValueError):
        return None


def _plan_prompt():
    """The Pro-only plan module, or None when it is absent (the free edition)
    or broken: then the hook prints no plan block and no skill reminder."""
    try:
        import _plan_prompt as module  # noqa: E402
        return module
    except Exception:  # noqa: BLE001
        return None


def _read_first_anchor(cwd: Path) -> tuple[str, str]:
    """(the plan's text, its relative path); empty without `_plan_prompt`."""
    module = _plan_prompt()
    return module.read_first_anchor(cwd) if module else ("", "")


def _fit(text: str, cap: int, where: str) -> str:
    """`text` cut to `cap` characters at a line boundary, saying what was cut."""
    if len(text) <= cap:
        return text
    notice_template = "\n[trimmed: {n} more chars — full text in {where}]"
    room = max(0, cap - len(notice_template.format(n=len(text), where=where)))
    cut = text.rfind("\n", 0, room)
    if cut <= 0:
        cut = room
    head = text[:cut].rstrip()
    return head + notice_template.format(n=len(text) - len(head), where=where)


def _read_audit_log(path: Path) -> list[dict]:
    try:
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []


def _write_audit_log(path: Path, entries: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def _unresolved(path: Path) -> list[dict]:
    return [e for e in _read_audit_log(path)
            if isinstance(e, dict) and not e.get("resolved", False)]


def _mark_resolved(path: Path, shown: list[dict]) -> None:
    """Mark the entries the model was shown as resolved.

    Called only after the output was written, so a failed emit leaves them
    for the next prompt. Re-reads the file: the writers append and trim, so
    the list read before emitting may no longer match it.
    """
    if not shown:
        return
    entries = _read_audit_log(path)
    changed = False
    for e in entries:
        if isinstance(e, dict) and not e.get("resolved", False) and e in shown:
            e["resolved"] = True
            changed = True
    if changed:
        _write_audit_log(path, entries)


def _format_findings(entries: list[dict]) -> str:
    lines: list[str] = []
    for entry in entries:
        findings = entry.get("findings")
        if not isinstance(findings, list):
            continue
        for f in findings:
            if not isinstance(f, dict):
                f = {"message": f}
            line = f"- [{f.get('rule', '?')}] {f.get('message', '')}"
            ev = f.get("evidence", "")
            if ev:
                line += f"\n  evidence: {ev}"
            lines.append(line)
    return "\n".join(lines)


def _format_pending_flags(unresolved: list[dict]) -> str:
    if not unresolved:
        return ""
    # Collapsed by (decision, reason): the gate writes one flag per gated call,
    # so a standing condition came back as one identical line per call.
    groups: dict[tuple, list[dict]] = {}
    for e in unresolved:
        # str(): a non-string field in a flag is unhashable.
        key = (str(e.get("warden_decision", "?")), str(e.get("reason", "")))
        groups.setdefault(key, []).append(e)
    # Every distinct target stays visible: a flag's reason need not name the
    # file, so one line per group must not hide which files it covered.
    lines: list[str] = []
    for (decision, reason), group in groups.items():
        last = group[-1]
        tool = last.get("tool", "?")
        step = last.get("plan_step_id") or "none"
        targets = list(dict.fromkeys(str(e.get("target", "?")) for e in reversed(group)))
        shown = ", ".join(f"'{t}'" for t in targets[:MAX_TARGETS_PER_FLAG])
        if len(targets) > MAX_TARGETS_PER_FLAG:
            shown += f" +{len(targets) - MAX_TARGETS_PER_FLAG} more"
        times = f" (x{len(group)})" if len(group) > 1 else ""
        lines.append(f"- [{decision}] {tool} on {shown} (plan_step={step}){times}: {reason}")
    return "\n".join(lines)


def _assemble(blocks: list[tuple[str, str]]) -> str:
    """The additionalContext text exactly as `_emit` writes it."""
    return "\n\n".join(f"{header}\n\n{content}" for header, content in blocks if content)


def _emit(blocks: list[tuple[str, str]]) -> bool:
    """True once the output is written (or there was none to write)."""
    body = _assemble(blocks)
    if not body:
        return True
    payload = {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": body,
        }
    }
    try:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        return False
    return True


def main() -> int:
    cwd: Path | None = None  # the project root, once resolved
    try:
        event = _read_event()
        shell_cwd = _resolve_cwd(event)
        if shell_cwd is None:
            return 0
        # State lives at the project root; the shell may have cd'd below it.
        cwd = _phase_policy.project_root(shell_cwd)

        # The route, in its own try: a failure drops only this block. It runs
        # before the policy check: a missing or unknown marker turns the rest off.
        route: list[tuple[str, str]] = []
        try:
            import _project_state  # noqa: E402
            prompt = event.get("prompt") if isinstance(event.get("prompt"), str) else ""
            text = _project_state.hook_route(_project_state.find_root(shell_cwd), prompt)
            if text:
                route = [(ROUTE_HEADER, text.removeprefix(ROUTE_HEADER).strip())]
        except Exception:
            route = []

        if not _phase_policy.is_active(HOOK_NAME, cwd):
            _emit(route)
            return 0

        plan_content, plan_source = _read_first_anchor(cwd)
        # Read and formatted here, resolved only after the emit below: an
        # exception or a failed write in between leaves them for next prompt.
        audit_path = cwd / AUDIT_LOG_RELATIVE_PATH
        pending_path = cwd / AUDIT_PENDING_RELATIVE_PATH
        audit_entries = _unresolved(audit_path)
        pending_entries = _unresolved(pending_path)
        audit_content = _format_findings(audit_entries)
        pending_content = _format_pending_flags(pending_entries)
        prompt_text = event.get("prompt") if isinstance(event.get("prompt"), str) else ""
        forced_on = (cwd / FORCED_RULE_SET_RELATIVE_PATH).is_file()
        plan_prompt = _plan_prompt()
        skill_content = plan_prompt.skill_discipline_reminder(prompt_text) \
            if forced_on and plan_prompt else ""

        # Plan review advisory, in its own try: a failure drops only this block.
        review_content = ""
        try:
            import plan_review  # noqa: E402
            if _phase_policy.read_current_phase(cwd) != "incident":
                review_content = plan_review.advisory(cwd)
        except Exception:
            review_content = ""

        # Everything must fit INLINE_BUDGET_CHARS, or the model sees a preview.
        rest: list[tuple[str, str]] = []
        if review_content:
            rest.append((PLAN_REVIEW_HEADER, review_content))
        if audit_content:
            rest.append((AUDIT_HEADER, _fit(audit_content, FINDINGS_MAX_CHARS,
                                            str(AUDIT_LOG_RELATIVE_PATH))))
        if pending_content:
            rest.append((PENDING_HEADER, _fit(pending_content, PENDING_MAX_CHARS,
                                              str(AUDIT_PENDING_RELATIVE_PATH))))
        if skill_content:
            rest.append((plan_prompt.SKILL_DISCIPLINE_HEADER, skill_content))

        blocks: list[tuple[str, str]] = list(route)
        if plan_content and plan_prompt:
            header = plan_prompt.PLAN_HEADER
            plan_room = INLINE_BUDGET_CHARS - len(_assemble(route + rest)) - len(header) - 4
            blocks.append((header, plan_prompt.plan_block(plan_content, plan_source, plan_room,
                                                          _fit)))
        blocks.extend(rest)

        if _emit(blocks):
            _mark_resolved(audit_path, audit_entries)
            _mark_resolved(pending_path, pending_entries)
        return 0
    except Exception as exc:
        try:  # fail open, but not silently
            import _hook_log  # noqa: E402
            _hook_log.record_failure(HOOK_NAME, cwd, exc)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())

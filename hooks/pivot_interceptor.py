#!/usr/bin/env python3
"""PreToolUse hook: pivot interceptor (sentinel runtime layer).

Catches the moment a model is about to edit code IT AUTHORED earlier in the
session, immediately after a failing pytest run.

Rule:
    IF tool is Edit/Write/NotebookEdit/MultiEdit
    AND the most recent pytest run in this session FAILED
    AND the target file_path is in the set of files the model previously
        Edit/Write/MultiEdit'd in this session
    AND `.sentinel/runtime/root_cause.token` does NOT exist
    THEN deny: "fix your solution, not the code".

Never denied: the plan file, and after a planned RED the files of a pending or
in-progress [IMPL] row of `.sentinel/runtime/active_plan.md` once a [TEST] row
before it in its phase is completed and none before it is still open
(`_plan_text.planned_red_paths`). Neither spends the token.

Bypass: create `.sentinel/runtime/root_cause.token` (single-use, consumed on
first allow).

Phase-gated: only runs in phases listed in `_phase_policy.PHASE_POLICY`.
Failure mode: any error inside main() → allow, exit 0; the failure is logged to `.sentinel/runtime/hook_errors.jsonl` and flagged on the next prompt (`_hook_log`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import _phase_policy  # noqa: E402
import transcript_scope  # noqa: E402

HOOK_NAME = "pivot_interceptor"
TOKEN_FILE = Path(".sentinel") / "runtime" / "root_cause.token"
PLAN_FILE = Path(".sentinel") / "runtime" / "active_plan.md"

HOOK_EVENT_NAME = "PreToolUse"
EDIT_GATED_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})

_PYTEST_CMD_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:python(?:\d+(?:\.\d+)?)?\s+-m\s+pytest|pytest)(?:\s|$)",
    re.IGNORECASE,
)
_FAIL_RE = re.compile(
    r"\bFAILED\b|^E\s|Traceback \(most recent call last\)|^ERROR\b|\b\d+\s+failed\b|\berror\b.*collecting",
    re.MULTILINE,
)
_PASS_RE = re.compile(r"\b\d+\s+passed(?:,\s*\d+\s+warning)?\b")

# pytest's own final line: "777 passed, 1 skipped in 17.06s", or
# "==== 1 failed, 3 passed in 0.12s ====". When present it decides the
# outcome; `_FAIL_RE` alone read FAILED anywhere in the output, so a green run
# printed beside text containing "gate FAILED" counted as failing.
_SUMMARY_RE = re.compile(
    r"^[=\s]*((?:\d+ (?:failed|passed|skipped|deselected|xfailed|xpassed|"
    r"warnings?|errors?|rerun)(?:, )?)+) in \d+(?:\.\d+)?s\b",
    re.MULTILINE,
)
# "2 xfailed" is not a failure: the literal space before "failed" leaves no
# room for the "x".
_SUMMARY_FAIL_RE = re.compile(r"\b\d+ (?:failed|errors?)\b")


def pytest_outcome_from_text(text: str) -> str:
    """'pass' or 'fail' for one pytest tool result.

    - INTERNALERROR anywhere: 'fail' (pytest may crash without a summary
      while another run in the same command printed a clean one).
    - Summary lines present: 'fail' if ANY reports failures or errors, so a
      summary echoed after a failing run does not hide it; else 'pass'.
    - No summary line: the old rule (failure marker → 'fail', pass count →
      'pass', neither → 'fail').

    Known limit: output whose real summary was filtered away
    (`pytest | tail -0; echo "1 passed in 0.1s"`) reads as a pass, as before.
    """
    if "INTERNALERROR" in text:
        return "fail"
    summaries = [m.group(1) for m in _SUMMARY_RE.finditer(text)]
    if summaries:
        if any(_SUMMARY_FAIL_RE.search(s) for s in summaries):
            return "fail"
        return "pass"
    if _FAIL_RE.search(text):
        return "fail"
    if _PASS_RE.search(text):
        return "pass"
    return "fail"


def _iter_records(transcript_path: Path) -> Iterator[dict]:
    if not transcript_path or not transcript_path.is_file():
        return
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, UnicodeDecodeError):
        return


def _iter_content_blocks(record: dict) -> Iterator[dict]:
    if not isinstance(record, dict):
        return
    message = record.get("message") if isinstance(record.get("message"), dict) else record
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                yield block


def _tool_result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                t = c.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return ""


def last_pytest_outcome(transcript_path: Path) -> str | None:
    pytest_uses: list[tuple[str, str]] = []
    results_by_id: dict[str, str] = {}

    for record in _iter_records(Path(transcript_path)):
        for block in _iter_content_blocks(record):
            btype = block.get("type")
            if btype == "tool_use" and block.get("name") in ("Bash", "PowerShell"):
                cmd_input = block.get("input") or {}
                if isinstance(cmd_input, dict):
                    cmd = cmd_input.get("command", "")
                    if isinstance(cmd, str) and _PYTEST_CMD_RE.search(cmd):
                        use_id = block.get("id")
                        if isinstance(use_id, str):
                            pytest_uses.append((use_id, cmd))
            elif btype == "tool_result":
                use_id = block.get("tool_use_id")
                if isinstance(use_id, str):
                    results_by_id[use_id] = _tool_result_text(block)

    if not pytest_uses:
        return None

    for use_id, _ in reversed(pytest_uses):
        if use_id not in results_by_id:
            continue
        return pytest_outcome_from_text(results_by_id[use_id])
    return None


def authored_files_in_transcript(transcript_path: Path, cwd: Path) -> set[str]:
    authored: set[str] = set()
    for record in _iter_records(Path(transcript_path)):
        for block in _iter_content_blocks(record):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in EDIT_GATED_TOOLS:
                continue
            tool_input = block.get("input") or {}
            if not isinstance(tool_input, dict):
                continue
            fp = tool_input.get("file_path")
            if isinstance(fp, str) and fp:
                authored.add(_normalize_path(fp, cwd))
    return authored


def _normalize_path(p: str, cwd: Path) -> str:
    try:
        path = Path(p)
        if not path.is_absolute():
            path = cwd / path
        return path.resolve().as_posix().lower()
    except (OSError, ValueError):
        return p.replace("\\", "/").lower()


def decide(
    tool_name: str,
    target_file_normalized: str,
    pytest_outcome: str | None,
    authored_files: Iterable[str],
    token_present: bool,
    plan_file_normalized: str = "",
    planned_red_files: Iterable[str] = (),
) -> tuple[str, str, bool]:
    if tool_name not in EDIT_GATED_TOOLS:
        return "allow", "", False
    # The plan is a plan, not code: status updates and amendments after a
    # failing (RED) test are the normal flow of /work-plan.
    if plan_file_normalized and target_file_normalized == plan_file_normalized:
        return "allow", "", False
    # A planned RED: the plan's tests are written and this file belongs to the
    # implementation row that makes them pass. The token is kept.
    if target_file_normalized and target_file_normalized in set(planned_red_files):
        return "allow", "", False
    if token_present:
        return "allow", "", True
    if pytest_outcome != "fail":
        return "allow", "", False
    if not target_file_normalized:
        return "allow", "", False
    if target_file_normalized not in set(authored_files):
        return "allow", "", False
    reason = (
        "Pivot interceptor: the last pytest run in this session FAILED, "
        f"and you are about to {tool_name} a file you authored earlier "
        "in this session. Fix your solution, not the code. Reconsider "
        "whether the diff addresses the cause or only the symptom. "
        "If you have verified this is a genuine root-cause fix (not "
        "a patch around your solution), create "
        "'.sentinel/runtime/root_cause.token' to bypass for one call. "
        "A file named by a pending or in-progress [IMPL] row of the active "
        "plan passes without the token once a [TEST] row before it in its "
        "phase is completed and none before it is pending, in progress or "
        "blocked."
    )
    return "deny", reason, False


def _planned_red_files(root: Path, cwd: Path) -> set[str]:
    """Normalized paths the active plan exempts after a planned RED. Files
    cells are relative to the project root. Own try: a broken `_plan_text` or
    an unreadable plan costs only the exemption, and the guard denies as
    before."""
    try:
        import _plan_text  # noqa: E402
        text = (root / PLAN_FILE).read_text(encoding="utf-8")
        return {_normalize_path(str(root / path), cwd)
                for path in _plan_text.planned_red_paths(text)}
    except Exception:
        return set()


def _read_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
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


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    try:
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        return


def main() -> int:
    root: Path | None = None  # the project root, once resolved
    try:
        event = _read_event()
        cwd = _resolve_cwd(event)
        if cwd is None:
            return 0
        # State lives at the project root; relative file paths stay the shell's.
        root = _phase_policy.project_root(cwd)

        if not _phase_policy.is_active(HOOK_NAME, root):
            return 0

        tool_name = event.get("tool_name")
        if not isinstance(tool_name, str) or tool_name not in EDIT_GATED_TOOLS:
            return 0

        tool_input = event.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            return 0

        target_fp = tool_input.get("file_path")
        target_norm = ""
        if isinstance(target_fp, str) and target_fp:
            target_norm = _normalize_path(target_fp, cwd)

        token_path = root / TOKEN_FILE
        token_present = token_path.is_file()

        # The acting agent's pytest runs and edits (hooks/transcript_scope.py).
        # An unresolved subagent transcript falls back to the session's: no
        # transcript here means "no pytest, allow", so the fallback is the
        # side that can still deny.
        tp, scope = transcript_scope.acting_transcript(event)
        if scope == transcript_scope.UNRESOLVED:
            tp = transcript_scope.session_transcript(event)
        pytest_outcome: str | None = None
        authored: set[str] = set()
        if tp is not None:
            pytest_outcome = last_pytest_outcome(tp)
            authored = authored_files_in_transcript(tp, cwd)

        # The plan is read only when a deny is possible.
        planned_red: set[str] = set()
        if pytest_outcome == "fail":
            planned_red = _planned_red_files(root, cwd)

        decision, reason, consume = decide(
            tool_name=tool_name,
            target_file_normalized=target_norm,
            pytest_outcome=pytest_outcome,
            authored_files=authored,
            token_present=token_present,
            plan_file_normalized=_normalize_path(str(root / PLAN_FILE), cwd),
            planned_red_files=planned_red,
        )

        if consume:
            try:
                token_path.unlink()
            except OSError:
                pass

        if decision == "deny":
            _emit_deny(reason)
        return 0
    except Exception as exc:
        try:  # fail open, but not silently
            import _hook_log  # noqa: E402
            _hook_log.record_failure(HOOK_NAME, root, exc)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())

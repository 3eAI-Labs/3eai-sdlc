#!/usr/bin/env python3
"""Stop hook: automatic post-response audit (sentinel runtime layer).

Self-audit is unreliable — the model that drifted cannot reliably notice its
own drift. This hook performs an external pattern-based check on every
assistant turn end, surfaces findings on stderr, and persists them so the next
UserPromptSubmit can re-inject unresolved items into the model's context.

Flow:
  1. Read Stop event JSON from stdin.
  2. Resolve transcript path; read the turn since the last human prompt
     (`_extract_turn`): the final message's text, the tool, search and work
     counts, and every path the session has seen.
  3. Read `.sentinel/runtime/active_plan.md`: its `**Constraints:**` block and
     its phase count (fence-stripped when `_plan_text` imports).
  4. Run `audit_heuristics.run_all_checks` on the response.
  5. Write findings to `.sentinel/runtime/audit_log.json`.
  6. Emit short human-readable summary on stderr.

Phase-gated: only runs in phases listed in `_phase_policy.PHASE_POLICY`.
Failure mode: any error inside main() → exit 0; the failure is logged to `.sentinel/runtime/hook_errors.jsonl` and flagged on the next prompt (`_hook_log`).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import audit_heuristics  # noqa: E402
import _phase_policy  # noqa: E402

HOOK_NAME = "auto_audit"

_RUNTIME = Path(".sentinel") / "runtime"
AUDIT_LOG_RELATIVE_PATH = _RUNTIME / "audit_log.json"
ACTIVE_PLAN_RELATIVE_PATH = _RUNTIME / "active_plan.md"
MAX_LOGGED_TURNS = 20

# The gate's edit tools (forced_rule_set_gate.EDIT_LIKE_TOOLS) and both names of the subagent tool.
WORK_TOOLS = frozenset({"Edit", "MultiEdit", "Write", "NotebookEdit", "Agent", "Task"})
_FILE_TOOLS = frozenset({"Read", "Edit", "MultiEdit", "Write", "NotebookEdit"})
_OUTPUT_TOOLS = frozenset({"Grep", "Glob", "Bash"})
_TOOL_BLOCKS = frozenset({"tool_use", "tool_call"})
# A command position: the start, a new line, or after | ; & ( .
_CMD = r"(?:^|[|;&(\n])\s*"
_SEARCH_BASH = re.compile(
    _CMD + r"(?:grep|rg|find|ls|stat|test|which|command\s+-v|git(?:\s+-C\s+\S+)?\s+(?:grep|ls-files))\b")
_WORK_BASH = re.compile(
    _CMD + r"(?:git(?:\s+-C\s+\S+)?\s+(?:commit|merge|push|rebase|cherry-pick|revert|tag|mv|rm)"
    r"|sed\s+-i|mv|rm|cp|mkdir|touch|chmod|tee)\b")
# Output redirected into a file; `2>&1`, `>&2` and `2>/dev/null` are not writes.
_REDIRECT = re.compile(r"(?<![0-9&])>>?\s*(?!/dev/null|&)\S")
_HEREDOC_BODY = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.DOTALL)
_SHELL_QUOTED = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")
_NOT_A_PROMPT = ("<task-notification>", "<bash-", "<command-", "<local-command-", "[Request interrupted")


@dataclass
class Turn:
    """What the Stop hook audits: the work since the last human prompt."""
    text: str = ""              # the final assistant message
    tool_calls: int = 0         # tool blocks since the last human prompt, denied ones included
    read_calls: int = 0
    work_calls: int = 0         # edits, subagents and state-changing Bash in the agent's own turn
    search_calls: int = 0       # Grep, Glob, search and probe commands, a Read that found nothing
    seen_paths: list[str] = field(default_factory=list)  # strings showing a file reached the session


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


def _read_text(path: Path) -> str:
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_transcript_records(transcript_path: Path):
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError:
        return


def _role(rec: dict) -> Any:
    return rec.get("role") or rec.get("type")


def _message(rec: dict) -> dict:
    msg = rec.get("message")
    return msg if isinstance(msg, dict) else rec


def _blocks(rec: dict) -> list[dict]:
    content = _message(rec).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return ""


def _is_human_prompt(rec: dict) -> bool:
    if rec.get("type") == "attachment":
        att = rec.get("attachment")
        origin = att.get("origin") if isinstance(att, dict) else None
        return (isinstance(att, dict) and att.get("type") == "queued_command"
                and isinstance(origin, dict) and origin.get("kind") == "human")
    if _role(rec) != "user":
        return False
    texts = [b.get("text") or "" for b in _blocks(rec) if b.get("type") == "text"]
    if not texts:
        return False  # tool results only
    origin = rec.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    if rec.get("isMeta") or rec.get("isCompactSummary"):
        return False
    return not texts[0].lstrip().startswith(_NOT_A_PROMPT)


# A script that writes: the write sits in the script body, not on the shell line.
_SCRIPT_WRITE = re.compile(
    r"write_text\(|write_bytes\(|(?<!stdout)(?<!stderr)\.write\(|open\([^)\n]*,\s*['\"][wax]b?\+?['\"]"
    r"|json\.dump\(|os\.(?:remove|rename|replace|unlink|makedirs|mkdir)\(|shutil\.")
# A tool the lists above do not know, run with a state-changing word among its
# first three arguments. Commands that only read or print never count here.
_QUIET_COMMANDS = (r"(?:grep|rg|ag|sed|awk|cat|echo|printf|ls|find|head|tail|wc|cut|sort|uniq|tr|test|stat"
                   r"|which|cd|python3?|jq|base64|diff|git|for|do|if|then|while|export)")
_MUTATING_SUBCOMMAND = re.compile(
    _CMD + r"(?!" + _QUIET_COMMANDS + r"\b)[\w./-]+(?:\s+[\w.-]+){0,2}?\s+"
    r"(?:install|uninstall|update|upgrade|create|delete|apply|deploy|publish|restart|bind-key|set-option"
    r"|remove|add)\b")


def _is_work_bash(command: str) -> bool:
    """A Bash command that changes state: a known mutating command, output
    redirected into a file, a script that writes, or an unknown tool run with a
    state-changing subcommand. A change through a command these patterns do not
    know is not seen."""
    if _WORK_BASH.search(command) or _SCRIPT_WRITE.search(command):
        return True
    shell = _SHELL_QUOTED.sub("", _HEREDOC_BODY.sub("", command))
    return bool(_REDIRECT.search(shell) or _MUTATING_SUBCOMMAND.search(shell))


def _tool_blocks(rec: dict) -> list[dict]:
    return [b for b in _blocks(rec) if b.get("type") in _TOOL_BLOCKS]


def _extract_turn(transcript_path: Path) -> Turn:
    records = list(_iter_transcript_records(transcript_path))
    turn = Turn()
    if not records:
        return turn

    # Tool results, by the id of the call they answer.
    failed: set[str] = set()
    results: dict[str, str] = {}
    for rec in records:
        if _role(rec) not in {"user", "tool", "tool_result"}:
            continue
        for b in _blocks(rec):
            if b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str):
                results[b["tool_use_id"]] = _result_text(b)
                if b.get("is_error"):
                    failed.add(b["tool_use_id"])

    # Seen paths come from the whole file.
    for rec in records:
        if rec.get("type") == "attachment":
            att = rec.get("attachment")
            if isinstance(att, dict) and att.get("type") == "file":
                try:
                    turn.seen_paths.append(str(att["content"]["file"]["filePath"]))
                except (KeyError, TypeError):
                    pass
            continue
        if _role(rec) != "assistant":
            continue
        for b in _tool_blocks(rec):
            name, tid = b.get("name"), b.get("id")
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            if name in _FILE_TOOLS:
                fp = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(fp, str) and tid not in failed:
                    turn.seen_paths.append(fp)
            elif name in _OUTPUT_TOOLS:
                for key in ("path", "command"):
                    if isinstance(inp.get(key), str):
                        turn.seen_paths.append(inp[key])
                if isinstance(tid, str) and results.get(tid):
                    turn.seen_paths.append(results[tid])

    start = 0
    for i, rec in enumerate(records):
        if _is_human_prompt(rec):
            start = i + 1
    window = [(i, rec) for i, rec in enumerate(records[start:], start) if _role(rec) == "assistant"]
    if not window:
        return turn

    # The final message: the last assistant record and the records sharing its id.
    last_i, last = window[-1]
    last_id = _message(last).get("id")
    final = {i for i, rec in window if last_id is not None and _message(rec).get("id") == last_id} | {last_i}
    turn.text = "\n".join(b.get("text") or "" for i, rec in window if i in final
                          for b in _blocks(rec) if b.get("type") == "text" and b.get("text"))

    # The agent's own turn starts after the previous turn-ending message.
    own_start = start
    for i, rec in window:
        if i not in final and _message(rec).get("stop_reason") == "end_turn":
            own_start = i + 1

    for i, rec in window:
        for b in _tool_blocks(rec):
            name, tid = b.get("name"), b.get("id")
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            command = inp.get("command") if isinstance(inp.get("command"), str) else ""
            turn.tool_calls += 1
            if name == "Read":
                turn.read_calls += 1
                if tid in failed:
                    turn.search_calls += 1  # the file was probed and is not there
            elif name in {"Grep", "Glob"} or (name == "Bash" and _SEARCH_BASH.search(command)):
                turn.search_calls += 1
            if i >= own_start and (name in WORK_TOOLS or (name == "Bash" and _is_work_bash(command))):
                turn.work_calls += 1
    return turn


def _extract_last_assistant_turn(transcript_path: Path) -> tuple[str, int, int]:
    """(text, tool calls, Read calls) of the turn; kept for callers of the old shape."""
    turn = _extract_turn(transcript_path)
    return turn.text, turn.tool_calls, turn.read_calls


def _load_existing_log(log_path: Path) -> list[dict]:
    text = _read_text(log_path)
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def _write_log(log_path: Path, entries: list[dict]) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def _emit_user_summary(findings: list[audit_heuristics.Finding]) -> None:
    if not findings:
        return
    lines = ["", "[Sentinel Audit] Possible violations detected in last turn:"]
    for f in findings:
        lines.append(f"  - {f.rule}: {f.message}")
    lines.append("  (Logged to .sentinel/runtime/audit_log.json — fed back to model next turn.)")
    text = "\n".join(lines) + "\n"
    try:
        os.write(2, text.encode("utf-8", errors="replace"))
    except OSError:
        return


def main() -> int:
    cwd: Path | None = None  # the project root, once resolved
    try:
        event = _read_event()
        shell_cwd = _resolve_cwd(event)
        if shell_cwd is None:
            return 0
        # State lives at the project root; the shell may have cd'd below it.
        cwd = _phase_policy.project_root(shell_cwd)

        if not _phase_policy.is_active(HOOK_NAME, cwd):
            return 0

        transcript_path_str = event.get("transcript_path")
        turn = Turn()
        if isinstance(transcript_path_str, str) and transcript_path_str:
            transcript_path = Path(transcript_path_str)
            if transcript_path.is_file():
                turn = _extract_turn(transcript_path)

        if not turn.text:
            return 0

        plan_text = _read_text(cwd / ACTIVE_PLAN_RELATIVE_PATH)
        # Own try: a broken helper costs only the fence stripping.
        try:
            import _plan_text  # noqa: E402
            counted = _plan_text.strip_fences(plan_text)
        except Exception:
            counted = plan_text
        plan_audit = audit_heuristics._plan_audit()
        current_phase_count = plan_audit.count_plan_phases(counted) if plan_audit else 0

        log_path = cwd / AUDIT_LOG_RELATIVE_PATH
        entries = _load_existing_log(log_path)
        prior_phase_count = 0
        if entries:
            try:
                prior_phase_count = int(entries[-1].get("plan_phase_count", 0) or 0)
            except (TypeError, ValueError):
                prior_phase_count = 0

        findings = audit_heuristics.run_all_checks(
            response_text=turn.text,
            plan_text=plan_text,
            tool_call_count=turn.tool_calls,
            current_phase_count=current_phase_count,
            prior_phase_count=prior_phase_count,
            work_calls=turn.work_calls,
            search_calls=turn.search_calls,
            seen_paths=turn.seen_paths,
        )

        entries.append({
            "session_id": event.get("session_id", ""),
            "findings": audit_heuristics.findings_to_dicts(findings),
            "resolved": False,
            "plan_phase_count": current_phase_count,
        })
        entries = entries[-MAX_LOGGED_TURNS:]
        _write_log(log_path, entries)

        _emit_user_summary(findings)
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

#!/usr/bin/env python3
"""PreToolUse hook: forced rule set gate (3eai-sdlc runtime layer).

Philosophy (audit-not-block)
----------------------------
The gate is OBSERVATIONAL. Tool calls are allowed by default; the only
hard-deny path is matching a destructive pattern, resolved across layers
(plugin `.claude-plugin/runtime/destructive_patterns.json` → `~/.sentinel/` →
`.sentinel-control/`; see rule_layers.py). An advisory verdict (assumption
sentinel, plan check) is logged and leaves a "pending audit flag" for the next
user prompt, but is NEVER used to deny a tool call.

Order of operations when forced_rule_set is ON:
  1. approve.token present and non-empty → consume + allow.
  2. Write to active_plan.md (plan bootstrap) → allow.
  3. Tool/params match a deny rule of destructive_patterns.json → DENY.
  4. Skill enforcement (`_plan_gate`): active plan present + no Skill tool
     call in transcript → DENY with 3eai-sdlc-specific reason.
  4b. The command matches an ask rule (`decision: "ask"`: an outward command
     such as `git push`, `scp`, a publish, a mail) → ASK the user, in every
     phase. Deny rules are tried before ask rules.
  5. Assumption sentinel (advisory): edit-like tool targeting an existing file
     that was never successfully Read this session (never_read), or that
     changed on disk after the last successful read/edit (stale_read) →
     log verdict + audit flag. NEVER denies.
  6. Plan check (advisory, `_plan_gate`): edit-like tool targeting a project file that no
     pending or in-progress step of the active plan names (DIVERGE), or an
     [IMPL] step's file while a [TEST] step before it in its phase is still
     open (TDD_VIOLATION) → log verdict + audit flag. NEVER denies. No config
     file and no child process: it runs wherever step 5 runs.
  7. Allow.

Gated tools: Edit, Write, NotebookEdit, MultiEdit, Bash, PowerShell and the
subagent tool (`Agent`; `Task` in older harness versions). A 3eai-sdlc skill the
user typed as a slash command counts as a Skill call for step 4.

Steps 4 and 6 live in `_plan_gate.py`, a Pro-only module imported at the
point of use; without it the gate skips them.

Phase-gated: only runs in phases listed in `_phase_policy.PHASE_POLICY`.
Outside them, with forced_rule_set on, a destructive match asks the user.
Failure mode: any error inside main() → allow, exit 0; the failure is logged to `.sentinel/runtime/hook_errors.jsonl` and flagged on the next prompt (`_hook_log`).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import _phase_policy  # noqa: E402
import gate_control  # noqa: E402
import rule_layers  # noqa: E402
import shell_position  # noqa: E402
import transcript_scope  # noqa: E402

HOOK_NAME = "forced_rule_set_gate"

_RUNTIME = Path(".sentinel") / "runtime"
FORCED_RULE_SET_FILE = rule_layers.CONTROL_DIR / "forced_rule_set"
APPROVE_TOKEN_FILE = rule_layers.CONTROL_DIR / "approve.token"
ACTIVE_PLAN_FILE = _RUNTIME / "active_plan.md"
DESTRUCTIVE_PATTERNS_FILE = rule_layers.CONTROL_DIR / "destructive_patterns.json"
AUDIT_FINDINGS_PENDING_FILE = _RUNTIME / "audit_findings_pending.json"
WARDEN_DECISIONS_LOG_FILE = _RUNTIME / "warden_decisions.jsonl"

HOOK_EVENT_NAME = "PreToolUse"

# The subagent tool: `Agent` today, `Task` in older harness versions. One name
# for the gate and for a rule's `tool` filter.
_SUBAGENT_TOOLS = frozenset({"Task", "Agent"})
DEFAULT_GATED_TOOLS = frozenset({
    "Edit", "Write", "NotebookEdit", "MultiEdit",
    "Bash", "PowerShell",
}) | _SUBAGENT_TOOLS
EDIT_LIKE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})

# Tools whose successful results give the model knowledge of a file's content.
KNOWLEDGE_TOOLS = frozenset({"Read", "Edit", "Write", "NotebookEdit", "MultiEdit"})
# mtime can lag the tool_result timestamp by disk/clock skew; absorb it.
ASSUMPTION_STALE_TOLERANCE_SEC = 5.0

MAX_PENDING_FLAGS = 50


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


def _normalize_path(p: str, cwd: Path) -> str:
    try:
        path = Path(p)
        if not path.is_absolute():
            path = cwd / path
        return path.resolve().as_posix().lower()
    except (OSError, ValueError):
        return p.replace("\\", "/").lower()


def read_forced_rule_set(path: Path) -> bool:
    return path.is_file()


def read_approve_token(path: Path) -> bool:
    """A non-empty file. On Linux the sandbox holds a write denial on a missing
    file with a 0-byte read-only placeholder while a command runs
    (code.claude.com/docs/en/sandboxing); that is no approval."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _plan_gate():
    """The Pro-only plan module, or None when it is absent (the free edition)
    or broken: then the gate runs no skill enforcement and no plan check."""
    try:
        import _plan_gate as module  # noqa: E402
        return module
    except Exception:  # noqa: BLE001
        return None


def read_files_from_transcript(transcript_path: Path, cwd: Path) -> set[str]:
    """Return the set of normalized file paths that have been Read in this
    session. Preserved for downstream callers that want to observe (not
    enforce) Read-before-Edit history.
    """
    if not transcript_path.is_file():
        return set()
    read_paths: set[str] = set()
    try:
        with transcript_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") != "Read":
                        continue
                    tool_input = block.get("input", {})
                    if not isinstance(tool_input, dict):
                        continue
                    fp = tool_input.get("file_path")
                    if isinstance(fp, str) and fp:
                        read_paths.add(_normalize_path(fp, cwd))
    except (OSError, UnicodeDecodeError):
        return set()
    return read_paths


# --- assumption sentinel ---


def _parse_iso_ts(raw: Any) -> float | None:
    """Parse a transcript ISO-8601 timestamp ('...Z') to epoch seconds."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def knowledge_times_from_transcript(transcript_path: Path, cwd: Path) -> dict[str, float]:
    """Map normalized file path -> epoch of the model's last SUCCESSFUL
    Read/Edit/Write/NotebookEdit/MultiEdit of it.

    Knowledge time is taken from the tool_result entry's timestamp
    (post-execution), NOT the tool_use entry — a permission prompt can delay
    execution by minutes and would otherwise make fresh knowledge look stale.
    Error tool_results (denied / failed calls) grant no knowledge.
    """
    if not transcript_path or not transcript_path.is_file():
        return {}
    pending: dict[str, str] = {}  # tool_use_id -> normalized path
    knowledge: dict[str, float] = {}
    try:
        with transcript_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                ts = _parse_iso_ts(entry.get("timestamp"))
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use" and block.get("name") in KNOWLEDGE_TOOLS:
                        tool_input = block.get("input", {})
                        if not isinstance(tool_input, dict):
                            continue
                        fp = tool_input.get("file_path") or tool_input.get("notebook_path")
                        bid = block.get("id")
                        if isinstance(fp, str) and fp and isinstance(bid, str) and bid:
                            pending[bid] = _normalize_path(fp, cwd)
                    elif btype == "tool_result" and ts is not None:
                        if block.get("is_error"):
                            continue
                        uid = block.get("tool_use_id")
                        path = pending.get(uid) if isinstance(uid, str) else None
                        if path:
                            knowledge[path] = max(knowledge.get(path, 0.0), ts)
    except (OSError, UnicodeDecodeError):
        return {}
    return knowledge


def assumption_check(
    tool_name: str,
    tool_input: dict[str, Any],
    knowledge_times: dict[str, float],
    cwd: Path,
) -> dict[str, Any] | None:
    """Detect assumption-based edits. Returns a DIVERGE verdict dict or None.

    This is the evidence-groundedness counterpart to `plan_check`: not
    "which file is being touched" but "is the model acting on verified
    knowledge or on an assumption".

    - never_read: target exists but was never successfully Read this session.
    - stale_read: target changed on disk after the model's last successful
      read/edit of it.

    New files (nothing to read yet) and `.sentinel/` runtime files are
    exempt. Fail-open on any filesystem error.
    """
    if tool_name not in EDIT_LIKE_TOOLS or not isinstance(tool_input, dict):
        return None
    fp = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(fp, str) or not fp:
        return None
    norm = _normalize_path(fp, cwd)
    if "/.sentinel/" in norm or norm.startswith(".sentinel/"):
        return None
    try:
        target = Path(fp)
        if not target.is_absolute():
            target = cwd / fp
        if not target.is_file():
            return None  # creating a new file is not an assumption about existing code
        mtime = target.stat().st_mtime
    except OSError:
        return None

    ts = knowledge_times.get(norm)
    if ts is None:
        return {
            "decision": "DIVERGE",
            "check": "never_read",
            "reason": (
                f"assumption-based edit: '{fp}' was never successfully Read in this "
                "session — on what basis? Read the file before editing it."
            ),
            "plan_step_id": None,
            "confidence": 0.9,
            "model_used": "assumption_sentinel",
            "cost_usd": 0.0,
        }
    if mtime > ts + ASSUMPTION_STALE_TOLERANCE_SEC:
        return {
            "decision": "DIVERGE",
            "check": "stale_read",
            "reason": (
                f"stale knowledge: '{fp}' changed on disk after your last successful "
                "read/edit of it — your mental model of this file may now be an "
                "assumption. Re-Read it before editing."
            ),
            "plan_step_id": None,
            "confidence": 0.85,
            "model_used": "assumption_sentinel",
            "cost_usd": 0.0,
        }
    return None


def load_destructive_patterns(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        patterns = data.get("patterns")
        if isinstance(patterns, list):
            return [p for p in patterns if isinstance(p, dict)]
    return []


def load_layered_destructive_patterns(cwd: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Patterns resolved plugin default → ~/.sentinel/ → project (rule_layers)."""
    return rule_layers.load_layered_rules(DESTRUCTIVE_PATTERNS_FILE.name, cwd=cwd)


def split_shell_commands(command: str, heredoc_bodies: bool = True) -> list[str]:
    """Split a shell line into simple commands, ignoring quoted separators.

    With `heredoc_bodies=False` heredoc body lines are dropped instead of
    becoming segments: ask rules use it, because writing a script that holds
    `git push` is not pushing.

    Without it a destructive verb in one command reached a path in another
    (`rm /tmp/x && cat important.txt`). A `#` at a word start outside quotes
    comments out the rest of its line only; the next line still runs, even
    when the comment ends in a backslash. Backslash-newline elsewhere outside
    single quotes joins lines. `$'...'` honours backslash escapes, `'...'`
    does not.

    Fail-safe: bash refuses a quote that never closes, so one still open at
    the end means this splitter misread the line (an apostrophe in data it
    did not recognise as data). The text after that quote is split again
    and checked as commands too: a misread costs a false deny, not a bypass.
    """
    if not isinstance(command, str) or not command:
        return []
    parts: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    quote_at = -1
    heredocs: list[tuple[str, bool, bool]] = []  # (delimiter, strip tabs, quoted)
    arith = 0  # open (( ... )) outside quotes: `<<` there is a shift
    i = 0
    while i < len(command):
        ch = command[i]
        if ch == "\n" and quote is None and heredocs:
            parts.append("".join(buf))
            buf = []
            i = _skip_heredoc_bodies(command, i + 1, heredocs, parts if heredoc_bodies else [])
            heredocs = []
            continue
        if ch == "\\" and quote != "'":
            if command[i + 1:i + 2] != "\n":
                buf.append(command[i:i + 2])
            i += 2
            continue
        if quote:
            buf.append(ch)
            if ch == quote[-1]:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = "$'" if ch == "'" and shell_position.opens_ansi_c_quote(command, i) else ch
            quote_at = i
            buf.append(ch)
            i += 1
            continue
        if command.startswith("((", i):
            arith += 1
        elif command.startswith("))", i) and arith:
            arith -= 1
        if command.startswith("<<", i) and not command.startswith("<<<", i) and not arith:
            found = _HEREDOC_OP.match(command, i)
            if found:
                word = found.group(2)
                delimiter = re.sub(r"[\\'\"]", "", word)
                heredocs.append((delimiter, found.group(1) == "-", delimiter != word))
                buf.append(found.group(0))
                i = found.end()
                continue
        if ch == "#" and (not buf or buf[-1].isspace()):
            newline = command.find("\n", i)
            if newline < 0:
                break
            i = newline
            continue
        if command[i:i + 2] in ("&&", "||"):
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in (";", "|", "&", "\n"):
            if ch == "\n":
                arith = 0
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    if quote is not None:
        parts.extend(split_shell_commands(command[quote_at + 1:], heredoc_bodies))
    return [p.strip() for p in parts if p.strip()]


_HEREDOC_OP = re.compile(r"<<(-?)\s*((?:'[^'\n]*'|\"[^\"\n]*\"|\\?[^\s;&|<>()'\"]+)+)")


def _skip_heredoc_bodies(
    command: str, i: int, heredocs: list[tuple[str, bool]], parts: list[str]
) -> int:
    """Consume heredoc bodies starting at `i`; each body line becomes a segment.

    A body is data, but an unquoted one still expands `$(...)` and one fed to
    a shell (`bash <<EOF`, `ssh host <<EOF`) is a script, so its lines stay
    matchable, with backslash-newline joined. What a body must not do is
    carry an apostrophe's open quote into the commands after it.
    """
    for delimiter, strip_tabs, quoted in heredocs:
        carry = ""
        while i < len(command):
            end = command.find("\n", i)
            end = len(command) if end < 0 else end
            line = command[i:end]
            i = end + 1
            # bash joins backslash-newline before the delimiter test only in an
            # unquoted body: `foo\<NL>EOF` there is the body line `fooEOF`.
            ending = line if quoted else carry + line
            if (ending.lstrip("\t") if strip_tabs else ending) == delimiter:
                if not quoted:
                    carry = ""
                break
            joined = carry + line
            trailing = len(joined) - len(joined.rstrip("\\"))
            if trailing % 2:
                carry = joined[:-1]
                continue
            parts.append(joined)
            carry = ""
        if carry:
            parts.append(carry)
    return min(i, len(command))



# Candidate kinds. A shell command yields its split segments AND the unsplit
# line; a pattern picks via `match_scope`. The default is "both": the gate
# before layering matched the whole line, and a project rule written for it
# (`curl ... | sh`) must keep matching. File paths and
# Task briefs are "other" and always considered.
CAND_SEGMENT = "segment"
CAND_LINE = "line"
CAND_OTHER = "other"


def _candidates_for_match(
    tool_name: str, tool_input: dict[str, Any], ask: bool = False
) -> list[tuple[str, str]]:
    """What a rule is matched against. For ask rules (`ask=True`) a shell
    command yields only its segments, without heredoc body lines."""
    candidates: list[tuple[str, str]] = []
    if tool_name in {"Bash", "PowerShell"}:
        cmd = tool_input.get("command")
        if isinstance(cmd, str):
            if ask:
                return [(seg, CAND_SEGMENT) for seg in split_shell_commands(cmd, heredoc_bodies=False)]
            candidates.extend((seg, CAND_SEGMENT) for seg in split_shell_commands(cmd))
            candidates.append((cmd, CAND_LINE))
    if tool_name in EDIT_LIKE_TOOLS:
        fp = tool_input.get("file_path")
        if isinstance(fp, str):
            candidates.append((fp, CAND_OTHER))
    if tool_name in _SUBAGENT_TOOLS:
        for k in ("description", "prompt"):
            v = tool_input.get(k)
            if isinstance(v, str):
                candidates.append((v, CAND_OTHER))
    return candidates


def candidate_allowed(kind: str, match_scope: str | None) -> bool:
    if kind == CAND_OTHER:
        return True
    scope = match_scope or "both"
    return scope == "both" or kind == scope


def match_destructive_pattern(
    tool_name: str,
    tool_input: dict[str, Any],
    patterns: list[dict[str, Any]],
    cwd: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any] | None:
    if not isinstance(tool_input, dict):
        return None
    # Deny rules first, then ask rules (`decision: "ask"`), each in list order:
    # a deny rule a later layer adds for an outward command is not shadowed by
    # an earlier ask rule. Ask rules see segments only, without heredoc bodies.
    for ask in (False, True):
        candidates = _candidates_for_match(tool_name, tool_input, ask=ask)
        if not candidates:
            continue
        for pat in patterns:
            if (pat.get("decision") == "ask") != ask:
                continue
            wanted_tool = pat.get("tool")
            if wanted_tool:
                allowed = wanted_tool if isinstance(wanted_tool, list) else [wanted_tool]
                if tool_name not in allowed and not (
                        tool_name in _SUBAGENT_TOOLS and _SUBAGENT_TOOLS & {str(a) for a in allowed}):
                    continue
            if "guard" in pat:
                if _guard_matches(pat["guard"], tool_name, tool_input, cwd or Path.cwd(), root):
                    return pat
                continue
            regex = pat.get("command_regex") or pat.get("file_regex") or pat.get("regex")
            if not isinstance(regex, str):
                continue
            try:
                compiled = re.compile(regex)
            except Exception:  # noqa: BLE001
                # Not only re.error: `a{4294967296}` raises OverflowError, deep
                # nesting RecursionError, and the gate fails open on exceptions.
                continue
            match_scope = "segment" if ask else pat.get("match_scope")
            anchor = pat.get("anchor")
            for text, kind in candidates:
                if not candidate_allowed(kind, match_scope):
                    continue
                found = compiled.search(text)
                if not found:
                    continue
                # anchor=command: a match inside an argument is a mention, not an act.
                if anchor == "command" and kind != CAND_OTHER and not _match_is_a_command(text, found):
                    continue
                return pat
    return None


def _guard_matches(
    guard: Any, tool_name: str, tool_input: dict[str, Any], cwd: Path, root: Path | None
) -> bool:
    """A rule checked by code, not a regex. Any failure counts the match.
    `cwd` is where the shell runs, `root` the project (see project_root)."""
    if guard != "control-files":
        return False
    try:
        if tool_name == "Bash":
            cmd = tool_input.get("command")
            return isinstance(cmd, str) and gate_control.shell_touches_control(
                cmd, cwd, split_shell_commands, root=root
            )
        fp = tool_input.get("file_path") or tool_input.get("notebook_path")
        return isinstance(fp, str) and bool(fp) and gate_control.path_is_control(fp, cwd, root=root)
    except Exception:  # noqa: BLE001
        return True


def _match_is_a_command(text: str, found: "re.Match[str]") -> bool:
    """Position check; any failure counts the match (deny is the safe side)."""
    try:
        return shell_position.match_is_a_command(text, found)
    except Exception:  # noqa: BLE001
        return True


def _short_target(tool_input: dict[str, Any]) -> str:
    if not isinstance(tool_input, dict):
        return ""
    for k in ("file_path", "notebook_path", "command"):
        v = tool_input.get(k)
        if isinstance(v, str) and v:
            return v[:200]
    return ""


def write_audit_flag(
    cwd: Path,
    tool_name: str,
    tool_input: dict[str, Any],
    warden_verdict: dict[str, Any],
) -> None:
    pending_path = cwd / AUDIT_FINDINGS_PENDING_FILE
    try:
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        entries: list[dict] = []
        if pending_path.is_file():
            try:
                raw = json.loads(pending_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    entries = [e for e in raw if isinstance(e, dict)]
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "target": _short_target(tool_input),
            "warden_decision": warden_verdict.get("decision"),
            "reason": warden_verdict.get("reason"),
            "plan_step_id": warden_verdict.get("plan_step_id"),
            "resolved": False,
        })
        entries = entries[-MAX_PENDING_FLAGS:]
        pending_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def append_warden_log(
    cwd: Path,
    tool_name: str,
    tool_input: dict[str, Any],
    warden_verdict: dict[str, Any],
    session_id: str = "",
) -> None:
    log_path = cwd / WARDEN_DECISIONS_LOG_FILE
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "tool": tool_name,
            "target": _short_target(tool_input),
            **warden_verdict,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return


# Addressed to the user: the agent reads deny reasons, and these files are
# denied to it (gate-control-files-* rules).
_USER_ONLY = (
    "Only the user can authorize this single call, by writing anything "
    "into '.sentinel-control/approve.token' outside the agent "
    "(e.g. `echo ok > .sentinel-control/approve.token` in a separate terminal), "
    "or exit forced mode by deleting '.sentinel-control/forced_rule_set'. "
    "The agent must not create, edit or delete either file."
)


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    forced_enabled: bool,
    gated_tools: frozenset[str],
    token_present: bool,
    cwd: Path,
    destructive_match: dict[str, Any] | None,
    skill_calls_seen: int = 0,
    active_plan_exists: bool = False,
    phase: str | None = None,
) -> tuple[str, str, bool]:
    """`phase` is None inside the gate's phases; otherwise the declared phase
    ('' if none). The phase file is the agent's to write, so outside the gate's
    phases a destructive match is a question for the user, not silence."""
    if not forced_enabled:
        return "allow", "", False
    if tool_name not in gated_tools:
        return "allow", "", False
    if token_present:
        return "allow", "", True

    if tool_name == "Write" and isinstance(tool_input, dict):
        target = tool_input.get("file_path")
        if isinstance(target, str) and target:
            target_norm = _normalize_path(target, cwd)
            plan_norm = _normalize_path(str(cwd / ACTIVE_PLAN_FILE), cwd)
            if target_norm == plan_norm:
                return "allow", "", False

    plan_gate = _plan_gate()
    skill_reason = plan_gate.skill_denial(tool_name, phase, active_plan_exists,
                                          skill_calls_seen) if plan_gate else None
    if destructive_match and destructive_match.get("decision") == "ask":
        # An outward command: not destructive, so the user decides, in every
        # phase. Skill enforcement keeps its place: it denies below.
        if not skill_reason:
            return "ask", (
                f"3eAI SDLC: '{tool_name}' matches outward rule {destructive_match.get('id', '<unnamed>')}. "
                f"Reason: {destructive_match.get('reason', 'leaves the machine')}. "
                "This leaves the machine, so you decide."
            ), False
    elif destructive_match:
        pat_str = (
            destructive_match.get("command_regex")
            or destructive_match.get("file_regex")
            or destructive_match.get("regex")
            or "<unspecified>"
        )
        what = (
            f"'{tool_name}' matches destructive pattern. "
            f"Reason: {destructive_match.get('reason', 'unsafe operation')}. "
            f"Pattern: {pat_str}. "
        )
        if phase is not None:
            return "ask", (
                f"3eAI SDLC: {what}Phase '{phase or 'none'}' is outside the gate's "
                "phases, so you decide."
            ), False
        reason = (
            f"3eAI SDLC forced rule set ON: {what}"
            "If this step is needed, stop and tell the user what you want to run "
            f"and why; they decide. {_USER_ONLY}"
        )
        return "deny", reason, False

    if skill_reason:
        return "deny", f"{skill_reason} {_USER_ONLY}", False

    return "allow", "", False


def _consume_token(token_path: Path) -> None:
    try:
        token_path.unlink()
    except OSError:
        return


def _emit(decision: str, reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": decision,
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
    cwd: Path | None = None  # the project root, once resolved
    tool_name: Any = ""
    try:
        event = _read_event()
        shell_cwd = _resolve_cwd(event)
        if shell_cwd is None:
            return 0
        # State lives at the project root; the shell may have cd'd below it.
        cwd = _phase_policy.project_root(shell_cwd)

        in_phase = _phase_policy.is_active(HOOK_NAME, cwd)

        tool_name = event.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            return 0
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        session_id = event.get("session_id")
        if not isinstance(session_id, str):
            session_id = ""

        forced_path = cwd / FORCED_RULE_SET_FILE
        token_path = cwd / APPROVE_TOKEN_FILE

        forced_enabled = read_forced_rule_set(forced_path)
        if not forced_enabled:
            return 0

        patterns, _pattern_report = load_layered_destructive_patterns(cwd)
        destructive_match = match_destructive_pattern(tool_name, tool_input, patterns, shell_cwd, cwd)

        plan_gate = _plan_gate()
        active_plan_exists = bool(plan_gate) and plan_gate.read_active_plan_exists(
            cwd / ACTIVE_PLAN_FILE)
        # Skill calls are counted in the SESSION transcript even for a
        # subagent call: the phase skill is invoked by the parent, and a
        # delegated coder works under it without invoking one itself.
        transcript_path_str = event.get("transcript_path")
        skill_calls_seen = 0
        if active_plan_exists and isinstance(transcript_path_str, str) and transcript_path_str:
            try:
                skill_calls_seen = plan_gate.read_skill_calls_from_transcript(
                    Path(transcript_path_str))
            except (OSError, ValueError):
                skill_calls_seen = 0

        decision, reason, consume = decide(
            tool_name=tool_name,
            tool_input=tool_input,
            forced_enabled=forced_enabled,
            gated_tools=DEFAULT_GATED_TOOLS,
            token_present=read_approve_token(token_path),
            cwd=cwd,
            destructive_match=destructive_match,
            skill_calls_seen=skill_calls_seen,
            active_plan_exists=active_plan_exists,
            phase=None if in_phase else _phase_policy.read_current_phase(cwd),
        )

        if consume:
            _consume_token(token_path)

        if decision in ("deny", "ask"):
            _emit(decision, reason)
            return 0
        if not in_phase:
            return 0

        if not consume and tool_name in DEFAULT_GATED_TOOLS:
            # Assumption sentinel: before plan-groundedness, check
            # evidence-groundedness — is this edit based on verified knowledge
            # (a successful Read/Edit of the target this session, still fresh)
            # or on an assumption? Advisory only: log + flag, never deny.
            if tool_name in EDIT_LIKE_TOOLS:
                knowledge: dict[str, float] = {}
                # The acting agent's reads, not the session's
                # (hooks/transcript_scope.py). An unresolved subagent
                # transcript yields no knowledge: never_read, advisory only.
                acting, _scope = transcript_scope.acting_transcript(event)
                if acting is not None:
                    try:
                        knowledge = knowledge_times_from_transcript(acting, cwd)
                    except (OSError, ValueError):
                        knowledge = {}
                assumption_verdict = assumption_check(tool_name, tool_input, knowledge, cwd)
                if assumption_verdict is not None:
                    append_warden_log(cwd, tool_name, tool_input, assumption_verdict, session_id)
                    write_audit_flag(cwd, tool_name, tool_input, assumption_verdict)

            # Plan-groundedness (Pro): does a pending or in-progress step of
            # the active plan name this file? Advisory only: log + flag.
            if plan_gate:
                plan_text = plan_gate.read_plan_text(cwd / ACTIVE_PLAN_FILE)
                for plan_verdict in plan_gate.plan_check(tool_name, tool_input, plan_text, cwd):
                    append_warden_log(cwd, tool_name, tool_input, plan_verdict, session_id)
                    write_audit_flag(cwd, tool_name, tool_input, plan_verdict)

        return 0
    except Exception as exc:
        try:  # fail open, but not silently
            import _hook_log  # noqa: E402
            _hook_log.record_failure(HOOK_NAME, cwd, exc, tool_name if isinstance(tool_name, str) else "")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())

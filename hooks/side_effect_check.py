#!/usr/bin/env python3
"""Side-effect check (3eai-sdlc runtime layer): after a shell call, tell the
agent which files changed that the command does not name.

Events (one script, told apart by `hook_event_name` and `tool_name`):
    PreToolUse of Bash/PowerShell      snapshot the changed and untracked files
    PostToolUse / PostToolUseFailure   compare, and report what the command
      of Bash/PowerShell               does not name, as `additionalContext`
    PostToolUse of an edit tool        while a snapshot is pending, record the
                                       edited path: another agent's edit is
                                       not the command's side effect

A change is a change on disk (`lstat` mtime and size), not a change of git
status: `git add` and `git commit` are silent. Advisory only: the hook never
blocks, always exits 0, and says nothing outside a git work tree.

State: `.sentinel/runtime/side_effect/`, which ignores itself (`.gitignore`
holding `*`). Phase-gated through `_phase_policy.PHASE_POLICY`.
Failure mode: an error inside main() is recorded through `_hook_log` and the
call goes on.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import _phase_policy  # noqa: E402

HOOK_NAME = "side_effect_check"
STATE_DIR = Path(".sentinel") / "runtime" / "side_effect"
REPORTED_FILE = "reported.json"
SLOW_MARKER = "slow"
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
EDIT_TOOLS = frozenset({"Edit", "Write", "NotebookEdit", "MultiEdit"})
CLOSING_EVENTS = frozenset({"PostToolUse", "PostToolUseFailure"})
GIT_TIMEOUT = 2.0  # seconds, per git call
STALE_SECONDS = 3600
MAX_LISTED = 5
MAX_KEYS = 50
MAX_PATHS_PER_KEY = 2000
MAX_GLOBS = 100
MAX_GLOB_CHARS = 256
SLOW_TEXT = "git took more than 2 s; the side-effect check is off for an hour"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_KEEP = frozenset({REPORTED_FILE, ".gitignore"})


# ---------- what changed ----------

def parse_status(output: str) -> list[str]:
    """Paths of a `git status --porcelain=v1 -z` output. A rename or copy
    entry carries its source as a second field, which is skipped."""
    fields = output.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1
    return paths


def _lstat(top: str, path: str) -> list[int] | None:
    try:
        st = os.lstat(os.path.join(top, path))
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def changed_paths(before: dict, after: dict, listed: Iterable[str]) -> list[str]:
    """`before` and `after` map a path to `[mtime_ns, size]` or None. A path is
    changed when it is new to the list, or when its file differs from the
    stored one. A path that left the list with its file untouched is not."""
    changed = [p for p in listed if p not in before]
    changed += [p for p, stored in before.items() if after.get(p) != stored]
    return changed


def is_state_path(path: str) -> bool:
    """3eAI SDLC's own state: hooks write there during any call."""
    probe = "/" + path
    return "/.sentinel/runtime/" in probe or "/.sentinel-control/" in probe


# ---------- what the command names ----------

_REWRITING = frozenset({
    "checkout", "switch", "restore", "reset", "stash", "merge", "rebase", "pull",
    "cherry-pick", "revert", "apply", "am", "clean", "submodule", "bisect",
    "sparse-checkout", "lfs",
})
_PREFIX_WORDS = frozenset({
    "then", "do", "else", "elif", "if", "while", "until", "time", "nohup",
    "command", "exec", "sudo", "env", "nice", "timeout",
})
_GIT_ARG_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
_LOCATION_COMMANDS = frozenset({"cd", "pushd", "set-location", "push-location"})
_EVERYTHING = frozenset({".", "./", "*", "./*"})
_WORD_SPLIT = re.compile(r"[\s'\"`;&|()<>,=]+")
_GLOB = re.compile(r"[*?\[]")


def _segments(command: str, heredoc_bodies: bool) -> list[str]:
    # Imported here, not at the top: the gate module is needed only once a
    # change was found, and a failure to import it is recorded by main().
    import forced_rule_set_gate
    return forced_rule_set_gate.split_shell_commands(command, heredoc_bodies=heredoc_bodies)


def _strip_wrapping(word: str) -> str:
    while word.startswith(("$(", "(", "{", "!")):
        word = word[2:] if word.startswith("$(") else word[1:]
    return word.rstrip(")")


def rewrites_tree(command: str) -> bool:
    """True when a segment of the command is a git command whose job is to
    rewrite the work tree (`git stash pop`, `git checkout x`)."""
    if not isinstance(command, str) or not command:
        return False
    for segment in _segments(command, False):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        words = [_strip_wrapping(w) for w in words]
        i = 0
        while i < len(words) and (
            not words[i] or _ASSIGNMENT.match(words[i]) or words[i].startswith("-")
            or words[i][0].isdigit() or words[i] in _PREFIX_WORDS
        ):
            i += 1
        if i >= len(words) or os.path.basename(words[i]) != "git":
            continue
        i += 1
        while i < len(words):
            if words[i] in _GIT_ARG_OPTIONS:
                i += 2
            elif words[i].startswith("-"):
                i += 1
            else:
                break
        if i < len(words) and words[i] in _REWRITING:
            return True
    return False


def _names_everything(command: str) -> bool:
    """An unquoted `.`, `./`, `*` or `./*` on the command line itself: the
    command works on "everything here". Heredoc bodies, quoted words, the
    command word and location words do not count."""
    for segment in _segments(command, False):
        try:
            tokens = shlex.split(segment, posix=False)
        except ValueError:
            tokens = segment.split()
        if not tokens or tokens[0].lstrip("({").lower() in _LOCATION_COMMANDS:
            continue
        skip = False
        for token in tokens[1:]:
            if skip:
                skip = False
            elif token == "-C":
                skip = True
            elif token.rstrip(")") in _EVERYTHING:
                return True
    return False


def _relative_to_top(path: str, top: str) -> str | None:
    """`path` relative to `top` in `/` form; '' for the top itself; None when
    it lies outside. The path and its real path are both tried."""
    bases = {os.path.normcase(os.path.normpath(t)) for t in (top, os.path.realpath(top))}
    for candidate in (path, os.path.realpath(path)):
        norm = os.path.normpath(candidate)
        folded = os.path.normcase(norm)
        for base in bases:
            if folded == base:
                return ""
            if folded.startswith(base + os.sep):
                return norm[len(base) + 1:].replace(os.sep, "/")
    return None


def _normalise(word: str, top: str, backslash: bool) -> str:
    if backslash:
        word = word.replace("\\", "/")
    if word.startswith("~"):
        word = os.path.expanduser(word)
    if os.path.isabs(word):
        relative = _relative_to_top(word, top)
        if relative is None:
            return ""  # outside the work tree: names nothing in it
        word = relative
    parts = word.split("/")
    while parts and parts[0] in (".", ".."):
        parts.pop(0)
    return "/".join(parts).strip("/")


def _command_words(command: str, top: str, backslash: bool) -> tuple[set[str], list[re.Pattern]]:
    """Plain words and compiled glob words of the command, heredoc bodies
    included: a script written inline names the files in its text."""
    plain: set[str] = set()
    globs: list[re.Pattern] = []
    for segment in _segments(command, True):
        words = [w for w in _WORD_SPLIT.split(segment) if w]
        if not words or words[0].lower() in _LOCATION_COMMANDS:
            continue  # `cd src` says where the command runs, not what it changes
        skip = False
        for word in words:
            if skip:
                skip = False
                continue
            if word == "-C":
                skip = True
                continue
            word = _normalise(word, top, backslash)
            if not word:
                continue
            if not _GLOB.search(word):
                plain.add(word)
            elif (len(globs) < MAX_GLOBS and len(word) <= MAX_GLOB_CHARS
                  and any(c.isalnum() for c in word)):
                try:  # from a component boundary to the end of the path
                    globs.append(re.compile(r"(?:.*/)?" + fnmatch.translate(word)))
                except re.error:
                    continue
    return plain, globs


def _has_run(parts: list[str], plain: set[str]) -> bool:
    """True when a run of whole components of the path is one of the words."""
    for i in range(len(parts)):
        run = parts[i]
        if run in plain:
            return True
        for part in parts[i + 1:]:
            run += "/" + part
            if run in plain:
                return True
    return False


def named_paths(command: str, changed: Iterable[str], top: str, tool_name: str = "Bash") -> set[str]:
    """The changed paths the command names."""
    changed = list(changed)
    if not changed or not isinstance(command, str) or not command:
        return set()
    if _names_everything(command):
        return set(changed)
    plain, globs = _command_words(command, top, tool_name == "PowerShell")
    named: set[str] = set()
    for path in changed:
        clean = path.strip("/")
        if _has_run(clean.split("/"), plain) or any(g.match(clean) for g in globs):
            named.add(path)
    return named


# ---------- what was already said ----------

def _load_reported(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def reported_paths(path: Path, key: str) -> set[str]:
    entry = _load_reported(path).get(key)
    paths = entry.get("paths") if isinstance(entry, dict) else None
    return {p for p in paths if isinstance(p, str)} if isinstance(paths, list) else set()


def remember_reported(path: Path, key: str, paths: Iterable[str], now: float | None = None) -> None:
    """Add `paths` to the list of `key`; keep the newest paths per key and the
    most recently written keys. An unreadable file counts as empty."""
    path = Path(path)
    data = {k: v for k, v in _load_reported(path).items()
            if isinstance(v, dict) and isinstance(v.get("paths"), list)}
    known = [p for p in data.get(key, {}).get("paths", []) if isinstance(p, str)]
    data[key] = {"at": time.time() if now is None else now,
                 "paths": (known + list(paths))[-MAX_PATHS_PER_KEY:]}
    newest = sorted(data.items(), key=lambda kv: _number(kv[1].get("at")), reverse=True)[:MAX_KEYS]
    _write_json(path, dict(newest))


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def build_message(paths: Iterable[str]) -> str:
    """One factual line: hook context that reads as a command can be taken
    for an injected instruction."""
    paths = sorted(paths)
    listed = ", ".join(paths[:MAX_LISTED])
    if len(paths) > MAX_LISTED:
        listed += f" (+{len(paths) - MAX_LISTED} more)"
    return (
        f"3eAI SDLC side-effect check: {len(paths)} file(s) changed during this command "
        f"that it does not name: {listed}. Each path is listed once."
    )


# ---------- state ----------

def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def _ensure_state_dir(state: Path) -> None:
    state.mkdir(parents=True, exist_ok=True)
    ignore = state / ".gitignore"
    if not ignore.exists():  # the directory ignores itself: no project needs a rule
        ignore.write_text("*\n", encoding="utf-8")


def _remove_stale(state: Path) -> None:
    try:
        entries = list(state.iterdir())
    except OSError:
        return
    cutoff = time.time() - STALE_SECONDS
    for entry in entries:
        if entry.name in _KEEP:
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:  # another call removed it first
            continue


def mark_slow(root: Path) -> bool:
    """Switch the check off for an hour. Only the call that creates the marker
    records the failure; returns whether this call did."""
    state = Path(root) / STATE_DIR
    _ensure_state_dir(state)
    try:
        os.close(os.open(state / SLOW_MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    import _hook_log
    _hook_log.record_failure(HOOK_NAME, root, TimeoutError(SLOW_TEXT))
    return True


def _git(root: Path, *args: str) -> str | None:
    """Output of `git -C root args`, or None when git is missing or fails.
    Raises subprocess.TimeoutExpired after GIT_TIMEOUT seconds."""
    try:
        proc = subprocess.Popen(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    try:
        out, _ = proc.communicate(timeout=GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=1)
        except Exception:  # noqa: BLE001 — a child may still hold the pipe
            pass
        raise
    if proc.returncode != 0:
        return None
    # A file name that is not UTF-8 survives the snapshot file and os.lstat.
    return out.decode("utf-8", "surrogateescape")


def _list_changed(root: Path) -> list[str] | None:
    # --no-optional-locks: this runs beside the agent's own git commands.
    out = _git(root, "--no-optional-locks", "status", "--porcelain=v1", "-z",
               "--untracked-files=all", "--", ".")
    return None if out is None else parse_status(out)


def _edited_paths(state: Path, top: str, since: float) -> set[str]:
    """Paths other tool calls edited since the snapshot, relative to the top."""
    edited: set[str] = set()
    for record in state.glob("edit-*.json"):
        try:
            if record.stat().st_mtime < since:
                continue
            path = json.loads(record.read_text(encoding="utf-8")).get("path")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(path, str):
            relative = _relative_to_top(path, top)
            if relative:
                edited.add(relative)
    return edited


# ---------- events ----------

def _before_shell(root: Path, tool_use_id: str) -> None:
    state = root / STATE_DIR
    if state.is_dir():
        _remove_stale(state)
        if (state / SLOW_MARKER).exists():
            return
    try:
        top = _git(root, "rev-parse", "--show-toplevel")
        if top is None:
            return  # not a git work tree: nothing cheap to compare
        top = top.strip()
        listed = _list_changed(root)
    except subprocess.TimeoutExpired:
        mark_slow(root)
        return
    if listed is None:
        return
    snapshot = {"top": top, "at": time.time(), "paths": {p: _lstat(top, p) for p in listed}}
    _ensure_state_dir(state)
    _write_json(state / f"snap-{tool_use_id}.json", snapshot)


def _after_shell(root: Path, event: dict[str, Any], tool_use_id: str) -> str:
    """The message for the agent, or '' when there is nothing to say."""
    state = root / STATE_DIR
    snap_file = state / f"snap-{tool_use_id}.json"
    try:
        snapshot = json.loads(snap_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        snapshot = None
    try:
        snap_file.unlink()
    except OSError:
        pass
    if not isinstance(snapshot, dict):
        return ""
    top, before = snapshot.get("top"), snapshot.get("paths")
    if not isinstance(top, str) or not isinstance(before, dict):
        return ""
    response = event.get("tool_response")
    if isinstance(response, dict) and isinstance(response.get("backgroundTaskId"), str) \
            and response["backgroundTaskId"]:
        return ""  # moved to the background at its timeout: still running
    if (state / SLOW_MARKER).exists():
        return ""
    try:
        listed = _list_changed(root)
    except subprocess.TimeoutExpired:
        mark_slow(root)
        return ""
    if listed is None:
        return ""
    after = {p: _lstat(top, p) for p in set(listed) | set(before)}
    changed = [p for p in changed_paths(before, after, listed) if not is_state_path(p)]
    if not changed:
        return ""
    command = event["tool_input"]["command"]
    if rewrites_tree(command):
        return ""
    explained = named_paths(command, changed, top, event.get("tool_name", "Bash"))
    explained |= _edited_paths(state, top, _number(snapshot.get("at")))
    key = str(event.get("session_id") or "")
    if isinstance(event.get("agent_id"), str) and event["agent_id"]:
        key += "/" + event["agent_id"]
    seen = reported_paths(state / REPORTED_FILE, key)
    fresh = sorted(p for p in changed if p not in explained and p not in seen)
    if not fresh:
        return ""
    remember_reported(state / REPORTED_FILE, key, fresh)
    return build_message(fresh)


def _after_edit(root: Path, event: dict[str, Any], tool_use_id: str, cwd: Path) -> None:
    state = root / STATE_DIR
    if not state.is_dir() or not any(state.glob("snap-*.json")):
        return  # no shell call is running: nobody to explain the edit to
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    path = next((tool_input[k] for k in ("file_path", "notebook_path")
                 if isinstance(tool_input.get(k), str) and tool_input[k]), None)
    if path is None:
        return
    if not os.path.isabs(path):
        path = os.path.join(str(cwd), path)
    _write_json(state / f"edit-{tool_use_id}.json", {"path": path})


def _read_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def main() -> int:
    root: Path | None = None  # the project root, once resolved
    tool = ""
    try:
        event = _read_event()
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return 0
        root = _phase_policy.project_root(Path(cwd))
        if not _phase_policy.is_active(HOOK_NAME, root):
            return 0
        tool_use_id = event.get("tool_use_id")
        if not isinstance(tool_use_id, str) or not _SAFE_ID.match(tool_use_id):
            return 0  # it becomes a file name
        name = event.get("hook_event_name")
        tool = event.get("tool_name") if isinstance(event.get("tool_name"), str) else ""

        if tool in EDIT_TOOLS:
            if name == "PostToolUse":
                _after_edit(root, event, tool_use_id, Path(cwd))
            return 0
        if tool not in SHELL_TOOLS:
            return 0
        tool_input = event.get("tool_input")
        if not isinstance(tool_input, dict) or not isinstance(tool_input.get("command"), str):
            return 0
        if tool_input.get("run_in_background") is True:
            return 0  # its closing event fires before the command ends

        if name == "PreToolUse":
            _before_shell(root, tool_use_id)
        elif name in CLOSING_EVENTS:
            message = _after_shell(root, event, tool_use_id)
            if message:
                json.dump({"hookSpecificOutput": {"hookEventName": name,
                                                  "additionalContext": message}}, sys.stdout)
                sys.stdout.write("\n")
        return 0
    except Exception as exc:
        try:  # fail open, but not silently
            import _hook_log  # noqa: E402
            _hook_log.record_failure(HOOK_NAME, root, exc, tool)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())

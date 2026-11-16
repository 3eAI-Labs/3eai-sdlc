"""A hook that fails still lets the call through (fail-open), but says so.

`record_failure` appends one row to `.sentinel/runtime/hook_errors.jsonl` and
one pending `HOOK_ERROR` flag to `audit_findings_pending.json`, which the
plan-anchor hook shows on the next prompt. It writes only where
`.sentinel/runtime/` already exists (a project that never declared a phase
gets no files) and never raises. Each hook imports it inside its own `except`,
so a broken or missing copy costs only the record. Stdlib only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_RUNTIME = Path(".sentinel") / "runtime"
ERRORS_FILE = _RUNTIME / "hook_errors.jsonl"
PENDING_FILE = _RUNTIME / "audit_findings_pending.json"
MAX_ROWS = 200
MAX_PENDING_FLAGS = 50  # the gate's writer keeps the same number
MAX_MESSAGE_CHARS = 300


def record_failure(hook: str, root, exc: BaseException, tool: str = "") -> None:
    """Record that `hook` failed with `exc` in the project at `root` and let
    the call through. `tool` is the tool the hook was judging, if any."""
    try:
        if root is None:
            return
        root = Path(root)
        if not (root / _RUNTIME).is_dir():
            return
        error = f"{type(exc).__name__}: {str(exc)[:MAX_MESSAGE_CHARS]}"
        ts = datetime.now(timezone.utc).isoformat()
        tool = tool if isinstance(tool, str) else ""
        _append_row(root / ERRORS_FILE, {"ts": ts, "hook": hook, "error": error, "tool": tool})
        _append_flag(root / PENDING_FILE, {
            "ts": ts,
            "tool": hook,
            "target": tool,
            "warden_decision": "HOOK_ERROR",
            "reason": f"{hook} failed and let the call through: {error}",
            "plan_step_id": None,
            "resolved": False,
        })
    except Exception:  # noqa: BLE001 — the hooks stay fail-open
        return


def _append_row(path: Path, row: dict) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        lines.append(json.dumps(row, ensure_ascii=False))
        path.write_text("\n".join(lines[-MAX_ROWS:]) + "\n", encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return


def _append_flag(path: Path, flag: dict) -> None:
    try:
        entries: list = []
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    entries = [e for e in raw if isinstance(e, dict)]
            except (json.JSONDecodeError, UnicodeDecodeError):
                entries = []
        entries.append(flag)
        path.write_text(json.dumps(entries[-MAX_PENDING_FLAGS:], indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return

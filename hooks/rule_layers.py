#!/usr/bin/env python3
"""Layered rule resolution: plugin default → user → project.

    plugin   <plugin_root>/.claude-plugin/runtime/<file>
    user     ~/.sentinel/<file>
    project  <cwd>/.sentinel-control/<file>

Before this module the gate read one cwd-relative file and returned `[]` when
it was missing: a project with `forced_rule_set` ON but no patterns file had
no destructive-pattern protection, and nothing said so.

Merge semantics
---------------
- Rule identity is `id`. Entries without one get a deterministic id from
  their content (`auto:<sha1[:12]>`), so a later layer can still target them.
- A later layer shallow-merges onto an earlier one by id, e.g.
  `{"id": "sql-truncate", "level": "off"}` without copying the rule.
- Changing or switching off a rule another layer introduced is honored only
  from the user layer (`override_is_honored()`). The project file lives in the
  repo the agent edits, and any field (`command_regex`, `tool`, `level`) can
  neuter a rule, so a project may add rules and change its own, nothing else.
  Refused overrides are listed in the report; the rule stays as it was.
- Position is owned by the layer that introduced the rule; overriding never
  reorders.

Failure policy: a malformed layer is skipped and recorded in
`report["errors"]`; nothing raises. Stdlib only, Python 3.8+.

Check what is active in a project:

    python3 <plugin_root>/hooks/rule_layers.py destructive_patterns.json [cwd]
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Ordered lowest → highest priority.
LAYER_ORDER = ("plugin", "user", "project")

PLUGIN_RULES_DIR = Path(".claude-plugin") / "runtime"
USER_RULES_DIR = Path(".sentinel")
# The gate's control files: a direct child of the project root, so a sandbox
# write denial on it cannot be undone by renaming a parent (measured
# 2026-10-14: a bwrap read-only bind does not protect its ancestors).
CONTROL_DIR = Path(".sentinel-control")
PROJECT_RULES_DIR = CONTROL_DIR

_ID_FIELDS = ("tool", "command_regex", "file_regex", "regex", "pattern", "reason")


# Layers outside the project repo that may change another layer's rules.
OVERRIDING_LAYERS = ("user",)


def override_is_honored(introduced_by: str, from_layer: str) -> bool:
    """May layer `from_layer` change a rule that layer `introduced_by` shipped?"""
    return from_layer == introduced_by or from_layer in OVERRIDING_LAYERS


def auto_id(entry: Dict[str, Any]) -> str:
    """Deterministic id for a rule that declares none."""
    parts = [f"{k}={entry.get(k, '')!r}" for k in _ID_FIELDS]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"auto:{digest[:12]}"


def _layer_dirs(
    cwd: Path, plugin_root: Optional[Path], home: Optional[Path]
) -> List[Tuple[str, Path]]:
    plugin_root = Path(plugin_root) if plugin_root else Path(__file__).resolve().parent.parent
    home = Path(home) if home else Path.home()
    return [
        ("plugin", plugin_root / PLUGIN_RULES_DIR),
        ("user", home / USER_RULES_DIR),
        ("project", Path(cwd) / PROJECT_RULES_DIR),
    ]


def _resolve(path: Path) -> str:
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):  # RuntimeError: symlink loop before 3.13
        return str(path)


def _entries_from_payload(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Accept {"rules": [...]}, {"patterns": [...]} or a bare list."""
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, dict):
        for key in ("rules", "patterns"):
            value = payload.get(key)
            if isinstance(value, list):
                return [e for e in value if isinstance(e, dict)]
    return None


def _layer_rules(path: Path) -> Tuple[Optional[List[Tuple[str, Dict[str, Any]]]], List[str]]:
    """`(rule_id, entry)` pairs of one layer file, and the non-string ids skipped.

    May raise; the caller then skips the whole layer, so a bad file never
    leaves half its rules merged.
    """
    entries = _entries_from_payload(json.loads(path.read_text(encoding="utf-8")))
    if entries is None:
        return None, []
    staged: List[Tuple[str, Dict[str, Any]]] = []
    skipped: List[str] = []
    for entry in entries:
        raw_id = entry.get("id")
        if raw_id is not None and not isinstance(raw_id, str):
            skipped.append(type(raw_id).__name__)
            continue
        staged.append((raw_id or auto_id(entry), entry))
    return staged, skipped


def load_layered_rules(
    filename: str,
    cwd: Any,
    plugin_root: Any = None,
    home: Any = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Resolve `filename` across the three layers.

    Returns `(rules, report)`. `rules` is ordered and excludes rules switched
    off with an honored `level: "off"`.
    """
    merged: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    introduced_by: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    refused: List[str] = []
    layers: List[Dict[str, Any]] = []
    errors: List[str] = []

    # One directory can serve two roles (e.g. cwd under the plugin root).
    # Keep the highest-priority name and load it once.
    by_path: "OrderedDict[str, str]" = OrderedDict()
    for name, directory in _layer_dirs(Path(cwd), plugin_root, home):
        by_path[_resolve(directory / filename)] = name

    for resolved_path, name in by_path.items():
        path = Path(resolved_path)
        if not path.is_file():
            continue
        try:
            staged, skipped = _layer_rules(path)
        except Exception as exc:  # noqa: BLE001
            # The gate fails open on exceptions: anything raised here switched
            # off every layer (a symlink loop, an unhashable id, deep nesting).
            errors.append(f"{name} layer at {path}: {type(exc).__name__}")
            continue
        if staged is None:
            errors.append(f"{name} layer at {path}: no 'rules'/'patterns' list")
            continue
        errors.extend(f"{name} layer at {path}: non-string id ({t}) skipped" for t in skipped)

        for rule_id, entry in staged:
            if rule_id in merged:
                if not override_is_honored(introduced_by[rule_id], name):
                    refused.append(f"{rule_id} ({name})")
                    continue
                merged[rule_id] = {**merged[rule_id], **entry, "id": rule_id}
            else:
                merged[rule_id] = {**entry, "id": rule_id}
                introduced_by[rule_id] = name
            sources[rule_id] = name

        layers.append({"name": name, "path": str(path), "count": len(staged) + len(skipped)})

    disabled = [
        rid for rid, rule in merged.items()
        if isinstance(rule.get("level"), str) and rule["level"].lower() == "off"
    ]
    rules = [rule for rid, rule in merged.items() if rid not in disabled]

    report = {
        "layers": layers,
        "total": len(rules),
        "disabled": disabled,
        "refused": refused,
        "sources": sources,
        "errors": errors,
        "summary": _summarize(filename, layers, len(rules), disabled, refused, errors),
    }
    return rules, report


def _summarize(
    filename: str,
    layers: Iterable[Dict[str, Any]],
    total: int,
    disabled: List[str],
    refused: List[str],
    errors: List[str],
) -> str:
    layers = list(layers)
    if not layers:
        return (
            f"{filename}: no rule layers found (plugin/user/project all absent) — "
            f"0 rules active. This is not protection."
        )
    where = ", ".join(f"{layer['name']}={layer['count']}" for layer in layers)
    text = f"{filename}: {total} rules active from {len(layers)} layer(s) [{where}]"
    if disabled:
        text += f"; {len(disabled)} switched off ({', '.join(disabled)})"
    if refused:
        text += f"; {len(refused)} cross-layer override(s) refused ({', '.join(refused)})"
    if errors:
        text += f"; {len(errors)} layer(s) skipped on error: {'; '.join(errors)}"
    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: rule_layers.py <filename> [cwd]", file=sys.stderr)
        sys.exit(2)
    _, _report = load_layered_rules(sys.argv[1], cwd=sys.argv[2] if len(sys.argv) > 2 else Path.cwd())
    print(_report["summary"])

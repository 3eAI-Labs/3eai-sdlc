"""Where a project is, derived from its gate records and deliverables.

Sentinel's claim is that the user knows how a project is built, not how
sentinel works. So the plugin works out the project's phase itself, refuses
to start a phase the project has not reached, and tells the model which skill
to enter; the user is asked only project questions ("approve the
architecture?"), never about phases, skills or markers.

- Two flows: the eight-phase Enterprise flow (`PHASES`) and the four-stage
  Core flow (`STAGES`). `flow(root)` reads the project's flow from
  `.sentinel/flow`, else infers it (see `flow`); None means undecided.
- `derive(root)`: in the project's flow, the later of (a) the phase after the
  highest approved gate and (b) the highest phase whose deliverables directory
  holds work; with neither, the flow's first phase. A gate's state is the
  decision of the last record in its gate file (`PHASE<N>_GATE.md`,
  `DEFINE_GATE.md`, …); a gate file with no decision line (written before gate
  records existed) and a phase 1 `PHASE1_APPROVAL.md` count as approved. An
  undecided project derives the empty phase. A project moved from Core
  (`upgraded-from: core <date>`) is at the first Enterprise phase without an
  approved gate.
- `route(root, phase)`: None when `phase` is a mode or a key of the project's
  flow at or before the derived phase, else the route text.
- `agent_route(root, phases)`: None when the marker is one of a phase
  agent's phases and not ahead of the project, else the route text.
- `hook_route(root, prompt)`: the plan-anchor hook's route for a missing,
  unknown or ahead-of-the-project marker in a project with deliverables.
- `write_approval(...)`: appends a Checkpoint Approval Record
  (HUMAN_OVERSIGHT_GUIDELINE §2.3) to the phase's gate file.
- `record_flow(root, flow)`, `upgrade(root)`: write `.sentinel/flow`.
- `find_root(cwd)`: the project root these read and write.
- `edition()`: `free` or `pro`, from the plugin's `BUILD_INFO.json`. The
  free edition holds the Core flow only: it refuses `flow enterprise` and
  `upgrade`, names sentinel Pro where Pro names an enterprise skill, and lets
  `flow core` replace an enterprise flow inferred only from a deliverables
  directory.

Stdlib only; errors propagate (the CLI and the hook fail open around them).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import _phase_policy


@dataclass(frozen=True)
class Phase:
    key: str
    directory: str   # where the phase's work lives
    gate_dir: str    # where its gate file lives
    label: str       # "3.5" in file names and prose
    checkpoint: str  # HUMAN_OVERSIGHT_GUIDELINE §2.1
    name: str        # what the user calls it
    gate_file: str   # the gate record's file name, in gate_dir
    review_file: str  # the review report's file name
    title: str       # the gate file's heading


def _enterprise(key: str, directory: str, gate_dir: str, label: str, checkpoint: str,
                name: str) -> Phase:
    return Phase(key, directory, gate_dir, label, checkpoint, name, f"PHASE{label}_GATE.md",
                 f"PHASE{label}_REVIEW.md", f"Phase {label}")


def _core(key: str, directory: str, name: str) -> Phase:
    up = key.upper()
    return Phase(key, directory, directory, key.title(), "—", name, f"{up}_GATE.md",
                 f"{up}_REVIEW.md", key.title())


_TABLE = (
    _enterprise("phase1", "docs/01_product", "docs/01_product", "1", "A", "product requirements"),
    _enterprise("phase2", "docs/02_business", "docs/02_business", "2", "B", "business rules"),
    _enterprise("phase3", "docs/03_architecture", "docs/03_architecture", "3", "C", "architecture (HLD)"),
    _enterprise("phase35", "docs/035_skeleton", "docs/035_skeleton", "3.5", "—", "walking skeleton"),
    _enterprise("phase4", "docs/04_design", "docs/04_design", "4", "D", "detailed design (LLD)"),
    _enterprise("phase5", "docs/05_implementation", "docs/05_implementation", "5", "E", "implementation"),
    _enterprise("phase55", "docs/05_implementation/testing", "docs/05_implementation", "5.5", "F", "testing"),
    _enterprise("phase6", "docs/06_deploy", "docs/06_deploy", "6", "G", "release"),
)
# The Core flow writes into the Enterprise directories, so a project can move on.
_CORE = (
    _core("define", "docs/01_product", "requirements"),
    _core("design", "docs/03_architecture", "design"),
    _core("build", "docs/05_implementation", "build"),
    _core("release", "docs/06_deploy", "release"),
)
PHASES = tuple(p.key for p in _TABLE)
STAGES = tuple(p.key for p in _CORE)
FLOWS = {"enterprise": _TABLE, "core": _CORE}
TABLE = {p.key: p for p in (*_TABLE, *_CORE)}
MODES = ("maintenance", "incident", "track0")
FLOW_FILE = Path(".sentinel") / "flow"
DECISIONS = ("APPROVED", "APPROVED WITH CONDITIONS", "REJECTED")

_DECISION = re.compile(r"^#{1,6}\s*Decision:\s*(APPROVED WITH CONDITIONS|APPROVED|REJECTED)\b",
                       re.MULTILINE)
_RECORD_DATE = re.compile(r"Date / Reviewer:\*\*[^/\n]*/[^/\n]*/\s*(\d{4}-\d{2}-\d{2})")
_NOT_WORK = re.compile(
    r"^(PHASE[\d.]+_(REVIEW|GATE)|(DEFINE|DESIGN|BUILD|RELEASE)_(REVIEW|GATE)|PHASE1_APPROVAL)\.md$")
_UPGRADED = re.compile(r"^upgraded-from:\s*core\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_LEGACY_PHASE1 = "PHASE1_APPROVAL.md"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def edition() -> str:
    """`free` when the plugin's `BUILD_INFO.json` says so; else `pro` (the
    development tree, and the Pro builds before the key existed)."""
    try:
        info = json.loads((PLUGIN_ROOT / "BUILD_INFO.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "pro"
    return "free" if isinstance(info, dict) and info.get("edition") == "free" else "pro"


def _free() -> bool:
    return edition() == "free"


@dataclass(frozen=True)
class State:
    phase: str
    reason: str
    source: str  # gate | inferred | none


def gate_path(root: Path, phase: str) -> Path:
    p = TABLE[phase]
    return Path(root) / p.gate_dir / p.gate_file


def _recorded(root: Path) -> tuple[str | None, str | None]:
    """(flow, upgrade date) from `.sentinel/flow`; (None, None) when absent or unreadable as a flow."""
    path = Path(root) / FLOW_FILE
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first not in FLOWS:
        return None, None
    moved = _UPGRADED.search(text) if first == "enterprise" else None
    return first, (moved.group(1) if moved else None)


def flow(root: Path) -> str | None:
    """The project's flow: `.sentinel/flow`, else inferred, committed evidence
    first: a Core gate or review file (core); an Enterprise gate file
    (enterprise); the phase marker's key; any deliverables directory
    (enterprise, so every project from before the Core flow keeps its own).
    None: undecided."""
    return _flow_source(root)[0]


def _flow_source(root: Path) -> tuple[str | None, str]:
    """(flow, what decided it): recorded, review or gate, marker, directory, none."""
    root = Path(root)
    recorded, _ = _recorded(root)
    if recorded:
        return recorded, "recorded"
    if any(gate_path(root, p.key).exists() or (root / p.directory / p.review_file).exists()
           for p in _CORE):
        return "core", "gate"
    if any(gate_path(root, p.key).exists() for p in _TABLE) or \
            (root / TABLE["phase1"].directory / _LEGACY_PHASE1).exists():
        return "enterprise", "gate"
    marker = read_marker(root)
    if marker in STAGES:
        return "core", "marker"
    if marker in PHASES:
        return "enterprise", "marker"
    if any((root / p.directory).is_dir() for p in _TABLE):
        return "enterprise", "directory"
    return None, "none"


def _core_may_replace(root: Path) -> bool:
    """Free edition: an enterprise flow inferred only from a deliverables
    directory may be replaced by `flow core`."""
    return _free() and _flow_source(root) == ("enterprise", "directory")


def _gate(root: Path, phase: str) -> tuple[bool, str]:
    """(approved, date) for a phase's gate; reading errors propagate."""
    path = gate_path(root, phase)
    if not path.exists() and phase == "phase1":
        legacy = Path(root) / TABLE["phase1"].directory / _LEGACY_PHASE1
        if legacy.exists():
            return True, _mtime_date(legacy)
    if not path.exists():
        return False, ""
    text = path.read_text(encoding="utf-8")
    decisions = _DECISION.findall(text)
    dates = _RECORD_DATE.findall(text)
    when = dates[-1] if dates else _mtime_date(path)
    if not decisions:
        return True, when  # a record from before gate records had a decision line
    return decisions[-1] != "REJECTED", when


def _mtime_date(path: Path) -> str:
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def _holds_work(directory: Path, skip: Path | None = None) -> bool:
    if not directory.is_dir():
        return False
    for path in directory.rglob("*"):
        if skip is not None and (path == skip or skip in path.parents):
            continue
        if path.is_file() and not _NOT_WORK.match(path.name):
            return True
    return False


def _reached(root: Path, table: tuple[Phase, ...]) -> str | None:
    """The highest phase of `table` whose deliverables directory holds work."""
    root = Path(root)
    for p in reversed(table):
        skip = root / TABLE["phase55"].directory if p.key == "phase5" else None
        if _holds_work(root / p.directory, skip):
            return p.key
    return None


_UNDECIDED = State("", "no flow recorded", "none")


def derive(root: Path) -> State:
    root = Path(root)
    current = flow(root)
    if current is None:
        return _UNDECIDED
    _, moved = _recorded(root)
    if moved:
        return _derive_moved(root, moved)
    table = FLOWS[current]
    keys = tuple(p.key for p in table)
    approved = [(k, when) for k in keys for ok, when in [_gate(root, k)] if ok]
    reached = _reached(root, table)
    first = table[0]
    if not approved and reached is None:
        return State(first.key, f"no {first.name} yet", "none")
    if approved:
        top, when = approved[-1]
        after = keys[min(keys.index(top) + 1, len(keys) - 1)]
    else:
        after = first.key
    if reached is not None and keys.index(reached) > keys.index(after):
        return State(reached, f"work on the {TABLE[reached].name} is in progress; "
                              "no approval is recorded for it yet", "inferred")
    if not approved:
        return State(after, f"work on the {TABLE[after].name} is in progress; "
                            "no approval is recorded for it yet", "inferred")
    return State(after, f"the {TABLE[top].name} {_was(TABLE[top].name)} approved on {when}", "gate")


def _was(name: str) -> str:
    return "were" if name.endswith("s") else "was"


def _derive_moved(root: Path, moved: str) -> State:
    """A project moved from Core: its Core work sits in the Enterprise
    directories, so only the Enterprise gate records count."""
    for key in PHASES:
        ok, _ = _gate(root, key)
        if not ok:
            return State(key, f"the project moved from the Core flow on {moved}; no approval "
                              f"is recorded for the {TABLE[key].name} yet", "none")
    return State(PHASES[-1], f"the {TABLE[PHASES[-1]].name} {_was(TABLE[PHASES[-1]].name)} approved", "gate")


def read_marker(root: Path) -> str:
    path = Path(root) / _phase_policy.CURRENT_PHASE_FILE
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def has_deliverables(root: Path) -> bool:
    root = Path(root)
    return any((root / p.directory).is_dir() or gate_path(root, p.key).exists()
               for p in (*_TABLE, *_CORE))


def find_root(cwd: Path) -> Path:
    """`CLAUDE_PROJECT_DIR` when it holds state, a flow file or deliverables;
    else the nearest of `cwd` and its parents holding a deliverables directory
    or a flow file; else the hooks' project root."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (_phase_policy._holds_state(Path(env)) or (Path(env) / FLOW_FILE).is_file()
                or has_deliverables(Path(env))):
        return Path(env)
    here = Path(cwd).resolve()
    for d in (here, *here.parents):
        if (d / FLOW_FILE).is_file() or any((d / p.directory).is_dir() for p in _TABLE):
            return d
    return _phase_policy.project_root(Path(cwd))


def _keys(current: str) -> tuple[str, ...]:
    return tuple(p.key for p in FLOWS[current])


def _ahead(phase: str, state: State, keys: tuple[str, ...] = PHASES) -> bool:
    return phase in keys and state.phase in keys and keys.index(phase) > keys.index(state.phase)


_NO_PHASE_QUESTIONS = "do not ask the user about phases, skills or markers."

_SIZE_ROUTE = (
    "SENTINEL ROUTE: this project has no sentinel flow recorded yet. Unless the user's request "
    "already says how big the project is, ask the user once, in project terms: is this a small "
    "project (one developer or a small team, with no regulatory or multi-team requirements) or "
    "an enterprise one? Record the answer with `sentinel-state flow core` (small project) or "
    "`sentinel-state flow enterprise` (enterprise project), then enter the sentinel:define "
    "skill (small project) or the sentinel:phase1 skill (enterprise project) with the Skill "
    "tool. Apart from that one question, do not ask the user about phases, skills, flows or "
    "markers.")

PRO_SENTENCE = ("the enterprise flow (several teams, regulatory requirements, formal architecture "
                "and release gates) is part of sentinel Pro; this edition of sentinel holds the "
                "Core flow")

_FREE_UNDECIDED_ROUTE = (
    "SENTINEL ROUTE: this project has no sentinel flow recorded yet. If the user's request says "
    "the project is large (several teams, regulatory requirements), first tell the user once, in "
    f"project terms, that {PRO_SENTENCE}, offer to build it with the Core flow, and go on only "
    "after the user accepts; record nothing before that. Then run `sentinel-state flow core` and "
    "enter the sentinel:define skill with the Skill tool. Apart from that one offer, do not ask "
    "the user about phases, skills, flows or markers.")


def _pro_route(root: Path, state: State) -> str:
    """Free edition: the route of a project that follows the enterprise flow."""
    text = (f"SENTINEL ROUTE: this project follows sentinel's enterprise flow ({state.reason}); "
            f"{PRO_SENTENCE}. Tell the user so once, in project terms.")
    if _core_may_replace(root):
        text += (" Its flow was inferred from its documentation folders only, so it can go on "
                 "with the Core flow: offer that, and after the user accepts run `sentinel-state "
                 "flow core`, then `sentinel-state status`, and enter the skill it names with "
                 "the Skill tool.")
    return text + f" Otherwise {_NO_PHASE_QUESTIONS}"


def _other_flow_route(state: State, current: str, wanted: Phase) -> str:
    here = TABLE[state.phase]
    if current == "core" and _free():
        return (f"SENTINEL ROUTE: this project follows sentinel's Core flow and is at the "
                f"{here.name} stage ({state.reason}); the {wanted.name} phase is not part of this "
                f"edition. Enter the sentinel:{state.phase} skill with the Skill tool and continue "
                f"there; {_NO_PHASE_QUESTIONS}")
    if current == "core":
        return (f"SENTINEL ROUTE: this project follows sentinel's Core flow and is at the "
                f"{here.name} stage ({state.reason}); the {wanted.name} phase belongs to the "
                f"enterprise flow. Enter the sentinel:{state.phase} skill with the Skill tool and "
                "continue there. Only if the user asked for the full enterprise process: confirm "
                "it with the user in project terms, run `sentinel-state upgrade`, then enter the "
                f"sentinel:phase1 skill. Otherwise {_NO_PHASE_QUESTIONS}")
    return (f"SENTINEL ROUTE: this project follows sentinel's enterprise flow and is at the "
            f"{here.name} stage ({state.reason}); the Core {wanted.label} stage does not apply to "
            f"it. Enter the sentinel:{state.phase} skill with the Skill tool and continue there; "
            f"{_NO_PHASE_QUESTIONS}")


def route(root: Path, requested: str) -> str | None:
    if requested in MODES:
        return None
    if requested not in TABLE:
        raise ValueError(f"unknown phase {requested!r}")
    current = flow(root)
    if current is None:
        return _undecided_route()
    state = derive(root)
    if current == "enterprise" and _free():
        return _pro_route(root, state)
    keys = _keys(current)
    if requested not in keys:
        return _other_flow_route(state, current, TABLE[requested])
    if not _ahead(requested, state, keys):
        return None
    here, wanted = TABLE[state.phase], TABLE[requested]
    return (f"SENTINEL ROUTE: this project is at the {here.name} stage ({state.reason}), so work on "
            f"the {wanted.name} cannot start yet. Enter the sentinel:{state.phase} skill with the "
            "Skill tool and continue there. Tell the user what the project needs next in project "
            f"terms (for example: work on the {here.name} is to be finished and approved); "
            f"{_NO_PHASE_QUESTIONS}")


def shown(marker: str) -> str:
    """The marker as a route shows it: no control characters, 40 at most."""
    return "".join(ch for ch in marker if ch.isprintable())[:40]


def _undecided_route() -> str:
    return _FREE_UNDECIDED_ROUTE if _free() else _SIZE_ROUTE


def agent_route(root: Path, phases: tuple[str, ...]) -> str | None:
    current = flow(root)
    if current is None:
        return _undecided_route()
    marker = read_marker(root)
    state = derive(root)
    if current == "enterprise" and _free():
        return _pro_route(root, state)
    keys = _keys(current)
    if marker in phases and marker in keys and not _ahead(marker, state, keys):
        return None
    mine, here = TABLE[phases[0]], TABLE[state.phase]
    return (f"SENTINEL ROUTE: this agent belongs to the {mine.name} stage; its skill was not "
            f"entered (phase marker: '{shown(marker) or 'none'}'). The project is at the "
            f"{here.name} stage ({state.reason}). Return this text to the caller, which enters "
            f"the sentinel:{state.phase} skill with the Skill tool; {_NO_PHASE_QUESTIONS}")


_OTHER_SKILLS = (
    "sentinel:maintenance, sentinel:incident, sentinel:track0 (platform work), sentinel:review "
    "(code review), sentinel:cso (security audit), sentinel:investigate (debugging), "
    "sentinel:sprint or sentinel:retro, sentinel:publish (documentation), sentinel:ship (test, "
    "commit, PR), sentinel:guard or sentinel:freeze (edit safety), sentinel:phase-review, "
    "sentinel:plan-review, sentinel:multi-review, sentinel:decision-audit, sentinel:work-plan, "
    "or an earlier phase's or stage's skill for a change to its deliverables")
_FREE_OTHER_SKILLS = (
    "sentinel:maintenance, sentinel:review (code review), sentinel:investigate (debugging), "
    "sentinel:retro, sentinel:ship (test, commit, PR), sentinel:guard or sentinel:freeze (edit "
    "safety), sentinel:phase-review, or an earlier stage's skill for a change to its deliverables")


def _known() -> frozenset[str]:
    return frozenset().union(*_phase_policy.PHASE_POLICY.values())


def hook_route(root: Path, prompt: str) -> str | None:
    if prompt.lstrip().startswith("/") or not has_deliverables(root):
        return None
    current = flow(root)
    if current is None:
        return None
    marker = read_marker(root)
    state = derive(root)
    keys = _keys(current)
    modes = _known() - set(TABLE)
    if marker and (marker in modes or (marker in keys and not _ahead(marker, state, keys))):
        return None
    if current == "enterprise" and _free():
        return _pro_route(root, state)
    note = f"; the phase marker reads '{shown(marker)}'" if marker else ""
    others = _FREE_OTHER_SKILLS if _free() else _OTHER_SKILLS
    return (f"SENTINEL ROUTE: this project is at the {TABLE[state.phase].name} stage "
            f"({state.reason}), and the phase set does not match it{note}. Before working on its "
            f"deliverables or code, enter the sentinel:{state.phase} skill with the Skill tool. If "
            "a sentinel skill entered earlier in this conversation covers the request, keep going "
            "in it. If the request belongs to another skill, enter that one instead: "
            f"{others}. Do not ask the user about phases, skills or markers.")


def write_approval(root: Path, phase: str, reviewer: str, decision: str = "APPROVED",
                   deliverables: str | None = None, checklist: str | None = None,
                   note: str | None = None, today: str | None = None) -> Path:
    if phase not in TABLE:
        raise ValueError(f"unknown phase {phase!r}")
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision {decision!r}")
    current = flow(root)
    if current is None:
        raise ValueError("no flow recorded for this project; record it with "
                         + ("`sentinel-state flow core` first" if _free() else
                            "`sentinel-state flow core|enterprise` first"))
    keys = _keys(current)
    if phase not in keys:
        raise ValueError(f"{phase} is not part of this project's {current} flow")
    state = derive(root)
    if _ahead(phase, state, keys):
        raise ValueError(f"{phase} is later than the project's phase ({state.phase}); "
                         "a record cannot skip gates")
    p = TABLE[phase]
    path = gate_path(root, phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    review = p.review_file
    record = (
        "\n## Checkpoint Approval Record\n"
        f"**Phase / Checkpoint / Date / Reviewer:** {phase} / {p.checkpoint} / "
        f"{today or datetime.now().date().isoformat()} / {reviewer}\n"
        f"### Deliverables Reviewed: {deliverables or f'{p.directory}/ (review: {review})'}\n"
        f"### Checklist Completion: {checklist or f'per {review}'}\n"
        f"### Decision: {decision}\n"
        f"### Notes / Signature: {note or '—'}; {reviewer}\n"
    )
    head = "" if path.exists() else f"# {p.title} Gate\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(head + record)
    return path


def write_marker(root: Path, phase: str) -> None:
    runtime = Path(root) / _phase_policy.CURRENT_PHASE_FILE.parent
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / _phase_policy.CURRENT_PHASE_FILE.name).write_text(phase, encoding="utf-8")


def record_flow(root: Path, value: str) -> Path:
    """Write `.sentinel/flow` for an undecided project; a recorded or inferred
    flow is never switched, except that the free edition lets `core` replace
    an enterprise flow inferred only from a deliverables directory."""
    if value not in FLOWS:
        raise ValueError(f"unknown flow {value!r}")
    if value == "enterprise" and _free():
        raise ValueError(f"{PRO_SENTENCE}: record it with `sentinel-state flow core`")
    current = flow(root)
    if current is not None and not (value == "core" and _core_may_replace(root)):
        raise ValueError(f"this project already follows the {current} flow")
    path = Path(root) / FLOW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return path


def upgrade(root: Path, today: str | None = None) -> State:
    """Move a Core project to the Enterprise flow: record the move, drop the
    Core phase marker, and return where the project resumes."""
    root = Path(root)
    if _free():
        raise ValueError(f"{PRO_SENTENCE} only, so this project cannot move to the enterprise "
                         "flow here")
    current = flow(root)
    if current != "core":
        raise ValueError(f"only a Core project can move to the enterprise flow "
                         f"(this one: {current or 'undecided'})")
    path = root / FLOW_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    when = today or datetime.now().date().isoformat()
    path.write_text(f"enterprise\nupgraded-from: core {when}\n", encoding="utf-8")
    if read_marker(root) in STAGES:
        (root / _phase_policy.CURRENT_PHASE_FILE).unlink()
    return derive(root)


# ---------- the project's .gitignore ----------

# What sentinel adds to a project's .gitignore: its per-session runtime files.
# INSTALL.md shows the same block.
GITIGNORE_LINES = (
    "# Sentinel runtime state — per-session, never commit",
    ".sentinel/runtime/audit_log.json",
    ".sentinel/runtime/audit_findings_pending.json",
    ".sentinel/runtime/hook_errors.jsonl",
    ".sentinel/runtime/warden_decisions.jsonl",
    ".sentinel/runtime/current_phase",
    ".sentinel-control/approve.token",
    ".sentinel/runtime/root_cause.token",
    ".sentinel/runtime/phase5_handoff.md",
)


def in_git_work_tree(root: Path) -> bool:
    root = Path(root).resolve()
    return any((folder / ".git").exists() for folder in (root, *root.parents))


def ensure_gitignore(root: Path) -> list[str]:
    """Append to `<root>/.gitignore` the runtime paths it lacks; return them.

    Only inside a git work tree. Patterns are relative to that .gitignore, so a
    root below the git top level works. A path already present counts under
    any header; the header is added once, with the first missing path.
    """
    root = Path(root)
    if not in_git_work_tree(root):
        return []
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = {line.strip() for line in text.splitlines()}
    header, paths = GITIGNORE_LINES[0], GITIGNORE_LINES[1:]
    missing = [p for p in paths if p not in present]
    if not missing:
        return []
    added = ([] if header in present else [header]) + missing
    prefix = "\n" if text and not text.endswith("\n") else ""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(prefix + "\n".join(added) + "\n")
    return missing

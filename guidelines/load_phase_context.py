# load_phase_context.py — the body of guidelines/load_phase_context.sh.
#
# The .sh checks its arguments, exports PHASE, PROJECT_ROOT, GUIDELINES_DIR and
# MANIFEST_PATH, and execs this file. Run it through the .sh, not directly.
import os, sys, re, pathlib, signal

# A reader that closes the pipe early (`| head -1`) ends this script quietly.
if hasattr(signal, "SIGPIPE"):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# NOTE: PyYAML is imported AFTER the mode flow below — modes read no YAML, so
# they keep working even where no YAML parser imports. The phase flow uses the
# system's PyYAML, or else the copy bundled in vendor/.

PHASE          = os.environ["PHASE"]
PROJECT_ROOT   = pathlib.Path(os.environ["PROJECT_ROOT"])
GUIDELINES_DIR = pathlib.Path(os.environ["GUIDELINES_DIR"])
MANIFEST_PATH  = pathlib.Path(os.environ["MANIFEST_PATH"])
DEBUG          = os.environ.get("SENTINEL_DEBUG") == "1"

# Phase → sections to load from each enabled guideline.
# Source of truth: GUIDELINE_TEMPLATE.md §3. Update both together.
PHASE_SECTIONS = {
    "phase1":       [1, 2],
    "phase2":       [1, 2],
    "phase3":       [1, 3],
    "phase35":      [1, 4, 5],
    "phase4":       [1, 3, 4],
    "phase5":       [1, 4, 5],
    "phase55":      [1, 5, 6],
    "phase6":       [1, 6],
    "phase-review": [1, 2, 3, 4, 5, 6],   # adversarial full context
}

# Mode → named guidelines, manifest NOT consulted. Full-file, except agent-phaseN
# section-filters v4 files.
# Ports the raw `cat` blocks that used to live in mode-skill / phase-agent
# preambles: same content, but path resolution is central and a missing file
# dies loudly (exit 3) instead of `cat ... 2>/dev/null` emitting nothing.
MODE_PROFILES = {
    # operational mode skills
    "maintenance":  ["MASTER_WORKFLOW", "MAINTENANCE_GUIDELINE", "CODING_GUIDELINES", "HUMAN_OVERSIGHT_GUIDELINE", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "incident":     ["INCIDENT_MANAGEMENT", "DEVOPS_GUIDELINE", "HUMAN_OVERSIGHT_GUIDELINE", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "sprint":       ["SPRINT_GUIDELINE", "MASTER_WORKFLOW", "HUMAN_OVERSIGHT_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "retro":        ["SPRINT_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "review":       ["REVIEWER_GUIDELINE", "CODING_GUIDELINES", "EVIDENCE_DECISIONS_GUIDELINE"],
    "investigate":  ["ERROR_HANDLING_GUIDELINE", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "ship":         ["DEVOPS_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "cso":          ["SECURITY_TESTING_GUIDELINE", "DATA_GOVERNANCE", "ERROR_HANDLING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    # phase-agent role primers: the profile a phase subagent's preamble loads
    # (agents/sentinel-phaseN-*.md); no phase load runs before it in the subagent
    "agent-phase1":  ["MASTER_WORKFLOW", "PRODUCT_OWNER_GUIDELINE", "DATA_GOVERNANCE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase2":  ["MASTER_WORKFLOW", "BUSINESS_ANALYST_GUIDELINE", "PRODUCT_OWNER_GUIDELINE", "ERROR_HANDLING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase3":  ["MASTER_WORKFLOW", "ARCHITECT_GUIDELINE", "HLD_GUIDELINE", "RELIABILITY_TIER_GUIDELINE", "DATA_GOVERNANCE", "API_DESIGN_GUIDELINE", "EVENT_DRIVEN_ARCHITECTURE_GUIDELINE", "OBSERVABILITY_GUIDELINE", "SECURITY_TESTING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase4":  ["MASTER_WORKFLOW", "LLD_GUIDELINE", "HLD_GUIDELINE", "API_DESIGN_GUIDELINE", "DATABASE_GUIDELINE", "ERROR_HANDLING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase5":  ["MASTER_WORKFLOW", "DEVELOPER_GUIDELINE", "CODING_GUIDELINES_COMMON", "ERROR_HANDLING_GUIDELINE", "OBSERVABILITY_GUIDELINE", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase55": ["MASTER_WORKFLOW", "TESTER_GUIDELINE", "CODING_GUIDELINES", "SECURITY_TESTING_GUIDELINE", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
    "agent-phase6":  ["MASTER_WORKFLOW", "REVIEWER_GUIDELINE", "DEVOPS_GUIDELINE", "CODING_GUIDELINES", "DEBUGGING_GUIDELINE", "EVIDENCE_DECISIONS_GUIDELINE"],
}

BUCKETS = ["core", "domain", "stack", "compliance"]

# Core flow stage → its essentials texts, whole. Names resolve only in
# guidelines/essentials/ (not a manifest bucket), so no bucket file can stand
# in for a Core text; no manifest, no YAML, no layers.
ESSENTIALS = "essentials"
CORE_PROFILES = {
    "define":      ["CORE_WORKFLOW", "DEFINE_GUIDELINE"],
    "design":      ["CORE_WORKFLOW", "DESIGN_GUIDELINE"],
    "build":       ["CORE_WORKFLOW", "BUILD_GUIDELINE"],
    "release":     ["CORE_WORKFLOW", "RELEASE_GUIDELINE"],
    "core-review": ["CORE_WORKFLOW", "DEFINE_GUIDELINE", "DESIGN_GUIDELINE", "BUILD_GUIDELINE", "RELEASE_GUIDELINE"],
}
# Helper mode → its essentials texts, used instead of its MODE_PROFILES entry
# when the project's flow is `core` or the plugin has no guidelines/core/
# (the free edition). Like CORE_PROFILES: no manifest, no YAML, no layers.
CORE_HELPER_PROFILES = {
    "maintenance": ["CORE_WORKFLOW", "CORE_MAINTENANCE", "CORE_DEBUGGING"],
    "review":      ["CORE_REVIEW"],
    "investigate": ["CORE_DEBUGGING"],
    "ship":        ["CORE_SHIP"],
    "retro":       ["CORE_RETRO"],
}


def helper_uses_essentials():
    """True when a helper mode loads its CORE_HELPER_PROFILES entry."""
    if PHASE not in CORE_HELPER_PROFILES:
        return False
    if not (GUIDELINES_DIR / "core").is_dir():
        return True
    try:
        sys.path.insert(0, str(GUIDELINES_DIR.parent / "hooks"))
        import _project_state
        return _project_state.flow(_project_state.find_root(PROJECT_ROOT)) == "core"
    except Exception:
        return False   # the enterprise profile, as before

# -------- validation --------

def die(code, msg):
    print(f"SENTINEL MANIFEST ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def debug(msg):
    if DEBUG:
        print(f"[debug] {msg}", file=sys.stderr)

# Single entry points (no manifest, no YAML):
#   guideline:<bucket>/<NAME>[:<N>]   one guideline with its overlays
#   list[:<bucket>]                   the names a manifest can enable
SINGLE_GUIDELINE = None   # (bucket, name, line limit or None)
LIST_BUCKETS = None       # the buckets to list

if PHASE.startswith("guideline:"):
    target, has_limit, limit_text = PHASE[len("guideline:"):].partition(":")
    bucket, _, name = target.partition("/")
    if bucket not in BUCKETS:
        die(2, f"guideline: '{bucket}' is not a bucket ({', '.join(BUCKETS)}); "
               f"the form is guideline:<bucket>/<NAME>[:<N>]")
    if not name or "/" in name or name.startswith("."):
        die(2, f"guideline: '{target}' is not <bucket>/<NAME>")
    limit = None
    if has_limit:
        if not re.fullmatch(r"[1-9][0-9]{0,8}", limit_text):
            shown = limit_text if len(limit_text) <= 20 else limit_text[:20] + "…"
            die(2, f"guideline: line limit '{shown}' is not a positive integer of at most nine digits")
        limit = int(limit_text)
    SINGLE_GUIDELINE = (bucket, name, limit)
elif PHASE == "list" or PHASE.startswith("list:"):
    only = PHASE[len("list:"):] if PHASE.startswith("list:") else None
    if only is not None and only not in BUCKETS:
        die(2, f"list: '{only}' is not a bucket ({', '.join(BUCKETS)})")
    LIST_BUCKETS = BUCKETS if only is None else [only]
elif PHASE not in PHASE_SECTIONS and PHASE not in MODE_PROFILES and PHASE not in CORE_PROFILES:
    die(2, f"unknown phase/mode '{PHASE}'. "
           f"Phases: {sorted(PHASE_SECTIONS)}  Modes: {sorted(MODE_PROFILES)}  "
           f"Core: {sorted(CORE_PROFILES)}  "
           f"Single: guideline:<bucket>/<NAME>[:<N>], list[:<bucket>]")

# -------- section extraction (no YAML; shared by mode and phase flow) --------

# A file is v4 (section-filterable) iff it contains `## §1.` at column 0.
# Otherwise treat as v0 legacy and emit full body.
SECTION_HEADER_RE = re.compile(r'^## §(\d+)\.\s', re.MULTILINE)

def is_v4(body):
    return bool(SECTION_HEADER_RE.search(body))

FENCE_RE = re.compile(r'(`{3,}|~{3,})')

def scan_markdown(text):
    """Single pass over `text`. Returns (first_h2_offset, ends_inside_fence).

    `first_h2_offset` is the offset of the first line beginning with `## ` that is
    NOT inside a fenced code block, or None. `ends_inside_fence` is True if the
    text finishes with a fence still open.

    Fence awareness is the whole point. Guidelines embed markdown templates in
    fenced blocks, and those templates legitimately contain `##` headings — see
    core/DATA_GOVERNANCE.md §2.3, whose template contains `## Data Classification
    Record`. A naive `^## ` search treats that as the start of the next section
    and silently truncates, which is exactly the defect this replaced (§2.4
    masking patterns and §2.5 data-rights surface never reached any phase agent
    in any project, with no error).

    Per CommonMark a fence may be indented up to three spaces and closes only on
    the same marker character.
    """
    offset = 0
    first_h2 = None
    fence_char = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip(" ")
        indented_ok = (len(line) - len(stripped)) <= 3
        fence_match = FENCE_RE.match(stripped) if indented_ok else None
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence_char is None:
                fence_char = marker
            elif marker == fence_char:
                fence_char = None
        elif fence_char is None and first_h2 is None and stripped.startswith("## ") and indented_ok:
            first_h2 = offset
        offset += len(line)
    return first_h2, fence_char is not None

def extract_section(body, n):
    """Return text from `## §N. ...` up to the next `## ` header (exclusive),
    ignoring `## ` lines that live inside fenced code blocks."""
    start_match = re.search(rf'^## §{n}\.\s', body, re.MULTILINE)
    if not start_match:
        return None
    start = start_match.start()
    tail = body[start + 1:]   # skip the leading `#` to not match itself
    rel_h2, _ = scan_markdown(tail)
    end = (start + 1 + rel_h2) if rel_h2 is not None else len(body)
    section = body[start:end].rstrip() + "\n"

    # Backstop. A correctly extracted section can never end with a fence still
    # open, so an unbalanced fence proves the slice was cut mid-block. Fixing the
    # fence scan removes the known cause; this makes any remaining cause LOUD
    # rather than silent — the failure mode that let the original defect survive
    # ten phase-review rounds was that it produced no signal at all.
    _, truncated = scan_markdown(section)
    if truncated:
        msg = (f"SENTINEL LOADER: §{n} ends inside an unclosed code fence — the "
               f"section was truncated and the content below is INCOMPLETE.")
        print(f"\n> ⚠️ **{msg}**\n")        # the agent reads stdout
        print(f"WARNING: {msg}", file=sys.stderr)   # the human reads stderr
    return section

# -------- guideline layers: user and project --------
# No YAML in this part: the mode flow runs it. Lowest to highest: the plugin's
# guidelines/, <user dir>/guidelines/, <project>/docs/01_product/guidelines/.
# A layer file is an added guideline (<bucket>/<NAME>.md, a name no lower layer
# has) or an overlay (<bucket>/<NAME>.overlay.md) for a guideline a lower layer
# has in that bucket. Contract: MANIFEST_SCHEMA.md §10.
#
# Nothing here may raise on a layer's content: a phase load reports a problem
# as a violation, a mode load skips the file and goes on.

OVERLAY_SUFFIX = ".overlay.md"
# ASCII digits, no leading zero; the heading may end right after the dot.
SECTION_HEADING_RE = re.compile(r'^## §([1-9][0-9]*)\.(?:\s|$)')

def frontmatter_split(text):
    """(block, rest) when `text` opens with front matter, else None.

    Front matter: a first line that is exactly `---`, then lines none of which
    is blank, then a line that is exactly `---`. A horizontal rule at the top
    of a file, or a closer mistyped as `----`, leaves the text whole: nothing
    is cut that the author did not mark as front matter.
    """
    lines = text.split("\n")
    if lines[0].rstrip("\r") != "---":
        return None
    for index in range(1, len(lines)):
        line = lines[index].rstrip("\r")
        if line == "---":
            if index == 1:
                return None
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:]).lstrip("\n")
        if not line.strip():
            return None
    return None

def strip_frontmatter_text(text):
    split = frontmatter_split(text)
    return text if split is None else split[1]

def layer_body(text):
    """An overlay's text without front matter; a front-matter block that holds
    a `## ` line is the overlay's content, not front matter."""
    split = frontmatter_split(text)
    if split is None or any(line.startswith("## ") for line in split[0].split("\n")):
        return text
    return split[1]

def open_fence(text):
    """The marker of a code fence `text` leaves open, or None."""
    marker = None
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if (len(line) - len(stripped)) > 3:
            continue
        match = FENCE_RE.match(stripped)
        if not match:
            continue
        if marker is None:
            marker = match.group(1)
        elif match.group(1)[0] == marker[0]:
            marker = None
    return marker

def printable(name):
    """A file name as it can be written to stdout and stderr."""
    return name.encode("utf-8", "backslashreplace").decode("utf-8")

def h2_headings(text):
    """(offset, line) of every `## ` heading outside a fenced code block.
    Lines end at a newline only, as `^` does in the section regex."""
    found, offset, fence_char = [], 0, None
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        stripped = line.lstrip(" ")
        indented_ok = (len(line) - len(stripped)) <= 3
        fence_match = FENCE_RE.match(stripped) if indented_ok else None
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence_char is None:
                fence_char = marker
            elif marker == fence_char:
                fence_char = None
        elif fence_char is None and indented_ok and stripped.startswith("## "):
            found.append((offset, line))
        offset += len(raw) + 1
    return found

def section_numbers(text):
    numbers = []
    for _, line in h2_headings(text):
        match = SECTION_HEADING_RE.match(line)
        if match:
            numbers.append(int(match.group(1)))
    return numbers

def user_dir():
    raw = os.environ.get("SENTINEL_USER_DIR", "")
    if raw:
        return pathlib.Path(raw)
    try:
        return pathlib.Path.home() / ".sentinel"
    except (RuntimeError, KeyError):
        return None   # no home directory: no user layer

def cut_overlay(body, target_body):
    """Cut an overlay for a sectioned target into its sections.

    Returns (sections, problem): {number: text} in document order, or the
    reason it cannot be taken. The sections are the slices between the `## `
    headings found by one scan, so together they are the whole body: no text
    can fall between them.
    """
    heads = h2_headings(body)
    numbers = section_numbers(body)
    if not numbers:
        return None, "its target is sectioned and it has no `## §N.` heading"
    if body[:heads[0][0]].strip():
        return None, "it has text before its first section heading"
    if len(numbers) != len(heads):
        return None, "it has a `## ` heading that is not a `## §N.` heading"
    if len(set(numbers)) != len(numbers):
        return None, "a section number appears twice"
    missing = sorted(set(numbers) - set(section_numbers(target_body)))
    if missing:
        return None, f"its target has no §{missing[0]}"
    bounds = [offset for offset, _ in heads] + [len(body)]
    return {n: body[bounds[i]:bounds[i + 1]] for i, n in enumerate(numbers)}, None

LAYER_TEXT = {}   # path of an added guideline -> its text, read once by the scan

def read_guideline(path):
    text = LAYER_TEXT.get(path)
    return path.read_text(encoding="utf-8") if text is None else text

def scan_layers():
    """Read the layer directories once.

    Returns (added, overlays, violations):
      added       {(bucket, name): (layer, path)}
      overlays    {(bucket, name): [{"layer", "rel", "body", "sections"}, ...]} in layer order
      violations  ["[<layer> layer] <path in the layer>: <why>", ...]
    A file named in a violation is in neither `added` nor `overlays`.
    """
    roots = []
    home = user_dir()
    if home is not None:
        roots.append(("user", home / "guidelines"))
    roots.append(("project", PROJECT_ROOT / "docs" / "01_product" / "guidelines"))

    def is_dir(path):
        try:
            return path.is_dir()
        except OSError:
            return False

    def listing(path):
        try:
            return sorted(path.iterdir(), key=lambda entry: entry.name)
        except OSError:
            return None

    known = {}   # guideline name -> (bucket, path, where it is from)
    for bucket in BUCKETS:
        bucket_dir = GUIDELINES_DIR / bucket
        if bucket_dir.is_dir():
            for path in bucket_dir.glob("*.md"):
                known[path.stem] = (bucket, path, "the plugin")
    added, overlays, violations = {}, {}, []

    for layer, root in roots:
        if not is_dir(root):
            continue

        def bad(rel, why, layer=layer):
            violations.append(f"[{layer} layer] {printable(rel)}: {why}")

        def skipped(name):
            return name.startswith(".") or name == "README.md"

        def utf8_name(name, rel):
            try:
                name.encode("utf-8")
                return True
            except UnicodeEncodeError:
                bad(rel, "its name is not UTF-8")
                return False

        top = listing(root)
        if top is None:
            bad("guidelines", "the layer directory cannot be listed")
            continue
        for entry in top:
            if skipped(entry.name) or not utf8_name(entry.name, entry.name):
                continue
            if not (entry.name in BUCKETS and is_dir(entry)):
                bad(entry.name, "not one of the bucket directories " + ", ".join(BUCKETS))

        guidelines, pending = {}, []
        for bucket in BUCKETS:
            bucket_dir = root / bucket
            if not is_dir(bucket_dir):
                continue
            entries = listing(bucket_dir)
            if entries is None:
                bad(bucket, "the bucket directory cannot be listed")
                continue
            for entry in entries:
                rel = f"{bucket}/{entry.name}"
                if skipped(entry.name) or not utf8_name(entry.name, rel):
                    continue
                try:
                    regular = entry.is_file()
                except OSError:
                    regular = False
                if not regular or not entry.name.endswith(".md"):
                    bad(rel, "not a regular .md file")
                    continue
                try:
                    text = entry.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeDecodeError):
                    bad(rel, "cannot be read as UTF-8 text")
                    continue
                if entry.name.endswith(OVERLAY_SUFFIX):
                    pending.append((bucket, entry.name[:-len(OVERLAY_SUFFIX)], rel, text))
                else:
                    guidelines.setdefault(entry.stem, []).append((bucket, entry, rel, text))

        new = {}
        for name, files in guidelines.items():
            if name in known:
                known_bucket, _, where = known[name]
                for _, _, rel, _ in files:
                    bad(rel, f"{where} already has a guideline named {name} "
                             f"({known_bucket}/{name}.md); add to it with {name}{OVERLAY_SUFFIX}")
            elif len(files) > 1:
                for _, _, rel, _ in files:
                    bad(rel, f"{name} is in more than one bucket of this layer")
            else:
                bucket, path, _, text = files[0]
                new[name] = (bucket, path, f"the {layer} layer")
                added[(bucket, name)] = (layer, path)
                LAYER_TEXT[path] = text

        for bucket, name, rel, text in pending:
            target = known.get(name)
            if target is None or target[0] != bucket:
                bad(rel, f"no guideline {bucket}/{name}.md in the plugin or a lower layer")
                continue
            try:
                target_body = strip_frontmatter_text(read_guideline(target[1]))
            except (OSError, UnicodeDecodeError):
                bad(rel, f"its target {bucket}/{name}.md cannot be read")
                continue
            body = layer_body(text)
            sections = {}
            if is_v4(target_body):
                sections, problem = cut_overlay(body, target_body)
                if problem:
                    bad(rel, problem)
                    continue
            overlays.setdefault((bucket, name), []).append(
                {"layer": layer, "rel": rel, "body": body, "sections": sections})
        known.update(new)   # an overlay targets a lower layer, never its own
    return added, overlays, violations

LAYER_ADDED, LAYER_OVERLAYS, LAYER_VIOLATIONS = scan_layers()

def overlays_printed(bucket, name, sectioned, numbers):
    """The overlays of a guideline that print at least one block in this load.
    `numbers`: the section numbers printed one by one, or None for a whole print."""
    found = LAYER_OVERLAYS.get((bucket, name), [])
    if not sectioned or numbers is None:
        return found
    return [ov for ov in found if any(n in ov["sections"] for n in numbers)]

def emit_overlay_sections(bucket, name, numbers, separator):
    """After a target's section(s): each overlay's sections among `numbers`
    (None: all of them, in number order), in layer order."""
    for ov in LAYER_OVERLAYS.get((bucket, name), []):
        for n in (sorted(ov["sections"]) if numbers is None else numbers):
            if n in ov["sections"]:
                separator(f"[{ov['layer']} layer] {ov['rel']} — §{n}")
                print(ov["sections"][n].rstrip() + "\n")

def emit_overlay_bodies(bucket, name, separator):
    """After an unsectioned target's body: each overlay's body, in layer order."""
    for ov in LAYER_OVERLAYS.get((bucket, name), []):
        separator(f"[{ov['layer']} layer] {ov['rel']} — full")
        print(ov["body"].rstrip() + "\n")

# -------- single entry points (no manifest; layers apply; never stop on a layer problem) --------

if SINGLE_GUIDELINE is not None or LIST_BUCKETS is not None:
    if not GUIDELINES_DIR.is_dir():
        die(4, f"the plugin's guidelines directory is missing at {GUIDELINES_DIR}")
    for violation in LAYER_VIOLATIONS:
        print(f"SENTINEL LAYER WARNING: {violation} — skipped", file=sys.stderr)

if LIST_BUCKETS is not None:
    layer_rank = {"user": 0, "project": 1}
    for bucket in LIST_BUCKETS:
        bucket_dir = GUIDELINES_DIR / bucket
        if bucket_dir.is_dir():
            for name in sorted(path.stem for path in bucket_dir.glob("*.md") if path.stem != "README"):
                print(f"{bucket}/{name}")
        added_here = sorted((layer_rank[layer], name, layer)
                            for (b, name), (layer, _) in LAYER_ADDED.items() if b == bucket)
        for _, name, layer in added_here:
            print(f"{bucket}/{name} [{layer} layer]")
    sys.exit(0)

if SINGLE_GUIDELINE is not None:
    bucket, name, limit = SINGLE_GUIDELINE

    def banner(title):
        print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n")

    if name == "README":
        die(3, f"guideline: {bucket}/README.md is not a guideline")
    path, layer = GUIDELINES_DIR / bucket / f"{name}.md", None
    if not path.is_file():
        layered = LAYER_ADDED.get((bucket, name))
        if layered is None:
            die(3, f"guideline: no {bucket}/{name}.md in the plugin or a layer")
        layer, path = layered
    try:
        body = strip_frontmatter_text(read_guideline(path))
    except (OSError, UnicodeDecodeError):
        die(3, f"guideline: {bucket}/{name}.md cannot be read as UTF-8 text")

    title = (f"[{layer} layer] {bucket}/{name}.md — single guideline" if layer
             else f"[{bucket}/{name}] single guideline")
    if limit:
        title += f" — first {limit} lines"
    banner(title)
    for violation in LAYER_VIOLATIONS:
        print(f"Layer skipped: {violation}")
    shown = "\n".join(body.split("\n")[:limit]) if limit else body
    print(shown.rstrip() + "\n")
    if limit and open_fence(shown):
        print(open_fence(shown) + "\n")   # the cut fell inside a code fence: close it
    # The overlays are never cut: under a line limit they are the text that must arrive.
    if is_v4(body):
        emit_overlay_sections(bucket, name, None, banner)
    else:
        emit_overlay_bodies(bucket, name, banner)
    sys.exit(0)

# -------- Core flow (manifest NOT consulted; the essentials texts only) --------

if PHASE in CORE_PROFILES or helper_uses_essentials():
    def _core_sep(title):
        print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n")

    folder = GUIDELINES_DIR / ESSENTIALS
    profile = CORE_PROFILES.get(PHASE) or CORE_HELPER_PROFILES[PHASE]
    paths = [(name, folder / f"{name}.md") for name in profile]
    missing = [f"Core profile '{PHASE}': '{name}' has no file in {folder}"
               for name, path in paths if not path.is_file()]
    if missing:
        die(3, "validation failed:\n  - " + "\n  - ".join(missing))
    _core_sep(f"SENTINEL core-context — {PHASE} — {len(paths)} guideline(s)")
    print(f"Project: {PROJECT_ROOT}")
    for name, path in paths:
        _core_sep(f"[{ESSENTIALS}/{name}] full load (Core profile)")
        print(strip_frontmatter_text(path.read_text(encoding="utf-8")).rstrip() + "\n")
    _core_sep("END core-context")
    sys.exit(0)

# -------- mode flow (manifest NOT consulted; named profiles) --------

if PHASE in MODE_PROFILES:
    def _sep(title):
        print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n")

    entries, missing = [], []
    for name in MODE_PROFILES[PHASE]:
        for bucket in BUCKETS:
            candidate = GUIDELINES_DIR / bucket / f"{name}.md"
            if candidate.is_file():
                entries.append((bucket, name, candidate))
                break
        else:
            missing.append(f"mode '{PHASE}': '{name}' has no file in any bucket under {GUIDELINES_DIR}")
    if missing:
        die(3, "validation failed:\n  - " + "\n  - ".join(missing))

    # agent-phaseN loads only phaseN's sections of v4 files; non-v4 load full.
    agent_sections = PHASE_SECTIONS.get(PHASE[len("agent-"):]) if PHASE.startswith("agent-") else None

    # A layer problem never stops a mode: the file is skipped and reported.
    for violation in LAYER_VIOLATIONS:
        print(f"SENTINEL LAYER WARNING: {violation} — skipped", file=sys.stderr)

    loaded = [(bucket, name, strip_frontmatter_text(path.read_text(encoding="utf-8")))
              for bucket, name, path in entries]

    _sep(f"SENTINEL mode-context — {PHASE} — {len(entries)} guideline(s)")
    print(f"Project: {PROJECT_ROOT}")
    for bucket, name, body in loaded:
        by_section = bool(agent_sections) and is_v4(body)
        for ov in overlays_printed(bucket, name, is_v4(body), agent_sections if by_section else None):
            print(f"Layer: [{ov['layer']}] {ov['rel']}")
    for violation in LAYER_VIOLATIONS:
        print(f"Layer skipped: {violation}")
    for bucket, name, body in loaded:
        if agent_sections and is_v4(body):
            _sep(f"[{bucket}/{name}] v4 — sections §{agent_sections} (mode profile)")
            for n in agent_sections:
                sec = extract_section(body, n)
                print(sec if sec else f"_(§{n} not present in this guideline — skipped)_\n")
                emit_overlay_sections(bucket, name, [n], _sep)
        else:
            _sep(f"[{bucket}/{name}] full load (mode profile)")
            print(body.rstrip() + "\n")
            if is_v4(body):
                emit_overlay_sections(bucket, name, None, _sep)
            else:
                emit_overlay_bodies(bucket, name, _sep)
    _sep("END mode-context")
    sys.exit(0)

# -------- phase flow (manifest-driven; needs PyYAML from here on: the system's or vendor/'s) --------

try:
    import yaml
except ImportError:
    # No system PyYAML: use the copy bundled two folders above this file.
    sys.modules.pop("yaml", None)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "vendor"))
    try:
        import yaml
    except ImportError:
        print("FATAL: PyYAML not installed, and the copy bundled in vendor/ is missing too.",
              file=sys.stderr)
        sys.exit(3)

if not MANIFEST_PATH.is_file():
    die(3, f"manifest missing at {MANIFEST_PATH}\n"
           f"  → run /sentinel:phase1 to bootstrap, or create the file per "
           f"{GUIDELINES_DIR.name}/MANIFEST_SCHEMA.md §8.")

try:
    raw_text = MANIFEST_PATH.read_text(encoding="utf-8")
    manifest = yaml.safe_load(raw_text) or {}
except yaml.YAMLError as e:
    die(3, f"manifest malformed: {e}")

if not isinstance(manifest, dict):
    die(3, "manifest root must be a mapping (system_tier + 4 buckets: core/domain/stack/compliance)")

# Pre-scan: collect inline-comment reasons for bare-string disabled entries.
# Format tolerated:  "  - FOO            # reason: \"...\""
INLINE_REASON_RE = re.compile(
    r'^\s*-\s+([A-Z][A-Z0-9_]*)\s*#\s*reason\s*:\s*["\']?(.+?)["\']?\s*$'
)
inline_reasons = {}
for line in raw_text.splitlines():
    m = INLINE_REASON_RE.match(line)
    if m:
        inline_reasons[m.group(1)] = m.group(2).rstrip('"\'')

# Pre-scan: capture inline comment on the bare-string `system_tier:` line, if any.
TIER_INLINE_RE = re.compile(
    r'^\s*system_tier\s*:\s*(T[1-4])\s*(?:#\s*(.+?))?\s*$'
)
tier_inline_comment = None
for line in raw_text.splitlines():
    m = TIER_INLINE_RE.match(line)
    if m and m.group(2):
        tier_inline_comment = m.group(2).rstrip('"\' ')
        break

missing_buckets = [b for b in BUCKETS if b not in manifest]
if missing_buckets:
    die(3, f"manifest missing required top-level buckets: {missing_buckets}")

# -------- system_tier validation --------

VALID_TIERS = {"T1", "T2", "T3", "T4"}
JUSTIFICATION_PATTERNS = re.compile(r'(SRS §|VISION §|ADR-\d+)')

raw_tier = manifest.get("system_tier")
if raw_tier is None:
    die(3, "manifest missing required top-level key: system_tier "
           "(one of T1/T2/T3/T4 — see MANIFEST_SCHEMA §3.1 + RELIABILITY_TIER_GUIDELINE §2.1)")

if isinstance(raw_tier, str):
    tier_level = raw_tier
    tier_justification = tier_inline_comment
elif isinstance(raw_tier, dict):
    tier_level = raw_tier.get("level")
    tier_justification = raw_tier.get("justification_ref")
else:
    die(3, "system_tier must be a string (T1/T2/T3/T4) or a mapping "
           "with 'level:' and 'justification_ref:' fields")

if tier_level not in VALID_TIERS:
    die(3, f"system_tier value '{tier_level}' not one of {sorted(VALID_TIERS)}")

if tier_level in {"T3", "T4"}:
    if not tier_justification or not JUSTIFICATION_PATTERNS.search(tier_justification):
        die(3, f"system_tier {tier_level} requires justification reference "
               f"(SRS §, VISION §, or ADR-NNN). Use mapping-form 'justification_ref:' "
               f"or a bare-string inline comment that cites one of these anchors.")

# -------- gate_policy validation (ADR-001; optional, default 'human') --------

VALID_GATE_POLICIES = {"human", "auto-with-escalation"}
raw_gate_policy = manifest.get("gate_policy", "human")
if not isinstance(raw_gate_policy, str):
    die(3, "gate_policy must be a string ('human' or 'auto-with-escalation')")
gate_policy = raw_gate_policy.strip()
if gate_policy not in VALID_GATE_POLICIES:
    die(3, f"gate_policy value '{gate_policy}' not one of {sorted(VALID_GATE_POLICIES)} "
           f"(see MANIFEST_SCHEMA §3.3 + HUMAN_OVERSIGHT_GUIDELINE §1.4)")

def normalize_entries(raw, bucket, kind):
    """raw is a list (possibly None). Returns list of dicts {name, reason}."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        die(3, f"{bucket}.{kind} must be a list")
    out = []
    for item in raw:
        if isinstance(item, str):
            reason = inline_reasons.get(item)
            out.append({"name": item, "reason": reason})
        elif isinstance(item, dict) and "name" in item:
            out.append({"name": item["name"], "reason": item.get("reason")})
        else:
            die(3, f"{bucket}.{kind} entry invalid: {item!r}")
    return out

resolved = {b: {"enabled": [], "disabled": []} for b in BUCKETS}
errors = list(LAYER_VIOLATIONS)   # a layer problem stops a phase load
for bucket in BUCKETS:
    section = manifest.get(bucket) or {}
    if not isinstance(section, dict):
        die(3, f"bucket '{bucket}' must be a mapping with 'enabled' and optional 'disabled'")
    enabled = normalize_entries(section.get("enabled"), bucket, "enabled")
    disabled = normalize_entries(section.get("disabled"), bucket, "disabled")

    # Validation: reason required on disabled
    for d in disabled:
        if not d["reason"]:
            errors.append(f"{bucket}.disabled['{d['name']}'] missing reason (required)")

    # Validation: disjoint sets
    enabled_names = {e["name"] for e in enabled}
    overlap = enabled_names & {d["name"] for d in disabled}
    if overlap:
        errors.append(f"{bucket}: names in both enabled and disabled: {sorted(overlap)}")

    # Validation: enabled name resolves to an existing file.
    # `disabled:` entries are pure metadata (name + reason) per schema §24
    # and the script's own docstring ("disabled guidelines are never opened").
    # Validating their file existence would force projects to ship stubs for
    # every guideline they have explicitly chosen NOT to use — inverting the
    # exclusion semantic and blocking project-specific disabled entries
    # (e.g. a domain/compliance the sentinel-repo doesn't track stubs for).
    for e in enabled:
        candidate = GUIDELINES_DIR / bucket / f"{e['name']}.md"
        if not candidate.is_file():
            layered = LAYER_ADDED.get((bucket, e["name"]))
            if layered:
                e["layer"], candidate = layered
            else:
                errors.append(f"{bucket}: '{e['name']}' has no file at {candidate}")
        e["path"] = candidate

    resolved[bucket]["enabled"] = enabled
    resolved[bucket]["disabled"] = disabled

if errors:
    msg = "\n  - ".join(errors)
    die(3, f"validation failed:\n  - {msg}")

# -------- frontmatter --------

def split_frontmatter(text):
    """Return (frontmatter_dict, body_text). If no frontmatter, frontmatter={}."""
    split = frontmatter_split(text)
    if split is None:
        return {}, text
    fm_text, body = split
    try:
        fm = yaml.safe_load(fm_text) or {}
    except (yaml.YAMLError, ValueError):   # ValueError: e.g. a date that does not exist
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body

# -------- always-on guidelines (applies_to.always: true) --------
# A guideline whose frontmatter declares `applies_to.always: true` loads in every
# project regardless of manifest membership — reserved for universal disciplines.
# The manifest still governs everything else, and an explicit `disabled:` entry
# OVERRIDES always-on (project sovereignty + the disabled reason stays auditable).
for bucket in BUCKETS:
    bucket_dir = GUIDELINES_DIR / bucket
    candidates = [(path, None) for path in sorted(bucket_dir.glob("*.md"))] if bucket_dir.is_dir() else []
    candidates += [(path, layer) for (b, _), (layer, path) in sorted(LAYER_ADDED.items()) if b == bucket]
    present = {e["name"] for e in resolved[bucket]["enabled"]}
    disabled_names = {d["name"] for d in resolved[bucket]["disabled"]}
    for path, layer in candidates:
        name = path.stem
        if name in present or name in disabled_names:
            continue
        try:
            fm, _ = split_frontmatter(read_guideline(path))
        except (OSError, UnicodeDecodeError):
            continue
        applies = fm.get("applies_to") or {}
        if isinstance(applies, dict) and applies.get("always") is True:
            entry = {"name": name, "reason": "applies_to.always", "path": path}
            if layer:
                entry["layer"] = layer
            resolved[bucket]["enabled"].append(entry)
            present.add(name)
            debug(f"always-on: {bucket}/{name} force-included")

# -------- emission --------

def emit_separator(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n")

sections_wanted = PHASE_SECTIONS[PHASE]
emit_separator(f"SENTINEL phase-context — {PHASE} — sections §{sections_wanted}")
print(f"Project: {PROJECT_ROOT}")
print(f"Manifest: {MANIFEST_PATH}")

# Emit a manifest summary so the human reviewer sees the filter decisions.
emit_separator("MANIFEST SUMMARY")
tier_line = f"system_tier: {tier_level}"
if tier_justification:
    tier_line += f"  ({tier_justification})"
print(tier_line)
print(f"gate_policy: {gate_policy}")
print()
for bucket in BUCKETS:
    en = resolved[bucket]["enabled"]
    dis = resolved[bucket]["disabled"]
    print(f"[{bucket}] enabled: {len(en)}  disabled: {len(dis)}")
    for e in en:
        if e.get("reason") == "applies_to.always":
            print(f"  + {e['name']:<24}  always-on (not in manifest)")
    for d in dis:
        print(f"  — {d['name']:<24}  disabled: {d['reason']}")

# Layer files this load uses (MANIFEST_SCHEMA.md §10); nothing is printed
# when there are none.
layer_lines = []
for bucket in BUCKETS:
    for entry in resolved[bucket]["enabled"]:
        _, entry["body"] = split_frontmatter(read_guideline(entry["path"]))
        if entry.get("layer"):
            layer_lines.append(f"[{entry['layer']}] {bucket}/{entry['name']}.md")
        for ov in overlays_printed(bucket, entry["name"], is_v4(entry["body"]), sections_wanted):
            layer_lines.append(f"[{ov['layer']}] {ov['rel']}")
if layer_lines:
    print()
    print("layers:")
    for line in layer_lines:
        print(f"  + {line}")

# Emit guideline content, in bucket order, in list order within bucket.
for bucket in BUCKETS:
    for entry in resolved[bucket]["enabled"]:
        body = entry["body"]

        if is_v4(body):
            emit_separator(f"[{bucket}/{entry['name']}] v4 — sections §{sections_wanted}")
            for n in sections_wanted:
                sec = extract_section(body, n)
                if sec:
                    print(sec)
                else:
                    print(f"_(§{n} not present in this guideline — skipped)_\n")
                emit_overlay_sections(bucket, entry["name"], [n], emit_separator)
        else:
            emit_separator(f"[{bucket}/{entry['name']}] LEGACY v0 — full-file load")
            print(body.rstrip() + "\n")
            emit_overlay_bodies(bucket, entry["name"], emit_separator)

emit_separator("END phase-context")

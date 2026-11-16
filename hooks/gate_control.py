"""Does a tool call write, move or delete the gate's own control files?

The gate-control-files rules first matched the file names as text. Bash does
not act on text: it removes quotes, expands globs, follows `cd` and
normalises `//` before a path reaches `rm`, and each of those let a call
through (`rm .sentinel/runtime/*.json`, `cd .sentinel/runtime && rm *`,
`rm .sentinel/runtime/forced_rule_'set'`, `rm -rf .sentinel//runtime`,
`find .sentinel -delete`; measured 2026-10-14, when the files lived there).
This resolves each word the way bash would, against the session cwd, and
compares paths.

Best effort: every review round found more (awk programs, expansion
defaults). Where the Claude Code sandbox runs, `bin/sentinel-lock` denies
writes to `.sentinel-control/` at the OS level; this is the fallback.

A control path in a simple command denies unless the command is a known
reader (`cat`, `ls`, `git diff`, ...): a list of writers missed every writer
not on it (`curl -o`, `tar -C`, `python -c`; measured 2026-10-14). A
directory above the control files denies only for verbs that delete, move
or re-permission it. Across commands the path can flow through a pipe into
`xargs` or through a variable, so a control path anywhere in the line
denies a writing command that runs `xargs` or uses an unresolvable word.

Scope: the accidental act. Unresolvable words (variables, command
substitution) count when their text names `.sentinel-control` or a control file.
"""

from __future__ import annotations

import fnmatch
import glob
import os
import re
import shlex
from pathlib import Path
from typing import Iterable

import rule_layers

CONTROL_NAMES = ("destructive_patterns.json", "forced_rule_set", "approve.token")
_PROJECT_DIR = rule_layers.CONTROL_DIR

WRITE_VERBS = frozenset({
    "rm", "rmdir", "unlink", "shred", "truncate", "mv", "cp", "install", "rsync",
    "dd", "touch", "ln", "chmod", "chown", "chgrp", "tee", "checkout", "restore",
})
_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>", ">&", "<>"})
_FIND_ACTIONS = frozenset({
    "-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls",
})
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_UNRESOLVABLE = re.compile(r"[$`]|\{[^}]*(?:,|\.\.)[^}]*\}")
_MAGIC = re.compile(r"[*?\[]")

DIRECT = "direct"      # a control file, or the directory that holds them
ANCESTOR = "ancestor"  # a directory above one (the project root, ~)


def known_paths(cwd: Path, home: Path | None = None, plugin_root: Path | None = None) -> list[str]:
    """Where the control files live for this session, as given and resolved
    (macOS /tmp is /private/tmp)."""
    paths = [os.path.normpath(Path(cwd) / _PROJECT_DIR / n) for n in CONTROL_NAMES]
    for layer, directory in rule_layers._layer_dirs(Path(cwd), plugin_root, home):
        if layer != "project":
            paths.append(os.path.normpath(directory / CONTROL_NAMES[0]))
    return list(dict.fromkeys(paths + [os.path.realpath(p) for p in paths]))


def classify(path: str, known: Iterable[str]) -> str | None:
    """DIRECT, ANCESTOR or None for an absolute path.

    Names compare case-folded: macOS and Windows file systems are case
    insensitive by default, so `.SENTINEL-Control/Forced_Rule_Set` is the
    marker there. An existing path also compares by file identity, which
    sees symlinks and hard links."""
    kinds = {_classify_one(os.path.normpath(path), known)}
    try:
        kinds.add(_classify_one(os.path.realpath(path), known))
        if os.path.exists(path) and _identity(path) in _control_identities(tuple(known)):
            kinds.add(DIRECT)
    except (OSError, ValueError):
        pass
    if DIRECT in kinds:
        return DIRECT
    return ANCESTOR if ANCESTOR in kinds else None


_CONTROL_FOLDED = frozenset(n.casefold() for n in CONTROL_NAMES)
_CONTROL_DIR_FOLDED = _PROJECT_DIR.name.casefold()


def _classify_one(p: str, known: Iterable[str]) -> str | None:
    p = p.casefold()
    parts = Path(p).parts
    if parts and parts[-1] in _CONTROL_FOLDED:
        return DIRECT
    if parts and parts[-1] == _CONTROL_DIR_FOLDED:
        return DIRECT
    prefix = p.rstrip("/") + "/"
    for k in known:
        k = k.casefold()
        if k == p:
            return DIRECT
        if k.startswith(prefix):
            return ANCESTOR
    return None


def _identity(path: str) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_dev, st.st_ino


def _control_identities(known: tuple[str, ...]) -> set[tuple[int, int]]:
    """Existing control files and the directories that hold them."""
    ids: set[tuple[int, int]] = set()
    for k in known:
        for h in (k, os.path.dirname(k)):
            if os.path.basename(h) in (".claude-plugin",):
                continue
            try:
                ids.add(_identity(h))
            except OSError:
                continue
    return ids


_NAMES = re.compile(
    r"(?<![\w-])\.sentinel-control(?![\w-])|(?:%s)(?![\w.-])"
    % "|".join(re.escape(n) for n in CONTROL_NAMES),
    re.IGNORECASE,
)


# `$P.sentinel-control` is `.sentinel-control` when P is empty, and so is
# `${P:-.sen}tinel-control` when P is unset: match every value bash could
# give, innermost `${...}` first
_BRACED = re.compile(r"\$\{(?:[#!]?\w*:?[-=+?]([^{}]*)|[^{}]*)\}")
_SIMPLE = re.compile(r"\$(?:\w+|[@*#?$!-])")


def _values(text: str) -> set[str]:
    out = {text}
    for keep in (False, True):
        v, prev = text, None
        while v != prev:
            prev, v = v, _BRACED.sub(lambda m: (m.group(1) or "") if keep else "", v)
        out.add(_SIMPLE.sub("", v))
    return out


_PROGRAM = re.compile(r"[\s\"'<>{}()=;|&]")  # a word that is code, not a path


def names_control(text: str) -> bool:
    """`text` mentions a control path (not `forced_rule_set_gate.py`)."""
    return any(_NAMES.search(v) for v in _values(text))


_UNKNOWN_DIR = "/\0unknown"  # cwd after a `cd` this cannot resolve


def expand(word: str, cur: str | None, home: str, hidden: bool = False) -> tuple[list[str], bool]:
    """Absolute paths bash would pass for `word`, and whether it is unresolvable.

    `cur` None: the cwd is unknown, so a relative glob is matched against the
    control names alone. `hidden`: `dotglob`/`GLOBIGNORE` make `*` match
    dot files."""
    m = _ASSIGN.match(word)
    if m:
        word = word[m.end():]
    if word == "~" or word.startswith("~/"):
        word = home + word[1:]
    for var, value in (("HOME", home), ("PWD", cur)):
        if value is not None:
            word = word.replace("${%s}" % var, value).replace("$%s" % var, value)
    if not word:
        return [], False
    if "{" in word and "$" not in word and "`" not in word:
        words = _braces(word)
        if len(words) > 1:
            out: list[str] = []
            for w in words:
                paths, unres = expand(w, cur, home, hidden)
                if unres:
                    return [], True
                out += paths
            return out, False
    if _UNRESOLVABLE.search(word):
        return [], True
    path = word if os.path.isabs(word) else os.path.join(cur or _UNKNOWN_DIR, word)
    if not _MAGIC.search(word):
        return [path], False
    # bash reads `[^...]` as `[!...]`; fnmatch reads it as a literal `^`
    path = path.replace("[^", "[!")
    hits = _glob(path, hidden) if cur is not None or os.path.isabs(word) else []
    if hits:
        return hits, False
    directory, pattern = os.path.split(path)
    if _MAGIC.search(directory):
        return [], True
    names = CONTROL_NAMES + (_PROJECT_DIR.name,)
    return [
        os.path.join(directory, n) for n in names
        if fnmatch.fnmatchcase(n, pattern.casefold())
        and (hidden or pattern.startswith(".") or not n.startswith("."))
    ], False


_BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")


def _braces(word: str, limit: int = 64) -> list[str]:
    """Bash brace expansion of comma lists (`.{sentinel,cache}`); sequences
    (`{a..c}`) stay unresolvable."""
    out, todo = [], [word]
    while todo and len(out) + len(todo) <= limit:
        w = todo.pop()
        m = _BRACE.search(w)
        if not m:
            out.append(w)
            continue
        todo += [w[:m.start()] + alt + w[m.end():] for alt in m.group(1).split(",")]
    return out + todo


def _glob(path: str, hidden: bool) -> list[str]:
    if not hidden:
        return glob.glob(path)
    try:
        return glob.glob(path, include_hidden=True)
    except TypeError:  # Python < 3.11
        directory, pattern = os.path.split(path)
        return glob.glob(path) + glob.glob(os.path.join(directory, "." + pattern))


def _words(segment: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(segment, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return None


# Verbs for which a directory above the control files matters: they delete,
# move or re-permission it. `cp x .` and `mv /tmp/f .` only write into it.
# git-clean / git-stash-u remove untracked files under the cwd (measured:
# `git stash -u` took an untracked .sentinel/ with it).
_ANCESTOR_VERBS = frozenset({
    "rm", "rmdir", "shred", "chmod", "chown", "chgrp", "find", "mv", "rsync",
    "git-clean", "git-stash",
})
# Commands that cannot write a file whatever their arguments. Anything else
# naming a control path is treated as writing it. Not here, because they
# write: awk (`print > f`), sed (`w f`), tree -o, yq -i, rg --pre, and
# git diff/log/show --output (measured 2026-10-14).
READERS = frozenset({
    "cat", "head", "tail", "grep", "egrep", "fgrep", "ls", "stat", "wc", "diff", "cmp",
    "md5sum", "sha1sum", "sha256sum", "sha512sum", "shasum", "jq", "test", "[", "[[",
    "echo", "printf", "realpath", "readlink", "dirname", "basename", "mkdir",
    "cd", "pushd", "popd", "true", ":", "du",
})
_GIT_READERS = frozenset({
    "add", "diff", "log", "show", "status", "ls-files", "blame", "cat-file", "check-ignore",
})
_KEYWORDS = frozenset({"!", "if", "then", "elif", "else", "do", "while", "until", "time", "{", "(", "}"})
_KNOWN_COMMANDS = WRITE_VERBS | READERS | {"sed", "perl", "find", "xargs", "git", "python", "python3"}


def command_name(word: str) -> str:
    """`/bin/RM`, `rm.exe` (Git Bash) and `grm` (GNU coreutils on macOS) are rm;
    macOS finds `RM` on its case-insensitive file system."""
    name = os.path.basename(word).casefold()
    if name.endswith(".exe"):
        name = name[:-4]
    if name not in _KNOWN_COMMANDS and name[:1] == "g" and name[1:] in _KNOWN_COMMANDS:
        name = name[1:]
    return name


def _head(words: list[str], names: list[str]) -> int | None:
    """Index of the command word: past keywords, assignments and redirects."""
    i = 0
    while i < len(words):
        w = words[i]
        if w in _REDIRECTS or w in ("<", "<<", "<<<"):
            i += 2
            continue
        if w in _KEYWORDS or _ASSIGN.match(w):
            i += 1
            continue
        return i
    return None


def _reads_only(words: list[str], names: list[str], verbs: set[str]) -> bool:
    h = _head(words, names)
    if h is None:
        return True  # assignments only: the value is checked as a flow
    name = names[h]
    if verbs - {"find"}:
        return False
    if name == "find":
        return "find" not in verbs  # no -delete/-exec/-fprint
    if name == "git":
        sub = next((w for w in words[h + 1:] if not w.startswith("-")), None)
        return sub in _GIT_READERS and not any(w.startswith("--output") for w in words)
    if name in ("python", "python3"):
        # The layer report, as source or as the release package's bytecode.
        return words[h + 1:h + 2] != [] and words[h + 1].endswith(
            ("rule_layers.py", "rule_layers.pyc"))
    return name in READERS


def _git_verb(names: list[str], words: list[str]) -> str | None:
    if "git" not in names:
        return None
    rest = words[names.index("git") + 1:]
    sub = next((w for w in rest if not w.startswith("-")), None)
    flags = [w for w in rest if w.startswith("-")]
    if sub == "clean" and any(
        f == "--force" or (not f.startswith("--") and "f" in f) for f in flags
    ):
        return "git-clean"
    if sub == "stash" and any(
        f in ("--include-untracked", "--all") or (not f.startswith("--") and ("u" in f or "a" in f))
        for f in flags
    ):
        return "git-stash"
    return None


_MAX_CWDS = 16


def _segment(words: list[str], curs: tuple, home: str, known: list[str], hidden: bool):
    """(denies, has direct path, flows, cwds after, nested) for one simple command.

    `curs` holds every cwd the command may run in: a `cd` inside `( )`, a
    pipeline or a `popd` may not persist, so a `cd` adds its target and keeps
    the old cwd (`cd .sentinel && (cd /tmp) && rm -rf runtime`, measured).
    None is a cwd this cannot name."""
    names = [command_name(w) for w in words]
    verbs = {n for n in names if n in WRITE_VERBS}
    git_verb = _git_verb(names, words)
    if git_verb:
        verbs.add(git_verb)
        words = words + ["."]  # it acts on the cwd
    if any(n in ("sed", "perl") for n in names) and any(
        w.startswith("--in-place") or re.match(r"^-[A-Za-z]*i", w) for w in words
    ):
        verbs.add("sed")
    if "find" in names and any(w in _FIND_ACTIONS for w in words):
        verbs.add("find")
    direct = ancestor = redirected = unresolved = False
    nested: list[str] = []
    last = len(words) - 1
    heres = _candidates(curs, known)  # `git -C dir` moves only git
    for i, w in enumerate(words):
        if i > 0 and words[i - 1] == "-C" and git_verb:
            heres = _cd(w, heres, home, keep=False)
            continue
        if w in _REDIRECTS or w in ("(", ")", "{", "}", "<", "<<", "<<<", "|", "&", ";"):
            continue
        if re.search(r"\s|\$\(|`", w):
            nested.append(re.sub(r"\$\(|`|\)", " ; ", w))
        target = i > 0 and words[i - 1] in _REDIRECTS
        if target and words[i - 1] == ">&" and w.isdigit():
            continue
        if w.startswith("-") and not target:
            if "=" not in w:
                continue
            w = w.split("=", 1)[1]
        kinds: set = set()
        for here in heres:
            paths, unres = expand(w, here, home, hidden)
            kinds |= {classify(p, known) for p in paths}
            if unres:
                unresolved = True
                if names_control(w):
                    kinds.add(DIRECT)
        # a program text (`awk '...>".sentinel/x"'`) names a path it is no path
        if DIRECT in kinds or (_PROGRAM.search(w) and names_control(w) and not target):
            direct = True
        if DIRECT in kinds:
            redirected = redirected or target
        if ANCESTOR in kinds and not ("mv" in verbs and i == last):
            ancestor = True
    after = curs
    if names and names[0] in ("cd", "pushd", "popd"):
        args = [w for w in words[1:] if w not in ("--", "-P", "-L", "-e", "-@")]
        if names[0] == "popd" or args[:1] == ["-"]:
            after = curs + (None,)
        elif not args:
            after = curs + (home,)
        else:
            after = _cd(args[0], curs, home, keep=True)
    after = tuple(dict.fromkeys(after))
    if len(after) > _MAX_CWDS:
        after = after[:_MAX_CWDS - 1] + (None,)
    denies = (
        redirected
        or (direct and not _reads_only(words, names, verbs))
        or (bool(verbs & _ANCESTOR_VERBS) and ancestor)
    )
    flows = bool(verbs) and ("xargs" in names or unresolved)
    return denies, direct, flows, after, nested


def _candidates(curs: tuple, known: list[str]) -> tuple:
    """An unknown cwd (None) may be any directory on the way to a control file."""
    if None not in curs:
        return curs
    near = []
    for k in known:
        d = os.path.dirname(k)
        near += [d, os.path.dirname(d), os.path.dirname(os.path.dirname(d))]
    return tuple(dict.fromkeys([c for c in curs if c is not None] + near + [None]))


def _cd(arg: str, curs: tuple, home: str, keep: bool) -> tuple:
    out = list(curs) if keep else []
    for here in curs:
        paths, unres = expand(arg, here, home)
        out.append(os.path.normpath(paths[0]) if paths and not unres else None)
    return tuple(dict.fromkeys(out))


def shell_touches_control(command: str, cwd: Path, split, home: Path | None = None,
                          plugin_root: Path | None = None, root: Path | None = None) -> bool:
    """`split` is the gate's split_shell_commands (heredoc bodies included).
    `cwd` is where the shell runs; `root` the project whose control files count."""
    home_s = str(home or Path.home())
    known = known_paths(root or cwd, home, plugin_root)
    hidden = re.search(r"dotglob|GLOBIGNORE", command) is not None
    return _line(command, (os.path.normpath(str(cwd)),), split, home_s, known, hidden, 0)


def _line(command: str, curs: tuple, split, home: str, known: list[str],
          hidden: bool, depth: int) -> bool:
    line_direct = line_flows = False
    for seg in split(command):
        # `$(...)` and backticks run their text as commands, quoted or not
        if depth < 4 and re.search(r"\$\(|`", seg) and _line(
            re.sub(r"\$\(|`|\)", " ; ", seg), curs, split, home, known, hidden, depth + 1
        ):
            return True
        words = _words(seg.lstrip("({ "))
        if words is None:
            # a quote shlex cannot close: the text decides (deny side)
            if names_control(seg) and re.search(r"(?i)>|\b(?:%s)\b" % "|".join(WRITE_VERBS), seg):
                return True
            continue
        denies, direct, flows, curs, nested = _segment(words, curs, home, known, hidden)
        if denies:
            return True
        # quoted text may be executed (`bash -c`, `ssh`, `$(...)`): read it as commands
        if depth < 4 and any(_line(n, curs, split, home, known, hidden, depth + 1) for n in nested):
            return True
        line_direct = line_direct or direct
        line_flows = line_flows or flows
    return line_direct and line_flows


def path_is_control(file_path: str, cwd: Path, home: Path | None = None,
                    plugin_root: Path | None = None, root: Path | None = None) -> bool:
    """Edit/Write target: a control file itself (through any symlink)."""
    path = file_path if os.path.isabs(file_path) else os.path.join(str(cwd), file_path)
    return classify(path, known_paths(root or cwd, home, plugin_root)) == DIRECT

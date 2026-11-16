#!/usr/bin/env python3
"""Is a pattern match an instruction, or text that merely mentions one?

Destructive patterns opt in per rule with `anchor: "command"`. For those rules
a match inside a closed quoted argument (`git commit -m "never git push --force
origin main"`) is data. Anything else counts as a command wherever it sits:
`eval`, `ssh host`, a leading redirect, a path (`/usr/bin/git`) and wrappers
run what follows them, and a list of transparent prefixes missed each of these
(measured 2026-10-11). An unquoted mention (`echo git push ...`, a heredoc
line) is a false deny.

Quoting is a signal about role, not danger, so it is never stripped wholesale:
a quoted string handed to something that executes it (`bash -c`, `sh -lc`,
`eval`, `ssh host`, `su -c`, `watch`) is re-examined as a command line of its
own, and so is double-quoted text after a `$(` or backtick. A quote that never
closes reads as unquoted: bash refuses one, so the scanner misread it (an
apostrophe in a heredoc line). Rules whose danger lives inside quotes (SQL) do
not carry the anchor.

Threat model: an agent's accidental destructive act, not an adversary — any
regex guard can be obfuscated past. Ambiguity resolves toward "command"
(a false deny, released by approve.token), never toward a silent allow.
Known blind spots: a quoted string that becomes code through an interpreter
(`python -c`, a heredoc calling `subprocess.run`) or through a shell's stdin
(`echo '...' | sh`, `bash <<< '...'`) reads as a mention.

Requirements: Python 3.8+, standard library only.
"""

from __future__ import annotations

import shlex
from typing import List, Optional, Tuple

# Characters that end one command and begin another. `>` and `<` are absent on
# purpose: a redirect continues the same command.
_SEPARATORS = ";&|\n"
_OPENERS = "(`)"

_SHELLS = frozenset({"sh", "bash", "zsh", "ksh", "dash", "fish"})
_RUNS_QUOTED_ARG = frozenset({"eval", "ssh", "watch"})
_RUNS_WITH_C_FLAG = frozenset({"su", "runuser"})


def in_command_position(text: str, start: int) -> bool:
    """False only if `text[start:]` sits in a closed quote nothing executes."""
    if start < 0 or start > len(text):
        return False
    span = _enclosing_quote(text, start)
    if span is None:
        return True
    open_idx, close_idx = span
    inner = text[open_idx + 1:close_idx]
    rel = start - open_idx - 1
    executed = _quote_is_executed(text, open_idx) or (
        text[open_idx] == '"' and _substitution_before(inner, rel)
    )
    return executed and in_command_position(inner, rel)


def match_is_a_command(text: str, match) -> bool:
    """Convenience wrapper for a `re.Match`."""
    return in_command_position(text, match.start())


def opens_ansi_c_quote(text: str, i: int) -> bool:
    """Whether the `'` at `i` opens `$'...'` (backslash escapes honoured inside).

    Only an odd run of unescaped `$` does: `$$'` is the PID variable followed
    by a plain quote, `\\$'` a literal dollar followed by one.
    """
    j = i
    while j > 0 and text[j - 1] == "$":
        j -= 1
    run = i - j
    slashes = 0
    while j - slashes > 0 and text[j - slashes - 1] == "\\":
        slashes += 1
    if slashes % 2:
        run -= 1
    return run % 2 == 1


def _enclosing_quote(text: str, index: int) -> Optional[Tuple[int, int]]:
    """(open, close) of the quoted span containing `index`, else None.

    Tracks single, double and ANSI-C (`$'...'`) quotes, honouring a backslash
    escape everywhere except inside plain single quotes. A quote that never
    closes gives None: bash refuses it, so this scan misread the text.
    """
    quote = None
    open_idx = -1
    i = 0
    while i < index and i < len(text):
        ch = text[i]
        if ch == "\\" and quote != "'":
            i += 2
            continue
        if quote is None and ch in "'\"":
            quote, open_idx = ch, i
            if ch == "'" and opens_ansi_c_quote(text, i):
                quote = "$'"
        elif quote is not None and ch == quote[-1]:
            quote = None
        i += 1
    if quote is None:
        return None
    j = index
    while j < len(text):
        ch = text[j]
        if ch == "\\" and quote != "'":
            j += 2
            continue
        if ch == quote[-1]:
            return open_idx, j
        j += 1
    return None


def _substitution_before(text: str, index: int) -> bool:
    """Whether a `$(` or backtick opens before `index` in double-quoted text.

    Bash runs those inside double quotes: `echo "$(git push -f origin main)"`
    pushes. Whether it closed before `index` is not judged: quotes nested in
    it fooled the depth count (`"$(echo ')'; git push ...)"`, measured), so
    `"$(date) git push ..."` is a false deny.
    """
    i = 0
    while i < index and i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text.startswith("$(", i) or text[i] == "`":
            return True
        i += 1
    return False


def _command_head(text: str, start: int) -> str:
    """Text between the nearest command boundary and `start`."""
    i = start - 1
    while i >= 0:
        ch = text[i]
        if ch in _SEPARATORS or ch in _OPENERS:
            break
        i -= 1
    return text[i + 1:start]


def _tokens(head: str) -> Optional[List[str]]:
    """shlex tokens of `head`; None when it cannot be parsed."""
    try:
        return shlex.split(head, posix=True)
    except ValueError:
        return None


def _quote_is_executed(text: str, open_idx: int) -> bool:
    """Whether the quoted argument opening at `open_idx` is run as a command."""
    tokens = _tokens(_command_head(text, open_idx))
    if tokens is None:
        return True  # unparseable: treat the payload as a command (safe direction)
    names = [t.rsplit("/", 1)[-1] for t in tokens]
    if any(n in _RUNS_QUOTED_ARG for n in names):
        return True
    for k, name in enumerate(names):
        if name in _SHELLS or name in _RUNS_WITH_C_FLAG:
            if any(_is_c_flag(t) for t in tokens[k + 1:]):
                return True
    return False


def _is_c_flag(tok: str) -> bool:
    """`-c`, or a short-flag cluster containing it (`-lc`, `-ec`)."""
    return tok.startswith("-") and not tok.startswith("--") and "c" in tok[1:]

"""Pattern-based audit heuristics for the 3eai-sdlc Stop hook.

Pure functions. No LLM, no network. Each check returns zero or more Finding
objects. The Stop hook (`auto_audit.py`) composes these checks and surfaces
findings to the user; the UserPromptSubmit hook re-injects unresolved findings
into the next turn's context.

Design constraint: false positives are cheaper than false negatives, but only
just. A finding that fires on every response trains the user to ignore the
audit. Each heuristic is tuned conservatively and ships with a list of
counter-patterns that suppress it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Shared cleanup: a described or quoted phrase is not a claim ----------

_FENCE_LINE = re.compile(r"^\s*```")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_QUOTED = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”")


def _blank_fences(text: str) -> str:
    if "```" not in text:
        return text
    lines = text.split("\n")
    inside = False
    for i, line in enumerate(lines):
        if _FENCE_LINE.match(line):
            inside = not inside
            lines[i] = ""
        elif inside:
            lines[i] = ""
    return "\n".join(lines)


def _clean(text: str, keep_code: bool = False) -> str:
    """`text` with fenced blocks blanked, then inline code spans (unless kept)
    and quoted text, each within one line only."""
    text = _blank_fences(text)
    if not keep_code:
        text = _INLINE_CODE.sub(" ", text)
    return _QUOTED.sub(" ", text)


# ---------- Rule 1: Fake completion ----------

_COMPLETION_PHRASES = (
    r"\btamamladım\b",
    r"\byaptım\b",
    r"\bbitirdim\b",
    r"\bhalletti[mk]\b",
    r"\bdone\b",
    r"\bcompleted?\b",
    r"\bfinished\b",
    r"\bimplemented\b",
    r"\bbaşar(ı|i)yla\s+tamamlandı\b",
    r"\btamamlandı\b(?!\s*m[ıi]\b)",  # a question is not a claim
)
_COMPLETION_RE = re.compile("|".join(_COMPLETION_PHRASES), re.IGNORECASE)


def _without_label_lines(text: str) -> str:
    """`text` minus the Done:/Skipped:/Deferred: label lines Rule 2 asks for:
    a required label is not a completion claim."""
    return "\n".join(ln for ln in text.split("\n")
                     if not (_DONE_RE.match(ln) or _SKIPPED_RE.match(ln) or _DEFERRED_RE.match(ln)))


def _claim_text(text: str) -> str:
    """Where a completion phrase counts: outside label lines, code and quotes."""
    return _clean(_without_label_lines(text))


def check_fake_completion(response_text: str, tool_call_count: int) -> list[Finding]:
    text = _claim_text(response_text)
    match = _COMPLETION_RE.search(text)
    if not match:
        return []
    if tool_call_count >= 3:
        return []
    snippet = text[max(0, match.start() - 40): match.end() + 40].strip()
    return [
        Finding(
            rule="fake_completion",
            message=(
                f"Response claims completion but only {tool_call_count} tool "
                "call(s) since the last prompt. Verify the work actually happened."
            ),
            evidence=f"...{snippet}...",
        )
    ]


# ---------- Rule 2: Skip non-disclosure ----------

_LIST_ITEM_RE = re.compile(r"(?m)^\s{0,4}(?:\d+[\.\)]|[-*])\s+\S")
_DONE_RE = re.compile(r"(?im)^\s*(?:#{1,6}\s+)?(?:\*\*|__)?\s*(done|tamamlanan)\s*(?:\*\*|__)?\s*:")
_SKIPPED_RE = re.compile(r"(?im)^\s*(?:#{1,6}\s+)?(?:\*\*|__)?\s*(skipped|atlanan)\s*(?:\*\*|__)?\s*:")
_DEFERRED_RE = re.compile(r"(?im)^\s*(?:#{1,6}\s+)?(?:\*\*|__)?\s*(deferred|ertelenen)\s*(?:\*\*|__)?\s*:")


def check_skip_non_disclosure(response_text: str, work_calls: int) -> list[Finding]:
    """A list of three or more items without the three labels, on a turn that
    did work (`work_calls`: edits, subagents, state-changing commands) or whose
    text claims completion. An explanation is not a delivery."""
    items = _LIST_ITEM_RE.findall(response_text)
    if len(items) < 3:
        return []
    has_done = bool(_DONE_RE.search(response_text))
    has_skipped = bool(_SKIPPED_RE.search(response_text))
    has_deferred = bool(_DEFERRED_RE.search(response_text))
    if has_done and has_skipped and has_deferred:
        return []
    if work_calls < 1 and not _COMPLETION_RE.search(_claim_text(response_text)):
        return []
    missing = []
    if not has_done:
        missing.append("Done")
    if not has_skipped:
        missing.append("Skipped")
    if not has_deferred:
        missing.append("Deferred")
    return [
        Finding(
            rule="skip_non_disclosure",
            message=(
                f"{len(items)}-item delivery without explicit "
                f"{'/'.join(missing)} list(s). Real multi-step work has skips."
            ),
            evidence=f"{len(items)} list items detected",
        )
    ]


# Rule 3 (silent divergence) lives in `_plan_audit.py` (Pro).


# ---------- Rule 4: Singleton recommendation ----------

_RECOMMEND_RE = re.compile(
    r"(?i)\b(?:i\s+recommend|i\s+suggest|tavsiye\s+ediyorum|tavsiye\s+ederim|"
    r"öneriyorum|önerim|recommendation|en\s+iyisi|best\s+option)\b",
)
_ARCH_TERMS_RE = re.compile(
    r"(?i)\b(?:architecture|architectural|mimari|database|framework|"
    r"library|service|microservice|monolith|orm|queue|message\s+broker|"
    r"auth(?:entication|orization)?\s+strategy)\b",
)
_ALTERNATIVE_RE = re.compile(
    r"(?i)\b(?:alternative|alternatif|option\s+[ab12]|seçenek|"
    r"another\s+approach|trade-?off|trade\s+off|or\s+(?:we\s+could|alternatively)|"
    r"on\s+the\s+other\s+hand)\b",
)


def check_singleton_recommendation(response_text: str) -> list[Finding]:
    if not _RECOMMEND_RE.search(response_text):
        return []
    if not _ARCH_TERMS_RE.search(response_text):
        return []
    alternative_count = len(_ALTERNATIVE_RE.findall(response_text))
    if alternative_count >= 2:
        return []
    m = _RECOMMEND_RE.search(response_text)
    snippet = response_text[max(0, m.start() - 30): m.end() + 60].strip()
    return [
        Finding(
            rule="singleton_recommendation",
            message=(
                "Architectural recommendation without ≥2 alternatives and "
                "explicit trade-offs."
            ),
            evidence=f"...{snippet}...",
        )
    ]


# ---------- Rule 5: Unmarked claim ----------

_ASSERTIVE_RE = re.compile(
    r"(?im)^[^\n]{0,160}\b(?:always|never|must|should|typically|generally|"
    r"asla|her\s+zaman|mutlaka|genellikle|tipik\s+olarak)\b[^\n]{0,160}$",
)
_CITED_EXT = r"(?:py|js|ts|md|json|go|rs|java|kt|rb|cs|cpp|c|h)"
_ANCHOR_RE = re.compile(
    r"\[(?:ctx:[^]]+|file:[^]]+|training)\]|"
    r"\b[\w./\\-]+\." + _CITED_EXT + r"\b(?::\d+)?",
)


def check_unmarked_claim(response_text: str) -> list[Finding]:
    matches = list(_ASSERTIVE_RE.finditer(response_text))
    if not matches:
        return []
    findings: list[Finding] = []
    for m in matches[:3]:
        line = m.group(0).strip()
        if _ANCHOR_RE.search(line):
            continue
        findings.append(
            Finding(
                rule="unmarked_claim",
                message="Assertive claim without [ctx:]/[file:]/[training] or file citation.",
                evidence=line[:140],
            )
        )
    return findings


# Rule 7 (scope expansion) lives in `_plan_audit.py` (Pro).


# ---------- Rule 8: Absence claim without a search ----------

# Each phrase has a near miss pinned in tests/test_audit_heuristics.py.
_ABSENCE_PHRASES = (
    r"does(?:n['’]t| not) exist",
    r"no such (?:file|function|method|class|module|key|field|path|directory)",
    r"not found",
    r"nowhere(?!\s+near)",
    r"no (?:callers?|references?|usages?) (?:of|to|for)",
    r"(?:nothing|no one|nobody) (?:calls|uses|reads|writes|imports|references)",
    r"(?:is|are) never (?:called|used|read|written|imported|set)",
    r"(?:is|are)(?:n['’]t| not) (?:used|called|referenced|imported) anywhere",
    r"hiçbir yerde",
    r"(?<!hata )(?<!sorun )(?<!uyarı )bulunamadı",
    r"hiç (?:çağrılmıyor|kullanılmıyor|okunmuyor|yazılmıyor)",
    r"(?:çağıran|kullanan|okuyan|yazan) (?:yok|kimse yok)",
)
_ABSENCE_RE = re.compile(r"(?<!\w)(?:" + "|".join(_ABSENCE_PHRASES) + r")(?!\w)", re.IGNORECASE)


def check_negative_claim(response_text: str, search_calls: int) -> list[Finding]:
    """An absence claim on a turn that ran no search. `search_calls` counts the
    Grep, Glob, search and probe commands since the last human prompt; a
    `[training]` marker is no search."""
    if search_calls > 0:
        return []
    for line in _clean(response_text).split("\n"):
        if _ABSENCE_RE.search(line):
            return [
                Finding(
                    rule="negative_claim",
                    message=(
                        "Absence claim with no search this turn: name the search "
                        "(command, scope, hits) that showed it (EVIDENCE_DECISIONS §1.1)."
                    ),
                    evidence=line.strip()[:140],
                )
            ]
    return []


# ---------- Rule 9: Citation of a file the session never opened ----------

_CITE_MARKER = re.compile(r"\[file:([^\]\s:]+)(?::[^\]]*)?\]")
_CITE_BARE = re.compile(r"(?<![\w/.:\-])(/?(?:[\w.$~\-]+/)*[\w.\-]+\." + _CITED_EXT + r"):\d")
_MAX_CITATIONS = 3


def _seen(path: str, seen_paths: list[str]) -> bool:
    """A cited path counts as seen when a seen string holds its last two
    components: `$G/hooks/x.py` and `cd repo && cat hooks/x.py` both show it."""
    key = "/".join(p for p in path.split("/") if p and p != ".")
    key = "/".join(key.split("/")[-2:])
    return any(key in s for s in seen_paths)


def check_unread_citation(response_text: str, seen_paths: list[str] | None) -> list[Finding]:
    """`[file:P:N]` and bare `P:N` citations of a path no Read, search, edit or
    command of the session touched. Skipped when `seen_paths` is None (a caller
    without a transcript). `[training]` does not excuse a citation."""
    if seen_paths is None:
        return []
    text = _clean(response_text, keep_code=True)
    cited: list[str] = []
    for m in list(_CITE_MARKER.finditer(text)) + list(_CITE_BARE.finditer(text)):
        path = m.group(1)
        if path.startswith("http") or path in cited:
            continue
        cited.append(path)
    findings: list[Finding] = []
    for path in cited:
        if _seen(path, seen_paths):
            continue
        findings.append(
            Finding(
                rule="unread_citation",
                message=f"Cites {path} but no Read, search, edit or command in this session touched it.",
                evidence=path,
            )
        )
        if len(findings) == _MAX_CITATIONS:
            break
    return findings


# ---------- Composition ----------


def _plan_audit():
    """The Pro-only plan checks, or None when absent (the free edition) or broken."""
    try:
        import _plan_audit as module  # noqa: E402
        return module
    except Exception:  # noqa: BLE001
        return None


def run_all_checks(
    response_text: str,
    plan_text: str = "",
    tool_call_count: int = 0,
    current_phase_count: int = 0,
    prior_phase_count: int = 0,
    work_calls: int = 0,
    search_calls: int = 0,
    seen_paths: list[str] | None = None,
) -> list[Finding]:
    """Run every heuristic and return the combined finding list.

    The Stop hook (`auto_audit.py`) supplies the counts from the turn since the
    last human prompt and `seen_paths` from the whole transcript; without
    `seen_paths` the citation check is skipped. `current_phase_count` and
    `prior_phase_count` enable the scope_expansion heuristic. The plan checks
    (silent divergence, scope expansion) run only when `_plan_audit` imports.
    """
    plan_audit = _plan_audit()
    findings: list[Finding] = []
    findings.extend(check_fake_completion(response_text, tool_call_count))
    findings.extend(check_skip_non_disclosure(response_text, work_calls))
    if plan_audit:
        findings.extend(plan_audit.check_silent_divergence(response_text, plan_text))
    findings.extend(check_singleton_recommendation(response_text))
    findings.extend(check_unmarked_claim(response_text))
    if plan_audit:
        findings.extend(plan_audit.check_scope_expansion(current_phase_count, prior_phase_count))
    findings.extend(check_negative_claim(response_text, search_calls))
    findings.extend(check_unread_citation(response_text, seen_paths))
    return findings


def findings_to_dicts(findings: Iterable[Finding]) -> list[dict]:
    return [f.to_dict() for f in findings]

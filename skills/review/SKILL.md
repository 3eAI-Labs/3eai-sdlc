---
name: review
description: |
  Pre-landing PR code review. Analyzes diff for SQL safety, trust boundary violations,
  error handling gaps, security issues, and structural problems. Use when asked to
  "review this PR", "code review", "check my diff", "review before merge".
  Not for: phase deliverable review (/phase-review); Phase 6 release gate (/phase6). (3eai-sdlc)
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

## Preamble (run first)

```bash
E3E_ROOT="$(sentinel-root)" || exit 1
echo "======================================================================"
echo "📝 3EAI-SDLC: CODE REVIEW — Pre-Landing Review"
echo "======================================================================"
echo ""
"$E3E_ROOT/guidelines/load_phase_context.sh" review "$PWD" || exit $?
echo ""

# Auto-detect the language (first match) and load the head of its guideline;
# a layer's overlay for it prints in full after the 80 lines. Skipped in a Core
# project or the free edition, where the review profile is CORE_REVIEW.
case "$(sentinel-state status 2>/dev/null)" in
  *"flow: core"*|*"edition: free"*) SKIP_LANGUAGE=1 ;;
  *) SKIP_LANGUAGE= ;;
esac
if [ -n "$SKIP_LANGUAGE" ]; then
  :
elif [ -f go.mod ] || [ -f go.sum ] || [ -n "$(find . -maxdepth 1 -name '*.go' -type f 2>/dev/null | head -1)" ]; then
  echo "--- DETECTED: Go project ---"
  "$E3E_ROOT/guidelines/load_phase_context.sh" guideline:core/CODING_GUIDELINES_GO:80 "$PWD" || exit $?
elif [ -f pom.xml ] || [ -f build.gradle ] || [ -f build.gradle.kts ]; then
  echo "--- DETECTED: Java project ---"
  "$E3E_ROOT/guidelines/load_phase_context.sh" guideline:core/CODING_GUIDELINES_JAVA:80 "$PWD" || exit $?
elif [ -f requirements.txt ] || [ -f pyproject.toml ] || [ -f setup.py ]; then
  echo "--- DETECTED: Python project ---"
  "$E3E_ROOT/guidelines/load_phase_context.sh" guideline:core/CODING_GUIDELINES_PY:80 "$PWD" || exit $?
fi

echo ""
echo "======================================================================"
echo "🤖 REVIEW MODE ACTIVE. Analyze diff, report findings by severity."
echo "======================================================================"
```

## Code Review Protocol

You are now in **Code Review Mode**. This is a READ-ONLY review — do NOT edit files.

### Step 1: Get the Diff

```bash
# PR diff against base branch
git diff main...HEAD
# Or unstaged changes
git diff
# Or staged changes
git diff --cached
```

### Step 2: Review Checklist

For every changed file, check:

#### 🔴 Critical (Blocks merge)
- [ ] **SQL Injection** — Unsanitized input in queries
- [ ] **Secrets exposure** — API keys, passwords, tokens in code
- [ ] **Auth bypass** — Missing authorization checks on endpoints
- [ ] **Data loss risk** — Destructive operations without confirmation
- [ ] **PII leak** — Sensitive data in logs, error messages, responses

#### 🟡 High (Should fix before merge)
- [ ] **Error handling** — Swallowed exceptions, empty catch blocks
- [ ] **Trust boundary** — Unvalidated external input crossing trust boundaries
- [ ] **Concurrency** — Race conditions, missing locks, shared mutable state
- [ ] **Resource leak** — Unclosed connections, file handles, streams
- [ ] **Missing tests** — New logic without corresponding tests
- [ ] **Name drift** — Function/variable name no longer matches actual behavior (CORE_REVIEW rule 3, or EVIDENCE_DECISIONS_GUIDELINE §5.3: the guideline the preamble printed)
- [ ] **Contract safety** — Inter-module DTO uses typed structure with strict deserialization, not `map`/`dict`/`JsonNode` (CORE_REVIEW rule 3, or CONTRACT_TESTING_GUIDELINE: the guideline the preamble printed)

#### 🟠 Medium (Fix within sprint)
- [ ] **Naming** — Unclear variable/function names
- [ ] **Complexity** — Functions > 30 lines, cyclomatic complexity > 10
- [ ] **Duplication** — Copy-paste code that should be extracted
- [ ] **API contract** — Breaking changes without version bump
- [ ] **Logging** — Missing correlation IDs, insufficient log context

#### 🔵 Low (Informational)
- [ ] **Style** — Inconsistent formatting (should be caught by linter)
- [ ] **Documentation** — Missing/outdated comments
- [ ] **TODO/FIXME** — New TODOs without tracking issue

### Step 2.5: Name Drift & Contract Check (CORE_REVIEW, or EVIDENCE_DECISIONS_GUIDELINE §5.3)

For every function or variable **modified** in the diff:

1. **Read before you claim** (CORE_REVIEW rule 1, or EVIDENCE_DECISIONS_GUIDELINE §5.2): the full function body and its callers, not just the changed lines, and, for code that must run, the entry point. Verify the function name still describes what it actually does after the change.
2. **Check callers** — does the change affect callers' expectations? Is a caller relying on an old behavior the name implied?
3. **Flag name drift** — if the change makes a function do something its name no longer describes, that's a 🟡 finding: "Name drift: `calculateDiscount` now also applies tax surcharge; rename or split."

For every **DTO/struct** modified at a module boundary:
1. Verify strict deserialization is in place (CORE_REVIEW rule 3, or CONTRACT_TESTING_GUIDELINE §4.2)
2. Check if a consumer-driven contract test exists and covers the changed fields
3. If field removed/renamed/type-changed: is this a breaking change? Was a new version created?

### Step 3: Report Format

```
## Code Review Report
PR: [branch name or PR number]
Reviewer: 3eai-sdlc /review
Date: YYYY-MM-DD

### Summary
- Files changed: X
- Lines added: +Y, removed: -Z
- Overall assessment: APPROVE / REQUEST CHANGES / BLOCK

### Findings

🔴 CRITICAL
- [file:path:line] Description → Recommendation

🟡 HIGH
- [file:path:line] Description → Recommendation

🟠 MEDIUM
- [file:path:line] Description → Recommendation

🔵 LOW
- [file:path:line] Description → Recommendation

### Positive Observations
- What's done well in this PR
```

### Rules
- **[BLOCKING]** DO NOT edit any files — review only
- **[REQUIRED]** Every finding must reference file and line number
- **[REQUIRED]** Every finding must have a remediation recommendation
- **[REQUIRED]** Check against the guideline the preamble printed: CORE_REVIEW in a Core project (or the free edition), else CODING_GUIDELINES and the language guideline
- Ask: *"Code review complete. Verdict: [APPROVE/REQUEST CHANGES]. See findings above."*

### Context
The preamble printed one of two profiles:
- In a Core project (or the free edition): CORE_REVIEW — correctness, security basics, errors, tests and readability, against the requirements and the design. No language guideline is loaded.
- Otherwise: REVIEWER_GUIDELINE (review checklist and standards), CODING_GUIDELINES (general coding standards), EVIDENCE_DECISIONS_GUIDELINE (evidence markers, decisions, reading code and claiming code works) and the language guideline (auto-detected).

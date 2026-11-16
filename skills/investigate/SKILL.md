---
name: investigate
description: |
  Systematic root-cause debugging — no fixes without diagnosis. Four phases: reproduce,
  isolate, hypothesize, implement. Iron Law: never apply a fix without understanding the
  root cause first. Use when asked to "debug this", "fix this bug", "why is this broken",
  "investigate", or when behavior diverges from expected. (sentinel)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

## Preamble (run first)

```bash
E3E_ROOT="$(sentinel-root)" || exit 1
echo "======================================================================"
echo "🔍 SENTINEL: INVESTIGATE — Root Cause Debugging"
echo "======================================================================"
echo ""
"$E3E_ROOT/guidelines/load_phase_context.sh" investigate "$PWD" || exit $?
echo ""
echo "======================================================================"
echo "🤖 INVESTIGATION MODE ACTIVE. Follow the debugging guideline printed above."
echo "======================================================================"
```

## Investigation Protocol

You are now in **Investigation Mode**. Apply the debugging guideline the preamble printed: CORE_DEBUGGING, or DEBUGGING_GUIDELINE §5.

When the fix is in and verified, ask: *"Investigation complete. Root cause identified and fixed. Do you approve?"*

### Context
The preamble printed one of two profiles:
- In a Core project (or the free edition): CORE_DEBUGGING — reproduce, isolate, hypothesise, fix the cause, keep the test.
- Otherwise: ERROR_HANDLING_GUIDELINE (error taxonomy, exception hierarchy, recovery patterns), DEBUGGING_GUIDELINE (the root-cause protocol, §5, and its review checklist, §6) and EVIDENCE_DECISIONS_GUIDELINE (evidence markers, decisions, reading code before claiming, §5.1–§5.3).

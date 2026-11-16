---
name: CORE_MAINTENANCE
title: Maintenance — Changing a Running Project
flow: core
---

# Maintenance — Changing a Running Project

## Purpose

Fix a bug or make a small improvement in a project that already works, without breaking what works.

## Rules

### Before changing

1. Say what the change is for in one sentence: the bug as the user sees it, or the improvement and who asked for it.
2. Reproduce a bug before touching the code: a failing test, or a recorded command and its output (CORE_DEBUGGING).
3. Read the code you will change and its callers. Run the existing tests first and note the result, so a later failure is known to be new.
4. A change that alters what a feature does (`F-NN` in `REQUIREMENTS.md`) or how it is built (`DESIGN.md`) is proposed to the user first, and recorded in that document's "Changes" list once agreed (CORE_WORKFLOW rule 4).

### Changing

5. Make the smallest change that solves the problem. Leave unrelated tidy-ups for a change of their own.
6. Follow the existing code's conventions: formatter, linter, naming, folder layout.
7. Add or change a test that fails without the change and passes with it.
8. No secrets in the code, the tests or the repository. Validate outside input and handle errors, as in the rest of the code.

### After changing

9. Run the whole test suite and report the result; never report it as passing without having run it.
10. Record the change where the project keeps them (changelog, `BUILD_REPORT.md` "Known issues", or the commit message): what changed, why, and how it was checked.
11. Tell the user what changed, what was checked, and anything left open.

## Review checklist

- [ ] The problem is stated, and a bug was reproduced before the fix.
- [ ] The change is the smallest that solves it, and nothing unrelated changed.
- [ ] A test covers the change, and the whole suite was run after it.
- [ ] A change to a feature or to the design was agreed with the user and recorded.
- [ ] No secrets; outside input is validated; errors are handled.
- [ ] The change is recorded with its reason.

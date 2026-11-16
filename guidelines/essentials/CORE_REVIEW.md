---
name: CORE_REVIEW
title: Review — Checking a Change Before It Lands
flow: core
---

# Review — Checking a Change Before It Lands

## Purpose

Check a change (a diff, a branch, a pull request) for what would hurt the project once it lands.

## Rules

1. Read the whole change, and for each changed function its full body and its callers, not only the changed lines.
2. Check it against what it is for: the feature (`F-NN`) and its acceptance criteria in `REQUIREMENTS.md`, and `DESIGN.md`. A change that does something they do not ask for is a finding.
3. **Correctness:** wrong logic, missing cases (empty, null, boundaries, errors), and a function whose name no longer says what it does.
4. **Security basics:** secrets in the code or the repository; outside input used without validation (in queries, commands, paths, HTML); missing access checks; sensitive data in logs.
5. **Errors:** an exception swallowed without logging or reporting; a failure the user cannot see.
6. **Tests:** the change has tests that would fail without it; the existing tests still pass, and the result shown is from a run, not assumed.
7. **Readability:** names, size of functions, dead code, and the conventions of the existing code.
8. Report each finding with its place (`file:line`), what is wrong, why it matters and a suggested fix, ordered by severity: must fix before landing, should fix, or a note.
9. Say what was checked and how. Do not report a finding you have not confirmed in the code; mark a suspicion as one.

## Review checklist

- [ ] The whole change and the code around it were read.
- [ ] The change matches the requirements and the design.
- [ ] Correctness, security basics, errors, tests and readability were each checked.
- [ ] Every finding has a place, a reason and a suggested fix, and a severity.
- [ ] The test result reported comes from a run in this session.

---
name: BUILD_GUIDELINE
title: Build — Code and Tests
flow: core
---

# Build — Code and Tests

## Purpose

Write working, tested code that implements the design.

## What to produce

- The code and its tests, in the project's source tree.
- `docs/05_implementation/BUILD_REPORT.md`, with these sections:
  1. **Built**: per feature (`F-NN`), what was built, where (paths), and its tests.
  2. **How to run**: setup, configuration, and the command that starts it.
  3. **How to test**: the command that runs the tests, and the last result (date, passed, failed, skipped).
  4. **Deviations**: where the code differs from `DESIGN.md`, and why.
  5. **Known issues**: what does not work yet.

## Rules

### Working

1. Read `REQUIREMENTS.md` and `DESIGN.md` first. Build in the order the design gives, one feature or component at a time.
2. Work in small steps: write a test for the behaviour, make it pass, then tidy up. Run the tests after each step.
3. Each acceptance criterion has at least one automated test that checks it, or, when it cannot be automated, a manual check written in the build report.
4. Follow the conventions of the language and of the existing code: formatter, linter, naming, folder layout.
5. A change the design did not foresee is made and recorded under Deviations; if it changes a requirement, ask the user first.

### Safety

6. No secrets, keys or passwords in code, tests, logs or the repository; read them from the environment or a secret store.
7. Validate every input from outside (users, files, network), and fail with a clear message, never silently.
8. Handle each error the design names; never swallow an exception without logging or reporting it.
9. Add a dependency only when it is needed, prefer the standard library, and record why.

### Debugging

10. Reproduce a failure before fixing it: a failing test, or a recorded command and its output.
11. Find the cause before changing code, fix the cause rather than the symptom, and keep the test that reproduced it.

### Done

12. The stage is done when every `must` feature is built, the whole test suite passes in a clean run, and the build report is complete.

## Review checklist

- [ ] Every `must` feature is built and has tests.
- [ ] Every acceptance criterion is checked by a test or by a recorded manual check.
- [ ] The test suite passes, and the report shows the last run.
- [ ] No secrets in the code or the repository.
- [ ] Outside input is validated; errors are handled and visible.
- [ ] Deviations from the design are listed with their reasons.
- [ ] The build report says how to run and how to test the project.

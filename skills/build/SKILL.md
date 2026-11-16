---
name: build
description: |
  Sentinel Core, stage 3 of 4 — build a small project (one developer or a small team): code and
  tests per its approved design, then the build report.
  Use after a small project's design is approved. Choose it by the user's words; its first step checks the
  project itself.
  Not for: an enterprise project's walking skeleton (/phase35), implementation from an approved
  LLD (/phase5) or QA phase (/phase55); fixes on a deployed system (/maintenance).
  Triggers: "build my app", "write the code for my small project", "start coding the design". (sentinel)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - Skill
  - AskUserQuestion
  - WebSearch
---

# Build — code and tests (Sentinel Core, stage 3 of 4)

**Stage marker (run first):** it checks that the project follows the Core flow and has reached this stage, and sets the stage. If it exits non-zero, stop this skill and follow its output.

```bash
sentinel-state enter build || exit $?
```

## Preamble (run after the stage marker)

```bash
"$(sentinel-root)/guidelines/load_phase_context.sh" build "$PWD" || exit $?
```

Follow the loaded CORE_WORKFLOW and BUILD_GUIDELINE.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md` and `docs/03_architecture/DESIGN.md`.
2. Build in the design's order, one feature or component at a time: a test, the code that passes it, a run of the tests.
3. When a test run fails, find the cause before editing further (BUILD_GUIDELINE rules 10–11); the runtime may hold edits until the failure is understood.
4. Write `docs/05_implementation/BUILD_REPORT.md` per BUILD_GUIDELINE, with the last full test run.
5. Run `/sentinel:phase-review build` (Skill tool). Fix every 🔴 finding and run it again; show the user each 🟡 finding and how it was handled.
6. Ask the approval question below and record the answer.

## Approval

- Ask: *"The code is built and its tests pass. Do you approve it, so the release can be prepared?"*
  Record the answer: on approval `sentinel-state approve build --reviewer "<the approver's name or role>"` (with conditions add `--decision "APPROVED WITH CONDITIONS" --note "<conditions>"`); on a no, the same with `--decision REJECTED --note "<reasons>"`, then address the reasons and review again.
- After the approval, the next skill is `sentinel:release`.

## Rules

- **[BLOCKING]** Never report tests as passing without running them in this session.
- **[BLOCKING]** No secrets in the code, the tests or the repository.
- **[REQUIRED]** A change to the design is recorded under Deviations; a change to a requirement is asked of the user first.

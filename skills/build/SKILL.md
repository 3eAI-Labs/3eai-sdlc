---
name: build
description: |
  3eAI SDLC Core, stage 3 of 4 — build a project: code and tests per its approved design,
  then the build report.
  Use after a project's design is approved. Its first step checks the project itself.
  Triggers: "build my app", "write the code for my small project", "start coding the design". (3eai-sdlc)
allowed-tools: [Read, Grep, Glob]
---

# Build — code and tests (3eAI SDLC Core, stage 3 of 4)

## Texts to follow

Read and follow `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/CORE_WORKFLOW.md` and `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/BUILD_GUIDELINE.md`.

## Where the project is

1. Apply CORE_WORKFLOW rules 1–2 (the project's flow). Stop if they say so.
2. This stage starts only when `docs/03_architecture/DESIGN_GATE.md` exists and its last `Decision:` heading, at any heading level, reads `APPROVED` or `APPROVED WITH CONDITIONS`; a file with no `Decision:` line counts as approved (CORE_WORKFLOW rule 3). If it does not, tell the user which earlier work is still open, in project terms, and start the skill of the stage the project is at.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md` and `docs/03_architecture/DESIGN.md`.
2. Build in the design's order, one feature or component at a time: a test, the code that passes it, a run of the tests.
3. When a test run fails, find the cause before editing further (BUILD_GUIDELINE rules 10–11).
4. Run the project's full test suite with the Bash tool, using the test command DESIGN.md names, for example:

   ```bash
   python3 -m pytest -q
   ```
5. Write `docs/05_implementation/BUILD_REPORT.md` per BUILD_GUIDELINE, with that command and what it printed.
6. Have the document reviewed in a fresh context: use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"` and only this prompt: *"Project root: <the absolute project root>. Stage: build. Follow your subagent contract in full: write the report and print the one-line summary. This is a fresh-context review; validate from the files alone."* Pass nothing else from this conversation. Then read `docs/05_implementation/BUILD_REVIEW.md`.
7. Fix every 🔴 finding and review again; show the user each 🟡 finding and how it was handled.
8. Ask the approval question below and record the answer.

## Approval

Ask: *"The code is built and its tests pass. Do you approve it, so the release can be prepared?"*

Record the answer by appending this block to `docs/05_implementation/BUILD_GATE.md`; a new file starts with the line `# Build Gate`. `<DATE>` is the session's current date as YYYY-MM-DD, `<REVIEWER>` the approver's name or role, `<DECISION>` one of `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED`, `<NOTE>` the conditions or reasons, or `—`.

```text

## Checkpoint Approval Record
**Phase / Checkpoint / Date / Reviewer:** build / — / <DATE> / <REVIEWER>
### Deliverables Reviewed: docs/05_implementation/ (review: BUILD_REVIEW.md)
### Checklist Completion: per BUILD_REVIEW.md
### Decision: <DECISION>
### Notes / Signature: <NOTE>; <REVIEWER>
```

On `REJECTED`, address the reasons, review again and ask again. After an approval, the next skill is `3eai-sdlc:release`.

## Rules

- **[BLOCKING]** Never report tests as passing without running them in this session.
- **[BLOCKING]** No secrets in the code, the tests or the repository.
- **[REQUIRED]** A change to the design is recorded under Deviations; a change to a requirement is asked of the user first.
- **[REQUIRED]** Ask the user project questions only; never about stages, skills or 3eai-sdlc.

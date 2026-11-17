---
name: release
description: |
  3eAI SDLC Core, stage 4 of 4 — release a project: version, pre-release checklist, deploy
  and rollback steps, known issues, from its approved build.
  Use after a project's build is approved. Its first step checks the project itself.
  Triggers: "release my app", "first release of my small project", "prepare the release". (3eai-sdlc)
allowed-tools: [Read, Grep, Glob]
---

# Release — ship and roll back (3eAI SDLC Core, stage 4 of 4)

## Texts to follow

Read and follow `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/CORE_WORKFLOW.md` and `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/RELEASE_GUIDELINE.md`.

## Where the project is

1. Apply CORE_WORKFLOW rules 1–2 (the project's flow). Stop if they say so.
2. This stage starts only when `docs/05_implementation/BUILD_GATE.md` exists and its last `Decision:` heading, at any heading level, reads `APPROVED` or `APPROVED WITH CONDITIONS`; a file with no `Decision:` line counts as approved (CORE_WORKFLOW rule 3). If it does not, tell the user which earlier work is still open, in project terms, and start the skill of the stage the project is at.

## Steps

1. Read `docs/05_implementation/BUILD_REPORT.md`, and `docs/06_deploy/RELEASE.md` if it exists.
2. Run the pre-release checklist of RELEASE_GUIDELINE rule 2 and record each result with its evidence. Its test run uses the Bash tool and the test command the build report names, for example:

   ```bash
   python3 -m pytest -q
   ```
3. Write `docs/06_deploy/RELEASE.md` per RELEASE_GUIDELINE.
4. Have the document reviewed in a fresh context: use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"` and only this prompt: *"Project root: <the absolute project root>. Stage: release. Follow your subagent contract in full: write the report and print the one-line summary. This is a fresh-context review; validate from the files alone."* Pass nothing else from this conversation. Then read `docs/06_deploy/RELEASE_REVIEW.md`.
5. Fix every 🔴 finding and review again; show the user each 🟡 finding and how it was handled.
6. Ask the approval question below and record the answer.
7. Tag, publish or deploy only after the approval and with the user's go-ahead for that action.

## Approval

Ask: *"The release is ready. Do you approve it?"*

Record the answer by appending this block to `docs/06_deploy/RELEASE_GATE.md`; a new file starts with the line `# Release Gate`. `<DATE>` is the session's current date as YYYY-MM-DD, `<REVIEWER>` the approver's name or role, `<DECISION>` one of `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED`, `<NOTE>` the conditions or reasons, or `—`.

```text

## Checkpoint Approval Record
**Phase / Checkpoint / Date / Reviewer:** release / — / <DATE> / <REVIEWER>
### Deliverables Reviewed: docs/06_deploy/ (review: RELEASE_REVIEW.md)
### Checklist Completion: per RELEASE_REVIEW.md
### Decision: <DECISION>
### Notes / Signature: <NOTE>; <REVIEWER>
```

On `REJECTED`, address the reasons, review again and ask again.

## Rules

- **[BLOCKING]** A failed checklist item blocks the release unless the user accepts it.
- **[BLOCKING]** No deploy, publish or push without the user's go-ahead.
- **[REQUIRED]** A rollback exists before deploying.
- **[REQUIRED]** Ask the user project questions only; never about stages, skills or 3eai-sdlc.

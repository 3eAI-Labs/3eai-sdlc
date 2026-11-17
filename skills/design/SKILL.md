---
name: design
description: |
  3eAI SDLC Core, stage 2 of 4 — the design of a project: stack and why, components, data,
  interfaces, decisions and risks, from its approved requirements.
  Use after a project's requirements are approved. Its first step checks the project itself.
  Triggers: "design my app", "pick the stack", "small project design". (3eai-sdlc)
allowed-tools: [Read, Grep, Glob]
---

# Design — how it will be built (3eAI SDLC Core, stage 2 of 4)

## Texts to follow

Read and follow `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/CORE_WORKFLOW.md` and `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/DESIGN_GUIDELINE.md`.

## Where the project is

1. Apply CORE_WORKFLOW rules 1–2 (the project's flow). Stop if they say so.
2. This stage starts only when `docs/01_product/DEFINE_GATE.md` exists and its last `Decision:` heading, at any heading level, reads `APPROVED` or `APPROVED WITH CONDITIONS`; a file with no `Decision:` line counts as approved (CORE_WORKFLOW rule 3). If it does not, tell the user which earlier work is still open, in project terms, and start the skill of the stage the project is at.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md`, and `docs/03_architecture/DESIGN.md` if it exists.
2. Ask the user what is fixed or preferred (language, hosting, budget for paid services), only where the requirements do not say.
3. Write `docs/03_architecture/DESIGN.md` per DESIGN_GUIDELINE, including the command that runs the project's tests.
4. Have the document reviewed in a fresh context: use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"` and only this prompt: *"Project root: <the absolute project root>. Stage: design. Follow your subagent contract in full: write the report and print the one-line summary. This is a fresh-context review; validate from the files alone."* Pass nothing else from this conversation. Then read `docs/03_architecture/DESIGN_REVIEW.md`.
5. Fix every 🔴 finding and review again; show the user each 🟡 finding and how it was handled.
6. Ask the approval question below and record the answer.

## Approval

Ask: *"The design is ready. Do you approve it, so the build can start?"*

Record the answer by appending this block to `docs/03_architecture/DESIGN_GATE.md`; a new file starts with the line `# Design Gate`. `<DATE>` is the session's current date as YYYY-MM-DD, `<REVIEWER>` the approver's name or role, `<DECISION>` one of `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED`, `<NOTE>` the conditions or reasons, or `—`.

```text

## Checkpoint Approval Record
**Phase / Checkpoint / Date / Reviewer:** design / — / <DATE> / <REVIEWER>
### Deliverables Reviewed: docs/03_architecture/ (review: DESIGN_REVIEW.md)
### Checklist Completion: per DESIGN_REVIEW.md
### Decision: <DECISION>
### Notes / Signature: <NOTE>; <REVIEWER>
```

On `REJECTED`, address the reasons, review again and ask again. After an approval, the next skill is `3eai-sdlc:build`.

## Rules

- **[BLOCKING]** Do not write production code before the approval is recorded.
- **[REQUIRED]** A change the design needs in the requirements is asked of the user first (CORE_WORKFLOW rule 6).
- **[REQUIRED]** Ask the user project questions only; never about stages, skills or 3eai-sdlc.

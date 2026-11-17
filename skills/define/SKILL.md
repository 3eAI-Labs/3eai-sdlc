---
name: define
description: |
  3eAI SDLC Core, stage 1 of 4 — the requirements of a new project, whatever its size
  (a large or regulated one included): goal, users, features with acceptance criteria,
  non-goals. Use when a project starts or its requirements change. Its first step checks
  the project itself.
  Triggers: "requirements for my app", "start a new project", "what should it do", "a new system for our teams". (3eai-sdlc)
allowed-tools: [Read, Grep, Glob]
---

# Define — the requirements (3eAI SDLC Core, stage 1 of 4)

## Texts to follow

Read and follow `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/CORE_WORKFLOW.md` and `${CLAUDE_PLUGIN_ROOT}/guidelines/essentials/DEFINE_GUIDELINE.md`.

## Where the project is

1. Apply CORE_WORKFLOW rules 1–2 (the project's flow). Stop if they say so.
2. Define is the first stage: it can always start. If `docs/01_product/DEFINE_GATE.md` already records an approval, the requirements are changing: keep them and add to their "Changes" list.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md` if it exists, and continue it rather than starting over.
2. Ask the user the project questions of DEFINE_GUIDELINE rule 1, a few at a time.
3. Write `docs/01_product/REQUIREMENTS.md` per DEFINE_GUIDELINE.
4. Have the document reviewed in a fresh context: use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"` and only this prompt: *"Project root: <the absolute project root>. Stage: define. Follow your subagent contract in full: write the report and print the one-line summary. This is a fresh-context review; validate from the files alone."* Pass nothing else from this conversation. Then read `docs/01_product/DEFINE_REVIEW.md`.
5. Fix every 🔴 finding and review again; show the user each 🟡 finding and how it was handled.
6. Ask the approval question below and record the answer.

## Approval

Ask: *"The requirements are ready. Do you approve them, so the design can start?"*

Record the answer by appending this block to `docs/01_product/DEFINE_GATE.md`; a new file starts with the line `# Define Gate`. `<DATE>` is the session's current date as YYYY-MM-DD, `<REVIEWER>` the approver's name or role, `<DECISION>` one of `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED`, `<NOTE>` the conditions or reasons, or `—`.

```text

## Checkpoint Approval Record
**Phase / Checkpoint / Date / Reviewer:** define / — / <DATE> / <REVIEWER>
### Deliverables Reviewed: docs/01_product/ (review: DEFINE_REVIEW.md)
### Checklist Completion: per DEFINE_REVIEW.md
### Decision: <DECISION>
### Notes / Signature: <NOTE>; <REVIEWER>
```

On `REJECTED`, address the reasons, review again and ask again. After an approval, the next skill is `3eai-sdlc:design`.

## Rules

- **[BLOCKING]** Do not start the design before the approval is recorded.
- **[REQUIRED]** Ask the user project questions only; never about stages, skills or 3eai-sdlc.

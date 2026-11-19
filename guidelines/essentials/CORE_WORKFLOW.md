---
name: CORE_WORKFLOW
title: 3eAI SDLC Core Workflow
flow: core
---

# 3eAI SDLC Core Workflow

## Purpose

3eAI SDLC Core is a four-stage flow for a developer working alone or in a small team. Each stage writes one document, is reviewed, and ends with the user's approval.

## What to produce

| Stage | Skill | Deliverable | Approval record |
|-------|-------|-------------|-----------------|
| Define | `3eai-sdlc:define` | `docs/01_product/REQUIREMENTS.md` | `docs/01_product/DEFINE_GATE.md` |
| Design | `3eai-sdlc:design` | `docs/03_architecture/DESIGN.md` | `docs/03_architecture/DESIGN_GATE.md` |
| Build | `3eai-sdlc:build` | code and tests in the source tree; `docs/05_implementation/BUILD_REPORT.md` | `docs/05_implementation/BUILD_GATE.md` |
| Release | `3eai-sdlc:release` | `docs/06_deploy/RELEASE.md` | `docs/06_deploy/RELEASE_GATE.md` |

## Rules

### Flow

1. The project's flow is the first line of `.sentinel/flow`. `core` is this flow. `enterprise`, or a line `upgraded-from: core` (followed by a date), means the project follows the enterprise flow, which is part of 3eAI SDLC Pro (https://3eai-labs.com): say so once, in project terms, and stop.
2. No `.sentinel/flow`: decide the flow from the project's files, in this order, and record it by writing `core` and a newline to `.sentinel/flow`.
   1. If the project holds a Core gate or review file (`DEFINE_GATE.md`, `DEFINE_REVIEW.md`, `DESIGN_GATE.md`, `DESIGN_REVIEW.md`, `BUILD_GATE.md`, `BUILD_REVIEW.md`, `RELEASE_GATE.md` or `RELEASE_REVIEW.md`) in its stage's directory: write `core` without asking.
   2. Else, if it holds a `PHASE<N>_GATE.md` or `PHASE1_APPROVAL.md` in a `docs/0x_*` directory: the project follows the enterprise flow; stop as in rule 1.
   3. Else, if it holds a `.sentinel/runtime/current_phase` that names a Core stage: write `core` without asking; one that names an enterprise phase: stop as in rule 1.
   4. Else, if it has a `docs/01_product/`, `docs/02_business/`, `docs/03_architecture/`, `docs/035_skeleton/`, `docs/04_design/`, `docs/05_implementation/` or `docs/06_deploy/` directory: ask the user whether to follow this four-stage flow, and write `core` only after a yes.
   5. Otherwise, a new project: write `core`.
3. A stage is approved when its approval record file exists and its last `Decision:` heading, at any heading level, reads `APPROVED` or `APPROVED WITH CONDITIONS`; a file with no `Decision:` line counts as approved. Work on one stage at a time, in order: a stage starts only after the one before it is approved. Asked for a later stage, name the stage the project is at and start that one.
4. Ask the user project questions only. Never ask about stages, skills or 3eai-sdlc itself.
5. A stage's document states decisions, not intentions. What is not decided yet goes under "Open questions", with who decides it.
6. A later stage that finds an earlier document wrong tells the user, changes that document only after the user agrees, and records the change in that document's "Changes" list with the date and the reason.

### Review and approval

7. When the deliverable is complete, have it reviewed in a fresh context: use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"`, as the stage skill says. The reviewer writes `<STAGE>_REVIEW.md` next to the deliverable.
8. Fix every 🔴 finding and review again before asking for approval. Show the user each 🟡 finding and how it was handled.
9. Ask for approval in project terms ("Approve the requirements?"), with the review's verdict and its open findings.
10. Record the answer by appending the stage skill's approval record to the stage's approval record file (a new file starts with its heading, `# <Stage> Gate`). On a no, record `REJECTED` with the reason, address the reason, review again and ask again.

### Evidence

11. Say what was checked and how: the file and line read, the command run and what it printed.
12. Mark a claim that was not checked as a guess ("I think", "not verified").
13. Never report a test, a build or a check as passing without having run it in this session.

### Moving to the Enterprise flow

14. When the user asks for the full enterprise process (more teams, regulation, formal architecture and release gates), say that it is part of 3eAI SDLC Pro (https://3eai-labs.com), which continues a project made with this flow from its documents and approvals.

---
name: CORE_WORKFLOW
title: 3eAI SDLC Core Workflow
flow: core
---

# 3eAI SDLC Core Workflow

## Purpose

3eAI SDLC Core is a four-stage flow for a developer working alone or in a small team. Each stage writes one document, is reviewed, and ends with the user's approval.

## What to produce

| Stage | Skill | Deliverable | What it hands to the next stage |
|-------|-------|-------------|---------------------------------|
| Define | `3eai-sdlc:define` | `docs/01_product/REQUIREMENTS.md` | the goal, the users, the features and their acceptance criteria |
| Design | `3eai-sdlc:design` | `docs/03_architecture/DESIGN.md` | the stack, the components, the data, the interfaces and the decisions |
| Build | `3eai-sdlc:build` | code and tests in the source tree; `docs/05_implementation/BUILD_REPORT.md` | working code, tested against each feature |
| Release | `3eai-sdlc:release` | `docs/06_deploy/RELEASE.md` | a version that can be run or deployed, and rolled back |

## Rules

### Flow

1. Work on one stage at a time, in order. A stage starts only after the one before it is approved; `sentinel-state enter <stage>` refuses a stage the project has not reached and names the one it is at.
2. Ask the user project questions only. Never ask about stages, skills, markers or 3eai-sdlc itself.
3. A stage's document states decisions, not intentions. What is not decided yet goes under "Open questions", with who decides it.
4. A later stage that finds an earlier document wrong tells the user, changes that document only after the user agrees, and records the change in that document's "Changes" list with the date and the reason.

### Review and approval

5. When the deliverable is complete, run `/3eai-sdlc:phase-review <stage>`. It writes `<STAGE>_REVIEW.md` next to the deliverable.
6. Fix every 🔴 finding before asking for approval. Show the user each 🟡 finding and how it was handled.
7. Ask for approval in project terms ("Approve the requirements?"), with the review's verdict and its open findings.
8. Record the answer with `sentinel-state approve <stage> --reviewer <the user's name>`. On a no, add `--decision REJECTED --note "<the reason>"`, address the reason, review again and ask again.

### Evidence

9. Say what was checked and how: the file and line read, the command run and what it printed.
10. Mark a claim that was not checked as a guess ("I think", "not verified").
11. Never report a test, a build or a check as passing without having run it in this session.

### Moving to the Enterprise flow

12. Only when the user asks for the full enterprise process (more teams, regulation, formal architecture and release gates), run `sentinel-state upgrade`. The project restarts at Enterprise phase 1, which starts from `REQUIREMENTS.md`; the Core documents and approvals stay as history.

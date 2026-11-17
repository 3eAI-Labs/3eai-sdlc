---
name: phase-review
description: |
  Fresh-context adversarial review of a stage's deliverables: the 3eAI SDLC Core stages
  (define, design, build, release) against their essentials checklists. Detects padding,
  scope creep, coverage gaps and contradictions, and writes the review report that the
  stage's approval relies on.
  Triggers: "phase-review", "review phase 1", "review phase 2", "adversarial review",
  "check phase output", "validate phase N", "review the define stage". (3eai-sdlc)
allowed-tools: [Read, Grep, Glob]
---

# Phase review — a fresh-context review of one Core stage

You are an orchestrator, not the reviewer. Do not review in this context: the reviewer's fresh context is what prevents a rubber-stamp review.

## Step 1: the stage

- The argument is one of `define`, `design`, `build`, `release`.
- A phase number (`1`, `2`, `3`, `3.5`, `4`, `5`, `5.5`, `6`), or a project whose `.sentinel/flow` reads `enterprise`: enterprise phase reviews are part of 3eAI SDLC Pro (https://3eai-labs.org). Say so once, in project terms, and stop.
- No argument: review the latest stage whose deliverable exists (`release`, `build`, `design`, `define`, in that order), and name it in the report.

| Stage | Directory | Deliverable |
|-------|-----------|-------------|
| `define` | `docs/01_product/` | `REQUIREMENTS.md` |
| `design` | `docs/03_architecture/` | `DESIGN.md` |
| `build` | `docs/05_implementation/` | `BUILD_REPORT.md` and the source tree |
| `release` | `docs/06_deploy/` | `RELEASE.md` |

If the deliverable does not exist, tell the user there is nothing to review yet, and stop.

## Step 2: invoke the reviewer

Use the Agent tool with `subagent_type: "3eai-sdlc:sentinel-core-review"` and only this prompt: *"Project root: <the absolute project root>. Stage: <stage>. Follow your subagent contract in full: write the report and print the one-line summary. This is a fresh-context review; validate from the files alone."*

Pass nothing else from this conversation: not the author's reasons, not a summary, not any framing.

## Step 3: the verdict

Read the report the reviewer wrote and show the user:

```
<Stage> review complete.

Report: <dir>/<STAGE>_REVIEW.md
Verdict: <READY-TO-ADVANCE | HAS-BLOCKERS | HAS-CONCERNS-NEEDING-ACK>
Findings: 🔴 <n>  🟡 <n>  🟢 <n>

Next action: <the report's next action>
```

Show each 🔴 finding (title and location) inline. Do not soften, re-grade or hide a finding.

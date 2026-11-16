---
name: design
description: |
  Sentinel Core, stage 2 of 4 — the design of a small project (one developer or a small team):
  stack and why, components, data, interfaces, decisions and risks, from its approved
  requirements.
  Use after a small project's requirements are approved. Choose it by the user's words; its first step checks the
  project itself.
  Not for: an enterprise project's HLD (/phase3), walking skeleton (/phase35) or LLD (/phase4).
  Triggers: "design my app", "pick the stack", "small project design". (sentinel)
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

# Design — how it will be built (Sentinel Core, stage 2 of 4)

**Stage marker (run first):** it checks that the project follows the Core flow and has reached this stage, and sets the stage. If it exits non-zero, stop this skill and follow its output.

```bash
sentinel-state enter design || exit $?
```

## Preamble (run after the stage marker)

```bash
"$(sentinel-root)/guidelines/load_phase_context.sh" design "$PWD" || exit $?
```

Follow the loaded CORE_WORKFLOW and DESIGN_GUIDELINE.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md`, and `docs/03_architecture/DESIGN.md` if it exists.
2. Ask the user what is fixed or preferred (language, hosting, budget for paid services) with AskUserQuestion, only where the requirements do not say.
3. Write `docs/03_architecture/DESIGN.md` per DESIGN_GUIDELINE.
4. Run `/sentinel:phase-review design` (Skill tool). Fix every 🔴 finding and run it again; show the user each 🟡 finding and how it was handled.
5. Ask the approval question below and record the answer.

## Approval

- Ask: *"The design is ready. Do you approve it, so the build can start?"*
  Record the answer: on approval `sentinel-state approve design --reviewer "<the approver's name or role>"` (with conditions add `--decision "APPROVED WITH CONDITIONS" --note "<conditions>"`); on a no, the same with `--decision REJECTED --note "<reasons>"`, then address the reasons and review again.
- After the approval, the next skill is `sentinel:build`.

## Rules

- **[BLOCKING]** Do not write production code before the approval is recorded.
- **[REQUIRED]** A change the design needs in the requirements is asked of the user first (CORE_WORKFLOW rule 4).

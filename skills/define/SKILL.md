---
name: define
description: |
  Sentinel Core, stage 1 of 4 — the requirements of a new project, whatever its size
  (a large or regulated one included): goal, users, features with acceptance criteria,
  non-goals. Use when a project starts or its requirements change. Its first step checks
  the project itself.
  Triggers: "requirements for my app", "start a new project", "what should it do", "a new system for our teams". (sentinel)
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
---

# Define — the requirements (Sentinel Core, stage 1 of 4)

**Stage marker (run first):** it checks that the project follows the Core flow and has reached this stage, and sets the stage. If it exits non-zero, stop this skill and follow its output.

```bash
sentinel-state enter define || exit $?
```

## Preamble (run after the stage marker)

```bash
"$(sentinel-root)/guidelines/load_phase_context.sh" define "$PWD" || exit $?
```

Follow the loaded CORE_WORKFLOW and DEFINE_GUIDELINE.

## Steps

1. Read `docs/01_product/REQUIREMENTS.md` if it exists, and continue it rather than starting over.
2. Ask the user the project questions of DEFINE_GUIDELINE rule 1 with AskUserQuestion, a few at a time.
3. Write `docs/01_product/REQUIREMENTS.md` per DEFINE_GUIDELINE.
4. Run `/sentinel:phase-review define` (Skill tool). Fix every 🔴 finding and run it again; show the user each 🟡 finding and how it was handled.
5. Ask the approval question below and record the answer.

## Approval

- Ask: *"The requirements are ready. Do you approve them, so the design can start?"*
  Record the answer: on approval `sentinel-state approve define --reviewer "<the approver's name or role>"` (with conditions add `--decision "APPROVED WITH CONDITIONS" --note "<conditions>"`); on a no, the same with `--decision REJECTED --note "<reasons>"`, then address the reasons and review again.
- After the approval, the next skill is `sentinel:design`.

## Rules

- **[BLOCKING]** Do not start the design before the approval is recorded.
- **[REQUIRED]** Ask the user project questions only; never about stages, skills or sentinel.

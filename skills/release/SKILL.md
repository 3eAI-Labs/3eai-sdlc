---
name: release
description: |
  Sentinel Core, stage 4 of 4 — release a small project (one developer or a small team):
  version, pre-release checklist, deploy and rollback steps, known issues, from its approved
  build.
  Use after a small project's build is approved. Choose it by the user's words; its first step checks the
  project itself.
  Not for: an enterprise project's release gate, compliance and deployment (/phase6); commit,
  push and PR of a branch (/ship).
  Triggers: "release my app", "first release of my small project", "prepare the release". (sentinel)
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

# Release — ship and roll back (Sentinel Core, stage 4 of 4)

**Stage marker (run first):** it checks that the project follows the Core flow and has reached this stage, and sets the stage. If it exits non-zero, stop this skill and follow its output.

```bash
sentinel-state enter release || exit $?
```

## Preamble (run after the stage marker)

```bash
"$(sentinel-root)/guidelines/load_phase_context.sh" release "$PWD" || exit $?
```

Follow the loaded CORE_WORKFLOW and RELEASE_GUIDELINE.

## Steps

1. Read `docs/05_implementation/BUILD_REPORT.md`, and `docs/06_deploy/RELEASE.md` if it exists.
2. Run the pre-release checklist of RELEASE_GUIDELINE rule 2 and record each result with its evidence.
3. Write `docs/06_deploy/RELEASE.md` per RELEASE_GUIDELINE.
4. Run `/sentinel:phase-review release` (Skill tool). Fix every 🔴 finding and run it again; show the user each 🟡 finding and how it was handled.
5. Ask the approval question below and record the answer.
6. Tag, publish or deploy only after the approval and with the user's go-ahead for that action.

## Approval

- Ask: *"The release is ready. Do you approve it?"*
  Record the answer: on approval `sentinel-state approve release --reviewer "<the approver's name or role>"` (with conditions add `--decision "APPROVED WITH CONDITIONS" --note "<conditions>"`); on a no, the same with `--decision REJECTED --note "<reasons>"`, then address the reasons and review again.

## Rules

- **[BLOCKING]** A failed checklist item blocks the release unless the user accepts it.
- **[BLOCKING]** No deploy, publish or push without the user's go-ahead.
- **[REQUIRED]** A rollback exists before deploying.

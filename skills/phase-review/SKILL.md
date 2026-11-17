---
name: phase-review
description: |
  Fresh-context adversarial review of any phase's deliverables. Validates Phase 1-6
  artifacts against VISION, manifest, enabled guidelines, and upstream phase outputs, and
  the 3eAI SDLC Core stages (define, design, build, release) against their essentials checklists.
  Detects padding, scope creep, traceability gaps, and cross-artifact contradictions.
  Produces a structured phase review report that gates progression to the next phase.
  Not for: a work plan (/plan-review).
  Triggers: "phase-review", "review phase 1", "review phase 2", "adversarial review",
  "check phase output", "validate phase N", "review the define stage". (3eai-sdlc)
allowed-tools:
  - Bash
  - Read
  - Agent
  - Grep
  - Glob
---

## 💡 Recommended Model for Orchestration: **Sonnet** (subagent uses Opus)

This skill is an orchestrator: validate invocation, delegate to the
`sentinel-phase-review` subagent (Enterprise phases) or the `sentinel-core-review`
subagent (Core stages), both Opus in a fresh isolated context, and surface the verdict.
Do NOT review in-context yourself — fresh context is what prevents rubber-stamp reviews.

```
/model sonnet
```

## Usage

```
/3eai-sdlc:phase-review <N>
```

Where `<N>` is one of: `1`, `2`, `3`, `3.5`, `4`, `5`, `5.5`, `6` (Enterprise flow), or one of
`define`, `design`, `build`, `release` (Core flow).

Examples:
- `/3eai-sdlc:phase-review 1` — review Phase 1 (VISION, MANIFEST, USER_STORIES, SRS, DATA_CLASSIFICATION)
- `/3eai-sdlc:phase-review 3` — review Phase 3 (HLD, API_CONTRACTS, ADRs, DATA_OWNERSHIP, manifest stack amendment)
- `/3eai-sdlc:phase-review 3.5` — review Phase 3.5 (walking skeleton smoke proof, RUNTIME_CONTRACT)
- `/3eai-sdlc:phase-review 5.5` — review Phase 5.5 (test coverage, security scans)
- `/3eai-sdlc:phase-review define` — review a Core project's requirements (`docs/01_product/REQUIREMENTS.md`)

If no argument is given, review the phase or stage `sentinel-state` prints (Step 1). Do not
guess from conversation context.

## Preamble (run first)

Set `REVIEW_ARG` to the argument as given (`define`, `3`, `3.5`, …), or leave it empty.

```bash
REVIEW_ARG=""
E3E_ROOT="$(sentinel-root)" || exit 1
echo "======================================================================"
echo "🔎 3EAI-SDLC: PHASE REVIEW — Fresh-Context Adversarial Reviewer"
echo "======================================================================"
echo ""
echo "Project root: $PWD"

STATE="$(sentinel-state status 2>/dev/null)"
FLOW="$(printf '%s\n' "$STATE" | sed -n 's/^flow: //p')"
CURRENT="$(printf '%s\n' "$STATE" | sed -n 's/^skill: 3eai-sdlc://p')"
EDITION="$(printf '%s\n' "$STATE" | sed -n 's/^edition: //p')"
if [[ "$EDITION" == "free" && "$FLOW" == "enterprise" ]]; then
  printf '%s\n' "$STATE"
  echo "⚠️  This project follows the enterprise flow, which is part of 3eAI SDLC Pro; this edition reviews the Core stages only. Tell the user so once, in project terms, and follow the 'next:' line above if there is one."
  exit 1
fi
if [[ "$FLOW" == "undecided" ]]; then
  printf '%s\n' "$STATE"
  echo "⚠️  No flow is recorded for this project, so there is nothing to review yet. Follow the 'next:' line above."
  exit 1
fi
case "$REVIEW_ARG" in
  "") ARG_FLOW="$FLOW" ;;
  define|design|build|release) ARG_FLOW="core" ;;
  *) ARG_FLOW="enterprise" ;;
esac
if [[ -n "$FLOW" && "$ARG_FLOW" != "$FLOW" ]]; then
  echo "⚠️  '$REVIEW_ARG' belongs to the $ARG_FLOW flow; this project follows the $FLOW flow and is at '$CURRENT'."
  echo "    Review that instead: /3eai-sdlc:phase-review $CURRENT"
  exit 1
fi
if [[ "$FLOW" == "core" ]]; then
  echo "Flow: core — the Core stage document is reviewed against guidelines/essentials (no manifest)."
  echo "Output: <dir>/<STAGE>_REVIEW.md + verdict summary"
  echo "======================================================================"
  exit 0
fi
echo "Input: Phase N deliverables in docs/0N_*/"
echo "Output: docs/0N_*/PHASE<N>_REVIEW.md + verdict summary"

MANIFEST="$PWD/docs/01_product/GUIDELINES_MANIFEST.yaml"
if [[ ! -f "$MANIFEST" ]]; then
  echo ""
  echo "⚠️  GUIDELINES_MANIFEST.yaml missing — phase-review cannot run without it."
  echo "    Fix path: run /3eai-sdlc:phase1 first to bootstrap the manifest."
  echo "    (Review needs the manifest to decide which guidelines apply.)"
  exit 1
fi

# Smoke-check loader works against the phase-review pseudo-phase
if ! "$E3E_ROOT/guidelines/load_phase_context.sh" phase-review "$PWD" > /dev/null 2>&1; then
  echo ""
  echo "⚠️  Loader validation failed. Running it verbosely so you can see the error:"
  "$E3E_ROOT/guidelines/load_phase_context.sh" phase-review "$PWD" 2>&1 | tail -20
  exit 1
fi

echo "✅ Manifest present and valid. Ready to delegate to subagent."
echo "======================================================================"
```

## Execution Contract

You are an **orchestrator**, not the reviewer. Your job has four steps.

### Step 1: Parse and validate the phase argument

- Extract `<N>` from the user's invocation.
- Valid values: `1`, `2`, `3`, `3.5`, `4`, `5`, `5.5`, `6` in an Enterprise project; `define`, `design`, `build`, `release` in a Core project (the preamble stopped on the other flow's values).
- If invalid or missing: review the phase or stage `sentinel-state` prints (`phaseNN` maps to `N.N`, e.g. `phase35` → `3.5`; a stage key maps to itself), and name it in the report.

### Step 2: Verify the target directory exists

Map phase → directory:

| N | Expected directory |
|---|---|
| 1 | `docs/01_product/` |
| 2 | `docs/02_business/` |
| 3 | `docs/03_architecture/` |
| 3.5 | `docs/035_skeleton/` |
| 4 | `docs/04_design/` |
| 5 | `docs/05_implementation/` + source tree |
| 5.5 | `docs/05_implementation/testing/` |
| 6 | `docs/06_deploy/` |
| `define` | `docs/01_product/` |
| `design` | `docs/03_architecture/` |
| `build` | `docs/05_implementation/` + source tree |
| `release` | `docs/06_deploy/` |

If the directory does not exist, report to the user and exit — there's nothing to review.

### Step 3: Invoke the `sentinel-phase-review` subagent

This is the critical step. Use the **Agent tool** with:

- `subagent_type: "sentinel-phase-review"`
- `description:` something like `"Phase <N> fresh-context review"`
- `prompt:` a self-contained brief that includes:
  - The absolute project root path (`$PWD`)
  - The phase argument `<N>`
  - The expected directory (per the table above)
  - A direct instruction: *"Follow your subagent contract in full. Read every required artifact for Phase <N>. Apply the 5 categories and the three mandatory passes (upstream coverage via `sentinel-trace`, guideline checklist, data contract). Produce the report at `docs/0<N>_<dir>/PHASE<N>_REVIEW.md`. Emit the single-line summary to stdout per your contract."*
  - A reminder that it has fresh context: *"This is a fresh-context review. You have not seen the authoring of these deliverables. That isolation is the point — validate from the artifacts alone."*

For a Core stage, use `subagent_type: "sentinel-core-review"` instead, with the project root, the stage, its directory and: *"Follow your subagent contract in full. Produce the report at `<dir>/<STAGE>_REVIEW.md` (e.g. `docs/01_product/DEFINE_REVIEW.md`) and emit the single-line summary."* The fresh-context reminder applies the same way.

**Do not** pass the author's conversation, rationale, or any framing text from this session into the subagent prompt. The prompt should read as if the subagent were invoked cold from the CLI.

### Step 4: Surface the verdict

When the subagent returns:

1. Read the report file it wrote (at the path from the phase→directory mapping).
2. Extract the Verdict line and the finding counts (🔴/🟡/🟢).
3. Present to the user, in this exact shape:

   ```
   Phase <N> review complete.

   Report: docs/0<N>_<dir>/PHASE<N>_REVIEW.md (a Core stage: <dir>/<STAGE>_REVIEW.md)
   Verdict: <READY-TO-ADVANCE | HAS-BLOCKERS | HAS-CONCERNS-NEEDING-ACK>
   Findings: 🔴 <n_critical>  🟡 <n_concern>  🟢 <n_observation>
   Coverage: <the SENTINEL_TRACE line from the report's Upstream Coverage section, or "n/a" (always for a Core stage)>

   Next action: <one of the three next-action strings from the report's final section>
   ```

4. If there are 🔴 findings: show each one (title + location) inline so the user doesn't have to open the file.
5. Do not editorialize. The subagent's report is authoritative. You summarize, you do not re-grade.

## Rules

- **[BLOCKING]** In an Enterprise project, the manifest must exist and validate. Preamble enforces this.
- **[BLOCKING]** You MUST invoke via the Agent tool with the `sentinel-phase-review` subagent (a Core stage: `sentinel-core-review`) — reviewing in-context defeats the purpose.
- **[REQUIRED]** The subagent's report file is written to `docs/0<N>_<dir>/PHASE<N>_REVIEW.md` (a Core stage: `<dir>/<STAGE>_REVIEW.md`) — verify it exists after the subagent returns.
- **[REQUIRED]** Phase-review is idempotent and re-runnable. Overwriting a previous review file is expected behavior after author fixes.
- **[REQUIRED]** Do not gate the report: every 🔴 finding is shown to the user. Never soften or hide findings.

## When to Run Phase Review

Primary trigger: at the **end of each phase**, before the human approval gate.

Secondary triggers:
- After any substantive amendment to phase artifacts (e.g. manifest amendment in Phase 3 → re-run Phase 3 review).
- When a later phase uncovers upstream issues ("Phase 4 found a contradiction in Phase 3 HLD") → re-run the affected earlier phase's review to confirm the fix.
- When onboarding a new reviewer or tenant audit — the report itself is a durable artifact.

## What Phase Review Does NOT Do

- It does not fix findings. Resolution is the author's responsibility.
- It does not negotiate severity. A 🔴 finding is resolved or acknowledged in writing by the PO — never debated down.
- It does not replace `3eai-sdlc:review` / `3eai-sdlc:cso` — those target code; phase review targets documentation-layer deliverables.

## Subagent Contract Reference

Full contracts: `agents/sentinel-phase-review.md` and `agents/sentinel-core-review.md` — authoritative over this skill.

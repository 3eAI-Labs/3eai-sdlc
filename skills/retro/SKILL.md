---
name: retro
description: |
  Sprint retrospective — analyzes commit history, work patterns, and code quality metrics
  with trend tracking. Use when asked to "retro", "retrospective", "what went well",
  "sprint review", "team review", or at the end of a sprint. (sentinel)
allowed-tools:
  - Bash
  - Read
  - Write
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

## Preamble (run first)

```bash
E3E_ROOT="$(sentinel-root)" || exit 1
echo "======================================================================"
echo "🔄 SENTINEL: RETRO — Sprint Retrospective"
echo "======================================================================"
echo ""
"$E3E_ROOT/guidelines/load_phase_context.sh" retro "$PWD" || exit $?
echo ""

# Gather data
echo "--- RECENT COMMITS (last 2 weeks) ---"
git log --oneline --since="2 weeks ago" --no-merges 2>/dev/null | head -30
echo ""
echo "--- FILES MOST CHANGED ---"
git log --since="2 weeks ago" --no-merges --name-only --pretty=format: 2>/dev/null | sort | uniq -c | sort -rn | head -15
echo ""
echo "--- CONTRIBUTORS ---"
git shortlog -sn --since="2 weeks ago" --no-merges 2>/dev/null
echo ""
echo "======================================================================"
echo "🤖 RETRO MODE ACTIVE. Analyze objectively, suggest improvements."
echo "======================================================================"
```

## Retrospective Protocol

You are running a **Sprint Retrospective**. Be objective, constructive, and data-driven.

### Step 1: Data Collection
Gather from git history:
- Commits per day/person
- Files most frequently changed (hotspots)
- Commit message quality
- PR merge times (if available)
- Test coverage changes

### Step 2: Analysis Framework

#### What Went Well ✅
- Completed features/tasks
- Good practices observed (small commits, clear messages, tests)
- Performance improvements
- Resolved tech debt

#### What Didn't Go Well ❌
- Hotspot files (changed too often → design issue?)
- Large commits (> 500 lines → should be broken down)
- Missing tests in new code
- Reverted commits (rework indicator)
- TODO/FIXME growth

#### Action Items 🎯
For each issue, propose:
- **What:** Specific, actionable improvement
- **Who:** Responsible person/role
- **When:** Next sprint or specific date
- **How to measure:** Success criteria

### Step 3: Metrics Dashboard

```
Sprint Metrics:
├── Velocity: X commits, Y files changed
├── Hotspots: [top 3 files changed most often]
├── Code Quality:
│   ├── Test coverage: X% (↑/↓ from last sprint)
│   ├── New TODOs added: N
│   ├── Linter warnings: N
│   └── Avg commit size: N lines
├── Process:
│   ├── Avg PR review time: X hours
│   ├── Reverts/rollbacks: N
│   └── Incidents: N
└── Health:
    ├── Bus factor: N (files only 1 person touches)
    └── Dependency updates: N pending
```

### Step 4: Trend Tracking
Save retrospective to `docs/retro/RETRO_YYYY_MM_DD.md` for trend comparison.

### Rules
- **[REQUIRED]** Be data-driven — cite specific commits, files, metrics
- **[REQUIRED]** Be constructive — praise good work, not just problems
- **[REQUIRED]** Action items must be SMART (Specific, Measurable, Achievable, Relevant, Time-bound)
- **[RECOMMENDED]** Compare with previous retro if available
- Ask: *"Retrospective complete. X action items identified. Do you want to add these to the backlog?"*

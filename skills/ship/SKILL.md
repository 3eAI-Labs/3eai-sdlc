---
name: ship
description: |
  Ship workflow — run tests, review diff, bump version, update changelog, commit, push,
  create PR. Use when asked to "ship", "push", "create PR", "bump version", or
  "merge and push". Not for: deploying to an environment (/phase6); the release checklist
  of a project the user calls small (/release). (3eai-sdlc)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
---

## Preamble (run first)

```bash
E3E_ROOT="$(sentinel-root)" || exit 1
echo "======================================================================"
echo "🚀 3EAI-SDLC: SHIP — Release Workflow"
echo "======================================================================"
echo ""
"$E3E_ROOT/guidelines/load_phase_context.sh" ship "$PWD" || exit $?
echo ""

# Show current state
echo "--- GIT STATUS ---"
git status --short 2>/dev/null
echo ""
echo "--- CURRENT BRANCH ---"
git branch --show-current 2>/dev/null
echo ""
echo "--- LAST 5 COMMITS ---"
git log --oneline -5 2>/dev/null
echo ""
echo "--- VERSION ---"
cat VERSION 2>/dev/null || echo "No VERSION file found"
echo ""
echo "======================================================================"
echo "🤖 SHIP MODE ACTIVE. Follow the checklist. No shortcuts."
echo "======================================================================"
```

## Ship Protocol

You are now in **Ship Mode**. Follow every step — no shortcuts.

### Pre-Ship Checklist

#### Step 1: Verify Clean State
```bash
git status
# Must be clean or have only intentional changes
```

#### Step 2: Run Tests
```bash
# Run the project's test suite
# Detect and run: npm test, go test, mvn test, pytest, etc.
```
**[BLOCKING]** If tests fail → STOP. Fix tests first. Do not ship broken code.

#### Step 3: Review Diff
```bash
git diff main...HEAD --stat
git diff main...HEAD
```
Quick self-review:
- Any debug code left? (console.log, fmt.Println, print())
- Any TODO/FIXME that should be resolved?
- Any secrets accidentally committed?
- Any large files that shouldn't be in git?

#### Step 4: Version Bump
If `VERSION` file exists:
- Determine bump type: patch (bug fix), minor (feature), major (breaking)
- Update VERSION file
- Ask user if unsure about bump type

#### Step 5: Update CHANGELOG
If `CHANGELOG.md` exists:
- Add entry under `## [version] - YYYY-MM-DD`
- Summarize changes from commits since last version
- Follow Keep a Changelog format

#### Step 6: Commit
```bash
git add -A
git commit -m "Release vX.Y.Z: [summary]"
```

#### Step 7: Push
```bash
git push origin [branch-name]
```

#### Step 8: Create PR
```bash
gh pr create --title "[summary]" --body "[changelog entry]"
```

### Rules
- **[BLOCKING]** Tests MUST pass before shipping
- **[BLOCKING]** No secrets in diff
- **[BLOCKING]** No debug code in diff
- **[REQUIRED]** Version bump if VERSION file exists
- **[REQUIRED]** CHANGELOG update if CHANGELOG.md exists
- **[REQUIRED]** PR description must summarize changes
- Ask: *"Ready to ship vX.Y.Z. Tests pass, diff clean, changelog updated. Proceed?"*

### Context
The preamble printed one of two profiles:
- In a Core project (or the free edition): CORE_SHIP — tests, review, version, changelog, commit, push only on the user's go-ahead.
- Otherwise: DEVOPS_GUIDELINE (CI/CD, deployment, release procedures) and EVIDENCE_DECISIONS_GUIDELINE (evidence markers, decisions, reading code and claiming code works).

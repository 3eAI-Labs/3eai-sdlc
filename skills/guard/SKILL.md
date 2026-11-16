---
name: guard
description: |
  Safety mode — warns before destructive commands and restricts edits to a specified
  directory. Use when working on production systems, debugging live environments, or
  when you want maximum safety. Combines destructive command warnings with directory
  scoping. Use when asked to "guard mode", "safe mode", "production mode". (sentinel)
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - AskUserQuestion
---

## Preamble (run first)

```bash
echo "======================================================================"
echo "🛡️ SENTINEL: GUARD MODE — Maximum Safety"
echo "======================================================================"
echo ""
echo "ACTIVE PROTECTIONS:"
echo "  🔒 Destructive command warnings (rm -rf, DROP, force-push, etc.)"
echo "  🔒 Edit/Write tools DISABLED — read-only mode"
echo "  🔒 All changes require explicit confirmation"
echo ""
echo "To exit guard mode, start a new session or use a different skill."
echo "======================================================================"
```

## Guard Mode Protocol

You are now in **Guard Mode**. Maximum safety is enforced.

### Protection Rules

#### 1. Destructive Command Detection
Before executing ANY bash command, check for these patterns. If detected, **STOP and warn**:

| Pattern | Risk | Action |
|---------|------|--------|
| `rm -rf` / `rm -r` | File deletion | ⚠️ WARN — confirm exact path and scope |
| `DROP TABLE` / `DROP DATABASE` | Data loss | 🔴 BLOCK — require explicit confirmation |
| `git push --force` / `git push -f` | History rewrite | 🔴 BLOCK — suggest `--force-with-lease` |
| `git reset --hard` | Uncommitted work loss | ⚠️ WARN — suggest stash first |
| `git checkout .` / `git restore .` | Uncommitted work loss | ⚠️ WARN — confirm intent |
| `kubectl delete` | Resource deletion | ⚠️ WARN — confirm namespace and resource |
| `docker system prune` | Container/image cleanup | ⚠️ WARN — confirm scope |
| `chmod 777` | Security risk | 🔴 BLOCK — suggest minimal permissions |
| `curl \| bash` / `wget \| sh` | Arbitrary code execution | 🔴 BLOCK — review script first |
| `> /dev/sda` / `dd if=` | Disk destruction | 🔴 BLOCK — extreme danger |
| `truncate` / `TRUNCATE TABLE` | Data loss | 🔴 BLOCK — require confirmation |
| `:wq!` / `--no-verify` | Safety bypass | ⚠️ WARN — explain why safety exists |

#### 2. Edit/Write Restrictions
- **Edit tool: DISABLED** — Do not modify any files
- **Write tool: DISABLED** — Do not create any files
- **Read-only mode** — Only observe, diagnose, report

#### 3. Confirmation Protocol
For any operation with side effects:
1. Explain exactly what the command will do
2. Show the exact command that will run
3. Ask: *"This operation has side effects. Type 'CONFIRM' to proceed."*
4. Only proceed after explicit "CONFIRM"

### Use Cases
- Debugging production issues (read logs, check status, no changes)
- Reviewing infrastructure state (kubectl get, describe — never delete)
- Investigating incidents (read-only forensics)
- Pair programming with junior developers (safety net)

### Rules
- **[BLOCKING]** NEVER execute destructive commands without explicit confirmation
- **[BLOCKING]** NEVER edit or write files in guard mode
- **[REQUIRED]** Always explain what a command does before running it
- **[REQUIRED]** Prefer read-only alternatives (e.g., `kubectl get` over `kubectl delete`)

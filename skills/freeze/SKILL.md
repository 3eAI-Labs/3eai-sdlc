---
name: freeze
description: |
  Restrict file edits to a specific directory. Blocks Edit and Write outside the allowed
  path. Use when debugging to prevent accidentally modifying unrelated code, or when
  scoping changes to one module. Use when asked to "freeze", "restrict edits",
  "only edit this folder", "scope changes to". (sentinel)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

## Preamble (run first)

```bash
echo "======================================================================"
echo "🧊 SENTINEL: FREEZE — Directory-Scoped Edits"
echo "======================================================================"
echo ""
echo "Usage: /freeze [directory]"
echo "Example: /freeze src/adapters"
echo ""
echo "All Edit/Write operations outside the specified directory will be BLOCKED."
echo "Read/Grep/Glob remain unrestricted — you can still explore the full codebase."
echo "======================================================================"
```

## Freeze Protocol

You are now in **Freeze Mode**. Edits are restricted to a specific directory.

### Setup
Ask the user: *"Which directory should I restrict edits to?"*

Once specified, enforce:

### Rules
1. **Edit/Write ALLOWED** only inside the specified directory
2. **Edit/Write BLOCKED** for any file outside the directory
3. **Read/Grep/Glob** unrestricted — explore anything
4. **Bash** — allowed but warn if command modifies files outside scope

### Enforcement
Before every Edit or Write operation:
1. Check if the target file path starts with the allowed directory
2. If outside: **STOP** and say: *"⚠️ BLOCKED: [file] is outside the freeze scope ([directory]). To edit this file, exit freeze mode."*
3. If inside: proceed normally

### Use Cases
- Working on a specific adapter (freeze to `src/adapters/cbs/`)
- Fixing a bug in one service (freeze to `services/tmf622/`)
- Refactoring a module without side effects (freeze to `pkg/utils/`)
- Junior developer safety net (freeze to their feature branch directory)

### Exit
To exit freeze mode, the user must explicitly say "unfreeze" or start a different skill.

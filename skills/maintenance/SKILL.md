---
name: maintenance
description: |
  Maintenance mode — bug fixes, tech debt, improvements, and adaptations on deployed systems.
  Use when fixing bugs, reducing tech debt, improving performance, or adapting to new requirements.
  Not for: production-down emergencies or hotfixes (/incident); building a project the user
  calls small (/build).
  Triggers: "maintenance", "bug fix", "tech debt", "improvement". (3eai-sdlc)
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

# Record current phase for 3eai-sdlc runtime hooks (see hooks/_phase_policy.py).
mkdir -p "$PWD/.sentinel/runtime" 2>/dev/null || true
printf '%s' "maintenance" > "$PWD/.sentinel/runtime/current_phase" 2>/dev/null || true
sentinel-state setup --root "$PWD" || true

echo "======================================================================"
echo "🔧 3EAI-SDLC: MAINTENANCE MODE"
echo "======================================================================"
echo ""
"$E3E_ROOT/guidelines/load_phase_context.sh" maintenance "$PWD" || exit $?
echo ""
echo "======================================================================"
echo "🤖 AGENT READY FOR MAINTENANCE. FOLLOW THE GUIDELINES STRICTLY."
echo "======================================================================"
```

## Maintenance Mode

Post-deployment operational mode for ongoing system maintenance.

### Maintenance Types
1. **Corrective** — Bug fixes (P1-P4 severity)
2. **Adaptive** — Changes for new environments, integrations, or regulations
3. **Perfective** — Performance improvements, UX enhancements
4. **Preventive** — Tech debt reduction, refactoring, dependency updates

### Rules
- **[REQUIRED]** Every fix must have a root cause analysis
- **[REQUIRED]** Every change must have tests
- **[REQUIRED]** Follow existing code patterns, per the guidelines the preamble printed: CORE_MAINTENANCE and CORE_DEBUGGING in a Core project (or the free edition), else CODING_GUIDELINES and its companions
- **[REQUIRED]** Human approval before deploying to production

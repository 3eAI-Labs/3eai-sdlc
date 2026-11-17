# 3eAI SDLC Core — Setup

3eai-sdlc's hooks activate when you install the plugin in Claude Code; there is no
separate install step. This guide covers what it writes and the one thing you
switch on yourself: the gate.

## What activates

1. **Hooks** — `hooks/hooks.json` is read by Claude Code on startup. The five hook
   scripts (`pivot_interceptor`, `forced_rule_set_gate`, `inject_plan_anchor`,
   `auto_audit`, `side_effect_check`) run on the matching events.
2. **Stage gate** — Each hook checks `.sentinel/runtime/current_phase` and stays off
   outside its stages and modes (`hooks/_phase_policy.py`). The one exception: in a
   project with deliverables, the `3EAI-SDLC ROUTE` block names the skill to enter
   when the marker is missing, unknown or ahead of the project's stage.
3. **The stage marker** — A stage skill's first line, `sentinel-state enter <stage>`,
   checks the project has reached the stage and writes the marker; `/maintenance`
   writes its own.

The hooks run a bare `python3` (Python 3.9 or newer; the smoke tests pass on 3.9 to 3.14), so `python3` must be on
`PATH`. `side_effect_check` also runs `git` and reports nothing when `git` is
missing. The hooks have been run on Linux; macOS and native Windows are not
verified. Below the minimum Python the hooks fail without a notice.

## Per-project `.gitignore`

3eai-sdlc writes these lines itself. When a stage or mode starts in a project that
is a git work tree, `sentinel-state` appends to the project's `.gitignore` the
lines below that it lacks, once, and prints which ones it added:

```gitignore
# 3eAI SDLC runtime state — per-session, never commit
.sentinel/runtime/audit_log.json
.sentinel/runtime/audit_findings_pending.json
.sentinel/runtime/hook_errors.jsonl
.sentinel/runtime/warden_decisions.jsonl
.sentinel/runtime/current_phase
.sentinel-control/approve.token
.sentinel/runtime/root_cause.token
.sentinel/runtime/phase5_handoff.md

# These ARE intended to be committed:
#   .sentinel/flow                           (the project's flow)
#   .sentinel-control/forced_rule_set        (opt-in marker)
#   .sentinel-control/destructive_patterns.json  (project gate rules)
```

`.sentinel/runtime/side_effect/` needs no line: it ignores itself.

## Switching the gate on

The gate that stops destructive commands is off until you switch it on. Run, yourself,
in the project:

```bash
<plugin_root>/bin/sentinel-lock --on     # then restart Claude Code
```

`<plugin_root>` is the folder `sentinel-root` prints in a Claude Code session.
`sentinel-lock --on` creates `.sentinel-control/forced_rule_set` and makes
`.sentinel-control/` unwritable by the agent through the project's
`.claude/settings.json` (the OS sandbox and a permission rule). `sentinel-lock --check`
reports what is missing, and fails while `.claude/settings.local.json` or your
`~/.claude/settings.json` undoes it.

With the gate on, in the build, design and release stages and in `/maintenance`, a
command that matches a destructive rule (for example `rm -rf /`, a force-push to a
protected branch, `DROP TABLE`) is denied; outside them you are asked. An outward
command (`git push`, `scp`, a package publish, a `gh` post, mail) asks you in every
stage.

The rules ship in `.claude-plugin/runtime/destructive_patterns.json`. You can add
layers: `~/.sentinel/destructive_patterns.json` (yours) and
`.sentinel-control/destructive_patterns.json` (the project's). A later layer adds
rules or changes fields by `id`; `{"id": "outward-git-push", "level": "off"}` in your
layer switches a rule off. Only your layer may change a rule another layer
introduced.

To let one denied call through, run in a separate terminal:

```bash
echo ok > .sentinel-control/approve.token
```

The token is single-use and must not be empty.

## When a hook fails

A hook that fails lets the call through and records it: one row in
`.sentinel/runtime/hook_errors.jsonl` and a `HOOK_ERROR` flag on the next prompt.

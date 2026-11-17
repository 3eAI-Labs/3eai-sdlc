#!/usr/bin/env bash
# 3eAI SDLC phase-context loader (M3 — manifest-driven).
#
# Reads the project's GUIDELINES_MANIFEST.yaml, validates it, then streams the
# phase-relevant sections of every `enabled` guideline to stdout. `disabled`
# guidelines are never opened.
#
# Usage:
#   load_phase_context.sh <phase|mode|core stage> [project_root]
#   load_phase_context.sh guideline:<bucket>/<NAME>[:<N>] [project_root]
#   load_phase_context.sh list[:<bucket>] [project_root]
#
#   <phase>         One of: phase1 phase2 phase3 phase35 phase4 phase5 phase55 phase6 phase-review
#                   Manifest-driven, section-filtered (context isolation).
#   <mode>          One of: maintenance incident sprint retro review investigate ship cso
#                   agent-phase1 agent-phase2 agent-phase3 agent-phase4 agent-phase5
#                   agent-phase55 agent-phase6
#                   Fixed named-guideline profiles (MODE_PROFILES in load_phase_context.py), full-file
#                   (agent-phaseN: v4 files section-filtered as phaseN), NO manifest
#                   required. Replaces the old per-skill raw `cat` blocks (which
#                   failed silently on path drift — see commit c991ff3).
#                   maintenance review investigate ship retro load their short
#                   essentials texts instead (CORE_HELPER_PROFILES) when the
#                   project's flow is core or the plugin has no guidelines/core/.
#   <core stage>    One of: define design build release core-review
#                   The Core flow's texts from guidelines/essentials/ (CORE_PROFILES in
#                   load_phase_context.py), whole. NO manifest, no YAML, no layers.
#   guideline:<bucket>/<NAME>[:<N>]
#                   One guideline whole (the first N lines of its body when a limit
#                   is given), then its layer overlays in full. No manifest, no
#                   YAML. A skill that needs one guideline
#                   calls this; it never opens the file itself.
#   list[:<bucket>] The names a manifest can enable, one `<bucket>/<NAME>` per
#                   line: the plugin's, then those a layer adds, tagged with the
#                   layer. No manifest, no YAML.
#   [project_root]  Defaults to $PWD (the project the user is operating on).
#   No argument writes the phase marker: the phase skill writes it.
#
# Exit codes:
#   0   success
#   2   invalid arguments
#   3   manifest missing / malformed / validation failed; a single guideline no file has
#   4   internal error (missing guideline file after validation; the plugin's
#       guidelines directory missing)
#   5   the release package's Python version check failed (python3 missing or
#       not the version its bytecode was built for; the notice says which)
#
# Environment:
#   CLAUDE_PLUGIN_ROOT   Path to the 3eai-sdlc plugin root. Auto-derived if unset.
#   SENTINEL_DEBUG       If set to 1, emit extra diagnostics to stderr.
#   SENTINEL_USER_DIR    The user directory of the guideline layers. Unset or
#                        empty: ~/.sentinel. Moves the guideline layer only; the
#                        gate's rule layer (hooks/rule_layers.py) has its own lookup.
#
# Layers (MANIFEST_SCHEMA.md §10), lowest to highest:
#   plugin   <plugin_root>/guidelines/<bucket>/<NAME>.md
#   user     <user dir>/guidelines/<bucket>/      added guidelines and overlays
#   project  <project_root>/docs/01_product/guidelines/<bucket>/   the same
# A layer adds a guideline (<NAME>.md, a new name) or adds to one of a lower
# layer (<NAME>.overlay.md, printed after its target). It never replaces one.

set -euo pipefail

PHASE="${1:-}"
PROJECT_ROOT="${2:-$PWD}"

if [[ -z "$PHASE" ]]; then
  echo "usage: $(basename "$0") <phase|mode|core stage|guideline:<bucket>/<NAME>[:<N>]|list[:<bucket>]> [project_root]" >&2
  exit 2
fi

LOADER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$LOADER_DIR")}"
GUIDELINES_DIR="$PLUGIN_ROOT/guidelines"
MANIFEST_PATH="$PROJECT_ROOT/docs/01_product/GUIDELINES_MANIFEST.yaml"

export PHASE PROJECT_ROOT GUIDELINES_DIR MANIFEST_PATH

exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/load_phase_context.py"

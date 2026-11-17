# 3eai-sdlc — 3eAI SDLC Core for Claude Code

3eai-sdlc gives Claude Code a simple way to build a project in four stages, each
written down, reviewed and approved by you: Define, Design, Build and Release. It
is meant for a developer working alone or in a small team. You say what you want
to build; 3eai-sdlc works out where the project is and asks you only project
questions.

## The four stages

| Stage | What Claude writes with you | Where |
|-------|-----------------------------|-------|
| Define | the goal, the users, the features and their acceptance criteria | `docs/01_product/REQUIREMENTS.md` |
| Design | the stack, the components, the data, the interfaces and the decisions | `docs/03_architecture/DESIGN.md` |
| Build | working code and tests, and a build report | the source tree, `docs/05_implementation/BUILD_REPORT.md` |
| Release | a version that runs, how it is deployed and how it is rolled back | `docs/06_deploy/RELEASE.md` |

Each stage ends with a review (`/3eai-sdlc:phase-review <stage>`, a fresh-context
reviewer) and your approval, recorded next to the document (`DEFINE_GATE.md` …). A
stage starts only after the one before it is approved.

Alongside the stages: `/maintenance` (fix or improve a running project),
`/investigate` (find the cause of a bug before fixing it), `/review` (check a change
before it lands), `/ship` (test, version, commit and, on your go-ahead, push),
`/retro` (look back at a stretch of work), and `/guard` and `/freeze` (edit safety).

## Getting started

Install 3eai-sdlc from Claude Code's plugin directory (the `/plugin` command), open
your project, and say what you want to build. For example:

1. "Start a new project: a command-line to-do app that keeps its list in a local file."
2. "I want a small web page where my club's members can book the tennis court."
3. "The CSV export of my invoicing tool drops the last row; find out why and fix it."

In a new project 3eai-sdlc records the flow in `.sentinel/flow` and starts with
Define. You do not need to know its stages or commands.

## What 3eai-sdlc runs, reads and writes

- Its hooks run `python3` and `git` on your machine, inside the project.
- The hooks read the current session's transcript, to check the turn they follow.
- It writes its state under `.sentinel/` in the project, and adds its per-session
  runtime files to the project's `.gitignore` when the project is a git work tree.
  `.sentinel/flow` and the gate and review files next to the documents are meant to
  be committed.
- It reads gate rule layers you add yourself, under `~/.sentinel/` and
  `.sentinel-control/`.
- The gate that stops destructive commands is off until you switch it on with
  `sentinel-lock --on` (run it yourself: `<plugin_root>/bin/sentinel-lock --on`, where
  `<plugin_root>` is what `sentinel-root` prints in a Claude Code session; then restart
  Claude Code). `sentinel-lock` writes `.sentinel-control/` and the project's
  `.claude/settings.json`, and reads your `~/.claude/settings.json`.
- `/ship` runs `git push` and `gh pr create` only after your go-ahead.
- 3eai-sdlc fetches nothing, and sends nothing to 3EAI.

## Requirements

- Claude Code.
- `python3` on `PATH`, Python 3.9 or newer (its smoke tests pass on 3.9 to 3.14; on an older
  Python the hooks fail without a notice).
- `git`, for the hooks that compare files and for the project's `.gitignore`.
- 3eai-sdlc has been run on Linux; macOS and native Windows are not verified.

## Editions

This is the free edition of 3eai-sdlc. 3eAI SDLC Pro, from 3EAI, adds the enterprise
flow (eight phases for several teams and regulated work, with detailed engineering
guidelines) and more runtime checks. A project built with this edition opens in Pro
unchanged: the same documents, the same gate records and the same hooks. Install one
edition, not both.

## Licence

The 3EAI Labs Proprietary Licence (`LICENSE`): the free edition may be used at no
charge; redistribution and modification are not allowed.

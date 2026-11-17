# 3eai-sdlc — 3eAI SDLC Core for Claude Code

3eai-sdlc gives Claude Code a simple way to build a project in four stages, each
written down, reviewed and approved by you: Define, Design, Build and Release. It is
meant for a developer working alone or in a small team. You say what you want to
build; Claude works out where the project is and asks you only project questions.

## The four stages

| Stage | What Claude writes with you | Where |
|-------|-----------------------------|-------|
| Define | the goal, the users, the features and their acceptance criteria | `docs/01_product/REQUIREMENTS.md` |
| Design | the stack, the components, the data, the interfaces and the decisions | `docs/03_architecture/DESIGN.md` |
| Build | working code and tests, and a build report | the source tree, `docs/05_implementation/BUILD_REPORT.md` |
| Release | a version that runs, how it is deployed and how it is rolled back | `docs/06_deploy/RELEASE.md` |

Each stage ends with a review by a fresh-context reviewer, which writes
`<STAGE>_REVIEW.md`, and with your approval, recorded next to the document
(`DEFINE_GATE.md` …). A stage starts only after the one before it is approved. You
can also ask for a review yourself: `/3eai-sdlc:phase-review <stage>`.

## Install

From Claude Code's plugin directory (the `/plugin` command), or from this repository:

```
claude plugin marketplace add 3eAI-Labs/3eai-sdlc
claude plugin install 3eai-sdlc@3eai-open
```

Then open your project and say what you want to build.

## Example prompts

1. "Start a new project: a command-line to-do app that keeps its list in a local file."
2. "I want a small web page where my club's members can book the tennis court."
3. "The requirements are approved; design the app."

## What it reads and writes

This plugin is Markdown only: five skills, one reviewer agent and five short
guidelines. It has no hooks, no scripts and no server. Claude writes the project's
documents, `.sentinel/flow` (the project's flow, `core`) and the review and approval
files next to the documents, and runs the project's tests in the Build and Release
stages; Claude Code asks you before each write and each command. It sends nothing to
3EAI. `.sentinel/flow` and the review and approval files are meant to be committed.

## Privacy

3eAI SDLC Core is Markdown only: it runs no code of its own, collects no data, and sends
nothing to 3EAI Labs or anyone else. What it writes (the stage documents, the review
reports and the approval records, which hold the approver's name or role as you enter
it) stays in your project's files on your machine. Claude Code's own handling of your
data is governed by Anthropic's terms.

## 3eAI SDLC Pro

3eAI SDLC Pro adds the enterprise flow (eight phases for several teams and regulated
work, with detailed engineering guidelines) and runtime checks that hold the flow in
place. A project made with this plugin opens in Pro with its documents and approvals.
Install one of the two, not both. Details and download: https://3eai-labs.org

## Licence

Apache License 2.0 (`LICENSE`).

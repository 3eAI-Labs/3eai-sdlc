---
name: CORE_SHIP
title: Ship — Test, Version, Commit, Push
flow: core
---

# Ship — Test, Version, Commit, Push

## Purpose

Turn finished work into a commit (and, when the user wants it, a push or a pull request) that is tested, versioned and described.

## Rules

1. Run the whole test suite first. Ship nothing on a failing or unrun suite; report the result as printed.
2. Review the diff before committing (CORE_REVIEW). Fix every finding that must be fixed before landing.
3. Check that no secret, key, password, local configuration or generated file is staged.
4. Bump the version where the project keeps it, by the project's own scheme; when the project has none, ask the user which to use.
5. Add a changelog entry (when the project keeps one): what changed for the user, in plain words.
6. Write a commit message that says what changed and why. One commit per change; do not mix unrelated changes.
7. Push, open a pull request, publish or deploy only with the user's go-ahead for that action. Name the branch and the remote first.
8. After a push, report what was pushed (branch, commit) and any check the remote runs.

## Review checklist

- [ ] The whole suite passed in a run before the commit.
- [ ] The diff was reviewed, and its must-fix findings are fixed.
- [ ] No secret or local file is committed.
- [ ] The version and the changelog are updated where the project keeps them.
- [ ] The commit message says what and why.
- [ ] Nothing left the machine without the user's go-ahead.

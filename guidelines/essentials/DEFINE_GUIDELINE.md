---
name: DEFINE_GUIDELINE
title: Define — Requirements
flow: core
---

# Define — Requirements

## Purpose

Turn the user's idea into requirements that the design and the tests can be checked against.

## What to produce

`docs/01_product/REQUIREMENTS.md`, with these sections:

1. **Goal**: the problem and the outcome, in a few sentences.
2. **Users**: who uses it, and what each of them needs from it.
3. **Features**: each one a short story with acceptance criteria:

   ```markdown
   ### F-01 <name>
   As a <user>, I want <capability>, so that <benefit>.
   Acceptance criteria:
   - Given <context>, when <action>, then <observable result>.
   Priority: must | should | could
   ```

4. **Non-goals**: what this project will not do.
5. **Constraints**: platforms, languages or services that are fixed; personal or sensitive data; legal or licence requirements the user names.
6. **Open questions**: what is not decided yet, and who decides it.
7. **Changes**: later edits, each with its date and reason.

## Rules

1. Ask before writing: the goal, the users, what each user does, what must never happen, and what is already fixed. Ask a few questions at a time; offer an example answer when the user is unsure.
2. Write only what the user said or confirmed. A requirement the agent inferred is marked "(proposed)" until the user confirms it.
3. Each feature gets an ID (`F-01`, `F-02`, …) that the later stages cite.
4. Each acceptance criterion is observable: a tester can say pass or fail without asking anyone. Replace words such as "fast", "easy" or "secure" with what the user would see or measure; when the user gives no value, put the question under Open questions.
5. Mark as `must` only the features the first release needs.
6. Name personal or sensitive data explicitly (what it is, whose it is), so that Design can protect it.
7. Do not choose technology here unless the user has fixed it; that is Design's work.
8. No placeholder text: a section with nothing in it says "None" and why.

## Review checklist

- [ ] Goal, Users, Features, Non-goals, Constraints and Open questions are present.
- [ ] Every feature has an ID, a story, at least one acceptance criterion and a priority.
- [ ] Every acceptance criterion is observable and testable.
- [ ] No requirement the user did not state or confirm, except those marked "(proposed)".
- [ ] Personal or sensitive data is named, or "None" is stated.
- [ ] No technology choice the user did not fix.
- [ ] Features, non-goals and constraints do not contradict each other.

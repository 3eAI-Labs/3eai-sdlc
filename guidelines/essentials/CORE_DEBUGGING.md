---
name: CORE_DEBUGGING
title: Debugging — Finding the Cause
flow: core
---

# Debugging — Finding the Cause

## Purpose

Find why something fails before changing code, and fix the cause rather than the symptom.

## Rules

1. **Reproduce.** Make the failure happen on demand: a failing test, or a command with its exact output. Record the steps, the input, the expected result and the actual one. A failure that cannot be reproduced is reported as such, with what was tried.
2. **Isolate.** Narrow it down: the smallest input that still fails, the last version that worked, the component where the expected and the actual values first differ. Read the code on that path, not only the line in the error message.
3. **Hypothesise.** State one cause that explains every observation. Test it with a check that could prove it wrong (a log line, a probe, a smaller test). A hypothesis the check refutes is dropped, not patched over.
4. **Fix the cause.** Change the code where the cause is. Do not hide the symptom with a retry, a broader exception handler, a skipped test or a changed expectation.
5. **Keep the test.** The test that reproduced the failure stays in the suite and passes after the fix. Run the whole suite.
6. **Report.** Tell the user the cause, the evidence for it, the fix, and how it was checked. Mark what was not verified as a guess.
7. After three fixes that did not hold, stop and tell the user what is known; the problem may lie in the design.

## Review checklist

- [ ] The failure was reproduced, and the steps are recorded.
- [ ] The cause is named, with the evidence that confirms it.
- [ ] The fix changes the cause, not only the symptom.
- [ ] The reproducing test is in the suite and passes; the whole suite was run.
- [ ] Unverified claims are marked as guesses.

---
name: RELEASE_GUIDELINE
title: Release — Ship and Roll Back
flow: core
---

# Release — Ship and Roll Back

## Purpose

Ship a version that can be run or deployed, and undone.

## What to produce

`docs/06_deploy/RELEASE.md`, with these sections:

1. **Version**: the version number (semantic versioning, MAJOR.MINOR.PATCH) and the date.
2. **Contents**: the features (`F-NN`) and the fixes in this version.
3. **Pre-release checklist**: each item of rule 2 with its result and evidence.
4. **How to run or deploy**: the exact steps for the target (a package, a server, an app store, a static host).
5. **Rollback**: how to return to the previous version, and what happens to stored data.
6. **Known issues**: what does not work yet, with any workaround.

## Rules

1. Read `BUILD_REPORT.md` first; release only what was built and tested.
2. Run the pre-release checklist and record each result:
   - the full test suite passes in a clean environment;
   - no secrets in the repository or the release files;
   - dependencies are pinned, and the ecosystem's audit tool shows no unaddressed critical vulnerability;
   - the README says what the project does and how to install, configure and run it;
   - the licences of the project and of its dependencies allow the release.
3. Tag the release in version control with its version, and write the change list from the feature IDs.
4. Deploy, publish or push only with the user's go-ahead: they are outward actions.
5. Have a rollback before deploying: the previous version's artifact or tag, and a data backup when the release changes stored data.
6. After deploying, check that it runs (start it, call it, open it) and record the result.
7. A failed checklist item blocks the release unless the user accepts it; record that acceptance under Known issues.

## Review checklist

- [ ] The version and the contents are stated.
- [ ] Every pre-release item has a result and evidence.
- [ ] The deploy steps are exact and complete.
- [ ] A rollback exists.
- [ ] Known issues are listed, or "None" is stated.
- [ ] The release holds only built and tested features.

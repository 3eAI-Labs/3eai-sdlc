---
name: DESIGN_GUIDELINE
title: Design — How It Will Be Built
flow: core
---

# Design — How It Will Be Built

## Purpose

Decide how the requirements will be built, before code is written.

## What to produce

`docs/03_architecture/DESIGN.md`, with these sections:

1. **Overview**: the shape of the system in a few sentences and one diagram (Mermaid or text).
2. **Stack**: language, framework, storage and hosting; for each, why, and the alternative considered.
3. **Components**: each with its responsibility, the features (`F-NN`) it serves, and what it depends on.
4. **Data**: the entities and their fields, where they are stored, which are personal or sensitive, and how those are protected (access, encryption, how long they are kept, as the user decides).
5. **Interfaces**: the commands, endpoints, screens or messages, with their inputs, outputs and errors.
6. **Error handling**: what can fail (input, network, storage, third parties) and what the user sees for each.
7. **Decisions**: each significant choice, with its reason and the alternatives rejected.
8. **Risks**: what could make the design fail, and the mitigation.
9. **Test approach**: what is tested at which level (unit, integration, end to end), and how the acceptance criteria are checked.
10. **Open questions** and **Changes**.

## Rules

1. Read `REQUIREMENTS.md` first. Every `must` feature maps to at least one component; a component that serves no feature is removed or justified.
2. Choose the simplest design that meets the requirements: the fewest services and moving parts, and the stack the user already knows. Add a component only for a stated requirement.
3. Choose widely used, maintained, openly licensed dependencies, and record each one's licence. Ask the user before choosing a paid service.
4. State the security basics for this project: how users sign in (if they do), where secrets live (never in the code or the repository), how input is validated, and how sensitive data is protected.
5. Each interface states its error cases, not only its success path.
6. Do not write production code here; a short snippet that fixes the shape of an interface is fine.
7. A change the design needs in the requirements is proposed to the user, not made silently (CORE_WORKFLOW rule 4).

## Review checklist

- [ ] Every `must` feature is served by a named component.
- [ ] Each stack choice has a reason and an alternative.
- [ ] Personal or sensitive data has its protection stated.
- [ ] Secrets have a stated home outside the code.
- [ ] Every interface lists its errors.
- [ ] Every significant decision has a reason.
- [ ] Every risk has a mitigation.
- [ ] The test approach covers the acceptance criteria.
- [ ] Nothing in the design contradicts the requirements.

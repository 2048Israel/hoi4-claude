# TH1: the agent definitions

**Lane:** Offline, after OR1 and ST1. **Files:** `.claude/agents/hoi4-<role>.md`, one per role.

## Why

Jerus, 2026-11-07: "wouldnt it be more efficient of multiple agents play at once and take care of specific stuff?",
and 2026-11-09 the structure itself: one agent each for policy, air, navy, civilian, military and naval industry,
the army, one per field marshal, and a task agent per operation. `docs/command.md` is the design; this batch writes
the agents. (This replaces the 2026-11-07 version of TH1, which had four broader thinkers.)

## What

- Ten agent files: `hoi4-policy`, `hoi4-research`, `hoi4-civilian-industry`, `hoi4-military-industry`,
  `hoi4-naval-industry`, `hoi4-air`, `hoi4-navy`, `hoi4-army`, `hoi4-field-marshal`, `hoi4-operation`. Each, in at
  most 80 lines:
  - what it owns and what it must leave to others (the ownership table in `docs/command.md`);
  - its goals and how it is measured (air: superiority over our fronts; military industry: no equipment
    shortfall; field marshal: no lost states, ground gained; operation: its `success` sentence);
  - its doctrine: short, concrete rules for Germany 1936-1941, including the lessons in
    `docs/changelog.md` and `docs/command.md` (Why): every wing has a mission, no idle factories, both fronts
    covered before a declaration, never re-order an army that is still marching;
  - the ops it may give and the requests it may make (OR1), within its budget;
  - its input (its ST1 slice + notes, budget, requests, results) and its reply: one JSON object
    `{orders, requests, report, notes}`, nothing else;
  - one worked example: a short input and the reply it should give.
- `hoi4-field-marshal` and `hoi4-operation` are templates: TL1 starts one per army group and per operation, with the
  name and charter in the input.
- Model per agent in the file's frontmatter: the army tree on the strongest model, the others on a cheaper one.

## Done when

- The ten files exist, and each example reply passes OR1's validator.
- A short table in the PR: each agent, its model, and its example's input and output size.

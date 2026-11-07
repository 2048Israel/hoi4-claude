# OR1: the orders format

**Lane:** Offline. **Module:** `hoi4_orders.py`, `tests/test_OR1.py`.

## Why

Jerus, 2026-11-07, on the design: "a delegator agents that just receives tasks and executes, the interface, while the
others think". Thinker agents (TH1) decide; one executor (EX1) owns the mouse and keyboard. They need a shared,
checkable format between them, so a thinker never describes clicks and the executor never makes decisions.

## What

- One order per line, as JSON (JSON Lines), each with `op` plus its fields. A first set of ops, from what a turn needs
  (the PLAYBOOK's "first week" list):
  - `focus.start {focus}`, `research.start {slot, tech}`, `production.set {line, factories}`,
    `production.add_line {equipment}`, `construction.queue {building, state, count}`,
    `recruit.train {template, count}`, `politics.hire {advisor}`, `politics.law {category, law}`,
    `decision.take {decision}`, `time.advance {days}`.
- Every order also carries `by` (which thinker), `why` (one line, for the log), and optional `priority`.
- A validator: `validate(order) -> list[str]` of problems (unknown op, missing field, wrong type), and
  `load(path_or_text)`. Plain Python 3, no third-party packages, and no import of `hoi4.py` (so it tests anywhere).
- A merge step for one turn: orders from several thinkers into one list, with clear conflict rules. Examples: two
  orders for the same research slot; production asking for more factories than exist; political power spent twice.
  It reports conflicts; it does not guess.

## Done when

- `docs/orders.md` lists every op with an example line.
- `tests/test_OR1.py` covers valid orders, each kind of problem, and each conflict rule.
- Names of things (techs, focuses, equipment) are free strings for now. EX1 maps them to the screen; SR1 and the mod
  supply the real names.

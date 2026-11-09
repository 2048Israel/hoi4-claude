# OR1: the orders format

**Lane:** Offline. **Module:** `hoi4_orderspec.py`, `tests/test_OR1.py`.

> 2026-11-07 (PC session): `hoi4_orders.py` now exists on `main` and holds the standing army orders behind
> `act army push` (`plans/orders.txt`). Put the orders format in `hoi4_orderspec.py` instead, and leave
> `hoi4_orders.py` alone; `act army push` can later read the new format through it.

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

## Added 2026-11-09: the command structure (`docs/command.md`)

Jerus asked for one agent per branch (policy, air, navy, civilian, military and naval industry, army, a field
marshal per army group, and task agents for single operations). The format now has to carry four more things:

- **Requests:** an order addressed to an agent instead of the executor, with `to` (an agent name) and an
  `op` of the form `request.<kind>`: `request.equipment {equipment, amount}`, `request.divisions {count, template,
  theater}`, `request.air_support {region, mission, until}`, `request.construction {building, state}`,
  `request.ships {type, count}`, `request.research {tech}`.
- **Budgets:** a per-turn object `{agent: {pp, cp, civ_factories, mil_factories, dockyards, manpower}}`. The merge
  step refuses spending over an agent's budget.
- **Results:** for each executed order, `done`, `refused` (with the game's reason as text) or `failed`, keyed by an
  order id, so the issuing agent sees it next turn.
- **Operation charters:** `operation.start {name, goal, forces, success, abort, deadline}` and
  `operation.end {name, outcome}`. `success` and `abort` are plain sentences for now; TL1 decides how to test them.
- Ops the executor has today: `air.assign {base, mission, region}`, `air.rebase {base, to}`,
  `army.target {army, city}`, `army.front {army}`, `army.execute {army}`, `diplomacy.act {city, action}`,
  `construction.queue {building, count}`, `event.choose {title, option}`, besides the first list above.
- Every agent's reply is one JSON object `{orders, requests, report, notes}`. Validate that shape too.

## Done when

- `docs/orders.md` lists every op with an example line.
- `tests/test_OR1.py` covers valid orders, each kind of problem, each conflict rule, an over-budget spend, a
  request, a result, and an operation charter.
- Names of things (techs, focuses, equipment) are free strings for now. EX1 maps them to the screen; SR1 and the mod
  supply the real names.

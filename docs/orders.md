# Orders: the format between the agents and the executor

The thinking agents of [`command.md`](command.md) decide; one executor clicks. Everything they hand each other is
in this format: orders to the executor, requests to another agent, budgets, results, and operation charters. A
thinker never describes a click, and the executor never makes a decision.

The code is [`hoi4_orderspec.py`](../hoi4_orderspec.py): plain Python 3, standard library only, no import of
`hoi4.py`. Its tests are `tests/test_OR1.py`, which also checks every example on this page.

```
python hoi4_orderspec.py check FILE [--agent NAME]   validate an orders file (JSON Lines) or one agent reply
python hoi4_orderspec.py ops                          every op, its fields, and who may give it
```

## An order

One JSON object per line (JSON Lines). Blank lines and lines starting with `#` or `//` are skipped.

| Field | | What |
|---|---|---|
| `op` | required | What to do, from the lists below |
| the op's fields | required unless marked optional | See each op |
| `by` | required | The agent giving it (names below) |
| `why` | required | One line for the turn log, at most 200 characters |
| `priority` | optional | 1 runs first, 9 last; 5 when left out. A `time.advance` always runs last |
| `id` | optional | Letters, digits and `. _ : -`. The merge gives one when it is missing: `t<turn>.<agent>.<n>` |
| `cost` | optional, required for laws, advisors and decisions | What it spends: `{"pp": 150}`, any of `pp`, `cp`, `civ_factories`, `mil_factories`, `dockyards`, `manpower`. `{}` when free |

Any other field is a problem, so a misspelt field is caught before the executor sees it.

Field kinds: **text** is one non-empty line; **whole number** excludes `true`/`false`; a **ref** is a number from 1
or a text (a production line by its number or its header); a **date** is `YYYY-MM-DD`. Names of things (techs,
focuses, equipment, advisors, states, cities, regions) are free text for now: the executor (EX1) finds them on the
screen, and the save reader (SR1) and the mod supply the real names. Air missions are the executor's:
`superiority`, `cas`, `interception`, `strategic`, `naval`, `port`, `logistics`, `supply`, `recon`.

## Agents

`supreme_command`, `policy`, `research`, `civilian_industry`, `military_industry`, `naval_industry`, `air`, `navy`,
`army`, and one `field_marshal_<x>` per army group and `operation_<name>` per operation (lower case, digits, `_`).
An agent file is the name with hyphens: `.claude/agents/hoi4-civilian-industry.md`, and the two templates
`hoi4-field-marshal.md` and `hoi4-operation.md` (TH1).

Each op says who may give it. Supreme Command may give any op; it alone advances time. An op from anyone else is
held as an `owner` conflict (below).

## Ops for the executor

| Op | Fields | Who | The executor today |
|---|---|---|---|
| `focus.start` | `focus` | policy | `act focus --name` |
| `research.start` | `slot` (number), `tech`; optional `replace` (true: replace what the slot researches now) | research | `act research --slot --tech [--replace]` |
| `production.set` | `line` (ref), `factories` (whole number, the line's new total); optional `dockyards` (true: a naval line) | military_industry, naval_industry | `act production --line/--name --add/--remove`; dockyard lines: EX4 |
| `production.add_line` | `equipment`; optional `factories`, `dockyards` | military_industry, naval_industry | none yet |
| `construction.queue` | `building`, `count`; optional `state` | civilian_industry | `act build --building --count`; in a named state: EX6 |
| `recruit.train` | `template`, `count` | army | `act recruit --count --template` |
| `politics.hire` | `advisor`; optional `slot` (as `read ideas` names it: `advisor-3`, `staff-6`, `research-2`); needs `cost` | policy | `act idea --slot --name` |
| `politics.law` | `category` (`conscription`, `trade`, `economy`), `law`; needs `cost` | policy | `act idea --slot law-<category> --name` |
| `decision.take` | `decision`; needs `cost` (`pp` or `cp`) | policy, army, air, navy | `act decision --name` |
| `time.advance` | `days` | supreme_command | `advance` |
| `air.assign` | `base`, `mission`, `region`; optional `wing` (one wing, else every wing at the base) | air | `act air assign --base [--wing] --mission --region-name` |
| `air.rebase` | `base`, `to` (the new base); optional `wing` | air | `act air rebase --base --to X Y [--only]` |
| `army.target` | `army` (number), `city` | army, field_marshal_\*, operation_\* | `act army target --army --city` |
| `army.front` | `army`; optional `against` (the country across the border) | army, field_marshal_\*, operation_\* | `act army front --army --at X Y` |
| `army.execute` | `army` | army, field_marshal_\*, operation_\* | `act army execute --army` |
| `diplomacy.act` | `city` (one of the target country's), `action` | policy | `act diplomacy --city --action` |
| `event.choose` | `title`, `option` (its number from 1, or its text) | policy | `act event --option` |

Where the executor needs a screen point (a region, a border, a base icon), it finds it from the name; the agent
never gives one. An op with no executor command yet is reported back as `failed` with "no executor command", and
the tool is built before the next turn (`command.md`, One turn).

```json
{"op": "focus.start", "focus": "Rhineland", "by": "policy", "why": "the next focus on the way to the Anschluss"}
{"op": "research.start", "slot": 2, "tech": "Improved Machine Tools", "by": "research", "why": "slot 2 is empty"}
{"op": "production.set", "line": 2, "factories": 6, "by": "military_industry", "why": "artillery short by 400 for the new divisions"}
{"op": "production.set", "line": "Bf 109", "factories": 10, "by": "military_industry", "why": "fighters for superiority in the west"}
{"op": "production.set", "line": "Submarine", "factories": 5, "dockyards": true, "by": "naval_industry", "why": "the navy asked for 12 submarines"}
{"op": "production.add_line", "equipment": "Ju 87", "factories": 3, "by": "military_industry", "why": "the air agent asked for close air support"}
{"op": "construction.queue", "building": "military_factory", "count": 8, "by": "civilian_industry", "why": "42 civilian factories idle"}
{"op": "construction.queue", "building": "land_fort", "count": 2, "state": "Baden", "by": "civilian_industry", "why": "the army asked for forts on the Rhine"}
{"op": "recruit.train", "template": "Infanterie-Division", "count": 10, "cost": {"manpower": 110000}, "by": "army", "why": "the eastern front needs 10 more divisions"}
{"op": "politics.hire", "advisor": "Walther Funk", "slot": "advisor-3", "cost": {"pp": 150}, "by": "policy", "why": "an empty advisor slot and 160 PP"}
{"op": "politics.law", "category": "economy", "law": "War Economy", "cost": {"pp": 150}, "by": "policy", "why": "more factories before the war"}
{"op": "decision.take", "decision": "War Propaganda", "cost": {"pp": 50}, "by": "policy", "why": "war support is under 50%"}
{"op": "time.advance", "days": 5, "by": "supreme_command", "why": "at war: 5 days a turn"}
{"op": "air.assign", "base": "Niederschlesien", "mission": "superiority", "region": "Western Poland", "by": "air", "why": "the Polish front has no air superiority"}
{"op": "air.assign", "base": "Holstein", "wing": "Kampfgeschwader 1", "mission": "cas", "region": "Western Poland", "priority": 2, "by": "air", "why": "operation warsaw asked for close air support"}
{"op": "air.rebase", "base": "Oberbayern", "to": "Niederschlesien", "by": "air", "why": "fighters closer to the Polish border"}
{"op": "army.target", "army": 3, "city": "Warsaw", "by": "operation_warsaw", "why": "the operation's goal"}
{"op": "army.front", "army": 1, "against": "France", "by": "field_marshal_west", "why": "the French border has no front line"}
{"op": "army.execute", "army": 4, "by": "field_marshal_east", "why": "the plan is at full planning"}
{"op": "diplomacy.act", "city": "Warsaw", "action": "Declare war", "by": "policy", "why": "Supreme Command set the war for today"}
{"op": "event.choose", "title": "The Anschluss", "option": 1, "by": "policy", "why": "the option that keeps world tension lower"}
```

## Requests

A request is an order to another agent instead of the executor: op `request.<kind>` and `to`, the agent it is for.
Anyone may ask; each kind goes to the agent that owns what is asked for. It reaches that agent in its next input,
and that agent spends its own budget to answer it, so a request has no `cost`. It is never sent to the executor.

| Op | Fields | To |
|---|---|---|
| `request.equipment` | `equipment`, `amount` | military_industry |
| `request.divisions` | `count`, `template`, `theater` | army, or a field_marshal_\* (an operation asking its field marshal) |
| `request.air_support` | `region`, `mission`, `until` (date) | air |
| `request.construction` | `building`, `state`; optional `count` | civilian_industry |
| `request.ships` | `type`, `count` | naval_industry |
| `request.research` | `tech` | research |

```json
{"op": "request.equipment", "to": "military_industry", "equipment": "infantry_equipment", "amount": 20000, "by": "army", "why": "16 new divisions"}
{"op": "request.divisions", "to": "army", "count": 6, "template": "Infanterie-Division", "theater": "west", "by": "field_marshal_west", "why": "the Westwall has two divisions a state and needs three"}
{"op": "request.divisions", "to": "field_marshal_east", "count": 2, "template": "Panzer-Division", "theater": "east", "by": "operation_warsaw", "why": "the breakthrough at Lodz stalled"}
{"op": "request.air_support", "to": "air", "region": "Western Poland", "mission": "cas", "until": "1939-09-20", "by": "operation_warsaw", "why": "the attack on the Narew line"}
{"op": "request.construction", "to": "civilian_industry", "building": "land_fort", "state": "Baden", "count": 2, "by": "army", "why": "the Rhine crossings have no forts"}
{"op": "request.ships", "to": "naval_industry", "type": "submarine", "count": 12, "by": "navy", "why": "convoy raiding in the Atlantic"}
{"op": "request.research", "to": "research", "tech": "Close Air Support", "by": "air", "why": "the Stuka line needs it"}
```

## Operation charters

An operation is a task agent with one goal (`command.md`, Operations). A field marshal (or the Army, for a
cross-theater task) starts it with a charter; the turn loop, not the executor, handles both ops: it starts
`operation_<name>`, tests `success` and `abort` from the snapshot each turn (TL1; plain sentences for now), and ends
it.

| Op | Fields | Who |
|---|---|---|
| `operation.start` | `name` (lower case, digits, `_`), `goal`, `forces` (a list), `success`, `abort`, `deadline` (date) | army, field_marshal_\* |
| `operation.end` | `name`, `outcome` | army, field_marshal_\*, operation_\* (only its own) |

```json
{"op": "operation.start", "name": "warsaw", "goal": "Take Warsaw", "forces": ["army 3", "army 4"], "success": "Warsaw is controlled by GER", "abort": "deadline passed, or the armies fall under 50% strength", "deadline": "1939-09-30", "by": "field_marshal_east", "why": "Poland's capital: its fall gives most surrender"}
{"op": "operation.end", "name": "warsaw", "outcome": "Warsaw taken on 1939-09-21; armies 3 and 4 back to the field marshal", "by": "field_marshal_east", "why": "the success test is true"}
```

## The reply

Every agent answers with one JSON object and nothing else: `orders` (for the executor, and operation charters),
`requests` (for other agents), `report` (at most three lines for Supreme Command and the turn log) and `notes` (its
plan for next time, at most 20 lines). Every order and request in it is `by` that agent. A reply may be wrapped in
one ```` ```json ```` fence; nothing else around it.

```json
{
  "orders": [
    {"op": "air.assign", "base": "Niederschlesien", "mission": "superiority", "region": "Western Poland", "by": "air", "why": "the Polish front has no air superiority"},
    {"op": "air.assign", "base": "Holstein", "mission": "cas", "region": "Western Poland", "priority": 2, "by": "air", "why": "operation warsaw asked for close air support"}
  ],
  "requests": [
    {"op": "request.equipment", "to": "military_industry", "equipment": "Bf 109", "amount": 200, "by": "air", "why": "two fighter wings are under half strength"}
  ],
  "report": "Superiority over Western Poland 40% and rising. CAS over the Narew attack. Short of 200 fighters.",
  "notes": "Keep superiority over Western Poland until Warsaw falls.\nThen move the fighters west (Oberbayern)."
}
```

## Budgets

Supreme Command gives each agent, every turn, what it may spend: `{agent: {pp, cp, civ_factories, mil_factories,
dockyards, manpower}}`, numbers from 0. An agent or a resource left out has 0. Supreme Command has no budget.

```json
{"policy": {"pp": 150}, "army": {"cp": 40, "manpower": 120000}, "air": {"cp": 10}, "military_industry": {"mil_factories": 28}, "naval_industry": {"dockyards": 10}, "civilian_industry": {"civ_factories": 35}}
```

What an order spends is its `cost`, plus, for `production.set` and `production.add_line`, its `factories`
(military factories, or dockyards with `"dockyards": true`). Laws, advisors and decisions must give a `cost`, so that
political and command power can be checked at all; the price is in the agent's state slice (ST1).

## Results

After the executor runs a turn, each order has one result, keyed by its id, and each agent's next input carries
its own (`results_for`). `reason` is required except for `done`.

| Status | Meaning |
|---|---|
| `done` | The executor did it, and its check passed |
| `refused` | The game said no; `reason` is the game's text |
| `failed` | The executor could not do it: a check failed, or there is no executor command yet |
| `dropped` | Never run: the order was invalid, or held for a conflict and not kept by Supreme Command |

```json
{"t12.research.1": {"status": "done", "by": "research", "op": "research.start"}, "t12.policy.2": {"status": "refused", "reason": "Requires 150 political power", "by": "policy", "op": "politics.law"}, "t12.air.1": {"status": "failed", "reason": "the cas button did not arm", "by": "air", "op": "air.assign"}, "t12.army.3": {"status": "dropped", "reason": "held for same_target; not kept by supreme_command", "by": "army", "op": "army.target"}}
```

## The merge step

`merge(replies, budgets, available, operations, turn)` turns one turn's replies (`{agent: reply}`) into one list
for the executor (`command.md`, One turn, step 6):

1. Every order and request gets an id, if it has none: `t<turn>.<agent>.<n>`, with n counting the reply's orders,
   then its requests, from 1.
2. Invalid ones are **dropped**, with the problems as the reason. Problems with a reply as a whole (a missing
   `report`, a report of five lines) are listed but drop nothing.
3. Valid requests go to their recipient (`requests`), for its next input.
4. The rules below find **conflicts**. Every order in a conflict is **held**, all of them: the merge never guesses
   which one should win. Supreme Command answers with `settle(merged, keep)`: the held orders it keeps run, the
   rest are dropped.
5. The rest are **ready**, in run order: by `priority`, then as the replies gave them, a `time.advance` last.

| Rule | Held when |
|---|---|
| `same_target` | Two orders for one research slot, one tech, one production line, the national focus, one law category, one advisor or advisor slot, one decision, one air base (unless each names a different `wing`), one army (`army.target` and `army.front`), one army's battle plan, one diplomatic action, one event, or one operation (two starts, or a start and an end); or two `time.advance` |
| `owner` | An agent gives an op that belongs to another (the "Who" columns), or an operation ends an operation other than itself |
| `over_budget` | An agent's orders together spend more of a resource than its budget gives it: all of that agent's orders spending it are held |
| `over_available` | All orders together spend more of a resource than the country has (`available`, same keys as a budget) |
| `budgets_over_available` | The budgets themselves give out more than the country has (nothing is held: it is Supreme Command's own mistake to fix) |
| `operation_active` | With `operations` (the running charters by name): an `operation.start` for one already running |
| `operation_unknown` | An `operation.end` for one that is neither running nor started this turn |
| `too_many_operations` | A field marshal would run more than three operations at once |

## In Python

```python
import hoi4_orderspec as S
orders = S.load("state/turn/12/air.jsonl")          # or the text itself, or a list
problems = S.validate(orders[0])                     # [] when valid
problems = S.validate_reply(S.load_reply(path), agent="air")
merged = S.merge({"air": reply_air, "army": reply_army}, budgets=budgets, available=available,
                 operations=running, turn=12)
merged.orders, merged.held, merged.conflicts, merged.requests, merged.dropped, merged.problems
orders, dropped = S.settle(merged, keep=["t12.army.2"])
S.dump(orders, "state/turn/12/orders.jsonl")
results = {o["id"]: S.result(o, "done") for o in orders}
S.results_for(results, "air")
```

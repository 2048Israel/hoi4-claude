# ST1: the state slicer

**Lane:** Offline, after SR1. **Module:** `hoi4_slices.py`, `tests/test_ST1.py`.

## Why

Each agent in `docs/command.md` should see only its own area, both to stay focused and to keep its input small
(cost). And no agent may see more than a human player could: the save holds every enemy unit.

## What

- `slices(snapshot, bridge_state) -> {agent: dict}` for the agents `policy`, `research`, `civilian_industry`,
  `military_industry`, `naval_industry`, `air`, `navy`, `army`, `field_marshal:<name>`, `operation:<name>`.
  `snapshot` is SR1's `extract()` output; `bridge_state` is what `hoi4.py state` parses from the log.
- What each slice holds (start here, trim by measuring):
  - policy: political power and its rate, stability, war support, the running focus, laws in force, advisors,
    wars, factions, neighbors.
  - research: slots (tech, days left), the year, researched techs (for prerequisites).
  - civilian_industry: civilian factories (used, free, consumer goods), the construction queue, free building
    slots per state, resource balances.
  - military_industry / naval_industry: their production lines (equipment, factories, efficiency), stockpiles,
    what the army wants (the bridge's `equip` lines).
  - air: wings (type, size, base, mission, region), bases with capacity, the regions of every front.
  - navy: fleets and task forces (ships, mission, region, port), convoys.
  - army: divisions by template and army, the training queue, templates, manpower, armies and their generals.
  - field_marshal / operation: only their armies' divisions (location, strength, organization), the provinces on
    their fronts, and the enemy units next to them.
- **Fog of war:** our country in full; an enemy only as the game shows it to the player: per country the division
  and factory counts (the bridge already reports these), and enemy divisions only in provinces adjacent to one of
  ours. Province adjacency is in the game's `map/adjacencies.csv` and `map/definition.csv` (read at run time from
  `GAME_DIR`, never committed); the tests use a tiny handmade map.
- A size check: print each slice's size in characters; aim for under 8,000 each.

## Done when

- `tests/test_ST1.py` builds every slice from the SR1 fixture plus a handmade bridge state, and checks that an enemy
  unit two provinces away is not in any slice.

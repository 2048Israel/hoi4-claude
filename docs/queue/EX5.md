# EX5: army structure in the executor

**Lane:** PC. **Module:** `hoi4_army.py`, `tests/test_EX5.py`.

## Why

The command structure (`docs/command.md`) has one agent per field marshal, so the game needs army groups with field
marshals, and the Army agent must be able to move divisions between armies. Today `act army new` is unsafe: on
1939-08-25 it twice took 12-16 divisions out of existing armies although only loose divisions were selected.

## What

- `read armies`: army groups, their field marshals, their armies and generals, division counts (cards plus the
  report's `general` lines).
- `act army group new --armies 1,2`, `act army group marshal --group N --name NAME`.
- A safe way to form an army: select the divisions by name in the selection panel (or by a box that the panel
  confirms holds only unassigned ones), then create the army, and refuse unless every other army's size is
  unchanged. Find out what New Army actually takes (the theater? 24 divisions?) and write it down in PLAYBOOK.md.
- `act army transfer --from N --to M --count K` (or by division names).
- `read templates` (names and battalions) and `act template copy/edit` later, if the Army agent needs it.
- Fix `act fix-queue`: it sets one deploy location per run, because at the standard camera Germany sits under the
  recruit panels. Pan the map first, or pick the province through the location list.

## Done when

- Checked live: an army group with a field marshal made from two armies; one army formed from loose divisions with
  every other army's size unchanged; a queue of 20 lines all given locations in one run.

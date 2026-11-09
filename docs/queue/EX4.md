# EX4: navy and dockyards in the executor

**Lane:** PC. **Module:** `hoi4_navy.py`, `tests/test_EX4.py`.

## Why

The Navy and Naval industry agents (`docs/command.md`) have no executor commands at all: in the campaign so far the
fleet and the dockyards were never touched.

## What

- `read navy`: fleets and task forces with their ships, mission, region and port (the naval overview, `p`).
- `act navy mission --fleet NAME --mission patrol|strike|convoy-escort|convoy-raid|minelaying|... --region X Y`, and
  `act navy port --fleet NAME --port CITY`. Confirm each by reading the fleet's mission back.
- Dockyard lines: `read production --dockyards` and `act production --dockyards --name ... --add/--remove`
  (the production screen's naval tab), plus a new line for a ship type.
- Follow the EX1 pattern: open by hotkey, check by OCR, act, confirm, close; stop with a message when a check fails.

## Done when

- Checked live: one task force given a mission, one dockyard line changed, both read back.

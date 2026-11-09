# EX6: trade and named construction in the executor

**Lane:** PC. **Module:** `hoi4_trade.py` and `hoi4_build.py`, `tests/test_EX6.py`.

## Why

The Civilian industry agent (`docs/command.md`) owns trade and construction. Resource shortfalls (rubber and
tungsten ran negative in 1940) were never answered, and `act build` can only pick the states with the most free
slots, not a state an agent names (forts on a border, an air base near a front).

## What

- `read trade`: resources (produced, used, imported, exported) and the trade deals in force.
- `act trade import --resource rubber --from COUNTRY [--amount N]`, and `act trade cancel`.
- `act build --building land_fort --state Baden`: find the state by name (Find window or the state's label on
  the construction map), click it, and check the queue grew by one line for that state.

## Done when

- Checked live: one import deal made and read back; one fort queued in a named state.

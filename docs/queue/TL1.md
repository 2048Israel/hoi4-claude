# TL1: the turn loop

**Lane:** PC, after OR1, ST1 and TH1. **Files:** `tools/turn.py`, `docs/turn.md`, `tests/test_TL1.py`.

## Why

This puts `docs/command.md` to work: the agents think, the executor clicks, and Supreme Command (the orchestrating
Claude session) settles what they cannot.

## What

- `tools/turn.py prepare`: pause; save `claude_state`; SR1 + ST1 into one input file per agent that is due
  (`state/turn/<n>/<agent>.json`), with budgets, requests and results; print which agents are due, in phases A
  (army tree), B (air, navy), C (industries, research, policy). Triggers decide who is due besides the cadence.
- The session runs each phase's agents in parallel (one message, several Agent calls, each pointed at its input
  file) and writes each reply to `state/turn/<n>/<agent>.out.json`.
- `tools/turn.py apply`: validate and merge (OR1), list conflicts for the session to settle, execute the orders in
  priority order through `hoi4_actions` / `hoi4_air` / ..., record each result, route requests into next turn's
  inputs, update `state/agents/<agent>.md` with each agent's notes.
- `tools/turn.py advance --days N`, and an operation's `success` / `abort` test from the next snapshot.
- `docs/turn.md`: the loop step by step, the cadence table, and what a turn costs.

## Done when

- One game month at war played with the loop from `claude_ger_1939_08_25_westwall`, compared with the single-player
  replay of the same dates (surrender progress, factories, losses), and the measured cost per turn in agent calls
  and tokens written in `docs/turn.md`.

# TH1: the thinker agents

**Lane:** Offline, after OR1. **Files:** `.claude/agents/hoi4-<role>.md`, `docs/turn.md`.

## Why

Jerus, 2026-11-07: "wouldnt it be more efficient of multiple agents play at once and take care of specific stuff?"
Each thinker reads the same paused-game state and returns orders for its own area, in parallel. The orchestrator
merges them (OR1's merge step) and the executor carries them out (EX1).

## What

- Four subagent definitions, each a Claude Code agent file with a short system prompt:
  - **economy:** production lines, construction, trade.
  - **research and focus:** research slots, the national focus.
  - **politics and diplomacy:** laws, advisors, decisions, diplomacy.
  - **military:** templates, recruiting, and later fronts (fronts need SR1's division locations).
- Each takes the state as JSON (`hoi4.py state` today, SR1's snapshot later) and returns only OR1 orders, each with a
  one-line `why`. No clicks, no coordinates, no screenshots.
- Shared budgets go in the turn's input, so thinkers do not spend the same thing twice: the political power each may
  spend, free factories, free research slots.
- `docs/turn.md`: one turn, step by step. Pause; snapshot; run the thinkers in parallel; merge and settle conflicts;
  execute; advance N days; repeat. Say what N should be in peace and in war.

## Done when

- The four agent files exist and each has one worked example: a short input and the orders it should give.
- `docs/turn.md` describes the loop and what one turn costs in agent calls.
- Remember that four thinkers per turn cost several times one player's tokens: keep their prompts and inputs short.

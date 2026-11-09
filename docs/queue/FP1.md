# FP1: the focus planner

**Lane:** Offline. **Module:** `hoi4_focus.py`, `tests/test_FP1.py`, a handmade fixture in `tests/fixtures/`.

## Why

In the 1939 replay (2026-11-08) no national focus ran for weeks: every name in `plans/focus_germany.txt` was done or
locked, and the list was guessed. The game's own focus files say exactly which focus needs which, so the Policy
agent (`docs/command.md`) can be given the focuses that can start now instead of a guessed list.

## What

- A parser for a focus tree file (Clausewitz script, the same syntax as saves; SR1's tokenizer can be shared). On
  Jerus's PC the German tree is `common/national_focus/germany.txt` under the game folder (`GAME_DIR` in
  `hoi4.py`): 38,933 lines, 438 `focus = { ... }` blocks. Per focus read:
  - `id`, `cost` (weeks: one cost point is 7 days), `x` / `y` and `relative_position_id` (layout only);
  - `prerequisite = { focus = A focus = B }`: one block = any one of them; several blocks = all of them;
  - `mutually_exclusive = { focus = X focus = Y }`;
  - `available = { ... }` and `bypass = { ... }`: game conditions the planner cannot test. Keep them as short text
    (the trigger names) so the agent can read what they ask, for example "has_government = fascism".
- `startable(tree, completed, current)` returns the focuses whose prerequisites are met, that are not completed,
  not running, and not excluded by a completed focus, each with its cost in days and its `available` text.
- Display names come from the localisation files (`localisation/english/*_l_english.yml`: `KEY:0 "Name"`), keyed by
  the focus id. Search all of them; several DLCs add German focuses.
- Mods can replace the tree: check the enabled mods (`dlc_load.json`, paths in the `.mod` descriptors) for a
  `common/national_focus/` file with focus ids for GER, and say which file won.
- A CLI: `python hoi4_focus.py --tree <file> --completed GER_a,GER_b [--current GER_c]`, and `--save <save>` to read
  `completed` and `current` from a save's `countries.GER.focus` block (SR0 found `current=`, `progress=` and repeated
  `completed="..."` there).
- No game files in the repo (`CLAUDE.md`, Standing rules): the tests use a small tree written by hand in the same
  syntax (five to ten focuses with OR and AND prerequisites and one exclusion). No import of `hoi4.py`.

## Done when

- `tests/test_FP1.py` covers OR vs AND prerequisites, exclusion, already completed, already running.
- The PR's "How to verify in the game" gives the CLI line for the real file and `claude_ger_1939_11_stop.hoi4`. The
  PC session checks the answer against the focus tree on screen, then wires `hoi4.py read focuses` and points
  `tools/war_rounds.py` at it instead of `plans/focus_germany.txt`.

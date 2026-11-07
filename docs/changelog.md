# Changelog

What shipped to `main`, newest first, under the version that shipped it. A batch adds its block at the top in the merge that ships it: a few lines
saying what changed and how it was checked.

# 0.1.0 (2026-11-07)

## 2026-11-07: SR0, a real text-save fixture

Jerus allowed text saves, so `save_as_binary=no` is set. Only that line changed; the old file is backed up in
`state/`. The game was restarted, which also loaded the mod's renamed `longest_war_months` field.

- **The fixture:** `tests/fixtures/ger_1936_02_25.txt`, 514 KB. It holds Germany on 1936-02-25 with the player name
  redacted, Germany's equipment designs, templates and states. It was cut by `tools/cut_save_fixture.py` in about
  12 s from a 66 MB text save (the binary save was 42.5 MB).
- **Guard:** `tests/test_SR0.py`.
- **For SR1:** its brief now says where research slots, the focus, production lines, divisions and states live in
  the file.

## 2026-11-07: working together

`AGENTS.md`, `CLAUDE.md`, `QUEUE.md` and `docs/queue/` set out how two Claude accounts work in parallel:
- when to branch;
- how to claim a batch;
- how a batch is handed to the PC session for the in-game check;
- the standing rules.

The queue proposes OR1, SR1 and TH1 for the offline lane, EX1, LV1 and PU1 for the PC lane, and SR0 pending on Jerus.

## 2026-11-07: focus fallback

`focus()` also tries an Alt tap and `SwitchToThisWindow` when Windows refuses `SetForegroundWindow`. That happened
while Jerus was typing in the Claude window. Checked live: the next command reached the game.

## 2026-11-07: the bridge

`hoi4.py`, the Claude Bridge mod, `PLAYBOOK.md` and the offline tests.

Checked in the live game (Germany, 1936): window focus, screenshots, clicks, hotkeys, the console report, pause,
resume, advance, and detecting whether the console is open.

The first campaign started: Germany, 1936, Regular, not Ironman.

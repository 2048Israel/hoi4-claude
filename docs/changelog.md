# Changelog

What shipped to `main`, newest first. A batch adds its block at the top in the merge that ships it: a few lines
saying what changed and how it was checked.

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

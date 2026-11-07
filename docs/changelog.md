# Changelog

What shipped to `main`, newest first, under the version that shipped it. A batch adds its block at the top in the merge that ships it: a few lines
saying what changed and how it was checked.

# 0.1.1 (2026-11-07)

## 2026-11-07: EX1, actions and readers without screenshots

`hoi4.py act ...` and `hoi4.py read ...` (`hoi4_actions.py`, positions in `ui_targets.json`) read the screen as text
with Windows' built-in OCR (`hoi4_ocr.py`, about 0.1-0.3 s a read) instead of returning a picture.

- **Readers:** research slots (tech and days), production lines (name, output, factories), the date, and the tech
  map.
- **Screens:** open and close by hotkey, confirmed by the screen's title.
- **Research:** found from the tech map and confirmed by the detail window's title. It handles the industrial
  organization picker, refuses a busy slot without `--replace`, and has a `--dry-run`.
- **Production:** factories +/- on lines 1-5, confirmed by the "Military Factories x/28" counter.
- **Saves:** `act save NAME` saves through the console, always as `claude_...`. `act load-save NAME` loads a save
  from the main menu, every step checked by OCR.
- **Tech map:** `act calibrate-research` clicks every icon once and reads its name, for all 9 tabs. Positions are
  kept in tree space, so they hold at any scroll:
  - Scrolling down is counted in exact 50 px wheel notches, with each tab's limit measured by matching pictures.
  - Scrolling sideways drags the bottom bar's knob, measured in (knob, offset) steps from labels that move with the
    tree. Trees open wherever they were left, so every action starts from the top-left.

**Checked live:**
- The tech map covers all 9 tabs: 499 techs, 1936 to the 1950s, with your mods' trees.
- Research dry runs pass on the furthest-right and the furthest-down tech of every tab (18 of 18): armor scrolls
  2,465 px down, and support and air about 2,600 px sideways.
- The busy-slot refusal; production line 2 at 3 → 2 → 3 factories; loading `claude_ger_1936` from the main menu
  with no screenshot.
- A research start that is not a dry run waits for the first free slot.

Windows OCR misses lone digits now and then, so a factory count may read `None`. The save reader (SR1) will give
exact numbers. EX2 has the rest of the actions.

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

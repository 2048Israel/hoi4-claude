# Changelog

What shipped to `main`, newest first, under the version that shipped it. A batch adds its block at the top in the merge that ships it: a few lines
saying what changed and how it was checked.

# Next (on main, not released yet)

- **Decisions:** `read decisions` lists every category and decision (scrolling the list, lining pages up by
  their shared rows); `act decision --name X [--dry-run]` finds a row, prints its tooltip and takes it, checked by
  the row's look and the political or command power spent; `act decision-category --name C --collapse|--expand`.
  Checked live on 1940-06-27: Utilize Domestic Film Industry, War Propaganda, Exhort Heroism, Collect Scrap Metal,
  Develop Ersatz Material (PP 1,235 -> 825) and Campaign Instructions against Poland (command power 160 -> 135).
  Radio Propaganda was refused (Radio not researched) and reported.
- **Tooltips anywhere:** `hover_tooltip` finds a tooltip by comparing the screen before and after the hover, so it
  works whether the tooltip opens above or below the cursor. `read pp` reads political power from the top bar.
- **act research-fill:** fills empty research slots from `plans/research_germany.txt`, skipping techs the game
  refuses. Checked live: five empty slots filled.
- **City orders say where they went:** `act army target` / `act order` print the target province's state, owner
  and controller from its tooltip. "Brest" found Brest in France, not Poland: two exact matches are now refused.
- **The console check waits for the screen to settle:** the focus tree fading out once read as an open console,
  and the report's text landed as hotkeys (it opened Construction and unpaused for an hour).
- **Screen titles** match word by word, since OCR can return them out of order ("EVENTS DECISIONS AND").

- **act army target --army N --city NAME:** orders an army at a city through the map's Find window, with
  no guessed pixels. Checked live: six armies sent at Warsaw, Lwów, Lublin, Białystok and Siedlce; all left
  their trenches (entrenchment 85% → under 15%) and joined combat.

- **read event / act event --option N:** events with choices, with each option's effects read from its tooltip.
  Checked live on "Draft Dodging" (three options with costs and odds).
- **act order --city NAME:** sends the selected divisions at a city; `tools/load_ingame.py` loads a save mid-game.
- **camera home is repeatable:** it zooms fully in before Go Home (which keeps the zoom), then out.
- **act army new is safer:** it refuses when army divisions are still selected, and reports if an existing army
  shrank. A box around Berlin once caught divisions of Armies 1-7; the campaign was reloaded both times.

# 0.1.2 (2026-11-07)

- **Notices:** "Research Finished!" and "National Focus Completed" notices sit on top of everything and catch
  clicks. Every `act` now closes them first, by their own Ok button; `act dismiss` does it alone.
- **Single-answer events:** an event with only one answer ("Excellent.") is taken automatically; events with
  two or more answers are left for a decision.
- **World News:** news popups (a headline and one answer button) also catch clicks; every `act` now closes
  them by their one answer. Events with several options are left open for a decision.
- **Production by name:** `act production --name "Bf 109" --add 10` finds any line by its header, scrolling the list.
- **Recruiting:** `act recruit --count N [--template NAME]` and `act fix-queue` replace `tools/queue_divisions.py`.
  Checked live: 15 infantry and 4 Panzer divisions queued at 1/1 with locations.
- **Focus:** `act focus --name NAME` and `read focus`. Checked live: refused starts reported their reasons
  (Zentrale Planung needs a war with a major power; Molotov-Ribbentrop needs Reorganize the Wehrmacht; Danzig or
  War needs Reassert Eastern Claims), and Reassert Eastern Claims started.
- **Armies:** `act army list|new|general|generals` and `act select-box`. Checked live: 75 loose divisions
  around Berlin made into Armies 1-4 (19, 14, 21, 21) under Rundstedt, Kluge, Rommel and Manstein.
  `act army front` gave all four a front line along the Polish border. `act army attack` drew their offensive arrows (toward Warsaw, Danzig and Kraków). War with Poland on 1939-06-26 (Britain and France
  joined); `act army execute` started all four plans, confirmed by entrenchment dropping and divisions in combat.
  - A mistake, recorded: on 1939-11-24 Bock's army was pulled off the French border too. By 1939-12-24 France had
    overrun western Germany (39 → 25 states controlled; kept as `claude_ger_1939_12_collapse`). The campaign
    went back to `claude_ger_1939_11` and Bock was put back on the western line. Lesson: never strip the
    front facing a great power.
- **Greyed-out research:** when the game will not start a tech (for example "Requires Technology"), `act research`
  says so, closes the windows, and stops.
- **Checked live:** the first real start, Mechanical Computing in slot 3 (260 days), with no screenshot.
- **The campaign so far (Germany, played with these commands):** Anschluss completed on 1938-08-17.
  - From 1936 to now: 35 → 70 civilian factories, 28 → 55 military factories, 30 → 85 divisions.
  - On the way: Extensive Conscription, War Economy, six MEFO price-control decisions, and the advisors Schacht,
    Krupp, Neurath, Beck, Guderian and Göring.
  - Save: `claude_ger_1938_08_anschluss`.
  - Then the Sudetenland through Munich (33 states by 1938-11) and the First Vienna Award. Fate of
    Czechoslovakia started on 1939-01-01.
  - Status on 1939-01-01: 74 civilian and 63 military factories, 105 divisions; Schörner and Rommel in high
    command. Save: `claude_ger_1939_01`.

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

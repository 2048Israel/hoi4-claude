# Changelog

What shipped to `main`, newest first, under the version that shipped it. A batch adds its block at the top in the merge that ships it: a few lines
saying what changed and how it was checked.

# Next (on main, not released yet)

# 0.1.8 (2026-11-09)

- **Agent definitions (.claude/agents, TH1):** the ten subagents of docs/command.md: policy, research, civilian,
  military and naval industry, air, navy, army, and the templates field-marshal (one per army group) and operation
  (one per operation). Each file (63-77 lines) says what the agent owns and leaves, its goals, its doctrine for
  Germany 1936-1941 with the 1939-1940 lessons, its OR1 ops and requests, its input and its one-object reply. The
  army tree runs on fable, the rest on sonnet, with the Read tool only. One worked example each, cut from real ST1
  slices of claude_ger_1939_11_stop (docs/agents/examples: inputs 1,000-7,100 characters, replies 640-1,730).
  Offline: tests/test_TH1.py (every reply passes OR1 within its budget; the ten merge as one turn with no conflict).

# 0.1.7 (2026-11-09)

- **State slicer (hoi4_slices.py, ST1):** `slices(snapshot, bridge_state, world)` gives each agent of
  docs/command.md its own input: policy, research, the three industries, air, navy, army, one field marshal per
  army group and one per running operation, keyed by OR1's agent names. Fog of war: enemy divisions only in
  provinces we hold or stand in, or next to one; per-country counts only from the bridge. Adjacency is read at run
  time from the game's provinces.bmp, definition.csv and adjacencies.csv (1.4 s, cached in state/). Beyond SR1 it
  reads province control, wars, air wings and bases, air superiority and the faction from the save, laws and
  building slots from the game's files, and FP1's startable focuses. On the 1939 save every slice is 750-6,700
  characters; 5.3 s in all (2.1 s of it FP1, skip with --no-focus). Offline: tests/test_ST1.py with a 14x3
  handmade map.

# 0.1.6 (2026-11-09)

- **Save reader (hoi4_save.py, SR1):** `python hoi4_save.py <save> [--tag GER] [--units POL]` turns a text save
  into compact JSON: research slots with days left, production lines, the construction queue, divisions (province,
  state, army, strength, org), armies with their generals, fronts, templates, training, fleets, owned states, the
  focus, political power, stability and war support. Days left follow the rule the saves show (a tech ahead of its
  year speeds up as it nears): it named the game's finish day for 9 of 10 techs, one day off for the 10th. Reads
  the 76 MB 1939 save in 0.9 s by stopping once the player's country is read. `--raw countries.GER.focus` prints
  one block. Offline: tests/test_SR1.py with a handmade save and game-folder fixtures.

# 0.1.5 (2026-11-09)

- **Orders format (hoi4_orderspec.py, OR1):** the JSON Lines format between the agents of docs/command.md and the
  executor: 25 ops (the first-week ops, the executor's, operation charters, six requests), each with by/why and
  optional priority/id/cost; validate(), validate_reply() for {orders, requests, report, notes}, budgets and
  results (done/refused/failed/dropped). merge() gives ids, routes requests, and holds conflicting or over-budget
  orders for Supreme Command (settle()); it never guesses. docs/orders.md has every op with an example line;
  `python hoi4_orderspec.py check FILE`. Offline: tests/test_OR1.py, which also checks every example in the docs.

# 0.1.4 (2026-11-09)

- **Focus planner (hoi4_focus.py, FP1):** `python hoi4_focus.py --save <save> [--json]` lists the focuses that can
  start now from the game's own focus files: prerequisites (OR in a block, AND across), exclusions both ways, cost
  in days, the `available` text only the game can check, and what each focus opens. It finds the tree the game
  gives the tag across the enabled mods, reads names from localisation, and decides has_completed_focus, has_dlc,
  game rules and the ruling ideology from the save. On `claude_ger_1939_11_stop` it lists 32 focuses (the game's
  germany.txt won; no enabled mod has focus files). `tests/test_FP1.py`, handmade fixtures.

- **Diplomacy (hoi4_diplomacy.py):** `act diplomacy --city Warsaw --action "Declare war" [--dry-run]` right-clicks
  the country owning the city, picks the action from its list by name (tooltip printed), and sends it. Used
  live: war on Poland declared 1939-08-25 in the replay.

- **Construction (hoi4_build.py, EX3):** `act build --building military_factory --count 8 [--per-state 2]` arms
  the building and clicks the visible states with the most free slots (their "used/total" labels), checking
  that the queue grew. Found live on 1939-06-26: the queue was empty with 42 civilian factories idle; now 12
  military factories and 2 refineries are queued and all 91 civilian factories are working. `tests/test_EX3.py`.
- **Events:** a second layout (portrait, title lower, button further left); options must sit on a dark button
  (sampled under the text); single-answer events use the same reader. War rounds close notices first and start
  the next focus from `plans/focus_germany.txt`.

# 0.1.3 (2026-11-07)

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
- **Laws, advisors and staff (hoi4_politics.py):** `read ideas --slot S` lists a Politics slot's choices with
  their effects; `act idea --slot S --name NAME [--dry-run] [--replace]` takes one, confirms a law's REPLACE dialog,
  and checks the political power spent. A filled advisor slot is never replaced without `--replace`. Slots:
  law-conscription/trade/economy, advisor-1..3, research-1..6, staff-1..6, gov-executive/judiciary/structure.
  Used live: Unitary State, Walther Funk, Werner von Fritsch.
- **act army push (hoi4_orders.py):** standing orders in `plans/orders.txt` (`army general city`); a fresh report
  shows each army's share of divisions in combat, and any army under `--min-share` (35%) is sent at its city
  again. Direct orders end when a path is blocked, and the army then digs in: in the first July 1940 run three
  armies sat idle for weeks while Berlin fell. `tests/test_ORD.py`.
- **Air wings (hoi4_air.py):** `read air` lists every wing with its base and area (the Air Forces Overview, `l`);
  `act air base|assign|rebase --base NAME` reads a base's wings, gives them a mission over a region
  (`--mission superiority|cas|interception|...  --region X Y`, a right-click with the mission armed) or moves them
  to another base, and checks each wing's order from its tooltip; `act air off` returns to the Default map (F1).
  Found live on 1940-07-31: all 14 wings were standing by with no mission. Now 13 fly air superiority or close
  air support over Eastern Germany. `tests/test_AIR.py` covers the overview rows and the wing filter.
- **City orders say where they went:** `act army target` / `act order` print the target province's state, owner
  and controller from its tooltip. "Brest" found Brest in France, not Poland: when Find lists a name twice, the
  first is taken with a warning (the state Gdynia and its city share a name), and the log line shows which.
- **tools/war_rounds.py:** plays the war in rounds: advance, answer events from `plans/event_answers.txt` (stops
  on any other event), close news, `act army push`, refill empty research, warn when no focus runs, summary.
- **Smaller fixes:** wrapped focus titles ("LEGION" over "CONDOR") are joined before matching; `act air assign
  --wing NAME` reaches wings a base panel cuts off; `act air` right-clicks only where the region's own tooltip
  shows; `fix-queue` tries several deploy points (camera home follows the capital); `tools/load_ingame.py`
  scrolls the save list.
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

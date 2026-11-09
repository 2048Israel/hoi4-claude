# hoi4-claude

A bridge that lets Claude play Hearts of Iron IV on this PC.

> **AI agents:** read [`CLAUDE.md`](CLAUDE.md) first. It covers who works on what, when to branch, and how a change
> reaches `main`. The work waiting is in [`QUEUE.md`](QUEUE.md).

- **Eyes:** screenshots of the game window, with a coordinate grid drawn on top.
- **Hands:** mouse and keyboard input sent to the game window.
- **Memory of the game:** the *Claude Bridge* mod writes the player's state and world news into
  `Documents\Paradox Interactive\Hearts of Iron IV\logs\game.log`, and `hoi4.py` turns that into short reports.

## Setup

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe hoi4.py launch
```

`launch` copies the mod into the HOI4 mod folder, adds it to your current mod list in `dlc_load.json`
(the old file is backed up in `state\`), and starts `hoi4.exe` directly, skipping the Paradox launcher.
`hoi4.py restore-mods` puts the old mod list back. The Paradox launcher also rewrites that file whenever you use it.

The game must run **borderless or windowed** (not exclusive fullscreen) and **not Ironman** (the console is needed for on-demand reports).

Two screen checks are calibrated for **1920x1200 at UI scale 1.0**:
- *Paused?* HOI4 draws pulsing hazard stripes behind the clock (top right) while paused. `pause`, `resume` and `advance` watch for them, press Space at most once, and say so if they cannot confirm the result.
- *Console open?* The console is a dark box at the top left. `report` and `console` only type after confirming it opened, and close it afterwards.

At a different resolution or UI scale, recalibrate `clock_box`/`pause_stripe_share` and `console_open` in `hoi4.py`.
On this PC, speed 5 runs about 3 in-game days per second; speed 4 about 8 seconds per day.

See `PLAYBOOK.md` for hotkeys and screen-by-screen notes for this game version. For example, the focus tree opens with Alt+Q.

## Commands

| Command | What it does |
|---|---|
| `look [--scale 0.6] [--region x0 y0 x1 y1] [--mark x,y]` | Screenshot with grid, plus the latest state line and new world news |
| `zoom x0 y0 x1 y1 [--scale 1.5]` | Close-up screenshot of one area |
| `click x y [--right] [--double] [--mods shift]` | Click at window coordinates |
| `move x y` | Hover (for tooltips) |
| `drag x1 y1 x2 y2 [--right]` | Drag (box-select, front lines) |
| `scroll x y n` | Mouse wheel; positive zooms in |
| `key y` / `key alt+q` / `key esc --times 2` | Press keys or combos |
| `type "text"` | Type text |
| `console "command"` | Run a console command |
| `report` | Ask the game for a full state report right now |
| `state` | Print the latest report already in the log |
| `news` | World news since the last check |
| `pause` / `resume` / `speed n` | Time control |
| `advance n [--speed 4]` | Let n days pass, then pause and summarize what changed |
| `do "key y ; wait 0.5 ; look"` | Several commands in one call |
| `read research` / `read production` / `read date` | The screen read back as **text** (Windows OCR), no screenshot |
| `read techs [--tab industry] [--grep PaK]` | Techs from the tech map: name, tab, research days |
| `act research --slot 5 --tech "Inter-War Artillery" [--mio first\|none\|NAME] [--dry-run]` | Start research with no screenshot: finds the icon from the tech map, checks the window's title, presses Research, picks the industrial organization, confirms the slot. Refuses a busy slot without `--replace` |
| `act production --line 2 --add 1` / `--remove 1` | Factories on production lines 1-5, confirmed by the factory counter |
| `act production --name "Bf 109" --add 4` | Any line, found by its header text (scrolls the list) |
| `act recruit --count 10 [--template "Panzer-Division"]` | Queue divisions: each line set to train once (not the default infinity) and given a deploy location |
| `act fix-queue` | Every training line: count 1 and a deploy location (locations can get lost) |
| `act select-box x0 y0 x1 y1` / `act army new [--halves N]` | Select divisions on the map, then make an army from the unassigned ones (S halves the selection: 75 → 38 → 19) |
| `act camera home` | The standard map view: Go Home (the capital), then 12 notches out. Map coordinates for plans are measured in this view |
| `act order --city NAME` | Send whatever divisions are selected at a city (no army needed) |
| `read event` / `act event --option N` | The open event's title, options and each option's effects (read from its tooltip); choose one |
| `act army target --army N --city Warsaw` | Order army N at a city by name: the map's Find window centres the camera on it, then a right-click on its label |
| `act army move --army N --to X Y` | Order every division of army N to move to / attack the province at X,Y (camera-home view). More reliable than plans |
| `act army execute [--army N]` | Start battle plans: clicks Execute only for armies the report shows still dug in (the button does not show its state; a second click stops a plan) |
| `act army attack --army N --at X Y --to X Y` | Offensive arrow for army N, right-dragged from its front into enemy land |
| `act army front --army N --at X Y` | Front line for army N along the border highlighted at X,Y (works in peacetime) |
| `act army list` / `act army generals` / `act army general --army N --name X` | Armies with their size and commander; give every army without one the game's top-listed general |
| `act focus --name "Danzig or War"` / `read focus` | Start a focus through the tree's search; when the game refuses, it prints the requirement lines. `read focus` shows the running one |
| `act diplomacy --city Warsaw --action "Declare war" [--dry-run]` | A diplomatic action on the country that owns the city |
| `act build --building military_factory --count 8 [--per-state 2]` | Queue buildings in the visible states with the most free slots (Construction screen) |
| `read ideas --slot staff-6` / `act idea --slot advisor-3 --name "Walther Funk" [--dry-run] [--replace]` | Laws, advisors, military staff and government slots: list choices with effects; take one (PP checked) |
| `read decisions` / `act decision --name "War Propaganda" [--dry-run]` | List every decision by category; take one by name after printing its tooltip. Checked by the row's look and the power spent |
| `act decision-category --name "Heavy Industry" --collapse` | Fold a decision category away (mods add big ones) |
| `act research-fill [--plan FILE]` | Fill every empty research slot from a priority list (`plans/research_germany.txt`) |
| `read pp` | Political power from the top bar |
| `act army push [--plan plans/orders.txt] [--min-share 0.35]` | Re-send every army that has mostly stopped fighting at its standing target city |
| `read air` | Every air wing with its base and area (Air Forces Overview) |
| `act air assign --base Holstein --mission cas --region X Y [--only Kampf,KG]` | Give a base's wings a mission over the region at a screen point; each wing's order is checked |
| `act air assign --wing Jagdgeschwader --base Niederschlesien --mission superiority --region X Y` | One wing by name through the overview (a base panel shows only four rows) |
| `act air rebase --base Oberbayern --to X Y [--only Jagd]` / `act air base --base NAME` / `act air off` | Move wings to the base icon at X Y; list a base's wings and orders; back to the Default map |
| `act open production` / `act close production` | Open or close a screen by its hotkey, confirmed by its title |
| `act save ger_1936_06` / `act load-save claude_ger_1936` | Save through the console (always as `claude_...`), or load a save from the main menu |
| `act calibrate-research [--tabs artillery]` | Build the tech map (`state/tech_map.json`): clicks each icon once and reads its name. About a minute per tab |
| `status`, `tail`, `install-mod`, `restore-mods` | Housekeeping |

Coordinates are always full-resolution game-window pixels. The grid labels show those numbers even on scaled-down screenshots.

## Mod

`bridge_mod\claude_bridge\` writes lines that start with `@CB;` into game.log:

- `day` once per in-game day (political power, stability, war support, manpower, divisions);
- a full report every week and when the console runs `event claude_bridge.1` (industry, resources, equipment
  stock against what the army needs, wars, allies, generals, front-line states, major powers, neighbors);
- `news` for war declarations, capitulations, annexations, puppets, peace deals, factions and government changes.

It only logs. It changes nothing about the game.

## Save reader

`hoi4_save.py` turns a text save into compact JSON for one country, so the agents of `docs/command.md` get the
game's state as data instead of screenshots:

```
python hoi4_save.py "<save>.hoi4" [--tag GER] [--units POL,SOV] [--indent 1] [--timing]
python hoi4_save.py "<save>.hoi4" --raw countries.GER.focus
```

- **research:** each slot's tech, points, cost, rate and days left; free slots with their saved points; techs done
- **production:** each line's equipment and variant, factories, efficiency and output per day (ships: progress)
- **construction:** building, state, levels, factories, progress and days left
- **divisions:** name, template, province and state, army, strength, organisation, manpower, where it is moving,
  in combat; **armies** with their general, **fronts**, **templates**, the **training** queue, **fleets**
- **focus** (running, progress, completed), political power, stability, war support, ideas, owned **states**
- `--units` adds other countries' divisions (province, template, strength) for the state slicer (ST1), which
  applies the fog of war. `--raw` prints any one block of the save, for exploring without reading the file.

Saves must be text (`save_as_binary=no`, `docs/queue/SR0.md`); a binary save is refused with that hint. Research
costs and years, state names and province-to-state come from the game's files and the mods enabled in
`dlc_load.json`, read-only (`--no-game` skips them). Saves are only ever read.

**Speed**, measured on the PC on 2026-11-09 with `claude_ger_1939_11_stop.hoi4` (76 MB, 1 Nov 1939): **0.9 s** in
all, of which 0.55 s is the save and 0.27 s the game's files; 54 KB of JSON. It reads only what it needs: unwanted
blocks are skipped by counting braces, and it stops once Germany, the first country, is read. Just tokenizing the
whole file would take 2.8 s, before building anything.

## State slicer

`hoi4_slices.py` cuts the save reader's snapshot and the bridge's report into one small input per agent of
`docs/command.md`, with the fog of war applied:

```
python hoi4_slices.py "<save>.hoi4" [--bridge report.log] [--agent air] [--indent 1]
python hoi4_slices.py "<save>.hoi4" --sizes [--operations ops.json] [--field-marshals fm.json] [--no-focus]
```

- **Slices:** `policy`, `research`, `civilian_industry`, `military_industry`, `naval_industry`, `air`, `navy`, `army`,
  one `field_marshal_<army group>` per army group and one `operation_<name>` per running operation. The keys are
  the agent names of `docs/orders.md`. Repeated rows are tables (`columns` + `rows`).
- **Fog of war:** our country in full. Enemy divisions only in provinces we control or stand in, or next to one;
  per-country division and factory counts only from the bridge (what diplomacy shows); hidden ideas left out.
  Adjacency comes from the game's `map/` (`provinces.bmp`, `definition.csv`, `adjacencies.csv`), read at run time
  and cached in `state/map_cache.json`; nothing from the game is committed.
- **Beyond SR1** it reads province control, wars, air wings and bases, air superiority and the faction from the
  save, laws, advisors and building slots from the game's files, and FP1's startable focuses for `policy`.

**Speed and size**, on `claude_ger_1939_11_stop.hoi4`: 5.3 s in all, of which 2.1 s is FP1's focus list (skip it with
`--no-focus` when the policy agent is not due) and 1.8 s the save with 16 enemies' divisions; every slice is under
7,000 characters (the aim is 8,000).

## Status and how to help

The program and mod run on one Windows PC that has the game; the first campaign there is **Germany, 1936**
(Regular, not Ironman). Anyone can work on the code, but only that PC can test against the live game, so
send changes as pull requests and describe how to check them in-game (the full process is in `CLAUDE.md`).

**Verified in the live game:** window focus, screenshots, clicks, hotkeys (Y production, Alt+Q focus tree),
console reports (`report`), the daily heartbeat, `pause` / `resume` / `advance`, and console open/close detection.

**Not verified yet:**
- `general` lines (`every_army_leader` + `is_leading_army`): no armies have generals at the 1936 start.
- `front`, `enemy` and `ally` lines: these need a war.
- News hooks (`on_declare_war`, `on_capitulation`, ...): none has fired yet.
- The screen checks at any resolution or UI scale other than 1920x1200 / 1.0.

**The work waiting** is in `QUEUE.md`, one brief per batch in `docs/queue/`. Ideas not queued yet: map helpers
(center the camera on a state, read who controls the province under the cursor) and a battle-plan helper (select an
army, draw a front line or offensive line, execute).

`tests/test_offline.py` covers the parts that need no game: log parsing, report/news formatting, keys, grid drawing.
Run it with `.venv\Scripts\python.exe tests\test_offline.py`. `PLAYBOOK.md` lists hotkeys and screen flows for this
game version, built from the game's own files.

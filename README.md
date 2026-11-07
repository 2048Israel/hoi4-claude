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

# HOI4 1.19.4 "Operation Postern" UI playbook (for the screenshot + input agent)

Built only from the installed files (launcher-settings.json: `v1.19.4.2.2da5`). Paths are relative to the game folder. `gui` = `interface/*.gui`,
`loc` = `localisation/english/*_l_english.yml`, `kb` = `keybinds/00_keybinds.txt`, `exe` = the string appears in `hoi4.exe` (checked with grep).
**Unconfirmed** means no file says so. **Inferred** means pieced together from element names or generic tooltips.

**Setup facts**
- Default keybinds are active: `Documents/Paradox Interactive/Hearts of Iron IV/settings.txt:72` has `keybind_profile=""`. The optional profile `keybind_profiles/wasd_camera.txt` would move the camera to WASD and push S/D/A to Ctrl+S/D/A.
- Shortcuts are case-sensitive key names: `"q"`, `"shift+q"`, `KP_PLUS` (numpad +), `DEL`, `RETURN`, `ESCAPE`.
- Enabled mods (`dlc_load.json`) replace `countrytechtreeview.gui`, `countryproductionlineview.gui`, `countrytradeview.gui`, `countrystateview.gui` and the tank/plane/equipment designers. Their copies keep only ESC/RETURN, so the research tree **loses Ctrl+Tab tab cycling** while those mods are on. No enabled mod touches topbar, battleplantools, unitview, naviesview, airselectionview or nationalfocusview.
- Almost every view's close button is bound to `ESCAPE`, and confirm/accept buttons in popups and send windows are bound to `RETURN` (more than 100 entries across gui files).

## 1. Hotkeys

### Top bar / screens (topbar.gui)
| Key | Opens | Source / notes |
|---|---|---|
| `q` | **Politics** (the player flag button `player_flag`) | topbar.gui:97. Clicking the flag toggles Politics; right-clicking it toggles your own Diplomacy (loc topbar:87) |
| `alt+q` | **National Focus tree** | topbar.gui:100-109: off-screen button `national_focus_shortcut` at x=-9000. Its comment says the view "has no visible topbar button". exe has the strings `add_national_goal_button`, `CLICK_OPEN_FOCUS` and `alt+q` together |
| `shift+q` | Decisions | topbar.gui:777. Right-clicking the button mutes notifications for all available decisions (loc topbar:81) |
| `ctrl+q` | Faction | topbar.gui:735 |
| `w` | Research, Research Slots tab | keybind `research_open` (kb:35, topbar.gui:888) |
| `ctrl+w` | Research, Experimental Facilities tab | keybind `research_open_facilities` (kb:38, topbar.gui:898). Mouse: right-click the Research button (loc topbar:16) |
| `alt+w` | Research with a free slot already selected | topbar.gui:908. Mouse: Alt+click (loc topbar:17) |
| `shift+w` | Intelligence Agency | topbar.gui:826 (needs the La Résistance DLC) |
| `e` | Diplomacy | topbar.gui:938 |
| `shift+e` | Officer Corps (high command, chiefs, theorists, doctrines) | topbar.gui:1052, loc politics:185 |
| `r` | Trade | topbar.gui:995 |
| `t` | Construction | topbar.gui:1005 |
| `y` | Production | topbar.gui:1022 |
| `u` | Recruit & Deploy | topbar.gui:1032 |
| `i` | Logistics | topbar.gui:1042 |
| `o` / `p` / `l` | Army / Navy / Air overview | topbar.gui:1064/1074/1084 |
| (none) | International Market | No top-bar button. Use the "go to market" button in Construction (countryconstructionsview.gui:1347, loc constructions:92) |

### Time
| Key | Action |
|---|---|
| `SPACE` | Pause/unpause (topbar.gui:575; "disabled in MP from code") |
| `KP_PLUS` / `KP_MINUS` | Speed up / down (topbar.gui:637/592; tutorial loc:34). Main-row `+`/`-` and number keys 1-5: **unconfirmed** |
| click `button_speedstep1..5` | Set speed 1-5 directly (topbar.gui:598-631, inferred) |
Speeds: `GAME_SPEED_SECONDS = {2.0, 0.5, 0.2, 0.1, 0.0}` for levels 1-5, where 5 is unbound (common/defines/00_defines.lua:12). The unit is seconds per tick; a tick being one in-game hour is inferred.

### Map, camera, misc
| Key | Action |
|---|---|
| Arrow keys | Pan camera (kb:45-56). Mouse-wheel zoom: **unconfirmed** for the map (the focus tree says wheel = zoom) |
| `F1`-`F10` | The 10 map-mode button slots (mapmodes_interface.gui:119-531). **F1 = Default, F4 = Supply** (tutorial loc:135-138). Other slots are assigned in code: **unconfirmed**. Right-click a slot to reassign it (loc core:1975) |
| `ctrl+F1` | "All map modes" window (mapmodes_interface.gui:85). In it: click = select, right-click = select and close (loc mapmode:65) |
| `ctrl+f` | Find/search window (mapmodes_interface.gui:75). Inside it, `h` = "go to home" (findview.gui:104; probably your capital, inferred) |
| `ctrl+m` | Toggle minimap (minimap.gui:121) |
| `ctrl+n` | Toggle day/night (mapmodes_interface.gui:1045) |
| `m` | Unit counters: all vs. players only (:1069) |
| `,` | Unit counter colour: country vs. allegiance (:1092) |
| `.` | Show allied battle plans (:1115) |
| `<` | Open/close the message log (menubar.gui:1631/1644) |
| `ESCAPE` | Close the current view. Opening the in-game menu with ESC when nothing is open: **unconfirmed** (engine) |

### Land units, with divisions selected (unitview.gui `army_division_list_view`)
| Key | Action |
|---|---|
| `s` | Select half (keybind `divisions_select_half`, kb:1) |
| `h` | Halt all selected units (unitview.gui:924, loc unit:105) |
| `b` / `ctrl+b` | Strategic-redeployment toggle (unitview.gui:879-880). "Use Ctrl+B to toggle strategic redeployment for move orders of selected armies" (loc army:124) |
| `ctrl+g+s`, `ctrl+g+d`, `ctrl+g+w` | 3-key chords on off-screen anchors: select HQ, deploy Army HQ, withdraw Army HQ (unitview.gui:797/1133/1241). Anchor names are in the exe; **how the chord is pressed is unconfirmed** |
| `ctrl+g+a` | The commander/leader button on the army badge (unitview.gui:465; also the fleet one at naviesview.gui:1062), meaning "change commander" (inferred) |
| (no key) | **Land divisions have no select-all, split or merge hotkey.** Use the `btn_consolidate_selection` button (merges under-strength divisions of the same template, loc core:1709) |

### Battle plan tools (army selected; battleplantools.gui)
| Key | Tool |
|---|---|
| `z` | Front line (:134) |
| `x` / `shift+x` | Offensive line / Spearhead (:152/:178) |
| `c` | Fallback line (:187) |
| `v` | Area defense (:198) |
| `n` / `shift+n` | Naval invasion / naval invasion with Floating Harbor (:107/:116) |
| `a` | Paratrooper (airborne) order (keybind `battle_planner_airborne_orders_tool`, kb:28) |
| `ctrl+h` | Unassign selected divisions from their orders (:215) |
| `DEL` | Delete-order tool: press it, then click an order (:231, loc core:859) |
| `shift+DEL` | Delete all orders without confirmation (:241; inferred from loc core:861) |
| `alt+DEL` (also `ctrl+alt+DEL` for AltGr) | Delete only airborne and naval-invasion orders (:251-253; inferred from loc core:862) |
| `k` / `shift+k` | Exercise / exercise until fully trained (:47-48, loc core:1201) |
| `shift+d` | Cohesion mode (Flexible/Balanced/Rigid/Immobile; :70, loc core:2167-2174, 2305) |
| `shift+s` | `btn_priority` (:59). Opens a plan-priority/planning setting: **meaning unconfirmed** |
| hold `ALT` / hold `CTRL` | Edit-arrow mode / assign-divisions mode (loc core:863, 883). Edit mode has no hotkey (`#shortcut="d"` is commented out, :222) |
| `ESCAPE` / `TAB` while drawing | Cancel the drawing / cycle arrow connections (loc theater:66-67) |

### Navy (fleet selected; naviesview.gui)
| Key | Action |
|---|---|
| `z` `x` `c` `v` | Missions: Patrol, Strike Force, Convoy Raid, Convoy Escort (:226-307; names from sprite names) |
| `b` / `shift+b` | Minelaying / Minesweeping (:330/:353) |
| `k` / `shift+k` | Naval exercise (:180-181) |
| `a` | Naval invasion support (keybind, kb:25) |
| `DEL` | Remove-region tool. Right-clicking the button clears all regions (:407, loc core:518) |
| `h` / `ctrl+h` | Hold: return to the nearest port / stay put (:414-415, loc core:545) |
| `d` / `s` / `g` | Split task force in half / select half / merge (kb:10, kb:7, :529). loc says Shift+G merges every task force in the theater (core:554); that is **not** in the gui |
| `shift+s` | Automate home base (:1025) |

### Air (air base or wings selected; airselectionview.gui)
| Key | Action |
|---|---|
| `a` / `s` / `d` | Select all wings / select half / split (kb:16, 13, 19) |
| `g` / `o` | Merge wings / merge groups (:1521/:1529) |
| `h` | Hold (:1733) |
| `n` | New air wing in the selected base (:288) |
| `z x c v b`, `ctrl+b`, `j`, `ctrl+r` | Mission-bar slots 0-4 and 7-9 (:1078-1245). Which mission sits in which slot is set in code: **unconfirmed**. Read the icon or tooltip |
| `k` / `shift+k` | Pilot Exercises / exercises until fully trained (:1294-1295, loc air:36) |
Operative selected (operativeleader.gui:342-503): `z x c v b n m` = mission slots 3, 1, 2, 5, 8, 4, 6; `d` = Diplomatic Pressure. Railway guns (railway_gun.gui): `s` half, `x` unassign, `h` hold.

## 2. Main screens

**Mouse conventions** (generic loc used on every screen):
- Number steppers: Click = ±1, Ctrl+Click = ±5, Shift+Click = ±10 (loc core:2219-2224, production:254).
- Priority arrows: Shift+Click = move to top/bottom.
- Right-click on a list entry usually pans the map to it (loc core:1021, 1081).
- Many tooltips print the bound key ("Shortcut: $KEY$", "Keybind: $KEY$", loc core:440-441), so a hover screenshot confirms a key.

**National Focus** (`alt+q`, or `q`, then click the focus box in Politics)
- Ways in: `alt+q`; or Politics → click the "active goal" box (`add_national_goal_button`, countrypoliticsview.gui:432; tooltip "Click to show your focus tree", loc core:1397).
- Click a focus → detail window → **Start** (bound to `RETURN`, nationalfocusview.gui:902).
- Shortcuts (generic loc core:1165-1169; that they apply to focuses is inferred): Shift+Click = start immediately; Alt+Click = start and keep the window open; Ctrl+Click = details while keeping other windows open; Shift+Click = bypass (when the focus can be bypassed).
- Search (loc core:1376): `ctrl+f` = search bar; `ctrl+TAB` / `ctrl+shift+TAB` = cycle hits (gui :414/:421); `RETURN` = open detail; `shift+RETURN` = start; `alt+RETURN` = start and keep open.
- Zoom: `PAGE_UP`/`PAGE_DOWN` (:105/:114) or the mouse wheel (loc core:1379). `ctrl+m` = minimap (:519).
- Cancel the running focus: the X on the focus box in Politics (`drop_focus_button`); progress is saved (loc core:1254).

**Research** (`w`)
- Click an empty slot (loc tutorial:157), pick a tree folder, then click a tech. Plain click on a tech: "Click to research" (loc research:39); the detail window's Research button is `RETURN` (countrytechtreeview.gui:4101).
- Shift+Click = research directly; Alt+Click = research and keep the window open; **Shift+Alt+Click = research and select the next free slot** (good for filling every slot); Shift+Right-Click = research without spending a research bonus (loc core:1170-1177).
- **No research queue or "right-click to queue" string exists in loc.** Swapping a tech that is in progress asks for confirmation (loc research:25).
- Tree tabs: the vanilla gui binds `ctrl+TAB`/`ctrl+shift+TAB` (countrytechtreeview.gui:3900/3907), but loc says plain `TAB`/`shift+TAB` (research:18), and the active mods remove the binding. **Click the tabs.**

**Production** (`y`)
- Four "new line" buttons (`infantry_button`, `tank_button`, `aircraft_button`, `naval_button`), then pick the equipment, which creates the line (loc tutorial:148). Click = add at the end; Shift+Click = add at the top (loc production:264).
- Factories: the ± buttons on the line. Priority: drag and drop, or the arrows (Shift = top/bottom) (production:37-38, 249).
- Click the equipment icon to change what the line builds (loses progress, production:208). Click X = cancel the line. **Shift+Click X cancels ALL lines** (production:79); never shift-click X.

**Construction** (`t`)
- Click a building button, then click a state or province on the map (loc constructions:15/18).
- On the map: Click = queue 1; Shift+Click = queue the maximum; Right-click = remove one; Shift+Right-click = remove all (constructions:54-59). Ctrl+Click = put at the front of the queue; Alt+Click = at the end (buildings:183).
- Queue: Shift+Click the priority arrows = highest/lowest; X = cancel; Ctrl+Click X = cancel all (constructions:44-48).
- Railways: enter railway mode, click a node, move along the provinces, click the target (constructions:16).
- Tutorial advice: build Civilian Factories first "for a couple of years" (tutorial:119).

**Recruit & Deploy** (`u`)
- Click a template = add it to the deployment queue ("Train"; loc deployment:11, 29). "Add unit" = parallel line; Shift+Click adds 5 (deployment:97).
- Deploy: select deployment(s), then click a green province on the map (deployment:45, core:1143). Per-line deploy-now button: deployment:116.
- Location button: Click = set, Right-click = reset (deployment:112). Up/down: Shift = top/bottom (deployment:128-129).
- The template's edit button opens the Division Designer (deployment:13).

**Division Designer** (reached from R&D edit/new template, or right-click a division's unit icon: "open in Division Designer", loc core:1088)
- Empty slot: Click = add; Shift+Click = copy the slot above; Ctrl+Click = fill the regiment (designer:3-8).
- Filled slot: Click = change; Shift+Click = remove; Ctrl+Click = clear the regiment (designer:9-11).
- Finish with `save_button` or `save_and_deploy_button`. Editing costs Army XP (tutorial:128-129). `ESCAPE` closes. Note that `RETURN` is bound to the battalion-picker "Back" button (divisiondesignerview.gui:969).

**Decisions** (`shift+q`)
- Each row has `btn_select`; click it to take the decision ("Take decision", countrydecisionview.gui:476, loc decisions:10). Watch the PP/CP cost.
- Category headers collapse; the checkbox toggles notifications (decisions:6-9).

**Diplomacy** (`e`; right-click your own flag = your own diplomacy)
- Switch to another country: click its flag in a view (loc diplomacy:495, state:15), or right-click a country to see the available actions (loc tutorial:126).
- Pick an action → popup → `RETURN` = send, `ESCAPE` = cancel (countrydiplomacyview.gui:1237/1243 and similar).
- Your own view has auto-accept/decline settings (diplomacy:8-16).

**Trade** (`r`)
- Trades civilian factories for resources (tutorial:169). Click a country row to trade (trade:111) → offer window `RETURN`/`ESCAPE` (countrytradeview.gui:647/656).
- Cancel imports (trade:56). Auto-import priority: drag to reorder, ± sets the accepted shortage (trade:165-172).

**Logistics** (`i`): mostly read-only. Sort columns; high/medium/low priority buttons. For supply on the map use `F4` (tutorial:135).

**Politics** (`q`)
- Laws and political advisors: click a slot in the idea categories, then pick ("Click to add $GROUP$", loc politics:21; change/remove: politics:114-115).
- Military advisors, high command and theorists are in Officer Corps (`shift+e`).

## 3. Army control
1. **Select.** Left-drag a box, or left-click a counter (loc tutorial:23, 38). Shift+Click adds (army:26).
   In the division list: Shift+Click = range, Ctrl+Click = toggle, Double-Click = all divisions of that template, Right-click = pan (core:1016-1021). Select half = `s`.
2. **Move.** Right-click a province (core:1278). Ctrl+Right-click = support attack (core:1280). Ports and transports: right-click a port (tutorial:37). `b`/`ctrl+b` = strategic redeploy.
3. **Make an army.** With divisions selected, click **New Army** at the bottom of the screen (tutorial:25, combat:101).
   - Army badges along the bottom: Click = select all its divisions (Ctrl+Click = non-HQ only, combat:104).
   - With divisions selected, Right-click a badge = assign them to it (combat:110).
4. **General.** Click the empty leader portrait at the top-left of the army panel, then pick from the list ("Click to change Commander", tutorial:32, unit:125).
5. **Plan.** Keep the army selected.
   - `z` front line: Click an enemy border = the whole border; Right-drag = part of it (core:865).
   - `x` offensive line: **right-click and hold, drag from the front into enemy land**; you can only draw it where a front line or invasion already exists (core:864, tutorial:27).
   - `shift+x` spearhead, `c` fallback (right-drag on friendly land), `v` area defense (click states), `n` invasion (click the source, right-click the target coast), `a` paradrop (click the air base, right-click the target) (core:866-881, theater:14-38).
   - Releasing the offensive-line drag on an execute-behaviour button sets the plan type (core:864).
   - Execute types are the Careful/Balanced/Rush buttons (battleplantools.gui:407-431).
6. **Execute.** Press the army badge's **Execute** button (leadergroups.gui:217).
   - Click = start/stop the whole plan.
   - Shift+Click, then click an order = toggle that order only.
   - Ctrl+Click = toggle all assigned armies (core:853).
   - Waiting lets planning reach its bonus (tutorial:28). Right-click provinces with a division selected to override the plan by hand (tutorial:34).
7. **Air support.** Click an air base (this selects its wings), Right-click an air region to assign them, then click a mission icon (tutorial:117, 29-30).
   Right-click an army badge with wings selected = attach them to the army (combat:105).

## 4. First week as a new country (UI steps)
1. Press `SPACE` (make sure the game is paused). Read the alert icons at the top first (tutorial:22).
2. `alt+q` opens the focus tree. Click a focus, then `RETURN` (or Shift+Click it). The tutorial suggests the branch that gives an extra research slot (tutorial:140). `ESC`.
3. `w`: Click an empty slot, pick a folder, then **Shift+Alt+Click** a tech; this researches it and jumps to the next free slot (core:1173). Repeat until every slot is used. Prefer industry/construction techs (tutorial:155). `ESC`.
4. `y`: check that the existing lines have factories; adjust with ± (Ctrl = 5). Add lines for missing equipment with the 4 category buttons. Watch the "no template" and "insufficient resources" alerts. `ESC`.
5. `t`: Civilian Factory button, then **Shift+Click** states with free slots (queues the maximum, constructions:58). Add infrastructure where it is low. `ESC`.
6. `u`: Click a template to queue it (several times for parallel lines); set the deploy location; deploy when ready by selecting the deployment and clicking a green province. `ESC`.
7. `q` (Politics): fill empty advisor slots and change economy/trade/conscription laws via the idea slots when PP allows. `shift+e`: high command and theorist. `ESC`.
8. `shift+q`: take any cheap useful decisions. `r`: import missing resources (Insufficient Resources alert, tutorial:169). `e`: diplomacy as needed.
9. Unpause with `SPACE`; set speed with `KP_PLUS`/`KP_MINUS`. Each in-game day, re-check the alerts and any empty research slot (alt+w opens research on a free slot).

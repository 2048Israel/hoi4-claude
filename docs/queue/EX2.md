# EX2: the rest of the executor

**Lane:** PC. **Module:** `hoi4_actions.py`. Follows EX1, which shipped screens, research, production lines 1-5
and the text readers.

Jerus, 2026-11-07: "isnt it better to just set up buttons where instead of claude taking a picture, its a program
that just clicks that button directly". EX1 did that for research and production. What is left, in the order a turn
needs it:

- **Recruit:** `act recruit --template "Infantrie-Division" --count N`. The training line defaults to infinity
  ("train forever"): set it to N with "+" and check it. Find the new line by OCR, not by position, because lines
  stack up.
- **Deploy:** finished divisions wait forever on "No location set" and do not count as divisions. Seen live on
  1936-07-06: 7 trained divisions were waiting.
  - `act deploy` should do what was done by hand then: click the line's location field; click a green-striped
    province (one near Poznań gave Hinterpommern); press the line's deploy arrow at x 572; repeat while a line
    shows a location. `hoi4.py state`'s division count confirms it.
  - Also check after each `advance`: a hint in `look` when trained lines are waiting.
  - A set location can be lost again: on 1938-03-26 four lines queued with Hinterpommern read "No location set"
    (probably when the province filled up). Re-check every line's location before each `advance`; OCR may read it
    as "No [öcation set", so match on "cation".
- **Construction:** `act build --building civilian_factory --state Sachsen [--count N]`. Try the map's find window
  (`ctrl+f`, type the state, jump the camera) and click the state at the screen's centre. Confirm with the
  construction queue's OCR.
- **Focus:** `act focus --name "Remilitarize the Rhineland"`. Open with `alt+q`, use the tree's search (`ctrl+f`
  inside the focus view; PLAYBOOK, National Focus) and `shift+RETURN` to start. Confirm through `hoi4.py state` or
  SR1's snapshot.
  - What worked live: click the search box at (1630,135), type the name, then Enter. That opens the detail window
    for the first hit; `ctrl+tab` moves to the next hit. Read the title, then click the window's "Start" (found by
    OCR). Confirm it in Politics: the focus box at (220-700, 120-230) reads the running focus, or "Select a
    National Focus" when none is running.
  - When Start does nothing, its tooltip says "You don't meet the requirements!". The requirement list scrolls
    inside its own box (870-1270, 240-380): scroll it and find the red X. Examples seen live: First Vienna Award
    needs "Owns North Sudetenland" (Munich must happen first); Zentrale Planung needs "At war with a Major
    Country".
  - The tree opens at whatever zoom it was left at, so a focus's screen position is not stable. Use the search,
    not coordinates.
- **Advisors and laws:** `act hire --name "Hjalmar Schacht"`. The list re-sorts, so find the row by OCR every time.
  - Open an **empty** slot, never a filled one. A filled slot's list replaces that advisor: the game asks "Replace
    Officer: do you want to replace Hjalmar Schacht with Franz Seldte?". Seen live on 1936-08-05 and cancelled.
    Political advisor slots in this setup: x 375, 475, 575 at y 735.
  - A red X in the list means "cannot hire". For example, Walther Funk needs Schacht and Erhard not hired. Read
    the reason from the tooltip, and do not click.
  - Check the hire by the drop in political power (`hoi4.py state` after one day, or OCR of the top bar).
  - **Laws ask for confirmation:** "REPLACE IDEA: do you want to replace Limited Conscription with Extensive
    Conscription for a total cost of 150?". Click its OK, read by OCR (it was at 1077,771). Closing the screen
    instead cancels silently. Seen live on 1936-12-22.
  - A world-news or event popup that opens meanwhile covers the dialog. Read the dialog's text before clicking,
    and stop if it is not the expected one (this worked live: nothing was clicked).
- **Decisions:** `act decision --name ...` by OCR of the decisions list.
  - The list opens on the mods' categories (Heavy Industry, academies, Navy Overhaul). Collapse them with their
    arrow at x 619, or scroll; vanilla categories such as MEFO Bills and Price Control Measures come after.
  - A row's tooltip opens just below the cursor (crop x 180-760, y+30 to y+240). Its "Take" button is at x 619 on
    the row's line. A taken decision drops to the end of its category, greyed.
  - Seen live on 1937-10-17: Import Tariffs (15 PP, -15% consumer goods), Guns before Butter and Arbeit und Brot
    (30 PP, -5% each).
- **Production lines past the first five:** scroll the list with known steps, and find lines by name with OCR.

Each action follows EX1's pattern: open by hotkey; check by OCR; act; confirm the result; close with the hotkey
(never a bare Esc); stop with a message and nothing more clicked when a check fails.

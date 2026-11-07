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
- **Construction:** `act build --building civilian_factory --state Sachsen [--count N]`. Try the map's find window
  (`ctrl+f`, type the state, jump the camera) and click the state at the screen's centre. Confirm with the
  construction queue's OCR.
- **Focus:** `act focus --name "Remilitarize the Rhineland"`. Open with `alt+q`, use the tree's search (`ctrl+f`
  inside the focus view; PLAYBOOK, National Focus) and `shift+RETURN` to start. Confirm through `hoi4.py state` or
  SR1's snapshot.
- **Advisors and laws:** `act hire --name "Hjalmar Schacht"`. The list re-sorts, so find the row by OCR every time.
- **Decisions:** `act decision --name ...` by OCR of the decisions list.
- **Production lines past the first five:** scroll the list with known steps, and find lines by name with OCR.

Each action follows EX1's pattern: open by hotkey; check by OCR; act; confirm the result; close with the hotkey
(never a bare Esc); stop with a message and nothing more clicked when a check fails.

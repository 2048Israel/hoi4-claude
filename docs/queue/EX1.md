# EX1: executor actions

**Lane:** PC. **Module:** `hoi4_actions.py` plus `ui_targets.json`, wired into `hoi4.py` as `hoi4.py act <op> ...`.

## Why

Most of the cost of playing now is finding buttons: almost every click needs a screenshot first. The first session
also showed what goes wrong without checks. Esc with nothing open brings up the game menu. A list of advisors
re-sorts itself, so a remembered position hits the wrong person. A click on a slot's Research button sometimes does
not register. A training line defaults to "train forever" (infinity).

## What

- `ui_targets.json`: named screen positions measured at 1920x1200, UI scale 1.0 (top-bar buttons, research slots,
  the tech-detail Research button, production line rows and their +/- buttons, construction building buttons, and so
  on). Each comes with a small check region and what it should look like.
- Checked actions for OR1's ops. Each one:
  - opens the right screen by hotkey;
  - checks with one small crop that the screen is open;
  - acts;
  - checks the result (for example, the slot now shows a tech);
  - closes the screen with its own X, never a bare Esc.
- A failed check stops the action, says what it saw, and saves the crop. It never retries blindly.
- `hoi4.py act` reads OR1 orders from a file or stdin.

## Done when

Every first-week op from OR1 runs from an order in the live game, at least once each. Record in the PR what each op
costs: number of screenshots, and seconds.

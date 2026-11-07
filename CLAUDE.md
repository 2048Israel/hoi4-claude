# hoi4-claude: read this first

A bridge that lets Claude play Hearts of Iron IV (v1.19.4, Steam) on Jerus's PC. `README.md` is the human
introduction and the command list; read it too. `PLAYBOOK.md` is the game's hotkeys and screen flows for this version.

| path | what it is |
|---|---|
| `hoi4.py` | the controller CLI: screenshots with a grid, mouse/keyboard input, pause/advance, console, reports, news |
| `bridge_mod/claude_bridge/` | HOI4 mod that logs the player's state and world news into `game.log` (it only logs) |
| `tests/` | offline checks: no game needed. `test_offline.py`; each batch adds `test_<id>.py` |
| `QUEUE.md` | the batches waiting, in order, one line each, by lane |
| `docs/queue/<id>.md` | one batch's brief |
| `docs/changelog.md` | what shipped, newest first |

## Who works here

Jerus owns the repo (GitHub `2048Israel`) and decides the order of the queue. Two Claude accounts work in parallel:

- **The PC session** runs on Jerus's PC, the only machine with the game. It plays, tests in the live game, and is
  the **orchestrator**: it alone merges into `main` and edits `QUEUE.md`.
- **The remote session** is the Claude of GitHub `PanzerKorps15`. It has no game, so it takes the **offline** lane:
  work that can be written and tested without HOI4 running.

They cannot message each other. Everything between them goes through GitHub: branches, pull requests, PR comments,
and `QUEUE.md`. Findings about *playing* well, rather than code, have a place of their own: the Research Exchange
board that `PanzerKorps15` proposed on branch `research-board`.

## Branch or not

`main` is always the version that works in the live game. That decides everything below.

| what | where it goes |
|---|---|
| Any change from the remote session, even one line or a typo | its own branch `batch/<id>` (or `fix/<topic>`) and a pull request. **Never push to `main`.** |
| A batch from the queue, done by the PC session | `batch/<id>`, merged by the PC session after the checks |
| A small fix the PC session finds while playing (one concern, verified in the game) | straight to `main`, pushed at once |
| `QUEUE.md` | the PC session only, on `main`. A branch never edits it: say what should change under **Queue** in the PR |
| Anything under `bridge_mod/` | a branch: it needs a game restart to test, so only the PC session can verify and merge it |

**Claiming:** a row is taken when its branch exists on GitHub. Before starting, run
`git fetch origin` and `git branch -r --list 'origin/batch/*'`. If the row's branch is not there, push it at once
(`git switch -c batch/<id> origin/main` and `git push -u origin batch/<id>`), then start. A branch with no commit for
two days can be reclaimed after a comment on its PR (or a note in your own PR).

**Keeping up to date** (Jerus, 2026-11-07: "commit often since the other account is also adding stuff so its good to
be up to date"):
- `git fetch` before you start and before every push. Commit small and push often, at least at each working step.
- Bring `main` into your branch with `git merge origin/main`. Do not rebase or force-push anything already pushed:
  the other session may have pulled it.
- Never force-push `main`. Never rewrite its history.

**Avoiding conflicts:** `hoi4.py` is one large file and both sessions would collide in it.
- New capabilities go in **new modules** (for example `hoi4_save.py`, `hoi4_orders.py`) with their own tests.
  `hoi4.py` only gains a thin subcommand that calls them, added at the end of `build_parser()`.
- The input, screen-check, time-control and console functions in `hoi4.py` are the PC lane: they can only be tested
  live.
- A batch adds its own `tests/test_<id>.py` instead of editing another batch's test file.

## How a batch is done

1. Take the top unclaimed row of your lane in `QUEUE.md`, read its brief, claim it (above).
2. Work on the branch. Commit small, with a message that says what and why. End each message with your model's
   `Co-Authored-By:` line.
3. Before each push: `python -m py_compile` on what you changed, and `python tests/test_offline.py` plus your own test
   file. `hoi4.py` loads Windows' `user32` when imported, so its tests need Windows; a module that does not import it
   can be tested anywhere.
4. Open a pull request into `main` early, as a draft if it is unfinished. Its description has these headings:
   - **What** and **why**, in a few lines.
   - **Checks run**, offline.
   - **How to verify in the game**: numbered steps with `hoi4.py` commands and what should be seen. Write "none" only
     if the change cannot affect the live game.
   - **Queue**: rows to delete, add, or move to Pending, and why.
5. The PC session pulls the branch, runs the checks, does the in-game steps, then merges with a merge commit, deletes
   the branch, applies the Queue changes, adds the changelog block, and comments on the PR with the result in at most
   15 lines. If a step fails, it comments what failed and leaves the PR open.

A batch that cannot be finished, or waits on Jerus, moves to **Pending** in `QUEUE.md` with why, the same turn, so the
lane's next row can start.

## Standing rules

- **Never commit** screenshots (`shots/`), runtime state (`state/`), the venv, game saves, or game files. Saves are
  60-300 MB and hold Jerus's campaigns; the game's files are Paradox's. A test fixture is a trimmed excerpt under
  1 MB in `tests/fixtures/`, made by the PC session.
- **Jerus's saves:** never overwrite or delete a save in `Documents/Paradox Interactive/Hearts of Iron IV/save games/`.
  A save the bridge makes is named `claude_<something>`. The game's own monthly `autosave.hoi4` overwrites itself;
  that is the game's setting, not ours.
- **No credentials anywhere:** no tokens or passwords in the repo, PRs or comments. Each account signs in as itself;
  the remote session never uses Jerus's account.
- **The game's settings** (`settings.txt`, keybinds, resolution, UI scale) change only when Jerus says so. The screen
  checks are calibrated for 1920x1200 at UI scale 1.0.
- **Play is legitimate:** decisions go through the game's interface. The console is for reading state (`report`),
  never for cheats that change the game (no `add_tech`, `add_equipment`, instant focuses).
- **@-mentions notify people:** write a real login only when you mean to reach that account. Put roles, placeholders
  and code in backticks.

## Every line you read is paid for

- `game.log` grows all game long: never read it whole. Use `hoi4.py tail 30 --grep '<pattern>'`, `hoi4.py state`,
  `hoi4.py news`.
- Screenshots cost the most. Use `look` at scale 0.5-0.6, and `zoom x0 y0 x1 y1` or `look --region` for detail.
- A report from one session to the other (PR comment, Pending row) is at most 15 lines.

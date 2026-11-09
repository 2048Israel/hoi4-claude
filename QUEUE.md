# The queue

The batches waiting, in order, one line each with a link to its brief, and nothing else.

- **Two lanes.** *Offline* needs no game (the remote session takes these). *PC* needs the live game (only the PC
  session can do these). Each session takes the **top unclaimed row of its lane**; a row is claimed when its
  `batch/<id>` branch exists on GitHub (`CLAUDE.md`, Branch or not).
- **Only the PC session edits this file**, on `main`. A branch says what should change under **Queue** in its PR.
- **Done: delete the row** in the merge that ships it. What shipped is `docs/changelog.md`'s to say.
- **Not done, or done in part:** delete the row and put what was not done under Pending, with why. A blocked batch
  moves to Pending the same turn, so the next row in its lane can start.
- **A Pending row leaves when Jerus reviews it:** back into the queue, or dropped.
- **No detail here.** The brief in `docs/queue/<id>.md` holds it.
- A new batch goes on the end of its lane unless Jerus places it. The order below was proposed by the PC session on
  2026-11-07; Jerus may reorder it.

## Queued

| batch | lane | what | brief |
|---|---|---|---|
| TH1 | Offline | The ten agent definitions of `docs/command.md`, each with a worked example (after OR1, ST1) | [TH1](docs/queue/TH1.md) |

The command structure these rows build is designed in [docs/command.md](docs/command.md) (2026-11-09).

## Pending

| batch | lane | waits on | brief |
|---|---|---|---|
| EX4 | PC | a live check of PR #4 (written offline; not run in the game) | [EX4](docs/queue/EX4.md) |
| EX5 | PC | game access | [EX5](docs/queue/EX5.md) |
| EX6 | PC | game access | [EX6](docs/queue/EX6.md) |
| TL1 | PC | game access, and TH1 | [TL1](docs/queue/TL1.md) |

Jerus, 2026-11-09: "dont open hoiv". The PC-lane batches need the game, so they wait here until Jerus says the
game may be used again. EX4's code is in PR #4, written and tested offline.

Removed 2026-11-07 (PC session), shipped in 0.1.2-0.1.3: **LV1** (general, front, enemy and ally lines are read
live by `report` and `act army push`; news hooks feed `news`), **PU1** (`read event`, `act event`, auto-dismissed
notices and news), and **EX2** except construction (focus, decisions, laws/advisors/staff, recruiting, production
by name are on `main`; construction moves to EX3). **EX3** shipped the same day as `act build` (by free slots; by
state name is still open).

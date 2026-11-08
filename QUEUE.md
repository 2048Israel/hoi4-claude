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
| OR1 | Offline | The orders format: what thinker agents send and the executor accepts (`hoi4_orders.py`, validator, tests) | [OR1](docs/queue/OR1.md) |
| SR1 | Offline | Save-file reader: an HOI4 text save into compact JSON for the player (research, production, construction, divisions) | [SR1](docs/queue/SR1.md) |
| TH1 | Offline | Thinker agents: economy, research and focus, politics and diplomacy, military; state in, orders out (after OR1) | [TH1](docs/queue/TH1.md) |
| EX3 | PC | Construction: queue factories, forts and infrastructure by state name; the rest of EX2 | [EX2](docs/queue/EX2.md) |

## Pending

| batch | lane | waits on | brief |
|---|---|---|---|

Removed 2026-11-07 (PC session), shipped in 0.1.2-0.1.3: **LV1** (general, front, enemy and ally lines are read
live by `report` and `act army push`; news hooks feed `news`), **PU1** (`read event`, `act event`, auto-dismissed
notices and news), and **EX2** except construction (focus, decisions, laws/advisors/staff, recruiting, production
by name are on `main`; construction moves to EX3).

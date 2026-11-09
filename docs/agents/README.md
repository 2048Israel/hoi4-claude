# The agents

The ten Claude Code subagents of [`command.md`](../command.md) live in [`.claude/agents/`](../../.claude/agents/),
one file each, at most 80 lines: what the agent owns and leaves to others, its goals, its doctrine for Germany
1936-1941, its ops and requests ([`orders.md`](../orders.md)), its input and reply, and one worked example. The turn
loop (TL1) runs them; Supreme Command is the orchestrating session itself, not a file here.

| Agent file | OR1 name | Model | Example input | Example reply |
|---|---|---|---|---|
| `hoi4-policy` | `policy` | sonnet | 3,365 | 1,003 |
| `hoi4-research` | `research` | sonnet | 3,880 | 637 |
| `hoi4-civilian-industry` | `civilian_industry` | sonnet | 2,168 | 1,211 |
| `hoi4-military-industry` | `military_industry` | sonnet | 1,408 | 668 |
| `hoi4-naval-industry` | `naval_industry` | sonnet | 983 | 959 |
| `hoi4-air` | `air` | sonnet | 3,094 | 1,731 |
| `hoi4-navy` | `navy` | sonnet | 1,827 | 873 |
| `hoi4-army` | `army` | fable | 4,863 | 1,212 |
| `hoi4-field-marshal` | `field_marshal_<group>`, one per army group | fable | 7,092 | 1,270 |
| `hoi4-operation` | `operation_<name>`, one per operation | fable | 3,216 | 1,072 |

Sizes are characters of compact JSON. The army tree (army, field marshals, operations) runs on the strongest model
(`fable`, Claude Fable 5.1); the rest on a cheaper one (`sonnet`). It is one line of each file's frontmatter. Every
agent has only the Read tool: it reads its input file and answers.

## Input

One JSON file per agent and turn (TL1 writes `state/turn/<n>/<agent>.json`; the prompt gives its path):

| Key | What |
|---|---|
| `agent` | its OR1 name, which every order's `by` must carry (`field_marshal_german_theater_1`, `operation_gdynia`) |
| `turn` | the turn number |
| `due` | why it runs now: its cadence, or a trigger ("slot 4 freed", "a support request from operation_gdynia") |
| `directive` | optional: Supreme Command's word to it (war aims, what not to do), a few lines |
| `budget` | what it may spend this turn: `pp`, `cp`, `civ_factories`, `mil_factories`, `dockyards`, `manpower` |
| `state` | its ST1 slice (`hoi4_slices.py`), as is |
| `notes` | its own `notes` from its last reply (kept in `state/agents/<role>.md`) |
| `requests` | OR1 requests addressed to it |
| `results` | what happened to its last orders, by id (`results_for`) |

## Reply

One JSON object and nothing else: `{orders, requests, report, notes}` (`orders.md`, The reply). `python
hoi4_orderspec.py check REPLY.json --agent NAME` checks one.

## The examples

`examples/<role>.in.json` and `.out.json`: the input an agent gets and the reply it should give. Each agent file
holds the same reply in its Example section. `tests/test_TH1.py` checks them all: each reply passes OR1 for its
agent and stays within its budget, the ten merged as one turn have no conflict, and each request an input carries
was made by another example's reply (army and air ask military industry; operation gdynia asks air).

Every `state` is a real ST1 slice of `claude_ger_1939_11_stop.hoi4` (1 November 1939: at war with Poland, Britain
and France since 25 August; no focus running, 722 PP, 8 of 12 dockyards and three wings idle, no army on the French
border). Turn numbers, `directive`, `notes`, `requests`, `results` and budgets were written for the examples.
Changed or trimmed by hand:

- policy: `can_start` cut to 12 of 31 focuses, `wars` to 8 of 16 enemies (the British dominions and mandates).
- research: the day Advanced Machine Tools ends (it had 19 days left): slot 4 free, the tech moved to `researched`.
- civilian industry: `states` cut to 12 of 36.
- military industry: `factories` (100, 6 free) filled in by hand; the bridge report was not in `game.log`.
- naval industry: `dockyards` (12, 8 free) from the Production screen on 1939-11-01 (EX4's live reading).
- operation: the charter is the field marshal example's `operation.start`; `around` and `enemy_seen` cut to
  Gdynia, Hinterpommern and Poznań.

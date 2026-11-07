# SR1: the save-file reader

**Lane:** Offline. **Module:** `hoi4_save.py`, `tests/test_SR1.py`, fixtures in `tests/fixtures/`.

## Why

Jerus, 2026-11-07: "something where they dont have to take pictures, just get data fed to them". The bridge mod
already logs what the game's script can see: political power, factories, manpower, equipment against what the army
wants, wars, neighbors (`hoi4.py state`). Script cannot see what each research slot is doing, the production lines,
the construction queue, or where divisions are. A save file holds all of it. The console's `savegame` (alias `save`)
writes one on demand.

## What

- A parser for HOI4's text save format (Clausewitz script): `key=value`, `key={ ... }` blocks, lists of bare values,
  quoted strings, dates like `1936.2.25.12`, repeated keys (keep them all, in order). The file starts with
  `HOI4txt`. It must be fast on a large file: saves run to hundreds of MB. Measure it, and prefer a streaming
  tokenizer that can skip blocks it does not need.
- `extract(path, tag)` returns compact JSON for one country: research slots (tech, progress), production lines
  (equipment, factories, efficiency), construction queue (building, state, progress), divisions (name, template,
  location, strength, organization), and the national focus in progress. The real keys are below, under "What SR0
  found". Build against `tests/fixtures/ger_1936_02_25.txt`, plus small handmade fixtures for edge cases.
- A CLI: `python hoi4_save.py <save> --tag GER` prints the JSON. The PC session wires `hoi4.py snapshot` (console
  `save claude_snapshot`, then this) when it merges.
- No import of `hoi4.py`, no third-party packages: it must run and test on any machine.

## What SR0 found (2026-11-07)

The real fixture is `tests/fixtures/ger_1936_02_25.txt`: Germany on 1936-02-25, 514 KB, cut from a 66 MB text save
by `tools/cut_save_fixture.py` (the same save was 42.5 MB as binary). `tests/test_SR0.py` guards it. What the fixture
shows; confirm each against it:

- **Header:** plain `key=value` lines, including `player="GER"`, `date="1936.2.25.12"` and `version=...`. The
  `player_countries` block's `user=` is redacted.
- **Research:** `countries.GER.technology.slots`. Each child is a tech in progress, for example `interwar_artillery`,
  with `used_saved_points` and `points_factor`. Days left is not stored there directly; find it. Researched techs
  are `technology.technologies.<tech>` with `level`, `research_points` and `date`.
- **Focus:** `countries.GER.focus`, with `current="GER_remilitarize_the_rhineland"`, `progress=8` and `completed=`.
  `completed` probably repeats once per completed focus.
- **Production:** `countries.GER.production` has repeated `military_lines`, `naval_lines` and `general_lines`
  blocks. A line has `active_factories`, `requested_factories`, `speed`, `amount` (-1 = no limit) and
  `equipment_variant_index={ id=N type=70 }`. That id points at the top-level `equipments` entry whose key is the
  equipment name (`convoy_1`, `infantry_equipment_0` ...) and whose `creator` is the designer.
- **Construction:** probably `general_lines` (6 civilian factories were queued in Sachsen and Hannover). Not
  confirmed.
- **Divisions:** repeated `countries.GER.units.division` blocks with `location` (a province id), `organisation`,
  `strength`, `division_template_id={ id=N type=52 }` and per-equipment `amount`. Templates are top-level
  `division_templates.division_template`, with `id`, `name`, `country` and `regiments`.
- **States:** top-level `states.<id>` with `owner`, `buildings` (level per building) and `manpower_pool`. Province to
  state mapping is not in the fixture.
- **Shape quirks:** keys repeat (keep them all); anonymous blocks `{ ... }` appear inside lists; numbers come as
  `53.62744`, `-1` and so on. Dates are quoted in the header but not always elsewhere.
- **Line endings are mixed:** the game writes both LF and CRLF in one save. The fixture keeps them byte-for-byte
  (`.gitattributes`), so treat `\r` as whitespace.

## Done when

- `tests/test_SR1.py` passes on the real fixture and the handmade ones.
- The README says how long a full save takes to read on a real file, once measured on the PC.
- Binary saves (`HOI4bin`) fail with a clear message pointing at SR0's setting.

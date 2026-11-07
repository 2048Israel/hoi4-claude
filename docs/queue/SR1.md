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
  location, strength, organization), and the national focus in progress. Find the real keys from SR0's fixture.
  Until it lands, build against small handmade fixtures and mark every key that is still a guess.
- A CLI: `python hoi4_save.py <save> --tag GER` prints the JSON. The PC session wires `hoi4.py snapshot` (console
  `save claude_snapshot`, then this) when it merges.
- No import of `hoi4.py`, no third-party packages: it must run and test on any machine.

## Done when

- `tests/test_SR1.py` passes on the handmade fixtures, and on SR0's real one once it exists.
- The README says how long a full save takes to read on a real file, once measured on the PC.
- Binary saves (`HOI4bin`) fail with a clear message pointing at SR0's setting.

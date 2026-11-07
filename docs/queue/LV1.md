# LV1: verify the unseen bridge lines

**Lane:** PC, done during play.

The mod writes these lines, and the report formats them, but none has appeared in a real game yet:

- ~~`general`~~: seen live on 1939-05-15 (four generals, divisions, entrenchment, battle plans).
- `front`, `enemy`, `ally`: need a war.
- `news`: `on_declare_war`, `on_capitulation`, `on_annex`, `on_puppet`, `on_peaceconference_ended`,
  `on_create_faction`, `on_join_faction`, `on_government_change`. The first will fire with the first war or new
  government anywhere.

For each: confirm the line appears in `game.log` (`hoi4.py tail 20 --grep '@CB;general'` and so on), that its values
make sense against the game's own screen, and that `hoi4.py report` or `news` shows it cleanly. Fix what is wrong. A
line that cannot be checked yet stays on this list.

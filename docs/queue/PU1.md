# PU1: event popups

**Lane:** PC.

Events open popups that wait for a choice (the first was "National Focus Completed" on 1936-02-25). Today they are
only noticed when `advance` reports that time stopped on its own, or a screenshot happens to show one.

- **Notice:** after `advance`, and at the start of `look`, check cheaply for an open popup. One known region, or a
  `game.log` line if the game writes one.
- **Read:** crop the popup alone (title, text, options) at a readable scale, so the player reads a small image
  instead of the whole screen.
- **Choose:** `hoi4.py popup <n>` clicks option n, then checks the popup closed.

Done when the three steps work on at least two different events in the live game.

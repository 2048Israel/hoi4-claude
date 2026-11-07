# SR0: a real text-save fixture

**Lane:** PC. **Pending:** waits on Jerus.

SR1 needs a real HOI4 text save to find the actual keys and to test against. Jerus's `settings.txt` has
`save_as_binary=yes`, so saves are binary (`HOI4bin`), which no public parser reads reliably.

**The question for Jerus:** may `save_as_binary` be set to `no`? This affects all his saves. Text saves are larger and
take longer to write. It can be set back at any time.

Once allowed:

1. Set it in `Documents/Paradox Interactive/Hearts of Iron IV/settings.txt`.
2. Write `claude_snapshot` with the console `save` command, and record its size and how long it took.
3. Cut fixtures under 1 MB from it: the header, the player country's research, production, construction and units
   sections, and enough of the rest to show the shapes.
4. Check the fixtures hold nothing personal. Commit them in `tests/fixtures/`, never the whole save.

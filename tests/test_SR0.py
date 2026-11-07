"""SR0: the real text-save fixture stays small, redacted and complete.

Standard library only, no game needed:  python tests/test_SR0.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import cut_save_fixture as cut  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "ger_1936_02_25.txt"


def main():
    data = FIXTURE.read_bytes()
    assert data.startswith(b"HOI4txt"), "a text save starts with HOI4txt"
    assert len(data) < 1_000_000, f"fixtures stay under 1 MB, this is {len(data):,}"

    names = re.findall(rb'\n\s*(?:user|player_name|name_of_player|steam_id|pdx_id|account)\s*=\s*"([^"]*)"', data)
    assert names and all(n == b"REDACTED" for n in names), f"unredacted player name fields: {names}"

    tops = [k for k, *_ in cut.top_blocks(data)]  # also proves the braces balance
    for section in ("countries", "equipments", "division_templates", "states"):
        assert section in tops, f"missing section {section}"

    assert b'player="GER"' in data and b'date="1936.2.25.12"' in data
    for needle in (b"\t\tfocus={", b"\t\t\tslots={", b"\t\t\tmilitary_lines={", b"\t\t\tdivision={"):
        assert needle in data, f"Germany's block should contain {needle!r}"
    assert b'current="GER_remilitarize_the_rhineland"' in data
    assert b"interwar_artillery={" in data  # one of the five research slots
    print("SR0 FIXTURE CHECKS PASSED")


if __name__ == "__main__":
    main()

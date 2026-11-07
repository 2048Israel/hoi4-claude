r"""Offline checks for hoi4_orders.py: the standing-orders file and the stalled-army test.

No game needed, but Windows is (hoi4.py loads user32):  .venv\Scripts\python.exe tests\test_ORD.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_orders as O  # noqa: E402


def main():
    plan = Path(tempfile.mkdtemp()) / "orders.txt"
    plan.write_text("# comment\n5 Guderian Berlin\n3 Rommel Lwow  # east\n\n1 Rundstedt Frankfurt an der Oder\n",
                    encoding="utf-8")
    orders = O.read_plan(plan)
    assert orders[0] == {"army": 5, "general": "Guderian", "city": "Berlin"}
    assert orders[1]["city"] == "Lwow" and orders[2]["city"] == "Frankfurt an der Oder"
    plan.write_text("Guderian Berlin\n", encoding="utf-8")
    try:
        O.read_plan(plan)
        raise AssertionError("a line without an army number must be refused")
    except O.ActionError:
        pass
    gens = [{"name": "Heinz Guderian", "units": "12", "in_combat": "0"},
            {"name": "Maximilian von Weichs", "units": "19", "in_combat": "19"}]
    assert O.find_general(gens, "guderian")["name"] == "Heinz Guderian" and O.find_general(gens, "Bock") is None
    assert O.stalled(gens[0], 0.35) and not O.stalled(gens[1], 0.35)
    assert not O.stalled({"units": "0", "in_combat": "0"}, 0.35), "an empty army is not re-ordered"
    print("ORD OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

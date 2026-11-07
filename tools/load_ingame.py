r"""Load a save from inside a running game: Esc menu > Load Game > pick the save > Load, then wait for the map.

Usage: .venv\Scripts\python.exe tools\load_ingame.py claude_ger_1940_06_breach
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hoi4
import hoi4_actions as A

name = sys.argv[1]
h = hoi4.need_window()
hoi4.focus(h)
A.deselect(h)
before = A.read_date(h)
hoi4.press_combo("esc")
time.sleep(1.0)
menu = A.read_box(h, [760, 300, 1160, 780])
load = [l for l in menu if A.norm(l.text) in ("loadgame", "load")]
if not load:
    raise SystemExit("game menu not open: " + str([l.text for l in menu]))
hoi4.click(h, 961, load[0].center[1])
time.sleep(2.0)
entry = A.find_text(h, name, (640, 360, 1200, 900), timeout=10)
hoi4.click(h, *entry.center)
time.sleep(1.0)
btn = [l for l in A.read_box(h, [640, 880, 1200, 940]) if A.norm(l.text) == "load"]
hoi4.click(h, *(btn[0].center if btn else (1062, 913)))
time.sleep(5)
deadline = time.time() + 180
while time.time() < deadline:
    d = A.read_date(h)
    if d and ", 19" in d:
        print(f"loaded {name}: {d} (was {before})")
        break
    time.sleep(3)
else:
    raise SystemExit("the game did not come back within 3 minutes")

r"""Load a save from inside a running game: Esc menu > Load Game > pick the save > Load, then wait for the map.

Usage: .venv\Scripts\python.exe tools\load_ingame.py claude_ger_1940_06_breach
"""
import re
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
# the list shows about six saves, newest first: scroll down until the name shows up
entry = None
hoi4.scroll(h, 960, 640, 40)  # start from the top (newest)
time.sleep(0.6)
for _ in range(40):  # ~60 saves, newest game date first
    # an exact name first; OCR can bend one character of a long name, so a very near match (0.97) also counts.
    # 0.9 was too loose: claude_ger_1939_06_prewar matched claude_ger_1939_08_25_prewar and loaded the wrong save
    lines = A.read_box(h, [640, 360, 1200, 900])
    exact = [l for l in lines if A.norm(l.text) == A.norm(name)]
    digits = lambda t: re.sub(r"\D", "", t)
    near = sorted((l for l in lines if digits(l.text) == digits(name) and A.similar(name, l.text) >= 0.8),
                  key=lambda l: -A.similar(name, l.text))
    if exact or near:
        entry = (exact or near)[0]
        print(f"picked {entry.text!r}")
        break
    hoi4.scroll(h, 960, 640, -3)
    time.sleep(0.6)
if entry is None:
    raise SystemExit(f"{name} is not in the load list")
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

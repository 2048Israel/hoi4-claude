r"""Reload a claude_ save through the main menu: Esc > Exit to Menu > OK > (summary) Exit to Menu > load-save.
Used when the in-game load list does not reach the save (it lists every save of every campaign, newest game
date first, and long lists do not scroll far enough).

Usage: .venv\Scripts\python.exe tools\reload_from_menu.py claude_ger_1939_08_25_prewar
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hoi4
import hoi4_actions as A

name = sys.argv[1]
if not name.startswith("claude_"):
    raise SystemExit("only claude_ saves are loaded by tools")
h = hoi4.need_window()
hoi4.focus(h)
A.deselect(h)
hoi4.press_combo("esc")
time.sleep(1.0)
menu = A.read_box(h, [760, 300, 1160, 780])
ex = [l for l in menu if A.norm(l.text) == "exittomenu"]
if not ex:
    raise SystemExit("game menu not open: " + str([l.text for l in menu]))
hoi4.click(h, *ex[0].center)
time.sleep(1.5)
ok = [l for l in A.read_box(h, [560, 300, 1360, 900]) if A.norm(l.text) in ("ok", "0k")]
if not ok:
    raise SystemExit("no OK on the resign dialog")
hoi4.click(h, *ok[0].center)
time.sleep(3)
b = A.find_text(h, "Exit to Menu", (1300, 960, 1700, 1080), timeout=30)
hoi4.click(h, *b.center)
A.load_save(h, name)

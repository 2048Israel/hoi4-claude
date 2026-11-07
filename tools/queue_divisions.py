"""Queue N infantry divisions: Train N times, set each new line from infinity to 1, give each a location.

Interim tool until EX2 adds `act recruit`. Usage: .venv\Scripts\python.exe tools\queue_divisions.py 10
"""
import sys
import time

sys.path.insert(0, r"C:\Users\Jerus\hoi4-claude")
import hoi4
import hoi4_actions as A

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
h = hoi4.need_window()
hoi4.focus(h)
A.dismiss_notices(h)
A.open_screen(h, "recruit")
train = [l for l in A.read_box(h, [700, 280, 1110, 360]) if A.norm(l.text) == "train"]
if not train:
    raise SystemExit("Infanterie-Division Train button not found")
for _ in range(N):
    hoi4.click(h, *train[0].center)
    time.sleep(0.45)


def counts():
    return [l for l in A.read_box(h, [0, 480, 700, 1200]) if l.box[0] > 480 and l.text.startswith("1/")]


fixed = 0
hoi4.scroll(h, 330, 900, 40)
time.sleep(0.4)
for _ in range(N * 3):
    inf = [l for l in counts() if l.text[2:] != "1"]
    if not inf:
        before = [l.text for l in A.read_box(h, [0, 480, 700, 1200])]
        hoi4.scroll(h, 330, 900, -6)
        time.sleep(0.45)
        if [l.text for l in A.read_box(h, [0, 480, 700, 1200])] == before:
            break
        continue
    y = inf[0].center[1]
    hoi4.click(h, 522, y - 140)
    time.sleep(0.5)
    # re-read the same row: only move on once it shows 1/1, so a slow redraw cannot cause a second "+"
    if any(abs(l.center[1] - y) < 12 and l.text[2:] == "1" for l in counts()):
        fixed += 1
    else:
        time.sleep(0.5)
print("set to 1:", fixed)

placed = 0
hoi4.scroll(h, 330, 900, 40)
time.sleep(0.4)
for _ in range(N * 3):
    unset = [l for l in A.read_box(h, [0, 480, 700, 1200]) if "location" in l.text.lower() and l.box[0] < 400]
    if not unset:
        before = [l.text for l in A.read_box(h, [0, 480, 700, 1200])]
        hoi4.scroll(h, 330, 900, -6)
        time.sleep(0.45)
        if [l.text for l in A.read_box(h, [0, 480, 700, 1200])] == before:
            break
        continue
    hoi4.click(h, *unset[0].center)
    time.sleep(0.8)
    hoi4.click(h, 1170, 480)
    time.sleep(0.8)
    placed += 1
print("locations set:", placed)
A.close_screen(h, "recruit")

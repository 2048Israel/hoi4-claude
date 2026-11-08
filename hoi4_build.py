"""Construction (t): queue buildings in the states with the most free slots.

How the game does it (1.19.4, seen live on 1939-06-26):
- The Construction screen lists the queue on the left and the building icons in a second column (Military Factory
  at (594, 420), Civilian Factory (650, 420), Synthetic Refinery (770, 420), Infrastructure (594, 244), ...).
- Clicking an icon arms it, and every state on the map gets a label "used/total" (building slots) with a
  percentage under it. Clicking a state (its label) queues one of that building there; clicking again adds one.
- The panels cover the map left of x ~870, so only states right of that can be clicked at the current camera.
"""
import re
import time

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

B = A.T["build"]


def queue_rows(hwnd):
    """The queue's rows as OCR reads them (location names in the left column)."""
    return [l for l in A.read_box(hwnd, B["queue_box"]) if A.HAS_WORD.search(l.text)
            and "consumer" not in l.text.lower() and l.box[0] < B["queue_name_x_max"]]


def slot_labels(hwnd):
    """[(free, used, total, line)] for every state label "used/total" on the visible map, most free first."""
    out = []
    for l in A.read_box(hwnd, B["map_box"], park=True):
        m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", l.text.replace(" ", "").translate(A.DIGIT_FIX))
        if m:
            used, total = int(m.group(1)), int(m.group(2))
            if 0 < total <= 99 and used <= total:
                out.append((total - used, used, total, l))
    return sorted(out, key=lambda t: -t[0])


def build(hwnd, building, count, per_state=2, log=print):
    """Queue `count` of `building` (a key of build.buildings), at most `per_state` in one state."""
    if building not in B["buildings"]:
        raise ActionError(f"unknown building {building!r}; known: {', '.join(B['buildings'])}")
    A.open_screen(hwnd, "construction")
    before = len(queue_rows(hwnd))
    hoi4.click(hwnd, *B["buildings"][building])
    time.sleep(1.0)
    labels = [t for t in slot_labels(hwnd) if t[0] > 0]
    if not labels:
        raise ActionError("no state label with free slots is visible right of the panels "
                          "(move the camera so your states show, e.g. act camera home)")
    queued = 0
    for free, used, total, l in labels:
        for _ in range(min(per_state, free)):
            if queued >= count:
                break
            hoi4.click(hwnd, *l.center)
            time.sleep(0.5)
            queued += 1
        if queued >= count:
            break
    time.sleep(0.6)
    after = len(queue_rows(hwnd))
    log(f"clicked {queued} state label(s) for {building}; queue rows {before} -> {after}")
    if after <= before:
        raise ActionError("the construction queue did not grow; check the screen (look)")
    A.close_screen(hwnd, "construction")
    return queued

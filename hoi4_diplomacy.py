"""Diplomacy: take an action on another country (declare war, justify a war goal, military access, ...).

How the game does it (1.19.4, seen live on 1939-08-25):
- Right-clicking a foreign country's land opens the Diplomacy screen on that country: its name at the top left
  (x 300, y 175), and an "Actions" list (x 340-640, rows ~36 px apart from y 660). Actions that cannot be taken
  have a red X; costs show at the right of the row.
- Clicking an action opens a confirm popup; RETURN sends it (PLAYBOOK: countrydiplomacyview.gui, RETURN = send).
"""
import time

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

D = A.T["diplomacy"]


def open_country(hwnd, city):
    """Open the Diplomacy screen of the country that owns `city` (found with the map's Find window)."""
    A.deselect(hwnd)
    pt = A.find_city(hwnd, city)
    hoi4.click(hwnd, *pt, button="right")
    time.sleep(1.2)
    head = " ".join(l.text for l in A.read_box(hwnd, D["header_box"]))
    if "diplomacy" not in A.norm(A.screen_title(hwnd)):
        raise ActionError(f"no Diplomacy screen opened by right-clicking {city} (title: {A.screen_title(hwnd)!r})")
    return head


def actions(hwnd):
    return [l for l in A.read_box(hwnd, D["actions_box"]) if A.HAS_WORD.search(l.text)
            and l.box[0] < D["action_name_x_max"] and A.norm(l.text) != "actions"]


def act(hwnd, city, action, dry_run=False, log=print):
    head = open_country(hwnd, city)
    rows = actions(hwnd)
    best = max(rows, key=lambda l: A.similar(action, l.text), default=None)
    if best is None or A.similar(action, best.text) < 0.8:
        raise ActionError(f"{head}: no action like {action!r}; actions read: {[l.text for l in rows]}")
    tip = " | ".join(l.text for l in A.hover_tooltip(hwnd, *best.center, x_min=best.box[0] - 20))
    log(f"{head}: {best.text}: {tip[:300]}")
    if dry_run:
        return
    hoi4.click(hwnd, *best.center)
    time.sleep(1.0)
    popup = " ".join(l.text for l in A.read_box(hwnd, D["confirm_box"]))
    log(f"confirm popup: {popup[:200]}")
    hoi4.press_combo("enter")
    time.sleep(1.5)
    log(f"sent: {best.text}")

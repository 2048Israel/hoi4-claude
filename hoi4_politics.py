"""Laws, advisors, military staff and the government-formation slots of the Politics screen (q).

How the game does it (1.19.4 with the user's mods, seen live in May-July 1940):
- The Politics screen shows rows of idea slots: Laws & Government (three laws, then three political advisors),
  Research & Production, Military Staff, and a mod's Government Formation row. Slot positions are in
  ui_targets.json ("politics" -> "slots").
- Clicking a slot opens a list to its right (x 690-1300): a title ("Select Political Advisor"), then one row per
  choice about 92 px apart, name at x 793. Hovering a row shows its effects and requirements; clicking it takes it.
- A filled slot's list replaces what is there, and laws ask "REPLACE IDEA: ... for a total cost of N?" with an OK
  button. Taking a choice spends political power, which is the check.
"""
import re
import time

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

PO = A.T["politics"]


def slot_point(slot):
    if slot not in PO["slots"]:
        raise ActionError(f"unknown slot {slot!r}; known: {', '.join(PO['slots'])}")
    return PO["slots"][slot]


def list_open(hwnd):
    x0, y0, x1, _ = PO["list_box"]
    return "select" in " ".join(l.text for l in A.read_box(hwnd, [x0, y0, x1, PO["list_rows_top"]])).lower()


def close_list(hwnd):
    """Close a slot's list, only if one is open: with none, its X spot is a top-bar alert that opens another
    screen (seen 1939-06-26: the Politics screen went away and the next click opened a state view)."""
    if list_open(hwnd):
        hoi4.click(hwnd, *PO["list_close"])
        time.sleep(0.4)


def open_slot(hwnd, slot):
    """Open a slot's list; returns (title, [name lines])."""
    A.open_screen(hwnd, "politics")
    close_list(hwnd)
    if not A.is_open(hwnd, "politics"):
        raise ActionError("the Politics screen is not open; nothing clicked")
    hoi4.click(hwnd, *slot_point(slot))
    time.sleep(1.2)
    lines = A.read_box(hwnd, PO["list_box"])
    title = " ".join(l.text for l in lines if l.box[1] < PO["list_rows_top"])
    if not title.strip():
        raise ActionError(f"no list opened for slot {slot}")
    # most lists are one column of names at x 793; Military High Command is a grid of two (x ~790 and ~1080)
    names = [l for l in lines if any(x0 < l.box[0] < x1 for x0, x1 in PO["name_cols"])
             and l.box[1] >= PO["list_rows_top"] and A.HAS_WORD.search(l.text)
             and not re.fullmatch(r"[\d\s%+.,-]+", l.text)]
    return title, names


def choices(hwnd, slot, log=print):
    """Each choice of a slot with its tooltip (effects, requirements, cost)."""
    title, names = open_slot(hwnd, slot)
    log(title)
    out, seen = [], set()
    for n in names:
        tip = " | ".join(l.text for l in A.hover_tooltip(hwnd, n.box[0] + PO["hover_dx"], n.center[1], x_min=PO["list_box"][0]))
        head = tip.split(" | ")[0] if tip else n.text
        if head in seen:  # a long name wraps onto two lines: one tooltip
            continue
        seen.add(head)
        out.append({"name": head, "y": n.center[1], "tip": tip})
        log(f"  {head}: {tip[len(head) + 3:][:220]}")
    close_list(hwnd)
    return out


def take(hwnd, slot, name, dry_run=False, replace=False, log=print):
    """Take the choice named like `name` in a slot's list; checks that political power was spent. A law always
    replaces the one in force; any other slot that is already filled is left alone unless replace=True."""
    title, names = open_slot(hwnd, slot)
    best = max(names, key=lambda l: A.similar(name, l.text), default=None)
    if best is None or A.similar(name, best.text) < 0.75:
        close_list(hwnd)
        raise ActionError(f"{title}: no choice like {name!r}; read: {[l.text for l in names][:12]}")
    tip = " | ".join(l.text for l in A.hover_tooltip(hwnd, best.box[0] + PO["hover_dx"], best.center[1], x_min=PO["list_box"][0]))
    log(f"{title}: {best.text}: {tip[:300]}")
    if dry_run:
        close_list(hwnd)
        return
    pp = A.read_pp(hwnd)
    hoi4.click(hwnd, best.box[0] + PO["hover_dx"], best.center[1])
    time.sleep(1.0)
    # laws (and replacing a filled slot) ask to confirm: read the dialog before pressing its OK
    dialog = A.read_box(hwnd, PO["confirm_box"])
    text = " ".join(l.text for l in dialog).lower()
    if "replace" in text and not (slot.startswith("law-") or replace):
        cancel = [l for l in dialog if A.norm(l.text) in ("cancel", "no", "back")]
        if cancel:
            hoi4.click(hwnd, *cancel[0].center)
            time.sleep(0.6)
        raise ActionError(f"slot {slot} is filled and taking {best.text} would replace it ({text[:120]!r}); "
                          "nothing replaced. Pick an empty slot, or add --replace")
    if "replace" in text:
        ok = [l for l in dialog if A.norm(l.text) == "ok"]
        if not ok:
            raise ActionError(f"a confirm dialog opened but no OK was read: {text[:120]!r}")
        log(f"confirm: {text[:160]}")
        hoi4.click(hwnd, *ok[0].center)
        time.sleep(1.0)
    after = A.read_pp(hwnd)
    if pp is not None and after is not None and after < pp:
        log(f"took {best.text}: political power {pp:.0f} -> {after:.0f}")
        A.close_screen(hwnd, "politics")
        return best.text
    raise ActionError(f"clicked {best.text!r} but political power did not drop ({pp} -> {after}); a red X in the "
                      "list means its requirements are not met (see the tooltip above)")

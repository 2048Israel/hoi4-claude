"""Air wings, in the air map mode: read a base's wings and their orders, give wings a mission over a region, move
wings to another base. Points are screen points at the standard camera (`hoi4.py act camera home`).

How the game does it (1.19.4, seen live on 1940-07-31):
- Clicking an air base's icon switches the map to the air mode and opens the base's panel at the top left, one
  row per wing, 60 px apart (in the air mode, its wing boxes open it too). F1 goes back to the Default map mode.
- Clicking a row selects that wing; shift-click adds one. The mission bar (top left, y 128) arms a mission; it is a
  toggle, so an armed mission (green check) is not clicked again.
- With wings selected and a mission armed, a RIGHT-click on a region assigns them ("Right-Click to assign selected
  Air Wings to this area"). A right-click on another air base moves them there ("Right-Click to move selected Air
  Wings to this base"). A left-click on the map only opens that region's panel and drops the selection.
- Hovering a wing's second line says its order: "100 of Fighter have the order: Air Superiority" or
  "... waiting for orders".
- `l` opens the Air Forces Overview: every wing with its base and area. Clicking a row there switches the map to
  the air mode, opens that wing's base panel and selects the wing, so a base can be reached by name; clicking a
  base icon on the default map can hit a battle icon drawn over it instead.
"""
import re
import time

import numpy as np

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

AIR = A.T["air"]


def mission_armed(hwnd, mission):
    x = AIR["missions"][mission]
    A.park_mouse(hwnd)
    y0, y1 = AIR["mission_check_band"]
    c = np.asarray(hoi4.grab(hwnd).convert("RGB")).astype(int)[y0:y1, x - 24:x + 24]
    green = (c[..., 1] > 120) & (c[..., 1] > c[..., 0] + 40) & (c[..., 1] > c[..., 2] + 40)
    return int(green.sum()) > 10


def air_view_open(hwnd):
    """The mission bar shows only in the air map mode; its Pilot Exercises button is always green."""
    x = AIR["missions"]["exercises"]
    y0, y1 = AIR["mission_check_band"]
    A.park_mouse(hwnd)
    c = np.asarray(hoi4.grab(hwnd).convert("RGB")).astype(int)[y0:y1, x - 24:x + 24]
    green = (c[..., 1] > 120) & (c[..., 1] > c[..., 0] + 40) & (c[..., 1] > c[..., 2] + 40)
    return int(green.sum()) > 40


def open_air_view(hwnd):
    """Nothing to press: clicking an air base's icon switches the map to the air mode by itself."""


def close_air_view(hwnd):
    close_base(hwnd)
    hoi4.press_combo(AIR["land_view_key"])  # F1: the Default map mode
    time.sleep(0.6)


def read_overview(hwnd, keep_open=False):
    """Every wing in the Air Forces Overview: [{'name', 'base', 'area', 'y'}]."""
    A.open_screen(hwnd, "air")
    first, step = AIR["overview_first_y"], AIR["overview_step"]
    c_base, c_area = AIR["overview_cols"]
    rows = {}
    for l in A.read_box(hwnd, AIR["overview_box"]):
        k = round((l.center[1] - first) / step)
        if k < 0 or abs(l.center[1] - (first + k * step)) > 10 or not A.HAS_WORD.search(l.text):
            continue
        col = "name" if l.box[0] < c_base else "base" if l.box[0] < c_area else "area"
        row = rows.setdefault(k, {"name": "", "base": "", "area": "", "y": round(first + k * step)})
        row[col] = (row[col] + " " + l.text).strip()
    if not keep_open:
        A.close_screen(hwnd, "air")
    return [rows[k] for k in sorted(rows) if rows[k]["name"]]


def open_base_by_name(hwnd, base):
    """Open a base's panel through the overview (click one of its wings there)."""
    rows = read_overview(hwnd, keep_open=True)
    hit = [r for r in rows if A.similar(base, r["base"]) >= 0.75 or A.norm(base) in A.norm(r["base"])]
    if not hit:
        A.close_screen(hwnd, "air")
        bases = sorted(set(r["base"] for r in rows))
        raise ActionError(f"no wing is based at {base!r}; bases with wings: {bases}")
    hoi4.click(hwnd, AIR["overview_click_x"], hit[0]["y"])
    head = A.wait_for(lambda: base_header(hwnd), timeout=2.0)
    if not head:
        raise ActionError(f"clicking {hit[0]['name']} in the overview opened no base panel")
    return head


def open_target(hwnd, base_pt=None, base=None):
    return open_base_by_name(hwnd, base) if base else open_base(hwnd, base_pt)


def base_header(hwnd):
    """(name, 'used/capacity') of the open base panel, or None."""
    lines = A.read_box(hwnd, AIR["header_box"])
    # OCR reads "340/1000" as "340/1 ooo": drop spaces and fix letters read for digits
    caps = [l.text.replace(" ", "").translate(A.DIGIT_FIX) for l in lines]
    cap = next((c for c in caps if re.fullmatch(r"\d+/\d+", c)), None)
    name = next((l.text for l, c in zip(lines, caps) if A.HAS_WORD.search(l.text) and "selected" not in l.text.lower()
                 and not re.fullmatch(r"[\d/]+", c)), None)
    return (name, cap) if name and cap else None


def close_base(hwnd):
    if base_header(hwnd):
        hoi4.click(hwnd, *AIR["panel_close"])
        time.sleep(0.5)


def open_base(hwnd, pt):
    """Open the panel of the air base whose icon (or wing box) is at pt. A panel already open is closed first:
    a click meant for the map would otherwise land on the panel's buttons."""
    close_base(hwnd)
    hoi4.click(hwnd, *pt)
    head = A.wait_for(lambda: base_header(hwnd), timeout=1.5)
    if not head:
        raise ActionError(f"no air base panel opened at {pt}; click an air base icon or its wing box")
    return head


def wing_rows(hwnd):
    """The open panel's wings: [{'name', 'y'}], read by the 60 px row grid."""
    first, step = AIR["row_first_y"], AIR["row_step"]
    rows = []
    for l in A.read_box(hwnd, AIR["panel_box"]):
        if not AIR["row_name_x"][0] < l.box[0] < AIR["row_name_x"][1] or l.center[1] < first - 10:
            continue
        k = round((l.center[1] - first) / step)
        if abs(l.center[1] - (first + k * step)) <= 9 and k not in [r["k"] for r in rows]:
            rows.append({"k": k, "name": l.text, "y": first + k * step})
    return sorted(rows, key=lambda r: r["k"])


def wing_order(hwnd, y, tries=3):
    """'Air Superiority', 'Close Air Support', 'waiting', or the tooltip text as read. The tooltip finder sometimes
    catches the map instead (a battle icon changing at the same time), so read again until it makes sense."""
    tip = ""
    for _ in range(tries):
        tip = " ".join(l.text for l in A.hover_tooltip(hwnd, AIR["status_hover_x"], y + 20,
                                                       x_min=AIR["status_hover_x"] - 25))
        m = re.search(r"have the order[.:]?\s*(.+?)(?:\s+Wing XP|\s+Majority|$)", tip)
        if m:
            return m.group(1).strip()
        if "waiting for orders" in tip:
            return "waiting"
    return tip[:60] or "?"


def read_base(hwnd, pt=None, log=print, base=None):
    head = open_target(hwnd, pt, base)
    rows = wing_rows(hwnd)
    log(f"{head[0]} ({head[1]} planes): {len(rows)} wing(s)")
    for r in rows:
        r["order"] = wing_order(hwnd, r["y"])
        log(f"  {r['name']}: {r['order']}")
    return head, rows


def select_wings(hwnd, rows):
    for i, r in enumerate(rows):
        hoi4.click(hwnd, AIR["row_click_x"], r["y"], mods=() if i == 0 else ("shift",))
        time.sleep(0.35)
    sel = " ".join(l.text for l in A.read_box(hwnd, AIR["selected_box"]))
    m = re.search(r"(\d+)\s*Selected", sel)
    if not m or int(m.group(1)) != len(rows):
        raise ActionError(f"meant to select {len(rows)} wing(s); the panel says {sel!r}")


def pick(rows, only):
    if not only:
        return rows
    words = [w.strip().lower() for w in only.split(",") if w.strip()]
    return [r for r in rows if any(w in r["name"].lower() for w in words)]


def assign(hwnd, base_pt, mission, region_pt, only=None, log=print, base=None):
    """Give the base's wings (or those whose names contain one of `only`) a mission over the region at region_pt.
    The base is a screen point (`base_pt`) or a name (`base`, found through the overview)."""
    if mission not in AIR["missions"] or mission == "exercises":
        raise ActionError(f"unknown mission {mission!r}; known: {', '.join(k for k in AIR['missions'])}")
    head = open_target(hwnd, base_pt, base)
    rows = pick(wing_rows(hwnd), only)
    if not rows:
        raise ActionError(f"no wing at {head[0]} matches {only!r}")
    select_wings(hwnd, rows)
    if not mission_armed(hwnd, mission):
        hoi4.click(hwnd, AIR["missions"][mission], AIR["mission_y"])
        time.sleep(0.5)
    if not mission_armed(hwnd, mission):
        raise ActionError(f"the {mission} button did not arm")
    pt = region_point(hwnd, region_pt)
    hoi4.click(hwnd, *pt, button="right")
    time.sleep(1.0)
    want = AIR["mission_names"][mission].lower()
    failed = []
    for r in rows:
        r["order"] = wing_order(hwnd, r["y"])
        # OCR can drop a stray number into the line ("Close Air 72 Support"): compare letters only
        ok = re.sub(r"[^a-z]", "", want) in re.sub(r"[^a-z]", "", r["order"].lower())
        log(f"{head[0]}: {r['name']}: {r['order']}" + ("" if ok else "  <- not given"))
        if not ok:
            failed.append(r["name"])
    if failed:
        raise ActionError(f"{len(failed)} wing(s) did not take {mission}: {failed}. A wing type can only fly its own "
                          "missions (fighters: superiority/interception; bombers: cas/strategic), and the region "
                          "must be in range")
    return rows


def assign_wing(hwnd, wing, mission, region_pt, base=None, region_name=None, log=print):
    """Give one wing a mission, picked by name in the overview (a base panel shows only four rows; clicking a row
    in the overview selects exactly that wing). With several wings of that name, one with no area goes first.
    With region_name, the wing's area is checked afterwards, and points further out are tried until it matches
    (a point near a region border can land in the neighbour: "Eastern Poland" for "Western Poland")."""
    tries = [(0, 0)] + ([(-100, 0), (0, 100), (100, 0), (0, -100), (-180, 60), (180, -60)] if region_name else [])
    last = None
    for dx, dy in tries:
        rows = read_overview(hwnd, keep_open=True)
        hits = [r for r in rows if (A.similar(wing, r["name"]) >= 0.8 or A.norm(wing) in A.norm(r["name"]))
                and (not base or A.similar(base, r["base"]) >= 0.75 or A.norm(base) in A.norm(r["base"]))]
        if not hits:
            A.close_screen(hwnd, "air")
            raise ActionError(f"no wing like {wing!r}" + (f" at {base!r}" if base else "") + " in the overview")
        # prefer a wing not yet in the wanted region (or with no area at all)
        row = sorted(hits, key=lambda r: (bool(region_name) and A.similar(region_name, r["area"]) >= 0.85,
                                          bool(r["area"])))[0]
        hoi4.click(hwnd, AIR["overview_click_x"], row["y"])
        if not A.wait_for(lambda: base_header(hwnd), timeout=2.0):
            raise ActionError(f"clicking {row['name']} in the overview opened no base panel")
        if not mission_armed(hwnd, mission):
            hoi4.click(hwnd, AIR["missions"][mission], AIR["mission_y"])
            time.sleep(0.5)
        if not mission_armed(hwnd, mission):
            raise ActionError(f"the {mission} button did not arm")
        try:
            pt = region_point(hwnd, (region_pt[0] + dx, region_pt[1] + dy))
        except ActionError as e:
            last = str(e)
            close_base(hwnd)
            continue
        hoi4.click(hwnd, *pt, button="right")
        time.sleep(1.0)
        close_base(hwnd)
        after = read_overview(hwnd)
        same = [r for r in after if r["name"] == row["name"] and r["base"] == row["base"]]
        areas = sorted(set(r["area"] or "(none)" for r in same))
        log(f"{row['name']} at {row['base']}: area now {areas}")
        if region_name is None:
            if all(not r["area"] for r in same):
                raise ActionError(f"{row['name']} still has no area after the right-click")
            return
        if any(A.similar(region_name, r["area"]) >= 0.85 for r in same):
            return
        last = f"landed in {areas}, not {region_name!r}"
    raise ActionError(f"{wing}: could not assign over {region_name or region_pt}: {last}")


def region_point(hwnd, pt):
    """A point near pt where a right-click assigns to the region: wing boxes, base icons and battle icons sit on
    the map too, and a right-click on them does something else. The region's own tooltip says "Right-Click to
    assign selected Air Wings to this area"."""
    for dx, dy in ((0, 0), (60, 0), (-60, 0), (0, 60), (0, -60), (90, 70), (-90, -70), (120, 0), (-120, 0)):
        x, y = pt[0] + dx, pt[1] + dy
        tip = " ".join(l.text for l in A.hover_tooltip(hwnd, x, y, x_min=max(0, x - 40))).lower()
        if "assign selected" in tip:
            if "none of the selected" in tip:
                raise ActionError(f"the region at {(x, y)} is out of range for the selected wings")
            return (x, y)
    raise ActionError(f"no point near {pt} shows the region's assign tooltip (wing boxes or icons in the way?)")


def rebase(hwnd, base_pt, to_pt, only=None, log=print, base=None):
    """Move the base's wings (or those matching `only`) to the air base whose icon is at to_pt."""
    head = open_target(hwnd, base_pt, base)
    rows = pick(wing_rows(hwnd), only)
    if not rows:
        raise ActionError(f"no wing at {head[0]} matches {only!r}")
    select_wings(hwnd, rows)
    hoi4.move_mouse(*hoi4.to_screen(hwnd, *to_pt))
    time.sleep(0.6)
    hoi4.click(hwnd, *to_pt, button="right")
    time.sleep(1.0)
    statuses = [l.text for l in A.read_box(hwnd, AIR["panel_box"]) if l.text.lower().startswith("to ")]
    if not statuses:
        raise ActionError(f"no wing shows a 'To ...' move after the right-click at {to_pt}; is it an air base?")
    log(f"{head[0]}: {len(rows)} wing(s) moving: {sorted(set(statuses))}")

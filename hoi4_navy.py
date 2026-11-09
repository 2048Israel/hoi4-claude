"""Navy and dockyards (EX4): task forces from the Navy Overview (p), a task force's mission over a sea region, a
fleet's home base, and the production screen's ship (dockyard) lines.

    hoi4.py read navy [--quick] [--fleet NAME]
    hoi4.py act navy mission --fleet NAME --mission patrol --region X Y [--region-name "Lower Baltic Sea"]
    hoi4.py act navy port --fleet NAME --port Kiel
    hoi4.py read production --dockyards
    hoi4.py act production --dockyards --name "Scharnhorst" --add 2      (or --remove 1)
    hoi4.py act production --dockyards --new "Typ VIIA" [--add 3]

How the game does it (1.19.4 with Jerus's mods, measured live on 1939-11-01 in the Germany campaign):
- `p` opens the Navy Overview: one row per TASK FORCE (the header still says "6 Fleets"), 43.8 px apart from
  y 429, with the columns Name, Area (where it is) and Size. Long names are cut ("North-West Germ...").
- Clicking a row selects that task force. The overview gives way to the fleet panel: the fleet's header on top
  (name, "Active in Regions: N", the home base, Select All), then the task force's card (ship count, name, Back,
  and a status line: "Docked in Weser-Ems", "Holding position in Lower Baltic Sea", "Operating in Lower Baltic
  Sea", "No assigned regions") and its ships, 51 px apart. Back shows every task force of the fleet (cards 154 px
  apart) and selects them all (the mission bar then reads "Missions - All Taskforces"). `p` again reopens the
  overview.
- The mission bar sits at the bottom centre, titled "Missions - <task force>". Each mission button has a small light
  at its top left: grey, or yellow once that mission is set for the selection. A click sets the mission.
- Regions belong to the FLEET ("Active in Regions"). With the mission set, a right-click on a sea region adds it;
  a right-click on a region already added changes nothing. A sea region's tooltip reads "Shallow Sea | This
  seazone requires at least ... Naval Dominance". The map's Find window knows land places only, so a region is a
  screen point at the standard camera (`act camera home`), as for `act air`.
- Hovering a task force's mission icon (the round icon left of its status line) shows the mission and the
  fleet's regions: "Patrol | Active in: | - Lower Baltic Sea", or "Hold ...", "Reserve". That is the read-back.
- Home base: Ctrl+Right-click a naval base on the map moves the fleet there and makes it the home base; the fleet
  header then names it. The base's anchor icon has the tooltip "<state> | Naval base: N". The gear left of the base
  toggles "Automate Home Base Selection" (on for the German fleets: a Baltic patrol moved the base from
  Wilhelmshaven to Kiel by itself).
- The fleet header's X deselects (tooltip "Deselect").
- Production (y): ship lines are mixed with the rest. The first filter row (y 437) is Infantry & Artillery
  Equipment, Armor, Air, Capital Ships, Screen Ships, Other Ships: each shows a yellow check while its lines are
  shown, and a click toggles it. "Dockyards 4/12" (used/total) sits right of "Military Factories".
- A ship line's header reads "N Name | Auto (deploy base) | - dockyards + | delete"; the dockyard count sits where a
  land line's factory count does. Under it: the ship type, the date the next ship is done, and a second +/- at
  x 380 for how many ships to build. Lines are 139 px apart.
- Build Ships (the anchor + button) opens a list of ship designs, 100 px apart ("Convoy", "Scharnhorst Klasse /
  Early Heavy Ship", ..., "Typ VIIA Klasse / Early Submarine"); a click adds a line at the end.
"""
import re
import time
from collections import Counter

import numpy as np

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

NV = A.T["navy"]
DY = A.T["dockyards"]
P = A.P

# OCR reads a cut-off name's "..." as a dash or a long dash
CUT = re.compile(r"\s*[—–\-.…]+$")
# a word of three letters, umlauts included ("Möwe"; A.HAS_WORD needs ASCII letters)
WORD = re.compile(r"[^\W\d_]{3}")
# an icon in front of a line reads as one letter and an apostrophe: "C' Docked in Holstein", "d' Pre-Dreadnought"
ICON = re.compile(r"^\W*[A-Za-z]?['’]\s+")


def clean_name(text):
    return CUT.sub("", ICON.sub("", text.strip())).strip()


def name_score(want, seen):
    """How well a name the agent typed matches one read off the screen (0-1). The screen may cut a name short
    ("North-West Germ...") and OCR may misread letters ("Marineschute Kiet")."""
    seen_c = clean_name(seen)
    w, s = A.norm(want), A.norm(seen_c)
    if not w or not s:
        return 0.0
    if w == s:
        return 1.0
    best = A.similar(w, s)
    if w in s and len(w) >= 4:
        best = max(best, 0.9)
    if len(s) > len(w):  # "Typ VIIA" against "Typ VIIA Klasse": compare the start
        best = max(best, A.similar(w, s[:len(w)]) - 0.05)
    if seen_c != seen.strip() and len(s) >= 5 and len(w) > len(s):  # cut short on screen
        best = max(best, A.similar(w[:len(s)], s))
    return best


def best_match(want, items, key, floor=0.75):
    """The item whose key(item) matches `want` best, or None. Two equally good ones are refused."""
    scored = sorted(((name_score(want, key(it)), i) for i, it in enumerate(items)), reverse=True)
    if not scored or scored[0][0] < floor:
        return None
    if len(scored) > 1 and scored[1][0] >= floor and scored[0][0] - scored[1][0] < 0.03 and scored[0][0] < 1.0:
        raise ActionError(f"{want!r} matches both {key(items[scored[0][1]])!r} and {key(items[scored[1][1]])!r}; "
                          "give more of the name")
    return items[scored[0][1]]


def _cy(l):
    return (l.box[1] + l.box[3]) / 2


def _number(text):
    m = re.search(r"\d+", text.translate(A.DIGIT_FIX).replace(" ", ""))
    return int(m.group()) if m else None


# --------------------------------------------------------------------------
# readers of OCR lines (pure: tested offline in tests/test_EX4.py)
# --------------------------------------------------------------------------
def overview_rows(lines):
    """Navy Overview OCR -> [{'name', 'area', 'size', 'y'}], one per task force, by the row grid."""
    first, step = NV["overview_first_y"], NV["overview_step"]
    x_area, x_size = NV["overview_cols"]
    rows = {}
    for l in lines:
        if "strategic area" in l.text.lower():
            continue
        k = round((_cy(l) - first) / step)
        if k < 0 or abs(_cy(l) - (first + k * step)) > 12:
            continue
        row = rows.setdefault(k, {"name": "", "area": "", "size": None, "y": round(first + k * step)})
        if l.box[0] >= x_size:
            if row["size"] is None:
                row["size"] = _number(l.text)
        elif not WORD.search(l.text):
            continue
        elif l.box[0] >= x_area:
            row["area"] = (row["area"] + " " + l.text).strip()
        else:
            row["name"] = (row["name"] + " " + l.text).strip()
    return [rows[k] for k in sorted(rows) if rows[k]["name"]]


def parse_fleet_header(lines):
    """The fleet panel's header -> {'fleet', 'home', 'regions'}; None when no fleet panel is open."""
    regions = None
    for l in lines:
        m = re.search(r"Active in Regions\W*(\w+)", l.text)
        if m:
            regions = _number(m.group(1))
    if regions is None:
        return None
    y0, y1 = NV["fleet_name_band"]
    hx0, hx1 = NV["home_base_x"]
    hy0, hy1 = NV["home_base_band"]
    fleet = " ".join(l.text for l in lines if y0 <= _cy(l) <= y1 and 60 <= l.box[0] < 320 and WORD.search(l.text))
    home = " ".join(l.text for l in lines if hy0 <= _cy(l) <= hy1 and hx0 <= l.box[0] < hx1
                    and WORD.search(l.text) and "select" not in l.text.lower())
    return {"fleet": fleet.strip(), "home": home.strip(), "regions": regions}


def parse_task_force(lines):
    """The selected task force's card -> {'name', 'ships', 'status'}; None when no card is open.
    OCR may glue the ship count to the name ("A12 Hochseeflotte"; the "A" is the rank chevron)."""
    y0, y1 = NV["tf_band"]
    nx0, nx1 = NV["tf_name_x"]
    sy0, sy1 = NV["tf_status_band"]
    band = [l for l in lines if y0 <= _cy(l) <= y1]
    name, ships = "", None
    for l in band:
        text = l.text.strip()
        if l.box[0] < NV["tf_count_x_max"]:
            m = re.match(r"^\W*[A-Za-z]?(\d+)\s+(\S.*)$", text)
            if m and WORD.search(m.group(2)):  # count and name read as one line
                ships, name = int(m.group(1)), m.group(2)
            elif re.fullmatch(r"\W*[A-Za-z]?\d+", text):
                ships = _number(text)
        elif nx0 <= l.box[0] < nx1 and WORD.search(text) and text.lower() not in ("back", "select"):
            name = (name + " " + text).strip()
    if not name:
        return None
    status = " ".join(ICON.sub("", l.text.strip()) for l in lines
                      if sy0 <= _cy(l) <= sy1 and WORD.search(l.text))
    return {"name": name, "ships": ships, "status": status.strip()}


MISSION_WORDS = ["Patrol", "Strike Force", "Convoy Raiding", "Convoy Escort", "Minelaying", "Minesweeping",
                 "Naval Invasion Support", "Naval Exercises", "Hold", "Reserve", "Awaiting Orders",
                 "Search and Destroy", "Transport/Invasion"]


def parse_mission_tip(lines):
    """The mission icon's tooltip -> (mission, [regions]): 'Patrol | Active in: | - Lower Baltic Sea'."""
    mission, regions, in_regions = None, [], False
    for l in lines:
        t = l.text.strip()
        if re.match(r"active in", t, re.I):
            in_regions = True
            continue
        if in_regions and re.match(r"^[-–—~]\s*\w", t):
            regions.append(re.sub(r"^[-–—~]\s*", "", t))
            continue
        if mission is None and not in_regions and WORD.search(t):
            known = max(MISSION_WORDS, key=lambda w: A.similar(w, t))
            mission = known if A.similar(known, t) >= 0.75 else t
    return mission, regions


def parse_ships(lines):
    """A task force's ship list -> [{'name', 'class'}]: a class line ("Pre-Dreadnought (Deutschland Klasse)") with
    the ship's name about 13 px above it, further right. OCR sometimes misses a name: it is then '?'."""
    x0 = NV["ship_name_x0"]
    names = [l for l in lines if l.box[0] >= x0 and WORD.search(l.text)]
    out = []
    for c in lines:
        if c.box[0] >= x0 or not WORD.search(c.text):
            continue
        above = [n for n in names if 5 <= _cy(c) - _cy(n) <= 22]
        out.append({"name": above[0].text.strip() if above else "?", "class": clean_name(c.text)})
    return out


def ship_summary(ships):
    """'2 Pre-Dreadnought, 8 Inter War Destroyer I' from the class lines (the design in brackets left out)."""
    kinds = Counter(re.split(r"\s*\(", s["class"])[0].strip() for s in ships)
    return ", ".join(f"{n} {k}" for k, n in kinds.most_common())


def parse_ship_lines(lines):
    """Production list OCR (ship lines only) -> [{'number', 'name', 'type', 'date', 'y'}], one per line header
    ("6 Scharnhorst"); its type and date sit about 34 px below."""
    out = []
    for h in lines:
        m = re.match(r"\s*(\d+)\s+(\S.*)", h.text)
        if h.box[0] >= 60 or not m or not WORD.search(m.group(2)):
            continue
        y = _cy(h)
        below = [l for l in lines if 22 <= _cy(l) - y <= 46]
        kind = " ".join(l.text for l in below if l.box[0] < 200 and WORD.search(l.text))
        when = " ".join(l.text for l in below if 200 <= l.box[0] < 420)
        d = re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+[^\s+]+", when)
        out.append({"number": int(m.group(1)), "name": m.group(2).strip(), "type": kind.strip(),
                    "date": d.group() if d else "", "y": round(y)})
    return out


def parse_dockyards(lines):
    """'Dockyards 4/12' -> (4, 12), or None."""
    for l in lines:
        m = re.search(r"(\d+)\s*/\s*(\d+)", l.text.translate(A.DIGIT_FIX).replace(" ", ""))
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def parse_designs(lines):
    """Build Ships list OCR -> [{'name', 'type', 'y'}]. A design is a name line with its type line about 17 px
    below; costs are numbers only and left out."""
    words = sorted((l for l in lines if l.box[0] < DY["picker_name_x_max"] and WORD.search(l.text)), key=_cy)
    out, last_y = [], -999
    for l in words:
        if _cy(l) - last_y > 40:
            out.append({"name": l.text.strip(), "type": "", "y": round(_cy(l))})
        elif out and not out[-1]["type"]:
            out[-1]["type"] = l.text.strip()
        last_y = _cy(l)
    return out


def light_on(img, x, y, r=4):
    """A mission button's light at (x, y) is yellow (set) rather than grey. img: an RGB array of the window."""
    c = img[y - r:y + r + 1, x - r:x + r + 1].astype(int)
    yellow = (c[..., 0] > 120) & (c[..., 1] > 100) & (c[..., 0] > c[..., 2] + 50)
    return int(yellow.sum()) >= 15  # the lit light filled about 35 of a 7x7 box; a grey one has none


FILTERS = ("equipment", "armor", "air", "capital", "screen", "other")
SHIPS = {"equipment": False, "armor": False, "air": False, "capital": True, "screen": True, "other": True}


def filter_state_from(img):
    """{category: shown} from the yellow checks of the production screen's first filter row."""
    y0, y1 = DY["filter_check_band"]
    out = {}
    for name in FILTERS:
        right = DY["filter_check_right"][name]
        c = img[y0:y1, right - 24:right + 4].astype(int)
        check = (c[..., 0] > 170) & (c[..., 1] > 130) & (c[..., 2] < 110) & (c[..., 0] > c[..., 2] + 80)
        out[name] = int(check.sum()) >= 6
    return out


# --------------------------------------------------------------------------
# the fleet panel
# --------------------------------------------------------------------------
def panel(hwnd):
    """(fleet header, task force card) of the open fleet panel; either is None when not shown."""
    lines = A.read_box(hwnd, NV["panel_box"])
    return parse_fleet_header(lines), parse_task_force(lines)


def fleet_open(hwnd):
    return panel(hwnd)[0] is not None


def deselect(hwnd):
    """Close the fleet panel by its X. The X is clicked only once the header is read: the same spot in the Navy
    Overview is one of its buttons."""
    for _ in range(2):
        if not fleet_open(hwnd):
            return
        hoi4.click(hwnd, *NV["deselect"])
        time.sleep(0.6)
    if fleet_open(hwnd):
        raise ActionError("the fleet panel did not close")


def read_overview(hwnd, keep_open=False):
    """Every task force in the Navy Overview: [{'name', 'area', 'size', 'y'}]. Lone digits (sizes) need a
    larger upscale, so that column is read twice."""
    if fleet_open(hwnd):
        deselect(hwnd)
    A.open_screen(hwnd, "navy")
    lines = A.read_box(hwnd, NV["overview_box"])
    lines += A.read_box(hwnd, NV["overview_size_box"], upscale=3, park=False)
    if not keep_open:
        A.close_screen(hwnd, "navy")
    return overview_rows(lines)


def mission_bar(hwnd):
    return " ".join(l.text for l in A.read_box(hwnd, NV["mission_bar_title_box"]))


def read_mission(hwnd):
    """(mission, [regions]) from the selected task force's mission icon tooltip."""
    x, y = NV["mission_icon"]
    for _ in range(2):  # the tooltip finder sometimes catches the map instead
        got = parse_mission_tip(A.hover_tooltip(hwnd, x, y, x_min=0))
        if got[0]:
            return got
    return None, []


def select_task_force(hwnd, name):
    """Select a task force by name through the overview. Returns (row, fleet header, card)."""
    rows = read_overview(hwnd, keep_open=True)
    row = best_match(name, rows, key=lambda r: r["name"])
    if not row:
        A.close_screen(hwnd, "navy")
        raise ActionError(f"no task force like {name!r}; the overview has: {[r['name'] for r in rows]}")
    hoi4.click(hwnd, NV["overview_click_x"], row["y"])
    got = A.wait_for(lambda: (lambda p: p if p[1] else None)(panel(hwnd)), timeout=2.5)
    if not got:
        raise ActionError(f"clicking {row['name']!r} in the overview opened no task force card")
    head, card = got
    if max(name_score(name, card["name"]), name_score(row["name"], card["name"])) < 0.7:
        deselect(hwnd)
        raise ActionError(f"meant to select {name!r}; the card shows {card['name']!r}")
    return row, head, card


def read_navy(hwnd, quick=False, log=print):
    """Every task force: name, fleet, ships, mission, status, area and the fleet's home base."""
    rows = read_overview(hwnd, keep_open=quick is False)
    if quick:
        log(f"{len(rows)} task force(s)")
        for r in rows:
            log(f"  {clean_name(r['name']):<32} {str(r['size'] or '?'):>3} ships  area {r['area'] or '?'}")
        return rows
    out = []
    try:
        for r in rows:
            A.open_screen(hwnd, "navy")
            hoi4.click(hwnd, NV["overview_click_x"], r["y"])
            got = A.wait_for(lambda: (lambda p: p if p[1] else None)(panel(hwnd)), timeout=2.5)
            if not got:
                log(f"  {r['name']}: no card opened")
                continue
            head, card = got
            mission, regions = read_mission(hwnd)
            item = {**r, **card, "fleet": head["fleet"], "home": head["home"], "mission": mission or "?",
                    "regions": regions, "ships": card["ships"] or r["size"]}
            out.append(item)
    finally:
        if fleet_open(hwnd):
            deselect(hwnd)
        A.close_screen(hwnd, "navy")
    log(f"{len(out)} task force(s)")
    for t in out:
        where = f"regions {', '.join(t['regions'])}" if t["regions"] else "no regions"
        log(f"  {t['name']:<30} fleet {t['fleet'] or '?':<22} {str(t['ships'] or '?'):>3} ships  "
            f"{t['mission']:<14} {t['status']:<38} home {t['home'] or '?'} | {where}")
    return out


def read_task_force(hwnd, name, log=print):
    """One task force's card and the ships the list shows."""
    row, head, card = select_task_force(hwnd, name)
    try:
        mission, regions = read_mission(hwnd)
        ships = parse_ships(A.read_box(hwnd, NV["ships_box"]))
    finally:
        deselect(hwnd)
    log(f"{card['name']} (fleet {head['fleet']}, home {head['home']}): {card['ships'] or '?'} ships, "
        f"{mission or '?'}, {card['status']}; regions: {', '.join(regions) or 'none'}")
    log(f"  ships shown: {ship_summary(ships)}" + (" (the list shows 10 at a time)" if len(ships) >= 10 else ""))
    for s in ships:
        log(f"    {s['name']:<22} {s['class']}")
    return card, ships


# --------------------------------------------------------------------------
# missions and home base
# --------------------------------------------------------------------------
def mission_set(hwnd, mission):
    x = NV["missions"][mission] + NV["light_dx"]
    A.park_mouse(hwnd)
    return light_on(np.asarray(hoi4.grab(hwnd).convert("RGB")), x, NV["light_y"])


def sea_point(hwnd, pt):
    """A point near pt whose tooltip is a sea zone's ("This seazone requires ... Naval Dominance"): a right-click
    there adds the region. Ship counters and ports sit on the sea too and show other tooltips."""
    for dx, dy in ((0, 0), (60, 0), (-60, 0), (0, 60), (0, -60), (90, 70), (-90, -70)):
        x, y = pt[0] + dx, pt[1] + dy
        tip = " ".join(l.text for l in A.hover_tooltip(hwnd, x, y, x_min=max(0, x - 40))).lower()
        if "seazone" in tip or ("sea" in tip and "dominance" in tip):
            return (x, y)
    raise ActionError(f"no sea zone tooltip at or near {pt}: give a point on open sea (standard camera)")


def letters(text):
    return re.sub(r"[^a-z]", "", (text or "").lower())


def set_mission(hwnd, task_force, mission, region_pt=None, region_name=None, log=print):
    """Give a task force a mission; with region_pt, also add the sea region there to its fleet's regions.
    Confirmed by the mission icon's tooltip (mission name and regions)."""
    if mission not in NV["missions"]:
        raise ActionError(f"unknown mission {mission!r}; known: {', '.join(NV['missions'])}")
    _, head, card = select_task_force(hwnd, task_force)
    try:
        bar = mission_bar(hwnd)
        if "mission" not in bar.lower():
            raise ActionError(f"no mission bar under the map (read {bar!r}); nothing clicked")
        before, _ = read_mission(hwnd)
        needs_region = mission not in NV["no_region"]
        if not (needs_region and mission_set(hwnd, mission)):
            hoi4.click(hwnd, NV["missions"][mission], NV["mission_y"])
            time.sleep(0.6)
        if needs_region and not mission_set(hwnd, mission):
            raise ActionError(f"the {mission} button did not light up for {card['name']} (not possible for these "
                              "ships, or not at war?)")
        if region_pt and needs_region:
            pt = sea_point(hwnd, region_pt)
            hoi4.click(hwnd, *pt, button="right")
            time.sleep(1.0)
        got, regions = read_mission(hwnd)
        status = (panel(hwnd)[1] or {}).get("status", "?")
        log(f"{card['name']} (fleet {head['fleet']}): {before or '?'} -> {got or '?'}; "
            f"regions {', '.join(regions) or '(none)'}; {status}")
        if letters(NV["mission_names"][mission]) not in letters(got):
            raise ActionError(f"{card['name']} shows {got!r}, not {NV['mission_names'][mission]!r}")
        if needs_region and not regions:
            raise ActionError(f"{card['name']} has the mission but its fleet has no region: add --region X Y "
                              "(a point on open sea at the standard camera)")
        if region_name and needs_region and not any(name_score(region_name, r) >= 0.8 for r in regions):
            raise ActionError(f"{region_name!r} is not among the fleet's regions {regions}")
    finally:
        deselect(hwnd)
    return got, regions


def anchor_candidates(img, pt, reach=320):
    """Screen points of teal anchor icons (naval bases) near pt, nearest first. img: RGB array of the window."""
    x0, y0 = max(0, pt[0] - reach), max(60, pt[1] - reach)
    c = img[y0:pt[1] + reach, x0:pt[0] + reach].astype(int)
    teal = (c[..., 2] > 140) & (c[..., 1] > 130) & (c[..., 0] < 100) & (c[..., 2] > c[..., 0] + 70)
    ys, xs = np.nonzero(teal)
    cells = {k: n for k, n in Counter(zip((ys // 16).tolist(), (xs // 16).tolist())).items() if n >= 8}
    pts, done = [], set()
    for start in cells:  # touching cells are one icon: its centre is their count-weighted middle
        if start in done:
            continue
        blob, todo = [], [start]
        done.add(start)
        while todo:
            cy, cx = todo.pop()
            blob.append((cy, cx))
            for nb in ((cy + a, cx + b) for a in (-1, 0, 1) for b in (-1, 0, 1)):
                if nb in cells and nb not in done:
                    done.add(nb)
                    todo.append(nb)
        if len(blob) > 12:  # far bigger than an icon: teal water or a panel
            continue
        w = sum(cells[c] for c in blob)
        pts.append((round(x0 + sum((c[1] * 16 + 8) * cells[c] for c in blob) / w),
                    round(y0 + sum((c[0] * 16 + 8) * cells[c] for c in blob) / w)))
    return sorted(pts, key=lambda p: abs(p[0] - pt[0]) + abs(p[1] - pt[1]))


def naval_base_near(hwnd, pt, tries=10):
    """The naval base icon near a city label: teal anchor icons first, then a ring of points around the label;
    each is hovered until its tooltip says 'Naval base'."""
    A.park_mouse(hwnd)
    img = np.asarray(hoi4.grab(hwnd).convert("RGB"))
    ring = [(pt[0] + dx, pt[1] + dy) for dx, dy in ((0, -60), (-60, -60), (60, -60), (-60, 0), (60, 0), (0, 0))]
    seen = 0
    for x, y in anchor_candidates(img, pt)[:tries] + ring:
        tip = " ".join(l.text for l in A.hover_tooltip(hwnd, x, y, x_min=max(0, x - 40)))
        seen += 1
        if re.search(r"naval base", tip, re.I):
            return (x, y), tip
    raise ActionError(f"no naval base icon found near {pt} ({seen} points hovered); is the city a port?")


def set_home_base(hwnd, task_force, port, log=print):
    """Make `port` the home base of the fleet that holds `task_force`: Back (the whole fleet), centre the map on
    the port with Find, Ctrl+Right-click its naval base icon; confirmed by the fleet header."""
    _, head, card = select_task_force(hwnd, task_force)
    try:
        hoi4.click(hwnd, *NV["tf_back"])
        time.sleep(0.8)
        if "all" not in mission_bar(hwnd).lower():
            raise ActionError("Back did not select the whole fleet (the mission bar does not say All Taskforces)")
        city = A.find_city(hwnd, port)
        base, tip = naval_base_near(hwnd, city)
        if not fleet_open(hwnd):
            raise ActionError("the fleet was deselected while searching; nothing ordered")
        hoi4.click(hwnd, *base, button="right", mods=("ctrl",))
        time.sleep(1.0)
        after = panel(hwnd)[0] or {}
        automate = " ".join(l.text for l in A.hover_tooltip(hwnd, *NV["automate_home_base"], x_min=0))
        log(f"fleet {head['fleet']}: home base {head['home'] or '?'} -> {after.get('home') or '?'} "
            f"(clicked {base}: {tip}) | {automate or 'automation state not read'}")
        if name_score(port, after.get("home", "")) < 0.75:
            raise ActionError(f"the fleet header shows {after.get('home')!r} as home base, not {port!r}")
        if "enabled" in automate.lower():
            log("note: Automate Home Base Selection is on, so the game may pick another base later")
    finally:
        deselect(hwnd)
        A.camera_home(hwnd, log=lambda m: None)
    return after.get("home")


# --------------------------------------------------------------------------
# dockyards: the production screen's ship lines
# --------------------------------------------------------------------------
def filter_state(hwnd):
    A.park_mouse(hwnd)
    return filter_state_from(np.asarray(hoi4.grab(hwnd).convert("RGB")))


def set_filters(hwnd, want):
    for _ in range(2):
        state = filter_state(hwnd)
        todo = [n for n in FILTERS if state[n] != want[n]]
        if not todo:
            return
        for n in todo:
            hoi4.click(hwnd, DY["filter_click_x"][n], DY["filter_y"])
            time.sleep(0.4)
    raise ActionError(f"the production filters did not switch: shown {filter_state(hwnd)}, wanted {want}")


class ShipsOnly:
    """Open production with only the ship categories shown; put the filters back as they were afterwards."""

    def __init__(self, hwnd, keep_open=False):
        self.hwnd, self.keep_open, self.prev = hwnd, keep_open, None

    def __enter__(self):
        A.open_screen(self.hwnd, "production")
        self.prev = filter_state(self.hwnd)
        set_filters(self.hwnd, SHIPS)
        return self

    def __exit__(self, *exc):
        A.open_screen(self.hwnd, "production")
        set_filters(self.hwnd, self.prev)
        if not self.keep_open:
            A.close_screen(self.hwnd, "production")
        return False


def read_small_number(img, box):
    """A lone digit or two (OCR often misses those): try a few upscales."""
    x0, y0, x1, y1 = box
    for up in (3, 4, 2):
        for l in A.ocr_image(img.crop((x0, y0, x1, y1)), origin=(x0, y0), upscale=up):
            n = _number(l.text)
            if n is not None:
                return n
    return None


def dockyards_used(hwnd):
    return parse_dockyards(A.read_box(hwnd, DY["dockyards_box"], upscale=3))


def ship_lines_page(hwnd):
    lines = A.read_box(hwnd, P["list_box"])
    img = hoi4.grab(hwnd)
    out = parse_ship_lines(lines)
    for s in out:
        s["dockyards"] = A.read_count(img, s["y"])
        cy = s["y"] + DY["ships_count_dy"]
        s["ships"] = read_small_number(img, (DY["ships_x"] - 20, cy - 13, DY["ships_x"] + 20, cy + 13))
    return out


def scan_ship_lines(hwnd, max_pages=8):
    """Every ship line (ships-only filter on), from the top of the list."""
    hoi4.scroll(hwnd, *P["scroll_point"], 40)
    time.sleep(0.4)
    seen, last = {}, None
    for _ in range(max_pages):
        page = ship_lines_page(hwnd)
        for s in page:
            seen.setdefault(s["number"], s)
        sig = [s["number"] for s in page]
        if sig == last:
            break
        last = sig
        hoi4.scroll(hwnd, *P["scroll_point"], -5)
        time.sleep(0.45)
    return [seen[k] for k in sorted(seen)]


def read_dockyard_lines(hwnd, log=print):
    with ShipsOnly(hwnd):
        used = dockyards_used(hwnd)
        rows = scan_ship_lines(hwnd)
    log(f"dockyards in use: {used[0]}/{used[1]}" if used else "dockyards in use: (not read)")
    for s in rows:
        log(f"  line {s['number']}: {s['name']} | {s['type']} | dockyards {s['dockyards']} | "
            f"ships to build {s['ships']} | next {s['date'] or '?'}")
    if not rows:
        log("  (no ship lines)")
    return used, rows


def line_wanted(name, line):
    """'Zerstörer 1934A' matches any such line; '8 Zerstörer 1934A' or '#8' only line 8."""
    m = re.fullmatch(r"\s*#(\d+)\s*(.*)", name) or re.fullmatch(r"\s*(\d+)\s+(\D.*)", name)
    if m:
        if int(m.group(1)) != line["number"]:
            return False
        name = m.group(2)
    return not name.strip() or name_score(name, line["name"]) >= 0.8


def find_ship_line(hwnd, name):
    """Scroll the ships-only list until a line matches; returns the line as on screen now (its y is current)."""
    hoi4.scroll(hwnd, *P["scroll_point"], 40)
    time.sleep(0.4)
    seen, last = [], None
    for _ in range(8):
        page = ship_lines_page(hwnd)
        hits = [s for s in page if line_wanted(name, s) and 500 <= s["y"] <= 1150]
        if hits:
            return hits[0]
        seen += [f"{s['number']} {s['name']}" for s in page]
        sig = [s["number"] for s in page]
        if sig == last:
            break
        last = sig
        hoi4.scroll(hwnd, *P["scroll_point"], -5)
        time.sleep(0.45)
    raise ActionError(f"no ship line like {name!r}; lines seen: {', '.join(dict.fromkeys(seen)) or 'none'}")


def change_dockyards(hwnd, name, add=0, remove=0, log=print):
    """Add or remove dockyards on a ship line, confirmed by the line's count and the Dockyards used/total."""
    with ShipsOnly(hwnd):
        used0 = dockyards_used(hwnd)
        line = find_ship_line(hwnd, name)
        y, before = line["y"], line["dockyards"]
        for _ in range(add):
            hoi4.click(hwnd, P["plus_x"], y)
            time.sleep(0.25)
        for _ in range(remove):
            hoi4.click(hwnd, P["minus_x"], y)
            time.sleep(0.25)
        time.sleep(0.3)
        A.park_mouse(hwnd)
        after = A.read_count(hoi4.grab(hwnd), y)
        used1 = dockyards_used(hwnd)
    log(f"line {line['number']} {line['name']}: dockyards {before} -> {after} | dockyards in use "
        f"{'/'.join(map(str, used0)) if used0 else '?'} -> {'/'.join(map(str, used1)) if used1 else '?'}")
    if before is not None and after is not None and after != max(0, before + add - remove):
        raise ActionError(f"expected {max(0, before + add - remove)} dockyards on line {line['number']}, "
                          f"the line shows {after} (a line has a maximum)")
    if after is None:
        raise ActionError(f"could not read line {line['number']}'s dockyard count after the clicks; check it with "
                          "read production --dockyards")
    return after


def picker_open(hwnd):
    return any("outdated" in l.text.lower() for l in A.read_box(hwnd, DY["picker_title_box"]))


def close_picker(hwnd):
    if picker_open(hwnd):
        hoi4.click(hwnd, *DY["picker_close"])
        time.sleep(0.5)


def new_ship_line(hwnd, ship, dockyards=0, log=print):
    """Add a production line for a ship design (Build Ships, then the design by name); then give it `dockyards`
    dockyards in all. Confirmed by a new line number whose header matches the design."""
    with ShipsOnly(hwnd):
        before = scan_ship_lines(hwnd)
        hoi4.click(hwnd, *DY["build_ships"])
        if not A.wait_for(lambda: picker_open(hwnd), timeout=2.0):
            raise ActionError("Build Ships opened no design list")
        pick, seen = None, []
        try:
            hoi4.scroll(hwnd, *DY["picker_scroll_point"], 20)
            time.sleep(0.4)
            for _ in range(6):
                designs = parse_designs(A.read_box(hwnd, DY["picker_box"]))
                seen += [d["name"] for d in designs]
                pick = best_match(ship, designs, key=lambda d: d["name"]) or \
                    best_match(ship, designs, key=lambda d: d["type"], floor=0.9)
                if pick:
                    break
                hoi4.scroll(hwnd, *DY["picker_scroll_point"], -5)
                time.sleep(0.45)
            if not pick:
                raise ActionError(f"no ship design like {ship!r}; designs seen: {', '.join(dict.fromkeys(seen))}")
            hoi4.click(hwnd, DY["picker_click_x"], pick["y"] + 15)
            time.sleep(1.0)
        finally:
            close_picker(hwnd)
        after = scan_ship_lines(hwnd)
        old = {s["number"] for s in before}
        new = [s for s in after if s["number"] not in old]  # a line added at the end takes the next number
        if not new:
            raise ActionError(f"no new ship line after picking {pick['name']!r} ({len(before)} lines before, "
                              f"{len(after)} after)")
        line = max(new, key=lambda s: s["number"])
        log(f"new line {line['number']}: {line['name']} | {line['type']} (picked {pick['name']} / {pick['type']}) "
            f"| dockyards {line['dockyards']}")
        if name_score(line["name"], pick["name"]) < 0.6:
            log(f"warning: the new line's header {line['name']!r} does not look like {pick['name']!r}")
    if dockyards and (line["dockyards"] or 0) < dockyards:
        change_dockyards(hwnd, f"#{line['number']}", add=dockyards - (line["dockyards"] or 0), log=log)
    return line

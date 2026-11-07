"""hoi4_actions.py: game actions and readers that need no screenshots (EX1).

Each action uses fixed positions from ui_targets.json, checks with OCR that each step worked, and stops with a
clear message if not. Readers return text read off the screen.

    hoi4.py act research --slot 5 --tech "Inter-War Artillery" [--mio first|none|NAME]
    hoi4.py act production --line 3 --add 2          (or --remove 1)
    hoi4.py act open production / hoi4.py act close production
    hoi4.py act calibrate-research [--tabs industry,artillery]
    hoi4.py read research | production | date | techs [--tab industry] [--grep TEXT]

The tech map from calibrate-research lives in state/tech_map.json: positions in tree space, so they hold for any
scroll position, at 1920x1200 with this mod setup.
"""
import argparse
import difflib
import json
import re
import time
from collections import deque
from pathlib import Path

import hoi4
from hoi4_ocr import ocr_image

ROOT = Path(__file__).resolve().parent
T = json.loads((ROOT / "ui_targets.json").read_text(encoding="utf-8"))
TECH_MAP = hoi4.STATE_DIR / "tech_map.json"
R = T["research"]


class ActionError(hoi4.BridgeError):
    pass


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def similar(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def park_mouse(hwnd):
    hoi4.move_mouse(*hoi4.to_screen(hwnd, *T["safe_mouse"]))
    time.sleep(0.2)


def read_box(hwnd, box, upscale=2, park=True):
    if park:
        park_mouse(hwnd)
    img = hoi4.grab(hwnd)
    return ocr_image(img.crop(tuple(box)), origin=tuple(box[:2]), upscale=upscale)


def wait_for(fn, timeout=2.0, step=0.15):
    deadline = time.time() + timeout
    while True:
        value = fn()
        if value or time.time() >= deadline:
            return value
        time.sleep(step)


# --------------------------------------------------------------------------
# screens
# --------------------------------------------------------------------------
def screen_title(hwnd):
    return " ".join(l.text for l in read_box(hwnd, T["screens"]["_title_box"]))


def is_open(hwnd, name):
    want = norm(T["screens"][name]["title"])
    return want in norm(screen_title(hwnd))


def open_screen(hwnd, name):
    if name not in T["screens"] or name.startswith("_"):
        raise ActionError(f"unknown screen {name!r}; known: {', '.join(k for k in T['screens'] if not k.startswith('_'))}")
    if is_open(hwnd, name):
        return
    for _ in range(2):
        hoi4.press_combo(T["screens"][name]["key"])
        if wait_for(lambda: is_open(hwnd, name), timeout=1.5):
            return
    raise ActionError(f"the {name} screen did not open (title reads {screen_title(hwnd)!r})")


def close_screen(hwnd, name):
    if not is_open(hwnd, name):
        return
    hoi4.press_combo(T["screens"][name]["key"])
    if not wait_for(lambda: not is_open(hwnd, name), timeout=1.5):
        raise ActionError(f"the {name} screen did not close")


# --------------------------------------------------------------------------
# research
# --------------------------------------------------------------------------
def parse_slots(lines):
    """Research slot list OCR -> [{slot, tech, days}] (tech None for an empty slot)."""
    slots = []
    for i, y in enumerate(R["slot_click_y"]):
        band = [l for l in lines if y - 45 <= l.center[1] <= y + 15]
        text = " ".join(l.text for l in band if l.box[0] < 480)
        days = next((int(m.group(1)) for l in band for m in [re.search(r"(\d+)\s*day", l.text)] if m), None)
        empty = "select" in text.lower() and "technology" in text.lower()
        tech = None if empty or not text else re.sub(r"\s+\d{4}$", "", text).strip()
        slots.append({"slot": i + 1, "tech": tech, "days": days})
    return slots


def read_research(hwnd, keep_open=False):
    open_screen(hwnd, "research")
    slots = parse_slots(read_box(hwnd, R["slots_box"]))
    if not keep_open:
        close_screen(hwnd, "research")
    return slots


def tree_open(hwnd):
    """The tech tree's frame right of the tabs is a flat dark band: mean ~36, spread ~5 in every tab. The slot
    list, the map and other screens read 140+ there. Measured at 1920x1200, UI scale 1.0."""
    from PIL import ImageStat
    s = ImageStat.Stat(hoi4.grab(hwnd).convert("L").crop(tuple(R["tree_band_box"])))
    return s.mean[0] < 60 and s.stddev[0] < 12


def detail_open(hwnd):
    """A tech's detail window shows its research time and a Research button."""
    lines = read_box(hwnd, [820, 195, 1260, 235], park=False)
    return any("day" in l.text.lower() or "research" in l.text.lower() for l in lines)


# Scrolling.
# - Down: the wheel moves a tree exactly 50 px a notch until the bottom. Each tab's v_max is measured once by
#   matching pictures; a view is then reached by counting notches.
# - Sideways: the bottom bar has a small round knob (the brightest pixel along the bar). Dragging the knob moves the
#   tree. The background picture does not move sideways, so sideways shifts are measured from text that moves with
#   the tree (section and year labels), in small knob steps from the left end to the right end. Each tab keeps a list
#   of (knob x, offset) views that together cover its width.
# - A tab opens wherever it was last left, so home is always: wheel fully up, knob fully left.
NOTCH = R["scroll_px_per_notch"]
KNOB_BOX = R["hbar_knob_box"]


def tree_pixels(hwnd, park=True):
    import numpy as np
    if park:
        park_mouse(hwnd)
    x0, y0, x1, y1 = R["tree_box"]
    return np.asarray(hoi4.grab(hwnd).convert("L").crop((x0, y0 + 10, x1, y1 - 10))).astype(np.int16)


def best_shift(a, b, axis, candidates):
    """The shift s (in candidates) for which b equals a moved back by s along axis (0 = down, 1 = right)."""
    import numpy as np
    best, best_err = 0, float("inf")
    n = a.shape[axis]
    for s in candidates:
        if s >= n - 40:
            continue
        if axis == 0:
            err = float(np.abs(a[s:, :] - b[:n - s, :]).mean())
        else:
            err = float(np.abs(a[:, s:] - b[:, :n - s]).mean())
        if err < best_err:
            best, best_err = s, err
    return best


def knob_x(hwnd):
    """x of the sideways scroll knob, or None when the tree is not wider than the screen."""
    import numpy as np
    park_mouse(hwnd)
    x0, y0, x1, y1 = KNOB_BOX
    col = np.asarray(hoi4.grab(hwnd).convert("L").crop((x0, y0, x1, y1))).astype(int).max(axis=0)
    return int(np.argmax(col)) + x0 if col.max() >= 150 else None


def set_knob(hwnd, x):
    """Drag the knob to x; returns where it ended up (None if there is no knob)."""
    k = knob_x(hwnd)
    if k is None:
        return None
    y = R["hbar_y"]
    hoi4.drag(hwnd, k, y, x, y)
    time.sleep(0.35)
    return knob_x(hwnd)


def scroll_home(hwnd):
    hoi4.scroll(hwnd, *R["scroll_point"], 40)
    time.sleep(0.2)
    set_knob(hwnd, KNOB_BOX[0])


def to_view(hwnd, knob, v_off, v_max=None):
    """Show the tree with the knob at `knob` (None, or its left end, means no sideways scroll) and scrolled down
    by v_off: a multiple of 50, or v_max itself (reached by scrolling past the bottom)."""
    scroll_home(hwnd)
    if knob is not None and knob > KNOB_BOX[0] + 15:
        set_knob(hwnd, knob)
    if v_off:
        notches = 40 if v_max is not None and v_off >= v_max else v_off // NOTCH
        hoi4.scroll(hwnd, *R["scroll_point"], -notches)
    time.sleep(0.35)


def label_xs(hwnd):
    return {l.text: l.center[0] for l in read_box(hwnd, R["tree_box"]) if len(l.text) >= 4}


def measure_h_views(hwnd, steps=12, span=1600):
    """[[knob_x, offset], ...] covering the tree from its left end to its right end."""
    scroll_home(hwnd)
    left = knob_x(hwnd)
    if left is None:
        return [[None, 0]]
    right_end = KNOB_BOX[2] - 8
    views, total, prev = [[left, 0]], 0, label_xs(hwnd)
    for i in range(1, steps + 1):
        actual = set_knob(hwnd, round(left + (right_end - left) * i / steps))
        cur = label_xs(hwnd)
        shifts = sorted(prev[t] - cur[t] for t in prev if t in cur)
        if not shifts:
            raise ActionError("a sideways step left no label in common; use more steps")
        total += shifts[len(shifts) // 2]
        views.append([actual, total])
        prev = cur
    # keep only the views needed: each kept view at most `span` px right of the one before, plus the last
    kept, candidate = [views[0]], None
    for v in views[1:]:
        if v[1] - kept[-1][1] <= span:
            candidate = v
        else:
            kept.append(candidate)
            candidate = v
    if kept[-1][1] < views[-1][1] - 20:
        kept.append(views[-1])
    return kept


def measure_geometry(hwnd):
    """(sideways views, v_max) for the open tab."""
    px, py = R["scroll_point"]
    scroll_home(hwnd)
    v_max, prev = 0, tree_pixels(hwnd)
    step = 10
    for _ in range(12):
        hoi4.scroll(hwnd, px, py, -step)
        time.sleep(0.35)
        cur = tree_pixels(hwnd)
        moved = best_shift(prev, cur, 0, range(0, step * NOTCH + 1, NOTCH))
        if moved < step * NOTCH:  # hit the bottom: the last notch may move only part-way, so find it to the pixel
            coarse = best_shift(prev[::2, ::4], cur[::2, ::4], 0, range(0, step * NOTCH // 2 + 1))
            moved = best_shift(prev, cur, 0, range(max(0, coarse * 2 - 3), coarse * 2 + 4))
            v_max += moved
            break
        v_max += moved
        prev = cur
    h_views = measure_h_views(hwnd)
    scroll_home(hwnd)
    return h_views, v_max


def views_for(h_views, v_max):
    """(knob, h_offset, v_offset) scroll positions that together show the whole tree."""
    vs = sorted(set(list(range(0, v_max, 750)) + [v_max]))  # v_max is reached by over-scrolling to the bottom
    return [(knob, h_off, v) for v in vs for knob, h_off in h_views]


def open_tree(hwnd, slot, tab):
    if tab not in R["tabs"]:
        raise ActionError(f"unknown research tab {tab!r}; known: {', '.join(R['tabs'])}")
    if not tree_open(hwnd):
        open_screen(hwnd, "research")
        hoi4.click(hwnd, R["slot_click_x"], R["slot_click_y"][slot - 1])
        if not wait_for(lambda: tree_open(hwnd), timeout=2.5):
            raise ActionError(f"clicking research slot {slot} did not open the tech tree")
    hoi4.click(hwnd, R["tabs"][tab], R["tab_y"])
    time.sleep(0.7)
    if not tree_open(hwnd):
        raise ActionError(f"the tech tree closed after clicking the {tab} tab")


def detail_title(hwnd):
    """The open detail window's tech name, or '' when no detail window is open."""
    if not detail_open(hwnd):
        return ""
    return raw_detail_title(hwnd)


def raw_detail_title(hwnd):
    lines = read_box(hwnd, R["detail_title_box"], park=False)
    return " ".join(l.text for l in lines).strip()


def close_detail(hwnd):
    hoi4.click(hwnd, *R["detail_close"])
    time.sleep(0.3)


def detect_candidates(img):
    """Points likely inside tech icons in a tree screenshot: bright blobs after removing thin lines,
    plus the grid of their row/column clusters (icons sit on a grid)."""
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    x0, y0, x1, y1 = R["tree_box"]
    mask = np.zeros(lum.shape, bool)
    mask[y0:y1, x0:x1] = lum[y0:y1, x0:x1] > 95
    b = 4
    h, w = mask.shape
    blocks = mask[:h // b * b, :w // b * b].reshape(h // b, b, w // b, b).mean(axis=(1, 3)) > 0.35

    def erode(m):
        o = m.copy()
        o[1:] &= m[:-1]; o[:-1] &= m[1:]; o[:, 1:] &= m[:, :-1]; o[:, :-1] &= m[:, 1:]
        return o

    def dilate(m):
        o = m.copy()
        o[1:] |= m[:-1]; o[:-1] |= m[1:]; o[:, 1:] |= m[:, :-1]; o[:, :-1] |= m[:, 1:]
        return o

    opened = dilate(dilate(erode(erode(blocks))))
    seen = np.zeros_like(opened)
    pts = []
    bh, bw = opened.shape
    for yy in range(bh):
        for xx in range(bw):
            if opened[yy, xx] and not seen[yy, xx]:
                q, ys, xs = deque([(yy, xx)]), [], []
                seen[yy, xx] = True
                while q:
                    cy, cx = q.popleft()
                    ys.append(cy); xs.append(cx)
                    for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= ny < bh and 0 <= nx < bw and opened[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
                bw_px, bh_px = (max(xs) - min(xs) + 1) * b, (max(ys) - min(ys) + 1) * b
                if 32 <= bw_px <= 320 and 32 <= bh_px <= 110:
                    pts.append(((min(xs) + max(xs) + 1) * b // 2, (min(ys) + max(ys) + 1) * b // 2))

    def clusters(values, gap=45):
        out = []
        for v in sorted(values):
            if out and v - out[-1][-1] <= gap:
                out[-1].append(v)
            else:
                out.append([v])
        return [sum(c) // len(c) for c in out if len(c) >= 2]

    cols, rows = clusters([p[0] for p in pts]), clusters([p[1] for p in pts])
    grid = [(cx, cy) for cx in cols for cy in rows]
    out = []
    for p in pts + grid:
        if x0 + 20 <= p[0] <= x1 - 20 and y0 + 20 <= p[1] <= y1 - 20 and all(
                abs(p[0] - q[0]) > 30 or abs(p[1] - q[1]) > 30 for q in out):
            out.append(p)
    return out


def calibrate_research(hwnd, tabs=None, slot=5, log=print):
    """Click every candidate icon in each tab, read the detail window's title, and store tree-space positions."""
    data = json.loads(TECH_MAP.read_text(encoding="utf-8")) if TECH_MAP.exists() else {"tabs": {}}
    for tab in tabs or list(R["tabs"]):
        open_tree(hwnd, slot, tab)
        h_views, v_max = measure_geometry(hwnd)
        log(f"  {tab}: scrolls {v_max} px down; sideways views (knob, offset) {h_views}")
        found = {}
        for knob, h_off, v_off in views_for(h_views, v_max):
            to_view(hwnd, knob, v_off, v_max)
            if not tree_open(hwnd):
                raise ActionError(f"{tab}: the tech tree is no longer open; stopped before clicking the map")
            park_mouse(hwnd)
            cands = detect_candidates(hoi4.grab(hwnd))
            log(f"  {tab} view +{h_off}/+{v_off}: {len(cands)} candidates")
            for n, (sx, sy) in enumerate(cands):
                if n and n % 12 == 0 and not tree_open(hwnd):
                    raise ActionError(f"{tab}: the tech tree closed during probing")
                tx, ty = sx + h_off, sy + v_off
                if any(abs(tx - e["x"]) < 30 and abs(ty - e["y"]) < 30 for e in found.values()):
                    continue
                hoi4.click(hwnd, sx, sy)
                time.sleep(0.45)
                title = detail_title(hwnd)
                if not title:
                    if raw_detail_title(hwnd):  # some window opened without days/Research: close it
                        close_detail(hwnd)
                    continue
                days = next((int(m.group(1)) for l in read_box(hwnd, R["detail_days_box"], park=False)
                             for m in [re.search(r"(\d+)\s*day", l.text)] if m), None)
                if title not in found:
                    found[title] = {"x": tx, "y": ty, "days": days}
                close_detail(hwnd)
        data["tabs"][tab] = {"h_views": h_views, "v_max": v_max, "techs": found}
        log(f"{tab}: {len(found)} techs")
        TECH_MAP.parent.mkdir(parents=True, exist_ok=True)
        TECH_MAP.write_text(json.dumps(data, indent=1), encoding="utf-8")
    hoi4.click(hwnd, *R["tree_close"])
    time.sleep(0.3)
    close_screen(hwnd, "research")
    return data


def find_tech(name):
    if not TECH_MAP.exists():
        raise ActionError("no tech map yet: run  hoi4.py act calibrate-research")
    data = json.loads(TECH_MAP.read_text(encoding="utf-8"))
    best = (0.0, None, None, None)
    for tab, info in data["tabs"].items():
        for title, pos in info["techs"].items():
            score = similar(name, title)
            if score > best[0]:
                best = (score, tab, title, pos)
    if best[0] < 0.75:
        raise ActionError(f"no tech like {name!r} in the map (closest: {best[2]!r}); recalibrate that tab?")
    info = data["tabs"][best[1]]
    return best[1], best[2], best[3], (info.get("h_views", [[None, 0]]), info.get("v_max", 0))


def choose_mio(hwnd, mio):
    """If the Military Industrial Organization picker is open, choose one. Returns what was chosen or None."""
    lines = read_box(hwnd, R["mio_box"])
    if not any("industrial organization" in l.text.lower() for l in lines):
        return None
    if mio == "none":
        target = next(l for l in lines if "without" in l.text.lower())
    else:
        rows = [l for l in lines if l.text.strip() and "organization" not in l.text.lower()
                and not re.search(r"(details|/day|manufacturer|name|cost)", l.text.lower())
                and l.box[1] > lines[0].box[1] + 40 and len(l.text) > 3]
        if not rows:
            raise ActionError("MIO picker open but no organizations could be read")
        if mio == "first":
            target = rows[0]
        else:
            target = max(rows, key=lambda l: similar(mio, l.text))
    hoi4.click(hwnd, *target.center)
    time.sleep(0.6)
    return target.text


def research(hwnd, slot, tech, mio="first", dry_run=False, log=print):
    """Start researching `tech` in `slot`. If the slot is busy the game asks before replacing (progress is
    kept for later), so this refuses a busy slot unless the caller has checked that with read_research."""
    tab, title, pos, (h_views, v_max) = find_tech(tech)
    open_tree(hwnd, slot, tab)
    # the sideways view that shows the target nearest the middle, and as little scrolling down as needed
    fits = [v for v in h_views if 40 <= pos["x"] - v[1] <= 1860] or h_views
    knob, h_off = min(fits, key=lambda v: abs(pos["x"] - v[1] - 960))
    v_off = 0 if pos["y"] <= 1140 else (pos["y"] - 680) // NOTCH * NOTCH
    if v_off >= v_max - NOTCH:
        v_off = v_max  # near the bottom: scroll all the way, which lands exactly on v_max
    to_view(hwnd, knob, v_off, v_max)
    off = (h_off, v_off)
    sx, sy = pos["x"] - h_off, pos["y"] - v_off
    if not (R["tree_box"][1] <= sy <= R["tree_box"][3] and 0 <= sx < 1920):
        raise ActionError(f"{title!r} is off screen at this scroll ({sx}, {sy}); nothing clicked")
    hoi4.click(hwnd, sx, sy)
    got = wait_for(lambda: detail_title(hwnd), timeout=1.5)
    if similar(got, title) < 0.75:
        if got:
            close_detail(hwnd)
        raise ActionError(f"clicked where {title!r} should be, but the window reads {got!r}")
    if dry_run:
        close_detail(hwnd)
        hoi4.click(hwnd, *R["tree_close"])
        time.sleep(0.4)
        close_screen(hwnd, "research")
        log(f"dry run: found {title} in the {tab} tab at ({sx}, {sy}) after scrolling {off}; nothing started")
        return None
    hoi4.click(hwnd, *R["detail_research"])
    time.sleep(0.6)
    chosen = choose_mio(hwnd, mio)
    if tree_open(hwnd):
        hoi4.click(hwnd, *R["tree_close"])
        time.sleep(0.4)
    slots = read_research(hwnd, keep_open=True)
    close_screen(hwnd, "research")
    now = slots[slot - 1]
    if not now["tech"] or similar(now["tech"], title) < 0.7:
        raise ActionError(f"slot {slot} now reads {now['tech']!r}, not {title!r}")
    log(f"slot {slot}: researching {title} ({now['days']} days)" + (f" with {chosen}" if chosen else ""))
    return now


# --------------------------------------------------------------------------
# production
# --------------------------------------------------------------------------
P = T["production"]


COUNT_CROPS = ((0, 640, 18, 2), (0, 640, 18, 3), (480, 640, 20, 2), (520, 580, 14, 4), (0, 700, 40, 2))


def read_count(img, y):
    """The factory count on a production line's header. Windows OCR often misses lone digits, so try a few
    crops and take the first number found near the count's position; None if every crop misses it."""
    lo, hi = P["count_box_x"]
    for x0, x1, dy, up in COUNT_CROPS:
        for l in ocr_image(img.crop((x0, y - dy, x1, y + dy)), origin=(x0, y - dy), upscale=up):
            if re.fullmatch(r"\d{1,3}", l.text.strip()) and lo - 30 <= l.center[0] <= hi + 30:
                return int(l.text)
    return None


def read_production(hwnd, keep_open=False):
    open_screen(hwnd, "production")
    hoi4.scroll(hwnd, *P["scroll_point"], 30)
    time.sleep(0.4)
    park_mouse(hwnd)
    img = hoi4.grab(hwnd)
    lines = ocr_image(img.crop((0, 300, 700, 1200)), origin=(0, 300), upscale=2)
    header = " ".join(l.text for l in lines if l.center[1] < 345)
    rows = []
    for i, y in enumerate(P["row_y"]):
        band = [l for l in lines if y - 15 <= l.center[1] <= y + 95]
        top = [l for l in band if abs(l.center[1] - y) <= 15]
        name = " ".join(l.text for l in top if l.box[0] < 420 and not re.fullmatch(r"\d+", l.text.strip())).strip()
        detail = " ".join(l.text for l in band if l not in top and l.box[0] < 420)
        rows.append({"line": i + 1, "name": re.sub(r"^\d+\s*(a\s+|\.\s*)?", "", name), "factories": read_count(img, y),
                     "detail": detail})
    if not keep_open:
        close_screen(hwnd, "production")
    return header, rows


def production(hwnd, line, add=0, remove=0, log=print):
    if not 1 <= line <= len(P["row_y"]):
        raise ActionError(f"only lines 1-{len(P['row_y'])} (the first screen) are supported so far")
    _, before = read_production(hwnd, keep_open=True)
    y = P["row_y"][line - 1]
    for _ in range(add):
        hoi4.click(hwnd, P["plus_x"], y)
        time.sleep(0.2)
    for _ in range(remove):
        hoi4.click(hwnd, P["minus_x"], y)
        time.sleep(0.2)
    header, after = read_production(hwnd, keep_open=True)
    close_screen(hwnd, "production")
    b, a = before[line - 1], after[line - 1]
    log(f"line {line} {a['name']}: factories {b['factories']} -> {a['factories']} | {header}")
    return a


# --------------------------------------------------------------------------
# saves
# --------------------------------------------------------------------------
SAVE_DIR = hoi4.USER_DIR / "save games"


def find_text(hwnd, text, box, timeout=20.0):
    deadline = time.time() + timeout
    while True:
        for l in read_box(hwnd, list(box)):
            if norm(text) in norm(l.text):
                return l
        if time.time() >= deadline:
            raise ActionError(f"never saw {text!r} on screen")
        time.sleep(1.5)


def save_game(hwnd, name, log=print):
    """Save through the console as claude_<name> (never one of Jerus's own save names)."""
    if not name.startswith("claude_"):
        name = "claude_" + name
    if not re.fullmatch(r"claude_[A-Za-z0-9_\-]+", name):
        raise ActionError("a save name may use letters, digits, _ and - only")
    path = SAVE_DIR / f"{name}.hoi4"
    before = path.stat().st_mtime if path.exists() else 0
    hoi4.run_console(hwnd, f"save {name}")
    deadline, last = time.time() + 60, -1
    while time.time() < deadline:
        if path.exists() and path.stat().st_mtime > before:
            size = path.stat().st_size
            if size == last:
                log(f"saved {path.name} ({size / 1e6:.0f} MB)")
                return path
            last = size
        time.sleep(1)
    raise ActionError(f"{path.name} did not appear within 60 s")


def load_save(hwnd, name, log=print):
    """From the main menu: Single Player, Load, pick the save, Load, Start; then wait for the map."""
    find_text(hwnd, "Single Player", (700, 300, 1220, 800), timeout=150)
    for label, box in (("Single Player", (700, 300, 1220, 800)), ("Load", (700, 300, 1220, 800))):
        l = find_text(hwnd, label, box)
        hoi4.click(hwnd, *l.center)
        time.sleep(2)
    entry = find_text(hwnd, name, (0, 500, 430, 1080), timeout=30)
    hoi4.click(hwnd, *entry.center)
    time.sleep(1.5)
    hoi4.click(hwnd, *find_text(hwnd, "Load", (180, 1120, 460, 1180)).center)
    start = find_text(hwnd, "START", (1500, 1100, 1920, 1190), timeout=120)
    time.sleep(2)
    hoi4.click(hwnd, *start.center)
    find_text(hwnd, ", 19", T["top_bar"]["clock_box"], timeout=120)
    log(f"loaded {entry.text}; in game at {read_date(hwnd)}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def read_date(hwnd):
    return " ".join(l.text for l in read_box(hwnd, T["top_bar"]["clock_box"]))


def main(argv):
    p = argparse.ArgumentParser(prog="hoi4.py act/read")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("research")
    s.add_argument("--slot", type=int, required=True)
    s.add_argument("--tech", required=True)
    s.add_argument("--mio", default="first", help="first, none, or an organization's name")
    s.add_argument("--dry-run", action="store_true", help="find and check the tech, start nothing")
    s.add_argument("--replace", action="store_true", help="allow replacing the research in a busy slot")
    s = sub.add_parser("production")
    s.add_argument("--line", type=int, required=True)
    s.add_argument("--add", type=int, default=0)
    s.add_argument("--remove", type=int, default=0)
    s = sub.add_parser("open")
    s.add_argument("screen")
    s = sub.add_parser("close")
    s.add_argument("screen")
    s = sub.add_parser("calibrate-research")
    s.add_argument("--tabs", help="comma-separated tab names (default: all)")
    s = sub.add_parser("save")
    s.add_argument("name", help="saved as claude_<name>")
    s = sub.add_parser("load-save")
    s.add_argument("name", help="the save's name as the Load list shows it, e.g. claude_ger_1936")
    s = sub.add_parser("read")
    s.add_argument("what", choices=["research", "production", "date", "techs"])
    s.add_argument("--tab")
    s.add_argument("--grep")
    args = p.parse_args(argv)

    hwnd = hoi4.need_window()
    hoi4.focus(hwnd)
    if args.cmd == "research":
        if not args.dry_run and not args.replace:
            busy = read_research(hwnd)[args.slot - 1]
            if busy["tech"]:
                raise ActionError(f"slot {args.slot} is busy with {busy['tech']} ({busy['days']} days left); "
                                  "add --replace to swap it out")
        research(hwnd, args.slot, args.tech, args.mio, dry_run=args.dry_run)
    elif args.cmd == "production":
        production(hwnd, args.line, args.add, args.remove)
    elif args.cmd == "open":
        open_screen(hwnd, args.screen)
        print(f"{args.screen} open")
    elif args.cmd == "close":
        close_screen(hwnd, args.screen)
        print(f"{args.screen} closed")
    elif args.cmd == "save":
        save_game(hwnd, args.name)
    elif args.cmd == "load-save":
        load_save(hwnd, args.name)
    elif args.cmd == "calibrate-research":
        calibrate_research(hwnd, args.tabs.split(",") if args.tabs else None)
        print(f"tech map saved to {TECH_MAP}")
    elif args.what == "research":
        for s in read_research(hwnd):
            print(f"  slot {s['slot']}: {s['tech'] or '(empty)'}" + (f" - {s['days']} days" if s["days"] else ""))
    elif args.what == "production":
        header, rows = read_production(hwnd)
        print(header)
        for r in rows:
            print(f"  line {r['line']}: {r['name']} | factories {r['factories']} | {r['detail']}")
    elif args.what == "date":
        print(read_date(hwnd))
    elif args.what == "techs":
        if not TECH_MAP.exists():
            raise ActionError("no tech map yet: run  hoi4.py act calibrate-research")
        data = json.loads(TECH_MAP.read_text(encoding="utf-8"))
        for tab, info in data["tabs"].items():
            if args.tab and tab != args.tab:
                continue
            for title, pos in sorted(info["techs"].items(), key=lambda kv: (kv[1]["y"], kv[1]["x"])):
                if args.grep and args.grep.lower() not in title.lower():
                    continue
                print(f"  {tab:<14}{title:<45}{(str(pos['days']) + ' days') if pos.get('days') else ''}")

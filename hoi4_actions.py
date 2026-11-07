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
    # OCR reads the Roman numeral III as "Ill" or "lll": treat them alike so "Construction III" finds "Construction Ill"
    text = re.sub(r"(?<![A-Za-z])(Ill|lll|IIl|IlI)(?![A-Za-z])", "III", text)
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
# notices ("Research Finished!", "National Focus Completed") sit on top of everything and catch clicks
# --------------------------------------------------------------------------
NOTICE_WORDS = ("researchfinished", "nationalfocuscompleted", "focuscompleted")


def dismiss_notices(hwnd, log=print, tries=4):
    """Close the small centre notices by their own Ok button. Returns how many were closed."""
    closed = 0
    for _ in range(tries):
        lines = read_box(hwnd, T["notice_box"])
        joined = norm(" ".join(l.text for l in lines))  # OCR may split "NATIONAL / Focus / COMPLETED"
        if not any(w in joined for w in NOTICE_WORDS):
            break
        ok = [l for l in lines if norm(l.text) in ("ok", "0k")]  # OCR often reads the O as a zero
        hoi4.click(hwnd, *(ok[0].center if ok else T["notice_ok"]))
        time.sleep(0.5)
        closed += 1
        log(f"closed a notice: {' '.join(l.text for l in lines[:4])}")
    closed += dismiss_treaties(hwnd, log)
    closed += dismiss_news(hwnd, log)
    return closed


def dismiss_treaties(hwnd, log=print, tries=3):
    """Peace results ("TREATY OF ...": who took which states) are a box with one Ok in the middle."""
    closed = 0
    for _ in range(tries):
        lines = read_box(hwnd, T["treaty_box"])
        title = " ".join(l.text for l in lines if l.box[1] < 440)
        if "treaty" not in norm(title):
            break
        ok = [l for l in lines if norm(l.text) in ("ok", "0k")]
        if not ok:
            log("a treaty popup is open but its Ok could not be read")
            break
        hoi4.click(hwnd, *ok[0].center)
        time.sleep(0.6)
        closed += 1
        log(f"closed {title}: " + "; ".join(l.text for l in lines if 450 < l.box[1] < 700))
    return closed


def dismiss_news(hwnd, log=print, tries=3):
    """World News popups (a newspaper with a headline and one answer button) also catch clicks. Close them by
    their single answer button. Real events with several options are left alone: they need a decision."""
    closed = 0
    for _ in range(tries):
        lines = read_box(hwnd, T["news_box"])
        if "news" not in norm(" ".join(l.text for l in lines if l.box[1] < 300)):
            break
        bx0, by0, bx1, by1 = T["news_button_box"]
        buttons = [l for l in lines if bx0 <= l.center[0] <= bx1 and by0 <= l.center[1] <= by1]
        if len(buttons) != 1:
            log(f"a news popup has {len(buttons)} answers; left open for a decision")
            break
        headline = next((l.text for l in lines if 520 <= l.center[1] <= 570), "")
        hoi4.click(hwnd, *buttons[0].center)
        time.sleep(0.6)
        closed += 1
        log(f"closed world news: {headline} ({buttons[0].text})")
    return closed


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
    hoi4.scroll(hwnd, *R["scroll_point"], 100)  # 5000 px: past the top of the tallest tree
    time.sleep(0.2)
    set_knob(hwnd, KNOB_BOX[0])


def to_view(hwnd, knob, v_off, v_max=None):
    """Show the tree with the knob at `knob` (None, or its left end, means no sideways scroll) and scrolled down
    by v_off: a multiple of 50, or v_max itself (reached by scrolling past the bottom)."""
    scroll_home(hwnd)
    if knob is not None and knob > KNOB_BOX[0] + 15:
        set_knob(hwnd, knob)
    if v_off:
        notches = v_max // NOTCH + 10 if v_max is not None and v_off >= v_max else v_off // NOTCH
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
    pos, step = left, (right_end - left) / steps

    def median_shift(a, b):
        shifts = sorted(a[t] - b[t] for t in a if t in b)
        return shifts[len(shifts) // 2] if shifts else None

    def bright_shift(a, b):
        """Sideways shift between two views from the tree's bright lines and icons only: the dim background
        picture is what stays still. For tabs with no text labels."""
        import numpy as np
        ma, mb = (a > 95).astype(np.int16), (b > 95).astype(np.int16)
        coarse = best_shift(ma[::4, ::4], mb[::4, ::4], 1, range(0, 400))
        return best_shift(ma[::2], mb[::2], 1, range(max(0, coarse * 4 - 6), coarse * 4 + 7))

    prev_px = tree_pixels(hwnd)
    while pos < right_end - 2:
        actual = set_knob(hwnd, round(min(right_end, pos + step)))
        cur = label_xs(hwnd)
        moved = median_shift(prev, cur)
        cur_px = tree_pixels(hwnd)
        if moved is None and step <= 160:  # no label in both views: match the bright tree instead
            moved = bright_shift(prev_px, cur_px) or None
        if moved is None:  # too far for any label to stay on screen: go back and take a smaller step
            if step < 15:
                raise ActionError("a sideways step left no label in common even at 15 px")
            set_knob(hwnd, round(pos))
            back = label_xs(hwnd)
            total += median_shift(prev, back) or 0
            prev, prev_px, step = back, tree_pixels(hwnd), step / 2
            continue
        if actual is None or actual <= pos:
            break
        total += moved
        views.append([actual, total])
        prev, prev_px, pos = cur, cur_px, actual
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
            score = 1.01 if norm(name) == norm(title) else similar(name, title)  # an exact match always wins
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
    if not chosen and similar(raw_detail_title(hwnd), title) >= 0.75:
        # still on the detail window: the button is greyed out. Its tooltip says why.
        hoi4.move_mouse(*hoi4.to_screen(hwnd, *R["detail_research"]))
        time.sleep(0.9)
        why = " ".join(l.text for l in ocr_image(hoi4.grab(hwnd).crop(tuple(R["tooltip_box"])),
                                                 origin=tuple(R["tooltip_box"][:2])) if "shortcut" not in l.text.lower())
        close_detail(hwnd)
        hoi4.click(hwnd, *R["tree_close"])
        time.sleep(0.4)
        close_screen(hwnd, "research")
        raise ActionError(f"the game will not start {title}: {why or 'Research is greyed out'}")
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


def line_matches(name, header_text):
    """A production line header reads like '11 BF109A' or '1 Karabiner 98k': match the name after the number."""
    m = re.match(r"\s*\d+\s*(.*)", header_text)
    if not m:
        return False
    rest = norm(m.group(1))
    want = norm(name)
    return bool(want) and (want in rest or similar(want, rest) >= 0.8)


def factory_header(hwnd):
    return " ".join(l.text for l in read_box(hwnd, [0, 300, 700, 365]) if "factor" in l.text.lower() or "/" in l.text)


def find_line(hwnd, name, max_scrolls=15):
    """Scroll the production list from the top until a line header matches `name`. Returns (y, header text)."""
    open_screen(hwnd, "production")
    hoi4.scroll(hwnd, *P["scroll_point"], 40)
    time.sleep(0.4)
    seen = []
    for _ in range(max_scrolls):
        lines = read_box(hwnd, P["list_box"])
        for l in lines:
            if l.box[0] < 60 and 500 <= l.center[1] <= 1150 and line_matches(name, l.text):
                return l.center[1], l.text
        seen += [l.text for l in lines if l.box[0] < 60 and re.match(r"\s*\d+\s", l.text)]
        before = [l.text for l in lines]
        hoi4.scroll(hwnd, *P["scroll_point"], -5)
        time.sleep(0.45)
        if [l.text for l in read_box(hwnd, P["list_box"])] == before:
            break
    raise ActionError(f"no production line like {name!r}; lines seen: {', '.join(dict.fromkeys(seen))}")


def production_by_name(hwnd, name, add=0, remove=0, log=print):
    """Add or remove factories on the line whose header matches `name`, anywhere in the list."""
    y, header_text = find_line(hwnd, name)
    park_mouse(hwnd)
    before = read_count(hoi4.grab(hwnd), y)
    for _ in range(add):
        hoi4.click(hwnd, P["plus_x"], y)
        time.sleep(0.2)
    for _ in range(remove):
        hoi4.click(hwnd, P["minus_x"], y)
        time.sleep(0.2)
    time.sleep(0.3)
    park_mouse(hwnd)
    after = read_count(hoi4.grab(hwnd), y)
    header = factory_header(hwnd)
    close_screen(hwnd, "production")
    log(f"{header_text}: factories {before} -> {after} | {header}")
    return after


# --------------------------------------------------------------------------
# armies
# --------------------------------------------------------------------------
AR = T["army"]


def deselect(hwnd):
    """Clear the unit selection: click open sea, then close the sea-region panel that opens."""
    hoi4.click(hwnd, *AR["empty_sea"])
    time.sleep(0.5)
    hoi4.click(hwnd, *AR["sea_panel_close"])
    time.sleep(0.3)


def army_cards(hwnd):
    """The army cards along the bottom, left to right: [(divisions, x)]."""
    lines = read_box(hwnd, AR["card_numbers_box"], upscale=3)
    # a card with a commander reads like "19 4": the count, then the general's skill badge
    return [(int(m.group(1)), l.center[0]) for l in lines for m in [re.match(r"\s*(\d+)", l.text)] if m]


def army_panel(hwnd):
    """The selected army's header: name, commander (or None), 'n/24'."""
    lines = read_box(hwnd, AR["army_header_box"])
    name = next((l.text for l in lines if re.match(r"Army \d+", l.text)), None)
    has_cmd = not any("no commander" in l.text.lower() for l in lines)
    general = None
    if has_cmd:
        gl = [l for l in lines if norm(l.text).startswith("genera")]  # OCR: "Generat"
        if gl:
            general = next((l.text for l in lines if 0 < l.center[1] - gl[0].center[1] < 35
                            and abs(l.box[0] - gl[0].box[0]) < 20), None)
    size = next((l.text for l in lines if re.match(r"\d+/\d+", l.text)), None)
    return {"name": name, "general": general if has_cmd else None, "size": size}


def select_army(hwnd, index):
    cards = army_cards(hwnd)
    if not 1 <= index <= len(cards):
        raise ActionError(f"there are {len(cards)} army cards; no army {index}")
    deselect(hwnd)
    hoi4.click(hwnd, cards[index - 1][1], AR["card_click_y"])
    time.sleep(0.8)
    return army_panel(hwnd)


def list_armies(hwnd, log=print):
    out = []
    for i, (n, _) in enumerate(army_cards(hwnd), 1):
        p = select_army(hwnd, i)
        out.append(p)
        log(f"  card {i}: {p['name']} | {p['size']} | {p['general'] or 'NO COMMANDER'}")
    deselect(hwnd)
    return out


def assign_general(hwnd, index, name=None, log=print):
    """Give army `index` a commander: `name`, or the first one the game lists (it sorts by skill)."""
    p = select_army(hwnd, index)
    hoi4.click(hwnd, *AR["commander_slot"])
    time.sleep(1.0)
    lines = read_box(hwnd, AR["commander_list_box"])
    labels = [l for l in lines if norm(l.text).startswith("genera") and len(l.text) < 10]
    names = [l for l in lines for g in labels if 0 < l.center[1] - g.center[1] < 35 and abs(l.box[0] - g.box[0]) < 20]
    if not names:
        raise ActionError(f"no generals readable in the commander list; read: {[l.text for l in lines][:10]}")
    pick = max(names, key=lambda l: similar(name, l.text)) if name else names[0]
    hoi4.click(hwnd, *pick.center)
    time.sleep(1.0)
    after = army_panel(hwnd)
    if not after["general"]:
        raise ActionError(f"clicked {pick.text} but {p['name']} still has no commander")
    log(f"{after['name']} ({after['size']}): commander {after['general']}")
    return after


def new_army_button(hwnd):
    """The green '+' that creates a new army from the selection."""
    import numpy as np
    park_mouse(hwnd)
    x0, y0, x1, y1 = AR["plus_band"]
    a = np.asarray(hoi4.grab(hwnd).convert("RGB").crop((x0, y0, x1, y1))).astype(int)
    g = (a[..., 1] > 150) & (a[..., 0] < 120) & (a[..., 2] < 120)
    cols = np.nonzero(g.sum(axis=0) >= 3)[0]
    groups = []
    for x in cols:
        if groups and x - groups[-1][-1] <= 6:
            groups[-1].append(x)
        else:
            groups.append([x])
    for grp in (g_ for g_ in groups if len(g_) >= 8):
        ys = np.nonzero(g[:, grp].any(axis=1))[0]
        pt = (int(np.mean(grp)) + x0, int(np.median(ys)) + y0)
        hoi4.move_mouse(*hoi4.to_screen(hwnd, *pt))
        time.sleep(1.0)
        tip = " ".join(l.text for l in ocr_image(hoi4.grab(hwnd).crop((500, 600, 1500, 1060)), origin=(500, 600))).lower()
        if "army" in tip and "army group" not in tip:
            return pt
    return None


def new_army(hwnd, halves=0, log=print):
    """Make an army from the selected unassigned divisions: drop armies from the selection, halve it `halves`
    times with S, then press New Army."""
    for _ in range(8):
        heads = [l for l in read_box(hwnd, AR["selection_box"]) if re.match(r"Army \d+$", l.text.strip())]
        if not heads:
            break
        hoi4.click(hwnd, AR["panel_close_x"], heads[-1].center[1])
        time.sleep(0.5)
    if "unassigned" not in " ".join(l.text for l in read_box(hwnd, AR["selection_box"])).lower():
        raise ActionError("no unassigned divisions are selected")
    for _ in range(halves):
        hoi4.press_combo("s")
        time.sleep(0.5)
    before = sum(n for n, _ in army_cards(hwnd))
    plus = new_army_button(hwnd)
    if not plus:
        raise ActionError("the New Army button was not found")
    hoi4.click(hwnd, *plus)
    time.sleep(1.2)
    cards = army_cards(hwnd)
    if sum(n for n, _ in cards) <= before:
        raise ActionError("New Army was pressed but no new army card appeared")
    p = army_panel(hwnd)
    log(f"created {p['name']} with {p['size']} | armies now {[n for n, _ in cards]}")
    return p


def front_line(hwnd, index, border_point, log=print):
    """Army `index` gets a front line along the border clicked at `border_point` (window pixels on the dashed
    border the front-line tool highlights). Works in peacetime too."""
    p = select_army(hwnd, index)
    hoi4.press_combo(AR["front_line_key"])
    time.sleep(0.6)
    hoi4.click(hwnd, *border_point)
    time.sleep(1.2)
    tip = " ".join(l.text for l in read_box(hwnd, AR["tooltip_box"], park=False)).lower()
    hoi4.press_combo("esc") if "cannot draw" in tip else None
    if "cannot draw" in tip:
        raise ActionError(f"the game would not draw a front line there: {tip[:160]}")
    log(f"{p['name']} ({p['general']}): front line drawn at {border_point}")
    return p


def select_box(hwnd, box):
    deselect(hwnd)
    hoi4.drag(hwnd, box[0], box[1], box[2], box[3])
    time.sleep(0.8)
    return " ".join(l.text for l in read_box(hwnd, AR["selection_box"]))[:200]


# --------------------------------------------------------------------------
# national focus
# --------------------------------------------------------------------------
FC = T["focus"]


def current_focus(hwnd):
    """The running focus as Politics shows it, or None ("Select a National Focus")."""
    open_screen(hwnd, "politics")
    text = " ".join(l.text for l in read_box(hwnd, FC["politics_focus_box"])).strip()
    close_screen(hwnd, "politics")
    return None if "select" in text.lower() and "focus" in text.lower() else (text or None)


def focus_view_open(hwnd):
    return "focustree" in norm(" ".join(l.text for l in read_box(hwnd, T["screens"]["_title_box"])))


def start_focus(hwnd, name, log=print):
    """Start a focus by name through the tree's search. Refuses when a focus is already running; when the game
    refuses Start, says so with the requirement lines it can read."""
    running = current_focus(hwnd)
    if running:
        raise ActionError(f"a focus is already running: {running}")
    if not focus_view_open(hwnd):
        hoi4.press_combo(FC["key"])
        if not wait_for(lambda: focus_view_open(hwnd), timeout=2.0):
            raise ActionError("the focus tree did not open")
    hoi4.click(hwnd, *FC["search_box"])
    time.sleep(0.3)
    hoi4.press_combo("ctrl+a")
    hoi4.type_text(name)
    time.sleep(0.4)
    hoi4.press_combo("enter")
    time.sleep(1.2)
    # the detail window opens in different places, so read the whole tree area and pair the title with its Start
    lines = read_box(hwnd, FC["tree_box"])
    titles = [l for l in lines if l.text.isupper() and len(l.text) > 3
              and (norm(name) in norm(l.text) or similar(name, l.text) >= 0.7)]
    if not titles:
        hoi4.press_combo(FC["key"])
        seen = [l.text for l in lines if l.text.isupper() and len(l.text) > 3]
        raise ActionError(f"no detail window titled like {name!r}; uppercase text seen: {seen[:8]}")
    title = titles[0]
    start = sorted((l for l in lines if norm(l.text) == "start"),
                   key=lambda l: abs(l.center[0] - title.center[0]) + abs(l.center[1] - title.center[1]))
    if not start or abs(start[0].center[1] - title.center[1]) > 150:
        hoi4.press_combo(FC["key"])
        raise ActionError(f"no Start button near {title.text}")
    title = title.text
    hoi4.click(hwnd, *start[0].center)
    time.sleep(1.0)
    if focus_view_open(hwnd):  # still open: the game refused (Start closes the tree when it works)
        hoi4.move_mouse(*hoi4.to_screen(hwnd, *start[0].center))
        time.sleep(1.0)
        reqs = []
        for _ in range(6):
            for l in read_box(hwnd, FC["requirements_box"], park=False):
                if l.text not in reqs:
                    reqs.append(l.text)
            hoi4.scroll(hwnd, *FC["requirements_scroll"], -2)
            time.sleep(0.3)
        hoi4.press_combo(FC["key"])
        raise ActionError(f"the game refused to start {title}. Requirements it lists: {' | '.join(reqs)}")
    now = current_focus(hwnd)
    if not now or similar(now, name) < 0.5 and norm(name)[:10] not in norm(now):
        raise ActionError(f"Start was clicked but the running focus reads {now!r}")
    log(f"started focus: {now}")
    return now


# --------------------------------------------------------------------------
# recruit & deploy
# --------------------------------------------------------------------------
RC = T["recruit"]


def _queue_lines(hwnd):
    return read_box(hwnd, RC["queue_box"])


def _count_fields(lines):
    """Training-count fields ('1/1', '1/∞' read as '1/30', '1/4') in the queue."""
    return [l for l in lines if l.box[0] > 480 and l.text.startswith("1/")]


def count_value(text):
    """'1/1' -> 1, '1/4 G' -> 4; infinity (OCR '1/30', '1/00', '1/∞') -> None."""
    m = re.match(r"1/(\d)(\d?)", text.strip())
    if not m or m.group(2):
        return None
    return int(m.group(1)) or None


def _scroll_queue(hwnd, notches):
    hoi4.scroll(hwnd, *RC["scroll_point"], notches)
    time.sleep(0.45)


def _each_queue_page(hwnd, fn, max_pages=20):
    """Call fn(lines) on each page of the training queue, top to bottom. fn returns True when it changed
    something on the page (the page is then read again before moving on)."""
    _scroll_queue(hwnd, 60)
    for _ in range(max_pages * 3):
        lines = _queue_lines(hwnd)
        if fn(lines):
            continue
        _scroll_queue(hwnd, -6)
        if [l.text for l in _queue_lines(hwnd)] == [l.text for l in lines]:
            return


def fix_queue(hwnd, log=print):
    """Every training line: count 1 (not infinity, not more) and a deploy location. Returns what it changed."""
    changed = {"count": 0, "location": 0}

    def fix(lines):
        for l in _count_fields(lines):
            n = count_value(l.text)
            y = l.center[1]
            if n == 1:
                continue
            if n is not None:  # more than 1: lower with "-"
                for _ in range(n - 1):
                    hoi4.click(hwnd, RC["count_minus_x"], y - RC["count_button_dy"])
                    time.sleep(0.3)
            else:  # infinity (OCR: '30', '00', '∞'): one "+" makes it 1
                hoi4.click(hwnd, RC["count_plus_x"], y - RC["count_button_dy"])
            time.sleep(0.5)
            changed["count"] += 1
            return True
        for l in lines:
            if "cation" in l.text.lower() and l.box[0] < 400:  # "No location set" (OCR: "No [öcation set")
                hoi4.click(hwnd, *l.center)
                time.sleep(0.8)
                hoi4.click(hwnd, *RC["deploy_province"])
                time.sleep(0.8)
                still = any("cation" in m.text.lower() and abs(m.center[1] - l.center[1]) < 12
                            for m in _queue_lines(hwnd))
                if still:
                    raise ActionError("could not set a deploy location: the map click hit no green province "
                                      "(was the camera moved?)")
                changed["location"] += 1
                return True
        return False

    _each_queue_page(hwnd, fix)
    log(f"training queue fixed: {changed['count']} counts, {changed['location']} locations")
    return changed


def queue_summary(hwnd):
    names, counts = [], []

    def read(lines):
        names.extend(l.text for l in lines if re.match(r"\d+\. ", l.text))
        counts.extend(l.text for l in _count_fields(lines))
        return False

    _each_queue_page(hwnd, read)
    return list(dict.fromkeys(names)), counts


def recruit(hwnd, count, template="Infanterie-Division", log=print):
    """Queue `count` divisions of a template, each training once, with a deploy location."""
    open_screen(hwnd, "recruit")
    rows = read_box(hwnd, RC["templates_box"])
    names = [l for l in rows if norm(l.text) not in ("train", "edit")]
    tmpl = [l for l in names if norm(l.text) == norm(template)] or [l for l in names if norm(template) in norm(l.text)]
    if not tmpl:
        raise ActionError(f"no template like {template!r}; seen: {', '.join(l.text for l in names[:12])}")
    # each template card: its name, then about 40 px lower its Train and Edit buttons
    train = [l for l in rows if norm(l.text) == "train" and 0 < l.center[1] - tmpl[0].center[1] < 70]
    if not train:
        raise ActionError(f"no Train button on the {tmpl[0].text} row")
    for _ in range(count):
        hoi4.click(hwnd, *train[0].center)
        time.sleep(0.45)
    fix_queue(hwnd, log)
    names, counts = queue_summary(hwnd)
    close_screen(hwnd, "recruit")
    log(f"queued {count} x {tmpl[0].text}; training-count fields seen: {sorted(set(counts))}")


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
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--line", type=int, help="line number 1-5 on the first screen")
    g.add_argument("--name", help="any line, found by its header text, e.g. 'Bf 109' or 'Ju 87'")
    s.add_argument("--add", type=int, default=0)
    s.add_argument("--remove", type=int, default=0)
    s = sub.add_parser("open")
    s.add_argument("screen")
    s = sub.add_parser("close")
    s.add_argument("screen")
    s = sub.add_parser("calibrate-research")
    s.add_argument("--tabs", help="comma-separated tab names (default: all)")
    s = sub.add_parser("dismiss", help="close 'Research Finished!' / 'National Focus Completed' notices")
    s = sub.add_parser("recruit", help="queue divisions: each trains once and has a deploy location")
    s.add_argument("--count", type=int, required=True)
    s.add_argument("--template", default="Infanterie-Division")
    s = sub.add_parser("fix-queue", help="every training line: count 1 and a deploy location")
    s = sub.add_parser("army", help="armies: list | new [--halves N] | general --army N [--name X] | generals")
    s.add_argument("op", choices=["list", "new", "general", "generals", "front"])
    s.add_argument("--at", type=int, nargs=2, metavar=("X", "Y"), help="front: a point on the highlighted border")
    s.add_argument("--army", type=int)
    s.add_argument("--name")
    s.add_argument("--halves", type=int, default=0)
    s = sub.add_parser("select-box", help="drag-select divisions in a screen box: x0 y0 x1 y1")
    s.add_argument("box", type=int, nargs=4)
    s = sub.add_parser("focus", help="start a national focus by name (via the tree's search)")
    s.add_argument("--name", required=True)
    s = sub.add_parser("save")
    s.add_argument("name", help="saved as claude_<name>")
    s = sub.add_parser("load-save")
    s.add_argument("name", help="the save's name as the Load list shows it, e.g. claude_ger_1936")
    s = sub.add_parser("read")
    s.add_argument("what", choices=["research", "production", "date", "techs", "focus"])
    s.add_argument("--tab")
    s.add_argument("--grep")
    args = p.parse_args(argv)

    hwnd = hoi4.need_window()
    hoi4.focus(hwnd)
    if args.cmd not in ("load-save",):
        dismiss_notices(hwnd)
    if args.cmd == "dismiss":
        return
    if args.cmd == "research":
        if not args.dry_run and not args.replace:
            busy = read_research(hwnd)[args.slot - 1]
            if busy["tech"]:
                raise ActionError(f"slot {args.slot} is busy with {busy['tech']} ({busy['days']} days left); "
                                  "add --replace to swap it out")
        research(hwnd, args.slot, args.tech, args.mio, dry_run=args.dry_run)
    elif args.cmd == "production":
        if args.name:
            production_by_name(hwnd, args.name, args.add, args.remove)
        else:
            production(hwnd, args.line, args.add, args.remove)
    elif args.cmd == "open":
        open_screen(hwnd, args.screen)
        print(f"{args.screen} open")
    elif args.cmd == "close":
        close_screen(hwnd, args.screen)
        print(f"{args.screen} closed")
    elif args.cmd == "recruit":
        recruit(hwnd, args.count, args.template)
    elif args.cmd == "army":
        if args.op == "list":
            list_armies(hwnd)
        elif args.op == "new":
            new_army(hwnd, args.halves)
        elif args.op == "general":
            if not args.army:
                raise ActionError("--army N is needed")
            assign_general(hwnd, args.army, args.name)
            deselect(hwnd)
        elif args.op == "front":
            if not args.army or not args.at:
                raise ActionError("front needs --army N --at X Y")
            front_line(hwnd, args.army, args.at)
            deselect(hwnd)
        else:
            for i, p in enumerate(list_armies(hwnd, log=lambda m: None), 1):
                if not p["general"]:
                    assign_general(hwnd, i)
            deselect(hwnd)
    elif args.cmd == "select-box":
        print(select_box(hwnd, args.box))
    elif args.cmd == "focus":
        start_focus(hwnd, args.name)
    elif args.cmd == "fix-queue":
        open_screen(hwnd, "recruit")
        fix_queue(hwnd)
        names, counts = queue_summary(hwnd)
        close_screen(hwnd, "recruit")
        print(f"training-count fields seen: {sorted(set(counts))}")
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
    elif args.what == "focus":
        print(current_focus(hwnd) or "(no focus running)")
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

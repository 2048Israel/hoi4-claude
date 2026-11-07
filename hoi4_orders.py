"""Standing army orders: re-send an army at its target city when it has mostly stopped fighting.

A direct order ends when the path is blocked or the target is reached, and the army then sits and digs in (its
entrenchment rises while few of its divisions are in combat). Seen live in July 1940: three armies idle for weeks
while the front moved. `act army push` reads a fresh report and re-orders each army in the plan file whose share of
divisions in combat is under --min-share.

Plan file (plans/orders.txt): one order per line, `army general city`, e.g.  `5 Guderian Berlin`. The general is
a word of the commander's name, used to find the army in the report; the army is its card number (act army list).
"""
import time
from pathlib import Path

import hoi4
import hoi4_actions as A
from hoi4_actions import ActionError

ROOT = Path(__file__).resolve().parent
DEFAULT_PLAN = ROOT / "plans" / "orders.txt"


def read_plan(path):
    orders = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            raise ActionError(f"{path}:{n}: want 'army general city', got {line!r}")
        orders.append({"army": int(parts[0]), "general": parts[1], "city": " ".join(parts[2:])})
    return orders


def fresh_generals(hwnd, timeout=20.0):
    """The 'general' records of a report run now (the console's report effect)."""
    start = hoi4.log_size()
    recs, _ = hoi4.records(max(0, start - 2_000_000))
    hb = hoi4.last_kind(recs, "day")
    tag = hb.get("tag") if hb else None
    hoi4.run_console(hwnd, f"effect {tag} claude_bridge_report" if tag else "effect claude_bridge_report")
    deadline = time.time() + timeout
    while time.time() < deadline:
        block = hoi4.last_report(hoi4.records(start)[0])
        if block:
            return [r for r in block if r["kind"] == "general"]
        time.sleep(0.2)
    raise ActionError("no report came back from the console")


def find_general(generals, word):
    hits = [g for g in generals if word.lower() in str(g.get("name", "")).lower()]
    return hits[0] if hits else None


def stalled(general, min_share):
    units = float(general.get("units") or 0)
    combat = float(general.get("in_combat") or 0)
    return units > 0 and combat / units < min_share


def push(hwnd, plan=DEFAULT_PLAN, min_share=0.35, log=print):
    orders = read_plan(plan)
    generals = fresh_generals(hwnd)
    sent = 0
    for o in orders:
        g = find_general(generals, o["general"])
        if not g:
            log(f"army {o['army']}: no commander named like {o['general']!r} in the report; skipped")
            continue
        share = float(g.get("in_combat") or 0) / max(1.0, float(g.get("units") or 0))
        if not stalled(g, min_share):
            log(f"army {o['army']} ({g.get('name')}): {share:.0%} in combat, still pushing")
            continue
        A.target_city(hwnd, o["army"], o["city"], log=log)
        sent += 1
    log(f"{sent} army order(s) re-sent")
    return sent

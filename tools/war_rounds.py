r"""Play the war in rounds: advance N days, answer events that have a standing answer, close news, re-send stalled
armies (act army push), refill empty research slots, warn when no focus runs, and print a short war summary. Stops at once on an event with no standing answer, so a
real decision is never made blindly.

Usage: .venv\Scripts\python.exe tools\war_rounds.py --rounds 4 --days 5 [--save-every 2 --save-name ger_1940]
Standing answers: plans/event_answers.txt, one per line: `option | words of the event title`.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
ANSWERS = ROOT / "plans" / "event_answers.txt"


def run(*args, timeout=900):
    out = subprocess.run([PY, str(ROOT / "hoi4.py"), *args], capture_output=True, text=True, timeout=timeout,
                         encoding="utf-8", errors="replace")
    return (out.stdout + out.stderr).strip()


def standing_answers():
    rules = []
    if ANSWERS.exists():
        for line in ANSWERS.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "|" in line:
                opt, words = line.split("|", 1)
                rules.append((int(opt.strip()), words.strip().lower()))
    return rules


def answer_events(rules, limit=6):
    """Answer open events from the standing answers. Returns the title of an event left open, or None."""
    for _ in range(limit):
        title = run("read", "event").splitlines()[0].strip() if run("read", "event") else ""
        if not title or title.startswith("(no event"):
            return None
        hit = next((opt for opt, words in rules if words in title.lower()), None)
        if hit is None:
            return title
        print("  " + run("act", "event", "--option", str(hit)).splitlines()[-1])
    return None


FOCUS_PLAN = ROOT / "plans" / "focus_germany.txt"


def start_next_focus():
    """Start the first focus in plans/focus_germany.txt that the game accepts (done or locked ones are refused)."""
    if not FOCUS_PLAN.exists():
        return "none running, and no plans/focus_germany.txt"
    for line in FOCUS_PLAN.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip()
        if not name:
            continue
        out = run("act", "focus", "--name", name)
        if "started focus" in out:
            return out.splitlines()[-1]
    return "none running; nothing in plans/focus_germany.txt could start"


def summary():
    rep = run("report")
    keep = [l for l in rep.splitlines()
            if re.search(r"our surrender|enemy POL|enemy FRA|^Factories|^Political power", l)]
    return "\n".join("  " + l.strip() for l in keep)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--save-every", type=int, default=0)
    p.add_argument("--save-name", default="war")
    args = p.parse_args()
    rules = standing_answers()
    for i in range(1, args.rounds + 1):
        adv = run("advance", str(args.days)).splitlines()
        print(f"round {i}: " + next((l for l in adv if l.startswith("Now:")), adv[-1] if adv else "?"))
        run("act", "dismiss")  # notices (focus completed, research finished) sit on top of events: close them first
        left = answer_events(rules)
        if left:
            print(f"STOP: event with no standing answer: {left!r} (read event, then act event --option N)")
            return 2
        run("act", "dismiss")
        run("act", "camera", "home")
        push = run("act", "army", "push").splitlines()
        print("  " + (push[-1] if push else "push: no output"))
        print(summary())
        # idle research and an empty focus slot cost the most when nobody looks: check them every round
        research = run("read", "research")
        if "(empty)" in research:
            filled = [l for l in run("act", "research-fill").splitlines() if l.startswith("slot")]
            print("  research: " + ("; ".join(filled) if filled else "empty slots, nothing in the plan could start"))
        if "no focus running" in run("read", "focus"):
            print("  focus: " + start_next_focus())
        if args.save_every and i % args.save_every == 0:
            print("  " + run("act", "save", f"{args.save_name}_r{i}").splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())

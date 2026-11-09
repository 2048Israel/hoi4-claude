r"""The focus planner: which national focuses can start now, read from the game's own focus files.

The Policy agent (docs/command.md) is given this list instead of a guessed one (plans/focus_germany.txt ran out in
the 1939 replay). Standard library only, and no import of hoi4.py, so it runs and tests on any machine.

  python hoi4_focus.py --save claude_ger_1939_11_stop.hoi4             # tree found in the game and enabled mods
  python hoi4_focus.py --tree germany.txt --completed GER_a,GER_b --current GER_c
  python hoi4_focus.py --save <save> --json                            # for an agent

Rules, from the game's focus files (`common/national_focus/*.txt`):
- `prerequisite = { focus = A focus = B }`: one block needs any one of them; several blocks are all needed.
- `mutually_exclusive = { focus = X }`: X locks this focus once X is done or running (either side may declare it).
- `cost` is in weeks: one point is 7 days (before focus-speed bonuses).
- `available` and `bypass` are game conditions. The few that can be decided from the save are decided (focuses done,
  `always`, the tag, the ruling ideology); the rest are kept as short text for the agent to read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV")
USER_DIR = Path.home() / "Documents" / "Paradox Interactive" / "Hearts of Iron IV"
FOCUS_DIR = "common/national_focus"
DAYS_PER_COST = 7
DEFAULT_COST = 10  # the game's cost when a focus has none
TEXT_LIMIT = 240   # trigger text longer than this is cut


class FocusError(Exception):
    """A file that cannot be read as asked: a binary or compressed save, no focus tree, no such country."""


# ---------------------------------------------------------------- Clausewitz script (focus files, saves, .mod files)

class Block(list):
    """One `{ ... }` block. Entries keep their order and repeats: `(key, op, value)` for `key = value`,
    `(None, None, value)` for a bare value in a list. A value is a str or another Block."""

    def get(self, key, default=None):
        for k, _op, v in self:
            if k == key:
                return v
        return default

    def all(self, key):
        return [v for k, _op, v in self if k == key]

    def blocks(self, key):
        return [v for k, _op, v in self if k == key and isinstance(v, Block)]


_TOKEN = re.compile(r'"(?:[^"\\\n]|\\.)*"|[{}]|[<>!?]?=|[<>]|#[^\n]*|[^\s{}=<>!?"#]+')
_OPS = {"=", "<", ">", "<=", ">=", "!=", "?="}


def tokenize(text):
    """Tokens of Clausewitz script with comments dropped: words, quoted strings (quotes kept), `{`, `}`, operators.
    A `\r` (saves mix CRLF and LF) is plain whitespace."""
    return [t for t in _TOKEN.findall(text) if t[0] != "#"]


def _unquote(tok):
    return tok[1:-1] if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"' else tok


def parse(text):
    """Parse script into a Block. Lenient: a stray `}` at the top is ignored, unclosed blocks end with the text."""
    toks = tokenize(text)
    root = Block()
    stack = [root]
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t == "}":
            if len(stack) > 1:
                stack.pop()
            i += 1
        elif t == "{":
            new = Block()
            stack[-1].append((None, None, new))
            stack.append(new)
            i += 1
        elif t in _OPS:
            i += 1  # an operator with no key: skip it
        elif i + 1 < n and toks[i + 1] in _OPS:
            key, op = _unquote(t), toks[i + 1]
            v = toks[i + 2] if i + 2 < n else ""
            if v == "{":
                new = Block()
                stack[-1].append((key, op, new))
                stack.append(new)
                i += 3
            elif v in _OPS or v == "}" or v == "":
                stack[-1].append((key, op, ""))
                i += 2
            else:
                stack[-1].append((key, op, _unquote(v)))
                i += 3
        else:
            stack[-1].append((None, None, _unquote(t)))
            i += 1
    return root


def read_text(path):
    """A game text file as str: UTF-8 with or without BOM; bytes that are not UTF-8 are replaced, not fatal."""
    return Path(path).read_bytes().decode("utf-8-sig", errors="replace")


# ---------------------------------------------------------------- triggers: short text, and the few we can decide

def trigger_text(block, limit=TEXT_LIMIT):
    """A trigger block as one short line, e.g. `has_war = no, NOT { has_government = communism }`."""
    if not isinstance(block, Block):
        return str(block or "")

    def render(b):
        parts = []
        for k, op, v in b:
            if isinstance(v, Block):
                inner = render(v)
                parts.append(f"{k} {{ {inner} }}" if k else f"{{ {inner} }}")
            elif k is None:
                parts.append(v)
            else:
                parts.append(f"{k} {op} {v}")
        return ", ".join(parts)

    s = render(block)
    return s if len(s) <= limit else s[:limit - 3].rstrip() + "..."


def check(block, facts):
    """Decide a trigger block: True, False, or None when it asks something only the game knows.

    `facts`: {"completed": set of focus ids, "tag": "GER", "ideology": "fascism" or None, "dlcs": set of DLC
    names or None, "rules": {game rule: option} or None}. Entries are ANDed; `NOT = { A B }` is true when none of
    A, B is (the game's NOR); `if`/`else_if`/`else` pass when their branch is not taken."""
    results = []
    chain = None  # if/else_if chain: "taken", "open" (no branch taken yet), "unknown"
    for k, op, v in block:
        if k in ("if", "else_if", "else") and isinstance(v, Block):
            if k != "if" and chain in ("taken", "unknown"):
                results.append(True if chain == "taken" else None)
                continue
            rest = Block(e for e in v if e[0] != "limit")
            lim = v.get("limit")
            lim = check(lim, facts) if k != "else" and isinstance(lim, Block) else True
            if lim is True:
                results.append(check(rest, facts))
                chain = "taken"
            elif lim is False:
                results.append(True)
                chain = "open"
            else:
                results.append(None)
                chain = "unknown"
            continue
        chain = None
        results.append(_check_one(k, op, v, facts))
    if False in results:
        return False
    return None if None in results else True


def _any(block, facts):
    results = [_check_one(k, op, v, facts) for k, op, v in block]
    if True in results:
        return True
    return None if None in results else False


def _check_one(k, op, v, facts):
    if k is None or op != "=":
        return None
    if isinstance(v, Block):
        if k == "AND":
            return check(v, facts)
        if k == "OR":
            return _any(v, facts)
        if k == "NOT":
            r = _any(v, facts)
            return None if r is None else not r
        if k == "custom_trigger_tooltip":
            return check(Block(e for e in v if e[0] != "tooltip"), facts)
        if k == "has_game_rule" and facts.get("rules") is not None:
            rule, option = v.get("rule"), v.get("option")
            if rule in facts["rules"] and option:
                return facts["rules"][rule].lower() == option.lower()
        return None
    if k == "always":
        return v == "yes"
    if k == "has_completed_focus":
        return v in facts.get("completed", ())
    if k in ("tag", "original_tag") and facts.get("tag"):
        return v == facts["tag"]
    if k == "has_government" and facts.get("ideology"):
        return v == facts["ideology"]
    if k == "has_dlc" and facts.get("dlcs") is not None:
        return v in facts["dlcs"]
    return None


def owned_dlcs(game_dir=GAME_DIR, user_dir=USER_DIR):
    """The DLC names the game can load: every `dlc/*/*.dlc` with its `name`, minus `disabled_dlcs` in
    `dlc_load.json`. Steam installs only owned DLC, so a folder with no .dlc file is not counted.
    None when there is no dlc folder (another machine): has_dlc is then left to the game."""
    base = Path(game_dir) / "dlc"
    if not base.is_dir():
        return None
    disabled = set()
    cfg = Path(user_dir) / "dlc_load.json"
    if cfg.exists():
        disabled = {str(d).replace("\\", "/") for d in json.loads(read_text(cfg)).get("disabled_dlcs", [])}
    names = set()
    for f in sorted(base.glob("*/*.dlc")):
        name = parse(read_text(f)).get("name")
        rel = f.relative_to(Path(game_dir)).as_posix()
        if name and name not in disabled and rel not in disabled and f.parent.name not in disabled:
            names.add(name)
    return names


def game_rule_defaults(game_dir=GAME_DIR):
    """{rule: default option} from the game's `common/game_rules/*.txt`; None when the folder is not there."""
    base = Path(game_dir) / "common" / "game_rules"
    if not base.is_dir():
        return None
    rules = {}
    for f in sorted(base.glob("*.txt")):
        for k, _op, v in parse(read_text(f)):
            if isinstance(k, str) and isinstance(v, Block):
                d = v.get("default")
                if isinstance(d, Block) and d.get("name"):
                    rules[k] = d.get("name")
    return rules


# ---------------------------------------------------------------- focus trees

def _number(raw, variables):
    raw = variables.get(raw, raw) if raw.startswith("@") else raw
    try:
        return float(raw)
    except ValueError:
        return None


def _focus(block, variables, file, line):
    fid = block.get("id")
    raw = block.get("cost", str(DEFAULT_COST))
    cost = _number(raw, variables) if isinstance(raw, str) else None
    prereq = [[f for f in b.all("focus")] for b in block.blocks("prerequisite")]
    excl = [f for b in block.blocks("mutually_exclusive") for f in b.all("focus")]
    out = {
        "id": fid,
        "cost": cost,
        "days": None if cost is None else round(cost * DAYS_PER_COST),
        "prerequisites": [p for p in prereq if p],
        "mutually_exclusive": excl,
        "available": trigger_text(block.get("available")),
        "bypass": trigger_text(block.get("bypass")),
        "allow_branch": trigger_text(block.get("allow_branch")),
        "will_lead_to_war_with": block.all("will_lead_to_war_with"),
        "x": block.get("x"), "y": block.get("y"),
        "relative_position_id": block.get("relative_position_id"),
        "file": str(file), "line": line,
        "_available": block.get("available"),
        "_allow_branch": block.get("allow_branch"),
    }
    if cost is None:
        out["cost_text"] = raw if isinstance(raw, str) else trigger_text(raw)
    return out


def tree_score(tree_block, tag):
    """How strongly a `focus_tree` claims a country: its `country` factor, plus `add` and times `factor` of every
    modifier that names this tag. Modifiers with no tag condition are left out: the planner cannot test them."""
    c = tree_block.get("country")
    if not isinstance(c, Block):
        return 0.0
    score = _number(str(c.get("factor", "0")), {}) or 0.0
    for mod in c.blocks("modifier"):
        tags = [v for k, _op, v in mod if k in ("tag", "original_tag") and isinstance(v, str)]
        if not tags or any(t != tag for t in tags):
            continue
        add = _number(str(mod.get("add", "0")), {}) or 0.0
        factor = _number(str(mod.get("factor", "1")), {})
        score = (score + add) * (1.0 if factor is None else factor)
    return score


def _line_of(text, needle_pos):
    return text.count("\n", 0, needle_pos) + 1 if needle_pos >= 0 else None


def load_tree(path, tag=None, shared=None):
    """Read one focus tree file. With several `focus_tree` blocks in it, the one that claims `tag` most is taken.
    `shared`: {id: focus block} of `shared_focus` blocks from other files, for trees that include them."""
    path = Path(path)
    text = read_text(path)
    root = parse(text)
    variables = {k: v for k, _op, v in root if isinstance(k, str) and k.startswith("@") and isinstance(v, str)}
    trees = root.blocks("focus_tree")
    if not trees:
        raise FocusError(f"{path}: no focus_tree block")
    block = max(trees, key=lambda t: tree_score(t, tag)) if tag and len(trees) > 1 else trees[0]

    # The line of each focus, found by its `id = X` (cheap; only used to point at the source).
    lines = {m.group(1): _line_of(text, m.start()) for m in re.finditer(r"\bid\s*=\s*\"?([A-Za-z0-9_.\-]+)", text)}
    focuses = {}
    for fb in block.blocks("focus"):
        f = _focus(fb, variables, path, lines.get(fb.get("id")))
        if f["id"]:
            focuses[f["id"]] = f

    shared_ids = block.all("shared_focus")
    pool = dict(shared or {})
    pool.update({b.get("id"): b for b in root.blocks("shared_focus") if b.get("id")})
    missing = []
    if shared_ids:
        # A shared focus brings itself and every shared focus that follows from it.
        want = [s for s in shared_ids if isinstance(s, str)]
        missing = [s for s in want if s not in pool]
        added = {s for s in want if s in pool}
        grew = True
        while grew:
            grew = False
            for sid, sb in pool.items():
                if sid in added:
                    continue
                needs = {f for b in sb.blocks("prerequisite") for f in b.all("focus")}
                if needs & added:
                    added.add(sid)
                    grew = True
        for sid in added:
            focuses.setdefault(sid, _focus(pool[sid], variables, path, lines.get(sid)))
    return {
        "id": block.get("id"),
        "file": str(path),
        "score": tree_score(block, tag) if tag else None,
        "default": block.get("default") == "yes",
        "focuses": focuses,
        "shared_missing": missing,
    }


# ---------------------------------------------------------------- where the tree comes from: the game and its mods

def enabled_mods(user_dir=USER_DIR):
    """The enabled mods in load order, from `dlc_load.json` and each `.mod` descriptor:
    [{"name", "descriptor", "path", "replace_path": [...], "exists": bool}]."""
    user_dir = Path(user_dir)
    cfg = user_dir / "dlc_load.json"
    if not cfg.exists():
        return []
    mods = []
    for rel in json.loads(read_text(cfg)).get("enabled_mods", []):
        desc = user_dir / rel
        info = {"name": rel, "descriptor": str(desc), "path": None, "replace_path": [], "exists": False}
        if desc.exists():
            d = parse(read_text(desc))
            info["name"] = d.get("name") or rel
            raw = d.get("path") or d.get("archive")
            if raw:
                p = Path(raw)
                p = p if p.is_absolute() else user_dir / p
                info["path"] = str(p)
                info["exists"] = p.is_dir()
            info["replace_path"] = [v.replace("\\", "/").strip("/") for v in d.all("replace_path")]
        mods.append(info)
    return mods


def focus_files(game_dir=GAME_DIR, mods=()):
    """{file name: (path, source)} after mods: a mod file with the same name replaces the game's, and a mod with
    `replace_path = "common/national_focus"` drops every file loaded before it."""
    files = {}
    base = Path(game_dir) / FOCUS_DIR
    for p in sorted(base.glob("*.txt")) if base.is_dir() else []:
        files[p.name] = (p, "game")
    for m in mods:
        if not m.get("exists"):
            continue
        if FOCUS_DIR in m.get("replace_path", []):
            files = {}
        d = Path(m["path"]) / FOCUS_DIR
        for p in sorted(d.glob("*.txt")) if d.is_dir() else []:
            files[p.name] = (p, m["name"])
    return files


def find_tree(tag="GER", game_dir=GAME_DIR, user_dir=USER_DIR):
    """Find the focus tree the game gives `tag`, across the game and the enabled mods.
    Returns (tree, report). The report says which file won and why, and which mods carry focus files."""
    mods = enabled_mods(user_dir)
    files = focus_files(game_dir, mods)
    if not files:
        raise FocusError(f"no focus files under {Path(game_dir) / FOCUS_DIR} or the enabled mods")
    word = re.compile(rf"\b{re.escape(tag)}\b")
    shared, candidates, default = {}, [], None
    for name, (path, source) in files.items():
        text = read_text(path)
        has_tag = bool(word.search(text))
        if not has_tag and "default" not in text and "shared_focus" not in text:
            continue
        root = parse(text)
        for sb in root.blocks("shared_focus"):
            if sb.get("id"):
                shared[sb.get("id")] = sb
        for tb in root.blocks("focus_tree"):
            score = tree_score(tb, tag) if has_tag else 0.0
            entry = {"file": str(path), "source": source, "tree_id": tb.get("id"), "score": score}
            if score > 0:
                candidates.append(entry)
            if tb.get("default") == "yes" and default is None:
                default = entry
    candidates.sort(key=lambda e: e["score"], reverse=True)
    won = candidates[0] if candidates else default
    if won is None:
        raise FocusError(f"no focus tree claims {tag}, and there is no default tree")
    tree = load_tree(won["file"], tag, shared)
    mod_focus = [m["name"] for m in mods if m.get("exists") and (Path(m["path"]) / FOCUS_DIR).is_dir()]
    report = {
        "tag": tag,
        "won": won,
        "why": ("highest country score for " + tag) if candidates else "no tree names " + tag + ": the default tree",
        "others": candidates[1:],
        "mods_enabled": [m["name"] for m in mods],
        "mods_with_focus_files": mod_focus,
        "mods_missing": [m["name"] for m in mods if not m.get("exists")],
    }
    return tree, report


# ---------------------------------------------------------------- display names

_LOC_LINE = re.compile(r'^\s*([^\s:#"]+):\d*\s*"(.*)"')
_LOC_REF = re.compile(r"\$([A-Za-z0-9_.\-]+)\$")


def localisation_dirs(game_dir=GAME_DIR, mods=()):
    """The localisation folders in load order: the game's, then each enabled mod's."""
    dirs = [Path(game_dir) / "localisation"]
    for m in mods:
        if m.get("exists") and (Path(m["path"]) / "localisation").is_dir():
            dirs.append(Path(m["path"]) / "localisation")
    return [d for d in dirs if d.is_dir()]


def load_names(dirs, keys, language="english"):
    """{key: display name} for `keys` from every `*_l_<language>.yml` under `dirs` (one level of `$KEY$` is
    resolved). Later folders win, and files in a `replace` folder win over the rest."""
    keys = set(keys)
    table = {}
    files = []
    for d in dirs:
        found = sorted(Path(d).rglob(f"*_l_{language}.yml"))
        files += [f for f in found if "replace" not in f.parts] + [f for f in found if "replace" in f.parts]
    for f in files:
        for line in read_text(f).splitlines():
            m = _LOC_LINE.match(line)
            if m:
                table[m.group(1)] = m.group(2).rstrip().rstrip('"') if m.group(2).endswith('"') else m.group(2)
    names = {}
    for k in keys:
        v = table.get(k)
        if v is not None:
            names[k] = _LOC_REF.sub(lambda m: table.get(m.group(1), m.group(0)), v)
    return names


# ---------------------------------------------------------------- the save: what is done and what is running

def read_save_focus(path, tag=None):
    """Read `countries.<tag>.focus` from a text save: {"tag", "date", "ideology", "completed": [...],
    "current", "progress", "paused"}. `tag` defaults to the save's player."""
    data = Path(path).read_bytes()
    head = data[:16]
    if head.startswith(b"HOI4bin"):
        raise FocusError(f"{path} is a binary save. Set save_as_binary=no in the game's settings.txt (see "
                         "docs/queue/SR0.md) and save again.")
    if head.startswith(b"PK"):
        raise FocusError(f"{path} is a compressed save: turn off save compression in the game and save again.")
    if not head.startswith(b"HOI4txt"):
        raise FocusError(f"{path} is not a HOI4 text save (no HOI4txt header)")
    header = data[:4096].decode("utf-8", errors="replace")

    def head_value(key):
        m = re.search(rf"^{key}=\"?([^\"\r\n]*)\"?", header, re.M)
        return m.group(1) if m else None

    player = head_value("player")
    tag = tag or player
    if not tag:
        raise FocusError(f"{path}: no player in the header; give --tag")
    # The save is written with one tab per level: countries={ / <tab>GER={ / <tab><tab>focus={ ... <tab><tab>}.
    start = data.find(b"\ncountries={")
    if start < 0:
        raise FocusError(f"{path}: no countries block")
    t = data.find(b"\n\t" + tag.encode() + b"={", start)
    if t < 0:
        raise FocusError(f"{path}: no country {tag}")
    t_end = data.find(b"\n\t}", t + 1)
    t_end = len(data) if t_end < 0 else t_end
    f = data.find(b"\n\t\tfocus={", t, t_end)
    out = {"tag": tag, "date": head_value("date"), "ideology": head_value("ideology") if tag == player else None,
           "completed": [], "current": None, "progress": None, "paused": None, "game_rules": {}}
    # Game rules changed from their defaults: a top-level game_rules={ ... } before the countries.
    g = data.find(b"\ngame_rules={", 0, start)
    if g >= 0:
        g_end = data.find(b"\n}", g + 1, start)
        rules = parse(data[g:g_end + 2].decode("utf-8", errors="replace")).get("game_rules")
        for k, _op, v in rules if isinstance(rules, Block) else []:
            option = v if isinstance(v, str) else (v.get("option") or v.get("name"))
            if isinstance(k, str) and isinstance(option, str):
                out["game_rules"][k] = option
    if f < 0:
        return out  # a country that never took a focus
    f_end = data.find(b"\n\t\t}", f + 1, t_end)
    block = parse(data[f:(t_end if f_end < 0 else f_end) + 4].decode("utf-8", errors="replace")).get("focus")
    if isinstance(block, Block):
        out["completed"] = [v for v in block.all("completed") if isinstance(v, str)]
        out["current"] = block.get("current")
        p = block.get("progress")
        out["progress"] = _number(p, {}) if isinstance(p, str) else None
        out["paused"] = block.get("paused")
    return out


# ---------------------------------------------------------------- the planner

def exclusions(tree):
    """{focus: set of focuses it locks out}, both ways (the files often declare it on one side only)."""
    ex = {fid: set() for fid in tree["focuses"]}
    for fid, f in tree["focuses"].items():
        for other in f["mutually_exclusive"]:
            ex.setdefault(fid, set()).add(other)
            ex.setdefault(other, set()).add(fid)
    return ex


def _facts(completed, facts):
    out = dict(facts or {})
    out["completed"] = set(completed)
    return out


def why_not(tree, fid, completed, current=None, facts=None, ex=None):
    """Why a focus cannot start now, or None if it can as far as the files and the save tell. In this order:
    completed, running, locked out by a completed or running focus, a missing prerequisite, its branch hidden
    (`allow_branch` false), an `available` the save answers as false."""
    f = tree["focuses"][fid]
    facts = facts if isinstance(facts, dict) and "completed" in facts else _facts(completed, facts)
    done = facts["completed"]
    ex = exclusions(tree) if ex is None else ex
    if fid in done:
        return "completed"
    if fid == current:
        return "running"
    lock = sorted((ex.get(fid, set()) & done) | ({current} & ex.get(fid, set())))
    if lock:
        return "excluded by " + ", ".join(lock)
    for group in f["prerequisites"]:
        if not done.intersection(group):
            return "needs " + " or ".join(group)
    ab = f.get("_allow_branch")
    if isinstance(ab, Block) and check(ab, facts) is False:
        return "branch hidden: " + f["allow_branch"]
    av = f.get("_available")
    if isinstance(av, Block) and check(av, facts) is False:
        return "not available: " + f["available"]
    return None


def _ready_ids(tree, facts, current, ex):
    return [fid for fid in tree["focuses"] if why_not(tree, fid, None, current, facts, ex) is None]


def startable(tree, completed, current=None, facts=None, names=None):
    """The focuses that can start now: prerequisites met, not completed, not running, not locked out by a
    completed or running focus, and not ruled out by an `allow_branch` or `available` the save answers.
    Each as {"id", "name", "cost", "days", "available", "available_ok" (True, or None = the game decides),
    "bypass", "will_lead_to_war_with", "prerequisites", "opens"}, in the order of the file. `opens` lists the
    focuses that become startable once this one is done."""
    facts = _facts(completed, facts)
    ex = exclusions(tree)
    names = names or {}
    ready = _ready_ids(tree, facts, current, ex)
    now = set(ready)
    out = []
    for fid in ready:
        f = tree["focuses"][fid]
        av = f.get("_available")
        ok = check(av, facts) if isinstance(av, Block) and len(av) else True
        after = _facts(facts["completed"] | {fid}, facts)
        opens = [o for o in _ready_ids(tree, after, current, ex) if o not in now]
        out.append({
            "id": fid, "name": names.get(fid, fid), "cost": f["cost"], "days": f["days"],
            "available": f["available"], "available_ok": ok, "bypass": f["bypass"],
            "will_lead_to_war_with": f["will_lead_to_war_with"], "prerequisites": f["prerequisites"],
            "opens": opens,
        })
    return out


def blocked(tree, completed, current=None, facts=None):
    """Focuses whose prerequisites are all met but which the save already rules out: their `allow_branch` or
    `available` is false (a DLC not owned, a focus that must not be done, the wrong government). {id: reason}."""
    facts = _facts(completed, facts)
    ex = exclusions(tree)
    out = {}
    for fid in tree["focuses"]:
        why = why_not(tree, fid, None, current, facts, ex)
        if why and (why.startswith("branch hidden") or why.startswith("not available")):
            out[fid] = why
    return out


def unknown_ids(tree, ids):
    """Ids that are not in the tree: a typo, or a save from another tree or mod set."""
    return [i for i in ids if i not in tree["focuses"]]


# ---------------------------------------------------------------- CLI

def _cut(s, n):
    return s if len(s) <= n else s[:n - 3].rstrip() + "..."


def plan(args):
    """Everything the CLI prints, as one dict (the --json output)."""
    state = {"tag": args.tag, "date": None, "ideology": args.ideology, "completed": [], "current": None,
             "progress": None, "game_rules": {}}
    if args.save:
        got = read_save_focus(args.save, args.tag)
        state.update({k: v for k, v in got.items() if v is not None or k not in ("ideology",)})
        state["ideology"] = args.ideology or got.get("ideology")
    state["tag"] = state["tag"] or "GER"
    state["completed"] = state["completed"] + [c.strip() for c in args.completed.split(",") if c.strip()]
    state["current"] = args.current or state["current"]

    if args.tree:
        tree = load_tree(args.tree, state["tag"])
        report = {"tag": state["tag"], "won": {"file": args.tree, "source": "--tree"}, "why": "given with --tree"}
        mods = enabled_mods(args.user_dir) if Path(args.user_dir).is_dir() else []
    else:
        tree, report = find_tree(state["tag"], args.game_dir, args.user_dir)
        mods = enabled_mods(args.user_dir)
    names = {}
    if not args.no_names:
        dirs = [Path(d) for d in args.loc] if args.loc else localisation_dirs(args.game_dir, mods)
        names = load_names(dirs, tree["focuses"].keys())

    dlcs = None if args.dlc_unknown else owned_dlcs(args.game_dir, args.user_dir)
    rules = game_rule_defaults(args.game_dir)
    if rules is not None:
        rules.update(state["game_rules"])
    facts = {"tag": state["tag"], "ideology": state["ideology"], "dlcs": dlcs, "rules": rules}
    cur = state["current"]
    return {
        "tree": report, "tag": state["tag"], "date": state["date"],
        "facts": {"ideology": state["ideology"], "dlcs": sorted(dlcs) if dlcs is not None else None,
                  "game_rules_changed": state["game_rules"]},
        "completed": state["completed"], "current": cur, "current_name": names.get(cur, cur) if cur else None,
        "progress": state["progress"],
        "startable": startable(tree, state["completed"], cur, facts, names),
        "ruled_out": [{"id": k, "name": names.get(k, k), "why": v}
                      for k, v in blocked(tree, state["completed"], cur, facts).items()],
        "unknown_ids": unknown_ids(tree, state["completed"] + ([cur] if cur else [])),
        "_names": names,
    }


def print_plan(p, width=110):
    won = p["tree"]["won"]
    names = p["_names"]
    print(f"Tree: {won['file']} ({won['source']}; {p['tree']['why']})")
    if p["tree"].get("mods_with_focus_files"):
        print("  mods with focus files: " + ", ".join(p["tree"]["mods_with_focus_files"]))
    cur = p["current"]
    running = f"{cur} \"{p['current_name']}\"" if cur else "none"
    print(f"{p['tag']}{' on ' + p['date'] if p['date'] else ''}: {len(p['completed'])} completed, running: {running}")
    if p["unknown_ids"]:
        print("  not in this tree: " + ", ".join(p["unknown_ids"]))
    print(f"Can start now ({len(p['startable'])}); 'needs' = a condition only the game can check:")
    for f in p["startable"]:
        days = "?" if f["days"] is None else f"{f['days']} days"
        print(f"  {f['id']}  \"{f['name']}\"  {days}")
        if f["available"] and f["available_ok"] is None:
            print("      needs: " + _cut(f["available"], width))
        if f["will_lead_to_war_with"]:
            print("      war with: " + ", ".join(f["will_lead_to_war_with"]))
        if f["bypass"]:
            print("      bypassed if: " + _cut(f["bypass"], width))
        if f["opens"]:
            print("      opens: " + _cut(", ".join(names.get(o, o) for o in f["opens"]), width))
    if p["ruled_out"]:
        print(f"Prerequisites met, but the save rules them out ({len(p['ruled_out'])}):")
        for r in p["ruled_out"]:
            print(f"  {r['id']}  \"{r['name']}\": " + _cut(r["why"], width))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Which national focuses can start now, from the game's focus files.")
    ap.add_argument("--tree", help="a focus tree file; default: the one the game gives --tag (game + enabled mods)")
    ap.add_argument("--tag", help="country tag; default: the save's player, or GER")
    ap.add_argument("--save", help="a text save: read completed and current from countries.<tag>.focus")
    ap.add_argument("--completed", default="", help="comma-separated focus ids already done")
    ap.add_argument("--current", help="the focus running now")
    ap.add_argument("--ideology", help="ruling ideology, to decide has_government (from the save if given)")
    ap.add_argument("--game-dir", default=str(GAME_DIR))
    ap.add_argument("--user-dir", default=str(USER_DIR), help="the Documents folder with dlc_load.json and mod/")
    ap.add_argument("--loc", action="append", help="a localisation folder (repeatable); default: game + mods")
    ap.add_argument("--no-names", action="store_true", help="skip display names (faster)")
    ap.add_argument("--dlc-unknown", action="store_true", help="do not decide has_dlc from the dlc folder")
    ap.add_argument("--json", action="store_true", help="print JSON for an agent")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        p = plan(a)
    except (FocusError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({k: v for k, v in p.items() if not k.startswith("_")}, ensure_ascii=False, indent=1))
    else:
        print_plan(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())

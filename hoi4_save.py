"""SR1: read an HOI4 text save (Clausewitz script) into compact JSON for one country.

    python hoi4_save.py <save> [--tag GER]           the player's state: research, production, construction,
                                                      divisions and armies, focus, political power, stability ...
    python hoi4_save.py <save> --units POL,SOV        also those countries' divisions (location, strength)
    python hoi4_save.py <save> --raw countries.GER.focus   one block of the save as JSON, for exploring
    python hoi4_save.py <save> --timing               how long each step took, on stderr

Standard library only, and no import of hoi4.py, so it runs and tests on any machine. Saves are only read.

Days left on research and state names need the game's own files: by default the Steam folder plus the mods enabled
in dlc_load.json, read-only (`--game-dir`, `--user-dir`, `--no-game`). Without them those fields are null.

The parser is general (the game's script files use the same syntax):
    parse(data, spec=None) -> Block        data is bytes or str
A Block is a dict from key to the list of every value given for that key, in file order (keys repeat in saves),
plus `.bare` for values without a key (`{ 5 42 50 }`, or anonymous `{ ... }` blocks inside lists).
`spec` says which blocks to build: None or True = everything; a dict = only the keys it names (`"*"` for any other
key), with the spec for that key's block as the value; SPAN = do not parse, just give the block's Span(start, end).
Blocks it does not name are skipped by matching braces only, which is several times faster than tokenizing them.
Plain `key=value` pairs are always kept.
"""
import argparse
import json
import math
import re
import sys
import time
from collections import namedtuple
from pathlib import Path

__all__ = ["Block", "Cmp", "Span", "SPAN", "Once", "SaveFormatError", "GameData", "parse", "parse_file", "read_save",
           "skip_block", "plain_braces", "extract", "raw", "leader_name", "research_eta", "enabled_mods"]

TEXT_MAGIC = b"HOI4txt"
BINARY_MAGIC = b"HOI4bin"
BINARY_HELP = ("binary save (starts with HOI4bin): this reader needs text saves. Set save_as_binary=no in "
               "Documents/Paradox Interactive/Hearts of Iron IV/settings.txt, then save again (docs/queue/SR0.md)")
DEFAULT_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV")
DEFAULT_USER_DIR = Path.home() / "Documents" / "Paradox Interactive" / "Hearts of Iron IV"


class SaveFormatError(ValueError):
    """The file is not an HOI4 text save, or its braces do not balance."""


# --------------------------------------------------------------------------------------------- the parser

class Block(dict):
    """A `{ ... }` block: key -> [every value for that key, in file order]; `.bare` holds values without a key."""
    __slots__ = ("bare",)

    def __init__(self):
        super().__init__()
        self.bare = []

    def one(self, key, default=None):
        """The first value given for key."""
        vals = dict.get(self, key)
        return vals[0] if vals else default

    def last(self, key, default=None):
        """The last value given for key."""
        vals = dict.get(self, key)
        return vals[-1] if vals else default

    def all(self, key):
        """Every value given for key, in file order ([] if none)."""
        return dict.get(self, key, [])

    def path(self, *keys, default=None):
        """Follow keys down through first values: b.path("technology", "slots")."""
        cur = self
        for k in keys:
            if not isinstance(cur, Block):
                return default
            cur = cur.one(k)
            if cur is None:
                return default
        return cur

    def to_py(self):
        """Plain dicts and lists for json.dumps: a key given once maps to its value, a repeated key to a list.
        Bare values become a list (or the "_" key of a block that also has keys)."""
        out = {}
        for k, vals in self.items():
            conv = [_to_py(v) for v in vals]
            out[k] = conv[0] if len(conv) == 1 else conv
        if self.bare:
            bare = [_to_py(v) for v in self.bare]
            if not out:
                return bare
            out["_"] = bare
        return out

    def __repr__(self):
        return f"Block({dict.__repr__(self)}, bare={self.bare!r})" if self.bare else f"Block({dict.__repr__(self)})"


Cmp = namedtuple("Cmp", "op value")
Cmp.__doc__ = "A value written with a comparison (`size > 5`), as in the game's script files. Saves use only `=`."
Span = namedtuple("Span", "start end")
Span.__doc__ = "Where a block's contents are: data[start:end], between its braces."


class _Marker:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


SPAN = _Marker("SPAN")
_SKIPPED = _Marker("SKIPPED")


def _to_py(v):
    if isinstance(v, Block):
        return v.to_py()
    if isinstance(v, Cmp):
        return {"op": v.op, "value": _to_py(v.value)}
    if isinstance(v, Span):
        return {"span": [v.start, v.end]}
    return v


# One token, after any whitespace (\r included: saves mix LF and CRLF) and # comments.
# Groups: 1 quoted string body, 2 number, 3 operator, 4 other word, 5 "{", 6 "}".
_TOKEN = re.compile(
    rb'(?:\s+|#[^\n]*)*'
    rb'(?:"((?:[^"\\]|\\.)*)"'
    rb'|(-?\d+(?:\.\d+)?)(?![^\s{}=<>!?#"])'
    rb'|([<>!?]?=|[<>])'
    rb'|((?:[^\s{}=<>!?#"]|[!?](?!=))+)'
    rb'|(\{)|(\}))')
_STRING, _NUMBER, _OP, _WORD, _OPEN, _CLOSE = 1, 2, 3, 4, 5, 6
_ESC = re.compile(r'\\(.)')


def _pair(pattern):
    """The same regex for bytes and for str."""
    return re.compile(pattern), re.compile(pattern.decode())


_RE = {name: _pair(p) for name, p in {
    "token": _TOKEN.pattern,
    "braces": rb'(\{)|\}',
    "special": rb'[{}"#]',
    "string": rb'"(?:[^"\\]|\\.)*"',
    "comment": rb'#[^\n]*',
}.items()}


def _re(name, data):
    return _RE[name][0 if isinstance(data, (bytes, bytearray)) else 1]


def plain_braces(data, start=0, end=None):
    """True when braces alone show the structure of data[start:end]: no '#' and no brace inside a quoted string.
    Then blocks can be skipped by counting braces, the fastest way (one C-speed pass to check)."""
    if end is None:
        end = len(data)
    is_bytes = isinstance(data, (bytes, bytearray))
    hash_, quote, braces = (b"#", b'"', (b"{", b"}")) if is_bytes else ("#", '"', ("{", "}"))
    if data.find(hash_, start, end) != -1:
        return False
    joined = (b"" if is_bytes else "").join(_re("string", data).findall(data, start, end))
    if joined.count(quote) != data.count(quote, start, end):
        return False                            # a string left open in the stretch: its braces may count
    return not any(c in joined for c in braces)


def skip_block(data, pos, plain=None):
    """data[pos] is just after an opening '{': return the index just after its matching '}'.
    plain=True: count braces only (the caller knows plain_braces holds). plain=False: step over strings and #
    comments, brace by brace. None: count braces, then check the skipped stretch with plain_braces and do it the
    exact way only if a string or comment there could hide a brace (same answer as False, much faster)."""
    if plain is not False:
        depth = 1
        for m in _re("braces", data).finditer(data, pos):
            if m.lastindex:
                depth += 1
            else:
                depth -= 1
                if not depth:
                    e = m.end()
                    if plain or plain_braces(data, pos, e):
                        return e
                    break
        if plain:
            raise SaveFormatError(f"unclosed '{{' opened before offset {pos}")
    depth = 1
    is_bytes = isinstance(data, (bytes, bytearray))
    o, c, q = (123, 125, 34) if is_bytes else ("{", "}", '"')
    search, string, comment = _re("special", data).search, _re("string", data).match, _re("comment", data).match
    while True:
        m = search(data, pos)
        if m is None:
            break
        ch = data[m.start()]
        if ch == o:
            depth += 1
            pos = m.end()
        elif ch == c:
            depth -= 1
            pos = m.end()
            if not depth:
                return pos
        else:
            s = (string if ch == q else comment)(data, m.start())
            pos = s.end() if s else m.end()
    raise SaveFormatError(f"unclosed '{{' opened before offset {pos}")


def _child_spec(spec, key):
    """The spec for the block under key: None (everything), a dict, SPAN, or _SKIPPED."""
    if spec is None:
        return None
    sub = spec.get(key, _SKIPPED)
    if sub is _SKIPPED:
        sub = spec.get("*", _SKIPPED)
    if sub is True:
        return None
    if sub is False or sub is None:
        return _SKIPPED
    return sub


class Once(dict):
    """A spec whose named keys each appear once in their block (a save's sections, the countries by tag).
    When every open block's spec is a Once and all their keys have been read, parsing stops there: the rest of
    the file is not read. Never wrap a spec for repeated keys (division, military_lines) in Once."""


def _todo(spec):
    """The keys a Once spec still waits for, or None (any other spec never stops early)."""
    if not isinstance(spec, Once) or "*" in spec:
        return None
    return {k for k, v in spec.items() if v is not False and v is not None}


def _finished(cur_todo, stack):
    """Every key named by the open blocks' Once specs has been read (each waits only for its open child)."""
    if cur_todo is None or cur_todo:
        return False
    for _, _, todo, child in stack:
        if todo is None or len(todo) > 1 or (todo and child not in todo):
            return False
    return True


def parse(data, spec=None, start=0, end=None, plain=None):
    """Parse Clausewitz script (bytes or str) into a Block. See the module docstring for spec, and Once.
    plain: how to skip blocks, as in skip_block (None: fast, and checked)."""
    if spec is True:
        spec = None
    is_bytes = isinstance(data, (bytes, bytearray))
    match = _re("token", data).match
    if end is None:
        end = len(data)
    if is_bytes:
        dot = b"."

        def text(b):
            return b.decode("utf-8", "replace")
    else:
        dot = "."

        def text(s):
            return s

    root = Block()
    stack = []               # (block, spec, keys it still waits for, key of the open child) of enclosing blocks
    cur, cur_spec = root, spec
    cur_todo = _todo(spec)
    ahead = None             # the next token's match, when it was read to see if a value is a key
    key = None               # a key waiting for its value
    op = None
    pos = start
    while True:
        if ahead is not None:
            m, ahead = ahead, None
        else:
            m = match(data, pos, end)
            if m is None:
                break
        pos = m.end()
        kind = m.lastindex
        if kind == _NUMBER:
            s = m.group(2)
            val = float(s) if dot in s else int(s)
        elif kind == _STRING:
            val = text(m.group(1))
            if "\\" in val:
                val = _ESC.sub(r"\1", val)
        elif kind == _WORD:
            val = text(m.group(4))
        elif kind == _OP:
            val = text(m.group(3))
        else:
            val = None

        if key is not None:                     # a key and its operator are waiting for the value
            if kind == _OPEN:
                sub = _child_spec(cur_spec, key)
                if sub is _SKIPPED or sub is SPAN:
                    e = skip_block(data, pos, plain)
                    if sub is SPAN:
                        item = Span(pos, e - 1)
                        lst = cur.get(key)
                        if lst is None:
                            cur[key] = [item]
                        else:
                            lst.append(item)
                    pos = e
                    if cur_todo and key in cur_todo:
                        cur_todo.discard(key)
                        if _finished(cur_todo, stack):
                            return root
                else:
                    child = Block()
                    item = child if op == "=" else Cmp(op, child)
                    lst = cur.get(key)
                    if lst is None:
                        cur[key] = [item]
                    else:
                        lst.append(item)
                    stack.append((cur, cur_spec, cur_todo, key))
                    cur, cur_spec = child, sub
                    cur_todo = _todo(sub)
            elif kind == _OP:
                raise SaveFormatError(f"key {key!r} has two operators (offset {pos})")
            else:
                nxt = m if kind == _CLOSE else match(data, pos, end)
                if nxt is not None and (kind == _CLOSE or nxt.lastindex == _OP):
                    item = ""                   # `role=` with nothing after it: this token starts the next pair
                    ahead = m
                else:
                    item = val
                    ahead = nxt
                if op != "=":
                    item = Cmp(op, item)
                lst = cur.get(key)
                if lst is None:
                    cur[key] = [item]
                else:
                    lst.append(item)
                if cur_todo and key in cur_todo:
                    cur_todo.discard(key)
                    if _finished(cur_todo, stack):
                        return root
            key = None
            continue

        if kind == _CLOSE:
            if not stack:
                raise SaveFormatError(f"'}}' without a matching '{{' (offset {pos})")
            cur, cur_spec, cur_todo, child_key = stack.pop()
            if cur_todo and child_key in cur_todo:
                cur_todo.discard(child_key)
                if _finished(cur_todo, stack):
                    return root
        elif kind == _OPEN:                     # anonymous block inside a list: same spec as its parent
            child = Block()
            cur.bare.append(child)
            stack.append((cur, cur_spec, cur_todo, None))
            cur, cur_todo = child, None
        elif kind == _OP:
            raise SaveFormatError(f"operator {val!r} without a key (offset {pos})")
        else:                                   # a key, or a bare value: the next token tells
            nxt = match(data, pos, end)
            if nxt is not None and nxt.lastindex == _OP:
                pos = nxt.end()
                key = val if kind != _NUMBER else (str(val) if isinstance(val, int) else text(m.group(2)))
                op = text(nxt.group(3))
            else:
                cur.bare.append(val)
                ahead = nxt
    if key is not None:
        raise SaveFormatError(f"key {key!r} has no value at the end")
    if stack:
        raise SaveFormatError(f"{len(stack)} block(s) not closed at the end")
    return root


def read_save(path):
    """The save's bytes, after checking it is a text save. Opens the file read-only."""
    data = Path(path).read_bytes()
    if data.startswith(BINARY_MAGIC):
        raise SaveFormatError(f"{Path(path).name}: {BINARY_HELP}")
    if not data.startswith(TEXT_MAGIC):
        raise SaveFormatError(f"{Path(path).name} is not an HOI4 text save: it does not start with HOI4txt")
    return data


def parse_file(path, spec=None):
    """Parse a whole text save (spec as in parse)."""
    data = read_save(path)
    return parse(data, spec, start=len(TEXT_MAGIC))


def _spec_for(keys):
    spec = True
    for k in reversed(keys):
        spec = Once({k: spec})
    return spec


def raw(path, dotted):
    """One block or value of a save by dotted path (countries.GER.focus), parsing only what leads to it and
    stopping once it is read. A repeated key gives its first value."""
    keys = [k for k in dotted.split(".") if k]
    root = parse_file(path, _spec_for(keys))
    return root.path(*keys)


# --------------------------------------------------------------------------------------------- the game's files

def _lua_number(text, name):
    """The last `NAME = number` in Lua defines text, comments removed."""
    text = re.sub(r"--[^\n]*", "", text)
    found = re.findall(r"\b" + re.escape(name) + r"\s*=\s*(-?\d+(?:\.\d+)?)", text)
    return float(found[-1]) if found else None


class GameData:
    """What the reader takes from the game's own files: research costs, state names, which state a province is in.
    `roots` are the game folder then each enabled mod, in load order; a later file of the same name replaces an
    earlier one, and a mod's replace_path drops every earlier file under that folder. Files are only read."""

    def __init__(self, roots):
        self.roots = [(Path(p), tuple(rp.strip("/").replace("\\", "/") for rp in replace)) for p, replace in roots]
        self._cache = {}

    @classmethod
    def load(cls, game_dir=None, user_dir=None, mods=True):
        """The game folder plus the mods enabled in user_dir/dlc_load.json, or None if there is no game folder."""
        game_dir = Path(game_dir) if game_dir else DEFAULT_GAME_DIR
        if not (game_dir / "common").is_dir():
            return None
        roots = [(game_dir, ())]
        if mods:
            roots += enabled_mods(Path(user_dir) if user_dir else DEFAULT_USER_DIR)
        return cls(roots)

    def files(self, folder, pattern="*.txt"):
        """{file name: path} of the files in folder that win, in name order."""
        folder = folder.strip("/")
        found = {}
        for root, replace in self.roots:
            if any(folder == rp or folder.startswith(rp + "/") for rp in replace):
                found = {}
            d = root / folder
            if d.is_dir():
                for p in d.glob(pattern):
                    found[p.name] = p
        return dict(sorted(found.items()))

    def _memo(self, name, fn):
        if name not in self._cache:
            self._cache[name] = fn()
        return self._cache[name]

    def define(self, name):
        """A number from the Lua defines (common/defines/*.lua, mods after the game), or None."""
        def load():
            value = None
            for p in self.files("common/defines", "*.lua").values():
                v = _lua_number(p.read_text(encoding="utf-8-sig", errors="replace"), name)
                if v is not None:
                    value = v
            return value
        return self._memo("define:" + name, load)

    def base_tech_cost(self):
        """NTechnology.BASE_TECH_COST: research points per point of a tech's research_cost (110 in 1.19)."""
        return self.define("BASE_TECH_COST")

    def ahead_penalty(self):
        """NTechnology.BASE_YEAR_AHEAD_PENALTY_FACTOR: research time grows by this much per year ahead (2)."""
        v = self.define("BASE_YEAR_AHEAD_PENALTY_FACTOR")
        return 2.0 if v is None else v

    def tech_info(self):
        """{tech: (research points to finish it, start_year or None)}; points = research_cost * BASE_TECH_COST."""
        def load():
            base = self.base_tech_cost()
            info = {}
            if not base:
                return info
            for p in self.files("common/technologies").values():
                root = parse(p.read_bytes(), {"technologies": {"*": {}}}, plain=False)
                for techs in root.all("technologies"):
                    if not isinstance(techs, Block):
                        continue
                    for name, vals in techs.items():
                        t = vals[-1]
                        if not isinstance(t, Block):
                            continue
                        rc, year = t.one("research_cost"), t.one("start_year")
                        if isinstance(rc, str) and rc.startswith("@"):
                            rc = root.one(rc)
                        if isinstance(year, str) and year.startswith("@"):
                            year = root.one(year)
                        if isinstance(rc, (int, float)):
                            info[name] = (rc * base, year if isinstance(year, int) else None)
            return info
        return self._memo("tech_info", load)

    def tech_costs(self):
        """{tech: research points to finish it}."""
        return {k: v[0] for k, v in self.tech_info().items()}

    def state_names(self):
        """{state id: English name}, from the STATE_<id> localisation keys."""
        def load():
            names = {}
            pat = re.compile(r'^\s*STATE_(\d+):\d*\s*"(.*)"', re.M)
            for folder in ("localisation/english", "localisation/replace/english", "localisation/replace"):
                for p in self.files(folder, "*_l_english.yml").values():
                    text = p.read_text(encoding="utf-8-sig", errors="replace")
                    if "STATE_" in text:
                        for sid, name in pat.findall(text):
                            names[int(sid)] = name
            return names
        return self._memo("state_names", load)

    def province_states(self):
        """{province id: state id}, from history/states."""
        def load():
            out = {}
            for p in self.files("history/states").values():
                root = parse(p.read_bytes(), {"state": {"provinces": True}}, plain=False)
                for st in root.all("state"):
                    if isinstance(st, Block) and isinstance(st.one("id"), int):
                        provs = st.one("provinces")
                        for prov in (provs.bare if isinstance(provs, Block) else []):
                            out[prov] = st.one("id")
            return out
        return self._memo("province_states", load)


def enabled_mods(user_dir):
    """[(mod folder, replace paths)] of the mods in dlc_load.json, in its order. Missing mods are left out."""
    dl = Path(user_dir) / "dlc_load.json"
    if not dl.is_file():
        return []
    out = []
    for rel in json.loads(dl.read_text(encoding="utf-8-sig")).get("enabled_mods", []):
        desc = Path(user_dir) / rel
        if not desc.is_file():
            continue
        d = parse(desc.read_text(encoding="utf-8-sig", errors="replace"))
        path = d.one("path") or d.one("archive")
        if not isinstance(path, str):
            continue
        p = Path(path)
        if not p.is_absolute():
            p = Path(user_dir) / p
        if p.is_dir():
            out.append((p, tuple(str(r) for r in d.all("replace_path"))))
    return out


# --------------------------------------------------------------------------------------------- the extract

_PARTICLES = {"von", "van", "der", "den", "de", "di", "da", "du", "del", "della", "la", "le", "zu", "und", "of",
              "the", "y", "e", "al", "bin", "ibn"}


def leader_name(key):
    """A readable name from a character's name key: GER_gerd_von_rundstedt -> Gerd von Rundstedt."""
    if not isinstance(key, str) or not key:
        return None
    if " " in key or not re.fullmatch(r"[A-Za-z0-9_]+", key):
        return key
    key = re.sub(r"^[A-Z][A-Z0-9]{2}_", "", key)
    words = [w for w in key.split("_") if w]
    return " ".join(w if (i and w.lower() in _PARTICLES) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def _ref(v):
    """(id, type) of an `{ id=N type=T }` reference block, or None."""
    if isinstance(v, Block):
        i, t = v.one("id"), v.one("type")
        if isinstance(i, int):
            return (i, t)
    return None


def _num(v, default=0):
    return v if isinstance(v, (int, float)) else default


def _r(v, nd=2):
    return round(v, nd) if isinstance(v, float) else v


def _day_number(date):
    """Days since year 0 for "1939.11.1.12" (the game's calendar has no leap years), or None."""
    if not isinstance(date, str):
        return None
    parts = date.split(".")
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        return None
    months = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    return y * 365 + months[max(1, min(m, 12)) - 1] + d


def _manpower_ratio(d):
    am = d.one("army_manpower")
    if not isinstance(am, Block):
        return None

    def total(key):
        blk = am.one(key)
        return sum(_num(v.one("value")) for v in blk.all("value") if isinstance(v, Block)) if isinstance(blk, Block) else 0
    need = total("army_manpower_need")
    return round(total("army_manpower_value") / need, 3) if need else None


# The parts of a country's block the extract reads; every other block in it is skipped (its plain values are kept).
_DIVISION = {"id": True, "division_template_id": True, "division_name": True, "army_manpower": True,
             "path": True}
_LINE = {"id": True, "equipment_variant_index": True, "factory_efficiencies": True}
COUNTRY_SPEC = {
    "technology": {"technologies": {"*": {}}, "slots": True},
    "focus": True,
    "politics": {"parties": {"*": {}}, "ideas": True},
    "production": {"military_lines": _LINE, "naval_lines": _LINE,
                   "general_lines": {"building": {"id": True, "building": True}}},
    "units": {"division": _DIVISION,
              "fleet": {"id": True, "task_force": {"id": True, "ship": {"id": True}, "mission": True}}},
    "theatres": {"theatre": {"orders_group": {"id": True, "member": True, "leader": True},
                             "theater_group": True, "front": {"provinces": True, "enemies": True}}},
    "deployment": {"military_deployment_conveyor": {
        "division_template_id": True,
        "military_deployment_line": {"military_deployment": {}}}},
}
OTHER_COUNTRY_SPEC = {"units": {"division": {"id": True, "division_template_id": True}}}
_TEMPLATES_SPEC = {"division_template": {"id": True, "regiments": True, "support": True}}
_STATES_SPEC = {"*": {"buildings": {"*": {}}, "manpower_pool": True}}

# An entry that starts with its own id: `{ id={ id=N type=T }`. Anchored on the brace, so the regex engine can
# jump between braces (a pattern that starts with the key's characters is 100x slower on a 4 MB block).
_ENTRY_ID = re.compile(rb'\{\s*id\s*=\s*\{\s*id\s*=\s*(\d+)\s+type\s*=\s*(\d+)\s*\}')
_WS = b" \t\r\n"


def _key_before(data, i):
    """The key of `key = {` whose '{' is data[i], or None."""
    j = i - 1
    while j >= 0 and data[j] in _WS:
        j -= 1
    if j < 0 or data[j] != 61:                  # '='
        return None
    j -= 1
    while j >= 0 and data[j] in _WS:
        j -= 1
    k = j
    while k >= 0 and data[k] not in b" \t\r\n{}=":
        k -= 1
    return data[k + 1:j + 1].decode("utf-8", "replace") if j > k else None


def _lookup(data, span, wanted, keys, entry_spec, plain, full_spec, full_pick):
    """{(id, type): (key, block)} for the references wanted, inside one top-level block.
    A regex finds each `key={ id={ id=N type=T }` entry (key in keys, if given); only those wanted are parsed.
    Anything not found that way is looked up again by parsing the whole block (slower, same answer)."""
    out = {}
    if not span or not wanted:
        return out
    for m in _ENTRY_ID.finditer(data, span.start, span.end) if isinstance(data, (bytes, bytearray)) else ():
        ref = (int(m.group(1)), int(m.group(2)))
        if ref in wanted and ref not in out:
            key = _key_before(data, m.start())
            if key is None or (keys and key not in keys):
                continue
            inner = m.start() + 1
            e = skip_block(data, inner, plain)
            blk = parse(data, entry_spec, start=inner, end=e - 1, plain=plain)
            if _ref(blk.one("id")) == ref:
                out[ref] = (key, blk)
    missing = set(wanted) - set(out)
    if missing:
        root = parse(data, full_spec, start=span.start, end=span.end, plain=plain)
        for ref, key, blk in full_pick(root):
            if ref in missing and ref not in out:
                out[ref] = (key, blk)
    return out


def _all_equipment(root):
    for key, vals in root.items():
        for blk in vals:
            if isinstance(blk, Block):
                yield _ref(blk.one("id")), key, blk


_LEADER_ROLES = ("corps_commander", "field_marshal", "navy_leader")


def _all_leaders(root):
    for group in root.values():
        for g in group:
            if not isinstance(g, Block):
                continue
            for ch in g.all("character"):
                if not isinstance(ch, Block):
                    continue
                for role in _LEADER_ROLES:
                    for blk in ch.all(role):
                        if isinstance(blk, Block):
                            yield _ref(blk.one("id")), role, blk


def extract(save, tag=None, units=(), game=None, timing=None):
    """Compact JSON-ready dict for one country (the player's when tag is None) from a text save.
    save: a path or the save's bytes. units: other countries whose divisions to include. game: a GameData for
    research days left and state names, or None. timing: a dict to fill with seconds per step."""
    clock = [time.perf_counter()]

    def lap(name):
        now = time.perf_counter()
        if timing is not None:
            timing[name] = round(now - clock[0], 3)
        clock[0] = now

    if isinstance(save, (bytes, bytearray)):
        data, name = bytes(save), None
        if data.startswith(BINARY_MAGIC):
            raise SaveFormatError(BINARY_HELP)
        if not data.startswith(TEXT_MAGIC):
            raise SaveFormatError("not an HOI4 text save: it does not start with HOI4txt")
    else:
        data, name = read_save(save), Path(save).name
    lap("read")
    plain = None             # skip blocks by counting braces, each skipped stretch checked (see skip_block)

    if tag is None:
        m = re.search(rb'\nplayer\s*=\s*"([^"]+)"', data[:65536])
        tag = m.group(1).decode() if m else None
        if not tag:
            raise SaveFormatError("no player= in the save's header: give --tag")
    units = [u for u in units if u and u != tag]
    # Once: each of these appears once, so reading stops when the last is done (in 1.19 saves the countries come
    # after the other sections, and the player is often the first country).
    spec = Once({
        "player": True, "date": True, "version": True,
        "countries": Once({tag: COUNTRY_SPEC, **{u: OTHER_COUNTRY_SPEC for u in units}}),
        "equipments": SPAN,
        "character_manager": SPAN,
        "division_templates": _TEMPLATES_SPEC,
        "states": _STATES_SPEC,
    })
    root = parse(data, spec, start=len(TEXT_MAGIC), plain=plain)
    lap("parse")

    countries = root.one("countries")
    c = countries.one(tag) if isinstance(countries, Block) else None
    if not isinstance(c, Block):
        raise SaveFormatError(f"country {tag} is not in the save")

    prod = c.one("production") if isinstance(c.one("production"), Block) else Block()
    lines = [(kind, ln) for kind in ("military_lines", "naval_lines") for ln in prod.all(kind) if isinstance(ln, Block)]
    want_eq = {_ref(ln.one("equipment_variant_index")) for _, ln in lines} - {None}
    equipment = _lookup(data, root.one("equipments"), want_eq, None, {"id": True}, plain,
                        {"*": {"id": True}}, _all_equipment)
    theatres = c.path("theatres")
    groups = []
    if isinstance(theatres, Block):
        for th in theatres.all("theatre"):
            if isinstance(th, Block):
                groups += [og for og in th.all("orders_group") if isinstance(og, Block)]
    want_leaders = {_ref(og.one("leader")) for og in groups} - {None}
    leaders = _lookup(data, root.one("character_manager"), want_leaders, _LEADER_ROLES, {"id": True, "traits": True},
                      plain, {"*": {"character": {"id": True, "corps_commander": {"id": True, "traits": True},
                                                  "field_marshal": {"id": True, "traits": True},
                                                  "navy_leader": {"id": True, "traits": True}}}}, _all_leaders)
    lap("lookups")
    if game:
        game.tech_info(), game.ahead_penalty(), game.state_names(), game.province_states()
        lap("game_files")

    states_names = game.state_names() if game else {}
    templates = {}
    dt = root.one("division_templates")
    if isinstance(dt, Block):
        for t in dt.all("division_template"):
            if isinstance(t, Block) and _ref(t.one("id")):
                templates[_ref(t.one("id"))] = t
    date = root.one("date")
    out = {
        "save": {"file": name, "date": date, "player": root.one("player"), "version": root.one("version"),
                 "difficulty": root.one("difficulty")},
        "tag": tag,
        "politics": _politics(c),
        "focus": _focus(c),
        "research": _research(c, game, _years(date)),
        "production": [_line(kind, ln, equipment) for kind, ln in lines],
        "construction": _construction(prod, states_names),
    }
    armies, army_of = _armies(theatres, leaders)
    out["divisions"] = _divisions(c, templates, army_of, date, game)
    out["armies"] = armies
    out["fronts"] = _fronts(theatres)
    out["templates"] = _templates(templates, tag, out["divisions"])
    out["training"] = _training(c, templates)
    out["fleets"] = _fleets(c)
    out["states"] = _states(root.one("states"), tag, states_names)
    if units:
        out["units"] = {u: _other_divisions(countries.one(u), templates) for u in units}
    lap("build")
    return out


def _politics(c):
    pol = c.one("politics") if isinstance(c.one("politics"), Block) else Block()
    parties = pol.one("parties")
    ideas = pol.one("ideas")
    return {
        "political_power": _r(pol.one("political_power")),
        "stability": _r(c.one("stability"), 3),
        "war_support": _r(c.one("war_support"), 3),
        "command_power": _r(c.one("command_power")),
        "ruling_party": pol.one("ruling_party"),
        "popularity": ({k: _r(v[0].one("popularity"), 1) for k, v in parties.items() if isinstance(v[0], Block)}
                       if isinstance(parties, Block) else {}),
        "ideas": list(ideas.bare) if isinstance(ideas, Block) else [],
    }


def _focus(c):
    f = c.one("focus") if isinstance(c.one("focus"), Block) else Block()
    return {
        "tree": c.one("focus_tree"),
        "current": f.one("current"),
        "progress": _r(f.one("progress")),
        "paused": f.one("paused") == "yes",
        "completed": list(f.all("completed")),
    }


def _years(date):
    """"1940.1.30.6" as a year with a fraction (365-day years, as the game counts), or None."""
    if not isinstance(date, str):
        return None
    parts = (date.split(".") + ["0"])[:4]
    try:
        y, m, d, h = (int(p) for p in parts)
    except ValueError:
        return None
    months = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    return y + (months[max(1, min(m, 12)) - 1] + d - 1 + h / 24) / 365


def research_eta(points, cost, factor, saved, start_year, now, penalty=2.0):
    """(points per day now, days left) for a tech being researched.

    What the saves show (Germany 1939-40, docs in the PR): a tech gains S / A(t) points a day, where
    A(t) = 1 + penalty * (years the date is before the tech's start_year, or 0) and S is the country's speed for it.
    The slot's points_factor is that rate on the day research started, and the saved points it used were added at
    that rate. So: find the start day that explains the points already earned, take S from it, and run the same
    curve forward to the cost. Without a start_year, the rate is taken as constant (points_factor)."""
    if not cost or not isinstance(factor, (int, float)) or factor <= 0:
        return None, None
    remaining = cost - points
    if start_year is None or now is None:
        return factor, max(0, math.ceil(remaining / factor - 1e-9))
    y = float(start_year)

    def a(t):
        return 1 + penalty * max(0.0, y - t)

    def integral(t0, t1):
        """The integral of 1 / A(t) from t0 to t1, in years."""
        total = 0.0
        if t0 < y:
            e = min(t1, y)
            total += math.log(a(t0) / a(e)) / penalty if penalty else e - t0
        if t1 > y:
            total += t1 - max(t0, y)
        return total

    earned = max(0.0, points - _num(saved) * factor)
    t0 = now
    if earned > 1e-9:
        lo, hi = now - 40.0, now
        for _ in range(100):
            mid = (lo + hi) / 2
            if 365 * factor * a(mid) * integral(mid, now) > earned:
                lo = mid
            else:
                hi = mid
        t0 = (lo + hi) / 2
    s = factor * a(t0)
    rate = s / a(now)
    if remaining <= 0:
        return rate, 0
    if now < y and penalty:
        until_year = 365 * s * math.log(a(now)) / penalty      # points earned between now and the start year
        if remaining <= until_year:
            a1 = a(now) * math.exp(-remaining * penalty / (365 * s))
            days = 365 * (y - (a1 - 1) / penalty - now)
        else:
            days = 365 * (y - now) + (remaining - until_year) / s
    else:
        days = remaining / s
    return rate, max(0, math.ceil(days - 1e-6))


def _research(c, game, now):
    tech = c.one("technology") if isinstance(c.one("technology"), Block) else Block()
    slots = tech.one("slots") if isinstance(tech.one("slots"), Block) else Block()
    techs = tech.one("technologies") if isinstance(tech.one("technologies"), Block) else Block()
    info = game.tech_info() if game else {}
    penalty = game.ahead_penalty() if game else 2.0
    running = []
    for name, vals in slots.items():
        if name == "empty":                     # an idle slot: empty={ points=30 } (saved points), one per slot
            continue
        s = vals[0] if isinstance(vals[0], Block) else Block()
        t = techs.one(name)
        points = _num(t.one("research_points")) if isinstance(t, Block) else 0
        cost, year = info.get(name, (None, None))
        rate, days = research_eta(points, cost, s.one("points_factor"), s.one("used_saved_points"), year, now,
                                  penalty)
        running.append({"tech": name, "points": _r(points), "cost": _r(cost, 1),
                        "per_day": _r(rate if rate is not None else s.one("points_factor"), 3), "days_left": days,
                        "years_ahead": round(max(0.0, year - now), 2) if year and now else None})
    researched = sorted(k for k, v in techs.items() if isinstance(v[0], Block) and _num(v[0].one("level")) >= 1)
    idle = [e.one("points") for e in slots.all("empty") if isinstance(e, Block)]
    n = c.one("research_slot")
    return {"slots": n, "free": len(idle) if idle else ((n - len(running)) if isinstance(n, int) else None),
            "saved_points": idle, "running": running, "researched": researched}


def _line(kind, ln, equipment):
    eq_type, variant = None, None
    hit = equipment.get(_ref(ln.one("equipment_variant_index")))
    if hit:
        eq_type, blk = hit
        variant = blk.one("name")
    active = _num(ln.one("active_factories"))
    effs = ln.one("factory_efficiencies")
    effs = [e for e in effs.bare if isinstance(e, (int, float))][:int(active)] if isinstance(effs, Block) else []
    speed, cost, produced = _num(ln.one("speed")), _num(ln.one("cost")), _num(ln.one("produced"))
    amount = ln.one("amount")
    row = {"kind": "naval" if kind == "naval_lines" else "military", "equipment": eq_type, "variant": variant,
           "factories": active, "requested": ln.one("requested_factories"),
           "efficiency": round(sum(effs) / len(effs), 1) if effs else None,
           "priority": ln.one("priority"), "amount": None if amount == -1 else amount}
    if kind == "naval_lines":
        row["progress"] = round(produced / cost, 3) if cost else None
        row["days_to_next"] = math.ceil((cost - produced) / speed) if speed and cost else None
    else:
        row["per_day"] = round(speed / cost, 2) if cost else None
    return row


def _construction(prod, state_names):
    gl = prod.one("general_lines")
    out = []
    for b in (gl.all("building") if isinstance(gl, Block) else []):
        if not isinstance(b, Block):
            continue
        what = b.one("building") if isinstance(b.one("building"), Block) else Block()
        speed, cost, produced = _num(b.one("speed")), _num(b.one("cost")), _num(b.one("produced"))
        loc = what.one("location")
        out.append({"building": what.one("template"), "state": loc, "state_name": state_names.get(loc),
                    "levels": b.one("amount"), "factories": _num(b.one("active_factories")),
                    "progress": round(produced / cost, 3) if cost else None,
                    "days_left": math.ceil((cost - produced) / speed) if speed and cost else None,
                    "priority": b.one("priority")})
    return out


def _armies(theatres, leaders):
    armies, army_of = [], {}
    if not isinstance(theatres, Block):
        return armies, army_of
    for th in theatres.all("theatre"):
        if not isinstance(th, Block):
            continue
        group_of = {}
        for tg in th.all("theater_group"):
            if isinstance(tg, Block):
                for ref in tg.all("orders_group"):
                    group_of[_ref(ref)] = tg.one("name")
        for og in th.all("orders_group"):
            if not isinstance(og, Block):
                continue
            members = [_ref(m.one("unit")) for m in og.all("member") if isinstance(m, Block)]
            name = og.one("name")
            for ref in members:
                army_of[ref] = name
            hit = leaders.get(_ref(og.one("leader")))
            leader = None
            if hit:
                role, blk = hit
                traits = blk.one("traits")
                leader = {"name": leader_name(blk.one("name")), "role": role, "skill": blk.one("skill"),
                          "attack": blk.one("attack_skill"), "defense": blk.one("defense_skill"),
                          "planning": blk.one("planning_skill"), "logistics": blk.one("logistics_skill"),
                          "traits": list(traits.bare) if isinstance(traits, Block) else []}
            armies.append({"name": name, "group": group_of.get(_ref(og.one("id"))), "leader": leader,
                           "divisions": len(members)})
    return armies, army_of


def _fronts(theatres):
    out = []
    if not isinstance(theatres, Block):
        return out
    for th in theatres.all("theatre"):
        if not isinstance(th, Block):
            continue
        for f in th.all("front"):
            if isinstance(f, Block):
                provs, enemies = f.one("provinces"), f.one("enemies")
                out.append({"enemies": list(enemies.bare) if isinstance(enemies, Block) else [],
                            "provinces": list(provs.bare) if isinstance(provs, Block) else []})
    return out


def _division_name(d, template_name):
    dn = d.one("division_name")
    if isinstance(dn, Block):
        if isinstance(dn.one("override"), str):
            return dn.one("override")
        if isinstance(dn.one("name"), str):
            return dn.one("name")
        if isinstance(dn.one("name_order"), int) and template_name:
            return f"{dn.one('name_order')}. {template_name}"
    return template_name


def _divisions(c, templates, army_of, date, game):
    units = c.one("units")
    today = _day_number(date)
    prov_state = game.province_states() if game else {}
    names = game.state_names() if game else {}
    out = []
    for d in (units.all("division") if isinstance(units, Block) else []):
        if not isinstance(d, Block):
            continue
        ref = _ref(d.one("id"))
        t = templates.get(_ref(d.one("division_template_id")))
        tname = t.one("name") if isinstance(t, Block) else None
        path = d.one("path")
        path = path.bare if isinstance(path, Block) else []
        loc = d.one("location")
        fought = _day_number(d.one("last_combat_date"))
        row = {"id": ref[0] if ref else None, "name": _division_name(d, tname), "template": tname,
               "location": loc, "army": army_of.get(ref),
               "strength": _r(d.one("strength"), 1), "org": _r(d.one("organisation"), 1),
               "manpower": _manpower_ratio(d),
               "moving_to": path[-1] if path else None,
               "in_combat": bool(today and fought and today - fought <= 1)}
        if game:
            sid = prov_state.get(loc)
            row["state"] = names.get(sid) or sid
        out.append(row)
    return out


def _templates(templates, tag, divisions):
    used = {}
    for d in divisions:
        used[d["template"]] = used.get(d["template"], 0) + 1
    out = []
    for t in templates.values():
        if t.one("country") != tag:
            continue
        regs, sup = t.one("regiments"), t.one("support")
        out.append({"name": t.one("name"),
                    "regiments": {k: len(v) for k, v in regs.items()} if isinstance(regs, Block) else {},
                    "support": list(sup.keys()) if isinstance(sup, Block) else [],
                    "divisions": used.get(t.one("name"), 0)})
    return out


def _training(c, templates):
    dep = c.one("deployment")
    out = []
    for conv in (dep.all("military_deployment_conveyor") if isinstance(dep, Block) else []):
        if not isinstance(conv, Block):
            continue
        t = templates.get(_ref(conv.one("division_template_id")))
        batches = []
        for ln in conv.all("military_deployment_line"):
            if isinstance(ln, Block):
                md = ln.one("military_deployment") if isinstance(ln.one("military_deployment"), Block) else Block()
                mx = _num(md.one("max_training"), 1) or 1
                batches.append({"divisions": ln.one("amount"), "progress": round(_num(md.one("training")) / mx, 2)})
        out.append({"template": (t.one("name") if isinstance(t, Block) else None) or conv.one("name"),
                    "queued": conv.one("amount"), "location": conv.one("location") or None, "training": batches})
    return out


def _fleets(c):
    units = c.one("units")
    out = []
    for f in (units.all("fleet") if isinstance(units, Block) else []):
        if not isinstance(f, Block):
            continue
        forces = []
        for tf in f.all("task_force"):
            if not isinstance(tf, Block):
                continue
            ships = [s for s in tf.all("ship") if isinstance(s, Block)]
            kinds = {}
            for s in ships:
                kinds[s.one("definition")] = kinds.get(s.one("definition"), 0) + 1
            mission = tf.one("mission")
            forces.append({"name": tf.one("name"), "location": tf.one("location"),
                           "mission": mission.one("mission") if isinstance(mission, Block) else mission,
                           "ships": kinds,
                           "strength": round(sum(_num(s.one("strength")) for s in ships), 1),
                           "org": round(sum(_num(s.one("organisation")) for s in ships) / len(ships), 1) if ships
                           else None})
        out.append({"name": f.one("name"), "home_base": f.one("home_base"), "task_forces": forces})
    return out


def _states(states, tag, names):
    out = []
    if not isinstance(states, Block):
        return out
    for sid, vals in states.items():
        st = vals[0]
        if not isinstance(st, Block) or st.one("owner") != tag:
            continue
        b = st.one("buildings")
        mp = st.one("manpower_pool")
        sid_n = int(sid) if sid.isdigit() else sid
        out.append({"id": sid_n, "name": names.get(sid_n), "category": st.one("state_category"),
                    "buildings": ({k: v[0].one("level") for k, v in b.items() if isinstance(v[0], Block)}
                                  if isinstance(b, Block) else {}),
                    "manpower": mp.one("available") if isinstance(mp, Block) else None})
    return out


def _other_divisions(c, templates):
    units = c.one("units") if isinstance(c, Block) else None
    out = []
    for d in (units.all("division") if isinstance(units, Block) else []):
        if isinstance(d, Block):
            t = templates.get(_ref(d.one("division_template_id")))
            out.append({"location": d.one("location"), "template": t.one("name") if isinstance(t, Block) else None,
                        "strength": _r(d.one("strength"), 1), "org": _r(d.one("organisation"), 1)})
    return out


# --------------------------------------------------------------------------------------------- the CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", help="a text save (.hoi4)")
    ap.add_argument("--tag", help="the country (default: the save's player)")
    ap.add_argument("--units", default="", help="other countries whose divisions to include, comma-separated")
    ap.add_argument("--raw", metavar="PATH", help="print one block of the save instead, e.g. countries.GER.focus")
    ap.add_argument("--game-dir", help=f"the game folder (default {DEFAULT_GAME_DIR})")
    ap.add_argument("--user-dir", help="the folder with dlc_load.json and mod/ (default Documents/Paradox Interactive/"
                                       "Hearts of Iron IV)")
    ap.add_argument("--no-game", action="store_true", help="do not read the game's files (no days left on research)")
    ap.add_argument("--no-mods", action="store_true", help="read the game's files without the enabled mods")
    ap.add_argument("--indent", type=int, default=None, help="pretty-print the JSON")
    ap.add_argument("--timing", action="store_true", help="print seconds per step on stderr")
    args = ap.parse_args(argv)
    try:
        if args.raw:
            value = raw(args.save, args.raw)
            print(json.dumps(_to_py(value), indent=args.indent, ensure_ascii=False))
            return 0
        timing = {}
        t0 = time.perf_counter()
        game = None if args.no_game else GameData.load(args.game_dir, args.user_dir, mods=not args.no_mods)
        units = [u.strip().upper() for u in args.units.split(",") if u.strip()]
        snap = extract(args.save, tag=args.tag.upper() if args.tag else None, units=units, game=game, timing=timing)
        text = json.dumps(snap, indent=args.indent, ensure_ascii=False,
                          separators=None if args.indent is not None else (",", ":"))
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(text)
        if args.timing:
            timing["total"] = round(time.perf_counter() - t0, 3)
            print("timing (s): " + ", ".join(f"{k} {v}" for k, v in timing.items()) + f"; json {len(text):,} chars",
                  file=sys.stderr)
    except (SaveFormatError, OSError) as e:
        print(f"hoi4_save: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

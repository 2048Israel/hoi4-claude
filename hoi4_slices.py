r"""ST1: the state slicer. One input per agent of docs/command.md, with the fog of war applied.

    python hoi4_slices.py <save> [--bridge FILE] [--agent air] [--indent 1]      every slice (or one) as JSON
    python hoi4_slices.py <save> --sizes                                          each slice's size and build time

In Python:
    game = hoi4_save.GameData.load()
    snap = snapshot(save, game=game)                      SR1's extract() plus what the slices need (below)
    world = MapData.load(game, cache=DEFAULT_CACHE)       province adjacency, states and regions, from map/
    out = slices(snap, bridge_state, world)               {agent name: dict}, names as hoi4_orderspec gives them

`bridge_state` is the bridge's last report: the records `hoi4.py` parses from game.log (a list of dicts with
"kind"), the same grouped by kind, or the log's text (see parse_bridge). It may be None.

Agents: policy, research, civilian_industry, military_industry, naval_industry, air, navy, army, one
field_marshal_<group> per army group and one operation_<name> per running operation (`field_marshals=` and
`operations=` override them). The keys are the agent names of docs/orders.md, so a slice goes to its agent as is.

Fog of war (docs/command.md, Fair play): our own country in full. Of an enemy, only what the game shows a player:
the division and factory counts per country from the bridge's report (diplomacy shows them), and its divisions
only in provinces we control or stand in, or next to one of those. Adjacency is read at run time from the game's
map/ (provinces.bmp, definition.csv, adjacencies.csv), never committed. Without a map, only enemy divisions inside
our own provinces are shown. Hidden ideas are left out.

Standard library only, no import of hoi4.py. The save and the game's files are only read.
"""
import argparse
import json
import re
import struct
import sys
import time
import unicodedata
from pathlib import Path

import hoi4_save as H

__all__ = ["MapData", "MapError", "AGENTS", "DEFAULT_CACHE", "SIZE_AIM", "snapshot", "read_extras", "read_wars",
           "parse_bridge", "slices", "sizes", "visible", "slug", "game_tables"]

ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = ROOT / "state" / "map_cache.json"      # state/ is never committed
AGENTS = ("policy", "research", "civilian_industry", "military_industry", "naval_industry", "air", "navy", "army")
SIZE_AIM = 8000                                         # characters of compact JSON per slice (docs/queue/ST1.md)
FOCUS_IF = 60                                           # characters kept of a focus's `available` text
MAP_CACHE_VERSION = 1


class MapError(ValueError):
    """The game's map files are missing or not in the expected format."""


# --------------------------------------------------------------------------------------------- the map

def _bmp_rows(path):
    """The rows of a 24-bit uncompressed BMP, as bytes of B,G,R pixels (row order does not matter here)."""
    data = Path(path).read_bytes()
    if data[:2] != b"BM" or len(data) < 54:
        raise MapError(f"{path} is not a BMP file")
    off, = struct.unpack_from("<I", data, 10)
    w, h = struct.unpack_from("<ii", data, 18)
    bpp, comp = struct.unpack_from("<HI", data, 28)
    if bpp != 24 or comp != 0:
        raise MapError(f"{path}: needs an uncompressed 24-bit BMP, found {bpp} bits, compression {comp}")
    stride = (w * 3 + 3) & ~3
    if off + stride * abs(h) > len(data):
        raise MapError(f"{path} is cut short")
    return w, [data[off + y * stride: off + y * stride + w * 3] for y in range(abs(h))]


_RUN = re.compile(rb"(...)\1*", re.S)      # one run of a repeated 3-byte pixel; matches stay pixel-aligned


def _touching_colors(rows):
    """Every pair of pixel colours that touch side by side or one above the other (the map wraps east-west).
    Runs of equal pixels are found by the regex engine, so only colour changes cost Python time."""
    pairs = set()
    prev_runs, prev_row = None, None
    for row in rows:
        runs = [(m.end() // 3, m.group(1)) for m in _RUN.finditer(row)]
        for i in range(1, len(runs)):
            a, b = runs[i - 1][1], runs[i][1]
            pairs.add((a, b) if a < b else (b, a))
        if len(runs) > 1 and runs[0][1] != runs[-1][1]:
            a, b = runs[0][1], runs[-1][1]
            pairs.add((a, b) if a < b else (b, a))
        if prev_runs is not None and row != prev_row:
            i = j = 0
            while i < len(prev_runs) and j < len(runs):
                (ea, a), (eb, b) = prev_runs[i], runs[j]
                if a != b:
                    pairs.add((a, b) if a < b else (b, a))
                if ea <= eb:
                    i += 1
                if eb <= ea:
                    j += 1
        prev_runs, prev_row = runs, row
    return pairs


def _read_definition(path):
    """{BGR bytes: province}, {province: land/sea/lake}, {province: terrain} from map/definition.csv."""
    color, kind, terrain = {}, {}, {}
    for line in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        p = line.split(";")
        if len(p) < 5 or not p[0].strip().isdigit():
            continue
        try:
            pid, r, g, b = (int(x) for x in p[:4])
        except ValueError:
            continue
        if pid <= 0:
            continue                                   # province 0 is the unused black
        color[bytes((b, g, r))] = pid
        kind[pid] = p[4].strip()
        if len(p) > 6 and p[6].strip():
            terrain[pid] = p[6].strip()
    return color, kind, terrain


def _read_adjacencies(path):
    """(added, removed) province pairs from map/adjacencies.csv: crossings (sea, or no type) join two provinces,
    `impassable` separates them."""
    added, removed = set(), set()
    if not path or not Path(path).is_file():
        return added, removed
    for line in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        p = line.split(";")
        if len(p) < 3:
            continue
        try:
            a, b = int(p[0]), int(p[1])
        except ValueError:
            continue                                   # the header
        if a <= 0 or b <= 0:
            continue                                   # the -1 line that ends the file
        pair = (a, b) if a < b else (b, a)
        (removed if p[2].strip().lower() == "impassable" else added).add(pair)
    return added, removed


def _read_regions(paths):
    """{province: region id}, {region id: its name key} from map/strategicregions/*.txt."""
    region_of, keys = {}, {}
    for p in paths:
        try:
            root = H.parse(Path(p).read_bytes(), {"strategic_region": {"provinces": True}}, plain=False)
        except H.SaveFormatError:
            continue
        for r in root.all("strategic_region"):
            if not isinstance(r, H.Block) or not isinstance(r.one("id"), int):
                continue
            rid = r.one("id")
            keys[rid] = r.one("name") if isinstance(r.one("name"), str) else f"STRATEGICREGION_{rid}"
            provs = r.one("provinces")
            for prov in (provs.bare if isinstance(provs, H.Block) else []):
                if isinstance(prov, int):
                    region_of[prov] = rid
    return region_of, keys


class MapData:
    """Which provinces touch, what each is (land, sea, lake; its terrain), and which state and strategic region
    each lies in. Built from the game's map/ folder (MapData.load) or handed in directly (tests)."""

    def __init__(self, neighbors, kind=None, terrain=None, region_of=None, region_names=None, state_of=None,
                 state_names=None):
        self.neighbors = {int(p): frozenset(int(q) for q in qs) for p, qs in neighbors.items()}
        self.kind = {int(k): v for k, v in (kind or {}).items()}
        self.terrain = {int(k): v for k, v in (terrain or {}).items()}
        self.region_of = {int(k): int(v) for k, v in (region_of or {}).items()}
        self.region_names = {int(k): v for k, v in (region_names or {}).items()}
        self.state_of = {int(k): int(v) for k, v in (state_of or {}).items()}
        self.state_names = {int(k): v for k, v in (state_names or {}).items()}
        self.provinces_of = {}
        for p, s in self.state_of.items():
            self.provinces_of.setdefault(s, set()).add(p)

    def ring(self, provinces):
        """The provinces next to any of these, not counting these."""
        provinces = set(provinces)
        out = set()
        for p in provinces:
            out |= self.neighbors.get(p, frozenset())
        return out - provinces

    def state_name(self, province):
        sid = self.state_of.get(province)
        return self.state_names.get(sid) or sid

    def region_name(self, rid):
        return self.region_names.get(rid) or rid

    @classmethod
    def from_files(cls, definition, bmp, adjacencies=None, regions=(), region_names=None, state_of=None,
                   state_names=None):
        """Read the map from its files. region_names: {name key: text} for the regions' localisation keys."""
        color, kind, terrain = _read_definition(definition)
        _, rows = _bmp_rows(bmp)
        neighbors = {}
        for a, b in _touching_colors(rows):
            pa, pb = color.get(a), color.get(b)
            if pa and pb and pa != pb:
                neighbors.setdefault(pa, set()).add(pb)
                neighbors.setdefault(pb, set()).add(pa)
        added, removed = _read_adjacencies(adjacencies)
        for a, b in added:
            neighbors.setdefault(a, set()).add(b)
            neighbors.setdefault(b, set()).add(a)
        for a, b in removed:
            neighbors.get(a, set()).discard(b)
            neighbors.get(b, set()).discard(a)
        region_of, keys = _read_regions(regions)
        names = {rid: (region_names or {}).get(key, key) for rid, key in keys.items()}
        return cls(neighbors, kind, terrain, region_of, names, state_of, state_names)

    @classmethod
    def load(cls, game, cache=None):
        """The map of the game (and its enabled mods) in `game` (a hoi4_save.GameData), or None without one.
        cache: a JSON file kept next to the run's state; rebuilt when any map file changes (size or time)."""
        if game is None:
            return None
        files = game.files("map", "*")
        need = [files.get(n) for n in ("definition.csv", "provinces.bmp")]
        if not all(need):
            return None
        adj = files.get("adjacencies.csv")
        regions = list(game.files("map/strategicregions").values())
        sources = [p for p in need + [adj] + regions if p]
        stamp = [[str(p), p.stat().st_size, p.stat().st_mtime_ns] for p in sources]
        state_of, state_names = game.province_states(), game.state_names()
        if cache and Path(cache).is_file():
            try:
                c = json.loads(Path(cache).read_text(encoding="utf-8"))
                if c.get("version") == MAP_CACHE_VERSION and c.get("sources") == stamp:
                    return cls(c["neighbors"], c["kind"], c["terrain"], c["region_of"], c["region_names"],
                               state_of, state_names)
            except (OSError, ValueError, KeyError):
                pass
        region_of, keys = _read_regions(regions)
        loc = localise(game, set(keys.values()))
        world = cls.from_files(need[0], need[1], adj, regions, loc, state_of, state_names)
        if cache:
            try:
                Path(cache).parent.mkdir(parents=True, exist_ok=True)
                Path(cache).write_text(json.dumps({
                    "version": MAP_CACHE_VERSION, "sources": stamp,
                    "neighbors": {p: sorted(q) for p, q in world.neighbors.items()}, "kind": world.kind,
                    "terrain": world.terrain, "region_of": world.region_of, "region_names": world.region_names},
                    separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        return world


# --------------------------------------------------------------------------------------------- the game's files

_LOC = re.compile(rb'^[ \t]*([A-Za-z0-9_.\-]+):\d*[ \t]*"(.*)"[ \t\r]*(?:#[^\n]*)?$', re.M)   # LF or CRLF
_LOC_REF = re.compile(r"\$([A-Za-z0-9_.\-]+)\$")


def localise(game, keys):
    """{key: English text} for the keys asked, from the game's and the enabled mods' english localisation."""
    keys = {k for k in keys if isinstance(k, str)}
    if not game or not keys:
        return {}
    files = [p for folder in ("localisation", "localisation/english", "localisation/replace",
                              "localisation/replace/english") for p in game.files(folder, "*_l_english.yml").values()]

    def scan(wanted):
        got = {}
        for p in files:                               # later folders (replace/) win
            for m in _LOC.finditer(p.read_bytes()):
                k = m.group(1).decode("utf-8", "replace")
                if k in wanted:
                    got[k] = m.group(2).decode("utf-8", "replace").strip()
        return got
    found = scan(keys)
    refs = {r for v in found.values() for r in _LOC_REF.findall(v)} - set(found)
    table = dict(found, **(scan(refs) if refs else {}))
    return {k: _LOC_REF.sub(lambda m: table.get(m.group(1), m.group(0)), v) for k, v in found.items()}


def game_tables(game):
    """What the slices take from the game's files: {idea: (category, cost)}, the law categories, the hired
    advisor slot of each advisor idea, the buildings that share a state's slots, and each state category's
    slots. Memoised on the GameData."""
    def load():
        ideas, laws = {}, set()
        for p in game.files("common/ideas").values():
            try:
                root = H.parse(p.read_bytes(), {"ideas": {"*": {"*": {}}}}, plain=False)
            except H.SaveFormatError:
                continue                               # a few of the game's own files do not balance
            for block in root.all("ideas"):
                if not isinstance(block, H.Block):
                    continue
                for cat, vals in block.items():
                    for c in vals:
                        if not isinstance(c, H.Block):
                            continue
                        if c.one("law") == "yes":
                            laws.add(cat)
                        for name, v in c.items():
                            if isinstance(v[0], H.Block):
                                cost = v[0].one("cost")
                                ideas[name] = (cat, cost if isinstance(cost, (int, float)) else None)
        advisors = {}
        tok = re.compile(rb"slot\s*=\s*(\w+)[^{}]*?idea_token\s*=\s*(\w+)|idea_token\s*=\s*(\w+)[^{}]*?slot\s*=\s*(\w+)")
        for p in game.files("common/characters").values():
            for m in tok.finditer(p.read_bytes()):
                slot, token = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                advisors[token.decode()] = slot.decode()
        shared, provincial = set(), set()
        for p in game.files("common/buildings").values():
            try:
                root = H.parse(p.read_bytes(), {"buildings": {"*": {"level_cap": True}}}, plain=False)
            except H.SaveFormatError:
                continue
            for block in root.all("buildings"):
                if not isinstance(block, H.Block):
                    continue
                for k, v in block.items():
                    cap = v[0].one("level_cap") if isinstance(v[0], H.Block) else None
                    if isinstance(cap, H.Block):
                        if cap.one("shares_slots") == "yes":
                            shared.add(k)
                        if cap.one("province_max") is not None:
                            provincial.add(k)     # built in one province: its location is a province id
        slots = {}
        for p in game.files("common/state_category").values():
            try:
                root = H.parse(p.read_bytes(), {"state_categories": {"*": {}}}, plain=False)
            except H.SaveFormatError:
                continue
            for block in root.all("state_categories"):
                if isinstance(block, H.Block):
                    for k, v in block.items():
                        if isinstance(v[0], H.Block) and isinstance(v[0].one("local_building_slots"), int):
                            slots[k] = v[0].one("local_building_slots")
        return {"ideas": ideas, "laws": sorted(laws), "advisors": advisors, "shared_buildings": sorted(shared),
                "provincial_buildings": sorted(provincial), "state_slots": slots}
    if game is None:
        return None
    return game._memo("st1_tables", load)


# --------------------------------------------------------------------------------------------- the save: extras

_EXTRA_SPEC = H.Once({
    "region": {"*": {"dominance": True}},
    "provinces": {"*": {}},
    "states": {"*": {}},
})
_DESIGNER_SLOTS = ("tank_manufacturer", "naval_manufacturer", "aircraft_manufacturer", "materiel_manufacturer",
                   "industrial_concern")


def _blocks_after(data, key, start=0):
    """(start, end) of the contents of every `key={` block in data (end is the closing brace)."""
    out, pos = [], start
    while True:
        i = data.find(key, pos)
        if i < 0:
            return out
        s = i + len(key)
        try:
            e = H.skip_block(data, s)
        except H.SaveFormatError:
            return out
        out.append((s, e - 1))
        pos = e


def read_wars(data, tag):
    """[{"enemy", "since"}] for every war `tag` is in, from the save's war_relation blocks (each sits in one of the
    two countries' diplomacy). Cheap: a byte search, then only those blocks are parsed."""
    wars = {}
    for s, e in _blocks_after(data, b"war_relation={"):
        b = H.parse(data, {}, start=s, end=e)
        first, second = b.one("first"), b.one("second")
        if tag in (first, second) and first != second:
            other = second if first == tag else first
            if other not in wars or (b.one("start_date") or "") < (wars[other] or ""):
                wars[other] = b.one("start_date")
    return [{"enemy": t, "since": d} for t, d in sorted(wars.items())]


def _read_air(data, tag):
    """Our air wings and the air bases they use or we own, from the save's strategic_air block, or None."""
    i = data.rfind(b"\nstrategic_air={")
    if i < 0:
        return None
    s = i + len(b"\nstrategic_air={")
    e = H.skip_block(data, s)
    blk = H.parse(data, {"air_base": {"id": True}, tag: {"air_wing_pool": {"air_base": True,
                                                                         "air_wings": {"mission": True}}}},
                  start=s, end=e - 1)
    bases = {}
    for b in blk.all("air_base"):
        if isinstance(b, H.Block):
            ref = H._ref(b.one("id"))
            if ref:
                bases[ref[0]] = {"state": b.one("state"), "carrier": b.one("carrier") is not None,
                                 "capacity": b.one("capacity"), "level": b.one("level")}
    wings = []
    mine = blk.one(tag)
    for pool in (mine.all("air_wing_pool") if isinstance(mine, H.Block) else []):
        if not isinstance(pool, H.Block):
            continue
        base = H._ref(pool.one("air_base"))
        for w in pool.all("air_wings"):
            if not isinstance(w, H.Block):
                continue
            m = w.one("mission") if isinstance(w.one("mission"), H.Block) else H.Block()
            wings.append({"name": w.one("name"), "type": pool.one("definition"), "planes": w.one("count"),
                          "base": base[0] if base else None, "mission": m.one("executing_mission"),
                          "region": m.one("strategic_region"),
                          "effectiveness": H._r(m.one("effectiveness")),
                          "experience": H._r(w.one("experience"), 0)})
    return {"bases": bases, "wings": wings}


def _faction(data, tag):
    """{"template", "members"} of the faction `tag` is in, or None."""
    for s, e in _blocks_after(data, b"\nfaction={"):
        try:
            b = H.parse(data, {"members": True}, start=s, end=e)
        except H.SaveFormatError:
            continue
        m = b.one("members")
        members = [x for x in m.bare if isinstance(x, str)] if isinstance(m, H.Block) else []
        if tag in members:
            return {"template": b.one("template"), "members": members}
    return None


def read_extras(save, tag):
    """What the slices need beyond SR1's extract: who controls which province, the air war, wars, the faction.
    Province control: a province's controller is written only where it differs from its state's owner."""
    data = save if isinstance(save, (bytes, bytearray)) else H.read_save(save)
    root = H.parse(data, _EXTRA_SPEC, start=len(H.TEXT_MAGIC))
    owners, overrides = {}, {}
    states = root.one("states")
    for sid, vals in (states.items() if isinstance(states, H.Block) else []):
        if isinstance(vals[0], H.Block) and sid.isdigit():
            owners[int(sid)] = vals[0].one("owner")
    provs = root.one("provinces")
    for pid, vals in (provs.items() if isinstance(provs, H.Block) else []):
        if isinstance(vals[0], H.Block) and pid.isdigit() and isinstance(vals[0].one("controller"), str):
            overrides[int(pid)] = vals[0].one("controller")
    superiority = {}
    region = root.one("region")
    for rid, vals in (region.items() if isinstance(region, H.Block) else []):
        dom = vals[0].one("dominance") if isinstance(vals[0], H.Block) else None
        if not isinstance(dom, H.Block) or not rid.isdigit():
            continue
        holders = dom.one("countries")
        holders = [x for x in holders.bare if isinstance(x, str)] if isinstance(holders, H.Block) else []
        ratio = None
        values = dom.one("values")
        for v in (values.bare if isinstance(values, H.Block) else []):
            if isinstance(v, H.Block) and v.bare[:1] == [tag] and len(v.bare) > 1 and isinstance(v.bare[1], H.Block):
                ratio = H._r(v.bare[1].one("individual_ratio"), 3)
        if holders or ratio:
            superiority[int(rid)] = {"held_by": holders, "ours": ratio}
    return {"control": {"state_owner": owners, "province_controller": overrides},
            "air": _read_air(data, tag), "air_superiority": superiority, "faction": _faction(data, tag)}


def _focus_options(save_path, snap, game, user_dir):
    """The focuses that can start now, from FP1 (hoi4_focus.plan), trimmed for the policy slice, or None."""
    try:
        import hoi4_focus
        from types import SimpleNamespace
        game_dir = game.roots[0][0]
        f = snap["focus"]
        args = SimpleNamespace(tag=snap["tag"], ideology=snap["politics"].get("ruling_party"),
                               save=str(save_path) if save_path else None, completed="" if save_path else
                               ",".join(f.get("completed") or []), current=None if save_path else f.get("current"),
                               tree=None, game_dir=game_dir, user_dir=user_dir, no_names=False, loc=None,
                               dlc_unknown=False)
        p = hoi4_focus.plan(args)
    except Exception as e:                          # FP1 is a helper here: never let it stop the snapshot
        return {"error": f"{type(e).__name__}: {e}"}
    out = []
    for s in p.get("startable", []):
        cond = s.get("available") if s.get("available_ok") is None else None
        out.append([s["id"], s["name"], s["days"],
                    (cond[:FOCUS_IF] + ("..." if len(cond) > FOCUS_IF else "")) if cond else None,
                    s.get("will_lead_to_war_with") or None, len(s.get("opens") or []) or None])
    return {"current_name": p.get("current_name"),
            "can_start": {"columns": ["id", "name", "days", "if (the game decides)", "war_with", "opens"],
                          "rows": out}}


def snapshot(save, tag=None, enemies=None, game=None, focus=True, user_dir=None, timing=None):
    """SR1's extract() of `save` (a path or bytes) with what the slices need added: "wars", "control", "air",
    "air_superiority", "faction", "game" (tables from the game's files) and "focus_options" (FP1, when focus and
    game). enemies: the countries whose divisions to read (default: every country at war with us)."""
    clock = [time.perf_counter()]

    def lap(name):
        now = time.perf_counter()
        if timing is not None:
            timing[name] = round(now - clock[0], 3)
        clock[0] = now

    path = None
    if isinstance(save, (bytes, bytearray)):
        data = bytes(save)
    else:
        path, data = Path(save), H.read_save(save)
    if tag is None:
        m = re.search(rb'\nplayer\s*=\s*"([^"]+)"', data[:65536])
        tag = m.group(1).decode() if m else None
    wars = read_wars(data, tag) if tag else []
    lap("wars")
    units = list(enemies) if enemies is not None else [w["enemy"] for w in wars]
    snap = H.extract(data, tag=tag, units=units, game=game)
    if path:
        snap["save"]["file"] = path.name
    lap("extract")
    snap["wars"] = wars
    snap.update(read_extras(data, snap["tag"]))
    lap("extras")
    tables = game_tables(game)
    if tables:
        ideas = snap["politics"]["ideas"]
        tag_ = snap["tag"]

        def switchable(name, cost):
            """A law a player can pick: it has a price, and it is not another country's own (ETH_, SWI_)."""
            m = re.match(r"([A-Z][A-Z0-9]{2})_", name)
            return cost is not None and (not m or m.group(1) == tag_)
        law_opts = {c: [k for k, v in tables["ideas"].items() if v[0] == c and switchable(k, v[1])]
                    for c in ("economy", "trade_laws", "mobilization_laws")}
        keys = set(ideas) | {k for v in law_opts.values() for k in v}
        snap["game"] = {"ideas": {i: tables["ideas"].get(i, (None, None)) for i in keys},
                        "law_categories": tables["laws"], "advisor_slots": {i: tables["advisors"][i] for i in ideas
                                                                           if i in tables["advisors"]},
                        "law_options": law_opts, "shared_buildings": tables["shared_buildings"],
                        "provincial_buildings": tables["provincial_buildings"],
                        "state_slots": tables["state_slots"], "names": localise(game, keys)}
        lap("game_files")
    if focus and game:
        snap["focus_options"] = _focus_options(path, snap, game, user_dir or H.DEFAULT_USER_DIR)
        lap("focus")
    return snap


# --------------------------------------------------------------------------------------------- the bridge

_CB = re.compile(r"@CB;(.*)$")
_LOG_DATE = re.compile(r"^\[\d\d:\d\d:\d\d\]\[(\d+\.\d+\.\d+\.\d+)\]")
_SINGLE = ("country", "politics", "industry", "territory", "resources", "army", "war", "day")
_MANY = ("equip", "enemy", "ally", "general", "front", "major", "neighbor")
_TEXT_FIELDS = {"tag", "name", "ideology", "party", "leader", "faction", "type", "state"}


def _value(key, v):
    if not isinstance(v, str) or key in _TEXT_FIELDS:
        return v
    try:
        f = float(v.replace(",", ""))
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else f


def _record(line):
    """One @CB log line as a dict (kind, date, fields), as hoi4.parse_cb reads it, or None."""
    m = _CB.search(line)
    if not m:
        return None
    parts = m.group(1).split(";")
    d = _LOG_DATE.match(line)
    rec = {"kind": parts[0], "date": d.group(1) if d else ""}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            rec["_" + k if k in rec else k] = v.strip()
    return rec


def parse_bridge(source):
    """The bridge's last report grouped by kind: {"politics": {...}, "enemy": [{...}], ..., "day": {...}}, numbers
    as numbers. source: None, a grouped dict (returned cleaned), a list of records (dicts with "kind", as
    hoi4.records() gives them), or log text / lines (the last complete rep_begin..rep_end block is used, plus the
    last daily heartbeat)."""
    if not source:
        return {}
    if isinstance(source, dict):
        out = {}
        for k, v in source.items():
            if isinstance(v, list):
                out[k] = [{f: _value(f, x) for f, x in r.items()} for r in v if isinstance(r, dict)]
            elif isinstance(v, dict):
                out[k] = {f: _value(f, x) for f, x in v.items()}
        return out
    if isinstance(source, str):
        source = source.splitlines()
    recs = [r for r in (_record(x) if isinstance(x, str) else x for x in source) if isinstance(r, dict) and
            r.get("kind")]
    end = next((i for i in range(len(recs) - 1, -1, -1) if recs[i]["kind"] == "rep_end"), None)
    start = next((i for i in range(end, -1, -1) if recs[i]["kind"] == "rep_begin"), None) if end is not None else None
    block = recs[start:end + 1] if start is not None else [r for r in recs if r["kind"] not in ("rep_begin", "rep_end")]
    out = {}
    for r in block:
        k = r["kind"]
        fields = {f: _value(f, v) for f, v in r.items() if f not in ("kind", "clock")}
        if k in _MANY:
            out.setdefault(k, []).append(fields)
        elif k in _SINGLE and k not in out:
            out[k] = fields
    day = next((r for r in reversed(recs) if r["kind"] == "day"), None)
    if day:
        out["day"] = {f: _value(f, v) for f, v in day.items() if f not in ("kind", "clock")}
    return out


def _strip(rec, *drop):
    return {k: v for k, v in (rec or {}).items() if k not in ("date",) + drop}


# --------------------------------------------------------------------------------------------- the slices

def slug(text):
    """"German Theater 1" -> "german_theater_1" (an agent name part, docs/orders.md)."""
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _clean(v):
    """Drop None, empty lists and empty dicts, recursively (keeps 0 and False)."""
    if isinstance(v, dict):
        out = {k: _clean(x) for k, x in v.items()}
        return {k: x for k, x in out.items() if x is not None and x != [] and x != {}}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _n(v, nd=0):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return v
    v = round(v, nd)
    return int(v) if nd == 0 or float(v).is_integer() else v


def _table(records, columns):
    """{"columns", "rows"} from a list of dicts: a column every row leaves empty is dropped. {} for no rows."""
    records = [r for r in records if isinstance(r, dict)]
    if not records:
        return {}
    cols = [c for c in columns if any(r.get(c) not in (None, "") for r in records)]
    return {"columns": cols, "rows": [[r.get(c) if r.get(c) != "" else None for c in cols] for r in records]}


def _ikeys(d):
    return {int(k): v for k, v in (d or {}).items()}


def visible(snap, world=None):
    """(ours, seen, controller): the provinces we control or stand in; those plus every province next to one of
    them; and a function giving any province's controller (None if unknown)."""
    tag = snap["tag"]
    ctl = snap.get("control") or {}
    owners, overrides = _ikeys(ctl.get("state_owner")), _ikeys(ctl.get("province_controller"))
    ours = {p for p, t in overrides.items() if t == tag}
    if world:
        own_states = {sid for sid, t in owners.items() if t == tag} or {s["id"] for s in snap.get("states", [])
                                                                         if isinstance(s.get("id"), int)}

        def controller(p):
            if p in overrides:
                return overrides[p]
            return owners.get(world.state_of.get(p)) or (tag if world.state_of.get(p) in own_states else None)
        for sid in own_states:
            ours |= {p for p in world.provinces_of.get(sid, ()) if p not in overrides}
    else:
        def controller(p):
            return overrides.get(p)
    ours |= {d["location"] for d in snap.get("divisions", []) if isinstance(d.get("location"), int)}
    seen = ours | (world.ring(ours) if world else set())
    return ours, seen, controller


class _Ctx:
    """What every slice builder shares: the snapshot, the bridge report, the map and the fog of war."""

    def __init__(self, snap, bridge, world, field_marshals, operations):
        self.snap, self.b, self.world = snap, bridge, world
        self.tag, self.date = snap["tag"], snap["save"].get("date")
        self.ours, self.seen, self.controller = visible(snap, world)
        self.names = (snap.get("game") or {}).get("names", {})
        # Enemy divisions the player can see: inside or next to our provinces. Nothing else of theirs is used.
        self.enemy_units = [(t, u) for t, units in (snap.get("units") or {}).items() for u in units
                            if u.get("location") in self.seen]
        self.armies = {a["name"]: a for a in snap.get("armies", []) if a.get("name")}
        self.divs_of = {}
        for d in snap.get("divisions", []):
            self.divs_of.setdefault(d.get("army"), []).append(d)
        self.legend = {}
        self.fms = self._field_marshals(field_marshals)
        self.ops = self._operations(operations)

    def _expand(self, names):
        """Army names for a list of army or army-group names ("army 3" matches "Army 3"); and those not found."""
        by_lower = {n.lower(): n for n in self.armies}
        groups = {}
        for a in self.armies.values():
            if a.get("group"):
                groups.setdefault(a["group"].lower(), []).append(a["name"])
        out, missing = [], []
        for n in names or []:
            k = str(n).strip().lower()
            hit = [by_lower[k]] if k in by_lower else groups.get(k)
            if hit:
                out += [h for h in hit if h not in out]
            else:
                missing.append(n)
        return out, missing

    def _field_marshals(self, given):
        if given is None:
            given = {}
            for a in self.armies.values():
                if a.get("group"):
                    given.setdefault("field_marshal_" + (slug(a["group"]) or "group"), []).append(a["name"])
        out = {}
        for name, forces in given.items():
            name = name if name.startswith("field_marshal_") else "field_marshal_" + slug(name)
            out[name] = self._expand(forces if isinstance(forces, (list, tuple)) else [forces])
        return out

    def _operations(self, given):
        if not given:
            return {}
        items = given.items() if isinstance(given, dict) else ((c.get("name"), c) for c in given)
        out = {}
        for name, charter in items:
            if not name:
                continue
            name = name[len("operation_"):] if name.startswith("operation_") else name
            out["operation_" + slug(name)] = (charter, self._expand(charter.get("forces", [])))
        return out

    def name(self, key):
        return self.names.get(key, key)

    def state_of(self, p):
        return self.world.state_name(p) if self.world else None

    def base(self, agent):
        return {"agent": agent, "date": self.date, "tag": self.tag}

    # ---- shared pieces

    def enemies(self, tags=None):
        """The bridge's per-country figures for our enemies (what diplomacy shows), else the wars from the save,
        as a table."""
        rows = [_strip(e) for e in self.b.get("enemy", [])]
        since = {w["enemy"]: w["since"] for w in self.snap.get("wars", [])}
        if not rows:
            rows = [{"tag": t} for t in since]
        for r in rows:
            if r.get("tag") in since:
                r["since"] = since[r["tag"]]
        return _table([r for r in rows if tags is None or r.get("tag") in tags],
                      ("tag", "name", "divs", "mil", "civ", "surrender", "since"))

    def tid(self, template):
        """A template's index in the slice's "templates" list (unit rows name templates by index)."""
        if template not in self.legend:
            self.legend[template] = len(self.legend)
        return self.legend[template]

    def units(self, divisions):
        """Our divisions by state: {state: [[template, province, strength, org, moving_to, in_combat], ...]}."""
        out = {}
        for d in divisions:
            st = d.get("state") or self.state_of(d.get("location")) or "?"
            out.setdefault(str(st), []).append([self.tid(d.get("template")), d.get("location"), _n(d.get("strength")),
                                                _n(d.get("org")), d.get("moving_to"), 1 if d.get("in_combat") else 0])
        return out

    def army_rows(self, names):
        out = []
        for n in names:
            a = self.armies.get(n, {})
            divs = self.divs_of.get(n, [])
            org = [d["org"] for d in divs if isinstance(d.get("org"), (int, float))]
            strength = [d["strength"] for d in divs if isinstance(d.get("strength"), (int, float))]
            ld = a.get("leader") or {}
            out.append({"name": n, "group": a.get("group"),
                        "leader": {k: ld.get(k) for k in ("name", "skill", "attack", "defense", "planning",
                                                          "logistics", "traits")} if ld else None,
                        "divisions": len(divs), "in_combat": sum(1 for d in divs if d.get("in_combat")),
                        "moving": sum(1 for d in divs if d.get("moving_to")),
                        "avg_org": _n(sum(org) / len(org), 1) if org else None,
                        "avg_strength": _n(sum(strength) / len(strength)) if strength else None,
                        "units": self.units(divs)})
        return out

    def enemy_near(self, provinces):
        """Visible enemy divisions in or next to these provinces: {country: {state: [[template, province,
        strength, org], ...]}}."""
        near = set(provinces) | (self.world.ring(provinces) if self.world else set())
        out = {}
        for t, u in self.enemy_units:
            if u.get("location") in near:
                st = str(self.state_of(u["location"]) or "?")
                out.setdefault(t, {}).setdefault(st, []).append([self.tid(u.get("template")), u["location"],
                                                                 _n(u.get("strength")), _n(u.get("org"))])
        return out

    def fronts_near(self, provinces):
        """The fronts with a province among or next to these: [{"against", "states", "provinces"}]."""
        near = set(provinces) | (self.world.ring(provinces) if self.world else set())
        out = []
        for f in self.snap.get("fronts", []):
            provs = f.get("provinces") or []
            if near & set(provs):
                out.append(self.front_row(f))
        return out

    def front_row(self, f):
        provs = f.get("provinces") or []
        states = sorted({str(s) for s in (self.state_of(p) for p in provs) if s is not None})
        return {"against": f.get("enemies"), "states": states, "provinces": provs}


def _policy(c):
    s, b = c.snap, c.b
    pol, game = s["politics"], s.get("game") or {}
    ideas = game.get("ideas", {})
    law_cats = set(game.get("law_categories", []))
    laws, advisors, spirits, unknown = {}, [], [], []
    for i in pol.get("ideas", []):
        cat = (ideas.get(i) or (None, None))[0]
        if cat == "hidden_ideas":
            continue                                  # the player never sees these
        if cat in law_cats:
            laws[cat] = c.name(i)
        elif i in game.get("advisor_slots", {}) or cat in _DESIGNER_SLOTS:
            advisors.append({"name": c.name(i), "slot": game.get("advisor_slots", {}).get(i, cat)})
        elif cat:
            spirits.append(c.name(i))
        else:
            unknown.append(i)
    options = {cat: [[c.name(k), (ideas.get(k) or (None, None))[1]] for k in names]
               for cat, names in game.get("law_options", {}).items()}
    p, ctry = b.get("politics", {}), b.get("country", {})
    fo = s.get("focus_options") or {}
    focus = {"current": fo.get("current_name") or s["focus"].get("current"), "progress": s["focus"].get("progress"),
             "paused": s["focus"].get("paused") or None, "completed": len(s["focus"].get("completed") or []),
             "can_start": fo.get("can_start"), "error": fo.get("error")}
    faction = dict(s.get("faction") or {})
    if ctry.get("faction"):
        faction["name"] = ctry["faction"]
    out = c.base("policy")
    out.update({
        "country": _strip(ctry), "political_power": pol.get("political_power"), "pp_per_day": p.get("ppd"),
        "stability": pol.get("stability"), "war_support": pol.get("war_support"),
        "ruling_party": pol.get("ruling_party"), "popularity": pol.get("popularity"),
        "election_in_days": p.get("election_days") if (p.get("election_days") or 0) > 0 else None,
        "focus": focus, "laws": laws, "law_options": options, "advisors": advisors, "spirits": spirits,
        "ideas_unread": unknown, "wars": c.enemies(), "war": _strip(b.get("war")), "faction": faction or None,
        "allies": _table(b.get("ally", []), ("tag", "name", "divs", "mil", "surrender")),
        "majors": _table(b.get("major", []), ("tag", "name", "ideology", "faction", "divs", "mil", "civ", "surrender")),
        "neighbors": _table(b.get("neighbor", []), ("tag", "name", "ideology", "faction", "divs", "mil")),
        "territory": _strip(b.get("territory"))})
    return out


def _research(c):
    r = c.snap["research"]
    out = c.base("research")
    out.update({"year": int(c.date.split(".")[0]) if c.date else None, "slots": r.get("slots"),
                "free": r.get("free"), "saved_points": r.get("saved_points"),
                "running": [{k: x.get(k) for k in ("tech", "days_left", "per_day", "years_ahead")}
                            for x in r.get("running", [])],
                "researched": r.get("researched")})
    return out


def _factories(c, *keys):
    ind = c.b.get("industry", {})
    return {k: ind.get(k) for k in keys} or None


def _civilian(c):
    s, game = c.snap, c.snap.get("game") or {}
    shared, slots = set(game.get("shared_buildings", [])), game.get("state_slots", {})
    provincial = set(game.get("provincial_buildings", [])) or {"rail_way", "supply_node", "bunker", "coastal_bunker",
                                                               "naval_base", "radar_station"}
    queued, repairs = {}, {}
    rows = []
    for q in s.get("construction", []):
        what = q.get("building")
        if what in provincial:                        # SR1 names a state; these are built in a province
            where = c.state_of(q.get("state")) or q.get("state")
        else:
            where = q.get("state_name") or q.get("state")
        if not q.get("levels"):                       # amount=0: the game's own repair of a damaged building
            r = repairs.setdefault(what, [0, 0])
            r[0] += 1
            r[1] += 1 if q.get("factories") else 0
            continue
        if what in shared:
            queued[q.get("state")] = queued.get(q.get("state"), 0) + q["levels"]
        rows.append([what, where, q.get("levels"), _n(q.get("factories")), q.get("progress"), q.get("days_left")])
    states = []
    for st in s.get("states", []):
        bl = st.get("buildings") or {}
        used = sum(v for k, v in bl.items() if k in shared and isinstance(v, (int, float)))
        base = slots.get(st.get("category"))
        states.append([st.get("name") or st.get("id"), st.get("category"), base, _n(used),
                       queued.get(st.get("id"), 0), None if base is None else _n(base - used - queued.get(st.get("id"), 0)),
                       bl.get("infrastructure"), bl.get("air_base")])
    ind = c.b.get("industry", {})
    out = c.base("civilian_industry")
    out.update({
        "factories": {"civilian": ind.get("civ"), "civilian_free": ind.get("civ_free"), "military": ind.get("mil"),
                      "dockyards": ind.get("nav")},
        "construction": {"columns": ["building", "state", "levels", "factories", "progress", "days_left"],
                         "rows": rows},
        "repairs": {k: {"queued": v[0], "with_factories": v[1]} for k, v in sorted(repairs.items())},
        "states": {"columns": ["state", "category", "slots", "used", "queued", "free", "infrastructure", "air_base"],
                   "note": "slots from the state category, before modifiers", "rows": states},
        "resources": _strip(c.b.get("resources")), "fuel_k": ind.get("fuel_k"), "max_fuel_k": ind.get("max_fuel_k")})
    return out


def _lines(c, kind):
    rows, n = [], 0
    for ln in c.snap.get("production", []):
        if ln.get("kind") != kind:
            continue
        n += 1
        if kind == "military":
            rows.append([n, ln.get("equipment"), ln.get("variant"), _n(ln.get("factories")), ln.get("efficiency"),
                         ln.get("per_day"), ln.get("priority"), ln.get("amount")])
        else:
            rows.append([n, ln.get("equipment"), ln.get("variant"), _n(ln.get("factories")), ln.get("progress"),
                         ln.get("days_to_next"), ln.get("priority"), ln.get("amount")])
    return rows


def _stock(c, naval):
    rows = []
    for e in c.b.get("equip", []):
        if (e.get("type") == "convoy") != naval:
            continue
        stock, fielded, target = (e.get(k) or 0 for k in ("stock", "fielded", "target"))
        if stock or fielded or target:
            short = max(0, target - fielded) if isinstance(target, (int, float)) and isinstance(fielded, (int, float)) else None
            rows.append([e.get("type"), stock, fielded, target, short])
    return {"columns": ["equipment", "stock", "in_units", "wanted", "short"], "rows": rows}


def _military(c):
    ind = c.b.get("industry", {})
    out = c.base("military_industry")
    out.update({"factories": {"military": ind.get("mil"), "military_free": ind.get("mil_free")},
                "lines": {"columns": ["line", "equipment", "variant", "factories", "efficiency", "per_day", "priority",
                                      "amount"], "rows": _lines(c, "military")},
                "stockpile": _stock(c, naval=False), "resources": _strip(c.b.get("resources"))})
    return out


def _naval_industry(c):
    ind = c.b.get("industry", {})
    ships = {}
    for f in c.snap.get("fleets", []):
        for tf in f.get("task_forces", []):
            for k, v in (tf.get("ships") or {}).items():
                ships[k] = ships.get(k, 0) + v
    out = c.base("naval_industry")
    out.update({"dockyards": {"total": ind.get("nav"), "free": ind.get("nav_free")},
                "lines": {"columns": ["line", "equipment", "variant", "dockyards", "progress", "days_to_next",
                                      "priority", "amount"], "rows": _lines(c, "naval")},
                "convoys": _stock(c, naval=True), "ships_afloat": ships,
                "resources": _strip(c.b.get("resources"))})
    return out


def _front_regions(c):
    """{region id: [enemies]} for the strategic regions our fronts run through."""
    out = {}
    if not c.world:
        return out
    for f in c.snap.get("fronts", []):
        for p in f.get("provinces") or []:
            rid = c.world.region_of.get(p)
            if rid is not None:
                out.setdefault(rid, set()).update(f.get("enemies") or [])
    return out


def _air(c):
    s = c.snap
    air = s.get("air") or {}
    bases = _ikeys(air.get("bases"))
    sup = _ikeys(s.get("air_superiority"))
    state_name = {st["id"]: st.get("name") for st in s.get("states", [])}
    names = c.world.state_names if c.world else {}

    def base_name(bid):
        b = bases.get(bid) or {}
        if b.get("carrier"):
            return "carrier"
        sid = b.get("state")
        return state_name.get(sid) or names.get(sid) or sid

    planes_at = {}
    wings = []
    for w in air.get("wings", []):
        planes_at[w.get("base")] = planes_at.get(w.get("base"), 0) + (w.get("planes") or 0)
        rid = w.get("region")
        wings.append([w.get("name"), w.get("type"), w.get("planes"), base_name(w.get("base")), w.get("mission"),
                      c.world.region_name(rid) if (c.world and rid is not None) else rid, w.get("effectiveness")])
    own = {st["id"] for st in s.get("states", [])}
    base_rows = []
    for bid, b in sorted(bases.items()):
        if b.get("carrier") or not (bid in planes_at or b.get("state") in own):
            continue
        base_rows.append([base_name(bid), b.get("level"), b.get("capacity"), planes_at.get(bid, 0)])
    regions = []
    fr = _front_regions(c)
    used = {w.get("region") for w in air.get("wings", []) if w.get("region") is not None}
    for rid in sorted(set(fr) | used):
        row = {"region": c.world.region_name(rid) if c.world else rid,
               "front_against": sorted(fr.get(rid, ())) or None}
        if rid in sup:
            row["superiority"] = sup[rid]
        regions.append(row)
    out = c.base("air")
    out.update({"wings": {"columns": ["name", "type", "planes", "base", "mission", "region", "effectiveness"],
                          "rows": wings},
                "bases": {"columns": ["state", "level", "capacity", "planes"], "rows": base_rows},
                "regions": regions, "read": air != {}})
    return out


def _navy(c):
    fleets = []
    for f in c.snap.get("fleets", []):
        tfs = []
        for tf in f.get("task_forces", []):
            loc = tf.get("location")
            where = c.world.region_name(c.world.region_of[loc]) if (c.world and loc in c.world.region_of) else None
            tfs.append({"name": tf.get("name"), "at": where or c.state_of(loc) or loc, "province": loc,
                        "mission": tf.get("mission"), "ships": tf.get("ships"), "strength": _n(tf.get("strength")),
                        "org": tf.get("org")})
        hb = f.get("home_base")
        fleets.append({"name": f.get("name"), "home_base": c.state_of(hb) or hb, "task_forces": tfs})
    out = c.base("navy")
    out.update({"fleets": fleets, "convoys": _stock(c, naval=True), "wars": [r[0] for r in c.enemies().get("rows", [])]})
    return out


def _army(c):
    s, b = c.snap, c.b
    by_army = {}
    for d in s.get("divisions", []):
        a = d.get("army") or "(no army)"
        by_army.setdefault(a, {})
        by_army[a][d.get("template")] = by_army[a].get(d.get("template"), 0) + 1
    armies = []
    for a in s.get("armies", []):
        ld = a.get("leader") or {}
        armies.append({"name": a.get("name"), "group": a.get("group"),
                       "leader": f"{ld.get('name')} (skill {ld.get('skill')})" if ld else None,
                       "divisions": a.get("divisions")})
    grouped = {}                                      # the queue repeats one line per order: group them
    for t in s.get("training", []):
        key = (t.get("template"), c.state_of(t.get("location")) or t.get("location"))
        g = grouped.setdefault(key, [0, 0, 0, None])
        batches = t.get("training", [])
        g[0] += 1
        g[1] += t.get("queued") or 0
        g[2] += sum(x.get("divisions") or 0 for x in batches)
        done = [x["progress"] for x in batches if isinstance(x.get("progress"), (int, float))]
        if done:
            g[3] = max(done) if g[3] is None else max(g[3], max(done))
    training = [[k[0], k[1]] + v for k, v in grouped.items()]
    short = [[r[0], r[4]] for r in _stock(c, naval=False)["rows"] if r[4]]
    out = c.base("army")
    out.update({
        "manpower": _strip(b.get("army")), "command_power": s["politics"].get("command_power"),
        "divisions_by_army": by_army, "armies": armies,
        "field_marshals": {k: v[0] for k, v in c.fms.items()},
        "templates": [{k: t.get(k) for k in ("name", "regiments", "support", "divisions")}
                      for t in s.get("templates", [])],
        "training": {"columns": ["template", "deploy_to", "lines", "queued", "in_training", "best_progress"],
                     "rows": training},
        "equipment_short": short, "enemies": c.enemies(),
        "fronts": [dict(c.front_row(f), provinces=len(f.get("provinces") or [])) for f in s.get("fronts", [])]})
    return out


def _command(c, agent, armies, extra):
    """A field marshal's or an operation's slice: only its armies, their fronts, the enemy next to them."""
    c.legend = {}
    divs = [d for a in armies for d in c.divs_of.get(a, [])]
    provs = {d["location"] for d in divs if isinstance(d.get("location"), int)}
    fronts = c.fronts_near(provs)
    zone = provs | {p for f in fronts for p in f["provinces"]}
    rows = c.army_rows(armies)
    seen = c.enemy_near(zone)
    against = {t for f in fronts for t in (f["against"] or [])} | set(seen)
    out = c.base(agent)
    out.update(extra)
    out.update({"templates": list(c.legend),
                "unit_columns": ["template (index in templates)", "province", "strength", "org", "moving_to",
                                 "in_combat"],
                "enemy_columns": ["template (index in templates)", "province", "strength", "org"],
                "armies": rows, "fronts": fronts, "enemy_seen": seen, "enemy_totals": c.enemies(against)})
    return out, provs


def _field_marshal(c, agent):
    armies, missing = c.fms[agent]
    ops = sorted(k for k, (ch, _) in c.ops.items() if ch.get("by") == agent)
    out, _ = _command(c, agent, armies, {"operations": ops, "unknown_forces": missing})
    return out


def _operation(c, agent):
    charter, (armies, missing) = c.ops[agent]
    keep = ("goal", "forces", "success", "abort", "deadline", "by")
    out, provs = _command(c, agent, armies, {"charter": {k: charter.get(k) for k in keep},
                                             "unknown_forces": missing})
    if c.world:
        around = sorted(c.world.ring(provs))
        out["around_columns"] = ["province", "state", "controller", "terrain"]
        out["around"] = [[p, c.state_of(p), c.controller(p), c.world.terrain.get(p)] for p in around
                         if c.world.kind.get(p, "land") == "land"]
    return out


_BUILDERS = {"policy": _policy, "research": _research, "civilian_industry": _civilian,
             "military_industry": _military, "naval_industry": _naval_industry, "air": _air, "navy": _navy,
             "army": _army}


def slices(snap, bridge_state=None, world=None, field_marshals=None, operations=None, agents=None, timing=None):
    """{agent: slice} for every agent (or only `agents`). snap: snapshot() or SR1's extract(); bridge_state: see
    parse_bridge; world: a MapData. field_marshals: {agent or group name: [army or army-group names]} (default:
    one per army group). operations: {name: charter} or [charter] with "name" (the operation.start fields).
    timing: a dict to fill with seconds per slice."""
    c = _Ctx(snap, parse_bridge(bridge_state), world, field_marshals, operations)
    out = {}
    names = list(AGENTS) + sorted(c.fms) + sorted(c.ops)
    for name in names:
        if agents and name not in agents:
            continue
        t = time.perf_counter()
        if name in _BUILDERS:
            sl = _BUILDERS[name](c)
        elif name in c.fms:
            sl = _field_marshal(c, name)
        else:
            sl = _operation(c, name)
        out[name] = _clean(sl)
        if timing is not None:
            timing[name] = round(time.perf_counter() - t, 4)
    return out


def sizes(out):
    """{agent: characters of its compact JSON}."""
    return {k: len(json.dumps(v, separators=(",", ":"), ensure_ascii=False)) for k, v in out.items()}


# --------------------------------------------------------------------------------------------- the CLI

def _load_bridge(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", help="a text save (.hoi4); only read")
    ap.add_argument("--tag", help="the country (default: the save's player)")
    ap.add_argument("--bridge", help="the bridge's report: JSON (records or grouped by kind) or game.log text")
    ap.add_argument("--agent", action="append", help="only this slice (repeatable)")
    ap.add_argument("--operations", help="a JSON file of running operations: {name: charter} or [charter]")
    ap.add_argument("--field-marshals", help="a JSON file: {field marshal: [army or army-group names]}")
    ap.add_argument("--game-dir", help=f"the game folder (default {H.DEFAULT_GAME_DIR})")
    ap.add_argument("--user-dir", help="the folder with dlc_load.json and mod/")
    ap.add_argument("--no-mods", action="store_true", help="read the game's files without the enabled mods")
    ap.add_argument("--no-focus", action="store_true", help="skip FP1's focus list (about 2 s)")
    ap.add_argument("--cache", default=str(DEFAULT_CACHE), help="the map cache file ('' for none)")
    ap.add_argument("--sizes", action="store_true", help="print each slice's size and build time instead")
    ap.add_argument("--indent", type=int, default=None, help="pretty-print the JSON")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        timing = {}
        t0 = time.perf_counter()
        game = H.GameData.load(args.game_dir, args.user_dir, mods=not args.no_mods)
        t = time.perf_counter()
        world = MapData.load(game, cache=args.cache or None)
        timing["map"] = round(time.perf_counter() - t, 3)
        snap = snapshot(args.save, tag=args.tag.upper() if args.tag else None, game=game, focus=not args.no_focus,
                        user_dir=args.user_dir, timing=timing)
        bridge = _load_bridge(args.bridge) if args.bridge else None
        ops = json.loads(Path(args.operations).read_text(encoding="utf-8")) if args.operations else None
        fms = json.loads(Path(args.field_marshals).read_text(encoding="utf-8")) if args.field_marshals else None
        per = {}
        out = slices(snap, bridge, world, field_marshals=fms, operations=ops, agents=args.agent, timing=per)
        total = time.perf_counter() - t0
    except (H.SaveFormatError, MapError, OSError, ValueError) as e:
        print(f"hoi4_slices: {e}", file=sys.stderr)
        return 2
    if args.sizes:
        print(f"{'slice':<34}{'chars':>8}{'ms':>8}")
        for k, n in sizes(out).items():
            print(f"{k:<34}{n:>8,}{per[k] * 1000:>8.1f}" + ("   over the aim" if n > SIZE_AIM else ""))
        print("setup (s): " + ", ".join(f"{k} {v}" for k, v in timing.items()) + f"; total {total:.2f}")
        if world is None:
            print("no map: enemy divisions only inside our own provinces")
        return 0
    one = len(out) == 1 and args.agent
    print(json.dumps(next(iter(out.values())) if one else out, indent=args.indent, ensure_ascii=False,
                     separators=None if args.indent is not None else (",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

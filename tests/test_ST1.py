r"""ST1: the state slicer (hoi4_slices.py) on SR1's handmade save, a handmade bridge report and a tiny handmade map.

Standard library only, no game and no Windows needed:  python tests/test_ST1.py

The map is drawn below as text and written out as the game's three map files (a 14x3 pixel provinces.bmp,
definition.csv, adjacencies.csv) in a temporary game folder, next to SR1's handmade game files.
"""
import contextlib
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_save as H  # noqa: E402
import hoi4_slices as L  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
SMALL = FIX / "sr1_small.txt"

# One cell per pixel. AAA holds state 1 (10-13); BBB holds state 2 (20-23); 30 is the sea. The map wraps east-west,
# so 12 touches 23 and 13 touches 30 across the edge. Our divisions stand in 10, 11 and 20 (SR1's save).
GRID = [
    "12 12 11 11 10 10 20 20 22 22 21 21 23 23",
    "12 12 11 11 10 10 20 20 22 22 21 21 23 23",
    "13 13 30 30 30 30 30 30 30 30 30 30 30 30",
]
KIND = {10: "land", 11: "land", 12: "land", 13: "land", 20: "land", 21: "land", 22: "land", 23: "land", 30: "sea"}
TERRAIN = {10: "plains", 11: "forest", 12: "hills", 13: "plains", 20: "plains", 21: "urban", 22: "forest",
           23: "marsh", 30: "ocean"}
# A strait from 12 to 22, and the coast of 13 closed to the sea.
ADJACENCIES = ("From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment\n"
               "12;22;sea;30;-1;-1;-1;-1;;Test strait\n"
               "13;30;impassable;-1;-1;-1;-1;-1;;Test cliffs\n"
               "-1;-1;;-1;-1;-1;-1;-1;-1;\n")


def color(pid):
    return (pid * 7 % 256, 100, 200 - pid)


def write_bmp(path, grid):
    """A 24-bit bottom-up BMP, each row padded to 4 bytes, as the game's provinces.bmp is."""
    rows = [[int(c) for c in line.split()] for line in grid]
    w, h = len(rows[0]), len(rows)
    stride = (w * 3 + 3) & ~3
    body = b""
    for r in reversed(rows):
        line = b"".join(bytes((b, g, rr)) for rr, g, b in (color(p) for p in r))
        body += line + b"\x00" * (stride - len(line))
    head = b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    Path(path).write_bytes(head + info + body)


FILES = {
    "history/states/1-Nordland.txt": "state={\n\tid=1\n\tname=\"STATE_1\"\n\tstate_category = city\n"
                                     "\tprovinces={\n\t\t10 11 12 13\n\t}\n}\n",
    "history/states/2-Suedland.txt": "state={\n\tid=2\n\tname=\"STATE_2\"\n\tprovinces={\n\t\t20 21 22 23\n\t}\n}\n",
    "map/strategicregions/1-Testland.txt": "strategic_region={\n\tid=1\n\tname=\"STRATEGICREGION_1\"\n"
                                           "\tprovinces={\n\t\t10 11 12 13\n\t}\n}\n",
    "map/strategicregions/2-Ostland.txt": "strategic_region={\n\tid=2\n\tname=\"STRATEGICREGION_2\"\n"
                                          "\tprovinces={\n\t\t20 21 22 23\n\t}\n}\n",
    "map/strategicregions/3-Test Sea.txt": "strategic_region={\n\tid=3\n\tname=\"STRATEGICREGION_3\"\n"
                                           "\tprovinces={ 30 }\n\tweather={ period={ between={ 0.0 30.0 } } }\n}\n",
    "localisation/english/st1_test_l_english.yml": (
        "﻿l_english:\n STRATEGICREGION_1:0 \"Testland\"\n STRATEGICREGION_2: \"Ostland\"\n"
        " STRATEGICREGION_3:0 \"Test Sea\" # a comment\n war_economy:0 \"War Economy\"\n"
        " civilian_economy:0 \"Civilian Economy\"\n AAA_spirit:0 \"Test Spirit\"\n hans_advisor:0 \"Hans the $WHO$\"\n"
        " WHO:0 \"Advisor\"\n AAA_fourth:0 \"The Fourth\"\n"),
    "common/ideas/_laws.txt": (
        "ideas = {\n\teconomy = {\n\t\tlaw = yes\n\t\tcivilian_economy = { cost = 150 }\n"
        "\t\twar_economy = { cost = 150 }\n\t\tisolation = { allowed = { always = no } }\n\t}\n"
        "\tmobilization_laws = {\n\t\tlaw = yes\n\t\textensive_conscription = { cost = 150 }\n"
        "\t\tETH_chitet_law = { cost = 150 }\n\t}\n\tcountry = {\n\t\tAAA_spirit = { }\n\t}\n"
        "\thidden_ideas = {\n\t\tAAA_secret = { }\n\t}\n\tindustrial_concern = {\n\t\ttest_works = { cost = 150 }\n"
        "\t}\n}\n"),
    "common/ideas/broken.txt": "ideas = {\n\tcountry = {\n\t\tbroken_idea = { }\n",
    "common/characters/AAA.txt": ("characters = {\n\tAAA_hans = {\n\t\tadvisor = {\n\t\t\tslot = political_advisor\n"
                                  "\t\t\tidea_token = hans_advisor\n\t\t\tcost = 150\n\t\t}\n\t}\n}\n"),
    "common/buildings/00_buildings.txt": (
        "buildings = {\n\tindustrial_complex = {\n\t\tlevel_cap = { shares_slots = yes }\n\t}\n"
        "\tarms_factory = {\n\t\tlevel_cap = { shares_slots = yes }\n\t}\n"
        "\tinfrastructure = {\n\t\tlevel_cap = { state_max = 5 }\n\t}\n"
        "\trail_way = {\n\t\tlevel_cap = { province_max = 1 }\n\t}\n}\n"),
    "common/state_category/city.txt": "state_categories = {\n\tcity = {\n\t\tlocal_building_slots = 6\n\t}\n}\n",
    "common/national_focus/aaa.txt": (
        "focus_tree = {\n\tid = aaa_focus\n\tcountry = { factor = 0 modifier = { add = 10 tag = AAA } }\n"
        "\tfocus = { id = AAA_first cost = 5 }\n"
        "\tfocus = { id = AAA_second prerequisite = { focus = AAA_first } cost = 5 }\n"
        "\tfocus = { id = AAA_third prerequisite = { focus = AAA_second } cost = 10 }\n"
        "\tfocus = { id = AAA_fourth prerequisite = { focus = AAA_second } cost = 7\n"
        "\t\tavailable = { has_war_with = BBB }\n\t}\n"
        "\tfocus = { id = AAA_fifth prerequisite = { focus = AAA_third } cost = 7 }\n}\n"),
}


def make_game():
    """A temporary game folder: SR1's handmade game files, the map above, and the files ST1 reads. No mods."""
    tmp = Path(tempfile.mkdtemp(prefix="st1_"))
    game = tmp / "game"
    shutil.copytree(FIX / "sr1_game" / "game", game)
    for rel, text in FILES.items():
        p = game / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (game / "map").mkdir(exist_ok=True)
    write_bmp(game / "map" / "provinces.bmp", GRID)
    rows = ["province;red;green;blue;x;y;z;continent", "0;0;0;0;land;false;unknown;0"]
    rows += [f"{p};{color(p)[0]};{color(p)[1]};{color(p)[2]};{KIND[p]};false;{TERRAIN[p]};1" for p in KIND]
    (game / "map" / "definition.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (game / "map" / "adjacencies.csv").write_text(ADJACENCIES, encoding="utf-8")
    user = tmp / "user"
    user.mkdir()
    return tmp, game, user


# SR1's handmade save, with what ST1 reads beyond SR1 added in place: province control (BBB took province 12),
# air superiority, the air war, a war and a faction, more ideas, a railway repair, and three more BBB divisions.
# The one in 23 is two provinces from anything of ours: it must reach no slice (nor must BBB's air wing).
TOP = """provinces={
	12={
		controller="BBB"
	}
}
region={
	1={
		dominance={
			countries={ AAA }
			values={

				{ "AAA"
 {
						current=50
						individual_ratio=0.8
					}
}
			}
		}
	}
	3={
		dominance={
			countries={ }
		}
	}
}
"""
TAIL = """strategic_air={
	air_base={
		id={ id=1 type=65 }
		state=1
		capacity=200
		countries={
			id={ id=9 type=4713 }
			country="AAA"
		}
		level=1
	}
	air_base={
		id={ id=2 type=65 }
		state=2
		capacity=100
		level=1
	}
	AAA={
		air_wing_pool={
			id={ id=11 type=4713 }
			definition=fighter
			air_base={ id=1 type=65 }
			air_wings={
				id={ id=1 type=69 }
				count=50
				experience=12.5
				mission={
					type=1
					executing_mission=air_superiority
					effectiveness=0.5
					strategic_region=1
				}
				name="Jagdgeschwader 1"
			}
		}
	}
	BBB={
		air_wing_pool={
			id={ id=12 type=4713 }
			definition=fighter
			air_base={ id=2 type=65 }
			air_wings={
				id={ id=2 type=69 }
				count=40
				name="Feindgeschwader"
			}
		}
	}
}
faction={
	id={ id=1 type=88 }
	template="faction_template_test"
	members={
		"AAA"
		"CCC"
	}
}
"""
BBB_DIVISIONS = """			division={
				id={ id=50 type=51 }
				location=12
				division_template_id={ id=3 type=52 }
				organisation=20
				strength=80
			}
			division={
				id={ id=51 type=51 }
				location=22
				division_template_id={ id=3 type=52 }
				organisation=21
				strength=81
			}
			division={
				id={ id=52 type=51 }
				location=23
				division_template_id={ id=4 type=52 }
				organisation=22
				strength=123.4
			}
"""
FAR_TEMPLATE = """	division_template={
		id={ id=4 type=52 }
		name="Fernkorps"
		country="BBB"
		regiments={
			infantry={ x=0 y=0 }
		}
	}
"""


def variant():
    """The augmented save as bytes."""
    s = SMALL.read_text(encoding="utf-8")

    def put(before, text, once=True):
        nonlocal s
        assert s.count(before) == 1 or not once, before
        s = s.replace(before, text + before, 1)
    put("division_templates={\n", TOP)
    put("\tdivision_template={\n\t\tid={ id=3 type=52 }", FAR_TEMPLATE)
    put("\t\t\tdivision={\n\t\t\t\tid={ id=2 type=51 }", BBB_DIVISIONS)
    put("\t\tstability=0.4\n", "\t\tdiplomacy={\n\t\t\tactive_relations={\n\t\t\t\tCCC={\n\t\t\t\t\twar_relation={\n"
        "\t\t\t\t\t\tfirst=\"BBB\"\n\t\t\t\t\t\tsecond=\"CCC\"\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n")
    put("\t\tcapital=1\n", "\t\tdiplomacy={\n\t\t\tactive_relations={\n\t\t\t\tBBB={\n\t\t\t\t\twar_relation={\n"
        "\t\t\t\t\t\tfirst=\"AAA\"\n\t\t\t\t\t\tsecond=\"BBB\"\n\t\t\t\t\t\tstart_date=\"1940.1.2.1\"\n\t\t\t\t\t}\n"
        "\t\t\t\t}\n\t\t\t}\n\t\t}\n")
    put("\t\t\t\tbuilding={\n\t\t\t\t\tid={ id=8 type=59 }", "\t\t\t\tbuilding={\n\t\t\t\t\tid={ id=9 type=59 }\n"
        "\t\t\t\t\tamount=0\n\t\t\t\t\tcost=430\n\t\t\t\t\tbuilding={\n\t\t\t\t\t\ttemplate=rail_way\n"
        "\t\t\t\t\t\tlocation=21\n\t\t\t\t\t}\n\t\t\t\t\tto_repair=1\n\t\t\t\t}\n")
    s = s.replace("war_economy extensive_conscription",
                  "war_economy extensive_conscription AAA_spirit AAA_secret test_works hans_advisor odd_idea")
    put("weather={\n", TAIL)
    return s.encode("utf-8")


PREFIX = "[10:00:02][1940.03.13.06]: @CB;"
BRIDGE = [PREFIX + x for x in (
    "rep_begin;tag=AAA",
    "politics;pp=1.0;ppd=0.5;stab=0.1;ws=0.1;cp=0;cpd=0;election_days=-1",   # an old report with no end
    "day;tag=AAA;pp=149.0;ppd=1.25;stab=0.65;ws=0.5;mpk=120.5;divs=3;cp=10",
    "rep_begin;tag=AAA",
    "country;tag=AAA;name=Testreich;ideology=fascism;party=TP;leader=Hans von Test;faction=Testpakt",
    "politics;pp=150.555;ppd=1.25;stab=0.65;ws=0.5;cp=10;cpd=0.5;election_days=-1",
    "industry;civ=20;mil=10;nav=2;civ_free=5;mil_free=1;nav_free=0;research_slots=3;techs=12;fuel_k=50;max_fuel_k=80",
    "territory;owned=1;controlled=1;occupied=0;cores=1;subjects=0",
    "resources;steel=12;oil=-3;aluminium=4;rubber=-1;tungsten=0;chromium=2",
    "army;mpk=120.5;max_mpk=9000;deployed_k=30.2;divs=3;armies=2;casualties_k=1.5;garrison_need=0;deploy_queue_mp=0",
    "equip;type=infantry_equipment;stock=500;fielded=9000;target=10000",
    "equip;type=artillery_equipment;stock=0;fielded=0;target=0",
    "equip;type=convoy;stock=40;fielded=0;target=0",
    "war;surrender=0;enemy_strength_ratio=1.2;alliance_strength_ratio=1.1;longest_war_months=2",
    "enemy;tag=BBB;name=Testonia;surrender=0.25;divs=7;mil=3;civ=4",
    "ally;tag=CCC;name=Cetland;surrender=0;divs=2;mil=1",
    "general;name=Hans von Test;units=2;in_combat=1;combat_progress=0.5;entrench=0.1;planning=0.4;skill=3;plans=1",
    "front;id=2;state=Südland",
    "major;tag=DDD;name=Deeland;ideology=democratic;faction=;divs=40;mil=20;civ=30;surrender=0",
    "neighbor;tag=EEE;name=Eeland;ideology=neutrality;faction=;divs=4;mil=1",
    "rep_end;tag=AAA",
)]

OPS = {"test": {"name": "test", "goal": "Take Suedland", "forces": ["army 1", "Army 9"], "success": "state 2 is ours",
                "abort": "under 50% strength", "deadline": "1940-04-30", "by": "field_marshal_heeresgruppe_test"}}


def check_map(game):
    m = game / "map"
    w = L.MapData.from_files(m / "definition.csv", m / "provinces.bmp", m / "adjacencies.csv",
                             sorted((m / "strategicregions").glob("*.txt")), {"STRATEGICREGION_1": "Testland"})
    n = {p: sorted(q) for p, q in w.neighbors.items()}
    assert n[10] == [11, 20, 30] and n[11] == [10, 12, 30], "side by side and one above the other"
    assert n[12] == [11, 13, 22, 23], "the map wraps east-west (12-23); the strait adds 12-22"
    assert n[13] == [12], "impassable removes 13-30, both across the edge and side by side"
    assert n[21] == [22, 23, 30] and 0 not in n, "province 0 and unknown colours are not provinces"
    assert w.kind[30] == "sea" and w.terrain[21] == "urban"
    assert w.region_of[22] == 2 and w.region_name(1) == "Testland" and w.region_name(2) == "STRATEGICREGION_2"
    assert w.ring({10, 11}) == {12, 20, 30}
    bad = m.parent / "bad.bmp"
    bad.write_bytes(b"BM" + bytes(26) + struct.pack("<HI", 8, 0) + bytes(30))
    try:
        L.MapData.from_files(m / "definition.csv", bad)
    except L.MapError as e:
        assert "24-bit" in str(e)
    else:
        raise AssertionError("an 8-bit BMP must be refused")

    g = H.GameData.load(game, game.parent / "user", mods=False)
    cache = game.parent / "state" / "map_cache.json"
    first = L.MapData.load(g, cache=cache)
    assert cache.is_file() and first.region_name(3) == "Test Sea", "region names from the localisation"
    assert first.state_of[13] == 1 and first.state_name(22) == "Südland", "states from the game's history files"
    again = L.MapData.load(g, cache=cache)
    assert again.neighbors == first.neighbors and again.region_names == first.region_names, "read back from the cache"
    c = json.loads(cache.read_text(encoding="utf-8"))
    c["neighbors"]["10"] = []                          # a stale cache must not be used once a map file changes
    cache.write_text(json.dumps(c), encoding="utf-8")
    assert L.MapData.load(g, cache=cache).neighbors[10] == frozenset(), "the cache is used while nothing changed"
    adj = m / "adjacencies.csv"
    adj.write_text(ADJACENCIES + "\n", encoding="utf-8")
    assert L.MapData.load(g, cache=cache).neighbors[10] == first.neighbors[10], "a changed map file rebuilds it"
    assert L.MapData.load(None) is None and L.MapData.load(H.GameData.load(FIX / "sr1_game" / "game")) is None, \
        "no game, or a game folder without map files: no map"
    print("  map: provinces.bmp runs side by side, above and across the edge; crossings, impassable, regions, cache")
    return first


def check_bridge():
    b = L.parse_bridge(BRIDGE)
    assert b["politics"]["pp"] == 150.555 and b["politics"]["election_days"] == -1, "the last complete report"
    assert b["day"]["mpk"] == 120.5 and b["country"]["name"] == "Testreich" and b["front"][0]["state"] == "Südland"
    assert [e["tag"] for e in b["enemy"]] == ["BBB"] and b["enemy"][0]["divs"] == 7 and len(b["equip"]) == 3
    assert b["country"]["faction"] == "Testpakt" and b["major"][0]["faction"] == ""
    recs = [L._record(x) for x in BRIDGE]
    assert L.parse_bridge(recs) == b, "the records hoi4.py parses give the same"
    assert L.parse_bridge("\n".join(BRIDGE)) == b and L.parse_bridge(b) == b, "log text and the grouped form too"
    grouped = L.parse_bridge({"politics": {"pp": "12.5"}, "enemy": [{"tag": "BBB", "divs": "3"}]})
    assert grouped == {"politics": {"pp": 12.5}, "enemy": [{"tag": "BBB", "divs": 3}]}
    assert L.parse_bridge(None) == {} and L.parse_bridge([]) == {}
    print("  bridge: last complete report, heartbeat, numbers; from log lines, records or a grouped dict")
    return b


def check_extras(data):
    ex = L.read_extras(data, "AAA")
    assert ex["control"] == {"state_owner": {1: "AAA", 2: "BBB"}, "province_controller": {12: "BBB"}}
    air = ex["air"]
    assert air["bases"][1] == {"state": 1, "carrier": False, "capacity": 200, "level": 1}
    assert air["wings"] == [{"name": "Jagdgeschwader 1", "type": "fighter", "planes": 50, "base": 1,
                             "mission": "air_superiority", "region": 1, "effectiveness": 0.5, "experience": 12}]
    assert ex["air_superiority"] == {1: {"held_by": ["AAA"], "ours": 0.8}}
    assert ex["faction"] == {"template": "faction_template_test", "members": ["AAA", "CCC"]}
    assert L.read_wars(data, "AAA") == [{"enemy": "BBB", "since": "1940.1.2.1"}], "BBB's own war with CCC is not ours"
    assert L.read_wars(data, "CCC") == [{"enemy": "BBB", "since": None}]
    plain = L.read_extras(SMALL.read_bytes(), "AAA")
    assert plain["control"]["province_controller"] == {} and plain["air"] is None and plain["faction"] is None
    print("  save extras: province control, air bases and wings (ours only), superiority, wars, the faction")


def leaks(out):
    """Everything in the slices that a player could not see: the far BBB unit and BBB's air wing."""
    text = json.dumps(out, ensure_ascii=False)
    found = [w for w in ("Fernkorps", "Feindgeschwader") if w in text]
    for sl in out.values():
        for country in (sl.get("enemy_seen") or {}).values():
            found += [r for rows in country.values() for r in rows if r[1] in (21, 23)]
    return found


def check_slices(data, world, bridge, game):
    g = H.GameData.load(game, game.parent / "user", mods=False)
    timing = {}
    snap = L.snapshot(data, game=g, focus=False, timing=timing)
    assert [u["location"] for u in snap["units"]["BBB"]] == [12, 22, 23, 20, 21], "the save holds every BBB unit"
    out = L.slices(snap, BRIDGE, world, operations=OPS)
    assert list(out) == list(L.AGENTS) + ["field_marshal_heeresgruppe_test", "operation_test"]
    assert not leaks(out), f"seen through the fog: {leaks(out)}"
    ctx = L._Ctx(snap, {}, world, None, None)          # the one list of enemy units every slice draws from
    assert sorted(u["location"] for _, u in ctx.enemy_units) == [12, 20, 22], "21 and 23 are two provinces away"
    for name, sl in out.items():
        assert sl["agent"] == name and sl["tag"] == "AAA" and sl["date"] == "1940.3.13.6"
    size = L.sizes(out)
    assert all(n < L.SIZE_AIM for n in size.values()), size

    ours, seen, controller = L.visible(snap, world)
    assert ours == {10, 11, 13, 20}, "state 1 without 12 (BBB took it), plus 20 where division 901 stands"
    assert seen == {10, 11, 12, 13, 20, 22, 30}, "and the provinces next to those: not 21 or 23"
    assert controller(12) == "BBB" and controller(13) == "AAA" and controller(21) == "BBB"

    p = out["policy"]
    assert p["laws"] == {"economy": "War Economy", "mobilization_laws": "extensive_conscription"}
    assert p["law_options"] == {"economy": [["Civilian Economy", 150], ["War Economy", 150]],
                                "mobilization_laws": [["extensive_conscription", 150]]}, \
        "laws without a price and other countries' laws are not offered"
    assert p["advisors"] == [{"name": "test_works", "slot": "industrial_concern"},
                             {"name": "Hans the Advisor", "slot": "political_advisor"}]
    assert p["spirits"] == ["Test Spirit"] and p["ideas_unread"] == ["odd_idea"] and "AAA_secret" not in json.dumps(p)
    assert p["wars"] == {"columns": ["tag", "name", "divs", "mil", "civ", "surrender", "since"],
                         "rows": [["BBB", "Testonia", 7, 3, 4, 0.25, "1940.1.2.1"]]}, "the bridge's counts, not the save's"
    assert p["pp_per_day"] == 1.25 and p["faction"] == {"template": "faction_template_test", "members": ["AAA", "CCC"],
                                                        "name": "Testpakt"}
    assert p["majors"]["columns"] == ["tag", "name", "ideology", "divs", "mil", "civ", "surrender"], "empty columns go"
    assert p["focus"] == {"current": "AAA_third", "progress": 12.5, "completed": 2}

    r = out["research"]
    assert r["year"] == 1940 and r["free"] == 1 and [x["tech"] for x in r["running"]] == ["future_tech", "steady_tech"]
    st = r["running"][1]
    assert (st["days_left"], st["per_day"]) == (50, 2) and r["researched"] == ["basic_tech"], "costs 150 without the mod"

    ci = out["civilian_industry"]
    assert ci["construction"]["rows"] == [["industrial_complex", "Nordland", 2, 15, 0.093, 66],
                                          ["arms_factory", "Südland", 1, 0, 0.0, None]]
    assert ci["repairs"] == {"rail_way": {"queued": 1, "with_factories": 0}}, "the game's repairs, summed"
    assert ci["states"]["rows"] == [["Nordland", "city", 6, 3, 2, 1, 5, None]], "6 slots, 3 used, 2 queued, 1 free"
    assert ci["factories"]["civilian_free"] == 5 and ci["resources"]["oil"] == -3

    mi = out["military_industry"]
    assert mi["lines"]["rows"] == [[1, "infantry_equipment_1", None, 2, 60.0, 18.0, 0, None]]
    assert mi["stockpile"]["rows"] == [["infantry_equipment", 500, 9000, 10000, 1000]], "empty and convoy rows go"
    ni = out["naval_industry"]
    assert ni["lines"]["rows"] == [[1, "ship_hull_light_2", "Klasse {A}", 1, 0.25, 10, 1, 2]]
    assert ni["convoys"]["rows"] == [["convoy", 40, 0, 0, 0]] and ni["ships_afloat"] == {"destroyer": 2}

    air = out["air"]
    assert air["wings"]["rows"] == [["Jagdgeschwader 1", "fighter", 50, "Nordland", "air_superiority", "Testland", 0.5]]
    assert air["bases"]["rows"] == [["Nordland", 1, 200, 50]], "our base only, not BBB's"
    assert air["regions"] == [{"region": "Testland", "front_against": ["BBB"],
                               "superiority": {"held_by": ["AAA"], "ours": 0.8}}]
    nv = out["navy"]
    assert nv["fleets"][0]["task_forces"][0]["at"] == "Test Sea" and nv["wars"] == ["BBB"]

    a = out["army"]
    assert a["divisions_by_army"] == {"Army 1": {"Infanterie-Division": 1, "Gebirgsjaeger": 1},
                                      "(no army)": {"Infanterie-Division": 1}}
    assert a["field_marshals"] == {"field_marshal_heeresgruppe_test": ["Army 1"]}, "one per army group"
    assert a["training"]["rows"] == [["Infanterie-Division", "Nordland", 1, 1, 2, 0.5]]
    assert a["equipment_short"] == [["infantry_equipment", 1000]] and a["manpower"]["mpk"] == 120.5
    assert a["fronts"] == [{"against": ["BBB"], "states": ["Nordland"], "provinces": 2}]

    fm = out["field_marshal_heeresgruppe_test"]
    assert [x["name"] for x in fm["armies"]] == ["Army 1"] and fm["operations"] == ["operation_test"]
    army = fm["armies"][0]
    assert army["divisions"] == 2 and army["in_combat"] == 1 and army["moving"] == 1 and army["avg_org"] == 32.6
    t = fm["templates"]
    assert {t[r[0]]: r[1:] for r in army["units"]["Nordland"]} == {"Infanterie-Division": [10, 180, 25, 12, 1],
                                                                  "Gebirgsjaeger": [11, 90, 40, None, 0]}
    assert set(fm["enemy_seen"]["BBB"]) == {"Nordland", "Südland"}
    rows = [r for st in fm["enemy_seen"]["BBB"].values() for r in st]
    assert sorted(r[1] for r in rows) == [12, 20], "next to Army 1 (10, 11) only: not 22, which is next to 20"
    assert fm["fronts"] == [{"against": ["BBB"], "states": ["Nordland"], "provinces": [10, 11]}]
    assert fm["enemy_totals"]["rows"][0][:3] == ["BBB", "Testonia", 7]

    op = out["operation_test"]
    assert op["charter"]["goal"] == "Take Suedland" and op["unknown_forces"] == ["Army 9"]
    assert op["around"] == [[12, "Nordland", "BBB", "hills"], [20, "Südland", "BBB", "plains"]], "land only"
    assert [x["name"] for x in op["armies"]] == ["Army 1"]
    print(f"  slices: all {len(out)} from SR1's save + a bridge report, each under {L.SIZE_AIM:,} chars "
          f"(largest {max(size.values()):,}); every section checked")
    return snap


def check_fog(snap, world):
    out = L.slices(snap, BRIDGE, world=None)
    assert not leaks(out) and set(out) == set(L.AGENTS) | {"field_marshal_heeresgruppe_test"}
    ours, seen, _ = L.visible(snap, None)
    assert ours == seen == {10, 11, 20}, "without a map: divisions and control overrides only, nothing next to them"
    ctx = L._Ctx(snap, {}, None, None, None)
    assert [u["location"] for _, u in ctx.enemy_units] == [20], "only the enemy inside our provinces (20, with 901)"

    plain = H.extract(SMALL, units=["BBB"], game=H.GameData.load(FIX / "sr1_game" / "game", mods=False))
    out = L.slices(plain, None, world)
    assert set(out) == set(L.AGENTS) | {"field_marshal_heeresgruppe_test"}, "a plain SR1 extract is enough"
    rows = {r[1] for sl in out.values() for c in (sl.get("enemy_seen") or {}).values() for st in c.values() for r in st}
    assert rows == {20}, "only BBB's unit in 20 is next to Army 1; 21 is two provinces away"
    assert "Testonia" not in json.dumps(out), "no bridge: no enemy figures"

    fms = L.slices(snap, None, world, field_marshals={"west": ["Army 2", "Heeresgruppe Test", "Army 7"]})
    fm = fms["field_marshal_west"]
    assert [a["name"] for a in fm["armies"]] == ["Army 2", "Army 1"] and fm["unknown_forces"] == ["Army 7"], \
        "armies and army groups by name"
    assert "field_marshal_heeresgruppe_test" not in fms
    assert list(L.slices(snap, None, world, agents=["air"])) == ["air"]
    print("  fog of war: no map = our provinces only; plain SR1 extract; field marshals and operations by name")


def check_focus(path, game):
    g = H.GameData.load(game, game.parent / "user", mods=False)
    snap = L.snapshot(path, game=g, focus=True, user_dir=game.parent / "user")
    fo = snap["focus_options"]
    assert "error" not in fo, fo
    rows = {r[0]: r for r in fo["can_start"]["rows"]}
    assert set(rows) == {"AAA_fourth"}, "FP1: prerequisites met, not running, not done"
    assert rows["AAA_fourth"][1:4] == ["The Fourth", 49, "has_war_with = BBB"]
    out = L.slices(snap, BRIDGE, None, agents=["policy"])
    assert out["policy"]["focus"]["can_start"]["rows"][0][0] == "AAA_fourth"
    bad = L._focus_options(None, snap, H.GameData([(game.parent / "nowhere", ())]), game.parent / "user")
    assert "error" in bad, "FP1 failing never stops the snapshot"
    print("  focus: FP1's startable focuses in the policy slice; a failure is reported, not raised")


def check_cli(path, game, bridge_file):
    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = L.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()
    common = ("--game-dir", game, "--user-dir", game.parent / "user", "--no-mods", "--no-focus",
              "--cache", game.parent / "state" / "cli_cache.json")
    code, out, _ = run(path, "--bridge", bridge_file, *common)
    slices = json.loads(out)
    assert code == 0 and "field_marshal_heeresgruppe_test" in slices and not leaks(slices)
    assert slices["policy"]["wars"]["rows"][0][1] == "Testonia"
    code, out, _ = run(path, "--agent", "air", *common)
    assert code == 0 and json.loads(out)["agent"] == "air", "one --agent prints that slice alone"
    ops = game.parent / "ops.json"
    ops.write_text(json.dumps(OPS), encoding="utf-8")
    code, out, _ = run(path, "--sizes", "--operations", ops, *common)
    assert code == 0 and "operation_test" in out and "setup (s):" in out and "over the aim" not in out
    code, _, err = run(game.parent / "missing.hoi4", *common)
    assert code == 2 and "hoi4_slices:" in err
    print("  CLI: JSON out, --bridge, --agent, --operations, --sizes; exit 2 with the reason")


def main():
    t = time.perf_counter()
    tmp, game, user = make_game()
    try:
        world = check_map(game)
        bridge = check_bridge()
        data = variant()
        check_extras(data)
        snap = check_slices(data, world, bridge, game)
        check_fog(snap, world)
        path = tmp / "st1_variant.hoi4"
        path.write_bytes(data)
        check_focus(path, game)
        bridge_file = tmp / "bridge.log"
        bridge_file.write_text("\n".join(BRIDGE) + "\n", encoding="utf-8")
        check_cli(path, game, bridge_file)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"ST1 CHECKS PASSED ({time.perf_counter() - t:.1f}s)")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()

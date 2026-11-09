r"""SR1: the save reader (hoi4_save.py) on the real 1936 fixture and on handmade ones.

Standard library only, no game and no Windows needed:  python tests/test_SR1.py
"""
import contextlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_save as S  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
REAL = FIX / "ger_1936_02_25.txt"
SMALL = FIX / "sr1_small.txt"
GAME = FIX / "sr1_game" / "game"
USER = FIX / "sr1_game" / "user"


def raises(fn, *args, contains="", **kw):
    try:
        fn(*args, **kw)
    except S.SaveFormatError as e:
        assert contains in str(e), f"error {e!r} should mention {contains!r}"
        return
    raise AssertionError(f"{fn.__name__}{args} should raise SaveFormatError")


def check_parser():
    data = (b'a=1 a=2 b={ 1 2 3 } c="x \\"y\\"" d=1936.1.1.12 e=-1 f=53.62744 g={ { x=1 } { x=2 } }\n'
            b'h={ { k 0}\n } role=\r\n closed=no 42={ v=yes } blk={ i=} tail=done')
    b = S.parse(data)
    assert b.all("a") == [1, 2] and b.one("a") == 1 and b.last("a") == 2, "repeated keys keep every value in order"
    assert b.one("b").bare == [1, 2, 3]
    assert b.one("c") == 'x "y"', "quoted strings lose their quotes and escapes"
    assert b.one("d") == "1936.1.1.12" and b.one("e") == -1 and isinstance(b.one("f"), float)
    assert [x.one("x") for x in b.one("g").bare] == [1, 2], "anonymous blocks inside a list"
    assert b.one("h").bare[0].bare == ["k", 0], "`0}` ends a token"
    assert b.one("role") == "" and b.one("closed") == "no", "`role=` with no value, then the next key"
    assert b.one("42").one("v") == "yes", "numeric keys stay text"
    assert b.one("blk").one("i") == "" and b.one("tail") == "done", "`i=}` is an empty value, then the block closes"
    assert S.parse(data.decode()) == b, "str input parses the same as bytes"
    assert b.to_py()["a"] == [1, 2] and b.to_py()["b"] == [1, 2, 3]

    game = S.parse('size > 5 x >= 1.5 y != no z ?= 3 # a comment with { a brace\nw = { has_war_support > 0.5 }')
    assert game.one("size") == S.Cmp(">", 5) and game.one("x") == S.Cmp(">=", 1.5)
    assert game.one("y") == S.Cmp("!=", "no") and game.one("z") == S.Cmp("?=", 3)
    assert game.path("w", "has_war_support") == S.Cmp(">", 0.5), "comments are skipped, braces in them too"

    nested = b'keep={ a=1 } skip={ deep={ x=1 } } s=1 other={ inner={ y=2 deeper={ w=1 } } junk={ z=3 } q=4 }'
    p = S.parse(nested, {"keep": True, "other": {"*": {}}})
    assert "skip" not in p and p.one("s") == 1 and p.path("keep", "a") == 1, "unnamed blocks skipped, values kept"
    assert p.path("other", "inner", "y") == 2 and "deeper" not in p.path("other", "inner"), \
        '"*": {} builds every child block with its plain values only'
    p = S.parse(nested, {"other": {"inner": True}})
    assert p.path("other", "inner", "y") == 2 and "junk" not in p.one("other")
    sp = S.parse(nested, {"skip": S.SPAN}).one("skip")
    assert isinstance(sp, S.Span) and S.parse(nested, start=sp.start, end=sp.end) == S.parse(nested).one("skip")

    assert not S.plain_braces(b'a="{" b={ }') and S.plain_braces(b'a="x" b={ }') and not S.plain_braces(b"#c\na=1")
    tricky = b'{ a="}" b={ c=1 } # }\n } tail'
    assert S.skip_block(tricky, 1, plain=False) == tricky.index(b" tail"), "braces in strings and comments ignored"
    assert S.skip_block(tricky.decode(), 1) == tricky.index(b" tail")
    raises(S.parse, b"a={ b=1", contains="not closed")
    raises(S.parse, b"a=1 }", contains="without a matching")
    raises(S.skip_block, b"{ a", 1, contains="unclosed")

    eq = b'equipments={ a={ creator="X" id={ id=5 type=70 } } b={ id={ id=6 type=70 } name="B" } c={ id=7 } }'
    span = S.parse(eq, {"equipments": S.SPAN}).one("equipments")
    found = S._lookup(eq, span, {(5, 70), (6, 70), (9, 70)}, None, {"id": True}, False, {"*": {"id": True}},
                      S._all_equipment)
    assert found[(6, 70)][0] == "b" and found[(6, 70)][1].one("name") == "B", "found by the regex"
    assert found[(5, 70)][0] == "a" and (9, 70) not in found, "an entry whose id is not first: found by parsing"

    real = REAL.read_bytes()
    assert S.plain_braces(real), "the real fixture has no braces inside strings"
    start = real.index(b"\ncountries={") + len(b"\ncountries={")
    assert S.skip_block(real, start, plain=True) == S.skip_block(real, start, plain=False), "fast skip = exact skip"
    print("  parser: repeats, lists, strings, empty values, comparisons, comments, spec, spans, errors")


def check_files():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "bin.hoi4").write_bytes(b"HOI4bin\x00\x01\x02")
    (tmp / "other.hoi4").write_bytes(b"PK\x03\x04")
    raises(S.read_save, tmp / "bin.hoi4", contains="save_as_binary=no")
    raises(S.read_save, tmp / "other.hoi4", contains="does not start with HOI4txt")
    raises(S.extract, b"HOI4bin...", contains="save_as_binary=no")
    raises(S.extract, SMALL, tag="ZZZ", contains="ZZZ is not in the save")
    assert S.raw(REAL, "countries.GER.focus").one("current") == "GER_remilitarize_the_rhineland"
    print("  files: binary and foreign saves refused with SR0's setting named; raw() by dotted path")


def simulate(s, year, start, now_days, cost, penalty=2.0):
    """Day-by-day research as the saves show it: points, rate at start, and the day the cost is reached."""
    def rate(t):
        return s / (1 + penalty * max(0.0, year - t))
    points, t = 0.0, start
    for _ in range(now_days):
        points += rate(t)
        t += 1 / 365
    now = t
    days, p = 0, points
    while p < cost:
        p += rate(t)
        t += 1 / 365
        days += 1
    return points, rate(start), now, days


def check_research_model():
    for s, year, start, n, cost in ((1.3, 1941, 1939.4, 300, 400), (0.8, 1940, 1939.0, 200, 300),
                                    (2.0, 1936, 1937.0, 50, 300), (1.0, 1945, 1940.0, 100, 500)):
        points, factor, now, days = simulate(s, year, start, n, cost)
        rate, est = S.research_eta(points, cost, factor, 0, year, now)
        assert abs(est - days) <= 1, f"days left {est} vs simulated {days} (S={s}, year {year})"
        assert abs(rate - s / (1 + 2 * max(0, year - now))) < 0.01, "today's rate"
    assert S.research_eta(50, 200, 2.0, 10, 1936, 1940.2) == (2.0, 75), "not ahead of time: a constant rate"
    assert S.research_eta(10, 100, 0.5, 0, None, None) == (0.5, 180), "no start year: points_factor as the rate"
    assert S.research_eta(10, None, 0.5, 0, 1941, 1940.0) == (None, None)
    # Jerus's saves (2026-11-07 run): what the model said from one save, and the day the game finished the tech.
    seen = [(142.29378, 220, 0.21195, 30, 1941, "1939.11.1.1", 174),     # construction4 -> 1940.4.24
            (120.14295, 220, 0.22778, 4, 1941, "1939.11.1.1", 213),      # concentrated_industry4 -> 1940.6.2
            (179.42365, 220, 0.21195, 30, 1941, "1940.1.30.6", 84),      # construction4 again, later save
            (186.52868, 220, 0.57174, 2, 1940, "1940.1.30.6", 28)]       # light_truck_tech -> 1940.2.27
    for points, cost, factor, saved, year, date, actual in seen:
        _, est = S.research_eta(points, cost, factor, saved, year, S._years(date))
        assert abs(est - actual) <= 1, f"predicted {est} days, the game took {actual}"
    print("  research: days left match a day-by-day simulation and four finished techs in real saves (+-1 day)")


def check_game_data():
    g = S.GameData.load(GAME, USER)
    assert [p.name for p, _ in g.roots] == ["game", "test"], "the game, then the enabled mod; a missing mod is left out"
    assert g.base_tech_cost() == 100 and g.ahead_penalty() == 2, "defines read, comments ignored"
    assert g.tech_costs() == {"steady_tech": 200, "future_tech": 200, "basic_tech": 100}, "the mod's file wins"
    assert g.tech_info()["future_tech"] == (200, 1941)
    assert g.state_names() == {1: "Nordland", 2: "Südland"}
    assert g.province_states() == {10: 1, 11: 1, 12: 1}, "replace_path drops the game's history/states"
    plain = S.GameData.load(GAME, USER, mods=False)
    assert plain.tech_costs()["steady_tech"] == 150 and plain.tech_info()["future_tech"] == (200, 1941), "@variable"
    assert plain.province_states()[20] == 2
    assert S.GameData.load(Path(tempfile.mkdtemp())) is None, "no game folder: no game data"
    print("  game files: defines, tech costs and years, state names, provinces; mod load order and replace_path")


def check_small():
    g = S.GameData.load(GAME, USER)
    snap = S.extract(SMALL, units=["BBB", "AAA", ""], game=g)
    assert snap["save"]["file"] == "sr1_small.txt" and snap["tag"] == "AAA", "the player's country by default"
    pol = snap["politics"]
    assert abs(pol["political_power"] - 150.555) < 0.01 and pol["stability"] == 0.65 and pol["war_support"] == 0.5
    assert pol["ideas"] == ["war_economy", "extensive_conscription"] and pol["ruling_party"] == "fascism"
    assert snap["focus"] == {"tree": "aaa_focus", "current": "AAA_third", "progress": 12.5, "paused": False,
                             "completed": ["AAA_first", "AAA_second"]}
    res = snap["research"]
    assert res["slots"] == 3 and res["free"] == 1 and res["saved_points"] == [25] and res["researched"] == ["basic_tech"]
    run = {r["tech"]: r for r in res["running"]}
    assert set(run) == {"future_tech", "steady_tech"}, "an idle slot (empty=) is not a tech"
    assert run["steady_tech"]["days_left"] == 75 and run["steady_tech"]["per_day"] == 2 and \
        run["steady_tech"]["cost"] == 200
    ft = run["future_tech"]
    assert (ft["per_day"], ft["days_left"]) == tuple(
        round(v, 3) if isinstance(v, float) else v
        for v in S.research_eta(20, 200, 0.5, 0, 1941, S._years("1940.3.13.6"))) and ft["years_ahead"] == 0.8

    mil, nav = snap["production"]
    assert mil == {"kind": "military", "equipment": "infantry_equipment_1", "variant": None, "factories": 2,
                   "requested": 3, "efficiency": 60.0, "priority": 0, "amount": None, "per_day": 18.0}
    assert nav["equipment"] == "ship_hull_light_2" and nav["variant"] == "Klasse {A}" and nav["progress"] == 0.25 \
        and nav["days_to_next"] == 10 and nav["amount"] == 2
    ic, af = snap["construction"]
    assert ic == {"building": "industrial_complex", "state": 1, "state_name": "Nordland", "levels": 2, "factories": 15,
                  "progress": 0.093, "days_left": 66, "priority": 0}
    assert af["state_name"] == "Südland" and af["factories"] == 0 and af["days_left"] is None

    d1, d900, d901 = snap["divisions"]
    assert d1["name"] == "7. Infanterie-Division" and d1["army"] == "Army 1" and d1["location"] == 10
    assert d1["manpower"] == 0.9 and d1["moving_to"] == 12 and d1["in_combat"] and d1["state"] == "Nordland"
    assert abs(d1["org"] - 25.25) < 0.06 and d1["strength"] == 180.5
    assert d900["name"] == "Gebirgs-Brigade" and d900["army"] == "Army 1" and not d900["in_combat"]
    assert d901["name"] == "8. Infanterie-Division" and d901["army"] is None and d901["state"] is None
    a1, a2 = snap["armies"]
    assert a1 == {"name": "Army 1", "group": "Heeresgruppe Test", "divisions": 2,
                  "leader": {"name": "Hans von Test", "role": "corps_commander", "skill": 3, "attack": 3,
                             "defense": 2, "planning": 4, "logistics": 1, "traits": ["old_guard", "trait_cautious"]}}
    assert a2["leader"]["name"] == "Erika Muster" and a2["leader"]["role"] == "field_marshal" and a2["group"] is None
    assert snap["fronts"] == [{"enemies": ["BBB"], "provinces": [10, 11]}]
    assert snap["templates"] == [
        {"name": "Infanterie-Division", "regiments": {"infantry": 3}, "support": ["engineer"], "divisions": 2},
        {"name": "Gebirgsjaeger", "regiments": {"mountaineers": 1}, "support": [], "divisions": 1}]
    assert snap["training"] == [{"template": "Infanterie-Division", "queued": 1, "location": 10,
                                 "training": [{"divisions": 2, "progress": 0.5}]}]
    assert snap["fleets"] == [{"name": "Flotte", "home_base": 30, "task_forces": [
        {"name": "TF 1", "location": 30, "mission": 2, "ships": {"destroyer": 2}, "strength": 95.5, "org": 35.0}]}]
    assert snap["states"] == [{"id": 1, "name": "Nordland", "category": "city",
                               "buildings": {"industrial_complex": 3, "infrastructure": 5}, "manpower": 1000}]
    assert list(snap["units"]) == ["BBB"], "the player's own tag and blanks are not repeated under units"
    bbb = snap["units"]["BBB"]
    assert [u["location"] for u in bbb] == [20, 21] and bbb[0]["template"] == "Piechota" and bbb[0]["org"] == 30.5

    # The same save with mixed line endings, as the game writes them, read from bytes: the same answer.
    lines = SMALL.read_bytes().split(b"\n")
    mixed = b"\n".join(ln + b"\r" if i % 2 else ln for i, ln in enumerate(lines))
    again = S.extract(mixed, units=["BBB"], game=g)
    assert again.pop("save")["file"] is None
    snap.pop("save")
    assert again == snap, "CRLF and LF read the same"
    bare = S.extract(SMALL)
    assert bare["research"]["running"][1]["days_left"] is None and bare["construction"][0]["state_name"] is None
    assert "state" not in bare["divisions"][0], "without the game's files: no state names, no days left"
    print("  handmade save: every section, leaders, armies, idle slots, braces in strings, CRLF, game files")


def check_real():
    timing = {}
    t = time.perf_counter()
    snap = S.extract(REAL, timing=timing)
    took = time.perf_counter() - t
    assert snap["tag"] == "GER" and snap["save"]["date"] == "1936.2.25.12"
    pol = snap["politics"]
    assert pol["political_power"] == 23.34 and pol["stability"] == 0.7 and pol["war_support"] == 0.3
    assert "limited_conscription" in pol["ideas"] and pol["popularity"]["fascism"] == 40
    assert snap["focus"]["current"] == "GER_remilitarize_the_rhineland" and snap["focus"]["progress"] == 8
    assert snap["focus"]["completed"] == ["GER_the_four_year_plan"]
    res = snap["research"]
    assert [r["tech"] for r in res["running"]] == ["basic_machine_tools", "construction1",
                                                   "electronic_mechanical_engineering", "rubber_processing",
                                                   "interwar_artillery"]
    assert res["running"][0]["points"] == 56.56 and res["running"][3]["per_day"] == 0.745 and res["free"] == 0
    assert "torpedoboat_destroyer_hull" in res["researched"] and "basic_machine_tools" not in res["researched"]
    prod = snap["production"]
    assert sum(p["kind"] == "military" for p in prod) == 8 and sum(p["kind"] == "naval" for p in prod) == 14
    assert prod[0]["equipment"] == "infantry_equipment_1" and prod[0]["factories"] == 11 and prod[0]["per_day"] == 58.7
    assert any(p["variant"] == "Typ IIB" for p in prod), "ship variants by name"
    assert all(p["equipment"] for p in prod), "every line's equipment found"
    cons = snap["construction"]
    assert [(c["building"], c["state"], c["levels"]) for c in cons] == [("industrial_complex", 65, 3),
                                                                        ("industrial_complex", 59, 3)]
    divs = snap["divisions"]
    assert len(divs) == 30 and divs[0]["location"] == 6334 and divs[0]["name"] == "25. Infanterie-Division"
    assert all(isinstance(d["location"], int) and d["template"] for d in divs)
    tmpl = {t["name"]: t for t in snap["templates"]}
    assert tmpl["Infanterie-Division"]["regiments"] == {"infantry": 9} and tmpl["Infanterie-Division"]["divisions"] > 0
    assert len(snap["fleets"]) == 3 and snap["fleets"][0]["name"] == "Kriegsmarine"
    assert {s["id"] for s in snap["states"]} >= {64, 65, 59} and len(snap["states"]) == 24
    size = len(json.dumps(snap, separators=(",", ":")))
    print(f"  real 1936 fixture: every section; {took:.2f}s for 514 KB, {size:,} chars of JSON; {timing}")


def check_cli():
    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = S.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    code, out, _ = run(SMALL, "--no-game")
    assert code == 0 and json.loads(out)["tag"] == "AAA" and "\n" not in out.strip(), "compact JSON by default"
    code, out, err = run(SMALL, "--game-dir", GAME, "--user-dir", USER, "--units", "bbb", "--indent", "1", "--timing")
    snap = json.loads(out)
    assert code == 0 and "BBB" in snap["units"] and snap["research"]["running"][1]["days_left"] == 75
    assert "timing (s):" in err and "game_files" in err
    code, out, _ = run(SMALL, "--raw", "countries.AAA.focus")
    assert code == 0 and json.loads(out)["completed"] == ["AAA_first", "AAA_second"]
    tmp = Path(tempfile.mkdtemp()) / "bin.hoi4"
    tmp.write_bytes(b"HOI4bin\x00")
    code, out, err = run(tmp)
    assert code == 2 and "save_as_binary=no" in err and not out
    code, _, err = run(SMALL, "--tag", "ZZZ", "--no-game")
    assert code == 2 and "ZZZ" in err
    print("  CLI: JSON out, --units, --raw, --timing; exit 2 with the reason for a binary save or a missing tag")


def main():
    check_parser()
    check_files()
    check_research_model()
    check_game_data()
    check_small()
    check_real()
    check_cli()
    print("SR1 CHECKS PASSED")


if __name__ == "__main__":
    main()

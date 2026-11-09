r"""Offline checks for hoi4_orderspec.py (OR1): the orders format, its validator, load, and the merge step.

No game and no Windows needed (the module does not import hoi4.py):  .venv\Scripts\python.exe tests\test_OR1.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_orderspec as S  # noqa: E402


def o(op, by, **fields):
    """A valid-looking order: op, fields, by, and a why."""
    return {"op": op, **fields, "by": by, "why": "test"}


def has(problems, text):
    assert any(text in p for p in problems), f"expected a problem with {text!r}, got {problems}"


def rules(merged):
    return sorted(c.rule for c in merged.conflicts)


def json_blocks(md):
    return re.findall(r"```json\n(.*?)\n```", md, re.S)


def check_no_hoi4_import():
    assert "hoi4" not in sys.modules, "hoi4_orderspec must not import hoi4.py"


def check_docs_examples():
    """Every op has an example in docs/orders.md, every example is valid, and each table row names the owners."""
    md = (ROOT / "docs" / "orders.md").read_text(encoding="utf-8")
    seen, replies, budgets, results = set(), 0, 0, 0
    for block in json_blocks(md):
        try:
            whole = json.loads(block)
        except json.JSONDecodeError:
            whole = None
        if isinstance(whole, dict) and "orders" in whole:
            assert S.validate_reply(whole, agent="air") == [], S.validate_reply(whole, agent="air")
            replies += 1
        elif isinstance(whole, dict) and all(isinstance(v, dict) and "status" in v for v in whole.values()):
            assert S.validate_results(whole) == [], S.validate_results(whole)
            results += 1
        elif isinstance(whole, dict) and "op" not in whole:
            assert S.validate_budgets(whole) == [], S.validate_budgets(whole)
            budgets += 1
        else:
            for order in S.load(block):
                assert S.validate(order) == [], (order, S.validate(order))
                seen.add(order["op"])
    assert seen == set(S.OPS), f"ops without an example in docs/orders.md: {set(S.OPS) - seen}"
    assert replies == 1 and budgets == 1 and results == 1, (replies, budgets, results)
    for name, op in S.OPS.items():
        row = next((ln for ln in md.splitlines() if ln.startswith(f"| `{name}` |")), None)
        assert row, f"no table row for {name}"
        for who in (op.to if op.handler == "agent" else op.owners):
            assert who.replace("*", "\\*") in row, f"{name}: the docs row does not name {who}"
    # docs/command.md's own examples are valid orders too
    cmd = (ROOT / "docs" / "command.md").read_text(encoding="utf-8")
    charter = json.loads(json_blocks(cmd)[0])
    assert S.validate(charter) == [], S.validate(charter)
    req = json.loads(re.search(r"`(\{\"op\": \"request\.equipment\".*?\})`", cmd).group(1))
    assert S.validate(req) == [], S.validate(req)


def check_air_missions_match_executor():
    targets = json.loads((ROOT / "ui_targets.json").read_text(encoding="utf-8"))
    assert set(S.AIR_MISSIONS) == set(targets["air"]["missions"]) - {"exercises"}


def check_problems():
    ok = o("research.start", "research", slot=2, tech="Improved Machine Tools")
    assert S.validate(ok) == []
    assert S.validate(dict(ok, priority=1, id="t1.research.1", replace=True)) == []
    has(S.validate("research"), "must be a JSON object")
    has(S.validate({"slot": 2}), "missing field 'op'")
    has(S.validate(dict(ok, op="research.strat")), "did you mean 'research.start'")
    has(S.validate({k: v for k, v in ok.items() if k != "tech"}), "missing field 'tech'")
    has(S.validate({k: v for k, v in ok.items() if k != "by"}), "missing field 'by'")
    has(S.validate({k: v for k, v in ok.items() if k != "why"}), "missing field 'why'")
    # wrong types
    has(S.validate(dict(ok, slot="two")), "field 'slot' must be whole number >= 1")
    has(S.validate(dict(ok, slot=0)), "field 'slot' must be whole number >= 1")
    has(S.validate(dict(ok, slot=True)), "field 'slot'")
    has(S.validate(dict(ok, slot=2.0)), "field 'slot'")
    has(S.validate(dict(ok, tech="")), "field 'tech' must be text")
    has(S.validate(dict(ok, tech=5)), "field 'tech' must be text")
    has(S.validate(dict(ok, replace="yes")), "field 'replace' must be true or false")
    has(S.validate(dict(ok, why="two\nlines")), "field 'why' must be text")
    has(S.validate(dict(ok, why="x" * 201)), "at most 200 characters")
    has(S.validate(dict(ok, by="researcher")), "field 'by' must be agent name")
    has(S.validate(dict(ok, by="field_marshal_")), "field 'by' must be agent name")
    assert S.validate(dict(ok, by="supreme_command")) == []
    has(S.validate(dict(ok, priority=0)), "priority")
    has(S.validate(dict(ok, priority=10)), "priority")
    has(S.validate(dict(ok, id="has space")), "field 'id'")
    has(S.validate(dict(ok, factory=3)), "unknown field 'factory'")
    has(S.validate(dict(ok, to="research")), "unknown field 'to'")
    assert S.validate(o("production.set", "military_industry", line="Bf 109", factories=0)) == []
    has(S.validate(o("production.set", "military_industry", line=0, factories=1)), "field 'line'")
    has(S.validate(o("production.set", "military_industry", line=1, factories=-1)), "field 'factories'")
    has(S.validate(o("air.assign", "air", base="Holstein", mission="close air", region="West")), "air mission")
    has(S.validate(o("event.choose", "policy", title="X", option=0)), "field 'option'")
    # dates and lists
    charter = o("operation.start", "field_marshal_east", name="warsaw", goal="Take Warsaw", forces=["army 3"],
                success="Warsaw is ours", abort="deadline passed", deadline="1939-09-30")
    assert S.validate(charter) == []
    has(S.validate(dict(charter, deadline="1939.9.30")), "date YYYY-MM-DD")
    has(S.validate(dict(charter, deadline="1939-02-30")), "date YYYY-MM-DD")
    has(S.validate(dict(charter, forces=[])), "non-empty list of text")
    has(S.validate(dict(charter, forces="army 3")), "non-empty list of text")
    has(S.validate(dict(charter, name="Fall Weiss")), "operation name")
    # cost
    law = o("politics.law", "policy", category="economy", law="War Economy")
    has(S.validate(law), "give 'cost'")
    assert S.validate(dict(law, cost={"pp": 150})) == [] and S.validate(dict(law, cost={})) == []
    has(S.validate(dict(law, cost={"power": 150})), "unknown resource 'power'")
    has(S.validate(dict(law, cost={"pp": -5})), "cost 'pp' must be a number >= 0")
    has(S.validate(dict(law, cost=150)), "field 'cost' must be an object")


def check_requests():
    req = o("request.equipment", "army", to="military_industry", equipment="infantry_equipment", amount=20000)
    assert S.validate(req) == [] and S.is_request(req) and not S.is_request(o("time.advance", "army", days=1))
    has(S.validate({k: v for k, v in req.items() if k != "to"}), "missing field 'to'")
    has(S.validate(dict(req, to="navy")), "goes to military_industry, not 'navy'")
    has(S.validate(dict(req, to="the factories")), "field 'to' must be agent name")
    has(S.validate(dict(req, to="military_industry", by="military_industry")), "cannot be addressed to the agent")
    has(S.validate(dict(req, cost={"pp": 1})), "a request spends nothing")
    div = o("request.divisions", "operation_warsaw", to="field_marshal_east", count=2, template="Panzer", theater="east")
    assert S.validate(div) == [] and S.validate(dict(div, to="army")) == []
    has(S.validate(dict(div, to="air")), "goes to army or field_marshal_*")
    air = o("request.air_support", "operation_warsaw", to="air", region="Western Poland", mission="cas",
            until="1939-09-20")
    assert S.validate(air) == []
    has(S.validate(dict(air, until="soon")), "date")
    # routed to the recipient by the merge, not to the executor
    m = S.merge({"army": [req], "operation_warsaw": {"orders": [], "requests": [div, air], "report": "", "notes": ""}},
                turn=7)
    assert m.ok and m.orders == [], m.to_dict()
    assert [r["id"] for r in m.requests["military_industry"]] == ["t7.army.1"]
    assert [r["op"] for r in m.requests["field_marshal_east"]] == ["request.divisions"]
    assert m.requests["air"][0]["id"] == "t7.operation_warsaw.2"


def check_results():
    order = dict(o("politics.law", "policy", category="economy", law="War Economy", cost={"pp": 150}), id="t3.policy.1")
    done = S.result(order, "done")
    assert done == {"status": "done", "by": "policy", "op": "politics.law"}
    results = {"t3.policy.1": S.result(order, "refused", "Requires 150 political power"),
               "t3.air.1": {"status": "failed", "reason": "the cas button did not arm", "by": "air", "op": "air.assign"},
               "t3.army.1": {"status": "done", "by": "army", "op": "army.target"},
               "t3.army.2": {"status": "dropped", "reason": "held for same_target", "by": "army"}}
    assert S.validate_results(results) == [], S.validate_results(results)
    assert set(S.results_for(results, "army")) == {"t3.army.1", "t3.army.2"}
    assert S.results_for(results, "policy")["t3.policy.1"]["reason"] == "Requires 150 political power"
    has(S.validate_results({"x": {"status": "refused", "by": "policy"}}), "needs a 'reason'")
    has(S.validate_results({"x": {"status": "failed", "reason": ""}}), "needs a 'reason'")
    has(S.validate_results({"x": {"status": "ok"}}), "status must be one of")
    has(S.validate_results({"x": {"status": "done", "by": "nobody"}}), "unknown agent")
    has(S.validate_results({"x": {"status": "done", "op": "fly"}}), "unknown op")
    has(S.validate_results({"x": {"status": "done", "when": 1}}), "unknown key 'when'")
    has(S.validate_results({"x y": {"status": "done"}}), "bad order id")
    has(S.validate_results([]), "results must be an object")


def check_reply_shape():
    reply = {"orders": [o("air.assign", "air", base="Holstein", mission="cas", region="Western Poland")],
             "requests": [o("request.equipment", "air", to="military_industry", equipment="Bf 109", amount=200)],
             "report": "CAS over the Narew.", "notes": "Keep it up."}
    assert S.validate_reply(reply, agent="air") == [] and S.validate_reply(reply) == []
    has(S.validate_reply([], "air"), "one JSON object")
    has(S.validate_reply({k: v for k, v in reply.items() if k != "notes"}), "missing 'notes'")
    has(S.validate_reply(dict(reply, plan="x")), "unknown key 'plan'")
    has(S.validate_reply(dict(reply, orders={"op": "x"})), "'orders' must be a list")
    has(S.validate_reply(dict(reply, report="1\n2\n3\n4")), "'report' has 4 lines, at most 3")
    has(S.validate_reply(dict(reply, notes="\n".join("n" * 21))), "'notes' has 21 lines, at most 20")
    has(S.validate_reply(dict(reply, report=["a"])), "'report' must be text")
    has(S.validate_reply(reply, agent="navy"), "but this is navy's reply")
    has(S.validate_reply(reply, agent="admiral"), "unknown agent")
    has(S.validate_reply(dict(reply, orders=reply["requests"]), "air"), "orders[0]: request.equipment is a request")
    has(S.validate_reply(dict(reply, requests=reply["orders"]), "air"), "requests[0]: air.assign is not a request")
    has(S.validate_reply(dict(reply, orders=[{"op": "air.assign", "by": "air"}])), "orders[0]: missing field 'base'")
    # load_reply takes the text, with or without a fence
    text = json.dumps(reply)
    assert S.load_reply(text) == reply and S.load_reply("```json\n" + text + "\n```") == reply
    for bad in ("not json at all {", "[1, 2]"):
        try:
            S.load_reply(bad + "\n")
            raise AssertionError(f"load_reply must refuse {bad!r}")
        except S.OrderError:
            pass


def check_load_and_dump():
    tmp = Path(tempfile.mkdtemp())
    a = o("focus.start", "policy", focus="Rhineland")
    b = o("time.advance", "supreme_command", days=5)
    text = "# turn 12\n\n" + json.dumps(a) + "\n// the advance\n" + json.dumps(b) + "\n"
    assert S.load(text) == [a, b]
    f = tmp / "orders.jsonl"
    f.write_text(text, encoding="utf-8")
    assert S.load(f) == [a, b] and S.load(str(f)) == [a, b]
    assert S.load([a]) == [a] and S.load(json.dumps([a, b])) == [a, b] and S.load(json.dumps(a)) == [a]
    for bad, where in ((json.dumps(a) + "\n{\"op\": \n", "line 2"), ("[1, 2]", "only objects"),
                       ("\n3\n", "line 2: an order must be a JSON object"),(str(tmp / "missing.jsonl"), "cannot read")):
        try:
            S.load(bad)
            raise AssertionError(f"load must refuse {bad!r}")
        except S.OrderError as e:
            assert where in str(e), (where, str(e))
    # dump writes the documented key order, one order per line, and reads back the same
    messy = {"why": "w", "by": "research", "tech": "T", "op": "research.start", "slot": 1, "priority": 2}
    line = S.dumps([messy])
    assert line.startswith('{"op": "research.start", "slot": 1, "tech": "T", "by": "research", "why": "w"')
    S.dump([messy, b], tmp / "out.jsonl")
    assert S.load(tmp / "out.jsonl") == [messy, b]
    assert S.describe("research.start") == "research.start {slot, tech} [replace]"


def check_conflicts():
    def merged(*orders, **kw):
        replies = {}
        for x in orders:
            replies.setdefault(x["by"], []).append(x)
        return S.merge(replies, **kw)

    def one(rule, *orders, ids=None, **kw):
        m = merged(*orders, **kw)
        assert rules(m) == [rule], (rule, m.to_dict())
        if ids is not None:
            assert sorted(m.conflicts[0].ids) == sorted(ids), (rule, m.conflicts[0].ids)
        return m

    rs = lambda slot, tech: o("research.start", "research", slot=slot, tech=tech)  # noqa: E731
    # same research slot; same tech in two slots; two slots and two techs are fine
    m = one("same_target", rs(1, "A"), rs(1, "B"), turn=4)
    assert m.orders == [] and [x["id"] for x in m.held] == ["t4.research.1", "t4.research.2"]
    assert "research slot '1'" in m.conflicts[0].message
    one("same_target", rs(1, "A"), rs(2, "a"))
    assert merged(rs(1, "A"), rs(2, "B")).ok
    # same production line (by number or header), but a military and a dockyard line of one name differ
    ps = lambda line, n, **k: o("production.set", "military_industry", line=line, factories=n, **k)  # noqa: E731
    one("same_target", ps(2, 3), ps("2", 5))
    assert merged(ps("Submarine", 1), dict(ps("Submarine", 2, dockyards=True), by="naval_industry"),
                  budgets={"military_industry": {"mil_factories": 5}, "naval_industry": {"dockyards": 5}}).ok
    one("same_target", o("production.add_line", "military_industry", equipment="Ju 87"),
        o("production.add_line", "military_industry", equipment="ju  87"))
    # one focus at a time
    one("same_target", o("focus.start", "policy", focus="Rhineland"), o("focus.start", "policy", focus="Four Year Plan"))
    # politics: one law category, one advisor, one advisor slot; one decision
    law = lambda law: o("politics.law", "policy", category="economy", law=law, cost={"pp": 10})  # noqa: E731
    one("same_target", law("War Economy"), law("Partial Mobilization"))
    hire = lambda name, slot: o("politics.hire", "policy", advisor=name, slot=slot, cost={})  # noqa: E731
    one("same_target", hire("Walther Funk", "advisor-1"), hire("Walther Funk", "advisor-2"))
    one("same_target", hire("Walther Funk", "advisor-1"), hire("Fritz Todt", "advisor-1"))
    assert merged(hire("Walther Funk", "advisor-1"), hire("Fritz Todt", "advisor-2")).ok
    dec = o("decision.take", "policy", decision="War Propaganda", cost={"pp": 50})
    one("same_target", dec, dict(dec, by="army", cost={"cp": 5}), budgets={"policy": {"pp": 50}, "army": {"cp": 5}})
    # two time advances
    adv = o("time.advance", "supreme_command", days=5)
    one("same_target", adv, dict(adv, days=7))
    # air: one base twice, unless each names a different wing; rebase and assign of one base clash
    aa = lambda **k: o("air.assign", "air", **{"base": "Holstein", "mission": "cas", "region": "Western Poland", **k})  # noqa: E731,E501
    one("same_target", aa(), aa(mission="superiority"))
    one("same_target", aa(), aa(wing="KG 1"))
    one("same_target", aa(wing="KG 1"), aa(wing="kg 1"))
    assert merged(aa(wing="KG 1"), aa(wing="KG 2")).ok
    one("same_target", aa(), o("air.rebase", "air", base="Holstein", to="Oberbayern"))
    # army: one set of orders per army (target or front), one battle plan start
    one("same_target", o("army.target", "field_marshal_east", army=3, city="Warsaw"),
        o("army.front", "operation_warsaw", army=3))
    assert merged(o("army.target", "field_marshal_east", army=3, city="Warsaw"),
                  o("army.execute", "field_marshal_east", army=3)).ok
    one("same_target", o("army.execute", "army", army=3), o("army.execute", "field_marshal_east", army=3))
    # diplomacy, events
    dip = o("diplomacy.act", "policy", city="Warsaw", action="Declare war")
    one("same_target", dip, dict(dip, action="declare  WAR"))
    assert merged(dip, dict(dip, city="Paris")).ok
    one("same_target", o("event.choose", "policy", title="The Anschluss", option=1),
        o("event.choose", "policy", title="The Anschluss", option="Accept"))
    # owner: an agent giving another agent's op; only Supreme Command advances time
    m = one("owner", o("research.start", "policy", slot=1, tech="A"), ids=None, turn=2)
    assert m.held[0]["id"] == "t2.policy.1" and "belongs to research, not policy" in m.conflicts[0].message
    one("owner", o("time.advance", "army", days=3))
    one("owner", o("air.assign", "navy", base="Kiel", mission="naval", region="North Sea"))
    assert merged(o("research.start", "supreme_command", slot=1, tech="A"), adv).ok
    assert merged(o("army.target", "operation_warsaw", army=3, city="Warsaw")).ok
    end = o("operation.end", "operation_warsaw", name="lodz", outcome="taken")
    one("owner", end)
    assert merged(dict(end, name="warsaw")).ok


def check_operations():
    def charter(name, by="field_marshal_east"):
        return o("operation.start", by, name=name, goal="Take " + name, forces=["army 3"], success=name + " is ours",
                 abort="deadline passed", deadline="1939-09-30")

    end = o("operation.end", "field_marshal_east", name="warsaw", outcome="Warsaw taken")
    m = S.merge({"field_marshal_east": [charter("warsaw")]}, operations={}, turn=1)
    assert m.ok and m.orders[0]["op"] == "operation.start" and S.OPS["operation.start"].handler == "loop"
    # two starts, or a start and an end, of one operation
    assert rules(S.merge({"field_marshal_east": [charter("warsaw"), charter("warsaw")]})) == ["same_target"]
    assert rules(S.merge({"field_marshal_east": [charter("warsaw"), end]})) == ["same_target"]
    # with the running charters: a start of a running one, an end of an unknown one
    running = {"warsaw": dict(charter("warsaw"), id="t1.field_marshal_east.1")}
    assert rules(S.merge({"field_marshal_east": [charter("warsaw")]}, operations=running)) == ["operation_active"]
    assert S.merge({"field_marshal_east": [end]}, operations=running).ok
    assert rules(S.merge({"field_marshal_east": [end]}, operations={})) == ["operation_unknown"]
    assert rules(S.merge({"field_marshal_east": [end]}, operations=[])) == ["operation_unknown"]
    assert S.merge({"field_marshal_east": [end]}).ok, "without operations the merge cannot know"
    # at most three per field marshal
    three = {n: charter(n) for n in ("warsaw", "lodz", "krakow")}
    m = S.merge({"field_marshal_east": [charter("posen")]}, operations=three)
    assert rules(m) == ["too_many_operations"] and "would run 4" in m.conflicts[0].message
    assert S.merge({"field_marshal_west": [charter("posen", "field_marshal_west")]}, operations=three).ok
    two = dict(list(three.items())[:2])
    assert S.merge({"field_marshal_east": [charter("posen")]}, operations=two).ok
    m = S.merge({"field_marshal_east": [charter("posen"), charter("danzig")]}, operations=two)
    assert rules(m) == ["too_many_operations"] and len(m.held) == 2


def check_budgets():
    law = o("politics.law", "policy", category="economy", law="War Economy", cost={"pp": 150})
    hire = o("politics.hire", "policy", advisor="Walther Funk", cost={"pp": 100})
    # political power spent twice: each fits, together they do not
    m = S.merge({"policy": [law, hire]}, budgets={"policy": {"pp": 200}}, turn=9)
    assert rules(m) == ["over_budget"] and m.orders == [] and len(m.held) == 2
    assert "policy spends 250 pp, its budget is 200" in m.conflicts[0].message
    assert S.merge({"policy": [law, hire]}, budgets={"policy": {"pp": 250}}).ok
    assert S.merge({"policy": [law, hire]}).ok, "no budgets: no budget check"
    # an agent or a resource missing from the budgets has 0
    assert rules(S.merge({"policy": [law]}, budgets={"army": {"cp": 5}})) == ["over_budget"]
    assert rules(S.merge({"policy": [law]}, budgets={"policy": {"cp": 500}})) == ["over_budget"]
    # only the over-budget agent's spending orders are held
    ps = o("production.set", "military_industry", line=1, factories=20)
    m = S.merge({"policy": [law, o("focus.start", "policy", focus="Rhineland")], "military_industry": [ps]},
                budgets={"policy": {"pp": 100}, "military_industry": {"mil_factories": 28}})
    assert [x["op"] for x in m.held] == ["politics.law"]
    assert sorted(x["op"] for x in m.orders) == ["focus.start", "production.set"]
    # production asking for more factories than exist (or than its budget)
    m = S.merge({"military_industry": [ps, dict(ps, line=2, factories=10)]},
                budgets={"military_industry": {"mil_factories": 28}})
    assert rules(m) == ["over_budget"] and "spends 30 mil_factories" in m.conflicts[0].message
    m = S.merge({"military_industry": [ps, dict(ps, line=2, factories=10)]}, available={"mil_factories": 28})
    assert rules(m) == ["over_available"] and "the country has 28" in m.conflicts[0].message
    dock = o("production.set", "naval_industry", line="Submarine", factories=12, dockyards=True)
    assert rules(S.merge({"naval_industry": [dock]}, budgets={"naval_industry": {"dockyards": 10}})) == ["over_budget"]
    assert S.merge({"naval_industry": [dock]}, budgets={"naval_industry": {"dockyards": 12, "mil_factories": 0}}).ok
    assert S.spending(dock) == {"dockyards": 12} and S.spending(law) == {"pp": 150}
    assert S.spending(o("production.add_line", "military_industry", equipment="Ju 87")) == {}
    # command power and manpower from explicit costs
    rec = o("recruit.train", "army", template="Infanterie-Division", count=10, cost={"manpower": 110000})
    dec = o("decision.take", "army", decision="Emergency Reinforcements", cost={"cp": 30})
    m = S.merge({"army": [rec, dec]}, budgets={"army": {"cp": 20, "manpower": 120000}})
    assert rules(m) == ["over_budget"] and [x["op"] for x in m.held] == ["decision.take"]
    # Supreme Command has no budget, but all orders together count against what the country has
    adv = o("decision.take", "supreme_command", decision="Annex", cost={"pp": 120})
    assert S.merge({"supreme_command": [adv]}, budgets={}).ok
    m = S.merge({"supreme_command": [adv], "policy": [law]}, budgets={"policy": {"pp": 150}}, available={"pp": 200})
    assert rules(m) == ["over_available"] and len(m.held) == 2
    # budgets that give out more than the country has: reported, nothing held
    m = S.merge({"policy": [hire]}, budgets={"policy": {"pp": 150}, "army": {"pp": 100}}, available={"pp": 200})
    assert rules(m) == ["budgets_over_available"] and m.held == [] and len(m.orders) == 1
    # malformed budgets are refused outright
    for bad in ({"policy": {"pp": -1}}, {"policy": {"power": 1}}, {"admiral": {"pp": 1}}, [1]):
        try:
            S.merge({}, budgets=bad)
            raise AssertionError(f"merge must refuse budgets {bad!r}")
        except S.OrderError:
            pass
    assert S.validate_budgets({"policy": {"pp": 150.5}, "army": {}}) == []
    has(S.validate_budgets({"policy": {"pp": "lots"}}), "budgets[policy]: budget 'pp' must be a number >= 0")
    has(S.validate_budgets({"policy": 150}), "budgets[policy]: budget must be an object")
    try:
        S.merge({}, available={"factories": 10})
        raise AssertionError("merge must refuse a malformed available")
    except S.OrderError as e:
        assert "available has unknown resource 'factories'" in str(e), str(e)


def check_merge():
    replies = {
        "research": {"orders": [o("research.start", "research", slot=1, tech="A"),
                                o("research.start", "research", slot=1, tech="B")],
                     "requests": [], "report": "", "notes": ""},
        "air": {"orders": [o("air.assign", "air", base="Holstein", mission="cas", region="Western Poland"),
                           {"op": "air.assign", "base": "Kiel", "by": "air", "why": "no mission"},
                           o("air.rebase", "air", base="Kiel", to="Holstein", priority=1, id="air-move")],
                "requests": [o("request.equipment", "air", to="military_industry", equipment="Bf 109", amount=200)],
                "report": "1\n2\n3\n4", "notes": ""},
        "supreme_command": [o("time.advance", "supreme_command", days=5, priority=1)],
        "policy": "nothing",
        "admiral": [o("time.advance", "supreme_command", days=1)],
        "army": {"orders": [o("research.start", "research", slot=3, tech="C"),
                            o("request.research", "army", to="research", tech="D")],
                 "requests": [], "report": "", "notes": ""},
    }
    before = json.dumps(replies, sort_keys=True)
    m = S.merge(replies, turn=12)
    assert json.dumps(replies, sort_keys=True) == before, "merge must not change its input"
    assert not m.ok
    # ready, in run order: priority 1 first, then as given; the time advance last whatever its priority
    assert [x["id"] for x in m.orders] == ["air-move", "t12.air.1", "t12.supreme_command.1"], m.orders
    assert all("_seq" not in x for x in m.orders + m.held)
    assert [x["id"] for x in m.held] == ["t12.research.1", "t12.research.2"]
    # dropped, with the reason and the agent; numbering counts orders then requests
    assert m.dropped["t12.air.2"]["status"] == "dropped" and "missing field 'mission'" in m.dropped["t12.air.2"]["reason"]
    assert m.dropped["t12.army.1"]["reason"] == "'by' is 'research', but this is army's reply"
    assert "is a request: it belongs in 'requests'" in m.dropped["t12.army.2"]["reason"]
    assert S.validate_results(m.dropped) == []
    assert m.requests == {"military_industry": [dict(replies["air"]["requests"][0], id="t12.air.4")]}
    has(m.problems, "air: 'report' has 4 lines")
    has(m.problems, "policy: a reply must be one JSON object")
    has(m.problems, "'admiral': unknown agent")
    m2 = S.merge({"air": {"orders": ["x", 5], "requests": [None], "report": "", "notes": ""}})
    assert sorted(m2.dropped) == ["air.1", "air.2", "air.3"] and S.validate_results(m2.dropped) == []
    assert m2.dropped["air.1"] == {"status": "dropped", "by": "air", "reason": "an order must be a JSON object, got str"}
    # ids: a duplicate id is dropped; a given id that clashes with an automatic one is avoided
    a = dict(o("focus.start", "policy", focus="A"), id="x1")
    m = S.merge({"policy": [a, dict(a, focus="B")]})
    assert [x["id"] for x in m.orders] == ["x1"] and "used twice" in m.dropped["policy.2"]["reason"]
    m = S.merge({"policy": [dict(a, id="policy.2"), o("politics.hire", "policy", advisor="F", cost={})]})
    assert sorted(x["id"] for x in m.orders) == ["policy.2", "policy.2-2"]
    # settle: Supreme Command keeps one of the held orders; the other is dropped with the rule as reason
    m = S.merge(replies, turn=12)
    orders, dropped = S.settle(m, keep=["t12.research.2"])
    # research's reply came before air's, so at one priority its order runs first
    assert [x["id"] for x in orders] == ["air-move", "t12.research.2", "t12.air.1", "t12.supreme_command.1"]
    assert dropped == {"t12.research.1": {"status": "dropped", "by": "research", "op": "research.start",
                                          "reason": "held for same_target; not kept by supreme_command"}}
    try:
        S.settle(m, keep=["t12.air.1"])
        raise AssertionError("settle must refuse an id that is not held")
    except S.OrderError:
        pass
    # the merged list round-trips through an orders file
    tmp = Path(tempfile.mkdtemp()) / "orders.jsonl"
    S.dump(orders, tmp)
    assert S.load(tmp) == [S.canonical(x) for x in orders] and all(S.validate(x) == [] for x in S.load(tmp))
    json.dumps(m.to_dict())  # the whole result is plain JSON


def check_cli():
    tmp = Path(tempfile.mkdtemp())
    good = tmp / "air.json"
    good.write_text("```json\n" + json.dumps({"orders": [], "requests": [], "report": "quiet", "notes": ""}) + "\n```",
                    encoding="utf-8")
    lines = tmp / "orders.jsonl"
    lines.write_text(json.dumps(o("focus.start", "policy", focus="Rhineland")) + "\n", encoding="utf-8")
    bad = tmp / "bad.jsonl"
    bad.write_text(json.dumps({"op": "focus.start", "by": "policy", "why": "w"}), encoding="utf-8")

    def run(*args):
        p = subprocess.run([sys.executable, str(ROOT / "hoi4_orderspec.py"), *map(str, args)], capture_output=True,
                           text=True)
        return p.returncode, p.stdout

    assert run("check", good, "--agent", "air") == (0, "reply: OK\n")
    assert run("check", lines)[0] == 0 and run("check", lines, "--agent", "army")[0] == 1
    code, out = run("check", bad)
    assert code == 1 and "order 1: missing field 'focus'" in out, out
    assert run("check", tmp / "none.jsonl")[0] == 2
    code, out = run("ops")
    assert code == 0 and len(out.splitlines()) == len(S.OPS) and "request.air_support" in out


def main():
    check_no_hoi4_import()
    check_docs_examples()
    check_air_missions_match_executor()
    check_problems()
    check_requests()
    check_results()
    check_reply_shape()
    check_load_and_dump()
    check_conflicts()
    check_operations()
    check_budgets()
    check_merge()
    check_cli()
    print("OR1 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

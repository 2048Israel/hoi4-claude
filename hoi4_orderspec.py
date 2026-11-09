"""The orders format (OR1): what the thinking agents hand the executor, and each other.

Plain Python 3, standard library only, and no import of hoi4.py, so it tests anywhere. `docs/orders.md` lists
every op with an example line; `docs/command.md` is the design it serves.

- An **order** is one JSON object: `op`, the op's fields, `by` (the agent giving it), `why` (one line for the log),
  and optionally `priority` (1 runs first, 9 last, default 5), `id`, and `cost` (what it spends).
- A **request** is an order to another agent instead of the executor: op `request.<kind>` plus `to`.
- An agent's **reply** is one object `{orders, requests, report, notes}`.
- A **budget** is `{agent: {pp, cp, civ_factories, mil_factories, dockyards, manpower}}` for one turn.
- A **result** says what happened to an order, keyed by its id: done, refused, failed, or dropped.
- `merge()` turns one turn's replies into one list for the executor. It reports conflicts and spending over
  budget, and holds those orders back for Supreme Command; it never picks a winner.

    python hoi4_orderspec.py check FILE [--agent NAME]   validate an orders file (JSON Lines) or one reply
    python hoi4_orderspec.py ops                          the ops, their fields, and who may give them
"""
from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class OrderError(ValueError):
    """Input that cannot be read as orders at all (bad JSON, a missing file, malformed budgets)."""


# ---------------------------------------------------------------- agents and resources

AGENTS = ("supreme_command", "policy", "research", "civilian_industry", "military_industry", "naval_industry",
          "air", "navy", "army")
# One agent per army group and per operation: field_marshal_east, operation_warsaw.
AGENT_TEMPLATES = ("field_marshal_", "operation_")
SUPREME = "supreme_command"

RESOURCES = ("pp", "cp", "civ_factories", "mil_factories", "dockyards", "manpower")

# The executor's air missions (ui_targets.json "air.missions", without "exercises").
AIR_MISSIONS = ("superiority", "cas", "interception", "strategic", "naval", "port", "logistics", "supply", "recon")

DEFAULT_PRIORITY = 5
MAX_WHY = 200
MAX_REPORT_LINES = 3
MAX_NOTES_LINES = 20
MAX_OPERATIONS = 3  # running operations per field marshal (docs/command.md, Operations)

_NAME = re.compile(r"[a-z0-9][a-z0-9_]*\Z")
_ID = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def is_agent(name) -> bool:
    """A known agent name: one of AGENTS, or field_marshal_<x> / operation_<x> in lower case."""
    if not isinstance(name, str):
        return False
    if name in AGENTS:
        return True
    return any(name.startswith(p) and _NAME.match(name[len(p):]) for p in AGENT_TEMPLATES)


# ---------------------------------------------------------------- field kinds

@dataclass(frozen=True)
class Kind:
    name: str                       # how the docs and the problems describe it
    check: Callable[[object], bool]


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _text(v):
    return isinstance(v, str) and v.strip() != "" and "\n" not in v and "\r" not in v


def _date(v):
    if not (isinstance(v, str) and _DATE.match(v)):
        return False
    try:
        _dt.date(int(v[:4]), int(v[5:7]), int(v[8:]))
    except ValueError:
        return False
    return True


TEXT = Kind("text", _text)
COUNT = Kind("whole number >= 1", lambda v: _is_int(v) and v >= 1)
WHOLE = Kind("whole number >= 0", lambda v: _is_int(v) and v >= 0)
REF = Kind("whole number >= 1 or text", lambda v: (_is_int(v) and v >= 1) or _text(v))
FLAG = Kind("true or false", lambda v: isinstance(v, bool))
DATE = Kind("date YYYY-MM-DD", _date)
TEXTS = Kind("non-empty list of text", lambda v: isinstance(v, list) and len(v) > 0 and all(_text(x) for x in v))
AGENT = Kind("agent name", is_agent)
MISSION = Kind("air mission (" + ", ".join(AIR_MISSIONS) + ")", lambda v: v in AIR_MISSIONS)
OPNAME = Kind("operation name (lower case, digits, _)", lambda v: isinstance(v, str) and bool(_NAME.match(v)))


def _norm(v) -> str:
    return " ".join(str(v).lower().split())


# ---------------------------------------------------------------- the ops

@dataclass(frozen=True)
class Op:
    name: str
    fields: dict                    # required field -> Kind, in the order the docs show them
    optional: dict = field(default_factory=dict)
    handler: str = "executor"       # "executor" (it clicks), "agent" (a request), "loop" (the turn loop, no click)
    owners: tuple = ()              # who may give it (fnmatch patterns; Supreme Command always may)
    to: tuple = ()                  # requests: who it may be addressed to (fnmatch patterns)
    command: str | None = None      # the executor command today; None when there is none yet
    doc: str = ""
    keys: Callable[[dict], list] = lambda o: []   # target keys: two orders sharing one conflict
    needs_cost: bool = False        # spends political or command power: `cost` must say how much

    def all_fields(self) -> dict:
        return {**self.fields, **self.optional}


def _key(label, value="", scope=None):
    """A target key. Two keys clash when label and value match and their scopes overlap (None covers all)."""
    return (label, _norm(value), None if scope is None else _norm(scope))


ARMY_TREE = ("army", "field_marshal_*", "operation_*")
INDUSTRY = ("military_industry", "naval_industry")

_OPS = [
    # The first week (PLAYBOOK).
    Op("focus.start", {"focus": TEXT}, owners=("policy",), command="act focus --name FOCUS",
       doc="start a national focus", keys=lambda o: [_key("national focus")]),
    Op("research.start", {"slot": COUNT, "tech": TEXT}, {"replace": FLAG}, owners=("research",),
       command="act research --slot SLOT --tech TECH [--replace]",
       doc="start a tech in a research slot; replace: allow replacing what the slot researches now",
       keys=lambda o: [_key("research slot", o["slot"]), _key("tech", o["tech"])]),
    Op("production.set", {"line": REF, "factories": WHOLE}, {"dockyards": FLAG}, owners=INDUSTRY,
       command="act production --line N | --name LINE --add/--remove (dockyard lines: EX4)",
       doc="set a production line (its number 1-5, or its header text) to this many factories; "
           "dockyards: true for a naval line",
       keys=lambda o: [_key("production line", o["line"], "dock" if o.get("dockyards") else "mil")]),
    Op("production.add_line", {"equipment": TEXT}, {"factories": WHOLE, "dockyards": FLAG}, owners=INDUSTRY,
       command=None, doc="a new production line for this equipment (or ship type), with factories on it",
       keys=lambda o: [_key("new production line", o["equipment"])]),
    Op("construction.queue", {"building": TEXT, "count": COUNT}, {"state": TEXT}, owners=("civilian_industry",),
       command="act build --building BUILDING --count N (in a named state: EX6)",
       doc="queue buildings; state: in that state, else where the most slots are free"),
    Op("recruit.train", {"template": TEXT, "count": COUNT}, owners=("army",),
       command="act recruit --count N --template TEMPLATE", doc="queue divisions of a template, each trained once"),
    Op("politics.hire", {"advisor": TEXT}, {"slot": TEXT}, owners=("policy",), needs_cost=True,
       command="act idea --slot SLOT --name ADVISOR",
       doc="hire an advisor, staff member or designer; slot as `read ideas` names it, e.g. advisor-3",
       keys=lambda o: [_key("advisor", o["advisor"])] + ([_key("advisor slot", o["slot"])] if "slot" in o else [])),
    Op("politics.law", {"category": TEXT, "law": TEXT}, owners=("policy",), needs_cost=True,
       command="act idea --slot law-CATEGORY --name LAW",
       doc="change a law; category: conscription, trade or economy", keys=lambda o: [_key("law", o["category"])]),
    Op("decision.take", {"decision": TEXT}, owners=("policy", "army", "air", "navy"), needs_cost=True,
       command="act decision --name DECISION", doc="take a decision by its name",
       keys=lambda o: [_key("decision", o["decision"])]),
    Op("time.advance", {"days": COUNT}, owners=(), command="advance DAYS",
       doc="let days pass, then pause (Supreme Command only)", keys=lambda o: [_key("time advance")]),
    # What the executor does besides.
    Op("air.assign", {"base": TEXT, "mission": MISSION, "region": TEXT}, {"wing": TEXT}, owners=("air",),
       command="act air assign --base BASE [--wing WING] --mission MISSION --region-name REGION",
       doc="give a base's wings (or one wing) a mission over a region",
       keys=lambda o: [_key("air base", o["base"], o.get("wing"))]),
    Op("air.rebase", {"base": TEXT, "to": TEXT}, {"wing": TEXT}, owners=("air",),
       command="act air rebase --base BASE --to X Y [--only WING]",
       doc="move a base's wings (or one wing) to another air base",
       keys=lambda o: [_key("air base", o["base"], o.get("wing"))]),
    Op("army.target", {"army": COUNT, "city": TEXT}, owners=ARMY_TREE, command="act army target --army N --city CITY",
       doc="send an army at a city", keys=lambda o: [_key("army orders", o["army"])]),
    Op("army.front", {"army": COUNT}, {"against": TEXT}, owners=ARMY_TREE, command="act army front --army N --at X Y",
       doc="give an army a front line; against: the country across that border",
       keys=lambda o: [_key("army orders", o["army"])]),
    Op("army.execute", {"army": COUNT}, owners=ARMY_TREE, command="act army execute --army N",
       doc="start an army's battle plan", keys=lambda o: [_key("army execute", o["army"])]),
    Op("diplomacy.act", {"city": TEXT, "action": TEXT}, owners=("policy",),
       command="act diplomacy --city CITY --action ACTION",
       doc="a diplomatic action on the country that owns the city; declaring war needs Supreme Command",
       keys=lambda o: [_key("diplomatic action", o["city"] + " / " + o["action"])]),
    Op("event.choose", {"title": TEXT, "option": REF}, owners=("policy",), command="act event --option N",
       doc="choose an option (its number from 1, or its text) of the open event with this title",
       keys=lambda o: [_key("event", o["title"])]),
    # Operations: handled by the turn loop, which starts or ends the operation agent.
    Op("operation.start", {"name": OPNAME, "goal": TEXT, "forces": TEXTS, "success": TEXT, "abort": TEXT,
                           "deadline": DATE},
       handler="loop", owners=("army", "field_marshal_*"),
       doc="start an operation agent with this charter; success and abort are plain sentences",
       keys=lambda o: [_key("operation", o["name"])]),
    Op("operation.end", {"name": OPNAME, "outcome": TEXT}, handler="loop", owners=ARMY_TREE,
       doc="end an operation and give its forces back", keys=lambda o: [_key("operation", o["name"])]),
]

# Requests: orders to another agent, delivered in its next input. Anyone may ask.
_REQUESTS = [
    ("equipment", {"equipment": TEXT, "amount": COUNT}, ("military_industry",), "equipment to be produced"),
    ("divisions", {"count": COUNT, "template": TEXT, "theater": TEXT}, ("army", "field_marshal_*"),
     "divisions for a theater"),
    ("air_support", {"region": TEXT, "mission": MISSION, "until": DATE}, ("air",), "air missions over a region"),
    ("construction", {"building": TEXT, "state": TEXT}, ("civilian_industry",), "a building in a state"),
    ("ships", {"type": TEXT, "count": COUNT}, ("naval_industry",), "ships to be built"),
    ("research", {"tech": TEXT}, ("research",), "a tech to be researched"),
]
_OPTIONAL_REQUEST = {"construction": {"count": COUNT}}
for _kind, _fields, _to, _doc in _REQUESTS:
    _OPS.append(Op("request." + _kind, {"to": AGENT, **_fields}, _OPTIONAL_REQUEST.get(_kind, {}), handler="agent",
                   to=_to, doc=_doc))
del _kind, _fields, _to, _doc

OPS ={op.name: op for op in _OPS}
COMMON = {"by": AGENT, "why": TEXT}
COMMON_OPTIONAL = ("priority", "id", "cost")


def is_request(order) -> bool:
    return isinstance(order, dict) and isinstance(order.get("op"), str) and order["op"].startswith("request.")


def describe(name: str) -> str:
    """One line for an op: `research.start {slot, tech} [replace]`."""
    op = OPS[name]
    s = f"{op.name} {{{', '.join(op.fields)}}}"
    if op.optional:
        s += f" [{', '.join(op.optional)}]"
    return s


# ---------------------------------------------------------------- validation

def _close(word, choices):
    near = difflib.get_close_matches(str(word), list(choices), n=1)
    return f" (did you mean '{near[0]}'?)" if near else ""


def _matches(name, patterns) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def _cost_problems(cost) -> list:
    if not isinstance(cost, dict):
        return [f"field 'cost' must be an object of {', '.join(RESOURCES)}"]
    out = []
    for k, v in cost.items():
        if k not in RESOURCES:
            out.append(f"cost has unknown resource '{k}'{_close(k, RESOURCES)}")
        elif not ((_is_int(v) or isinstance(v, float)) and v >= 0):
            out.append(f"cost '{k}' must be a number >= 0, got {v!r}")
    return out


def validate(order) -> list:
    """Every problem with one order or request, as text; [] when it is valid."""
    if not isinstance(order, dict):
        return [f"an order must be a JSON object, got {type(order).__name__}"]
    name = order.get("op")
    if name is None:
        return ["missing field 'op'"]
    if name not in OPS:
        return [f"unknown op {name!r}{_close(name, OPS)}"]
    op = OPS[name]
    problems = []
    want = {**op.fields, **COMMON}
    for f, kind in want.items():
        if f not in order:
            problems.append(f"missing field '{f}'")
        elif not kind.check(order[f]):
            problems.append(f"field '{f}' must be {kind.name}, got {order[f]!r}")
    for f, kind in op.optional.items():
        if f in order and not kind.check(order[f]):
            problems.append(f"field '{f}' must be {kind.name}, got {order[f]!r}")
    known = set(want) | set(op.optional) | set(COMMON_OPTIONAL) | {"op"}
    for f in order:
        if f not in known:
            problems.append(f"unknown field '{f}' for {name}{_close(f, known - {'op'})}")
    why = order.get("why")
    if isinstance(why, str) and len(why) > MAX_WHY:
        problems.append(f"field 'why' is one line of at most {MAX_WHY} characters, got {len(why)}")
    if "priority" in order and not (_is_int(order["priority"]) and 1 <= order["priority"] <= 9):
        problems.append(f"field 'priority' must be a whole number 1-9, got {order['priority']!r}")
    if "id" in order and not (isinstance(order["id"], str) and _ID.match(order["id"])):
        problems.append(f"field 'id' must be letters, digits and . _ : - only, got {order['id']!r}")
    if "cost" in order and op.handler == "agent":
        problems.append("a request spends nothing: the agent that answers it pays, so it has no 'cost'")
    elif "cost" in order:
        problems += _cost_problems(order["cost"])
    elif op.needs_cost:
        problems.append(f"{name} spends power: give 'cost', e.g. {{\"pp\": 150}} ({{}} if it is free)")
    if op.handler == "agent" and is_agent(order.get("to")):
        if not _matches(order["to"], op.to):
            problems.append(f"{name} goes to {' or '.join(op.to)}, not '{order['to']}'")
        if order.get("to") == order.get("by"):
            problems.append("a request cannot be addressed to the agent that makes it")
    return problems


def validate_reply(reply, agent: str | None = None) -> list:
    """Every problem with an agent's reply `{orders, requests, report, notes}`; [] when it is valid.
    With `agent`, every order and request must also be `by` that agent."""
    problems = _reply_shape(reply, agent)
    if not isinstance(reply, dict):
        return problems
    for where, i, item in _items(reply):
        problems += [f"{where}[{i}]: {p}" for p in _item_problems(item, where, agent)]
    return problems


def _reply_shape(reply, agent) -> list:
    if not isinstance(reply, dict):
        return ["a reply must be one JSON object {orders, requests, report, notes}"]
    problems = []
    if agent is not None and not is_agent(agent):
        problems.append(f"unknown agent {agent!r}")
    for k in ("orders", "requests", "report", "notes"):
        if k not in reply:
            problems.append(f"missing '{k}'")
    for k in reply:
        if k not in ("orders", "requests", "report", "notes"):
            problems.append(f"unknown key '{k}' in the reply{_close(k, ('orders', 'requests', 'report', 'notes'))}")
    for k in ("orders", "requests"):
        if k in reply and not isinstance(reply[k], list):
            problems.append(f"'{k}' must be a list")
    for k, most in (("report", MAX_REPORT_LINES), ("notes", MAX_NOTES_LINES)):
        if k in reply:
            if not isinstance(reply[k], str):
                problems.append(f"'{k}' must be text")
            elif len(reply[k].splitlines()) > most:
                problems.append(f"'{k}' has {len(reply[k].splitlines())} lines, at most {most}")
    return problems


def _items(reply):
    for where in ("orders", "requests"):
        items = reply.get(where)
        if isinstance(items, list):
            for i, item in enumerate(items):
                yield where, i, item


def _item_problems(item, where, agent) -> list:
    problems = validate(item)
    if isinstance(item, dict) and item.get("op") in OPS:
        if where == "orders" and is_request(item):
            problems.append(f"{item['op']} is a request: it belongs in 'requests'")
        if where == "requests" and not is_request(item):
            problems.append(f"{item['op']} is not a request: it belongs in 'orders'")
    if agent is not None and isinstance(item, dict) and "by" in item and item["by"] != agent:
        problems.append(f"'by' is {item['by']!r}, but this is {agent}'s reply")
    return problems


def validate_budgets(budgets) -> list:
    """Problems with a turn's budgets {agent: {resource: amount}}."""
    if not isinstance(budgets, dict):
        return ["budgets must be an object {agent: {" + ", ".join(RESOURCES) + "}}"]
    problems = []
    for agent, b in budgets.items():
        if not is_agent(agent):
            problems.append(f"budgets: unknown agent {agent!r}")
        problems += [f"budgets[{agent}]: {p.replace('cost', 'budget', 1)}" for p in _cost_problems(b)]
    return problems


# ---------------------------------------------------------------- results

RESULT_STATUSES = ("done", "refused", "failed", "dropped")
# done: the executor did it and its check passed. refused: the game said no (reason: the game's text).
# failed: the executor could not do it (a check failed, no executor command yet). dropped: never run
# (invalid, or held for a conflict and not kept by Supreme Command).


def result(order: dict, status: str, reason: str | None = None) -> dict:
    """One result entry for an order, to store under its id."""
    r = {"status": status}
    if isinstance(order, dict):
        r.update({k: order[k] for k in ("by", "op") if order.get(k) is not None})
    if reason:
        r["reason"] = reason
    return r


def validate_results(results) -> list:
    """Problems with a results object {order id: {status, reason, by, op}}."""
    if not isinstance(results, dict):
        return ["results must be an object {order id: {status, reason, by, op}}"]
    problems = []
    for oid, r in results.items():
        if not (isinstance(oid, str) and _ID.match(oid)):
            problems.append(f"results: bad order id {oid!r}")
        if not isinstance(r, dict):
            problems.append(f"results[{oid}]: must be an object")
            continue
        st = r.get("status")
        if st not in RESULT_STATUSES:
            problems.append(f"results[{oid}]: status must be one of {', '.join(RESULT_STATUSES)}, got {st!r}")
        elif st != "done" and not _text(r.get("reason")):
            problems.append(f"results[{oid}]: a {st} result needs a 'reason'")
        if "by" in r and not is_agent(r["by"]):
            problems.append(f"results[{oid}]: unknown agent {r['by']!r}")
        if "op" in r and r["op"] not in OPS:
            problems.append(f"results[{oid}]: unknown op {r['op']!r}")
        for k in r:
            if k not in ("status", "reason", "by", "op"):
                problems.append(f"results[{oid}]: unknown key '{k}'")
    return problems


def results_for(results: dict, agent: str) -> dict:
    """The results of one agent's orders, for its next input."""
    return {oid: r for oid, r in results.items() if isinstance(r, dict) and r.get("by") == agent}


# ---------------------------------------------------------------- load and dump

def _read(src) -> str:
    if isinstance(src, Path):
        try:
            return src.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise OrderError(f"cannot read {src}: {e}") from None
    if isinstance(src, str):
        s = src.lstrip()
        if "\n" in src or s.startswith(("{", "[")) or s == "":
            return src
        return _read(Path(src))
    raise OrderError(f"cannot load orders from {type(src).__name__}")


def load(src) -> list:
    """Orders from JSON Lines (a path, a Path, or the text itself), a JSON array, or a list already parsed.
    Blank lines and lines starting with # or // are skipped. Bad JSON raises OrderError with the line number;
    the orders themselves are checked by validate()."""
    if isinstance(src, list):
        return list(src)
    text = _read(src)
    if text.lstrip().startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise OrderError(f"line {e.lineno}: not JSON: {e.msg}") from None
        if not all(isinstance(x, dict) for x in data):
            raise OrderError("a JSON array of orders must hold only objects")
        return data
    return _lines(text)


def _lines(text: str) -> list:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith(("#", "//")):
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            raise OrderError(f"line {n}: not JSON: {e.msg}") from None
        if not isinstance(obj, dict):
            raise OrderError(f"line {n}: an order must be a JSON object, got {type(obj).__name__}")
        out.append(obj)
    return out


_FENCE = re.compile(r"\A\s*```(?:json)?\s*\n(.*?)\n\s*```\s*\Z", re.S)


def load_reply(src) -> dict:
    """One agent reply (a path, a Path, or the text), allowing one ```json fence around it."""
    if isinstance(src, dict):
        return src
    text = _read(src)
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise OrderError(f"line {e.lineno}: the reply is not JSON: {e.msg}") from None
    if not isinstance(data, dict):
        raise OrderError("a reply must be one JSON object {orders, requests, report, notes}")
    return data


def canonical(order: dict) -> dict:
    """The same order with its keys in the documented order: op, fields, by, why, priority, cost, id."""
    op = OPS.get(order.get("op"))
    first = ["op"] + (list(op.all_fields()) if op else []) + list(COMMON) + list(COMMON_OPTIONAL)
    out = {k: order[k] for k in first if k in order}
    out.update({k: v for k, v in order.items() if k not in out})
    return out


def dumps(orders) -> str:
    """Orders as JSON Lines, one per line, keys in the documented order."""
    return "".join(json.dumps(canonical(o), ensure_ascii=False) + "\n" for o in orders)


def dump(orders, path) -> None:
    Path(path).write_text(dumps(orders), encoding="utf-8")


# ---------------------------------------------------------------- the merge step

@dataclass
class Conflict:
    rule: str       # same_target, owner, over_budget, over_available, budgets_over_available,
                    # operation_active, operation_unknown, too_many_operations
    message: str
    ids: list       # the orders held because of it (none for budgets_over_available)

    def to_dict(self):
        return {"rule": self.rule, "message": self.message, "ids": list(self.ids)}


@dataclass
class MergeResult:
    orders: list        # ready: in run order, each with an id. The executor runs those with handler "executor";
                        # the turn loop handles "loop" ops (operation.start / end)
    held: list          # valid orders in at least one conflict: they wait for Supreme Command (settle())
    conflicts: list     # Conflict, one per rule broken
    requests: dict      # recipient agent -> its requests, for its next input
    dropped: dict       # order id -> result: invalid orders, never run
    problems: list      # problems with a reply as a whole (its shape, an unknown agent)
    seq: dict = field(default_factory=dict, repr=False)   # order id -> place in the replies, for settle()

    @property
    def ok(self) -> bool:
        return not (self.conflicts or self.dropped or self.problems)

    def to_dict(self) -> dict:
        return {"orders": self.orders, "held": self.held, "conflicts": [c.to_dict() for c in self.conflicts],
                "requests": self.requests, "dropped": self.dropped, "problems": self.problems}


def spending(order: dict) -> dict:
    """What an order spends: its `cost`, plus the factories a production order puts on a line."""
    out = {}
    if order.get("op") in ("production.set", "production.add_line"):
        n = order.get("factories", 0)
        if n:
            out["dockyards" if order.get("dockyards") else "mil_factories"] = n
    if isinstance(order.get("cost"), dict):
        out.update({k: v for k, v in order["cost"].items() if v})
    return out


def _sort_key(order, seq=None):
    """Run order: by priority, then as the replies gave them; a time advance always last."""
    n = order["_seq"] if seq is None else seq.get(order["id"], 0)
    return (order["op"] == "time.advance", order.get("priority", DEFAULT_PRIORITY), n)


def _strip(order):
    return {k: v for k, v in order.items() if k != "_seq"}


def merge(replies: dict, budgets: dict | None = None, available: dict | None = None,
          operations: dict | list | None = None, turn: int | None = None) -> MergeResult:
    """One turn's replies, {agent: reply}, into one list for the executor.

    - Each order and request gets an id (`t<turn>.<agent>.<n>`, n counting the reply's orders then its requests
      from 1) unless it has one. Invalid ones are dropped with the problems as the reason.
    - Valid requests are routed to their recipient (`requests`).
    - Conflicts hold orders back, all of them, for Supreme Command to settle; nothing is guessed:
      same_target (two orders for one research slot, tech, production line, focus, law, advisor, decision,
      air base, army, event, operation, or two time advances), owner (an agent giving another agent's op),
      over_budget (an agent spending past its budget), over_available (all agents together past what the
      country has), operation_active / operation_unknown / too_many_operations (with `operations`, the
      running charters by name).
    - budgets: {agent: {resource: amount}}; an agent or resource missing from it has 0. None skips the check.
      Supreme Command has no budget, but counts towards `available`.
    A reply may also be a plain list of orders and requests (an orders file)."""
    if budgets is not None and (bp := validate_budgets(budgets)):
        raise OrderError("; ".join(bp))
    if available is not None and (ap := _cost_problems(available)):
        raise OrderError("available: " + "; ".join(ap))
    if not isinstance(replies, dict):
        raise OrderError("replies must be an object {agent: reply}")
    prefix = f"t{turn}." if turn is not None else ""
    valid, requests, dropped, problems, used = [], {}, {}, [], set()
    seq = 0
    for agent, reply in replies.items():
        if not is_agent(agent):
            problems.append(f"{agent!r}: unknown agent, its reply was not read")
            continue
        if isinstance(reply, list):
            reply = {"orders": [o for o in reply if not is_request(o)], "requests": [o for o in reply if is_request(o)]}
        else:
            problems += [f"{agent}: {p}" for p in _reply_shape(reply, agent)]
            if not isinstance(reply, dict):
                continue
        for n, (where, i, item) in enumerate(_items(reply), 1):
            oid = item.get("id") if isinstance(item, dict) else None
            item_problems = _item_problems(item, where, agent)
            if not (isinstance(oid, str) and _ID.match(oid)) or oid in used:
                if isinstance(oid, str) and oid in used:
                    item_problems.append(f"id {oid!r} is used twice")
                base = oid = f"{prefix}{agent}.{n}"
                k = 1
                while oid in used:
                    k += 1
                    oid = f"{base}-{k}"
            used.add(oid)
            if item_problems:
                op = item.get("op") if isinstance(item, dict) else None
                dropped[oid] = result({"by": agent, "op": op if op in OPS else None}, "dropped",
                                      "; ".join(item_problems))
                continue
            order = dict(item, id=oid, _seq=seq)
            seq += 1
            if is_request(order):
                requests.setdefault(order["to"], []).append(_strip(order))
            else:
                valid.append(order)

    conflicts = _target_conflicts(valid) + _owner_conflicts(valid) + _operation_conflicts(valid, operations)
    conflicts += _budget_conflicts(valid, budgets, available)
    held_ids = {i for c in conflicts for i in c.ids}
    ready = sorted((o for o in valid if o["id"] not in held_ids), key=_sort_key)
    held = sorted((o for o in valid if o["id"] in held_ids), key=_sort_key)
    return MergeResult([_strip(o) for o in ready], [_strip(o) for o in held], conflicts, requests, dropped,
                       problems, {o["id"]: o["_seq"] for o in valid})


def _target_conflicts(orders) -> list:
    groups = {}
    for o in orders:
        for label, value, scope in OPS[o["op"]].keys(o):
            groups.setdefault((label, value), []).append((o, scope))
    out = []
    for (label, value), members in groups.items():
        clash = []
        for i, (a, sa) in enumerate(members):
            for b, sb in members[i + 1:]:
                if sa is None or sb is None or sa == sb:
                    clash += [x["id"] for x in (a, b) if x["id"] not in clash]
        if clash:
            what = f"{label} {value!r}" if value else label
            out.append(Conflict("same_target", f"{len(clash)} orders for the same {what}: {', '.join(clash)}", clash))
    return out


def _owner_conflicts(orders) -> list:
    out = []
    for o in orders:
        op, by = OPS[o["op"]], o["by"]
        if by == SUPREME:
            continue
        if not _matches(by, op.owners):
            owners = " or ".join(op.owners) if op.owners else SUPREME
            out.append(Conflict("owner", f"{o['id']}: {o['op']} belongs to {owners}, not {by}", [o["id"]]))
        elif o["op"] == "operation.end" and by.startswith("operation_") and by != "operation_" + o["name"]:
            out.append(Conflict("owner", f"{o['id']}: {by} can only end its own operation, not "
                                         f"{o['name']!r}", [o["id"]]))
    return out


def _operation_conflicts(orders, operations) -> list:
    if operations is None:
        return []
    running = operations if isinstance(operations, dict) else {n: {} for n in operations}
    out = []
    starts = [o for o in orders if o["op"] == "operation.start"]
    for o in starts:
        if o["name"] in running:
            out.append(Conflict("operation_active", f"{o['id']}: operation {o['name']!r} is already running",
                                [o["id"]]))
    started = {o["name"] for o in starts}
    for o in orders:
        if o["op"] == "operation.end" and o["name"] not in running and o["name"] not in started:
            out.append(Conflict("operation_unknown", f"{o['id']}: no running operation {o['name']!r}", [o["id"]]))
    per = {}
    for name, charter in running.items():
        by = charter.get("by") if isinstance(charter, dict) else None
        if by:
            per[by] = per.get(by, 0) + 1
    new = {}
    for o in starts:
        if o["name"] not in running:
            new.setdefault(o["by"], []).append(o["id"])
    for by, ids in new.items():
        if by.startswith("field_marshal_") and per.get(by, 0) + len(ids) > MAX_OPERATIONS:
            out.append(Conflict("too_many_operations", f"{by} would run {per.get(by, 0) + len(ids)} operations, "
                                                       f"at most {MAX_OPERATIONS}", ids))
    return out


def _fmt(n):
    return f"{n:g}" if isinstance(n, float) else str(n)


def _budget_conflicts(orders, budgets, available) -> list:
    out = []
    spent = {}   # (agent, resource) -> [total, ids]
    for o in orders:
        for res, amount in spending(o).items():
            entry = spent.setdefault((o["by"], res), [0, []])
            entry[0] += amount
            entry[1].append(o["id"])
    if budgets is not None:
        for (agent, res), (total, ids) in spent.items():
            if agent == SUPREME:
                continue
            have = budgets.get(agent, {}).get(res, 0)
            if total > have:
                out.append(Conflict("over_budget", f"{agent} spends {_fmt(total)} {res}, its budget is {_fmt(have)}: "
                                                   f"{', '.join(ids)}", ids))
    if available is not None:
        for res in RESOURCES:
            if res not in available:
                continue
            total = sum(t for (a, r), (t, _) in spent.items() if r == res)
            ids = [i for (a, r), (_, ii) in spent.items() if r == res for i in ii]
            if total > available[res]:
                out.append(Conflict("over_available", f"all orders spend {_fmt(total)} {res}, the country has "
                                                      f"{_fmt(available[res])}: {', '.join(ids)}", ids))
            if budgets is not None:
                given = sum(b.get(res, 0) for b in budgets.values() if isinstance(b, dict))
                if given > available[res]:
                    out.append(Conflict("budgets_over_available", f"the budgets give out {_fmt(given)} {res}, "
                                                                  f"the country has {_fmt(available[res])}", []))
    return out


def settle(merged: MergeResult, keep, by: str = SUPREME) -> tuple:
    """Supreme Command's answer to the conflicts: the held orders to keep run with the ready ones, in run order;
    the others are dropped. Returns (orders, dropped results by id)."""
    keep = set(keep)
    held = {o["id"]: o for o in merged.held}
    unknown = keep - set(held)
    if unknown:
        raise OrderError(f"not held: {', '.join(sorted(unknown))}")
    orders = merged.orders + [o for i, o in held.items() if i in keep]
    orders.sort(key=lambda o: _sort_key(o, merged.seq))
    rules = {}
    for c in merged.conflicts:
        for i in c.ids:
            rules.setdefault(i, []).append(c.rule)
    dropped = {i: result(o, "dropped", f"held for {', '.join(rules.get(i, ['a conflict']))}; not kept by {by}")
               for i, o in held.items() if i not in keep}
    return orders, dropped


# ---------------------------------------------------------------- command line

def _check(path: str, agent: str | None) -> int:
    text = _read(Path(path))
    fence = _FENCE.match(text)
    try:
        whole = json.loads(fence.group(1) if fence else text)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, dict) and "op" not in whole:
        problems = validate_reply(whole, agent)
        what = "reply"
    else:
        if isinstance(whole, dict):
            orders = [whole]
        elif isinstance(whole, list):
            orders = load(whole)
        else:
            orders = _lines(text)
        problems = []
        for n, o in enumerate(orders, 1):
            ps = validate(o)
            if agent is not None and o.get("by") != agent:
                ps.append(f"'by' is {o.get('by')!r}, expected {agent!r}")
            problems += [f"order {n}: {p}" for p in ps]
        what = f"{len(orders)} order(s)"
    for p in problems:
        print(p)
    print(f"{what}: {'OK' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="hoi4_orderspec.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate an orders file (JSON Lines) or one agent reply")
    c.add_argument("file")
    c.add_argument("--agent", help="every order must be by this agent")
    sub.add_parser("ops", help="list the ops, their fields and who may give them")
    a = ap.parse_args(argv)
    if a.cmd == "ops":
        for name, op in OPS.items():
            who = ("to " + " or ".join(op.to)) if op.handler == "agent" else ("by " + (", ".join(op.owners) or SUPREME))
            print(f"{describe(name):58} {who:40} {op.doc}")
        return 0
    try:
        return _check(a.file, a.agent)
    except OrderError as e:
        print(f"error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())

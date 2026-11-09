r"""Offline checks for the agent definitions (TH1): .claude/agents/hoi4-<role>.md and their worked examples.

No game and no Windows needed:  .venv\Scripts\python.exe tests\test_TH1.py

- each of the ten agent files exists, has at most 80 lines, and its frontmatter names it, describes it, gives a
  model (the army tree the strongest, the others a cheaper one) and limits its tools to Read;
- each has one worked example: docs/agents/examples/<role>.in.json (a trimmed ST1 slice with budget, notes,
  requests and results) and <role>.out.json (the reply), the same reply as the agent file's own json block;
- every example reply passes OR1's validate_reply() for its agent, and merges within its budget with no conflict;
- the ten replies merged as one turn have no conflict, and every request in an example input was made by
  another example's reply.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_orderspec as S  # noqa: E402

AGENTS = ROOT / ".claude" / "agents"
EXAMPLES = ROOT / "docs" / "agents" / "examples"
ROLES = ["policy", "research", "civilian_industry", "military_industry", "naval_industry", "air", "navy", "army",
         "field_marshal", "operation"]
ARMY_TREE = {"army", "field_marshal", "operation"}
STRONGEST, CHEAPER = "fable", "sonnet"
MAX_LINES = 80
INPUT_KEYS = {"agent", "turn", "due", "budget", "state", "notes", "requests", "results"}
OPTIONAL_INPUT_KEYS = {"directive"}


def path(role):
    return AGENTS / f"hoi4-{role.replace('_', '-')}.md"


def frontmatter(text):
    """{key: value} from the '---' block at the top (one line per key)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter at the top"
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        assert sep and key.strip() and value.strip(), f"frontmatter line {line!r} is not 'key: value'"
        assert ": " not in value and " #" not in value and value[0] not in "'\"[{&*!|>%@`", \
            f"frontmatter {key!r}: not a plain YAML value"
        out[key.strip()] = value.strip()
    return out


def example(role):
    inp = json.loads((EXAMPLES / f"{role}.in.json").read_text(encoding="utf-8"))
    out = json.loads((EXAMPLES / f"{role}.out.json").read_text(encoding="utf-8"))
    return inp, out


def check_files():
    assert sorted(p.name for p in AGENTS.glob("*.md")) == sorted(path(r).name for r in ROLES), \
        "the agent files are exactly the ten roles of docs/command.md"
    for role in ROLES:
        text = path(role).read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= MAX_LINES, f"{path(role).name}: {len(lines)} lines, at most {MAX_LINES}"
        fm = frontmatter(text)
        assert fm.get("name") == path(role).stem, f"{path(role).name}: name is {fm.get('name')!r}"
        assert len(fm.get("description", "")) >= 40, f"{path(role).name}: a description says what it owns"
        want = STRONGEST if role in ARMY_TREE else CHEAPER
        assert fm.get("model") == want, f"{path(role).name}: model {fm.get('model')!r}, expected {want!r}"
        assert fm.get("tools") == "Read", f"{path(role).name}: tools {fm.get('tools')!r}, only Read"
        for heading in ("## Yours, and not yours", "## Goals", "## Doctrine", "## Orders and requests",
                        "## Input", "## Reply", "## Example"):
            assert heading in text, f"{path(role).name}: no {heading!r} section"


def check_examples():
    for role in ROLES:
        inp, out = example(role)
        agent = inp["agent"]
        assert INPUT_KEYS <= set(inp) <= INPUT_KEYS | OPTIONAL_INPUT_KEYS, f"{role}.in.json keys {sorted(inp)}"
        assert S.is_agent(agent), f"{role}.in.json: {agent!r} is not an OR1 agent"
        assert agent == role or agent.startswith(role + "_"), f"{role}.in.json is for {agent}"
        assert inp["state"].get("agent") == agent, f"{role}.in.json: the slice is for {inp['state'].get('agent')}"
        assert not S.validate_budgets({agent: inp["budget"]}), f"{role}.in.json: bad budget"
        assert not S.validate_results(inp["results"]), f"{role}.in.json: bad results"
        for r in inp["requests"]:
            assert not S.validate(r) and S.is_request(r) and r["to"] == agent, f"{role}.in.json: bad request {r}"
        problems = S.validate_reply(out, agent=agent)
        assert problems == [], f"{role}.out.json: {problems}"
        merged = S.merge({agent: out}, budgets={agent: inp["budget"]}, turn=inp["turn"])
        assert not merged.conflicts and not merged.dropped, \
            f"{role}.out.json: {[c.rule for c in merged.conflicts]} {merged.dropped}"
        assert out["orders"] or out["requests"], f"{role}.out.json gives nothing"
        blocks = re.findall(r"```json\n(.*?)\n```", path(role).read_text(encoding="utf-8"), re.S)
        assert len(blocks) == 1 and json.loads(blocks[0]) == out, \
            f"{path(role).name}: its json block is not {role}.out.json"
        assert f"docs/agents/examples/{role}.in.json" in path(role).read_text(encoding="utf-8")


def check_one_turn():
    """The examples tell one story: merged as one turn they clash nowhere, and each request an input carries
    was made by another example's reply."""
    replies, budgets = {}, {}
    for role in ROLES:
        inp, out = example(role)
        replies[inp["agent"]] = out
        budgets[inp["agent"]] = inp["budget"]
    merged = S.merge(replies, budgets=budgets, turn=12)
    assert not merged.conflicts and not merged.dropped and not merged.problems, \
        f"{[(c.rule, c.ids) for c in merged.conflicts]} {merged.dropped} {merged.problems}"
    def bare(r):
        return {k: v for k, v in r.items() if k != "id"}
    made = [bare(r) for out in replies.values() for r in out["requests"]]
    for role in ROLES:
        inp, _ = example(role)
        for r in inp["requests"]:
            assert bare(r) in made, f"{role}.in.json: no example reply made {r}"


def check_docs():
    md = (ROOT / "docs" / "agents" / "README.md").read_text(encoding="utf-8")
    for role in ROLES:
        assert f"`{path(role).stem}`" in md, f"docs/agents/README.md does not list {path(role).stem}"


def main():
    check_files()
    check_examples()
    check_one_turn()
    check_docs()
    print("TH1 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

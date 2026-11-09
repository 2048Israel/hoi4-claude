r"""Offline checks for hoi4_focus.py, the focus planner.

No game and no Windows needed (it does not import hoi4.py):  .venv\Scripts\python.exe tests\test_FP1.py
Fixtures are handmade: tests/fixtures/focus_tree_mini.txt (8 GER focuses + 1 ITA), focus_loc/, focus_save_mini.txt.
On a PC with the game installed, the last check also reads the real German tree (read-only); elsewhere it is skipped.
"""
import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_focus as F  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
TREE = FIX / "focus_tree_mini.txt"
SAVE = FIX / "focus_save_mini.txt"
LOC = FIX / "focus_loc"


def ids(rows):
    return [r["id"] for r in rows]


def test_parser():
    b = F.parse('a = 1 # comment "x"\r\nb = "q # not a comment" c = { x y { z = 2 } }\nc = 3 d > 4 e = { }\n')
    assert b.get("a") == "1" and b.get("b") == "q # not a comment"
    assert b.all("c")[1] == "3", "repeated keys are kept in order"
    inner = b.get("c")
    assert [v for _k, _o, v in inner][:2] == ["x", "y"] and inner.blocks(None)[0].get("z") == "2"
    assert ("d", ">", "4") in b and isinstance(b.get("e"), F.Block) and len(b.get("e")) == 0
    assert F.parse("a = { b = 1 } } c = 2").get("c") == "2", "a stray } at the top is ignored"
    assert F.trigger_text(F.parse("has_war = no NOT = { tag = POL }")) == "has_war = no, NOT { tag = POL }"
    assert F.trigger_text(F.parse("a = " + "x" * 300), limit=20).endswith("...")


def test_check():
    facts = {"completed": {"A"}, "tag": "GER", "ideology": "fascism", "dlcs": {"La Resistance"},
             "rules": {"obsolete_focus_branches_visibility": "HIDE"}}
    c = lambda s: F.check(F.parse(s), facts)  # noqa: E731
    assert c("") is True and c("always = no") is False
    assert c("has_completed_focus = A") is True and c("has_completed_focus = B") is False
    assert c("NOT = { has_completed_focus = A has_completed_focus = B }") is False, "NOT is NOR"
    assert c("NOT = { has_completed_focus = B has_completed_focus = C }") is True
    assert c("OR = { has_completed_focus = B has_war = no }") is None, "unknown stays unknown"
    assert c("OR = { has_completed_focus = A has_war = no }") is True
    assert c("has_war = no has_completed_focus = B") is False, "one false is enough"
    assert c("tag = GER has_government = fascism") is True and c("has_government = communism") is False
    assert c('has_dlc = "La Resistance"') is True and c('has_dlc = "Man the Guns"') is False
    assert F.check(F.parse('has_dlc = "Man the Guns"'), {"dlcs": None}) is None, "no dlc list: unknown"
    rule = "has_game_rule = { rule = obsolete_focus_branches_visibility option = HIDE }"
    assert c(rule) is True
    # if/else: a branch not taken passes; a taken one must hold.
    assert c(f"if = {{ limit = {{ {rule} }} has_completed_focus = B }}") is False
    assert c("if = { limit = { has_completed_focus = B } always = no }") is True
    assert c("if = { limit = { has_completed_focus = B } always = no } else = { always = no }") is False
    assert c("if = { limit = { has_completed_focus = A } always = yes } else = { always = no }") is True
    assert c("if = { limit = { has_war = no } always = no }") is None
    assert c("custom_trigger_tooltip = { tooltip = X has_completed_focus = A }") is True


def test_tree():
    t = F.load_tree(TREE, "GER")
    assert t["id"] == "test_german_focus" and len(t["focuses"]) == 8
    f = t["focuses"]
    assert f["GER_root_a"]["days"] == 35 and f["GER_root_b"]["cost"] == 10.0, "cost from @long_cost"
    assert f["GER_and_child"]["days"] == 70, "no cost: the default 10"
    assert f["GER_or_child"]["prerequisites"] == [["GER_root_a", "GER_root_b"]]
    assert f["GER_and_child"]["prerequisites"] == [["GER_root_a"], ["GER_root_b"]]
    assert f["GER_left"]["mutually_exclusive"] == ["GER_right"] and f["GER_left"]["will_lead_to_war_with"] == ["POL"]
    assert f["GER_root_b"]["available"] == "has_war = no" and f["GER_right"]["bypass"] == "has_war_with = POL"
    assert f["GER_dlc_branch"]["allow_branch"] == "has_dlc = Test DLC"
    assert f["GER_left"]["line"] and f["GER_left"]["relative_position_id"] == "GER_or_child"
    assert list(F.load_tree(TREE, "ITA")["focuses"]) == ["ITA_only"], "the tree that claims the tag"
    assert F.tree_score(F.parse(TREE.read_text()).blocks("focus_tree")[0], "ITA") == 0


def test_startable():
    t = F.load_tree(TREE, "GER")
    s = lambda done, cur=None, facts=None: ids(F.startable(t, done, cur, facts))  # noqa: E731
    # Nothing done: only the roots.
    assert s([]) == ["GER_root_a", "GER_root_b"]
    # OR: one root opens the OR child, not the AND child. Completed ones are not listed.
    assert s(["GER_root_a"]) == ["GER_root_b", "GER_or_child", "GER_dlc_branch"]
    assert s(["GER_root_b"]) == ["GER_root_a", "GER_or_child"]
    # AND: both roots open the AND child.
    assert "GER_and_child" in s(["GER_root_a", "GER_root_b"])
    # Exclusion, declared on GER_left only, works both ways.
    base = ["GER_root_a", "GER_or_child"]
    assert {"GER_left", "GER_right"} <= set(s(base))
    assert "GER_right" not in s(base + ["GER_left"]) and "GER_left" not in s(base + ["GER_right"])
    # Running: not listed, and it locks out what it excludes.
    run = s(base, "GER_left")
    assert "GER_left" not in run and "GER_right" not in run and "GER_root_b" in run
    # An `available` the save answers: GER_after_left must not follow GER_root_b.
    assert "GER_after_left" in s(base + ["GER_left"])
    assert "GER_after_left" not in s(base + ["GER_left", "GER_root_b"])
    out = F.blocked(t, base + ["GER_left", "GER_root_b"])
    assert list(out) == ["GER_after_left"] and out["GER_after_left"].startswith("not available")
    # Ideology: decided when known, left to the game when not.
    assert "GER_right" not in s(base, facts={"ideology": "communism"})
    rows = {r["id"]: r for r in F.startable(t, base)}
    assert rows["GER_right"]["available_ok"] is None and rows["GER_root_b"]["available_ok"] is None
    assert rows["GER_left"]["available_ok"] is True and rows["GER_left"]["days"] == 35
    assert F.startable(t, base, facts={"ideology": "fascism"})[-1]["available_ok"] is True
    # A DLC branch: shown with the DLC, hidden without, left to the game when the DLC list is unknown.
    assert "GER_dlc_branch" in s(["GER_root_a"], facts={"dlcs": {"Test DLC"}})
    assert "GER_dlc_branch" not in s(["GER_root_a"], facts={"dlcs": set()})
    assert F.blocked(t, ["GER_root_a"], facts={"dlcs": set()})["GER_dlc_branch"].startswith("branch hidden")
    # What each one opens.
    opens = {r["id"]: r["opens"] for r in F.startable(t, [])}
    assert opens["GER_root_a"] == ["GER_or_child", "GER_dlc_branch"] and opens["GER_root_b"] == ["GER_or_child"]
    assert F.unknown_ids(t, ["GER_root_a", "GER_typo"]) == ["GER_typo"]


def test_names():
    names = F.load_names([LOC], ["GER_root_a", "GER_root_b", "GER_or_child", "GER_left", "GER_right"])
    assert names == {"GER_root_a": "Root A", "GER_root_b": "Root B", "GER_or_child": "Either Child",
                     "GER_left": "Left F\u00fchrer"}, names
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "english" / "replace").mkdir(parents=True)
        (tmp / "english" / "a_l_english.yml").write_text('l_english:\n X:0 "old"\n', encoding="utf-8-sig")
        (tmp / "english" / "replace" / "z_l_english.yml").write_text('l_english:\n X:0 "new"\n', encoding="utf-8")
        (tmp / "english" / "b_l_english.yml").write_text('l_english:\n X:0 "later"\n', encoding="utf-8")
        assert F.load_names([tmp], ["X"]) == {"X": "new"}, "the replace folder wins"
        assert F.load_names([LOC, tmp], ["GER_root_a"])["GER_root_a"] == "Root A"
    finally:
        shutil.rmtree(tmp)


def test_save():
    s = F.read_save_focus(SAVE)
    assert s["tag"] == "GER" and s["date"] == "1939.11.1.1" and s["ideology"] == "fascism"
    assert s["completed"] == ["GER_root_a", "GER_or_child"], "GER's own block, not AUS's or a deeper one"
    assert s["current"] == "GER_left" and s["progress"] == 3.5 and s["paused"] == "no"
    assert s["game_rules"] == {"obsolete_focus_branches_visibility": "SHOW"}
    assert F.read_save_focus(SAVE, "AUS")["completed"] == ["AUS_decoy"]
    assert F.read_save_focus(SAVE, "AUS")["ideology"] is None, "the header's ideology is the player's"
    ita = F.read_save_focus(SAVE, "ITA")
    assert ita["completed"] == [] and ita["current"] is None, "a country that never took a focus"
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "bin.hoi4").write_bytes(b"HOI4bin\x00\x01\x02")
        (tmp / "zip.hoi4").write_bytes(b"PK\x03\x04....")
        for name, word in (("bin.hoi4", "save_as_binary"), ("zip.hoi4", "compress")):
            try:
                F.read_save_focus(tmp / name)
                raise AssertionError(name + " must be refused")
            except F.FocusError as e:
                assert word in str(e), e
        try:
            F.read_save_focus(SAVE, "FRA")
            raise AssertionError("a missing country must be refused")
        except F.FocusError:
            pass
    finally:
        shutil.rmtree(tmp)


def _fake_install(tmp):
    """A game folder and a Documents folder: the handmade tree as the game's germany.txt, a generic default tree,
    two DLCs (one folder empty), a game rule, and a mod descriptor with a relative path."""
    game, user = tmp / "game", tmp / "user"
    (game / F.FOCUS_DIR).mkdir(parents=True)
    shutil.copy(TREE, game / F.FOCUS_DIR / "germany.txt")
    (game / F.FOCUS_DIR / "generic.txt").write_text(
        "focus_tree = { id = generic_focus country = { factor = 1 } default = yes focus = { id = generic_a } }\n")
    (game / "localisation" / "english").mkdir(parents=True)
    shutil.copy(LOC / "focus_mini_l_english.yml", game / "localisation" / "english")
    (game / "dlc" / "dlc001_test").mkdir(parents=True)
    (game / "dlc" / "dlc001_test" / "dlc001.dlc").write_text('name = "Test DLC"\npath = "dlc/dlc001_test"\n')
    (game / "dlc" / "dlc002_empty").mkdir()
    (game / "common" / "game_rules").mkdir(parents=True)
    (game / "common" / "game_rules" / "r.txt").write_text(
        "my_rule = { name = X default = { name = HIDE } option = { name = SHOW } }\n")
    (user / "mod").mkdir(parents=True)
    return game, user


def _mods(user, entries):
    (user / "dlc_load.json").write_text(json.dumps({"enabled_mods": [e[0] for e in entries], "disabled_dlcs": []}))
    for rel, body in entries:
        (user / rel).write_text(body)


def test_install():
    tmp = Path(tempfile.mkdtemp())
    try:
        game, user = _fake_install(tmp)
        assert F.owned_dlcs(game, user) == {"Test DLC"}, "an empty DLC folder is not owned"
        assert F.game_rule_defaults(game) == {"my_rule": "HIDE"}
        assert F.owned_dlcs(tmp / "nowhere", user) is None and F.game_rule_defaults(tmp / "nowhere") is None

        # No mods: the game's file wins on score; another tag falls back to the default tree.
        tree, rep = F.find_tree("GER", game, user)
        assert Path(rep["won"]["file"]).name == "germany.txt" and rep["won"]["source"] == "game"
        assert len(tree["focuses"]) == 8 and rep["mods_with_focus_files"] == []
        tree, rep = F.find_tree("FRA", game, user)
        assert tree["id"] == "generic_focus" and "default" in rep["why"]

        # A mod with a relative path that ships a file of the same name: it replaces the game's.
        mod = user / "mod" / "my_mod"
        (mod / F.FOCUS_DIR).mkdir(parents=True)
        (mod / F.FOCUS_DIR / "germany.txt").write_text(
            "focus_tree = { id = mod_german country = { factor = 0 modifier = { add = 10 tag = GER } }"
            " focus = { id = GER_mod_only cost = 1 } }\n")
        _mods(user, [("mod/my_mod.mod", 'name = "My Mod"\npath = "mod/my_mod"\n'),
                     ("mod/gone.mod", 'name = "Gone"\npath = "C:/nowhere/gone"\n')])
        tree, rep = F.find_tree("GER", game, user)
        assert rep["won"]["source"] == "My Mod" and list(tree["focuses"]) == ["GER_mod_only"]
        assert rep["mods_with_focus_files"] == ["My Mod"] and rep["mods_missing"] == ["Gone"]

        # A mod adding a new file that claims GER more strongly wins over the game's.
        (mod / F.FOCUS_DIR / "germany.txt").unlink()
        (mod / F.FOCUS_DIR / "zz_reich.txt").write_text(
            "focus_tree = { id = big country = { factor = 0 modifier = { add = 50 tag = GER } }"
            " focus = { id = GER_big cost = 2 } }\n")
        tree, rep = F.find_tree("GER", game, user)
        assert tree["id"] == "big" and rep["others"][0]["tree_id"] == "test_german_focus"

        # replace_path drops every focus file loaded before the mod.
        (mod / F.FOCUS_DIR / "zz_reich.txt").unlink()
        _mods(user, [("mod/my_mod.mod", 'name = "My Mod"\npath = "mod/my_mod"\n'
                                        'replace_path = "common/national_focus"\n')])
        try:
            F.find_tree("GER", game, user)
            raise AssertionError("an emptied focus folder must be refused")
        except F.FocusError:
            pass

        # The CLI on the fake install: JSON for an agent, and the text form.
        _mods(user, [])
        out = io.StringIO()
        with redirect_stdout(out):
            assert F.main(["--save", str(SAVE), "--game-dir", str(game), "--user-dir", str(user), "--json"]) == 0
        p = json.loads(out.getvalue())
        assert p["current"] == "GER_left" and p["current_name"] == "Left F\u00fchrer"
        assert ids(p["startable"]) == ["GER_root_b", "GER_dlc_branch"], ids(p["startable"])
        assert p["startable"][0]["name"] == "Root B" and p["facts"]["dlcs"] == ["Test DLC"]
        out = io.StringIO()
        with redirect_stdout(out):
            F.main(["--tree", str(TREE), "--completed", "GER_root_a,GER_typo", "--game-dir", str(game),
                    "--user-dir", str(user), "--dlc-unknown"])
        text = out.getvalue()
        assert "Can start now (3)" in text and "GER_or_child  \"Either Child\"  49 days" in text, text
        assert "not in this tree: GER_typo" in text and "needs: has_war = no" in text
    finally:
        shutil.rmtree(tmp)


def test_real_files_if_present():
    """On the PC with the game: the real German tree parses, read-only. Skipped anywhere else."""
    real = F.GAME_DIR / F.FOCUS_DIR / "germany.txt"
    if not real.exists():
        print("  (real game files not here: skipped)")
        return
    t = F.load_tree(real, "GER")
    assert len(t["focuses"]) > 400 and all(f["days"] for f in t["focuses"].values())
    rhine = t["focuses"]["GER_remilitarize_the_rhineland"]
    assert ids(F.startable(t, ["GER_the_four_year_plan"])) and rhine["days"] > 0
    print(f"  real germany.txt: {len(t['focuses'])} focuses")


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("FP1 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

r"""Offline checks for hoi4_navy.py (EX4): the Navy Overview rows, the fleet panel, the mission tooltip, ship lists,
the production screen's ship lines and the Build Ships list, the light and filter pixel checks, and the CLI wiring.

The OCR lines are the ones read in the live game on 1939-11-01 (Germany campaign). No game needed, but Windows is
(hoi4.py loads user32):  .venv\Scripts\python.exe tests\test_EX4.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4  # noqa: E402
import hoi4_actions as A  # noqa: E402
import hoi4_navy as N  # noqa: E402
from hoi4_actions import ActionError  # noqa: E402
from hoi4_ocr import OcrLine as L  # noqa: E402

OVERVIEW = [L("Size", (590, 371, 620, 383)), L("Name", (290, 372, 332, 383)), L("Area", (470, 372, 504, 384)),
            L("24", (571, 416, 591, 429)), L("German Reich Reserve", (220, 423, 385, 436)),
            L("North-West Germ.", (419, 423, 560, 437)), L("Hochseeflotte", (220, 467, 326, 480)),
            L("North-West Germ.", (419, 467, 560, 480)), L("l. U-Boots Flottitte We—", (221, 511, 394, 524)),
            L("Jutland Peninsula", (418, 511, 554, 524)), L("II- U-Boots-Ausbildun—", (221, 554, 393, 568)),
            L("North-West Germ—", (419, 555, 560, 568)), L("Marineschule Kiel", (220, 598, 351, 611)),
            L("Jutland Peninsula", (418, 598, 554, 611)), L("10", (572, 635, 591, 647)),
            L("Ostseeflotte", (220, 642, 314, 655)), L("Lower Battic Sea", (419, 642, 540, 655)),
            L("Active in 3 Strategic area(s)", (216, 1159, 445, 1177))]
# a second read of the size column at a larger upscale found one more size
SIZES = [L("24", (571, 416, 591, 428)), L("12", (572, 459, 590, 472)), L("10", (572, 634, 590, 647))]

# the fleet panel with Ostseeflotte selected, before and after its patrol (home base moved, region added)
PANEL_BEFORE = [L("3", (449, 121, 458, 134)), L("Kriegsmarine", (88, 123, 185, 138)),
                L("No Commander", (101, 189, 211, 200)), L("Click to", (20, 191, 76, 203)),
                L("12 F 2", (309, 227, 374, 244)), L("Wilhelmshav—", (324, 281, 432, 295)),
                L("Active in Regions: O", (20, 282, 181, 300)), L("Select All", (489, 287, 566, 301)),
                L("Ostseeflotte", (87, 379, 181, 393)), L("Back", (510, 381, 544, 393)), L("A10", (19, 382, 50, 402)),
                L("Holding position in Lower Battic Sea", (75, 431, 337, 446))]
PANEL_AFTER = [L("Kriegsmarine", (88, 123, 185, 138)), L("Active in Regions: 1", (20, 282, 179, 300)),
               L("Stettin", (324, 283, 374, 295)), L("Select All", (489, 287, 566, 301)),
               L("TQ-a-", (524, 320, 555, 346)), L("Ostseeflotte", (87, 379, 181, 393)),
               L("Back", (510, 381, 544, 393)), L("A10", (20, 390, 50, 406)),
               L("Operating in Lower Battic Sea", (75, 431, 292, 446))]
PANEL_FLEET_VIEW = [L("Kriegsmarine", (88, 123, 185, 138)), L("Active in Regions: O", (20, 282, 181, 300)),
                    L("A12 Hochseeflotte", (19, 379, 193, 402)), L("Select", (505, 381, 550, 393)),
                    L("Docked in Weser-Ems", (100, 431, 274, 443))]
PANEL_RESERVE = [L("German Reich Flotta 1", (87, 122, 249, 135)), L("Wilhelmshav—", (324, 281, 432, 295)),
                 L("Active in Regions: O", (20, 282, 181, 300)), L("@ Back", (450, 374, 544, 404)),
                 L("German Reich Reserve fleet 1", (88, 379, 302, 393)), L("24", (30, 390, 50, 402)),
                 L("Docked in Weser-Ems", (100, 431, 274, 443))]
PANEL_UBOOT = [L("Unterseeboots-Flotte", (88, 122, 248, 135)), L("Active in Regions: O", (20, 282, 181, 300)),
               L("L U-Boots Flottille Weddigen", (88, 380, 302, 395)), L("Back", (510, 381, 544, 393)),
               L("14", (460, 391, 478, 402)), L("Docked in Holstein", (100, 431, 255, 443))]
OVERVIEW_OPEN = [L("NAVY", (52, 119, 125, 143)), L("OVERVIEW", (152, 119, 306, 143)), L("6 Fleets", (221, 184, 287, 199))]

TIP_PATROL = [L("Patrol", (84, 646, 127, 659)), L("-x", (46, 682, 65, 695)), L("Active in:", (84, 686, 156, 699)),
              L("- Lower Baltic Sea", (83, 706, 224, 719))]
TIP_HOLD = [L("Hold", (84, 492, 119, 505)), L("Active in:", (84, 532, 156, 545)),
            L("- Lower Baltic Sea", (83, 552, 224, 565)), L("Operatmg in Lower Bai", (75, 586, 242, 600))]

SHIPS = [L("d' Pre-Dreadnought (Deutschland Klasse)", (197, 533, 520, 563)),
         L("t' Pre-Dreadnought (Deutschland Klasse)", (197, 584, 520, 614)), L("Möwe", (231, 631, 281, 644)),
         L("t' Inter War Destroyer I (Raubvogel-Ktas—", (197, 636, 555, 665)),
         L("Albatros", (230, 681, 302, 695)), L("d' Inter War Destroyer I (Raubvogel-Klas—", (197, 687, 555, 716)),
         L("Seeadter", (230, 732, 303, 746)), L("d' Inter War Destroyer I (Raubvogel-Ktas—", (197, 738, 555, 768))]

# production list with only the ship categories shown
SHIP_LINES = [L("6 Scharnhorst", (25, 513, 162, 527)), L("Auto", (334, 514, 372, 527)),
              L("Earty Heavy Ship", (25, 547, 149, 562)), L("8 Aug *1242 +", (238, 547, 393, 568)),
              L("Ship NSmes", (455, 610, 539, 627)), L("7 Zerstörer 1934A", (25, 653, 197, 666)),
              L("Auto", (334, 653, 372, 665)), L("ssc", (678, 679, 700, 690)), L("Early Destroyer", (25, 686, 142, 701)),
              L("3 Oct 1940", (238, 688, 326, 701)), L("Ship Names", (455, 751, 539, 766)),
              L("8 Zerstörer 1934A", (25, 792, 197, 805)), L("4 Nov 1940 +", (236, 824, 393, 843)),
              L("Early Destroyer", (25, 825, 142, 840)), L("9 Zerstörer 1934A", (25, 931, 197, 944)),
              L("Earty Destroyer", (25, 963, 142, 979)), L("8 Dec 1940", (237, 966, 326, 979))]

DESIGNS = [L("Convoy", (711, 308, 773, 325)), L("70", (721, 377, 741, 390)),
           L("Scharnhorst Klasse", (711, 407, 872, 421)), L("Early Heavy Ship", (713, 426, 838, 441)),
           L("10769", (722, 477, 770, 490)), L("Admirat Hipper Klasse", (711, 507, 892, 525)),
           L("Early Heavy Cruiser", (713, 526, 859, 541)), L("Admirat Graf Spee A Klasse", (711, 607, 933, 625)),
           L("Panzerschiff", (713, 626, 805, 638)), L("Leipzig A Klasse", (712, 707, 843, 725)),
           L("Interwar Light Cruiser", (713, 726, 876, 741)), L("Zerstörer 1934A A Klasse", (711, 807, 922, 821)),
           L("Early Destroyer", (713, 826, 831, 841)), L("Typ VI'A Klasse", (711, 907, 834, 925)),
           L("Early Submarine", (713, 926, 833, 941)), L("Typ \"B A Klasse", (711, 1007, 838, 1025)),
           L("Improved Coastal Submarine", (713, 1026, 923, 1041)), L("Early Heavy Ship", (712, 1107, 845, 1125))]


def check_overview():
    rows = N.overview_rows(OVERVIEW + SIZES)
    assert [N.clean_name(r["name"]) for r in rows] == [
        "German Reich Reserve", "Hochseeflotte", "l. U-Boots Flottitte We", "II- U-Boots-Ausbildun",
        "Marineschule Kiel", "Ostseeflotte"], rows
    assert [r["size"] for r in rows] == [24, 12, None, None, None, 10], [r["size"] for r in rows]
    assert [r["y"] for r in rows] == [429, 473, 517, 560, 604, 648], [r["y"] for r in rows]
    assert rows[5]["area"] == "Lower Battic Sea" and rows[0]["area"] == "North-West Germ."
    assert not any("Strategic" in r["name"] for r in rows), "the footer is not a task force"


def check_matching():
    rows = N.overview_rows(OVERVIEW)
    pick = lambda name: N.best_match(name, rows, key=lambda r: r["name"])  # noqa: E731
    assert pick("Ostseeflotte")["y"] == 648
    assert pick("Marineschule Kiel")["y"] == 604
    assert pick("I. U-Boots Flottille Weddigen")["y"] == 517, "a name the overview cuts short still matches"
    assert pick("II. U-Boots-Ausbildungsflottille")["y"] == 560
    assert pick("Bismarck Gruppe") is None
    assert N.name_score("Marineschule Kiel", "Marineschute Kiet") >= 0.8, "OCR misreads l as t"
    assert N.name_score("Lower Baltic Sea", "Lower Battic Sea") >= 0.8
    assert N.name_score("Wilhelmshaven", "Wilhelmshav—") >= 0.75, "a cut home base name"
    assert N.name_score("Kiel", "Stettin") < 0.5


def check_panel():
    head = N.parse_fleet_header(PANEL_BEFORE)
    assert head == {"fleet": "Kriegsmarine", "home": "Wilhelmshav—", "regions": 0}, head
    card = N.parse_task_force(PANEL_BEFORE)
    assert card == {"name": "Ostseeflotte", "ships": 10, "status": "Holding position in Lower Battic Sea"}, card
    head, card = N.parse_fleet_header(PANEL_AFTER), N.parse_task_force(PANEL_AFTER)
    assert head["home"] == "Stettin" and head["regions"] == 1, head
    assert card["status"] == "Operating in Lower Battic Sea", card
    card = N.parse_task_force(PANEL_FLEET_VIEW)
    assert card["name"] == "Hochseeflotte" and card["ships"] == 12, "count and name read as one line: 'A12 Hochseeflotte'"
    card = N.parse_task_force(PANEL_RESERVE)
    assert card == {"name": "German Reich Reserve fleet 1", "ships": 24, "status": "Docked in Weser-Ems"}, card
    assert N.parse_fleet_header(PANEL_RESERVE)["fleet"] == "German Reich Flotta 1"
    card = N.parse_task_force(PANEL_UBOOT)
    assert card["name"] == "L U-Boots Flottille Weddigen" and card["ships"] is None, "the 14 at the right is not the count"
    assert N.parse_task_force([L("C' Docked in Holstein", (76, 735, 255, 755))]) is None
    assert N.parse_fleet_header(OVERVIEW_OPEN + OVERVIEW) is None, "the overview is not a fleet panel"


def check_mission_tip():
    assert N.parse_mission_tip(TIP_PATROL) == ("Patrol", ["Lower Baltic Sea"])
    assert N.parse_mission_tip(TIP_HOLD) == ("Hold", ["Lower Baltic Sea"])
    assert N.parse_mission_tip([L("Reserve", (84, 492, 145, 509))]) == ("Reserve", [])
    assert N.parse_mission_tip([L("Convoy Raidmg", (84, 492, 190, 505))])[0] == "Convoy Raiding", "OCR'd name fixed"
    assert N.parse_mission_tip([]) == (None, [])
    assert N.letters("Convoy Raiding") in N.letters("Convoy 1 Raiding"), "letters only, as act air compares"


def check_ships():
    ships = N.parse_ships(SHIPS)
    assert [s["name"] for s in ships] == ["?", "?", "Möwe", "Albatros", "Seeadter"], ships
    assert ships[0]["class"] == "Pre-Dreadnought (Deutschland Klasse)"
    assert ships[2]["class"] == "Inter War Destroyer I (Raubvogel-Ktas"
    assert N.ship_summary(ships) == "3 Inter War Destroyer I, 2 Pre-Dreadnought", N.ship_summary(ships)


def check_ship_lines():
    lines = N.parse_ship_lines(SHIP_LINES)
    assert [(s["number"], s["name"]) for s in lines] == [(6, "Scharnhorst"), (7, "Zerstörer 1934A"),
                                                         (8, "Zerstörer 1934A"), (9, "Zerstörer 1934A")], lines
    assert [s["y"] for s in lines] == [520, 660, 798, 938], [s["y"] for s in lines]
    assert lines[0]["type"] == "Earty Heavy Ship" and lines[0]["date"] == "8 Aug *1242"
    assert lines[1]["type"] == "Early Destroyer" and lines[1]["date"] == "3 Oct 1940"
    assert lines[2]["date"] == "4 Nov 1940", "the + button after the date is not part of it"
    assert N.line_wanted("Scharnhorst", lines[0]) and not N.line_wanted("Scharnhorst", lines[1])
    assert N.line_wanted("Zerstörer 1934A", lines[2])
    assert N.line_wanted("8 Zerstörer 1934A", lines[2]) and not N.line_wanted("8 Zerstörer 1934A", lines[1])
    assert N.line_wanted("#9", lines[3]) and not N.line_wanted("#9", lines[2])
    assert N.parse_dockyards([L("Dockyards", (385, 312, 470, 328)), L("4/12", (505, 312, 545, 328))]) == (4, 12)
    assert N.parse_dockyards([L("Dockyards", (385, 312, 470, 328)), L("4/1 2", (505, 312, 545, 328))]) == (4, 12)
    assert N.parse_dockyards([L("Dockyards", (385, 312, 470, 328))]) is None


def check_designs():
    designs = N.parse_designs(DESIGNS)
    assert [d["name"] for d in designs] == [
        "Convoy", "Scharnhorst Klasse", "Admirat Hipper Klasse", "Admirat Graf Spee A Klasse", "Leipzig A Klasse",
        "Zerstörer 1934A A Klasse", "Typ VI'A Klasse", "Typ \"B A Klasse", "Early Heavy Ship"], designs
    assert designs[6]["type"] == "Early Submarine" and designs[0]["type"] == ""
    by_name = lambda want: N.best_match(want, designs, key=lambda d: d["name"])  # noqa: E731
    assert by_name("Typ VIIA")["y"] == 916, "OCR reads VIIA as VI'A"
    assert by_name("Zerstörer 1934A")["y"] == 814
    assert by_name("Admiral Hipper")["y"] == 516
    assert by_name("Scharnhorst")["y"] == 414
    assert by_name("Bismarck") is None
    try:
        N.best_match("Zerstörer", [{"n": "Zerstörer 1934A"}, {"n": "Zerstörer 1936"}], key=lambda d: d["n"])
        raise AssertionError("two equally good designs must be refused")
    except ActionError:
        pass


def check_pixels():
    img = np.full((1200, 1920, 3), 54, dtype=np.uint8)
    x, y = N.NV["missions"]["patrol"] + N.NV["light_dx"], N.NV["light_y"]
    assert not N.light_on(img, x, y), "a grey light is not set"
    img[y - 3:y + 4, x - 3:x + 4] = (200, 180, 60)  # the lit light: mean (158, 140, 71) over 7x7 live
    assert N.light_on(img, x, y)
    x2 = N.NV["missions"]["strike"] + N.NV["light_dx"]
    assert not N.light_on(img, x2, y), "the next button's light is separate"

    img = np.full((1200, 1920, 3), 45, dtype=np.uint8)
    assert N.filter_state_from(img) == {k: False for k in N.FILTERS}
    y0, y1 = N.DY["filter_check_band"]
    for name in ("capital", "screen", "other"):  # a yellow check drawn at the icon's bottom right
        r = N.DY["filter_check_right"][name]
        img[y0 + 8:y0 + 12, r - 10:r - 6] = (230, 190, 60)
    assert N.filter_state_from(img) == N.SHIPS, N.filter_state_from(img)

    img = np.full((1200, 1920, 3), 60, dtype=np.uint8)
    img[500:516, 940:956] = (40, 180, 200)  # a teal anchor icon
    assert N.anchor_candidates(img, (1007, 601))[:1] == [(948, 508)], N.anchor_candidates(img, (1007, 601))
    img[300:400, 1000:1300] = (70, 120, 170)  # sea is blue, not teal
    assert len(N.anchor_candidates(img, (1007, 601))) == 1


def check_cli():
    """The act/read wiring parses; the game is never reached (need_window is stubbed to stop right there)."""
    class Reached(Exception):
        pass

    def stop():
        raise Reached

    real = hoi4.need_window
    hoi4.need_window = stop
    try:
        for argv in (["read", "navy"], ["read", "navy", "--quick"], ["read", "navy", "--fleet", "Ostseeflotte"],
                     ["read", "production", "--dockyards"],
                     ["navy", "mission", "--fleet", "Ostseeflotte", "--mission", "patrol", "--region", "1150", "300",
                      "--region-name", "Lower Baltic Sea"],
                     ["navy", "port", "--task-force", "Ostseeflotte", "--port", "Kiel"], ["navy", "deselect"],
                     ["production", "--dockyards", "--name", "#8", "--add", "2"],
                     ["production", "--dockyards", "--new", "Typ VIIA", "--add", "3"],
                     ["production", "--line", "2", "--add", "1"]):
            try:
                A.main(argv)
            except Reached:
                continue
            raise AssertionError(f"{argv} did not reach the game")
    finally:
        hoi4.need_window = real
    assert set(N.NV["missions"]) == set(N.NV["mission_names"])
    assert set(N.NV["no_region"]) <= set(N.NV["missions"])
    assert A.T["screens"]["navy"] == {"key": "p", "title": "NAVY OVERVIEW"}


def main():
    check_overview()
    check_matching()
    check_panel()
    check_mission_tip()
    check_ships()
    check_ship_lines()
    check_designs()
    check_pixels()
    check_cli()
    print("EX4 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

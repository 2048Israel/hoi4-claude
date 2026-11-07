"""EX1 offline checks for hoi4_actions.py: research slot parsing, fuzzy names, tech lookup, icon candidates.

No game needed, but Windows is (hoi4.py loads user32):  .venv\\Scripts\\python.exe tests\\test_EX1.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_actions as A  # noqa: E402
from hoi4_ocr import OcrLine  # noqa: E402


def slot_lines():
    """The research slot list as Windows OCR read it in the live game on 1936-02-25 (slot 3 emptied here)."""
    raw = [
        ("Basic Machine Toots", (83, 392, 249, 406)), ("108 day(s)", (503, 392, 585, 410)), ("1936", (83, 453, 122, 466)),
        ("Construction", (83, 517, 193, 531)), ("162 day(s)", (503, 517, 585, 535)), ("1936", (83, 578, 122, 591)),
        ("Select a technology to research", (83, 642, 365, 660)), ("1936", (83, 703, 122, 716)),
        ("Rubber Processing", (83, 767, 235, 785)), ("158 day(s)", (503, 767, 585, 785)),
        ("kft", (678, 817, 700, 831)), ("1937", (83, 828, 122, 841)),
        ("Inter-War Artillery", (83, 892, 237, 910)), ("122 day(s)", (503, 892, 585, 910)),
        ("rut", (676, 952, 700, 966)), ("1936", (83, 953, 122, 966)),
    ]
    return [OcrLine(t, b) for t, b in raw]


def main():
    slots = A.parse_slots(slot_lines())
    assert slots[0] == {"slot": 1, "tech": "Basic Machine Toots", "days": 108}, slots[0]
    assert slots[1]["tech"] == "Construction" and slots[1]["days"] == 162
    assert slots[2]["tech"] is None, "an empty slot reads 'Select a technology to research'"
    assert slots[4] == {"slot": 5, "tech": "Inter-War Artillery", "days": 122}, slots[4]

    assert A.similar("Basic Machine Tools", "Basic Machine Toots") > 0.9
    assert A.similar("Inter-War Artillery", "Rubber Processing") < 0.5

    tmp = Path(tempfile.mkdtemp())
    A.TECH_MAP = tmp / "tech_map.json"
    A.TECH_MAP.write_text(json.dumps({"tabs": {"artillery": {
        "home_labels": {"1936": [139, 604], "1940": [139, 957]},
        "techs": {"Inter-War Artillery": {"x": 950, "y": 600, "days": 122},
                  "cm PaK 36": {"x": 1560, "y": 600, "days": 134},
                  "12,8 cm PaK 44": {"x": 1564, "y": 1478, "days": 1181}}}}}), encoding="utf-8")
    tab, title, pos, home = A.find_tech("inter war artillery")
    assert (tab, title) == ("artillery", "Inter-War Artillery")
    assert A.find_tech("3,7 cm PaK 36")[1] == "cm PaK 36", "OCR drops the '3,7' prefix; fuzzy lookup still finds it"
    assert A.find_tech("12,8 cm PaK 44")[2]["y"] == 1478
    # OCR writes the numeral III as "Ill"; III must not fall back to the similar-looking II
    data = json.loads(A.TECH_MAP.read_text(encoding="utf-8"))
    data["tabs"]["industry"] = {"techs": {"Concentrated Industry II": {"x": 812, "y": 754, "days": 336},
                                          "Concentrated Industry Ill": {"x": 798, "y": 930, "days": 842}}}
    A.TECH_MAP.write_text(json.dumps(data), encoding="utf-8")
    assert A.find_tech("Concentrated Industry III")[1] == "Concentrated Industry Ill"
    assert A.find_tech("Concentrated Industry II")[1] == "Concentrated Industry II"
    try:
        A.find_tech("Nuclear Reactor")
        raise AssertionError("an unknown tech must raise")
    except A.ActionError:
        pass

    # production lines by name: headers as OCR read them in the live game
    assert A.line_matches("Bf 109", "11 BF109A") and A.line_matches("Ju 87", "12 Ju87")
    assert A.line_matches("Karabiner", "1 Karabiner 98k") and not A.line_matches("Ju 87", "11 BF109A")
    assert not A.line_matches("Bf 109", "Basic Small Airframe")  # a line header always starts with its number

    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1920, 1200), (25, 25, 25))
    d = ImageDraw.Draw(img)
    centers = [(300 + 175 * c, 430 + 175 * r) for c in range(4) for r in range(3)]
    for cx, cy in centers:
        d.rectangle((cx - 40, cy - 40, cx + 40, cy + 40), fill=(170, 160, 120))
    d.rectangle((300, 600, 1000, 605), fill=(170, 170, 170))  # a thin connector line: not an icon
    cands = A.detect_candidates(img)
    for cx, cy in centers:
        assert any(abs(cx - x) <= 30 and abs(cy - y) <= 30 for x, y in cands), f"icon at {(cx, cy)} not found"
    assert all(abs(y - 602) > 30 or any(abs(x - cx) <= 45 for cx, _ in centers) for x, y in cands), \
        "the connector line alone must not produce candidates"
    print("EX1 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

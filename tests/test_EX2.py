"""EX2 offline checks: the decisions list reader, the tooltip finder and the top-bar number reader.

No game needed, but Windows is (hoi4.py loads user32):  .venv\\Scripts\\python.exe tests\\test_EX2.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_actions as A  # noqa: E402
from hoi4_ocr import OcrLine  # noqa: E402


def page(raw):
    """A decision_page-style list from (text, y, kind) as OCR placed them in the live game on 1940-06-27."""
    out = []
    for text, y, kind in raw:
        box = (264, y, 396, y + 14) if kind == "cat" else (88, y, 300, y + 14)
        out.append((kind, OcrLine(text, box), True if kind == "cat" else None))
    return out


def main():
    # headers are centred; "War Measures" is only 14 px tall and must still count
    assert A.is_header(OcrLine("War Measures", (267, 604, 392, 618)))
    assert not A.is_header(OcrLine("100", (524, 427, 549, 438))), "a cost is not a header"
    assert not A.is_header(OcrLine("50.0%", (270, 752, 322, 765))), "a panel value is not a header"
    assert A.is_row(OcrLine("War Bonds", (88, 807, 165, 820)))

    # two pages that overlap by two rows; the second scrolled a little less than asked (end of the list)
    p1 = page([("Propaganda Efforts", 300, "cat"), ("War Propaganda", 350, "row"), ("Exhort Heroism", 400, "row"),
               ("War Measures", 450, "cat"), ("Women in the Workforce", 500, "row")])
    p2 = page([("War Measures", 350, "cat"), ("Women in the Workforce", 400, "row"), ("War Bonds", 450, "row"),
               ("Political Actions", 500, "cat"), ("Improved Worker Conditions", 550, "row")])
    items = A.merge_pages([p1, p2], step_px=120)
    texts = [t for _, _, t, _ in items]
    assert texts == ["Propaganda Efforts", "War Propaganda", "Exhort Heroism", "War Measures",
                     "Women in the Workforce", "War Bonds", "Political Actions", "Improved Worker Conditions"], texts
    assert [y for y, _, t, _ in items if t == "War Bonds"] == [550], "page 2 is placed by its shared rows (100 px)"

    # the top-bar numbers: OCR reads 825 as "82s"
    assert "82s".translate(A.DIGIT_FIX) == "825" and "1O6".translate(A.DIGIT_FIX) == "106"

    # the tooltip finder: a tooltip block above the cursor, a highlighted row at the cursor, and map noise apart
    import numpy as np
    from PIL import Image
    before = np.full((1200, 1920), 40, dtype=np.uint8)
    after = before.copy()
    after[440:780, 330:780:2] = 200          # tooltip text: every other column changes, as text does
    after[795:830, 0:650] = 90               # the hovered row's highlight
    after[100:140, 1500:1700] = 200          # something else changing on the map, far away
    box = A.changed_box(Image.fromarray(before), Image.fromarray(after), x_min=310, cursor=(300, 813))
    assert box and 320 <= box[0] <= 340 and 430 <= box[1] <= 450 and 770 <= box[2] <= 790 and 770 <= box[3] <= 790, box
    assert A._runs([True, True, False, True, False, False, False, True], gap=1) == [(0, 4), (7, 8)]
    # focus titles wrap onto two rows in the detail window ("LEGION" over "CONDOR"): they are joined
    merged = [l.text for l in A.merge_title_lines([OcrLine("LEGION", (900, 300, 980, 318)),
                                                   OcrLine("CONDOR", (895, 322, 985, 340)),
                                                   OcrLine("GERMAN REICH", (60, 120, 300, 140))])]
    assert "LEGION CONDOR" in merged and "GERMAN REICH" in merged, merged
    # event options: map labels under a small popup are not options (seen on "Ace Pilot Promoted")
    from PIL import ImageDraw
    img = Image.new("RGB", (1920, 1200), (200, 180, 140))
    d = ImageDraw.Draw(img)
    d.rectangle((870, 500, 1330, 530), fill=(50, 45, 40))
    d.rectangle((870, 560, 1330, 590), fill=(50, 45, 40))
    for x in range(870, 1330, 20):
        d.rectangle((x, 640, x + 10, 660), fill=(160, 170, 120))
        d.rectangle((x + 10, 640, x + 20, 660), fill=(90, 120, 160))
    opts = [OcrLine("Who dares, wins.", (1000, 508, 1200, 522)), OcrLine("Second", (1000, 568, 1200, 582)),
            OcrLine("Budapest", (1000, 643, 1100, 657))]
    assert [o.text for o in A.on_buttons(img, opts)] == ["Who dares, wins.", "Second"]
    print("EX2 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

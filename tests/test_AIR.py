r"""Offline checks for hoi4_air.py: the Air Forces Overview rows and the wing filter.

No game needed, but Windows is (hoi4.py loads user32):  .venv\Scripts\python.exe tests\test_AIR.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_actions as A  # noqa: E402
import hoi4_air as H  # noqa: E402
from hoi4_ocr import OcrLine  # noqa: E402


def main():
    # the overview as OCR read it in the live game on 1940-07-31 (two of its 14 rows, plus a header line)
    lines = [OcrLine("Name", (216, 446, 260, 460)),
             OcrLine("Jagdgeschwader 232", (184, 489, 330, 503)), OcrLine("Poznań", (390, 489, 440, 503)),
             OcrLine("Eastern Germany", (506, 489, 636, 503)),
             OcrLine("Kampfgeschwader", (184, 975, 330, 989)), OcrLine("Oberbayern", (380, 975, 460, 989))]
    A.read_box = lambda hwnd, box, **kw: lines
    A.open_screen = A.close_screen = lambda hwnd, name: None
    rows = H.read_overview(None)
    assert [r["name"] for r in rows] == ["Jagdgeschwader 232", "Kampfgeschwader"], rows
    assert rows[0]["base"] == "Poznań" and rows[0]["area"] == "Eastern Germany" and rows[0]["y"] == 496
    assert rows[1]["base"] == "Oberbayern" and rows[1]["area"] == "", "a wing on the move has no area"

    wings = [{"name": "Jagdgeschwader 1"}, {"name": "KG 1 'Hindenburg'"}, {"name": "Kampfgeschwader..."}]
    assert [w["name"] for w in H.pick(wings, "Kampf,KG")] == ["KG 1 'Hindenburg'", "Kampfgeschwader..."]
    assert H.pick(wings, None) == wings
    print("AIR OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

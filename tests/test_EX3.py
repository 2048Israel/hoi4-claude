r"""EX3 offline checks for hoi4_build.py: the state slot labels on the construction map.

No game needed, but Windows is (hoi4.py loads user32):  .venv\Scripts\python.exe tests\test_EX3.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hoi4_actions as A  # noqa: E402
import hoi4_build as Bd  # noqa: E402
from hoi4_ocr import OcrLine  # noqa: E402


def main():
    # labels as OCR read them on 1939-06-26: "used/total", a percentage line, city names, a letter read for a digit
    lines = [OcrLine("12/42", (1100, 640, 1150, 656)), OcrLine("60%", (1105, 660, 1140, 674)),
             OcrLine("0/41", (1100, 920, 1140, 936)), OcrLine("Warsaw", (1300, 600, 1370, 616)),
             OcrLine("5/1s", (900, 700, 940, 716)), OcrLine("2/12", (1360, 400, 1400, 416)),
             OcrLine("1940/05", (1500, 20, 1580, 36))]
    A.read_box = lambda hwnd, box, **kw: lines
    labels = Bd.slot_labels(None)
    assert [(f, u, t) for f, u, t, _ in labels] == [(41, 0, 41), (30, 12, 42), (10, 5, 15), (10, 2, 12)], labels
    print("EX3 OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

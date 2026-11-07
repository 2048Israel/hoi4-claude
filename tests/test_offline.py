"""Offline checks for hoi4.py that need no running game: log parsing, report and news
formatting, key mapping, batch splitting and screenshot annotation.

Run on Windows (hoi4.py loads user32 at import):
    .venv\\Scripts\\python.exe tests\\test_offline.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hoi4  # noqa: E402

PREFIX = "[10:00:02][1936.01.02.12]: "
LINES = [
    "[10:00:00][game.cpp:12]: Executing History from -1.1.1.1 to  2.1.1.1",
    "[10:00:01][1936.01.01.24]: @CB;day;tag=GER;pp=45.123;ppd=1.850;stab=0.52;ws=0.61;mpk=650.4;divs=45;cp=30.000",
    "[10:00:02][1936.01.02.24][effectbase.cpp:99]: @CB;day;tag=GER;pp=47.000;ppd=1.850;stab=0.52;ws=0.61;mpk=651.0;divs=46;cp=31.0",
    PREFIX + "@CB;rep_begin;tag=GER",
    PREFIX + "@CB;country;tag=GER;name=German Reich;ideology=fascist;party=NSDAP;leader=Adolf Hitler;faction=",
    PREFIX + "@CB;politics;pp=47.000;ppd=1.850;stab=0.52;ws=0.61;cp=31.0;cpd=0.5;election_days=-1",
    PREFIX + "@CB;industry;civ=35;mil=28;nav=10;civ_free=20;mil_free=8;nav_free=0;research_slots=5;techs=101;fuel_k=297;max_fuel_k=372",
    PREFIX + "@CB;territory;owned=24;controlled=24;occupied=0;cores=24;subjects=0",
    PREFIX + "@CB;resources;steel=182;oil=3;aluminium=107;rubber=-5;tungsten=3;chromium=2",
    PREFIX + "@CB;army;mpk=651.0;max_mpk=65595;deployed_k=269.6;divs=30;armies=30;casualties_k=0;garrison_need=0;deploy_queue_mp=0",
    PREFIX + "@CB;equip;type=infantry_equipment;stock=5200;fielded=92000;target=100000",
    PREFIX + "@CB;equip;type=medium_tank_chassis;stock=0;fielded=0;target=0",
    PREFIX + "@CB;war;surrender=0;enemy_strength_ratio=0;alliance_strength_ratio=0;longest_war_months=0",
    PREFIX + "@CB;general;name=Gerd von Rundstedt;units=24;in_combat=0;combat_progress=0;entrench=0.1;planning=0.5;skill=4;plans=0",
    PREFIX + "@CB;major;tag=ENG;name=United Kingdom;ideology=democratic;faction=Allies;divs=38;mil=15;civ=32;surrender=0",
    PREFIX + "@CB;neighbor;tag=POL;name=Poland;ideology=non-aligned;faction=;divs=40;mil=6",
    PREFIX + "@CB;rep_end;tag=GER",
    "[10:00:03][1936.03.07.06]: @CB;news;what=war_declared;a=ITA;a_name=Italy;b=ETH;b_name=Ethiopia",
    "[10:00:03][1936.03.07.06]: @CB;news;what=war_declared;a=ITA;a_name=Italy;b=ETH;b_name=Ethiopia",
    "[10:00:03][1940.06.20.12]: @CB;news;what=peace;a=GER;a_name=Germany;b=FRA;b_name=France",
    "[10:00:03][1940.06.20.12]: @CB;news;what=peace;a=ITA;a_name=Italy;b=FRA;b_name=France",
    "[10:00:03][1940.06.20.12]: @CB;news;what=peace;a=GER;a_name=Germany;b=BEL;b_name=Belgium",
    "[10:00:04][1940.06.21.06]: @CB;day;tag=GER;pp=4",  # cut off: no newline after it
]


def main():
    tmp = Path(tempfile.mkdtemp())
    log = tmp / "game.log"
    log.write_text("\n".join(LINES[:-1]) + "\n" + LINES[-1], encoding="utf-8")
    hoi4.LOG_PATH = log
    hoi4.STATE_DIR = tmp / "state"

    recs, end = hoi4.records(0)
    assert end < log.stat().st_size, "a partial last line must not be consumed"
    assert sum(r["kind"] == "day" for r in recs) == 2, "the cut-off heartbeat must be skipped"
    assert all(r["date"] for r in recs), "every bridge line has a date"
    news = [r for r in recs if r["kind"] == "news"]
    assert news[0]["what"] == "war_declared" and news[0]["kind"] == "news"

    block = hoi4.last_report(recs)
    assert block and block[0]["kind"] == "rep_begin" and block[-1]["kind"] == "rep_end"
    report = hoi4.format_report(block)
    print(report)
    assert "election" not in report, "election_days=-1 must be hidden"
    assert "short" in report and "8,000" in report

    assert hoi4.nice_date("1936.01.07.24") == "1936-01-08 00:00"
    assert hoi4.nice_date("1936.12.31.24") == "1937-01-01 00:00"

    first = hoi4.take_news()
    print("\n".join(first))
    assert len(first) == 2, first  # duplicate war line collapsed, peace lines grouped
    assert "Germany, Italy won against France, Belgium" in first[1]
    assert hoi4.take_news() == [], "news already read must not repeat"

    # A new game session writes a new log with a different first line: the cursor must reset.
    log.write_text("[11:11:11][game.cpp:1]: new session\n" + LINES[17] + "\n", encoding="utf-8")
    assert len(hoi4.take_news()) == 1

    for name in ["y", "Q", "esc", "space", "f1", "kp_plus", "kp_minus", "console", "up", "enter"]:
        hoi4.key_scan(name)
    assert hoi4.key_scan("kp_plus") == (0x4E, False)
    assert hoi4.key_scan("console") == (0x29, False)
    assert hoi4.key_scan("up")[1] is True
    assert hoi4.split_batch('key y ; type "a;b" ; look') == ["key y ", ' type "a;b" ', " look"]

    from PIL import Image
    img = Image.new("RGB", (1920, 1200), (40, 60, 90))
    shot = hoi4.annotate(img, scale=0.6, grid=100, marks=[(960, 600)])
    assert shot.size == (1152, 720)
    zoom = hoi4.annotate(img.crop((800, 500, 1100, 700)), origin=(800, 500), scale=2.0, grid=50)
    assert zoom.size == (600, 400)
    print("ALL OFFLINE CHECKS PASSED")


if __name__ == "__main__":
    main()

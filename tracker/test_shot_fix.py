"""
Smoke test for helpers/event_log.set_shot_location (the mistap fixer),
against a THROWAWAY DB. Run: python tracker/test_shot_fix.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["APP5_DATA_DIR"] = tempfile.mkdtemp(prefix="app5_shotfix_test_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import execute, initialize_database, query   # noqa: E402
initialize_database()

import helpers.court_geom as CG                                # noqa: E402
import helpers.event_log as EL                                 # noqa: E402
import helpers.game_events as GE                               # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAIL: {label}"
    PASS += 1
    print(f"  ok  {label}")


# ── fixture: two teams, one shooter + one defender each side, one game ────────
t1 = execute("INSERT INTO teams (name, class, gender) VALUES ('Home', '3A', 'F')")
t2 = execute("INSERT INTO teams (name, class, gender) VALUES ('Away', '3A', 'F')")
p1 = execute("INSERT INTO players (team_id, name, number) VALUES (?, 'Ann', 1)", (t1,))
p2 = execute("INSERT INTO players (team_id, name, number) VALUES (?, 'Bea', 2)", (t2,))
gid = execute("INSERT INTO games (team1_id, team2_id, date) VALUES (?,?,'2026-01-10')",
              (t1, t2))

floor = [(p1, t1), (p2, t2)]

# A made paint 2 (x=0, y=6 → zone C, value 2)
eid = GE.log_event(gid, {"event_type": "shot", "quarter": 1, "time": "7:40",
                         "primary_player_id": p1, "shot_result": "make",
                         "shot_x": 0.0, "shot_y": 6.0}, floor)
ev = query("SELECT * FROM game_events WHERE id=?", (eid,))[0]
ok(ev["shot_type"] == 2 and ev["zone"] == "C", "fixture: paint make logged as 2PT C")
pm = {r["player_id"]: r["plus_minus"]
      for r in query("SELECT player_id, plus_minus FROM game_lineup_players WHERE game_id=?", (gid,))}
ok(pm[p1] == 2 and pm[p2] == -2, "fixture: +/- credited 2 both ways")

pid2team = EL.game_people(gid)["pid2team"]

# ── move it beyond the arc: value flips 2 -> 3, zone re-derives, +/- shifts ──
zone, val = EL.set_shot_location(gid, eid, 0.0, 28.0, pid2team)
ok(val == 3, "move past arc -> value 3")
ok(zone == CG.zone_from_xy(0.0, 28.0), "zone re-derived from new x/y")
ev = query("SELECT * FROM game_events WHERE id=?", (eid,))[0]
ok(ev["shot_x"] == 0.0 and ev["shot_y"] == 28.0, "x/y stored")
ok(ev["shot_type"] == 3 and ev["zone"] == zone, "row carries derived zone + 3PT")
pm = {r["player_id"]: r["plus_minus"]
      for r in query("SELECT player_id, plus_minus FROM game_lineup_players WHERE game_id=?", (gid,))}
ok(pm[p1] == 3 and pm[p2] == -3, "+/- shifted to 3 both ways on the 2->3 flip")
ok(EL.score_from_events(gid) == (3, 0), "derived score follows the flip")

# ── moving a MISS never touches +/- ──────────────────────────────────────────
eid2 = GE.log_event(gid, {"event_type": "shot", "quarter": 1, "time": "6:55",
                          "primary_player_id": p2, "shot_result": "miss",
                          "shot_x": -10.0, "shot_y": 10.0}, floor)
EL.set_shot_location(gid, eid2, 20.0, 24.0, pid2team)
pm = {r["player_id"]: r["plus_minus"]
      for r in query("SELECT player_id, plus_minus FROM game_lineup_players WHERE game_id=?", (gid,))}
ok(pm[p1] == 3 and pm[p2] == -3, "moving a miss leaves +/- alone")

# ── adding a location to a legacy zone-only shot ─────────────────────────────
eid3 = GE.log_event(gid, {"event_type": "shot", "quarter": 2, "time": "5:00",
                          "primary_player_id": p1, "shot_result": "make",
                          "shot_type": 2, "zone": "LW"}, floor)
zone, val = EL.set_shot_location(gid, eid3, -18.0, 22.0, pid2team)
ev = query("SELECT * FROM game_events WHERE id=?", (eid3,))[0]
ok(ev["shot_x"] is not None and val == ev["shot_type"], "legacy shot gains x/y + derived value")

# ── non-shots are refused ────────────────────────────────────────────────────
eid4 = GE.log_event(gid, {"event_type": "turnover", "quarter": 2, "time": "4:30",
                          "primary_player_id": p2}, floor)
ok(EL.set_shot_location(gid, eid4, 0.0, 10.0, pid2team) is None,
   "turnover refused by the fixer")

# ── retyping a located shot away from "shot" clears its tap location ─────────
eid5 = GE.log_event(gid, {"event_type": "shot", "quarter": 3, "time": "6:00",
                          "primary_player_id": p1, "shot_result": "miss",
                          "shot_x": -22.0, "shot_y": 2.0}, floor)
EL.update_event(gid, eid5, {"event_type": "turnover",
                            "quarter": 3, "time": "6:00",
                            "primary_player_id": p1}, pid2team)
ev = query("SELECT * FROM game_events WHERE id=?", (eid5,))[0]
ok(ev["shot_x"] is None and ev["shot_y"] is None,
   "shot->turnover retype clears stale x/y")

print(f"\nALL {PASS} CHECKS PASSED")

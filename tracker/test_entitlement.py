"""
Smoke test for helpers/entitlement.py tier gating, against a THROWAWAY DB.
Run: python tracker/test_entitlement.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["APP5_DATA_DIR"] = tempfile.mkdtemp(prefix="app5_ent_test_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import execute                    # noqa: E402
import helpers.entitlement as E                     # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, f"FAIL: {label}"
    PASS += 1
    print(f"  ok  {label}")


# teams: A + B opted into the pool, C private
a = execute("INSERT INTO teams (name,class,gender) VALUES ('A','3A','F')")
b = execute("INSERT INTO teams (name,class,gender) VALUES ('B','3A','F')")
c = execute("INSERT INTO teams (name,class,gender) VALUES ('C','3A','F')")
execute("UPDATE teams SET in_pool=1 WHERE id IN (?,?)", (a, b))

admin = {"role": "admin", "plan": "free", "team_id": None}
free = {"role": "coach", "plan": "free", "team_id": a}
paid_pooled = {"role": "coach", "plan": "paid", "team_id": a}    # team A is pooled
paid_private = {"role": "coach", "plan": "paid", "team_id": c}   # team C is private

print("has_paid_plan")
ok(E.has_paid_plan(admin), "admin counts as paid")
ok(E.has_paid_plan(paid_pooled), "paid plan counts")
ok(not E.has_paid_plan(free), "free is not paid")
ok(not E.has_paid_plan(None), "no identity -> not paid")
ok(E.has_paid_plan({"role": "coach", "plan": "free", "paid_until": "2999-01-01"}),
   "future paid_until counts")
ok(not E.has_paid_plan({"role": "coach", "plan": "free", "paid_until": "2000-01-01"}),
   "past paid_until fails")

print("pool membership")
ok(E.pool_team_ids() == {a, b}, "pool = {A,B}")

print("can_see_team_tracked")
ok(E.can_see_team_tracked(admin, c), "admin sees any team's tracked")
ok(not E.can_see_team_tracked(free, a), "free can't see even own tracked")
ok(E.can_see_team_tracked(paid_private, c), "paid sees OWN team (even when private)")
ok(E.can_see_team_tracked(paid_pooled, a), "paid sees own pooled team")
ok(E.can_see_team_tracked(paid_pooled, b), "paid+pooled scouts pooled opponent B")
ok(not E.can_see_team_tracked(paid_pooled, c), "paid can't see private opponent C")
ok(not E.can_see_team_tracked(paid_private, b), "paid but not-in-pool can't scout B")

print("tracked_gate messaging")
vis, msg = E.tracked_gate(free, a, True)
ok(not vis and "Paid" in msg, "free -> upgrade message")
vis, msg = E.tracked_gate(paid_private, b, True)
ok(not vis and "league pool" in msg.lower(), "not-in-pool -> join-pool message")
vis, msg = E.tracked_gate(paid_pooled, c, True)
ok(not vis and "private" in msg.lower(), "private opponent -> private message")
vis, msg = E.tracked_gate(paid_pooled, b, True)
ok(vis and msg is None, "pooled opponent visible, no lock")
vis, msg = E.tracked_gate(free, a, False)
ok(not vis and msg is None, "no tracked data -> no lock message (own note)")
vis, msg = E.tracked_gate(admin, c, True)
ok(vis and msg is None, "admin always visible")

print(f"\nALL {PASS} CHECKS PASSED")

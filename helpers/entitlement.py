"""
entitlement.py — coach-tier gating: who may see TRACKED play-by-play depth, and
whose tracked data is in the shared league pool.

Streamlit-free + pure (pass the viewer identity dict in) so it's unit-testable
headlessly, like the other engine helpers. The identity dict is what
helpers.auth.current_user() returns: {'email','role','plan','paid_until',
'team_id', ...}.

Model (see scaling-roadmap memory):
  Free   -> no tracked depth anywhere (box-score + rankings only).
  Paid   -> tracked depth on their OWN team always; on OTHER teams only when
            BOTH the viewer's team and the target team have opted into the
            league pool (teams.in_pool) — reciprocity: read the pool only if
            you are in it.
  admin  -> everything.
"""
from __future__ import annotations

from datetime import date

from database.db import query


def has_paid_plan(ident: dict | None) -> bool:
    """Viewer holds a Paid plan. Admin always qualifies; a future paid_until
    counts even if the plan text still says 'free' (the Stripe poll writes the
    date)."""
    if not ident:
        return False
    if ident.get("role") == "admin":
        return True
    if ident.get("plan") == "paid":
        return True
    pu = (ident.get("paid_until") or "").strip()
    if pu:
        try:
            return pu >= date.today().isoformat()
        except Exception:
            return False
    return False


def pool_team_ids() -> set[int]:
    """Team ids opted into the shared league pool (teams.in_pool = 1)."""
    return {r["id"] for r in query("SELECT id FROM teams WHERE in_pool=1")}


def _viewer_in_pool(ident: dict | None, pool: set[int]) -> bool:
    tid = ident.get("team_id") if ident else None
    return tid is not None and int(tid) in pool


def can_see_team_tracked(ident: dict | None, team_id,
                         pool: set[int] | None = None) -> bool:
    """May this viewer see TRACKED depth for `team_id`? See the model above.
    `pool` may be passed in to avoid re-querying in a loop."""
    if not has_paid_plan(ident):
        return False
    if ident.get("role") == "admin":
        return True
    own = ident.get("team_id")
    if own is not None and team_id is not None and int(own) == int(team_id):
        return True
    pool = pool_team_ids() if pool is None else pool
    return _viewer_in_pool(ident, pool) and (team_id is not None and int(team_id) in pool)


def tracked_gate(ident: dict | None, team_id, raw_has_tracked: bool,
                 pool: set[int] | None = None):
    """Resolve a team's tracked-depth visibility for the UI.

    Returns (visible, lock_msg):
      visible   — True if the viewer may see tracked depth for this team.
      lock_msg  — None when visible, OR when there's simply no tracked data
                  (caller shows its own 'track a game' note). Otherwise a short
                  reason the depth is locked (paywall / not-in-pool / private)."""
    if not raw_has_tracked:
        return False, None
    if can_see_team_tracked(ident, team_id, pool):
        return True, None
    if not has_paid_plan(ident):
        return False, ("🔒 Tracked analytics — shot charts, lineups, four factors "
                       "and scouting — are a **Paid** feature. Upgrade to unlock.")
    pool = pool_team_ids() if pool is None else pool
    if not _viewer_in_pool(ident, pool):
        return False, ("🔒 Scouting another team's tracked data needs the **league "
                       "pool**. Turn on the league toggle for your team in Settings.")
    return False, ("🔒 This team keeps its tracked data **private** (not in the "
                   "league pool) — only box-score views are available.")

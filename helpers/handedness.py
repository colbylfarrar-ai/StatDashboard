"""
handedness.py — single source for "which hand side did this shot come from?".

A player has a shooting hand (players.handedness, 'right'|'left', default 'right').
Each shot's FLOOR side comes from its zone (authoritative + always present, unlike
the optional tap x/y): LC/LW = left, RW/RC = right, C = straightaway/center.

Mapping side -> hand bucket, per the shooter's handedness:
  right-handed shooter: RIGHT floor side = DOMINANT, LEFT = WEAK
  left-handed  shooter: LEFT  floor side = DOMINANT, RIGHT = WEAK
  zone C (straightaway): its own CENTER bucket, never dominant/weak.

Pure + Streamlit-free (mirrors helpers/stats.py). The aggregation functions that
roll shots into these buckets live next to their siblings:
  - per-player : helpers.stats.player_hand_splits
  - per-team   : helpers.team_analytics.hand_splits
so callers reach them as S.* / TA.* like the guarded/zone splits.
"""
from __future__ import annotations

from database.db import query

LEFT_ZONES = frozenset({"LC", "LW"})
RIGHT_ZONES = frozenset({"RC", "RW"})

# Display order for the three buckets.
HAND_BUCKETS = ("dominant", "weak", "center")
HAND_LABELS = {"dominant": "Dominant side", "weak": "Weak side", "center": "Center"}


def floor_side(zone) -> str:
    """'left' | 'right' | 'center' for a shot's zone (None/unknown -> 'center')."""
    if zone in LEFT_ZONES:
        return "left"
    if zone in RIGHT_ZONES:
        return "right"
    return "center"


def hand_bucket(zone, handedness) -> str:
    """'dominant' | 'weak' | 'center' for a shot given the shooter's handedness."""
    side = floor_side(zone)
    if side == "center":
        return "center"
    dominant_side = "left" if (handedness == "left") else "right"
    return "dominant" if side == dominant_side else "weak"


def hand_map() -> dict:
    """{player_id: 'right'|'left'} for every player (defaults blanks to 'right')."""
    return {r["id"]: (r["handedness"] or "right")
            for r in query("SELECT id, handedness FROM players")}

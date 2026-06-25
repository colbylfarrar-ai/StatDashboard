import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from helpers.ui import page_chrome, lab_hero as _lab_hero
from database import db
import helpers.ossaa_sync as SYNC
from tools.ossaa_import import build_plan_single, build_plan_crawl

_cfg, ACCENT = page_chrome("OSSAA Import")
_lab_hero("OSSAA Import", phase="BUILD",
          sub="Pull team schedules from ossaarankings.com and turn them into "
              "teams + games. Preview first — nothing is written until you import.")

CLASS_OPTIONS = ["6A", "5A", "4A", "3A", "2A", "A"]
GENDER_OPTIONS = ["Boys", "Girls"]
GMAP = {"M": "Boys", "F": "Girls"}

st.caption("Source: ossaarankings.com (unofficial; fetches are rate-limited). "
           "Team names get a **Boys**/**Girls** suffix, which also keeps boys & "
           "girls of the same school as separate teams.")

mode = st.radio("Mode", ["Single team", "Crawl a class"], horizontal=True)
c = st.columns(4)
if mode == "Single team":
    seed = c[0].number_input("OSSAA team id", min_value=1, step=1, value=158209,
                             help="The t=NNNNN in an ossaarankings team URL.")
    klass = gender = None
    max_fetch = 1
else:
    seed = c[0].number_input("Seed team id", min_value=1, step=1, value=158209)
    klass = c[1].selectbox("Class", CLASS_OPTIONS, index=4)
    gender = c[2].radio("Gender", GENDER_OPTIONS, horizontal=True)
    max_fetch = c[3].slider("Max teams to fetch", 1, 60, 12,
                            help="Each team is one polite web request (~1s).")

# ── scrape (network runs only on this click, never on a plain rerender) ───────
if st.button("🔍 Preview plan", type="primary"):
    status = st.empty()
    seen = []

    def _progress(sched, tid):
        seen.append(sched.school)
        status.info(f"Fetched {len(seen)}: {sched.school} "
                    f"({sched.klass} {GMAP.get(sched.gender, '?')}) — "
                    f"{len(sched.games)} games")

    try:
        with st.spinner("Scraping ossaarankings.com…"):
            if mode == "Single team":
                plan, _ = build_plan_single(int(seed))
            else:
                plan, _ = build_plan_crawl(int(seed), klass, gender,
                                           int(max_fetch), progress=_progress)
        status.empty()
        st.session_state["ossaa_plan"] = plan
    except Exception as exc:  # network / parse failure — keep the page usable
        st.error(f"Scrape failed: {exc}")

# ── preview + import ──────────────────────────────────────────────────────────
plan = st.session_state.get("ossaa_plan")
if plan:
    SYNC.ensure_schema()

    team_rows = []
    for name, (k, g, oid, state) in sorted(plan.teams.items()):
        exists = bool(oid and db.query("SELECT 1 FROM teams WHERE ossaa_id=?", (oid,)))
        if not exists:
            exists = bool(db.query("SELECT 1 FROM teams WHERE name=?", (name,)))
        team_rows.append({"team": name, "class": k, "gender": GMAP.get(g, "?"),
                          "state": state, "ossaa_id": oid or "",
                          "status": "exists" if exists else "NEW"})
    tdf = pd.DataFrame(team_rows)
    new_teams = int((tdf["status"] == "NEW").sum())

    game_rows = [{"date": d, "home": h, "away": a,
                  "score": (f"{hs}-{as_}" if hs is not None else "—")}
                 for (d, h, a, hs, as_, _t) in sorted(plan.games)]
    gdf = pd.DataFrame(game_rows)
    played = sum(1 for g in plan.games if g[3] is not None)

    st.subheader("Plan preview")
    m1, m2, m3 = st.columns(3)
    m1.metric("Teams", len(tdf), f"{new_teams} new")
    m2.metric("Games", len(gdf), f"{played} played")
    m3.metric("Future / no-score", len(gdf) - played)

    with st.expander(f"Teams ({len(tdf)})"):
        st.dataframe(tdf, use_container_width=True, hide_index=True)
    with st.expander(f"Games ({len(gdf)})", expanded=True):
        st.dataframe(gdf, use_container_width=True, hide_index=True)

    st.warning("Import writes to the **active season** DB. Existing teams are "
               "matched (by OSSAA id, else name — case-insensitive); existing "
               "games are skipped, never overwritten. Crawl mode imports the "
               "**whole scraped schedule** (every team + game, not just the seed "
               "team) — opponent-vs-opponent games show in league-wide Rankings.")
    if st.button("⬇️ Import to database", type="primary"):
        with st.spinner("Writing teams & games…"):
            res = SYNC.ingest(plan)
        st.success(
            f"Done — {res['teams_created']} teams created "
            f"({res['teams_matched']} matched), {res['games_inserted']} games "
            f"inserted ({res['games_skipped']} already present).")
        st.session_state.pop("ossaa_plan", None)

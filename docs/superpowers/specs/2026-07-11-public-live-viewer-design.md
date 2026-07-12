# Public Live Game Viewer ("Fan Link") — Design

Date: 2026-07-11
Status: approved (founder), building on `feat/public-live`

## Goal

ESPN/GameChanger-style **public, no-login, live follow-along page** for a single
game. Fans open a shared link on their phone and watch score, box score,
play-by-play and a shot chart update live while a coach tracks courtside.
Free forever — top-of-funnel for the paid coach product.

## Non-goals (v1)

- No statewide scoreboard / landing page (waits for the OSSAA live scraper).
- No Streamlit changes. The coach analytics hub is untouched.
- No fan accounts, notifications, or installs (plain web page, NOT a PWA).
- No delay toggle (founder: everyone keeps a book; nothing sensitive is public).

## Architecture

New **unauthenticated** surface on the existing tracker FastAPI app
(`tracker/api.py`) — same process, same SQLite DB, $0 extra hosting:

- `GET /live/{token}` → static fan page (`tracker/static/live.html`).
- `GET /api/public/game/{token}` → allowlisted JSON state (poll every ~8s live,
  ~60s once final). Served through a 3-second in-process cache so N fans cost
  ~1 DB read per interval per game.
- Coach control (authenticated, existing `/api` router):
  `POST /api/games/{id}/public` → flip `is_public`, mint `share_token`
  (once, stable thereafter), return the share URL. Exposed as a "Fan link"
  button on the PWA lineup screen.

## Privacy model (allowlist, never blocklist)

`helpers/public_feed.py` builds the public payload by explicit construction.
Nothing else can leak because nothing else is ever read into the payload.

- **Players: jersey numbers only.** No names, either team, anywhere (box,
  play-by-play, shot chart).
- **Officials: anonymized crew slots R / U1 / U2** (assigning convention),
  public payload = foul counts per slot only. Names never leave the server.
  Who is R vs U1 is known offline to assigners/ADs/coaches/crew — the page
  never maps slot→name. Slot order = `game_lineup_officials.slot` when set,
  else first-seen (insertion id) order.
- **In:** score, status, quarter/clock (last event), quarter scores, team
  fouls by quarter, per-player box lines (PTS, FG, 3FG, FT, REB, AST, STL,
  BLK, TOV, PF), on-floor markers, play-by-play strings ("#23 3PT make
  (assist #3)"), shot chart dots (x, y, make, 2/3, team, jersey).
- **Out:** player names, play_type, defense, turnover_type, foul_type,
  official names/ratings, all ratings (OVR/RTG/Game Score), lineup analytics,
  possession counts, minutes.

Unknown token and non-public game return an identical 404 (no existence leak).

## Schema (idempotent migrations in `database/db.py`)

- `games.is_public INTEGER NOT NULL DEFAULT 0`
- `games.share_token TEXT NOT NULL DEFAULT ''` (+ index)
- `game_lineup_officials.slot INTEGER` (NULL = fall back to id order)

## Fan page (`live.html`)

Self-contained mobile-first page in the PWA's dark brand look; reuses
`/static/court.js` for the half-court SVG (dots appended to its group).
Sections: score header (teams, status, Q/clock) → quarter-scores strip → box
score tabs (both teams, numbers only, on-floor dot) → shot chart with
team/player filter → play-by-play → officials R/U1/U2 foul line → watermark
footer "Live stats by HoopTracks" + CTA link. Polls with `version` (max event
id) short-circuit so unchanged states skip re-render. Outside the service
worker (`sw.js` bypasses `/live`); fans never register the SW.

## Testing

`tracker/test_public_feed.py` (same throwaway-DB pattern as `test_api.py`):
seed → log events via the authenticated API → assert 404 before opt-in →
flip public → assert payload correctness AND a hard privacy sweep (serialized
JSON contains no player/official names, no play_type/defense values) →
finish game → status flips to final. Plus token stability across off/on.

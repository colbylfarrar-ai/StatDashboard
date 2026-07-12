# Live viewer: back-to-game nav + landing Teams/Rankings view

Date: 2026-07-12 · Status: approved by founder (chat)

## Goals

1. Fan on a live game page taps a team name → team schedule page. Needs an
   obvious way BACK to the live game.
2. `/live` becomes a true landing: search ANY team at any time, see records,
   find games — plus a public rankings snapshot.

## Decisions (founder-approved)

- **Rankings exposure: rank + record only.** Ordinal rank and W-L, derived
  from `team_ratings.score_ratings` (results-only engine — inputs are the
  same public final scores the scoreboard already shows). No `Power`, no
  `Rating`, no tracked/possession numbers, ever. The public_feed allowlist
  discipline ("would I put this on a gym scoreboard?") extends to: a wall
  ranking poster is fine, engine output numbers are not.
- **Layout: Scores | Teams toggle on `/live`.** One page, one URL. Scores
  view is the existing page unchanged; Teams view adds search + rankings.
- **Default filter = Oklahoma.** Teams view opens with class chips
  `OK B2, OK B1, OK A, OK 2A, OK 3A, OK 4A, OK 5A, OK 6A` pre-selected, so
  only OK schools show by default (OK teams with class N/A are also hidden by
  default — founder's explicit chip list). Chips are toggleable; a non-empty
  search bypasses chip filters entirely (searching "Bentonville" must work).

## 1. Back-to-game (client-only)

- `live.html`: team-name links gain `?from={token}` (the page's own share
  token, URL-encoded).
- `live_team.html`: read `from` from the query string, validate against a
  conservative token shape (`^[A-Za-z0-9_-]{4,64}$`), and when present render
  `‹ Back to game` → `/live/{from}` in the brand bar ahead of the existing
  `Scores` link. Invalid/absent param → today's behavior. No server change,
  no open-redirect surface (path is always `/live/` + validated token).

## 2. New public API — `GET /api/public/teams`

`public_feed.teams_directory()`:

- **Season**: the season of the most recent finished game (active `Current`
  when in-season; latest archived label in the offseason — same precedent as
  `team_profile`). Payload carries the resolved label (`""` for Current).
- **Ranks**: `score_ratings(gender, season=…)` per gender (M, F). Copy out
  rank + record fields only.
- **Per team**: `{id, name, gender: Boys|Girls, state, class_lbl, wins,
  losses, gp, rank, of, class_rank, class_of}` — `rank` fields null for
  teams below the engine's radar (no finished games). Every team in the
  `teams` table is listed so search always resolves.
- **Cache**: module TTL cache. Age < 60 s → serve. Otherwise check
  `results_fingerprint()` (a few ms): unchanged → re-stamp, changed →
  recompute (~0.5 s full league). Wired into `clear_cache()`.
- Route sits with the other UNAUTHENTICATED `/api/public/*` routes in
  `tracker/api.py`.

## 3. Landing UI (`live_index.html`)

- Brand bar gains a `Scores | Teams` segmented toggle; view state in the
  query string (`?v=teams`) via `history.replaceState` so links/refresh keep
  the view. Scores view: existing DOM untouched.
- Teams view:
  - Always-visible search box (all teams, not just today's slate).
  - Gender chips Boys | Girls (single-select, default Boys).
  - Class chips from payload's distinct `class_lbl` values, multi-select,
    default = the 8 OK classes above (intersected with what exists), plus an
    `All` chip that clears class filtering.
  - Rows: `#rank Team  W–L` with `class_lbl` sub-line, linking to
    `/live/team/{id}`. Ranked teams by rank asc; unranked teams after, A-Z.
  - Render cap: first 150 rows + `Show more` button (full list stays in
    memory for search; keeps the DOM phone-friendly at ~1 400 teams).
  - Season caption when showing an archived season.
  - One fetch when the Teams view first opens; no polling.

## 4. Tests + hygiene

- `tracker/test_public_feed.py` additions: directory payload shape; privacy
  sweep proves no `Power`/`Rating`/`AdjNet` keys and no player/official names
  in the teams payload; unranked team gets `rank: null`; API route 200.
- `sw.js` cache version bump (static HTML changed).

## Out of scope

- Power numbers public, per-player anything, `/live/teams` as its own page,
  archive season picker on the public site.

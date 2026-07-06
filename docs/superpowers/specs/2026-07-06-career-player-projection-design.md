# Career Player Projection — Design (base layer)

**Date:** 2026-07-06
**Branch:** feat/coach-tiers
**Status:** approved design → implementation plan next

## Purpose

Projected, sample-stabilized rate stats for every player, so thin-sample kids get a
directional read instead of raw noise. This is the **base layer** for the larger
projection map (lineup projection → depth-chart minutes → 4-factor lineup optimizer →
year-to-year team projection). Ship it alone, on the player card, paid-gated.

## Data reality (drives every decision)

One season tracked. One team at 21 games; nearly everyone else at ~3. Raw rates on
3 games are noise. So the module is fundamentally a **shrinkage + prior** engine, not
a new-stat engine. Designed around the 21-game team as the reference case; stabilize
around ~15 games; accept that season-1 priors are thin.

## Non-goals (YAGNI)

- No new statistics or new math — reuse `helpers/shrinkage.py` and existing leaves.
- No multi-season data yet (only one season exists) — but the career aggregation is
  written so widening the game window across seasons via `identity` is a one-line
  change when season 2 lands.
- No depth-chart minutes, no lineup optimizer, no team season projection — those are
  separate specs that consume this one.
- No new page — player-card tab only.

## Architecture

New pure-data module `helpers/projection.py`. Same contract as `lineups.py` /
`rotation_plan.py`: db + stats + no streamlit. It **orchestrates** existing pieces:

| Concern | Reused from | Notes |
|---|---|---|
| Beta-binomial blend (make/att rates) | `shrinkage.stabilize_rate` | FG%/3P%/FT% style |
| Volume-shrunk blend (rate w/o clean count) | `shrinkage.stabilize_value` | TS%/eFG%/SMOE style |
| 0-100 index toward anchor by games | `shrinkage.stabilize_index` | `k_games=3.0` default already = target curve |
| Pool prior (mean + k) | `shrinkage.eb_prior` | feed archetype subset OR whole league |
| Confidence band / tier | `shrinkage.rating_confidence`, `wilson_interval` | the ± band + High/Low label |
| Raw player leaves + counts | `player_ratings.player_stat_table` | already carries FGM/FGA/… and the app leaves |
| Cross-game/-season player identity | `identity` | career opportunity aggregation |
| Archetype label per player | `archetypes` | the role-aware prior anchor |

### Credibility curve (the 21-game / 15-game intent)

Index-style shrink uses `stabilize_index` with `k_games = 3.0` (the existing default):
`weight = g/(g+3)` → 3g≈50%, 15g≈83%, 21g≈87.5%. Matches the approved curve. Rate-style
stats shrink by **their own opportunity volume** through `stabilize_rate`/`stabilize_value`
(attempts, shot-equivalents, possessions) with the per-stat EB `k` — the more correct
per-opportunity version of the same "≈15 games to stabilize" intent, so a 3-game starter
with real volume out-trusts a 3-game bench cameo.

### The prior (graceful degradation)

For each stat, `prior_mean` is chosen role-aware **when there is enough evidence**:

1. Compute the player's archetype (`archetypes`).
2. If that archetype's pooled opportunities for the stat clear a sample gate
   (`ARCHETYPE_MIN_OPP`, e.g. ≥150 attempts-equiv across the archetype), use
   `eb_prior` over just that archetype's players → archetype anchor.
3. Else fall back to `eb_prior` over the whole tracked league → league anchor.

Season-1 truth: almost no archetype clears the gate, so nearly everyone regresses to
the league mean (itself dominated by the 21-game team). Accepted limitation. Season 2+,
archetype priors switch on with **no code change** — only the data grows.

### Baseline normalization

Every projected rate is also returned as a delta vs the **average tracked team**
(the chosen baseline): `delta = proj − tracked_league_mean(stat)`. Free and honest —
the opponent adjustment already centers league-mean at 0. Enables "+3.1 SC% above
tracked-average" copy and feeds the downstream optimizer's normalization.

## Public API

```python
project_player(pid, gender=None, game_ids=None, table=None, priors=None) -> dict | None
project_roster(team_id, gender=None, game_ids=None) -> {pid: projection}
```

`project_player` returns, per stat in the v1 set:

```python
{
  "pid": int, "name": str, "archetype": str,
  "games": int, "poss": int,
  "confidence": {"tier","label","frac","ci"},   # from rating_confidence
  "stats": {
     "<stat>": {
        "own":   float | None,   # raw observed rate
        "prior": float,          # anchor used (archetype or league)
        "proj":  float,          # stabilized = shrink(own, volume, prior)
        "c":     float,          # credibility weight 0-1 actually applied
        "band":  [lo, hi] | None,# uncertainty band (wilson / rating_confidence)
        "delta": float,          # proj − tracked-average baseline
        "prior_src": "archetype" | "league",
        "flag":  "solid" | "directional" | "thin",
     }, ...
  },
}
```

`project_roster` batches: build the stat table + EB priors + archetype pools **once**,
pass them into each `project_player` (the `table`/`priors` params) so the roster call is
one table build, not N.

### v1 stat set

The leaves that feed the 4 factors + win formula + the named list: **SC, usage, SC%,
pass%, SMOE, RimDef, PerimDef**, plus the 4-factor contributors already in the table
(eFG, TOV, OREB, FTR). Each classified as make/att (→`stabilize_rate`) or
volume-rate (→`stabilize_value`) by its natural denominator; a single `_STAT_SPECS`
table maps stat → (kind, made_key, att_key | volume_key). Adding a stat = one row.

### Career aggregation (season-forward hook)

Opportunity counts come from `player_stat_table(game_ids=...)`. Today `game_ids` = the
current season's tracked pool. `identity` resolves a player's id across seasons/teams;
the aggregation collects **all game_ids linked to that identity** so, when a second
season exists, the same call spans the career. One resolver function, gated so season-1
behavior is identical (only current-season ids exist to collect).

## Surface

New **"Projection"** tab on the player card (`helpers/dashboard/player_card.py` /
`profile_tab` neighbor). Paid-gated via the existing entitlement check used by the other
paid tabs. Shows per stat: `own → proj (band)`, the delta-vs-average chip, the prior
source, and a confidence meter. Every value carries the `flag` so a `thin`/`directional`
read is visually honest — same discipline as `rotation_plan` notes. No new page, no new
nav.

## Error / edge handling

- Unrated / zero-opportunity player → `project_player` returns the prior with `c≈0`,
  `flag="thin"`; never crashes, never invents a number.
- No tracked games in scope → `project_roster` returns `{}`.
- Archetype unknown → league prior, `prior_src="league"`.
- `eb_prior` already clamps k to a sane band; degenerate pools can't produce a runaway
  prior.

## Testing (`tracker/test_projection.py`)

1. Credibility monotonic in volume (more poss → higher `c`, `proj`→`own`).
2. 3-game player lands ≈50% blend (own/prior weight ~0.5 on the index curve).
3. 21-game player `proj` ≈ own rate (`c` ≈ 0.875+).
4. Prior degrades archetype→league when the archetype pool is below the sample gate.
5. `delta` sign correct vs a known tracked-average.
6. Unrated/zero-opp player returns prior + `flag="thin"`, no crash.
7. `project_roster` == per-player `project_player` (batch equals loop).

## Build order

1. `helpers/projection.py` — `_STAT_SPECS`, prior builder, `project_player`,
   `project_roster`, identity career hook.
2. `tracker/test_projection.py` — the 7 checks above (TDD: tests first).
3. Player-card "Projection" tab, paid-gated.

Downstream (separate specs): depth-chart minutes → 4-factor lineup optimizer →
year-to-year team projection, all consuming `projection.project_roster`.

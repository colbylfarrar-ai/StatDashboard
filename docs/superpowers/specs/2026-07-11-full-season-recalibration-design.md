# Full-Season Recalibration — Design

**Date:** 2026-07-11
**Status:** Approved by founder (straight-to-prod, full audit, harness-first, phased)
**Context:** Local DB now mirrors prod (13,363 games / 5,314 events / 1,449 teams; season
`2025-2026`, post-rollover). Adair Girls have 23/32 games event-tracked — near-full season,
playoffs starting. Every engine constant was tuned on a ~15-game assumption; this project
re-derives them against the fuller data.

## Data reality (measured, drives the whole design)

| Fact | Value | Consequence |
|---|---|---|
| Tracked games (league) | 29 | Player-level backtest ≈ Adair-only |
| Adair Girls tracked | 23 | The one real holdout sample; k-fold it |
| Next-deepest teams | 5, 4, 3, 3, 3… | League pool stays thin — constants must stay protective for them |
| Manual-box games in 2025-2026 | 0 | `MANUAL_GAME_WEIGHT` currently inert; tune principle-only |
| Score-only games | ~13.3k | Rich league-wide signal for team ratings / SOS targets |
| Season sentinel | data under `2025-2026`, not `Current` | Harness must scope explicitly (archive-hardcode gotcha) |

## Two weight families

**Family A — sample-size / trust knobs.** Control how hard values regress toward average
and when signals display. These are legitimately functions of sample size and are the real
"more data" win. Re-tuned in Phase 1.

**Family B — structural leaf weights.** Encode basketball priors about which stat carries
signal (e.g. `TS%` at 1.5 in `_SHOOTING`). NOT sample-size dependent; touching them without
an out-of-sample test is guessing. Only re-tuned in Phase 3, against the harness.

## Non-negotiable principle

**The harness is the deploy gate.** Every constant change — Family A or B — ships only if
the backtest shows improvement (or non-regression, for principle-driven changes like
season-fraction anchoring) on held-out games. No vibe-tuning on a straight-to-prod system.

## Phase 0 — Validation harness (`tools/backtest.py`, new; no engine changes)

K-fold holdout over Adair's 23 tracked games (4 folds, ~5-6 games each), plus a league-wide
team-margin target over the full score graph (hold out latest 10% of dated games).

Targets, scored on held-out games only, engines built on the remainder:
1. **Team margin MAE** — `team_ratings` (+SOS) predicted margin vs actual.
2. **Player production MAE + Spearman corr** — projected per-game line (projection.py)
   vs actual held-out per-game line, Adair pool.
3. **Rating validity corr** — train-side OVERALL vs held-out on-court net (fallback: held-out
   Game Score when lineup data too thin in a fold).

Also `tools/rating_diff.py`: dumps every player's five ratings under old vs new constants,
sorted by |Δ OVERALL|, so each phase gets an eyeballable before/after. Both tools scope
season explicitly and run against the real local DB path via `database.db.get_db_path()`.

## Phase 1 — Family A recalibration (harness-swept)

Inventory (file → constant → current):

| File | Constant | Now |
|---|---|---|
| shrinkage.py | `DEFAULT_RATE_K` | 12 |
| shrinkage.py | `DEFAULT_INDEX_K` | 3 |
| shrinkage.py | `_K_BOUNDS` | (4, 60) |
| shrinkage.py | `k_poss` (rating_confidence) | 40 |
| shrinkage.py + player_ratings.py | confidence ladder | 10/6/3 games |
| player_ratings.py | `RATING_K_GAMES` | 5 |
| player_ratings.py | `MANUAL_GAME_WEIGHT` | 0.35 |
| player_ratings.py | `MIN_POOL_FOR_RESTD` | 8 |
| projection.py | `K` (=DEFAULT_RATE_K) | 12 |
| projection.py | `CAREER_CUTOFF` | 5 |
| projection.py | `ARCHETYPE_MIN_OPP` | 150 |
| lineup_projection.py | `MIN_TEAM_GAMES` / `MIN_PP` | 8 / 8 |
| rapm.py | `DEFAULT_MIN_POSS` | 40 |
| rapm.py | `PRIOR_SCALE` | 0.10 |
| team_ratings.py | `DEFAULT_REG` / `DEFAULT_SOS_WEIGHT` | 4.0 / 0.8 |
| insights.py / team_insights.py / insights_team.py / situational.py | `MIN_Z`, `MIN_GAMES`, `MIN_TRACKED`, shot/poss gates | 1.0 / 5 / 3 / various |

Method: per-constant candidate grid, swept against Phase-0 targets; joint sanity pass on the
winning vector (constants interact — e.g. `RATING_K_GAMES` × `DEFAULT_INDEX_K`).

**Season-fraction anchoring:** trust/display gates (confidence ladder, miner density gates)
re-anchor on games ÷ team-season-length where a fixed count would misread — 23-game Adair
reads full-confidence, 3-game teams stay gated. Shrink-k's remain `g/(g+k)` (already
games-adaptive); the sweep just finds the right k for the fuller pool.

Notes: RAPM ridge λ already auto-tunes via `RidgeCV` (1200 is a no-sklearn fallback) and
`eb_prior` already refits per-pool — both confirmed self-calibrating, no changes needed there
beyond gates/bounds.

## Phase 2 — Signal unlocks

Signals deliberately damped for thin data, now re-validated and (if harness agrees) enabled
or strengthened: RAPM impact pillar (possessions now clear `DEFAULT_MIN_POSS` for the core
pool), `oppadj` shrink (schedule spread now real), archetype-anchored projection priors
(`ARCHETYPE_MIN_OPP` clearance), career blend (`CAREER_CUTOFF`), insight-miner density.

## Phase 3 — Family B structural weights

Coordinate descent, one weight at a time, against target 3 (rating validity) and target 2
(production): `_SHOOTING` / `_OFFENSE_PARTS` / `_OVERALL_PARTS` / `_DEFENSE_PARTS` leaf
weights, `game_rating.py` role weights. Keep only measured improvements. **Explicit out:**
if fold-to-fold noise swamps the signal (likely on 23 games), Phase 3 ships nothing and says
so — an honest null result, not a failure.

## Rollout / risk controls

- Phased deploys (Phase 1 first), each preceded by `rating_diff` review + full test suite.
- Straight-to-prod, mixed team depths → season-fraction anchoring + protective league-pool
  constants; a change must help the pool, not just Adair.
- Second agent concurrently deploying to prod → re-fetch BEL + check prod HEAD immediately
  before each deploy; apply on top; never force-push.
- Deploy path (from memory): Desktop commit → format-patch → BEL clone `git am --3way
  --directory=APP5.0` → push → `ssh app5@107.170.27.154 ~/update.sh` → verify HEAD,
  3 services, app+track 200.

## Success criteria

1. Harness runs clean on the local prod-snapshot DB; targets reproducible.
2. Phase-1 constant vector beats current constants on held-out targets (or ties with better
   calibration story, e.g. confidence labels matching realized error).
3. No thin-team player rating moves toward extremes without evidence (rating_diff audit).
4. Existing test suites stay green; new tools carry their own tests.

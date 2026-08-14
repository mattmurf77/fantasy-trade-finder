# PRD: P3 — Archetypes & Value Decomposition

> Phase P3 of the trade-relevance initiative. Parents SIGNED OFF and binding:
> [enhancement-plan.md](../enhancement-plan.md) §Phase 3, [hld.md](../hld.md)
> (D9, §5.2, R11), [lld.md](../lld.md) (B14, §4.11/4.12). This PRD adds the
> product contract and the decision gates; it does not reopen design. P3-4
> (build philosophy) is absorbed into P3-2 per the HLD. Dual-agent authored;
> log in [../reconciliation-log.md](../reconciliation-log.md).

## 1. Summary

FTF knows *how much* a user values a player (Elo board) but not *what kind*.
The deck can say "needs a RB"; it cannot say "needs a pass-catching RB for
your PPR contender." The operator's own trade philosophy — the founding user
voice — is explicitly archetype-shaped: rushing QBs vs pocket passers,
pass-catching backs vs grinders, deep threats vs possession WRs, age as
tiebreak. None of that is representable in the current feature space. The raw
signal already exists unread: `member_rankings` snapshots every user's Elo
deltas vs consensus (a direct, revealed statement of taste), and nflverse
publishes free, licensed per-player usage stats that separate archetypes
cleanly. P3 connects the two — as data + models only (P4 makes it visible),
with deck ordering improving invisibly this phase via taste, F6 interactions,
wildcard auditions, and archetype-aware need-fit.

## 2. Problem & Context

Suggestion quality plateaus at "right position, right value band, wrong
player." Three consumers are ready for archetype signal today (taste vectors,
the F7 audition pool, `need_fit_score`) and F6 v2's feature space (P1) is
built to take interaction features. What's missing is the data layer and the
per-user preference decomposition — plus honest answers to four feasibility
questions this PRD gates on: August data staleness, threshold validity,
actual user eligibility, and circularity with the board-derived taste prior.

## 3. Goals & Non-Goals

**Goals**

- G1 (P3-1): nightly `player_archetypes` — 8 continuous axes + threshold
  tags, nflverse-sourced, Sleeper-keyed, coverage-gated with keep-yesterday.
- G2 (P3-2, incl. P3-4): per (user, scoring_format) `user_value_profiles` —
  interpretable Elo-denominated coefficients (position/age/archetype premia)
  + build-philosophy keys, confidence-gated, clamped ±300.
- G3 (P3-3): archetypes wired into serving — `arch:<tag>` taste dims, F6 v2
  interaction features, F7 archetype auditions, archetype-aware need-fit —
  so ordering improves this phase, invisibly.
- G4: **causally measured** like-rate lift on archetype signal (§4), and zero
  "insulting inference" incidents (template rules are P4's, but P3's
  coefficients must be renderable non-insultingly: market/fit units, clamps).

**Non-Goals (binding)**

- No LLM classification; no request-time nflverse reads; no weekly
  play-by-play ingestion (season aggregates only, v1).
- **No UI this phase** — "your trading profile" is P4-4; personal hooks are
  P4-1; P3 ships dark.
- No archetype/profile *editing* — P3 implements only the `declared`
  override-at-read precedence; no write surface.
- No IDP archetypes; no rookie-pick archetypes (picks are excluded from the
  design matrix and get no archetype rows); no per-league archetype values
  (league effects live in P2's market model); no rookie-projection product.

## 4. Success Metrics

**Causal, not correlational — naive "matched-card like-rate" is banned as
evidence** (matched cards are matched *because* the user already likes those
players; the naive lift is positive and meaningless). Binding measurement
design:

1. **Randomized audition slots:** the F7 archetype-audition arm serves
   matched vs unmatched cards at logged propensity; the causal read is
   within-slot.
2. **Per-user holdback cell** on the consume flag (interaction features
   zeroed) in the dark-launch experiment.
3. **Offline IPS/SNIPS** on frozen `features_json` (14-day maturation) as
   corroboration.

Success = lift in (1) or (2), read as **a within-slot (or variant-vs-holdback)
like-rate difference whose CI excludes zero** — stated now so "lift" isn't
relitigated at evaluation time; the operator-accept escape hatch remains for
directional-but-underpowered results. **Holdback scope:** the holdback cell
disables ALL archetype consumption for its users — F6 interaction features,
`arch:*` taste dims, F7 archetype arms, and need-fit specialization — not
just the F6 channel. **Attribution caveat, in writing:** `relevance.profiles`
also gates the P2 profile multipliers (LLD §4.10), so its flip co-activates
P2 consumption; any P3 lift claim carries that caveat or uses the
archetype-only holdback for the causal read. Supporting metrics: corrected-
denominator archetype coverage (≥90% gate); % of weekly-actives (defined:
≥1 `session_init` in the trailing 7 days, computed identically wherever the
threshold is used) with `confidence='ok'` profiles; audition win-rate for
archetype arms.
Guardrails: flag rate; F6 position-debias non-regression; batch pass health;
the anti-circularity correlation monitor (§5 R6).

## 5. Requirements

**P3-1 — Archetype layer (LLD §4.11):**

- R1. Nightly `archetypes` pass (D12 registry): nflverse season files via
  temp-file + `os.replace`; `REQUIRED_COLS` schema validation before math;
  missing column ⇒ `error` + keep-yesterday + named column in the report.
- R2. The 8 axes + tag thresholds exactly per LLD §4.11; thresholds are
  reviewed constants in `archetypes.py`, changeable only with a §6 panel
  rerun.
- R3. Crosswalk via `db_playerids`; unmapped ⇒ no row ⇒ neutral.
  **Coverage gate with the corrected denominator:** mapped-rostered coverage
  ≥90% **excluding `years_exp = 0` players and picks** (parent amendment 1) —
  rookies get an age-only row (`axes:{}`, `tags:[]`, `archetype_confidence=0`):
  present, honest, neutral to ordering. (Draft-capital pedigree is **deferred**
  — the nflverse season-stats file carries no draft capital and the field has
  no home in `archetype_json`'s shape; if wanted later it needs its own source
  and a schema note.) Without the exclusion the gate fails every August night
  on rookie-heavy dynasty rosters and wedges the pass in permanent
  keep-yesterday.
- R4. **Seasonal honesty ladder, stated in docs and the scope block:**
  Mar–Aug serves prior-season usage (FA/team changes mislabeled — accepted;
  tags are last-season facts); Sep–Oct a blend rule — **serve the
  prior-season row until current-season games ≥ 6**, stamping
  `season_source` inside `archetype_json` so features are auditable; Nov+
  current season, full confidence. **Tag serving is defined per served row:
  tags travel with the served row, and the games<6 suppression is evaluated
  on the served row's own games** — so while `season_source='prior'`, the
  prior season's tags serve (no September tag blackout for veterans);
  rookies, having no prior row, stay tag-suppressed until current games ≥ 6
  (OQ-B's residual blackout is scoped to rookies only).

**P3-2 — Value decomposition (LLD §4.12):**

- R5. Ridge on the 14×14 system (intercept + 4 position one-hots +
  age_centered + 8 axes), λ=25, pure Python; gates n≥25 ranked AND ≥10 rows
  |y|≥50, else `confidence='insufficient'` and **nothing downstream uses or
  renders it** (never a guess); coefficients clamped ±300 Elo;
  build-philosophy keys (`stars_and_scrubs`, `age_barbell`, `qb_premium`) in
  the same JSON; nightly, ordered after archetypes; user-deletable;
  `declared` overrides inferred at read (no write surface this phase).

**P3-3 — Wiring (flags: `data.archetypes` for derive, `relevance.profiles`
for consume; both default off, byte-identical when off):**

- R6. `card_taste_attrs` gains `arch:<tag>` (top receive-side asset); F6 v2
  gains user-coefficient × card-axis interaction features (frozen into
  `features_json`, 14-day maturation before any training); F7 pool may
  audition archetype arms; `need_fit_score` may specialize need by tag.
  **Single-source anti-circularity rule:** board deltas enter the stack
  through the decomposition channel *only* — `arch:*` taste dims are
  swipe/outcome-derived with a **zero prior, never board-seeded**, and no F6
  feature may combine a board-derived taste prior with a board-derived
  decomposition coefficient. Enforced by a named unit test (taste-update
  path for `arch:*` has no `member_rankings` input) + an eval-pass monitor:
  sustained r > 0.8 between `arch:*` taste dims and decomposition
  interaction features on live impressions ⇒ ledger `warn` (redundant
  channel, candidate for removal). Without this, decomposition shapes
  ordering → ordering shapes likes → taste "confirms" the decomposition.
- R7. Docs per gates: data-dictionary (2 tables), config-reference (flags,
  λ, thresholds pointer), glossary (archetype, decomposition, build
  philosophy), scope block.

## 6. Scope & Phasing — gated rollout

- **Gate 0 (pre-build, hard):** three measurements into the scope block —
  (a) **prod eligibility query** (attempted during PRD authoring; blocked by
  session permissions, so the fleet number is *unknown and this PRD refuses
  to guess*): distinct users with `member_rankings`, with ≥25 rows in one
  format, and of those with ≥10 |delta|≥50 rows. Decision rule: if the last
  number is <30% of weekly actives, decomposition still ships (batch,
  cheap) but P4-4 descopes from the near-term roadmap and sparse F6
  interactions are expected — in writing, not discovered in dark launch.
  (b) August coverage query under the corrected denominator. (c) LLD §8 open
  question 6 verification that `target_share`/`wopr` exist in the current
  nflverse release.
- **Build dark:** tables + passes land; nightly runs populate; no consumers.
- **Threshold panel (blocks tag consumers only):** 50 well-known 2025
  players spanning all axes; tags from the real pipeline vs consensus labels
  (operator + one published usage source); ≥80% agreement per axis or the
  threshold revises and the panel reruns; **operator signs off in writing**
  (panel doc committed to this folder). Until sign-off, tags feed nothing;
  continuous axes may feed F6 features (the model learns its own cuts).
- **Wire + dark-launch:** interaction features freeze into `features_json`
  (mature 14d); F7 auditions at logged propensity; holdback cell assigned.
- **Evaluate (§4):** consume flag stays on only after causal lift or an
  explicit operator accept. P4 copy remains a P4 decision.

Rollback at every step = flag off + keep-yesterday tables; no serving-path
dependency on nflverse availability.

## 7. Dependencies & Risks

**Dependencies:** P1's F6 v2 feature space (interaction features);
`archetype_auditions` staging (exists — F7); P2 profiles enrich context but
don't block. Upstream fragility inherited with guards: nflverse renames
(REQUIRED_COLS + keep-yesterday), price-level small-n (NULL floors); the
archetype report lines up coverage %, unmapped count, and days-stale so
drift is seen, not inferred.

| Risk | Answer |
|---|---|
| August coverage gate fails as written | R3 corrected denominator + pedigree-only rookie rows + R4 ladder; a residual failure is a *finding recorded in the scope block*, never a quietly lowered constant |
| Thresholds are priors, not data | §6 panel with written sign-off; tags blocked until then |
| Eligibility too low to matter | Gate 0 measurement + the <30% descope rule |
| Board counted twice (circularity echo) | R6 single-source rule + unit test + correlation monitor |
| Selection effects fake the win | §4 causal design; naive lift banned as evidence |
| Rookie gsis ids missing at draft time | OQ-A below; pedigree-only rows persist until ids land |

## 8. Rollout & Measurement

Flag order: `data.archetypes` (derive, dark) → panel sign-off →
`relevance.profiles` consume wiring with holdback cell → causal evaluation →
operator accept. Acceptance: 7 consecutive green nightly passes at corrected
coverage ≥90% (or the documented August finding); panel doc committed with
signatures; Gate-0 numbers recorded; the R6 unit test passing; the §4
measurement design implemented before any lift claim; TEST_LEDGER + sim-gate
rows per the feature gates.

**Open questions:** OQ-A — does `db_playerids` gain rookie gsis ids at draft
time or Week 1 (owner: eng, Gate 0)? OQ-B — blend-rule cutover (games ≥ 6)
vs weighted blend: simple cutover ships; revisit only if September
tag-blackout telemetry hurts. OQ-C — should `declared` corrections re-fit
the ridge or override at read? D10 says override-at-read; re-fit is future
work. OQ-D — panel consensus source: operator + one published reference
(required); confirm feasibility.

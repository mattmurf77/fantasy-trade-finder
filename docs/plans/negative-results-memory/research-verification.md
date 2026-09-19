# Negative-Results Memory — Research Verification Memo

**Date:** 2026-08-21 · **Checkout:** clean `origin/main` worktree (`claude/vigilant-spence-8583f5`, HEAD `451d2eb`)
**Purpose:** verify, with file:line citations on this checkout, everything that already exists in the
suppression/preference space before the "negative-results memory" feature is designed. The design risk this
memo exists to kill: **building a fourth overlapping suppression system**. All line numbers are from this
checkout; `server.py` and `database.py` move fast — re-grep before trusting a number across merges.

---

## 1. The swipe/rejection record

### 1.1 `trade_decisions` — the disposition ledger (append-only)

`backend/database.py:319-337`. Columns: `id`, `user_id`, `league_id`, `trade_id`, `give_player_ids` /
`receive_player_ids` (JSON arrays), `decision` (`'like' | 'pass'`), `created_at`, `retracted_at`
(#318 awaiting-dismiss marker, `database.py:328-336`). **Append-only**; rows are never rewritten — a
retraction sets `retracted_at`, a re-like writes a *fresh* row (`database.py:334-336`). Write path:
`save_trade_decision` (`database.py:5171`) with a replay-dedupe (G-049): returns False when the call is a
replay of the immediately-preceding identical row (`database.py:5179-5187`). The UI's "dismiss" is the
API's `decision='pass'` (`database.py:2390`); `/api/trades/awaiting/dismiss` is a *different* action.

### 1.2 `deck_impressions` — the served-card spine (append-only, one row per card per completed job)

`backend/database.py:500-608` (design comment 486-499). Written once per completed generation job by
`server._run_trade_job` → `_log_deck_impressions` (writer body `server.py:4040-4259`), never per poll.
Key columns: `impression_id` (uuid4 PK), `user_id`, `league_id`, `deck_job_id`, `card_index` (final
served order), `trade_hash` (stable hash of give|receive|partner), `features_json` (frozen at serve),
`propensity` (Thompson multiplier ACTUALLY applied; 1.0 on deterministic serves — `database.py:497-499`),
`base_score` / `final_score`, `archetype` (= lane today, `server.py:4230`), `shape_bucket` ("1x1", "2x1",
…), `served_at`, plus flag-gated additive columns: `centerpiece_id` (F3, `database.py:514-517`),
telemetry columns `is_ghost` / `policy_version` / `candidate_set_id` / `candidate_set_size` /
`assets_json` (`database.py:518-539`), bake-off attribution `model_arm` / `arm_rank` /
`fairness_threshold` / `group_key` / `group_rank` / `lane_slot` / `trade_intent` (`database.py:540-607`).

**What `features_json` freezes at serve time** (`server.py:4135-4212`): `shape`, `basis`, `likes_you`,
`lane`, `give_positions` / `receive_positions`, `give_value` / `receive_value` + 500-wide
`*_value_band`s (`server.py:3943-3949`), `involves_pick`, `partner_user_id`, `surplus_margin`
(mismatch), `fairness_score`, `need_fit`, `partner_fit`, `fit_premium`, `aggression_variant`,
`relaxed`, board-state-at-serve (`ranked_player_count`, `last_board_update_at`, `user_value_basis`),
plus flag-gated `deck_source` ("replenish"), `first_deck`, `taste_attrs` (F5 — the frozen attribute
keys, `server.py:4180-4182`), wildcard provenance, and bake-off `also_proposed_by` / `fit` / `fit_diag`.
Frozen-at-serve is a hard contract: outcome-time consumers (taste, Thompson v2, F8 eval) never
re-derive features (`database.py:492-494`, `taste_service.py:238-249`).

### 1.3 `deck_outcomes` — append-only labels

`backend/database.py:741-761`. `id`, `impression_id` (soft ref, no FK), `action` ∈
`viewed | like | pass | not_interested | propose | undo`, `dwell_ms` (capped 120s), `detail_expanded`,
`calc_opened`, `acted_at`. Rows are **never mutated** (`database.py:743`); `undo` appends *alongside* the
original row. `viewed` = card front-of-deck ≥500ms client-side. Writer: `_save_deck_outcome_safe`
(`server.py:4320`), called from the swipe route (`server.py:11662`), not-interested (`server.py:12404`),
propose paths (`server.py:14819`, `25877`, `26363`), and the pass-reason route (`server.py:12037`). The
same writer synchronously drives the F5 taste update (`server.py:4373`).

### 1.4 `trade_pass_reasons` — the reason record (UPSERT, deliberately)

`backend/database.py:873-943` (table def 924-937). One row per passed card keyed on `impression_id`
(PK), the ONE table in this family that upserts — the row grows in place layer 1 → layer 2 → free text
(`database.py:880-887`). Columns: `user_id`, `league_id`, `trade_id`, `key_source`
(`'impression' | 'local'` — only `'impression'` rows join the F1 spine; `'local'` is the degraded
surrogate, `database.py:915-923`), `reason` (layer-1: `value | fit | other`), `detail` (layer-2 codes:
`value_giving | value_getting | value_other | fit_outlook | fit_new_weakness | fit_duplicate |
fit_other | other_player_keep | other_player_avoid | other_text` — the two `other_player_*` codes added
2026-08-19 because "Neither" was **47% of the first production burst** and its free text was
overwhelmingly player-level preference, `database.py:894-902`), `free_text` (stored here and NOWHERE
else — never an analytics property, `database.py:903-905`), `switched_from`, `elo_signal_at` (doubles
as the once-only Elo-write claim via conditional UPDATE, `database.py:910-914`), `created_at`,
`updated_at`. Vocabulary registry: `PASS_REASON_LAYER2` (`database.py:5579`). Route:
`POST /api/trades/pass-reason` (`server.py:12091`); Elo suppression knob `pass_reason_elo_suppression`
(only `value_giving` passes still write Elo; D-066, CHANGELOG line 405). Flag `feedback.decline_reasons`
is ON for all users (`config/features.json`).

### 1.5 How far back usable data goes, and the contamination window

- **F1 spine (`deck_impressions`/`deck_outcomes`) exists since 2026-07-26** — W1 of the discovery-deck
  engine (`living-memory/archive/CHANGELOG-2026Q3.md:23`, flag `deck.signal_v2` ON same day).
- **`trade_decisions` predates the spine** (Thompson v2 treats pre-spine rows as the frozen "legacy
  seam", `server.py:3701-3718`, `load_legacy_shape_counts`).
- **Reason-carrying passes exist only since 2026-08-17T22:22:56Z** (decline-reason capture go-live,
  D-066; encoded as the `pass_cooldown_start_epoch` amnesty default 2026-08-17T22:30:00Z,
  `database.py:2393`, `trade_service.py:364-370`). Dismisses before that instant carry no reason and
  are amnestied from the D-067 cooldown (`server.py:17192-17208`).
- **Contamination window 2026-08-16 → 2026-08-19 (D-091 phantom picks):** 339 of 2,651 served cards
  (12.8%; 23.2% of pick-bearing) offered a phantom 2029 pick; 12.9% of all recorded like/pass outcomes
  landed on one, skewed 6.7% of likes vs 15.8% of passes vs 21.4% of not-interested. That window of
  preference data "must not be cited as a clean propensity or bake-off baseline"
  (`living-memory/DECISIONS.md` D-091 Consequences; `living-memory/TEST_LEDGER.md:707`;
  `living-memory/CHANGELOG.md:242`). A negative-results model trained naively on it partly learns
  "picks get passed on" from cards rejected for being nonsense.
- Prod volumes (committed docs, see §8): ~810 decisions total at 2026-08-17, ~845 like/pass outcomes at
  2026-08-19 — this is **small data**; per-partner per-shape cells will be mostly empty.

---

## 2. Every existing mechanism that suppresses, down-weights, or learns from rejections

This is the heart of the memo. Summary table, then detail. "GEN" = acts at generation (candidate never
exists / is removed before scoring output), "POST" = acts after generation (ordering / filtering of
generated cards).

| # | Mechanism | Storage | Acts at | Hard/soft | Flag / knobs |
|---|---|---|---|---|---|
| a | F3 soft fatigue | derived on read from `deck_impressions⨝deck_outcomes` | POST (ordering multiplier) | soft, ≤1.0 | `deck.fatigue` (ON); `fatigue_*` knobs |
| a | F3 decline suppression | `deck_suppressions` | POST (card removal pre-serve) | hard, 30d + retest | `deck.fatigue` (ON); `fatigue_decline_*` |
| b | R4 windowless exclusion | derived per job from awaiting likes + pending/accepted matches | GEN (filter in `_dedup_and_sort`) | hard, windowless | `trade.presentment_rules` (ON); **no knob** (bypass = bake-off arm A thread-local only) |
| b | Already-swiped dedup (D-067 cooldown) | `trade_decisions` → `past_decision_keys` | GEN (same filter) | hard, pass 14d / like 7d | `pass_cooldown_days`, `pass_cooldown_start_epoch` (model_config) |
| c | `trade_matches.user_{a,b}_dismissed` | `trade_matches` | **neither** — inbox display only | — | none |
| d | Dismiss cooldown (D-067) | same as (b) + live in-memory bind | GEN | hard | shipped 2026-08-17/18 |
| e | F5 taste vectors | `user_taste` | POST (ordering multiplier, clamped) | soft, may boost | `deck.taste_vectors` (ON); `taste_*` knobs |
| f | gen_v2 acceptance prior | **no storage — unfed stub** | GEN (score multiplier) | soft | `gen2_accept_global_prior`=0.5, `gen2_accept_prior_strength`=10 |
| g | Thompson F2 | derived on read from spine + legacy `trade_decisions` | POST (ordering multiplier 0.5–1.5) | soft | `deck.thompson_v2` (ON); `thompson_*` knobs |
| h | Fit arm post-filters | inputs passed in | POST-score inside the arm | hard | fit knobs; `past_decision_keys` shared |
| — | Not-interested / untouchables (#163) | `users` prefs | GEN + POST (authoritative hard filters) | hard, indefinite | — |
| — | A6 diversity + C4/C4b headliner caps | derived from recent impressions / in-deck | POST | hard caps | `trade.deck_diversity` (ON), `deck_headliner_cap` |

### 2a. Deck fatigue F3 (`deck.fatigue`, ON)

Design comment `server.py:4379-4400`; PRD `docs/plans/tiktok-discovery/prds/F3-fatigue-suppression.md`.
Two layers, both per-user, both **POST-generation**:

- **Soft fatigue** — derived at read time (no stored state) by `_deck_fatigue_state`
  (`server.py:4430-4479`) from `viewed` outcomes in `fatigue_lookback_days` (30) and after any
  "Refresh my deck" reset marker (`deck_fatigue_resets`, `database.py:796-803`;
  `load_deck_fatigue_reset` consulted at `server.py:4445-4447`). Keys: `trade_hash`, centerpiece,
  archetype; multiplier form `w1·exp(−a·count) + w2·exp(−b·age)` floored at `fatigue_floor` (0.25),
  MIN across keys (`server.py:4482-4541`), plus a session demotion (0.2) for centerpieces passed ≥2×
  in one job (`server.py:4402`, `4468-4473`). Applied as `fatigue_mult` inside `_order_deck`
  (`server.py:3894-3896`) — **reorders, never removes, never rescues** (`server.py:4388-4390`).
  Computed in the job worker at `server.py:5804-5811`; bypassed on bake-off decks (Channel 2).
- **Hard decline suppression** — `deck_suppressions` (`database.py:775-794`): one row per
  decline/proposal-kill; columns `centerpiece_id`, `shape_bucket`, `package_value`, `declined_at`,
  `expires_at` (+`fatigue_decline_suppress_days`, 30), `retested_at` / `retest_trade_hash`,
  `lifted_at` (user undo ⇒ permanently inert). Near-duplicate match = same centerpiece + same shape
  bucket + package value within ±`fatigue_decline_value_band` (10%) (`_row_matches`,
  `server.py:4598-4604`). Written ONLY from the match-decision route on `decision == 'decline'` —
  including the mirrored write for a partner whose accepted proposal was killed
  (`server.py:15391-15411`) — via `_save_decline_suppression` (`server.py:4675-4697`). **Dismisses
  never write here** (D-067 Context: 0 rows in prod as of 2026-08-17). Applied by
  `_apply_deck_suppression` (`server.py:4544-4672`) in the worker at `server.py:5794` — removes
  near-duplicates from the *generated* deck (post-gen, pre-serve), grants exactly ONE low-exposure
  retest card after expiry (`retest_mult` 0.5), lazily re-arms the window if the retest is passed
  (`server.py:4575-4596` — the swipe path stays write-free), never shrinks the deck below
  `_DECK_MIN_CARDS` = 5 (`server.py:4651-4663`), and never suppresses `likes_you` cards
  (`server.py:4621`).
- **"Refresh my deck" reset** affects soft fatigue only; decline suppressions and
  not-interested/untouchables are unaffected (`database.py:796-798`).

### 2b. R4 windowless exclusion + already-swiped dedup (GENERATION-time)

Two distinct key-sets, filtered at the same seam:

- **R4 (#336)** — built once per job by `_load_presentment_exclusions` (`server.py:5358-5385`):
  `(frozenset(my_give), frozenset(my_receive))` keys from (a) un-retracted awaiting likes in this
  league (no time window) and (b) `pending`/`accepted` `trade_matches` rows via
  `load_matches_for_exclusion` (`database.py:8070-8098` — `declined` rows deliberately do NOT block,
  Q-G6-2). Built under `FLAGS.trade_presentment_rules` at `server.py:5498-5505`, passed into
  `generate_trades` (`server.py:5758`), stored per call as `TradeService._exclusion_keys`
  (`trade_service.py:3983`), enforced in `_dedup_and_sort` (`trade_service.py:4189-4202`) — which runs
  both on streaming snapshots and final assembly. **No knob exists**; the only bypass is bake-off arm
  A's thread-local `r4_bypass()` (`trade_service.py:1014-1037`). The likes-you injector honors the
  same set (`server.py:3294-3310`) and gen_v2 receives it merged into `past_decision_keys`
  (`trade_service.py:4029-4031`).
- **Already-swiped dedup** — `past_decision_keys`, loaded once per `session_init` from
  `trade_decisions` (`server.py:17173-17232`) and injected into every `TradeService` constructor
  (`server.py:17232`, `trade_service.py:3849-3857`). Same exact-pair key; filtered in
  `_dedup_and_sort` (`trade_service.py:4192-4196`) and never bypassed, even by arm A
  (`trade_service.py:1030-1031`).

### 2c. `trade_matches.user_a_dismissed` / `user_b_dismissed`

`database.py:429-435`, writer `dismiss_match` (`database.py:8336-8366`). **Generation does not consult
these flags anywhere.** They are a per-user inbox archive: `load_matches` filters the caller's own
flag (`database.py:8011-8017`), the counts helper mirrors it (`database.py:7001-7019`), and dismissing
carries no Elo signal (`database.py:8346-8348`). The generation-side match exclusion is R4's
status-based read above, which ignores dismissal. (The brief's phrasing "where generation honors it"
presumes a link that does not exist — see Corrections.)

### 2d. Dismiss cooldown (D-067, shipped 2026-08-17/18)

What shipped (`living-memory/DECISIONS.md` § D-067; plan `docs/plans/pass-cooldown/plan.md`):
1. A dismiss ("pass") is a **hard exact-pair exclusion for `pass_cooldown_days` (14.0)**, separate
   from likes' 7-day window — implemented in the `session_init` load (`server.py:17176-17223`), knob
   seeded at `database.py:2392` / `trade_service.py:363`.
2. **Immediate in-memory bind at swipe time** to every service in `sess["trade_svcs"]` (not just the
   active-format alias) — `server.py:11671-11694`.
3. **Legacy-dismiss amnesty**: dismisses recorded before `pass_cooldown_start_epoch`
   (2026-08-17T22:30:00Z = decline-reason-capture go-live) are exempt (`server.py:17192-17208`,
   `database.py:2393`).
4. Deliberately exact-pair, NOT near-duplicate ("one swipe must not silence a player's whole trade
   space"), and served-but-unacted cards may re-show (98.5% of the reporting user's repetition was
   unacted impressions: 4,003 impressions vs 61 decisions in 14 days).
5. **Operator principle, recorded and governing:** *"accuracy, not volume. Bad suggestions are worse
   than limited suggestions"* — deck thinning is an accepted cost of exclusion work.
   D-067 Alternatives also records "reading `deck_impressions` back at generation to suppress
   served-but-unacted cards" as **out of scope per the operator** — a fact the new feature's scope
   should cite before re-opening it.

### 2e. Taste vectors F5 (`deck.taste_vectors`, ON) — re-ranking ONLY

`backend/taste_service.py` (all 549 lines read); storage `user_taste` (`database.py:839-845`):
one row per (user, attr), columns `w_short` (τ=21d), `w_long` (τ=180d), `updated_at`. **User-scoped,
not league-scoped — taste follows the manager across leagues, and partner attrs are global user ids**
(`database.py:836-838`).

- **Attr taxonomy** (`taste_service.py:40-52`, derivation 169-235): `shape:{G}x{R}`, `arch:{lane}`,
  `window:aligned|off`, `cpos:{POS}`, `givepos:/recvpos:{POS}`, `giveband:/recvband:{low|mid|high|elite}`,
  `giveage:/recvage:{u23|23-26|27-29|30plus}`, `pick:none|mid|premium`, **`partner:{user_id}`**
  (`taste_service.py:231-233`), plus `prior:`-prefixed board-derived rows (rewritten wholesale on
  board saves by `refresh_board_prior`, `taste_service.py:541-548`; folded into the long vector at
  read, `taste_service.py:390-397`).
- **Decay/update math**: `w ← w·exp(−Δt/τ) + r(action)` on every F1 outcome write
  (`update_taste_from_outcome`, `taste_service.py:314-363`, hooked at `server.py:4373`); rewards
  `like +1.0, propose +6.0, pass −0.5, not_interested −4.0` (+0.3 long-dwell bonus ≥8s,
  `taste_service.py:78-87`, `304-311`); GC below `taste_epsilon` on read and write.
- **Where applied — CRITICAL ANSWER: re-ranking only.** `taste_multipliers`
  (`taste_service.py:429-462`) produces per-card multipliers
  `clamp((1+η_l·cos_long)(1+η_s·cos_short), 0.7, 1.4)`, computed in the worker AFTER the F3
  suppression pass (`server.py:5845-5850`) and folded into `_order_deck`'s ordering key
  (`server.py:3898-3904`). The module docstring is explicit: "taste reorders gate-passing candidates
  only; untouchables, not-interested, outlook filters and the surplus/fairness gates stay
  authoritative upstream" (`taste_service.py:34-38`). It never changes candidate membership and is
  bypassed on bake-off decks.

### 2f. gen_v2 empirical-Bayes acceptance prior — direct layer-2 prior art, currently an UNFED STUB

`backend/trade_gen_v2.py:283-308`:

```python
p = (accepts + m·p0) / (responses + m)      # m = gen2_accept_prior_strength (10.0)
                                            # p0 = gen2_accept_global_prior (0.5)
```

Interface: `acceptance_stats: dict[user_id → (accepts, responses)]`; per-opponent, computed once per
member in the generation loop (`trade_gen_v2.py:951`) and multiplied into every candidate's score
`score = joint_gain × accept_prior × priority_weight` (`trade_gen_v2.py:655`, dataclass field
`trade_gen_v2.py:359-360`). Knobs seeded at `trade_service.py:660-661`.

**The critical finding: no caller ever supplies `acceptance_stats`.** The serving-path call
(`trade_service.py:4001-4033`) and the bake-off arm-C call (`bakeoff_runner.py:1212-1229`) both omit
the kwarg, so it defaults to `None` (`trade_gen_v2.py:862`) and `acceptance_prior` returns exactly
`p0 = 0.5` for every manager — a uniform scale that "leaves ordering untouched"
(`trade_gen_v2.py:295-297`). There is no accept/response aggregation query anywhere in `backend/`
(`git grep acceptance_stats` matches only the module and its tests). The design intent is recorded in
the module: "The narrow dict interface … is deliberate: a learned acceptance model replaces this
function without touching the pipeline" (`trade_gen_v2.py:297-299`). So: the *shape* of layer 2
(per-partner shrunk acceptance rate as a generation-time score multiplier) already exists, ratified,
with knobs — what does not exist is any wiring from `trade_decisions`/`trade_matches`/`deck_outcomes`
into it. Also note `trade_gen.v2` is **OFF** (`config/features.json`); the module runs only as
bake-off arm C (`trade.bakeoff` ON, serving dark — `bakeoff_serve_interleaved` default 0).

### 2g. Thompson sampling F2 (`deck.thompson_v2`, ON)

`server.py:3589-3786`. Arms are **archetype × shape_bucket** where archetype = the card's `lane`
(`_card_archetype`, `server.py:3660-3663`) and shape = `f"{len(give)}x{len(recv)}"`
(`server.py:3544-3547`). Feedback: **viewed-gated like/pass outcomes** from the F1 join
(`load_deck_arm_events`, consumed `server.py:3686-3699` — cards served but never fronted update
nothing), with per-event lazy decay `γ^age_days` (γ=0.995), a 120-day arm-inactivity TTL, warm-start
from the parent shape posterior below 5 raw observations (`server.py:3727-3747`), and a frozen
"legacy seam" of pre-spine `trade_decisions` counted at shape level
(`load_legacy_shape_counts`, `server.py:3701-3718`). Prior is pessimistic Beta(1, 1/p̂) at the trailing
30-day global like rate (`server.py:3622-3643`). Output: one Beta draw per arm per job →
`clamp(draw / prior_mean, 0.5, 1.5)` sort-key multiplier (`server.py:3750-3786`), applied in
`_order_deck` (`server.py:3854-3866`). **POST-generation ordering authority only**; deterministic
per-job seed (`server.py:3536-3541`); v1 (`trade.thompson_deck`, shape-only arms from
`load_trade_decision_shape_counts`) remains as the fallback path (`server.py:3867-3888`).

### 2h. Fit arm post-score filters, and where a shared prior-consultation hook could sit

`backend/trade_gen_fit.py:753-850` (`_apply_post_filters`, order pinned): min_them/min_aggregate
floors → untouchables (`:799`) → not-interested (`:803`) → position pins (`:807`) →
**R4/already-swiped** (`:811-815`, exact-pair `past_decision_keys`, post-score by operator ruling
PRD §6.4) → C4 centerpiece cap (`:818-835`) → max_per_opponent (`:837-849`). The fit arm receives
`past_decision_keys` as an input (`trade_gen_fit.py:267`).

**Candidate insertion points for a generation-time prior, per path** (each is where per-opponent /
per-candidate context and the existing negative-signal inputs are already in hand):

| Path | Anchor | Notes |
|---|---|---|
| v1/v3 serving engine | `trade_service._generate_trades_impl` — per-opponent loop at `trade_service.py:4563` (`for member in opponents:`); exclusion state reset at `:3983-3986`; shared kill-site `_dedup_and_sort` `:4180-4230` | `_past_decision_keys` + `_exclusion_keys` are already instance state consulted here; a prior map loaded once per job (like `exclusion_keys` at `server.py:5498-5505`) could ride the same constructor/kwarg seam (`server.py:17232`, `:5758`) |
| gen_v2 | `generate_league_suggestions` — `acceptance_stats` kwarg (`trade_gen_v2.py:862`) consumed per member at `:951`, multiplied at `:655` | **The hook already exists**; feed it. Both call sites to update: `trade_service.py:4001` and `bakeoff_runner.py:1212` |
| fit arm | `_apply_post_filters` (`trade_gen_fit.py:753`) — add alongside step 5 (`:811`), or upstream in its scorer | Fit is post-score by ruling; a *hard* family exclusion belongs at step 5, a *soft* prior belongs in the rank score |
| presentation (all arms uniformly) | the worker's post-generation stack: suppression `server.py:5794` → fatigue mults `:5804` → taste mults `:5845` → `_order_deck` `:5900` | The one place every serving path already converges. A `prior_mult: dict[id(card) → m]` computed once per job (the `_deck_fatigue_multipliers` pattern: one bulk DB read, per-card dict, `server.py:4482-4541`) composes into `_order_deck`'s existing multiplier stack (`server.py:3894-3904`) with zero per-candidate DB reads. Caveat: this is POST-generation — it down-weights doomed families but cannot stop them consuming generation/enumeration budget, and bake-off decks bypass this stack (`server.py:5885-5895`, D-086 re-ranker contamination rule) |

R4-style *generation* filtering for all four paths already has a uniform seam too: the
`past_decision_keys` kwarg is threaded to v1 (`_dedup_and_sort`), gen_v2
(`trade_service.py:4029-4031`), fit (`trade_gen_fit.py:267`), and the likes-you injector
(`server.py:3292`). A "doomed-family" hard filter that can be expressed as a key-set membership test
inherits all four paths by extending what goes into that set — but note it is exact-pair keyed today;
family semantics (centerpiece+shape+band) exist only in `deck_suppressions`' matcher
(`server.py:4598-4604`).

### Other suppressors to not rebuild

- **Not-interested / untouchables (#163)** — "the authoritative hard filters upstream"
  (`server.py:4399-4400`); enforced in-engine and in the fit arm and the likes-you injector
  (`server.py:3276-3284`).
- **A6 diversity + per-target cap** (`server.py:3906-3933`, `_cap_per_target` `:3560-3586`) and the
  **C4/C4b headliner caps** (`trade_service.py:4206-4230`, `cap_give_headliners`
  `trade_service.py:4043-4044`) — league-level saturation control, POST.
- **D-070 superseded-job gating** — stops orphaned workers writing impressions
  (`living-memory/DECISIONS.md` § D-070) — relevant because it protects the training data.

---

## 3. Trade-shape taxonomy today (inventory for sharing with the Receipts sibling)

One canonical *shape* definition, several *labels* riding beside it:

| Notion | Definition | Where |
|---|---|---|
| `shape_bucket` / `shape` | `f"{len(give)}x{len(receive)}"` — "1x1", "2x1", … | `server._card_shape` (`server.py:3544-3547`); `deck_impressions.shape_bucket` (`database.py:512`); `deck_suppressions.shape_bucket` (`database.py:780`, written as the same f-string `server.py:4693`); taste attr `shape:{G}x{R}` (`taste_service.py:178`); Thompson v1 bucket (`server.py:3397-3404`) and v2 arm dimension |
| `_LEGAL_SHAPES` | frozenset of every (n_give, n_recv) in 1–3 × 1–3 | `trade_gen_fit.py:45-49`, gate `_k1_shape_ok` `:154-156`; gen_v2 independently bounds "max 3 assets+picks per side" (`config/features.json` `_comment_trade_gen_v2`) |
| `basis` | `'divergence' \| 'consensus'` — how the card was generated | `TradeCard.basis` (`trade_service.py:3655`); `trade_impressions.basis` (`database.py:466`); frozen into `features_json` (`server.py:4138`); bake-off group axis (`database.py:566-592`) |
| `lane` | `'window' \| 'value' \| None` — deck lane from the user's resolved window | `TradeCard.lane` (`trade_service.py:3690-3693`); stamped by `classify_lane` late in `_generate_trades_impl`; IS the `archetype` column (`server.py:4230`, `database.py:511`) and the Thompson/exploration/fatigue archetype key (`server.py:3660-3663`) |
| `archetype` | today literally = lane; F7 auditions are keyed per archetype label globally | `archetype_auditions` (`database.py:847-870`) |
| MESO package-shape classes | `classify_package_shape` — rationale vocabulary for gen_v2 return-package variants | `trade_gen_v2.py:311-315` |
| `signed_lane_shift` | signed toward/away-from-window scalar per card (D-060) | `TradeCard` comment `trade_service.py:3695-3703`; swipe-K weighting `server.py:11620-11632` |
| Analytics | no separate shape enum — events reuse `shape` from features_json; `trade_narrative.py` carries **no** shape taxonomy (grep "shape" = 0 hits) | — |

Recommendation the designers can lift directly: the shared taxonomy already exists as the triple
**(shape_bucket, basis/lane, centerpiece)** — it is what F3 suppression matches on
(centerpiece+shape+value-band, `server.py:4598-4604`), what Thompson arms learn over
(archetype×shape), and what F5 encodes as attrs. Any new "trade family" definition that is not
expressible in these terms creates a fourth vocabulary.

Centerpiece has exactly one definition, shared on purpose: `trade_service.deck_centerpiece`
(delegated by `server._fatigue_centerpiece`, `server.py:4405-4412` — "one definition, so the cap and
the metric … cannot drift apart"; F5 mirrors it at `taste_service.py:190-192`).

---

## 4. Value/outcome history (context only — sibling owns it)

- **`elo_history`** (`database.py:1264-1283`): append-only per (user, league, player, format,
  snapshot_at); written on every `save_ranking_swipes` for players whose Elo actually changed — no
  cron (`database.py:1266-1272`; writer `database.py:10699-10733`).
- **`player_value_history`** (`database.py:1285-1311`): one row per universal-pool player per format
  per **day** — consensus `consensus_elo` + denormalized `consensus_value` + `search_rank`/`adp`,
  unique on (player_id, format, snapshot_date); written by `POST /api/cron/value-snapshot`
  (`database.py:1289-1296`). D-096's prod reconstruction used exactly this table plus
  `draft_picks.pool_value` (DECISIONS D-096 Context).
- Adjacent: `league_roster_history` (ownership side, ADR-011, `database.py:1314+`) and
  `sleeper_trades` (raw executed league trades, `database.py:1370-1396` region — capture-only,
  idempotent on transaction_id).

## 5. Analytics taxonomy — registering a new "memory" event

`backend/analytics_taxonomy.py` is "single source of truth for event names" (`:1-24`). A new event is
either added to `ALLOWED_CLIENT_EVENTS` (`:38`, client-fired; default-deny at `POST /api/events`;
"new client event types require a tracking-plan addendum first") or `SERVER_FIRED_EVENTS` (`:505`,
server-authoritative via `database.record_event`; the namespaces must stay disjoint — import-time
invariant `:22-24`). CLAUDE.md's standing rule (root CLAUDE.md, Common tasks): register in
`analytics_taxonomy.py` **and** classify in `analytics_queries.NON_INTENT_EVENTS`
(`analytics_queries.py:63-…`; `INTENT_EVENTS` is the complement, `:255`) **in the same commit as the
emitter** — intent is a deny-list, so an unclassified impression-class event silently inflates
DAU/retention (`analytics_queries.py:66-73`). Concrete precedent to copy: the decline-reason events —
`trade_pass_layer2.detail` widened 8 → 10 values with "emitter untouched, NON_INTENT_EVENTS unchanged"
(`living-memory/CHANGELOG.md:340`) and free text is never a property (`database.py:903-905`).

## 6. Cron surface

`render.yaml` defines the web service + **three cron services** (`render.yaml:36-76`):
`notif-realtime-tick` (*/15 min → `POST /api/cron/realtime-tick`), `notif-hourly-tick` (hourly →
`/api/cron/hourly-tick`), `notif-daily-tick` (13:30 UTC → `/api/cron/daily-tick`). All authenticate
with `X-Cron-Secret` = `CRON_SECRET` (`_require_cron_auth`, fails closed in prod —
`backend/CLAUDE.md` § Adding a route). A new recurring job should ride an existing tick, exactly as
F10 replenishment does: it "runs INSIDE /api/cron/daily-tick (no new external schedule)"
(`server.py:18344-18357`), with a weekday `>=` gate so a missed day self-heals
(`server.py:18560-18566`) and the **`deck_replenish_log` unique constraint as the idempotency gate** —
`UniqueConstraint(user_id, league_id, iso_week)` (`database.py:812-822`), checked via
`replenish_week_done` (`database.py:5473`) before work and marked via `log_deck_replenish`
(`database.py:5487`) **before** the push ("a marker-without-push beats a push-without-marker",
`server.py:18586-18590`). Push dedup backstop: `dedup_key = f"{league_id}:{iso_week}"`
(`server.py:17982-17984`, `18622`). ISO-week helper shape is also mirrored in `database.py:1372`.

## 7. Privacy-relevant facts — what exists about NON-app-user league-mates

The engine already models every league-mate, installed or not:

- **`league_members`** (`database.py:340-349`): every member of every synced league — platform
  `user_id`, `username`, `display_name`, full `roster_data` JSON — regardless of app installation.
- **`member_rankings`** (`database.py:395-403`): personal boards. Written only by app users' board
  saves (replace-atomically; the "prior" refresh hook lists the writers, `server.py:4702-4708`).
  **Non-users have no rows** — they are exactly the opponents served by the consensus `basis` path
  (`TradeCard.basis` comment `trade_service.py:3650-3655`).
- **`trade_decisions` / likes** — only app users generate them; `load_recent_league_likes` (the
  likes-you injector, `server.py:3239-3241`) therefore only ever reflects installed managers.
- **`sleeper_trades`** (`database.py:1370-1396` region): raw executed trades of the WHOLE league,
  including non-users — the one behavioral record that covers everyone. `suggestion_trade_links`
  (`database.py:657-671`) ties them back to served/ghost suggestions.
- **`trade_block`** (`database.py:360-369`): any manager's on-the-block flags from Sleeper, non-users
  included.
- **Already-shipped precedent for per-manager preference modeling:** `user_taste`'s
  `partner:{user_id}` attribute — an app user's learned affinity for trading with a *specific named
  league-mate*, stored under the app user but keyed by the partner's **global** user id
  (`taste_service.py:231-233`, `database.py:836-838`). And gen_v2's `acceptance_prior(user_id, …)` is
  explicitly per-manager P(responds positively) (`trade_gen_v2.py:287`). So layer 2 ("inferred
  acceptance tendencies of other managers") extends an existing pattern rather than introducing the
  first non-user modeling — but the PRD must still flag it: a *dedicated table of inferred tendencies
  per league-mate* is a step beyond attrs buried in one user's taste vector, and `accounts.
  delete_user_data` (`backend/CLAUDE.md` module map) currently has no reason to touch rows keyed by a
  *partner's* id.

## 8. Data volumes (committed docs only — no prod queries run)

| Fact | Value | Source |
|---|---|---|
| Trade decisions, prod, 2026-08-17 | 810 (496 pass / 314 like); 61% already outside the old 7-day window | DECISIONS D-067 Context |
| Recorded like/pass outcomes, 2026-08-19 | 845 | TEST_LEDGER.md:688-690 (§ 2026-08-19 pick-horizon) |
| Served cards (impressions with outcomes measurable), 2026-08-19 | 2,651; 339 phantom-pick (12.8%) | DECISIONS D-091; CHANGELOG.md:242 |
| One user's 14-day slice | 4,003 impressions vs 61 decisions (98.5% of repetition = unacted) | DECISIONS D-067 (4) |
| `deck_suppressions` rows in prod, 2026-08-17 | **0** — the hard decline path had never fired | DECISIONS D-067 Context |
| Likes-you slice, one league, 08-11→08-19 | 198 served impressions / 51 distinct cards | DECISIONS D-096 Context |
| Tester decision supply | ~400 decided cards/week | DECISIONS.md:1074 (bake-off arm-budget ruling) |
| Pass-reason "Neither" share, first burst | 47% | database.py:898-900 |
| Comparisons with both sides pinned | 67.8% of 4,013 | DECISIONS D-069 Context |
| G6 presentment kill rate | 18.4% | DECISIONS D-067 Consequences |
| Contaminated window | 2026-08-16 → 08-19 (42.4% of one audit's 8,617 rows) | D-091; docs/reviews/2026-08-19-armb-audit-claim-7.md:303 |

Implication: per-(partner × shape × reason) cells will be nearly all empty at today's volume —
empirical-Bayes shrinkage toward pooled priors (exactly the gen_v2 form) is not optional.

---

## Corrections to the brief

1. **The gen_v2 acceptance prior exists but is a stub with no data source.** The brief says "the
   flags comment claims it exists — find it, document its math … and whether it models per-partner
   tendencies." The function and math exist (`trade_gen_v2.py:283-308`) and are multiplied into every
   candidate score (`:655`), but **no production caller passes `acceptance_stats`**
   (`trade_service.py:4001-4033`, `bakeoff_runner.py:1212-1229`), so it returns the global prior 0.5
   uniformly and models nothing per-partner today. It is prior art as an *interface and ratified
   math*, not as a working system. Also `trade_gen.v2` is OFF; the module runs only as bake-off arm C
   (dark).
2. **`trade_matches.user_{a,b}_dismissed` is never honored by generation.** It is an inbox-archive
   flag only (`database.py:8011-8017`, `8336-8366`). Generation's match exclusion is R4's
   status-based read (`pending`/`accepted` only, dismissal-blind — `database.py:8070-8098`).
3. **"Already-swiped dedup" is windowed, not permanent.** Since D-067: pass = 14d, like = 7d, plus
   the pre-2026-08-17T22:30Z dismiss amnesty (`server.py:17182-17223`). Only R4's awaiting/matched
   keys are windowless. A "doomed forever" mental model of the current dedup is wrong.
4. **"Deck fatigue F3 (deck_suppressions … )" conflates the two F3 layers.** `deck_suppressions`
   holds only **decline/proposal-kill** windows (0 rows in prod as of 2026-08-17); ordinary dismisses
   never reach it. Soft pass-fatigue is derived on read, not stored (`database.py:771-774`).
5. **Thompson arms**: correct as stated (archetype×shape), with the caveat that "archetype" is
   literally `lane` today (`server.py:3660-3663`) — a two-value axis (`window`/`value`/None), so the
   arm space is much coarser than the word "archetype" suggests.
6. **`58 tables in database.py` (root CLAUDE.md) is stale** — `backend/CLAUDE.md` says 63; either
   way, count from the file, not the brief.
7. **D-096 and D-090 status lines in DECISIONS.md say "not pushed and not merged", but both are in
   this checkout** (`likes_you_gate_level` ladder at `server.py:3223-3233` / `3330-3339`;
   `pick_slots.py` exists). The decision log's status fields lag the merges — verify against code.

---

## Design constraints that fall out of the code

1. **No per-candidate DB reads at generation.** Every existing learner follows one of two patterns:
   (a) a **key-set built once per job** and tested by membership in the enumeration/dedup path
   (`past_decision_keys` / `exclusion_keys` — `server.py:5498-5505`, `trade_service.py:4189-4202`), or
   (b) a **per-card multiplier dict computed once per job** from one bulk read
   (`_deck_fatigue_multipliers` `server.py:4482-4541`, `taste_multipliers`
   `taste_service.py:429-462`, `_thompson_v2_arm_stats` `server.py:3666-3724`). A generation-time
   prior must be loadable as one map per (user, league) job — e.g. keyed by (partner, shape_bucket,
   centerpiece-or-reason-family) — and consulted in-memory inside the per-opponent loops
   (`trade_service.py:4563`, `trade_gen_v2.py:939-975`).
2. **Derive-on-read is the house style for learned state; stored state is for durable promises.**
   Soft fatigue and Thompson arm posteriors are recomputed from the event spine at read time — "no
   cron mutates stored state" (`server.py:3599-3612`); only user-facing commitments
   (`deck_suppressions`, `deck_replenish_log`) get tables. A negative-results memory that can be
   derived from `trade_decisions` + `trade_pass_reasons` + `deck_impressions⨝deck_outcomes` at job
   start needs no new state table at current volumes (≤ thousands of rows per user-league); if a
   materialized table is chosen anyway, the reason must be latency-measured, not assumed.
3. **Respect the layer contract: gates decide membership, priors decide order — and say which layer
   each memory effect lives in.** Everything soft is clamped and applied AFTER all generation gates
   ("a fatigued card can sink, never rise, and no gated card is ever rescued," `server.py:4388-4390`;
   taste "reorders gate-passing candidates only," `taste_service.py:34-38`). A generation-time prior
   that *down-weights* is new territory only in location, not in kind — gen_v2's `accept_prior`
   multiplier at `trade_gen_v2.py:655` is the precedent — but a prior that *excludes* must be
   expressed through the existing key-set seam or it will be the fourth overlapping hard filter.
4. **Exact-pair vs family semantics are a recorded operator line.** D-067 deliberately kept dismisses
   exact-pair ("one swipe would silence a player's whole trade space") and put
   "reading deck_impressions back at generation to suppress served-but-unacted cards" out of scope.
   A family-level prior is exactly the territory D-067's alternatives rejected *as a hard filter* —
   which is the strongest argument that the new feature should be a **soft prior with knobs**, not
   another exclusion, and its scope block should cite D-067's operator principle (accuracy over
   volume) and get an explicit ruling on family-level semantics.
5. **The reason taxonomy already routes consequences — extend that routing, don't parallel it.**
   `elo_signal_at` + `pass_reason_elo_suppression` already make the *reason* decide the Elo
   consequence (`database.py:910-914`). `other_player_avoid` / `other_player_keep` /
   `fit_duplicate` / `value_giving` are precisely the "rejection reason" dimension the memory wants —
   and they only exist since 2026-08-17, only on 'impression'-keyed rows joinable to features
   (`key_source`, `database.py:915-923`).
6. **Training-data hygiene is pre-solved — use the existing markers.** Serve-time-frozen
   `features_json`, viewed-gating (only fronted cards count — `server.py:3601-3603`), ghost rows
   excluded naturally (`database.py:522-527`), superseded jobs write nothing (D-070), bake-off decks
   bypass re-rankers and record `policy_version`/`model_arm` for attribution, and the D-091
   contamination window (2026-08-16→08-19) must be excluded or down-weighted by timestamp.
7. **A prior consulted at ordering time must respect the bake-off bypass.** Any new post-generation
   layer must consult `bypass_rerankers()` (`living-memory/LLD.md:266`); a new swipe-path Elo write
   must apply `elo_freeze_mult()` — both are structurally tested. A *generation-time* prior sidesteps
   this but then changes arm behavior — it becomes part of the model under test and needs its own
   config knob snapshotted via `bakeoff_runs.config_json` (`database.py:722-728`).
8. **User-scoped vs league-scoped identity.** Taste is user-scoped by design (follows the manager
   across leagues, `database.py:836-838`); suppressions and decisions are (user, league)-scoped.
   Layer-2 partner tendencies are league-mate facts keyed by **league identity**
   (`_league_user_id`, `backend/CLAUDE.md` § Identity) — mixing account ids in will recreate the bug
   class `sleeper_roster.py` exists to prevent.
9. **Every knob's disable value must be byte-identical to prior behavior** — the D-074/D-069/D-096
   house rule (model_config knob, golden-tested revert; `likes_you_gate_level = 0` restores pre-D-096
   in one value). Schema + flag surface changes cross CLAUDE.md's express-lane bright line: full
   gates.
10. **Feed the existing hook first.** The cheapest credible v1 of layer 2 is an aggregation query
    (accepts, responses) per league-mate — from `trade_matches` decisions and/or awaiting-like
    response behavior — passed as `acceptance_stats` into the two existing gen_v2 call sites. It
    requires zero schema, zero new math, and its knobs (`gen2_accept_prior_strength/global_prior`)
    are already seeded and documented.

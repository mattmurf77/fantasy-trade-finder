# Trade Disposition Review — Per-Arm Acceptance, Decline Reasons, Accuracy Signals

## Question & context

Operator asked: for each model currently serving trades, what is the acceptance
rate, what decline-reason trends show up, and what else matters for trade
accuracy? This feeds the three-model bake-off read (docs/plans/three-model-bakeoff/)
— i.e., which arm(s) earn more deck share and where generation quality should
be tuned next.

## Data sources & freshness

- **Prod Postgres (Render), read-only**, via `DATABASE_URL_PROD` from
  `secrets.local.env`, queried **2026-08-29**. Data current through the same
  day (`deck_impressions` max `served_at` 2026-08-29T20:33Z).
- The local SQLite copy (`data/trade_finder.db`, dated 2026-08-26) holds **zero
  rows** in `deck_impressions` / `deck_outcomes` / `trade_pass_reasons` /
  `bakeoff_runs` — it is a dev shell, unusable for this question. Everything
  below is prod-measured.
- Serving posture at query time (`model_config`): `bakeoff_serve_interleaved=1`;
  rostered arms **current**, **challenger**, **gen_v2**
  (`bakeoff_include_baseline=0`, `bakeoff_include_fit=0`, `bakeoff_serve_fit=0`,
  `ghost_holdout_one_in=0`, composition layer off via `bakeoff_group_size=0`).
  Challenger and gen_v2 first served 2026-08-21, so the clean 3-arm comparison
  window is **2026-08-21 → 2026-08-29**.

## Findings (measured)

### 1. Acceptance rate per arm (3-arm window, 2026-08-21+)

Decided = distinct cards with a `like` or `pass` outcome (non-ghost,
arm-stamped). **N = 5 deciding users** — treat every percentage below as a
small-N direction, not a verdict.

| Arm | Likes | Passes | Decided | Like rate |
|---|---|---|---|---|
| current | 16 | 17 | 33 | **48%** |
| challenger | 33 | 41 | 74 | **45%** |
| gen_v2 | 19 | 28 | 47 | **40%** |

```sql
SELECT di.model_arm,
       COUNT(DISTINCT di.impression_id) FILTER (WHERE o.action='like')  AS likes,
       COUNT(DISTINCT di.impression_id) FILTER (WHERE o.action='pass')  AS passes
FROM deck_impressions di
JOIN deck_outcomes o ON o.impression_id = di.impression_id
WHERE COALESCE(di.is_ghost,0)=0 AND di.model_arm IS NOT NULL
  AND di.served_at >= '2026-08-21'
GROUP BY di.model_arm;
```

Full bake-off window (2026-08-19+) shifts current to 34/118 = 29%: its
2026-08-19→20 pre-roster-change slice was 18 likes / 67 passes (21%). Window
choice changes current's story more than any arm gap does.

Concentration: challenger's numbers are 69% one user (51 of 74 decided by
user `3135…9408`); gen_v2 splits into one user liking 13 of 25 and another
liking 0 of 12. `entry:espn:…` (an ESPN entry identity) decided 1 card.

### 2. Decline-reason trends per arm

`trade_pass_reasons` joined to arm-stamped impressions (`key_source='impression'`
only), all-time; N = 123 joinable reason rows.

| Arm | Top reasons | Reads as |
|---|---|---|
| current (72) | fit 40 (fit_outlook **31**), value 25 (value_giving 23) | "this trade misreads my roster direction" — but the fit rows come from only **2 users** |
| challenger (36) | value 18 (value_giving **17**), fit 11 (fit_new_weakness, 1 user), other 7 (player_keep/avoid) | "you're asking me to give up too much" |
| gen_v2 (15) | value_giving **10**, fit_outlook 4 | same give-side complaint |

Cross-arm: **`value_giving` is the single most common structured decline
(50 of 123)** — the consistent complaint is the *give* side being priced too
aggressively, not the receive side (`value_getting` is 2 rows total). Current
is the outlier with a fit_outlook skew.

```sql
SELECT di.model_arm, r.reason, COALESCE(r.detail,'(layer-1 only)') AS detail, COUNT(*)
FROM trade_pass_reasons r
JOIN deck_impressions di ON di.impression_id = r.impression_id
WHERE r.key_source='impression' AND di.model_arm IS NOT NULL
GROUP BY 1,2,3 ORDER BY 1,4 DESC;
```

Reason-capture coverage: 347 reason rows total, but **135 (39%) are
`key_source='local'`** — recorded with no impression key, so no card features
and no arm attribution behind them. Another 89 join to NULL-arm impressions
(pre-bake-off / injected cards). Only 123/347 are usable for per-arm work.

### 3. Proposal attribution is broken (biggest accuracy gap)

- `user_events` has **92 `trade_proposed` events by 6 users since 2026-08-21**
  (463 lifetime, latest 2026-08-28).
- `deck_outcomes` has **zero `propose` rows, ever** — for any arm, any window.

The propose write in `backend/server.py` (`_save_deck_outcome_safe(..., "propose")`
at :16274 and :28236) only fires when the client sends `impression_id`, and
`trade_proposed` events carry no `source` prop either. So the bake-off's
strongest positive label — *the user actually sent this trade* — currently
credits no arm. Likes are the only per-arm currency, and likes are cheap.

### 4. Duplicate pass writes inflate row-count metrics

120 of 410 passed impressions carry 2–3 `pass` rows (e.g. challenger: 68 rows
over 41 cards). Sampled duplicates land 20–90 ms apart — one row without
`dwell_ms`, one with — and 110 of the 120 have a decline-reason row: the
✕-reason layer-1 tap and the swipe handler are **both** writing the pass
disposition. Elo is safe (`trade_pass_reasons.elo_signal_at` claims once), but
any analysis counting rows instead of `DISTINCT impression_id` overstates
passes ~30%. All measured numbers above use distinct impressions.

### 5. gen_v2 is supply-constrained

`bakeoff_runs` since 2026-08-21 (219–221 runs/arm): gen_v2 produced 1,952 cards
vs challenger 4,941 / current 4,998, went **empty in 58 of 219 runs (26%)** and
forfeited 2,432 rotation slots (challenger 704, current 419). It is also ~10×
cheaper to run (avg 217 ms vs ~2.1–2.4 s). Zero error runs for any arm.

### 6. Secondary accuracy signals

- **Within-arm ordering is directionally valid:** liked cards sit at better
  own-arm rank than passed cards in all three arms (challenger 3.7 vs 4.4,
  current 7.9 vs 9.5, gen_v2 2.9 vs 4.0 avg `arm_rank`).
- **Dwell:** median decided-card dwell ~8–9 s on challenger/gen_v2 cards vs
  ~5.2 s on current — testers deliberate longer over the newer arms' cards.
- **Executed-trade reality check:** of 174 real Sleeper trades examined by the
  matcher (`suggestion_trade_links`), only **2 were even partial matches** to a
  rendered suggestion. Recommendations are not yet shaping (or predicting)
  real league trades.
- **Mutual-match dispositions** (`trade_matches`): 15 lifetime — 3 accepted,
  2 declined, 10 pending. Too small to cut by anything.
- Elo mechanics note: fit- and other-reason passes *always* suppress the Elo
  signal (120/120 and 47/47), value passes mostly carry it (155/180) — per
  SPEC §4 design, so pass-Elo learns almost exclusively from value declines.

### 7. Follow-up cuts: user×arm, deck position, player position, age

All cuts below: 3-arm window (2026-08-21+), distinct decided cards
(like|pass), non-ghost, arm-stamped. Age/position tags come from
`features_json.taste_attrs` (`cpos:`, `giveage:`, `recvage:` buckets); a card
can carry several age tags, so age rows overlap.

**User × arm** (likes/decided, top decline reason):

| User | current | challenger | gen_v2 | Their complaint |
|---|---|---|---|---|
| `3135…9408` | 10/21 (48%) | 22/51 (43%) | 6/9 (67%) | varies by arm: value_giving / fit_new_weakness / player_keep |
| `4795…0624` | 5/11 (45%) | 8/15 (53%) | 13/25 (52%) | value_giving on every arm |
| `8679…7504` | — | 3/7 (43%) | **0/12 (0%)** | no reasons captured |
| `8678…6480` | — | 0/1 | 0/1 | value_giving |
| `entry:espn:…` | 1/1 | — | — | — |

gen_v2 is the polarizing arm: 67% and 52% for two users, 0% for the other two.
No user shows arm loyalty; the same user declines different arms for different
reasons.

**Deck position** (pooled): 0–4 → 48% (n=60), 5–9 → 42% (n=31), 10–19 → 47%
(n=36), 20+ → 33% (n=27). Only a mild tail decay. Per arm, gen_v2 collapses
past card 10 (56/50/20/31%) — its likable cards are its top-ranked ones —
while challenger oddly peaks at 10–19 (61%).

**Centerpiece position** (`cpos:`):

- QB-centered cards: 2/12 liked pooled — 0/6 on current+challenger. QB
  centerpieces are near-auto-declines.
- PICK-centered: 2/11 (18%).
- RB: current 12/17 (**71%**) vs challenger 11/29 (38%).
- WR: challenger 17/30 (**57%**) vs current 2/6 (33%), gen_v2 9/24 (38%).
- TE: 40–67% everywhere (n≤9 per arm).

**Age buckets** (pooled; overlapping tags):

| Bucket | Receive-side like rate | Give-side like rate |
|---|---|---|
| u23 | 18/37 (49%) | **1/11 (9%)** |
| 23–26 | 41/93 (44%) | 36/89 (40%) |
| 27–29 | 9/22 (41%) | 17/44 (39%) |
| 30+ | **2/14 (14%)** | **22/38 (58%)** |

Monotone age story on both sides: testers accept cards that *hand them youth
and ship out age*, and reject the mirror image — receiving a 30+ player runs
14%, giving up a u23 player runs 9%. Challenger served 4 cards receiving 30+
(0 liked); gen_v2's best pocket is u23-receive (9/15, 60%).

## Interpretation (labeled as such)

- No arm separates on like rate at this N (40–48%, 5 deciders). The honest
  read is "no winner yet," not "current leads."
- The decline reasons are more decisive than the rates: the dominant fixable
  signal is **give-side over-ask** (`value_giving` everywhere), and for the
  current arm specifically an **outlook/fit mismatch** concentrated in 2 users
  — worth checking whether those two users' window/outlook settings are being
  read correctly before tuning the model.
- gen_v2's 40% like rate on 26% empty runs suggests it's a decent *ranker* of
  the few things it generates but can't carry a deck; its role may be a
  contributor lane, not a full arm.
- Until propose attribution is fixed, the bake-off cannot measure what it was
  built to measure; that fix is cheap (send `impression_id` on the propose
  call) and unblocks the strongest label retroactively going forward.

## Gaps & caveats

- 5 deciders, 154 decided cards in the clean window — every cut is beta-scale.
- 39% of decline reasons are `key_source='local'` (client sent no impression
  id) — arm-attributable reason data is thinner than reason data overall.
- `trade_proposed` events carry no `source` prop → can't tell deck vs
  calculator proposals.
- Window confound: current served alone pre-2026-08-21 with a much lower like
  rate; deck mix, users active, and roster all changed at once that day.
- Ghosting is off (`ghost_holdout_one_in=0`), so no incrementality read exists
  for this window.

## Decisions needed

1. Fix propose attribution (client sends `impression_id`; add `source` prop to
   `trade_proposed`) — instrumentation ask routed to an-data-architect.
2. Dedupe the double pass write (✕-reason tap + swipe handler) — eng fix.
3. Whether to act on `value_giving` (give-side pricing) now or wait for more N.
4. gen_v2's roster status given the 26% empty-run rate.

## Handoffs

- an-data-architect: propose-attribution + `source` prop + `key_source='local'`
  rate (39%) as instrumentation asks.
- eng-backend / `/feedback` pipeline: duplicate pass-row write.
- an-experiment: window/confound handling for the bake-off readout.

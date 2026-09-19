# Arm-B engine audit — consolidated findings (2026-08-19)

> **Status:** point-in-time audit snapshot, not reference. Per [`docs/reviews/CLAUDE.md`](CLAUDE.md),
> read for context; the code and `docs/api-reference.md` are truth. **No engine line was changed by
> any of this work** — all seven source memos are read-only analyses.
>
> **Scope:** arm B, the live engine at live defaults (`TradeService._generate_trades_impl`,
> `backend/trade_service.py:3107`). Arm C (`trade_gen_v2.py`) is out of scope; its flag is off.

---

## Table of Contents
- [What was audited and how](#what-was-audited-and-how)
- [The headline](#the-headline)
- [Verdict summary](#verdict-summary)
- [Confirmed — the real findings](#confirmed--the-real-findings)
- [Refuted — where the reviews are wrong](#refuted--where-the-reviews-are-wrong)
- [Bugs neither review found](#bugs-neither-review-found)
- [What actually moves the number](#what-actually-moves-the-number)
- [Recommended order](#recommended-order)
- [Warnings for whoever implements](#warnings-for-whoever-implements)
- [Source memos](#source-memos)

---

## What was audited and how

Two external reviews of the arm-B trade engine, validated by **seven independent agents** that were
forbidden from changing engine code:

- **Round 1** — seven factual claims about how arm B behaves.
- **Round 2** — fifteen remediation proposals, bucketed by the reviewer into *dualize* (A),
  *drop or invert* (B), and *keep viewer-centric* (C).

Every verdict required: **file:line on `origin/main`**, the **live knob/flag value** (behaviour here is
knob-driven, so a gate that exists but is disabled is a different finding from one that fires), and
**prod measurement** where the claim was empirical. Round-2 agents were additionally required to judge
whether each proposed *remedy would work*, not merely whether its premise was true.

The strongest evidence came from a **replay harness**: six real production boards run through the real
`RankingService.replay_from_db` and `_generate_trades_impl` with live flags and prod `model_config`,
measuring how often the same 1-for-1 exists in only one orientation.

**Resolution caveat, stated by the agents themselves:** six boards / 15 pairs / unions of 30–241.
Deltas ≥5pp are directionally trustworthy; anything moving <3pp should read as "did not move it,"
not as a signed effect.

---

## The headline

**96.3% of 1-for-1 trades exist in only one direction** — they appear for one manager and not the
other, on the live untargeted path.

| Configuration | One-orientation-only |
|---|---|
| **Live (untargeted, R5 active)** | **96.3%** |
| Live (targeted path, `bypass_need_gate`) | 86.9% |
| Symmetric-pricing control (both boards raw) | 63.2% |

And on the consensus path — **84.5% of all served cards** — the user pays on **0 of 7,094** own-deck
cards. Not a tilt: an invariant.

Outlook is not the driver (86.7% holding it equal). The driver is that the two boards are priced by
different functions.

---

## Verdict summary

### Round 1 — factual claims

| # | Claim | Verdict |
|---|---|---|
| 1 | Consensus cards force the user to win | **CONFIRMED** — and understated |
| 2 | Raw 1-for-1 gain gate is user-only | **CONFIRMED** |
| 3 | R5 need gate is a hard user-receive filter | **CONFIRMED** (kill matrix PARTIAL) |
| 4 | User Elo shrunk + clamped, partner raw | **CONFIRMED** — measured |
| 5 | Picks are one number on both boards | **CONFIRMED** — plus a stronger corollary |
| 6 | "Fairness" is consensus, not `min(user, partner)` | **MIXED**, headline example REFUTED |
| 7 | Ranking and copy tilt toward the user | **PARTIALLY** — 3 of 6 levers refuted |

### Round 2 — remediation proposals

| Bucket | Row | Premise | Remedy |
|---|---|---|---|
| A | #108 1-for-1 gate | CONFIRMED | dualize **WORSE** (→90.1%) · delete cosmetic |
| A | Elo shrink + clamp | **PARTIALLY** (clamp half wrong) | **delete = biggest lever** (→63.2%) |
| A | Filler `max(you, them)` | **REFUTED** | dualize no-op · delete **WORSE** (→100%) |
| A | Need R5 | CONFIRMED | **SOUND** (96.3→88.7%) |
| A | Outlook ranking | **REFUTED as stated** | measured **byte-identical** |
| A | `fit_premium` | numbers right, framing REFUTED | category error standalone |
| B | Consensus `rv ≥ gv` | CONFIRMED | **delete = WORSE** (exposes 45.4%) |
| B | Aggression `light` | CONFIRMED | **already ships** as `fair` |
| B | #189 relaxation | CONFIRMED | arithmetically **incoherent** |
| B | Range-overlap | PARTIALLY | dualizing inputs fixes nothing |
| C | 5 "safe" overlays | — | **4 of 5 act pre-gate or reach around it** |
| C | `_tier_mult_v2` gray zone | mechanism REFUTED | conclusion **CONFIRMED**, `min()` undefined |

---

## Confirmed — the real findings

**1. The consensus path is structurally one-sided, and it is most of the product.**
`rv - gv < user_gain_epsilon` with ε = **0.0**, plus fairness. No partner surplus test of any kind.
84.5% of traffic. 752 cards (10.6%) have the partner paying more than 25%, median gap 498.
The live fairness threshold is **0.50**, not the 0.75 the reviewer assumed — the mobile default
flipped off 2026-08-17, so the one-sided band is twice as wide as argued.

**2. Dualizing that gate is genuinely impossible, and for the right reason.**
Both packages are priced through the same `seed_value` functional, so user surplus and partner surplus
are exact negatives. Symmetric ε > 0 is unsatisfiable. The fix is board *count*, not gate *shape* —
which is why the divergence path works, and why `trade_gen_v2.py:628-638` already holds a two-board
version, dark.

**3. Partner boards cannot carry confidence.** `LeagueMember` (`trade_service.py:2821`) has five
fields and none is a confidence map. `member_rankings` stores only `elo`. So "shrink the partner using
their comparison counts" is not a config change — the counts do not exist to plumb.

**4. Picks are unprunable.** One `pick_elos` dict is written to the seed map, the user's board, and
every member's board (`server.py:10403-10410`, commented *"user board: consensus for picks"*). The
divergence prune (`trade_service.py:4765-4766`) keeps a candidate when `_vo(p) >= user_value[p] * 0.97`.
For a pick both sides are the same number, so both tests reduce to `x >= 0.97x` — **always true**.
Players get pruned; picks never do. This is a mechanical explanation for pick flooding, independent of
pricing.

**5. R5 kills trades that fill both sides' needs.** No opponent argument exists in `need_gate_ok`.
Across 30 ordered pairs of six boarded members it killed 1,778 shapes, **61 with dual
`need_fit >= 0.75`** — the clearest being a surplus RB sent to a manager whose stated need is
literally `['RB']`.

**6. Zero `1x2` packages exist in production** — 6,635 `1x1`, 459 `2x1`. Partner-favourable
consolidation is unrepresentable, exactly as claimed.

**7. `_tier_mult_v2` sets the stakes.** On consensus, `composite = fairness x tier_mult x 0.30`.
Because the gate forces `rv >= gv`, `1 - fairness` **is** the viewer's surplus fraction — fairness is
the only brake, and being a ratio it is blind to scale. `tier_mult` spans **4.57x** (0.35→1.60) against
fairness's **2.00x**. An elite card outranks a perfectly balanced solid card once its fairness reaches
**0.625 — while taking 60% more than it gives**. Measured: elite-band mean absolute viewer surplus
**790** vs **78** for depth/bench, **10.2x**.

> It does not make the top of the deck more lopsided. It makes it lopsided at several times the stakes.

---

## Refuted — where the reviews are wrong

- **`placement_tier_clamp` is not part of the bias — it reduces it.** Clamp at 1.0 → 86.9% one-sided;
  at 0.0 → **95.3%**. Anyone acting on round 2's bucket-A row would revert the wrong lever.
- **Filler is not one-sided.** `filler_ok` (`:1513-1546`) applies the identical metric to both sides.
  Deleting it measured **86.9% → 100%**.
- **Outlook's stated mechanism is impossible.** `outlook_direction_mult` (`:2331-2409`) takes no
  partner argument, so contender↔contender and contender↔rebuilder receive an identical x1.1325.
  Dualizing it measured **byte-identical**.
- **"fits their timeline" is not shown to anyone.** No client renders the backend `narrative` field —
  the only mentions are a code comment and an unrelated activity feed.
- **`min(user, partner)` already exists**, spelled as a hard surplus floor of 60 running before
  fairness. 1,335 of 1,335 divergence cards clear it.
- **The `abs(tilt)` remedy already ships** — `trade_service.py:4401` is
  `mult = 1.0 - w_ab * abs(tilt)`, the `fair` variant. The ask is "default to `fair`", not build.
- **#189's relaxation is incoherent as criticised** — ε is *already* 0, so relaxing equalises rather
  than tilts. Blast radius: 1 card in 7,721.
- **`min(your_tier_mult, their_tier_mult)` is undefined** — `_generate_consensus_for_pair` receives no
  opponent Elo map at all. On the 15.5% where it is computable it suppresses the highest-divergence
  cards the path exists to find.
- **82.8% `light` is not a bug.** MD5 buckets recomputed for all five prod users; all match. 3 of 5
  hash to `light` and the heaviest user is 68.7% of cards.

---

## Bugs neither review found

| # | Bug | Impact |
|---|---|---|
| 1 | **Likes-you injector bypasses every gate** — no ε, no `user_gain_ok_1for1`, no `filler_ok`, no R1, no fairness threshold. Only floor is `likes_you_min_user_delta` = **−500**, which explicitly permits a loss. Its floor is raw-sum while the displayed value bar is package-adjusted. | **101 of 169 cards have the user paying, worst −6,019**, vs 0 of 6,340 on the gated path |
| 2 | **The app claims a trade is balanced when it is not** — `TradeCard.tsx:453` renders *"this is a balanced trade by consensus value"* gated on `isConsensus` alone, no fairness check. Same string in `web/js/app.js`. | **805 of 7,282 consensus cards (11.1%)** below the app's own bar |
| 3 | **`filler_ok` board-provenance mismatch** — v3's `_uv` reads `shrunk_elo` while its docstring and callsite both claim raw. 200/200 sampled match shrunk, 0/200 raw. The consensus path passes raw. The two paths disagree. | silent inconsistency between generation paths |
| 4 | **`comparison_counts` excludes `decision_type='trade'` rows entirely** — Adams has 36 distinct comparison opponents and counts as **1**, for two independent reasons. | `w` undercounts systematically |
| 5 | **6 of 123 divergence cards served below their own recorded fairness threshold** (0.488 vs a 0.50 floor), none flagged `relaxed`. | gate not holding |
| 6 | **Turning fairness ON at 0.75 only gives you 0.75 for players you have voted on ≥5 times.** Range-overlap is confidence-scaled; below that the effective floor drops. Nothing tells the user. | user-facing surprise |

**Bug 1 also closes round 1's open R1 anomaly.** The 22 served cards where `overpay_ok` failed to fire
are likes-you cards; D-055 sub-decision (5) records that this path gets *"exactly R4 dedup, none of
the quality rules."* It is a decision to revisit, not a leak to chase.

---

## What actually moves the number

Measured on the replay harness. **Only two of the fifteen proposals move it.**

| Change | One-sided |
|---|---|
| Baseline (live, untargeted) | **96.3%** |
| Stop shrinking the user before surplus (bucket A row 2, *delete*) | 86.9 → **63.2%** |
| Soft dual need instead of R5 hard-kill (row 4) | 96.3 → **88.7%** |
| **Both together** | **96.3 → 73.3%** (all shapes 96.6 → 60.8%) |

Everything else is cosmetic or harmful: deleting filler **+13.1pp**, dualizing #108 alone **+3.2pp**,
dropping `fit_premium` **+1.6pp**.

---

## Recommended order

1. **Likes-you injector.** Largest measured user harm, and it reverses a recorded decision (D-055) —
   operator call, not an engineering one.
2. **The false "balanced trade" string.** One-line client fix; the app currently asserts something
   untrue to the user on 11.1% of consensus cards.
3. **Stop shrinking the user before surplus** (or shrink neither). Biggest single lever on the
   asymmetry, and free — twinning is not available, since the partner's counts do not exist.
4. **Make R5 dual or soft.** Second-biggest lever; it is currently killing trades that fill both holes.
5. **Fairness-ON degradation** (bug 6) and the **6 sub-threshold cards** (bug 5).
6. **`tier_mult` on the consensus path.** Not an asymmetry fix — a stakes fix. Fairness cannot see
   scale and `tier_mult` selects for it.
7. **`filler_ok` provenance mismatch** (bug 3) — cheap, and it makes the two paths agree.

**Do not:** delete the consensus `rv >= gv` gate (exposes 45.4% of consensus cards to a 0.50 floor),
delete filler, revert `placement_tier_clamp`, or dualize outlook.

---

## Warnings for whoever implements

- **Import-time binding.** `trade_optimizer.py:62-63` and `trade_gen_v2.py:118-121` bind these
  functions **by value**. An A/B that wraps rather than edits the definition will report "no effect"
  while the original still runs. One audit agent hit exactly this and initially measured a perfect
  no-op on a gate firing 1.17M times.
- **Two paths, different provenance.** Consensus passes raw values; v3 passes shrunk. A change made in
  one place will not behave the same in the other (bug 3).
- **The D-091 phantom-pick window pollutes acceptance data.** 12.8% of served cards contained picks
  that did not exist in the league, passed at roughly double their like rate. Compositional measures
  are fine; any propensity or bake-off baseline drawn from before 2026-08-19 is not.
- **Targetedness is not persisted** anywhere in `deck_impressions` or `trades_generated`, so the
  untargeted share can only be bounded (≈73–80% of prod generations), not measured.

---

## Source memos

All seven are read-only analyses committed alongside this file.

| Memo | Covers |
|---|---|
| [`2026-08-19-armb-audit-claims-1-2.md`](2026-08-19-armb-audit-claims-1-2.md) | consensus user-win gate; user-only 1-for-1 gate |
| [`2026-08-19-armb-audit-claims-3-4.md`](2026-08-19-armb-audit-claims-3-4.md) | R5 need gate; Elo asymmetry (the replay harness lives here) |
| [`2026-08-19-armb-audit-claims-5-6.md`](2026-08-19-armb-audit-claims-5-6.md) | pick representability; fairness basis |
| [`2026-08-19-armb-audit-claim-7.md`](2026-08-19-armb-audit-claim-7.md) | ranking overlays and narrative copy |
| [`2026-08-19-armb-remedy-bucket-a.md`](2026-08-19-armb-remedy-bucket-a.md) | six dualization proposals, measured |
| [`2026-08-19-armb-remedy-bucket-b.md`](2026-08-19-armb-remedy-bucket-b.md) | four drop-or-invert proposals |
| [`2026-08-19-armb-remedy-bucket-c.md`](2026-08-19-armb-remedy-bucket-c.md) | five "safe to keep user-only" overlays |

Related same-day work: [`2026-08-19-pick-year-valuation.md`](2026-08-19-pick-year-valuation.md),
[`2026-08-19-ktc-pick-value-comparison.md`](2026-08-19-ktc-pick-value-comparison.md),
[`2026-08-19-pick-badge-scale.md`](2026-08-19-pick-badge-scale.md).

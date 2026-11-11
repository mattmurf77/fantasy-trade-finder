# Feature Scope — Fit block, version 3, with outlook tags (WS4b, recommendation R11)

**Date:** 2026-11-10
**Entry point:** direct operator ask, [offer-learnings plan](plan.md) §3 WS4b. The operator, after
[`mockups/fit-copy/`](../../../mockups/fit-copy/index.html): "I like version 3 with a team outlook
tag for both teams as well." Coordinator addendum (binding): the block must not slow the cards;
prove it with a measurement and a guard test.
**Builder:** WS4b builder session, branch `feat/fit-block-v3` (from `feat/offer-learnings`)
**Replaces:** WS4's one-line-per-side `fit_lines` ([scope-fit-first-copy.md](scope-fit-first-copy.md)),
same flag `trade.fit_first_copy` (default off), template version `fit-1` → `fit-2`.
**Operator sign-off on waivers:** needed for §1 (analytics waived, as in WS4).

---

## 0. What the card carries

Per team, the other team first, at most two lines:

```
LEAGUE RANK · POSITION VALUE
THEM              Rebuild-leaning: adds Eli Brandt, 23
Looks rebuilding  WR 9th → 7th
YOU               Win-now: adds Marcus Hale, 29
Contending        WR 3rd → 4th
```

- **Left column:** the team label (THEM / YOU) over its outlook tag.
- **Line 1, the lead:** the single strongest proof-backed reason, plan then need; or, with no
  supported gain, only what moves ("Gets Tomas Reyes, gives Kenji Oduya"), no praise. Truncated,
  never wrapped.
- **Line 2, the ranks:** the team's league rank at each position the trade moves, gains first, then
  losses, in IBM Plex Mono. Absent when nothing moves a rank. Truncated, never wrapped.
- The block is absent when neither team has a supported lead or a rank move: today's card.

Wire (`docs/api-reference.md`): `fit_block: {v: "fit-2", teams: [{side, tag?: {code, source, text},
lead: {code, text}, ranks: [{pos, before, after}]}]}`.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** dark behind a default-off flag, graded by the
  operator on TestFlight first, exactly as WS4. When it is lit for an A/B, the existing
  `deck_impressions` / `deck_outcomes` rows plus the payload's `fit_block.teams[].lead.code` are the
  join; stamping `FIT_TMPL_VERSION` into `features_json` would be the first addition, specced then.
  **Operator sign-off needed.**

## 2. Schema & flag scope

- New/changed tables or columns: none. No proof field (the proof is read, never extended).
- Flag: the existing `trade.fit_first_copy` (default **false**), description updated in
  `docs/config-reference.md`. No new env var or `model_config` key; thresholds are module constants
  in `trade_narrative.py`, pinned by test.
- Prepared-inventory codec (`prepared_trade_payload.py`): `fit_block` added to `PUBLIC_FIELDS`
  (the stored public card may carry it) and `fit_context` to `CAPTURE_ONLY_FIELDS` (the job's shared
  context is not captured; its output already is). See §6.

## 3. The rules

### 3.1 League position ranks

- **Measure:** summed consensus value of a team's players at the position, exactly
  `power_rankings.compute_power_rankings(...)[i]["positions"][P]["value"]`, with League rankings'
  seed and metadata (`server._power_value_inputs`, now shared by `_power_ranking_inputs` and the fit
  block). Never the personal basis.
- **Rank:** 1 + teams strictly above; ties share a rank (League rankings' `teamPosRank`).
- **Noise bar:** a move shows only when the position's value changes by ≥ `FIT_RANK_MIN_MOVE` =
  5% of the league median there (`server._position_medians`, the median League rankings draws) and
  the rank changes. Unchanged, sub-threshold and same-rank positions are omitted.
- **Picks:** no position rank. A pick-only side has no rank line.
- **Small leagues:** no ranks with fewer than `FIT_RANK_MIN_TEAMS` = 3 teams whose players carry
  value (Home's `MIN_SPLIT_TEAMS`).
- **Disagreement:** if the context does not place a traded player on the team the card says, the
  card gets no ranks (never a wrong rank).
- **Order:** gains first, larger moves first, then QB/RB/WR/TE.

### 3.2 Lead phrases (template `fit-2`)

Triggers are WS4's plan and need rules unchanged ([scope-fit-first-copy.md](scope-fit-first-copy.md)
§3); WS4's surplus template is dropped (the mockup's version 3 falls back from plan, to need, to
moves). Per team the first that fires wins.

| Code | Wording (exact) | Fires when (proof field / public fact) |
|---|---|---|
| `plan_rebuild.you` | `Rebuilding: adds {asset}` | viewer `outlook` ∈ {rebuilder, jets}, `outlook_source == "declared"`, viewer `benefits` ∋ `outlook` or `future_pick_capital`; receives a pick or a QB/WR/TE ≤ the generator's youth band (`trade_gen_bilateral._YOUNG`). Highest-market qualifying asset |
| `plan_rebuild.you_roster` | `Rebuild-leaning: adds {asset}` | as above, `outlook_source == "inferred"` |
| `plan_rebuild.them` | `Rebuild-leaning: adds {asset}` | the other team's **roster read** (§3.3) ∈ {rebuilder, jets} and the trade's public now-lean shift for them ≤ −0.05; same asset rule |
| `plan_win_now.you` | `Win-now: adds {asset}` | viewer `outlook` ∈ {contender, championship}, declared, plan benefit present; receives a QB/RB/WR/TE with `_now_lean ≥ 0.05` |
| `plan_win_now.you_roster` | `Win-now-leaning: adds {asset}` | as above, inferred |
| `plan_win_now.them` | `Win-now-leaning: adds {asset}` | roster read ∈ {contender, championship}, shift ≥ +0.05, receives a player with `_now_lean ≥ 0.05` |
| `need.you` / `need.them` | `Upgrades {pos}: adds {name}` | the side's outlook (the viewer's proof outlook; the other team's roster read) is not rebuilder/jets; at a position P where it receives a player (the highest-market one there, age known), `usable_depth_delta[P]` > the proxy's backup credit for him (0.15 × market × `age_now_mult`) and ≥ 10% of `usable_depth_before[P]`. Highest relative lift wins |
| `moves.you` / `moves.them` | `Gets {gets}, gives {gives}` | no plan or need phrase fires. Names joined by ` + `, picks by label. No praise |

`{asset}` is `{name}, {age}` for a player (`Eli Brandt, 23`) and `the {label}` for a pick
(`the 2027 1st`); a player with no age never fills it.

### 3.3 Outlook tags

| Team | Source | Words | From |
|---|---|---|---|
| Viewer, declared | proof `viewer.outlook`, `outlook_source == "declared"` | championship `All-in`, contender `Contending`, rebuilder `Rebuilding`, jets `Tanking` | the app's declared-outlook names, `OutlookBiasReceipt.tsx` `OUTLOOK_DISPLAY_NAME` |
| Viewer, undeclared | proof `viewer.outlook` (the engine's read) | contender `Looks contending`, rebuilder `Looks rebuilding` | Team Review's league-mate words ("Contending teams" / "Rebuilding teams", partners beat) marked with the deck receipt's "look" for an inferred outlook ("you look" vs "you're") |
| Other team, always | `FitLeagueContext.reads[target]`: a stored inferred outlook, else `trade_service.infer_team_outlook(roster, players, num_teams)` under the job's config, exactly as `trade_gen_owner._team` resolves an undeclared team | as the row above | as the row above |

No tag for `not_sure` or no read (Team Review drops a read that declined to commit). The roster
read never yields the extremes. A league-mate's declared outlook is never read, shown or implied:
the other team's plan and need rules use the roster read in place of the proof's outlook, so even
the choice between a need phrase and "Gets …, gives …" cannot depend on what they declared.

### 3.4 Privacy

The other team's block reads, from their side of the proof, only `usable_depth_before` and
`usable_depth_delta` (a market-value proxy, as in WS4). Everything else is public: rosters, ages,
consensus values and ranks (League rankings shows them), and the roster read (Team Review shows
league-mates' windows). `test_their_whole_block_ignores_every_private_counterparty_field` mutates
their declared outlook, outlook source, benefits, intent, preferences (incl. a stored
`team_outlook`), preference evidence, plan gains and the per-asset personal-board fields and
requires their whole block to be byte-identical;
`test_the_other_teams_declared_outlook_is_never_the_tag` and
`test_job_context_reads_are_the_generators_and_ignore_declared_outlooks` cover the tag and the job
context.

## 4. Where the ranks are computed and stored (and what it costs)

1. **Once per trade job:** `server._run_trade_job` calls `_fit_league_context(owner_context,
   service)` (`server.py:13319`) right after the owner context is captured, before generation. One
   `compute_power_rankings` over the job's rosters (picks excluded, as `league_members` holds them),
   one `_position_medians`, one roster read per team. Flag off or no owner context: returns `None`
   at once, before any import or computation.
2. **Shared, not copied:** `_gen_owner` stamps the same object on every owner card
   (`card.fit_context`, `server.py:13361`). `FitLeagueContext` returns itself on copy/deepcopy.
3. **Per card, at serialization:** `trade_card_to_dict` (`server.py:21099-21107`) calls
   `trade_narrative.fit_block`, a constant-size update for the two teams (move the traded players'
   values, re-rank only the touched positions against the other teams' unchanged values). No call
   walks a roster per card.
4. **Stored:** the result is in the card dict the job publishes (`_publish_owner_batch`,
   `server.py:14291-14304`), which is what `job["cards"]`, the P1 first-page store and the prepared
   inventory's public record hold. Serving a page reads those dicts; no serve path calls the
   composer (`test_serving_a_stored_or_running_page_never_recomposes`).

Measured on recorded production requests: §8 "Speed".

## 5. Evidence scope

- [x] **Unit / worker tests:** `backend/tests/test_fit_block_v3.py` (48 tests) replaces
  `backend/tests/test_fit_first_copy.py` (removed with `fit_lines`). Covers: rank parity with
  `compute_power_rankings` before and after on 60 random leagues (480 trades, ties common), ties,
  the 5% noise edge (147.5 shows, 147.4 does not), picks, small leagues, context disagreement, rank
  order; every lead template and its threshold edges; every tag and the no-tag cases; privacy;
  omission; malformed input; pinned templates, tags, constants and version; serialization on real
  revision-2 cards (flag off: no key and the composer never runs; flag on without a context:
  byte-identical; payload equals the composer; no private field; mutated card: no block); the job
  context (League rankings' inputs, no picks, the generator's read, declared outlooks ignored, none
  with the flag off); the prepared codec; and, on the real worker (owner route harness, revision 2),
  one context and one league walk per deck with the composer run once per published card, and zero
  league work with the flag off.
- [x] **Structural guard:** `mobile/tests/check-fit-first-copy.js` (`npm run test:fit-first-copy`),
  rewritten: 10 checks (flag + edited gate; placement above every value surface; them row first,
  each row its own team; server text only beyond three labels; single-line lead and ranks, ranks in
  mono; neutral colours only; ordinal and rank text executed; wire type; normalizer; npm script).
- [x] **Sabotages** (each red, then green on revert; scripts kept outside the repo):
  backend S1 ties-break-by-order, S2 noise-bar-off, S3 noise-bar-inclusive, S4 picks-ranked,
  S5 min-teams-ignored, S6 no-owner-check, S7 their-tag-from-proof, S8 their-lead-from-declared,
  S9 their-benefits-read, S10 viewer-roster-read-claimed-declared, S11 viewer-tag-ignores-source,
  S12 not-sure-tagged, S13 viewer-first, S14 moves-counted-as-shown, S15 reword-without-bump,
  S16 losses-first, S17 need-lift-zero, S18 no-backup-guard, S19 young-rb-rebuild,
  S20 after-rank-uses-before, S21 flag-ignored, S22 context-without-flag, S23 no-proof-match,
  S24 context-reads-declared, S25 context-keeps-picks, S26 public-field-missing,
  S27 capture-field-missing, S28 context-copied, S29 worker-not-stamping, S30 per-card-context,
  S31 league-walk-per-card, S32 recompose-on-serve; mobile M1 flag-not-read,
  M2 edited-card-shows-block, M3 viewer-row-first, M4 lead-wraps, M5 ranks-coloured,
  M6 ordinal-teens-wrong, M7 unknown-version-accepted, M8 empty-key-sent, M9 card-reads-code,
  M10 client-copy-added, M11 fit-lines-still-read, M12 block-below-strength.
- [x] **Code-walk proof:**
  1. Generation is untouched: no `backend/trade_gen_*.py` file changed. The proof is read through
     `evidence.as_dict()` only.
  2. `_run_trade_job` builds the context once (`server.py:13319`) and `_gen_owner` stamps it
     (`server.py:13361`); with the flag off `_fit_league_context` returns `None` at its first line
     (`server.py:21019`) and no card is stamped.
  3. `trade_card_to_dict` (`server.py:21099-21107`) requires the flag, a stamped context and
     `evidence.matches(card)`; it adds `fit_block` only when the composer returns one.
  4. `trade_narrative.fit_block` (`trade_narrative.py:650`) loops them → you; the other team's
     view is `{outlook: context read, outlook_source: "inferred", usable_depth_*}` only; ranks come
     from `_fit_rank_rows` (`trade_narrative.py:600`).
  5. `mobile/src/api/trades.ts:191-216` validates the block (`v === "fit-2"` only), `:312` spreads it
     only when a team passes. `TradeCard.tsx:280-282` gates on the flag and the edited state;
     `:652` renders the block after the header and before `<StrengthBar` (`:768`), the sides and
     `<TradeValueBar` (`:1005`).
- [x] **Manual TestFlight checklist** (operator; `trade.fit_first_copy` on via `FTF_FLAGS` plus
  `POST /api/feature-flags/reload`, relaunch the app, then pull a fresh deck in a 10–12-team Sleeper
  league served by the bilateral owner engine; use an iPhone SE / mini or Display Zoom for 375 px):
  1. On cards that carry it, a "LEAGUE RANK · POSITION VALUE" label sits directly under "Trade with
     @name", above Match strength, the player sides, the value bar and Pass / Like. THEM's row is
     above YOU's.
  2. On a 375 px screen the busiest card (two rank moves per team) still shows the whole value bar
     and Pass / Like without scrolling. Each team takes at most two lines; a long lead ends in "…"
     rather than wrapping.
  3. Every lead names a player or pick on the card, on the right side ("adds X" for THEM: X is under
     YOU SEND; for YOU: under YOU GET). A team with no reason reads "Gets …, gives …" and nothing
     else; no card says "good fit", carries an emoji or an exclamation mark.
  4. Open League rankings, pick the other team, and compare: each "before" rank on the card equals
     the rank chip on that position's header there (All view, consensus). Do the same for your
     team. After accepting a trade in a test league and re-syncing, the "after" ranks match.
  5. Ranks show both gains and losses, in the mono face, in the same colour; nothing is red or
     green. A pick-only side shows no rank line. A small test league (fewer than 3 valued teams)
     shows no rank lines.
  6. Tags: your tag reads your declared outlook (All-in / Contending / Rebuilding / Tanking) when you
     set one in Trade DNA, and "Looks contending" / "Looks rebuilding" when you have not. The other
     team's tag is always "Looks …" or absent. Ask a league-mate who declared an outlook in the app
     that differs from their roster (or use a second test account): their tag never shows the
     declared word.
  7. Edit a card (swap a player): the block disappears, like Match strength.
  8. Turn the flag off and relaunch: the blocks disappear from the same cards without rebuilding
     the deck; everything else on the card is unchanged. A card without a block looks exactly as
     before the build.
  9. Time to the first card feels unchanged with the flag on versus off on the same league.
- `testID`s: `trade-card.fit-block`, `trade-card.fit-team.them`, `trade-card.fit-team.you`,
  `trade-card.fit-tag.them`, `trade-card.fit-tag.you` (`mobile/scripts/testid-lint.sh` passes).
  WS4's `trade-card.fit-lines` / `fit-line.*` are gone.

## 6. Stored pages, prepared inventories and `fit-1`

- **Stored first pages (P1):** the stored card dicts carry the block exactly as published; a serve
  never recomposes it. `trade_narrative.py` is in `_ENGINE_CODE_MODULES`, so this change moves every
  page's engine version: pages stored with WS4's `fit-1` lines fall through and rebuild on deploy.
  The flag is not part of the page key: after turning it on, blocks appear on decks built from then
  on; after turning it off, the app's own flag gate hides stored blocks at once.
- **Prepared inventories:** they store the public card dict and serve it as stored. Before this
  build, the prepared codec rejected any public key outside `PUBLIC_FIELDS`, so with WS4's flag on a
  `fit_lines` card made the capture fail (`prepared_payload:fields`) and the inventory was not
  prepared. Now `fit_block` is allowlisted and `fit_context` is capture-only, so prepared
  inventories carry the block (test: `test_prepared_inventory_accepts_the_card_and_carries_the_block`).
  A restored runtime card has no context, so a route that re-serializes it (pending trades, swipe
  response) omits the block; those are not deck renders.
- **`fit-1` lines:** the server no longer emits `fit_lines`; the app's normalizer no longer reads
  them, so any `fit_lines` still on a stored page are dropped silently (the key is absent from the
  normalized card). WS4 never shipped to `main`, so no released app reads them.

## 7. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | trade card payload: `fit_block` replaces `fit_lines` |
| `living-memory/LLD.md` | n/a because no schema, route or invariant convention shifted; one optional payload key under existing routes |
| `docs/architecture.md` | n/a because no module wiring changed: the worker calls one server helper and `trade_card_to_dict` a pure function in an existing module |
| `living-memory/HLD.md` | n/a because no architecture shift |
| `docs/cross-client-invariants.md` | updated | § Fit block ranks and outlook tags (the rank rule, the rank text, the tag vocabulary) |
| `docs/glossary.md` | updated | Fit block, League position rank, Outlook tag (replaces "Fit line") |
| `docs/config-reference.md` | updated | § Flags — Fit-first card copy |
| ADR or `DECISIONS.md` entry | updated | `living-memory/DECISIONS.md` D-NEXT |

## 8. Speed

Budget (coordinator, binding): ≤ 10 ms added before the first published batch on a 12-team
league, ≤ 5% added to the whole deck build, nothing before the first card that scales with the
deck, flag off costs nothing.

**Where the work runs.** The league-wide step runs once per job, before generation
(`server.py:13319`). The per-card step runs inside `trade_card_to_dict`, which on the production
owner-serve path is called by `_publish_owner_batch` for the cards of each committed batch only
(first batch 30, then 100s, after their evidence is recorded): nothing before the first card
scales with the deck. A card's rank is a binary search over the league's sorted position values
(precomputed once in the context) plus a two-team correction. Flag off: `_fit_league_context`
returns at its first line and `trade_card_to_dict` skips the branch; no `trade_narrative` fit code
runs (`test_flag_off_job_builds_nothing_and_composes_nothing`).

**Measured** on 20 recorded production requests (12-team, organic, untargeted; aggregates only;
`generate_bilateral_trades` full inventory, then the fit-block steps on its cards; the shared
machine was under load from other builders, so absolute times are pessimistic):

| Measure | Median | Max |
|---|---|---|
| Cards in the full inventory | 2,808 | 4,016 |
| Full deck build (generator) | 5,221 ms | 6,199 ms |
| League-wide step (`_fit_league_context`) | 0.86 ms | 1.88 ms |
| Per-card serialization cost added (flag on minus off, `trade_card_to_dict`) | 24.7 µs | 63.9 µs |
| Before the first batch (league step + 30 cards) | 1.6 ms | 3.1 ms |
| 150-card deck (fast deck) | 4.7 ms | 10.8 ms |
| Full inventory, every card serialized once | 67 ms | 201 ms |
| Share of the full deck build | 1.3% | 3.4% |

`fit_block` alone on one 4,002-card inventory in a quieter moment: 21–24 µs per card. Cards with a
block: 88.6%. Within the budget on every measure; the per-card maximum (64 µs under load) is above
the 50 µs target, which is why the per-card work stays per batch rather than front-loaded.
Guards: `test_flag_on_job_computes_the_league_once_and_never_per_card` (one context, one league
walk per deck, the composer once per published card; sabotages S30, S31),
`test_serving_a_stored_or_running_page_never_recomposes` (S32).

## 9. Ship gate declaration

- **CI green:** `backend-tests` is expected RED on `test_deck_pipeline_digest` only:
  `_run_trade_job` and `trade_card_to_dict` changed and three helpers joined
  `DECK_PIPELINE_FUNCTIONS` (`_fit_league_context`, `_power_value_inputs`, `_position_medians`; two
  references added to `DECK_PIPELINE_IGNORED`). Left red on purpose for the coordinator's single
  `DECK_PIPELINE_VERSION` bump. `mobile-typecheck` (tsc + all `check-*.js`) and
  `maestro-testid-lint` pass.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** §5 checklist, run by the operator before the flag is lit.
- Express lane declared by the operator? no.

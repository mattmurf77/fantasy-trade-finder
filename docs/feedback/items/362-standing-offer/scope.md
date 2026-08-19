# Feature Scope — #362 Standing offer: broaden a liked 1-for-1

**Date:** 2026-08-19
**Entry point:** feedback #362 (jonbonjourvi, TradesHome, v1.15.0, idea)
**Builder:** Author agent (this session) → backend + mobile build agents
**Operator sign-off on waivers:** **required — 3 waivers below** (§4 rows for
`docs/cross-client-invariants.md` and ADR; §3 has none). Waivers are marked **WAIVED** and
each states its reason.

> **Gate posture: BRIGHT LINE — full gates, not express.** New table + 3 new routes + new
> feature flag + 5 new analytics events. Per CLAUDE.md §Feature gates this cannot be a
> quick fix and no agent may self-select express. The operator has not declared express.
>
> Contract: [`prd.md`](prd.md) · [`lld-delta.md`](lld-delta.md) ·
> [`hld-delta.md`](hld-delta.md) · Plan: [`plan.md`](plan.md) ·
> Design: [`mockups/standing-offer-362/`](../../../../mockups/standing-offer-362/)

---

## 1. Analytics scope

**(a) New events specced.** Five. Full taxonomy detail — literal registration sites,
frozenset syntax, and the banner-comment requirements — in
[`lld-delta.md`](lld-delta.md) §7.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `standing_offer_prompted` | `round` (int), `seasons_offered` (int count of pills shown), `teams_offered` (int count of rows shown) | the post-like sheet becomes visible | mobile (`screen: 'Trades'`) |
| `standing_offer_posted` | `round` (int), `seasons` (int count selected), `teams` (int count selected), `used_all_teams` (bool) | `POST /api/trades/standing-offer` returns 200 | mobile (`screen: 'Trades'`) |
| `standing_offer_skipped` | `snoozed` (bool), `retired` (bool) | "Just this one trade" is tapped | mobile (`screen: 'Trades'`) |
| `standing_offer_revoked` | `age_days` (int) | revoke returns 200 | mobile (`screen: 'Matches'`) |
| `standing_offer_card_shown` | `round` (int), `seasons` (int count) | a standing-offer card is injected into a served deck | **server** (`record_event`) |

**Cardinality:** counts only. No player ids, no member ids, no `team_user_ids`, no query
strings — the `mock_*` family convention (`backend/analytics_taxonomy.py:991-1013`,
`:1018-1031`). `team_user_ids` is never an analytics prop (PRD R-19).

**Follow-through, all four sites, in the SAME commit as the emitters:**

1. `backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS` (`:38`) — the four client
   events, under one dated banner block in the `:449-487` style.
2. `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` (`:627`) — **mandatory**: the
   import-time completeness check at `:1283-1288` raises `ValueError` at boot if a client
   event has no entry.
3. `backend/analytics_taxonomy.py` `SERVER_FIRED_EVENTS` (`:494`) —
   `standing_offer_card_shown`, props documented in the inline comment (server-fired
   events carry no `CLIENT_EVENT_PROPS` entry — the `awaiting_trade_dismissed` precedent
   at `:540-556`).
4. `backend/analytics_queries.py` `NON_INTENT_EVENTS` (`:63`) — `standing_offer_prompted`,
   `standing_offer_skipped`, `standing_offer_card_shown`. `_posted` and `_revoked` are
   deliberately **absent** (deliberate user actions = intent). `INTENT_EVENTS` is derived
   by subtraction at `:244`, so an omitted impression-class event silently inflates
   DAU/WAU — the NULL-`platform` failure mode.

**`FUNNEL_CRITICAL` (`backend/analytics_taxonomy.py:604`): no.** This is a side surface,
not a step in the sign-in → suggestion core loop.

**Not evented:** likes-you cap drops. They are a **counter**
(`trade_service._standing_offer_cap_drops` / `_organic_like_cap_drops`, the
`_r4_excluded_keys` idiom at `backend/trade_service.py:3078`), logged once per job. One
event per dropped card in a chatty league is high-cardinality server noise for a question
a counter answers. See PRD R-15.

**Stored?** No new analytics table. `standing_offers` itself is feature state, and it is
in `docs/data-dictionary.md` per §4.

**Tracking-plan addendum:** to be written at
`docs/business/analytics/2026-08-19-standing-offers.md` before the taxonomy edit — the
precondition `backend/analytics_taxonomy.py`'s own module docstring demands, and the
convention the `:449-487` banner block follows.

---

## 2. Schema & flag scope

**New tables or columns:**

- **`standing_offers`** (new table) — full DDL in [`lld-delta.md`](lld-delta.md) §2.
  Columns: `id`, `user_id`, `league_id`, `player_id`, `round`, `seasons` (JSON text),
  `team_user_ids` (JSON text, **private**), `source_trade_id`, `created_at`, `expires_at`,
  `revoked_at`, plus `Index("ix_standing_offers_league_live", "league_id", "revoked_at")`.
- **Migration entry reviewed: none required, and adding one is a bug.** A wholly new
  `Table(...)` is created by `metadata.create_all(engine)`
  (`backend/database.py:3331`). `migration_cols` (`backend/database.py:2432`) holds
  three-tuples for *columns on existing tables*; an entry there would attempt an
  `ALTER TABLE` for a column `create_all` just made.
- **`TradeCard`** gains two optional in-memory fields (`standing_offer_reason`,
  `standing_offer_mine`) at `backend/trade_service.py:2833`. Not persisted; no schema
  impact.
- **`OnboardingPersisted`** (client, AsyncStorage) gains four keys
  (`mobile/src/state/useOnboardingState.ts:16-92`). Client-local; no server schema impact.
- → `docs/data-dictionary.md` **updated** (§4).

**New/changed feature flags:**

- **`trade.standing_offers`**, **default OFF (`false` in `config/features.json`)**.
  Registered in `config/features.json` (with a `_comment_standing_offers` sibling),
  `backend/feature_flags.py` `FLAG_KEYS` (neighbour `trade.likes_you` at `:89`),
  `docs/config-reference.md`, and the client flag map.
- **Off ⇒ byte-identical:** the three routes return 404, the prompt never fires, the
  injector's standing-offer branch is never entered, `_stamp_own_standing_offers` is never
  called, and no new key appears on any card payload (both new keys are serialized only
  when set — `lld-delta.md` §5.5). Pinned by `UT-14`.
- **Depends on two existing flags**, both currently `true`: `trade.likes_you`
  (`config/features.json:30`) is the receiving half, gated at `backend/server.py:5422`;
  `trade.picks_in_pool` (`config/features.json:58`) is what makes picks roster assets
  (`backend/server.py:10240-10248`). With either off the feature is inert by construction,
  and PRD R-1 conditions 1-2 make the prompt refuse to fire rather than promise an
  injection that cannot happen.
- **Graduation criterion:** the operator's manual TestFlight pass MT-1 … MT-10 (PRD §8.3)
  clean on a real 12-team Sleeper league, logged in `living-memory/TEST_LEDGER.md`. Then
  flip to `true` for testers.

**New env vars / `model_config` keys:**

- **No new env vars.**
- **`standing_offer_days`** (default `30.0`) — expiry window; stored on the row at create
  time, so a change moves only offers created after it.
- **`standing_offer_inject_cap`** (default `2.0`) — max of the 3 likes-you slots a deck
  may spend on standing offers. **This is the ship-the-knob lever:** `3` reproduces an
  unreserved cap; **`0` stops standing-offer injection entirely without a flag flip or a
  deploy**, which is the intended rollback if the feature crowds organic likes out of
  decks. Appended to `_MODEL_CONFIG_DEFAULTS` (`backend/database.py:2157`).
- → `docs/config-reference.md` **updated** (§4).

---

## 3. Evidence scope

**D-056 posture: NO Maestro, NO simulator, NO `screens/` captures.** Existing
`mobile/.maestro/` flows are historical artifacts; none is authored or run for this item.
`screens/` stays frozen at 2026-08-11.

- [x] **Structural guard:** `mobile/tests/check-standing-offer-362.js` — dependency-free
      node following `mobile/tests/check-league-candidates-300.js` (header stating the
      silently-wrong failure mode, soft-require of `typescript` → `process.exit(2)`,
      `assert(cond, name, detail)` where `detail` names the sabotage, `stripComments()`
      before any "appears nowhere" assertion, `process.exit(1)` on failure). Matching
      script `"test:standing-offer-362": "node tests/check-standing-offer-362.js"` appended
      to `mobile/package.json` after `:52`.

      **Pins (SC-1 … SC-15, itemised per requirement in PRD §4):** all eleven trigger
      conditions present in the gate; the sheet's visibility set from exactly one gated
      function (no `setVisible` bypass); the persisted snooze ladder uses
      `patchOnboardingState`, not a module-scoped session flag; **no hardcoded year literal
      or year-count window anywhere in the sheet**; the members list and the pick
      annotations come from their own queries and are not conflated;
      `STANDING_OFFER_DEFAULT_SELECTION === 'source-only'` and exactly one branch reads it;
      the deck advance is not inside any standing-offer branch; the toast count reads the
      server's `team_count`; no player-level badge component reads offer state; `Segment`
      has exactly three members and the standing segment renders no Edit/Repost; no new
      pill component in `TradeCard.tsx`; the trigger reads only reconstruction-safe card
      fields; **`team_user_ids` appears in no recipient-facing render path in
      `mobile/src/`**; the flag key agrees between `config/features.json` and the client
      default map; the five client-side event-name literals cross-check against
      `backend/analytics_taxonomy.py`.

- [x] **Unit tests:** `backend/tests/test_standing_offers.py` (**new file** — no collision
      with another agent's test ownership). **UT-1 … UT-15**, each with the sabotage it
      catches, tabulated in PRD §8.1. Coverage: create/duplicate/revoke lifecycle; horizon
      and membership validation; the three injector match cases; five independent
      filter-inheritance cases; the cap split and drop counter; both expiries (clock and
      roster); the exact reason string; the sender chip stamp; injector determinism; no
      event on a drop; **the serialized card dict carries no `team_user_ids` and no team
      count**; `round != 1` rejected; flag-off byte-identity; taxonomy + `NON_INTENT_EVENTS`
      registration.

- [x] **Code-walk proof:** three traces, written into `status.md` with `file:line`
      citations (PRD §7.3). **CW-1** — `advance('like')` (`TradesScreen.tsx:3947`,
      post-like branch `:4179-4241`) showing the prompt cannot fire during any of the eight
      competing post-like surfaces (`:4207-4215`, `:4220-4227`, `:3447`, `:4189-4195`,
      `:3113`/`:3355`, `:4105-4154`, `:4184`, `:4190`/`:4216`/`:4238`, `:1820-1839`), whose
      constraint the code states twice as *"never two overlapping surfaces"* (`:4183`,
      `:4205`). **CW-2** — the like is banked (`:4165`) and the deck advanced (`:4178`)
      before the sheet can mount, so dismissal is byte-identical to today. **CW-3** — the
      injector predicate traced showing every pre-existing filter (`server.py:3010`,
      `:3016`, `:3021`, `:3031`, `:3038`, `:3055`) still runs on standing-offer candidates.

- [x] **Manual TestFlight checklist:** **MT-1 … MT-10**, PRD §8.3 — numbered, with expected
      results, on a real 12-team Sleeper league. Runtime proof genuinely matters here: the
      trigger's correctness is a *timing* property against eight other surfaces, and the
      privacy invariant is only observable from a second account. Steps cover the
      post-advance sheet timing, the source-only default and CTA count, skip-is-a-no-op,
      one-prompt-per-session, the persisted ladder across a cold start, the sender chip,
      the recipient's card **with no team names or counts**, the non-selected team seeing
      nothing, revoke propagation, the player-not-pick negative, and the ESPN /
      short-horizon negatives.

- [ ] **WAIVED because:** — n/a, nothing in this section is waived.

- **`testID`s added:** `standing-offer-sheet`, `standing-offer-season-<season>`,
  `standing-offer-team-<user_id>`, `standing-offer-all-seasons`,
  `standing-offer-all-teams`, `standing-offer-confirm`, `standing-offer-skip`,
  `matches-segment-standing`, `standing-offer-row-<offer_id>`,
  `standing-offer-revoke-<offer_id>`. **None renamed.** All must pass
  `mobile/scripts/testid-lint.sh` (still in CI).

---

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `## Trades` (`:227`) — three rows: `POST /api/trades/standing-offer`, `GET /api/trades/standing-offers`, `POST /api/trades/standing-offer/revoke`, house style (body inline in backticks, response after `→`, errors after `·`, flag bolded, `Off ⇒ 404`). Plus `standing_offer_reason` and `standing_offer_mine` added to the `### Trade card object` block (`:253`). Contract pinned in [`lld-delta.md`](lld-delta.md) §4. |
| `docs/data-dictionary.md` | **updated** | new `## \`standing_offers\`` section in the `league_preferences` (`:650`) / `asset_preferences` (`:797`) style: purpose line naming the one-live-row rule, column table, and a closing **Constraint:** paragraph stating that uniqueness is enforced at the writer with `revoked_at IS NULL` and **not** by a unique index. Markdown drafted in [`lld-delta.md`](lld-delta.md) §2. |
| `docs/config-reference.md` | **updated** | (a) `## Feature flags` — new group `## Flags — Standing offers (#362) (2026-08-19 — ships dark)`, one row for `trade.standing_offers`, Gates cell naming the files and ending with the `Off ⇒ …` clause. (b) `## \`model_config\` keys` (`:529`) — new group `### Standing offers — \`backend/server.py\`, DB-seeded`, rows for `standing_offer_days` and `standing_offer_inject_cap`, the latter's Meaning cell ending with the bolded kill-switch sentence. |
| `living-memory/LLD.md` | **updated** | one convention line: *the likes-you match rule is a union of exact mirrors and standing offers; both pass the identical filter sequence and share one cap.* Plus the general rule this item generalises: **"at most one live row" is enforced at the writer with a `<x>_at IS NULL` predicate, not a `UniqueConstraint`, whenever the row has a revoke concept** (`trade_decisions.retracted_at`, now `standing_offers.revoked_at`). Text in [`lld-delta.md`](lld-delta.md) §10. |
| `docs/architecture.md` | **updated** | § Data flow (`:5`) gains the `standing_offers` node and its cross-user read edge; § "Request lifecycle (trade card — v2 engine)" step 5 (`:189`) is rewritten as a two-source union plus an own-offer-stamping bullet; § Components (`:120`) gains one table row. Replacement text in [`hld-delta.md`](hld-delta.md) §§2-4. |
| `living-memory/HLD.md` | **updated** | § Key Flows (`:106`) gains **Flow F — Standing offer**, including the privacy invariant; § Design Trade-offs (`:154`) gains the "bounded by selection, not by a value model" entry. Text in [`hld-delta.md`](hld-delta.md) §§5-6. **Justification for updating HLD at all** (most items should not): `standing_offers` is the system's first cross-user broadcast record — the first row a user writes that is evaluated on behalf of *other* users, repeatedly, without further action from its author. That is a genuine data-flow addition, argued in [`hld-delta.md`](hld-delta.md) §1. |
| `docs/cross-client-invariants.md` | **WAIVED — n/a because** no shared constant, color, enum string, tier band, or K-factor crosses clients. The feature ships mobile-only in v1; the tier/position hexes its cards render are already-governed encodings it merely reuses; `standing_offer_inject_cap` and `standing_offer_days` are server-side and never read by a client. **Operator sign-off requested.** |
| `docs/glossary.md` | **updated** | one bold-paragraph entry appended at the end (the file is append-only, thematic-adjacent, **not** alphabetical): **Standing offer** — a user's generalised, time-boxed, team-targeted intent to trade one player for any pick of a round in one league; distinct from a **like**, which is one exact package. Names the governing flag and the `standing_offer_days` knob, per the house convention. |
| ADR or `DECISIONS.md` entry | **updated (`DECISIONS.md`) / ADR WAIVED** | **D-093** — *A standing offer is bounded by round and by the user's own team selection, not by a pick-value band* (text in [`hld-delta.md`](hld-delta.md) §9). Next id verified as 093 (max present is D-092, 2026-08-19); **grep before writing**. **ADR waived because** this decision reverses a *lab proposal*, not a shipped architectural commitment, and it is fully explained by two existing decisions (D-079, D-090) plus one open question (Q-023) — a DECISIONS entry pointing at those is the honest weight. An ADR would restate them. **Operator sign-off requested.** |

**Third waiver (not a docs row):** **no tracking-plan PR precedes the taxonomy edit in the
usual sequence** — instead the addendum
(`docs/business/analytics/2026-08-19-standing-offers.md`) is written by the build agent
immediately before the taxonomy edit, in the same commit. **WAIVED because** this is a
single-session pipeline with no separate analytics reviewer; the default-deny prop policy
(`backend/analytics_taxonomy.py:612-616`) is still satisfied because every prop is
enumerated in §1 above and pinned by `UT-15`. **Operator sign-off requested.**

---

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests`, `mobile-typecheck`
  (`tsc --noEmit`), `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`).
  Most recent measured pytest suite on this branch point: **3526 passed, 1 skipped, 0
  failed** (`living-memory/TEST_LEDGER.md:23`); the clean-`origin/main` baseline of
  **3480 passed, 1 skipped** is at `:105`. **Re-measure the baseline on your own branch
  point** rather than assuming either number.
- **`mobile/tests/check-*.js`** — **60 passed, 0 failed** baseline
  (`living-memory/TEST_LEDGER.md:176`), 61 with `check-standing-offer-362.js`. These are `npm run`-only and gate nothing in CI
  yet (open item in `NEXT.md`), so the build agent runs them explicitly and pastes the
  PASS count into `status.md`.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it
  proved — the UT/SC counts, the three code-walk proofs, and the MT outcome.
- **TestFlight verification:** MT-1 … MT-10 (PRD §8.3) run by the operator; outcome logged
  in `TEST_LEDGER.md`. Required before the flag flips to `true`.
- **Simulator gate:** `githooks/pre-push` still enforces the retired marker
  (`qa/sim-runs/last-sim-run.json`). Under D-056 the standing posture is
  **`FTF_SKIP_SIM_GATE=1`** — set it and note the evidence run above instead. Install hooks
  once per clone: `git config core.hooksPath githooks`.
- **Recovery ledger:** the worktree/branch for this item is swept per
  `docs/recovery/CLAUDE.md` — content verified against `origin/main` (this repo
  squash-merges, so ahead-counts and `git branch -d` refusals are not evidence), tip sha
  ledgered in a dated `docs/recovery/` file, **then** removed.
- **Express lane declared by the operator?** **No.** Full gates. This change touches
  schema, API contracts, a feature-flag surface, and analytics events — all four sides of
  the CLAUDE.md bright line — so it could not be express even if declared, without an
  explicit confirming yes.

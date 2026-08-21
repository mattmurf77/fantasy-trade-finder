# Feedback items — index

> One row per `docs/feedback/items/<id>-<slug>/` folder, derived from the
> first ~15 lines of that folder's `status.md` (or its other files when
> `status.md` is missing). This is the fast duplicate-check surface for the
> `/feedback` pipeline and anyone triaging a new report.
>
> **Phase-0 duplicate checks read THIS FILE only — never glob the item
> folders.** Reading 100+ folders to check for a prior fix costs 8–110k
> tokens; this table costs a few hundred.
>
> **Regeneration rule:** any session that changes an item's status (ships it,
> merges it, flips its flag, backfills its `status.md`, adds a new item
> folder) updates that row in the same session. This file is allowed to lag
> by a session, never by a quarter.
>
> **Status values:** `shipped` (live, no caveat) · `built-dark` (built,
> behind a default-off flag or an allowlisted experiment) · `planned` (spec
> written, build not started) · `in-progress` (built/fixed but not confirmed
> merged/shipped — worktree branch, "pending merge", "awaiting QA", etc.) ·
> `mockup-only` (design only, no code) · `research-only` (investigation/
> interview only) · `open` (spec/PRD only, not built) · `declined` (operator
> passed) · `unknown` (no readable evidence).
>
> `planned` is carried here to match the `status.md` enum in
> [README.md](README.md) § Status line format, which added it 2026-08-18. No
> row currently uses it — every item whose `status.md` says `planned` turned
> out to have shipped — but the vocabularies must not drift apart again.
>
> **Legacy audit, 2026-08-18.** Every pre-existing row was re-checked against
> `living-memory/CHANGELOG.md` (+ `archive/CHANGELOG-*.md`), `TEST_LEDGER.md`,
> `DECISIONS.md`, `docs/recovery/*.md`, and `config/features.json`. **67 rows
> were corrected**, nearly all `in-progress` → `shipped`: they were written
> pre-merge, cited a worktree branch, and were never revisited after the work
> landed. A row's `where` cell now names the evidence that settled it (commit,
> PR, flag, or dated CHANGELOG entry), so any status here can be re-audited
> without reopening the item folder.
>
> **What `in-progress` means in the 36 rows that kept it.** These are
> individually-built items from the `teardown-remediation` era (2026-07-12 →
> 2026-08-08) whose `status.md` says "built" on a worktree branch and which no
> CHANGELOG entry, TEST_LEDGER row, recovery ledger, or feature flag names.
> The [2026-08-08 branch triage](../../reviews/2026-08-08-branch-triage.md)
> content-verified that era's branches broadly — 44 of 50 DELETE, i.e. content
> already on `main`, with only three RECOVER items — so these are *probably*
> shipped too. But that is a branch-level inference, not a per-item record, and
> the specific `worktree-agent-*` branches they cite appear in no recovery
> ledger. Read `in-progress` as **"built; merge unconfirmed for this item,"**
> never "abandoned" — and don't upgrade one to `shipped` without finding the
> evidence this audit could not.
>
> **Backfilled 2026-08-18** — the 2026-08-09→2026-08-18 gap named in
> [README.md](README.md) § Known drift is closed. 41 rows added (#211 through
> #341, plus the two named programs); the table is now 1:1 with the folder
> listing. Rows for #289 onward were derived from `status.md` **plus**
> corroborating merge evidence in `living-memory/CHANGELOG.md`,
> `living-memory/TEST_LEDGER.md`, `docs/recovery/*-sweep.md`, and
> `config/features.json` — several per-item `status.md` files still read
> "built"/"planned" because they were written pre-merge and never revisited.
> **Where they disagree, the row follows the merge evidence, not the folder.**
>
> **Caveat — the 2026-08-16 wave (#303 #304 #321–#341).** Those 17 rows read
> `shipped` on the strength of the `2026-08-16` CHANGELOG entry (merge
> `20b40db`, 17 items / 7 groups) and the `2026-08-17` TEST_LEDGER entry
> (v1.13.5 build 114, gates green, deploy verified by content). Their own
> `status.md` files still say `built`/`planned 2026-08-16` and are **stale**.
> The wave's branch/worktree ledger, `docs/recovery/2026-08-16-feedback-wave-sweep.md`,
> was written on the wave's own branch and **is not present on `main`** — so
> the ship record here is the two living-memory files, not that ledger. Owed
> at ship and still open per the CHANGELOG: per-group operator TestFlight
> checklists, the prod-DB deck-eval replay for G6's bands, and #339's
> `pick_gap_frac` tuning.
>
> **Seven folders have no `status.md`** — #295, #300, #307, #309, #311, #313,
> #318 carry date- or role-suffixed variants instead (`status-backend-*.md`,
> `status-mobile-*.md`, `status-2026-08-13.md`). Their rows were derived from
> those files. This is a real deviation from the README's "Expected contents",
> not corruption, and **not** a reason to skip them when regenerating: read the
> suffixed files. Nothing here renames or creates item files.
>
> **Group/wave shape.** Where a row belongs to a wave group, the `where` cell
> names the group and marks the **canonical** folder (the lowest id, holding
> the full doc set); satellite rows point at it. See
> [README.md](README.md) § Wave/group folders.

## Table

| id | slug | status | date | where |
|---|---|---|---|---|
| 78 | calc-suggestions | shipped | 2026-07-17 | FB-78/87/88 calculator suggestions server-confirmed — CHANGELOG 2026-07-17, v1.8.0 |
| 117 | eight-tier-recalibration | shipped | 2026-07-12 | FB-117/118 affine value recalibration `2e9d542` — CHANGELOG 2026-07-12 |
| 121 | anchors-resume | in-progress | 2026-07-12 | trade-engine-v2 |
| 122 | quickset-default | shipped | 2026-07-18 | FB-122 Quick Set as default method — CHANGELOG 2026-07-18, v1.9.0 `71e1a61` |
| 124 | format-aware-copy | shipped | 2026-07-17 | FB-124/139 cross-format tier copy — CHANGELOG 2026-07-17 |
| 126 | verify-persistence | shipped | 2026-07-12 | FB-126 Keychain JWT + silent replay `2b5e07a` — CHANGELOG 2026-07-12 |
| 127 | player-position-dup | shipped | 2026-07-12 | FB-127 position-strict DP↔Sleeper join `2b5e07a` — CHANGELOG 2026-07-12 |
| 129 | espn-sheet-keyboard | unknown | — | n/a |
| 130 | settings-nav-espn-cta | shipped | 2026-07-12 | contract live on `main`; explicitly preserved by #266's fix — CHANGELOG 2026-08-08 |
| 131 | apple-signin-error | shipped | 2026-07-12 | FB-131 applesignin entitlement `2b5e07a` — CHANGELOG 2026-07-12, v1.7.1–v1.7.3 |
| 132 | all-players-view | in-progress | 2026-07-17 | trade-engine-v2 |
| 134 | hide-toptier-question | in-progress | 2026-07-12 | trade-engine-v2 |
| 135 | tiers-header | in-progress | 2026-07-12 | trade-engine-v2 |
| 136 | quick-rank | in-progress | 2026-07-12 | trade-engine-v2 |
| 137 | quickset-format-search | in-progress | 2026-07-17 | trade-engine-v2 |
| 140 | chip-team-age | shipped | 2026-07-17 | FB-140 Waivers→FA label `8a00d0e` — CHANGELOG 2026-07-17, v1.8.1 |
| 141 | filler-threshold | shipped | 2026-07-17 | trade-engine-v2 |
| 142 | league-summary | shipped | 2026-07-17 | FB-142/144 league power rankings + roster tap-through — CHANGELOG 2026-07-17 |
| 143 | fa-finder | shipped | 2026-07-17 | FB-143 `backend/free_agent_service.py` — CHANGELOG 2026-07-17 |
| 145 | ktc-blend | shipped | 2026-07-18 | FB-145 KTC blend `ktc_blend_weight=0.5` — CHANGELOG 2026-07-18, v1.9.0 |
| 146 | send-gate-espn | shipped | 2026-07-18 | FB-146 Send-in-Sleeper ESPN gate — CHANGELOG 2026-07-18, v1.9.0 |
| 147 | trade-blocks | shipped | 2026-07-17/18 | trade-engine-v2 |
| 148 | tep-te-copy | shipped | 2026-07-18 | FB-148 `tep_te_uplift=1.18` — CHANGELOG 2026-07-18, v1.9.0 |
| 149 | espn-trade-away | shipped | 2026-07-25 | platform-routing proxy fix `52be577` (#149/#150) — CHANGELOG 2026-07-25 |
| 150 | replace-player | shipped | 2026-07-25 | platform-routing proxy fix `52be577` (#149/#150) — CHANGELOG 2026-07-25 |
| 151 | free-agents-fixes | shipped | 2026-07-25 | free-agents union + 503 `rosters_unavailable` — CHANGELOG 2026-07-25; regression class in DECISIONS |
| 152 | streak-increment | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 153 | otb-badge | in-progress | 2026-07-25 | worktree-agent-ae33eec5a00d24264 |
| 155 | multi-format-rank-sets | declined | 2026-08-08 | operator passed — CHANGELOG 2026-08-08 "Closed: … #155 (declined)" |
| 156 | trade-finding-hub | shipped | 2026-07-25 | teardown-remediation |
| 157 | calc-value-clarity | in-progress | ~2026-07-25 | n/a |
| 158 | picks-ownership | shipped | undated (PRD); cross-refs 2026-07 to -08 | `picks.owned_sync` flag |
| 159 | empty-tier-cta | in-progress | 2026-07-27 | teardown-remediation |
| 160 | tweener-spots | declined | 2026-08-08 | operator passed → `docs/feedback/backlog.md` — CHANGELOG 2026-08-08 |
| 161 | quickset-demote | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 162 | ranking-nav-loop | shipped | 2026-07-25 | `RankHomeScreen.choose` replace→navigate `fbb6f3e` — CHANGELOG 2026-07-25 |
| 163 | not-interested | shipped | 2026-07-25 | `not_interested` receive-side exclusion — CHANGELOG 2026-07-25 |
| 164 | trends-empty | in-progress | ~2026-07-25 | teardown-remediation |
| 166 | league-format-default | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 168 | looking-for-intents | shipped | 2026-08-08 | closed done — CHANGELOG 2026-08-08; PRD objection reconciled by #172 |
| 169 | outlook-league-summary | built-dark | 2026-07-23 | teardown-remediation / `outlook.odds` flag |
| 169 | position-impact | shipped | 2026-08-09 | `trade.position_impact` flag ON — graduated from mockup to build in the 2026-08-09 design-decision batch. **ID COLLISION with the row above**; see `docs/feedback/items/169-position-impact/status.md` — verify the real feedback-table ID before treating either as canonical |
| 172 | trade-intents | shipped | 2026-08-08 | `trades.intent_modes` flag ON in features.json — CHANGELOG 2026-08-08 wave |
| 173 | untouchables-discoverability | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 174 | package-constraint | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 175 | outlook-directional-suggestions | shipped | 2026-07-25 | `trade.outlook_direction` flag ON in features.json; `outlook_direction_mult` live per DECISIONS |
| 177 | mfl-auth-link | shipped | 2026-07-25 | `mfl.auth_link` flag ON in features.json; `POST /api/mfl/auth-link` `03e3e38` — CHANGELOG 2026-07-25 |
| 178 | fa-filter-regression | shipped | 2026-07-25 | `owner_id:null` orphan-roster fix — DECISIONS regression-class entry |
| 179 | fa-add-button | shipped | 2026-07-25 | teardown-remediation (worktree) |
| 180 | trade-send-validation | shipped | 2026-07-25 | `trade.send_in_sleeper` flag |
| 181 | league-rankings-primary | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 182 | fa-from-trades | shipped | 2026-07-25 | teardown-remediation (worktree) |
| 183 | hide-idp | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 184 | feedback-badge-count | in-progress | 2026-07-25 | n/a |
| 185 | pick-values-in-suggestions | shipped | 2026-07-25 | `_inject_owned_picks` primes Elo `1200 + 6*pick_value` `68920c3` — CHANGELOG 2026-07-25 |
| 186 | see-other-side | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 187 | avatar-dismiss | in-progress | ~2026-07-25 | teardown-remediation |
| 188 | feedback-fab-rule | in-progress | ~2026-07-25 | teardown-remediation |
| 189 | always-offer-fallback | shipped | 2026-07-25 | two-stage relaxed fallback for zero-card jobs — CHANGELOG 2026-07-25 |
| 190 | edit-in-calculator | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 191 | partner-rank-sync | shipped | 2026-07-25 | `rankings.cross_format_derive` (ships true) |
| 192 | ranked-badges | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 193 | chasing-shopping-conflict | in-progress | 2026-07-27 | teardown-remediation |
| 194 | pick-tag-and-remove-asset | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 195 | bar-stack-order | in-progress | 2026-07-27 | teardown-remediation |
| 196 | double-fab | shipped | 2026-07-27 | `6f2ac95` — CHANGELOG 2026-07-27 |
| 198 | upgrade-semantics | shipped | 2026-07-27 | `0106aba` — CHANGELOG 2026-07-27 (#198/#200) |
| 199 | switcher-add-league | shipped | 2026-07-27 | `6f2ac95` — CHANGELOG 2026-07-27 (#196/#199/#201) |
| 200 | summary-picks-missing | shipped | 2026-07-27 | `0106aba` — CHANGELOG 2026-07-27 (#198/#200) |
| 201 | mfl-format-detection | shipped | 2026-07-27 | `mfl_service.detect_scoring_format` `6f2ac95` — CHANGELOG 2026-07-27 |
| 202 | calc-prefill-focus | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 203 | picker-suggestions | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 204 | calc-value-bar | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 205 | design-tenets | research-only | 2026-07-28 | n/a |
| 207 | rookie-draft-detection | shipped | 2026-08-05 | `picks.rank_year_labels` flag ON; docs residual recovered per 2026-08-08 branch triage |
| 208 | ranks-follow-position-filter | in-progress | 2026-08-08 | worktree-agent-ac81596c5b45c68c9 |
| 210 | mfl-name-entities | shipped | 2026-08-01 | `_clean_text` html-unescape `572f5aa` — CHANGELOG 2026-08-01 |
| 211 | player-first-trades | mockup-only | 2026-08-08 | branch worktree-agent-aba27261d3ac0e30a — design lab `mockups/polish-lab-2026-08/trades-player-first.html`, no code |
| 212 | trade-dna-redesign | shipped | 2026-08-02 | teardown-remediation |
| 213 | find-a-trade-entry | shipped | 2026-08-01 | `572f5aa` — CHANGELOG 2026-08-01 (#210/#213/#217/#226) |
| 214 | stud-tax | shipped | 2026-08-05 | #214/#215 stud-tax retune `6577668` — CHANGELOG 2026-08-05 |
| 216 | featured-trade-window | shipped | 2026-08-02 | #216/#209 featured-trade window `ba78631` — CHANGELOG 2026-08-02 |
| 217 | quickset-back-btn | shipped | 2026-08-01 | `572f5aa` — CHANGELOG 2026-08-01 |
| 218 | hub-fit-to-screen | in-progress | 2026-08-01 | teardown-remediation (worktree, pending merge) |
| 220 | picks-chart-again | shipped | 2026-08-01 | pick-integrity batch `2b8ecca` — CHANGELOG 2026-08-01 |
| 222 | picks-in-fa | shipped | 2026-08-01 | pick-integrity batch `2b8ecca` — CHANGELOG 2026-08-01 |
| 223 | header-league-switcher | shipped | 2026-08-01 | teardown-remediation (worktree) |
| 225 | notifications-dechalk | shipped | ~2026-08-01 | teardown-remediation (worktree) |
| 226 | otb-overlap-give-side | shipped | 2026-08-01 | `PlayerCard.badgeSlot` `572f5aa` — CHANGELOG 2026-08-01 |
| 227 | no-pick-swap-cards | shipped | 2026-08-01 | `pick_swap_ok` gate `2b8ecca` — CHANGELOG 2026-08-01 |
| 228 | post-draft-pick-hiding | shipped | 2026-08-01 | pick-integrity batch `2b8ecca` — CHANGELOG 2026-08-01 |
| 229 | empty-states-progress | shipped | 2026-08-02 | #229/#230/#234 `4ac6673`, ships unflagged — CHANGELOG 2026-08-02 |
| 232 | rank-chooser-consolidation | shipped | 2026-08-02 | #232/#233 `2e4ca17` — CHANGELOG 2026-08-02 |
| 236 | dna-autosave | shipped | 2026-08-02 | teardown-remediation (worktree) |
| 237 | mirrored-filters | in-progress | 2026-08-02 | n/a |
| 238 | lineup-impact | shipped | 2026-08-03 | `optimal_starter_slots()` `c5f6f9c` — CHANGELOG 2026-08-03 |
| 239 | invite-universal-links | shipped | 2026-08-02 | associated-domains entitlement `c0e99ba` — CHANGELOG 2026-08-02 |
| 240 | idea-row-overlap | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 241 | duplicate-card | shipped | 2026-08-02 | never-two-cards invariant live on `main` and explicitly preserved by #317 — CHANGELOG 2026-08-14 |
| 242 | team-picker-height | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 243 | scroll-audit | shipped | 2026-08-03 | vertical-density campaign `4795a21`… — CHANGELOG 2026-08-03; status→shipped confirmed in a later entry |
| 244 | rank-launch-routing | shipped | 2026-08-05 | completion-aware Rank landing `deaa6b2` — CHANGELOG 2026-08-05 |
| 245 | acquire-tab | shipped | 2026-08-05 | Trades→Acquire `31c7731` + sweep `c795971` — CHANGELOG 2026-08-05 |
| 246 | guided-first-landing | shipped | 2026-08-05 | guided chip strip + `TradeDnaSheet.tsx` `69a8ff8` — CHANGELOG 2026-08-05 |
| 247 | format-tile | in-progress | 2026-08-05 | teardown-remediation |
| 248 | combined-bars | shipped | 2026-08-05 | ghost ticks + delta chips `2e3f61f` — CHANGELOG 2026-08-05 |
| 249 | matches-lock | in-progress | 2026-08-05 | teardown-remediation |
| 250 | team-targeting | shipped | 2026-08-05 | `opponent_user_id` on asset-ideas `7d259d4` — CHANGELOG 2026-08-05 |
| 251 | evener-placement | in-progress | 2026-08-05 | teardown-remediation |
| 253 | outlook-cleanup | in-progress | ~2026-08-05 | agent/253-outlook-cleanup (off teardown-remediation) |
| 257 | edit-full-sheet | shipped | 2026-08-08 | `trades.edit_full_sheet` flag ON (2026-08-08 wave) |
| 258 | mfl-name-entities | shipped | 2026-08-08 | backfill `_backfill_mfl_name_entities()`; merge `b682ee2` → `8c3c742`, build 91 |
| 260 | league-summary-key | shipped | 2026-08-08 | n/a — express legend fix (2026-08-08 wave) |
| 261 | risers-exclude-picks | in-progress | 2026-08-08 | worktree agent-a795927256b2f29e7 |
| 262 | rookie-ranking-broken | shipped | 2026-08-08 | n/a — fixed upstream by commit `be56567` |
| 263 | calc-tier-values | shipped | 2026-08-08 | n/a — additive `tier` on `/api/trade/values`; later superseded by #303/D-065 |
| 264 | manual-calc-trade-options | in-progress | 2026-08-08 | teardown-remediation (worktree) |
| 265 | mutual-match-threshold | shipped | 2026-08-08 | `leagueUnlocks.ts` threshold=1 — CHANGELOG + TEST_LEDGER 2026-08-08 wave |
| 266 | espn-link-buttons | shipped | 2026-08-08 | transitionEnd deferral; merge `b682ee2` → `8c3c742`, build 91 |
| 267 | pick-grid-live-totals | shipped | 2026-08-08 | n/a — covers #268/#267 (2026-08-08 wave) |
| 269 | sheet-targeting | shipped | 2026-08-09 | `trades.sheet_targeting` flag ON — covers #269/#276 (wave 3) |
| 270 | inline-trades-home | built-dark | 2026-08-09 | worktree-agent-acc329e0f3f9a3cd5, experiment `trades_home_inline` (strip + canvas variants, covers #270/#272) |
| 273 | future-year-picks | shipped | 2026-08-09 | n/a — covers #273/#274/#275 (wave 3) |
| 277 | tier-labels-appwide | shipped | 2026-08-09 | #277/#278/#280/#281 fable deep pass, 28 files — CHANGELOG 2026-08-09 wave 3 |
| 279 | aggregate-tier-labels | shipped | 2026-08-16 | experiment GRADUATED to all users (D-064) in the 2026-08-16 wave; no longer in features.json |
| 285 | pick-sums | shipped | 2026-08-09 | aggregate "≈X firsts" on players-only value — CHANGELOG 2026-08-09 |
| 286 | player-offers-flow | shipped | 2026-08-09 | `trades.player_offers_calc` flag ON — CHANGELOG 2026-08-09 (#286/#287/#288) |
| 289 | mfl-draft-room-ids | shipped | 2026-08-10 | PR #103 → `6c304c7`, v1.12.0 b98 — G1 of the #289–#294 batch |
| 290 | mock-draft-engine | shipped | 2026-08-10 | PR #103 → `6c304c7` — G2 **canonical** (#290/#291/#292) |
| 291 | mock-draft-interactive | shipped | 2026-08-10 | PR #103 — G2, canonical `290-mock-draft-engine/` |
| 292 | second-mock-draft | shipped | 2026-08-10 | PR #103 — G2, canonical `290-mock-draft-engine/` |
| 293 | picks-in-subsets | shipped | 2026-08-10 | PR #103 / `league.picks_always_counted` ON — G3 **canonical** (#293/#294) |
| 294 | picks-position-filters | shipped | 2026-08-10 | PR #103 — G3, canonical `293-picks-in-subsets/` |
| 295 | mock-user-not-in-draft | shipped | 2026-08-13 | PR #114 → `e71a654`, v1.13.3 b110 — covers #295/#296/#305 |
| 297 | lineup-impact-single-pin | shipped | 2026-08-12 | PR #108 → `f8acd71` — covers #297/#298 |
| 299 | league-tile-density | shipped | 2026-08-12 | PR #108 → `f8acd71` — covers #299/#302 |
| 300 | league-rankings-trade-candidates | shipped | 2026-08-12 | PR #112 → `5139b45`, v1.13.1 b106, both flags ON |
| 303 | calc-send-placement | shipped | 2026-08-16 | wave `20b40db`, v1.13.5 b114 — G1 **canonical** (#303/#306/#320) |
| 304 | positional-need-filter | shipped | 2026-08-16 | wave `20b40db` / `trade.presentment_rules` ON — G6 **canonical** (#304 #336 #339 #340 #341) |
| 307 | matches-link-routing | shipped | 2026-08-14 | PR #117 → `7057d86`, v1.13.4 b111 — covers #307/#308 |
| 309 | send-copy-stale | shipped | 2026-08-14 | PR #117 → `7057d86` — covers #309/#312/#314(partial)/#315/#316/#317 |
| 311 | lineup-values-nonsleeper | shipped | 2026-08-14 | PR #117 → `7057d86`, v1.13.4 b111 |
| 313 | 1qb-qb-cap | shipped | 2026-08-15 | PR #128 → `34ebd84` (branch `build-313`); prod tier read verified |
| 318 | awaiting-dismiss | shipped | 2026-08-14 | PR #117 → `7057d86` — backend + mobile halves, with #319 |
| 321 | espn-token-bleed | shipped | 2026-08-16 | wave `20b40db`, v1.13.5 b114 — G5 **canonical** |
| 322 | mock-draft-room-ui | shipped | 2026-08-16 | wave `20b40db` — G2 **canonical** (#322–#327) |
| 323 | mock-draft-pick-labels | shipped | 2026-08-16 | wave `20b40db` — G2, canonical `322-mock-draft-room-ui/` |
| 324 | mock-draft-picks-wrap | shipped | 2026-08-16 | wave `20b40db` — G2, canonical `322-mock-draft-room-ui/` |
| 325 | mock-draft-ticker-height | shipped | 2026-08-16 | wave `20b40db` — G2, canonical `322-mock-draft-room-ui/` |
| 326 | mock-draft-team-sheet | shipped | 2026-08-16 | wave `20b40db` — G2, canonical `322-mock-draft-room-ui/` |
| 327 | mock-draft-pool-search | shipped | 2026-08-16 | wave `20b40db` — G2, canonical `322-mock-draft-room-ui/` |
| 328 | mock-draft-pick-assignment | shipped | 2026-08-16 | wave `20b40db` — G3 **canonical** |
| 330 | offer-prefill | shipped | 2026-08-16 | wave `20b40db` — G4 **canonical** |
| 334 | matches-dismiss-latency | shipped | 2026-08-16 | wave `20b40db` — G9 **canonical** (#334 #335) |
| 335 | matches-filter-counts | shipped | 2026-08-16 | wave `20b40db` — G9, canonical `334-matches-dismiss-latency/` |
| 336 | exclude-actioned-trades | shipped | 2026-08-16 | wave `20b40db` — G6, canonical `304-positional-need-filter/` |
| 339 | pick-not-the-gap | shipped | 2026-08-16 | wave `20b40db` — G6, canonical `304-positional-need-filter/`; `pick_gap_frac` band still untuned |
| 340 | max-overpay-cap | shipped | 2026-08-16 | wave `20b40db` — G6, canonical `304-positional-need-filter/` |
| 341 | package-position-cap | shipped | 2026-08-16 | wave `20b40db` — G6, canonical `304-positional-need-filter/` |
| 357 | team-review | planned | 2026-08-19 | **canonical** for #357/#358/#359 — full doc set, build not started; blocked on Q-025 waivers. `trades.team_review` specced, not yet in features.json |
| 358 | team-review-link | planned | 2026-08-19 | canonical `357-team-review/` |
| 359 | team-review-link | planned | 2026-08-19 | canonical `357-team-review/` |
| 364 | team-review-fixes | shipped | 2026-08-20 | PR #152 `bc43b6f`, Render live, EAS build 124; IDP disclaimer names the unpriced slots |
| 365 | team-review-window-signals | planned | 2026-08-20 | `364-team-review-fixes/plan-remaining.md` §1 — bright-line ENGINE change (`outlook_alpha`), needs 3 decisions |
| 366 | team-review-tier-ladder | planned | 2026-08-20 | `364-team-review-fixes/plan-remaining.md` §2 — Handcuff needs an NFL depth chart FTF does not ingest |
| 367 | consensus-gap-direction | shipped | 2026-08-20 | canonical `364-team-review-fixes/`; sell direction fixed UPSTREAM (D-100), PR #152 — toggle half still planned §4 |
| 368 | team-review-partners | shipped | 2026-08-20 | canonical `364-team-review-fixes/`; route dropped the pick capital it computed, PR #152 |
| 369 | team-review-plan-beat | planned | 2026-08-20 | `364-team-review-fixes/plan-remaining.md` §3 |
| 370 | deck-repeat-liked-trades | planned | 2026-08-20 | `364-team-review-fixes/plan-remaining.md` §6 — TradesHome deck, NOT Team Review; needs a repro |
| 371 | outlook-as-window-driver | planned | 2026-08-20 | `364-team-review-fixes/plan-remaining.md` §5 — decide with #365 |
| 372 | window-composite | planned | 2026-08-20 | third report on the window beat (#365 → #371 → #372); composite re-weighting behind `trade.outlook_composite`, DARK, committed not merged on `claude/372-window-composite` |
| — | 2026-07-26-adjustments-breakdown | shipped | 2026-07-26 | n/a |
| — | 2026-07-26-asset-trade-ideas | shipped | 2026-07-26 | teardown-remediation / `trade.asset_ideas` ON |
| — | 2026-07-26-calc-eveners | shipped | 2026-07-26 | `eveners`/`adjustments`/`naive_totals` on `/api/trade/evaluate` — CHANGELOG 2026-07-26 |
| — | 2026-07-27-calc-polish | shipped | 2026-07-27 | calculator trio `fbd5561` — CHANGELOG 2026-07-27 |
| — | 2026-07-27-deck-player-changer | shipped | 2026-07-27 | deck player-changer `ec25407` — CHANGELOG 2026-07-27 |
| — | 2026-08-02-rankings-import | shipped | 2026-08-02 | `ranks.import` flag ON; `backend/rankings_import.py` `2e4ca17` — CHANGELOG 2026-08-02 |
| — | api-observability | shipped | 2026-08-09 | `obs.api_events` flag ON — operator-directed program, no feedback id |
| — | espn-webview-escape | shipped | 2026-08-09 | build 95 — operator-directed program, no feedback id; device walkthrough was owed at ship |

## Status distribution (167 rows, regenerated 2026-08-18)

| Status | Count |
|---|---|
| shipped | 124 |
| built-dark | 2 |
| planned | 0 |
| in-progress | 36 |
| mockup-only | 1 |
| research-only | 1 |
| open | 0 |
| declined | 2 |
| unknown | 1 |

167 rows against 167 folders in `docs/feedback/items/` — 1:1, verified
2026-08-18. Two rows share id **#169** (a real id collision, flagged inline);
the eight `—` rows are the six date-keyed operator asks plus the two named
programs, per [README.md](README.md) § Naming.

**The two `built-dark` rows are the only genuinely dark work left:** #169
`outlook-league-summary` (`outlook.odds: false` in `config/features.json`, so
`GET /api/league/outlook` is never called) and #270 `inline-trades-home`
(experiment `trades_home_inline`, overlay-only flags that never enter
features.json, tester-allowlist targeting). The single `unknown` is #129
`espn-sheet-keyboard`, which has no readable evidence in any source.

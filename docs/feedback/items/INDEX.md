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
> behind a default-off flag) · `in-progress` (built/fixed but not confirmed
> merged/shipped — worktree branch, "pending merge", "awaiting QA", etc.) ·
> `mockup-only` (design only, no code) · `research-only` (investigation/
> interview only) · `open` (spec/PRD only, not built) · `declined` (operator
> passed) · `unknown` (no readable evidence). Many `in-progress` rows below
> are individually-built worktree/isolated-branch items from the
> `teardown-remediation` era (2026-07-12 through 2026-08-08) whose status.md
> never states a merge to `main` — treat `in-progress` here as "built,
> merge-status unconfirmed from the doc alone," not "abandoned."

## Table

| id | slug | status | date | where |
|---|---|---|---|---|
| 78 | calc-suggestions | in-progress | 2026-07-17 | trade-engine-v2 |
| 117 | eight-tier-recalibration | in-progress | 2026-07-12 | trade-engine-v2 |
| 121 | anchors-resume | in-progress | 2026-07-12 | trade-engine-v2 |
| 122 | quickset-default | in-progress | 2026-07-17 | trade-engine-v2 |
| 124 | format-aware-copy | in-progress | 2026-07-17 | trade-engine-v2 |
| 126 | verify-persistence | in-progress | 2026-07-12 | trade-engine-v2 |
| 127 | player-position-dup | in-progress | 2026-07-12 | trade-engine-v2 |
| 129 | espn-sheet-keyboard | unknown | — | n/a |
| 130 | settings-nav-espn-cta | in-progress | 2026-07-12 | trade-engine-v2 |
| 131 | apple-signin-error | in-progress | 2026-07-12 | trade-engine-v2 |
| 132 | all-players-view | in-progress | 2026-07-17 | trade-engine-v2 |
| 134 | hide-toptier-question | in-progress | 2026-07-12 | trade-engine-v2 |
| 135 | tiers-header | in-progress | 2026-07-12 | trade-engine-v2 |
| 136 | quick-rank | in-progress | 2026-07-12 | trade-engine-v2 |
| 137 | quickset-format-search | in-progress | 2026-07-17 | trade-engine-v2 |
| 140 | chip-team-age | in-progress | 2026-07-17 | trade-engine-v2 |
| 141 | filler-threshold | shipped | 2026-07-17 | trade-engine-v2 |
| 142 | league-summary | in-progress | 2026-07-17 | trade-engine-v2 |
| 143 | fa-finder | in-progress | 2026-07-17 | trade-engine-v2 |
| 145 | ktc-blend | in-progress | 2026-07-17 | trade-engine-v2 |
| 146 | send-gate-espn | in-progress | 2026-07-17 | trade-engine-v2 |
| 147 | trade-blocks | shipped | 2026-07-17/18 | trade-engine-v2 |
| 148 | tep-te-copy | in-progress | 2026-07-17 | trade-engine-v2 |
| 149 | espn-trade-away | in-progress | 2026-07-25 | worktree-agent-ae33eec5a00d24264 |
| 150 | replace-player | in-progress | 2026-07-25 | worktree-agent-ae33eec5a00d24264 |
| 151 | free-agents-fixes | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 152 | streak-increment | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 153 | otb-badge | in-progress | 2026-07-25 | worktree-agent-ae33eec5a00d24264 |
| 155 | multi-format-rank-sets | open | undated | n/a |
| 156 | trade-finding-hub | shipped | 2026-07-25 | teardown-remediation |
| 157 | calc-value-clarity | in-progress | ~2026-07-25 | n/a |
| 158 | picks-ownership | shipped | undated (PRD); cross-refs 2026-07 to -08 | `picks.owned_sync` flag |
| 159 | empty-tier-cta | in-progress | 2026-07-27 | teardown-remediation |
| 160 | tweener-spots | open | 2026-07-25 | n/a |
| 161 | quickset-demote | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 162 | ranking-nav-loop | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 163 | not-interested | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 164 | trends-empty | in-progress | ~2026-07-25 | teardown-remediation |
| 166 | league-format-default | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 168 | looking-for-intents | open | 2026-07-25 | n/a |
| 169 | outlook-league-summary | built-dark | 2026-07-23 | teardown-remediation / `outlook.odds` flag |
| 169 | position-impact | mockup-only | 2026-08-08 | teardown-remediation (worktree) — **ID COLLISION with the row above**, see `docs/feedback/items/169-position-impact/status.md`; this row covers the unrelated "TE 10→17 ppg" trade-summary position-impact ask — verify the real feedback-table ID before treating either as canonical |
| 172 | trade-intents | built-dark | 2026-08-08 | worktree agent-a1f6f3577eb4bc80a / `trades.intent_modes` flag |
| 173 | untouchables-discoverability | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 174 | package-constraint | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 175 | outlook-directional-suggestions | built-dark | ~2026-07-25 | `trade.outlook_direction` flag |
| 177 | mfl-auth-link | built-dark | 2026-07-25 | `mfl.auth_link` flag |
| 178 | fa-filter-regression | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 179 | fa-add-button | shipped | 2026-07-25 | teardown-remediation (worktree) |
| 180 | trade-send-validation | shipped | 2026-07-25 | `trade.send_in_sleeper` flag |
| 181 | league-rankings-primary | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 182 | fa-from-trades | shipped | 2026-07-25 | teardown-remediation (worktree) |
| 183 | hide-idp | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 184 | feedback-badge-count | in-progress | 2026-07-25 | n/a |
| 185 | pick-values-in-suggestions | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 186 | see-other-side | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 187 | avatar-dismiss | in-progress | ~2026-07-25 | teardown-remediation |
| 188 | feedback-fab-rule | in-progress | ~2026-07-25 | teardown-remediation |
| 189 | always-offer-fallback | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 190 | edit-in-calculator | shipped | 2026-07-25 | teardown-remediation (#156 batch) |
| 191 | partner-rank-sync | shipped | 2026-07-25 | `rankings.cross_format_derive` (ships true) |
| 192 | ranked-badges | in-progress | 2026-07-25 | teardown-remediation (worktree) |
| 193 | chasing-shopping-conflict | in-progress | 2026-07-27 | teardown-remediation |
| 194 | pick-tag-and-remove-asset | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 195 | bar-stack-order | in-progress | 2026-07-27 | teardown-remediation |
| 196 | double-fab | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 198 | upgrade-semantics | in-progress | 2026-07-27 | teardown-remediation / `trade.asset_ideas` |
| 199 | switcher-add-league | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 200 | summary-picks-missing | in-progress | 2026-07-27 | teardown-remediation |
| 201 | mfl-format-detection | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 202 | calc-prefill-focus | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 203 | picker-suggestions | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 204 | calc-value-bar | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| 205 | design-tenets | research-only | 2026-07-28 | n/a |
| 207 | rookie-draft-detection | in-progress | 2026-08-05 | worktree-agent-afae520a937d45e74 / `picks.rank_year_labels` ON |
| 208 | ranks-follow-position-filter | in-progress | 2026-08-08 | worktree-agent-ac81596c5b45c68c9 |
| 210 | mfl-name-entities | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 212 | trade-dna-redesign | shipped | 2026-08-02 | teardown-remediation |
| 213 | find-a-trade-entry | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 214 | stud-tax | in-progress | 2026-08-05 | teardown-remediation (worktree) |
| 216 | featured-trade-window | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 217 | quickset-back-btn | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 218 | hub-fit-to-screen | in-progress | 2026-08-01 | teardown-remediation (worktree, pending merge) |
| 220 | picks-chart-again | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 222 | picks-in-fa | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 223 | header-league-switcher | shipped | 2026-08-01 | teardown-remediation (worktree) |
| 225 | notifications-dechalk | shipped | ~2026-08-01 | teardown-remediation (worktree) |
| 226 | otb-overlap-give-side | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 227 | no-pick-swap-cards | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 228 | post-draft-pick-hiding | in-progress | 2026-08-01 | teardown-remediation (worktree) |
| 229 | empty-states-progress | in-progress | 2026-08-02 | worktree-agent-af4b9c0445be5f5a5 (pending merge) |
| 232 | rank-chooser-consolidation | in-progress | 2026-08-02 | teardown-remediation (worktree) |
| 236 | dna-autosave | shipped | 2026-08-02 | teardown-remediation (worktree) |
| 237 | mirrored-filters | in-progress | 2026-08-02 | n/a |
| 238 | lineup-impact | in-progress | 2026-08-03 | teardown-remediation (worktree) |
| 239 | invite-universal-links | in-progress | ~2026-08-02 | teardown-remediation (worktree, pending merge+deploy) |
| 240 | idea-row-overlap | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 241 | duplicate-card | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 242 | team-picker-height | in-progress | 2026-08-02 | teardown-remediation (pending merge) |
| 243 | scroll-audit | in-progress | 2026-08-03 | teardown-remediation (worktree, implied) |
| 244 | rank-launch-routing | in-progress | 2026-08-05 | teardown-remediation |
| 245 | acquire-tab | in-progress | 2026-08-05 | teardown-remediation (worktree) |
| 246 | guided-first-landing | in-progress | 2026-08-05 | teardown-remediation (worktree) |
| 247 | format-tile | in-progress | 2026-08-05 | teardown-remediation |
| 248 | combined-bars | in-progress | 2026-08-05 | teardown-remediation (worktree) |
| 249 | matches-lock | in-progress | 2026-08-05 | teardown-remediation |
| 250 | team-targeting | in-progress | 2026-08-05 | worktree agent-a0d2eb20f30acda42 |
| 251 | evener-placement | in-progress | 2026-08-05 | teardown-remediation |
| 253 | outlook-cleanup | in-progress | ~2026-08-05 | agent/253-outlook-cleanup (off teardown-remediation) |
| 258 | mfl-name-entities | in-progress | 2026-08-08 | worktree-agent (from origin/main @ 6c30dd2) |
| 261 | risers-exclude-picks | in-progress | 2026-08-08 | worktree agent-a795927256b2f29e7 |
| 262 | rookie-ranking-broken | shipped | 2026-08-08 | n/a — fixed upstream by commit `be56567` |
| 264 | manual-calc-trade-options | in-progress | 2026-08-08 | teardown-remediation (worktree) |
| 265 | mutual-match-threshold | in-progress | 2026-08-08 | worktree-agent-a5c5a806d0d32845e |
| 266 | espn-link-buttons | in-progress | 2026-08-08 | worktree-agent (from origin/main @ 6c30dd2) |
| 277 | tier-labels-appwide | in-progress | 2026-08-09 | worktree agent-a398ef6c79029326f (covers #277/#278/#280/#281 + #263 remainder) |
| 279 | aggregate-tier-labels | built-dark | 2026-08-09 | branch worktree-agent-a1e9ac18717f11781, experiment `aggregate_tier_labels` |
| — | 2026-07-26-adjustments-breakdown | shipped | 2026-07-26 | n/a |
| — | 2026-07-26-asset-trade-ideas | shipped | 2026-07-26 | teardown-remediation / `trade.asset_ideas` ON |
| — | 2026-07-26-calc-eveners | in-progress | 2026-07-26 | teardown-remediation (worktree) |
| — | 2026-07-27-calc-polish | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| — | 2026-07-27-deck-player-changer | in-progress | 2026-07-27 | teardown-remediation (worktree) |
| — | 2026-08-02-rankings-import | in-progress | 2026-08-02 | teardown-remediation (worktree) |

## Status distribution (120 rows)

| Status | Count |
|---|---|
| shipped | 19 |
| built-dark | 3 |
| in-progress | 93 |
| mockup-only | 0 |
| research-only | 1 |
| open | 3 |
| declined | 0 |
| unknown | 1 |

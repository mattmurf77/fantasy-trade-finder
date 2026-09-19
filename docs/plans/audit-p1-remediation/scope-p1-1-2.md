# Feature Scope — P1-1 / P1-2: share artifacts carry a link, and the two dead landings get callers

<!--
Copied from docs/templates/feature-scope.md. Every section is answered or explicitly
WAIVED with a reason. Build plan: docs/plans/audit-p1-remediation/plan-p1-1-2.md
-->

**Date:** 2026-08-11
**Entry point:** mobile UX audit findings **P1-1 (A-10)** and **P1-2 (A-11)** —
`docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` §P1,
`06-resolutions.md` rows A-10/A-11
**Builder:** planning session, worktree `ftf-p1-remediation`, branch `p1-remediation-2026-08-11` @ `ab9368f`
**Operator sign-off on waivers:** **pending** — waivers W-1 … W-4 below, plus nine operator
checkpoints in the plan's [Operator checkpoints](plan-p1-1-2.md#operator-checkpoints) section.
**Rigor level:** full gates. No express lane was declared, and this change touches a
deep-link route alias and the analytics taxonomy — both named bright lines in root `CLAUDE.md`
§Conventions, so express would not apply without an explicit confirming yes anyway.

---

## 1. Analytics scope

**(a) New events specced** — and, unusually, two *existing* events are being repaired: both are
firing into the ingest allowlist and being discarded today.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `calc_trade_shared` **(register — currently DROPPED)** | `mode` (`live`\|`demo`), `landing` (bool — rung A reached), `surface` | Calculator text share completes (not dismissed) | mobile |
| `trade_card_shared` **(widen props — `landing` currently STRIPPED)** | `trade_id`, `channel`, **`landing`**, **`surface`** | Liked-trade share completes | mobile |
| `tier_board_shared` **(new)** | `position` (QB\|RB\|WR\|TE), `format` (`1qb_ppr`\|`sf_tep`), `surface` (`tiers`) | Tier-board save-toast Share action tapped | mobile |
| `share_package_created` **(new)** | `surface`, `give_n`, `receive_n`, `outcome` (`ok`\|`rate_limited`\|`demo`\|`failed`) | Every `POST /api/share/package` attempt resolves | mobile |

`surface` value set (cross-client enum): `calc_live` \| `calc_in_league` \| `trades_liked` \| `tiers`.

**Evidence for the two repairs** (this is the NULL-`platform`-class trap the feature gates
exist for):
- `calc_trade_shared` is fired at `mobile/src/screens/TradeCalculatorScreen.tsx:535` and is
  absent from `ALLOWED_CLIENT_EVENTS` (`backend/analytics_taxonomy.py:38-99`); the ingest path
  is default-deny and drops the whole envelope (`backend/analytics_ingest.py:379-383`).
- `trade_card_shared` is allowed (`analytics_taxonomy.py:74`) but its prop set is
  `{trade_id, channel}` (`:222`), while `TradesScreen.tsx:2760-2766` sends `{trade_id, landing}`
  — `landing` is stripped at `analytics_ingest.py:384-389`, and `channel` is never sent by
  either client.

**Ordering rule:** server-side registration deploys **before** the mobile build that fires the
names. Guarded by a pytest assertion, not by discipline (see §3).

Follow-through: `docs/data-dictionary.md` **n/a** (no stored schema — these are `user_events`
rows under the existing envelope); analytics tracking-plan addendum under
`docs/business/analytics/` **required**, and it must record that share telemetry has been
absent since these events shipped.

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** `shared_packages` already exists
  (`backend/database.py:1417, 10653-10654`) and is already documented
  (`docs/data-dictionary.md:856`, including the public-by-URL privacy note and the
  keep-indefinitely retention rule). No migration. The client-side mint cache is in-memory
  only, keyed on the package's id list — no AsyncStorage, no TTL to reason about.
- **New/changed feature flags:** **none.**
  Reuses `growth.share_landing`, which already exists in `FLAG_KEYS`
  (`backend/feature_flags.py:272`), is already exposed to clients from that same block, is
  already `true` in `config/features.json:125` and in `backend/tests/fixtures/flags/release.json:126`,
  and already gates the exact server routes involved (`backend/server.py:16838, 16881, 16904`).
  **Justification for not adding one:** a new flag is itself a surface change (bright line), and
  it would gate a fix whose entire premise is that these paths convert zero today. Default state
  unchanged; no graduation criterion needed because nothing new is being graduated.
  **Consequence, stated deliberately:** the flag is ON in production, so this work is
  user-visible on merge — there is no dark period. That is [OC-1](plan-p1-1-2.md#operator-checkpoints),
  and it is an operator decision, not an assumption baked in here.
- **New env vars / `model_config` keys:** **none.**
  **Ship-the-knob / deploy-free rollback lever:** `growth.share_landing` → `false` via
  `config/features.json`. Flipping it reverts mobile to the pre-change URLs (the flag-off
  branches are preserved byte-identical) *and* 404s the package routes server-side. One lever
  covers both halves. Note it does **not** cover `/s/tiers` + `/og/tiers`, which are unflagged
  server-side (`server.py:16759-16779`, `:16663-16680`) — the flag only suppresses the mobile
  affordance. That gap is [OC-3](plan-p1-1-2.md#operator-checkpoints).

## 3. Test scope (mobile test platform)

- **New flow:** `mobile/.maestro/flows/growth/share-links.yaml` (`# flags: release`,
  `# profile: standard`) — three blocks:
  1. calculator live mode → the resolved share link is present and matches `/s/p/` (**rung A**);
  2. same path with `fail_next` on `POST /api/share/package` returning the route's real 429 body
     (`{"error":"rate_limited","message":"Too many shares — try again later."}`, read from
     `server.py:16865-16866`, per README law 12) → the link is *still* present and matches
     `?ref=` (**rung B**) — this is the block that proves an artifact is never link-free;
  3. tier board → save → the toast's Share action is visible.
- **Extended flow:** none. `flows/smoke/07-calculator.yaml` and `flows/smoke/04-tiers.yaml`
  cross this surface but assert nothing that moves; they are left untouched and **run** as part
  of the tier-1 gate rather than assumed green.
- **Explicit non-assertion (W-1, waived with reason):** **no flow taps a share button.** The
  iOS share sheet is `UIActivityViewController`, out of process; README law 20
  (`mobile/.maestro/README.md:159-166`) records a native dialog poisoning every later step. The
  fix is designed around this — the resolved URL is rendered *inside* the app
  (`testID="calc.share-link"`) specifically so the thing that was broken is assertable without
  opening the sheet. The sheet itself, the produced PNG, and the OG preview are covered by
  manual tests 10–18 in the plan.
- **Pre-existing-flow audit (required by the build brief):** `grep -rn "share" mobile/.maestro/`
  returns **only prose** — no flow references `calc.share-image` or any share affordance.
  **No existing flow asserts the bug**, so none needs correcting in the same commit.
- **`testID`s added:** `calc.share-link`, `share.card-url`, `tiers.share-toast-action`
  (must pass `mobile/scripts/testid-lint.sh`). `share.card-url` sits on the off-screen capture
  surface (`ShareTradeImage.tsx:130`, `left: -9999`) and is therefore **not** Maestro-assertable
  — recorded here so nobody later adds a flaky assertion for it. A `testID` passthrough is added
  to `Toast`'s action button (`mobile/src/components/Toast.tsx:111-124`).
- **Capture delta:** `calc` and `tiers` — and `trades` if [OC-2](plan-p1-1-2.md#operator-checkpoints)
  is taken. Derived from `screens/manifest.json`: `calc.source` = `TradeCalculatorScreen.tsx` +
  `InLeagueCalculator.tsx`; `tiers.source` = `TiersScreen.tsx`; `trades.source` =
  `TradesScreen.tsx`. `quick-set` is **not** in the delta — the Quick Set completion `Alert` is
  deliberately untouched ([OC-5](plan-p1-1-2.md#operator-checkpoints)).
  Run `mobile/scripts/screen-capture.sh --screen calc --screen tiers [--screen trades]`;
  confirm with `screen-freshness.sh` before and after; eyeball every shot (law 23).
- **Smoke-suite impact:** 2 of 11 cross the surface — `07-calculator.yaml` (reaches
  `calc.verdict`, one scroll above the actions row) and `04-tiers.yaml` (asserts
  `tiers.save-btn`). Both expected green; both **run**.
- **Backend pytest added/updated:**
  - `backend/tests/test_share_package.py` — new cases: the four event names are in
    `ALLOWED_CLIENT_EVENTS` and each name's full prop set survives `POST /api/events`
    unstripped. This is the standing regression guard for the silent-drop class.
  - `backend/tests/test_universal_links.py` — new case: AASA still claims `/s/*`, so the new
    client-side `/s/tiers/*` alias has a matching server claim.
  - Existing `test_share_package.py` route cases stay green unchanged (no route is modified).
- **Mobile unit tests:** **WAIVED (W-2)** — there is no jest harness in `mobile/`
  (`mobile/package.json` has no test script). Mobile verification is `tsc --noEmit` + Maestro +
  manual, which is the project's standing state, not a new gap introduced here.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **YES** | No route changes. Two rows become wrong-by-omission: `:546` (`POST /api/share/package`) — record that mobile now calls it and from which surfaces; `:544` (`GET /s/tiers/<pos>/<username>`) — record that it is **unflagged**, is now linked from the mobile tier board, and that `/s/*` is AASA-claimed so clients must alias it. |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **YES** | New convention, and a load-bearing one: **any path shape claimed by AASA must have a matching `rewriteUniversalPath` alias, or the link opens the app onto the fallback toast** (`deepLinks.ts:353-364`). `/s/*` is claimed wholesale (`server.py:8094-8107`), so this binds every future `/s/…` route. |
| `docs/architecture.md` (module wiring / data flow changed) | **n/a** | No backend module added, removed, or re-wired; the mobile addition is one utility module (`shareLinks.ts`) inside an existing layer. |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | No new module, client, or major flow — three existing surfaces gain a call to an existing route. |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **YES** | Two share-URL shapes become a real cross-client contract: `<base>/s/p/<id>?ref=<u>` and `<base>/s/tiers/<pos>/<u>?fmt=<f>`. Mobile's `shareLinks.ts` must match web's `buildTierShareUrl` (`web/js/app.js:5285-5295`) exactly, including the `fmt`-omitted-when-`1qb_ppr` rule and the QB/RB/WR/TE-only position set (`og_image.py:304-309`). Also records the `surface` enum used by the analytics events. |
| `docs/glossary.md` (new domain term) | **YES** | **share package** (a `/s/p/<id>` snapshot of an arbitrary give/receive build) and **share link ladder** (the rung A/B/C degradation) — both land in code as named concepts. |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | **YES — `DECISIONS.md`** (re-check next id after the P0 merge; P0-3 also claims `D-011`) | Four choices: (1) reuse `growth.share_landing` rather than mint a flag, accepting that this ships live; (2) the link ladder degrades rather than blocking the share, so no artifact is ever link-free; (3) the tier affordance is the save toast, **not** the Quick Set native `Alert` (untestable, already carries a next-step); (4) web stays unwired this round. No ADR — none of these rises to architectural weight. |

**Additional docs not in the template's table but triggered by `docs/CLAUDE.md`:**

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/data-dictionary.md` | **n/a** | No `backend/database.py` schema change; `shared_packages` already documented at `:856`. |
| `docs/config-reference.md` | **YES** | `growth.share_landing` (`:251`) currently describes only `/s/trade` + `/s/tiers` URL composition. Rewrite: it additionally gates the package mint and the tier-board affordance, and — critically — **it is already ON**, so the entry must say this ships live on merge. |
| `docs/runbook.md` | **YES** | New short section: mint failures are expected and benign (ladder degrades to `?ref=`); the 20/user/hour cap (`server.py:16812`) and its 429 body; the diagnosis order when shares stop carrying `/s/p/` links (flag → `dropped_unknown_type` health counter → route 404). |
| `docs/coding-guidelines.md` | **n/a** | No new behavioural rule beyond the DECISIONS entries. |
| `living-memory/GOTCHAS.md` | **YES** (re-check next id after the P0 merge) | `captureRef` snapshots the **rendered** tree, so an awaited value must be committed *and painted* before capture — a mint cannot live in the same `share()` body. Plus the comment-rot pattern: two files carried the same false "no `/s/` route exists" claim for weeks (same class as A-33). |
| `docs/business/analytics/` tracking plan | **YES** | Addendum for the four events, including that `calc_trade_shared` has been dropped and `trade_card_shared.landing` stripped since they shipped. |
| `docs/design/design-system.md` + `components.md` | **read, not edited** | Footer text and the toast action reuse existing Chalkline tokens (`type.label`, `chalk.faint`, the `Toast` action spec at `Toast.tsx:170-171`). No new component, no new token, no radius/accent exception. |
| `docs/feedback/items/<id>-<slug>/` | **n/a** | Audit-driven, not feedback-driven. Home is `docs/plans/audit-p1-remediation/`. |
| `docs/recovery/` | **at sweep** | Required before the P1 worktree/branch is removed, per root `CLAUDE.md` — capture tip sha, verify by content against `origin/main`, then delete. Not a build-time doc. |
| `living-memory/CHANGELOG.md`, `NEXT.md`, `HANDOFF.md`, `TEST_LEDGER.md`, `DEPENDENCIES.md` | **CHANGELOG/NEXT/TEST_LEDGER YES at ship; DEPENDENCIES n/a** | No dependency added — `react-native-view-shot@4.0.3` is already installed and already used by this component. |

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 1** — mobile screen change (`TradeCalculatorScreen`,
  `InLeagueCalculator`, `TiersScreen`, and `TradesScreen` if
  [OC-2](plan-p1-1-2.md#operator-checkpoints) is taken), so: **full smoke suite (11 flows) + the
  new `flows/growth/share-links.yaml`**, plus `screen-capture.sh` for `calc`, `tiers`
  (+`trades`).
  Backend changes on their own would be tier 4 (taxonomy only, CI-covered), but the mobile
  change dominates and the higher tier governs.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json` written
  after the run. Enforced locally by `githooks/pre-push`; `FTF_SKIP_SIM_GATE` is **not** used.
- **Operator deviation from the matrix:** none proposed.
- **Merge ordering (precondition, not a deviation):** `p0-remediation-2026-08-10` merges to
  `main` first; this branch rebases onto it. Overlaps are enumerated in the plan's
  [Risks and cross-item collisions](plan-p1-1-2.md#risks-and-cross-item-collisions) — chiefly
  `backend/analytics_taxonomy.py` (P0-3 §B4 adds invite events to the same frozenset),
  `mobile/src/utils/deepLinks.ts` (different functions), `mobile/src/screens/TradesScreen.tsx`
  (P0-2's `job.error` work, different region), and shared docs. `DECISIONS.md` / `GOTCHAS.md`
  next-ids must be re-read post-merge.

---

## Waivers (each answered, none silent)

| # | Waived | Reason |
|---|---|---|
| **W-1** | No Maestro step taps a share button or asserts the native share sheet | `UIActivityViewController` is out of process; README law 20 records a native dialog poisoning every subsequent step. Mitigated by design: the resolved URL renders in-app (`calc.share-link`) so the broken behaviour is assertable without the sheet. Sheet, PNG, and OG preview covered by manual tests 10–18. |
| **W-2** | No mobile unit tests | No jest harness exists in `mobile/`. Standing project state, not a gap introduced here. |
| **W-3** | No web change, despite two dead URL builders at `web/js/app.js:5285-5301` | Web share placement is a design question the mobile audit did not cover; mixing it in doubles the review surface for zero mobile benefit. Filed as follow-up ([OC-9](plan-p1-1-2.md#operator-checkpoints)). |
| **W-4** | The Quick Set walk's completion moment gets no share affordance, despite the audit naming it | It is a native `Alert` (`QuickSetTiersScreen.tsx:272-286`) — untestable by Maestro and already carrying a "Quick rank" next-step. The save toast one screen later covers the same board. Revisit is [OC-5](plan-p1-1-2.md#operator-checkpoints). |

## Bright lines touched (enumerated per root `CLAUDE.md` §Conventions)

| Bright line | Touched? | What |
|---|---|---|
| **Routes** | **YES** | One deep-link alias: `/s/tiers/<pos>/<username>` → `app/rank/tiers` in `rewriteUniversalPath` (`deepLinks.ts:189-199`). No server route added, renamed, or contract-changed. No new AASA claim (`/s/*` is already claimed), therefore **no CDN lead time**. |
| **Schema** | no | none |
| **Feature-flag surfaces** | no | reuses `growth.share_landing`; no key added, no default changed |
| **Analytics events** | **YES** | 2 new names, 1 name registered that was being dropped, 1 prop set widened |

Because two bright lines are crossed, this is **not** a quick fix and the full gates stand.

# Changelog — Fantasy Trade Finder

> **Purpose:** cross-session memory. Capture what was built, decisions that affect future work, and known gaps.
>
> Retention: last 10 entries live here; older entries are in [archive/](archive/) — grouped by quarter. Per-entry cap ~1,200 bytes; overflow detail belongs in docs/plans/ or the PR body, linked.
>
> **Read at:** session start.
> **Write at:** session end.
>
> Companion files: [`HANDOFF.md`](HANDOFF.md) for forward-looking; [`../docs/`](../docs/) for per-feature reference updates.

---


## 2026-08-23 — Fleeced the ram: mascot decided, art built, swap built dark behind `onboarding.mascot_ram`

**Not shipped to anyone.** Built on `claude/ram-mascot-fleeced`, CI green, flag `false`. Reaching the operator needs a
build plus an experiment that has not been created.

**Decided.** [D-155](DECISIONS.md) — the ram is the mascot *and* the guide avatar, **named Fleeced**;
[Q-009](OPEN_QUESTIONS.md) closed after 15 months as "neither — the ram", its premise having been contradicted by the
shipped icon all along. The raster rule gains a scoped exception (mascot sprites only, under `mascot/ram/`, ≤60 KB).
[D-156](DECISIONS.md) — painted at every size, chosen **against** the measured 44 pt legibility evidence and recorded
that way so nobody later "fixes" it; plus the sizing rule: mascot art is inset to **70 % of box width**, because `size`
is the width of the *box*, not the character, and the Analyst only ever fills 62–90 pt of its 96 pt box.

**Built.** Six painted poses generated one at a time from one approved hero (`nano_banana_pro` / `nano_banana`), alpha
cut, exported `@1x/@2x/@3x` as 256-colour PNG-8 — worst sprite **15.6 KB** against a 60 KB budget, whole set 167 KB.
`AnalystAvatar` becomes a flag switch; all three call sites and the tour script are untouched. New guard
`check-mascot-ram.js`, sabotage-tested. Three self-contained lab pages under `mockups/avatar-lab/`.

**Two corrections worth carrying forward.** (1) `BUBBLE_ANCHOR` is **exported and never consumed** — `AnalystGuide`
lays the bubble out *beside* the avatar in a flex row, not above it with a tail. The "anchor moves off-centre" decision
had nothing to move, and the avatar lab's horn-clash test describes the layout the brief *described*, not the one that
ships. (2) The ID reservation flagged at D1 was correct and then some: `main` took **D-153** (W6-B) *and* **D-154**
(`trade.full_sweep`) while this work was in flight, so both entries renumbered on rebase.

**Also fixed:** `test_release_flags_mirror_features_json` was already failing on `origin/main` (`trade.full_sweep` lit
without updating the mirror fixture). CI was red for everyone; one value corrected.

## 2026-08-23a — Full sweep SHIPPED and LIT: the deck now scores every leaguemate (`trade.full_sweep`)

The [full-sweep build](../docs/plans/full-sweep/plan.md) ([D-154](DECISIONS.md), ledger [2026-08-22j](TEST_LEDGER.md)) merged to `main` with the flag flipped **true** in the same PR, by operator instruction ("merge and flip it on"). Both opponent loops now skip the `global_target` early exit, so every eligible leaguemate is generated against and `_dedup_and_sort` ranks the league globally; wall-clock rail `full_sweep_budget_s` = 30 s (the v3 pair path has no deadline of its own); per-opponent keep is the knob `exploration_base_per_opp` (5.0, clamped ≥ 1). Expected in FFV3: every deck reaches all 11 partners (was ~6, fixed set in single-board leagues); deck grows toward `bakeoff_deck_limit` (prod 60); `gen_ms` ≈ 2×. **Owed:** the scope §3 post-flip verification (count partners, read `gen_ms`, prove the kill switch). Kill switch: flag → false + `POST /api/feature-flags/reload`. Review PR #181 (three trade-model reports, Q-030/G-058) merged first, same day.

## 2026-08-22m — Trade-model restrictiveness review, two reads (docs + living-memory only)

Two operator-facing HTML reports in `docs/reviews/`: [`…restrictiveness.html`](../docs/reviews/2026-08-22-trade-model-restrictiveness.html) (three parallel Opus audits + prod telemetry) and [`…second-read.html`](../docs/reviews/2026-08-22-trade-model-second-read.html) (a second model re-verifying the first). **No engine line changed.** Knobs read from prod `model_config`.

Carry forward: the deck reaches a median **6 of 11** partners (sweep breaks at `global_target`) and in single-board leagues it is the **same six every time** — 5/13 and 7/13 leaguemates never served. The bake-off **is serving** (`bakeoff_serve_interleaved = 1`, contra prior memos): `gen_v2` 57% liked vs `current` 6% on the same basis. **Like rate is a viewer-appeal meter** (consensus 30% vs divergence 19%); two-sided scoreboard: 465 likes → 15 matches → 3 accepted; 1 partial / 0 exact of 127 linked real trades. `consensus_both_ways` delivers ≈+18%, not 2×. (A first-draft "`calc_opened` is dead" claim was retracted: 3 of 525 rows set, 7 taps ever.)

Write-back: [Q-030](OPEN_QUESTIONS.md), [G-058](GOTCHAS.md), `docs/reviews/CLAUDE.md` rows.

## 2026-08-22l — #384 W8: the REAL cause of the blank Analyst bubble, found in the simulator (v1.16.2)

Build 127 was still blank at Set outlook. W7's placement theory was wrong. Lead built for the iOS
simulator (one-off, D-056 still stands) and reproduced it on the sign-in username beat: **every
targeted beat after another beat drew its ring and no band.** Cause: the band unmounts while a
targeted spotlight is pending; the native-driven entry spring started on ACTIVATION ran against the
unmounted band, and the remounted band initialised from the stale JS value (0) and never updated.
Fix: spring keyed on the band rendering, JS-driven. Verified in the simulator n10 → n16 incl. the
failing Set outlook beat. Two more found the same way: the auto-tour died behind the deck's
`s2.wait` bubble and — worse — recorded the first-visit receipt with zero beats shown (fixed:
starting tour tears down any standing bubble; receipt only when a beat was shown); "Show me around"
from the In-league tab could not pass n10 (fixed: the tab tap advances n10 even when selected).
Scroll-into-view reserves tab-bar chrome. Guards: spotlight §14a–f, calc-tour 29/41/42. Gates: tsc
· 76/76 · lint. Deck half still unverified on device (unverified simulator session 403s on
generation).

**Second pass, same branch, before the build was cut.** Three first-landing defects reproduced and
fixed: the auto-start's `InteractionManager` fallback fired before the header laid out (now a 1 s
timer behind `transitionEnd`); the band latched its OFFSET from that early frame (side stays
latched, offset live; latch waits for an on-screen cutout); tearing down the deck's stale bubble let
TradesScreen request N2 synchronously and take n10's slot (hold + owned ids now go up BEFORE the
teardown — calc-tour 43). Then a fourth, found because the simulator had auto-started the tour
more than three times: with n10/n11 at `maxDisplayCount` the runner stepped over them and the
auto-tour OPENED ON n12's DEGRADE LINE with the page still on Real values — an auto-start now
refuses up front when n10 is capped (calc-tour 44/44a; "Show me around" still resets). The
operator's device has abandoned the tour repeatedly, so on 128 expect NO auto-tour — use "Show me
around". Verified in the simulator on the first landing: n10 rings the In-league tab with the band
beneath it, n11 rings the outlook row with its CTA. Session cost: a `pod install` re-sync left the
DEBUG Hermes under a `Release` marker and the app SIGSEGV'd at launch — [G-057](GOTCHAS.md).
Shipped v1.16.2 / EAS 128.

## 2026-08-22k — #384 W7: the tour as the operator actually saw it on device — placement, timing, targets, Next buttons (v1.16.1)

First runtime evidence for #384 came from the operator on build 126, six reports. One Opus
package, lead-reviewed. **Cause of the big one:** `AnalystGuide` parked the avatar band at a fixed
`top: 54` whenever the target sat in the lower 60% of the window — every calculator beat after the
outlook — on the one screen with a native-stack header; the deck (no header) showed it. Replaced by
`solveBandPlacement()`: the band sits **adjacent to its ring** (above if it clears `insets.top`,
else below, floored at the top inset; else the legacy bottom band), height measured by `onLayout`
and latched per step. **First-landing misplacement** was measure timing: auto-start now waits for
`transitionEnd` (InteractionManager fallback) and the calculator announces `onLayout` +
`onContentSizeChange` as well as scroll. **Three new targets:** `calc.outlook-row` (n11),
`trades.swap-first` (n20), `trades.send-btn` (n23/n23b). **Scroll-into-view:** `guideTargets`
scroller registry (calculator + deck); a targeted step below the fold is scrolled up once. **Next /
Done buttons** replace tap-anywhere on all eleven talk beats (the full-screen tap-catcher was what
broke scrolling); n10/n18 stay action beats. Guard hardening found a pre-existing hole:
`registerGuideTarget\('id'` matched `unregisterGuideTarget('id')` — now word-bounded. Gates: tsc ·
76/76 guards · lint (backend untouched). Shipped as v1.16.1 (EAS build 127).

## 2026-08-22j — #384 SHIPPED: merged calculator LIVE for all users (PR #172 `80dee42`, flags LIT, app 1.16.0)

Operator: *"Merge and ship live. Turn the flags on and make available for all users."* Branch
`claude/manual-calculator-e2e-review-39a467` (20 commits: E2E review → W5 → D-151 → W6-A → W6-B →
flip) rebased onto `613a34c`, squash-merged as **#172**. `calc.merged_layout` **true** and
**`onboarding.guide_v2` true** (its original graduation criteria — TestFlight pass + M1–M8
diagnostics — waived by the operator; note it lights EVERY v2 Analyst beat for all users, not only
the calculator tour; config-only revert). Fixture mirrors updated (release, onboarding-v2,
profiles-on). App **1.16.0** (`app.json`, `Info.plist`, pbxproj) — EAS production build
`--auto-submit` to TestFlight cut from the same tip. Gates at ship: pytest 4173 · tsc · 76/76
guards · testid-lint. **No runtime evidence** (D-056); the rewritten checklist is now a POST-ship
checklist. Render auto-deploys the backend from `main`.

## 2026-08-22i — #384 W6-B: Find a Trade forks on the canvas — fairness-only packages (D-153); still dark, not pushed

Operator re-ruled the contract (no model for a filled canvas; toggle dropped; tour ends in the
modeled cards). One Opus build package, lead-reviewed. Backend: `POST /api/trades/fair-packages`
(flag-gated) — give side an exact anchor, 1–3-asset returns, receive side a ranking preference;
`_generate_asset_ideas_impl._eval` extracted to `trade_service.eval_consensus_package` and shared
(asset-ideas byte-identical, golden green); `fair_packages_cap` knob (20); deterministic `fairpk_`
ids that `_reconstruct_swipe_card` accepts (tested end to end). Mobile: handoff `fairAnchor`
replaces `includePlayers`; TradesScreen forks before the model gate and `setDeck`s
`ideaToCard` cards (helper moved to `utils/ideaToCard.ts`, pure); toggle removed (row 70/15/15);
tour `n10 n11 n12 n13 n15 n16 n18 | n19–n24` (n14/n17 builders deleted; n16 a tap beat);
calculator `ScrollView` announces scroll + guard rule 10 makes it mandatory; "Search all trades"
exit on fair decks. Analytics: `calc_include_players_toggled` removed, `path` prop,
`deck_search_all_tapped`. Gates: pytest **4173** · tsc · 76/76 guards · 5 sabotages red.
Q-029 fully closed (✓ half D-152, receive-side half retired by D-153). Also this session:
`docs/plans/ram-mascot/brief.md` (own thread, awaiting D1).

## 2026-08-22h — #384 W6-A: the ✓ cell is wired — `POST /api/trades/queue` (D-152); D-151 closes §6b (still dark, not pushed)

Operator rulings: §6b → the merged calculator keeps its own tab ([D-151](DECISIONS.md), Q-028 closed);
the ✓ like/queue contract approved and built as **W6-A** ([D-152](DECISIONS.md)). One Opus build
package, lead-reviewed: the route records the deck's own like through `_reconstruct_swipe_card` →
`record_decision` with a deterministic `calcq_` id (idempotent, one Elo signal), evaluates the
counterparty's likes-you gates **up front** and refuses with a closed six-reason enum recording
nothing; `find_live_trade_like` is a read-only helper (no schema change). Mobile: `onLikeTrade` →
`queueTradeForOpponent`, per-reason toasts, in-flight lock; `calc_trade_queued {queued, reason}`
registered (INTENT). 26 backend tests incl. "the queued like reaches the opponent's deck"; pytest
**4154**; 76/76 guards; docs (api-reference, cross-client-invariants reasons enum, architecture,
LLD, glossary, scope, status W6-A, checklist 13/13a/13b). Next: **W6-B** — Find a Trade with a
filled canvas becomes a fairness-only package search (asset-ideas engine generalised), empty canvas
keeps the modeled deck, the Include-players toggle is removed, the tour is reshaped to end in the
modeled cards, and the calculator `ScrollView` announces scroll so spotlights track.

## 2026-08-22g — #384 W5: the journey works on paper again (three Opus build packages, lead-reviewed; still dark, not pushed)

Built on the review below, same branch. `fcf3413` **W5-B** — 13 calculator/tour/deck events +
`prompt_deferred` registered with exact prop allowlists and NON_INTENT classification
(ingest was dropping every one); addendum `docs/business/analytics/2026-08-22-384-calc-finder-addendum.md`;
pytest 4128. `9dcd003` **W5-D** — the ✕-overlay stays up through layer 2 and a backdrop-dismiss after a
banked tile commits the deferred advance (the P0 dead-end); `reasonsAsOverlay` is a host PROP driven by a
handoff `origin:'calculator'` (not a flag read — shipped decks keep their tiles); `FinderHandoff` gains
`origin`/`includePlayers`/nullable opponent and the choke point regenerates on a calculator arrival;
Back-to-calculator via the #190 prefill shape; unpin-retry for any pin count, regenerates; deck guide
targets registered. `a52c91e` **W5-T** — n10/n16/n17/n18 advance on the real action; Find a Trade uses
`popTo` (G-056) and the runner PARKS/resumes on deck arrival; auto-start gated on a `calc_tour_completed`
receipt, `hasLeague`, and `onboarding.guide_v2`; tour-owned mute in `useGuide`; n11 opens the DNA sheet +
outlook fallback row; format chips restored; league-keyed remount; n23/n23b by platform. Lead added: endTour
tears down its own bubble, run-ahead Find-a-Trade jumps to the deck half, arrival waits for a card.
Gates: tsc · lint · **76/76 guards** (+13 assertions) · pytest 4128. **Still open (bright line):** ✓
like/queue contract (cell stays disabled), receive-side `pinned_receive_mode:'all'`, §6b, rollout shape.

## 2026-08-22f — #384 E2E review: do NOT flip `calc.merged_layout` yet (review-only, nothing shipped)

Five independent Fable code-walk reviews + lead verification of every P0/P1 on
`feat/calc-finder-merge` @ `7399e18`. Gates re-run and green (tsc · lint · 76/76 guards ·
pytest 4117). **5 P0 · 8 P1 · 7 P2 · 4 P3** in
[review-2026-08-22-e2e.md](../docs/feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md).
The journey does not work: the ✕-overlay strands every card (layer-1 closes the sheet, the host
advances only from layer 2); four `action` beats have no `advanceGuideIfActive` call site; the
deck half of the tour is unreachable (navigate PUSHES a second TradesHome — routers 7.5.3, no
`getId`/`pop` — and nothing regenerates; deck targets never registered); the tour's spotlights
and caps hang off `onboarding.guide_v2` (false) and the outlook row off `trade.outlook_direction`
(false), neither named as a prerequisite; the ✓ cell is a permanently disabled control
(`onLikeTrade` never passed). Also: receive-side pins are any-one not all (`trade_optimizer.py:522`),
the overlay is app-wide (`TradeCard.tsx:205`), no first-visit gate, league switch leaves a stale
canvas, format chips dropped, 12/61 sabotages stayed green, no scope.md, tour events unregistered.
Four bright-line operator decisions listed in the review. Suggested W5 (no API) / W6 (after rulings).

## 2026-08-22e — The merged calculator: five waves, BUILT DARK (#384, `feat/calc-finder-merge`, not merged)

The report the cap ate ([D-149](DECISIONS.md)) turned into the build. #384 — canonical for
#310/#379/#380, touching #333 — specced a merged Find-a-Trade/calculator surface plus a
fifteen-beat tour. Ten rulings at triage, four at plan review, then "continue through all
waves". [D-150](DECISIONS.md).

- **W0 `224a830` — the demo CALCULATOR removed** (net −239 lines), and only that. "Demo" names
  two unrelated systems across sixteen files; the demo **SESSION** (`/api/session/demo`,
  try-before-you-sync, `onboarding.demo_bridge`) is open-access onboarding and is untouched,
  verified by an empty `git diff` over its five files. `check-demo-calc-removed.js` is
  two-sided so a future change cannot delete the wrong one. It also surfaced that
  `tradeCalcMock.ts` exported two types that were never demo-only, and that
  `utils/CLAUDE.md` called `tradeCalcMath.ts` "demo mode only" when three components import
  it — a stale doc that would have justified deleting a live module.
- **W1 `dfcd532` — the layout**, behind `calc.merged_layout` (**false**). Outlook beat,
  league/team dropdowns (#333), two vertical columns, the 40/30/15/15 action row. Flag-off is
  proven by **excising every gated region by brace balancing** and asserting no merged-only
  testID survives — not by grepping for gates.
- **W2 `56111a0` — behaviour.** ✕ keeps one button and pops the reasons as an overlay;
  end-of-deck gains "Back to calculator" and "Search without <player>"; include-players writes
  the **shipped** `useFinderTargets` pin store rather than a `requireAssets` param nothing
  would have read. **The send ruling needed no code** — `resolveSendPlatform` already routes
  Sleeper/MFL/ESPN.
- **W3 `4ff15f3` — a tour-long HOLD, not a new gate.** The plan priced this as building
  suppression across six surfaces; `useInterruptCoordinator` already was that gate and is
  live. The real gap: the slot frees BETWEEN steps, so an interstitial legitimately wins the
  gap. A hold closes it; `isInterruptBusy()` extends it to the root modals.
- **W4 `ae605ad` — 15 beats compressed to the CI copy budget** (auto 12 / action 16 / tap 20 /
  cta 16), every line word-counted before authoring, worst case 14/16. Runner owns sequence
  and lifecycle; the script stays data. Beats decline behavioural retirement **with the reason
  written inline**, because no receipt means "understands the calculator".

**Gates every wave:** pytest **4117 passed / 1 skipped**, tsc clean, testid-lint OK,
structural suites **71 → 76**.

**Five dead assertions found and fixed — all in MY OWN guards, none in the product:** two
substring anchors that survived their own sabotage (`/isDemo/` matched `isDemoRenamed`,
`/onDemo/` matched `onDemoStarted`), a backwards proximity search for the flag gate that
stayed green when the gate it should have read was replaced, a fixed-size window that read the
next JSX prop's body, and a drift detector that threw instead of failing a named assertion.
An existing suite also broke honestly (`check-decline-reasons.js` pinned the ✕ condition as a
literal string); its two legal shapes are now enumerated rather than the pattern loosened —
verified by sabotage that it still rejects `reasons && false`.

**Nothing is live and nothing has runtime evidence.** `calc.merged_layout` is false, the
branch is unmerged, and the 27-step TestFlight checklist is unrun. Reported not buried: a
**pre-existing** Chalkline floor violation (`lineupHeadText` at fontSize 10, on `main` since
#297), and plan §6b — ruling 3 collides with #310 and with the tour's own first beat, built to
a stated assumption that still wants a yes/no.

## 2026-08-22d — A long feedback note stopped vanishing (cap 2000 → 8000, and the three silences around it)

The operator wrote a long in-app note, tapped Save, watched the sheet close normally — and it
never arrived. Not a network blip: `POST /api/feedback` had refused it with `400 text_too_long`,
and **three separate behaviors conspired to make that invisible** ([G-055](GOTCHAS.md),
[D-149](DECISIONS.md)):

- the compose sheet had **no counter and no `maxLength`**, so nothing hinted a cap existed;
- `onSave` cleared the draft and closed **unconditionally**, so failure looked exactly like success;
- `useFeedback.add` fired the POST into a detached `void (async …)()` IIFE that **always** resolved
  `synced:false`, so the caller could not have checked even if it had tried. And because a 400 is
  *permanent*, `retrySync()` plus the AppState foreground hook re-attempted the same doomed
  request forever.

**Nothing was actually lost** — `add()` persists to AsyncStorage *before* the network call, so the
note sat readable the whole time at Settings → Testing → "Test feedback", badged `Sync failed`. The
defect is that nothing said so.

- **Cap raised 2000 → 8000, and deliberately kept.** `/api/feedback` accepts anonymous writes, so
  the bound is the only limit on payload size. `app_feedback.text` is unbounded `TEXT` — validation,
  not storage, so no migration.
- **Soft cap, not `maxLength`.** RN's `maxLength` silently truncates a *paste* — the same data loss
  moved earlier. The counter reddens, names the overshoot, and holds Save; the app never edits the
  user's text.
- **One number, pinned across the seam** (`backend/server.py` ↔ `mobile/src/api/feedback.ts`) by
  `check-feedback-capture.js`. **It caught a real mismatch on day one:** mid-build the client was at
  8000 while the server was still at 2000, and the assertion fired with the right diagnosis.
- **Deploy order matters and CI cannot enforce it:** backend-first is safe, client-first *reproduces*
  the defect for 2001–8000-char notes. Backend ships now; the client half waits for a build.

**Evidence.** pytest **4117 passed / 1 skipped** (baseline 4114 + 3 boundary tests); `tsc` clean;
testid-lint OK; **71** structural guards incl. the new 6-assertion one. Red-proofed both ways: the
new guard is **6/6 RED** on the pristine defect tree at `9e1a8be`, and **20 sabotage cycles** (one
per named failure branch) each fired the branch it targeted. The backend trio caught three
sabotages including the nastiest — making the server **truncate** at 2000 instead of refusing still
returns `201`, so only the stored-length assertion catches it.

**Unknowable, and worth stating plainly:** a rejected POST writes no row, so there is no
server-side record of how many notes this cap ate before today. `obs.api_events` captures the 400s
from here on.

## 2026-08-21d — Decision-ID attribution corrected: slot pricing is D-146 everywhere (docs only)

Nine reference-doc sites and three `LLD.md` headings credited the wrong decision for
per-slot pick pricing. Root cause: the slot-pricing session drafted its decision as
**D-144**, renumbered only the `DECISIONS.md` entry to **D-146** ([G-048](GOTCHAS.md)),
and left the draft ID in every doc it had already written. PR #168 then blanket-replaced
`D-144` → `D-147` across `LLD.md`, turning an already-wrong ID into a differently-wrong
one; the tell was a heading reading D-147 above an anchor still reading `d-144`.
Corrected against `DECISIONS.md` **one site at a time, by what each decision actually
decided** — never by adjacency or date:

- `LLD.md` — "Retiring a per-user setting" and "Pricing waterfalls" → **D-146**;
  "Append-only… `receipts_*`" stays **D-144** (genuinely Receipts); "Consulting a leaf"
  stays **D-147** (negmem), anchor healed. All five TOC rows now agree with their
  headings, and the receipts section got the TOC row #165 never gave it.
- `api-reference` (retired `/api/settings/pick-pricing`), `config-reference`
  (`trade.slot_pricing`), `data-dictionary` (`pick_pricing_mode`) and **5** sites in
  `cross-client-invariants` → **D-146**. Each had been sending readers to Receipts grading.
- PR #169's day-old D-148 section opened *"D-144 put per-slot pick pricing into the
  engine"* — inherited from the neighbour it was written beside. Fixed.

`docs/plans/**` drafts keep `D-144` on purpose (historical record of the draft).
New [G-054](GOTCHAS.md): a heading/anchor mismatch is the fingerprint of a blanket
replace, with a slug-every-heading detector; **`git grep` the OLD id after any renumber.**
Also indexed G-049/G-050, which had entries but no index row (so the SessionStart
injection never surfaced them). Docs only — no code, no schema, no routes.

## 2026-08-21c — League surfaces now price picks at the engine's waterfall (PR #169, `70ae4f4`)

Closes the disagreement [D-146](DECISIONS.md) knowingly left open: a 2026 1.01 read **2117.0 on
Power Rankings and 4867.1 inside a trade card**. Five call sites now share ONE seam
(`_priced_pick_value`), bidirectionally AST-guarded so a sixth cannot appear —
[D-148](DECISIONS.md), closes [Q-026](OPEN_QUESTIONS.md).

- **A real defect fell out:** `_roster_eveners` sized its one-tap "add their 1.01" suggestions off
  the stored ladder while the same response's `gap` came from priced picks — offering to close a
  2117.0 hole it charged 4867.1 for.
- **Power Rankings deflate, monotonically by slot:** +12.4 % (1.01 holder) → −40.3 % (1.12),
  **−22.1 % league-wide**. These have been the ENGINE's prices since `3192d13`; this stops a
  screen contradicting them. **50 of 96 badges re-band** (bands + five client mirrors untouched).
- **ADR-011 boundary named:** `roster_history.team_value` steps at this merge (Wrapped/trends read
  across it). Nothing historical recomputed — pinned by a test asserting `roster_history.py`
  contains no pricing call at all.
- Golden set in isolation **3×, zero edits**; suite **4114p/1s**; zero client diffs.
- Residues raised not buried: pick-SHARE ratios stay legacy (waiver 3 — an inference input, and
  changing it changes deck generation), and the non-12-team board/engine mapping became
  **[Q-027](OPEN_QUESTIONS.md)** (a 10-team league's last first displays 820.8, prices 1069.8).

## 2026-08-22c — negmem SHIPPED dark: merged to `main`, deployed to Render (PR #168)

The negative-results-memory branch merged (`7b7c314`) after re-merging `origin/main`
(Receipts #165, arm-C sweetener #166, slot pricing #167 — no code conflicts; my
`trade_gen_v2` seam and the new arm-C sweetener coexist, suite 4097 green). **D-number
collision caught and fixed at merge:** Receipts landed D-144 first, so the negmem entry
renumbered **D-144 → D-147** with every negmem cross-reference repointed — renumber the
newcomer, never someone else's landed entry. CI green on 3.12.3; zero mobile files, so no
TestFlight build was cut (operator instruction: GH + Render only). Render deploy verified
by `trade.negmem` moving ABSENT → false on `/api/feature-flags`. **Everything is dark:**
flag false ∧ allowlist empty (ON needs both) ∧ arm A pinned to 0. Rollout remains two
operator flips at a bake-off round boundary; the TestFlight checklist is UNRUN and is the
only runtime evidence this feature can get (D-056).

## 2026-08-22 — negmem BUILT DARK: the whole v1 is on the branch, nothing is lit (`claude/vigilant-spence-8583f5`, not merged)

Build gate opened by the operator's three §6 rulings (D1 yes · D2 seed-only · D3 (a) full
layer 2, knowingly against the recommendation). Built in **three waves**: B1 the leaf
`backend/negmem.py` (83 tests, 26/26 sabotages RED-then-restored, LLD worked examples exact)
→ B2 the registration surface (flag + 6 knobs ×3 registrations, arm-A pin, allowlist file;
arm-A golden UNMOVED, no recapture) → B3 the four consultation seams + threading + the stamp
trichotomy (33 seam tests, 6 sabotage families) → this wave: the `bakeoff_runner` forwarding
that B3 left, 5 through-the-runner tests, the two readout SQL files, the TestFlight checklist,
and every docs row. Suite **4025 passed / 1 skipped / 0 failed** (wave-2 baseline 4016; +9 this wave); testid-lint OK; zero mobile files touched.
[ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md) + [D-147](DECISIONS.md)
record the soft-prior-not-a-filter shape and the build-complete state.

**Known gap, deliberate:** nothing is lit. `trade.negmem` is false and
`config/negmem_leagues.json` is empty — the ON-condition is BOTH — so no deck has ever been
generated with this on. The [TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md)
is written and **unrun**. Rollout is two operator flips at a bake-off round boundary, not code.

## 2026-08-21b — negmem LLD FINAL: the planning suite is COMPLETE (branch `claude/vigilant-spence-8583f5`, not merged)

Resumed post-limit-reset; LLD authored via drafts (Fable) → merge agent under an 11-point
ruling sheet → rounds 2–3 on **Opus** (operator-directed model switch). Dual sign-off
round 3/4. The round-2 review killed a merge-adopted mechanism outright (`owner_alias`:
unbuildable AND unnecessary — M1 needed no aliasing; M2 ships identity + a real
tripwire), fixed the like-leg retraction to honor the schema's revive path, made a
vacuous sabotage falsifiable, and resolved OQ-4b by independent convergence (keep the
shrinkage-gate discontinuity; `negmem_sat_k` is the deploy-free flap lever). 27
sabotage-pinned tests; 7 HLD/PRD deltas logged. **Suite: memo · scope · PLAN · PRD FINAL
· HLD FINAL · LLD FINAL · reconciliation-log (3 sections) — planning only, zero code.**
Shared taxonomy closed at v1.1.1 (three-way + my admission-list footnote). Batch
delivery to the operator: pinged Receipts; rides with the breaker suite. The three
operator decisions (negmem scope §6) remain the build gate.

## 2026-08-21 — negmem planning suite: memo, scope, plan, PRD FINAL, HLD FINAL (branch `claude/vigilant-spence-8583f5`, not merged)

Operator product-gap item 2 ("Negative-results memory") taken through full gates,
planning only. Code-truth memo (518 lines: every existing rejection-consumer cited; the
gen_v2 `acceptance_prior` unfed-stub finding; D-067 soft-only constraint) → scope block
(3 operator decisions) → PLAN → dual-agent **PRD FINAL** (9 blockers fixed across 4
rounds; v1 = soft prior keyed (partner × {value,fit}), 22 cells, floor 0.6 + feed the
stub; privacy rec = aggregate-only derive-on-read) → dual-agent **HLD FINAL** (8+1
blockers across 4 rounds; pure `effective_mult`, kwarg threading, stamp trichotomy,
M2×strength decision: `negmem_strength` M1-only, M2 kill = `gen2_accept_prior_strength=0`).
Three-way reconciliation with Receipts CONFIRMED (their contract §7; two data boundaries
inherited); breaker boundary agreed (shape_aversion producer=negmem); operator ghost
ruling absorbed (checked NOT load-bearing). **LLD pending — session limit** (see HANDOFF).
## 2026-08-21b — Triple ship: Receipts LIVE (grading lit) · arm C unbenched with its sweetener · TRUE PER-SLOT pick pricing

Three merges, all operator-driven same-day, each a value/measurement boundary:

- **#165 `93f1fd0` Receipts** — nightly suggestion grading over the 4,051-card cohort
  (P0 prod checks passed: cohort from 2026-08-16, zero snapshot gaps, top testers 750–840
  gradeable each). `receipts.grading` LIT at ship (Q-1..Q-4 rulings); screen dark until the
  operator's TestFlight pass. First mature grades ≈ 2026-08-30.
- **#166 `3df71c0` arm-C gap sweetener** (cherry-picked from the operator's side session)
  — closes the regression that benched gen_v2 at #162; `bakeoff_include_gen_v2` 0→1 @18:49Z.
  **All three serving arms now run honest pricing + the sweetener.**
- **#167 `3192d13` per-slot pick pricing, unconditional** ([D-146](DECISIONS.md), closes
  Q-023 fully; Q-026 ruled-deferred). 1QB 2026: 1.01 **4867** … 1.12 **821** (5.9× spread)
  where the ladder charged 2117 flat. The operator's Maye+Adams ↔ 1.05+2027-1st proof case:
  +372 picks-favored → **−15 near-even**. Opt-in mode/route/Settings row retired (repo's
  first 410). Goldens: 156 assertions, zero edits, twice. Repo's first conftest.py pins the
  DP pick snapshot (suite was one network fetch from flaky).

Origin story for the day: operator feedback on ONE trade (Maye+Adams for 1.03+1.05) →
market-curve analysis → benchmark+sweetener ship → per-slot ship. Suite 3969p/1s at day end.
## 2026-08-21 — Receipts built dark on `feat/receipts` (NOT pushed, NOT merged)

Grades our own past suggestions against subsequent consensus movement. No competitor grades
its own advice. Everything is behind two default-false flags.

- **Metric is swap edge** (`receive-delta − give-delta` on `player_value_history`), not an
  acquire-side % — the give side is the market control (D-145). Valuation never comes from
  the frozen card, whose values may be the user's personal board.
- **Grades are append-only + `grader_version`-stamped** (D-144): no UPDATE/DELETE path exists
  for `receipts_*`, test-enforced. A correction is a regrade; old rows stay.
- Ships: `backend/receipts_service.py` (leaf — no engine import, both directions guarded), 2
  tables, 3 routes (cron 202+daemon, viewer-scoped league read, admin per-cell readout with
  Wilson intervals), daily-tick guard, `scripts/receipts_backfill.py`, `ReceiptsScreen` +
  entry point, 3 analytics events.
- **Both screen states built** per operator ruling Q-1 — the maturity/ledger state is the
  launch hero, not an empty state.
- Evidence: 54 pytest + 12 structural checks, **21 named sabotages all RED**; six guards were
  blind on the first pass and were strengthened. Two real defects caught: a dedup keeping the
  latest serve (masked by a stale `.pyc`) and a flag-off daily-tick payload change.
- Backfill exercised on a synthetic fixture DB: 565 resolvable → 542 graded + 23 ungradeable,
  terminating on two zero-work runs, 0 ghosts graded. The real dev DB has no impressions, so
  its dry-run correctly reports 0; the prod P0 cohort read is still outstanding.

## 2026-08-22 — SHIPPED early by operator call: package pricing honesty + gap auto-sweetener (PR #162, `d42872f`)

Operator: *"I would rather the more accurate trade suggestions now."* Merged ahead of the
Monday boundary; this week's readout is two-window censored at the merge SHA (accepted).

- **The mid-package-buys-stud defect is dead:** `_package_value_market` depth discount now
  benchmarks against the TRADE's best asset. Nacua proof case 0.952 → 0.709 (blocked).
- **Gap auto-sweetener:** consensus gap > 1539 (one late 1st) ⇒ generation adds the best
  equalizer from the richer side. Real-boards replay: fires 1.42/deck, closed **17 of 17**
  it touched (mean gap 2173 → 850); deck cost only **−1.6%**; arm-B over-line 8.1 → 3.8%.
- **NOT independently revertable** (replay finding): the benchmark fix ALONE raises the
  over-line share (v3 6.7→11.3%) — the sweetener nets it down. Rollback = BOTH
  `package_bench_trade_wide ≤ 0` AND `sweetener_gap_threshold ≤ 0` together ([D-143](DECISIONS.md)).
- **Arm A never moved:** knobs pinned 0.0 in `MODEL_A_PROFILE`, deck-level byte-identity
  proven on fixtures AND real boards — golden un-recaptured, operator-ratified ("Y").
- **Arm C benched at ship** (`bakeoff_include_gen_v2` 0, logged 16:37Z): it inherits honest
  pricing without the sweetener (37.2% over-line on real boards). Unbench when the arm-C
  sweetener extension (separate session, in flight) merges.
- `ghost_holdout_one_in` code/seed defaults → 0 (the 08-21 ruling, now durable). Opus
  review pre-ship fixed two inherited defects (sweetener targeting bypass; stale
  fit_premium on v3 sweetened cards). Suite 3897p/1s post-#161-merge; CI green ×2.

## 2026-08-21 — Counterparty-breaker suite CONVERGED (dual-agent, three-way reconciled); build started dark

Full planning suite for the "Counterparty breaker" (evaluates every trade suggestion from the
OTHER manager's seat; predicts their decline reason in `trade_pass_reasons` vocabulary; v1 =
stamp + hesitation narrative, zero ordering effect) completed on `claude/counterparty-breaker-plan`
(tip `c14680a`+): [docs/plans/counterparty-breaker/](../docs/plans/counterparty-breaker/) —
scope · PLAN · HLD · LLD · PRD, each dual-agent converged (4 rounds each), full
[reconciliation-log](../docs/plans/counterparty-breaker/reconciliation-log.md).

- **Three-way reconciled** with Receipts + negative-results-memory; shared taxonomy **v1.1.1**
  closed on `plan/receipts` (`5572604`, producer column enforces the breaker/negmem boundary);
  Receipts batch check **PASS**.
- **Review caught real defects pre-build:** false seam claim (likes-you cards injected after the
  fit-stamp site), payload-layer privacy leak (dark window now serves NO breaker key), rung-5
  handler crash, picks-in-lean contradiction, lost flag-off MUST — all fixed in-loop.
- **Binding constraints recorded:** operator NO-ghost ruling; interleave discipline (v1 zero
  ordering effect); Monday `fix/package-benchmark-sweetener` ship = named measurement boundary
  (arm A byte-invariant — knobs pinned 0.0 in its profile; `gap_sweetener` key).
- **Build COMPLETE same session** per operator instruction (Opus subagents, 3 waves: module+knobs+
  templates+mobile → server seam → docs/evidence). Everything behind `trade.breaker` +
  `trade.breaker_narrative`, both **false**; suite at tip **3872p/1s**; 25 knobs ×5; taxonomy
  v1.1.1 landed; calibration spec committed pre-flag-on; [D-142](DECISIONS.md);
  **[PR #161](https://github.com/mattmurf77/fantasy-trade-finder/pull/161) open — merge is the
  operator's.** 20-item register in PRD §9 — defaults ship, register is post-build tuning.

## 2026-08-21 — Serving RE-LIT (B/D/C interleaved), ghosts OFF by ruling, QB 1QB repriced, planning fleet

**All prod changes via `scripts/set_knob.py`, logged in `model_config_changes` (the M1 rail's
first live use).** Operator-driven session, all decisions theirs:

- **Interleaved serving LIVE** 00:43Z: `bakeoff_serve_interleaved` 1, `bakeoff_group_size` 0
  (plain draft), `bakeoff_deck_limit` 60. First decks: 26–29 cards, arm mix challenger 38 /
  current 26 / gen_v2 17. Root cause of the operator's 6-card-repeat deck: FFV3 pool exhaustion
  (287 decided + 812 standing decisions) **amplified by ghost accumulation** — ghosts can never
  be decided so never leave the pool (one hash ghost-served 35×; two decks were 100% ghost).
- **Ghost holdout OFF** (`ghost_holdout_one_in` 0) and then **ghosts ruled out entirely**
  (operator: "I still am against the ghost cards") — Receipts amended post-sign-off (`325896e`),
  all three planning suites carry the ruling; code/seed defaults flip to 0 next ship.
- **QB 1QB repriced** 04:46Z: `qb_1qb_cap_elo` 1785→**1644**, knee 1580→**1200** — two-anchor
  solve: Allen = exactly a late 1st (1539), sub-first QBs = mid-2nds. The old cap priced Allen
  ABOVE an early 1st (3592 vs 3373). Also seeded 10 never-seeded serving/ghost knobs
  (`024b030`) — the "deploy-free" flips had been code-default edits all along.
- **Tier-anchor diagnostic** (operator's "too flat" thesis): within-band spread is HEALTHY
  (p10/p50/p90 ≈ .07/.5/.9 in every band) — thesis not confirmed as stated; rung occupancy
  lumpy; market-curve steepness comparison (D-084 method, vs KTC/FC) running as the follow-up.
- **Post-flip card analysis:** 15% of cards carry gap > a late 1st, all from arms D/C at
  fairness .73–.83 on big packages — the ratio-gate scale-blindness, live. Operator
  commissioned an **auto-sweetener pass** (add the equalizer instead of serving the gap); queued.
- **Planning fleet** (3 sessions + coordinator): Receipts suite COMPLETE (dual sign-off, round 3;
  8 blockers fixed incl. a wrong Wilson formula and a sign error both reviewers independently
  caught) on `plan/receipts`; negmem + breaker reconciled against its §7 contract; shared
  trade-shape taxonomy v1.0.0 seeded (`docs/plans/shared/`). Batch → operator when sibling LLDs land.

## 2026-08-20c — Team Review #364–#376 all shipped; #366 tiers LIT, three window flags dark

Operator ran the flow end-to-end and filed **thirteen reports**. All closed in code across
PRs #152/#155/#156/#157/#158 and builds **124**/**125**.

- **#372 — one re-weighted composite window** ([D-140](DECISIONS.md), `trade.outlook_composite`,
  **dark**): age 1.00 → 0.40, `starter_index` +0.60, `playoff_index` +0.40, cuts unmoved. Measured
  on prod (12 leagues / 156 teams) the legacy vector called **65% of every team a rebuilder**; the
  composite gives 62/40/54. FFV3 flips rebuilder → contender; `PaulSm3nis` flips the other way,
  reading contender on age alone while owning the league's worst starting lineup.
- **#366 tiers LIT** (PR #157, operator call, evidence caveat reaffirmed). `trade.position_tiers`
  moves `position_needs`/`position_surplus` and therefore **every deck**. Handcuff is real, not
  approximated — Sleeper's `depth_chart_order`, exactly 32 RB2s, one per NFL team.
- **#369/#375 — plan beat rebuilt**, and it uncovered live data loss: the depth beat's "Save &
  continue" **had never saved anything** (positions-only body, route 400s without `team_outlook`,
  client throws, the success line never ran behind an empty `catch`). So
  `team_review_action_taken{action:'positions_set'}` has **never fired in production**.
- **#376 — the filters were NOT removed by an update.** Build 123→124 changed four files, none on
  TradesHome; all 178 prod flags matched `main`. Cause: `trades_home_inline` at **100% strip since
  2026-08-09**, where `TradeHomeUtilityRow` replaces the mode bar and shipped with no conditions
  entry. Filters button restored; experiment kept by operator choice.
- **#374** — "pointed the other way" defined from both sides in the user's own window terms.
- **Evidence quality is the story: FIVE dead tests found** across three waves — one asserted the
  defect, one went vacuous when a fix changed selection, one's escape hatch held only by accident,
  one's helper zeroed its own index so deleting the guard was a numeric no-op, one regex needed a
  literal word near a differently-written gate. Separately, forcing #366's bands on left **all 65
  engine tests green** — proven meaningless by disabling the small-pool guard, which turned exactly
  1 of 65 red.
- Final gates: pytest **3761 passed, 1 skipped**, tsc clean, **68** `check-*.js` suites, testid-lint OK.
- **Owed:** four TestFlight checklists, all unrun. #372 is in no build.

 + measurement rail + serving guards (dark; SHIPPED to `main` 2026-08-20)

**Session arc:** re-reviewed the trade-suggestion research corpus against fresh read-only prod
pulls (position curve INVERTED — like-rate 16.9% top-of-deck → 50%+ past card 25; `propose` = 0
all-time; pass reasons 40% `value_giving` / 33% `fit_outlook`; only arm `current` has ever
served), wrote [trade-engine-accuracy/PLAN.md](../docs/plans/trade-engine-accuracy/PLAN.md),
reviewed the operator's fit-challenger PRD
([review](../docs/reviews/2026-08-20-fit-challenger-review.md), C1–C7 + T1–T4), then ran the
full dual-agent pipeline (drafts → cross-critique → merged
[PLAN-v2](../docs/plans/fit-challenger/PLAN-v2.md) → HLD → LLD → PRD-build) and BUILT it in
5 commits: PR-M `980eeea` (knob log `model_config_changes` + `set_knob.py` + readout SQL incl.
lens calibration), PR-S `b2b4461` (08-18 shrink regression test, sabotage-proven; bypass
code-walk: all 7 layers covered; finding: serving-mode state is `served_arm` alone), PR-F1
`ba5b1e0` (knockout chain, K3-last, T1 module-binding sabotage-tested), PR-F2 `d8a80a5`
(enumerator + dual 0–100 scorer on RAW boards + `fit_diag` stamp w/ lenses), PR-F3 `cb3cb3d`
(post-filters, runner wiring, serve-bit proven at BOTH draft paths, docs rows). Suite
**3645 passed, 1 skipped**. 17 knobs, all arm-A-dispositioned. [D-098](DECISIONS.md)/[D-099](DECISIONS.md),
ADR-013/014. Fixture dry run: fit **253 distinct ideas vs arm B 12** (~21×), one_sided 0.48,
junk 0.055, 1.8 s @ 5k cap — R-8 says rostering is now an **operator decision**
([register, 9 items](../docs/plans/fit-challenger/PRD-build.md)). Everything dark:
`bakeoff_include_fit` = 0 (operator: flip to 1 at W3), `bakeoff_serve_fit` = 0,
`bakeoff_serve_interleaved` untouched at 0. Same-day operator rulings shipped with it:
K1 widened to include 2-2/3-3 (PRD §12.6), `trade.outlook_direction` OFF (experiment #1 —
watch `fit_outlook` pass-reason share), ms bar set (scope.md §6). No client build needed:
zero mobile files changed.
**Corrections:** D-096 likes-you gates (`7110af2`), balanced-claim fix (`d755b3b`), and arm D
(`38806e0`) are MERGED on `origin/main` — earlier HANDOFF/NEXT entries calling them unmerged are
stale.
## 2026-08-20 — "Elite" meant four different things, and the NFL depth chart was there all along (#366, dark, not merged)

Second item from the same operator pass. Two flags, both **OFF**, neither graduated; committed on
`worktree-agent-a4ab94c51456abb78`, **not pushed and not merged**.
[scope](../docs/feedback/items/366-tier-ladder/scope.md) ·
[code-walk](../docs/feedback/items/366-tier-ladder/code-walk.md) ·
[D-120](DECISIONS.md) · [D-121](DECISIONS.md)

- **The elite logic was a disguised overall-rank cut.** `_bin_player` banded on three absolute
  `dynasty_value` thresholds, and `dynasty_value` is a monotone function of Sleeper's **overall**
  `search_rank` — so 4000/1500/500 really meant "overall rank ≤ 73 / 151 / 238", applied identically
  to a TE and a RB. Measured on the live pool: **33 elite RBs, 33 elite WRs, 17 elite QBs, 7 elite
  TEs.** One word, four meanings, exactly as reported. Behind `trade.position_tiers` the bands now cut
  in rank **within the position** — Elite = top half of the league's starting demand, Starter = inside
  1.5×, Replacement = inside 2.5×, superflex widening QB to the RB/WR cuts.

- **The third layer existed and was never rendered.** `bench` has been computed since the function was
  written; the beat printed `N elite · N starter` and dropped it. `bench` is **not renamed** —
  `replacement` ships alongside it as an alias so the shipped TestFlight build keeps parsing, and the
  screen reads `replacement ?? bench`. The label is "Replacement"; the word "bench" is never shown.

- **Handcuff is real data, and the plan doc was wrong about that.**
  [plan-remaining.md](../docs/feedback/items/364-team-review-fixes/plan-remaining.md) §2 said no FTF
  feed carries an NFL depth chart and floated approximating with "second-highest-valued RB on the
  team". Sleeper's `depth_chart_position` / `depth_chart_order` have been ingested since
  `database.py:8769`, re-synced every 24 h, and hydrated onto every pooled `Player` at
  `server.py:1580` — **149 of 603 RBs carry a real order today**, matching the 32 actual NFL charts.
  So the tag is the operator's literal definition (`order == 2`), not a guess that would have been
  wrong in precisely the committee backfields where the label matters. `handcuff_rb` is **absent** when
  its flag is off, never `0`: "we did not look" and "you own none" are different claims.

- **Two flags, not one, because the blast radii differ by orders of magnitude.**
  `analyze_roster_strengths` also produces `position_needs` / `position_surplus`, which the trade
  engine consumes — `trade.position_tiers` ON **changes every deck for every user**, so OFF returns a
  byte-identical dict (pinned, sabotage-proven). `trade.rb_handcuff` is one additive integer no engine
  path reads. Rollback is deploy-free: flip `config/features.json`, `POST /api/feature-flags/reload`.

- **Found while testing, and it is a graduation blocker:** 65 pre-existing engine tests are
  **completely insensitive** to the new banding — they stay green with the flag forced on, because
  every fixture pool is smaller than the small-pool guard and cannot distinguish the bands.
  `trade.position_tiers` must not graduate on a green suite; it needs `scripts/deck_eval.py` on real
  leagues plus the TestFlight step written for it.

Gates: **3638 backend tests** (+32), `tsc` clean, 65 `check-*.js` suites green (new
`check-team-review-depth`, 8 assertions), testid-lint OK, **12 of 12 sabotages red then green**.

## 2026-08-20 — Team Review defect batch: the sell list was inverted, the partners beat was starved (#364/#367/#368)

First operator pass over the Team Review flow shipped 2026-08-19 produced 8 reports. Three built,
four planned by operator selection ([plan-remaining.md](../docs/feedback/items/364-team-review-fixes/plan-remaining.md)).

- **#367 — the sell list selected the wrong players, in two places.** `compute_consensus_gap` kept
  roster players the USER rated *above* the market; the card then promised *"someone pays you more
  than you think they're worth"* over exactly the set nobody overpays for. Separately,
  `_divergence` crossed both field names, so the user's best BUYS rendered under **"Skip these."**
  Fixed **upstream** by operator call, which repairs mobile Trends too ([D-100](DECISIONS.md)).
- **#368 — one root cause, both symptoms.** The route computed `pick_share` and `first_rounds` per
  owner and never passed them, so `_partners` fell back to `{}`: every team read "0 firsts" **and**
  a contender's sort key was uniformly 0.0, leaving the beat in arbitrary order. Two kwargs.
- **#364 — the outlook caption now names IDP** and lists the unpriced slots, reading
  `meta.priced_slot_coverage.unpriced_slots`, on the wire since 2026-08-10 and never read by any client.
- **Operator asks, same session:** `window.model` ships all seven inference knobs so the beat renders
  its own inputs ([D-101](DECISIONS.md)) — it had hardcoded *"age 23 and under"* against a `youth_age`
  of **26**; and completing the flow now minimizes the entry card to a "Team review · done" row.
- **Docs:** `/api/league/team-review` was **never documented** — added, post-fix contract. New
  `cross-client-invariants.md` § Consensus-gap direction (three consumers, so the sign is an invariant).
- **Gates:** pytest **3606 passed, 1 skipped**; tsc clean; 64 `check-*.js` suites green; testid-lint OK.
  6 new backend tests, **5 sabotage-proven red**; 2 pre-existing tests repaired — one asserted the
  defect, one had gone **vacuous** under the fix while still passing. TestFlight checklist UNRUN.
- **No flag reverts #367** — `compute_consensus_gap` is ungated and shared. Rollback is a code revert.
- **SHIPPED.** PR #152 merged `bc43b6f`; CI green on the pushed sha (backend-tests, mobile-typecheck,
  testid-lint). Render **live on `bc43b6f`**, so the divergence/partners/caption fixes are serving now.
  EAS **build 124 (v1.15.0)** from that sha submitted to App Store Connect and accepted, awaiting Apple
  processing — the corrected COPY and the window inputs card need the build; the payload half did not.

---
## 2026-08-19 — likes-you injector gated (D-096); the floor moves into the units the user reads

**Not shipped — committed to `fix/likes-you-quality-gates`, not pushed, not merged.**

`server._inject_likes_you_cards_impl` faced no quality gates by design ([D-055](DECISIONS.md)
sub-decision (5) / Q-G6-1). Its only floor was measured on **raw summed** values while the
value bar renders **package-adjusted** ones — so a −500 floor shipped a −5,571 card, pinned
to deck position 1–3. Read-only prod measurement: **115 of 198** served likes-you
impressions showed the user paying, vs. effectively none on the gated deck.

[**D-096**](DECISIONS.md) reverses the exemption: the floor moves into package-adjusted
units at a default of **0.0** (= `user_gain_epsilon`, the gated path's own rule), and R1
`overpay_ok` + `filler_ok` run at level 2. **R1 runs DIRECTIONALLY** — blanket R1 was
measured and rejected because it kills 58 of the 83 floor-surviving cards and **all 58 are
cards where the USER is being overpaid**, the largest a +6,325 one-for-one the counterparty
had already liked. Fairness/R2/R3/R5 excluded with stated reasons and a pinning test.

Measured cost: **198 → 83 impressions (41.9%), 51 → 16 distinct cards, user-pays 115 → 0,
worst card −5,571 → +32.** One knob, `likes_you_gate_level`; **`= 0` restores today's
behaviour exactly, deploy-free**, which is why `likes_you_min_user_delta` keeps its −500
default. `pytest backend/tests` 3524 → **3540 passed, 1 skipped**. Evidence per D-056:
16 unit tests, a code-walk proof, 4 sabotage runs, and an UNRUN operator TestFlight
checklist. Arm A of the bake-off is deliberately not pinned (serving-layer post-process);
`bakeoff_profiles.py` untouched.

## 2026-08-19 — Bake-off arm D: the landability challenger (dark, not merged)

**Branch `feat/bakeoff-arm-a-challenger` off `origin/main` `50e0451`. Not pushed.**
[D-095](DECISIONS.md) · [PRD](../docs/plans/landability-challenger/PRD.md).

A fourth bake-off arm, `challenger`, running the live v1/v3 engine under a
thread-local overlay: shrink neither board, drop the consensus `rv ≥ gv` sign
test (so an even trade can surface in the direction the **partner** gains),
enumerate 1-for-2, floor consensus fairness at 0.75, R5 off, tier ladder
compressed 4.57× → 1.44× so fairness can outrank the biggest name.

**It was briefed as "the new Arm A" and is deliberately not one.** D-075 pins
arm A as a constant with a golden; overwriting it makes the bake-off
unfalsifiable. Arm A, its profile and its captured deck are untouched — the
new knobs are *excluded* from `MODEL_A_PROFILE` because their **defaults are
the pre-wave engine**.

Dark: `bakeoff_serve_interleaved` stays 0, users still see arm `current`.
`bakeoff_include_challenger` = 0 is the no-deploy kill. Arm B byte-identical,
proved by goldens captured at the pre-knob commit. 3524 → **3554 passed, 1
skipped**; 13 sabotages, 13 caught.

## 2026-08-19 — `outlook.odds` LIT + Team Review planned (PR #142, merged `6a3eab3`)

**Shipped.** Playoff odds are live. Operator override (*"Outlook odds should be visible. Forward PPG cut. I waive maestro"*) reversed the same session's own D-093 recommendation — [D-094](DECISIONS.md). Lights the #169 League-Summary layer built-but-dark since `f27c0f5` (2026-08-11): the D-025 collapsed strip, the section behind it, `GET /api/league/outlook`. **No client release needed** — the UI shipped months ago and flags come from the server; verified live, `/api/feature-flags` serves `outlook.odds: true`.

**Bands only, and that is enforced, not intended.** `title_pct` stays unrenderable at any week (absence of skill, CI spans zero); `playoff_pct` renders only as the three-band chip; `OUTLOOK_WEEK6_PERCENT_ENABLED` stays false. Preseason posture (`completed_weeks == 0`): Sleeper only, `meta.beta` true ⇒ bands + row order, no win-loss numbers.

**The flip was five touches, not one** — `config/features.json` plus the `release`/`onboarding-v2`/`profiles-on` fixtures (the latter two each asserted to differ from release by exactly one key). `DEFAULT_FLAGS` stays false (fails CLOSED) and mobile's `LAUNCHED_FLAG_DEFAULTS` stays untouched (those fail OPEN, which would outlive a kill).

**Evidence** (Maestro waived, already void under D-056): new `mobile/tests/check-outlook-bands.js`, 7 assertions, **all six sabotages proven red**; the two darkness-guard tests inverted, keeping `test_flag_off_still_closes_the_route` (flag off ⇒ 404 + empty fan-out). Gates: pytest **3525 passed/1 skipped**, tsc clean, 61 structural suites, testid-lint OK.

**Also merged:** the Team Review plan for #357/#358/#359 (docs only — [D-092](DECISIONS.md), Q-024, Q-025). Build not started.

**Released.** EAS iOS **build 121 (v1.15.0)**, `ccc3cd57`, built from `f1cb03e` (same tree as `main`), **submitted to TestFlight** and accepted by App Store Connect (submission `769a6193`). Awaiting Apple processing. Backend gates re-run on the merged sha with `node_modules` finally installed: `tsc --noEmit` clean and **61** structural suites green — both had been unrunnable in this worktree earlier in the session.

**Watch:** nobody has seen the lit surface on a device; a preseason band can be confidently wrong (2 of 6 backtested seasons lose to climatology); `meta.priced_slot_coverage` is still unrendered, so IDP bands read as whole-lineup on 7-of-15 priced slots.

---
## 2026-08-19 — `account.settings_hub` lit for all TestFlight testers

**Flag flip only — no code, no build.** `account.settings_hub` false → **true** in
`config/features.json` and the three fixture mirrors (`release.json`,
`onboarding-v2.json`, `profiles-on.json` — the latter two assert value parity with
release, so they move together or `test_seed_ui_test_db` goes red).

Everyone on **1.15.0 build 120** now gets the Settings hub and its seven second-level
pages instead of the flat list. Operator decision 2026-08-19: there is no operator-only
path for a plain `useFlag` — `/api/feature-flags` serves `flags_dict()` globally and only
`experiments`/`configs` resolve per device (`backend/server.py:17723`) — so seeing it at
all meant lighting it for the whole tester group.

**This inverts the plan's graduation rule**, which said verify on TestFlight *then*
graduate. The 10-item checklist in `docs/plans/settings-ia-hub/plan.md` §9 is still
unrun; it is now being run against a live flag rather than ahead of it.

**Rollback is one line and no rebuild:** set the flag false in `config/features.json`,
push, Render redeploys. That covers the hub only — the sheet→page presentation flip
([D-089](DECISIONS.md)) is outside the flag and still needs a build to undo.

`pytest backend/tests` 3524 passed, 1 skipped, 0 failed.

---

## 2026-08-19 (Phantom draft-pick years — a league is only offered the classes it actually has; NOT SHIPPED, on `fix/pick-horizon`)

- **Reported (feedback [#355](../docs/feedback/items/355-phantom-pick-years/scope.md), BUG, TradesHome, v1.15.0):** "2029 picks showing on sleeper league without 2029 picks available". Confirmed against the live Sleeper API and read-only prod: `database.sync_draft_picks` built its grid over a fixed `current_season … current_season + 3` — **four** draft classes — and Sleeper carries **three**.
- **The rule, derived not guessed ([D-091](DECISIONS.md)):** a league carries three consecutive rookie classes **anchored to the first class that has not yet been drafted**, so the window *rolls*. Pinned at both ends by live probes, including a **positive** one: the operator's `pre_draft` league has traded picks in 2026/27/28 and none in 2029, while a league whose 2026 draft reads `complete` genuinely does hold 2029 traded picks. Absence proves nothing; presence proves existence — which is why the horizon also **widens** on any season the platform itself reports.
- **Why only some leagues were wrong:** #228's completed-draft exclusion shifted a post-draft league's window by one and made it accidentally correct. Every 2027-starting grid in prod is healthy; both 2026-starting grids carry a phantom 2029. [D-079](DECISIONS.md) (round-1 picks flat across years) is why it turned acute — a 2029 1st prices identically to a 2026 1st, so the generator reached for far-dated firsts freely.
- **The blast radius, measured read-only on prod:** **339 of 2,651 served cards (12.8 %; 23.2 % of pick-bearing cards)** offered a phantom 2029 pick, 360 mentions, all in the operator's league, concentrated on 8/17–8/19. **12.9 % of all recorded like/pass outcomes** landed on one — and the skew matters more than the volume: phantom cards drew **6.7 %** of likes but **15.8 %** of passes and **21.4 %** of not-interested. **That window of preference data is contaminated** and should not be used as a clean propensity or bake-off baseline; a model tuned on it has partly learned "picks get passed on" from cards rejected for being nonsense.
- **Fixed at the WRITER, not at presentation.** The serving path has no season predicate anywhere — `load_draft_picks` returns every row, `_inject_owned_picks` puts picks on rosters, and all three engines then pick them up implicitly because they build pools off rosters. A presentation filter would have hidden the phantom while still letting it consume generation work and distort every score computed over the pool. New pure helper `draft_status.pick_horizon()`; `sync_draft_picks` builds over it.
- **Kill switch `picks.league_horizon`, default ON** — OFF restores the historical window byte-for-byte. Rollback is deploy-free *and* data-complete: the sync is a **replace**-sync, so no migration and no backfill is needed in either direction (stale rows die on the next `session_init`, and flipping the flag off rebuilds them).
- **Scope deliberately held:** MFL enumerates the real `futureDraftPicks` export (no phantom); ESPN has no platform pick source at all; the manual assignment grid (`seed_pick_grid`, `current + 3`) is a **recorded operator decision** wired into the assignment progress denominator, so it was left alone and logged as [Q-022](OPEN_QUESTIONS.md) rather than changed unilaterally. Zero ESPN pick rows exist in prod, so that exposure is currently theoretical.
- **ID collision worth knowing:** the reserved `D-089` was already taken on `origin/main` by the settings-IA work that landed after `28c12a0`; this decision is **D-091**. `Q-022` was free as reserved.

## 2026-08-19 (Current-year picks read as their real draft slot; NOT SHIPPED, on `feat/pick-slot-labels`)

- **An owned 2026 pick now reads `2026 1.08`, not `2026 1st`** — and `2026 1.08 (from mattmurf77)` when acquired, because a slot says WHERE the pick picks and the suffix says WHOSE it was. Answers the operator's 2026-08-19 TradesHome report. [D-090](DECISIONS.md), [scope](../docs/plans/pick-slot-labels/scope.md).
- **The standing "we can't resolve a slot" position (operator, 2026-07-18) is NARROWED, not overturned.** Its premise is now false for the current year: a slot is the league's draft ORDER composed with `draft_picks.original_roster_id`, and both sources are already paid for — Sleeper's `draft_order` **rides the `/league/<id>/drafts` payload `_sync_sleeper_owned_picks` already fetches** for #228, and a user-assigned ESPN board's order is already in `pick_assignment_settings`. **Zero new upstream calls.** The pricing half of the decision is untouched: every pick of a round still costs the Mid rung.
- **New `backend/pick_slots.py`** (dependency-free: no Flask, no `database`, no HTTP) + additive `leagues.draft_slot_order`. **The ORDER is stored, the SLOT never is** — renumbering must never touch an owner (D18). Three refusals return today's generic label rather than a guess: an unset `draft_order` (Sleeper's pre-draft `slot_to_roster_id` identity map is never read — the D5 rule), any season but the stamped one (#273 — nobody knows 2027's order), and a snake with `reversal_round` set.
- **`server._owned_pick_label` stays the single formatter**, gaining an optional order argument threaded through all five sites (eveners, `/api/league/picks`, the Matches name arrays, deck cards, power-rankings draft capital). **Zero mobile/web/extension files changed** — every client already renders the server string.
- **Flag `picks.slot_labels`, ON**; kill value restores the pre-D-090 string byte-for-byte and short-circuits before the DB read. **Display only, pinned:** no seed, band, `pool_value` or engine input moves in either state.
- **Sized in prod (read-only):** current-year picks are in **469 of 2,651 served cards (17.7 %)** — but 451 of those are the operator's own league, one of only **3 of 12** leagues that still hold 2026 picks (#228 deletes them at draft completion). `pytest backend/tests` 3480 → **3508 passed, 1 skipped**.
- **Left for the operator ([Q-023](OPEN_QUESTIONS.md)):** should the slot drive PRICE? Measured, not built — on DP's 2026 curve a 1.01 is **+130 %** and a 1.12 **−61 %** against our flat 2117 (5.9× inside one round); on the operator's league that would move **48 of 48** values and **38 of 48** tier badges. Cross-client pricing call, not a polish item.

---
## 2026-08-19 (Settings IA — hub page + seven sub-pages, and Settings stops being a modal; NOT SHIPPED, on `feat/settings-ia-hub`)

- **`account.settings_hub` registered, default OFF** (`config/features.json`, `backend/feature_flags.py` `FLAG_KEYS`, `docs/config-reference.md`, and the `backend/tests/fixtures/flags/release.json` mirror the seed test asserts against). The flag is a `SettingsRoute` **wrapper in RootNav**, not a branch inside `SettingsScreen`: that screen opens six queries and two fetches from hooks at the top of its body, so a branch inside it would still pay all of it on every open — the hub's zero-network promise would have been fiction, and an early return above those hooks is a rules-of-hooks violation. Mounting one component or the other is the only version that is both legal and honest.
- **The 1,712-line `SettingsScreen` split into twelve section modules** under `mobile/src/screens/settings/sections/`, each owning its own queries and state, plus a shared `Row.tsx` and a `styles.ts` lifted verbatim so the extracted sections render identically to the flat list. One intended behavior change (plan F4): the full-screen `prefsQuery.isLoading` gate is gone **on the hub path only** — it is still live at `SettingsScreen.tsx:745` on the flag-off flat list, and dies with the legacy branch in phase 4. (This corrects the phase-0 commit message, which claimed it was gone outright.)
- **A hub that fires zero settings queries.** Previews read the session store and two non-reactive `getQueryData` peeks; anything not free is **not rendered rather than guessed**. Trade values therefore has no preview at all — stud tax and pick pricing are read by bare effects with no React Query key, so "Stud tax: Market" would have been the code default printed as the user's setting. The notifications preview counts the **three delivery toggles**, not four: folding quiet hours into the numerator let "3 of 4 on" go **up** as the user turned notifications off.
- **Settings is a pushed page, not a `presentation: 'modal'` sheet ([D-089](DECISIONS.md#d-089--settings-is-a-pushed-page-not-a-modal-130s--is-removed-rather-than-reverted)).** `HeaderClose` / `settings.close-btn` are deleted with the presentation — **#130's ✕ is removed, not reverted**; the back chevron is the discoverable control it was reaching for. `navigateFromSettings` collapses to a plain `navigate` (the goBack-first branch existed only to escape the modal, and on a page it pops Settings so Back can never return), and the flat list now mounts a `FeedbackFAB` too — it had none only because #188 exempts modals and it was one. **The flip is registered on the route, outside the flag,** so it applies in both flag states; flipping `account.settings_hub` false restores the flat list but **not** the modal presentation or swipe-down-to-dismiss. Operator accepted 2026-08-19; `docs/plans/settings-ia-hub/scope.md` §2's original "no deploy, no rebuild" rollback claim is corrected in place.
- **Three structural checks encode plan §4 as an executable contract** — `mobile/tests/check-settings-ia.js` / `check-settings-nav.js` / `check-settings-testids.js` (`npm run test:settings-ia|settings-nav|settings-testids`): no section orphaned or duplicated, all 34 rows resolving to exactly one module, no settings route carrying `presentation: 'modal'`, every page mounting the FAB, `settings.close-btn` gone from src **and** the capture flows. **Verified by mutation, not by reading** — restoring the modal, swapping the Sign out / Delete account order, and renaming a shipped testID each fail with an accurate message. Like the other 56 suites they are `npm run`-only and gate nothing in CI.
- **Gates:** `tsc --noEmit` exit 0; `testid-lint.sh` OK; 59/59 structural assertions pass. **`pytest backend/tests` was NOT green** — 5 failures that reproduce on a clean `origin/main` checkout and predate this branch (see `HANDOFF.md`).
- **What is NOT done.** Nothing is merged; `main` is untouched. `account.settings_hub` is default **OFF**, so no user is on the hub. **Phase 4 is not started** — the flag is not graduated, `account.settings_v2`'s dead legacy branch is not deleted, and the flat list is still in the binary. **There is no runtime evidence of any kind**: the 10-item operator TestFlight checklist in [plan §9](../docs/plans/settings-ia-hub/plan.md) is unrun, and under D-056 it is the only runtime evidence this change can get. Two doc updates the scope block promised are still owed: `living-memory/LLD.md` and `mobile/src/screens/CLAUDE.md`.
## 2026-08-19f (bake-off: the outlook lane that filled zero — NOT SHIPPED, on `fix/bakeoff-outlook-lane`)

- **Reported:** the bake-off's outlook lane filling **0 of 5** slots and 10-card decks arriving from an arm that generated 37–40 candidates — the pair of symptoms that put `bakeoff_serve_interleaved` back to dark. ([D-086](DECISIONS.md), [scope](../docs/plans/three-model-bakeoff/scope-outlook-lane.md))
- **The number that settled it, read-only from prod across all 18 runs (54 group-runs, 527 cards):** the `(none)` bucket is **0 in every single group-run**. Every pooled card carried a `lane`, so the label plumbing is healthy and `window` is **24.7 %** of live supply — not ~0 %. Not a plumbing bug.
- **What it actually was:** a 5/5 quota asks each group for 50 % outlook from a 24.7 %-outlook supply, and the value lane was capped at 5 and **forbidden to use the slots the outlook lane could not fill**. Per run: target 30, supply 29.3, within-group capacity 16.0, **served 13.8** — 40 of 288 fillable slots destroyed by the lane split alone.
- **Fix: lane reallocation (`bakeoff_lane_reallocate`, default on).** A lane extends into the other lane's unfillable slots **drawing only from its own bucket**, so no card ever occupies the other lane's slot and `lane_slot` stays literally true — the distinction from `bakeoff_fill_policy` = 1, which substitutes *across* lanes and flags it. **13.8 → 16.0 cards/deck.**
- **D-078's finding is fully preserved, and that was the constraint.** `short` is computed against the nominal 5/5 ask *before* reallocation and never rewritten; `pool` is untouched; the spill is recorded in a new `groups_json[key].realloc`. Asserted directly: `on[G1]["short"] == off[G1]["short"]`.
- **A re-tuned split was the obvious move and lost on its own arithmetic.** Replaying the 54 real pools: fixed 7/3 reaches 15.6/run, reallocation reaches **16.0 at every split from 5/5 to 10/0** — no magic number to maintain against drifting supply.
- **The remaining 16.0 → 30 gap is a different defect and is named, not absorbed:** the group partition strands surplus (one run held 37 cards in one group and zero in the other two). That is the concurrent arm-C forfeit work.
- **Open:** `current_divergence` produced **0 `window` cards out of 23** while `gen_v2` — also divergence-basis, same user and week — produced 16.2 %. Suggestive at p ≈ 1.4 %, too small to call ([Q-020](OPEN_QUESTIONS.md)).
- **Gates:** pytest **3441 → 3448 passed, 1 skipped, 0 failed** (+7). Zero files under `mobile/` changed. `bakeoff_serve_interleaved` deliberately **not** touched. Not pushed, not merged.

## 2026-08-19d (arm C per-stage kill counts — the forfeit was a supply fact; NOT SHIPPED, on `fix/armc-gen-v2-forfeits`)

- **Arm C is not broken — it is the best divergence generator in the bake-off, and nothing has ever let it reach a user.** `cards=0, forfeits=9` was read as a broken generator. Per-league it collapses: arm C returns 0 **only** in leagues `62846` and `11896`, and 6–16 in all 11 runs of league `1312140920132497408`. The reported "9 forfeits → 2 overnight improvement" was two different leagues being compared. ([D-087](DECISIONS.md), [scope](../docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md))
- **Cause: no boarded opponent.** `member_rankings` has **zero** rows for `62846` and one user's for `11896` (the requester himself) against 4,416 rows / 6 users for `1312…`. Arm C is divergence-only by design, so those leagues give it nothing; `gen_ms` of **3** vs 221 is it returning at the `boarded` loop before enumerating anything.
- **The aggregate "15.2 % divergence exists" does not rescue the bug theory.** 96.8 % of all-time divergence impressions (1,196/1,235) come from the single league with ≥3 boards; the boardless leagues have **zero divergence impressions ever**. The control is decisive: arm `current`'s own divergence pool is **0 in all six runs** there too — while in the boarded league arm C's pool is 6–16 (median 7) against arm `current`'s median **1**, with arm `current` producing no divergence at all in 8 of 11 runs.
- **Zero `gen_v2` impressions is SERVING, not generation.** `served_arm = 'current'` on every run (`bakeoff_serve_interleaved = 0.0`, dark), so `model_arm` can only ever be `current` or NULL. Arm C already contributed 6 of 6 composed cards to the interleaved deck that is not served. Left at 0.0 — re-lighting is the operator's call.
- **Fix = instrumentation, no behaviour change.** `GenerationReport.kill_counts()` emits every stage in pipeline order (`S0` supply → `S1` selection → `S2` enumeration → `S3a-d` gates → `S4`/`S6`) plus a `starvation_reason` non-null only when nothing was enumerated; `gen_v2_cards` keeps the report it used to discard and adds its own `S7_intent_filter` / `S7_headliner_cap` kills; it lands on `bakeoff_runs.arms_json[arm].diagnostics`. No gate, knob, pool or ordering rule touched.
- **One real bug fixed alongside:** `run_row` looked forfeits up by ARM against a GROUP-keyed dict, so arm `current` (groups `current_divergence` + `current_consensus`) recorded a flat **0 in all 18 rows ever written** while arm C's key coincidentally matched. `forfeits_for_arm()` now sums over an arm's groups.
- **Gates:** pytest **3441 → 3449 passed, 1 skipped, 0 failed** (+8). No TS/mobile/web file changed. Not pushed, not merged.

## 2026-08-19c (the round-3 badge was a wrong inverse, not a price — NOT SHIPPED, on `fix/pick-round3-value`)

- **Verified the compression claim, then found it was not the cause.** [D-084](DECISIONS.md) attributed a current-year 3rd badging "2nd" to `seed_elo_for_value`'s floor compression. The compression is real — re-derived on the checked-in DP snapshot, ranks 200→300 span Elo 1262.9 → 1208.0, **100 ranks inside 54.9 Elo points**, one eighth the resolution of ranks 50–100 — and it does make market-rank alignment for 3rds/4ths unreachable via seeds. It just is not what produced the badge. ([D-088](DECISIONS.md), [memo](../docs/reviews/2026-08-19-pick-badge-scale.md), [scope](../docs/plans/pick-badge-scale/scope.md))
- **Root cause: `GET /api/league/picks` used the wrong inverse.** `pool_value` is in `elo_to_value` units (`database.py:1040` says so), whose exact inverse is `trade_service.value_to_elo`. #320 inverted it with `seed_elo_for_value`, which inverts DynastyProcess's raw 0–10000 scale. **The two maps agree at exactly Elo 1548.0** and diverge either side, inflating every rung below a mid-1st: Mid 3rd **1320 → 1383.5** (+63.4), Mid 4th 1240 → 1339.3 (+99.3), Late 4th 1220 → 1329.5. The map error was **4.7× the 13.5-point margin** that flipped the badge; the pick's real price sits 45 Elo *inside* `third`. Third instance of the #263 scale-confusion class ([G-052](GOTCHAS.md)).
- **Fix is one expression. Nothing was repriced.** `GENERIC_PICK_SEEDS`, `tier_config.json`, all five client mirrors and every stored `pool_value` are byte-unchanged, so the bright-line five-mirror rule was never triggered and `test_tier_occupancy.py` is untouched at 47 passed. `seed_elo_for_value` is removed from `server.py`'s imports so the wrong tool is out of reach there.
- **Display blast radius is bigger than the report: 600 of 1,104 live pick rows (54.3 %) change badge**, computed both ways over the actual stored prod values (7 leagues, read-only). Current-year 3rd `second` → **`third`**; current-year 4th `third` → **`fourth`** (wrong since #320, unnoticed because `third`'s old max covered it). A 2029 4th prices at Elo 1142.5, below the `waivers` floor, so it now carries **`null`** and the client falls back to the numeric — more honest than claiming it is worth a 3rd.
- **The prod numbers argue against ever repricing rounds 3–4:** 3rd-round picks are in **27 of 2,376 served cards (1.1 %)** and 4ths in **zero**; picks are in 55.9 % of cards but firsts are 80.9 % of mentions. [Q-019](OPEN_QUESTIONS.md) closed; the seed-map half re-logged as **Q-021**, correctly sized as an every-player-board change.
- **Gates:** pytest **3443 passed, 1 skipped, 0 failed** (baseline 3441 + 2 new tests); `tsc --noEmit` clean; `testid-lint OK`. New pin is a *property*, not a literal: a current-year pick of round R must badge where `GENERIC_PICK_SEEDS[(R, "Mid")]` sits. Not pushed, not merged.

---
## 2026-08-19b (give-side headliner cap — the flood the existing cap could not see; NOT SHIPPED, on `fix/deck-give-headliner-cap`)

- **The cap that was supposed to stop this was on, and killed nothing.** Operator: *"the model will spit out 4 or 5 varieties of offers with Davante included."* His deck `2740a7fc` — 22 cards — had Adams on the give side of **6**, `1466` on **6**, Mayfield on **5**: **17 of 22 cards were three players**, with `deck_headliner_cap` = 2 in force. ([D-082](DECISIONS.md), [scope](../docs/plans/deck-give-headliner-cap/scope.md))
- **Root cause, read off the column the cap keys on.** That deck stamped **20 distinct `centerpiece_id`s across 22 cards**. `deck_centerpiece` maxes over give **+ receive**, so on "give Adams, get a 2028 1st" the *pick* is the centerpiece — and every card offers a *different pick slot*, so every card is unique and a cap of 2 can never fire. [D-079](DECISIONS.md), shipped hours earlier, made it worse: every 1st now sits at Elo ~1650, so picks out-Elo more players.
- **Fix: a second cap on a second definition — `deck_give_headliner_cap`, default 3, kill value 0.** Keyed on the **give-side headliner** (highest seed Elo among the give assets, **players preferred over picks**). `deck_centerpiece` is left byte-for-byte alone *on purpose*: it is also the decline-time fatigue key, so re-keying it would silently change which past declines suppress which future cards.
- **Applied on all three generation paths, not one.** `_dedup_and_sort` covers the v1/v3 engine; the `trade_gen.v2` branch and `bakeoff_runner.gen_v2_cards` (bake-off arm C) both `return` before that method ever runs and needed the call explicitly — otherwise arm C would be the only group allowed to flood and the bake-off would compare arms under different rules. Arm A pins it to 0; **no golden re-capture was needed**, because the kill value returns the list unchanged.
- **Decks get thinner, measured rather than hand-waved.** Replayed over 66 prod candidate pools (1,925 served cards): **10.1 % of cards drop**, median deck **29 → 26.5**, worst deck 36 → 24, and per-deck worst repeat goes from a median of 6 (max 13) to exactly 3 everywhere. No deck approaches the `_DECK_MIN_CARDS` = 5 floor. Cap 2 would have cost 23.8 %; cap 4 still permits the reported defect. **Leave-short, never backfill** — a backfill would put the same headliner right back and would hide the hole from `bakeoff_runs.groups_json[...].short`.
- **Gates:** pytest **3416 → 3427 passed, 1 skipped, 0 failed** (+11). Zero files under `mobile/` changed. Two sabotages applied, observed red, reverted. Not pushed, not merged.

---

## 2026-08-19 (round-2 picks repriced to market rank; the `second` tier floor moves with them — NOT SHIPPED, on `feat/round2-pick-recalibration`)

- **The operator was right, and KTC's published numbers say the opposite.** KTC's mid 2nd:1st is 0.697 to our 0.387, which reads as "our gap is twice too severe". It is a scale artifact — KTC's scale is bottom-compressed, and transplanting 0.697 would price a mid-2nd at the **86th**-best dynasty asset, above George Kittle. The scale-free measure is player-rank equivalence, on boards first verified to rank *players* identically: our Mid 1st is **exact** (rank 65 vs a market median of 66.5) and our Mid 2nd is the **119th** against a median of the **141st**. KTC '26/'28, FantasyCalc and DynastyProcess are all cheaper than us. ([D-084](DECISIONS.md), [memo](../docs/reviews/2026-08-19-ktc-pick-value-comparison.md), [scope](../docs/plans/round2-pick-recalibration/scope.md))
- **Round 2 only: 1520/1460/1400 → 1470/1400/1370.** Mid 2nd:1st falls 0.387 → **0.287**; the Mid 2nd lands at rank ~136 against a target of 140.5. **Round 1 is untouched** — it is the one part of the ladder the market fully endorses. Rounds 3/4 are untouched because they are *not fixable via seeds* ([Q-019](OPEN_QUESTIONS.md)).
- **This is a tier change, not just a pricing tweak.** `tier_config.json`'s `_calibration` makes each tier's floor a rung of the pick ladder, so `second.min` 1400 → **1370** and `third.max` 1395 → **1365** moved in the *same commit* across all 8 (format, position) blocks — plus every client mirror. 2–5 players per position/format move up from `third` into `second`; `second` peaks at 32 against a ceiling of 35.
- **Five mirrors, and they are not the same kind.** Mobile (`tierBands.ts`) and `web/positional-tiers.html` hold pre-fetch fallbacks that `/api/tier-config` overwrites at boot; **`web/js/app.js` is a pure hardcode that never fetches** and can only drift silently ([G-051](GOTCHAS.md)). The extension is genuinely clean. All updated.
- **⚠️ One badge looks wrong on purpose: a current-year 3rd now reads "2nd."** It prices at Elo 1383.5 through `seed_elo_for_value` — 16.5 below the old floor, 13.5 above the new one. That is the pre-existing round-3 overprice becoming visible, not a banding defect; 2027+ 3rds and every 4th still badge `third`. Pinned with an explanatory note and made step 9 of the TestFlight checklist so it is expected, not reported as a surprise.
- **No knob, deliberately** — unlike [D-079](DECISIONS.md). A seeds-only `model_config` key would desynchronise the exact seed/band pair this change exists to keep in step, and would buy no revert speed (`TIER_CONFIG` is read once at import). Revert = revert the commit and redeploy; **clients re-fetch `/api/tier-config` at boot, so no client release is needed.**
- **The prod answer, and it is a "no".** Read-only: cards containing a 2nd are liked at **34.8 % (n=46)** vs **35.2 %** for cards with no pick at all (Fisher **p = 1.00**); 2nds touch only 13.7 % of served cards, and zero of 23 free-text passes mention one. The measurable pricing pain is in **1sts** (1st-on-give 15.6 % liked vs 1st-on-receive 47.1 %). **Shipped on the rank measurement, not on acceptance data — expect no lift.**
- **Gates:** pytest **3429 passed, 1 skipped** — byte-identical to the `93ac695` baseline; `tsc --noEmit` clean; `testid-lint OK`; `test_tier_occupancy` 47 passed. The pre-retarget run failed **exactly the eleven** the memo predicted, no more and no fewer. The M6b scorecard moved −0.40 → **−0.284** and was rewritten to pin the value with the remaining gap declared intentional. Not pushed, not merged.

---

## 2026-08-19 (draft-pick year decay is per round; firsts stop decaying — NOT SHIPPED, on `feat/pick-year-decay`)

- **One constant was pricing every pick, and it was the whole bug.** `pick_values.YEAR_DISCOUNT = 0.85` took 15 % off a pick per season it sat in the future, *regardless of round*, on all four pricing paths. A 2029 1st therefore priced at **1300.1** against a 2026 1st's 2117.0 — 61.4 %. The operator reported the fallout three times across two sessions ("1st round picks seem undervalued"; "Another example of a random 1st swap. Shouldn't happen"; "I think 2029 1st values are the issue… Offering him for a 1st is nonsense"). Both symptoms trace to that one number. ([D-079](DECISIONS.md), [review](../docs/reviews/2026-08-19-pick-year-valuation.md), [scope](../docs/plans/pick-year-decay/scope.md))
- **The decay rate is now per round, and round 1 is flat** — a 2029 1st prices exactly like a 2026 1st (2117.0). Rounds 2–4 keep the shipped 0.85, which is also the best-corroborated number available (KTC's 1QB crowd rates for those rounds are 0.860 / 0.860 / 0.856). Four `model_config` knobs (`pick_year_decay_r1..r4`); all four at 0.85 restores the old ladder with **no deploy**.
- **Measured, not assumed.** Against 2048 prod `deck_impressions`: **58.5 %** of served cards contain a pick, firsts are **84 %** of pick mentions, and **99 cards (4.8 %)** moved a 1st one way and a different-year 1st the other. That last number *is* the "random 1st swap" complaint, counted — and it exists because two 1sts of different years were different-priced instances of the same asset. Flat firsts make the gradient exactly zero, so that card class becomes unreachable by a value-seeking search rather than filtered afterwards.
- **The operator's exact card, and the gate that let it through.** Impression `c67c2fd1e97cb6bf`: give Davante Adams (consensus 1138.8), receive a 2029 1st (1300.1). `overpay_ok` kills at gap ≥ 500 **and** ≥ 25 % of the big side; 161.3 / 12.4 % missed both. At 2117.0 it is 978.2 / 46.2 % — killed. That verdict flip is the code-walk proof (D-056: no simulator), asserted as a boolean.
- **⚠️ We now price firsts above every public market source, deliberately.** DynastyProcess publishes an explicit flat 20 %/yr rule; FantasyCalc's 2027→2029 CAGR for firsts is 0.80; KTC's 0.83 — and **three of four sources discount firsts *harder* than later rounds**, the opposite of the model shipped here. The operator's direction stands as a product call, and flat is the only rate that structurally kills the swap defect, but the divergence is real and logged as **[Q-018](OPEN_QUESTIONS.md)**, revertible with one config write.
- **Two deliberate second-order effects.** A far-out 1st now badges `first_1` instead of `second` (D-320-2's *rule* is unchanged — the badge still reflects today's value; the value moved, and the old badge was itself a symptom). And the four knobs are **excluded from bake-off arm A** — they price an asset rather than choose a package, so pinning arm A would confound generation policy with a repricing; reason recorded where the guard demands it.
- **Gates:** pytest **3404 → 3416 passed, 1 skipped, 0 failed** (+12). Zero files under `mobile/` changed. Seven existing test files retargeted, each to assert the new intent *plus* a still-decaying round. Not pushed, not merged.

---

## 2026-08-19 (decline reasons — "Neither" gains player preference; NOT SHIPPED, on `feat/decline-reason-player-pref`)

- **The 47% bucket now has codes.** The first production burst of decline-reason capture was 19 passes in 9 minutes, and **"Neither" took 9 of them — the largest bucket and the only un-coded one** (it offered free text and nothing else). Its free text was overwhelmingly one reason: *"Don't like Troy"*, *"No need to move kelce"*, *"I just traded marshawn Lloyd away…"* — **player-level preference**, a third axis the taxonomy did not have. The tile now carries structured options ([D-080](DECISIONS.md#d-080), [SPEC §2a](../docs/plans/decline-reason-capture/SPEC.md), [scope](../docs/plans/decline-reason-capture/scope-player-preference.md)).
- **Two codes, not one, and that is the whole decision.** `other_player_keep` ("Won't trade one of my players") is a **give-side keep-list** signal; `other_player_avoid` ("Don't want one of their players") is a **receive-side avoid-list** signal. Different code paths — package construction vs. candidate sourcing — so one merged code would force reading free text to route the fix, which is exactly what made "Neither" a black box. Both poles are attested at n=4 (Kelce outgoing; Troy and Lloyd incoming). `other_text` stays as the residual "Other → free text" row, last, as on every tile.
- **No schema change, no migration, no backfill.** `trade_pass_reasons.detail` is a free-form `String`; the vocabulary lives in `database.PASS_REASON_LAYER2` and `PASS_REASON_PARENT` derives from it, so the route's `invalid_detail` / `detail_reason_mismatch` 400s pick the codes up for free. **No new analytics event and no new property** — `trade_pass_layer2.detail` widens 8 → 10 values, emitter untouched, `NON_INTENT_EVENTS` unchanged.
- **Elo unchanged, and `other_player_keep` is the near-miss worth naming.** "Won't give up my guy" *looks* like `value_giving`, but it is attachment, not a market-value claim — "not this player at any price" is the opposite of a statement about price. Both codes suppress **structurally**: `PASS_REASON_ELO_KEEP` is an allow-list of one.
- **`other_text` kept its meaning but changed its population** — before today it was *every* "Neither" answer; after, only what the two player codes did not absorb. Cohort any before/after comparison on 2026-08-19. Recorded in the data dictionary.
- **Two things found on the way.** (1) **`SPEC.md` was untracked** — the operator-approved contract for a shipped feature lived only in one checkout's working tree, so the structural suite's "codes still match SPEC §2" cross-check had been silently taking its `existsSync` SKIP branch and had never once run. Committed; it runs. (2) The old free-text-only "Neither" rendered its composer straight from the tile tap and **banked nothing**, so a tester who opened it and bailed left `detail = NULL`; the "Other" row now banks `other_text` before the box opens, per SPEC §3.3.
- **Gates:** pytest **3404 → 3417 passed, 1 skipped** (+13, zero regressions); `tsc --noEmit` clean; all **56** `check-*.js` suites green; `check-decline-reasons.js` green (extended with an AST-based §6 that fails on a revert to free-text-only *or* a collapse of the pair); `testid-lint OK`. Manual TestFlight checklist written for the operator, **not yet run**. Nothing pushed, nothing merged.

---

## 2026-08-18c (bake-off deck composition — three groups of ten; NOT SHIPPED, on `feat/bakeoff-composition`)

- **The served bake-off deck is now composed, not just drafted** (operator decision; [D-078](DECISIONS.md#d-078--a-bake-off-deck-is-composed-of-groups-and-an-unfilled-quota-is-the-finding), [scope-composition](../docs/plans/three-model-bakeoff/scope-composition.md)). 30 cards from three **groups** of ten — arm `current`/`divergence`, arm `current`/`consensus`, arm `gen_v2` — each split 5 value / 5 outlook, mapped onto the fields that already carry those axes (`TradeCard.basis`, `TradeCard.lane`; `window` **is** the outlook lane). No new taxonomy.
- **The groups interleave, not the arms.** Arm `current` holds two of the three groups, so a per-arm rotation hands it two of every three slots and leaves arm `gen_v2` in the tail. Measured on identical inputs: per-arm concatenation puts arm C at mean deck position **24.5 of 30**; the group draft puts it at **14.5**, and over 500 decks all three groups sit at 14.48–14.55 with the two lanes at 14.52 / 14.48.
- **Arm A left serving by configuration, not deletion.** `bakeoff_include_baseline` = 0. `MODEL_A_PROFILE`, `model_a()`, the arm-A golden and the 189-key knob-inventory guard all stay and still pass — asserted directly, not assumed. It was also the slowest arm (4.19 s of the 7.36 s three-arm fixture), so the fan-out cost Phase 4 was told to watch roughly halves.
- **An unfilled quota is the finding, so the default leaves the hole.** `window` is only ~19% of live divergence supply, so a divergence group needs ~25 surviving cards before it can expect five outlook cards (consensus clears at ~20). Shortfalls are recorded per (group, lane) in the new `bakeoff_runs.groups_json`; `bakeoff_fill_policy` = 1 backfills from the group's own other lane, flagging every substitute `deck_impressions.lane_slot = 'fill'` and still recording the shortfall.
- **Absent `lane` is its own bucket** — never value, never outlook, reachable only as flagged fill. And when *nothing* in a group's pool carries a lane the axis is undefined for that deck (no window direction, or `trade.lanes` off), so the split goes inert rather than serving an empty deck to every `not_sure` user.
- **Two plumbing gaps closed so the test compares generators.** `_generate_trades_impl`'s v2 branch applies the #172 intent filter to gen-v2's output, and `classify_lane` runs *after* that branch returns — so calling the module directly skipped both, and **no gen-v2 card has ever carried a lane**. Left alone, group 3's outlook quota would have under-filled 100% of the time and read as "arm C cannot produce outlook ideas". Arm C now gets both.
- **`trade_intent` captured, per the same rule that caught `fairness_threshold`:** record the gate that APPLIED, never the one requested. The requested and effective values genuinely diverge (`_generate_trades_impl` resolves the request to None whenever `trades.intent_modes` is off; the route already drops out-of-vocabulary values). The user-facing trade settings stay visible during the bake-off — testers are briefed verbally — so a tester can move the intent chip mid-test and shift every group's basis/lane mix.
- **Analysis shape is asymmetric and the docs now say so.** Groups 1 vs 3 is the clean head-to-head; group 2 is a **consensus reference slice with no arm-C counterpart** (arm `gen_v2` is divergence-only by construction). The documented clean-comparison query groups by `(model_arm, group_key)` for exactly that reason, and a test executes it.
- **Gates:** pytest **3363 → 3404 passed, 1 skipped, 0 failed** (+41 tests, zero regressions). Flag-off golden byte-for-byte unchanged, with the four new columns asserted NULL on every row. Flag `trade.bakeoff` stays **OFF**; nothing user-visible ships.

---

## 2026-08-18b (bug-sweep follow-ons 3/4/5 + two research verdicts — NOT SHIPPED, on `feat/sweep-followups-2026-08-18`)

- **`swipe_guard_blocked` (D-071).** The B4 stall produced **zero telemetry** — fifty taps, no events — which is why it took a user report. One event covers **both** deck guards (`guard` prop discriminates); emission is **laddered** (`1,2,3,5,10,25` per card, 50/session) so a trapped user's fifty taps land as six rows topping out at `blocked_n=25`. Tracking-plan addendum written first, per the taxonomy's default-deny precondition. **Contested call recorded:** not added to `NON_INTENT_EVENTS` (affects DAU/WAU) — reasoning is pinned by a test, one line to reverse.
- **`is_pick` on `/api/trade/values` (D-072).** Five clients each re-derived pick identity from `team == "PICK"`; that inference shipped #222 and the B3 sweep. Now explicit and additive — `_PICK_POS` untouched (load-bearing for trio/rank tab distribution). Only an *explicit boolean* is authoritative, so a client on an older server can't read `undefined` as "not a pick". `cross-client-invariants.md` gains the **mirror-locations table** whose absence let the drift go uncaught. The orchestrator wired the field through `CalcValueRow`→`CalcPlayer` and all three mappers — without that the field reached nothing.
- **Replayed-pass guard (D-073) — and G-049 was wrong.** `_compute_elo` replays **`swipe_decisions`**, not `trade_decisions`, so the unique constraint everyone reached for would have fixed **nothing measurable**. A constraint is also unavailable: `retracted_at` (#318) makes duplicate rows *deliberate*. Prod (933 rows) split duplicates into **40 double-writes at 0.015–0.200 s** vs **23 genuine re-decisions at 147.7 s+** — a **738× empty band**, which is what makes a 10 s window safe rather than a guess. Guard returns `bool`; **both** route call sites gate the Elo write on it. `check_for_match` deliberately not gated — nor is `record_trade_signal`: it writes derived in-memory state that `replay_from_db` rebuilds from `swipe_decisions` each `session_init`, so gating it would trade a bounded, self-healing 2x overcount for an unbounded 0x undercount on a DB blip. A **route-level** test now POSTs the swipe twice against a real DB with the real `save_trade_swipes` and counts rows — the `inspect.getsource` pins could only see a gate's *text*, not whether it worked.
- **Two tests proved a MODEL of the code, not the code.** The idempotency suite defined its own `swipe_once()` helper, so both route call-site gates could be deleted with every test green — caught by sabotage, closed with `inspect.getsource` route pins. Earlier in the sweep the tier test passed with the direction comparison inverted. Recorded as the running theme in **G-050**.
- **Research: the spotlight bug was worse than the ticket.** The banner theory was mostly a false alarm — two named suspects disproven (`TradingWithStrip` is height-stable; `VerifyAccountBanner` is absolutely positioned *by design*). The real gap is the **keyboard**: SignIn spotlights the username field and asks the user to type; its `KeyboardAvoidingView` (`behavior:'padding'`) shrinks a centre-justified body and the field travels up ~150 pt while the ring stays. **First spotlight of the tour, every first-run user** — a larger blast radius than the scroll bug just fixed, and structurally uncatchable by the shipped `onScroll` fix because that screen has no scroll container. Fixed with two `Keyboard` listeners in `AnalystGuide.tsx`; zero host changes (a notifier in `SignInScreen` would fail the suite's rule 9b). Rotation closed: portrait-locked on iPhone.
- **Research: the QuickSet regen stall is real and reachable.** `trade_id` *is* freshly minted per card — but `/api/trades/generate` shares a still-`running` job **verbatim even under `force`**, so ids recur. The QuickSet handoff cleared the deck without clearing the guard, dropping the job, or bumping the epoch, so the stale job refilled the emptied deck and stranded the user right after the "That's your board now" toast. Fixed. The unsound `setDeck([])` test exemption removed — the rewind scan went **4 → 9 sites**.
- **Flagged, not changed:** `/api/trades/generate`'s in-flight share ignores `force_fresh` (API contract, bright line). Routed to the "Matchmaking model research agents" session, which owns that area.
- **Gates:** pytest **3191 passed / 1 skipped**; `tsc --noEmit` clean; **56** `check-*.js` suites; testid-lint OK. Every new assertion sabotage-verified. (Follow-up pass, after a rebase onto the engine-quality `main`: **3219 / 1**; see TEST_LEDGER 2026-08-18c.)

---

## 2026-08-18 (operator bug sweep B1–B5 — five reports, four of them not where they looked)

- **B4 — a failed pass trapped the user permanently** (the headline). `swipeMutation.onError` rewinds the deck to re-front the failed card but never cleared `lastDispositionedRef`, so every later ✕/✓/swipe on that card hit a bare `return` at `TradesScreen.tsx:3846`. No error, no visual change, no escape but a league switch. Six other sites clear that guard — one with a comment describing this exact hazard — `onError` was simply omitted. Reporter `jonbonjourvi` (FFv3) was on a pre-116 build where the ✕ still renders; the defect is build-independent. Trigger unproven (no prod logs): `/api/trades/swipe` is in `NO_RETRY_PATHS`, so a 502/503 is never retried; a 403 verification gate fits "no way past it" best. **The pick-heavy package was incidental** — `trade_id` is server-minted, not client-hashed; that hypothesis was tested and disproved.
- **B2 — the "Tier down" button was already correct.** The bug was the tier-target chips ("Move to 3rd") and the VoiceOver action, both appending to the tier's END. Backend Elo spread is order-preserving (`ranking_service.py:1419-1427`), so persistence was never the culprit. Both are now direction-aware; **"move up" deliberately unchanged** (minimal-displacement, `TiersScreen.tsx:1552-1555`).
- **B3 — the PICK chip matched nothing** because `build_universal_pool` stamps generic rungs with a FAKE player position (`_PICK_POS = {1:"RB",…}`, `server.py:1464`) and marks them picks by `team == "PICK"`. The picker checked `p.pos` alone, so PICK was empty in the calculator's default mode while RB/WR/TE/QB wrongly listed picks. Client now mirrors `trade_service.is_pick_asset`. `_PICK_POS` untouched — it is load-bearing for trio/rank tab distribution.
- **B5 — picks rendered as raw ids on Matches, and on three sibling routes.** The serializers named assets from `players` only, falling through `get(pid, pid)`. "Mutual matches" had it too, and `/api/trades/matches` (web) was worse — it *dropped* picks, rendering a 2-for-1 as 1-for-1. Fixed backend-side so a Render deploy repairs every installed build with no app release; all four routes now share one ladder (session pool → `players_table` → pick label → raw id).
- **B1 — the spotlight never re-measured.** One-shot `measureInWindow` at step activation, absolute window coordinates, no scroll listener anywhere. Hosts now notify a pub/sub; the guide re-measures under rAF coalescing. Live path is v1 (`onboarding.guide_v2:false`), so both paths were fixed.
- **Method: two adversarial rounds.** Round 1 was **discarded** — it ran against a checkout 151 commits stale where `TradesScreen.tsx` differed by ~1,200 lines. Each bug's original researcher then reviewed the fix built from its own analysis and found **four real defects**, two of which would have shipped: a **new B2 regression** (double-tap teleported a player from the top of a tier to the bottom — the reported symptom), a **polarity-blind B2 test** (a reviewer inverted both guards and all 12 assertions stayed green), a **vacuous B5 test** (raised `AssertionError` inside `except Exception`), and **B1's viewport fix covering only the endpoint, not the transit**. Ticket + full disposition: [`docs/reviews/2026-08-18-bug-sweep/ticket.md`](../docs/reviews/2026-08-18-bug-sweep/ticket.md).
- **A ticket claim was corrected mid-flight:** `save_trade_decision` is a plain `INSERT`, **not** idempotent (no upsert, no unique constraint). That killed the planned Retry button — with the guard cleared, the card's own ✕ re-POSTs *and* advances, so Retry did strictly less while inviting a duplicate row and a doubled `trade_k_pass`. See **D-068**.
- **Gates:** pytest **3148 passed / 1 skipped** (baseline 3125 + 23 new); `tsc --noEmit` clean; **54** `check-*.js` suites pass; testid-lint OK. Every new test sabotage-verified RED→GREEN.

---

## 2026-08-18 (dismiss cooldown SHIPPED — a pass finally sticks; D-067)

- **A dismissed suggestion is now a hard exclusion, not a score demotion** (`505ca2c`, merged off `f2c81f6`). Operator report: identical suggestions in the same order between sessions. **Dispositions were saving correctly the whole time** — 496 passes / 314 likes in prod, and `_dedup_and_sort` filtered them properly. The bug was that `deck.fatigue` has two tiers and a dismiss only ever earned the weak one: a **score multiplier floored at `fatigue_floor = 0.25`** that demotes but never removes. The durable path (`deck_suppressions`, 30-day near-duplicate) fires **only** on `decision == "decline"` — a mutual-match backout — so `deck_suppressions` had **0 rows in prod**, having never fired for anyone. Measured symptom: one card served across **41 separate deck jobs** in 12 days.
- **Three fixes.** `pass_cooldown_days` (**14.0**) gives dismisses their own hard window, split from the 7-day like window that 61% of prod decisions had already aged out of. A dismiss now **binds immediately** to every service in `sess["trade_svcs"]` — `sess["trade_svc"]` is an alias for the *active format only*, so updating it alone left other formats stale (prod trace: one trade decided 5× in 6 minutes). Both knobs are the deploy-free revert (`pass_cooldown_days = 7.0` restores pre-fix behavior), so **no new feature flag**.
- **Legacy-dismiss amnesty** (`pass_cooldown_start_epoch`, default `2026-08-17T22:30:00Z`): dismisses recorded before decline-reason capture went live carry no reason, so the avoidance rule must not apply to them. Operator asked for "around 5pm est"; reason capture actually landed at **18:22 EDT**, so 5pm would have suppressed the very taps the amnesty protects — the default is set just past the verified landing instead. **Still owed:** the true boundary is when the reason-carrying *mobile* build reaches testers; raise the knob to that moment if pre-build dismisses should also be amnestied (one `PUT /api/admin/config` call).
- **Scope, deliberately narrow.** Exact-pair matching only — **not** the decline path's near-duplicate suppression, which would let one swipe silence a player's whole trade space. **Served-but-unacted repetition is untouched by operator decision**, and it is 98.5% of what the reporting user actually sees (4,003 impressions vs 61 decisions in 14 days). Measured thinning from the window change: **2 rows prod-wide**, against a 27.8-card average deck — so R-2 (the immediate bind), not R-1, is what fixes the symptom at today's volume.
- **Gates:** pytest **3125 passed / 1 skipped / 0 failed**; 15 tests, **8 named sabotages** each proven RED then reverted (incl. two-sided bars proving the cooldown *expires* and the amnesty is a boundary, not an off-switch). Deploy verified by content. **No TestFlight build cut** — the change is backend-only and main's mobile tree is byte-identical to v1.14.0 build 116.
- **Ledger note:** second decision-ID collision in two days — decline-reason capture claimed D-066 concurrently; this is **D-067**.

---



## 2026-08-17 (Decline reason capture LIVE + fairness default OFF — v1 feedback instrument)

- **The ✕ is gone.** A passed trade now asks *why* in two layers: three tiles (**Value · Fit · Neither**) where the tile tap **is** the pass, then the specific fault inline beneath it (Value: giving/getting too much · Other; Fit: outlook / new weakness / duplicate need · Other; Neither: free text). No receipt — the next trade is the confirmation. Design settled with the operator against `mockups/decline-reason-capture/07-two-step-diagnostic.html`; spec `docs/plans/decline-reason-capture/SPEC.md`.
- **Every tap commits.** `trade_pass_reasons` upserts per passed card (`impression_id` PK, `local:` surrogate fallback marked by `key_source` when `deck.signal_v2` is off); the FIRST write performs the pass, later writes only sharpen. `/api/trades/swipe` untouched ⇒ the flag is a structural kill switch.
- **Elo consequence (D-066):** a pass used to assert "I value my players more" for every decline. Now only `value_giving` keeps that write (claimed once via `elo_signal_at`); every other code suppresses it. Knob `pass_reason_elo_suppression=0` restores prior behavior with no deploy. **Not retracted** if a user later switches tiles — no negative-K path on this route.
- **Fairness default flipped OFF** (client pref, unset ⇒ 0.5 wide net; an explicit `on` is preserved) so testers see and judge a wider set — the reason capture is the instrument that grades it. Both read sites derive from one helper so pregen and the screen can't disagree.
- Ships **live for all users** (`feedback.decline_reasons: true`, no allowlist — operator decision). `trade_gen.v2` stays dark; feedback deliberately precedes v2 so pass reasons have a v1 baseline. Suite **3110 passed / 1 skipped**; 58 new backend tests, 38/38 mobile checks. **Sim gate waived by operator** — Maestro flows authored, unexecuted; TestFlight is the QA.

## 2026-08-16 (feedback wave: 17 items, 7 groups — presentment rules ON, calc labels graduated, mock-draft picks real)

- **The largest single feedback wave to date: 27 open items triaged, 17 built across 7 groups, one closed as already-fixed** (#329). Merge `20b40db` off `main` `92c31d5`. Specs branch `feedback-2026-08-16-specs`, integration branch `feedback-2026-08-16-integration`. Batch plan + every operator decision: [`docs/feedback/items/304-positional-need-filter/batch-plan.md`](../docs/feedback/items/304-positional-need-filter/batch-plan.md).
- **G6 — trade presentment rules (#304 #336 #339 #340 #341), flag `trade.presentment_rules` SHIPS ON** with 7 `model_config` knobs as deploy-free per-rule kill switches. Two-part design: construction rules (overpay ceiling enforced **independently of the client fairness toggle** — the "horrid trades" root cause was `fairness_floor_divergence=0.55` applying regardless; net ±1 per position; two-sided pick-gap band) + eligibility rules (window-scaled need gate on **untargeted decks only**; windowless matched/awaiting exclusion — #336's root cause was `past_decision_keys` loading `since_days=7`). Measured on the D-055 corpus: **18.4% combined kill, all 8 known insult cards caught, 0 empty decks, deck size 99.7% of flag-OFF** (construction-time kills with heap refill, never post-hoc filtering). [D-062].
- **G1 — calculator (#303 #306 #320):** `aggregate_tier_labels` **graduated** — pick-equivalent labels ("≈N firsts") now ship to every user, not just the operator allowlist ([D-064]); send button moved above the verdict card; pick rows carry tier badges at their **discounted** value ([D-065], supersedes #263). New cross-client invariant: aggregate values are pick-equivalent labels, never raw numerics.
- **G2+G3 — mock draft (#322-#328):** traded-pick ownership is now resolved **per platform at create** (Sleeper board / MFL `draft_picks` / ESPN's manual assignment grid) with an honest `platform|user|partial|none` label and caption — the #328 root cause was `server.py:12110` short-circuiting every non-Sleeper league to a randomized order with empty ownership ([D-063]). Room UI: ascending fixed-height ticker (1.01 at top, earliest scrolls off), tier chips in a 3-across grid, team sheet, pool filter + search, three new analytics events.
- **G5 — ESPN identity binding (#321):** wrong-account credentials are now **rejected instead of silently failing** (new `wrong_account` verdict → 403, wire code unchanged, additive `reason`); pre-release `verified_at` stamps evicted at boot (one-time re-sign-in for the small ESPN cohort). Blast radius was **bounded to same-device account switching** — server storage was always account-keyed.
- **G4 — offer prefill (#330):** Offer now lands on Find a Trade with the team scoped, the player hard-locked, and the search already run; honest empty state that never silently relaxes the constraint. **G9 — matches (#334 #335):** dismissed tiles stop resurrecting (a background refresh could repopulate the cache after the optimistic removal); hidden-aware counts on segments and team chips.
- **Gates (merged tree, orchestrator-run):** **pytest 3050/0**, tsc clean, **48/48 structural suites**, testid-lint OK. Phase-1 dual-agent loop raised **14 blocking + 33 non-blocking objections**, all resolved — two would have shipped real defects: a one-sided pick predicate that banned the operator's own stud-consolidation style, and a migration cutoff dated 6.5h **before** the fix it depended on. Phase-3 QA cleared 6/6 cross-group seams; Phase-4 closed 9 of 11 findings (two are ship-time operator items).
- **Process:** Maestro/sim n/a per [D-056] — operator TestFlight checklists are the runtime gate. A concurrent session's gen-v2 parity port caught an **internal spec contradiction mid-build** (a test gloss contradicting R-2's own formula); the formula bound, the gloss was corrected, and "recompute every worked example against its formula" is now a standing critique-round rule.
- **Owed:** operator prod-DB deck-eval replay (the build agent was permission-denied on `DATABASE_URL_PROD` — G6's bands are unmeasured on divergence boards + real like history); **#339's band defaults are untuned** (zero pick-carrying candidates in any corpus — `pick_gap_frac` is the named lever, NEXT.md); post-deploy `transition→decide` curls to retire `aggregate_tier_labels`; TestFlight passes per group; first-week `presentment-tripwire` watch on contender-heavy leagues.

---

## 2026-08-16 (rank nav: one exit per surface — SHIPPED, dark-free, device-unproven)

- **Back is gone from all 8 flag-on rank surfaces; "More ways to rank" now navigates to the RankHome chooser** ([PR #137](https://github.com/mattmurf77/fantasy-trade-finder/pull/137), `3a10751`). Operator called the redundancy: Back's fallback was RankHome and the RankMenu sheet listed the same methods RankHome already shows — two controls, one destination. Side effect that motivated it: the rankings-import entry ("Have rankings already?") lives ONLY on the chooser, so it was a tap deeper than the sheet and the operator couldn't find it.
- **Never-strand preserved** (#162/#165's "stuck in a ranking loop" trap): `RankHome` keeps its own back control — it is the one rank screen with no More-ways control — and iOS edge-swipe is untouched. `headerBackVisible: false` is **load-bearing, not belt-and-braces**: native stack draws the OS chevron on a PUSHED screen even with a null `headerLeft`.
- **The three-option RankMenu sheet is now unreachable in production** (that is the intent). It stays mounted for the `ux.rank_tab_destination: false` tab-press path, which makes flipping that flag the complete rollback — no deploy, no new flag added.
- **Gates:** new `check-rank-nav-exit.js` (9 assertions, **6 sabotages caught** — restoring headerLeft, dropping headerBackVisible, re-pointing More-ways at the sheet, stripping RankHome's back, breaking the flag-off branch, dropping MoreWaysButton); tsc clean; testid-lint OK; CI green. Maestro n/a per [D-056] — and the existing flows that tap `rank.more-ways` expecting the sheet now document stale behavior (kept, never run, flagged in the scope block).
- **Owed:** operator TestFlight pass on a build **newer than 112** — header rendering is device-only evidence. Scope block: `docs/plans/rank-nav-single-exit/scope.md`.

## 2026-08-16 (premium import: first real DN run, all 4 unmatched fixed — PR #136 live)

- **The operator ran the first real Dynasty Nerds in-app-browser import** (build 112, `ranks.source.dynasty_nerds` flipped ON same day): capture → confirm → apply worked end-to-end; `rankings_preset_detected {via: browser, set_confirmed: true}` + `rankings_import_applied {296/296}` verified in prod. Board was **backed up from prod before the test and restored byte-exact after** (md5-verified; `feedback-workspace/board-backup/`) — v1 has no in-app undo (WS-A2), the backup was the net.
- **All 4 unmatched rows root-caused via DN's public widget data (full arrays + sleeperIds are public; only display is premium-capped)** and fixed in PR #136 (`3aad130`): (1) `_NAME_ALIASES` bridges Kenneth→Kenny Gainwell + Chigoziem→Chig Okonkwo (Sleeper canonical forms); (2) **`sync_players` dropped rostered IR/suspended players** — Sleeper marks them `Inactive` while they hold a team; Ricky Pearsall + Chris Brazzell were invisible app-wide (G-008 class). Non-Active veterans are now dropped only when TEAMLESS. Post-deploy forced players-refresh verified both rows in prod.
- **Drive-by repair:** `3c0541c` (another session) flipped `suggestion.telemetry` in features.json without the three fixture mirrors — main's suite was red; mirrored in #136.
- 4 new tests, sabotage-proven; full suite green on the branch. Caveat: Brazzell (2026 rookie) is in `players` but ranked-pool membership depends on consensus-value coverage — verify via import **preview** (never apply, it overwrites the board).

## 2026-08-16 (Organic trade corpus BACKFILLED to prod + first POM patterns report)

- **555 executed Sleeper trades now in prod `sleeper_trades`** (529 new): every synced league swept plus up to 3 prior seasons via `previous_league_id` chains — 22 league-seasons, 5 franchises, 2022–2026. New operator scripts `scripts/backfill_sleeper_trades.py` + `scripts/backfill_suggestion_links.py` (both idempotent, `--dry-run`, flag-independent; runbook § Organic trade backfill).
- **Retro suggestion links written:** 109 pre-telemetry trades examined by exact serve-time trade_hash ([D-061](DECISIONS.md) — `retro_exact` match type, telemetry-era trades left to the live matcher). Result: **0 matched — honest baseline**, impressions only exist since 2026-07-27 and just 1 captured trade postdates that. `was_recommended` ratio now 0/121.
- **First patterns report** (`docs/business/analytics/2026-08-16-organic-trade-corpus.md`) — the POM calibration filters for the future league simulator: trades/league-season median 22 (10–86, strong per-league propensity); 31% of trades have 3+ assets on a side; 69% mix players+picks; Aug/Nov spikes with Dec collapse; dyad repetition above chance (369 distinct pairs vs 410 expected); participation Gini mean 0.374.
- Built on `feat/organic-backfill` (unmerged worktree; scripts + 20 tests + docs). Backend suite green (2943/1 + 20 new); pre-existing `release-300.json` fixture mismatch with `suggestion.telemetry: true` flagged separately.

## 2026-08-16 (App identity — Fleeced name + ram icon SHIPPED to TestFlight)

- **The app is `Fleeced` on the home screen, `Fleeced: Dynasty Trade Finder` in the store** — the implementation of [D-057](DECISIONS.md), recorded 2026-08-09 but never built. Exactly the two keys that decision names: `expo.name` (`mobile/app.json`) + `CFBundleDisplayName` (`Info.plist`) — app.json alone does nothing in this bare workflow.
- **App icon replaced** with the ram mark (pigskin football head, cyan horns, pink eyes): 1024x1024, sRGB, **no alpha**, square and unmasked per App Store rules. Picked from a 50-variant facial-expression round; masters in `docs/design/icon-explorations/2026-08-08/imgen-r5-rams/`.
- **Home-screen name is `Fleeced` alone, deliberately** — measured 36.5pt against the ~70pt iOS label budget (`GarageBand`, the longest Apple ships, is 57.9pt); `Fleeced Dynasty` at 76.8pt truncates. Confirmed on an iOS 18 simulator.
- **Shipped as EAS `1.13.4 (113)`** (`242a399`), production/STORE, auto-submitted; operator confirmed name + icon on device. **Gates not run** — see TEST_LEDGER. Reserving the store name in App Store Connect remains an operator step.

## 2026-08-16 (Matchmaking engine phase 1 — telemetry + trade-gen v2 SHIPPED dark; research corpus + mockup)

- **Operating thesis landed: FTF is matchmaking for trade partners** (Tinder/Hinge model — suggest a trade both managers will accept). 3 research rounds (11 memos, ~400 sources) in `docs/research/matchmaking/`; presentation mockup (9 Chalkline states, operator-approved pyramid: endorsed hero → featured → **uncapped** browse) in `mockups/trade-suggestion-redesign/`.
- **`suggestion.telemetry` (dark):** counterfactual logging on the deck spine (candidate sets, policy version, rank), deterministic 1-in-10 ghost holdout, `suggestion_trade_links` (`was_recommended` + ghost incrementality), admin ratio route. Zero mobile diff.
- **`trade_gen.v2` (dark):** staged divergence-driven pipeline — dual-board ε on consolidation-discounted packages, ±15% consensus band, joint-gain ranking, EB acceptance prior, MESO variants, two-sided rationale, exposure shaping as head-ordering; **no engine truncation** — full survivor set with endorsed/featured/browse tiers (operator decision).
- Both squash-merged from branches (tips `deb965c`, `c940a86`; fork `0b2dcee`); scope blocks in `docs/plans/matchmaking-engine/`. Operator waivers: Maestro (backend-only dark flags), telemetry analytics waiver, sim gate Tier 4. Merged-state suite result in TEST_LEDGER. Next: wire acceptance stats into the prior, mobile pyramid UI (needs real Maestro flows), lighting checklist per flag.
- **2026-08-16 (later): `suggestion.telemetry` LIT by operator** — collection + ghost holdout live; `trade_gen.v2` stays dark pending G6 merge, endorsed-ghost-exemption patch, and a logged v1 baseline (sequencing rationale in the session log + `docs/plans/matchmaking-engine/2026-08-16-g6-validation.md`).

## 2026-08-15 (Fit-congruence signal weighting — SHIPPED, PR #134)

- Swipe ingestion now weights Elo K by **surprise vs the user's window** ([D-060](DECISIONS.md)): fit-explained swipes (rebuilder passes the vet) ×0.4, fit-defying swipes (rebuilder likes the vet anyway) full K, no-window/sub-threshold exactly 1.0. Reuses the lanes machinery (`signed_lane_shift`); applied to in-memory signal AND persisted `k_factor` (DB replay agreement). Knob-only kill switch (`fit_k_explained_mult` = 1.0). Lands **before** Phase B's grading lane starts counting these signals toward "your board" — plan §B-2 now notes flags/declines get the same rule at build time; sends stay full-K. `main` @ `6f293f4`.

## 2026-08-15 (Guided Onboarding v2 Phase 0+1 — built dark behind `onboarding.guide_v2`)

- **The Analyst tour gains a machine-enforced eligibility layer + 8 new beats**, built from the 7-round dual-agent PRD (`docs/plans/guided-onboarding-v2/`) + the operator's O-1…O-7 decisions, by 6 Opus build agents across 2 waves, orchestrator-reviewed line-by-line. Ships **dark** (`onboarding.guide_v2: false` = v1 behavior graph); graduation = operator TestFlight checklist (`docs/plans/guided-onboarding-v2/testflight-checklist.md`) + first-cohort diagnostics.
- **Engine (FR-E2…E10):** GuideStep carries retireAfter/maxDisplayCount/invalidateOn/adoptionEvent/degrade contract, CI-linted (`check-guide-script.js`, 228 asserts); guide claims the interrupt slot; suppression + spotlight-degrade instrumented; v1-upgrader release cap; client-receipt rule (server-fired events never drive retirement — D-059).
- **Beats:** N1 calibration reframe · N2 two-form outlook re-aim · N4 pin-targets on the summary card · N6.1 first-like router ("they haven't seen it yet" — honest copy) · **N8 import question** (O-6: upload/DLF-DN entry vs Trios) · N9 Matches first-visit · N5 league divider · s3.2→RankHome re-route; s7.1 cut (fired pointing at an unmountable target in prod); full copy pass incl. the softened s2.1 claim + s5.1 plural fix.
- **Coupling note:** N8 routes to RankHome's import *entry* — becomes the premium chooser automatically when `feat/premium-import-v1` (D-057/D-058, unmerged) lands. D-numbering: this session used **D-059**, skipping the import branch's claimed 057/058.
- **Verified:** tsc 0 · all `check-*.js` green (now CI-wired) · testid-lint OK · backend 2838/1. **Owed:** operator TestFlight walk; Phase 2 (N6.2, N3, N5 spotlights, N7 trios rung, MFL/ESPN attempt events) waits on Phase-1 gates.
## 2026-08-15 (Premium Rankings Import v1 — built on `feat/premium-import-v1`, dark, unmerged)

- **Import your paid DLF / Dynasty Nerds rankings, or any CSV.** Built per [D-058] + `docs/plans/connected-rankings/build-v1-premium-import/scope.md` by two opus agents (backend `627dcd0`, mobile `52e4807`+`8660b8c`), merged clean on `feat/premium-import-v1` (zero file overlap). Placement per operator: imports are **the user's rankings** via the existing import pipeline; consensus untouched; schema-free.
- **Backend:** `POST /api/rankings/import-match` gains optional ordered `rows:[{name,team,pos}]` — hints only *disambiguate* (strictest-first ladder: both → pos → team; never reject). Paste path locked byte-identical by a golden fixture captured from the pre-change implementation. Flags `ranks.source.dynasty_nerds` / `ranks.source.dlf` default **false** everywhere. Events `rankings_preset_detected` / `rankings_preset_fallback` registered NON-INTENT; `rankings_import_applied` retroactively registered INTENT.
- **Mobile:** `ImportRankingsSheet` (DN/DLF rows flag-gated, Upload CSV, Paste), `PremiumRankingsBrowserScreen` (user logs into the site, taps the site's OWN Export CSV; passive `INJECTED_DOWNLOAD_CAPTURE` shim intercepts the user-generated file — never clicks/navigates/reads the page; scope §6.1 deviation taken), order-only preset parser with mandatory set+format confirmation (`contender_` files blocked by default; SFLEX/STD only via labeled nearest-format remap), 400-only fallback to the text path, staleness stamps. New dep `expo-document-picker` → **next build must be full EAS, not OTA**.
- **Gates:** merged-state backend suite **2855 passed / 1 skipped**; tsc clean; testid-lint OK; 36/36 mobile check suites (2 new: 27 structural + 42 parser cases); **13 sabotage runs all caught** (3 backend, 10 mobile). Maestro n/a per [D-056]. Runtime proof owed: operator's on-device DN export pass (checklist in the scope folder) before flipping `ranks.source.dynasty_nerds`. DLF stays preset-dark until a real fixture (addendum §3.4).

## 2026-08-15 (Open-access Phase A — SHIPPED: v2 onboarding is the default; likes_you floor; s5.1 fixed)

- **Operator ratified the open-access plan** (`docs/business/product/2026-08-14-open-access-onboarding.md`, O-1…O-9 + D-055/D-056) and the whole train merged same-day: [#131](https://github.com/mattmurf77/fantasy-trade-finder/pull/131) `likes_you_min_user_delta` floor (all 8 insulting first-deck cards gone, measured 1.48%→0.37% w/ control) → [#132](https://github.com/mattmurf77/fantasy-trade-finder/pull/132) S-43 fix: content-based late-bound regen diff + deck clear (**`s5.1` renders for the first time in repo history**; doubled-deck bug fixed) → [#129](https://github.com/mattmurf77/fantasy-trade-finder/pull/129) six flags true; v2 flow is the product, not an experiment overlay. `main` @ `0d8d7bb`.
- **Pre-flip gates ran for the first time** (`docs/plans/open-access-phase-a-gates.md`): deck-eval scoring half had never executed; S-43 proven FAIL then fixed. Deck-quality bars ratified as standing (D-055).
- **Maestro/simulator retired entirely** (D-056; CLAUDE.md + runbook updated). TestFlight is the only runtime proof path.
- **Owed:** operator TestFlight pass (5-step check) + runtime retirement of `onboarding_v2_rollout` (runbook procedure). P1-9 gained the counterparty-basis clause G10 (PRD §11) for Phase B.
- **Ledger note:** this session's first D-numbering used a stale checkout (D-047/D-048) and collided with device-auth's; renumbered to D-055/D-056 in the same docs commit (G-048).

## 2026-08-15 (#313 — 1QB QB values cap at "1 1st", SHIPPED + deploy-verified)

- **Value-side re-pricing, not a label cap** ([D-054](DECISIONS.md)). The operator reported 1QB QBs reading "2 1sts"; the label derives client-side from the served Elo, so the fix compresses `1qb_ppr` QB **seed values** post-blend / pre-Elo-map — order-preserving monotone piecewise-linear, applied **last** in `_apply_consensus_blend` so KTC rank-normalisation can't lift a QB back over. Allen/Maye/Lamar drop `firsts_2` → `first_1`; order preserved across all 95 QBs, zero new ties; non-QB, sub-knee-QB, and `sf_tep` byte-identical. Tier bands and every client mirror untouched — no ladder fork.
- **Knobs, not flags:** `qb_1qb_cap_elo=1785` / `qb_1qb_cap_knee_elo=1580` (`model_config`); either ≤0 is a deploy-free kill switch, proven byte-identical over the full 633-player × 2-format pool.
- **Built by an Opus subagent, reviewed + shipped by the orchestrator across a session boundary** (prior session hit its usage limit the moment the agent finished). Review re-ran the full suite after rebasing onto a main that had moved 7 commits (no footprint overlap): **2827 passed / 1 skipped**. 16 new tests, 6/6 sabotage matrix RED, incl. a shape pin a hard clamp fails.
- **Deploy verified by behaviour:** prod `/api/trade/values?scoring_format=1qb_ppr` serves the top three QBs at `first_1` (first post-merge poll). Squash [PR #128](https://github.com/mattmurf77/fantasy-trade-finder/pull/128) → `main` @ `34ebd84`. #313 marked fixed.
- **Known one-time cosmetic:** top ~5 1QB QBs read as large fallers in the 30-day movers strip until the window rolls.
- **Gates:** analytics + Maestro waived (no new surface/UI); **Tier 4 (CI only) recorded as an operator decision** in the scope block. See [TEST_LEDGER](TEST_LEDGER.md).

---

## 2026-08-15 (trade-card narrative claimed positions the received player doesn't play)

- **User-facing copy bug on the deck's primary surface, backend-only.** `build_narrative` took the position from the roster analysis (`match_context.user_needs` / `opponent_surplus`) and the player from the card (`_top_received_name` — highest dynasty value, **no position filter**) and printed them side by side. Nothing linked them, so a QB-thin manager receiving a tight end read "Adds Brock Bowers to address your thin QB group." Found by running the real engine against the operator's four Sleeper leagues: **23 of 32 cards**; both live paths call it, so it was on every card.
- **Fix:** every positional branch resolves player and position **together** through `_top_received(card, players, positions)` — the highest dynasty-value received player whose *own* position is in the candidate set — and prints that player's own position. Nothing received fills a need → fall through to the neutral fairness sentence instead of inventing a benefit. The `fit_premium` branch's `needs[0]` fallback (same hazard) is deleted. [D-053](DECISIONS.md).
- **Judgment call:** among qualifying players the highest-**value** one wins, not the highest-priority need — the sentence names the card's headline asset rather than a bench body that happens to fill the top gap. Both are true; this one matches what the card visibly is.
- **Tests:** `test_trade_narrative.py` 5 → 12, including the reported repro and an invariant sweep over every needs × received-position combination. **Negative control:** 5 of the 7 new tests fail against the pre-fix module. Full suite **2811 passed, 1 skipped** on the merged tree (main's 2804 + 7).
- **Not measured post-fix:** the four-real-league run needs live Sleeper data (local dev DB has no stored cards), so 23/32 is the pre-fix baseline only.
- **Gates (full — no express declared):** scope block [`docs/plans/narrative-position-accuracy/scope.md`](../docs/plans/narrative-position-accuracy/scope.md); Maestro delta waived (no mobile code, no `testID`, data-derived copy a seeded flow can't judge); `docs/architecture.md` module row updated; sim tier 4 (backend-only), pytest is the gate — [TEST_LEDGER](TEST_LEDGER.md).
- **SHIPPED AND LIVE:** operator said push live and deploy. Squash [PR #125](https://github.com/mattmurf77/fantasy-trade-finder/pull/125) → `main` @ `dc9a130`, all three CI checks green; Render deploy `live` on that commit at 2026-08-15T18:57:53Z, prod `/api/feature-flags` + `/api/tier-config` 200. **No probe fingerprints this change** — backend-only, no route/flag/client-asset surface — so the deploy record is the evidence, not a behavioural check. Branch ledgered ([recovery](../docs/recovery/2026-08-15-narrative-position-accuracy-sweep.md), tip `98bc17d`); worktree removal is the one step left.

---

## 2026-08-15 (compressed opponent boards produced empty decks — SHIPPED, PR #122, flags ON)

- **Field bug, backend-only.** Running the real engine against the operator's league FFV3 with prod boards: three of four **boarded** opponents (MangoPatti, Bcork, gdubs10) yielded **zero** cards at any per-opponent budget; the fourth (jonbonjourvi) yielded five. Their boards are floor-pinned — median Elo 1201 vs jonbonjourvi's 1379 — the shape of "started ranking and stopped".
- **Defect 1 (`trade_optimizer.py`):** the v3 pool prune ranked by the raw divergence `_vo - _uv`. `elo_to_value` is exponential, so a uniformly-lower board deflates studs by thousands and bench bodies by tens — every tradeable stud sorted **below** the user's junk and the top-12 pool filled with worthless assets. The key was not invariant to a board-wide offset, which carries no preference information. Fix: rescale the opponent's value space by the geometric-mean ratio over the assets in play before differencing. **Prune ordering only** — surplus/fairness/composite keep each side's raw space. Flag `trade.pool_calibration`.
- **Defect 2 (`trade_service.py`):** the boarded/unboarded branch was `if/else` with no fall-through, so a boarded member yielding zero divergence cards got no consensus fallback either and **vanished from the deck** — ranking a little made a leaguemate a worse partner than never ranking. Fix: fall back to `_generate_consensus_for_pair`, cards still labeled `basis:"consensus"`. Flag `trade.divergence_fallback`.
- **Measured read-only on prod boards** (pool 12): calibration alone takes gdubs10 0→5 divergence; both flags take MangoPatti and Bcork 0→5 consensus; jonbonjourvi unchanged. Deck total stays at the 30 cap, so boarded members **displace** unranked members' consensus cards — intended priority order, but visible. Raising `v3_pool_size` to 30 rescues all three with divergence cards but costs **26–102 s per pair** vs ~2 s — not a shippable mitigation. Residual: calibration can't undo a *nonlinear* compression ([Q-017](OPEN_QUESTIONS.md)).
- **Tests:** new `backend/tests/test_compressed_board.py` (8), every fix paired with a flag-off test pinning today's behaviour. Full suite **2771 passed, 1 skipped**. Scope block: [`docs/plans/compressed-board-pool/scope.md`](../docs/plans/compressed-board-pool/scope.md); [D-052](DECISIONS.md), [G-045](GOTCHAS.md), config-reference + glossary updated.
- **SHIPPED:** squash [PR #122](https://github.com/mattmurf77/fantasy-trade-finder/pull/122) → `main` @ `19d4174`, all three CI checks green (backend-tests on 3.12, mobile-typecheck, testid-lint). **Deploy verified live** — `GET /api/feature-flags` on prod returns both keys `true` (they were ABSENT pre-deploy, since both are new to `FLAG_KEYS`; that absence→true transition is the deploy probe).
- **POST-DEPLOY deck read against prod, real flag state:** every boarded member now produces cards — jonbonjourvi 5 divergence, gdubs10 4 divergence, MangoPatti 5 consensus, Bcork 5 consensus. The zero-card cliff is gone in production.
- **Correction found by that read:** the earlier claim that "the deck total stays at 30" was **wrong**. `global_target` is a stop-when-reached threshold checked *after* each opponent's whole batch is appended, not a truncation, so the deck overshoots by up to `max_per_opponent - 1` — the live read returned **34**, not 30. The three pre-deploy reads hit exactly 30 only because every batch was a full 5. Displacement itself is real and confirmed (four unranked members returned 0). Corrected in `features.json`, `config-reference.md`, the scope block and [D-052](DECISIONS.md).
- Both flags flipped ON by operator instruction (agents don't self-select a ship state); each stays its own deploy-free kill switch. **Card counts are verified; card quality is not, and all field data is FFV3 only.**
- Merged `origin/main` (PR #121, co-owned rosters) into the branch; IDs renumbered to [D-052](DECISIONS.md) / [G-045](GOTCHAS.md) after #121 claimed D-051 and G-042–G-044.

---

## 2026-08-15 (Sleeper co-owned rosters: a co-manager's league was dead — `co_owners` had never been read)

- **The bug, confirmed live against the operator's own account** (`mattmurf77`, `313560442465169408`): he **co-owns** roster 3 of league `1338231586314780672` ("Bush League"). Sleeper counts co-ownership in `/user/{id}/leagues`, so the league appeared in the picker — then every roster match in the product (`owner_id == user_id`, backend + mobile + web) found nothing. Two failures: no team at all, **and** — because the opponent filter was `owner_id != user_id` — his own roster was posted back as a *leaguemate* for the engine to trade against.
- **The decision is why this isn't a one-liner** ([ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md) / [D-051](DECISIONS.md)): `league_members` is a league-SHARED table, so widening only the client predicate gives roster 3 two rows (one from the co-owner's sync, one from any leaguemate's) — a 12-team league with 13 members, one roster duplicated, and session_init's DB-member merge handing the engine a phantom copy of the caller's own team. Instead: a co-owner is an **alias** of the roster's primary `owner_id`, and every session now carries an ACCOUNT identity (`user_id` — rankings, swipes, entitlements, analytics) and a LEAGUE identity (`_league_user_id()` — `league_members` keys, `is_you`, "my roster", mock-draft owners). Identical strings for a sole owner, so the common path is byte-identical.
- **Landed:** new `backend/sleeper_roster.py` (the one predicate, mirrored in `mobile/src/api/sleeper.ts` + `web/js/app.js`); `POST /api/session/init` gains optional additive `league_user_id`/`league_display_name`; call sites fixed in session_init member-keying, power-rankings `is_you` + rank-chip, free agents, mock-draft owner set, Send-in-Sleeper `_roster_id_for_owner`, draft-order co-owner aliasing, and six client roster lookups (untouchables picker, in-league calculator, trades target/swap pools, web leaguemate pool).
- **Known limitation, accepted:** `member_rankings` stays account-keyed (re-keying would attribute one person's board to another's Sleeper id in cross-league Trends), so a co-owned team's board reaches leaguemates only if the *primary* owner uses FTF. In [NEXT.md](NEXT.md).
- **SHIPPED:** operator said push live. Squash [PR #121](https://github.com/mattmurf77/fantasy-trade-finder/pull/121) → `main` @ `6158e65` (2026-08-15T17:20:03Z), all three CI checks green. **Deploy confirmed live** — prod `/js/app.js` serves the new `ownsRoster` predicate, `/api/tier-config` 200, and the rosters proxy returns roster 3's `co_owners` intact. **Web + backend are live now; the MOBILE half is not** — the client-side resolution ships in the app binary, so a co-owner on the current TestFlight build still sees the bug until the next EAS build. Branch ledgered + deleted ([recovery ledger](../docs/recovery/2026-08-15-co-owner-rosters-sweep.md), tip `e060d59`); worktree removal is the one step left.
- **Gates (FULL — API contract; operator signed off the field + all three waivers):** 33 new tests in `test_co_owner_rosters.py` against a new co-owned fixture; 7 of them fail if the predicate narrows back to `owner_id` alone. Suite **2796 passed / 1 skipped**; `tsc` clean; testid-lint OK; 24 structural suites green. Scope block: [`docs/plans/sleeper-co-owner-rosters/scope.md`](../docs/plans/sleeper-co-owner-rosters/scope.md). Sim tier 2 **RUN** on `FTF-iOS18` against `44c8bbf`: 2/4 flows pass; the changed path is proven green on-device (`session/init` 200, 26 on roster / 11 opponents, sole-owner branch), and both failures are assertion staleness with screenshots to prove it. Three pre-existing harness defects found and recorded — [G-042](GOTCHAS.md) (no `JAVA_HOME`, so **no local sim gate could run at all**), G-043, G-044. See [TEST_LEDGER.md](TEST_LEDGER.md).

---

## 2026-08-14 (deck-outcome impression-ownership validation — taste-poisoning hole closed)

- **Security/correctness fix, backend-only.** `_save_deck_outcome_safe` accepted any client-supplied `impression_id` and wrote `deck_outcomes` + (under `deck.taste_vectors`) the **impression owner's** taste vector — so a stale or foreign id let one session label and taste-poison another user's history. Found by the trade-relevance-engine dual-agent LLD review (docs landed same day, entry below); standalone subset of that initiative's P0 validation spec — when P0 builds, reconcile against this shipped fix rather than rebuilding (its PRD R6 specs the same check).
- **Fix:** helper now requires `acting_user_id` (route-resolved, never body) and writes only when the impression exists, is owned by the acting user, and was served ≤30 days ago. All six call sites covered (swipe, flag, /api/events side-channel, Sleeper/MFL/ESPN propose). Rejects are counted-and-dropped ([D-050](DECISIONS.md)) — response contracts byte-identical; counters (`no_user`/`unknown`/`foreign`/`stale`) on `GET /api/admin/analytics/health` as `deck_outcome_rejects`.
- **Tests:** helper-level (foreign/stale/unknown/no-user reject + legitimate-path regression, `test_deck_taste.py`) and route-level (`test_deck_signal_v2.py`); full backend suite green pre-merge AND re-run on the tree merged with PR #120 (see [TEST_LEDGER.md](TEST_LEDGER.md)). Scope block: [`docs/plans/deck-outcome-validation/scope.md`](../docs/plans/deck-outcome-validation/scope.md); api-reference updated.
- **Shipped:** operator-directed; [PR #119](https://github.com/mattmurf77/fantasy-trade-finder/pull/119), CI green (backend-tests, mobile-typecheck, testid-lint). Merge races with PR #120 (roster history — its D-049 stands, this decision renumbered D-050) and the trade-relevance docs push resolved en route. Sim-gate tier 4 (backend-only), no sim run required.

---


## 2026-08-14 (trade-relevance engine: X-algorithm research → audit → HLD/LLD signed off → 5 PRDs — SHIPPED to `main`, docs only)

- **Nine reference docs + seven planning artifacts, all dual-agent authored** (Fable subagents, adversarial loops per `.claude/skills/dual-agent-doc-review`). X open-sourced its For You algorithm 2026-08-13 (`xai-org/x-algorithm` @ `a389166`); four subagents documented it in [`../reference/x-algorithm/`](../reference/x-algorithm/) (real prod weights: report −234 vs favorite +0.5; 1024-event behavior sequence as identity; zero human labels). A fifth mapped FTF's own recommender → [`../docs/plans/trade-relevance-engine/`](../docs/plans/trade-relevance-engine/): `ftf-current-state.md` (supersedes tiktok-discovery/current-state.md), `audit-x-vs-ftf.md`, `enhancement-plan.md` (P0 close loops → P1 learned ranker → P2 market/FA/pre-join history → P3 archetypes + value decomposition → P4 presentation).
- **hld.md and lld.md SIGNED OFF** (4 adversarial rounds each); **prds/ P0–P4** dual-drafted + cross-reviewed (8 blockers fixed; parents amended in-place, ⟨PRD-AMENDED⟩ marks). Full objection/fix record + **operator decision queue** (⛔: Sleeper OQ-1 public reads, Postgres timing, D4/harm-check ratification, D6 bypass set, WAU/MDE, vblend audit storage) in `reconciliation-log.md`.
- **Reviews caught real defects pre-build:** P0-3 join semantics inverted vs `create_trade_match`; `surface='push'` rows would poison six impression readers; the vblend validator rejected its own default blend; D4's window graded a different artifact nightly; P2's "day-zero" promise arithmetically false at the call budget (→ 48h/7d SLO); the August archetype coverage gate fails on rookie-heavy rosters.
- **Live bug found in passing:** `_save_deck_outcome_safe` (`server.py:3657`) accepts foreign/stale impression ids → another user's taste vector poisoned. Operator spun up a fix session (task chip); the P0 PRD's R6 specs the same validation.
- **Cross-session supersession noted at ship time:** P0-1 (register the dropped client events) was independently shipped today by the G-031 session (PR #116) — the P0 PRD carries a dated note; remaining P0-1 work is verification-only.

---

## 2026-08-14 (Dynasty Year in Review P0: roster-history capture — branch `feat/roster-history`)

- **The ownership side of team value is finally being written down.** `player_value_history` has logged the market side daily since 2026-07-26; rosters were overwritten on every sync with zero rows of history. Two new append-only tables ([ADR-011](../docs/adr/adr-011-league-state-history-is-append-only.md)): `league_roster_history` (one row per team per ISO week, key `(league_id, team_key, scoring_format, period_key)`) and `league_board_history` (complete member boards — C5/C6 in one table, deliberately NOT a fork of `elo_history`). Built from the pm-growth plan + two 3-round adversarial reviews under operator rulings **YR-1…YR-8**; scope + premise checks in [`../docs/plans/dynasty-year-in-review/scope.md`](../docs/plans/dynasty-year-in-review/scope.md).
- **Three triggers, one precedence-aware writer** ([D-049]): on-sync (co-primary — session-init daemon LAST block for Sleeper, after each of the SEVEN `replace_espn_league_members` callers' transactions for platform leagues, never inside), a `daily-tick` weekday-gated daemon sweep fetching **server-side on all four platforms** (YR-8; ESPN-private uses the stored encrypted cookie, and an expired one degrades to a visible `espn_reconnect` bell row — new cross-client notification type — never a silent gap), and `POST /api/cron/roster-snapshot` as the manual lever. `weekly` outranks `sync` on upsert; the `source` column is the cron liveness detector.
- **The value contract:** `team_value` is `compute_power_rankings`' consensus-basis total through the same pick pricing as the Power Rankings screen — the December chart and that screen are contractually the same number. NULL-never-0; `valued_player_count`/`value_basis_date` keep K/DEF gaps legible; grey-don't-interpolate is the rendering rule.
- **Fixed en route:** `docs/architecture.md:230`'s false claim of a provisioned `value-snapshot-daily` cron (reverted same-day in `1e50d3e`; the hourly-tick guard is the operative writer). Two review-doc corrections: their **ISO boundary example was wrong** (2026-12-31 is `2026-W53`, not `2027-W01` — 2026 is a 53-week ISO year; the principle stands, pinned in tests), and the mock-draft branches blocking C3 turned out to be **merged** (PR #114), so the pick fold-in (`pick_ids` + contested-slots-skipped-AND-counted `pick_ids_excluded`) shipped in P0 rather than deferring to P1.
- **Gates (FULL — schema + data collection, not express-eligible):** 22 new tests in `test_roster_history.py`; suite 2725 passed / 1 skipped (rookie_scope excluded as known local-3.14-only); `tsc` clean; `check-notif-glyphs.js` 10 types 5/5. Docs: data-dictionary, api-reference, config-reference (+`FTF_ROSTER_SNAPSHOT_WEEKDAY`), runbook monitoring + retirement rule, cross-client-invariants, glossary, ADR-011. See [`TEST_LEDGER.md`](TEST_LEDGER.md).

---

## 2026-08-14 (sleeper FAAB: the encoding fix is right, the *shape* it encodes is unverified — Q-016)

- **Docs-only. No code change** — `79123a0` (2026-08-13) already fixed the `waiver_budget` GraphQL encoding, and correctly. This session independently reproduced the bug from the 2026-08-12 device-side-auth review and converged on the same design (`_graphql_object_literal`, bare keys, GraphQL-Name-validated). **The duplicate implementation was discarded, not pushed.**
- **Worth noting as a concurrency data point, not a mistake:** `79123a0` was **not** on `origin/main` at this session's start fetch (`7dfcd16`, 08-12 22:27) — it landed 08-13 18:20, mid-session, from a parallel session. Both sessions independently found the same latent bug and wrote near-identical fixes. The re-fetch-before-push is what caught it. Two sessions converging on one dormant bug is cheap; two sessions pushing rival implementations of it is not.
- **What survived is the part nobody had recorded.** The shipped fix encodes `[{sender, receiver, amount}]` — a shape that has **never been observed**. The 2026-07-02 capture only ever showed `waiver_budget: []`; the object shape is an *inference* from the runbook. Meanwhile the public `__schema` dump says the arg is `[String]`, and it is demonstrably right about `draft_picks`. If it is right about `waiver_budget` too, the shape is wrong at the **type** level — the bare-key fix makes the document parseable, not acceptable, and the first FAAB trade still fails.
- **Filed as [Q-016]** with the caveat mirrored into `backend/sleeper_write.py`'s module docstring (which asserted the inferred shape as fact) and `docs/integrations/sleeper.md`. **Treat FAAB-over-Sleeper as unimplemented, not merely untested** — non-blocking, since no caller populates it and `[]` is valid under every candidate answer. Needs one real FAAB capture to close.
- **Verified against the merged tree:** `pytest backend/tests/test_sleeper_write.py backend/tests/test_sleeper_write_route.py -q` → 37 passed. No behavior touched. See [TEST_LEDGER.md].

---

## 2026-08-14 (feedback wave: eleven items across League, Matches, Trades, backend — v1.13.4 build 111)

- **Four parallel plan→build groups, disjoint file ownership, one integration.** #307 (League match tiles land on Matches league-scoped, frozen param contract built by both sides independently) · #308 (the contrarian fold line stops lying — the gate counts in-format callers-included, the bar counts any-format callers-excluded, and the copy described neither; now dynamic + a cache key missing `activeFormat` fixed) · #309 (send copy no longer claims "Sleeper-only", false since 08-12) · #311 (MFL/ESPN/Fleaflicker trade summaries get starting lineups via a platform-aware standard template) · #312 (DNA add-button row obeys give-left/get-right — now a cross-client invariant) · #314-partial (filters below the banner; Players pill HELD) · #315 (banner details row) · #316 (deck-done copy drops the false "after waivers" mechanic) · #317 (deck-done tile taps re-present the featured window; #241/#298 invariants preserved by construction) · #318 (dismiss awaiting trades — `retracted_at` like-retraction, four suppression points incl. receiver-deck injection and match maturation, idempotent route, 5s undo, server-fired event) · #319 (Matches value disclosure + open-in-calc).
- **Gates (merged tree, orchestrator-run):** pytest **2737/1**; tsc clean; 19 `check-*` suites ~600 assertions all green; **48 named sabotages** RED-then-green across the groups. Deploy proven by content (dismiss route 405→401). Shipped `7057d86` (PR #117) + `7fb1e34` (v1.13.4), **build 111** submitted.
- **Process notes:** one build agent ended its turn waiting on a monitor (the documented stall pattern — resumed by nudge); one group voided its own plan's Maestro waiver when the fixture turned out to cover the state; two groups' plan defects (setLeague vs switchLeague, unreachable cross-tab navigate, dismiss placement vs footprint directive) were built around with documentation rather than improvised silently.
- **Sim gate: NOT run** — flows authored across all four groups (incl. the 500-injection dismiss rollback), never executed. #317's resume and #318's undo ship on static evidence; owed with the next sim session, plus the #309 QA rider (verify real send buttons on awaiting + calculator mounts for MFL/ESPN — the operator retracted their earlier confirmation as not having checked those surfaces specifically).
- **Held for the operator:** calculator group (D-306-1 graduate `aggregate_tier_labels`), #313 (D-313 value-side QB cap), the #314 Players pill.

---

## 2026-08-14 (G-031 backlog zeroed — 27 dropped client events registered, colliding quickset_completed emitter deleted)

- **Every remaining silently-dropped mobile event now lands in `user_events`.** The 2026-08-11 sweep's "29 remaining" (mostly teardown S3/S4 instrumentation — help surface, prompt arbiter, push primers, undo family, player context menu, settings mode changes, rating prompt — dark since ship): 27 names registered in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` with props mirroring the shipped emitters verbatim; 8 impression/dismissal/outcome-class names into `NON_INTENT_EVENTS` same-commit (DAU-seam rule); the other 19 are real user decisions and stay INTENT.
- **`quickset_completed`'s client emitter deleted, not registered** — server-authoritative name, namespaces disjoint by import-time assert. Accepted loss: its client-only `onboarding` prop (addendum records it; a future need means a NEW name, never an alias).
- **Seam:** no historical series exists for any of the 27 (every prior envelope destroyed on arrival); don't trend per-feature action counts across 2026-08-14. Addendum: [`docs/business/analytics/2026-08-13-dropped-emitter-backlog.md`](../docs/business/analytics/2026-08-13-dropped-emitter-backlog.md); cross-client-invariants backlog note now reads **0**.
- **Shipped:** PR [#116](https://github.com/mattmurf77/fantasy-trade-finder/pull/116) squash → `main` @ `4733f78`, CI green (backend-tests, mobile-typecheck, testid-lint); operator confirmed the bright-line taxonomy change. 243 backend tests + import asserts + `tsc` clean pre-merge. Deploy-then-probe: see [`TEST_LEDGER.md`](TEST_LEDGER.md). Sim gate n/a (zero user-visible behavior).

---

## 2026-08-13 (#295/#296/#305 — the mock draft works; manual mode; v1.13.3 build 110)

- **The mock draft has never let any user pick, on any platform, since it was enabled** — three reports (#295, #296, #305) of one defect. The create route read `sess["league"].members` — caller-excluded by app-wide convention, its third bite after FB #41 and #291 — as "everyone in the league", so every mock completed at create with zero user picks. Newton's "13 picks per round in a 14-team league" was the same missing member. **Five** membership sites fixed (two found only in this round's LLD, incl. `_mock_usernames`, which would have rendered the user's own recap rows "Unassigned"); a `build_settings` `UserNotInDraft` raise makes a born-broken row unwritable; `user_not_in_draft` joins the capability ladder as the fourth rung.
- **Manual mode (#305 priority): `mode: "cpu" | "manual"`** — "You pick for: Your team / Every team". Create-time-immutable, persisted in the existing `settings` JSON, one engine lever; no schema change, no new route, no new flag. `settings_echo` gains `mode` + `user_owner_id` (the only mode truth; "my team" keys on `picked_by_user_id`, never `by` — in manual mode every pick is `by: "user"`).
- **The sim→stop→pick→resume loop was proven live before ship:** 12 teams, user at slot 8 — create simmed picks 1–7 and stopped on the user's clock; availability was exactly pool − taken; the user's off-consensus pick landed `by: user` and the **same** `apply_user_pick` call resumed the CPU, which skipped the user's player and stopped at pick 20. The loop is engine-owned, not client choreography.
- **Five-phase Fable pipeline** (plan → HLD → LLD → PRD + mockups → build ×2), each document committed at phase exit. The LLD caught the HLD's contract being one field short; the mockup round caught `PickTicker` rendering a blank who-column across all of manual mode, and the fixture seeder having traded away the QA user's round-1 pick — **the shipped bug reproduced in miniature in the test world**. The shipped route fixture put the caller inside `members`, the coincidence that blinded #291; rewritten to production shape.
- **Analytics:** the five-event mock family registered in an isolated first commit; `mock_completed`/`mock_create_refused` NON_INTENT same-commit. Merge race with the notification-inbox family resolved additively. **Deploy-then-probe PASSED in prod** — all five events, every property echoed back, including `for_own_team` and the `user_not_in_draft` reason. The probe's loose first poll (`accepted:1, dropped:1` — old build, type dropped) was caught before it false-passed; the honest condition is `accepted ≥ 1 AND dropped == 0`.
- **Gates:** merged-tree pytest **2714 passed / 1 skipped**; tsc clean; ten `check-*` suites green; **34 named sabotages** RED-then-green, 0 false passes. Shipped `e71a654` (PR #114), **v1.13.3 build 110** (1.13.2 was taken by the notif-inbox ship mid-flight). **Sim gate: NOT run** — the PRD recommends Tier 1 and the flows (`d3` retargeted to `draft-pre`, new `d4` manual mode) are authored, lint-clean, never executed; owed with the next sim session. See [`TEST_LEDGER.md`](TEST_LEDGER.md).

---

## 2026-08-13 (device-side platform auth: LLD + Plan converged; all four artifacts done)

- **The dual-agent design programme is complete.** LLD (4 rounds, 24 blocking objections resolved) and Plan (3 rounds, same-round dual sign-off) join the PRD and HLD decisions. All on branch `design/device-auth-lld` — **push to `main` was denied by the permission classifier; the branch awaits the operator.** Docs: `docs/plans/device-side-platform-auth-{lld,plan}-2026-08-13.md`.
- **Six claims measured rather than asserted** (SQLite 3.50.4 / PG 18.3 / SA 2.0.49), two of which *refuted* the doc as drafted: `begin_nested()` on the main engine silently commits on SQLite (→ [G-040]), and unique-violation errors name the index on PG but only the column on SQLite (→ [G-041]). NULL-distinct unique index and the lock/state CHECK confirmed on both engines.
- **The Plan's spine:** S0 safe bundle now (keychain accessibility — the 365-day JWT is iCloud-backup eligible *today* — Sentry scrub, FAAB fix); Gates A–F; S6 = the point of no return; R7 = the kill criterion with a graduated read; expo-updates spike owns the Gate C decision.
- **Provenance:** PRD/HLD/LLD lenses ran on Opus; the Plan's on Fable (weekly Opus limit hit mid-programme).

## 2026-08-13 (notification inbox as a growth surface, phase 1 — SHIPPED to `main`)

- **Six push kinds that left no trace now write a bell row**, and the bell has instrumentation for the first time ever. Built from the pm-growth brief ([`../docs/business/product/2026-08-12-notification-inbox-growth-surface.md`](../docs/business/product/2026-08-12-notification-inbox-growth-surface.md)) under operator decisions GD-1…GD-8. Phase 1 is **inbox rows only, no push change** — inbox rows bypass prefs, buckets, quiet hours and OS permission, so this ships to **every** user while push stays operator-only.
- **Rows are written beside the push at the call site, never inside `_send_typed_push`** ([D-045]). The dispatcher's five gates are all statements about *interrupting*; inheriting them would have made `deck_replenished`'s inbox row reach zero users exactly as its push does. Idempotency cannot be borrowed either — `notification_events_log` is only written when a push actually leaves, so the 15-minute `match_expiring` cron would have re-written its row ~96×/day per match. It uses `notification_exists_with_meta`.
- **Three live dead-tap bugs fixed, two of them found by the new test rather than by reading.** `referral_joined` — the row that says the user's own invite worked — has rendered as an untappable grey bell since the referral loop shipped. `trade_accepted`/`trade_declined` were absent from mobile's routing because only the *push* kind `match_accepted` was listed: **two of the four original inbox types**. And web's `clickNotif` sent match rows to `switchView('trades')` while scrolling `match-card-<id>`, an element that lives inside `view-matches`.
- **`counter_offer` has no emitter anywhere in the backend** — a bucket mapping and two client kind sets, nothing more. The brief asked for a row "beside the existing push"; there is no such push. Glyph + routing only, so it renders correctly if the kind ever ships.
- **"Clear all" now means it.** New `notifications.dismissed_at` + `POST /api/notifications/dismiss-all`. Replaces mobile's zustand clear (rows re-hydrated on the next open) and web's per-browser localStorage set; web's set becomes read-only so pre-cutover clears survive. Rows are retained, never deleted.
- **Zero prompt rows, deliberately** ([D-046]). The invite ask lives in the **empty state**, gated at the shipped <50%-penetration rule — never a standing row, because a row true for every user every day is not news. Ordering stays recency-only; no schema for priority/expiry until a prompt row is actually approved.
- **Analytics registered one commit ahead of any emitter**: `notif_inbox_opened` + `notif_empty_state_shown` (NON_INTENT, added to `NON_INTENT_EVENTS` in the same commit — the bell is in the global TopBar, so intent-by-default would step-change DAU on ship day) and `notif_row_tapped` (INTENT). `surface` enum gains `notif_empty`. **Mobile only — web has no analytics SDK at all**, so these are not a product-wide bell open rate.
- **Gates:** 13 new backend tests; full suite green except 6 `test_rookie_scope` failures which are **local-only** (Python 3.14; CI on 3.12 is green on `main`, verified via `gh run list`). `tsc` clean, `testid-lint OK`, new `check-notif-glyphs.js` 5/5. Sim gate + Maestro waived under D-P1-08. **Shipped on the operator's directive**, which also resolved the `counter_offer` question (glyph + routing only, four write sites) and ratified both adjacent dead-tap fixes. See [`TEST_LEDGER.md`](TEST_LEDGER.md).

---

## 2026-08-12 (#300 position-scoped trade candidates — shipped LIT, v1.13.1 build 106)

- **Filter League rankings to one position and the list now tells you who to trade with.** A **median divider** on the shipped playoff-cutline pattern, labelled in **pick tiers** (never a number); the bottom 33% carry a **"Buyer"** label and the top 33% a **"Seller"** (`round(count × 0.33)` — 4/4/4 in a 12-team league). **The LINE, not the label, is the direction rule**, which is what keeps every team tappable and directional including the unlabelled middle. Tapping a team opens a **stacked**-roster drill-in — your players if they sit below the line, theirs if above — with **Offer** (pins give) / **Target** (pins receive) routing into the trade finder. Both flags shipped **ON**, not dark.
- **Rules A and B are gone — a deliberate reversal of #293/#294** ([D-044]). A position filter no longer auto-adds `PICKS`. This was load-bearing, not cosmetic: with rule A live, tapping WR ranked by **WR + capital** while the median measured WR alone, so no honest line could be drawn, and in a pick-carrying league the feature sat one undiscoverable tap from invisible. Rule B could not be narrowed — with rule A gone every `PICKS` is hand-chosen, so its trigger set and the case the ruling protects became the same states. Reversibility is now structural and strictly better than before. **The #293 complaint can return** (capital uncounted under a filter unless asked for); that is the intended trade.
- **Backend adds `medians: {QB|RB|WR|TE: {value, value_label}}`**, served **unflagged** — additive, one sort per position per request. The label is **de-gated from `aggregate_tier_labels`**: that experiment only controls whether per-team labels attach, while `_aggregate_pick_label` is a pure function, so the divider labels correctly for every user. That closed an item the frozen spec had listed as unresolved.
- **Two events, classified in the same commit as registration.** `league_candidate_pinned {verb, position, rank, side}` (INTENT) — `verb` and `side` are *not* redundant, because the drill-in stacks the **mirror** roster, so all four combinations occur and their agreement rate measures how often users override the line. `league_pos_candidates_viewed {position, divider}` (**NON-INTENT**) with `divider ∈ shown | no_median | no_split` — load-bearing precisely because the sim gate was waived: without exposure data a zero on the action event cannot distinguish "nobody found it" from "nobody wanted it".
- **Shipped with the simulator gate and Maestro execution waived by the operator.** The flow is authored and has never run; the 44pt hit-slop treatment, the divider and the rule-A removal have **never executed on a device or simulator**. Operator confirmed the build behaves in TestFlight — that is the only runtime evidence. Kill switch: either flag `false`.
- **Gates:** 2610 passed / 1 skipped; tsc clean; **271 structural assertions** across six suites, all sabotage-proven. **A fifth false-passing test** was caught this session — an assertion matched an identifier that also appeared in a dep array. Analytics verified in production by deploy-then-probe, every property echoed back. Caveat unchanged: no `check-*.js` suite runs in CI, so none of it gates. See [`TEST_LEDGER.md`](TEST_LEDGER.md).

---

## 2026-08-12 (P1 audit remediation: tier-board exposure closed, share loop wired, invite promoted, anchors unlockable)

- **A live privacy exposure was closed.** `/og/tiers/<pos>/<username>.png` and `/s/tiers/<pos>/<username>` shipped with **no guard at all** — no session, no flag, no in-app link — so any user's rankings board was fetchable by guessing a URL. Both now 404 behind `growth.tier_board_share`, **OFF as its resting state** per D-P1-12 (sharing of rankings is not a product surface). The operator believed this had already been disabled; what had been disabled was the public *profile* surface, a different thing.
- **The share loop is wired end-to-end.** Every shared trade image and message now carries a link back; the share-package landing is called from both the calculator and the liked-but-unmatched path. **Two false comments** claiming the route didn't exist were the reason nobody wired it — the audit found one, the build found the second on the path it called "the more common case". Trades containing picks fall back to the simple link rather than rendering "Unknown player".
- **Invite promoted with a penetration rule:** below 50% of leaguemates joined, invite leads the Matches empty state; at or above, "Find a trade" leads. Social proof comes from an aggregate already on `/api/league/summary` — no new endpoint, no flag dependency. Ships on **all** platforms: the claim that non-Sleeper invites are dead was traced and **did not hold** (nothing platform-conditional in the emit path), so gating would have suppressed a working outcome.
- **Anchor users can unlock.** `'anchor'` was a valid ranking method with no arm in the unlock branch, so those users fell to a swipe rule anchoring never satisfies. Five of eight rung labels contradicted the app's own vocabulary (the audit found two); labels are now **derived** from the canonical ladder with an AST test preventing re-divergence. Unlock backfill matched to P0-1's so no burst of "@user just unlocked" pushes.
- **`league_id` is no longer scrubbed as PII** (G-036). The 16+-digit rule, aimed at card numbers, matched every 18-digit Sleeper league id — five event types stored `"[scrubbed]"`. ESPN's 6-digit ids passed through, which is why spot-checks looked fine. Exemption is exact-key and skips that one rule only.
- **Reverted before shipping:** email capture. Built, then dropped in full — flag, policy, docs and living-memory. Sequencing was backwards: plaintext PII, indefinite retention, no removal path and no legal review, in exchange for 3–5 addresses that **no email-sending infrastructure exists to use**.
- **Gates:** 2663 passed / 1 skipped; `tsc` clean; simulator gate skipped under D-P1-08 (retired as policy, TestFlight is now primary QA). Analytics registration ships **unproven** until the corrected post-deploy probe runs — the probe as originally specced would have passed against a broken build. See [`TEST_LEDGER.md`](TEST_LEDGER.md).

---

## 2026-08-12 (Send in MFL + Send in ESPN live; ESPN write proven; Sleeper device-calls unblocked)

- **Both new send paths are LIVE in production.** `main` @ `cad99fb`; prod `/api/feature-flags` serves `trade.send_in_mfl: true` and `espn.send: true` (neither key existed before). TestFlight 1.13.0 builds 102–105, then 1.13.1 build 107. Every build status read from `eas-cli build:list --json`, never the exit code — **`eas build` exits 0 even when the remote build ERRORED** (a concurrent session lost two builds to that).
- **MFL send is live-verified end-to-end.** A real 2-for-2 proposal succeeded from the app: `trade_sent {platform:"mfl", give_count:2, receive_count:2, outcome:"proposed"}`. Because `mfl_write._parse_import_response` **refuses ambiguous success**, `outcome:"proposed"` is positive evidence the real import response parsed unambiguously — the response-shape `TODO(live-verify)` is answered by a round-trip, not an assumption. Also read `pendingTrades` live: field vocabulary confirmed, `FP_0002_2028_2` confirms the pick encoder in the wild, and **MFL stamps unix SECONDS while ESPN uses epoch MILLISECONDS** — the normalized model must convert.
- **ESPN trade-write proven and shipped** ([D-039], reversing the standing "never" NO-GO). Two probes, neither of which cost a real trade: the DP crosswalk's `espn_id` **is** the write-API `playerId` (4/4 live), and a bare POST with only `espn_s2`+`SWID` and static `x-fantasy-*` headers — **no CSRF token** — returned 409 `TRAN_INVALID_TRADE_TEAM_COUNT`, a validation error only reachable after auth. Accept/decline envelopes validated the same way (409 `TRAN_NOT_FOUND` with a fake id), retiring the "payloads were never captured — do not implement" caution the leading public ESPN write project recorded.
- **The ESPN status trap, settled 8/8 across two leagues.** A **declined** proposal keeps `status:"PENDING"` and `isPending:true` on its own record; an **accepted** one vanishes from the pending feed; `teamActions` can never show a decline. But `mPendingTransactions` itself is **self-pruning and authoritative** — it is `mTransactions2` (history) whose proposal status is frozen at creation. Net: the planned inbox read is *simpler* than designed, one call not two.
- **Sleeper device-calls unblocked.** A temporary in-app probe (shipped, run, and deleted the same day) returned **PASS 4/4** — Chrome-spoofed and honest iOS headers, Wi-Fi and cellular, all 200. Settles the one unknown that could have invalidated ADR-011's Sleeper half. **Design consequence: do NOT port the Chrome spoof to the device** — the server spoofs because a datacenter IP needs cover; a phone doesn't, FTF has Sleeper's permission, and a tolerated UA/fingerprint mismatch is a latent failure. `docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`.
- **Platform unlink shipped after a real incident.** The operator signed into ESPN with a friend's account and could not remove it — their FTF account held another person's encrypted cookies with **no user-facing removal path** (the row had to be deleted from prod). ESPN had no DELETE route; **MFL had the identical gap**, found by audit. Both now have one, plus Settings Disconnect rows and a domain-scoped cookie clear before sign-in (never `clearAll` — the native store is app-wide and would take Sleeper's session with it). Cross-user isolation proven by sabotage.
- **ESPN credential honesty fixed.** ESPN was the only platform storing **unproven** credentials — a consequence of cookie-scraping rather than performing a login (MFL's auth-link *is* a login; Sleeper calls `verify_token_live`). Now probes `fetch_fan_leagues` before storing, gated by `espn_credentials.verified_at`. The fan API was chosen because it has **no anonymous success mode**; an authenticated *league* read was rejected as a probe because a **public** league 200s with garbage cookies and proves nothing.
- **Sleeper terms resolved by the operator.** Research found Sleeper rewrote its Terms 2026-07-24 with language directly describing the already-live `trade.send_in_sleeper` feature. The operator holds explicit agreement — the §11.3 carve-out — so it is cleared. Sleeper's **full GraphQL schema is public**: `accept_trade` confirmed, pending-trade reads confirmed. Sleeper pending offers are **token-only** (>1,600 public trades sampled, all `complete`), which retires a question that blocked feature #11 for two months.
- **Planning:** four docs written — the cross-platform pending-trades inbox plan, ESPN/MFL/Sleeper lifecycle research, the Sleeper feasibility memo (the "#83 memo" the #11 plan was gated on), and ADR-011 + HLD for device-side auth (on `design/device-side-platform-auth`, unmerged).
- **Process:** operator directed express (sim gate waived, `FTF_SKIP_SIM_GATE=1`, CI not run). Near-misses avoided: the `.easignore` gitignore-semantics bug that killed two other builds was merged in **before** building; a stale-checkout `DECISIONS.md` commit would have **destroyed 13 decision records** from concurrent sessions (renumbered D-026→D-039 instead). `origin/main` moved **four times** mid-session.
## 2026-08-11 (P1-7 — anchor + manual unlock, derived rung labels) — **branch only, NOT merged**

- **Pick Anchors was a permanent dead end, and the ladder said so in code.** `get_rankings_progress` branches on `ranking_method`; `'anchor'` had **no arm** and fell to the trio rule, which needs 10 swipe interactions per position — and `apply_anchor` writes Elo overrides and *never a swipe*. Not "hard to unlock": structurally unreachable, for as long as the method has existed. Second-order damage rode along — the League ring read 0/4 forever and the push primer never armed for that cohort. Both audit options were rejected with proof and the proof lives in the ladder comment: option 1 is **inert** (the tiers arm reads `tiers_saved`, which the anchor lane never writes and is forbidden from writing), option 2 is **non-durable** (`_interactions` is rebuilt from persisted swipes at session build, so an in-memory bump dies on the next cold start) and would hand credit to the `via:'draft_room'` path P0-1 deliberately excludes. [D-041, G-038]
- **The manual lane's live defect is the OPPOSITE of what the round's decision assumed.** D-P1-10 folded `'manual'` into this item on the premise that P0 had *locked* it. It had not: the arm is `unlocked = True`, unconditionally, and P0-1's own comment says so. What P0 changed is *who reaches it* — one drag on Manual Ranks, or one Quick Rank step through the same handler, now pins the method and grants a permanent unlock. Both arms now read the same durable evidence, the persisted board. **`MANUAL_UNLOCK_MIN = 40` is a stated assumption awaiting operator confirmation** — and with today's client posting the whole visible list on every drag, it is a floor against "pinned with no board at all", not the strong A-17 gate, which needs a product decision and a payload change.
- **Analytics seam worth knowing before someone finds it in a chart:** `ranking_complete_first_time` begins firing for the anchor cohort, a step change in a shipped funnel series. The leaguemate push burst that would have accompanied it is suppressed the way P0-1 suppressed its own — a boot-time backfill pre-seeding `unlocked_formats`, not a special case in the `was_first` branch. [D-042]
- **Five of the eight anchor rung labels disagreed with the tier the answer lands in** — not the two the audit found. A user tapped "1 2nd" and read back "2nd" inside one interaction. Labels are now derived from `TIER_LABEL` and pinned by an AST test whose **own first cut false-passed** on the exact regression it exists to catch (a label re-typed inside a ternary); it now walks the whole initializer subtree. `no_value` displays **FA** while staying `null` in the type system, so the code never asserts an equivalence the backend does not make. [D-043, G-035]
- **The `anchors-done` fixture seeds `unlocked: false` on purpose** — a seeded `unlocked_formats` row clears the monotonic floor *before* the new branch is reached, so the obvious fixture would have gone green with the fix reverted. The seeder now refuses that shape outright. [G-037]
- Gates: **2504 passed / 1 skipped** against a 2467/1 baseline measured on this tree (+37, fully accounted for, no pre-existing failures); tsc clean; `testid-lint OK`; `check-anchor-labels.js` 20/20 with all five mutations proven to fail. Sim gate: none, per D-P1-08. **Not verified on device:** the new unlock hint and the five changed labels are visual and owed a TestFlight look. Evidence in [`TEST_LEDGER.md`](TEST_LEDGER.md).

## 2026-08-11 (feedback #297/#298/#299/#302 — single-pin recovery, League density + drill-in exit, batch analytics)

- **#298 — pinning one asset no longer strips the deck.** Two `singlePin ? null` gates removed the Find-a-Trade CTA and the **entire deck wrapper**, and with it swipe, the Pass/Like row and the VoiceOver actions — every path into `advance()`. They fired identically in the `trades_home_inline` **control** group, so the experiment was never the cause and reverting it would not have helped. The deck now takes the featured window's lead slot once it has cards (`singlePinDeckActive`), preserving #241's never-two-cards invariant rather than reverting it. Composes with #169: ungating the deck is what makes the card — and therefore the relocated Pass/Like — reachable when pinned. Second defect fixed in passing: picking a team from the strip's pill called `resetDeckForNewTargets()` but only auto-regenerated in `finderMode === 'team'`, so it **silently emptied the deck and regenerated nothing**. [D-034, D-035]
- **#297 — the missing lineup impact was never a regression.** `LineupImpactTable` has only ever been mounted in the calculator; nothing was removed. The real fault is that `_starter_impact` returns `None` whenever the league's slot template can't be resolved — **which includes the operator's own linked MFL and ESPN leagues** — and the client rendered that as `null` with **no copy at all**, indistinguishable from a feature that broke. Now an honest row naming the requirement. Deck-card mounts and MFL/ESPN slot derivation remain explicitly out of scope.
- **#299 — League roster tiles 60pt → 32pt (−47%)**, pitch 64 → 36, **728pt reclaimed** on a 26-man roster, 4 → 8 players above the fold; draft-capital rows 40 → 32 in the same pass. Delivered as an **opt-in `denseSingleLine` prop**, so the Tiers drag board and the FA list are byte-identical. The literal 30pt the operator asked for was declined: it needs a fork of the shared `Badge` primitive for two points. [D-036]
- **#302 — the drill-in gets an exit that works.** A back control existed, but it scrolled away above ~1,600pt of roster, sat top-right against a top-left convention, and no system back worked at all because the drill-in is component state, not a stack push. Moved to the stack header (`headerLeft` + title swap), **tab-root only** — the legacy root-stack push already owns its `headerLeft` and `setOptions` can't restore what it overwrites. **The Android `BackHandler` was built and withdrawn before ship** — no Android device or emulator was available and this release is iOS-only, so it would have shipped unverified down a path no tester can reach; Android still has no way back out of the drill-in, and that gap is now explicit rather than accidental. `'hardware_back'` stays a reserved analytics value with no emitter, pinned both ways so it cannot creep back unnoticed. [D-037]
- **Analytics — the operator rejected the waivers, so the batch is instrumented.** Two new client events (`lineup_impact_unavailable`, `league_team_closed`) and three widened props (`mode` on `find_trades_tapped` + `trade_card_viewed`; `source` on `find_trades_tapped` — a **bug fix**: the client had been sending it into an empty prop registry that popped it on every row since #257). The League drill-in **adopts the shipped `league_team_opened`** rather than minting a duplicate enter event; a `league_team_focused`/`unfocused` pair specced against an older `main` was discarded. Both new names landed in `NON_INTENT_EVENTS` in the same commit — as INTENT they would have step-changed DAU/WAU with no error and no log. [D-038]
- **Process — four false-passing tests were caught, in four independently authored suites**, every one by running assertions against a deliberately sabotaged tree: an ancestor-walking JSX gate check that passed on an unconditional badge ([G-035]); a first-element-only testID lookup; a platform assertion that survived a sabotage leaving the lookup line in place; and three raw-source scans matched by the comments naming the constructs they forbade. Also learned the hard way: **an instrumentation gap analysis is only valid against the `origin/main` it will land on** — `main` advanced 21 commits mid-batch and falsified two premises, forcing a rebase and an analytics redo.
- Gates: **2452 passed / 1 skipped**, tsc clean, `testid-lint OK`, 81 structural assertions across three suites (17 + 29 + 35). **Sim gate deferred by operator**, and the batch's largest unverified-code gap was closed by *removing* it rather than testing it — the Android `BackHandler` is withdrawn, with its absence pinned and sabotage-proven in both suites. **Deploy-then-probe still owed** per new event. Caveat worth repeating: none of the ten `check-*.js` suites run in CI, so none of these assertions gate anything yet. Evidence in [`TEST_LEDGER.md`](TEST_LEDGER.md).

## 2026-08-11 (P0 remediation batch — eight launch blockers from the 2026-08-09 mobile UX audit)

- **Eight of the audit's nine P0 blockers closed on one branch** (`p0-remediation-2026-08-10`, commits 1-13; P0-4 was **withdrawn** by the operator before the build). **Two behaviour changes users will notice:** account-only testers sitting on empty tabs land on the **league picker** at next launch (P0-5 — that is the fix working, and it is retroactive), and MFL/Fleaflicker users **lose a tappable Send button** (P0-6 — not purely additive; the control always 400s today, so no capability is lost).
- **P0-1 — Quick Set users unlock the Trade Finder.** `ranking_method` is now written at the **point of use** by the four save routes, first-use wins, with `'anchor'` the single upgradable value. A boot backfill tags the pre-fix cohort — including retroactively, and **without a notification burst** (`unlocked_formats` is pre-seeded in the same `UPDATE`; permanent consequence: that cohort never gets the unlock push). [D-026, G-034]
- **P0-2 — a failed trade search now says so** and offers a retry, instead of looking identical to never having searched. `job.error` is mapped to app copy, never echoed — it is `str(e)` of a Python exception or the literal `"timeout"`. Found en route: a first run plus four failed polls left a **skeleton card that never resolved**. [D-027, G-029]
- **P0-3 — the invite loop is repaired on mobile for every link already shared.** **The web client was already parsing `?league=` correctly** — only mobile was not, which is why "the invite loop converts zero" read as a two-sided failure and was really one-sided. New unflagged server surfaces: `GET /app/league/join/<id>` (302) and `GET /api/league/invite-meta` (Sleeper public API only, never the `leagues` table). The new URL format stays **dark behind `growth.invite_join_link`** pending AASA CDN propagation + on-device verification — parsers ship first, emitter last, because Apple caches AASA for ~24h. [D-028, G-033]
- **P0-5 — account-only sign-in reaches a league choice.** Routing keys off the `no_league` **sentinel**, never `user.account_only`; the Sleeper-link form moved verbatim into `LinkSleeperSheet`. [D-029, G-032]
- **P0-6 — ESPN/MFL/Fleaflicker matches get a stated reason and a working Copy trade.** The old gate was `league_id.isdigit()`, which is true for MFL and Fleaflicker too — the third instance of that bug class in this repo. [D-030, G-030]
- **P0-7 — launch-day instrumentation.** 15 client names + the server-fired `sleeper_send_succeeded` registered and wired. **`invite_shared` had been firing into a default-deny wall since the day it shipped**, which is why the invite loop was never actually measurable. `tab_selected` / `league_view` / `experiment_exposed` / `quickset_abandoned` landed as NON_INTENT in the same commit — as INTENT they would have step-changed DAU/WAU on ship day and broken every retention series at that seam. [D-031, G-031]
- **P0-8 — no more false tour sign-off**, gated on beat identity rather than a step count. The audit called 9 of 15 steps unreachable; the build's own sweep found **16 of 20**. **P0-9 shipped as test *preparation*, not the 32-tap redesign** — validation pass plus an operator runbook for the `trades_first_operator_test` experiment ([prd-p0-8-9.md §5](../docs/plans/audit-p0-remediation/prd-p0-8-9.md)). Also fixed: the first-like celebration was consumed before the bubble slot was checked and silently lost. [D-032, D-033]
- **Deliberately deferred, with the evaluations on the record** (see [`NEXT.md`](NEXT.md)): match accept/decline UX; the `is_linked_platform_league` guard on `/api/sleeper/propose`; `invite_shared` from the League-tab invite module; **29 client `track()` names still counted-and-dropped** (33 of 73 found by the sweep, 3 fixed here); `quickset_completed`'s client emitter, which cannot be registered because the name is server-authoritative.
- Gates: **2377 → 2448 passed / 1 skipped**, exit 0; tsc clean. Planning corpus (7 plans + 7 scope blocks + HLD + 7 LLDs + 7 PRDs) committed at [`../docs/plans/audit-p0-remediation/`](../docs/plans/audit-p0-remediation/); the audit itself at [`../docs/business/product/2026-08-09-mobile-ux-audit/`](../docs/business/product/2026-08-09-mobile-ux-audit/) — a dated artifact, not rewritten. Sim-gate evidence in [`TEST_LEDGER.md`](TEST_LEDGER.md).
## 2026-08-11 (#169 frame decisions built: outlook strip + in-card Pass/Like, shipped)

- **PR #107 squash-merged as `f27c0f5`, CI green.** League Summary gains the frame-E collapsed "your outlook" strip (band chip + "projected Nth of M", per-league/user persisted via `state/outlookStrip.ts`, full section one tap away) — dark behind `outlook.odds`, render byte-identical while dark. Pass/Like moved **inside** the top deck card beneath the player tiles (testIDs unchanged; "Accept this trade" VoiceOver strings renamed to Pass/Like — now a cross-client invariant, own section + [D-025]). No odds block on the card at any week — absence is the operator's design; week 6+ deferred, not designed.
- **`outlook_strip_toggled` specced + wired day one** (operator rejected the dark-flag analytics waiver): taxonomy allowlist + props entry + tracking-plan addendum; zero volume until lighting.
- **Process:** full doc set (plan/HLD/LLD/PRD/scope) adversarially reviewed — 21 findings applied, four were blockers (incl. a Maestro delta that would have passed identically before/after; replaced with positional `childOf` asserts, proven on-sim). Sabotage-proven checks: `check-card-disposition.js` (×2) + taxonomy test.
- **Sim gate: Tier-1 halted mid-run by operator** (usage cost) — deviation + partial evidence in scope.md §5 / TEST_LEDGER. Owed next sim session: green full suite, 4 re-captures, freshness sweep. En route: G-027 (npm ci strands Pods paths), G-028 (rookie-scope tests fail in data-carrying checkouts), disk-full incident (0 bytes → 25 Hermes launch crash-loops), stale-Maestro-driver-after-erase. Both #169 doc-drift finds fixed (#243 status → shipped; NEXT item on `outlook.odds`).

## 2026-08-10 (screen library shipped: 141 captures, 32 screens, capture harness)

- **The screen library is live** (`screens/` at repo root): every reachable mobile screen in every reachable state — 141 pngquant-compressed captures across 9 fixture profiles x 2 flag sets (incl. the **complete Analyst onboarding set**, 16 scenes, all six poses), regenerable in one command (`mobile/scripts/screen-capture.sh`), freshness-linted (`screen-freshness.sh`), mockup ground truth per [`../mockups/CLAUDE.md`](../mockups/CLAUDE.md) + [`../screens/CLAUDE.md`](../screens/CLAUDE.md). New: launch-argument screen entry (test builds only, build-time gate), draft/espn fixture profiles + 3 `/__test__` pins, sim-gate tier rows + scope-block capture-delta + warn-only pre-push freshness check. Unreachable states documented, not faked; the UX audit's nine capture requests all resolved (response doc in the audit folder). Found en route: spotlight-solver product bug, trios controls inert under Maestro (open), `isdigit()` ESPN guard bug (fix running in separate session).

## 2026-08-10 (feedback batch #289-#294 — MFL names, mock engine, pick value in every view)

- **#289 MFL Draft Room identity.** Franchise names and player names both rendered raw ids. Fixed at `_render_mfl` with four ordered tiers (all-zeros sentinel → our `players` row → DP crosswalk `by_mfl_id` → `Player <id>`). **The keying is the guard, not the query list:** 255 MFL ids in the committed crosswalk are also a *different* player's Sleeper id, so reading `{player_id: row}` by a raw id renders one pick's player on another. [D-022]
- **#290/#292 mock draft.** `cpu_pick` scored *list position* and never read `row["value"]`, so a 3-slot reach cost the same across a 5-Elo gap or a 300-Elo cliff. Now truncates at a locally-significant value gap composed via `min()` with the W2e round cap (can only tighten). No single gap multiple works — 27 configs swept, `sf_tep` collapses to a forced 1.01 where `1qb_ppr` looks fine — so tightness and wall-strength were split into two constants. `max()` need-aggregation was inert (TE's `(S,B)=(1,0)`); now denominator-weighted. Dismissal *paginated* through completed mocks instead of clearing them, which is why "can't do a second mock draft" looked unfixable from the client. [D-024]
- **#291** was already built — the pick path worked; the row just looked identical to the read-only Draft Room row until after you tapped it. Fixed the affordance, not the capability.
- **#293/#294 pick value** now counted in All/Starters/Bench and under position filters, behind `league.picks_always_counted` (**shipped ON**, graduated with its `LAUNCHED_FLAG_DEFAULTS` entry; the flag stays a kill switch). Reverses a rule documented in eight comment sites. Starters + Bench deliberately no longer partition All. [D-023]
- **The sim gate had never actually run.** Three flag-pin defects plus a bash-3.2 `$!` bug meant the stale-Flask assertion fired on a clear port every time and the EXIT trap orphaned Flask for the next run. All repaired, each proven by constructing the failure first. Five docs claiming the mock was OFF/unvalidated were corrected — it has been live since `6caca35`.
- **Known gaps:** G2's Maestro flow is unrunnable (the QA seeder writes nothing for `mock_drafts`); G1 has no flow by design; G3's R-5/R-0.4 and the kill-switch drill are manual. Sim gate bypassed by operator direction — see [`TEST_LEDGER.md`](TEST_LEDGER.md).
## 2026-08-10 (Season outlook UI built to the approved design — still dark)

- **`LeagueSummaryScreen` season-outlook v2 shipped behind the dark `outlook.odds` flag.** `OddsSection`/`OddsRow`/`OddStat` replaced by `SeasonOutlookSection`/`OutlookRow`/`OutlookUnsupportedRow`. **Row order + playoff cutline IS the projected standings; a 3-band chip (Likely ≥0.65 / Toss-up / Unlikely <0.35) IS the playoff odds.** `meta.beta` is the sole two-state switch (`showRecords = !meta.beta`) — weeks 0–5 order+bands only, week 6+ adds `4-2 · proj 9-5`. **Title odds deleted.** Flag-off byte-identical, query stays `enabled:false` so the endpoint is never called.
- **Three build decisions better than the spec, documented as decisions:** (1) rows sort by `odds.projected_seed`, NOT the payload's `playoff_pct` order — "nearly standings order" is exactly what would place a team below the cutline above one projected to finish ahead of it, breaking the section's whole premise; (2) band label always ships WITH the color (color alone fails a colour-blind read, and here the band IS the number) plus an accessibilityLabel; (3) the IDP caption derives "defensive"/"kicker" wording from `unpriced_slots[]` and singularises, so a kicker-only league never reads "defensive" and a slot-less payload stays generic instead of guessing.
- **Preconditions met:** non-Sleeper gate + honest explanatory row (**unknown platform resolves to SUPPORTED** — platform is only trustworthy while `draft.room` is on, so a guess must not delete the section); IDP coverage caption gated on `affects_strength && fraction < 1`; `docs/cross-client-invariants.md` gains a Playoff-outlook-bands section (keys, thresholds + boundary rule, hexes, the `title_pct` prohibition, the 5%-rounding rule, the `projected_seed` ordering rule) so web parity can't re-derive them.
- **The week-6 percentage is off by one constant:** `OUTLOOK_WEEK6_PERCENT_ENABLED = false`, ANDed with `!meta.beta` so no payload can produce a percentage in weeks 0–5. Operator risk option, not a recommendation.
- **ROUTE DEFECT FIXED:** `/api/league/outlook` resolved `platform` from the session's attached league (line 19465) while taking `league_id` from the query string (19439) — now `get_league_draft_context(league_id)`, the convention used by the pick-assignments seeder and draft-status stamp. 3 regression tests, each verified failing pre-fix: ESPN session + Sleeper league → 200 Sleeper (was spurious 501); Sleeper session + ESPN id → honest 501 (was 404/500).
- **Sibling defect found and deliberately NOT fixed** (documented in the audit for follow-up): `POST /api/league/pick-assignments/order` (~line 11075) has the identical bug class — prefers `g_league.platform` over the DB lookup keyed on the requested `league_id`. Latent because that route is exercised almost exclusively single-league.
- **Open operator decisions** (cheap now, awkward later): section **placement** (kept between the basis toggle and the chart; audit floated below-chart) and **basis** (still follows the Consensus/My-board toggle; audit recommended pinning to consensus, since odds off a personal board are a different claim than league-wide odds).
- Gates: **2301 passed / 1 skipped**, exit 0; tsc clean; testid-lint OK. Maestro delta waived with reason (flag dark ⇒ a flow asserting these ids fails every run; required coverage recorded for whoever lights it).

## 2026-08-10 (odds surface audit — one surface belongs, nearly everything rejected)

- **12 surfaces audited, exactly ONE "belongs now": `LeagueSummaryScreen`.** Design: one merged, seed-ordered "Season outlook" section where **the row order + cutline IS the projected standings** and a 3-band chip (Likely ≥0.65 / Toss-up / Unlikely <0.35) IS the playoff odds. `meta.beta` is the two-state switch — weeks 0–5 bands only (order, no W-L numbers); week 6+ adds current + projected records, with a 5%-rounded percentage available as an explicit OPERATOR RISK OPTION, not a recommendation. Answers the open "where do projected standings live" question by absorbing it rather than adding a surface.
- **Belongs later (2):** calculator/trade-summary "Season impact" disclosure (week 6+, on-demand, one CRN-paired sim per opened trade) and a deck-top band context line (cached league band, zero per-card cost). Plus web parity once `league-rankings.html` lights, and one band-transition clause in the existing `weekly_digest` (week 6+).
- **Rejected with reasons:** per-deck-card odds deltas (**measured ~3.8 s CPU per 10k-sim run × ~30 cards, re-paid on every DNA-edit regenerate, to mostly print "band unchanged"**); Matches inbox; featured-trade/asset-ideas; all eight peripheral screens (decoration, fails tenet #205); the extension (would contradict Sleeper's native odds on the same host page); **standalone odds pushes — CONSENT BREACH: the push primer promises transactional match events only** (kept verbatim so it survives re-proposal); title odds and the multi-year block everywhere; anything `pre_draft`.
- **ROUTE DEFECT found by the audit (fix before lighting):** `backend/server.py:19465` resolves `platform` from the session's attached league while `:19439` takes `league_id` from the query string — a multi-league user gets a spurious 501 (ESPN session → Sleeper league) or a misleading 404. **Latent today** (flag dark, client passes its own id, Sleeper data public); **wrong-answer-producing the day the flag lights.**
- **Ship-first:** League Summary outlook v2 (frames B + C1 + D) with three preconditions — the route fix, a non-Sleeper client gate + explanatory row (today it degrades to total silence), and cross-client-invariants entries for band keys/thresholds/colors.
- **Where the settled constraints forced the design (agent's own disclosure):** title-odds removal killed the champion-odds emotional headline #169 literally asked for; the bands verdict defers W-L numbers — the standings product's most legible element — to week 6; and bands-from-week-0 was accepted over "nothing until week 6", which is surfaced as the conservative operator alternative rather than argued away.
- Mockups: `mockups/outlook-odds/{league-summary-outlook-v2,outlook-card-v2}.html` (10 frames); July frames demoted to history in `index.html`. Audit: `docs/feedback/items/169-outlook-league-summary/odds-surface-audit.md`.

## 2026-08-10 (DP name map: "Ken Walker III" historical-board join)

- **Root cause was a DP rename, not a missing alias.** DynastyProcess's 2022-era boards say **"Ken Walker III"**; their current board says **"Kenneth Walker III"** (already mapped). So the gap never touched the live valuation path — it only broke the *dated historical* board joins that `backend/dp_values_history.py` feeds to the outlook backtests, silently dropping DP rank 61 from the 2022 season.
- **Fix:** one `DP_TO_SLEEPER_NAME` entry (`"ken walker iii" -> "kenneth walker"`), commented with the rename history and with an explicit note that the RB/WR "Kenneth Walker" collision is handled downstream by #127's position-strict `pos_map`, NOT by this name map — so nobody removes it later as a collision risk. Inert on the live path while DP emits the long form.
- **Verified:** 2022 board now has **zero unmatched Walkers**, total unmatched 15/553. Regression test asserts against the join report (the value map is keyed by Sleeper id, not name — a first attempt asserting a name key failed and was corrected).
- Gates: **2298 passed / 1 skipped**, exit 0. Closes the blemish disclosed in `dated-values-revalidation-2026-08-09.md` §2.

## 2026-08-10 (definitive post-fix calibration — both operator decisions now evidence-backed)

- **Combined re-measurement after the four-bug wave** (`calibration-combined-2026-08-10.md`): in-season playoff **Brier 0.0997, +60.1 % skill, CI [+47.6, +72.2]**, improving .2012 → .1065 → .0538 → .0372 across weeks 3/6/9/12. Preseason playoff **0.1968, +21.3 %, CI [+2.9, +39.1]**. Title odds **+4.2 %, CI spans zero, and 3 of 6 leagues lose to climatology** — unshippable at any week.
- **DECISION 1 — bands, not percentages. Verdict stands, now better supported.** Both pillars moved the wrong way after the fixes: over-confidence **survived** (preseason top bucket 0.947 predicted → 0.778 realized; one middle bucket materially worse) and the preseason skill floor slipped **+4.1 % → +2.9 %**. A 5 %-rounded playoff percentage from week 6 is defensible on pooled in-season calibration but is an operator risk call, not a validated result. Title odds: never a percentage.
- **DECISION 2 — gate at week 6; bands from week 0; never week 3.** Week 3 is dominated by both neighbours: preseason is statistically indistinguishable and nominally better (paired Δ −0.0043), and week 3 is the ONLY week the engine loses to a standings baseline (0.2012 vs 0.1875) and has title odds worse than a constant 1/12. Week 6 nearly halves Brier and already equals `_BETA_UNTIL_COMPLETED_WEEKS` — **`meta.beta` clearing IS the gate**, no new mechanism. BUG-1's preseason regression argues FOR this: it diagnoses a weak roster-value prior, not a bad fix.
- **BUG-3 bracket fix was a measurable NULL** — pooled title Brier 0.0733 → 0.0732, playoff unchanged (max |Δ| = 0.000000): the playoff field is settled before bracket structure matters. Correct to have fixed (it was wrong for 4 of 6 seasons); it just buys nothing. An **AST guard** now fails the suite if any future call site drops `playoff_seed_type`.
- **`meta.priced_slot_coverage` shipped** (`{fraction, total_slots, priced_slots, unpriced_slots[], affects_strength}`) — FFv3 reads 0.4667 with its 8 unpriced slots named; `affects_strength` false for `trailing_scores` so a payload never implies dependence on a board it didn't read. Prediction-neutral, test-pinned. This was the precondition for ever lighting odds on an IDP league.
- Re-confirmed unchanged: bye multiplier still NO-SHIP (Δ +0.0031, CI spans 0); random-re-pairing fallback ~7 % of playoff Brier.
- **Still unvalidated** (deliverable §9): title odds, IDP pricing, `playoff_seed_type: 1` semantics (doc-corroborated, never fixture-proven), per-week calibration stratification, and the 2-league sample.
- Gates: **2297 passed / 1 skipped**, exit 0; tsc clean. `outlook.odds` still dark — nothing user-visible shipped in the entire program.

## 2026-08-10 (outlook odds: four bugs fixed, engine measurably better — still dark)

- **BUG-1 median-match win booking FIXED (G-024 resolved).** Sleeper's `league_average_match` books TWO W/L decisions per week (H2H + vs league median); the sim booked one, yielding 22 projected wins in a 14-week season. Median opponent now computed inside the sim loop from that week's drawn scores (no extra randomness — non-median leagues keep an identical draw sequence). **In-season playoff Brier 0.1113 → 0.0997 (−10.5%); median leagues 0.1017 → 0.0666 (−34.5%); skill +55.5% → +60.1%.** Per-league signature exactly as predicted: both Lakeview seasons improved, all four FFv3 seasons bit-identical (max |Δ| = 0.000000, asserted). The tracking xfail now PASSES; suite has zero xfails.
- **Stated regressions, not tuned around:** title Brier +1.1%, week-3 playoff Brier 0.1972 → 0.2012, and preseason on median leagues 0.2298 → 0.2326. Mechanism: the median game removes luck ⇒ the engine is MORE confident ⇒ confidence costs Brier wherever the prior is weak, and the dynasty-value prior is weak. **This strengthens the case for gating** (contra the earlier reading that the gate bought nothing) — the live question is now week 3 vs week 6, not week 0 vs week 3.
- **BUG-2 was a NON-BUG.** Phase 1 already ingested real future pairings, so the "~5% Brier fallback cost" was never being paid. Real gains instead: `pre_draft` leagues no longer fire 14 upstream calls that can only return `[]`, and the random-pairing fallback is now observable (`SimResult.random_paired_weeks`).
- **BUG-3 playoff_seed_type modelled — and the engine had it backwards for 4 of 6 seasons.** Proven by fixture replay (3 divergent round-1 upsets, all matching the fixed-bracket prediction): **`0` = FIXED bracket** (FFv3, fixture-proven), **`1` = reseed** (Lakeview, doc-corroborated only — disclosed). The engine reseeded unconditionally. Corrects an earlier claim that our reseeding was an advantage over DynastyDaddy's static tree — both structures exist and the setting must be read. Unrecognized values log a warning and fall back to reseed, never silent.
- **BUG-5 (new, operator-hypothesised): IDP/K starting slots price at 0.** The DP board is QB/RB/WR/TE only, so **8 of FFv3's 15 starting slots are unpriced (53% of slots, 33–34% of realized points)**. Second defect found in the same function: slot names were matched against raw NFL positions, so `DL` never accepted DE/DT/NT and `IDP_FLEX` accepted nobody — **25–33 of 180 slots left empty per league-season**; fixed. **No license-clean dynasty IDP source exists** (DP, FantasyCalc, nflverse, KTC, Sleeper search_rank all verified live; DP's `db_fpecr` IDP page is a FantasyPros scrape = ToS landmine, rank-not-value, 100 players vs 84 needed). League-mean fallback measured worse; renormalising is a mathematical no-op. **Verdict: real defect, no available fix beats status quo** — shipped the correctness fix + a `lineup_pricing()` coverage instrument. G-026.
- **Correction to an earlier claim in this session:** unpriced slots do NOT bias the calibration — they contribute 0.0 to every team and cancel in the cross-team z-score. It is a *missing signal*, not a bias; Brier 0.1959/+21.6% stand arithmetically. What was wrong is the description: for 4 of 6 league-seasons the preseason number ranks teams on their **offensive core alone** (true starting-slot coverage 7/15, not the 100% previously recorded).
- Gates: **2284 passed / 1 skipped / 0 xfailed**, exit 0. `outlook.odds` still dark; nothing user-visible changed.
- **Two gaps before a trustworthy final number:** the backtest script doesn't pass `playoff_seed_type` (FFv3 still scored on the wrong bracket), and `lineup_pricing()` isn't wired into the payload (IDP leagues can't be labelled offence-only). Both queued.

## 2026-08-09 (ESPN numeric-id guard fix: Sleeper-only helpers now skip linked-platform leagues; branch, not merged)

- **Bug:** `server._fetch_sleeper_league_meta` and `trade_block_service.sync_league_trade_block` guarded "is this Sleeper?" with `isdigit()` alone, though their docstrings claimed they no-op for ESPN imports — ESPN native ids ARE numeric, so every `/api/session/init` on an ESPN league fired 1–3 Sleeper requests that 404 (prod latency/noise; false `vcr_misses` in the FTF_TEST_MODE harness). Same root cause as #149/#150.
- **Fix (branch `claude/suspicious-chaplygin-7dab59`, worktree modest-cerf-12ce88):** both guards now pair `isdigit()` with `database.is_linked_platform_league(league_id)` — the established convention from the rosters/league_users proxies (server.py ~13909/13940). Regression tests in `test_espn_link_route.py` pin both helpers to zero Sleeper calls for a linked ESPN league.
- **Follow-up once merged:** revert two workarounds in worktree `~/ftf-worktrees/screens-wt` (branch screen-library-2026-08-09) that exist only to route around this bug: `espn.json` profile pinning `sleeper.trade_block: false`, and `seed_ui_test_db.py`'s `{"__http_error__": 404}` ESPN cassette sentinel + its `_verify_no_cassette_gap` carve-out + `test_espn_league_emits_no_sleeper_cassettes`.
- Gates: full suite 2219 passed / 1 skipped / 1 xfailed after change. No schema/API/flag surface touched.

## 2026-08-09 (dated DP value boards — preseason source finally backtested; NOT merged, no flag change)

- **The "no dated dynasty-value board exists" blocker was FALSE (G-025).** DynastyProcess keeps the full git history of `values-players.csv` (weekly, back to ~2020-09); any revision is a plain GET at `raw.githubusercontent.com/.../<sha>/...`. New `backend/dp_values_history.py` + **24 committed dated boards** (2022–2025 × weeks 0/3/6/9/12/14, 484 KB) in `backend/tests/fixtures/dp-values-history/`. Offline by default — an uncaptured date raises rather than substituting a neighbour; live path is capture-only and `observe_call`-wrapped. Name→Sleeper join reuses the shipped crosswalk (3 tiers, position-strict): unmatched **0.2–1.8 %** of DP rows, **96.8–99.3 %** roster coverage, **100 %** starting-slot coverage on all six league-seasons.
- **Preseason `roster_value` backtested for the first time** (rewinds standings AND real week-1 rosters AND values): playoff Brier **0.1959** vs climatology 0.2500 = **+21.6 %**, 90 % CI **[+4.1, +38.3]** (excludes 0). Title **+3.1 %**, CI [−17.7, +24.9] — **no skill**. **Statistically indistinguishable from the week-3 `trailing_scores` model**, so the standing `completed_weeks >= 3` gate buys no accuracy at week 3 (its case is weeks 6+). But **over-confident at the extremes** (95 % → 75 % realized), beaten by climatology in **2 of 6** league-seasons, and much weaker on the median-match league (0.2298 vs 0.1789) — BUG-1's simulation half is live even though its ingestion half is inert at week 0. **Recommendation: playoff odds only, banded not precise, title odds withheld, BUG-1 first.** Operator decides; nothing flipped.
- **Hypothesis 1b WEAKENED.** Its Δ-roster-value sub-test flips −0.113 → **+0.076 with a CI spanning zero** under period-correct pricing; the confound strengthens (−0.35 → −0.41); (ii), (iii) and the buy:sell gradient (2.4:1 → 0.7:1 → 0.6:1) are bit-identical. Δ dynasty value is a structurally bad instrument for 1b — a rebuild trades present output for future value, moving it the *opposite* way. Sub-test retired, "do not spec a term" stands.
- Corrections issued inline to `calibration-report-2026-08-09.md` (incl. P9 FAIL-untestable → MARGINAL), `hypothesis-pick-capital-2026-08-09.md`, `phase-2-plan.md`; `docs/integrations/dynastyprocess.md` documents the history surface. Report: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.
- Gates: **2194 → 2217 passed / 1 skipped / 1 xfailed**, exit 0 (+23). No `backend/outlook/` change, no `config/features.json` change, no mobile diff; `outlook.odds` still dark. **Branch not merged or pushed.**

## 2026-08-09 (dated value boards: preseason source validated, 1b retired, design constraint found)

- **The "no dated historical value board exists" blocker was FALSE** — recorded in three prior docs, corrected today. DynastyProcess keeps full git history of `values-players.csv` back to 2020; `backend/dp_values_history.py` resolves nearest-commit-at-or-before a date, with **24 slim boards (2022–2025 × wks 0/3/6/9/12/14) committed as fixtures** so analysis runs offline (an uncaptured date raises, never silently substitutes). Roster coverage 96.8–99.3%, 100% of starting slots. Disclosed blemish: Ken Walker III fails the DP→Sleeper name bridge in the 2022 board (task chip spawned; shipped Elo-seed join untouched).
- **Preseason `RosterValueStrength` backtested for the first time** (the calibration report had called it untestable): playoff Brier **0.1959, +21.6% skill vs climatology, CI [+4.1, +38.3]** — real but marginal. **Over-confident at the extremes** (95%→75% realized, 4%→18%), loses to climatology in 2 of 6 league-seasons, and best-possible shrink recovers only 2.2% of Brier. Preseason **title** odds: no skill. **Design verdict: show BANDS ("likely / toss-up / unlikely"), never a bold percentage** — which is also what operator design tenet #205 argues for independently.
- **Two plan-changing findings.** (1) Preseason (0.1959) ≈ week-3 in-season (0.1972), statistically indistinguishable — so the recommended `completed_weeks >= 3` gate **buys no measured accuracy**; the honest case for a gate is weeks 6+. (2) The model is materially worse on median-match leagues (0.2298 vs 0.1789 H2H) — i.e. the operator's own Lakeview — so any UI must degrade honestly by league format, not present all leagues with equal confidence. Hindsight fear was also directionally wrong: TODAY's board scored worse (0.2073) than period-correct boards.
- **Hypothesis 1b re-tested and WEAKENED to a null.** With period-correct values the Δ-roster-value correlation flips from −0.11 (CI excluding 0) to **+0.076 (CI spanning 0)** and the confound strengthens (−0.35 → −0.41). The value-independent evidence is bit-identical (buy:sell 2.4:1 → 0.7:1 → 0.6:1). Refinement: high-capital teams *gained* dynasty value while losing more games — a competent rebuild trades present output for future value, so **Δ dynasty value is a structurally poor instrument for 1b; sub-test retired rather than re-run**. "Do not spec a term" stands, better supported. G-025 logged.
- **Design brief authored** (not yet dispatched): `docs/feedback/items/169-outlook-league-summary/odds-surface-audit-brief.md` — a design-orchestrator prompt to audit every surface for playoff odds AND **projected standings** (a distinct product that appears nowhere today), carrying the bands constraint, the gate question, the median-match degradation, and the July-planned surfaces as a baseline to challenge.
- Gates: 2217 passed / 1 skipped / 1 xfailed, exit 0. `outlook.odds` still dark; nothing user-visible changed.

## Archive index

- 2026-Q3 — 16 entries (2026-07-04 → 2026-07-27) — [archive/CHANGELOG-2026Q3.md](archive/CHANGELOG-2026Q3.md)
- 2026-Q2 — 4 entries (2026-05-21 → 2026-06-11) — [archive/CHANGELOG-2026Q2.md](archive/CHANGELOG-2026Q2.md)

Earlier project history (pre-changelog) lives at the bottom of [archive/CHANGELOG-2026Q2.md](archive/CHANGELOG-2026Q2.md). The "Outstanding / Known Gaps" list as it stood on 2026-08-08 was moved to the bottom of [archive/CHANGELOG-2026Q3.md](archive/CHANGELOG-2026Q3.md) — check [`NEXT.md`](NEXT.md) for the current state.

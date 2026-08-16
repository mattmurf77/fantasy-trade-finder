# Addendum: Premium Expert Rank Sets (DLF, Dynasty Nerds, Establish The Run)

> **Status: FINAL (v3, 2026-08-15) — adversary-reviewed, signed off.** Amends [`plan-2026-08-15.md`](plan-2026-08-15.md).
> Trigger: operator correction 2026-08-15 — the initiative's real target was never limited to
> *user-authored* rankings; it includes **premium expert rank sets the user pays for** (DLF,
> Dynasty Nerds, Establish The Run): "let them log into the site and we'll import the rankings
> on their behalf." The base plan scored candidates only on user-authored data and therefore
> under-weighted this category (it examined Dynasty Nerds solely through that lens).
> Research: [`research/2026-08-15-dlf.md`](research/2026-08-15-dlf.md) ·
> [`research/2026-08-15-dynasty-nerds.md`](research/2026-08-15-dynasty-nerds.md) ·
> [`research/2026-08-15-etr.md`](research/2026-08-15-etr.md) (public-information-only; no
> logins, no paywall bypass). Adversary review 2026-08-15: 6 blocking objections, all
> resolved in this version (see the reconciliation log's addendum section).
> **Operator decisions 2026-08-15:** Q11 and Q12 resolved — lane 1 AND lane 2a (assisted
> in-app-browser export, DLF + Dynasty Nerds, ETR excluded) approved; lane 2b stays parked.
> Recorded as **[D-058]** in `living-memory/DECISIONS.md`. Q13 remains open.

## 1. What the research found (2026-08-15)

| | DLF (dynastyleaguefootball.com) | Dynasty Nerds (DynastyGM) | Establish The Run |
|---|---|---|---|
| Dynasty rank sets | Top-250+ consensus (**Avg**) **+ per-analyst columns** (6 rankers observed, user-deselectable — so the table/CSV shape is dynamic), positional, rookie, superflex, IDP, devy; 1QB + SF; TE-prem unverified | Dynasty **and Contender** (win-now) value sets × 4 formats (PPR/SF/STD/SF-TEP); consensus + 3 analysts; rookie toggle; "updated weekly", per-analyst near-daily | 1QB + SF (TEP as column) + rookie, by Anthony Amico; "continuously updated" |
| Subscriber export | **Yes — built-in "Export CSV" + "Export PDF"** on the rankings table (client-side DOM→file; columns vary with ranker selection). A second Trade-Analyzer values CSV is reported but **unverified** (sourced from a search-index snippet of a 403'd FAQ page) | **Yes — Premium CSV export** on the rankings widget (sanctioned feature; `Rank, Player, Team, Position, Age, Exp, Value` + optional `Trend, PPG` + `Pos Rank`; **format/set live only in the filename** `dynasty_rankings_[contender_]<scoring>[_<pos>][_rookies].csv`) | **Unverified for dynasty** (embedded Ninja Tables page; CSV *is* ETR's pattern for best-ball products) |
| API | None. Server-rendered WordPress; Cloudflare 403s non-browser clients | None public. Private Expo SPA ↔ `gm3.dynastynerds.com` (OAuth/PKCE + JWT; endpoints mapped in research); domain 403s automation | None. WordPress; server-side paywall strips table for non-members |
| Login | WordPress + MemberPress (user/pass) | WordPress/Woo accounts (user/pass; own PKCE handshake, no social login) | WordPress + WooCommerce Memberships (user/pass) |
| ToS posture | Personal-use license; no download/redistribute/derivative-works; anti-circumvention; 1-account-per-person. No explicit robot clause, but the combination covers it. Research's own conclusion: "Legal review recommended before building" | **Personal, non-commercial** license; **"Account credentials may not be shared with or transferred to any other person"**; termination right for shared access. No explicit anti-scraping clause found | **Explicit** bans: automated scraping/robots, account sharing, redistribution, monetizing ETR content |
| Licensing precedent | None found | None found (Sleeper integration is inbound league sync) | **Yes, twice — but for DFS/best-ball projections, not dynasty rankings**: The Solver (entitlement-sync by matching email) and FantasyLabs ("ETR projections require separate subscription"). No known dynasty-rankings licensing precedent anywhere |
| Price | $12.99/mo · $59.99/yr | $69.99/yr · $6.99/mo | $54.99/season (Draft Kit Pro incl. dynasty) |

## 2. The verdict on "log in and we fetch on their behalf"

The literal mechanism fails the same three ways at all three sites, and the base plan's
guardrails already prohibit it:

1. **No APIs.** All three are WordPress sites whose rankings are server-rendered behind a
   membership login; two of the three 403 non-browser clients at the edge. "Fetch on their
   behalf" means credentialed headless-browser scraping — the thing §2 (Out) already bars.
2. **ToS.** Every site licenses content for *personal* use and bars redistribution; ETR
   explicitly bans automation and credential sharing; DN explicitly bars credential
   sharing/transfer and reserves termination — the account at risk is **the user's paid
   account**, not just FTF's standing.
3. **Custody.** Server-side login-and-fetch means FTF holding WordPress passwords for three
   more sites — exactly what the device-auth programme (G1/G2/D5) is dismantling. This
   addendum does not reopen that.

**But the goal survives the mechanism.** The user's actual want — "my paid rankings, in FTF,
kept fresh, without repeated manual CSV surgery" — is served by a three-lane ladder, in
ascending order of friction-removed and permission-required:

### Lane 1 — First-class assisted import of the sites' own exports (sanctioned surfaces only)
DLF and Dynasty Nerds both ship **subscriber-facing CSV export buttons**. FTF meets the file:
- **Per-source presets** in the base plan's assisted-export path (WS-E + D4): recognized
  header signatures auto-detect the **source**; set + format are confirmed per §3.2's rules
  (never silently inferred from headers). Provenance stamps `source = dlf | dynasty_nerds`
  per WS-A.
- In-app walkthrough per site ("Rankings → Export CSV → open in FTF"), file-picker +
  "Open in FTF" document-type intake, remembered mapping → repeat import is ~3 taps.
- **Freshness is user-initiated re-export — stated plainly.** No machinery in the base plan
  watches a CSV import for staleness (D6/WS-F operate only on `ranking_connections` rows).
  Lane 1 adds a **client-side staleness reminder** — the "Your subscriptions" card shows
  "imported N weeks ago" and nudges past a threshold — priced into the §3.2 delta. The
  re-import diff itself is real and free: it rides A4's merge preview.
- ETR joins this lane only if dynasty CSV export is confirmed (§3.4); otherwise ETR is
  lane-3-only.
- **Legal track (§3.4): per-site ToS memo + counsel read — run in parallel, non-blocking,
  per [D-058]** — the user clicking a sanctioned export button is personal use, but FTF
  publishing branded walkthroughs and marketing named presets is inducement-adjacent;
  walkthrough copy is nominative-use only, no logos. An adverse counsel read flags the
  affected surface dark (`ranks.source.*`) rather than having blocked the build.

This lane involves **no credentials, no automation against the sites, no new scraping** — the
user exercises the export feature their subscription already includes, for their own board.

### Lane 2a — Assisted in-app-browser export (APPROVED by operator 2026-08-15, [D-058])
The scoped middle ground, **approved as an operator decision** (rationale: rankings are
never exposed to other users; the user is using rankings they already pay for). Shape:
- The user opens DLF or Dynasty Nerds **in an in-app browser** and logs in there —
  **credentials never touch FTF** (no capture, no injection into the login form).
- The user taps **the site's own subscriber Export CSV button** in their own session.
  **No script injection in v1** — FTF does not click for the user; it provides a hint
  overlay ("tap Export CSV on this page") and **intercepts the file download**, piping it
  into the §3.2 preset pipeline (source detection, set+format confirmation, order-only
  import, provenance stamp).
- **User-present and on-demand only** — never background, never scheduled. Each refresh is
  the user re-doing the same in-browser export.
- **DLF + Dynasty Nerds only. ETR is excluded** (explicit automation ban; top lane-3
  target) unless a partnership lands.
- In-flow copy: this is the user's own subscription and account; use of the site's export
  is between the user and the site.
- **Counsel read (§3.4) proceeds in parallel, non-blocking** — per the operator's call. If
  it comes back adverse, the lane-2a surface is flag-gated (`ranks.source.*`) and can go
  dark same-day without touching lane 1.
Residual risks accepted with eyes open in [D-058]: a site could read even user-present use
as automation-adjacent and terminate the user's account (judged low for the user operating
the site's own feature in a real browser session); Apple App Review 5.2.2 exposure noted
for the public App Store release.

### Lane 2b — Fully automated device-side fetch (NOT approved; parked)
FTF driving page loads or endpoint calls itself — even on-device, even in the user's
session (DLF's export is client-side DOM serialization FTF *could* trigger; DN's SPA
exposes JSON the logged-in client receives). Still **automation of a paid site by a
commercial product** against personal-use licenses, an explicit ETR ban, and edge
bot-defense. Parked as **Q12b** — revisit only with counsel review, and never for ETR
absent a partnership.

### Lane 3 — Entitlement-sync partnership (the proven model; re-points WS-J)
ETR has done this twice — for DFS/best-ball projections: the user proves an active ETR
subscription (email match / account link), and the partner tool receives the data through a
**licensed feed** (The Solver auto-syncs ETR data for ETR subscribers; FantasyLabs preloads
ETR projections gated on the user's own ETR sub). **No known precedent covers dynasty
rankings specifically — at ETR or anywhere** — so the pitch extends a proven model to a new
content type rather than copying an existing deal. It converts base-plan WS-J from
speculative outreach into a concrete, precedent-backed pitch: *"your subscribers get your
rankings inside their trade tool; entitlement checked against your member list; no scraping,
no credential sharing; your subscription becomes more valuable."* Entitlement-sync is also
the **only lane that verifies the user actually subscribes** (lane 1 cannot police a shared
CSV). Outreach order: **ETR first** (precedent, and not a trade-tool competitor), DLF second
(Betsperts may want distribution), DN last (direct competitor; DynastyGM *is* a trade tool).

## 3. Concrete edits to the base plan

### 3.1 §0 premise table + provenance classes
- §0 gains a row-group: *premium expert rank sets* — DLF and DN move to **"lane-1 assisted
  import today (sanctioned CSV), lane-3 entitlement-sync if partnership lands"**; ETR added
  as **"lane-3 target #1; lane-1 pending CSV verification."**
- The §0 consequence "everything else is consensus" is corrected: expert rank sets are a
  third provenance class, **`provides: premium_expert`** — neither the user's own opinions
  nor free community consensus.
- **Registry home for lane-1 sources (labeling machinery):** DLF/DN/ETR register as WS-B
  registry entries with `auth_kind: none` and a new contract field **`intake ∈ {api, file}`**
  (`intake: file` = no `fetch()`, no `ranking_connections` row; the entry exists so the
  `provides`-driven label component, banned-phrase check, and picker grouping apply to them).
  WS-B's `provides` enum widens to `{consensus, user_authored, premium_expert}`. The WS-E
  banned-phrase check extends: "your rankings" is banned copy for premium sources exactly as
  for consensus. WS-I's `cross-client-invariants.md` update adds both enums (`provides`,
  `intake`). **WS-C guard:** `GET /api/rankings/sources` lists `intake: file` entries (the
  picker needs them), but `POST /api/rankings/connections` refuses them with a 400 (they
  have no `fetch()` to validate against and never get a `ranking_connections` row) — with a
  boundary test. **Each premium entry gets a `ranks.source.dlf|dynasty_nerds|etr` flag like
  any adapter**, so R16's "preset disabled pending fix" uses the same D8 disable path.
- **Picker/UI:** premium sources render under a third group, **"Your subscriptions"** —
  never "Your rankings" (they are the analysts' opinions), never "Community rankings."
  Tapping one opens the import-preset flow; its card shows "imported N weeks ago" — derived
  as max(`sourced_at`) for that source from WS-A provenance, no new store — (there is no
  connection row behind it) with the §2 lane-1 staleness nudge, plus **"requires your own
  <site> subscription"** copy (FTF cannot verify entitlement in lane 1 and does not claim to).

### 3.2 WS-E + D4 (assisted export) — the preset build
- **Header-signature detection identifies the *source only*, on anchor columns, never exact
  whole-header equality**: DN = `Rank,Player,Team,Position,Age,Exp,Value` present (columns
  `Trend`/`PPG` optional per research); DLF = anchor set TBD from a real fixture (`Rank` +
  `Player` + `Avg` expected — DLF's header is **dynamic**, varying with the user's ranker
  selection and DLF's analyst roster). Unknown signature falls back to the generic
  column-mapping UI — never guesses.
- **Set + format are confirmed, never header-inferred.** DN's CSV columns are identical
  across all four formats and across Dynasty vs Contender; the distinction lives only in the
  filename. Preset flow: parse the filename when intake preserves it; regardless, show an
  explicit one-tap confirmation of *value system + format* before apply. **`contender_`
  files are flagged as a win-now set and excluded from dynasty-board seeding by default**
  (operator-visible copy, not a silent remap). Format mapping to FTF's two boards, stated:
  DN `PPR → 1qb_ppr`, `SFLEXTEP → sf_tep` (exact); `SFLEX` and `STD` import only through an
  explicit nearest-format confirmation (`SFLEX → sf_tep`, `STD → 1qb_ppr`), named in the
  preview copy.
- **Analyst choice: consensus only in v1** (DLF `Avg`; DN consensus ranker). Per-analyst
  import is deferred; the preview names which set was read.
- **Values never enter FTF.** Presets read *order only*; the CSV `Value`/`Trend`/`PPG`
  columns are never persisted (see R14). This also falls naturally out of the base pipeline —
  `apply_reorder` permutes FTF's existing Elo multiset, so there is nowhere for a foreign
  value to land.
- **Matcher hint extension (BE-owned):** `match_rank_list` is name-only today
  (`rankings_import.py`) — presets pass optional team/position hints from their parsed
  columns to disambiguate same-name players; DN CSVs carry both. This function also serves
  the live paste path, so the change lands with a paste-path regression test and sits in
  BE's resourcing row, not MOB's.
- **Preset analytics, specced in the same D10 taxonomy PR:** `rankings_preset_detected`,
  `rankings_preset_fallback` (unknown signature → generic mapping), and
  `rankings_preset_confirm_changed` (user overrode the inferred set/format) — these are what
  make R16's trigger measurable.
- **Pick coverage, stated up front:** DN/DLF exports are player-only (~338 / ~250 rows, no
  pick rows). Expected D9 pick-gate finding: pick coverage = 0 — picks are untouched and the
  list applies on top of the existing board per A3's partial-list path. Recorded as a known
  finding, not discovered at gate time.
- **Intake:** three routes into the same preset pipeline — (i) file picker, (ii) **"Open in
  FTF" document-type registration** (infoPlist-only, vanilla-Expo-compatible; a true iOS
  share-sheet *target* requires a native share extension and is **out of scope**), and
  (iii) **lane-2a in-app-browser download interception** ([D-058]): an in-app browser
  screen (react-native-webview `onFileDownload` on iOS / download listener on Android,
  including `data:`/`blob:` URI capture — both sites build their CSVs client-side), a
  per-site hint overlay pointing at the site's own Export button, and the captured file
  handed to the preset flow. No script injection into the sites in v1.
- **Fixture gate:** each site's preset builds only after a **real subscriber-exported CSV
  fixture** for that site lands (§3.4). No fixture, no preset.
- Revised estimate: **+5–8 d on WS-E's range** (presets + confirmation flow + staleness
  nudge + matcher hints + walkthroughs at +3–5 d, plus the lane-2a in-app browser screen
  + download interception + hint overlays at +2–3 d), superseding the draft's +2–3 d.
- **QA posture per [D-056] (Maestro/simulator retired entirely, 2026-08-15):** the base
  plan's Maestro flow references (`connect-rankings.yaml`, `rank-resync-conflict.yaml`,
  WS-I sim tier) convert to structural `check-*.js` suites + code-walk proofs + an operator
  TestFlight checklist. This applies to the whole Connected Rankings initiative, not just
  this addendum.

### 3.3 WS-J — re-scoped to an active outreach track
Lane-3 pitch and the ETR→DLF→DN order; unchanged rule: each target ships licensed or closes
with a written "no" in `DECISIONS.md`.

### 3.4 WS-0 additions (gates before lane-1 build)
- **Per-site ToS memo (quoted clauses) + a counsel read on the lane-1/2a posture** — the
  research's own recommendation for DLF; **runs in parallel with the build, non-blocking,
  per [D-058]**; an adverse read darkens the affected `ranks.source.*` flag same-day.
  Walkthrough copy rule: nominative use only, no logos.
- **Acquire real subscriber CSV fixtures for all three sites.** **Dynasty Nerds: the
  operator holds an active subscription and has volunteered it (2026-08-15)** — the DN
  fixture and the first end-to-end lane-2a test both run on the operator's account. DLF and
  ETR: support inquiry or one-month sub. This simultaneously resolves ETR's dynasty-CSV
  question and pins the DLF/DN header shapes the presets depend on.
- **Demand probe:** "which premium sites do FTF users pay for?" — **if pursued, this is a
  taxonomy-specced analytics event and a bright-line non-express change** (new data
  collection; base-plan gates apply). The existing FeedbackFAB free-text is not a survey
  mechanism. May be answered more cheaply from the WS-0 `rankings_import_applied` corpus +
  direct tester conversation at current user counts; operator's call which.

### 3.5 §2 Out (non-goals) — new line
**No server-side login-and-scrape of DLF / Dynasty Nerds / ETR under any framing.**
Fully automated device-side fetch (lane 2b) is not in v1 and exists only as parked Q12b.
Lane 2a (assisted in-app-browser export, user-present) is IN per [D-058].

### 3.6 New open questions
- **Q11 (OP): RESOLVED 2026-08-15** — operator approved the ladder, with lane 2a included:
  lane 1 (CSV upload presets) **and** lane 2a (assisted in-app-browser export) both build
  after §3.4's fixture gate; ToS memos + counsel read run in parallel per [D-058]; lane 3
  outreach proceeds; lane 2b parked.
- **Q12 (OP + counsel): RESOLVED as [D-058]** — assisted in-app-browser export approved,
  scoped (user-present, on-demand, no injection, DLF + DN only, ETR excluded). **Q12b
  (parked):** fully automated device-side fetch — revisit only with a counsel read; never
  for ETR absent partnership.
- **Q13 (OP):** who sends lane-3 outreach, and is FTF willing to pay a per-subscriber
  licensing fee if a partner asks?

## 4. New risk rows

| # | Risk | Sev | Mitigation | Trigger |
|---|---|---|---|---|
| R14 | **Redistribution exposure** — premium content propagating beyond the paying user through FTF surfaces | Critical | Three honest layers: (1) **premium values never enter FTF** — presets import *order only* and never persist `Value`/`Trend`/`PPG`, and the ordinal pipeline (`apply_reorder`) has no slot for foreign values anyway; (2) the raw labeled set and per-source provenance are **never shown to any other user** — provenance is the importing user's private metadata; (3) **what leaguemates see is the user's own derived board**, republished exactly as any hand-built board is on every subsequent write — the base pipeline republishes `member_rankings` on all six write paths, so per-apply suppression is not claimed (it would be new machinery protecting nothing past the first swipe). Counsel read (§3.4) covers whether order-only derivation + no-labeled-display is sufficient | Any surface found showing another user a premium-labeled set or raw premium values → flag off same-day; counsel read says order-derivation is insufficient → lane 1 halts |
| R15 | **Partner-site C&D / user account termination** (a site reading lane 1/2a as scraping or inducement) | High | Lanes 1 and 2a touch no site systems beyond the user's own browser session exercising the site's own export ([D-058]: user-present, no injection, no scheduling); walkthrough copy is nominative-use, no logos; §3.4 counsel read runs in parallel with a same-day flag-dark path; lane 2b parked; outreach creates a named contact before any incident; in-flow copy names the user's own account as the one at stake | Platform contact → cited in support runbook, same-day response, user-present-export-only posture stated; a user reports an account action by a site → surface goes dark pending review |
| R16 | **Wrong-set/wrong-format import** — a Contender or STD file silently seeding a dynasty `sf_tep` board (headers identical; only the filename differs) — plus ordinary header drift | High | §3.2's confirmation step (set + format explicitly confirmed, `contender_` flagged, nearest-format remaps named in copy); anchor-column source detection with generic-mapping fallback (never guesses); per-source fixture tests; filename parse when available | Signature-mismatch or misconfirmation rate spike in analytics → preset review; any confirmed wrong-set apply → same class as R2, snapshot-ring restore + preset disabled pending fix |

## 5. What does NOT change

- The custody rules (G1/G2/D5), the ordinal-merge foundation (WS-A), the all-six-write-paths
  edit capture, refresh-as-proposal (D6) *for connector sources*, and paste's permanence —
  all untouched. Premium CSVs flow through the same matcher → merge → preview → apply
  pipeline as every other import; lane 1 adds presets, a confirmation step, labeling
  registry entries, and a staleness nudge — priced in §3.2 — and no new credential, fetch,
  or scheduling machinery.
- MFL (WS-H), FantasyCalc (WS-D), and every base-plan gate/estimate outside the §3.2 delta.

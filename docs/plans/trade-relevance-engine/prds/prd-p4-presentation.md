# PRD: P4 — Personal Hooks, Why-This & Trading Profile

> Phase P4 of the trade-relevance initiative ("Presentation: relevant AND
> enticing"). Parents SIGNED OFF and binding:
> [enhancement-plan.md](../enhancement-plan.md) §Phase 4, [hld.md](../hld.md)
> (Component F, D9, §5.2, R9), [lld.md](../lld.md) (B15, §2.3 `/why` route,
> E23). B15 is the least-specified build step in the LLD (no §4.x body) — this
> PRD is where its contract gets written down. UI follows Chalkline; all items
> take the four feature gates; **none of P4 is express-eligible** (API + flag
> surfaces). Dual-agent authored; log in
> [../reconciliation-log.md](../reconciliation-log.md).

## 1. Summary

The deck orders trades by a learned estimate of what this user will act on
(P0–P3), but the cards say nothing personal — today's `reasons[]` are
structural, indistinguishable from any calculator. P4 is the payoff phase:
**same trades, presented so the user sees why THEY should care** ("Adds the
rushing-QB profile you rate above market"), plus transparency and control over
what the app has inferred (why-sheet + editable profile — a trust feature no
competitor has, whose edits are free declared labels for the ranker). The
central risk (HLD R9) is the mirror of the value: **a wrong or condescending
hook is worse than no hook**. Every requirement is shaped by that asymmetry —
confidence-gated, template-only, never about the user's competence — and by
coverage honesty: at flag-flip most users will not clear the profile gates, so
absence must be invisible and nothing may advertise an experience most users
won't see.

## 2. Problem & Context

Relevance work is invisible and under-rewarded: users can't tell the deck was
built for them, so they skim, fast-pass, and distrust pushes. P3 produces the
raw material (`user_value_profiles`, `player_archetypes`,
`league_market_profiles`); P4 renders it — under a coverage reality check: a
hook requires the **intersection of three coverage curves** (profile
`confidence='ok'`, archetype row for the anchor asset, fresh market profile),
and the binding constraint at launch is the ≥25-ranked-players gate.

## 3. Goals & Non-Goals

**Goals**

- G1: Hooked cards convert better — like-rate up with **flag-rate on hooked
  cards NOT rising** (the plan's honesty check; the kill metric).
- G2: The why-sheet is the universal transparency surface — one tap on any
  deck card, explaining from the frozen serve-time record (never post-hoc),
  complete-looking even with zero profile (the launch-majority state).
- G3: Pushes earn their interruption — unsolicited push copy binds a personal
  hook or falls back per kind (inbox-only or nothing); total unsolicited
  volume drops while tap-through rises.
- G4 (stretch, conditionally descoped — §6): users see, correct, and delete
  their inferred profile; edits persist as `declared` labels outranking
  inference.

**Non-Goals (decisions, not omissions)**

- No generative/LLM copy in the serving path, ever (D9 — restated because it
  will be proposed).
- No coefficients, scores, or probabilities in push text; no urgency
  theatrics ("desperate to sell" never sends).
- No naming of opponent/non-user tendencies on any surface, including
  "insights" reframings ("this league pays up for RBs" passes; "Alex
  overpays" never).
- No copy-variant A/B in v1 — one template per `hook_id`; the experiment is
  hooks-on vs hooks-off. No localization (en-US strings; template ids are the
  future localization keys).
- **No web parity in v1** — web decks carry no `impression_id` (LLD §8.1), so
  the why route would uniformly 404 and read as broken; web ships after that
  fix lands, as its own gated item.
- No new screens beyond the sheet + profile section; no card-layout redesign
  beyond the hook line; no ranking/gate/push-cap changes — presentation only.

## 4. Success Metrics

- **Primary:** like-rate on hooked vs unhooked cards (attributable via
  `hook_id` frozen per impression), judged in a hooks-on/off experiment.
- **Kill metric (automated red line, human flip):** trailing-7d flag rate on
  hooked views > **1.25×** unhooked with **n ≥ 200** hooked views ⇒ red line
  on the operator report; default action `ui.personal_hooks` OFF (one flag,
  byte-identical). Below-n windows are inconclusive, never green.
  **Per-template:** any template ≥ 2× baseline flag rate at n ≥ 100 is
  retired (template id retired in code; ids never reused — reuse would alias
  flag attribution). **Like-for-like comparison:** the hooks-off arm stamps
  *counterfactual hook eligibility* (the dark-assembly report already
  computes it), so the red line compares hooked views against
  would-have-been-hooked views — high-confidence users' baseline flag rate
  differs, and the naive hooked-vs-all comparison would be confounded by the
  coverage gates. **All thresholds here (1.25×, 2×, n≥200, n≥100, the 20%
  flip bar, `hook_display_min_elo`=100) are operator-ratifiable
  `model_config` seeds, not hard-coded requirements** — ratified at the
  dark-run report, tunable without deploy, per the gates-stay-editorial
  guardrail.
- **Why-sheet:** open rate exists; flag rate on why-viewed cards ≤ baseline.
- **Push:** tap-through on hook-bound pushes up vs the trailing unhooked
  baseline while unsolicited volume drops (volume down alone proves nothing —
  P1's dark-window method applies).
- **Profile (if shipped):** declared-taste corrections from ≥10% of viewers;
  profile-delete rate tracked as a trust guardrail.

## 5. Requirements

**P4-1 — Personal hooks (`ui.personal_hooks`):**

- R1. One template-assembled sentence per card max, server-rendered into a
  **distinct payload field (`hook`), never prepended into `reasons[]`** —
  legacy/web/extension clients ignore it by construction (prepending would
  silently violate the no-web-parity non-goal, since web renders `reasons[]`
  from the same payload). Hook attachment is gated on client capability
  (min-app-version), so views from apps that can't render hooks never count
  as "hooked views" and dilute the kill metric toward green. Hooks lead,
  never replace, structural `reasons[]`.
- R2. **Confidence gating is absolute and per-card:** insufficient profile,
  missing archetype, or coefficient below `hook_display_min_elo` (seeded
  **100**, vs the ±300 clamp; resolver-read, operator-tunable) ⇒ no hook —
  the card renders **byte-identically to today**. No placeholders, no generic
  fallback hooks. T-30 extends to the display-threshold case.
- R3. Hook family v1 (priority order fixed in the scope block): fit-to-value
  ("Adds the rushing-QB profile you rate above market"), market timing
  ("Sells a cliff-adjacent RB while your league still pays up for RBs" —
  only for leagues clearing P2's price floor), need sharpening ("A
  pass-catching RB for your PPR flex hole").
- R4. Every served hook stamps `hook_id` (encoding template id) into
  `features_json`.
- R5. **Coverage bar before flip:** a dark-run report states % users with
  `confidence='ok'` and % of served cards that *would* carry a hook; hooked-
  card rate < **20%** ⇒ hooks do not flip — ship the why-sheet first and
  revisit as P3 coverage grows. Marketing/App Store copy may not lead with
  hooks until hooked-card rate ≥ 50% (or operator sign-off).

**P4-2 — Why-this sheet (`ui.why_this`):**

- R6. Entry on every deck card (Chalkline component spec); one tap; a bottom
  sheet, not a screen. Content from `GET /api/trades/why/<impression_id>`
  only: plain-language factor rows with relative contribution ("major/minor
  factor") — **never raw numbers or coefficients**.
- R7. **Payload whitelist, enumerated (closes the hygiene gap E23/T-27 don't
  cover).** The route's `features` subset MUST exclude all `opp_*` fields,
  partner divergence/valuation numbers, `vblend_id`/`model_record_id`, and
  any per-manager market attribution; may render `arch_match_*` and
  league-level `market_*`. **`score_components` (LLD §2.3 amendment,
  logged):** the signed-off payload served raw `propensity` (Thompson
  internals) inside `score_components` — a probing client could harvest it
  from its own impressions; the amended contract serves **relative-
  contribution labels computed server-side** ("major/minor factor" per
  component) and never the raw `propensity`/multiplier values. The whitelist
  is a code constant with a test asserting the **full payload** (both
  `features` and `score_components`) — not just the `features` subset.
- R8. Degrades honestly: no profile ⇒ `hooks: []` and components-only — the
  sheet is **designed to look complete in that state** (it IS the launch-
  majority state). Client treats the uniform 404 as "explanation unavailable,"
  no retry loop (route rate-limited).

**P4-3 — Hook-bound push copy (rides `push.eligibility_bar`; no new flag):**

- R9. Unsolicited-suggestion pushes only; bypass set per P1-3/D6. A push
  clearing eligibility must bind a hook clearing its display threshold; no
  hook ⇒ **per-kind fallback from a table in the scope block** (inbox-only
  with generic-structural copy, or nothing) — a silent drop of a
  previously-sent kind is a behavior change testers will report as a bug, so
  the table is a launch requirement (OQ-C). Fallback counts logged.
- R10. Push text = hook + league name, nothing else personal; push templates
  are a reviewed-set subset flagged push-safe; push impressions log
  `surface='push'` + `hook_id`.

**Copy governance (pre-flip gate, all surfaces):**

- R11. Templates ship as a reviewed constants module with stable ids; the
  scope block includes the rendered template list verbatim; **the operator
  approves it against the HLD §5.2 banned-copy rules before any flip** — R9's
  "copy spec gets a real review" is this requirement and is not satisfiable
  by code review alone.
- R12. **A copy change is a behavior change:** new/edited templates need a
  new id, the banned-copy checklist in the PR, and a lint that greps for
  banned patterns (second-person competence verbs — "you
  undervalue/overpay/misjudge"; counterparty name + tendency claims).

**P4-4 — Trading profile (stretch; `ui.trading_profile`):**

> **LLD amendments required (logged), because R14/R15 extend signed-off
> schema semantics:** (a) LLD §3.3/§4.12 gain the `declared` null-tombstone
> semantics and the writer invariant — **the nightly `value_decomposition`
> pass overwrites `coefficients` only, never `declared`** — with a sabotage
> test that lands **with B14 in P3**, not with B15 (an implementer following
> only the pre-amendment LLD could legally clobber tombstones nightly and
> nothing would catch it until P4-4); (b) the full-delete opt-out state gets
> a named home: the row is replaced by an **opt-out stub** (`coefficients`
> NULL, `confidence='insufficient'`, `declared={"opt_out": true}`) rather
> than deleted outright — one table, already covered by the §6.5 deletion
> cascade, `_EXPORT_TABLES`, and T-32, and the nightly pass skips stub rows.

- R13. A section in existing settings/profile navigation rendering the
  decomposition as plain-language statements; insufficient confidence ⇒
  honest empty state ("Not enough ranking history yet"), never fabricated
  leanings. Framing describes market/fit; fit diagnostics render as a
  plain-language confidence label, never numbers inviting self-judgment; the
  banned-copy lint applies.
- R14. **Edit semantics (decided here — the LLD doesn't):** corrections
  write `declared` per key, outranking inferred at read (D10). **Deleting a
  single value writes a `declared` tombstone (`key: null`) that survives
  nightly recomputes** (the pass overwrites `coefficients` only, never
  `declared`) — without the tombstone, deleted values silently regenerate
  and the user learns their edits are ignored, worse than no editability.
- R15. **Full delete = the opt-out stub** (see the amendment note above) —
  stops nightly regeneration until the user re-enables ("row DELETEd" alone
  regenerates tomorrow); the confirm dialog states consequences ("hooks and
  profile-based tips will stop"). Declared never expires in v1 — accepted and
  surfaced (edit dates shown; re-confirmation prompts are future work).
- R16. Corrections are labels: `declared` values feed D10 precedence but are
  **excluded from the decomposition's own training target** — the model
  never learns its own suggestions back.

## 6. Scope & Phasing

Ship P4-1/2/3. **Interim trust posture, surfaced for operator sign-off in
the scope block (not left implicit):** if P4-4 descopes while
`ui.personal_hooks` is live, users see personalized inferences with no
correction/deletion surface — HLD §5.2's "see, correct, and delete" is
deferred and the only remedies are account deletion or league unlink;
defensible (the parent marks P4-4 stretch) but it is the operator's call.
**P4-4 is conditionally descoped:** it carries a full gate
stack, the hardest copy risk, and novel edit semantics, while its dependency
(P3 coverage) is the same one throttling hooks — it ships only if hooks clear
the R5 coverage bar AND the kill metric stays green 14 days; otherwise it
moves to the next phase with its scope block already drafted. Rollout order
is load-bearing (LLD §6.1): `ui.why_this` → `ui.personal_hooks` →
`ui.trading_profile`, each preceded by its dark-run report, each
independently revertible to byte-identical behavior.

## 7. Dependencies & Risks

B13 (profiles) and B14 (archetypes + decomposition) green in the pass ledger
≥7 consecutive nights before any P4 flag flips; P1-3's push bar enforced
(P4-3 rides it); P3's panel sign-off (tags feed copy only after it). Gate
cost: three Maestro flows (`why-this-sheet.yaml`, `personal-hooks.yaml`,
`trading-profile.yaml`), testID lint, sim-gate tier per runbook, TEST_LEDGER
rows. Docs rows: `/why` → api-reference; terms → glossary; flags →
config-reference; banned-copy rules cross-referenced from the card spec in
`docs/design/components.md`.

| Risk | Answer |
|---|---|
| Hook coverage too thin → feature invisible or oversold | R5 20% flip bar + dark-run report + marketing gate |
| Wrong hook harms trust | R2 display threshold + R11 template review + kill metric with rollback rule |
| Why-sheet leaks counterparty context | R7 enumerated whitelist + serializer test |
| Edits silently ignored | R14 tombstones + R15 opt-out |
| Copy drift over time | R12 change-control + lint + id discipline |
| Gate-cost overrun | §6 conditional descope of P4-4 |

## 8. Rollout & Measurement

Dark-run coverage report → operator template approval (R11) → `ui.why_this`
ON (universal surface, works for everyone) → hooks dark-run → R5 bar check →
`ui.personal_hooks` ON in a hooks-on/off experiment → kill metric watched 14
days → P4-3 copy binding under the existing push bar → P4-4 decision.
Rollback at every step = one flag, byte-identical.

**Open questions:** OQ-A — is the 20% flip bar the right shape, or per-user
("≥N% of active users see ≥1 hook per deck")? Operator call at the dark-run
report. OQ-B — does the profile-less why-sheet need league-market-only copy,
or is components-only sufficient for trust? Decide from dark-run open rates.
OQ-C — the per-kind fallback table for P4-3 (which kinds fall to *nothing*).
OQ-D — kill-metric red line: report + human flip (default, per the
gates-stay-editorial guardrail) — confirm no automated flag-off.

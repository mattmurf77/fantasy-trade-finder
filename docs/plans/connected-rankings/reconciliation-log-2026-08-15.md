# Reconciliation Log — Connected Rankings plan (dual-agent review)

> Companion to [`plan-2026-08-15.md`](plan-2026-08-15.md). Four rounds, two lenses
> (Agent A = Author/Feasibility, Agent B = Adversary/Risk), both drafting from the same
> repo-research seed. Both signed off in Round 4 with **no blocking objections**.
> Sessions: dual-agent run started 2026-08-14 (session `2d5ce3c8`, halted at Round 4 by a
> usage limit), finalized 2026-08-15.

---

## Round 1 — independent drafts (from a shared repo-research seed)

A repo-research agent first established the ground truth both drafts were built on: the
credential custody model (one Fernet key, three per-user credential tables, MFL's
session-only key-less fallback vs ESPN's 503), the KTC scrape posture (spoofed Chrome UA,
daily TTL, `ktc_blend_weight` kill switch), and the board model (`users.tier_overrides`
JSON blob, no history, whole-blob read-modify-write; `member_rankings` as the published
snapshot).

- **Agent A (Author)** drafted "Connected Rankings — Replace Paste Import with
  Authenticated Source Connectors": accepted the initiative's goal but immediately
  surfaced the honest-framing finding — most candidate platforms do **not** hold
  user-authored rankings.
- **Agent B (Adversary)** drafted "Rankings Provenance & Assisted Connect": rejected the
  initiative's *mechanism* outright (premise audit: KTC has no personal rankings and its
  ToS bars both scraping and competitive use; FantasyPros' API never returns a user's own
  rankings; Dynasty Nerds is partnership-or-nothing), keeping only the goal.

**Convergence out of Round 1:** both agents independently reached the same reframing —
provenance + zero-credential connectors + assisted export + one sanctioned authenticated
connector (MFL) + refresh-as-proposal, with paste demoted but never removed. The v1
candidate merged the two drafts on that shared skeleton.

## Round 2 — cross-review of candidate v1

**Agent A's blocking objections (3):**
1. **The merge engine was specified against a data model the board doesn't have.** The
   board is an ordinal permutation (`apply_reorder` deals the sorted Elo multiset across
   every pool id), so a row-wise value-diff engine flags the whole board as changed and
   `user_edited` is underivable from the store. → Rewrote WS-A1/A3 in rank-index space;
   added WS-A0 (write-time edit capture) preceding any schema choice.
2. **WS-G's "MFL fail-open plaintext fallback is a bug" claim was factually wrong** — the
   key-less path is session-only, plaintext never reaches the DB, and "fixing" it would
   break MFL-only users' sole verification path. → Restated as a posture *question* for
   the ADR record, dropped from WS-H's blocking pre-reqs.
3. **Q4 presented a false binary** — `rank_sets`/`rank_set_entries` already exist as a
   versioned per-player rank store. → Added as explicit Q4 option (iii) with a required
   written accept/reject, decided jointly with the rankings-marketplace plan.

**Agent B's blocking objections (5):**
1. **The plan was unaware of the in-flight device-side platform-auth programme** and
   contradicted its settled decisions (G1/G2/D5). → Both docs became hard dependencies;
   WS-G re-scoped from "write a new ADR" to "conform to the merged device-auth decisions";
   MFL server-scheduled refresh banned (on-open/on-demand only).
2. **The MFL exception passed a storage gate while the real expansion was of *use*** —
   purpose, frequency, attendance. → D7 rewritten as a use gate: per-purpose consent
   naming data + cadence, grant record with independent revoke; repairing the
   documented-inaccurate MFL disclosure copy became an unconditional WS-H pre-req.
3. **The "unconditional encryption pre-req" mischaracterized the code** (same finding as
   A's #2, from the custody side) — the real defect is that a key-less deploy's session
   cookie is unreachable by cron. → WS-H connections cannot be created without an
   encrypted `mfl_credentials` row; `needs_reauth` became a first-class connection state.
4. **Merge engine vs the permutation invariant** (same finding as A's #1, from the
   tier-occupancy-bug side). → Same fix; assertions target order + tier-band occupancy.
5. **`user_edited` cannot be backfilled and the plan had no policy.** → Backfill policy
   set: every pre-migration override is `user_edited = true` (over-mark, never under-mark).

Non-blocking accepted: WS-B's pure half parallelized with WS-A (~2.5 d off the critical
path); DynastyProcess demoted to test-only reference adapter (it's already half of FTF's
default consensus); KTC blend-zeroing re-priced as a product-quality event, and the
two-unsanctioned-upstream cap now counts the existing KTC scrape; shared
`_apply_board_order(...)` helper so paste and connectors can't drift.

## Round 3 — cross-review of candidate v2

**Agent A's blocking objection (1):**
- **The Round-2 backfill fix collided with the Round-2 conflict UI**: an all-pinned
  (backfilled) board admits only the identity permutation, so connect could never change
  a legacy board, and per-row resolution meant ~500 decisions. → D2 gained bulk
  "replace all / keep all", a row-count threshold suppressing the per-row list, and a
  single all-or-nothing accept for fully-pinned boards backed by the WS-A2 snapshot ring.

**Agent B's blocking objections (3):**
1. **A0's route list omitted the app's primary ranking mechanism** — rank3 swipes (the
   3-player Elo matchup loop) and tiers/copy-from-format. A matchup-only board would have
   an empty pinned set and be silently overwritten on first re-seed, with the existing
   pinned-index tests passing vacuously. → All six write paths enumerated; a
   rank3-only-built fixture added; fail-safe default (uninstrumented path ⇒
   `user_edited = true`).
2. **A0's capture mechanism was unspecified** and the client-supplied variant would break
   already-shipped builds. → Mechanism (a) named explicitly: server-side pre/post-write
   diff, no client protocol change; absent-signal ⇒ `user_edited = true` if a client
   signal is ever added.
3. **The "MFL APIKEY default" contradicted `docs/integrations/mfl.md`** ("there is no
   separate MFL API key — the credential *is* the session cookie"); APIKEY is plausibly
   the same secret in a query string (worse custody). → APIKEY demoted from default
   transport to a Q7 discovery output; WS-H's transport is the existing encrypted cookie,
   `Cookie:` header only; the mfl.md-vs-device-auth-PRD contradiction became a required
   WS-G reconciliation deliverable ("docs/ wins; whichever loses gets edited"); the
   "read-only by construction" claim was struck (read-only is by contract + review).

Non-blocking accepted: Q4 option (iii)'s two concrete obstacles named (no provenance
columns; immutable-per-version model); copy specced for "signed in to MFL, rankings
connection unavailable" on key-less deployments; merge assertions avoid exact
Elo-multiset equality (the −0.001 tie-break drifts); timeline low end reconciled to ~28 d.

## Round 4 — final review of candidate v3

**Both agents: SIGN-OFF, no blocking objections.** Agent A spot-verified every
load-bearing repo claim added in v3 (all six write-path line numbers, `record_event`'s
missing `platform`, the permutation semantics, `rank_sets` shape, flag-key immutability,
the fail-open `espn.link` precedent) and confirmed them accurate.

Nine non-blocking suggestions, **all applied in the final v4**:

| # | From | Suggestion | Where applied |
|---|---|---|---|
| 1 | A | `_IMPORT_MAX_ROWS` hard-rejects with 400 `too_many_rows`, doesn't silently truncate — fix the wording | WS-C row cap |
| 2 | A | The snapshot ring's storage location (same `tier_overrides` blob vs sibling table) is a real WS-A LLD decision — an in-blob ring shares the failure mode of the blob it protects | WS-A2 |
| 3 | A | `apply_reorder` no-ops under 2 ids — add a tiny-match test so a near-empty connector result can't silently apply nothing | WS-A3 |
| 4 | B | Name the two persistence families (`save_tier_overrides` vs rank3's `save_ranking_swipes`) — the fail-safe backstop guards only the former | D1 |
| 5 | B | Q1 still said "MFL-via-APIKEY", contradicting §0/WS-G/WS-H/Q7 — restate on the actual custody story | Q1 |
| 6 | B | Cite the override-write call-site set, not `_refresh_taste_board_prior`'s stale docstring (it omits import-apply); fix the docstring in A0 | D1 |
| 7 | B | A flat `platform='server'` default would mis-stamp client-triggered events flowing through `record_event` — derive from `device_info`/`source`, fall back to `'server'` | D10 |
| 8 | B | Key the all-or-nothing escape hatch on board *state* (all ids pinned), not migration provenance — post-migration boards can become fully pinned too | D2, WS-A3 |
| 9 | B | Name MFL disconnect (`DELETE /api/mfl/auth-link`) beside reset in WS-C — a `ranking_connections` row must not outlive its credential | WS-C |

## Unresolved disagreements

**None left standing between the agents.** Everything contested was either fixed in the
document or explicitly converted into an operator decision (Q1–Q10) or a discovery probe
(Q7, WS-H's 3-day timebox). The two genuinely open *factual* questions the review could
not settle from the repo are carried as first-class plan items, not smoothed over:

1. **Does MFL's `myDraftList` exist and behave as researched?** Zero in-repo
   corroboration; the entire WS-H premise is externally sourced until the Q7 probe runs.
2. **Does MFL issue any credential distinct from `MFL_USER_ID`?** `docs/integrations/mfl.md`
   and the device-auth PRD disagree; WS-G must reconcile them and edit the loser.

---

# Addendum review — Premium Expert Rank Sets (2026-08-15)

> Covers [`premium-rank-sets-addendum-2026-08-15.md`](premium-rank-sets-addendum-2026-08-15.md),
> triggered by the operator's correction that the initiative targets **premium expert rank
> sets** (DLF, Dynasty Nerds, Establish The Run) the user pays for — "let them log into the
> site and we'll import the rankings on their behalf." Process: three parallel
> public-information-only research agents (reports in [`research/`](research/)), an
> orchestrator draft, then a two-round adversary review (single adversary lens — the
> addendum amends an already dual-agent-validated plan rather than standing alone).

## Round 1 — adversary review of the draft

**Blocking objections (6), all accepted and fixed in v2:**
1. **R14's "premium applies never republish `member_rankings`" was unimplementable** — the
   shared pipeline republishes on the apply AND on all six subsequent write paths, so
   per-apply suppression is new machinery protecting nothing past the first swipe. →
   Rewritten as three honest layers: order-only import (premium *values* never enter FTF —
   the ordinal pipeline has no slot for them), provenance private to the importing user,
   derived board republishes like any board; counsel read gates whether that posture
   suffices.
2. **"Kept fresh" rested on nonexistent machinery** — D6/WS-F refresh operates only on
   `ranking_connections` rows; a CSV import creates none. → Stated plainly as
   user-initiated re-export; a client-side staleness nudge on the "Your subscriptions"
   card specced and priced.
3. **The DLF header signature was unverified and structurally dynamic** (per-analyst
   columns are user-deselectable), and WS-0 only verified ETR. → Real subscriber CSV
   fixtures required for all three sites; each preset gated on its fixture; anchor-column
   matching, never exact-header equality.
4. **"Auto-detect format" was false and dangerous** — DN's CSV is column-identical across
   all four formats and Dynasty-vs-Contender; only the filename differs. A Contender file
   silently seeding a dynasty board is R2-class corruption. → Explicit set+format
   confirmation step, `contender_` flagged and excluded by default, DN→FTF format mapping
   enumerated, consensus-only analyst choice for v1.
5. **`provides: premium_expert` had no machinery home** — lane-1 sources aren't adapters
   and create no connections. → Registered as WS-B registry entries with new
   `intake ∈ {api, file}` field; `provides` enum widened; banned-phrase check extended;
   both enums added to the WS-I invariants update.
6. **Lane 1 shipped with no legal gate** despite DLF research recommending review. →
   Per-site ToS memos + counsel read on the lane-1 posture (nominative-use copy, no logos)
   as a precondition to building any preset.

Non-blocking accepted (8): WS-D→WS-E citation fix; ETR precedent caveated (DFS/best-ball
projections only — no dynasty-rankings licensing precedent exists anywhere); matcher
team/pos hint extension; pick-coverage-zero finding stated up front; "Open in FTF"
document-type registration (not a native share extension); the demand survey named a
bright-line taxonomy change; "requires your own subscription" copy (lane 3 is the only
lane that verifies entitlement); DLF Trade-Analyzer CSV marked unverified.

## Round 2 — re-review of v2

**Sign-off: yes, no blocking objections.** All six resolutions verified as substantive
against the codebase (republish call sites, `apply_reorder` semantics, `match_rank_list`
name-only matching, D10 taxonomy list). Six one-line tightenings, applied in the final v3:
`POST /api/rankings/connections` refuses `intake: file` sources (400 + boundary test) while
`GET /api/rankings/sources` lists them; the three preset analytics events named into the
D10 taxonomy PR; premium entries get `ranks.source.*` flags so the D8 disable path exists;
the matcher-hint extension assigned to BE with a paste-path regression test; this log
section appended; the staleness card's "imported N weeks ago" derived from WS-A
`sourced_at`, no new store.

## Unresolved disagreements

None. The reframing itself — three lanes instead of literal login-and-fetch — was endorsed
by the adversary in both rounds ("honest and well-argued against the operator's literal
ask"). What remains is operator decisions: **Q11** (approve the ladder), **Q12** (device-side
authorized fetch stays parked pending counsel), **Q13** (lane-3 outreach ownership and
willingness to pay licensing fees).

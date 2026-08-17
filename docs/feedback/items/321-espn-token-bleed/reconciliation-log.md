# Reconciliation log — #321 ESPN token bleed, review round 1

> Author's dispositions for every objection in
> [`review-round-1.md`](review-round-1.md) (Planner as critic). All new
> factual claims re-verified against git / `d3fe3ac` before incorporation;
> the verification additions are recorded in `prd.md` §8.

| ID | Objection (short) | Disposition |
|---|---|---|
| B1 | Migration cutoff factually wrong, unsafe direction | **Incorporated — and widened further** |
| B2 | "Newest linked league row" unspecified | **Incorporated** (critic's rule adopted) |
| B3 | Store-then-link path never re-checked | **Incorporated** (incl. the optional re-sync assertion) |
| N1 | Condition-2 client surface unspecified | **Incorporated** |
| N2 | R4 punishes public import over optional credential | **Incorporated** (critic's preferred semantics) |
| N3 | R9 must reuse `espn_reconnect` type | **Incorporated** |
| N4 | R5 silently dropped plan §F1's ownerless fallback | **Incorporated** (drop stated as deliberate) |
| N5 | TestFlight checklist refinements (4 points) | **Incorporated** (all four) |

## BLOCKING

### B1 — Incorporated, and widened beyond the critic's proposal

Critic's facts verified independently: `2fa1ff2` committed
2026-08-12T04:25:58Z and is the birth commit of
`espn_credentials.verified_at` (the earlier `git log -S` hit, `920a638`
2026-07-11, is `users.verified_at` — different table; confirmed by diffing
`2fa1ff2~1`); `7dfcd16` committed 2026-08-13T02:27:03Z — ~6.5h after the
PRD's `2026-08-12T20:00:00+00:00` cutoff. The original cutoff was wrong in
the unsafe direction, exactly as charged; prd.md §8 now records that this
was the one v1 claim taken on faith.

**Resolution goes further than the critic's `2026-08-13T06:00:00Z`.** The
critic's own findings justify it: post-`7dfcd16` stamps are still not
identity-trustworthy — the weak oracle vacuously accepts any account (B3
step 1), the public-league import path stamped with no verify at all (the
R4 gap, live until this fix), and the strong oracle passes any league
*member's* pair. Since identity binding does not exist until this release,
R10 now evicts **every pre-release stamp**: cutoff = a `RELEASE_CUTOFF`
literal finalized at ship (observed deploy-completion time from Render,
else push-time + 1h margin, erring later — the coordinator's "when in
doubt, evict more"). Render deploy timestamps for the 08-12 commits are not
recoverable from the repo, which also argues for a bound we control rather
than a reconstructed one. The UPDATE stays date-bounded because
`_migrate_db` runs on every boot — an unbounded null-all would sign users
out on every deploy. NULL-fails-`<` idempotency is now named explicitly in
R10 (critic's parenthetical), T9 respec'd with vintage fixtures, blast
radius corrected (whole small cohort, once; born-NULL pre-`2fa1ff2` rows
untouched), and scope.md §2 + waiver summary surface the widened blast
radius to the operator. Timestamps + final literal go in the ship-time
DECISIONS entry.

### B2 — Incorporated: any-conclusive-mismatch-across-all-bound-leagues

Adopted the critic's rule verbatim in substance (R1 rewritten): evaluate
**every** linked league row with a team binding, set semantics, no ordering
key — deliberately, since `load_espn_leagues_for_user`
(`backend/database.py:10606`, verified: no ORDER BY) pins no order and one
ESPN human owns one SWID. Verdict precedence specified: conclusive mismatch
> accept (all matches/inconclusives) > unavailable. At most one live read
per league, store time only. The mixed-verdict edge (pair matches league
1's bound team, mismatches league 2's) is specified as a *binding* error
surfaced as `wrong_account` with re-link recovery — intended, not a false
reject — and covered by new test T2b with sabotage `SAB-first-league-wins`.
No rebuttal: the "newest" wording had no defensible ordering key.

### B3 — Incorporated, including the optional re-sync assertion

The hole is real and verified: the stored-cookie fallback
(`server.py:20206-20216`) sets `pasted_cookie=False`, so v1's R3
("pasted/captured") skipped it, and a public-league fetch succeeds with any
cookies — the vacuous-accept-then-link sequence lands in exactly the #321
state. R3 now runs the comparison-only membership assertion at the
team-binding step **regardless of cookie provenance** whenever a pair
accompanies the import; on conclusive mismatch → 403 `wrong_account`,
nothing imported, and the stored row's stamp is nulled **when the
mismatching SWID is the stored credential's** (a mismatching pasted pair
that differs from the stored one proves nothing about the stored row —
author's refinement of the critic's "null the stamp"). The critic's
optional `espn_import` re-sync assertion is included as R3b (data verified
in hand at `server.py:20462-20470`; comparison-only) — it is the only
surface that catches wrong-identity rows *bound before this fix* that the
migration can't distinguish. New tests T8b (`SAB-pasted-only`) and T8c
(`SAB-skip-resync-check`).

## NON-BLOCKING

### N1 — Incorporated

Critic's client-surface trace verified (`client.ts:552-553`;
`EspnLinkSheet.tsx:277/287/314/324/528/549`): the link-path 403 surfaces via
the sheet's generic catch rendering the server `message` under
`espn-link.error`, and `espn_bad_credentials` does not enter the
`isEspnAuthRequired` branch. R7 now states this as the intended condition-2/3
surface (no sheet change required), and §7.2 gains a structural check
pinning the branch order so a refactor can't swallow it.

### N2 — Incorporated (critic's preferred branch)

R4 respec'd: identity mismatch still blocks (identity failures always
block), but otherwise a public-league import **succeeds independent of
credential health**; an unproven pair is simply not stored (existing
principle) and the 200 response says so via new additive
`credential_stored` (+ `credential_reason: "unverified" | "unavailable"`)
fields, fully specced in §5. The two-readings spot the critic flagged is
resolved: verify-`unavailable` never produces a 502 on the import path —
it lands in `credential_reason`. T7 respec'd to assert the 200 + not-stored
+ field values.

### N3 — Incorporated

Web allowlist verified (`web/js/app.js:4895` LEAGUE_TYPES includes
`espn_reconnect`; icon map at `:4716`). R9 now pins: **same
`espn_reconnect` type, new copy/`meta.reason` only** — a new type string
would be silently dropped on web. scope.md's cross-client-invariants row
reworded: still n/a, but now *because* R9 deliberately mints no new enum
value, with the multi-client constraint stated rather than overlooked.

### N4 — Incorporated

R5 now states the drop of plan §F1's ownerless fallback ("is any team's
owner") as **deliberate** — unconditional inconclusive-accept is simpler
and strictly zero-false-reject — with an explicit instruction that builders
must not restore the fallback from the plan. Also added to the ship-time
DECISIONS entry list in scope.md §4.

### N5 — Incorporated (all four points)

1. Step 1 made conditional on pre-update connection state — though under
   the B1 full-eviction respec the condition simplifies: *any* pre-update
   connected state must read not-connected at first launch (the critic's
   "his stamp postdates the corrected cutoff" concern dissolves, since no
   stamp survives).
2. New step 5: passive-harvest repro — sign in as B, back out without
   disconnecting, relaunch, reopen ESPN Connect → genuinely signed out,
   nothing auto-captured (the original #321 shape, not just the
   active-switch shape).
3. New step 7: second-FTF-account independence check (runtime proof of the
   account-keyed blast-radius verdict).
4. R8 typed-`reason` helper folded into §7.2's first structural check.

## Round-2 readiness

All three blockers are resolved with verified facts; all five non-blocking
points are incorporated (none rebutted — each was correct on the merits;
the only deviations are in the *stronger* direction: B1 widened to full
eviction, B3's optional re-sync made mandatory as R3b, plus the B3 nuance
that only the stored pair's mismatch nulls the stored stamp). The author
considers `prd.md` + `scope.md` ready for round-2 review.

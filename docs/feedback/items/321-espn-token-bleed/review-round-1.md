# Review round 1 — #321 ESPN token bleed (Planner as critic)

> Critic review of `prd.md` + `scope.md` (working tree, 2026-08-16) against
> the plan, the code at `d3fe3ac`, and fresh evidence gathered for this
> review. Line-drift to `0b2dcee` is recorded in prd.md §8 and is not raised
> here. Verdict: the docs are strong — faithful to the plan, honestly cited,
> tests are non-vacuous by construction — but three findings block, one of
> them on new factual evidence.

## BLOCKING

### B1 — The migration cutoff is factually wrong, in the unsafe direction
**Cites:** prd.md §4 R10, §7.1 T9; scope.md §2.

The PRD asserts the cutoff `2026-08-12T20:00:00+00:00` is "deploy time of
`7dfcd16`". It is not. Verified this round against git:

- `2fa1ff2` (verify-before-store, **introduces `verified_at`** — first
  commit touching `backend/database.py` with that string) — committed
  **2026-08-12T00:25:58-04:00 = 2026-08-12T04:25:58Z**.
- `7dfcd16` (the real-oracle fix) — committed **2026-08-12T22:27:03-04:00 =
  2026-08-13T02:27:03Z**, i.e. **~6.5 hours AFTER the PRD's cutoff**.

Consequences:

1. Stamps minted between `2026-08-12T20:00:00Z` and `7dfcd16`'s deploy
   (~`2026-08-13T02:27Z` + Render deploy lag) were produced by the **broken
   unbound-fan-leagues verify** — exactly the dishonest stamps R10 exists to
   evict — and would **survive the migration as trusted**. The migration
   silently under-evicts its own target window.
2. The blast-radius framing ("every pre-08-12 ESPN-connected user gets one
   re-sign-in ask") is also off: rows stored **before** `2fa1ff2`
   (04:25:58Z) never had `verified_at` at all — the column and the stamp
   were born in that commit — so they are already NULL and already read
   `connected: false`. The migration's true target set is the ~22-hour
   dishonest-stamp window **2026-08-12T04:26Z → 2026-08-13T02:27Z(+deploy
   lag)** — small, precise, and entirely missed above 20:00Z by the current
   cutoff.

**Fix:** move the cutoff to a value provably ≥ the `7dfcd16` deploy
completion — a generous `2026-08-13T06:00:00+00:00` is safe (over-eviction
costs one harmless re-sign-in; under-eviction re-opens #321). Record the
timestamps and reasoning in the ship-time DECISIONS entry scope.md §4
already promises, correct the blast-radius paragraph, and update T9's
boundary fixture to the final string. Idempotency itself is adequately
specified (T9's re-run no-op; NULL fails `<` — worth one explicit sentence
in R10 naming that mechanism, since the try/except wrapper in `_migrate_db`
would otherwise swallow a permanently-failing UPDATE).

### B2 — "Newest linked league row" is an unspecified contract term
**Cites:** prd.md §4 R1, §5 condition 1.

Two engineers will implement R1 differently:

- **Ordering undefined.** "Newest" by what — `created_at`, `updated_at`,
  insertion order? The existing strong-oracle loop
  (`server.py:19958-19964`) just takes the **first** cookie-gated row from
  `load_espn_leagues_for_user` (`backend/database.py:10606`), whose order
  R1 doesn't pin either.
- **Multi-league semantics undefined.** A user with two bound leagues where
  the pair matches league 1's bound team but not league 2's: R1 as written
  checks only one league, and *which* one decides the verdict. One ESPN
  human owns one SWID — a conclusive mismatch against **any** of the
  caller's bound linked leagues indicates the wrong account.

**Fix:** replace "newest" with a deterministic rule in §5, e.g.: *evaluate
every linked league row with a team binding; any conclusive mismatch →
`wrong_account`; otherwise conclusive match or inconclusive → accept per
R5/R6*, with at most one live read per league and the existing fail-open
posture. Add a T-test for the two-league mixed-verdict case. (This
ambiguity originated in plan §F1 — I own that — but §5 is the contract of
record and must resolve it.)

### B3 — Missing error case: league linked (or re-linked) AFTER the credential was stored — the stamp is never re-checked
**Cites:** prd.md §4 R1/R3, §5 condition 2; server.py:20206-20222 (stored-cookie fallback), 20415+ (`espn_import`).

R1 runs at **verify time** and R3 only "when cookies are
**pasted/captured** with an `espn_league_id` + chosen `team_id`". Neither
covers the sequence that re-opens #321:

1. Wrong-human pair is stored while the user has **no linked league** — R5's
   vacuous accept, correctly, stamps it (nothing to mismatch against). This
   also describes any post-08-12 wrong-account stamps the migration cannot
   identify.
2. The user then links a **public** league and picks their team — via the
   no-cookie path or the stored-cookie fallback (`server.py:20206-20222`,
   `pasted_cookie=False`). R3 does not fire (nothing pasted); the public
   fetch succeeds with any cookies; the stale stamp survives.
3. Result: verified stamp + bound team + wrong SWID — `connected: true`,
   my-leagues lists the other person's leagues, and a send would author the
   ESPN write as the other human (`member_swid`, `server.py:23545`) with
   whatever mislabeled error ESPN returns. The exact #321 state, one flow
   away.

**Fix:** extend R3 to run the same membership assertion on the league-link
**team-binding step regardless of cookie provenance** (pasted, captured, or
stored-fallback) whenever a credential row exists — the team list with
`owner_swid`s is already in hand from the import fetch, so this is
comparison-only, no extra ESPN read. On mismatch: 403 `wrong_account` **and
null the stamp** (or delete the row) so status stops lying. Add a pytest
(T8b) with a named sabotage, mirroring T8. Optionally assert at
`espn_import` re-sync too — cheap, same data in hand — or state its
exclusion explicitly.

## NON-BLOCKING

### N1 — Condition 2's client surface is unspecified (it works, but by accident of the wrapper)
prd.md §5 names two conditions producing the 403 but R7 gives a client
surface for condition 1 only (`EspnConnectScreen`). Condition 2 (league-link
path) surfaces in `EspnLinkSheet`'s generic catch — verified this round:
`ApiError` carries the server's `message`
(`mobile/src/api/client.ts:552-553`) and the sheet renders `e?.message`
(`EspnLinkSheet.tsx:287,324`, testID `espn-link.error`). So the
wrong-account copy does reach the user — but the PRD should say so (one
sentence in R7 or §5) and §7.2 should add a structural check that the
link-path rejection isn't swallowed by the `isEspnAuthRequired` branch.

### N2 — R4's failure semantics punish a public-league import over an optional credential
§5: "else the request fails with the verify verdict's status". For a PUBLIC
league the cookies are unnecessary to the import itself — failing the whole
import with a 502 because the fan-profile probe hiccuped degrades a
previously-working success path. Prefer: public-league import **succeeds**;
the pasted pair is simply **not stored/stamped** when verify doesn't pass
(response could carry an additive note). If the Author keeps fail-the-
request, §5 must at least say explicitly which status wins when import
succeeded but verify returned `unavailable` — that's the one genuinely
two-readings spot in an otherwise tight contract.

### N3 — R9 must reuse the `espn_reconnect` notification type — the web client allowlists types
Verified: `web/js/app.js:4895` allowlists inbox row types and maps
`espn_reconnect` at 4716. A new `wrong_account` type would be silently
dropped on web. R9 as drafted ("add `wrong_account` copy" to the existing
nudge) is compatible — pin one sentence in R9: *same type, new copy/meta
only*. Also softens scope.md §4's cross-client-invariants "n/a": true for
the 403 contract, but the notification-type enum IS multi-client.

### N4 — R5 silently dropped plan §F1's ownerless fallback
Plan §F1 said: bound team ownerless → "fall back to 'is any team's owner'".
PRD R5 turned that into unconditional inconclusive-accept. Defensible
(simpler, zero-false-reject), and I don't ask for the fallback back — but
the PRD should state the drop as deliberate so a builder doesn't
"helpfully" restore it from the plan.

### N5 — TestFlight checklist refinements
- Step 1 assumes the operator's row is pre-cutoff. If he re-signed-in on
  ≥1.13.2, his stamp postdates the (corrected) cutoff and step 1 "fails"
  misleadingly. Make it conditional: check `verified_at` (or GET status)
  before deploy and set the expectation accordingly.
- The original #321 symptom was **passive harvest** (stale jar captured with
  no login). Steps 4→5 only prove fresh-login after an active B sign-in. Add
  the explicit repro: sign in as B in the WebView, back out **without**
  disconnecting, relaunch, open ESPN Connect → login page must be signed
  out and nothing auto-captured.
- The blast-radius verdict ("bounded, account-keyed") deserves one runtime
  line: sign in to a **second FTF account** on the same device and confirm
  its ESPN status is independent (`not connected`).
- R8 (typed `reason` helper) has no test anywhere; fold into §7.2's first
  structural check.

## Summary

3 BLOCKING (B1 cutoff factually unsafe; B2 "newest league" underspecified
in the contract of record; B3 link-after-store path leaves the wrong-account
stamp undetected), 5 NON-BLOCKING. Everything else — the repro narrative,
Defect A/B analysis, the additive-`reason` compat posture, the sabotage
test discipline, D-056 waivers, and the docs table — checks out against
code and repo invariants. No objection to the drift note (recorded, per
coordinator).

---

## ROUND 2: SIGNED OFF

All eight round-1 dispositions verified present in the revised `prd.md` /
`scope.md` text, not merely claimed in the reconciliation log. B1's widened
full-eviction migration is sound and I re-derived its date-bound logic
independently: the every-boot `UPDATE … WHERE verified_at < RELEASE_CUTOFF`
cannot loop (nulled rows fail `<` under three-valued NULL — named in R10 and
pinned by T9's re-run fixture), a new-code stamp inside the +1h fallback
margin is evicted at most once (its re-stamp postdates the literal), and the
lexicographic ISO boundary behaves correctly even for microsecond-bearing
stamps against a seconds-precision literal (`.` sorts above `+`, so
post-cutoff stamps survive) — no off-by-one found, and the whole-cohort
blast radius is surfaced to the operator in scope.md §2 and waiver #5. B2's
any-conclusive-mismatch set semantics with explicit precedence (and the
mixed-verdict case specified as an intended binding error, T2b
`SAB-first-league-wins`) resolves the ambiguity; the precedence's
conservative edge (match-plus-outage → `unavailable`, nothing stored) is
deterministic and errs safe, so no objection. B3 is closed
provenance-independently (R3 at the team-binding step incl. the
`pasted_cookie=False` fallback, stamp-nulled only when the mismatching SWID
is the stored credential's — a correct refinement of my ask — plus
mandatory R3b at re-sync, T8b/T8c). N1–N5 are all in text, including the
`espn_reconnect` type-reuse pin against the web allowlist and the
checklist's passive-harvest and second-FTF-account steps. No round-2
objections. `prd.md` + `scope.md` are ready for Phase 2 build.

# FB-321 — group canonical folder

- **Status:** built 2026-08-16 · **Phase:** 2 (build complete on `feat/fb321-espn`, awaiting review/merge)
- **Group:** G5 — ESPN token bleed
- **Batch plan:** [`../304-positional-need-filter/batch-plan.md`](../304-positional-need-filter/batch-plan.md)
- **Spec base:** `origin/main` @ `d3fe3ac` (v1.13.4) · **Build base:** specs commit `56856f7` (= `origin/main` @ `96f6945` + Phase-1 specs); all PRD cites re-verified against the build tree (ESPN regions had drifted only in line numbers)

## Reported

> I think there is an issue with cookies or something else for my account.. I tested using another user account the other day and I think it is treating those tokens as mine, but that user is not in the espn league I am in, so it is silently failing. [Operator 2026-08-16: same physical device — investigate device-scoped credential storage first.]

## Build record (2026-08-16, G5 build agent)

Commits on `feat/fb321-espn` (in order):

1. `1627d27` — backend: identity binding (R1/R2), team-binding assertion (R3),
   re-sync assertion (R3b), public-league stamp gap closed (R4), R10
   migration + `clear_espn_credential_verification`, R9 nudge copy +
   identity-aware sweep, `espn_connect_store_rejected` registered (R11);
   two pre-existing tests updated to the new contract.
2. `2e216df` — `backend/tests/test_espn_identity_binding.py`: T1–T10
   (+T2b/T8b/T8c), 13 cases.
3. `2c7b068` — mobile: `espnRejectionReason` helper (R8), wrong-account
   state on `EspnConnectScreen` (R7, testID `espn-connect.wrong-account`),
   R11 event emitter, structural check
   `mobile/tests/check-espn-wrong-account.js` (+npm script).
4. `1e0f0fc` — docs: api-reference (§5 contract; **"Known residual
   (2026-08-12)" deleted — closed by R4**; GET migration note; import R3b
   note), data-dictionary `verified_at` addendum, runbook re-sign-in +
   wrong-account support section.

### Sabotage evidence (T1–T10 — apply → RED → revert → GREEN)

All 13 proven via a scripted loop (apply the one-line mutation, run the
named test expecting FAIL, `git checkout` revert, re-run expecting PASS):

| Test | Named sabotage | RED under sabotage | GREEN reverted |
|---|---|---|---|
| T1 `test_verify_wrong_swid_cookie_league` | `SAB-skip-membership` | ✔ | ✔ |
| T2 `test_verify_wrong_swid_public_league` | `SAB-public-skip` | ✔ | ✔ |
| T2b `test_verify_two_league_mixed_verdict` | `SAB-first-league-wins` | ✔ | ✔ |
| T3 `test_verify_correct_swid_each_oracle` | `SAB-invert-compare` | ✔ | ✔ |
| T4 `test_verify_ownerless_team_inconclusive` | `SAB-reject-ownerless` | ✔ | ✔ |
| T5 `test_verify_no_linked_league_unchanged` | `SAB-force-fetch` | ✔ | ✔ |
| T6 `test_verify_membership_read_outage` | `SAB-outage-as-bad` | ✔ | ✔ |
| T7 `test_link_public_league_no_stamp` | `SAB-always-stamp` | ✔ | ✔ |
| T8 `test_link_chosen_team_swid_mismatch` | `SAB-skip-link-check` | ✔ | ✔ |
| T8b `test_link_stored_cookie_fallback_mismatch` | `SAB-pasted-only` | ✔ | ✔ |
| T8c `test_import_resync_swid_mismatch` | `SAB-skip-resync-check` | ✔ | ✔ |
| T9 `test_migration_nulls_prerelease` | `SAB-invert-cutoff` | ✔ | ✔ |
| T10 `test_403_shape_additive` | `SAB-rename-code` | ✔ | ✔ |

T9's fixture set: born-NULL row untouched · dishonest-window stamp
(08-12T12:00Z) nulled · post-oracle pre-cutoff stamp (08-14) nulled ·
exact-cutoff boundary survives (`<` is strict) · microsecond stamp just
past the cutoff survives (lexicographic `.` > `+`) · post-release stamp
survives · **re-run returns rowcount 0** (NULL fails `<`) · GET reports
`connected: false` for a nulled row.

### R10 cutoff literal — provisional, FINALIZE AT SHIP

`_ESPN_VERIFIED_AT_RELEASE_CUTOFF = "2026-08-17T06:00:00+00:00"`
(`backend/database.py`). Chosen as same-day ship (2026-08-16) push-to-main
plus a generous overnight margin; reference timestamps `2fa1ff2` =
2026-08-12T04:25:58Z, `7dfcd16` = 2026-08-13T02:27:03Z (both verified from
git, PRD §8). **Erring later is safe; earlier is not** — so if the deploy
completes AFTER 2026-08-17T06:00Z, the ship agent MUST bump the literal to
observed-deploy-time (+1h) before/with the ship and update T9's boundary
fixtures (they read the constant, so only the raw date fixtures need a
glance). Record the final literal + both commit timestamps in the ship-time
DECISIONS entry (scope.md §4).

### Verification summary (D-056 — no Maestro/simulator)

- Backend: `test_espn_identity_binding.py` 13/13 green; full ESPN-adjacent
  suites green (`test_espn_link_route` 17, `test_link_status_routes`,
  `test_espn_propose_route`/`write`/`draft_order` 88, `test_roster_history`,
  `test_accounts`, `test_test_users`, analytics suites 117). Two
  pre-existing tests were UPDATED to the new contract (see prd deviations
  below).
- Mobile: `npm ci` (no symlink) · `npx tsc --noEmit` clean ·
  `mobile/scripts/testid-lint.sh` green ·
  `tests/check-espn-wrong-account.js` 21/21 (PRD §7.2 items incl. the
  EspnLinkSheet fall-through pin and the no-device-persistence invariant) ·
  existing `check-espn-connect-clear.js` still green.
- Web: `web/js/app.js` allowlist verified only (`espn_reconnect` at :4895,
  icon map :4716) — **not edited**, which is why R9 reuses the type.
- Runtime proof: operator TestFlight checklist = PRD §7.3 (two-account
  switch + passive-harvest repro + second-FTF-account keying check).

### PRD deviations (all small, with reasons)

1. **R4 gatedness detection**: the PRD says "cookie-league imports are
   unchanged" but gives no mechanism for the server to KNOW a league is
   auth-gated. Implemented with one **anonymous probe** at the import
   commit step (refused → gated → the cookie fetch was real proof; served →
   public → verify decides; probe transport failure → pair not stored,
   `credential_reason: "unavailable"`). Cost: one extra anonymous ESPN read
   per pasted-cookie import commit (store-time only, rare — within plan §7's
   stated risk posture).
2. **Import-path verify exclusion**: when the R4 verify runs during a
   re-link, THIS league's old binding is excluded from the membership
   assertion (`skip_league_id`) — otherwise a user re-linking to FIX a
   wrong binding is deadlocked by the old binding rejecting the pair R3
   just accepted against the newly chosen team. Not in the PRD; required
   for the re-link recovery the PRD itself promises (R1 "re-link recovery").
3. **auth_mode honesty on unproven public pairs**: when the league is
   proven PUBLIC and the pasted pair is NOT stored, the link is recorded
   `espn_auth='public'` (previously always `'cookie'` when a pair was
   pasted) — otherwise re-sync would 403 demanding cookies for a league
   that needs none while no credential row exists.
4. **Membership read refused (EspnAuthError) on a secondary league** is
   treated as a **conclusive mismatch** (the pair is a proven-live session
   that a linked league refuses → non-member), not `unavailable`. The PRD's
   R6 lists only transport/5xx/unparseable as `unavailable`; this is the
   set-semantics reading of R1.
5. **R9 implemented (not dropped)** with the sweep made identity-aware:
   on a conclusive stored-SWID-vs-bound-team mismatch the sweep writes the
   wrong-account `espn_reconnect` nudge (same type, `meta.reason`) and
   **continues syncing** (league rosters are league truth regardless of
   whose credential read them).
6. **Two pre-existing tests updated** to the new contract:
   `test_link_private_league_stores_encrypted_cookies` (must paste the
   owning SWID against a genuinely gated mock; now also asserts
   `credential_stored: true`) and the two oracle-preference tests in
   `test_link_status_routes.py` (owning SWID; the public-league test now
   expects exactly one membership league read).
7. **`credential_stored: true` on the stored-fallback provenance** (no new
   write happens — the response states the fact that a pair is at rest),
   matching §5's "any provenance" wording.

### Ship-time remainder (owned by the ship/merge agent)

- Finalize the R10 cutoff literal (above) — bright-line item.
- DECISIONS entry (grep max D-id first): identity ≠ session validity; the
  any-bound-league mismatch rule; inconclusive-accept incl. the deliberate
  plan-§F1 fallback drop; the full-eviction migration with the final
  cutoff + `2fa1ff2`/`7dfcd16` timestamps.
- CHANGELOG + TEST_LEDGER entries; GOTCHAS candidate ("a `verified_at`
  stamp proves session validity, not identity").
- Taxonomy doc (an-data-architect) row for `espn_connect_store_rejected`.
- Operator TestFlight checklist (PRD §7.3) post-deploy; log outcome in
  TEST_LEDGER.

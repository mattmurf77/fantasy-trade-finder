# PRD — P1-3 · Email capture at the Apple bind point (audit A-12)

> **Status:** REQUIREMENTS ONLY. No source file is changed by this document.
> **Worktree:** `p1-remediation-2026-08-11` @ `ab9368f`. **Lane L** in `HLD-p1.md` — governance-gated,
> **rebases and lands last** (`HLD-p1.md:324-333`, `:367`).
> **Companion:** [LLD-p1-3.md](LLD-p1-3.md) — the exact diff sites, the flip mechanism, the probe,
> the data flow, and the corrections to the plan.
> **Precedence:** [DECISIONS-p1.md](DECISIONS-p1.md) → [HLD-p1.md](HLD-p1.md) →
> [plan-p1-3.md](plan-p1-3.md) / [scope-p1-3.md](scope-p1-3.md).

## Contents

- [1. Problem statement](#1-problem-statement)
- [2. Goals and non-goals](#2-goals-and-non-goals)
- [3. The gate sequence — the spine of this item](#3-the-gate-sequence--the-spine-of-this-item)
- [4. Acceptance criteria](#4-acceptance-criteria)
- [5. Maestro position](#5-maestro-position)
- [6. Ship gate](#6-ship-gate)
- [7. Docs impact](#7-docs-impact)
- [8. Rollback](#8-rollback)
- [9. Decisions this document does not make](#9-decisions-this-document-does-not-make)

---

## 1. Problem statement

**The audit finding (A-12 / backlog P1-3) is that FTF captures no email address at all.** That is
true at runtime and false as a statement about the build.

Verified at `ab9368f`: the four `accounts` email columns are deployed and NULL
(`backend/database.py:1372-1375`, migrations `:1845-1848`); the capture logic is merged, flag-gated
and unit-tested (`backend/accounts.py:249-359`, `backend/tests/test_email_capture.py`); the Apple
bind point already passes the address through (`backend/server.py:18024-18027`); all three mobile
sign-in call sites already request the EMAIL scope. **One boolean is `false`**
(`config/features.json:58`) and one public document says we do not do this thing
(`web/privacy.html:95-96`, `:172`).

So the deliverable is not engineering. **The deliverable is the governance that makes flipping the
boolean legitimate**, and the sequencing that makes the flag and the published policy move as one.
The engineering is XS. The governance is M. This document is the governance.

Two things make it more than a one-line change, and they are the reason for the gates:

1. **Plaintext PII lands in columns that were NULL.** Not a structural schema change; a
   data-classification change. An email address, linked to an identifiable account, retained
   indefinitely, removable only by deleting the whole account, unencrypted at rest. That is a
   bright line under root `CLAUDE.md` § Feature gates, and it is why this item is **not
   express-lane eligible** (`plan-p1-3.md:382`, `scope-p1-3.md:137`).
2. **The urgency argument is unverified and the code contradicts its premise.** The resolution says
   Apple shares the address on first authorization only, so existing users can never be backfilled
   — "every week this stays off is permanently lost reach". FTF does not read the first-auth-only
   native credential property; it reads the `email` claim from the server-verified identity-token
   JWT, and `backend/accounts.py:327-333` is a deliberate repeat-auth backfill branch with a test
   pinning it. **If the claim is present on repeat authorizations, existing users backfill
   themselves on next launch and the urgency dissolves.** Nobody should buy a rushed legal review
   with an argument nobody has measured. That measurement is Gate 0, and it costs one log line and
   about a day.

---

## 2. Goals and non-goals

**Goals.**

- G1 — Answer, with evidence, whether repeat Apple authorizations carry the `email` claim.
- G2 — Store the provider-supplied address at bind time, for the Apple cohort, with a consent stamp.
- G3 — Make the published privacy policy true on the same deploy, and keep it true afterwards by
  making the mismatch a **red build** rather than a matter of memory.
- G4 — Leave every downstream obligation (send tooling, unsubscribe, App Store label, the Settings
  capture UI) explicitly owned and explicitly unbuilt, rather than implied.

**Non-goals.** Each is out of scope by decision, with the reason recorded in
[LLD §7](LLD-p1-3.md#7-deferred-by-decision): the Settings/onboarding "Add your email" field (owned
by the onboarding-conversion stream, and the **only** path that reaches Sleeper-username-only users
— the majority); any send path or Apple relay-domain registration; an unsubscribe route or any
writer for `email_unsubscribed_at`; the `email_captured` analytics event; encryption at rest for the
column; anything touching `fleaflicker.link`.

**Reach, stated honestly so nobody over-claims the outcome.** This lane reaches users who sign in
with Apple. Sleeper-username-only users — the majority — remain unreachable until the capture UI
ships. P1-3 does not close the retention gap; it stops the bleeding for one cohort.

---

## 3. The gate sequence — the spine of this item

**Six gates. They are ordered, and the order is not a suggestion.** `plan-p1-3.md:323`:
*"Nothing in this plan may proceed past gate 1 without sign-off."* Every gate below is an operator
decision — none is agent-decidable, and an agent that finds a gate unanswered stops and asks rather
than choosing the recommended option on the operator's behalf.

**Read this table first — it is the whole item.**

| Gate | HLD id | Decides | Owner | Blocks (artifact) | Evidence that closes it |
|---|---|---|---|---|---|
| **0** | `PV-1` | Is the urgency claim true? Do repeat Apple auths carry the `email` claim? | Operator (measurement executed by build agent) | **Everything.** No other gate may be answered on an unmeasured premise. | A dated result in `2026-07-17-email-capture-spec.md`'s status block, from the probe — **or** a written operator decision to proceed on the audit's premise without measuring (Option B), recorded as such. |
| **1** | `PV-2` | Flip `auth.email_capture` → `true`, and **by what mechanism**. | Operator | **Everything downstream.** Gates 2–5 exist only if the answer is "flip". | Written sign-off naming Option A (`config/features.json`, paired commit) and explicitly forbidding Option B (`FTF_FLAGS`), recorded in `DECISIONS.md`. |
| **2** | `PV-3` | Who writes the privacy-policy rewrite, and **does a lawyer read it**? | Operator (+ counsel, or the in-repo `/legal-privacy` skill) | **`web/privacy.html`, and therefore the entire flip commit** — the flag and the policy are one commit, so an unresolved Gate 2 blocks the flag too. | Either a reviewed diff, or a dated note in `web/privacy.html`'s header recording that review did not happen and that this was a knowing choice. |
| **3** | `PV-6` | What the policy promises about **removal and retention**. | Operator | The §5 and §6 text. Also blocks any temptation to build a removal path. | The policy's §5/§6 text matches the verified code behaviour in [LLD §6](LLD-p1-3.md#6-deletion-export-retention--as-it-already-stands), and promises no unsubscribe and no partial removal. |
| **4** | `AN-6` | Ship the `email_captured` analytics event? | Operator | The **shape of the change list**. Defer ⇒ zero analytics files touched. Elect ⇒ a `backend/server.py` edit **plus a T1 amendment commit** carrying T1's full deploy-and-verify gate, because `analytics_taxonomy.py` is frozen after T1 (`HLD-p1.md:286-287`). | A recorded answer. Default and recommendation: **defer** — three independent plans concur (`plan-p1-3.md:369`, `HLD-p1.md:480`, `scope-p1-3.md:20-28`). |
| **5** | `PV-7` | App Store privacy label — **Contact Info → Email Address**, linked to user (App Functionality + Developer Communications). | Operator | **Not the deploy. The next App Store submission.** | The obligation recorded in `docs/runbook.md` § *Sign in with Apple* (`:349-357`) and actioned in App Store Connect at the next submission. |

### 3.1 What each gate is actually asking

**Gate 0 — measure before you spend.** The probe is one `log.info` in `backend/server.py`, placed
after `find_or_create_account` returns so `acct["created"]` is available, emitting three fields:
provider, is-this-a-new-identity, does-the-claim-exist. **No address, no hash, no `sub`, no
`account_id`.** Implementation and read-out are in
[LLD §4](LLD-p1-3.md#4-gate-0-probe). Two ways to close it: the deterministic one — the operator
signs out and re-authenticates their own Apple ID and reads the log line — and the organic one,
watching repeat sign-ins for a day. With a production user count in the teens, the organic read
alone is weak evidence for a *null* result; say so rather than treating silence as proof.

*Why this gate is first:* if the claim arrives on repeat auths, existing Apple users backfill
themselves and Gate 2 can be a considered legal review instead of a rushed one. The audit was
already wrong once on this item (`plan-p1-3.md:124`).

**Gate 1 — the flip, and the mechanism.** Option A is `config/features.json` in the paired commit.
Option B is Render's `FTF_FLAGS` env var — one console click, no deploy, no diff, no reviewer, no
CI. **Option B is the only mechanism that can decouple capture from the policy, which is the exact
accident the pairing exists to prevent, and it is therefore prohibited for this key in both
directions.** Option C — don't flip — is defensible; note the asymmetry that capture is
reversible-forward (stop storing) while consent obtained at sign-in is not re-obtainable later.
Mechanism detail: [LLD §3](LLD-p1-3.md#3-flag-flip-mechanism).

**Gate 2 — the one document where a wrong sentence is a public misrepresentation.**
`web/privacy.html` is the App Store Connect privacy URL. Its own header
(`web/privacy.html:2-8`) carries a standing operator TODO: *"Have a lawyer review this document (it
has not had legal review)."* **This is the first change to the document that expands a collection
claim rather than narrowing one.** In no case does a build agent write final policy text unreviewed
and merge it — the LLD deliberately drafts none, and specifies only which claims can no longer stand
and which verified facts the replacement must cover
([LLD §2.4](LLD-p1-3.md#24-webprivacyhtml--sites-only-the-copy-is-not-this-llds-to-write)).

*Carried to this reviewer as context, not as scope:* `web/privacy.html:172`'s "the Service has no
email field" is already inaccurate in a second, independent way — Fleaflicker league discovery
collects a user-typed account email (never stored) and is dark only because `fleaflicker.link` is
`false` (`config/features.json:66`). Turning that flag on makes the same sentence false a second
way. One §2 rewrite can close both. **This does not put the Fleaflicker surface in P1-3's scope.**

**Gate 3 — disclose what exists, promise nothing else.** Verified: there is no way for a user to
remove their address short of deleting the account; `email_unsubscribed_at` has no writer anywhere;
there is no send path to unsubscribe from; retention is indefinite while the account exists.
Writing an unsubscribe promise now creates a written commitment the code cannot honour on the day it
publishes. Building a removal path instead turns a tier-4 governance release into a tier-1 mobile
change.

**Gate 4 — the event stays deferred, as a decision, not an oversight.** In this lane capture is a
server-side side effect of signing in, not a user action, and the quantity is already exactly
queryable from state (`SELECT count(*), email_source FROM accounts WHERE email_consent_at IS NOT
NULL`) — more accurately than from an append-only log. Electing it costs an intent-by-default DAU
decision (`analytics_queries.py:60-65` is a deny-list), an import-time-assert blast radius
(`analytics_taxonomy.py:298-332` — a mistake fails app boot, not a test), and a **sixth** claimant
on the round's most contended file, which T1 freezes.

**Gate 5 — a submission obligation, not a deploy blocker.** The label describes the binary's data
practices; the collection happens server-side and the next submission is the natural checkpoint.
"Wrong privacy label = rejection" is a recorded in-repo risk
(`docs/plans/analytics-platform/prd.md:239`), which is why the runbook entry is **mandatory rather
than advisory**.

### 3.2 Gate → artifact, restated as an unskippable dependency chain

```
Gate 0 ─┐
        ├─► Gate 1 ─► Gate 2 ─┐
Gate 3 ─┘                     ├─► C-flip  (ONE commit: 4 flag files + privacy.html
Gate 4 ───────────────────────┘            + 3 tests + docs + living-memory)
                                              │
                                              ▼
                                         Render deploy
                                              │
                                              ▼
                                    Gate 5 ─► next App Store submission

Gate 0 is closed by C-probe (backend/server.py, one log line, its own commit, tier 4).
C-probe is the ONLY artifact that may exist before Gates 1–4 are answered.
```

- **Nothing but the probe may be built before Gate 1 is signed off.**
- **The flip commit cannot be split.** Splitting the flag from the policy re-creates the exact
  window the pairing exists to close, and `test_release_flag_and_privacy_policy_ship_together` will
  make the split red anyway.
- **Gate 5 blocks nothing in this round.** It blocks the next submission, and it is the one gate
  that survives after the item ships.

---

## 4. Acceptance criteria

Each is individually testable by the stated method. **Every one must pass.**

**Gate 0 / the probe**

1. `C-probe` changes exactly one file and adds exactly one logging statement.
   *Method:* `git show --stat` shows only `backend/server.py`; `git show` shows one added
   `log.info` plus its comment.
2. The probe emits no address, no hash, no `sub`, and no `account_id`.
   *Method:* read the added line; `grep` the emitted format string for `email=`/`sub`/`account_id`
   → the only email-related token is the boolean `has_email_claim`.
3. The Gate-0 result is recorded, dated, with its method (deterministic re-auth and/or organic log
   window), in `docs/business/product/2026-07-17-email-capture-spec.md`'s status block — **or** a
   written operator election of Option B is recorded there instead.
   *Method:* read the file.

**The flip**

4. `config/features.json` has `"auth.email_capture": true`, preceded by a `_comment_auth_email_capture`
   block containing all five required clauses (what ON does · the policy pairing and its enforcing
   test · the `FTF_FLAGS` prohibition in both directions · that rollback stops writes but does not
   delete stored addresses · that the capture UI is unbuilt).
   *Method:* read the file.
5. All three flag fixtures carry `"auth.email_capture": true` —
   `backend/tests/fixtures/flags/release.json`, `profiles-on.json`, `onboarding-v2.json` — and
   `all-on.json` is unchanged.
   *Method:* `git diff --name-only`; then AC-6.
6. `test_release_flags_mirror_features_json`,
   `test_onboarding_v2_flags_are_release_plus_the_onboarding_surface`, and
   `test_profiles_on_flags_turn_on_public_pages_only` are green.
   *Method:* `pytest backend/tests/test_seed_ui_test_db.py`.
7. The flag flip and the `web/privacy.html` edit are in **one commit**.
   *Method:* `git show --name-only <C-flip>` lists both.
8. `auth.email_capture` is **not** present in any `FTF_FLAGS` value on Render, in either direction.
   *Method:* operator attestation + after deploy, `GET /api/feature-flags` returns `true` and the
   deployed commit's `config/features.json` says `true` — the two agree, so no override is in play.

**The policy**

9. `web/privacy.html` contains neither `"We never store your email"` nor `"No email addresses"`.
   *Method:* `grep`; and AC-13 makes it permanent.
10. §1 discloses that an address is stored when the provider shares one, that "Hide My Email" yields
    an Apple private-relay proxy stored the same way, and that the SHA-256 hash is also retained.
    *Method:* Gate-2 reviewer's read against
    [LLD §5](LLD-p1-3.md#5-data-flow--jwt-claim-to-column).
11. §5 states retention (kept while the account is active, deleted with it, no separate opt-out) and
    §6 names the email address in the deletion enumeration. **Neither promises an unsubscribe nor a
    partial removal.**
    *Method:* Gate-2/Gate-3 reviewer's read against
    [LLD §6](LLD-p1-3.md#6-deletion-export-retention--as-it-already-stands).
12. The effective date (`web/privacy.html:66`) is the flip date, and the header comment records the
    §1/§2/§5/§6 re-sync **and Gate 2's outcome** — reviewed, or knowingly not reviewed. The standing
    legal-review TODO is not deleted.
    *Method:* read the file.

**Tests**

13. `test_release_flag_and_privacy_policy_ship_together` exists and **fails** when the flag is `true`
    and either retired sentence is restored.
    *Method:* run it; then restore one sentence locally, confirm red, revert.
14. `test_delete_account_removes_email` and `test_export_includes_account_email` are new and green.
    *Method:* `pytest backend/tests/test_email_capture.py`.
15. The four pre-existing tests in `test_email_capture.py` are **byte-unchanged** and green.
    *Method:* `git diff` on the file shows additions only.
16. Full `pytest backend/tests/` is green and `npx tsc --noEmit` is clean.
    *Method:* CI.

**No drift, no scope creep**

17. `backend/feature_flags.py`'s comment above `"auth.email_capture"` no longer instructs the reader
    to flip only alongside a capture UI, states the `FTF_FLAGS` prohibition, and states that the
    Settings capture UI is unbuilt. `FLAG_KEYS` itself is unchanged.
    *Method:* read the diff.
18. Zero files under `mobile/src/` or `mobile/.maestro/` are changed.
    *Method:* `git diff --name-only <C-flip> | grep -c '^mobile/'` → 0.
19. `backend/analytics_taxonomy.py` and `backend/analytics_queries.py` are untouched, and no new
    event name exists anywhere in the diff (Gate 4 = defer).
    *Method:* `git diff --name-only`; `grep -r email_captured backend/` → no code hits.
20. `backend/accounts.py` and `backend/database.py` are untouched — no DDL, no logic change.
    *Method:* `git diff --name-only`.
21. Every docs row in [§7](#7-docs-impact) marked **Updated** is updated, and the two known factual
    drifts are corrected: `email_source`'s domain is `'apple' | 'google' | 'user'`, and
    `email_unsubscribed_at` is recorded as having no writer.
    *Method:* read the diffs.
22. `living-memory/`: a dated `CHANGELOG.md` H2; a `DECISIONS.md` entry carrying all three decisions
    (paired commit + `FTF_FLAGS` prohibition · relay-ness derived from the address suffix ·
    `email_captured` deferred), with the ID **read off the file at write time**, not taken from any
    plan; a `TEST_LEDGER.md` tier-4 entry with rationale, pytest result and SHA; **no
    `qa/sim-runs/last-sim-run.json` write.**
    *Method:* read the files.

**Post-deploy verification**

23. A fresh Apple sign-in produces one `accounts` row with `email` populated, `email_source='apple'`,
    and `email_consent_at` stamped.
    *Method:* row inspection after a real sign-in.
24. Re-authenticating an existing Apple account whose `email` is NULL either backfills it or does
    not, **matching the Gate-0 finding**. A contradiction here means Gate 0 was measured wrong and is
    reported, not rationalised.
    *Method:* row inspection.
25. A "Hide My Email" sign-in stores a value ending `@privaterelay.appleid.com` and nothing
    downstream errors.
    *Method:* row inspection + error-log scan.
26. A Sleeper-username sign-in creates no `accounts` row and therefore stores no address.
    *Method:* row inspection — confirms the flip's blast radius is the Apple cohort only.
27. `/privacy` on the deployed URL renders, and §1/§2/§5/§6 read end to end without internal
    contradiction. *(These sections cross-reference each other; a partial edit reads worse than no
    edit.)*
    *Method:* load the page and read all four.
28. The App Store Connect **Contact Info → Email Address** declaration is queued as a mandatory
    pre-submission action in `docs/runbook.md:349-357`.
    *Method:* read the file. *(Actioning it is Gate 5, at the next submission.)*

---

## 5. Maestro position

**Waived. The waiver is restated here from `plan-p1-3.md:231-241` and `scope-p1-3.md:74-84`, not
re-derived.**

- **No mobile diff exists to test.** The change set is `config/features.json`, three flag fixtures,
  `backend/feature_flags.py` (comment), `backend/tests/`, `web/privacy.html`, docs and
  `living-memory/`. Nothing under `mobile/src`. The three Apple sign-in call sites already request
  `AppleAuthenticationScope.EMAIL` and already forward only `cred.identityToken`; the address is
  read server-side from the verified JWT. Identical before and after the flip.
- **No new or renamed `testID`s** — `mobile/scripts/testid-lint.sh` is unaffected.
- **The "existing flow pins the bug" trap was checked for and is absent.** Every Maestro file
  mentioning Apple, sign-in or privacy was read: `flows/smoke/11-apple-entitlement.yaml` (an
  entitlement sensor that cannot reach a real Apple consent sheet, so it never exercises token
  claims), `flows/s1-spike-signin-ids.yaml` (backend-less testID spike), `capture/signin.yaml`,
  `capture/onboarding-signin@fresh.yaml`. **None asserts privacy copy and none asserts the absence
  of an email field.**
- **No capture delta** — no screen's visuals change, so `mobile/scripts/screen-freshness.sh` should
  flag nothing. If it flags something, something outside this scope moved.
- **When the waiver expires:** the moment the Settings/onboarding capture field ships (out of scope,
  owned by the onboarding stream), a flow covering enter → save → persists-across-relaunch becomes
  mandatory.

One nuance the flip introduces, recorded so it is not mistaken for a defect: the fixture flips mean
the harness now runs with capture ON. It is inert — no flow reaches a real Apple consent sheet, and
post-P0 the harness identity (`_test_mode_identity`) carries only `sub`, so no `email` claim ever
exists in a harness run and no address is ever written.

---

## 6. Ship gate

**Simulator tier 4** — backend/web/docs-only, per the matrix at `docs/runbook.md:92-99`. Zero
`mobile/src` files, no screen/navigation/state change, no route added or altered.

`githooks/pre-push` only blocks pushes containing `mobile/src` changes, so it will not fire here.
**The tier-4 declaration is therefore an honesty obligation, not an enforced one** — which is
exactly why it is logged in `TEST_LEDGER.md`.

Required before merge: CI green — `pytest backend/tests/` (including the three new tests) and
`npx tsc --noEmit`. Evidence: a `TEST_LEDGER.md` entry naming the tier, the rationale, the pytest
result and the SHA. **No `qa/sim-runs/last-sim-run.json` write** — tier 4 requires no sim run, and
writing a record for a run that did not happen would be worse than writing nothing.

**Express lane: not eligible.** Four bright lines — data classification (plaintext PII into
previously-NULL columns), feature-flag surface (a shipped default flip), public legal text, and
conditionally analytics. Per root `CLAUDE.md` § Feature gates, agents never self-select express, and
if the operator declares express on a bright-line change it must be surfaced and a confirming yes
obtained first. Stated here so it is not re-litigated at build time.

**Operator deviation available if belt-and-braces is wanted:** `smoke/11-apple-entitlement.yaml`
alone (~2 min), worth it only if the merge lands on top of P0 changes to the auth surface. Recorded
as a deviation in the scope block if taken.

---

## 7. Docs impact

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `web/privacy.html` | **Updated** | §1 (`:90-99`), §2 (`:172`), §5 (`:198-208`), §6 (`:210-234`), effective date (`:66`), header comment (`:2-8`). **Gate 2 owns the words.** |
| `docs/config-reference.md` | **Updated** | `auth.email_capture` row (`:155`) — default `true`, what it gates, pairing as shipped fact, `FTF_FLAGS` prohibition, Settings UI still unbuilt. |
| `docs/data-dictionary.md` | **Updated** | `accounts` rows `:814-817` — drop "dark / NULL until…"; state live behaviour; relay-address note; **correct `email_source`'s domain to `'apple' \| 'google' \| 'user'`**; record that `email_unsubscribed_at` has no writer. |
| `docs/runbook.md` | **Updated** | `:355` — the "keep it that way or amend the policy" instruction is now stale; record the amendment and add the App Store Connect label obligation. **This section (`:349-357`) is the correct home — the runbook has no generic pre-submission checklist.** |
| `docs/business/product/2026-07-17-email-capture-spec.md` | **Updated** | Dated status block: shipped vs deferred, the Gate-0 finding against the spec's own `:7` claim, and a correction to `:22` (deletion hard-deletes the row; it does not null the columns). |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/DECISIONS.md` | **Updated** | Three decisions; ID allocated at write time. |
| `living-memory/TEST_LEDGER.md` | **Updated** | Tier-4 declaration + pytest result + SHA. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if Gate 0 shows the Apple JWT behaving differently from the spec's documented expectation. |
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed or contract-changed. `GET /api/feature-flags` returns a different *value* for an existing key in an undocumented-per-key map; no client reads it (grep of `mobile/src` + `web/`: zero hits). |
| `docs/architecture.md` / `living-memory/HLD.md` | **n/a** | No module wiring or data-flow change — same call graph, same tables, same clients. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shift; the convention (flag-gated PII, consent stamped at capture) was set by the 2026-07-17 spec and is unchanged. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, colour or threshold consumed by multiple clients; `email_source` is backend-only. |
| `docs/glossary.md` | **n/a** | No new domain term. "Private relay" is Apple's vocabulary, defined inline where used. |
| `docs/design/design-system.md` / `components.md` | **n/a** | `privacy.html` is a self-contained static page with inline Chalkline tokens; the edit is prose inside existing `<li>` elements. |
| ADR | **n/a** | No architectural shift → `DECISIONS.md`, not a new ADR. |

---

## 8. Rollback

### 8.1 What reverses cleanly

| Action | How | Effect |
|---|---|---|
| Stop capturing | `git revert` **C-flip** — all four flag files and `web/privacy.html` move back together | New sign-ins stop writing addresses; the policy reverts with them. **The pairing test guarantees they revert together**: reverting one alone is a red build. |
| Stop capturing without reverting the policy | Set `"auth.email_capture": false` in `config/features.json` **and the three fixtures**, in one commit | Writes stop. The policy keeps describing capture — **this is legitimate**: over-disclosure is not a breach, and it is the direction the ordering rule permits. |
| Remove the probe | `git revert` **C-probe**, or delete the line in a follow-up | One log line stops. Nothing else depends on it. |

**The rollback lever is a commit, not a console click.** This is the deliberate cost of Gate 1's
prohibition on `FTF_FLAGS`: the deploy-free kill switch is given up **in both directions** for this
key, because the same mechanism that would let us turn capture off quickly is the mechanism that
could turn it on without the policy. Reverting requires a push and a Render deploy — minutes, not
seconds. That trade-off is accepted, and it is the reason it is recorded in four places.

### 8.2 What does **not** reverse

Read this before Gate 1 is signed off, not after.

1. **Addresses already stored are not deleted by turning the flag off.** The flag gates *writes*,
   not reads. Every row written while it was on stays exactly where it is. There is no purge path:
   nothing in the codebase nulls `accounts.email`, and building one is not in this item's scope. A
   purge would be a deliberate, manual, unreviewed-by-any-test operation on production data.
2. **Backups.** Whatever the hosting/database backup regime retains, the addresses are in it from
   the moment they are written. A revert does not reach backups.
3. **Consent, in the other direction.** Consent obtained at sign-in is **not re-obtainable later** —
   this is the argument *for* capturing promptly, and it is also why "we can always turn it off" is
   an incomplete description of the risk. The two asymmetries point in opposite directions and the
   operator should hold both.
4. **A published privacy policy is a public record.** Once `/privacy` has served the amended text it
   has been crawled, archived and (potentially) reviewed by Apple. Reverting the file does not
   unpublish the claim; it creates a second, contradictory version in the record.
5. **The App Store privacy label**, once declared at submission, describes the app to users in the
   store. Withdrawing it later is a subsequent submission and a visible change, not an undo.
6. **The relay-address property.** Apple private-relay proxies break permanently if the user revokes
   the app in iOS Settings → Apple ID → Sign in with Apple. A relay address that breaks is not
   recoverable by any action on our side, and re-consent is not obtainable.

**Practical consequence for Gate 1:** "we can flip it back" is true of *behaviour* and false of
*data*. If the operator's comfort with flipping rests on reversibility, the honest framing is: the
switch is reversible, the storage is not.

---

## 9. Decisions this document does not make

Every one of these belongs to the operator, and this PRD's only obligation is to make the
consequences visible and to name what is blocked until each is answered:

- **The privacy-policy copy** — any of it. Gate 2. The LLD names retired claims and required facts
  and drafts no sentence.
- **Whether a lawyer reads it.** Gate 2. The document has never had legal review, by its own header,
  and this is the first change that expands a collection claim.
- **Retention policy.** Gate 3. The LLD states what the code does; it does not propose a TTL, a
  reaper, or an unsubscribe.
- **The App Store data disclosure.** Gate 5.
- **Whether to ship `email_captured`.** Gate 4 / `AN-6`. Recommended defer; the recommendation is
  recorded as a decision with its reason so it does not read as an omission.
- **Whether to measure at all.** Gate 0 Option B is a legitimate operator choice; it is not an
  agent's choice.
- **Encryption at rest for `accounts.email`.** Not created by this item, not resolved by it.
- **Anything about `fleaflicker.link`.** Carried to the Gate-2 reviewer as context for one §2
  rewrite, and nowhere else.

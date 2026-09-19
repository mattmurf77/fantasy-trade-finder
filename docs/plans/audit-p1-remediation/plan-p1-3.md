# P1-3 — Email capture at the Apple bind point (audit A-12)

> **Status:** PLAN ONLY. No code touched. Every gate below is an operator decision.
> **Audit source:** `docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` P1-3 · resolution row `06-resolutions.md:97` (A-12, Idea, Ship as-is) · brief `02-tier-a-briefs.md:32`.
> **Worktree verified against:** `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at plan time).
> **Companion scope block:** [scope-p1-3.md](scope-p1-3.md).

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

Every line below was read in this worktree at `ab9368f`. Where a comment and the code disagreed, the code is cited.

### The flag exists and is wired end to end

| Thing | Where | State today |
|---|---|---|
| Flag value | `config/features.json:58` | `"auth.email_capture": false` |
| Flag registration | `backend/feature_flags.py:142` (doc comment `:138-141`) | Present in `FLAG_KEYS`; comment says "Flip ONLY in the same release as the capture UI + the privacy-policy update" |
| Flag resolution | `backend/feature_flags.py:641-713` | Process-cached (`_flags_cache`), computed from `config/features.json` **plus** the `FTF_FLAGS` env var (`:666-667`); `reload()` at `:708-713` |
| Flag exposure to clients | `backend/server.py:17270` `GET /api/feature-flags`; reload at `:17336` | The dotted map is served to every client — the flag's value is public once flipped |
| Test fixtures | `backend/tests/fixtures/flags/release.json:59`, `profiles-on.json:59`, `onboarding-v2.json:59` | All `false` |

### What the flag actually gates (it is **not** nothing)

`backend/accounts.py`:

- `_email_capture_enabled()` — `:249-259`. Lazy-imports `is_enabled("auth.email_capture")` and swallows any exception → `False`. A flags outage degrades to the pre-spec (hash-only) behaviour, never to a sign-in failure.
- `_normalize_email()` — `:262-265`. Requires an `@`, lowercases, trims.
- `find_or_create_account()` — `:288-359`. Line `:302` is the gate: `email = _normalize_email(email) if _email_capture_enabled() else None`. Three consequences:
  - **New identity path** `:346-352` — the `accounts` row is inserted with `email`, `email_source=provider`, `email_consent_at=now`.
  - **Returning identity path** `:325-333` — **an explicit backfill branch**: `if email and not acct.email` → write it. Never overwrites an address already on the row.
  - `email_hash` backfill for `linked_identities` `:317-324` runs regardless of the flag.
- `set_account_email(account_id, email, source="user")` — `:268-285`. The intended entry point for a future Settings/onboarding capture field. **Zero call sites** anywhere in `backend/`, `web/`, `mobile/src` (verified by repo-wide grep, tests excluded).
- `hash_email()` — `:234-238`. Unchanged, unflagged; the SHA-256 keeps flowing to `linked_identities.email_hash` (`backend/database.py:1383`) whether or not the flag is on.

### The schema already ships

`backend/database.py:1369-1375` — `accounts` already carries four nullable columns, live in `main` today:

```
Column("email",                 String)   # plaintext, normalized lower/trim
Column("email_source",          String)   # 'apple' | 'user'
Column("email_consent_at",      String)   # ISO — consent stamped at capture
Column("email_unsubscribed_at", String)   # ISO — never send when set
```

Additive migration entries at `:1844-1848`. **There is no DDL to write.** The columns are deployed and NULL in production.

### The Apple bind point

- **Backend:** `backend/server.py:18005-18027` `_provider_auth_response(provider, claims)` — shared by `/api/auth/apple` and `/api/auth/google`. Line `:18024-18026` is the single call site:
  ```python
  acct = _accounts.find_or_create_account(
      provider, sub, _accounts.hash_email(claims.get("email")),
      email=claims.get("email"),   # stored only when auth.email_capture is on
  )
  ```
  `claims` is the **server-verified identity-token JWT** payload (`accounts.verify_apple_token` → `verify_identity_token`, `:210-221`), not a client-supplied field. The account-only branch is `_mint_account_only_session()` `:18039-18075`.
- **Mobile:** three call sites, all already requesting the EMAIL scope and all forwarding only `cred.identityToken`:
  - `mobile/src/screens/SignInScreen.tsx:136-148` (scopes `:137-141`, token guard `:142`, POST `:148`)
  - `mobile/src/screens/SettingsScreen.tsx:354-361` (Apple link-from-Settings)
  - `mobile/src/components/AppleSaveMomentSheet.tsx:48-55` (onboarding save-moment sheet)

  **No mobile change is required for capture.** The client never sees or sends an address; the backend reads it from the verified token.

### Deletion and export already cover the address

- **Deletion:** `accounts.delete_user_data()` `:619-726`. The `accounts` row is **hard-deleted** at `:709-714` for every account id resolved at `:692-700` (bound accounts via `accounts.sleeper_user_id == uid`, plus the session-attached `account_id`). `linked_identities` deleted at `:703-708`. The email dies with the row — no nulling step needed. Route: `DELETE /api/account` (`server.py:18453+`), deliberately **not** flag-gated (App Store 5.1.1(v)).
- **Export:** `accounts.export_user_data()` `:774-832`. `_EXPORT_TABLES` (`:742-765`) does **not** list `accounts` — but the function handles the identity layer separately at `:806-830`, emitting `tables["accounts"]` and `tables["linked_identities"]`. So the plaintext email **is** in the GDPR archive automatically. Route `GET /api/account/export` at `server.py:18420-18450`, flag `account.data_export` = `true` (`config/features.json:127`), passing `account_id=sess.get("account_id")` so account-only users are covered too.

  *(I looked for an export gap here and did not find one. The `_EXPORT_TABLES` omission is real but not load-bearing.)*

### There is genuinely no email infrastructure

Repo-wide grep for `smtp|sendgrid|mailgun|postmark|boto3|ses_client|resend|nodemailer` across `backend/`, `requirements.txt`, `requirements-dev.txt`, `mobile/package.json`: **zero hits** (one false positive: `test_streaks.py:123`, the word "uses_client_tz"). Nothing writes `email_unsubscribed_at` (`database.py:1375` declares it; no writer). There is no unsubscribe route, no template, no send path, no domain configured for Apple Private Email Relay.

### The privacy policy contradicts the flipped state in two places

`web/privacy.html`, served at `/privacy` (`server.py:8058-8061`), which is also the App Store Connect privacy URL:

- **§1** (`:90-99`): "…and — if the provider shares an email address — a one-way SHA-256 hash of it. **We never store your email address itself**…"
- **§2 "Information we do NOT collect"** (`:172`): "**No email addresses**, phone numbers, or payment information — the Service has **no email field**, no billing, and no in-app purchases."
- §5 retention (`:198-208`) and §6 deletion/export (`:210-234`) are accurate but say nothing about an address.
- File header (`:1-8`) carries a standing operator TODO: *"Have a lawyer review this document (it has not had legal review)."*

Linked from: `mobile/src/screens/SignInScreen.tsx:557`, `SettingsScreen.tsx:1331`, `SleeperConnectScreen.tsx:124`, `EspnConnectScreen.tsx:279`, `web/index.html:127`, `web/faq.html:218,225`. `web/faq.html` makes **no** "we don't store email" claim — grep confirms; only the policy does.

**Already-latent inaccuracy in §2, unrelated to this item:** `mobile/src/components/PlatformLinkSheet.tsx:55,147-157` collects a Fleaflicker account email and posts it for league discovery (`backend/fleaflicker_service.py:125-133`, route `server.py:20964`). It is never stored. §2's "the Service has no email field" is true today only because `fleaflicker.link` is `false` (`config/features.json`). Worth telling the operator while the policy is open.

### The `email_captured` analytics event does not exist

`backend/analytics_taxonomy.py:105-136` `SERVER_FIRED_EVENTS` — no `email_captured`. The name appears **only** in the 2026-07-17 spec (`docs/business/product/2026-07-17-email-capture-spec.md:32`). Enforcement facts that matter if it is added:

- `record_event(user_id, event_type, …)` at `database.py:2592` requires a `users` row to exist (it bumps denorm columns in the same transaction).
- A new name in `SERVER_FIRED_EVENTS` is **intent-by-default**: `analytics_queries.py:60-65`, `INTENT_EVENTS = (SERVER_FIRED_EVENTS | ALLOWED_CLIENT_EVENTS) - NON_INTENT_EVENTS`.
- Import-time asserts at `analytics_taxonomy.py:298-332` (namespace disjointness; client events must have a `CLIENT_EVENT_PROPS` row) — a mistake here fails app boot, not a test.
- PII is already defended in the analytics layer: `analytics_ingest.py:160-162` denylists prop keys containing `email` and regex-strips address-shaped values; `api_observability.py:143` redacts `email`.

### Existing test coverage

`backend/tests/test_email_capture.py` — four tests, all passing today by monkeypatching `_email_capture_enabled`:
`test_flag_off_never_stores_plaintext`, `test_flag_on_stores_normalized_email_with_consent`, `test_backfill_fills_missing_but_never_overwrites`, `test_set_account_email_user_path_and_gates`.

### Drift from audit

The audit is two days and ~60 commits old. Here is what it got wrong or overstated, and what it got right.

| Audit claim | Verdict | Evidence |
|---|---|---|
| "No email capture … at all" (P1-3 title) | **Overstated.** True at *runtime*; false as a *build* statement. Schema, gate, normalization, consent stamping, first-auth store, repeat-auth backfill, the future UI's entry point, and four unit tests are all merged and shipping dark. | `accounts.py:249-359`, `database.py:1369-1375,1844-1848`, `tests/test_email_capture.py` |
| Effort **M** | **Too high** for the resolution as written. The code lane is a one-character flag flip; the cost is entirely policy, legal review and release choreography. Re-grade the *engineering* to XS and the *governance* to M. | see [Exact change list](#exact-change-list) |
| "Store the Apple relay address **at bind time**" | **Already implemented.** Bind time is exactly where it happens (`server.py:18024-18026` → `accounts.py:302,325-333,346-352`). Nothing to build. | as cited |
| "Apple shares the address on **first authorisation only**, so existing users **can't be backfilled** — every week this stays off is permanently lost reach." | **Unverified, and the code disagrees with the premise.** Two distinct Apple channels are being conflated: `ASAuthorizationAppleIDCredential.email` (the native credential property) *is* first-authorization-only — but FTF never reads it. FTF reads the `email` claim from the **verified identity-token JWT** (`server.py:18025`), a different channel, and `find_or_create_account:325-333` contains a deliberate repeat-auth backfill branch with a test pinning it. If the JWT carries `email` on repeat sign-ins, existing Apple users backfill themselves on their next launch and the urgency argument dissolves. **This must be measured, not assumed** — see [Operator checkpoints](#operator-checkpoints) gate 0. | `accounts.py:325-333`, `tests/test_email_capture.py::test_backfill_fills_missing_but_never_overwrites` |
| "Nothing user-visible to test" | **Confirmed** for the mobile client. No screen, copy, or `testID` changes. The one user-visible artifact is `web/privacy.html`. | no mobile diff in the change list |
| "No email infrastructure" | **Confirmed**, and worse than stated: no send path, no unsubscribe writer, no relay domain registration. | grep, `database.py:1375` |
| Resolution omits the analytics event the 2026-07-17 spec promised | **Gap.** `email_captured` is specced and unimplemented. | `analytics_taxonomy.py:105-136` |
| Backlog table lists P1-3 lever as `[R]` (retention) | **Confirmed**, with a caveat: capture reaches only Apple sign-in users. Sleeper-username-only users — the majority per the 2026-07-17 spec's own reality check — remain unreachable until the Settings/onboarding capture field ships. This lane does **not** close the retention gap; it stops the bleeding for one cohort. | `accounts.py:268-285` has no callers |

---

## Design

### Principle

The engineering is already merged and tested. **This item is a governance release, not a build.** The design job is (a) proving the urgency claim before spending a legal review on it, (b) making the two truth-surfaces — the flag and the policy — flip atomically, and (c) refusing to widen scope into UI or send infrastructure that this item does not need.

### Lane A — capture ON (the item)

One commit, one release, containing exactly:

1. `config/features.json` — `auth.email_capture` `false` → `true`.
2. `web/privacy.html` — §1 and §2 rewritten; §5 gains a retention line; §6 confirms deletion covers it.
3. `docs/config-reference.md` + `docs/data-dictionary.md` — the "dark / NULL until…" language becomes live language.
4. A regression test pinning the pairing (see [Test plan](#test-plan)).

Nothing else. No mobile diff, no route, no schema, no send path.

### Atomicity: the precise ordering constraint

Both truth-surfaces deploy from the same Render push of `main` — `config/features.json` is read by the backend process and `web/privacy.html` is served by the same Flask app from `static/`. **A single commit is therefore atomic in deploy terms**, and that is the only safe shape. Two hazards break the atomicity, and both must be closed explicitly:

- **`FTF_FLAGS` env override.** `feature_flags.py:666-667` lets a Render environment-variable change flip the flag with no code deploy — i.e. capture ON while the old policy is still being served, which is the exact failure this pairing exists to prevent. **Rule for this flag: never via `FTF_FLAGS`, only via `config/features.json` in the paired commit.** (Note this repo's standing gotcha that Render ignores `render.yaml` `envVars`, so a real env flip is a manual console action — one click, no review.)
- **`POST /api/feature-flags/reload`** (`server.py:17336`) re-reads both sources at runtime. Harmless when the paired commit is what's deployed; dangerous alongside an env override.

**Ordering, stated as a rule:** the policy may ship *before* capture (a policy that describes data you don't yet hold is over-disclosure, not a breach). Capture may never ship before the policy. The recommended shape is *same commit*, which satisfies both.

### Retention and deletion posture (nothing to build, everything to state)

| Question | Answer, as verified | Action |
|---|---|---|
| How long is the address kept? | Indefinitely while the account exists — no TTL, no reaper. | Policy §5 must say so plainly. |
| What deletes it? | `DELETE /api/account` → `delete_user_data` hard-deletes the `accounts` row (`accounts.py:709-714`). Not flag-gated. | Policy §6 gains an explicit "your email address" mention. |
| Is it exportable? | Yes — `export_user_data:806-830` emits `tables["accounts"]`. | Policy §6's export bullet already covers it generically; optionally name it. |
| Can a user remove *only* the email, keeping the account? | **No.** No route, no UI. `email_unsubscribed_at` has no writer. | Do **not** claim unsubscribe/removal in the policy. Disclose exactly what exists. This is gate 3. |
| Does it leak into analytics? | No — `analytics_ingest.py:160-162` denylist + regex; `api_observability.py:143` redaction; nothing puts an address in a prop. | Keep it that way (see the event gate). |

### Apple Private Relay vs a real address

`claims["email"]` is either the user's real address or an `@privaterelay.appleid.com` proxy, depending on the user's "Hide My Email" choice at the consent sheet. Verified in code: **nothing distinguishes them.** `_normalize_email` (`accounts.py:262-265`) accepts both identically; the `is_private_email` claim Apple ships alongside `email` is never read (repo-wide grep: zero hits for `is_private_email`).

Consequences the operator should hold before flipping:

- Relay addresses are **not** durable contact points. They break permanently if the user revokes the app in iOS Settings → Apple ID → Sign in with Apple, and they are unusable for outreach that asks a human to reply from their own inbox (user-interview recruiting — the operator's original stated motive).
- **Sending to a relay requires setup FTF has not done:** the sending domain must be registered in Apple Developer → Certificates, IDs & Profiles → **Sign in with Apple for Email Communication**, with SPF/DKIM. Mail to a relay from an unregistered domain is dropped. There is no such domain, no sender, and no send path today.
- **Storing them is still worth it** — a relay address is a valid, deliverable channel once the domain is registered, and re-consent is not obtainable later.
- **Optional, recommended, cheap:** persist Apple's own signal instead of inferring it from the string. Either read `claims.get("is_private_email")` and store `email_source='apple_relay'` vs `'apple'`, or (simpler, zero schema thought) leave `email_source='apple'` and derive relay-ness at query time from the `@privaterelay.appleid.com` suffix. Recommend **the derive-at-query-time option** for this lane: it adds no code, no enum, and no doc churn, and the suffix is stable and self-describing. Recorded so a future lifecycle build does not discover this the hard way.

### Explicitly out of scope

| Deferred | Why | Owner |
|---|---|---|
| Settings / onboarding "Add your email" field | The 2026-07-17 spec assigns the UI to the onboarding-conversion stream (`docs/plans/onboarding-conversion/`), which owns prompt cadence and snooze patterns. `set_account_email` is already waiting for it. **This is the only path that reaches Sleeper-username-only users.** | onboarding stream / `/eng-mobile` |
| Any send path (SMTP/SES/relay domain registration) | Nothing to send, no list yet. Registering the relay domain is a prerequisite of the *first send*, not of capture. | `/mkt-lifecycle` |
| Unsubscribe route / `email_unsubscribed_at` writer | CAN-SPAM obligation attaches to sending, not storing. Build it with the first send. | `/mkt-lifecycle` |
| `email_captured` analytics event | See gate 4 — recommended **defer**. | — |

---

## Exact change list

Ordered. Steps 0 and 1 are gates, not edits.

| # | File | Change |
|---|---|---|
| 0 | *(none — measurement)* | **Before any code change:** land a log-only probe or read prod logs to answer "does Apple's identity-token JWT carry `email` on *repeat* authorizations?" Cheapest honest form: one `log.info` at `server.py:18021` recording `provider`, `bool(claims.get("email"))`, and whether this `sub` is new — no address, no hash, in the log line. Ship it, watch a handful of repeat sign-ins, then decide. This answers gate 0 and costs nothing. |
| 1 | *(none — approvals)* | Operator sign-off on gates 1–5 below. Legal review of the §1/§2 diff if elected. |
| 2 | `web/privacy.html` | **§1, `:90-99`** — replace the trailing "We never store your email address itself" clause. New text discloses: when the provider shares an address we store it (plaintext) to contact you about the product and to invite you to occasional user research; note that choosing "Hide My Email" means we hold Apple's private-relay proxy, not your real address; note we also keep the one-way hash. **§2, `:172`** — delete "No email addresses" from the not-collected list; keep "no phone numbers, payment information, no billing, no in-app purchases"; drop the now-false "the Service has no email field". **§5, `:198-208`** — new bullet: the address is kept while the account is active and is deleted with it; there is no separate opt-out today. **§6, `:210-226`** — add "your email address" to the enumerated deletion list. **§9 "Changes to this policy"** — bump the effective date. Header comment `:1-8` — record that §1/§2 were re-synced to `auth.email_capture=true` on this date, and whether legal review happened. |
| 3 | `config/features.json:58` | `"auth.email_capture": false` → `true`. Add/extend the neighbouring `_comment_*` block: what it now gates, the policy pairing, and the **"never flip via `FTF_FLAGS`"** rule. |
| 4 | `backend/feature_flags.py:138-141` | Update the comment above `"auth.email_capture"` — it currently reads "Flip ONLY in the same release as the capture UI + the privacy-policy update". The capture *UI* is still not shipping; the accurate statement is "policy shipped with the flip on <date>; the Settings capture UI remains unbuilt (`set_account_email` has no callers)." **Do not leave a comment that lies about runtime state — this is the A-33 failure mode.** |
| 5 | `backend/tests/test_email_capture.py` | Add `test_release_flag_and_privacy_policy_ship_together` (see [Test plan](#test-plan)) — reads `config/features.json` and greps `web/privacy.html` for the two retired claims; fails if the flag is on while either sentence survives. This is the durable enforcement of the pairing. |
| 6 | `backend/tests/fixtures/flags/release.json:59` | `auth.email_capture` → `true`, so the release-profile fixture matches shipped reality. Leave `profiles-on.json` / `onboarding-v2.json` alone unless their suites assert on this key (they do not). |
| 7 | `docs/config-reference.md:155` | Rewrite the row: current state ON, what it gates, the policy pairing as a *shipped fact* rather than a future obligation, the `FTF_FLAGS` prohibition, and the still-missing Settings UI. |
| 8 | `docs/data-dictionary.md:814-817` | Drop "dark behind `auth.email_capture` (default off)" and "NULL until the flag + capture UI + privacy-policy flip ship together" from the `email` row. State: populated from the Apple/Google identity-token `email` claim at sign-in; `email_source` is `'apple'` in practice (`'user'` unreachable until the Settings field ships); private-relay addresses are stored indistinguishably and identifiable by the `@privaterelay.appleid.com` suffix; `email_unsubscribed_at` has no writer yet. |
| 9 | `docs/business/product/2026-07-17-email-capture-spec.md` | Append a dated status block: which parts shipped (schema, Apple path, flag, policy), which did not (Settings UI, `email_captured` event, unsubscribe, send tooling), and the gate-0 finding about repeat-auth backfill. |
| 10 | `docs/runbook.md:355` | That line currently instructs the reader to keep the hash-only posture ("keep it that way or amend the policy"). Amend it — the policy *was* amended. Add the App Store Connect label action (Contact Info → Email Address, linked to user) to the pre-submission checklist. |
| 11 | `living-memory/` | `CHANGELOG.md` (dated H2 — capture live + policy), `DECISIONS.md` (`D-0NN`: policy and flag ship in one commit; `FTF_FLAGS` prohibited for this flag; relay-ness derived from the address suffix rather than a new enum), `TEST_LEDGER.md` (tier-4 gate entry). |

**Conditional, only if gate 4 returns "add the event":** `backend/analytics_taxonomy.py:105-136` add `"email_captured"` to `SERVER_FIRED_EVENTS` under a new comment block; `backend/server.py` `_provider_auth_response` fire `record_event(user_id, "email_captured", source="api", props={"source": provider})` **after** the users row exists (i.e. after `_account_build_session` in the account-only branch `:18039-18075`, and after the bound-user session is resolved) — `record_event` writes denorm columns on `users` and needs the row; `find_or_create_account` would need to return whether it wrote an address (additive key on its return dict, existing callers unaffected). Also decide `NON_INTENT_EVENTS` membership (`analytics_queries.py:60`).

---

## Surface changes

| Surface | Change | Bright line? |
|---|---|---|
| **Routes** | **None.** No route added, removed, or contract-changed. `GET /api/feature-flags` (`server.py:17270`) begins reporting `auth.email_capture: true` — a value change in an existing payload, not a contract change. No client reads this key (repo-wide grep of `mobile/src` and `web/`: zero hits for `email_capture`). | No |
| **Schema** | **No DDL.** `accounts.email`, `email_source`, `email_consent_at`, `email_unsubscribed_at` already exist (`database.py:1369-1375`) with additive migration entries (`:1844-1848`). **But the columns start receiving PII where they previously held NULL** — a *data-classification* change even without a *structural* one. **Treated as a schema bright line.** | **YES** |
| **PII** | **New personal data class stored in plaintext**: an email address, linked to an identifiable account, retained indefinitely, deletable only by deleting the whole account. Apple private-relay proxies are stored under the same column with no distinguishing marker. **Bright line in its own right** — the reason this item cannot be an express-lane change. | **YES** |
| **Feature flags** | **No new flag.** `auth.email_capture` already exists (`feature_flags.py:142`, `config/features.json:58`); this is a **default-state change** on an existing flag. Nothing in this plan justifies a second flag. **Flag-surface bright line** (a shipped default flip is a behaviour change for every user). | **YES** |
| **Analytics events** | **None in the recommended lane.** `email_captured` is specced (`2026-07-17-email-capture-spec.md:32`) and unimplemented (`analytics_taxonomy.py:105-136`); recommendation is to defer it to the capture-UI build. **If the operator elects to add it, that is an analytics bright line** with an import-time-assert blast radius (`analytics_taxonomy.py:298-332`) and intent-by-default DAU semantics (`analytics_queries.py:65`). | **Only if elected** |
| **Public-facing legal text** | `web/privacy.html` — the App Store Connect privacy URL. Externally visible, legally load-bearing. | **YES (judgment/legal)** |
| **App Store privacy label** | Requires a **Contact Info → Email Address** declaration (linked to user; purposes App Functionality + Developer Communications) at the next submission. Not a code change; a submission-time obligation. Currently tracked only in `2026-07-17-email-capture-spec.md:38` and adjacent to `runbook.md:355`. | **YES (submission gate)** |

**Four bright lines. This is not a quick fix and must not be run express-lane.** Per `CLAUDE.md` § Feature gates, if the operator declares express on this item, that must be surfaced and a confirming yes obtained before proceeding.

---

## Maestro delta

**Waived, with reasoning.**

- **No mobile diff.** The change list touches `config/features.json`, `web/privacy.html`, `backend/tests/`, `backend/tests/fixtures/`, and docs. Nothing under `mobile/src`. The three Apple sign-in call sites (`SignInScreen.tsx:136-148`, `SettingsScreen.tsx:354-361`, `AppleSaveMomentSheet.tsx:48-55`) already request `AppleAuthenticationScope.EMAIL` and forward only `identityToken` — unchanged before and after the flip.
- **No new or renamed `testID`s.** `mobile/scripts/testid-lint.sh` is unaffected.
- **No flow asserts the surface, and I checked for the "flow pins the bug" trap.** Every Maestro file mentioning Apple, sign-in, or privacy was read:
  - `mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` — entitlement regression sensor. Taps `signin.apple-btn`, asserts the native failure copy is absent, then a Settings reachability leg (`settings.link-apple-btn`). It cannot reach a real Apple consent sheet (Maestro cannot drive it), so it never exercises token claims. Unaffected.
  - `mobile/.maestro/flows/s1-spike-signin-ids.yaml` — testID visibility spike, backend-less. Unaffected.
  - `mobile/.maestro/capture/signin.yaml`, `capture/onboarding-signin@fresh.yaml` — screen-library captures. No visual change on any screen, so **no capture delta**; `mobile/scripts/screen-freshness.sh` should flag nothing.
  - **No flow asserts privacy-policy copy** and none asserts the absence of an email field — so no existing flow is pinning the behaviour being changed. (This was the specific failure mode to look for; it is absent here.)
- **`testID`s needed: none.**
- **When the waiver expires:** the moment the Settings/onboarding capture field ships (out of scope here), a new flow covering enter → save → persists-across-relaunch becomes mandatory.

**Sim-gate tier: 4** (backend-config/web/docs-only) per `docs/runbook.md:98-99`. CI-only: pytest + `tsc --noEmit`. No `qa/sim-runs/last-sim-run.json` write required; `githooks/pre-push` only blocks pushes touching `mobile/src`. Log the tier-4 declaration in `TEST_LEDGER.md` regardless.

---

## Docs impact table

Row per `docs/CLAUDE.md` trigger.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, removed, or contract-changed. `GET /api/feature-flags` returns a different *value* for an existing key; the response shape is a flag map with no per-key documentation. |
| `docs/data-dictionary.md` | **Updated** | `accounts` table, `email` / `email_source` / `email_consent_at` / `email_unsubscribed_at` rows (`:814-817`) — drop "dark / NULL until…", state live behaviour, relay-address note, "`email_unsubscribed_at` has no writer". |
| `docs/config-reference.md` | **Updated** | `auth.email_capture` row (`:155`) — ON, what it gates, pairing shipped, `FTF_FLAGS` prohibition, Settings UI still unbuilt. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. Same call graph (`server._provider_auth_response` → `accounts.find_or_create_account`), same tables; only a boolean changes. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shift. The convention (flag-gated PII, consent stamped at capture) was established by the 2026-07-17 spec and is unchanged. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, colour, or threshold consumed by multiple clients. `email_source`'s `'apple'`/`'user'` values are backend-only — no client reads them. |
| `docs/glossary.md` | **n/a** | No new domain term. "Private relay" is Apple vocabulary, defined inline in the policy and the data dictionary. |
| `docs/runbook.md` | **Updated** | `:355` — the "keep it that way or amend the policy" instruction is now stale; record the amendment and add the App Store Connect label action (Contact Info → Email Address) to the pre-submission checklist. |
| ADR / `living-memory/DECISIONS.md` | **Updated — `DECISIONS.md`, not an ADR** | Three non-obvious choices: (a) flag + policy in one commit, `FTF_FLAGS` prohibited for this flag; (b) relay-ness derived from the address suffix rather than a new `email_source` value or an `is_private_email` column; (c) `email_captured` deferred to the capture-UI build. No architectural shift → `DECISIONS.md` entry, not a new ADR. |
| `docs/design/design-system.md` / `components.md` | **n/a** | `web/privacy.html` is a self-contained static page with inline Chalkline tokens (`:20-24`); the edit is prose inside existing `<li>` elements. No component or token change. |
| `docs/business/product/2026-07-17-email-capture-spec.md` | **Updated** | Dated status block — shipped vs deferred, plus the gate-0 backfill finding. |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | Tier-4 gate declaration + pytest result. |

---

## Test plan

**Backend (pytest) — the whole automated surface.**

1. **Existing four tests keep passing unchanged.** `backend/tests/test_email_capture.py` monkeypatches `_email_capture_enabled` (`:41`), so it is deliberately independent of the flag's real value — flipping `config/features.json` must not move them. If any of them changes behaviour, something other than the flag moved.
2. **New: `test_release_flag_and_privacy_policy_ship_together`.** The durable pairing enforcement, and the single most valuable artifact this item produces. Reads `config/features.json`; if `auth.email_capture` is true, assert `web/privacy.html` contains **neither** `"We never store your email"` **nor** `"No email addresses"`. A future session that flips the flag without the policy, or reverts the policy without the flag, gets a red CI run instead of a silent misrepresentation. Cheap, no fixtures, no network.
3. **New: `test_flag_default_is_on_in_release_fixture`.** Pin `backend/tests/fixtures/flags/release.json` so the release profile can't drift back.
4. **New: `test_delete_account_removes_email`.** End-to-end at the `accounts` level with a real in-memory engine (same pattern as `test_email_capture.py:22-31`): create an account with an email, run `delete_user_data`, assert the row is gone. Pins the retention promise the policy will now make. `accounts.py:709-714` says it works; the test says it keeps working.
5. **New: `test_export_includes_account_email`.** Assert `export_user_data(...)["tables"]["accounts"][0]["email"]` is present. Pins `accounts.py:806-830` — the export path that makes policy §6 truthful — against a future refactor into `_EXPORT_TABLES`.
6. **Regression sweep:** full `pytest backend/tests/` — the flag now resolves true in any test that does *not* monkeypatch it, so any incidental dependency on the old default surfaces here. `test_accounts.py` in particular.

**Manual / operational.**

7. **Gate-0 probe (before the flip).** With the log line from change 0 deployed: sign in with Apple on a *fresh* Apple ID (expect `email=True`), then sign out and re-authenticate the *same* ID (the answer). Record the result in the spec's status block. This is the measurement that decides whether the audit's urgency framing survives.
8. **Post-flip verification (staging or first prod sign-in).** New Apple sign-in → confirm one `accounts` row with `email` populated, `email_source='apple'`, `email_consent_at` stamped. Then re-authenticate an existing Apple account with a NULL email → confirm the `:325-333` backfill fires (or does not, per gate 0).
9. **"Hide My Email" path.** Sign in choosing Hide My Email → confirm the stored value ends `@privaterelay.appleid.com` and that nothing downstream chokes on it.
10. **Policy render.** Load `/privacy` on the deployed URL and re-read §1, §2, §5, §6 end to end for internal contradictions — the sections cross-reference each other and a partial edit reads worse than no edit.
11. **Non-Apple path unchanged.** Sleeper-username sign-in → `accounts.email` stays NULL (there is no account row at all for a pure username session). Confirms the flip has zero blast radius on the majority path.

**Not tested, by design:** any send path (none exists); unsubscribe (no writer); the Settings capture field (not built).

---

## Risks and cross-item collisions

**Risks.**

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Capture goes live while the old policy is served — a public misrepresentation on the App Store privacy URL. | **High** | Single commit; test 2 makes the mismatch a red build; `FTF_FLAGS` prohibited for this flag and recorded in `DECISIONS.md`. |
| R2 | The policy §1/§2 rewrite is done by an agent and never legally reviewed — on a document whose own header says it has never been reviewed (`privacy.html:1-8`). | **High** | Gate 2. Draft the diff, ship nothing until the operator signs it or elects to accept the standing no-review posture *knowingly*. |
| R3 | App Store submission with a stale privacy label → rejection or a post-hoc correction. Precedent in-repo: `docs/plans/analytics-platform/prd.md:239` names exactly this failure. | **Medium** | Gate 5; runbook checklist addition (change 10). Not blocking for the *deploy*, blocking for the next *submission*. |
| R4 | Relay addresses accumulate and are undeliverable when the first campaign runs, because the sending domain was never registered. | **Medium** | Documented in the spec status block as a prerequisite of the first send. Not a blocker for capture. |
| R5 | Users have no way to remove their address short of deleting the account, while the policy is being rewritten to describe capture. | **Medium** | Gate 3 — disclose the actual state; do **not** write an unsubscribe promise the code cannot keep. `email_unsubscribed_at` exists but has no writer (`database.py:1375`). |
| R6 | Plaintext addresses in an unencrypted SQLite file on Render, alongside Fernet-encrypted Sleeper tokens — a visible asymmetry in the security posture. | **Low–Medium** | Accept and disclose; `privacy.html:236-243` already states the beta-service security posture honestly. Encryption-at-rest for this column is a separate decision, not this item's. |
| R7 | Comment drift — `feature_flags.py:138-141` and `config-reference.md:155` both currently instruct a reader that the flag is off and must ship with a capture UI. Leaving either stale reproduces **A-33**, the exact failure the audit already caught. | **Medium** | Changes 4 and 7 are mandatory, not optional. Verify by re-reading, not by trusting the diff. |
| R8 | The urgency argument ("every week is permanently lost reach") drives a rushed legal review, and turns out to be false. | **Medium** | Gate 0 measures it first. The probe is one log line and costs a day. |

**Cross-item collisions.**

| With | Collision | Resolution |
|---|---|---|
| **P0-5** (`account_only` users stranded — `docs/plans/audit-p0-remediation/plan-p0-5.md`) | Same function, `server.py:_provider_auth_response` / `_mint_account_only_session` (`:18039-18075`). P0-5 changes post-auth *routing*; P1-3 changes nothing in that function in the recommended lane. **If gate 4 elects the `email_captured` event, both items edit this function** — and the event must fire after the users row exists, which is precisely the code P0-5 is restructuring. | P0 merges to `main` first (stated constraint). Rebase P1-3 on merged `main` and re-verify `:18005-18075` line numbers before editing. In the recommended (no-event) lane there is **zero file overlap** with P0-5. |
| **P0-7** (client analytics instrumentation — `plan-p0-7.md:241-307`) | P0-7 edits `backend/analytics_taxonomy.py` in three places: `ALLOWED_CLIENT_EVENTS` (`:38-99`), `SERVER_FIRED_EVENTS` (`:105-136`, the Trades block), and `CLIENT_EVENT_PROPS` (`:165-255`). A P1-3 `email_captured` entry lands in the same frozenset. | Sequential, not parallel — P0 merges first. Recommended lane touches this file not at all, which is an additional argument for gate 4 = defer. |
| **P0-1** (`ranking_method` written at point of use) | None. Different tables, different routes. | — |
| **Onboarding-conversion stream** (`docs/plans/onboarding-conversion/`) | Owns the Settings/onboarding capture UI per `2026-07-17-email-capture-spec.md:30`. If that stream ships a capture field **before** this flag flips, `set_account_email` (`accounts.py:276`) silently returns `False` and the field appears to work while storing nothing. | Whichever ships first must state the dependency. Flipping the flag first is strictly safer — capture-without-UI is invisible; UI-without-capture is a lie to the user. Another argument for shipping this lane now. |
| **`fleaflicker.link`** (`config/features.json`, currently `false`) | Turning it on makes `web/privacy.html:172` ("the Service has no email field") false a *second* way, via `PlatformLinkSheet.tsx:147-157`. | Fix both in the same §2 rewrite while the file is open — one edit, two latent inaccuracies closed. Flag it to the operator. |
| **Other P1 items in this round** | No file overlap with P1-1/P1-2 (share paths), P1-4 (adjustments), P1-5 (invite), P1-7/P1-8 (unlock coherence), P1-10 (Sleeper Connect analytics — *does* touch `analytics_taxonomy.py`; another reason to keep P1-3 out of that file). | Coordinate `analytics_taxonomy.py` ownership at build time; recommended lane needs none of it. |

---

## Operator checkpoints

Six gates. Each is a decision that belongs to the operator, not to the build agent. Nothing in this plan may proceed past gate 1 without sign-off.

### Gate 0 — Measure the urgency claim before acting on it *(recommended: do this first, it is nearly free)*

The resolution's urgency rests on "Apple shares the address on first authorisation only, so existing users can't be backfilled — every week this stays off is permanently lost reach." **The code contradicts the premise.** FTF reads `email` from the verified identity-token JWT (`server.py:18025`), not from the native credential property that is genuinely first-auth-only, and `accounts.py:325-333` contains a repeat-auth backfill branch with a test pinning it.

- **Option A — probe first (recommended).** Ship one log line (`bool(claims.get("email"))` + is-new-sub, no address, no hash) at `server.py:18021`. Watch a few repeat Apple sign-ins. If the claim is present on repeat auths, the whole "permanently lost reach" framing dissolves, existing users backfill themselves on next launch, and this item can proceed at a considered pace with a proper legal review instead of a rushed one. Cost: one deploy, ~a day.
- **Option B — accept the audit's premise and flip now.** Faster; risks compressing gates 2 and 5 on an unverified urgency argument.

**Recommendation: A.** It is a single log line, it costs a day, and it determines whether the legal review is a rush job or a considered one. The audit itself was wrong once already on this item (see the Drift table).

### Gate 1 — Flip `auth.email_capture` to `true`

- **Option A — flip in `config/features.json`, in the same commit as the policy (recommended).** Atomic at deploy; the paired-commit test (test 2) enforces it forever after.
- **Option B — flip via Render's `FTF_FLAGS` env var.** One console click, no deploy, no review, no CI. **Recommend explicitly forbidding this** for this flag and recording the prohibition in `DECISIONS.md` — it is the only mechanism that can decouple capture from the policy, which is the exact accident the pairing exists to prevent.
- **Option C — don't flip.** Defensible only if the operator decides email is not a channel worth the compliance surface. Note the asymmetry: capture is cheap and reversible-forward (flip back off and stop storing), but consent obtained at sign-in is *not* re-obtainable later.

**Recommendation: A**, sequenced after gate 0 resolves.

### Gate 2 — Privacy-policy rewrite: who writes it, and does a lawyer read it?

`web/privacy.html:1-8` carries a standing operator TODO: *"Have a lawyer review this document (it has not had legal review)."* This item makes the first change to the document that expands a data-collection claim rather than narrowing one.

- **Option A — agent drafts the §1/§2/§5/§6 diff, lawyer reviews before merge (recommended).** The one document where a wrong sentence is a public misrepresentation on the App Store privacy URL.
- **Option B — agent drafts, operator reviews, ship without legal.** Consistent with the document's current (unreviewed) posture; a knowing acceptance rather than an oversight. Note that adding a *collection* disclosure is lower-risk than removing one — over-disclosure is not a breach.
- **Option C — have `/legal-privacy` (the in-repo role skill) review, then operator.** Middle ground; not a substitute for counsel.

**Recommendation: A if a lawyer is reachable inside the launch window; otherwise C plus a dated note in the file header recording that the review did not happen.** In no case should a build agent write final policy text unreviewed and merge it — this plan deliberately does not draft that text.

### Gate 3 — What the policy promises about removal

Verified: there is **no** way for a user to remove their address without deleting the entire account. `email_unsubscribed_at` (`database.py:1375`) has no writer; there is no unsubscribe route; there is no send path to unsubscribe *from*.

- **Option A — disclose exactly the current state (recommended).** "We keep it while your account exists; deleting your account deletes it; we do not currently send email." Truthful, and it ages gracefully — no promise to retrofit.
- **Option B — write an unsubscribe promise now and build it later.** Creates a written commitment the code cannot honour on the day it publishes.
- **Option C — build a removal path in this item.** Scope creep: a route, a Settings row, a Maestro flow, and a mobile diff — turning a tier-4 governance release into a tier-1 mobile change.

**Recommendation: A.** Revisit at the first send, which is when the CAN-SPAM obligation actually attaches.

### Gate 4 — Ship the `email_captured` analytics event?

Specced at `2026-07-17-email-capture-spec.md:32`, unimplemented (`analytics_taxonomy.py:105-136`).

- **Option A — defer to the capture-UI build (recommended).** In this lane the capture is a *server-side side effect of signing in*, not a user action. It is already perfectly countable from the `accounts` table itself (`SELECT count(*), email_source FROM accounts WHERE email_consent_at IS NOT NULL`) — more accurately than an event log, since it reflects current truth rather than an append-only stream. Adding a taxonomy name costs an import-time-assert blast radius, intent-by-default DAU semantics (`analytics_queries.py:65`), a `server.py` edit inside the function P0-5 is restructuring, and a collision with P0-7 and P1-10 in `analytics_taxonomy.py`. The event earns its place when a *user* acts — i.e. when the Settings field ships.
- **Option B — add it now** to honour the spec as written. Then it must go in `SERVER_FIRED_EVENTS`, fire after the users row exists, carry `props={"source": provider}` (**never the address** — `analytics_ingest.py:160-162` would strip it anyway, which is the safety net, not the design), and get an explicit `NON_INTENT_EVENTS` decision.

**Recommendation: A.**

### Gate 5 — App Store privacy label

Capturing an address obliges a **Contact Info → Email Address** declaration (linked to user; purposes App Functionality + Developer Communications) at the next submission.

- **Option A — flip capture now, update the label at the next submission (recommended).** The label describes the app binary's data practices; the collection happens server-side and the next submission is the natural checkpoint. Add it to the runbook's pre-submission checklist (change 10) so it cannot be forgotten — `docs/plans/analytics-platform/prd.md:239` records "wrong privacy label = rejection" as a known risk from a previous round.
- **Option B — hold the flip until the next submission is being prepared**, so label and capture go live together. Maximally conservative; costs the reach the audit is worried about.

**Recommendation: A, with the checklist entry treated as mandatory rather than advisory.**

### Bright-line acknowledgement

Per `CLAUDE.md` § Feature gates: this item crosses **four** bright lines — schema/data-classification (plaintext PII into previously-NULL columns), feature-flag surface (shipped default flip), public legal text, and (conditionally) analytics events. **It cannot be run express-lane.** If the operator declares express, that must be surfaced and a confirming yes obtained before any of the above proceeds.

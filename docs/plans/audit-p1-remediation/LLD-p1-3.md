# LLD — P1-3 · Email capture at the Apple bind point (audit A-12)

> **Status:** DESIGN ONLY. No source file is changed by this document.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at authoring time).
> **Inputs, in precedence order:** [DECISIONS-p1.md](DECISIONS-p1.md) (binding) →
> [HLD-p1.md](HLD-p1.md) → [plan-p1-3.md](plan-p1-3.md) + [scope-p1-3.md](scope-p1-3.md).
> **Companion:** [PRD-p1-3.md](PRD-p1-3.md) — the gate sequence and acceptance criteria.
> **Every file:line below was re-read in this worktree at `ab9368f`.** Where the plan and the
> code disagree, the code is cited and the disagreement is recorded in
> [§10 Corrections to the plan](#10-corrections-to-the-plan).

## Contents

- [0. Position in the program](#0-position-in-the-program)
- [1. Anchors, re-verified](#1-anchors-re-verified)
- [2. The diff, site by site](#2-the-diff-site-by-site)
- [3. Flag-flip mechanism](#3-flag-flip-mechanism)
- [4. Gate-0 probe](#4-gate-0-probe)
- [5. Data flow — JWT claim to column](#5-data-flow--jwt-claim-to-column)
- [6. Deletion, export, retention — as it already stands](#6-deletion-export-retention--as-it-already-stands)
- [7. Deferred by decision](#7-deferred-by-decision)
- [8. Test matrix](#8-test-matrix)
- [9. Re-verify after P0 merge](#9-re-verify-after-p0-merge)
- [10. Corrections to the plan](#10-corrections-to-the-plan)
- [11. What this LLD deliberately does not do](#11-what-this-lld-deliberately-does-not-do)

---

## 0. Position in the program

`HLD-p1.md` §B classifies P1-3 as **lane L — "not a wave, a lane"** (`HLD-p1.md:324-333`), and §C
step **L** places it **last**: "P1-3 lands whenever its gates clear — before, between or after any
of steps 2–6, but always rebasing onto whatever is on `main`" (`HLD-p1.md:367`). §D restates why:
the item is *decision-throughput-bound, not build-bound*, and Gate 2 asks a question — does a
lawyer read the diff — that is not on an engineering timeline (`HLD-p1.md:405-413`).

Three consequences this LLD is written around, and which a builder must not quietly reverse:

1. **No wave slot, no wave clock.** There is no "P1-3 ships in wave X" date. The build starts when
   gates 0–3 are signed off, not when a wave opens.
2. **Every line number here is provisional.** P1-3 rebases onto a `main` that will by then contain
   the whole P0 merge and (probably) T1 + waves A–B. Three other items write
   `config/features.json` and `backend/feature_flags.py` before it. [§9](#9-re-verify-after-p0-merge)
   is the mandatory re-locate pass.
3. **The ID-allocation rule applies.** `HLD-p1.md:261-271` — P1-3 is *last* in the allocation
   order, so its `DECISIONS.md` / `GOTCHAS.md` IDs are read off the file at write time. Do not use
   any ID printed in `plan-p1-3.md`.

**Rigor posture.** Four bright lines (data classification, feature-flag default flip, public legal
text, and — only if AN-6 flips — analytics). Full gates, **never express** (`scope-p1-3.md:137`,
root `CLAUDE.md` § Feature gates). Simulator tier **4** (`docs/runbook.md:98-99` — backend/web/docs
only, no `mobile/src` diff).

---

## 1. Anchors, re-verified

Every claim `plan-p1-3.md` makes about the code held at `ab9368f`. Re-verified line numbers:

| Fact | Location at `ab9368f` | State |
|---|---|---|
| Flag value | `config/features.json:58` | `"auth.email_capture": false,` |
| Flag registration + comment | `backend/feature_flags.py:142`, comment `:138-141` | present in `FLAG_KEYS` (one flat tuple opened at `:47`) |
| Flag defaults are all-False | `backend/feature_flags.py:619` | `DEFAULT_FLAGS = {key: False for key in FLAG_KEYS}` — **`config/features.json` is the only source of a `true`** |
| Resolution + precedence | `backend/feature_flags.py:683-691` `_compute_flags`; JSON loader `:644-661`; env loader `:664-680` | defaults → `config/features.json` → `FTF_FLAGS` |
| Process cache | `backend/feature_flags.py:641-642`, `flags_dict()` `:694-705`, `reload()` `:708-713` | computed once per process |
| Client exposure | `backend/server.py:17270-17332`, response `:17329-17333` | returns `flags_dict()` **whole** — every key, including this one, is public once flipped |
| Runtime reload route | `backend/server.py:17336-17346` | `POST /api/feature-flags/reload`, `X-Cron-Secret`-guarded |
| Capture gate | `backend/accounts.py:249-259` `_email_capture_enabled()` | lazy import, swallows every exception → `False` |
| Normalizer | `backend/accounts.py:262-265` | requires `@`, lower + strip |
| The one gate line | `backend/accounts.py:302` | `email = _normalize_email(email) if _email_capture_enabled() else None` |
| Repeat-auth backfill branch | `backend/accounts.py:327-333` | `if email and not acct.email:` → write; never overwrites |
| New-identity insert | `backend/accounts.py:344-349` | `email`, `email_source=provider`, `email_consent_at=now` |
| Future capture-UI entry point | `backend/accounts.py:268-285` `set_account_email` | **zero call sites** in `backend/`, `mobile/src`, `web/` (grep, tests excluded) |
| Hash path (unflagged) | `backend/accounts.py:234-238`; identity insert `:350-354`, backfill `:317-324` | unchanged by this item |
| Schema | `backend/database.py:1372-1375`, migrations `:1845-1848` | four nullable columns, deployed, NULL in prod. **No DDL.** |
| Apple bind point | `backend/server.py:18024-18027` inside `_provider_auth_response` (`:18005`) | the single call site |
| Token verification | `backend/accounts.py:213-221` → `verify_identity_token` | signature, `iss`, `aud`, `exp` — `claims` is server-verified, never client-supplied |
| Apple route | `backend/server.py:18160-18176`; Google `:18179-18203` | Google returns **503 `not_configured`** without `GOOGLE_OAUTH_CLIENT_ID` (`:18189-18192`) |
| Mobile scopes (3 sites, no diff needed) | `SignInScreen.tsx:138-139,142,148` · `SettingsScreen.tsx:356-357,360-361` · `AppleSaveMomentSheet.tsx:50-51,54-55` | all request `AppleAuthenticationScope.EMAIL`, all forward only `cred.identityToken` |
| Deletion | `backend/accounts.py:691-716` | `accounts` row **hard-deleted**; the address dies with it |
| Export | `backend/accounts.py:806-830` | emits `tables["accounts"]` outside `_EXPORT_TABLES` (`:742-765`) |
| Policy claim §1 | `web/privacy.html:95-96` | "We never store your email address itself" |
| Policy claim §2 | `web/privacy.html:172` | "No email addresses … the Service has no email field" |
| Policy §5 / §6 / §9 / date | `web/privacy.html:198`, `:210`, `:251`, effective date `:66` | §5 and §6 accurate but silent on an address |
| Policy legal-review status | `web/privacy.html:2-8` | header TODO: *"Have a lawyer review this document (it has not had legal review)."* |
| Existing tests | `backend/tests/test_email_capture.py` | 4 tests, all monkeypatch `_email_capture_enabled` (`:39-40`) — deliberately flag-value-independent |
| `email_captured` event | `backend/analytics_taxonomy.py:105-136` `SERVER_FIRED_EVENTS` | **absent**; the name exists only at `docs/business/product/2026-07-17-email-capture-spec.md:32` |
| PII defences in analytics | `backend/analytics_ingest.py:160-168`; `backend/api_observability.py:142-146` | key denylist contains `email`; value regex strips address shapes |
| `is_private_email` | repo-wide grep | **zero hits** — Apple's relay signal is never read |
| `fleaflicker.link` | `config/features.json:66` | `false` — see [§10.6](#10-corrections-to-the-plan) |

**Two facts the plan does not carry, and both change the change list** — see
[§2.2](#22-the-three-flag-fixtures--four-files-flip-or-ci-goes-red) and
[§10.1](#10-corrections-to-the-plan).

---

## 2. The diff, site by site

Two commits, in this order. **They are not interchangeable and must not be squashed together.**

| Commit | Contents | Gate that unlocks it |
|---|---|---|
| **C-probe** | `backend/server.py` — one `log.info`. Nothing else. | Gate 0 opened (operator elects Option A) |
| **C-flip** | Everything in §2.1–§2.7. **One commit** — the flag and the policy are atomic or the item has failed. | Gates 0, 1, 2, 3 closed |

### 2.1 `config/features.json` — the flip

**Site:** `config/features.json:58`.

```
current:   "auth.email_capture": false,
intended:  "auth.email_capture": true,
```

Plus a `_comment_auth_email_capture` string key **immediately above** it (house style — see
`_comment_espn_webview` at `:59` preceding `espn.webview_capture` at `:60`), which pushes the flag
key to `:59`. Required clauses, all five, none optional:

1. What ON does: the Apple/Google identity-token `email` claim is stored in plaintext on
   `accounts.email` with `email_source` and an ISO `email_consent_at`.
2. The pairing: shipped in one commit with the `web/privacy.html` §1/§2 rewrite on `<FLIP_DATE>`;
   the pairing is enforced by `test_release_flag_and_privacy_policy_ship_together`.
3. **The `FTF_FLAGS` prohibition, in both directions** — see [§3](#3-flag-flip-mechanism).
4. Rollback semantics: setting `false` stops *new* writes; it does **not** delete addresses already
   stored (the flag gates writes, not reads).
5. The Settings/onboarding capture UI is still unbuilt, so `email_source='user'` is unreachable.

*Non-issue a builder will see and misread:* `_load_from_json` (`backend/feature_flags.py:655-660`)
prints `[feature_flags] ignoring unknown key '_comment_…'` for every comment key. That is
pre-existing behaviour for the ~dozen comment keys already in the file, not a defect introduced
here.

### 2.2 The three flag fixtures — **four files flip, or CI goes red**

`plan-p1-3.md:202` says to flip `backend/tests/fixtures/flags/release.json:59` and to "leave
`profiles-on.json` / `onboarding-v2.json` alone unless their suites assert on this key (they do
not)." **They do**, transitively, and the plan's instruction produces two red tests.

| Test | Location | What it asserts |
|---|---|---|
| `test_release_flags_mirror_features_json` | `backend/tests/test_seed_ui_test_db.py:107-113` | `release.json` is an **exact mirror** of `config/features.json` (keys starting `_` stripped) |
| `test_onboarding_v2_flags_are_release_plus_the_onboarding_surface` | `backend/tests/test_seed_ui_test_db.py:790-810` | `set(release) == set(onboarding-v2)` **and** the differing-key set is exactly five pinned onboarding keys |
| `test_profiles_on_flags_turn_on_public_pages_only` | `backend/tests/test_seed_ui_test_db.py:1003-1016` | differing-key set is exactly `{"profiles.public_pages"}` |

So the flip is **four files, byte-consistent**:

| File | Line at `ab9368f` | Change |
|---|---|---|
| `config/features.json` | `:58` | `false` → `true` (+ comment key above) |
| `backend/tests/fixtures/flags/release.json` | `:59` | `false` → `true` |
| `backend/tests/fixtures/flags/profiles-on.json` | `:59` | `false` → `true` |
| `backend/tests/fixtures/flags/onboarding-v2.json` | `:59` | `false` → `true` |

`backend/tests/fixtures/flags/all-on.json` — **do not touch.** It is a partial sweep fixture
(41 keys) that does not contain `auth.email_capture` at all and has no mirror test; adding the key
would change what the sweep lights up. Precedent for deliberate omission from this file:
`backend/tests/test_outlook_route_cache.py:246-249`.

**Behavioural consequence of flipping the fixtures, stated so nobody is surprised:** the Maestro
harness and the seeder (`backend/tests/fixtures/seed_ui_test_db.py:215-222` `load_flag_set`) now run
with capture ON. This is inert in practice — no harness flow reaches a real Apple consent sheet
(`mobile/.maestro/flows/smoke/11-apple-entitlement.yaml` terminates at the native boundary), and
post-P0 the harness Apple identity is `_test_mode_identity`, whose claims contain **only `sub`**
(`ftf-p0-remediation/docs/plans/audit-p0-remediation/hld.md:611-613`). No fixture, seed profile, or
flow supplies an `email` claim, so no test address is ever written.

### 2.3 `backend/feature_flags.py` — the comment that must stop lying

**Site:** `backend/feature_flags.py:138-141` (the four comment lines above `"auth.email_capture"`
at `:142`).

Current text ends: *"Flip ONLY in the same release as the capture UI + the privacy-policy update —
the policy currently says 'no email addresses'."* After the flip **both halves are false**: the
capture UI has not shipped, and the policy no longer says that. Leaving it is the **A-33 failure
mode** (a comment that describes intent while the runtime does something else) — the exact class of
defect this audit round exists to close.

Intended replacement (placeholders in `<>` filled at build time):

```python
    # Email capture (docs/business/product/2026-07-17-email-capture-spec.md).
    # ON since <FLIP_DATE>, flipped in config/features.json in one commit with
    # the web/privacy.html §1/§2 rewrite. That pairing is enforced by
    # backend/tests/test_email_capture.py::
    #   test_release_flag_and_privacy_policy_ship_together.
    # NEVER flip this key via FTF_FLAGS or POST /api/feature-flags/reload, in
    # either direction: an env-only flip changes what we store without changing
    # what the published privacy policy says (DECISIONS.md <ID>).
    # The Settings/onboarding capture UI is still UNBUILT — set_account_email
    # (backend/accounts.py:268) has no callers, so email_source='user' is
    # unreachable; the Apple identity-token path is the only writer today.
    "auth.email_capture",
```

**No `FLAG_KEYS` entry is added or removed.** `plan-p1-9.md:609` lists P1-3 among items that "add
flags to the same list" — that is wrong; P1-3 edits a comment only. (`HLD-p1.md:201` has it right.)

### 2.4 `web/privacy.html` — sites only; **the copy is not this LLD's to write**

Gate 2 (`PV-3`, `HLD-p1.md:465`) owns the words. This LLD specifies **where** the edit lands and
**what must be true of it**, and deliberately drafts no sentence. The file's own header
(`web/privacy.html:2-8`) records that the document **has never had legal review**; this is the first
change to it that *expands* a collection claim rather than narrowing one.

| Site | Line(s) at `ab9368f` | What must change |
|---|---|---|
| §1 "Information we collect", Sign-in identity bullet | `web/privacy.html:90-99`, retired clause at `:95-96` | The clause "We never store your email address itself" cannot survive. Whatever replaces it must cover: that an address is stored when the provider shares one; that "Hide My Email" yields an Apple private-relay proxy stored the same way; that the SHA-256 hash is also retained. |
| §2 "Information we do NOT collect" | `web/privacy.html:172` | The bullet as written asserts both "No email addresses" **and** "the Service has no email field". Both are retired. Phone numbers / payment information / no billing / no IAP remain true. **Also see the `fleaflicker.link` note below.** |
| §5 "Data retention" | `web/privacy.html:198-208` | Gains a retention statement. The verified truth: indefinite while the account exists, no TTL, no reaper, deleted with the account. |
| §6 "Deletion and your choices" | `web/privacy.html:210-234` | The deletion enumeration (`:212-227`) does not name an email address; it should. Export (`:228-230`) already covers it generically — see [§6](#6-deletion-export-retention--as-it-already-stands). **Gate 3 (PV-6) forbids promising an unsubscribe or a partial removal — neither exists.** |
| Effective date | `web/privacy.html:66` | `Effective date: July 19, 2026` → flip date. §9 (`:251-255`) already promises this. |
| Header provenance comment | `web/privacy.html:2-8` | Append a dated line recording the §1/§2/§5/§6 re-sync to `auth.email_capture=true`, **and whether legal review happened** (Gate 2's outcome, either way). Do not delete the standing TODO. |

**Carried forward for the reviewer, not scope for this item:** `web/privacy.html:172`'s "the
Service has no email field" is *already* inaccurate in a second, independent way. Fleaflicker league
discovery collects a user-typed Fleaflicker account email —
`mobile/src/components/PlatformLinkSheet.tsx:55` (state), `:147-157` (`findByEmail`), `:430-442`
(the UI), `mobile/src/api/platformLink.ts:221-227` → `POST /api/fleaflicker/discover`
(`backend/server.py:20964-20977`) → `backend/fleaflicker_service.py:125-133`. It is **never
stored**. The sentence is true today only because `fleaflicker.link` is `false`
(`config/features.json:66`); turning that flag on makes the same sentence false a second way. **This
is context for the Gate-2 reviewer while the file is open — one §2 rewrite can close both. It is
not a licence to widen P1-3's scope into the Fleaflicker surface.**

Every inbound link to the policy, so the reviewer knows the blast radius:
`mobile/src/screens/SignInScreen.tsx:557`, `SettingsScreen.tsx:1331`,
`SleeperConnectScreen.tsx:124`, `EspnConnectScreen.tsx:279`, `web/index.html:127`,
`web/faq.html:218,225`, and the App Store Connect privacy URL. `web/faq.html` makes **no**
"we don't store email" claim of its own (grep: zero `email` hits in that file), so it needs no edit.

### 2.5 `backend/tests/test_email_capture.py` — the durable enforcement

The four existing tests are **unchanged**. They monkeypatch `_email_capture_enabled` (`:39-40`), so
they are independent of the flag's real value; if any of them moves when the flag flips, something
other than the flag moved.

| New test | Asserts | Notes |
|---|---|---|
| `test_release_flag_and_privacy_policy_ship_together` | Read `config/features.json`. **If** `auth.email_capture` is `true`, `web/privacy.html` contains **neither** `"We never store your email"` **nor** `"No email addresses"`. | Repo root via `Path(__file__).resolve().parents[2]` (pattern: `backend/tests/test_seed_ui_test_db.py:109`). No fixtures, no network, no engine. **The asymmetry is the design:** flag OFF + rewritten policy passes (over-disclosure is permitted; the plan's ordering rule at `plan-p1-3.md:156` allows the policy to ship first). Flag ON + either sentence alive is red. |
| `test_delete_account_removes_email` | In-memory engine (pattern `test_email_capture.py:22-31`): create an account with an email, run `delete_user_data`, assert the `accounts` row is gone. | Pins `backend/accounts.py:691-716` — the mechanism that makes the policy's §6 deletion promise true. |
| `test_export_includes_account_email` | `export_user_data(...)["tables"]["accounts"][0]["email"]` is present. | Pins `backend/accounts.py:806-830` against a future refactor that folds accounts into `_EXPORT_TABLES` (`:742-765`), which omits `email`-bearing tables' handling. |

**Dropped from the plan:** `test_flag_default_is_on_in_release_fixture` (`plan-p1-3.md:276`) is
**redundant** — `test_release_flags_mirror_features_json`
(`backend/tests/test_seed_ui_test_db.py:107-113`) already pins the release fixture, and does so more
strictly (the entire map, not one key). Adding a second, weaker guard on the same invariant is
duplicate coverage.

*Known weakness of the pairing test, recorded rather than fixed:* it is a **negative** assertion, so
a Gate-2 rewrite that removes both sentences but says nothing about capture would pass. Closing that
would need a positive marker in the file (e.g. a stable HTML comment token the test greps for) —
**an addition beyond the plan, not adopted here.** If the operator wants it, it is a one-line test
change plus one HTML comment, and it does not constrain the legal copy in any way.

### 2.6 Docs

| Doc | Site | Change |
|---|---|---|
| `docs/config-reference.md` | `:155` (`auth.email_capture` row) | Default column `false` → `true`. Body: what it now gates as *shipped fact*; the policy pairing as history, not obligation; the `FTF_FLAGS` prohibition; that the Settings capture UI remains unbuilt. The row currently ends "Flip only in the same release as the capture UI + `web/privacy.html` update — the policy currently states no email addresses are stored", which after the flip is false twice over. |
| `docs/data-dictionary.md` | `:814-817` (`accounts` email columns) | `:814` — delete "**dark behind `auth.email_capture` (default off)**" and "NULL until the flag + capture UI + privacy-policy flip ship together". State: populated from the server-verified Apple/Google identity-token `email` claim at sign-in; private-relay addresses stored indistinguishably, identifiable only by the `@privaterelay.appleid.com` suffix. `:815` — **the documented domain is wrong**: `find_or_create_account` writes `email_source=provider` (`backend/accounts.py:347`), so the domain is `'apple' \| 'google' \| 'user'`, and `'user'` is the *unreachable* one today (`set_account_email` has no callers) while `'google'` is unreachable for a different reason (`backend/server.py:18189-18192` returns 503 without `GOOGLE_OAUTH_CLIENT_ID`). `:817` — record that `email_unsubscribed_at` **has no writer anywhere**. |
| `docs/runbook.md` | `:355` (step 3 of § *Sign in with Apple — App Store Connect / Apple Developer setup*, `:349-357`) | The line currently instructs the reader to keep the hash-only posture: "we store only a SHA-256 `email_hash`, never the raw email; keep it that way or amend the policy." The policy *was* amended — say so, dated. Add the App Store Connect **Contact Info → Email Address** (linked to user; App Functionality + Developer Communications) declaration as a submission-time obligation. **There is no generic "pre-submission checklist" section in this runbook** (see [§10.4](#10-corrections-to-the-plan)); `:349-357` is the correct and only home. |
| `docs/business/product/2026-07-17-email-capture-spec.md` | append | Dated status block. Shipped: schema, Apple bind path, flag, policy. Not shipped: Settings/onboarding UI, `email_captured` (deferred, AN-6), unsubscribe writer, any send path. Plus the Gate-0 finding, which either confirms or retires the spec's own claim at `:7` ("Apple shares the email once, on first authorization only … Existing Apple users **cannot be backfilled server-side**") — the origin of the audit's urgency framing. Also correct `:22` in passing if the status block touches it: deletion does **not** null `email`/`email_source`, it hard-deletes the row. |
| `docs/api-reference.md` | — | **n/a.** No route added, renamed, removed, or contract-changed. `GET /api/feature-flags` returns a different *value* for an existing key in an undocumented-per-key map. |
| `docs/architecture.md`, `living-memory/HLD.md`, `living-memory/LLD.md`, `docs/cross-client-invariants.md`, `docs/glossary.md`, `docs/design/*` | — | **n/a**, reasons as enumerated in `scope-p1-3.md:99-120`; re-verified: same call graph, same tables, no shared constant, no new domain term, no component/token change. |

### 2.7 `living-memory/`

| File | Entry |
|---|---|
| `CHANGELOG.md` | Dated H2: capture live + policy amended, in one commit; the Gate-0 result; the four-file flag flip. |
| `DECISIONS.md` | Next free ID **read at write time** (`HLD-p1.md:261-271`). Three decisions: (a) flag + policy ship in one commit and `FTF_FLAGS`/`/reload` are prohibited for this key in both directions; (b) relay-ness is derived from the `@privaterelay.appleid.com` suffix rather than modelled as a new `email_source` value or an `is_private_email` column; (c) `email_captured` deferred to the capture-UI build (AN-6). |
| `TEST_LEDGER.md` | Tier-4 declaration + rationale + pytest result + SHA. **No `qa/sim-runs/last-sim-run.json` write** — tier 4 requires no sim run, and writing a record for a run that did not happen is worse than writing nothing. |
| `GOTCHAS.md` | **Conditional** — only if Gate 0 shows the Apple JWT behaving differently from the spec's documented expectation. That is precisely a >30-minute quirk a future session would otherwise re-derive. |

### 2.8 Files deliberately NOT touched

`backend/accounts.py` · `backend/database.py` · `backend/analytics_taxonomy.py` ·
`backend/analytics_queries.py` · anything under `mobile/src` · anything under `mobile/.maestro` ·
`web/js/app.js` · `web/faq.html` · `backend/server.py` **in C-flip** (it is touched only by C-probe;
see [§4](#4-gate-0-probe)).

---

## 3. Flag-flip mechanism

### 3.1 How the value actually resolves

```
DEFAULT_FLAGS (all False, feature_flags.py:619)
  → config/features.json        (_load_from_json,  :644-661)
  → FTF_FLAGS env var           (_load_from_env,   :664-680)
  = _compute_flags()            (:683-691) → cached in _flags_cache (:642)
```

Read path: `accounts._email_capture_enabled()` (`backend/accounts.py:249-259`) lazily imports
`is_enabled` and swallows every exception to `False`. A flags outage therefore degrades to
hash-only capture, never to a sign-in failure — that fail-safe is pre-existing and this item does
not change it.

Because `DEFAULT_FLAGS` is all-False, **`config/features.json` is the only place a `true` can come
from short of the env var.** The flip is a one-character change to that file, and the cache means it
takes effect on process start — i.e. on the Render deploy of the same commit.

### 3.2 The atomicity argument

Both truth-surfaces ship from the same Render push: the backend process reads
`config/features.json`, and Flask serves `web/privacy.html` from `static/`
(`backend/server.py:8059-8061`, the App Store Connect privacy URL). **A single commit is therefore
atomic in deploy terms.** Two mechanisms can break that atomicity, and both are closed by rule
rather than by code:

- **`FTF_FLAGS`** (`backend/feature_flags.py:664-680`) — a Render environment-variable change flips
  the flag with **no code deploy, no diff, no review, no CI**. That is capture ON while the old
  policy is still being served: the exact accident the pairing exists to prevent.
- **`POST /api/feature-flags/reload`** (`backend/server.py:17336-17346`) — re-reads *both* sources
  at runtime. Harmless when the deployed commit is the paired one; it is the delivery mechanism that
  makes an env override take effect without a restart.

### 3.3 The hard constraint

> **`auth.email_capture` is flipped through `config/features.json`, in the paired commit, and
> through nothing else — in either direction.** `FTF_FLAGS` is prohibited for this key. So is using
> `POST /api/feature-flags/reload` to activate an env override of it.

This is `PV-2` / Gate 1 Option A with Option B explicitly forbidden (`HLD-p1.md:464`,
`plan-p1-3.md:337`, `scope-p1-3.md:64`). It is a **deliberate surrender of the deploy-free lever**:
this repo's standing gotcha is that Render ignores `render.yaml` `envVars`
(`docs/runbook.md:479`), so a real env flip is a manual console action — one click, no reviewer, no
record. Rollback for this item is therefore a commit, not a console click
(see [PRD §Rollback](PRD-p1-3.md)). The prohibition is recorded in `DECISIONS.md`, in the
`config/features.json` comment, in the `feature_flags.py` comment, and in `docs/config-reference.md`
— four places, because the lever is one click away and nothing in the code prevents it.

**Ordering rule (unchanged from the plan, restated as a rule):** the policy may ship *before*
capture — describing data you do not yet hold is over-disclosure, not a breach. Capture may
**never** ship before the policy. Same commit satisfies both, which is why it is the specified
shape.

---

## 4. Gate-0 probe

The whole purpose: measure the audit's urgency claim before anyone pays for a rushed legal review
(`PV-1`, `HLD-p1.md:463`). The claim under test — "Apple shares the address on first authorization
only, so existing users can't be backfilled" — traces to
`docs/business/product/2026-07-17-email-capture-spec.md:7`, and **the code disagrees with its
premise**: FTF never reads `ASAuthorizationAppleIDCredential.email` (the genuinely first-auth-only
native property); it reads the `email` claim from the server-verified identity-token JWT
(`backend/server.py:18025`), and `backend/accounts.py:327-333` is a repeat-auth backfill branch with
a test pinning it (`test_backfill_fills_missing_but_never_overwrites`).

### 4.1 Site

**After** the `find_or_create_account` call, not before it. `plan-p1-3.md:196` places the log line
at `server.py:18021`, where the answer is not yet computable: "is this identity new" is only known
from the returned `acct["created"]`. Intended insertion is between the call and
`sess = _account_session()`:

```
backend/server.py
:18024-18027   acct = _accounts.find_or_create_account(...)        (unchanged)
:18028         ← INSERT the probe here
:18028         sess = _account_session()                            (shifts to :18029)
```

### 4.2 The line

```python
    # GATE-0 PROBE (P1-3, temporary). Answers: does the Apple identity-token
    # JWT carry an `email` claim on REPEAT authorizations? No address, no
    # hash, no sub, no account_id — three booleans and a provider name.
    log.info("EMAIL-CLAIM-PROBE provider=%s new_identity=%s has_email_claim=%s",
             provider, acct["created"], bool(claims.get("email")))
```

`log` is the module logger `logging.getLogger("trade_finder")` (`backend/server.py:55`). The
grep-able uppercase tag follows the house convention already used for `AUTH-GRACE`
(`backend/server.py:2386-2388`), which `docs/runbook.md` § *Verified-session grace monitoring*
teaches operators to grep.

**What it must never contain:** the address, the hash, `sub`, `account_id`, or anything else
correlatable to a person. `acct["created"]` is the repeat-vs-new discriminator and is sufficient.

### 4.3 Reading it

Render logs → `grep EMAIL-CLAIM-PROBE`.

| Observation | Conclusion |
|---|---|
| Any `new_identity=False has_email_claim=True` | The JWT **does** carry the claim on repeat auths. Existing Apple users backfill themselves on next launch via `accounts.py:327-333`. The "permanently lost reach" framing dissolves; Gate 2 can proceed at a considered pace. |
| Only `new_identity=True has_email_claim=True`, with several `new_identity=False has_email_claim=False` | The spec's premise holds. Urgency is real for the existing-user cohort — but note the cohort is small and the reach argument should be sized against it, not asserted. |
| `new_identity=True has_email_claim=False` | A separate finding: the scope request is not yielding the claim at all. That would make the whole item inert and **stops the build** rather than being patched around. |

**Statistical honesty:** the production user count is small (`PR-4`, `HLD-p1.md:443`, cites 16
users). A handful of organic repeat sign-ins is weak evidence for a null result. The deterministic
version is the operator's own device: sign out, re-authenticate the same Apple ID, read the line.
That is `plan-p1-3.md:283` test 7 and it is the recommended way to close Gate 0 — organic log
watching is the supplement, not the measurement.

### 4.4 Lifecycle and sequencing — the part neither the plan nor the HLD states

1. **The probe is a `backend/server.py` change.** `plan-p1-3.md:312` and `HLD-p1.md:200` both say
   P1-3 touches "zero `server.py` lines" in the recommended lane. That is true of **C-flip** and
   false of **C-probe**. See [§10.3](#10-corrections-to-the-plan).
2. **It lands inside `_provider_auth_response`.** P0's W1-BE commit 4 edits the *adjacent* route
   function `auth_apple` (`backend/server.py:18160-18176`) and adds `_test_mode_identity`
   (`ftf-p0-remediation/.../hld.md:343`, `:608-617`). Different function, ~135 lines apart — but
   **P0's HLD gives `server.py` to W1-BE for the whole P0 build.** If the probe is to land while P0
   is in flight, the P0 `server.py` owner must be told, or the probe hunk is lost in a rebase with
   no test to catch it (nothing asserts a log line).
3. **Recommended sequencing:** land C-probe on `main` as its own tiny commit — tier 4, backend-only,
   no flag, no schema, no route — **and notify the P0 `server.py` owner if P0 has not yet merged.**
   The alternative (wait for P0) is safe but spends the very days Gate 0 exists to inform.
4. **Removal.** Not specified by the plan. Recommendation: **keep the line through the flip**, because
   post-flip verification (`plan-p1-3.md:284` test 8) reads the same signal, then remove it in a
   follow-up commit once the spec's status block records the finding. Keeping it forever is one
   `log.info` per authentication — cheap, but it is a diagnostic, not telemetry. **Builder's call,
   recorded either way in the spec status block.**

---

## 5. Data flow — JWT claim to column

```
Apple consent sheet
  │  scope EMAIL requested at:
  │    mobile/src/screens/SignInScreen.tsx:138-139
  │    mobile/src/screens/SettingsScreen.tsx:356-357
  │    mobile/src/components/AppleSaveMomentSheet.tsx:50-51
  ▼
cred.identityToken  ── the ONLY field forwarded (SignInScreen.tsx:142,148;
  │                     SettingsScreen.tsx:360-361; AppleSaveMomentSheet.tsx:54-55)
  │                     the client never sees, holds, or sends an address
  ▼
POST /api/auth/apple                              backend/server.py:18160-18176
  │  gate: is_enabled("auth.accounts")  :18164    (true — config/features.json:56)
  ▼
accounts.verify_apple_token(token)                backend/accounts.py:213-221
  │  → verify_identity_token: JWKS signature, iss, aud, exp
  │  → claims  (SERVER-VERIFIED; not a client-supplied field)
  ▼
_provider_auth_response("apple", claims)          backend/server.py:18005
  │  :18021-18023  sub guard → 401 missing_sub
  │  [C-probe log line sits here, §4.1]
  ▼
find_or_create_account(provider, sub,             backend/server.py:18024-18027
        hash_email(claims["email"]),                   → accounts.py:288
        email=claims["email"])
  │
  ├─ :302  THE GATE
  │        email = _normalize_email(email) if _email_capture_enabled() else None
  │        _email_capture_enabled  :249-259  → is_enabled("auth.email_capture")
  │        _normalize_email        :262-265  → requires "@", lower, strip
  │
  ├─ EXISTING identity (:307-341)
  │    ├─ :317-324  linked_identities.email_hash backfill — UNFLAGGED, unchanged
  │    └─ :327-333  if email and not acct.email:
  │                   accounts.email = email
  │                   accounts.email_source = provider
  │                   accounts.email_consent_at = now
  │                 → never overwrites an address already on the row
  │
  └─ NEW identity (:342-357)
       :344-349  INSERT accounts(email, email_source=provider,
                                 email_consent_at=now)   [all NULL when the flag is off]
       :350-354  INSERT linked_identities(email_hash)     [flag-independent]
```

Facts that fall out of this flow and belong in the record:

- **No mobile diff is required or made.** All three call sites already request the EMAIL scope and
  already forward only the token. The flag changes server behaviour only.
- **`email_source` is written as `provider`** (`accounts.py:347` and `:331`), so its true value
  domain is `'apple' | 'google' | 'user'`. `'google'` is unreachable while
  `GOOGLE_OAUTH_CLIENT_ID` is unset (503 at `server.py:18189-18192`); `'user'` is unreachable while
  `set_account_email` has no callers. The data dictionary claims `'apple' | 'user'` — corrected in
  [§2.6](#26-docs).
- **Apple private relay is indistinguishable at the column.** `claims["email"]` is either a real
  address or an `@privaterelay.appleid.com` proxy depending on the user's "Hide My Email" choice;
  `_normalize_email` accepts both identically and Apple's `is_private_email` claim is never read
  (grep: zero hits). **By decision, relay-ness is derived from the address suffix at query time** —
  no new enum value, no new column, no migration. Operational consequence for whoever ships the
  first send: mail to a relay is dropped unless the sending domain is registered in Apple Developer
  → *Sign in with Apple for Email Communication* with SPF/DKIM. No such domain, sender, or send path
  exists (`plan-p1-3.md:84-86`, re-verified: zero hits for `smtp|sendgrid|mailgun|postmark|ses|resend`
  across `backend/`, `requirements*.txt`, `mobile/package.json`).
- **The hash keeps flowing regardless.** `hash_email` (`accounts.py:234-238`) is unflagged;
  `linked_identities.email_hash` (`backend/database.py:1383`) is written on both paths. The flip
  adds a column, it does not replace one.
- **The Sleeper-username majority path is untouched.** A username-only session has no `accounts`
  row at all, so the blast radius of the flip is exactly "users who sign in with Apple".
- **Under `FTF_TEST_MODE` (post-P0), claims carry only `sub`** — capture is structurally inert in
  the harness.

---

## 6. Deletion, export, retention — as it already stands

**No code change. Two new tests pin what the policy is about to promise.**

| Question | Verified answer | Code |
|---|---|---|
| How long is an address kept? | Indefinitely while the account exists. No TTL, no reaper, no scheduled purge. | absence of any writer/reaper — grep |
| What deletes it? | `DELETE /api/account` → `delete_user_data` resolves account ids (`accounts.py:691-700`: accounts bound via `sleeper_user_id`, **plus** the session-attached `account_id`), deletes `linked_identities` (`:702-707`) then **hard-deletes the `accounts` row** (`:708-714`). The address dies with the row — there is no nulling step and none is needed. The route is deliberately **not** flag-gated (App Store Guideline 5.1.1(v)). | `accounts.py:691-716` |
| Is it exportable? | Yes, automatically. `_EXPORT_TABLES` (`:742-765`) does not list `accounts`, but `export_user_data` handles the identity layer separately at `:806-830` and emits `tables["accounts"]` — full rows, so the plaintext address is in the GDPR archive. Route `GET /api/account/export`, flag `account.data_export` = `true` (`config/features.json:127`), and it passes `account_id` so account-only users are covered. | `accounts.py:774-832` |
| Can a user remove **only** the address, keeping the account? | **No.** No route, no UI, no writer. `email_unsubscribed_at` (`database.py:1375`) is declared and written by nothing. | grep |
| Does it leak into analytics or observability? | No. `analytics_ingest.py:160-168` denylists prop keys containing `email` and regex-strips address-shaped values; `api_observability.py:142-146` redacts `email`. Nothing puts an address in a prop. **That is the safety net, not the design** — the design is that no address ever enters a prop. | as cited |
| Encryption at rest? | None. Plaintext in SQLite on Render, alongside Fernet-encrypted Sleeper tokens. `web/privacy.html:236-243` already states the beta-service security posture honestly. A separate decision, not this item's. | `privacy.html:236-243` |

**Gate 3 (`PV-6`) consumes this table.** The policy must disclose exactly these facts. It must not
promise an unsubscribe, a partial removal, or a retention limit, because none of the three exists in
the code on the day it publishes.

---

## 7. Deferred by decision

Recorded as decisions with their reasons, so they do not read later as omissions.

| Deferred | Decision + reason | Owner |
|---|---|---|
| **`email_captured` analytics event** | **Deferred** (AN-6, `HLD-p1.md:480`; Gate 4 Option A, `plan-p1-3.md:369`; `scope-p1-3.md:20-28`). **This LLD adds no event and no taxonomy edit.** Four reasons, all verified: (1) in this lane the capture is a server-side side effect of signing in, not a user action — there is no moment a user chose anything; (2) the quantity is already exactly queryable from state, and more accurately than from an append-only log: `SELECT count(*), email_source FROM accounts WHERE email_consent_at IS NOT NULL`; (3) a new `SERVER_FIRED_EVENTS` name is **intent-by-default** (`analytics_queries.py:60-65` is a deny-list), so it would enter DAU/WAU/retention unless explicitly excluded — an unforced analytics decision for zero added insight; (4) `backend/analytics_taxonomy.py` is the round's most contended file with five claimants, frozen after commit **T1** (`HLD-p1.md:286-287`), so a late `email_captured` would require a **T1 amendment commit with T1's full deploy-and-verify gate**, not a drive-by edit. The event earns its place when a *user* acts — i.e. when the Settings capture field ships. | — |
| **Settings / onboarding "Add your email" field** | Out of scope; owned by the onboarding-conversion stream (`docs/plans/onboarding-conversion/`), which owns prompt cadence and snooze patterns (`2026-07-17-email-capture-spec.md:31`). `set_account_email` is already built and waiting. **This is the only path that reaches Sleeper-username-only users** — the majority. This lane does not close the retention gap; it stops the bleeding for the Apple cohort. **Dependency worth stating in both directions:** `set_account_email` is itself flag-gated (`accounts.py:276`), so if that UI ships before this flag flips, the field appears to work and stores nothing. | onboarding stream / `/eng-mobile` |
| **Any send path** (SMTP/SES/relay-domain registration) | Nothing to send and no list yet. Registering the Apple relay domain is a prerequisite of the *first send*, not of capture. | `/mkt-lifecycle` |
| **Unsubscribe route / `email_unsubscribed_at` writer** | The CAN-SPAM obligation attaches to sending, not storing. Build it with the first send. Until then the policy must not promise it (Gate 3). | `/mkt-lifecycle` |
| **Encryption at rest for `accounts.email`** | Its own decision with its own blast radius; not created by this item and not resolved by it. | operator |

---

## 8. Test matrix

**Automated — the whole CI surface.**

| # | Test | Type | Pins |
|---|---|---|---|
| 1 | The four existing `test_email_capture.py` tests | unchanged | Movement means something other than the flag moved |
| 2 | `test_release_flag_and_privacy_policy_ship_together` | new | The flag↔policy pairing, forever |
| 3 | `test_delete_account_removes_email` | new | The §6 deletion promise |
| 4 | `test_export_includes_account_email` | new | The §6 export promise |
| 5 | `test_release_flags_mirror_features_json` (`test_seed_ui_test_db.py:107`) | existing, must stay green | The four-file flip stayed consistent |
| 6 | `test_onboarding_v2_flags_are_release_plus_the_onboarding_surface` (`:790`) + `test_profiles_on_flags_turn_on_public_pages_only` (`:1003`) | existing, must stay green | The derived fixtures were flipped too |
| 7 | `pytest backend/tests/` in full | regression sweep | The flag now resolves **true** in any test that does not monkeypatch it — `test_accounts.py`, `test_account_first.py` and (post-P0) `test_account_only_harness.py` in particular |
| 8 | `npx tsc --noEmit` | unchanged | No TS is touched; run it anyway per the ship gate |

**Manual / operational** (owned by the PRD's gates; listed here for completeness):
Gate-0 probe read (deterministic operator re-auth + organic log watch) · post-flip row inspection
(`email`, `email_source='apple'`, `email_consent_at` stamped) · repeat-auth backfill observed or
not, per Gate 0 · "Hide My Email" path stores an `@privaterelay.appleid.com` value and nothing
downstream chokes · `/privacy` loaded on the deployed URL and §1/§2/§5/§6 read **end to end** for
internal contradictions (the sections cross-reference each other; a partial edit reads worse than no
edit) · Sleeper-username sign-in leaves no `accounts` row and therefore no address.

**Not tested, by design:** any send path (none exists), unsubscribe (no writer), the Settings
capture field (not built).

---

## 9. Re-verify after P0 merge

Run **before the first edit**, per `HLD-p1.md` §G. **A row that comes back "the premise no longer
holds" stops the build and returns the item to planning — it is not patched around at the keyboard.**
Answer each in writing in `scope-p1-3.md`.

### 9.1 From §G.0 — applies to every item (`HLD-p1.md:544-554`)

- [ ] `git fetch origin && git rev-parse origin/main` — record the sha in the scope block.
- [ ] Confirm the P0 commits are present (P0-1, -2, -3, -5, -6, -7, -8/9).
- [ ] Rebase; resolve nothing blind.
- [ ] **Re-read `DECISIONS.md`, `GOTCHAS.md`, `MISTAKES.md`, `OPEN_QUESTIONS.md` for the next free
      IDs.** P1-3 allocates **last** (`HLD-p1.md:271`). Do not use any ID printed in the plan.
- [ ] Re-grep every `file:line` this LLD cites.
- [ ] Confirm `mobile/node_modules` is still symlinked. **Never run `npm install`.**

### 9.2 From §G.8 — P1-3's own rows (`HLD-p1.md:624-631`)

- [ ] **Gate 0's probe result is recorded**, or the operator has knowingly chosen Option B.
- [ ] `config/features.json:58` — `auth.email_capture` still `false` and still at that key.
      **P1-9 (Wave B) edits this file.** Re-locate by content.
- [ ] `backend/feature_flags.py:138-141` — re-locate the comment block; other items edit this file.
- [ ] `web/privacy.html` — `:90-99`, `:172`, `:198-208`, `:210-234` still carry the sentences the
      change list retires, and the header TODO at `:2-8` is unchanged.
- [ ] `fleaflicker.link` still `false` (`config/features.json:66`) — if it flipped, `:172` is
      already false a second way and Gate 2's reviewer must be told before the rewrite, not after.
- [ ] **If AN-6 / Gate 4 = Option B:** re-read `backend/server.py:18005-18075` in full; the event
      must fire **after** the `users` row exists (`record_event`, `backend/database.py:2592`, bumps
      denorm columns on `users` in the same transaction), and the registration **must go into a T1
      amendment commit** carrying T1's deploy-and-verify gate — `analytics_taxonomy.py` is frozen
      after T1 (`HLD-p1.md:286-287`).

### 9.3 Rows this LLD adds (not in §G.8)

- [ ] **The three derived flag fixtures.** Re-confirm `profiles-on.json` and `onboarding-v2.json`
      still differ from `release.json` only in their pinned key sets
      (`test_seed_ui_test_db.py:790-810`, `:1003-1016`), and that `release.json` still exact-mirrors
      `config/features.json` (`:107-113`). If P1-9 added `notif.trade_found`, all four files already
      carry it — confirm before flipping, and flip **all four**. See [§2.2](#22-the-three-flag-fixtures--four-files-flip-or-ci-goes-red).
- [ ] **Wave C is gone.** `D-P1-01` drops P1-11 from the round (`DECISIONS-p1.md:18-61`), so
      `HLD-p1.md`'s serialization for `config/features.json` / `backend/feature_flags.py`
      (`:201-202`: "P1-9 → P1-11 → P1-3") loses its middle term: the only P1 writer ahead of P1-3 on
      those files is **P1-9 (Wave B)**. `HLD-p1.md` §G.7 and §B Wave C no longer apply.
- [ ] **`_provider_auth_response` is intact.** Re-read `backend/server.py:18005-18075` and confirm
      the `find_or_create_account` call still reads `email=claims.get("email")` and that P0 did not
      move the gate. Expected: unchanged — see [§10.3](#10-corrections-to-the-plan). If P0 *did*
      restructure it, C-probe's insertion point and the Option-B emit site both move.
- [ ] **The harness identity seam exists and carries no email.** Confirm `_test_mode_identity` (P0
      W1-BE commit 4, `ftf-p0-remediation/.../hld.md:343`) returns `{"sub": …}` only. If it ever
      grows an `email` key, flipping the fixture flags starts writing addresses in harness runs.
- [ ] **`docs/runbook.md:355`** — re-locate; P0 also edits this file (`hld.md:714`).
- [ ] **`docs/config-reference.md:155` / `docs/data-dictionary.md:814-817`** — re-locate; P1-9 adds
      rows to `config-reference.md`, and P0-1 edits `database.py`.

---

## 10. Corrections to the plan

Where `plan-p1-3.md`, `scope-p1-3.md`, `HLD-p1.md`, or a sibling plan is wrong against the code at
`ab9368f`. Each was verified, not inferred.

### 10.1 The flag flip is **four** files, not two — and the plan's instruction produces a red build

`plan-p1-3.md:202` and `scope-p1-3.md:61` say to flip `config/features.json` and
`release.json`, and explicitly to leave `profiles-on.json` / `onboarding-v2.json` alone "unless
their suites assert on this key (they do not)". **They do.**
`test_onboarding_v2_flags_are_release_plus_the_onboarding_surface`
(`backend/tests/test_seed_ui_test_db.py:790-810`) and
`test_profiles_on_flags_turn_on_public_pages_only` (`:1003-1016`) assert the **exact differing-key
set** between each derived fixture and `release.json`. Flipping `release.json` alone adds
`auth.email_capture` to both differing sets and turns both tests red. All four files flip together.
Detail in [§2.2](#22-the-three-flag-fixtures--four-files-flip-or-ci-goes-red).

### 10.2 One proposed test is redundant

`plan-p1-3.md:276` / `scope-p1-3.md:92` propose `test_flag_default_is_on_in_release_fixture`.
`test_release_flags_mirror_features_json` (`backend/tests/test_seed_ui_test_db.py:107-113`) already
pins `release.json` to `config/features.json` in full. Dropped as duplicate coverage.

### 10.3 **P0-5 does not restructure `_provider_auth_response`**

`plan-p1-3.md:312`, `scope-p1-3.md:27`, and `HLD-p1.md` (§P-2 `:59`, §A.4 `:200`, §G.8 `:630`, §E
AN-6 `:480`) all state that P0-5 restructures `server.py:_provider_auth_response` /
`_mint_account_only_session`, and use that as an argument for deferring the event. **The conclusion
is right; the premise is not.** `ftf-p0-remediation/docs/plans/audit-p0-remediation/lld-p0-5.md:69`
lists "edit `backend/server.py`" under **must not** — P0-5's own change list (`:43-52`) is
`testRouteEntry.ts`, `RootNav.tsx`, `SignInScreen.tsx`, `LeaguePickerScreen.tsx`,
`LinkSleeperSheet.tsx` (new), `SettingsScreen.tsx`, and two Maestro files. The only server-side P0
work near this code is W1-BE commit 4 — `_test_mode_identity()` plus a branch in **`auth_apple`**
(`backend/server.py:18160-18176`) — and P0's HLD states outright that "`_provider_auth_response`,
`_mint_account_only_session` … is the real production path, **unmodified**"
(`hld.md:616-617`). No P0 item edits `backend/accounts.py`'s capture code either (grep across the
P0 LLDs: no hits).

**Why it still matters even though the deferral stands:** the re-verification row in `HLD-p1.md`
§G.8 asks the builder to re-read a function P0 will not have moved, which is cheap; but the same
mistaken premise makes the *probe*'s sequencing look safer than it is (the real contention is P0's
whole-file hold on `server.py`, not a function rewrite). [§4.4](#44-lifecycle-and-sequencing--the-part-neither-the-plan-nor-the-hld-states)
states the real constraint.

### 10.4 The probe is a `server.py` change, and its line is in the wrong place

- `plan-p1-3.md:312` / `HLD-p1.md:200`: "In the recommended lane P1-3 touches **zero** `server.py`
  lines." True of **C-flip**; **false of C-probe**, which the same plan makes step 0 of its own
  change list (`plan-p1-3.md:196`). The lane touches `server.py` exactly once, temporarily.
- `plan-p1-3.md:196` puts the log line at `server.py:18021`. At that point `acct` does not exist, so
  "whether this `sub` is new" is not computable. The probe must sit **after** the
  `find_or_create_account` call and read `acct["created"]` — [§4.1](#41-site).

### 10.5 `docs/runbook.md` has no "pre-submission checklist" to add to

`plan-p1-3.md:206` and `scope-p1-3.md:117` say to "add the App Store Connect label action … to the
pre-submission checklist." No such section exists. The runbook's section list (`:8-55`) contains no
release/submission checklist; the only App Store Connect content is § *Sign in with Apple — App
Store Connect / Apple Developer setup* at `:349-357`, whose step 3 (`:355`) is exactly the stale
line this item must amend. That section is the correct home, and the amendment and the addition are
the same edit.

### 10.6 Two smaller factual drifts

- **`email_source`'s domain.** `docs/data-dictionary.md:815` documents `'apple' | 'user'`.
  `find_or_create_account` writes `email_source=provider` (`accounts.py:331`, `:347`), so `'google'`
  is a fourth possibility structurally (unreachable today: 503 without `GOOGLE_OAUTH_CLIENT_ID`,
  `server.py:18189-18192`). Corrected in [§2.6](#26-docs).
- **`plan-p1-9.md:609`** lists P1-3 among the items adding a key to `feature_flags.py`'s
  `FLAG_KEYS`. P1-3 adds no key; it edits a comment (`HLD-p1.md:201` has this right). Harmless, but
  it inflates the expected conflict surface on that file.
- **The 2026-07-17 spec is wrong about deletion.** `2026-07-17-email-capture-spec.md:22` says
  account deletion "**also nulls** `email`/`email_source`". It does not — the whole `accounts` row
  is hard-deleted (`accounts.py:708-714`). The outcome is stronger than the spec promised; the
  status block should correct the sentence while it is being appended to.

### 10.7 What the plan gets right and this LLD did not change

The audit-drift table (`plan-p1-3.md:120-128`) survives re-verification in full: the schema ships,
the gated code is merged and unit-tested, mobile already requests the EMAIL scope, bind time is
already where capture happens, there is genuinely no email infrastructure, and the `email_captured`
event genuinely does not exist. The engineering really is XS and the governance really is M.

---

## 11. What this LLD deliberately does not do

- **It writes no privacy-policy text, and no policy copy of any kind.** Gate 2 (`PV-3`) owns the
  words and the reviewer. This document specifies which claims can no longer stand and which facts
  must be covered — nothing more. `web/privacy.html:2-8` records that the document has never had
  legal review; that is a fact for the operator, not a licence for an agent to fill the gap.
- **It decides nothing about retention, unsubscribe, or the App Store data disclosure.** Those are
  Gates 3 and 5 (`PV-6`, `PV-7`). §6 states the code's behaviour so the decisions are made against
  facts.
- **It adds no analytics event** and no `analytics_taxonomy.py` edit — [§7](#7-deferred-by-decision).
- **It invents no design.** The additions to `plan-p1-3.md` are: the three-fixture finding, the
  probe's corrected site and lifecycle, the `email_source` domain correction, the P0-5 correction,
  and the runbook-section correction. All are corrections against the code, not new design. The one
  genuine *addition* considered — a positive marker in `privacy.html` to close the pairing test's
  false-green — is flagged in [§2.5](#25-backendteststest_email_capturepy--the-durable-enforcement)
  as **not adopted**, pending an operator or builder call.
- **It does not widen scope into `fleaflicker.link`.** That observation is carried to the Gate-2
  reviewer as context for one §2 rewrite, and nowhere else.

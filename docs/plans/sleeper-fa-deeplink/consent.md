# Direct add/drop in Sleeper (D1): the connect, consent and move flow — spec (2026-10-20)

> **What this file covers:** the product spec for decision D1. When the user taps the move, FTF performs the free-agent add, the add with a drop, or the waiver claim in Sleeper itself, using the user's connected Sleeper sign-in. The first move in each rolling 7-day window needs a ticked consent box, and the server enforces it.
>
> **Where everything else lives:**
> - **The `sleeper://` hand-off:** [prd.md](prd.md). It is the add path's fallback and still the whole send-a-trade path.
> - **The gates:** [scope.md](scope.md).
> - **The mutation shapes and the write route's implementation:** the separate D1 write spike, `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet). This file does not duplicate it. It states only what the route must do for the product (§3).
>
> **Inputs folded in on 2026-10-20** (review notes held outside the repo, cited by role and section):
> - `legal-lead` R15 (R15.1–R15.8, including R15.8's rulings on D5, D10, D11 and D12, and the final v1 and v2 consent texts) and LEG-L12;
> - `ux-lead`'s #351 consent review, K-F1 to K-F7, plus test steps K1–K7;
> - `design-lead`'s #351 consent checkbox and not-installed message review;
> - `head-product` P31, and P34 (decisions D6, D9, D10 and D11).
>
> This is a spec. It changes no code, and nothing was sent to Sleeper while writing it.

## Contents

- [1. Decisions and inputs](#1-decisions-and-inputs)
- [2. The flow: connect, then consent, then move](#2-the-flow-connect-then-consent-then-move)
- [3. What the write route must do (implemented in sleeper-fa-write)](#3-what-the-write-route-must-do-implemented-in-sleeper-fa-write)
- [4. Consent](#4-consent)
- [5. After the move](#5-after-the-move)
- [6. Analytics](#6-analytics)
- [7. Acceptance criteria (AC-19 to AC-40)](#7-acceptance-criteria-ac-19-to-ac-40)
- [8. Evidence](#8-evidence)
- [9. Reviews and ship gate](#9-reviews-and-ship-gate)

## 1. Decisions and inputs

**Operator, 2026-10-20, verbatim** (relayed by the coordinator to `head-product`):

> D1: "Yes. With User authorization to do so. (A checkbox for the first attempt every 7 days)"

> D2: "In app message"

**What the decision means:**
- FTF makes a roster move in Sleeper **only when the user starts it and confirms it in the app** (R15.2.4).
- The checkbox is needed on the first move in any rolling 7 × 24 h window, timed from the server's consent timestamp (R15.2.3).
- FTF never makes a scheduled, automatic or background move. Adding one would go back to the operator as its own yes/no, with new copy.
- **D2** (an in-app message when Sleeper isn't installed) applies **only on the fallback path** ([prd.md § 4.4](prd.md#44-when-sleeper-isnt-installed-decision-d2--decided)). The main add path doesn't need the Sleeper app (`design-lead`, ux-lead's D2 row).

**What D1 does not settle:**
- **E2 stays logged.** This is the risk register's agreement-scope question (Sleeper Terms §11).
- **`platforms-pm` still owes a dated write-feature-gate pass** for the new write.
- **LEG-L12 is MUST before the add/drop build ships** (§9). `legal-lead` notes that it is not part of the launch build unless `platforms-pm` puts it there.

**Where the work lands:**

| Input | Folded into |
|---|---|
| R15.8 final copy (v1, v2) | §4.1, verbatim. This replaces the R15.1 draft |
| R15.8 rulings (D5, D10, D11, D12) | §2.2, §3, §4.1–§4.3 |
| R15.2 mechanics | §4.2 and §4.4 |
| R15.3 evidence | §4.3: two append-only tables |
| R15.4–R15.5 privacy and terms | scope.md §4: a docs/legal dependency row |
| R15.6 | no label change; scope.md §1 |
| R15.7 | professional review [PRO], §9 |
| K-F1 to K-F7 | §2 and §5 |
| design-lead | §2 (checkbox spec, the window line, refusal pattern) and prd §4.4 (the D2 alert) |
| P31 | prd §9 and scope §5: device tests gate the **merge**, not the start of the build |
| P34 | D9: the step (§2.3). D10: the named button (§2.2), since confirmed by `legal-lead` R15.8. D11: per account (§4.2, §4.3), since confirmed by R15.8. D6: the flag turns on only under three conditions (§3, §9). The secondary button's words go to `marketing-lead`. K-F5 handed off (§5) |

## 2. The flow: connect, then consent, then move

The order is **connect → consent → move** (K-F1). The claim sheet looks the same on every visit (K-F2). The connect and consent steps appear only after a CTA tap that needs them.

A pure function, `faWriteGate({flagOn, linked, linkExpired, consentValid, ticked})` (`mobile/src/utils/faWriteGate.ts`, zero runtime imports), makes the decision so guard S17 can execute it. It returns one of `'handoff' | 'connect' | 'verify' | 'consent' | 'write' | 'write_with_consent'`. **Only the last two** call the write API.

### 2.1 Sheet states

| State at CTA tap | What the user sees | Then |
|---|---|---|
| Flag `sleeper.fa_write` off (or the route answers 404) | The sheet is in **hand-off mode**: the steps block plus the prd's **Open in Sleeper** CTA (prd §4.2) | the hand-off |
| Flag on, **no Sleeper connection** (K-F1) | A **connect step** inside the sheet: "To make the move for you, Fleeced needs your Sleeper sign-in". Buttons: **Connect**, plus the secondary **Do it in Sleeper instead** (K-F4) | **Connect** opens `SleeperConnect`, the same WebView Send in Sleeper uses (`SendInSleeperButton.tsx:215-218`) |
| Flag on, connection **expired**, or 403 `verification_required` | The same step, with **Verify** instead of **Connect**, as Send in Sleeper does (`SendInSleeperButton.tsx:271-292`) | the same |
| Connected, consent **valid** | No extra step. The CTA **is** the move | the write |
| Connected, consent **missing, lapsed or withdrawn** | A **consent step** (K-F2), described in §4.1. **Make the move** is disabled until the box is ticked. **Not now** returns to the sheet unchanged | the write, with the tick |
| User picks **Do it in Sleeper instead**, from any step or the sheet | The sheet switches to **hand-off mode**: steps block plus **Open in Sleeper**. If Sleeper isn't installed, the D2 message shows | the hand-off |

**Connect step details (K-F1):**
- **Why connect comes first.** The consent wording refers to "the Sleeper sign-in you connected", and the consent record must name the Sleeper user the moves are made as (R15.3). So the user connects before they tick.
- **Keeping the user's work.** While `SleeperConnect` is open, the sheet is hidden, not destroyed. The host screen keeps the claim target, bid and drop, using the same approach as `SendInSleeperButton.tsx:180-205` (a ref plus a check when the screen regains focus).
- **Coming back connected.** The host re-checks the link status and **re-shows the same claim sheet with the bid and drop intact**. It goes on to the consent step if one is needed. It **never performs the move automatically**: the user taps again.
- **Coming back without connecting.** If the user backs out of the WebView, they return to the same sheet, unchanged, with one chalk-dim line, "Sleeper isn't connected". The sheet still offers **Do it in Sleeper instead**. Nothing is recorded or sent.

### 2.2 The CTA is the per-move confirmation (K-F3)

**D10, no per-move dialog.** Decided by `head-product` (P34) and **confirmed by `legal-lead` (R15.8, D10)**. The named button is the per-move confirmation, and there is no separate dialog. R15.8 sets six conditions, all required:
- **(a) The button names the move.** Its label names the add and the drop: "Add {Player A}, drop {Player B}", or "Add {Player A}" when there's no drop (`design-lead`). The **league** is named on the button or directly beside it.
- **(b) The finality line.** "Final on Sleeper. Fleeced can't undo it." sits directly under the button. It is always visible and never collapsed.
- **(c) Claims.** For a claim, the waiver line and the **bid amount** sit under the button. Claims only come once v2 is live (§3, §4.1). The waiver line is R15.1's: "This places a waiver claim for {Player A} (dropping {Player B} if it clears). Sleeper processes it on its waiver schedule."
- **(d) The consent step names the move.** On the first move of a window, the consent step shows the line *"This move: {CTA label} in {League}."* above the checkbox. It is part of the final copy in §4.1. Tapping **Make the move** then confirms a named move.
- **(e) Every send needs a fresh tap.** Nothing sends after connect, after consent, or on return to the sheet without a new tap (§2.1).
- **(f) One tap is one move.** The button is disabled from the tap until the result arrives.

That tap is followed by a result line (§5). The consent copy's "You'll still confirm every move" stays true, because the named-button tap is that confirmation. This is **[PRO]** under R15.7(a).

### 2.3 Visual spec (`design-lead`)

- **Checkbox.** Chalkline has no checkbox spec yet; this is it.
  - Box: 20×20, `--r-xs`, 1.5px `--line-strong` border on `--ink-2`.
  - Checked: `--ice` border plus the `check` icon in `--ice` (stroke 1.75). Not an ice fill, so the CTA stays the only ice fill on the sheet.
  - The whole row is the tap target, at least 44pt tall. `accessibilityRole="checkbox"`, `accessibilityState={{checked}}`, with a 2px ice focus ring.
  - Label: `type.bodySm` in **chalk** (not chalk-dim). It wraps freely and is **never truncated**.
  - **Never pre-checked.** The CTA uses the Button's own disabled state, with no separate warning text.
  - `design-lead` owes a `components.md` Forms row for it.
- **Placement, D9: decided by `head-product` (P34). Consent is its own step.** R15.1's full panel doesn't fit inline, and the step shows at most once a week. The inline option is dropped.
  - Inside the step, `design-lead`'s type and placement spec applies: the box sits **directly above the primary button** (**Make the move**).
  - The label is `type.bodySm` in chalk and is never truncated.
- **Steps block.** It shows **only in hand-off mode**, never next to the checkbox (`design-lead`). This replaces the earlier "every state" wording.
- **The window line (K-F7).** Inside an active window, one chalk-dim line sits under the CTA: **"Adds authorized until {date}"**, followed by a **Turn off** link that opens the Settings control (§4.4).
- **Results** (words from `marketing-lead`, with `legal-lead` for the result lines, K-F6):
  - **In progress:** the CTA's `loading` state; the sheet stays open; double sends are blocked.
  - **Success:** the sheet body becomes a confirmation: the `check` icon in chalk, then the result lines in `title` / `body-sm`, then **Done** as the primary button. No celebration, mascot or flare.
  - **Recoverable failure** (network or 5xx): the reason plus **Try again**.
  - **Sleeper refusal** (waivers locked, a roster rule, a player no longer available): the reason in plain words, **no retry**, and a secondary **Open in Sleeper** that goes to the hand-off. Error text is `body-sm` in `--neg`, never a `--neg` fill.

### 2.4 Declining never strands the user (K-F4)

The secondary **Do it in Sleeper instead** is always on the sheet and in every step. It is the path for:
- "Not now" on the consent or connect step;
- consent withdrawn;
- the flag off;
- a refused move.

The same rule covers writes switched off under the platform risk register.

**The secondary button's words are still open.** They are `marketing-lead`'s call and are waiting on a slot with `head-bizops`. The candidates are:
- ux-lead: "Do it in Sleeper instead";
- `design-lead`: "Open in Sleeper";
- R15.8 v1 copy: "Not now" for the consent step.

"Do it in Sleeper instead" is the working label in this spec.

## 3. What the write route must do (implemented in `sleeper-fa-write`)

**Mutation shapes: none recorded in-repo.** A search on 2026-10-20 (`git grep` over `backend/`, `docs/`, `living-memory/`) found no add, add/drop or waiver-claim mutation shape. It also found no claim FAAB encoding and no way to read a player's waiver status.
- `sleeper_write.py` records only `propose_trade` and `reject_trade`.
- The pending-trades memo's Addendum §1 cites a public `__schema` dump, but quotes only the trade signatures and doesn't record the dump's URL.
- Q-016 leaves FAAB element types unresolved.
- Live introspection is stripped (`docs/feedback/items/147-trade-blocks/status.md:24-26`).

**So the spike is a precondition.** `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet) owns:
- the schema read;
- capture from Sleeper's own web client (runbook §C2);
- the route and adapter design.

Any capture or replay is a **live write that needs the operator's approval when it runs**, in a test league, with the change reversed afterwards. **Waiver claims stay refused** (`waiver_claim_unsupported`, which leads to the hand-off) until **both** of these are true, per `legal-lead` R15.8 D5:
1. the server's current consent copy is **`sleeper-roster-moves-v2`** (§4.1);
2. the spike has **captured the claim shape**.

A claim shape is never guessed, and claims never run under v1.

**Product requirements on the route** (`POST /api/league/free-agents/add`; the final name is the spike's):

- **Request body.** `{league_id, add_player_id, drop_player_id?, faab_bid?, consent?: {copy_version, locale}, attempt_id}`. `attempt_id` is a client-generated UUID, required, one per tap (`analytics-lead` F3). The server echoes it on `sleeper_fa_write_succeeded` and stores it in `platform_write_moves`.

- **Order of checks.** The route runs these in order: test-mode fail-closed (599) → `sleeper.fa_write` (404) → session and `_verified_write_denial` (`server.py:2653`) → body → credential (`sleeper_not_linked` / `sleeper_expired` / `sleeper_unconfigured`, as `server.py:19515-19524`) → **consent** (§4.2) → the pre-write public reads (roster resolved by roster, D-051) → the write → the **move record** (§4.3).
- **Consent before any Sleeper write.** A body carrying `consent: {copy_version, locale}` with the current version records the grant first, then writes. **The grant row is committed before Sleeper is called**, in the same request (`legal-lead` R15.8, "also required"). If Sleeper then rejects the move, the grant stands and the move row records the failure. Without a valid grant the route answers 409 **`consent_required`**, and nothing is sent.
- **Refusals the client must handle.** Each one is `{error, message, detail}` with `detail = message` (#428).

| Code | When | Client |
|---|---|---|
| 404 `feature_disabled` | the flag is off | hand-off mode |
| 409 `sleeper_not_linked` / `sleeper_expired`, 403 `verification_required` | no usable connection | the connect or verify step (§2.1) |
| 409 **`consent_required`** (new; adds `copy_version`) | no valid consent | the consent step |
| 422 **`roster_full_drop_required`** (new) | `open_slots` is **known** to be 0 and there is no drop. When capacity is unknown, Sleeper decides, because FTF's count includes IR and taxi (`api/league.ts:877-886`) | highlight the drop list |
| 422 `asset_not_owned` (reused, the overhaul meaning, `overhaul_service.py:44`) | the drop is no longer on the roster | refresh the drop list |
| 422 **`player_unavailable`** (new) | the add target was just rostered | "{Name} was just picked up" + refresh |
| 422 **`waiver_bid_over_budget`** (new; adds `remaining`) | bid > the server-recomputed remaining FAAB | the inline bid error (`ClaimSheet.tsx:219-224`) |
| 422 **`waiver_claim_unsupported`** (new) | a claim, while the current copy is v1 or no claim shape has been captured (R15.8 D5) | hand-off mode |
| 409 `sleeper_rejected` (reused; the credential is deleted, so consent is withdrawn, §4.4) | Sleeper refused the token | the refusal pattern, then the connect step on the next try |
| 502 `sleeper_write_failed` (reused; `detail` = Sleeper's sentence) | Sleeper refused the move | the refusal pattern (§2.3): reason, no retry, Open in Sleeper |

- **Success response.** It reports `mode` (`add` \| `claim`), `status` (`complete` \| `pending`), what was added and dropped **as Sleeper reports it** (a partial result is stated exactly), `move_id` and `attempt_id`. A Sleeper rejection or error is never a success response. It returns an error code, so the client fires only `sleeper_fa_write_failed` (F4).
- **Kill switch.** `sleeper.fa_write`, default **`false`**. It gates the write route and the two consent routes (they 404 instantly when off), and the client's direct-write UI and Settings row. It is absent from `LAUNCHED_FLAG_DEFAULTS` until it graduates. It goes into `FLAG_KEYS`, the flag fixtures and `docs/config-reference.md`. This flag is the write's deploy-free rollback lever.
  - **D6, decided by `head-product` (P34).** The flag turns on only after **all three** of: LEG-L12 is done, the P31 device tests have passed, and the `platforms-eng` spike has captured the mutation shapes. **The flip itself is the operator's.**

## 4. Consent

### 4.1 The consent step: `legal-lead` R15.8 final copy, verbatim

Shown when the user taps the button with no active consent (none yet, expired after 7 days, or withdrawn). The R15.1 draft is superseded: legal keeps it for the record and does not ship it.

**Final consent copy, v1 (adds and drops; while claims are refused)**, verbatim from R15.8:

> **Let Fleeced make roster moves in Sleeper?**
> - Fleeced will add and drop players in your Sleeper leagues for you, using the Sleeper sign-in you connected.
> - Moves are final on Sleeper. Fleeced can't undo them, and a player you drop can be picked up by another team.
> - This uses an unofficial Sleeper connection, so it could stop working at any time. *(R15.7(c) [PRO]: keep or drop)*
> - Your OK lasts 7 days. You'll still confirm every move. Turn it off any time in Settings › Leagues › Stop roster moves.
>
> *This move: {CTA label} in {League}.*
>
> ☐ **I authorize Fleeced to add and drop players in my Sleeper leagues for the next 7 days.**
>
> [Make the move] · [Not now] — Terms · Privacy

**Final consent copy, v2 (required once claims are enabled)**, verbatim from R15.8: as v1, except:
- Bullet 1: *"Fleeced will add and drop players, and place waiver claims, in your Sleeper leagues for you, using the Sleeper sign-in you connected."*
- Bullet 2: *"Moves are final on Sleeper and Fleeced can't undo them. A player you drop can be picked up by another team. A waiver claim runs on Sleeper's schedule and spends any bid you set."* If `platforms-pm` verifies it, add *"You can cancel a pending claim in Sleeper before it runs."*
- Checkbox: **"I authorize Fleeced to add and drop players and place waiver claims in my Sleeper leagues for the next 7 days."**

**Which version ships with which capability** (`legal-lead` R15.8 D5):

| Copy version | Ships with | Server's current constant |
|---|---|---|
| `sleeper-roster-moves-v1` | add and add+drop only. Claims are refused (`waiver_claim_unsupported` → hand-off) | v1 from the first ship |
| `sleeper-roster-moves-v2` | add, add+drop **and waiver claims** | switched to v2 **in the same release that enables claims**. Claims need **both** v2 and the spike's captured claim shape (§3) |

- **Moving from v1 to v2 is a copy-version bump.** Every v1 grant stops matching (§4.2, validity), so every user re-consents on their next move, under the existing lapse rules.
- **The Settings path is in v1 itself.** v1 has not shipped, so the path doesn't need a version bump (R15.8 D5).

Notes on the copy:
- **The [PRO] marker** on bullet 3 is `legal-lead`'s note, not UI text. Whether that bullet ships is R15.7(c).
- **"This move: {CTA label} in {League}."** renders the exact button label and league (D10(d), §2.2).
- **Scope, D11: per account,** decided by `head-product` P34 and **confirmed by `legal-lead` R15.8**. Consent covers every Sleeper league of the connected Sleeper user, including a league linked during the window. The league is named on every move (D10(a)).
- **"You'll still confirm every move"** stays true: the named-button tap is that confirmation (R15.8 D10).
- **Storage.** Both versions live in the repo, in `mobile/src/utils/sleeperConsentCopy.ts`, keyed by `copy_version` and `locale` (`en-US`). A version is never edited in place; changed wording means a new version (guard S22 pins both). The server's current constant is `SLEEPER_ROSTER_MOVES_CONSENT_VERSION` (guard S19).
- **Other words.** Words outside the consent step (button labels, result lines, the connect-step line) are `marketing-lead`'s. They must not contradict D10(a)–(c) or say a move can be undone (R15.8).

### 4.2 Mechanics (R15.2)

1. **Unticked by default.** Ticking it is the only way to consent. It is never pre-ticked, never bundled, and can't be skipped (guard S21).
2. **The server enforces it.** No write is sent unless the server finds an active grant for **this FTF user and this Sleeper user**. Under D11 (per account; confirmed by `legal-lead` R15.8) the grant covers every Sleeper league of that Sleeper user, including one linked during the window. Consent is **keyed by user, never by league**.
3. **Validity.** A grant is valid when all of these hold:
   - it is the latest grant for (user, `sleeper`, the current credential's `sleeper_user_id`);
   - `copy_version` equals the server's current constant;
   - no withdrawal row refers to it;
   - now < `expires_at`, where `expires_at` = `consented_at` + 7 × 24 h, from server UTC.
4. **Moves don't extend the window.** Only a new tick does. There is no reminder before it lapses.
5. **After a lapse**, the next tap shows the consent step. Nothing is ever sent without a valid grant.
6. **Re-consent is required when:**
   - the copy version changes, including the v1 → v2 bump when claims are enabled;
   - the connected Sleeper account changes;
   - Sleeper is disconnected and reconnected (§4.4).

### 4.3 Evidence: two append-only tables (R15.3)

Rows are **never edited, only added**. Neither table ever stores a token or credential (the `sleeper_write.py` rule).

**`platform_write_consents`** holds grants and withdrawals:

| Column | Notes |
|---|---|
| `consent_id` | PK, uuid |
| `kind` | `grant` \| `withdrawal` |
| `refers_to` | on a withdrawal: the `consent_id` of the grant it ends |
| `user_id` | FTF user id, indexed. Under D11, this and `platform_user_id` are the lookup key; there is no league key |
| `platform` | `'sleeper'` only. `eng-architect` may drop the column |
| `platform_user_id` | the Sleeper user the moves are made as |
| `league_scope` | Always `'all_linked'` (D11, per account, confirmed by R15.8). It is kept because R15.3 lists it |
| `copy_version`, `locale` | the exact text is in the repo under the version (§4.1) |
| `consented_at`, `expires_at` | server UTC; grants only |
| `client_platform`, `app_version` | from the `X-Device` / `X-App-Version` headers the server already reads (`server.py:2831-2849`) |
| `trigger_move_id` | grants: the move the tick was given for |
| `withdrawn_at`, `withdrawn_via` | withdrawals: `settings` \| `disconnect` \| `credential_expired` \| `credential_rejected`. There is no `account_deletion` value: under R15.8 D12 the rows are deleted with the account instead |

**`platform_write_moves`** has one row per move:

| Column | Notes |
|---|---|
| `move_id` | PK, uuid |
| `attempt_id` | the client UUID from the request (`analytics-lead` F3). Joins the `sleeper_fa_write_*` events to this row |
| `consent_id` | the grant that covered it |
| `user_id` | |
| `league_id` | |
| `add_player_ids`, `drop_player_ids` | JSON lists |
| `mode` | `add` \| `claim` |
| `faab_bid` | claims |
| `sent_at` | server UTC |
| `result` | `accepted` \| `rejected` \| `partial` \| `error` |
| `sleeper_transaction_id` | if Sleeper returns one |
| `error_code` | the §3 code on a refusal |

**Why new tables.** `git grep -n -i consent` finds only `accounts.email_consent_at` (`database.py:2474`), which is email-only, with no scope, version or history. `sleeper_credentials` (`:2374-2381`) is deleted on expiry and on refusal, and is upserted on relink. `user_events` is analytics, not an authority.

**Coverage.** Both tables join `delete_user_data` and `export_user_data` **in the same change that adds them**:
- add both names to `accounts._ADDITIONAL_PRIVATE_TABLES` (`accounts.py:652-658`), which covers deletion (`:781`) and export (`:988-992`);
- `test_account_deletion_coverage.py:48` parametrizes over that tuple;
- each table gets a `docs/data-dictionary.md` entry.

**Retention, D12: ruled by `legal-lead` (R15.8).** Consent and move records are **deleted with the account**: both tables are removed by `delete_user_data`, through `_ADDITIONAL_PRIVATE_TABLES` as above. This keeps privacy §6's deletion promise and Apple 5.1.1(v); the move itself stays in Sleeper's own history. **[PRO]:** a professional confirms that no retention duty applies. If one does, keeping a minimal record becomes a new operator decision and a policy change (H6). Export includes both tables while the account exists.

### 4.4 Withdrawal is as easy as consent (R15.2.6, K-F7)

**The Settings row** is placed by this spec, as R15 asked of `platforms-pm` (R15.2 item 6, H5c):
- **Where.** Settings › **Leagues** (`SettingsLeaguesScreen.tsx:64`), inside `PlatformDisconnectSection` (`sections/PlatformDisconnectSection.tsx:40`), directly under the Sleeper-sending connection row. It is shown when `sleeper.fa_write` is on and Sleeper is connected.
- **Status line.** Active: "Roster moves: on until {date}". None: "Roster moves: off. You'll be asked the next time you make a move."
- **Control.** **Stop roster moves**, shown only while active. One tap calls `DELETE /api/sleeper/write-consent`, which appends a `withdrawal` with `via = 'settings'`. There is no confirm dialog, because withdrawing is safe and is meant to be as easy as giving consent.
- **Notice**, using R15.2.6's copy verbatim: *"Roster moves are off. Fleeced won't add or drop players until you agree again. Moves already made stay in Sleeper."*
- **testIDs:** `settings.roster-moves.status`, `settings.roster-moves.stop`.

**The Turn off link** on the sheet's "Adds authorized until {date}" line opens this Settings row (K-F7).

**Other things that withdraw consent:**
- **Disconnecting Sleeper** (`DELETE /api/sleeper/link`, `server.py:19268-19274`).
- **Any deletion of the Sleeper credential.** That includes token expiry (`server.py:19523`) and Sleeper's refusal of the token (`:19608`). Each one appends a withdrawal with the matching `via`, so a reconnect always means re-consent (R15.2.5).
- **Account deletion** deletes the rows (§4.3).
- **A copy-version bump** stops every existing grant from matching.

Withdrawing takes effect at once and never undoes moves already made.

**Routes** (this spec's, behind `sleeper.fa_write`):
- `GET /api/sleeper/write-consent` returns `{valid, consented_at, expires_at, copy_version, league_scope}`, never a token.
- `DELETE /api/sleeper/write-consent` is the Settings withdrawal above.
- The grant itself is recorded by the write route (§3), so a consent with no move behind it is never stored.

## 5. After the move

- **K-F5, the app reflects the move.**
  - **Done** closes onto a **refreshed** Free Agents list: invalidate the `['free-agents', leagueId, *]` queries, and the Usage Trends FA query on that surface.
  - The added player no longer offers Add.
  - A waiver claim shows as **pending** for the rest of the session, from the success response. A durable pending state is a later item.
  - **The trade deck drops the dropped player at once.** The in-app roster change invalidates the affected trade cards immediately (#339 §5.1, "a change the app itself knows about"), so no deck card offers the dropped player as the user's.
  - **Handed off to `trades-pm` as I-2/U2.** The mechanism is theirs. TestFlight step 29 checks the result.
- **K-F6, say exactly what happened.**
  - The in-progress and result copy separate a **waiver claim placed** from a **player added**, as Sleeper reports it.
  - A partial result names both halves exactly.
  - Draft lines, R15.1 verbatim:
    - success: *"Done. {Player A} added, {Player B} dropped in {League}."*
    - rejection: *"Sleeper didn't accept this move, so nothing changed. Try again in Sleeper."*, used only when Sleeper reports a rejection.
  - `design-lead`'s layout pairs "Added {Name}" with "Dropped {Drop}".
  - The final words are `marketing-lead`'s, with `legal-lead`.

## 6. Analytics

**Status: granted 2026-10-20 (`analytics-lead`), conditions G1–G7 and F1–F5.** The source is `analytics-lead`'s #351 update review at `8b63ef10`, together with the original #351 grant (G1–G7). The props below are exactly as granted. None of these events is a WAT event.

They follow the P0-7 split:
- **client:** attempts, failures and exposures;
- **server:** successes and the consent ledger events.

| Event | Side | Class (granted) | Props (granted) |
|---|---|---|---|
| `sleeper_fa_connect_shown` | client | NON_INTENT (exposure) | `surface`, `reason` ∈ `not_linked` \| `expired` \| `unverified` |
| `sleeper_fa_consent_shown` | client | NON_INTENT (exposure) | `surface`, `reason` ∈ `first` \| `lapsed` \| `version` \| `withdrawn` |
| `sleeper_fa_consent_recorded` | server | **NON_INTENT** | `surface`, `copy_version` |
| `sleeper_fa_consent_withdrawn` | server | **NON_INTENT** | `via` ∈ `settings` \| `disconnect` \| `credential_expired` \| `credential_rejected` |
| `sleeper_fa_write_attempted` | client | INTENT | `surface`, `has_drop`, `has_bid`, `consent_ticked`, `attempt_id` |
| `sleeper_fa_write_succeeded` | server | INTENT | `mode` ∈ `add` \| `claim`, `has_drop`, `has_bid`, `result` ∈ `accepted` \| `partial`, `attempt_id` |
| `sleeper_fa_write_failed` | client | INTENT (a refused deliberate act stays intent) | `surface`, `error_code` (closed: the §3 codes ∪ `network` \| `timeout` \| `unknown`), `status` (int), `attempt_id` |

**Both consent events are NON_INTENT.** Withdrawals include system ones (`credential_expired`, `credential_rejected`), and one event name carries one class. Grants and withdrawals are twins. Nothing is lost, because `consent_recorded` always arrives in the same request as the INTENT `write_attempted`.

**Conditions, as written by `analytics-lead`:**
- **F1.** The append-only `platform_write_consents` / `platform_write_moves` tables (§4.3) are the R15.3 record of truth. These events are telemetry and are **never** read as consent proof.
- **F2.** No event fires for `account_deletion` withdrawals; the user's events are deleted with the account anyway. (Under R15.8 D12 no such withdrawal row exists: the rows are deleted.) Background (system) withdrawals are written non-touching: they don't bump `users.last_active_at` or `events_count`. This is the referral loop's C6 rule.
- **F3.** `attempt_id`, a client UUID, rides on attempted, succeeded and failed. The request body carries it (§3), and `platform_write_moves` stores it (§4.3).
- **F4.** `sleeper_fa_write_succeeded` fires only for `accepted` | `partial`. A Sleeper rejection or error reaches the client as an error and fires `sleeper_fa_write_failed` only, so the two can never double-count. `transaction_id` is not a prop: `attempt_id` joins the moves table, which holds `sleeper_transaction_id`.
- **F5.**
  - `surface` uses the claim-sheet values shared with `sleeper_handoff_resolved`.
  - `has_bid` is a bool, never the amount.
  - No player ids, names, tokens or free text.
  - `test_analytics_taxonomy_sleeper_fa_write.py` asserts exact props, the class split, namespace disjointness and succeeded/failed exclusivity.
  - A dated addendum is written before the emitters ship.

**`sleeper_handoff_resolved`** (the fallback hand-off) is granted separately, under G1–G7 (scope §1).
- On this sheet it carries `has_drop` only on claim-sheet `target=add` rows.
- Per G2, the key is **omitted** everywhere else, never sent as `null`.

## 7. Acceptance criteria (AC-19 to AC-40)

AC-1 to AC-18 are in [prd.md § 6](prd.md#6-acceptance-criteria).

| AC | Criterion | Verified by |
|---|---|---|
| AC-19 | The mutation shapes (and the claim encoding, or the fact that it's missing) are recorded in `sleeper-fa-write` before any write code merges | that folder's record; `sleeper_write.py` header |
| AC-20 | Flag off: all three routes 404, and the sheet opens in hand-off mode | `test_fa_write_flag_off_404`; S17 |
| AC-21 | **No Sleeper write without a valid grant.** On `consent_required` the opener is never called. The consent check comes before the write in source order | `test_fa_write_no_consent_never_calls_opener`; `test_fa_write_consent_check_precedes_write_structural` |
| AC-22 | A current-version tick appends a grant with every R15.3 field, then writes. A stale version appends nothing and gets 409 | `test_consent_grant_records_r15_fields`, `test_fa_write_stale_copy_version_refused` |
| AC-23 | A grant is valid at 7 d − 1 min and invalid at 7 d. Moves don't extend it | `test_consent_window_rolling_from_server_tick` |
| AC-24 | Settings withdrawal, disconnect, credential expiry and credential rejection each **append** a withdrawal. A different Sleeper account invalidates the grant. No row is ever updated | `test_consent_withdrawals_append_only`, `test_consent_bound_to_sleeper_account` |
| AC-25 | Every move appends a `platform_write_moves` row with the R15.3 fields, the request's `attempt_id` and Sleeper's result, including on refusals | `test_move_record_written_per_attempt` |
| AC-26 | Account deletion removes both tables' rows (R15.8 D12 [PRO]), and export includes them while the account exists | `test_account_deletion_coverage.py` (parametrized); `test_consent_and_moves_in_export` |
| AC-27 | Each §3 refusal returns its code with `detail = message`. Pre-write refusals never call the opener | `test_fa_write_refusals` (parametrized) |
| AC-28 | Mocked success for add and add+drop builds the spike-recorded body (golden) and returns `mode` / `status` / the halves. A claim gets 422 `waiver_claim_unsupported` and no write until the server's copy is v2 **and** the claim shape is captured (R15.8 D5); only then is it tested the same way | `test_build_fa_*_body_golden`, `test_fa_write_success_modes`, `test_fa_write_claim_refused_until_v2_and_capture` |
| AC-29 | `faWriteGate` truth table: the write API is called only on `write` / `write_with_consent`. An unticked box in a lapsed window never writes | S17 (executed), S18 |
| AC-30 | **Connect comes before consent.** No connection → `connect` (or `verify` when expired) wins over `consent` | S17 |
| AC-31 | Returning from `SleeperConnect` re-shows the same sheet with bid and drop intact, and never auto-sends. Cancelling returns unchanged | S23; TestFlight 21–22 |
| AC-32 | The checkbox is never pre-ticked. Make the move is disabled while it is unticked. A busy CTA prevents a double send | S21; TestFlight 23 |
| AC-33 | Client and server copy versions are equal. Both v1 and v2 texts are pinned, and a wording change needs a new version. The server's current version is v1 while claims are refused, and must be v2 before claims can be enabled. The v1 → v2 bump invalidates every v1 grant | S19, S22; `test_claims_require_v2_copy`, `test_consent_copy_version_bump_invalidates` |
| AC-34 | **Do it in Sleeper instead** is present in every state, and fallback refusals route to hand-off mode | S20; TestFlight 26, 28 |
| AC-35 | The steps block renders only in hand-off mode, never alongside the checkbox | S24 |
| AC-36 | No separate per-move dialog: the named button is the confirmation (D10, confirmed by `legal-lead` R15.8). Conditions (a)–(f) all hold: the league is on or beside the button; the finality line is always visible; claims show the waiver line and bid; the consent step shows "This move: …"; every send needs a fresh tap; the button is disabled from tap until the result | S25, S28 |
| AC-37 | After success, the FA list is refreshed. The trade deck no longer offers the dropped player as the user's (handed off to `trades-pm` as I-2/U2) | TestFlight 29 (with `trades-pm`'s mechanism test) |
| AC-38 | Result copy distinguishes a claim placed from a player added, and states partials exactly | S26; TestFlight 25 |
| AC-39 | The Settings row shows the window and withdraws in one tap with R15.2.6's copy. The sheet's Turn off link opens it | S27; TestFlight 27 |
| AC-40 | The seven granted `sleeper_fa_*` events are registered and classified in the same commit as their emitters, per F1–F5. Both consent events are in `NON_INTENT_EVENTS`. `write_succeeded` fires only for `accepted` / `partial`. A request without `attempt_id` is a 400 `bad_request`. | `test_analytics_taxonomy_sleeper_fa_write.py` |

## 8. Evidence

### 8.1 Backend tests

Sleeper is mocked through `sleeper_write._opener`. **Nothing here ever makes a live write.**

- **`test_sleeper_fa_write_route.py`** (new; the route itself is per `sleeper-fa-write`):
  - `test_fa_write_flag_off_404`
  - `test_fa_write_test_mode_fail_closed`
  - `test_fa_write_no_consent_never_calls_opener`
  - `test_fa_write_consent_check_precedes_write_structural` (sabotage: move the write above the consent check)
  - `test_fa_write_stale_copy_version_refused`
  - `test_fa_write_refusals[…]` (asserts the opener count for each)
  - `test_fa_write_success_modes[add|add_drop]`, with `[claim]` added once v2 is current and a claim is captured
  - `test_fa_write_claim_refused_until_v2_and_capture`
  - `test_claims_require_v2_copy` (enabling claims while the current version is v1 fails)
  - `test_grant_committed_before_write` (R15.8: the grant row exists before the opener is called, and stays when Sleeper rejects)
  - `test_move_record_written_per_attempt`
  - `test_fa_write_sleeper_rejected_withdraws_consent`
- **`test_sleeper_write_consent.py`** (new):
  - `test_consent_grant_records_r15_fields`
  - `test_consent_window_rolling_from_server_tick`
  - `test_consent_withdrawals_append_only` (asserts no UPDATE on either table)
  - `test_consent_bound_to_sleeper_account`
  - `test_consent_copy_version_bump_invalidates`
  - `test_consent_get_and_delete_routes`
  - `test_consent_and_moves_in_export`
- **Extended existing tests:**
  - `test_sleeper_write.py`: the golden bodies from the spike;
  - `test_account_deletion_coverage.py`: automatic, through the tuple;
  - the flag-parity test: `sleeper.fa_write` default false.
- **Granted events:** `test_analytics_taxonomy_sleeper_fa_write.py` (F5: exact props, class split, namespace disjointness, succeeded/failed exclusivity). Plus `test_fa_write_succeeded_only_accepted_or_partial` and `test_fa_write_attempt_id_round_trip` in the route test file.

### 8.2 Guard additions (`mobile/tests/check-sleeper-handoff.js`)

| Id | Assertion | Kind | Named sabotage |
|---|---|---|---|
| S17 | The `faWriteGate` truth table, executed. Order: flag off → `handoff`; not linked → `connect`; expired or unverified → `verify`; invalid and unticked → `consent`; invalid and ticked → `write_with_consent`; valid → `write`. Never a write value without a connection, or while unticked in a lapsed window | executed | Make invalid + unticked return `'write'` |
| S18 | The write API (`addFreeAgentInSleeper`, `api/sendInSleeper.ts`) has exactly one call site, in `ClaimSheet.tsx`, inside a branch on the gate returning `write` / `write_with_consent` | text | Call it straight from the CTA `onPress` |
| S19 | The client `copy_version` equals the server's `SLEEPER_ROSTER_MOVES_CONSENT_VERSION` | cross-file | Bump only the client |
| S20 | The refusal mapping sends `feature_disabled`, `sleeper_write_failed`, `waiver_claim_unsupported` and "Do it in Sleeper instead" to hand-off mode | text | Drop the hand-off from the `sleeper_write_failed` branch |
| S21 | The checkbox state starts `false`. Make the move's `disabled` includes `!ticked`. The CTA is disabled while `sending` | text | Initialize the state to `true` |
| S22 | `sleeperConsentCopy.ts`: the v1 and v2 texts each match a pinned hash, and v1 contains the "This move:" line and the Settings path | text | Edit one word of v1 in place |
| S23 | The connect return path re-shows the sheet with the preserved `bid` / `dropId`, and doesn't call the write | text | Call the write in the focus handler |
| S24 | `fa-claim.steps` renders only when the sheet mode is `handoff` | text | Render it unconditionally |
| S25 | No `Alert.alert` confirm sits between the button and the write (D10, R15.8) | text | Add an `Alert.alert` confirm before every write |
| S28 | D10(a)–(d): the button label includes the add, the drop and the league (or the league sits beside it). The finality line renders unconditionally under the button. A claim renders the waiver line and the bid. The consent step renders "This move: {CTA label} in {League}." above the box | text | Wrap the finality line in a collapsible or conditional |
| S26 | The success renderer branches on `mode === 'claim'` and renders both halves from the response | text | Render "Added" for claims |
| S27 | The Settings row exists in `PlatformDisconnectSection` behind `sleeper.fa_write`, calls `DELETE /api/sleeper/write-consent`, and shows R15.2.6's notice verbatim | text | Change the notice text |

### 8.3 Code-walk skeleton

This is section G of [prd.md § 7.2](prd.md#72-code-walk-proof-skeleton).

1. `ClaimSheet` CTA → link status + consent GET → `faWriteGate`.
2. If connect or verify is needed: `SleeperConnect` → focus return → the same sheet.
3. The consent step → `addFreeAgentInSleeper`.
4. On the server, in order: test mode → flag → session / verified → credential → **consent** (record the grant, then validate) → reads → `sleeper_write` (`_opener`) → the move row → the event → the response.
5. Back on the client: the result (claim vs add) → **Done** → FA refetch + deck invalidation. On a refusal: the refusal pattern, then hand-off mode.
6. Withdrawal: the Settings row → `DELETE /api/sleeper/write-consent` → a withdrawal row. Disconnect, expiry and rejection also append withdrawals.

### 8.4 TestFlight checklist (direct write)

**Every real add, drop or claim below is a production platform write.** Each one needs:
- the operator's approval when it runs;
- the operator's **test league** only;
- a reversal straight afterwards: release the added player, use a throwaway drop, or cancel the claim before it processes.

Turning `sleeper.fa_write` on for these steps is itself operator-approved, and it is switched off if a step fails. The steps fold in ux-lead's K1–K7.

| # | Setup | Steps | Expected |
|---|---|---|---|
| 21 (K1) | flag on, **no** Sleeper connection | Add → CTA | The connect step, with the reason. **Connect** → sign in → back on **the same sheet with bid and drop intact**. Nothing is sent |
| 22 | same | Connect → back out of the WebView | The same sheet, unchanged, with "Sleeper isn't connected" and **Do it in Sleeper instead** |
| 23 (K2) | connected, no consent | CTA | The consent step with the **v1** copy, including "This move: {CTA label} in {League}.", unticked, and Make the move disabled. Tick → it enables → the move happens. **No extra dialog** (if K-F3 holds). Reverse the move |
| 24 (K3) | inside the window | A second move (then reverse it) | No consent step. "Adds authorized until {date}" is shown |
| 25 | full roster, then a FAAB waiver claim | Add + throwaway drop; then a claim with bid ≤ remaining | The result says "added / dropped" vs "claim placed", exactly as Sleeper reports it. Reverse the add and cancel the claim. (While the copy is v1, or until a claim shape is captured, expect the `waiver_claim_unsupported` hand-off instead. When claims are enabled with v2, the consent step re-appears with the v2 copy) |
| 26 (K4) | consent step | **Not now** → **Do it in Sleeper instead** | The sheet is unchanged, then hand-off mode with steps → Sleeper opens (prd §4) |
| 27 (K7) | Settings › Leagues | **Stop roster moves** | R15.2.6's notice. The next move shows the consent step again. Disconnect → reconnect also re-asks |
| 28 (K6) | bid > remaining; then a move Sleeper refuses (if one can be set up safely) | Tap | Bid over budget: the inline error, no write. Sleeper refusal: the reason, **no retry**, Open in Sleeper. Not installed: the D2 message |
| 29 (K5) | after step 23's success, before reversing | Done | The FA list no longer offers Add for the player. The **Trades deck shows no card giving away the dropped player as yours**, via the mechanism handed off to `trades-pm` (I-2/U2) |

There are no ESPN, MFL or Fleaflicker steps: they keep `NO_ADD_REASON`, and they get no write and no consent.

## 9. Reviews and ship gate

| Reviewer | What | Through |
|---|---|---|
| `legal-lead` | **R15.8 rulings folded:** D10 and D11 confirmed; D5 ruled (v1/v2 copy); D12 ruled (delete with the account). Legal reviews the build against R15. Its remaining items are the LEG-L12 [PRO] confirmations under R15.7 | `head-bizops` |
| ux-lead | K-F1 to K-F7 as landed (§2, §5), and TestFlight 21–29 | `head-product` |
| `design-lead` | The checkbox, step, window line, result and refusal states, the Settings row, and the D2 alert | `platforms-pm` |
| `marketing-lead` | All words except the R15.8 consent copy: button labels, the connect-step line, result lines and the D2 alert (through `platforms-pm`). None may contradict D10(a)–(c) or imply a move can be undone. The secondary button's words (§2.4) are **open**, waiting on the `head-bizops` slot | `head-bizops` |
| `analytics-lead` | The seven §6 events: **granted** 2026-10-20 (G1–G7, F1–F5). Reviews the addenda | `platforms-pm` |
| `trades-pm` | The K-F5 deck invalidation (#339 §5.1), **handed off** as I-2/U2 | `head-product` |
| `platforms-pm` | The write-feature-gate pass and the risk-register row | — |
| `platforms-eng` / `eng-architect` | `docs/plans/sleeper-fa-write/` (being opened by `platforms-eng`; not on origin/main yet): spike, route and adapter. Also the two table shapes | `head-eng` |

**Ship gate for the add/drop build** (in addition to scope.md §5):
- **LEG-L12 [PRO] — MUST.** All of R15 must be in place before the add/drop build ships:
  - the consent copy: the R15.8 final **v1** text (and v2 before claims are enabled);
  - the consent evidence (R15.3);
  - the privacy-policy changes (R15.4);
  - the terms §5 changes (R15.5);
  - the label check (R15.6: no change, re-checked if a new data type appears);
  - professional review of R15.7(a)–(e).
- `platforms-pm`'s write-feature-gate pass (risk register).
- **`sleeper.fa_write` turns on (D6, `head-product` P34).** It needs all three of:
  - LEG-L12 done;
  - the P31 device tests passed;
  - the spike's mutation shapes captured.

  The flip itself is the operator's. Straight after it, TestFlight 21–29 run in the test league. Each real write is approved when it runs and reversed afterwards, and the flag goes back off if any step fails.

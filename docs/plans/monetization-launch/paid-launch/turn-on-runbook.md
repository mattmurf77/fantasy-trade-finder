# Turn-on runbook — paid launch (enforcement ON) and rollback

**Date:** 2026-11-21 · **Owner:** the operator (and release-lead, on the operator's word) ·
**Scope:** [scope.md](scope.md) · **Proof:** [code-walk-proof.md](code-walk-proof.md)

Nothing in this repo turns enforcement on. `config/features.json` and
`backend/tests/fixtures/flags/release.json` keep every `monetize.*` flag **false**, and the knob seeds are
0. These are the operator's steps, in order. Each step says how to check it before going on.

**The one rule:** enforce = `monetize.entitlements` ∧ `monetize.paywall` ∧ model_config
`paywall_enforce_enabled` == **exactly 1** (`backend/entitlements.py:313-320`). The knob is read live on every
gated request, so **0 is the instant, deploy-free kill**. Flags only change through `FTF_FLAGS` on Render
plus a restart.

**Today's production state (G-076, read 2026-11-10; re-read it, don't trust this line):**

- `FTF_FLAGS` has `monetize.paywall: true`, so the paywall UI and Settings › Subscription are live.
- `monetize.entitlements` is false.
- `paywall_enforce_enabled` is 0.
- So nothing is locked.

- [A. Before anything: what must be true outside the code](#a-before-anything-what-must-be-true-outside-the-code)
- [B. Turn-on, in order](#b-turn-on-in-order)
- [C. Device checklist (TestFlight, sandbox)](#c-device-checklist-testflight-sandbox--c1c14-before-b6-the-rest-right-after)
- [R. Rollback](#r-rollback)
- [F. The fixture rule](#f-the-fixture-rule)

## A. Before anything: what must be true outside the code

Each line is a hard prerequisite. Most already appear in
[`../../monetization/iap-enablement/sandbox-test-checklist.md`](../../monetization/iap-enablement/sandbox-test-checklist.md)
Part 0 (P1–P8), cited here rather than repeated.

1. **App Store Connect** (sandbox checklist P1, P2). All four must hold:
   - The Paid Apps agreement is Active.
   - `ftf_pro_monthly` and `ftf_pro_annual` are in one subscription group, at the prices and with the one-month free intro the paywall copy states.
   - The scheduled price change starts 2027-01-02 with "keep current price for existing subscribers".
   - Both subscriptions are submitted **with** the binary in step A4.
2. **RevenueCat** (P3, P5, P6):
   - The entitlement identifier is exactly `pro`.
   - The Current offering has `annual` and `monthly` packages.
   - The webhook points at `https://<render-host>/api/billing/revenuecat/webhook` with `REVENUECAT_WEBHOOK_SECRET`, set in the **Render dashboard**, not `render.yaml` (G-018). An unset secret makes the route 503.
3. **The binary.** `EXPO_PUBLIC_REVENUECAT_IOS_KEY` must be in the EAS production env at build time (P4; inlined at build, so no OTA fix). The build must contain:
   - #474 (M1), #488 (M2) and #495 (M3);
   - this branch (`feat/paid-launch`). Without it, enforcement is still safe, but a non-subscriber's Send shows "Couldn't send. Something went wrong" over the paywall, and Shop shows "Couldn't sweep the league".
   - Check: the TestFlight build number in TEST_LEDGER names the merge commit of this branch.
4. **App Review.**
   - **Two review accounts:** demo A is entitled (grant it with the admin route below); demo B is never entitled, stays pristine, and is never used for testing.
   - **Review notes** must say that trade finding and sending need a subscription, that the first deck page is free, and where Restore is (the paywall, and Settings › Subscription).
5. **Copy decisions** (operator, then marketing and legal). The paywall bullets (`mobile/src/copy/monetization.ts`, `mon.pay.b1`–`b4`) promise "Proposals sent to Sleeper, **ESPN** or MFL" and "Shop a player and **Win Now** trade targets".
   - **Decided 2026-11-25:** the owner kept ESPN send and the Win Now trade search for launch ("Restore it with ESPN assumed live"), so both lines are back to the legal-approved text. If either is cut later, those lines overclaim again: change them in the copy source before the binary.
   - `mon.lock.free` says "trends" are free. Keep that true if any candidate in scope §8 is adopted.
6. **Existing users** (operator decision, **decided 2026-11-22**: "All current app users get free pro for life."). Every account that exists when B6 turns enforcement on gets lifetime Pro; people who join after B6 pay. Without the grant, every current user would lose trade finding beyond the first page and lose sending the moment B6 lands.
   - **How:** `scripts/grant_lifetime_pro_existing_users.py`. It reads the user list from the database (read-only connection) and sends the grants through `POST /api/admin/entitlements/bulk-grant`: perpetual `pro`, source `manual_grant`, granted_by `operator`, note `lifetime-pro: existing user at paid launch (operator 2026-11-22)`. One grant per person, however they signed in (Sleeper, Sign in with Apple, or both linked). Anyone already on perpetual Pro is skipped, so it is safe to re-run.
   - **Dry run first, then `--apply`.** Run the dry run now to see the counts. Run `--apply` at B5a, the last step before B6, so accounts created in the meantime are included.
   - **Demo B stays out.** Create demo B (A4) **before** the first run, and pass it with `--exclude` on every run. Pass any never-entitled test account the same way (`--exclude-file` takes a list). An exclude that matches no user stops the run. Anything created after the B5a run is never granted, so a fresh account for §C is never-entitled by construction.
   - A current subscriber (trial or paid) also gets lifetime Pro. Their Apple subscription keeps billing until they cancel it in Apple's settings; the grant does not cancel it.
   - Lapsed rows read `lapsed`, so comped users who later expire get the lapsed copy, not a second trial. Lifetime grants never expire.
7. **Web** (owner decision, **decided 2026-11-25**: "aligned. Close this"). The wall covers non-app requests too, so `paywall_web_enforce_enabled` goes to **1** at B6a. Nothing on the web has to be ready first:
   - Since the launch cut of web sign-in (PR 729), no web page calls a gated route, and there is no web 402 state: "continue on iPhone" was never built. The only 402 handling on the web is in `web/js/app.js` (a toast), and no page loads that file.
   - A browser visitor has no session, so a gated route gives that route's own sign-in answer, never a 402. The landing, legal, FAQ, contact, ranking-method, share (`/s/…`, `/og/…`) and join pages are free routes, so they are never gated, whatever the knob says.
   - What the knob closes: a call with a session token but without the app's `X-Device` header (a script, an old web tab, a hand-made request). Until it is 1, such a call skips the wall.
   - `IOS_INSTALL_URL` is not needed for this.

## B. Turn-on, in order

Run from the repo root with `CRON_SECRET` in `secrets.local.env`. Every `set_knob.py` call goes through the logged `PUT /api/admin/config/<key>` path (`scripts/set_knob.py`). Never write the prod DB directly, because the change won't load until a restart.

| Step | Action | Check before going on |
|---|---|---|
| **B0** | Read the live state: `GET /api/feature-flags` (public) and `GET /api/admin/config` (`X-Cron-Secret`). | `monetize.paywall` true, `monetize.entitlements` false, `paywall_enforce_enabled` 0, `paywall_preview_pages` 1, `paywall_web_enforce_enabled` 0. If any differs, stop and find out why (G-076). |
| **B1** | Confirm the preview knob: `python3 scripts/set_knob.py paywall_preview_pages 1` (a no-op if already 1; the source is logged). | `GET /api/admin/config` shows 1. config-reference requires this live before the enforce knob. |
| **B2** | **Render → Environment → `FTF_FLAGS`:** add `"monetize.entitlements": true` to the existing JSON. **Keep every other key exactly as it is**, especially `monetize.paywall: true` (G-076: removing keys silently turns seven features off). Save, which restarts the service. | After the deploy is live, `GET /api/feature-flags` shows both `monetize.entitlements` and `monetize.paywall` true. This is **observe mode**: the knob is still 0, so nothing is blocked. |
| **B3** | Observe for a day (or at least one active evening). | Render logs show `ENTITLE-OBSERVE … would_block=` lines (`entitlements.check_pro`). `would_block=True` counts are the users who **will** see the paywall. If that number is surprising (testers you meant to comp), go back to A6. `/api/me/entitlements` now returns real `pro` values but `enforcing:false`, so the app still shows no lock. |
| **B4** | Grant the App Review demo A account and your own test account. Use the admin grant route; don't buy. | `/api/me/entitlements` on those sessions: `pro:true`. |
| **B5** | On a TestFlight build from A3 with a sandbox Apple ID, run **§C1 and C14** with the knob still 0 (purchase, Restore and the webhook can also be exercised now: C5–C8 work without enforcement, they just unlock nothing). | Those steps pass. |
| **B5a** | **Lifetime Pro for every existing user (A6), immediately before B6.** `set -a; . ./secrets.local.env; set +a` then `export DATABASE_URL="$DATABASE_URL_PROD"`. Dry run: `python3 scripts/grant_lifetime_pro_existing_users.py --exclude <demo B> --out feedback-workspace/lifetime-pro/would-grant.txt`. If the counts look right, the same command with `--out feedback-workspace/lifetime-pro/granted.txt --apply --base-url https://<render-host>`. Then the dry run once more. | The first line names the prod database. The apply ends `SUMMARY: sent N; confirmed perpetual pro on read-back N; failures 0`, exit 0. Any failure: re-run the same command (granted users are skipped). The last dry run says `would grant: 0`. `GET /api/admin/entitlements?user=<a known existing user>` shows a `manual_grant` `pro` row with `expires_at` null; `?user=<demo B>` shows no active `pro` row. |
| **B6** | **Turn on**, in a watched window with the kill command ready: `python3 scripts/set_knob.py paywall_enforce_enabled 1`. Then run **§C2–C15** straight away (they need enforcement; if a staging server is wired to the same RevenueCat project, run them there first instead). Any failure → §R1 at once. | Within one request: a never-entitled test account's second deck page → 402 `preview_used`; its Send → the paywall. `/api/me/entitlements` → `enforcing:true`. `paywall_gate_hit` rows start (`/api/admin/analytics/...`, once per user, gate and family per day). |
| **B6a** | **Close the wall to non-app requests (A7)**, only once B6's §C checks pass: `python3 scripts/set_knob.py paywall_web_enforce_enabled 1`. Its own step, so a web misfire can be killed without touching the app (§R4). | `GET /api/admin/config` shows `paywall_web_enforce_enabled` 1. In a desktop browser, `/`, `/privacy`, `/terms`, `/faq.html`, `/contact.html` and `/ranking-method.html` load as before, with no 402 anywhere. On the never-entitled test account, the app's Send still opens the paywall (C3, unchanged). If you hold that account's session token: `POST /api/trades/propose` with it and **no** `X-Device` header → 402 `{"error": "pro_required", "gate": "never_trialed"}`, the app's answer. |
| **B7** | Watch the first 24 h. | K0 alarm: any 402 `preview_used` to a user never served a card should be zero. Webhook 200s in the Render logs for every sandbox or real purchase. No spike in `api_request_failed` on free routes. |
| **B8** | Re-read the live state, as in B0. | `paywall_enforce_enabled` 1 and `paywall_web_enforce_enabled` 1. `paywall_gate_hit` rows with `source` `web` are expected only from calls without the app's header (scripts, old tabs); the website itself sends none. |

Do **not** edit `config/features.json`. Production is driven by `FTF_FLAGS`. The file's defaults stay dark so a fresh environment or a test run is never enforcing by accident (§F).

## C. Device checklist (TestFlight, sandbox) — C1/C14 before B6, the rest right after

This adds to the launch scope's T1–T20 (`plan/monetization-launch` scope §3, which is not on main) and to the IAP sandbox checklist §1–§11. Run those as written. The steps below are the paid-launch additions and the user states the brief names. Run **each never-entitled check on a fresh account**.

1. **Sandbox setup.**
   - Sign the device into a sandbox Apple ID with no prior purchase of either SKU (P7).
   - Install the A3 build.
   - Expect: Settings › Subscription shows See plans and Restore (verified session).
2. **Never-entitled, the free page.** Fresh verified account: Find a trade → cards → swipe to the end of page 1.
   - Expect: the end card "That's the first page." + "Finding trades needs a subscription." + See plans; no "Couldn't load more trades".
3. **Every launch entry point opens the paywall, with no error on top.** On the never-entitled account (page used) and on a lapsed sandbox account, try each one:
   - Find a trade (Acquire tab);
   - the calculator's Find a trade, with a give side and without;
   - the calculator ✓ (queue);
   - Send in Sleeper on a deck card, on the calculator, on Shop and on a Matches row;
   - Send in MFL on an MFL league;
   - League rankings Offer and Target;
   - Usage Trends Trade;
   - More offers / Shop a player;
   - a single pin (the ideas panel).

   **Expect, for each:**
   - the paywall opens once, with the headline naming the action ("Sending trades…" for Send and ✓, "Finding trades…" otherwise) and the four bullets;
   - **no** "Couldn't send" alert, **no** "Couldn't queue that" toast, **no** "Couldn't sweep the league", **no** "No defensible packages";
   - after Not now, Shop and the panel show "Finding trades needs a subscription." + See plans, and no second paywall opens by itself within 10 s.
4. **Send stops before the confirm.** Verified, never entitled, entitlements loaded (wait 5 s after launch): tap Send.
   - Expect: the paywall, **before** any "Send this trade?" confirm. Nothing reaches Sleeper.
5. **Trial purchase.** From the C3 paywall (annual): Start 1-month trial → Apple's sandbox sheet → confirm.
   - Expect: back on the same screen (or the Founding GMs welcome, then Back).
   - On the deck end card, the next page loads by itself.
   - Shop and the panel replace the notice with ideas by themselves.
   - Find a trade and Send need one fresh tap and then work.
   - Render log: a RevenueCat webhook 200; `/api/me/entitlements` → `pro:true`.
6. **Paid purchase.** A second sandbox Apple ID that already used the intro (or monthly after annual's trial).
   - Expect: no "free" anywhere; "Subscribe"; the price; then the same results as C5.
7. **Restore.**
   - Delete the app, reinstall, sign in to the same account → Settings › Subscription → Restore. Expect "Welcome back. Your subscription is restored."
   - On a never-purchased Apple ID, Restore → "No subscription found for this Apple ID…", and the paywall stays open.
8. **Cross-device.** Sign in to the C5 account on a second device (with a different Apple ID, or none).
   - Expect: Pro is honoured, because the server owns the entitlement, keyed on the account and not the Apple ID.
   - Restore on the second device's Apple ID finds nothing and changes nothing.
9. **Lapse and expiry.** Sandbox subscriptions renew every few minutes and stop after about 6 renewals. Cancel in sandbox settings and wait for expiry. Background, then foreground the app (that refreshes entitlements).
   - Expect: the next Find a trade or Send → the paywall, whose 402 gate is `trial_expired` (trial only) or `lapsed`.
   - No paywall opens by itself when access ends (T9).
   - The deck shows no stale cards beyond one held page at most 5 minutes old.
10. **Refund.** Request a sandbox refund through App Store Connect's sandbox tools, or send a RevenueCat CANCELLATION/EXPIRATION test event.
    - Expect: within one foreground refresh, `/api/me/entitlements` → `pro:false`, and gated actions open the paywall. The client never keeps Pro on a receipt (`useEntitlements.refresh`).
11. **Unverified session.** Sign in by typing a Sleeper username (don't connect); tap Find a trade, then Send.
    - Expect: "Verify this session first" (Verify with Sleeper, Cancel) and **never** the paywall or a price.
    - Compare an entitled and a never-entitled username side by side: identical (R28.9).
    - After verifying, the find call re-runs by itself; Send returns to its confirm.
12. **Demo session** (if `landing.try_before_sync` is on; it is off today): the deck works, and Send or Settings › Subscription show "A new sign-in is needed" and no purchase.
13. **Delete account while subscribed.** Settings › Account → Delete.
    - Expect: the dialog's sub-note and the "Manage subscription" button (Apple's page). Delete works with no 402.
    - The subscription is **not** cancelled by deletion; the dialog says so.
14. **Free surfaces stay free:** rank, tiers, Calibration, the calculator's value comparison, Matches (view), League standings and forecast, Draft Room, Settings, Export, Feedback. No paywall, no 402.
15. **Kill test.** `python3 scripts/set_knob.py paywall_enforce_enabled 0`.
    - Expect: the next Find a trade gives a full deck and Send works.
    - Back to 1 → gated again (T11).

Log every step's result in `living-memory/TEST_LEDGER.md` with the build number.

## R. Rollback

1. **Instant (no deploy):** `python3 scripts/set_knob.py paywall_enforce_enabled 0`.
   - Every gated route lets requests through on the next request.
   - The app's pre-checks go dark on the next `/api/me/entitlements` refresh (foreground), because `enforcing` turns false.
   - Purchases and Restore keep working, and subscribers keep their rows.
   - **Use this for any gate misfire.**
2. **If you also want observe mode off:** remove `monetize.entitlements` from `FTF_FLAGS` (leave every other key), then restart. With it off, every user is implicitly Pro (`check_pro` → True).
3. **Do not turn `monetize.paywall` off** to roll back the gate. It hides the paywall, Restore and Manage subscription from paying subscribers (App Store guideline 3.1.1 needs Restore), and with G-076's `FTF_FLAGS` it is shared with other features' config. The knob is the lever.
4. **Web only:** `python3 scripts/set_knob.py paywall_web_enforce_enabled 0`. Requests without the app's `X-Device` header go back to ungated; the app stays walled.
5. **Preview mis-sized:** `paywall_preview_pages` is live. 0 removes the free page (Product decision, copy rewrites); 1 is the launch value.

## F. The fixture rule

`backend/tests/fixtures/flags/release.json` mirrors `config/features.json` for every key, including `monetize.*`. Several tests read both and assert the pairs match: e.g. `test_events_api.py:1216` "the 3-touch mirror", and the flag-reading tests listed by `git grep -n "fixtures/flags/release.json" backend/tests`.

- **Turning enforcement on for launch changes neither file.** It is `FTF_FLAGS` plus the knob.
- If the operator ever graduates `monetize.entitlements` / `monetize.paywall` to true **in the file**, change `release.json` in the same commit, update `docs/config-reference.md`'s rows (and the G-076 "production overrides" line), and run the full suite.
- Never set `paywall_enforce_enabled`'s seed to 1. The seed is insert-if-absent, so a fresh DB, or every local and test environment, would enforce.

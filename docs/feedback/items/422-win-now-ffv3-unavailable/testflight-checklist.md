# TestFlight checklist — 2026-09-08 feedback batch (G-422, G-423, G-425, G-427, G-428)

One pass for the whole batch. Consolidated from both QA agents' checklists per group; this file is the only runtime evidence mobile gets (D-056), so run every step you can.

| Field | Value |
|---|---|
| App version | 1.17.3 |
| Build number | ______ (App Store Connect) |
| Backend source sha (Render LIVE) | ______ |
| Date run | ______ |
| Tester | ______ |

**Record the outcome of every step (pass / fail / skipped + one line why) in `living-memory/TEST_LEDGER.md` under this date.**

Before you start: Render must be LIVE on the merge sha and the 1.17.3 build installed. Sign in as mattmurf77 with both **FFV3** (Sleeper `1312140920132497408`) and **Lakeview** (`1312076055586050048`) linked. "Render log" steps: Dashboard → the web service → Logs, and search for the quoted text. Cancel every real Sleeper offer you send, in the Sleeper app, right after the step.

## G-422 — Win Now on FFV3 says why it can't run (#422)

Backend-only. Needs FFV3 (steps 1–4) and Lakeview (step 5).

1. **[FFV3]** League tab → "Season projections & Win Now". Expect, within about 2 seconds, this exact text under the "Refresh season projections" button: "Win Now can't model this league yet. Its starting lineup uses K, DL, LB, DB, IDP_FLEX (8 of 15 starting slots), and season projections cover QB, RB, WR and TE only. Kicker and IDP projections are not supported, so standings and trade search stay off for this league." No standings card, no priority buttons, no "Find Win Now trades" button. **Fail** if it still says "Unsupported roster slots", misses any of the five slots or "8 of 15", or takes ~10 seconds.
2. **[FFV3]** Same screen → tap "Refresh season projections". Expect the label to flip to "Loading season projections…" and the same sentence back within ~2 seconds.
3. **[FFV3]** Trades tab → "Win Now" entry. Expect the identical sentence (same screen, same result).
4. **[FFV3, Render log]** Find `GET /api/league/season-projections?league_id=1312140920132497408` → status 200, body roughly 300–350 bytes. In the seconds before it there must be **no** burst of `projections/nfl/2026/` lines and no `matchups/` lines. **Fail** on any `/projections/` line tied to that request (before the fix there were 17).
5. **[Lakeview]** League tab → "Season projections & Win Now". Expect anything *except* the K/IDP sentence — today either projected standings, "Unknown starter availability…", or "Current-week play may have started…". **Fail** if the slot sentence appears for Lakeview.
6. **Web (optional):** sign in at the Render site → Win Now view. FFV3 active → same sentence as step 1; Lakeview active → step 5's behaviour. **Fail** on "Unsupported roster slots".
7. **Regression:** any offense-only league that showed standings before this deploy still shows standings.

## G-423 — Team review outlook and "done" state register on the landing (#423, #424)

Mobile. Needs Lakeview (has a saved outlook: Rebuilding), FFV3, and ideally a third league never reviewed on this device. A sub-second "Outlook · Not set" (or the previous league's name) on first paint that fixes itself is normal loading, not the bug; the bug is "Not set" that **stays**.

1. **[Lakeview]** Acquire landing → TopBar league switcher → pick Lakeview → let it settle. Expect the row under "Show me around" to read "Outlook · Rebuilding", not "Not set", with no relaunch.
2. **[Lakeview]** Tap the Team review entry → window beat → pick a **different** outlook (e.g. Contending) → Confirm → immediately leave with the header back arrow (do not reach the plan beat). Expect on the landing: "Outlook · Contending" right away; the entry is still the **full** "Start team review" card (not done).
3. **[Lakeview]** Open Team review again → Confirm the window → depth beat "Save & continue" → skip through to the **plan beat** → tap a third outlook chip (e.g. Rebuilding) → leave with the header back arrow, **not** "Find my trades". Expect on the landing, no relaunch: "Outlook · Rebuilding" and the entry reads "Team review · done".
4. **[Lakeview]** Kill the app → relaunch. Expect the row still "Outlook · Rebuilding" and the entry still "Team review · done". Then tap that row → run to the plan beat → tap "Find my trades". Expect: back on the landing, still "done", row still current, no error or duplicate toast.
5. Switch to **FFV3**. Expect FFV3's own saved outlook and its own done/not-done state (never Lakeview's once the fetch settles). Switch back to Lakeview: Lakeview's values return.
6. **Third league (never reviewed):** landing shows the full "Start team review" card and "Outlook · Not set" with a working "Change" that opens the Trade DNA sheet. Save an outlook there → row updates without relaunch. A saved "Not sure" must read "Outlook · Not sure", never "Not set".
7. **League switch on the plan beat (must NOT mark the new league done):** target = a league whose entry is still the full card (step 6's league). On FFV3 open Team review → reach the plan beat → open the TopBar league switcher **without leaving the review** → pick the target league. Expect the review to restart on the target league's **first** beat with no chips carried over. Leave with the back arrow. On the target league's landing: entry is **still the full card**, and its row shows its own outlook (or "Not set"). Switch back to FFV3: FFV3 reads "Team review · done" (it did reach its plan beat).
8. **Same-league re-render does not restart:** open Team review → Confirm the window → on the depth beat toggle a chasing position, do not save → background the app ~10 s and come back (or open and close the league switcher without picking). Expect: still on the depth beat with the toggle intact.

## G-425 — Team overhaul tile replaces the Draft cell on Acquire (#425, #426)

Mobile. FFV3 or Lakeview, operator account. `overhaul.enabled` is on in production.

1. **Acquire tab, no saved overhaul plan:** the first block under the "Win Now · season gains…" link is a full-width ice tile — uppercase TEAM OVERHAUL / "Plan 4–5 trades that push all in or blow it up." / "Start overhaul ›". Directly beneath it the utility row shows **exactly two** cells: Free agents and Manual calc. **Fail:** a Draft cell in that row, a three-cell row, or the tile anywhere but directly above the row.
2. **Scroll the same page:** between the pills/banners and the trade builder there is only the Team review entry (collapsed row or full card). **Fail:** a second Team overhaul card or tile anywhere.
3. **Tap the tile:** it darkens while pressed → the Team overhaul Outlook step opens. Back → Acquire, same league, tile unchanged. Admin feed shows `overhaul_started` with `entry=trades_home_card`. **Fail:** no navigation, or a different `entry` value.
4. **With a saved plan** (start one, pick an outlook, come back): the tile reads RESUME OVERHAUL with a single line "<Push all in | Blow it up | Outlook not set> · <summary>" (ellipsis if long, never a second line) and "Resume ›". Tap → the plan screen for that overhaul, not the Outlook step.
5. **Draft Room still reachable:** bottom Draft tab (seasonal) opens it; League tab → "Rookie draft" tile opens it. If you can view the control cohort (a non-allowlisted account), the tile sits above the mode chip strip and the strip's leading chip is still Draft. **Fail:** any entry missing.
6. **Pushed "Trade ideas" page:** run Find a Trade so the results deck pushes. Expect the tile and the two-cell utility row at the top of that page, same as the landing. **Fail:** tile missing there, or a Draft cell present.
7. **Toast clearance:** trigger any toast on Acquire (switch leagues, or like/pass a suggestion). Expect it below the utility row, not over the tile or the row.
8. **Flag off (optional — needs a flag flip):** with `overhaul.enabled` false and no saved plan, the tile is gone and the row is still two cells — the Draft cell must **not** come back. Restore the flag.

## G-427 — First-round picks exempt from the package-depth tax (#427)

Backend-only. Trade Calculator in any league; open "Value adjustments" to see the rows. Both agents agreed two seconds must still be taxed.

1. **Give:** "2027 Mid 1st" twice (or two owned 2027 firsts). **Receive:** one player whose tier badge is "2 1sts", sitting near the bottom of that band. Expect verdict **Even**, give total = the two picks' face values added together, and **no** "Package depth" row on the give side (the disclosure may be empty).
2. Same give → receive a player **mid-band** in "2 1sts". Expect "favors receive", but the give total still equals the two firsts' face values (no depth deduction).
3. **Give:** "2027 Mid 2nd" twice → **Receive:** a player badged "2nd" worth about two seconds. Expect the player side ahead **with** a negative "Package depth" row on the give side — seconds are still taxed.
4. **Give:** one 2027 Mid 1st + one WR of similar value → **Receive:** a single player worth roughly their sum. Expect **fair, not even** (ratio ≈ 0.91), with one "Package depth" deduction on the give side that matches the WR only.
5. **Trades deck:** find or generate a card with two firsts on one side → open the same package in the calculator. Expect the card's verdict and side values to match the calculator's exactly.
6. **Settings → stud tax = Heavy** → repeat step 1. Expect the player side slightly ahead (≈ 0.93) but the give total still the two firsts' face values. Switch back to Market.

## G-428 — Sleeper pick send refused for a drafted 2026 pick (#428)

Backend + mobile (1.17.3 carries the "Couldn’t send" detail text). Needs FFV3 (2026 draft complete 2026-08-26). Both agents agreed a players-only send must be unchanged.

1. **[FFV3, Render log]** Force-quit and reopen the app with FFV3 selected (this runs the pick sync). Expect one of two log lines: `owned-pick sync for 1312140920132497408: excluding [2026] — Sleeper reports the draft complete` or `… drafts read empty — excluding 2026 on the cached drafted/… verdict (D-189)`. Neither line ⇒ reopen once more before continuing.
2. **[FFV3]** League → Picks list → scroll the whole list. Expect **no 2026 pick anywhere**; earliest class is 2027. Any 2026 row ⇒ STOP, report the step-1 log line.
3. **[FFV3]** Trades → Calculator (in-league) → add from "My picks". Expect only 2027/2028/2029 picks; "2026 4th (orig. roster 11)" is gone. Then Trades → Deck → swipe until a card carries a pick: every pick on every card is 2027–2029.
4. **[FFV3] Positive send, own pick:** Calculator → give your **2028 4th** for any player → Send in Sleeper → the pre-flight is the plain "Send this trade?" (no "This trade will likely fail") → confirm. Expect **"Trade sent"** and the pending offer in the Sleeper app → cancel it there.
5. **[FFV3] Positive send, far class + acquired pick:** repeat step 4 with your **2029 1st** → "Trade sent" → cancel. Then receive "2027 1st (orig. you)" from roster 5 for one of your players → "Trade sent" → cancel. (Proves Sleeper's window really is 2027–2029, and acquired picks send.)
6. **[FFV3, Render log] Players-only send unchanged:** one of your players for one of theirs, no picks → Send → "Trade sent" → cancel. The Render lines for that `/api/trades/propose` show Sleeper reads for `/league/…` and `/rosters` only — **no** `/drafts`, **no** `/traded_picks`.
7. **[FFV3] Negative send, spent 2026 pick — only if reachable:** the web app has no send flow, so use a Deck or Matches card cached **before** step 1 that still names a 2026 pick. Send in Sleeper → expect the pre-flight "This trade will likely fail" with "1 draft pick in this trade can’t be traded in Sleeper right now — 2026 picks are no longer tradable (Sleeper is trading 2027–2029 picks). Rebuild the trade with one of those." → tap "Send anyway" → expect the alert **"Couldn’t send"** with that same sentence, **not** "Please try again", and **no** Sleeper reconnect screen. Render log: **no** `sleeper propose write-failed` line for this attempt. No such card ⇒ log "not reachable" (the server refusal is covered by tests).
8. **Sleeper's own refusal wording (if one happens):** any send Sleeper itself rejects shows "Couldn’t send" followed by Sleeper's sentence, never a `[{"message": …` fragment. Nothing provoked ⇒ log "not provoked".

## Not runnable by the operator

- **Prod DB queries** (G-428 agent steps): `SELECT season, COUNT(*) FROM draft_picks WHERE league_id='1312140920132497408' GROUP BY season` before/after the deploy (expect 2027–2029 only, 48 rows each after), and the `user_events` check for `sleeper_send_failed` / `sleeper_send_succeeded` with `error_code = 'sleeper_pick_untradable'`. Needs a read-only prod shell; skip unless one is set up.
- **First-year startup league** (G-428): a league whose 15+-round startup draft is complete for 2026 should also hide all 2026 picks after one app open. No such league is linked — log "no startup-year league available".
- **G-427 rollback drill** via `POST /api/admin/config` `stud_tax_exempt_first_round = 0` — ops-only, optional.
- **G-425 control cohort** (step 5's Draft chip) needs a non-allowlisted account; log "no control account" if none.

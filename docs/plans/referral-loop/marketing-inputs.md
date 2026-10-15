> **Owner:** marketing-lead (proposed; operator approval of words pending). Copied verbatim from marketing-lead's wave-2 working file on 2026-10-15 (re-copied 2026-10-15 after the lab addendum) so the PRD's citations stay durable.

# marketing-lead, wave 2: referral loop words, channels and UTM convention (task 3)

> `marketing-lead`'s three deliverables for `growth-pm`'s referral-loop PRD (`docs/plans/referral-loop/`, branch `plan/referral-loop`): **A** the copy table for every loop hop, **B** the channel plan with a CTA-target recommendation, and **C** the UTM / install-source convention with a registration proposal for `analytics-lead`. These are drafts for a PRD, not shipped copy. Nothing here is sent, posted or committed by marketing.

**Owner:** `marketing-lead` (Business Operations), reporting to `head-bizops`. **Partner:** `growth-pm` (W4 direct route, operator-approved 2026-10-15). **Basis:** code read at `origin/main` 678834ab, on 2026-10-15. Every `file:line` is at that sha.
**State:** **accepted by `growth-pm` on 2026-10-15.**
- The PRD carries option A as amended, plus token-only links and one inviter notification.
- It takes defects 1–9 and 11 as fixes. Defect 10 (the public TestFlight link) is an operator decision.
- The copy rows are cited in the PRD as *proposed*, pending the operator's approval of the words, which goes through `marketing-lead` → `head-bizops`.
- The S-series is remapped to `growth-pm`'s fixed IDs (§0.4). Workers: `mkt-writer` (A), `mkt-partners` (B), `mkt-seo` (C). I reviewed all three, accepted them with the edits listed in §0.4, and re-checked the claims marked *lead-verified*.

## Contents

- [0. Lead summary](#0-lead-summary)
- [A. Copy table](#a-copy-table-mkt-writer)
- [B. Channel plan](#b-channel-plan-mkt-partners)
- [C. UTM / install-source convention](#c-utm--install-source-convention-mkt-seo)
- [D. Decisions needed](#d-decisions-needed)
- [E. Handoffs](#e-handoffs)

## 0. Lead summary

### 0.1 Where to find growth-pm's five asks

| Ask | Where |
|---|---|
| 1. Invite message, with and without the league name | §A `gp.invite.msg`, `gp.invite.msg_league`. **Default: the version without the league name**, which fits ~140 characters. The recipient is in that league already |
| 2. Join landing: title, OG description, headline, value prop, CTA labels for each option | §A `gp.join.*`. The page **doesn't exist yet**: `/app/league/join/<id>` 302s to `/` (`server.py:12596-12624`) |
| 3. Inviter pushes: the existing "joined via your invite" and the future `referral_joined` | §A `gp.push.*`. The existing row renders its sentence twice (title = body, `database.py:12632-12636`) |
| 4. UTM / source values for `invite_card`, `invite_banner`, `league_tab`, `share_package`, `trade_card` | §C "Convention" table. Your five names don't match the existing `surface` props, so §C proposes a **bridge, not a rename** |
| 5. Where invites travel, and what the OG card must survive | §B "Where invites and shares travel" and its "What the OG card must survive" list |

### 0.2 CTA target: lead recommendation

**Recommendation: A** (your pick). iOS goes to the public TestFlight link; everything else goes to web `/`. It needs **three amendments**, listed after the finding below.

**The finding that decides it (lead-verified).** On the web, Sleeper sign-in **requires the desktop Fleeced browser extension**.
- `web/js/browser-auth.js:1` says "Browser verification requires the installed Fleeced extension".
- It fails with `extension_unavailable` after 2s (`:5`, `:45`).
- `handleLogin` calls it unconditionally (`web/js/app.js:334`).
- ESPN and MFL browser sign-in shows "not available … yet" (`app.js:1263-1264`).

So **on a phone, web `/` dead-ends every invitee on every platform.** Phone chats are where invites travel (§B).

**Why not B or C before the listing:**
- B ("/" for everyone) strands every phone invitee.
- C is B with no end date.
- The two workers disagreed (`mkt-partners`: A plus "Continue on web" for iOS Sleeper users; `mkt-seo`: C, with web sign-in first to lock attribution). Both assumed a phone can sign in on the web. It can't, so I'm overriding both on that point.

**The three amendments, to ship with A:**
1. **A re-tap step at H3a** (from `mkt-partners`).
   - Under the TestFlight CTA: "Installed? Go back to the chat and tap the invite again." (§A `gp.join.retap`). A re-tap is a universal link, so it lands on H3b with `league` and `ref`.
   - Optionally, a `dtf://?league=<id>&ref=<u>` button. The scheme is at `mobile/app.json:8`.
   - Without this, a TestFlight install opens cold with no league and no `ref`, and `referral_joined` never fires.
2. **League-scoped attribution as the fallback** (from `mkt-seo` §C, recovery (ii)). This is query-only, with no build: credit the league when a new user's first `league_id` matches an `invite_shared.league_id` from the prior 14 days.
   - It also covers ESPN and MFL. `invited_by` is only sent by the two Sleeper session-init builders (`mobile/src/api/auth.ts:514`, `:607`; lead-verified).
3. **An honest line for everyone who isn't on iOS** (§A `gp.join.cta.A_desktop`, `gp.join.android_note`).
   - Desktop: "Open the web app", plus a line saying sign-in uses the Chrome/Edge extension.
   - Android and other phones: say plainly that Fleeced runs on iPhone and desktop web for now. Never offer a web button that can't sign them in.

**After the listing:** the App Store link takes TestFlight's place in the same slot. That's option C's end state, with campaign `ct` tokens per §C.
- **Riskiest assumption:** iOS invitees finish a two-app install from a chat link and come back to re-tap.
- **Cheapest test** (no build; the operator runs it):
  - Paste the public TestFlight link under the invite in a few of their own leagues, including one ESPN or MFL league.
  - Compare `league_member_joined` against `referral_joined`. The gap is the credit lost to cold opens.
  - Add one TestFlight-checklist step: tap an invite inside Sleeper's league chat, with and without the app, and note what opens.

### 0.3 Loop defects found, for the PRD's fix list

Each is cited in its section. Items marked *lead-verified* I re-checked myself.

| # | Defect | Hop | Where |
|---|---|---|---|
| 1 | **Old product names across the loop**, against D-057. These are the invite message, share text, share image, calculator captions, `/s/*` title and footer, the OG PNG footer, the inviter push, and the web logos | H1–H7, S | §A "Notes": 17 strings in the loop. *lead-verified:* `InviteLeaguematesBanner.tsx:132`, `server.py:22662` |
| 2 | **`/s/*` CTAs drop the `ref` they arrived with**, because all three are hard-coded `cta_url="/"` | S → H3a | `server.py:25548`, `:25563`, `:25669` (*lead-verified*) |
| 3 | **`ref` is the sharer's raw Sleeper username.** It's PII in every URL, Render log and preview. It's also unauthenticated: a crafted `?ref=<someone>` makes `referral_joined` fire at that person | H2, H7 | `shareLinks.ts:86-92`, `InviteLeaguematesBanner.tsx:56-60`, `server.py:22653-22668` (*lead-verified*). §C, decision 3 |
| 4 | **ESPN and MFL joins never credit the inviter.** `invited_by` is only sent on the Sleeper session-init paths | H5 | `auth.ts:514`, `:607` (*lead-verified*) |
| 5 | **No join landing exists**, so every invite preview is the generic `/` OG: no league name and no image | H3a | `server.py:12596-12624`, `web/index.html:9-14` |
| 6 | **Web H3a is unmeasured:** there's no web `invite_link_opened`, and opening an `/s/*` link fires no event on either client | H3a, H8 | §C "Today" |
| 7 | **The `referral_joined` inbox row shows one sentence twice**, and the inviter also gets the `league_member_joined` push, so they're notified twice | H7 | `database.py:12632-12636`, `server.py:22699-22718` |
| 8 | **The `/s/*` og:image is relative, and `robots.txt` blocks `/s/` and `/og/`,** so X cards likely don't render | S | `server.py:25485`, `web/robots.txt` |
| 9 | **The join redirect strips UTMs on purpose** (test T7). Letting them through reverses a tested contract | H3a | `backend/tests/test_invite_links.py:132-136` (*lead-verified*) |
| 10 | **No public TestFlight link exists** in the repo. Option A needs the operator to create one | H3a | §A open question 3 |
| 11 | **The `/s/*` landing CSS is off-Chalkline:** a 999px pill, a system and Roboto font stack, and a 16px radius with a box-shadow | S | `server.py:25493-25512`, for `design-lead` |

### 0.4 Lead edits to the worker drafts

- **§A:**
  - I added `gp.join.retap`, `gp.join.cta.A_desktop`, `gp.join.cta.A_desktop_help` and `gp.join.android_note`. They're marked *lead-added*.
  - I re-pointed `gp.join.cta.A_other` and `gp.join.cta.B` to desktop only, after the extension finding.
  - I chose the invite-message default (0.1).
- **§B:** I overrode amendment 1 ("Continue on web" for iOS Sleeper users) after the extension finding. I removed a store app ID and used "the operator" in place of gendered pronouns.
- **§C:** I overrode the "C with web sign-in first" recommendation, and noted that "web sign-in preserves attribution" holds only for desktop users who have the extension.
- **S-series: remapped to `growth-pm`'s fixed IDs (2026-10-15).**
  - The fixed IDs:
    - S1: trade-card image
    - S2: `/s/p` package
    - S3: `/s/trade`
    - S4: `/s/tiers`
    - S5: shared `/s/*` chrome
    - S6: send-in-league offers
    - S7: power rankings
    - S8: Year in Review
    - S9: `/u/` profile
    - S10: rating prompt
    - S11: copy-trade text
    - S12: overhaul copy
  - The `/?ref=` root fallback is the last rung of S1/S2.
  - §A's hop column now uses these IDs. Row keys are unchanged, so PRD citations hold.
  - §B and §C keep their workers' local IDs in the prose. Each section opens with a key that maps local → fixed.

## A. Copy table (mkt-writer)


**Brief (provisional):** marketing-lead, wave 2 task 3, plus growth-pm's PRD asks (share message, join landing, inviter pushes) and hop IDs (H1 to H8, with S for `/s/*` landings). Two audiences. The **inviter** is an existing user asking leaguemates to join. The **invitee** is a leaguemate getting a link, usually without the app. The CTA is to open or install, then rank.
**Basis:** all `file:line` refs are at `origin/main` 678834ab. The voice is the assistant-GM register (`docs/business/marketing/2026-07-17-assistant-gm-voice.md`). The name is **Fleeced: Dynasty Trade Finder**, short form **Fleeced** (D-057). Lines whose wording depends on the persona call are marked **O5**.
**Counting:** counts leave out `{vars}`. "+name", "+u" and "+URL" mark the variable part. Invite URLs run 84 chars (legacy `/?league=&ref=`) to 92 chars (`/app/league/join/`), measured with a 19-digit Sleeper id and a 10-char username (assumed typical).
**CTA options:** A is device-aware: iOS goes to the public TestFlight link, every other device goes to web `/`. B is web `/` on every device. C reuses the A/B labels and has no rows of its own. Waitlist/email is dropped, per the PRD.

### Copy table

#### growth-pm asks

| key | hop | surface | current (`file:line` @678834ab) | proposed | limit (count) | voice note | O5? |
|---|---|---|---|---|---|---|---|
| `gp.invite.msg` | H2 | Share-sheet message, no league name | `InviteLeaguematesBanner.tsx:132` "Join me on Dynasty Trade Finder to find trades in ${where} → ${url}" (`where` = name or 'our league', :129) | `Join me on Fleeced to find trades we both like → {url}` | ~140 total: 49 + URL = 133–141 | User's own voice, not the assistant GM. "on Fleeced" marks the product | — |
| `gp.invite.msg_league` | H2 | Same, league name known | same | `Join me on Fleeced to find trades we both like in {leagueName} → {url}` | 52 + name + URL ≈ 155–170, **over** | League name goes last so odd names still parse. The URL is a fixed cost | — |
| `gp.join.page_title` | H3a | Join landing `<title>` (**page does not exist**) | none. `/app/league/join/<id>` 302s to `/` (`server.py:12596-12624`), which serves `web/index.html:6` "Fleeced — Dynasty Trade Finder" | `{leagueName} on Fleeced: Dynasty Trade Finder`; fallback `Your league on Fleeced: Dynasty Trade Finder` | 33+name / 44 | Browser chrome gets the full D-057 name | — |
| `gp.join.og_title` | H3a | og:title | `index.html:11` "Fleeced — Dynasty Trade Finder" (today's preview on every invite) | `{leagueName}: trades that work for both sides`; fallback `Dynasty trades that work for both sides` | ≤60: 33+name (name ≤27) / 39 | Names the league, not the inviter. The bubble already shows the sender, and this keeps URL-supplied `ref` out of previews | — |
| `gp.join.og_desc` | H3a | og:description | `index.html:12` "Rank your dynasty players, compare boards … come out ahead. Free. Works with Sleeper, ESPN, and MyFantasyLeague." | `Rank your players on Fleeced and see trades where both sides come out ahead. Works with Sleeper, ESPN and MFL.` | ≤155: 110 | Drops "Free." (see Claims audit) | — |
| `gp.join.og_site` | H3a | og:site_name | `index.html:10` "Fleeced: Dynasty Trade Finder" | keep | 29 | Already D-057 | — |
| `gp.join.headline` | H3a | Page H1 | none (the web auth card shows "Invited by @${ref}", `web/js/app.js:6415`) | `@{ref} invited you to Fleeced`; fallback `A leaguemate invited you to Fleeced` | 24+ref / 35 | Declarative, no exclamation | O5 |
| `gp.join.valueprop` | H3a | One-line value prop | `index.html:75` "Fleeced finds trades where both sides come out ahead." | `Rank your players, then see trades in {leagueName} where both sides come out ahead.`; fallback uses "your league" | 71+name / 82 | What you do comes first, then the payoff. "Fleeced" is never the subject | O5 |
| `gp.join.cta.A_ios` | H3a | CTA, option A, iOS | none | `Get the iOS beta` | ≤20: 16 | Says what it is: a TestFlight beta | — |
| `gp.join.cta.A_ios_help` | H3a | Helper under the A-iOS CTA | none | `Installs through Apple's TestFlight app.` | 40 | Neutral, system | — |
| `gp.join.cta.A_desktop` | H3a | CTA, option A, desktop (re-pointed by the lead; was `A_other`, all non-iOS) | none | `Open the web app` | ≤20: 16 | Desktop only. Web sign-in needs the Chrome/Edge extension (`web/js/browser-auth.js:1`, `:45`) | — |
| `gp.join.cta.A_desktop_help` | H3a | Helper under the desktop CTA (*lead-added*) | none | `Sign-in uses the Fleeced extension for Chrome or Edge.` | 54 | Neutral, system. Sets expectations before `extension_unavailable` (`browser-auth.js:5`) | — |
| `gp.join.android_note` | H3a | Non-iOS phone: no CTA (*lead-added*) | none | `Fleeced runs on iPhone and desktop web for now.` | 47 | Neutral. Never offer a web button a phone can't sign in through | — |
| `gp.join.retap` | H3a | Under the A-iOS CTA: the re-tap step (*lead-added*; §0.2 amendment 1) | none | `Installed? Go back to the chat and tap the invite again to join {leagueName}.`; fallback `…to join your league.` | 69+name / 78 | Says the next move. The re-tap is a universal link, so it lands on H3b with `league` and `ref` | — |
| `gp.join.cta.B` | H3a | CTA, option B, all devices | none | `Open the web app` | ≤20: 16 | **Lead note:** on phones B dead-ends at sign-in (extension needed; ESPN/MFL "not available yet", `app.js:1263-1264`). Desktop only, in practice. C reuses A's labels | — |
| `gp.push.joined_inbox_title` | H7 | Existing `referral_joined` inbox row, title | `server.py:22662` "@{new_username} joined Fantasy Trade Finder via your invite." (title = body, `database.py:12632-12636`) | `@{new_username} joined Fleeced via your invite` | 32+u | Name rule. "joined Fleeced" can only mean the app. No period, matching `database.py:12237` | — |
| `gp.push.joined_inbox_body` | H7 | Same row, body | Same sentence, rendered a second time (`TopBar.tsx:499-501`) | `Once they rank, trades with them can use their board, not just consensus.` | 73 | Says what changes next. "can", not "will": see D-052 | O5 |
| `gp.push.referral_title` | H7 | **Future** push title (Phase 2, `NEXT.md:532`, GD-5, `trade_matches` bucket) | none | `@{new_username} joined via your invite` | ~40 (guidance, assumed): 24+u, fits if u ≤16 | iOS already shows "Fleeced" as the sender, so the title leaves it out | — |
| `gp.push.referral_body` | H7 | Future push body | none | `Once they rank, trades with them can use their board, not just consensus.` | ~110 (guidance, assumed): 73 | Same line as the inbox body | O5 |
| `gp.push.referral_inbox` | H7 | Future inbox line | none | Reuse `gp.push.joined_inbox_title` and `_body`. Phase 2 adds a push to the existing row, not a second row | — | — | — |
| `gp.inbox.activated_title` | H7 | `referral_activated` bell row, title. Goes to the inviter; inbox only (PRD FR-19). *Added 2026-10-15 at growth-pm's request* | none (new type) | `@{new_username} weighed in on their first trade` *(revised 2026-10-15; was "…has their first trade ideas", which described stage 6)* | inbox: 32 + u (42 with a 10-char name; inbox only, so the ~40 push guidance applies only in Phase 2) | Matches activation at stage 7, first opinion: liked or passed on a trade (PRD FR-17). No ranking claim. No period, like other bell titles (`database.py:12237`) | — |
| `gp.inbox.activated_body` | H7 | Same row, body (distinct from the title, per AC-18's rule) | none | `If they like a trade with you, it can surface in your deck.` | ≤90: 59 | Leaguemates' likes are mirrored into your deck (`server.py:3951-3972`; flag `trade.likes_you` on, `config/features.json:37`). It's capped and quality-gated, hence "can". "Like" is the app's verb (`TradeCard.tsx:836`). No "Fleeced" and no first person, so O5 doesn't apply | — |

#### Hops H1 to H8

| key | hop | surface | current (`file:line` @678834ab) | proposed | limit (count) | voice note | O5? |
|---|---|---|---|---|---|---|---|
| `h1.banner.title` | H1 | Trades cold-start banner | `InviteLeaguematesBanner.tsx:163` "0 of {total} league-mates have ranked" | `0 of {total} leaguemates have ranked` | 29+n | Spelled "leaguemate", as in the voice-spec vocabulary | — |
| `h1.banner.body` | H1 | Same | `:165-167` "Ideas below are fair-value estimates. Real trade matches unlock when league-mates rank their players." | `These trades use consensus values. Mutual matches start once one leaguemate ranks.` | 82 | Opens like voice spec #8. "one" is the literal threshold | O5 |
| `h1.banner.btn` | H1 | Same | `:178` "Invite" | keep | ≤20: 6 | — | — |
| `h1.banner.a11y` | H1 | Same | `:176` "Invite league-mates" | `Invite leaguemates` | 18 | a11y, neutral | — |
| `h1.card.tick` | H1 | League Home invite card | `InviteLeaguematesCard.tsx:90` "Grow your league" | `Who's in` | 8 | "Grow" is growth-team talk. The league isn't growing; turnout is | — |
| `h1.proof` | H1 | Card, Matches, bell | `inviteSocialProof.ts:56` / `:58` / `:60` | keep all three | — | Factual framing locked by the operator (D-P1-13 · PR-5) | — |
| `h1.rationale` | H1 | Card, Matches, bell (shared const) | `inviteSocialProof.ts:25-26` "More boards to trade against means sharper suggestions — and more trades that actually happen." | `Each leaguemate who ranks is one more board to find trades against, beyond consensus.` | 85 | Cuts two claims with no source | O5 |
| `h1.cta` | H1 | 4 buttons | `InviteLeaguematesCard.tsx:99`, `MatchesScreen.tsx:994`, `TopBar.tsx:481`, `LeagueScreen.tsx:1004` "Invite leaguemates" | keep | ≤20: 18 | — | — |
| `h1.progress` | H1 | League progress line | `LeagueProgressModule.tsx:161-163` "{n} more ranked leaguemate… unlocks mutual matches." plus `:143` "Invite them" | keep | — | Leads with a count; accurate (`leagueUnlocks.ts:13`) | — |
| `h1.bell_empty` | H1 | Bell empty state | `TopBar.tsx:469-471` "You're all caught up" / "You'll hear when leaguemates rank players, match a trade, or join." | keep | — | Empty states are where the mascot appears (BRAND.md) | O5 |
| `h1.calc_note` | H1 | In-league calculator | `InLeagueCalculator.tsx:1179-1180` "…Invite them to rank for a two-sided verdict." | keep | — | No tap target (see Notes) | — |
| `h1.web.members` | H1 | Web League panel | `web/index.html:984` "Who has and hasn't joined Trade Finder yet." | `Who has and hasn't joined Fleeced yet.` | 38 | Name rule | — |
| `h1.web.unlock` | H1 | Web League panel | `web/index.html:1004` "Who's joined Trade Finder and how far along they are." | `Who's joined Fleeced and how far along they are.` | 48 | Name rule | — |
| `h1.web.modal` | H1 | Web invite modal | `web/index.html:1089` "Invite your league" | keep | 18 | — | — |
| `h2.web.default` | H2 | Web invite message | `web/js/app.js:5834` "Join me on Dynasty Trade Finder to find trades in ${leagueName} → ${url}" | `= gp.invite.msg_league` (or `gp.invite.msg` when `:5833` falls back to 'our league') | see gp rows | Name rule | — |
| `h2.web.sms` | H2 | Web SMS channel | `app.js:6082` "${leagueName} fantasy trade finder — join me: ${url}" | `= gp.invite.msg_league` | see gp rows | Old name in lowercase | — |
| `h2.web.x` | H2 | Web X channel | `app.js:6086` "Joined @FantasyTradeFinder to find trades in ${leagueName}. Come ruin the league with me: ${url}" | `Finding dynasty trades in {leagueName} on Fleeced. Join me → {url}` | 49+name+URL | Cuts a handle in the old name that no evidence says exists | — |
| `h2.web.chat` | H2 | Web WhatsApp, Telegram | `app.js:6089`, `:6095` "Hey! Been using Fleeced for ${leagueName} — it finds trades both sides actually like. Join me: ${url}" | `Been using Fleeced for {leagueName}. It finds trades that work for both sides. Join me → {url}` | 77+name+URL | Drops the exclamation, and drops "actually like" (a prediction) | — |
| `h2.web.groupme` | H2 | Web GroupMe | `app.js:6092` "yo who's tired of \"What you want for X?\" — try this: ${url}" | `Tired of "what you want for X?" Join me on Fleeced → {url}` | 53+URL | Keeps the in-joke and adds the name the old message lacked | — |
| `h2.web.email` | H2 | Web email body | `app.js:6105` "Takes about 5 minutes to set up. Give it a shot:" (lines 6102-6108 otherwise keep; subject `:6098` keep) | `Give it a look:` | 15 | The time claim has no source, so it's cut | — |
| `h2.web.sleeper` | H2 | Web Sleeper and default | `app.js:6112`, `:6118` "Join me on Fleeced for ${leagueName}: ${url}" | keep | 26+name+URL | — | — |
| `h3a.index_title` | H3a | **Today's** invite preview (`/` OG) | `web/index.html:6`, `:11` "Fleeced — Dynasty Trade Finder" | `Fleeced: Dynasty Trade Finder` | 29 | Exact D-057 form (colon). Keeps the current preview right until the join page ships | — |
| `h3a.web.invited` | H3a | Web auth card | `app.js:6415` "Invited by @${ref}" | keep | 12+ref | — | — |
| `h3b.join.loading` | H3b | LeagueJoin | `LeagueJoinScreen.tsx:134` "Joining {cachedName or 'your league'}…" | keep | 9+name | Transactional | — |
| `h3b.join.fail` | H3b | LeagueJoin error | `:118` "We couldn't open that invite. Pick a league to keep going." | `That invite didn't open. Pick a league to keep going.` | 53 | No "we". Says what failed and the next move | — |
| `h3b.join.fail_cta` | H3b | Same | `:122` "Choose a league" | keep | ≤20: 15 | — | — |
| `h4.picker.notice` | H4 | LeaguePicker | `LeaguePickerScreen.tsx:569-570` "You're not in that league yet — pick one below, or join it on your fantasy platform and open the invite again." | keep | 110 | Has to stay platform-neutral (`:561-566`) | — |
| `h4.picker.empty` | H4 | LeaguePicker empty, invited | `:507-508` "@{inviteBy} invited you to {inviteName or 'their league'}. Connect Sleeper, ESPN or MFL to join." | keep | — | — | — |
| `h5.signin.invite` | H5 | SignIn banner | `SignInScreen.tsx:230-231` "@{invitedBy} invited you to {league or 'their league'} — sign in and we'll take you straight there." | `@{invitedBy} invited you to {league}. Sign in to go straight there.` | 48+vars | Drops "we'll" (voice: no first-person plural) | — |
| `h5.signin.invite_noref` | H5 | Same, no inviter | `:233-234` "You were invited to {league} — sign in and we'll take you straight there." | `You're invited to {league}. Sign in to go straight there.` | 49+league | Same | — |
| `h6.web.logo` | H6 | Web app header | `web/index.html:379` "Dynasty <span>Trade Finder</span>" | `Fleeced` (wordmark as `index.html:54`) | 7 | "Dynasty Trade Finder" on its own breaks the name rule | — |
| `h6.web.rm_logo` | H6 | Web ranking-method screen | `web/index.html:331` same | `Fleeced` | 7 | Same | — |
| `h7.peer.push` | H7 | `league_member_joined` push (the inviter gets it too) | `server.py:22709-22712` "@{u} joined {league_name}" / "…your league"; body `:22712` "A new leaguemate can mean new trade matches." | keep | 9+vars / 44 | Already in voice, hedged honestly | — |
| `h7.peer.inbox` | H7 | Same, coalesced inbox | `database.py:12237-12241` | keep | — | — | — |
| `h8` | H8 | Measurement | — | no copy | — | — | — |

#### Share surfaces (growth-pm's fixed S-IDs)

The hop column uses `growth-pm`'s fixed IDs (2026-10-15):
- S1: the trade-card image
- S2: the `/s/p` package
- S3: `/s/trade`
- S4: `/s/tiers` (dark)
- S5: the shared `/s/*` chrome
- S11: the copy-trade text

Row keys keep their original names, so the PRD's citations still hold. The key prefix `s0`–`s4` is a legacy label, not the ID. The `/?ref=` root fallback is the last rung of S1/S2, not its own ID.

| key | hop | surface | current (`file:line` @678834ab) | proposed | limit (count) | voice note | O5? |
|---|---|---|---|---|---|---|---|
| `s0.image.mark` | S1 | Share-image footer | `ShareTradeImage.tsx:255` "Dynasty Trade Finder" | `Fleeced: Dynasty Trade Finder` | 29 | "Dynasty Trade Finder" alone breaks the name rule | — |
| `s0.image.btn` | S1 | Same | `:235` "Share image" | keep | 11 | — | — |
| `s0.trades.msg` | S2, S3 | Trades share message | `TradesScreen.tsx:5328-5330` "…Found on Fantasy Trade Finder — {url}" | `Trade idea for our league: I send {give}, get {recv} from @{opp}. Found on Fleeced → {url}` | 68+vars | Brand token changes; nothing else | — |
| `s0.calc.cap` | S2 | Calculator caption and text | `TradeCalculatorScreen.tsx:560`, `:1049` "Trade idea (DTF Trade Calculator · {fmt})" | `Trade idea (Fleeced trade calculator · {fmt})` | 40+fmt | "DTF" is internal | — |
| `s0.inleague.cap` | S2 | In-league share text | `InLeagueCalculator.tsx:1568` "Trade idea vs @{opp} (Dynasty Trade Finder · {fmt})" | `Trade idea vs @{opp} (Fleeced · {fmt})` | 28+vars | Name rule | — |
| `s0.proposal.sig` | S11 | Copied proposal text | `tradeText.ts:105` "(Built with Fantasy Trade Finder)" | `(Built with Fleeced)` | 20 | Name rule | — |
| `s1.trade.title` | S3 | `/s/trade` og:title and H1 | `server.py:25555` "Trade Match" | `A dynasty trade both sides liked` | ≤60: 32 | Says what a mutual match is in plain words | — |
| `s1.trade.desc` | S3 | og:description and body | `:25556` "A dynasty fantasy trade — see the give/get breakdown and fairness verdict." | `Two leaguemates each said yes to this trade. See the give/get breakdown and the fairness read.` | ≤155: 94 | — | — |
| `s1.trade.cta` | S3 | CTA, A-other and B | `:25562` "Find your next trade" | keep | ≤20: 20 | — | — |
| `s2.pkg.title` | S2 | `/s/p` og:title and H1 | `:25664` "Trade Package" | `Dynasty trade idea` | ≤60: 18 | "Package" is engine language. Matches the "Trade idea" share text | — |
| `s2.pkg.desc` | S2 | og:description | `:25665-25666` "A {n}-player dynasty trade package — see the give/get breakdown and fairness read." | `A {n}-player dynasty trade. See the give/get breakdown and the fairness read.` (when n=1: `A one-player dynasty trade. …`) | ≤155: 74+n / 77 | — | — |
| `s2.pkg.cta` | S2 | CTA, A-other and B | `:25668` "Build your own trade" | keep | ≤20: 20 | — | — |
| `s.cta.A_ios` | S2, S3 | CTA, option A, iOS | none (all S CTAs go to `/`, `:25548`, `:25563`, `:25669`) | `Get the iOS beta`, plus helper `Installs through Apple's TestFlight app.` | ≤20: 16 / 40 | The destination changes, so the label has to change with it | — |
| `s3.tiers` | S4 | `/s/tiers` (dark) | `:25537`, `:25539`, `:25547` | keep; no work. The surface is dark (`config/features.json:188`, D-P1-12) | — | — | — |
| `s4.title` | S5 | Wrapper `<title>` | `server.py:25479` "{title} · Fantasy Trade Finder" | `{title} · Fleeced: Dynasty Trade Finder` | 32+title | Name rule | — |
| `s4.brand` | S5 | Wrapper footer | `:25512` "Fantasy Trade Finder" | `Fleeced: Dynasty Trade Finder` | 29 | Tagline left out on purpose (see Notes) | — |
| `s4.og_site` | S5 | og:site_name (new tag) | absent (`:25482-25491`). og:title carries no brand today | `Fleeced: Dynasty Trade Finder` | 29 | Puts the name on every `/s/` preview | — |
| `s4.og_footer` | S5 | OG PNG footer | `og_image.py:171` "Fantasy Trade Finder · fantasy-trade-finder.onrender.com" | `Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com` | 65 | 22px font on a 1080px rule (`:172-173`). Fits, assumed | — |

### Notes

**Neutral and transactional strings, kept plain under the voice spec ("where the voice does not apply"):** a11y labels, page `<title>`s, og:site_name, the OG footer and watermark, the TestFlight helper line, LeagueJoin's loading line, the LeaguePicker notices, and the social-proof sentence (operator-locked factual framing). The voice spec counts errors as voiced ("name what failed"), so `h3b.join.fail` was rewritten; it carries no persona, so it isn't marked O5.

**Changes forced by the name rule (old names in user copy):**
- Mobile: `InviteLeaguematesBanner.tsx:132`, `ShareTradeImage.tsx:255`, `TradesScreen.tsx:5329`, `TradeCalculatorScreen.tsx:560` and `:1049` ("DTF"), `InLeagueCalculator.tsx:1568`, `tradeText.ts:105`.
- Backend: `server.py:22662`, `:25479`, `:25512`, `og_image.py:171`.
- Web: `app.js:5834`, `:6082`, `:6086`; `index.html:331`, `:379`, `:984`, `:1004`.

**Old names outside the loop (reported, not rewritten):** `ClaimSheet.tsx:72/79/86`, `DraftRoomScreen.tsx:830`, `PickAssignmentScreen.tsx:1136` ("Fantasy Trade Finder can't…") and `useFeedback.ts:269` ("DTF Mobile Feedback", operator-facing).

**Ambiguity rule as applied:** "Fleeced" only appears as an object or after a preposition: "on Fleeced", "joined Fleeced", "invited you to Fleeced", "Built with Fleeced". It is never the subject of an analysis verb, because the ram plays "The Analyst" (BRAND.md §Mascot). No line reads "I'm … Fleeced". The tagline "Don't get fleeced." stays off the `/s/*` footer: under someone's shared trade it reads as a verdict that they got fleeced.

**Interpolated templates. Variables are unchanged and only the literal text moves:**
- Invite message: `shareInvite()` `args.leagueName` and `url`. Use `gp.invite.msg_league` when a league name is present and `gp.invite.msg` otherwise. This replaces the `'our league'` fallback at `:129`.
- SignIn: `invitedBy` and `invitedLeagueName`, keeping the `'their league'` fallback.
- LeagueJoin: `cachedName`.
- Pushes: `new_username` (from `username or display_name or user_id`, `server.py:22658`), plus `league_name` on the peer push.
- `/s/p`: `n` (`server.py:25662`), with a separate literal for n=1.
- Join landing (new page): `{leagueName}` and `{ref}`. Show the fallback when the name is null: `invite-meta` resolves Sleeper names only (`server.py:26445-26483`) and returns null for ESPN/MFL.

**The domain can't be fixed in copy.** `fantasy-trade-finder.onrender.com` shows the internal name in every invite URL, the share-card footer (`ShareTradeImage.tsx:263`) and the OG PNG footer. The custom domain is still outstanding under D-057.

**H6 has no referral-specific string.** The invitee's first-value copy is the voice spec's 15 lift-verbatim strings.

### Claims audit

| claim in proposed copy | source |
|---|---|
| "trades we both like" / "both sides liked" / "each said yes" (mutual match = both said yes) | `MatchesScreen.tsx:1016`. `/s/trade` serves mutual matches only: `server.py:25571` |
| "trades where both sides come out ahead" / "work for both sides" | Shipped product line, `web/index.html:7`, `:12`, `:75`. Mutual-gain trade discovery (CLAUDE.md) |
| "Works with Sleeper, ESPN and MFL" | `config/features.json:110` (`espn.link`), `:117` (`mfl.link`), Sleeper core. Caveat: browser sign-in is Sleeper only (`app.js:1264`) |
| "Mutual matches start once one leaguemate ranks" | `leagueUnlocks.ts:13` `MATCH_UNLOCK_MATES = 1`; `:15-18` |
| "These trades use consensus values" (no leaguemate ranked) | `InviteLeaguematesBanner.tsx:9-12`; voice spec #8 |
| "one more board to find trades against, beyond consensus" / "trades with them can use their board" | `InviteLeaguematesBanner.tsx:9-12` (the divergence engine needs a ranked counterparty). The hedge "can" exists because ranked members can still get consensus cards (D-052, behind a dark flag) |
| "@x joined via your invite" | Fires on the new user's first session with `invited_by`: `server.py:22648-22662` |
| "Get the iOS beta" | The iOS app is TestFlight-only (CLAUDE.md; brief). A **public TestFlight link does not exist in the repo** (no `testflight.apple.com` hit), so this is assumed until the operator makes one |
| "Installs through Apple's TestFlight app" | **Assumed** (Apple platform behavior; no repo source) |
| "{n}-player" / "give/get breakdown and the fairness read" | `server.py:25662`, `:25665-25666` (existing copy) |
| **CUT** "Free." (og:description) | True today, since all `monetize.*` flags are off (`features.json:141-148`). But crawled previews outlive a paywall flip, so it doesn't belong in durable OG text |
| **CUT** "sharper suggestions", "more trades that actually happen" | No an-* measurement. The operator direction (D-P1-13 · PR-5) is a framing, not a result |
| **CUT** "@FantasyTradeFinder" | No evidence the account exists, and it uses the old name |
| **CUT** "Takes about 5 minutes to set up" | No source |

### Open questions

1. **O5 (operator).** Rows marked O5 are written for the neutral assistant GM. If the ram speaks in first person, those rows need a second pass, and none of them may read "I'm Fleeced".
2. **Audit decision 4: does option B dead-end on phones?** ESPN/MFL browser sign-in shows "not available … yet" (`app.js:1263-1264`), and web Sleeper sign-in is built around a desktop browser extension (`index.html:167-170`). Does B work at all for a phone invitee, and does "Open the web app" over-promise there? → growth-pm, eng-web.
3. **Option A needs a public TestFlight link.** None exists in the repo; the operator has to create one. The tester cap is assumed, not checked.
4. **The join landing is a new page.** Today every invite preview is the generic `/` OG. H3a needs a server-rendered OG page on `/app/league/join/<id>`, plus the legacy `/?league=` path, using the Sleeper-public name lookup (`server.py:26445`). → eng-backend.
5. **`ref` comes straight from the URL.** Anyone can craft a link with any `ref` text. The proposed headline echoes it, as the web (`app.js:6415`) and SignIn (`SignInScreen.tsx:230`) already do. It is kept out of OG and `<title>` on purpose. Is that enough? → eng-security.
6. **The `referral_joined` row shows its sentence twice.** `push_notification()` sets title = body (`database.py:12632-12636`) and TopBar renders both. A separate body needs a code change. → eng-backend.
7. **The inviter gets two notifications.** The inviter is a joined peer, so they get the `league_member_joined` push and row (`server.py:22699-22718`) on top of `referral_joined`. Phase 2 should dedupe for the inviter. → mkt-lifecycle, pm-retention.
8. **Push title length.** `@{u} joined via your invite` stays ≤40 only when u ≤16. The Sleeper username length cap is unknown (assumed ≤20).
9. **The share message runs over.** `gp.invite.msg_league` comes to ~155–170 chars with the URL. Accept it (iMessage turns the URL into a card), or ship the league-less line everywhere? → growth-pm.
10. **The in-league calculator note has no invite button.** It says "Invite them to rank" (`InLeagueCalculator.tsx:1179`) with no tap target. Is that a missing H1 entry point? → pm-growth.
11. **The `referral_activated` row will usually arrive right after the join row** *(added 2026-10-15)*. Onboarding targets a first card in under 60s (`docs/plans/onboarding-conversion/plan.md:85`), so the joined and activated rows will usually land together. Options:
    - delay the activation row;
    - move activation to stage 5 (`ranking_complete_first_time`). That changes the title to a ranking line, and it then overlaps `league_member_unlocked_trades` (`server.py:10526-10560`), so dedupe the two.
    → growth-pm, analytics-lead.
12. **Replenish decks count as activation.** The weekly replenish cron emits the same `trades_generated` with no user present (`server.py:9228-9231`, `:23865`). FR-17 should probably ignore `deck_source == "replenish"`. The copy says "has", not "pulled" or "saw", so it holds either way. → growth-pm.
13. **The route doesn't match the body.** The body points to the deck, but AC-19 sends the tap to League (`deepLinks.ts:306-312`). Either route it to Trades or accept the mismatch. → growth-pm, design-lead.
14. **The row needs `new_username` in its meta.** The PRD's `referral_activated` event props don't carry it (`prd.md:660`). → growth-pm.
15. **Another old-name string, next to this row:** `league_member_unlocked_trades` says "@X just unlocked Trade Finder." (`server.py:10542`, lead-verified). Add it to the FR-3 name sweep. → growth-pm.

### Addendum: design-lead's lab slots and growth-pm's four questions (2026-10-15)

Source: `growth-pm`'s questions on the lab, `mockups/referral-loop/index.html` (`design-lead`, draft PR #343, branch `mockup/referral-loop`). The strings are `mkt-writer` drafts, accepted by `marketing-lead` with one lead rewrite (A2). They're **proposed** and need the operator's approval like the rest of §A.

**Lead answers:**
1. **FR-11 as the landing headline: yes.** `{display name} invited you to {league}` works, because token-only links mean the inviter is resolved server-side and can't be supplied by the URL. It supersedes `gp.join.headline` ("@{ref} invited you to Fleeced"). The "their league" fallback reads correctly on line 2: it is the inviter's league. The FLEECED wordmark carries the product name above the fold, so the headline doesn't need it. Fallback ladder:
   - `{display name} invited you to their league`
   - `A leaguemate invited you to {league}` (the A5 "…to {league}" form)
   - `A leaguemate invited you`
2. **"Dynasty Trade Finder" on the invite OG card: yes, as a lockup only.** It goes directly with the FLEECED wordmark, smaller than it. Together they read as D-057's full name. Never standalone (AC-3 still bans it in share text, where it reads as an old brand). Never on its own line away from the wordmark: DLF has a product called "Dynasty Trade Finder". **No period in the wordmark.** "FLEECED." turns the name into a sentence, and on any surface showing a trade it reads as a verdict ("you got fleeced"). The lab draws `FLEECED` without one (line 625), which is right.
3. **Spelling: "leaguemates"**, one word. That's the voice spec's form (`2026-07-17-assistant-gm-voice.md:29`), and it outnumbers "league-mates" 265 to 29 in `mobile/src` + `web` at `origin/main`. The banner changes, per `h1.banner.title` / `h1.banner.a11y`.

**Slot fills:**

| slot | lab line | proposed | chars | note · source |
|---|---|---|---|---|
| A2 honest note (iPhone, public TestFlight link not set) | 419 | `The iPhone beta isn't open to the public yet. Already have it? Open the invite in the app.` | 88 | **Lead rewrite.** The worker's "invite-only" would confuse a reader who is holding an invite. "Open in the app" is real: `dtf://app/league/join/:leagueId` → LeagueJoin (`deepLinks.ts:119`, `:243`). Older builds ignore `t=`, so credit falls back to the league match. No "Request TestFlight access" link in v1, per `growth-pm` |
| OG (iii) line, under the league name | 625 | `Trades that work for both sides` | 31 | Same words as `gp.join.og_title`. No "Fleeced" and no analysis verb |
| og:title, league known | previews | `{leagueName}: trades that work for both sides` | 33 + name | `gp.join.og_title`, unchanged. If the name runs over 27 chars: `{leagueName}` alone, cut at 59 + "…" (PRD AC-7b) |
| og:title fallback | previews | `Dynasty trades that work for both sides` | 39 | Unchanged |
| §5 label 1 | 734 | `All leagues` | 11 | The tiles are totals (FR-21 `totals`). Renders uppercase |
| §5 label 2 | 742 | `By league` | 9 | FR-21 `leagues[]` |
| "Activated" explainer | 741 | `Activated: joined from your link, then liked or passed on a trade within 14 days.` | 81 | Literal stage-7 definition (PRD FR-17, `first_opinion`). If D-8 moves the stage, this string moves with it |
| Zero-join league line | 744 | `No joins yet`; when opens ≥ 1: `{N} opened · no joins yet` | 12 / 22 + N | The number is literal. The chevron is the next step |
| Empty-state prompt, in place of the four tiles | 767 | `No invite links yet. Send one and its opens, joins and activations show up here.` | 80 | Counts only, never "who": the payload has no names (§8.5) |

**Flags from this pass** (→ `growth-pm`, `design-lead`):
- **The lab's landing sub-line breaks the name rule.** A1–A6 use "Fleeced finds trades where both sides come out ahead." (`web/index.html:75`), which makes Fleeced the subject of an analysis verb (the ram plays The Analyst). Use `gp.join.valueprop` instead. The shipped `index.html:75` should go into the FR-3 name sweep.
- **The FAQ claim is false:** `web/faq.html:206` says the web app "works in any phone browser", but web sign-in needs the desktop extension. A2's footer links to that FAQ. Fix it with the landing.
- **The desktop path has a hidden install step.** The extension is an unpacked GitHub release, not a store listing (`extension/README.md:44`). `gp.join.cta.A_desktop_help` is accurate, but few desktop invitees will sideload it. That makes iOS TestFlight even more clearly the main path under A.
- **The activation title is revised to stage 7** (see the `gp.inbox.activated_title` row).
- **`/contact.html` can't take a TestFlight request** (bug/idea/polish/data topics, no email field, `contact.html:71-90`). That's moot for v1. If the link returns, add a TestFlight topic and an email field first.

## B. Channel plan (mkt-partners)


> Distribution plan for the invite loop (H1–H8) and the trade-share loops (S1–S4). Code was read at `origin/main` 678834ab. **[assumed]** means *assumed (general knowledge, unverified)*: there was no web access, so every outside-platform claim carries that tag. Nothing here is a measured number.

> **S-ID key (lead, 2026-10-15).** This section uses its own local IDs. Map them to `growth-pm`'s fixed series like this:
> - local S1 `/s/trade` → **S3**
> - local S2 `/s/p` → **S2**
> - local S3 `/?ref=` root → the **last rung of S1/S2** (not its own ID)
> - local S4 the iOS trade image → **S1**

Share loops (local IDs): **S1** `/s/trade/<match_id>` · **S2** `/s/p/<short_id>` · **S3** `/?ref=<u>` root fallback · **S4** the iOS trade image (ShareTradeImage).

### Where invites and shares travel

**What the app sends (H1–H2).** There are five invite surfaces: `league_home`, `matches_empty`, `trades_banner`, `members_overlay` and `notif_empty` (`mobile/src/components/InviteLeaguematesBanner.tsx:70-75`). All five go through one call, `Share.share({ message })`, with no `url` field. The text is `Join me on Dynasty Trade Finder to find trades in <League> → <url>` (`InviteLeaguematesBanner.tsx:131-133`). The URL is the legacy `https://fantasy-trade-finder.onrender.com/?league=<id>&ref=<user>`, because `growth.invite_join_link` is false (`config/features.json:190`, builder at `InviteLeaguematesBanner.tsx:56-65`). The share loops send:
- S1, S2 and S3 come from Trades: `Trade idea for our league: … Found on Fantasy Trade Finder — <url>` (`mobile/src/screens/TradesScreen.tsx:5326-5331`).
- The calculator sends `Trade idea (DTF Trade Calculator …)` plus a `Build your own: <url>` line (`TradeCalculatorScreen.tsx:560-605`).
- On iOS, S4 sends the image plus the message, and the URL is also printed on the image (`ShareTradeImage.tsx:24, :144`).

The web app has a per-channel share grid: SMS, WhatsApp, Telegram, X intent, GroupMe, and Sleeper (copy the link, then nudge `sleeper://`) (`web/js/app.js:6173-6205`).

| Channel | How a Fleeced link gets there today | What the recipient sees | Opens the app if installed? | Norms |
|---|---|---|---|---|
| **Sleeper league chat** (the inviter's own league) | iOS share sheet if Sleeper offers a share target **[assumed]**, otherwise copy-paste. Web says outright "Copied — open Sleeper and paste" (`app.js:6189-6205`). | Unknown whether Sleeper chat unfurls OG tags **[assumed/unverified]**. Plan for a bare, long link: `onrender.com/?league=<19-digit id>&ref=…` | Uncertain. A link tapped inside a chat app may open an in-app browser that never hands off to universal links **[assumed]**. | It's the inviter's own league, so no promo rules apply. Etiquette still does: one invite, framed around trades in *this* league, not repeated. |
| **Group text / iMessage / GroupMe** | Share sheet → Messages natively. GroupMe through the share sheet **[assumed]**. | iMessage builds a preview from OG tags **[assumed]**. The invite URL is served the static `/` page (`backend/server.py:12579-12581`), so the preview reads "Fleeced — Dynasty Trade Finder" with **no og:image** and `twitter:card summary` (`web/index.html:9-14`). That's a text-only card with no league and no inviter. | Yes. The AASA file claims `/?league=*` and `/?ref=*` (`server.py:12672-12677`), and Messages honors universal links **[assumed]**. | Private. Best experience of all the channels. |
| **ESPN / MFL league chat or message board** | Copy-paste only **[assumed: no share target]**. | A bare link is likely **[assumed]**. On web, the ESPN and MFL chips dead-end at "Continue in the Fleeced app · Request TestFlight access → /contact.html" (`app.js:1262-1265`, `index.html:263-267`). | Same uncertainty as Sleeper chat. | Same as the Sleeper row. |
| **League Discord server** | Share sheet (Discord has a share extension **[assumed]**) or paste. | Discord embeds og:title, description and image **[assumed]**. The invite shows as a text-only embed. S2/S1 images use a *relative* og:image (`server.py:25485`, fed `"/og/p/<id>.png"` at `:25667`), which may not resolve **[assumed]**. | Uncertain. Links open in a browser and the universal-link hand-off is unknown **[assumed]**. | Server rules vary. Usually a "#promo" or "tools" channel exists **[assumed]**. |
| **X** | Share sheet or the web intent (`app.js:6173`). | Twitterbot honors robots.txt **[assumed]**, and `web/robots.txt` disallows `/s/` and `/og/`. So **S1 and S2 cards likely render as bare links on X**. Invite links aren't blocked but have no image. | n/a | Invites don't belong here (they're league-scoped). Trade cards are fine as content. If the operator posts, they disclose that they built the app. |
| **r/DynastyFF** | Operator posts only. This is an acquisition seed, **not** an invite channel. | A thumbnail from og:image **[assumed]**. | n/a | **[assumed]** Self-promo is restricted and often confined to designated threads. Disclose as the developer, lead with value (data or analysis), and read the sidebar before every post. |

**What the OG card must survive** (feeds growth-pm's PRD):
1. **A bare link** (Sleeper/ESPN/MFL chats, unverified **[assumed]**). Here the *message text is the card*. Put the league name and the payoff in roughly the first 60 characters. The URL is long and on onrender.com, which reads as unbranded **[assumed trust cost]**. The open question is whether the copy beats that.
2. **A title-only or small card** (iMessage without an image, Discord text embed, X `summary`). og:title is the entire pitch. Keep it to about 60 characters with the hook in the first ~40 (truncation varies by client **[assumed]**). Today it's the generic site title.
   - For Sleeper invites, `/api/league/invite-meta` already resolves a public league name with no privacy leak (`server.py:26446-26482`). That's enough for "@ref invited you to <League>".
   - ESPN and MFL names are deliberately null there, so those links need a fixed fallback title.
3. **An image card** (iMessage, Discord, WhatsApp, Reddit, X `summary_large_image`).
   - Keep 1200×630 (already declared at `server.py:25486-25487`) and make it legible at thumbnail width.
   - Keep the key content center-safe for square crops **[assumed]**.
   - Use an **absolute** og:image URL (the OG spec expects one **[assumed]**).
   - Don't block the image path from X's crawler.
   - The invite link has **no image at all** today.
4. **One brand name.** The preview says "Fleeced" (`index.html:11`), but the same thread can also show:
   - "Dynasty Trade Finder" (invite text, `InviteLeaguematesBanner.tsx:132`; image watermark, `ShareTradeImage.tsx:255`)
   - "Fantasy Trade Finder" (`/s/` `<title>`, `server.py:25479`; OG footer, `backend/og_image.py:171`; trade text, `TradesScreen.tsx:5329`; inviter push, `server.py:22662`)
   - "DTF Trade Calculator" (`TradeCalculatorScreen.tsx:560`)

   Several different names on one link looks like a phishing link. D-057 says the user-facing name is Fleeced.

### Before the App Store listing

**Posture: closed loop, league-scoped, value-first. No public broadcast of an install link.**
- **Lead with invites from a league the inviter already plays in.** That's the five H1 surfaces. The pitch is the inviter's own payoff: matches unlock when leaguemates rank (`InviteLeaguematesBanner.tsx:162-167`). Every recipient already knows the sender, so trust is solved before the link is even tapped.
- **Run trade-card shares into the league chat around the deadline (S1, S2, S4).** Every share carries a link (`mobile/src/utils/shareLinks.ts:106-155`). A trade idea addressed to a specific leaguemate (`@opponent`) is the most natural way to get a chat to tap.
- **Pick shares degrade.** Packages with draft picks fall back to S3 (`shareLinks.ts:128-129`). That matters more in rookie season (see the calendar).
- **Treat r/DynastyFF and X as operator-only and optional before launch.** One disclosed, value-first post per community at most. No creator push until the listing exists: creator audiences hit the TestFlight friction below at scale, and their clicks can't be attributed.
- **TestFlight friction** (all **[assumed]**):
  - The recipient installs the TestFlight app first, then Fleeced: two installs.
  - Public links have a tester cap (about 10,000).
  - External builds need Beta App Review.
  - Builds expire about 90 days after upload, so a public link must always point at a live, reviewed build.
  - There's no Android build.
- **No public TestFlight link exists today.** The repo has none, and the web iOS path is "Request TestFlight access" → `/contact.html` (`index.html:266`). Per `web/CLAUDE.md`, that form posts to `/api/feedback`, so every tester is added by hand.
- **Fix order on the distribution side:**
  1. One brand name in all share text.
  2. A league-named title and an image on the invite preview (Sleeper).
  3. The chosen CTA at H3a.

### After the listing

- **The CTA becomes the App Store listing.** `ascAppId` (`mobile/eas.json:21`) is presumably the store ID **[assumed]**. Add campaign links (`pt`/`ct` tokens) per surface and season. They report in App Analytics as aggregates and nothing reaches the app **[assumed]**, so per-league credit still depends on the re-tap (CTA section).
- **Add a smart app banner.** Put `<meta name="apple-itunes-app" content="app-id=…, app-argument=<url>">` on `index.html` and the `/s/` pages. None exists today (git grep found no match). It shows in Safari only **[assumed]**.
- **Point the `/s/` landings at the listing.** Today S1 and S2 use `cta_url="/"` (`server.py:25563, 25669`) and drop the `?ref=` they arrived with, so a visitor who isn't installed is unattributed at the click.
- **Open the public channels.** Creators and podcasts (the mkt-partners pipeline), a disclosed r/DynastyFF launch post, and X. That's only worth doing after the X card fix (robots.txt).
- **Seasonal pushes** follow the calendar below.

### CTA target — recommendation per option

**Every option shares the same start and the same installed path.**
- **H1–H2:** five surfaces, then `shareInvite`, then the legacy URL.
- **H3b (installed):** the universal link opens the app. `handleDeepLink` captures `ref` (`deepLinks.ts:401`) and `league` (`:418-430`) and emits `invite_link_opened` (`:426`). LeaguePicker auto-pins. `session_init` carries `invited_by` (`mobile/src/api/auth.ts:514, :607`). The inviter gets `referral_joined` (`server.py:22653-22673`).

The CTA choice only changes **H3a onward** (link opened, app not installed).

**Attribution facts that apply to all three options:**
- **Two mechanisms, and only one is league-scoped.**
  - League-scoped: `league_member_joined` notifies every joined leaguemate on the new user's first session, whether or not they had a ref (`server.py:22699-22718`). So the inviter *hears* "@x joined <League>" through league membership.
  - Credit by username: the `invited_by` column, `referral_joined` and `/api/invite/impact` all key on the username (`server.py:26239-26241`). They need `ref` to survive all the way to `session_init`.
- **`invited_by` only travels on the Sleeper `session_init` payloads.** The two sites are `auth.ts:514` and `:607`. I found no ESPN or MFL emitter, so **ESPN/MFL joins never credit the inviter today**.
- **Web H3a is unmeasured.** `invite_link_opened` is mobile-only; git grep found no web emitter.

| | **A — device-aware: iOS → TestFlight, else → `/`** (growth-pm's pick) | **B — `/` for everyone** (status quo, D-173 Companion) | **C — B until the listing, then the store** |
|---|---|---|---|
| **H3a — what the recipient sees** | **iOS:** Safari opens `/?league&ref`, then needs a new iOS branch showing the TestFlight CTA. **Elsewhere:** same as B. | `/` with "Invited by @ref" (`app.js:6408-6417`) and the generic preview. | Before the listing it's B. After it, the store page plus a smart banner. |
| **H4–H5 — join and sign-in** | **After a TestFlight install the app cold-opens with no league and no ref.** Web stored them in Safari localStorage (`app.js:6390-6403`), which the app can't read. Result: no "@X invited you to <League>" headline (`SignInScreen.tsx:229`) and no auto-pin. | **Sleeper:** works. Auto-select (`app.js:436-441`), and `invited_by` is sent (`app.js:810`). **ESPN/MFL:** **dead end**, the contact form described in §1. | Before the listing it's B. After it, the same cold-open loss as A, minus the TestFlight step. |
| **H6–H7 — first value, inviter told** | iOS path: the inviter is notified through the league path, but `referral_joined` and the credit are lost unless the recipient re-taps the link. | **Sleeper:** full credit, the best of the three options. **ESPN/MFL:** none. Web is companion-grade (D-173), allowed to lag the app. | B, then A-like. |
| **What breaks** | The two-install flow. The cap, review and expiry **[assumed]**. Credit is lost without a re-tap step. | Every ESPN/MFL invitee. iOS Sleeper invitees get the lesser web product. | Same as B, with **no end date**: the listing date is unknown. |
| **Surfaces to build** | Public TestFlight link (operator, in App Store Connect). An iOS-plus-league branch on `/`: legacy links land there, and `/app/league/join` only 302s to it (`server.py:12596-12624`). A re-tap step. A web H3a event. | None. | B now. Store link, smart banner and campaign links later. |
| **My call (pre-listing)** | **Yes, with two amendments (below).** | Acceptable for Sleeper. Fails ESPN/MFL. | The right end state, but "wait" isn't a pre-listing plan. |

**Amendments to A.**

> **Lead override (marketing-lead):** amendment 1 is **withdrawn.** Web Sleeper sign-in requires the desktop browser extension (`web/js/browser-auth.js:1`, `:45`; `app.js:334`), so "Continue on web" fails on a phone. Amendment 2 (the re-tap step) stands. See §0.2 for the amendments that replace it.

1. ~~**Make it platform-aware as well as device-aware.**~~ *(withdrawn, see above)* On iOS, if `invite-meta` resolves the league (that means Sleeper, `server.py:26482`), show TestFlight as the primary CTA and "Continue on web" as secondary: web is one step and fully credited for Sleeper. If it doesn't resolve (ESPN/MFL), show TestFlight only, since web dead-ends them.
2. **Ship the re-tap step in the same change.**
   - Landing copy: "Installed? Go back to the chat and tap the invite again." The re-tap is a universal link, which puts the user on H3b.
   - Optionally, a `dtf://?league=<id>&ref=<u>` button. The `dtf` scheme is declared at `mobile/app.json:8`, and `handleDeepLink` reads the query from any prefix.
   - The button can't be an https link to our own domain: a same-domain tap in Safari doesn't trigger universal links **[assumed]**.

**Overall pick: A, amended.** TestFlight is the only install path that exists. It's the only route at all for ESPN/MFL invitees. And the trade-deadline window is now, so this can't wait for a listing date nobody has.
- **Where I differ from growth-pm:** a pure device split sends iOS Sleeper users away from a one-step, fully credited web path. Without the re-tap step it also silently zeroes `referral_joined` on the path we'd be promoting.
- **Riskiest assumption:** iOS invitees will finish a two-app TestFlight install from a chat link, *and* come back and re-tap so the credit lands.
- **Cheapest test (no build):**
  1. During the deadline window, the operator pastes the public TestFlight link as a second line under the invite in a few of the operator's own leagues, including one ESPN or MFL league.
  2. Compare the league-summary joined counts and `league_member_joined` against `referral_joined`. The gap between them is the credit lost to the cold open.
  3. Add one manual TestFlight-checklist item: tap an invite inside Sleeper's league chat, with and without the app installed, and record what opens (in-app browser, Safari, or the app).

### Seasonal timing

| When | Loop push | Channel emphasis |
|---|---|---|
| **Now → early Nov** (NFL trade deadline) | Trade-card shares (S1, S2, S4) into league chats, and invites framed as "find trades before the deadline". The A test runs now. | League chat, group text |
| **Mid-Nov → Dec** (league deadlines vary; fantasy playoffs **[assumed]** Dec) | Fewer invites. Eliminated dynasty teams start rebuilding, so the pitch is "sell your vets". | League chat |
| **Jan → Feb** (offseason trading reopens in many leagues **[assumed]**) | Invite plus trade shares for rebuilders, and a "reset the board" ranking prompt. | League chat, Discord |
| **Mar → Apr** (NFL free agency, then the NFL Draft late Apr **[assumed]**) | Pick-trade season. Fix pick shares falling back to S3 before this window. | League chat, X content |
| **Apr → May** (rookie drafts) | Invites around rookie drafts. If the listing exists, the first public push goes here (creators, r/DynastyFF). | League chat, creators |
| **Jun** | Lull. Pitch creators for the July–August placements (the mkt-partners timing rule). | Partners |
| **Jul → Aug** (startup drafts, new leagues forming) | Biggest invite moment: commissioners invite a whole new league in one go. Store launch campaign if listed. | League chat, Discord, creators |

### Decisions needed

1. **The CTA (audit decision 4).** A as amended, plain A, B or C. Operator.
2. **Create a public TestFlight link.** That means accepting that anyone holding it can install, plus the tester cap and keeping builds fresh **[assumed]**. Operator.
3. **One brand name in every share artifact:** invite text, trade text, calculator text, `/s/` title, OG footer, inviter push, image watermark. This is D-057 applied to the share artifacts. Operator / growth-pm.
4. **X cards versus `robots.txt`.** Unblock `/og/` (and `/s/`) for X's crawler, and keep them out of the search index another way. growth-pm with mkt-seo.
5. **Whether to make any public seed posts** (r/DynastyFF, X) before the listing. I recommend at most one disclosed post per community. Operator.

### Handoffs

- **growth-pm**
  - A's H3a branch: iOS plus a Sleeper/non-Sleeper split, keyed off `invite-meta`.
  - The re-tap step or `dtf://` bridge.
  - The legacy `/` must carry the branch, because `growth.invite_join_link` is still off.
  - S1/S2 CTAs drop `ref` (`server.py:25563, 25669`).
  - ESPN/MFL never set `invited_by`.
  - The title-length and image rules in §1.
- **design-lead**
  - An invite OG card (1200×630, league name and inviter for Sleeper, a fallback for ESPN/MFL, center-safe).
  - The H3a TestFlight / continue-on-web layout.
  - The `/s/` landing CSS is off-Chalkline: a 999px pill, a system and Roboto font stack, 16px radius plus box-shadow (`server.py:25493-25512`).
- **analytics-lead**
  - Web H3a has no `invite_link_opened`.
  - Add a TestFlight-CTA tap event. Register any new event in `analytics_taxonomy.py` *and* `NON_INTENT_EVENTS` in the same commit.
  - Measure the cold-open credit loss as `league_member_joined` without `invited_by`.
  - Campaign-token reporting after the listing.
- **engagement-pm**
  - H7 copy. The referral push says "Fantasy Trade Finder" (`server.py:22662`).
  - ESPN/MFL inviters are never credited.
  - Re-engagement beats line up with the seasonal table (deadline, rebuild, rookie drafts, startups).

## C. UTM / install-source convention (mkt-seo)


> Read-only pass at `origin/main` 678834ab, 2026-10-15. Every code claim is cited `file:line` at that sha. Anything about Apple / App Store Connect / iOS share sheets is **assumed (general knowledge, unverified)**. Hop IDs are growth-pm's (H1–H8). For the share loops I number S1 `/s/trade/<match_id>`, S2 `/s/p/<short_id>`, S3 `/?ref=` root, S4 `/s/tiers/…` (dark). **S-ID key (lead, 2026-10-15):** these map to `growth-pm`'s fixed series as follows:
> - local S1 → **S3**
> - local S2 → **S2**
> - local S3 → the **last rung of S1/S2**
> - local S4 → **S4** Two outputs, kept separate: **§Convention** (paste-ready for the PRD; analytics-lead writes the final version, P18) and **§Proposal for analytics-lead** (what to register).

### Today

**No UTM or install-source handling exists.** `git grep -i -e utm_ -e install_source -e campaign` over backend/web/mobile/src finds exactly one hit: a test asserting that `utm_source` is **dropped** (`backend/tests/test_invite_links.py:132-136`).

| Link (built at H2) | Params | Built at |
|---|---|---|
| Invite, legacy (live: `growth.invite_join_link`=false, `config/features.json`) | `/?league=<id>&ref=<u>` | `mobile/src/components/InviteLeaguematesBanner.tsx:62-64`; web `web/js/app.js:5822-5829` (same shape) |
| Invite, path form (flag off) | `/app/league/join/<id>?ref=<u>` | `InviteLeaguematesBanner.tsx:59-60` |
| S1 trade share (mutual match) | `/s/trade/<match_id>?ref=<u>` | `mobile/src/screens/TradesScreen.tsx:5297-5303` |
| S2 package share (rung A) | `/s/p/<short_id>?ref=<u>` | `mobile/src/utils/shareLinks.ts:143-148` (surfaces `calc_live`, `calc_in_league`, `trades_liked`) |
| S3 rung B/C fallback | `/?ref=<u>` or bare `/` | `shareLinks.ts:86-92` |
| `growth.share_landing` off | bare `https://fantasy-trade-finder.onrender.com` | `TradesScreen.tsx:5300-5301` |
| S4 tiers (dark, `growth.tier_board_share`=false; D-P1-12 cancelled it) | `/s/tiers/<pos>/<username>?fmt=` | `backend/server.py:25522-25549` |
| Profile `/u/<username>` | no share emitter in the app. The username appears only in the Settings copy | `mobile/src/screens/SettingsScreen.tsx:1198` |

**What `ref` holds:** the sharer's **Sleeper username**, raw. It isn't an opaque code (`InviteLeaguematesBanner.tsx:58`, `shareLinks.ts:90`). Mobile lowercases it at capture (`mobile/src/state/useSession.ts:492`). Web shows it back as "Invited by @<ref>" (`web/js/app.js:6415`).
**PII FLAG:** that handle sits in every invite and share URL. It also reaches Render access logs and link previews, and it travels with every forward beyond the league. S4 puts a username in the *path*. A second problem: `ref` is unauthenticated, so anyone can craft `?ref=<someone>` and make that person get a "joined via your invite" push (H7, `server.py:22653-22668`).

**How it is read and stored:**
- **H3a, not installed:** the `/app/league/join/<id>` 302 keeps only `league` and `ref` (`server.py:12620-12624`). Web `captureReferralFromUrl` stores `ref` and `league` in localStorage and then `replaceState`s away the **entire** query string (`app.js:6390-6403`, strip at `:6398`). It runs before `boot()` (`app.js:6723`), so `app_opened` (`app.js:159`) never sees the URL.
- **H3a, S-loops (bug):** every `/s/*` landing CTA is hard-coded `cta_url="/"` (`server.py:25548`, `:25563`, `:25669`). A non-installed recipient of `/s/p/<id>?ref=<u>` who taps "Build your own trade" arrives with **no ref**.
- **H3b, installed:** AASA claims `/s/*`, `/app/league/join/*`, `/?ref=`, `/?league=` (`server.py:12668-12678`). `handleDeepLink` reads `ref` (`mobile/src/utils/deepLinks.ts:398-402`) and `league` (`:418-438`). `/s/*` is aliased onto existing routes (`deepLinks.ts:229-237`). The path form goes to `LeagueJoinScreen.tsx:57-61`.
- **H4:** the invite intent `{leagueId, invitedBy, leagueName, ts}` is persisted to AsyncStorage with a 14-day TTL (`useSession.ts:44-59`, `:491-531`). Web uses localStorage `ftf_invited_by` / `ftf_invited_league`.
- **H5:** `consumeInvitedBy` feeds `session_init.invited_by` (`mobile/src/api/auth.ts:497-514`, `:590-607`; web `app.js:810`). On the server it is read at `server.py:22185`, and `upsert_user` writes `users.invited_by` **on INSERT only** (`backend/database.py:5131-5156`; column at `:462`).
- **H7:** `referral_joined` is a push/notification type, resolved by username (`server.py:22653-22675`). It is **not** an analytics event: the taxonomy only mentions it in a comment (`backend/analytics_taxonomy.py:1371`).
- **H8:** `invite_link_opened{league_id,has_ref,format,auth_state}` (`analytics_taxonomy.py:1157-1158`) fires from `deepLinks.ts:426` (legacy) and `LeagueJoinScreen.tsx:77` (path). It records `has_ref`, never the handle, on purpose (`deepLinks.ts:424-425`). `signup` is server-fired with **no props** (`server.py:22620-22627`). Opening an S1/S2/S3 link fires **no** event on either client, and web fires no `invite_link_opened` at all.

**Surface vocabulary check (growth-pm's 5 names against the existing `surface` enums):**

| growth-pm name | Existing value(s) at origin/main | Mismatch |
|---|---|---|
| `invite_card` | `league_home` (`InviteLeaguematesCard.tsx:64-67`) | The name differs, and `league_home` is shared with the inline link (next row) |
| `invite_banner` | `trades_banner` (`InviteLeaguematesBanner.tsx:150`) | Name only |
| `league_tab` | Probably the League tab's inline "Invite them" link. That link reports **`league_home`** through the same handler (`LeagueScreen.tsx:480-494`) | **Can't be told apart from `invite_card` today.** Separating them needs a new `InviteSurface` value plus a taxonomy change |
| `share_package` | `calc_live` / `calc_in_league` / `trades_liked` (`shareLinks.ts:28`) | `share_package` is a **link format** (rung A, S2), not a surface. `trades_liked` emits S1 *or* S2 |
| `trade_card` | `trade_card_shared.surface` is reserved and never sent (`analytics_taxonomy.py:1035-1038`) | The boundary with `share_package` is undefined |
| *(unlisted)* | `matches_empty`, `members_overlay`, `notif_empty` (`MatchesScreen.tsx:934`, `LeagueScreen.tsx:1012`, `TopBar.tsx:277`) | These are real invite surfaces with no growth-pm name |
| *(unlisted)* | Web invite sheet (`app.js:5822-5835`) | Real, but has no surface prop and no event |

### Convention

**Rules.** Four params: `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`. No `utm_term`. Values are lowercase snake_case from the closed vocabulary below, and each must match `^[a-z0-9_]{1,40}$`. Anything else is dropped at capture and recorded as `other`. `ref` stays a separate param: **`ref` = who** (the inviter), **UTMs = which surface or channel**. Never put a username, email, league name or league id into a UTM. Order in the URL: path params first (`league`, `ref`), then the four `utm_*` in fixed order. The values are a pure function of the H2 surface, built by one `surface → utm` map per client next to `buildInviteUrl` / `resolveShareUrl`. Event `surface` props keep their **existing** values (renaming them breaks series), and the table below is the bridge between the two.

**Proposed values (paste into the PRD):**

| Surface → `utm_content` | Existing `surface` prop | `utm_source` | `utm_medium` | `utm_campaign` | Status |
|---|---|---|---|---|---|
| `invite_card` | `league_home` (card) | `ios_app` | `invite` | `league_invite` | emitter exists |
| `invite_banner` | `trades_banner` | `ios_app` | `invite` | `league_invite` | emitter exists |
| `league_tab` | `league_home` (inline link) | `ios_app` | `invite` | `league_invite` | needs a new surface value to be distinct |
| `matches_empty` · `members_overlay` · `notif_empty` | same names | `ios_app` | `invite` | `league_invite` | extra rows (exist in code) |
| `web_invite` | none (web sheet) | `web_app` | `invite` | `league_invite` | extra row (exists in code) |
| `share_package` | `calc_live`, `calc_in_league` | `ios_app` | `share` | `trade_share` | S2. Proposed boundary: calculator shares |
| `trade_card` | `trades_liked` + S1 | `ios_app` | `share` | `trade_share` | S1/S2. Proposed boundary: any Trades-tab share |
| `tier_share` | n/a | `ios_app` | `share` | `tier_share` | **reserved, not emitted** (S4 dark, D-P1-12) |
| `profile_share` | n/a | — | — | — | **omit**: no emitter in code |
| `web_landing` | n/a | — | — | — | **not a source.** The `/s/*` CTA *forwards* the inbound params unchanged (§Composition) |
| Partner/creator (later) | n/a | `<partner_slug>` from a registry mkt-partners owns | `creator` \| `partner` | `<yyyy>_<name>`, e.g. `2027_preseason` | `utm_content` ∈ `bio_link` \| `video_desc` \| `newsletter` \| `pinned_post` |
| App Store campaign (later) | n/a | — not UTMs — | — | `ct=<utm_campaign>` (assumed ≤40 chars) | `pt=<provider token>` (assumed) |

**What the app knows vs doesn't.** The app knows the **surface** at H2, so `utm_content` and `utm_campaign` are exact. It does **not** know the **channel** (iMessage, Discord, a Sleeper chat) when it builds the link: the URL is built first (`InviteLeaguematesBanner.tsx:128`) and the sheet opens after (`:131`). On iOS, `Share.share` resolves `{action, activityType}`, and `activityType` (e.g. `com.apple.UIKit.activity.Message`) is filled in only after a completed share (**assumed**, RN docs, unverified on RN 0.81). So the channel goes on the **event** as a bucketed `channel` prop, never into the URL. `utm_source` therefore means "which client built the link", not the chat app.

**Examples** (`<ref>` stands in for today's username, `B` = `https://fantasy-trade-finder.onrender.com`):
1. `B/?league=1048123456789&ref=<ref>&utm_source=ios_app&utm_medium=invite&utm_campaign=league_invite&utm_content=invite_card`
2. `B/app/league/join/1048123456789?ref=<ref>&utm_source=ios_app&utm_medium=invite&utm_campaign=league_invite&utm_content=invite_banner`
3. `B/s/p/Ab3_x9Qz?ref=<ref>&utm_source=ios_app&utm_medium=share&utm_campaign=trade_share&utm_content=share_package`
4. `B/?utm_source=<partner_slug>&utm_medium=creator&utm_campaign=2027_preseason&utm_content=video_desc` (no `ref`: a partner isn't a user)

### Composition and capture

- **AASA still matches** with UTMs appended, because `league` or `ref` is present. That assumes the `components` matcher ignores unlisted query items (**assumed**; confirm with the external AASA validator per `docs/runbook.md` § AASA). A UTM-only root URL (example 4) does not open the app, which is what we want for web-first partner traffic.
- **H3b, installed:** `handleDeepLink` reads the four `utm_*` next to `ref` (`deepLinks.ts:396-438`). `LeagueJoinScreen` reads them from route params (`deepLinks.ts:119`; that query params arrive as route params is **assumed**). They are stored as a new `utm` field in the invite-intent blob: same 14-day TTL, last-write-wins, same semantics as `invitedBy` (`useSession.ts:491-507`).
- **H3a, web:** (1) the 302 at `server.py:12620-12624` forwards the four `utm_*` from a closed allowlist with values validated. That reverses T7, so `test_invite_links.py:132-136` flips. (2) `captureReferralFromUrl` reads `utm_*` **before** the strip at `app.js:6398` and writes `ftf_first_touch` to localStorage **only if it is absent** (first touch). (3) **Fix the S-loop ref drop:** `_share_html` builds the CTA as `"/?" + urlencode(allowlisted inbound ref + utm_*)` instead of `"/"` (`server.py:25548/25563/25669`).
- **H5:** both clients send an optional `first_touch: {utm_source, utm_medium, utm_campaign, utm_content}` in the `session_init` body, next to `invited_by` (`auth.ts:514`, `app.js:810`), and the server attaches it to `signup`. That changes the API contract, so it gets the full gates and a `docs/api-reference.md` update.
- **Why web sign-in preserves attribution** *(lead note: this holds only for desktop users who have the Fleeced extension. Web sign-in can't run on a phone, per `web/js/browser-auth.js:1`)*. Both clients key `users` on `sleeper_user_id` through `session_init` (`server.py:22175`, `:22598-22604`), and `invited_by` is immutable after INSERT. A recipient who signs in on web first is attributed permanently, and a later app install on the same Sleeper account inherits it. Two cases lose it: account-only (`acct_`) mobile users, who have a different id, and in-app browsers such as Discord or Sleeper, whose storage is separate from Safari's (**assumed**).
- **CTA option A (iOS → public TestFlight link; no TestFlight URL exists in code today):** `ref` and the UTMs are **lost at the TestFlight hop**. TestFlight has no deferred deep link, and first launch has no initial URL (**assumed**). Attribution survives only if (a) the user signed in on web before the hop, or (b) the user taps the original link again after installing, which hits H3b and the 14-day intent. Recovery options without email (capture was reverted, 65c63479):
  - (i) Landing copy: "After installing, tap this link again." Cheap.
  - (ii) League-scoped inference, query-only: a new user whose first `league_id` matches an `invite_shared.league_id` from the prior 14 days is "league-attributed". Credit the league, not a person, when several people invited.
  - (iii) A "Who invited you?" picker of joined leaguemates after sign-in. This needs a new write route, because `invited_by` is INSERT-only. That means API + flag + taxonomy, full gates.
  - Not recommended: clipboard-based deferred linking (iOS paste prompt, **assumed**).
- **Option B (web `/`):** `ref` and the UTMs survive end to end through localStorage → H5 → `users.invited_by` plus `signup` props. It has the fewest losses.
- **Option C (B, then the App Store listing):** same as B before launch. After launch, the store link carries `pt` + `ct`, and App Store Connect reports installs **per campaign, in aggregate, never per user** (**assumed**). Per-user attribution therefore falls back to recovery (i) and (ii), exactly as in A. `ct` = the inbound `utm_campaign` (+ `_utm_content` if it fits in 40 chars).
- ~~**My recommendation for growth-pm:** C, with the TestFlight link shown as a *secondary* CTA only **after** web sign-in, when attribution is already stored. If A ships, ship (i) and (ii) with it.~~
  > **Lead override (marketing-lead):** C is not recommended. Web sign-in needs the desktop extension (`web/js/browser-auth.js:1`, `:45`), so "web sign-in first" can't happen on a phone. The lead pick is **A**, with recovery (i) (the re-tap) and (ii) (league inference) shipped alongside, per §0.2.
- **Canonical / robots:** static pages already carry absolute, query-free canonicals (e.g. `web/index.html:8`), so UTM'd URLs canonicalize to the clean URL, and new pages must keep that. `robots.txt` already disallows `/s/` and `/og/`. The `/s/*` landings emit no canonical, which is fine while they are disallowed.

### Proposal for analytics-lead

Repo rule: register in `backend/analytics_taxonomy.py` **and** classify in `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitter. Prop-only additions keep the existing classification.

| Event | New / changed | Props added | Intent vs NON_INTENT | Emitter (file) | Why |
|---|---|---|---|---|---|
| `invite_shared` | changed | `channel` (activityType bucketed: `messages`\|`mail`\|`copy`\|`discord`\|`slack`\|`other`\|`unknown`) | INTENT (unchanged) | `InviteLeaguematesBanner.tsx:135` | The channel the link can't carry |
| `calc_trade_shared` | changed | `channel` | INTENT (unchanged) | `TradeCalculatorScreen.tsx:614` | Same, for S2 |
| `trade_card_shared` | **no taxonomy change** | start *sending* the reserved `channel` + `surface` (`analytics_taxonomy.py:1035-1038`) | INTENT (unchanged) | `TradesScreen.tsx:5338` | Client-only change |
| `invite_link_opened` | changed | `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`; new `format` value `web` | INTENT (unchanged) | `deepLinks.ts:426`, `LeagueJoinScreen.tsx:77`, **new web emitter** in `captureReferralFromUrl` (`app.js:6390`) | Which surfaces' links get opened. H3a is invisible today |
| `app_opened` | changed (web) | `has_ref`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` (omitted when absent) | NON_INTENT (unchanged) | `app.js:159`. Must read from the values captured at `:6723`, because the URL is already stripped | Anonymous first touch for web visitors, including S-loop CTA arrivals |
| `share_link_opened` | **NEW** (client) | `kind` (`trade`\|`package`\|`ref_root`), `has_ref`, `auth_state`, the 4 `utm_*` | Suggest **NON_INTENT** (an arrival, like `app_opened`). Flag: `invite_link_opened` is INTENT, so align the two | `deepLinks.ts` `handleDeepLink`, for non-`league` links | S1–S3 opens fire nothing today. Not put on mobile `app_opened`, because `App.tsx:136` and `getInitialURL` (`App.tsx:171`) aren't ordered |
| `signup` | changed (server-fired; outside `CLIENT_EVENT_PROPS`) | `has_ref`, `ref_resolved` (referrer found, `server.py:22655-22656`), `attribution` (`link`\|`none`; later `league_inferred`\|`self_reported`), `first_utm_source`, `first_utm_medium`, `first_utm_campaign`, `first_utm_content` | INTENT / funnel (unchanged) | `server.py:22620-22627`, fed by `session_init.first_touch` | **The install-source / first-touch field.** It fires exactly once per account, so no `users` column is needed |
| `share_landing_viewed` | NEW, **optional / deferred** | `kind`, `has_ref`, the 4 `utm_*` | NON_INTENT | A JS beacon on `_share_html` loading `events.js`. `record_event` needs a `user_id` (`database.py:4416-4417`), so it can't be fired server-side | S-loop H3a views. Without it, only CTA click-throughs are counted |

**Totals:** 1 new event (+1 optional/deferred) and 18 new prop keys across 5 existing events (`channel` ×2, utm ×4, `has_ref`+utm 5, signup 7), plus one new `format` value. `trade_card_shared` needs no registration.
**Also asked of analytics-lead:** today `CLIENT_EVENT_PROPS` allowlists keys, not values. A value check (vocabulary or regex → `other`) at ingest or in the client map is what makes this vocabulary actually closed.
**Privacy:** no usernames or emails in UTMs or props. Keep the `has_ref` pattern (`deepLinks.ts:424-425`) and never copy `ref` into props. The value regex stops a pasted handle from riding along in a UTM.

### Decisions needed

1. **CTA option A / B / C** (operator via growth-pm). I recommend C, with TestFlight shown only after web sign-in.
2. **Vocabulary bridge, not rename:** keep the existing `surface` enums and map them to growth-pm's `utm_content` names. Still open: what `league_tab` *is*; where the `trade_card` / `share_package` boundary sits; whether to keep the three unlisted invite surfaces plus `web_invite`.
3. **`ref` = Sleeper username (PII).** Option 1: accept it, since recipients are mostly leaguemates who already see the handle. Option 2: mint an opaque per-user referral code (a `users` schema change → full gates) and keep parsing usernames forever for links already in the wild. Either way it also settles the spoofed-`ref` push.
4. Attribution windows: first touch on `signup`; last touch within the 14-day TTL on link events.
5. Let UTMs through the `/app/league/join` 302. This reverses T7's closed contract (eng-backend).
6. Build the "Who invited you?" picker (new API) or rely on league-scoped inference.
7. *(Outside UTMs.)* Share and invite copy still says "Dynasty Trade Finder" / "Fantasy Trade Finder" (`InviteLeaguematesBanner.tsx:132`, `server.py:25512`, `:22662`) instead of Fleeced (D-057) → mkt-brand.

### Handoffs

- **growth-pm (PRD owner):** paste the §Convention table. Choose A/B/C. Resolve decision 2. Add the S-loop CTA ref-drop (`server.py:25548/25563/25669`) as an H3a fix item. Add recovery (i)/(ii) if A is chosen.
- **analytics-lead (P18, final convention):** the §Proposal table; ingest-time value validation; the `share_link_opened` intent classification versus `invite_link_opened`; documenting `signup`'s server props.
- **eng-backend (via PRD):** 302 UTM passthrough + T7 flip; `_share_html` CTA passthrough; `session_init.first_touch` + `docs/api-reference.md`.
- **eng-web:** UTM capture before `replaceState`; `app_opened` props; web `invite_link_opened`; `web_invite` UTMs.
- **eng-mobile:** the `surface→utm` map in `shareInvite` / `resolveShareUrl` / `TradesScreen.tsx:5297`; capture in `handleDeepLink` / `LeagueJoin`; `channel` bucketing.
- **mkt-partners:** own the partner-slug registry. **mkt-aso:** `ct` values once the listing exists.

## D. Decisions needed

Consolidated from §A–§C, with the decider named. "Rec" is `marketing-lead`'s recommendation.

| # | Decision | Decider | Rec |
|---|---|---|---|
| D1 | CTA target before the listing: A, B or C (audit decision 4) | **Operator**, through `growth-pm`'s PRD | **A, with the three amendments in §0.2.** B and C dead-end every phone invitee, because web sign-in needs the desktop extension |
| D2 | Create a public TestFlight link. Anyone with the link can install; there's a tester cap; builds must stay fresh (assumed) | **Operator** | Yes. A depends on it |
| D3 | `ref` = raw Sleeper username. Accept it, or mint an opaque per-user referral code (a schema change, full gates) | `growth-pm` with `head-eng` (eng-security); operator if it's a schema change | **An opaque code.** It removes the PII and closes the spoofed `referral_joined`. Keep parsing usernames for links already in the wild |
| D4 | The default invite message: without or with the league name | `growth-pm` | **Without it.** It fits ~140 characters, and the recipient is in that league already. Use the league-named version only outside league chat |
| D5 | Surface vocabulary: bridge or rename. Also settle what `league_tab` is, and where `trade_card` ends and `share_package` begins | `growth-pm` with `analytics-lead` | A bridge (§C). Never rename event values that already have history |
| D6 | Let UTMs through the `/app/league/join` 302 (this flips test T7) | `growth-pm`, then `head-eng` | Yes, from a closed allowlist with values validated (§C) |
| D7 | Attribution recovery: league-scoped inference (query only), or a "Who invited you?" picker (a new write route) | `growth-pm` | **League inference first.** It needs no build and covers ESPN and MFL. Build the picker only if the gap in the §0.2 test is large |
| D8 | X cards versus `robots.txt` (`/s/`, `/og/` blocked) | `growth-pm` with `head-eng` | Unblock `/og/` for X's crawler, and keep `/s/` out of search another way |
| D9 | Public seed posts (r/DynastyFF, X) before the listing | **Operator** | At most one disclosed, value-first post per community. Better after the listing |
| D10 | O5, the persona (open since wave 1, D2) | **Operator**, through `head-bizops` | 7 rows in §A are marked O5. They read fine as the neutral assistant GM, and get a second pass only if the ram speaks |

## E. Handoffs

The W4 route covers `growth-pm` only. Everything else goes through `head-bizops`, or through `growth-pm` where §3 of the brief allows.

- **`growth-pm`** (direct):
  - §A as the copy spec, carried in the PRD as exact strings;
  - §0.3 defects 1–11 into the PRD's fix list;
  - §C's "Convention" table;
  - D1, with the §0.2 amendments;
  - the S-series renumbering;
  - the §0.2 cheapest test, as an operator checklist step.
- **`analytics-lead`** (through `growth-pm`, or `head-bizops` → `head-product`):
  - §C's "Proposal for analytics-lead": 1 new event (+1 deferred) and 18 prop keys on 5 existing events;
  - ingest-time validation of values;
  - the league-scoped attribution query (D7);
  - measuring the cold-open credit loss (`league_member_joined` without `invited_by`).
- **`design-lead`** (`growth-pm` partners it directly; visual review of marketing assets goes `head-bizops` → `head-product`):
  - the invite OG card: 1200×630, the league name for Sleeper and a fallback for ESPN and MFL, center-safe;
  - the H3a layout: the TestFlight CTA plus helper, the re-tap line, and the desktop and Android lines;
  - the off-Chalkline `/s/*` CSS (§0.3 #11).
- **`engagement-pm`** (through the heads):
  - the H7 copy (§A `gp.push.*`);
  - the title = body rendering bug;
  - deduping the inviter, who gets both `league_member_joined` and `referral_joined`.
- **`onboarding-pm`** (through the heads), for its queued batch PRD: old names outside the loop, in `ClaimSheet.tsx:72/79/86`, `DraftRoomScreen.tsx:830` and `PickAssignmentScreen.tsx:1136`. The loop's own strings go in this PRD. The web logos (`index.html:331`, `:379`) appear in both, so whichever PRD ships first takes them.
- **`head-eng`** (through the heads): `ref` spoofing and PII (D3), for an eng-security read.
- **`head-bizops`:**
  - O5 / D10;
  - the custom domain (wave 1 D6). Every invite URL and share footer shows `fantasy-trade-finder.onrender.com`, which reads as a third product name (§A "Notes").

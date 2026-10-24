# FAQ copy — build input for `web/faq.html` (SUP-M4)

**Source:** `marketing-lead-copy.md` §2 (`marketing-lead`, basis `origin/main` `712dcbed`), **source as of 2026-10-23 18:17, R22 applied (§0 item 11)**. That file sits in the org-bringup worktree (`docs/plans/org-bringup/leads/`) and isn't tracked in git, so its text is copied here for the builder. Spec: [prd.md §7b](prd.md#7b-faq-sup-m4) · scope block: [scope-faq-sup-m4.md](scope-faq-sup-m4.md).
**Status:** DRAFT. Nothing here is built or published yet.
**Approval:** the meaning changes are **pending operator §6 (I)**. `marketing-lead`'s §6 block I covers the answers listed under "FAQ, changes in meaning vs. today" below, including two operator commitments: Q18's "Replies come within 2 business days." and Q16's R10 wording. Q18 now also states the data-request timing; both targets are **consistent with D-10**.
**Legal-owned:** Q16 and Q17 are `legal-lead`'s (R10 wording). Q8, Q15 and Q17 carry `legal-lead`'s R22.1 edits.
**Pending confirmation:** Q9 (the ranking answer: K-factor 32 for a matchup, 8 for a like, 4 for a pass) is **pending model_config confirmation**: `analytics-lead` reads prod `model_config` and `models-lead` confirms, via `head-bizops`.
**Ship order: decided (P37, `head-product`, 2026-10-23).** The FAQ goes live **with** the new Privacy Policy and Terms, by **Mon 2026-11-09**, before the Tue 2026-11-10 App Store submission, and Q3's App Store line flips on **Wed 2026-11-18**, alongside `IOS_INSTALL_URL` and the `m4.348.*` rows. Marketing's revised §2, kept verbatim below, says the FAQ goes live "only after the app is released on the App Store (planned 2026-11-18; R22.5)". **That order is declined (P37):** the live FAQ says "TestFlight beta" (`web/faq.html:206` at `712dcbed`), and a reviewer can reach it from the app. The builder follows [prd.md §7b](prd.md#7b-faq-sup-m4) (FAQ-R2), not §2's go-live sentence.
**Review tags:** the bracketed tags (`[new]`, `[R10]`, `[R10 · R8]`, `[R10 · R21 #3]`, `[R22.1 edit]`, `[R22.1 edit; head-eng confirms the number's scope]`, `[R22.3 / R22.4 timing]`, `[goes live only at release, 2026-11-18, with the real URL; R22.1]`) and the `[APP STORE URL]` placeholder are for review only. **They are never published.**
**Wording:** the body of each section below is copied verbatim from the source. The one-line italic lead-ins and the "Open copy items" list are this spec's. Change no wording.

## Contents

- [2. FAQ text (verbatim, marketing §2)](#2-faq-text-verbatim-marketing-2)
- [1c. Verdict table (verbatim, marketing §1c)](#1c-verdict-table-verbatim-marketing-1c)
- [3. Notes for builders (verbatim, marketing §3)](#3-notes-for-builders-verbatim-marketing-3)
- [Open copy items](#open-copy-items)

## 2. FAQ text (verbatim, marketing §2)

This is the paste-ready text for `web/faq.html`, by worker C, accepted with the §0.9 edits. Tags in brackets are for review only; don't publish them. **Go live together with `legal-lead`'s new Privacy Policy and Terms, and only after the app is released on the App Store (planned 2026-11-18; R22.5).** The policy and terms may go first. Until then, keep today's FAQ.

Build notes: each blank-line paragraph is one `<p>`. Every `fleecedapp@gmail.com` is `<a href="mailto:fleecedapp@gmail.com">` with an ASCII "@" (R11, R18 build rules). "Privacy Policy" links `/privacy`; "Terms of Use" links `/terms`. Keep the first item `open`. Tags in brackets are for review only; don't publish them.

**Head**
- `<title>`, og:title: `FAQ — Fleeced: Dynasty Trade Finder` (unchanged)
- meta + og:description (137/155): `How rankings, trade values and Sleeper, ESPN and MyFantasyLeague (MFL) league connections work in Fleeced, and what happens to your data.`
- H1 and sub: unchanged.

**Q1. What is Fleeced?**
A dynasty fantasy football trade finder. Rank your players, and the app compares your board with your leaguemates' boards to find trades built to work for both sides.

Every value and every suggested trade is an estimate from rankings, not a guarantee. The call is yours.

**Q2. Which league platforms work with Fleeced?** [new]
Sleeper, ESPN and MyFantasyLeague (MFL). On all three you can import your league, get suggested trades built from your board, and send a trade proposal in your league.

Sleeper also works in the desktop web app and the browser extension.

Fleeced is not affiliated with or endorsed by any of these platforms.

**Q3. Where can I use Fleeced?** (was "Is there a mobile app?")
On iPhone: the Fleeced app on the App Store ([APP STORE URL]). [goes live only at release, 2026-11-18, with the real URL; R22.1] Sign in with Apple, Sleeper, ESPN or MFL.

On a computer: the web app on this site, in Chrome or Edge with the Fleeced browser extension installed. The extension is installed by hand from a release download; it isn't in the Chrome Web Store. The web app signs in with Sleeper only. ESPN and MFL leagues sign in through the iPhone app.

There's no Android app. Phone browsers can't run the extension, so on a phone, use the iPhone app.

**Q4. How do I connect a Sleeper league?**
In the iPhone app, sign in with Apple or continue with your Sleeper username, and the app finds that account's leagues. Pick a league and every roster in it comes in.

To verify the account and send trades, sign in to Sleeper on Sleeper's own page inside the app. Your Sleeper password stays on Sleeper's own sign-in page. The app keeps the sign-in token Sleeper issues, encrypted, to verify your account and send trades you approve. [R10 · R21 #3]

On a computer: install the browser extension, sign in at sleeper.com in another tab, then verify your username on this site.

**Q5. How do I connect an ESPN league?** [new]
In the iPhone app, choose ESPN and sign in on ESPN's own page inside the app. Your ESPN password stays on ESPN's sign-in page, and the app lists your leagues.

The app keeps two ESPN sign-in cookies: espn_s2 (encrypted) and SWID (your ESPN member ID). They're used to import your leagues and to send trades you approve. Disconnect any time in Settings. [R10 · R8]

A public league can also be added by league ID with no sign-in. Sending a trade needs the ESPN sign-in.

**Q6. How do I connect an MFL league?** [new]
In the iPhone app, choose MFL and sign in with your MFL username and password, or enter a league ID or a myfantasyleague.com league URL.

Your password goes to MFL to sign you in. It's never stored; only the encrypted session MFL returns is kept. [R10 · R8]

Sending a trade needs the MFL sign-in.

**Q7. My league is private. Does it still work?**
Yes. Sleeper: your username finds that account's leagues, public or private. Signing in to Sleeper inside the app proves the account is yours and protects your board.

ESPN: private leagues need the ESPN sign-in. Public leagues can be added by league ID.

MFL: private leagues work with the MFL sign-in.

**Q8. Can I send a trade from the app?** [new]
Yes, on Sleeper, ESPN and MFL. Adjust any trade in the trade calculator, then send it as a real trade proposal in your league. Nothing goes out until you tap send. If you haven't signed in to that platform yet, the app asks you to first.

Some of these connections, including Sleeper's and ESPN's, aren't officially supported for outside apps, so they can stop working without notice. The Terms of Use cover the details. [R22.1 edit]

**Q9. How does the ranking system work?**
Your board comes from your calls: three-player matchups, tier placements and reorders. Each matchup splits into head-to-head results (winner beats loser), and those feed an Elo rating, so each player's value moves relative to the rest of the pool. The more matchups a player appears in, the more settled that player's rating.

By default a three-player matchup moves ratings with a K-factor of 32. Trade-card swipes count for less: 8 for a like, 4 for a pass. One trade card can't swing a rating as much as a direct ranking.

**Q10. Where do the starting values come from?** (was the KTC / Dynasty Daddy question)
Every board starts from consensus values from DynastyProcess and other published sources, so on day one your values look roughly like other published consensus values.

As you rank, your board moves away from consensus wherever your calls disagree with it. That gap between your board and your leaguemates' boards is where trades come from.

**Q11. How are trade values worked out?** [new]
A trade card prices your side with a blend of your board and consensus. The more often you've compared a player, the more the price follows your board: a player you've never ranked sits at consensus, and a player you've ranked many times carries your value. A player you've placed in a tier stays inside that tier.

Your leaguemate's side uses their board. Until a leaguemate ranks, their side uses consensus values.

Every value and every suggested trade is an estimate from rankings, not a guarantee. The call is yours.

**Q12. What's a "tier"?**
A group of players you consider roughly interchangeable, labeled in draft-pick terms: 4+ 1sts, 3 1sts, 2 1sts, a 1st, a 2nd, a 3rd, a 4th, and FA.

Sorting players into tiers is faster than ranking each one, and it sets a rating band for each tier. Matchups still move a player within that tier.

**Q13. What's the difference between 1QB PPR and SF TEP?** (unchanged)
1QB PPR is the classic dynasty format: one starting quarterback, one point per reception.

SF TEP is Superflex with Tight End Premium: you can start a second QB in a flex spot, and tight ends score extra points per catch. QBs and TEs are worth much more in this format.

Your two boards are separate, so you can hold different opinions about the same player in each format.

**Q14. Why two rank sets?**
The same player is worth very different things in different scoring formats. Tiers, ratings and progress are all tracked per format. Switch formats and the app shows your board for that format only.

**Q15. Can my leaguemates see my rankings?** [R10]
No. Your ranking list isn't shown to leaguemates. Boards are compared on the server: your board shapes which trades your leaguemates are shown. When you and a leaguemate like the same trade, it becomes a matched trade and shows for both of you.

The league page can show each member's contrarian score: one number for how far that board sits from the league's consensus, not which players it's high or low on. [R22.1 edit; head-eng confirms the number's scope]

**Q16. Is my data sold or shared?** [R10]
We don't sell your data. We share it only with the service providers and platforms listed in our Privacy Policy, to run the app.

**Q17. What data does the app keep, and how do I delete it?** [R10] (was "Privacy policy summary")
What it needs to run: how you sign in, your leagues and rosters (including leaguemates' rosters), your rankings and trade decisions, and usage events. Passwords aren't stored. The full list, and how long each item is kept, is in the Privacy Policy.

You can download a copy of your data or delete your account yourself in the app: Settings → Account & data. If you can't sign in, email fleecedapp@gmail.com from the address you'd like the reply sent to. Account data is never sent by email. You may be asked to confirm the account is yours. [R22.1 edit]

**Q18. How do I get help or report a bug?** [new]
For anything that needs an answer, email fleecedapp@gmail.com. Replies come within 2 business days. Data requests are acknowledged within 2 business days and completed within 30 days. [R22.3 / R22.4 timing]

For bugs and ideas, use the feedback button on any screen in the app. It's one-way: replies don't come back in the app, so email if you want to hear back.

**Footer:** `Still have questions? Email fleecedapp@gmail.com.` then the existing Privacy Policy · Terms of Use links.

## 1c. Verdict table (verbatim, marketing §1c)

*Lines are `web/faq.html` at `712dcbed`.*

| Current Q | Line | Verdict | Why |
|---|---|---|---|
| `<title>` / meta + OG description | 6-7, 11-12 | Keep title; rewrite description | Description names Sleeper only and says "what we do" |
| H1 + sub | 126-127 | Keep | Neutral |
| What is Fleeced? | 130-132 | Rewrite | "both sides come out ahead" needs R21 #8's qualifier; "we cross-reference" |
| How does the ELO ranking system work? | 137-140 | Rewrite (light) | K 32/8/4 accurate (`ranking_service.py:57-59`). Says tiers are "decomposed" into comparisons, but tiers set a band (`:1468-1475`) |
| 1QB PPR vs SF TEP | 145-149 | Keep | Accurate (`database.py:592`, `LeagueSummaryScreen.tsx:276-277`) |
| Why two rank sets? | 154-156 | Keep (light) | Accurate. "ELOs" → "ratings" |
| How do I sync my Sleeper league? | 161-164 | Rewrite | Says a username alone works and the board is open until verified. Board reads now need a verified session (`server.py` `_verified_read_denial`, 54 gated routes). Web needs the extension (`app.js:334`) |
| My league is private | 169-171 | Rewrite | Sleeper-only; same stale caveat |
| Do you share my data? | 176-178 | Rewrite [R10] | "share with third parties" replaced by R10's line (drafts `:361`). "Interest indicator" is not verifiable in code, so it's cut. Mutual match kept |
| Can I use values from KTC / Dynasty Daddy? | 183-185 | Rewrite | Q5b = No: KTC drops out (drafts `:361`) |
| What's a "tier"? | 190-192 | Rewrite (light) | Ladder is 8 tiers. "Override any player's value after setting tiers" isn't verified, so it's cut |
| What's the I AM SPEED button? | 197-199 | Cut | A speed claim ("goes turbo"); the brief excludes speed claims |
| Is there a mobile app? | 204-206 | Rewrite | TestFlight line (R10). Web needs the extension, so "any phone browser" is false |
| Privacy policy summary | 211-213 | Rewrite [R10] | Sleeper-only; "we do not … share" replaced by R10 |
| Footer | 217-222 | Rewrite | Add `fleecedapp@gmail.com` (R11) |

## 3. Notes for builders (verbatim, marketing §3)

*The FAQ's changes in meaning, which operator §6 block I approves:*

**FAQ, changes in meaning vs. today (worker C):**

- Q1: "both sides come out ahead" → "built to work for both sides", plus the estimate qualifier.
- Q3: "works in any phone browser" and "TestFlight beta" → App Store on iPhone, desktop web in Chrome or Edge with the extension, no Android.
- Q4/Q7: "username only, no password" and "anyone with your username could see this board" → sign-in on Sleeper's page verifies, and board reads require it.
- Q4–Q8: Sleeper-only → Sleeper, ESPN and MFL, including sending trades on all three.
- Q9: tiers are no longer "decomposed into comparisons"; they set a band.
- Q10: "looks like KTC or Dynasty Daddy" and "the tool trusts you over the crowd" → DynastyProcess and other published consensus; no third-party value sites named.
- Q11 (new): trade values are a comparison-weighted blend, not your raw board.
- Q12: "override any player's value after setting tiers" removed; full 8-tier ladder.
- Q15: the "interest indicator on the mirrored suggestion" is dropped; only the mutual match remains.
- Q16/Q17: "never share with third parties" → shared only with listed service providers and platforms (R10). Deletion and export in-app, not "see the policy".
- I AM SPEED: removed.

*The launch-day flip notes. They cover the landing page and #348, not the FAQ; the FAQ's Q3 flip follows the same pattern.*

- **Launch-day flip (M4).**
  - `m3.web.mobile_cta` flips at release (2026-11-18, R22.1), not before. Until then, the TestFlight line is true.
  - The heading above it (`index.html:264`, "Continue in the Fleeced app") and the platform note (`app.js:1264`) already read correctly.
  - If the official Apple badge artwork is used, "Download on the App Store" is the badge's own text.
- **Stale §A strings from #348.** These accepted §A strings become false at release (2026-11-18) and aren't on main yet: `gp.join.cta.A_ios` / `s.cta.A_ios` ("Get the iOS beta") and `gp.join.cta.A_ios_help` ("Installs through Apple's TestFlight app.").
  - Launch-day variants: `Get the iPhone app` (≤20: 18) and helper `Opens the App Store.` (20), pointing to `[APP STORE URL]`.
  - `marketing-lead` should route these into #348 before it merges.

## Open copy items

*These are this spec's, not marketing's.*

1. **Pre-launch Q3 text: pre-launch variant: marketing-lead via head-bizops (in progress); R22.5 order declined (P37).** Marketing's revised Q3 tags its App Store sentence "goes live only at release, 2026-11-18, with the real URL" but gives no text for what Q3 says before release. The FAQ goes live by 11-09 (P37), so Q3 ships marketing's pre-launch variant until the 11-18 flip. The flip mechanism is `head-eng`'s.
2. **Pricing-line placement: marketing-lead.** P36 includes R21 #6's line, verbatim: "Free to use today. Nothing in the app is for sale." `marketing-lead` places it (its §4 open question). It comes out the moment a purchase exists.
3. **Extension link: eng confirms at build.** Q3 links the current GitHub release if it is still `extension-v0.1.1`. Today `web/index.html:170` links `https://github.com/mattmurf77/fantasy-trade-finder/releases/tag/extension-v0.1.1`; the FAQ's link must equal it.
4. **Q9's K-factors: pending model_config confirmation** (see the header).
5. **Q16 and Q17: legal-lead.** Q17 now carries an R22.1 edit. Marketing's §4 still offers a passive alternative to Q16 for `legal-lead`'s yes or no, verbatim: "Your data isn't sold. It's shared only with the service providers and platforms listed in the Privacy Policy, to run the app." It also still lists Q17's change of C4's "the address you'd like us to reply to" to "the address you'd like the reply sent to" for `legal-lead`'s OK.
6. **Q11's blend values: head-product to decide.** Marketing's §4 asks `models-lead` to confirm prod `user_elo_shrink` and `placement_tier_clamp` as well as the K-factors, because Q11 describes the blend. P36 names only the K-factor answer (Q9). Whether Q11 waits on the same `model_config` read is open.
7. **Q15's contrarian score: head-eng confirms.** Marketing's tag on Q15's R22.1 edit asks `head-eng` to confirm the scope of the "one number".
8. **Q18: consistent with D-10.** "Replies come within 2 business days. Data requests are acknowledged within 2 business days and completed within 30 days." matches `head-bizops`'s D-10 targets. D-10's 30 days was pending `legal-lead`'s confirmation; marketing tags Q18's timing R22.3 / R22.4.

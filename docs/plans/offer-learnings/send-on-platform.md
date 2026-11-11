# Sending and following up on the platform: a definition (WS6, R10)

**Date:** 2026-11-10 · **Status:** definition for the operator to decide from; nothing here is
built · **Spec:** [plan.md](plan.md) §1 (R10 row) and §3 WS6 · **Evidence:**
[offer-history.md](../realtime-trade-engine/offer-history.md) (612 real offers, one proposer)

The operator's direction, in his words: "the nudge should just be to send the trade on the
platform. I'm also wondering if the initial offers should just push directly to sleeper rather
than our app.. Or atleast give users an easy 'summary' page to quickly decide which offers they
liked get sent into sleeper. And for this process, all offers go to DMs by default with a
invitation/copy to the app 'This trade was built in Fleeced'."

## Open questions for the operator

Each can be answered in a sentence. The recommendation (section 6) assumes the answer in
brackets.

1. Is "by default" met by a message that is **pre-written and offered after every send, but
   sent only when the user taps send in Sleeper or Messages**, rather than posted automatically?
   [Yes.]
2. Should Fleeced add a **second unofficial Sleeper write**, posting direct messages as the user,
   on top of the trade proposal it already sends? The risk of account restriction falls on the
   user's Sleeper account. [Not in the first version.]
3. Should a **like stay a private "maybe"**, with sending a separate tap, rather than a like
   sending a real offer? [Stay private.]
4. Is a cap of **two offers per league-mate per seven days**, and at most one per league-mate in
   any one batch, acceptable for the test? [Yes, as a starting value.]
5. Is the first version **Sleeper only**? Your three leagues are Sleeper leagues. [Yes.]
6. Will you **tell your league-mates** before the test that offers may arrive with a Fleeced
   note, and ask them afterwards how it felt? [Yes. This is the only way to measure the spam
   risk in a sample this small.]
7. Do you approve the message wording **"This trade was built in Fleeced"** plus a link to the
   trade's own page, editable before it sends? [Yes. The existing share text still says
   "Found on Fantasy Trade Finder" and would change with it.]
8. Should the send list **replace the "Awaiting them" tab** on Matches or sit beside it?
   [Replace it: it already is a list of your liked trades with a send button on each.]
9. Should this ship **only after WS2 Part A** (outcomes of sent trades) is on, so every send is
   measured? [Yes.]

## In one paragraph

Fleeced can already send a trade into Sleeper as a real pending offer, from the deck, from a
match and from each liked trade, always after a "Send this trade?" confirmation. It cannot send
a Sleeper direct message, and nothing in the repository tries to. A like on its own reaches the
other manager only if they also use Fleeced, which in a normal league most do not. So the
cheapest way to turn likes into offers is a **send list**: the user's liked trades in one place,
send one or several in a single confirmation, and after the send a pre-written, editable note
("This trade was built in Fleeced", with a link) that the user sends themselves through the
iPhone share sheet. Automated direct messages are left out: they need a new unofficial Sleeper
write, they are the step most likely to read as spam to a league that knows the sender, and
they break the app's rule that nothing goes to another person without the user's tap.

## 1. What exists today

### 1.1 A like

- A like is `POST /api/trades/swipe` with `decision: "like"` (`backend/server.py:22632-22660`).
  It records the user's decision, feeds their own ranking (the like and pass carry Elo weight,
  `backend/server.py:22690-22700`), and checks for a mirror like from the other manager
  (`backend/server.py` around 22840, `find_mirror_like` in `backend/database.py:11707`).
- It is **not a send**. Nothing reaches Sleeper. The glossary is explicit for the calculator's
  equivalent ("the other manager sees a suggested trade, not a proposal",
  `docs/glossary.md:192`).
- The other manager sees a like only inside their own Fleeced deck, as a "They're interested"
  card (`trade.likes_you`, on: `config/features.json:41`; `docs/glossary.md:206`). **A league-mate
  who does not use Fleeced never learns the like happened.**
- The analytics event a like fires is named `trade_proposed`
  (`backend/server.py:22808-22813`). The name is misleading: no proposal is made. Anyone
  reading send funnels should use `sleeper_send_succeeded` and `trade_sent` instead
  (`backend/analytics_taxonomy.py:857,877`).
- On screen, a like shows a "Liked" toast (`mobile/src/screens/TradesScreen.tsx:7263-7270`),
  may offer a standing offer sheet (`:7276`, `trade.standing_offers` on,
  `config/features.json:300`), and shows a "Share your last liked trade" row
  (`mobile/src/screens/TradesScreen.tsx:10292-10300`).

### 1.2 A match, and "Awaiting them"

- A **match** is two managers liking mirror versions of the same trade. The server creates a
  match row, an in-app notification and a push to both (`create_trade_match`,
  `backend/database.py:11825`; notification and push in `backend/server.py` around 22900-22970).
  A match also needs both managers to be Fleeced users.
- **Awaiting them** is every trade the user liked that has not become a match
  (`docs/glossary.md:270`; `GET /api/trades/awaiting`, `backend/server.py:27121`;
  `load_awaiting_trades`, `backend/database.py:12092`). It is the second segment of the Matches
  screen (`mobile/src/screens/MatchesScreen.tsx:158`).
- **Each awaiting trade already carries a "Send in Sleeper" button**
  (`mobile/src/components/TradeCard.tsx:1014-1030`, `surface="awaiting"`), as does each match
  (`:985-1011`). In effect the summary page the operator describes exists in rough form; what it
  lacks is selecting several, knowing which have been sent, and any prompt to go there.
- The awaiting list does not record whether a trade was sent: it filters only retracted likes
  (`backend/database.py:12092-12130`), and the button's "Proposal sent" state lives in the
  component (`mobile/src/components/SendInSleeperButton.tsx:122,558-562`). A sent trade can
  therefore show a fresh "Send in Sleeper" button later.

### 1.3 Send in Sleeper

- **Route:** `POST /api/trades/propose` (`backend/server.py:26532-26601`), whose body is
  `_sleeper_propose_core` (`backend/server.py:26604-26880`). Flag `trade.send_in_sleeper`, **on**
  (`config/features.json:56`; the module docstring's "default OFF" is out of date).
- **How it sends:** it reproduces Sleeper's private `propose_trade` GraphQL mutation, captured
  from Sleeper's own website traffic (`backend/sleeper_write.py:1-38,287-415`;
  `docs/integrations/sleeper.md:53-67`). Sleeper publishes a read-only API and no write API.
- **Credential:** the user logs into Sleeper's own page in an in-app browser and the app keeps
  Sleeper's 365-day session token. It is a full-account credential, encrypted at rest and never
  logged (`docs/integrations/sleeper.md:101-149`).
- **Sleeper's terms:** the repository's own legal note records that Sleeper's terms grant a
  personal, non-commercial licence and prohibit reverse-engineering, scraping and circumventing
  technical measures, so this path is "ToS-adverse on multiple counts", with App Store, account
  ban and token-custody risk stacked on top. The operator accepted that risk on 2026-07-02 as a
  flagged, opt-in beta, keeping a deep-link hand-off as the clean fallback
  (`docs/plans/sleeper-write-capture-runbook.md:136-138`; module header
  `backend/sleeper_write.py:4-9`). The app's Terms tell users the same in plain words and promise
  "Proposals are sent only when you tap send" (`web/terms.html:95-102`).
- **Gates:** a verified session only, no grace period (`backend/server.py:26560-26570`); fails
  closed in test mode (`:26550-26554`); re-checks both rosters and every pick live before
  sending (`docs/integrations/sleeper.md:280-282`).
- **On success** it writes the durable `trade_proposals` row with Sleeper's transaction id
  (`backend/server.py:26860-26872`; table `backend/database.py:866-919`), the deck outcome and the
  `sleeper_send_succeeded` event. This row is what WS2 Part A will follow up.
- **On screen:** a "Send this trade?" alert ("This proposes the trade directly in Sleeper — your
  leaguemate gets it as a pending offer"), then "Trade sent. Check your Sleeper app for the
  pending offer." (`mobile/src/components/SendInSleeperButton.tsx:408-415,280-282`). The button
  sits on every deck card (`mobile/src/screens/TradesScreen.tsx:10221-10240`), so a user can send
  without liking first.
- **Opening Sleeper instead:** the clean hand-off can only open the Sleeper app at whatever screen
  it last showed. Sleeper ignores the trade parameters in its links, so the app cannot open a
  pre-filled trade screen (`docs/integrations/sleeper.md:77,79`).

### 1.4 Direct messages: none

- **The app cannot send a Sleeper direct message, and no code attempts it.** A search of
  `backend/`, `mobile/src/`, `web/` and `extension/` finds no message-sending call; the only
  mentions of Sleeper chats are invite links users pasted there themselves
  (`mobile/src/components/InviteLeaguematesBanner.tsx:24`).
- The capture notes record that when a trade is proposed on Sleeper's own website, Sleeper's page
  also fires a separate `create_message` call to post a "proposed a trade" message, and that
  **Fleeced deliberately does not reproduce it** (`docs/plans/sleeper-write-capture-runbook.md:161`).
  Its exact shape was never captured. The offer history adds that offer cards appear in a
  conversation "only when the proposer included them"
  ([offer-history.md](../realtime-trade-engine/offer-history.md), "Read this first"), which
  suggests the message is optional on Sleeper's side. Unverified: check by proposing a trade on
  sleeper.com in a test league and watching whether a message is posted and whether it can be
  turned off.
- So a trade sent from Fleeced today probably arrives **without** the chat message a trade sent
  from Sleeper itself can carry. Whether Sleeper still notifies the recipient (a push or an
  in-app alert) is not recorded anywhere in the repository. Unverified: send one from Fleeced in a
  test league and look at the recipient's phone.
- What adding one would involve: capture `create_message` from live traffic (as was done for
  `propose_trade`), add a second write to `backend/sleeper_write.py` under the same full-account
  token, and decide where message text comes from. It would carry the same terms problem as the
  proposal, with three differences that make it worse: it writes free text into another person's
  conversation; messages are the thing platforms police most for automation and spam (general
  knowledge, unverified for Sleeper); and a reported message is visible to the recipient and,
  in a group chat, the league.

### 1.5 ESPN and MFL

- **MFL:** `POST /api/trades/propose-mfl` (`backend/server.py:42710-42740`), flag
  `trade.send_in_mfl` on (`config/features.json:57`). It uses MFL's documented import API, so it
  does not carry Sleeper's terms problem. It **accepts a comment** that travels with the offer
  (`backend/mfl_write.py:175,222-224`, capped at 512 characters).
- **ESPN:** `POST /api/trades/propose-espn` (`backend/server.py:43325-43350`), flag `espn.send`
  on (`config/features.json:121`; `mobile/src/components/CLAUDE.md` still calls it dark, which is
  out of date). It uses ESPN's undocumented write API, players only, and also **accepts a
  comment** (`backend/server.py` propose-espn core, `comment=` at about line 43605).
- Neither app button sends a comment today (`mobile/src/components/SendInMflButton.tsx`,
  `SendInEspnButton.tsx`: no `comments` argument; the API clients allow one,
  `mobile/src/api/sendInMfl.ts:61`, `sendInEspn.ts:69`). On those platforms a "built in Fleeced"
  note could ride on the offer itself, through the platform's own field, with no direct message.

### 1.6 Things already built that this can reuse

- **Share links for a trade.** `POST /api/share/package` mints a public page and preview image for
  any give/receive package (`docs/api-reference.md:1371`); `POST /api/share/trade` does the same
  for a match (`:1369`). Flag `growth.share_landing` on (`config/features.json:193`). The page has
  an install button and carries referral attribution.
- **A share of the last liked trade** through the iPhone share sheet, with that link
  (`mobile/src/screens/TradesScreen.tsx:6678-6755`). Its text is "Trade idea for our league: I
  send …, get … from @…. Found on Fantasy Trade Finder — <link>" (`:6737-6741`). The user picks
  where it goes and taps send there. This is the ToS-clean version of the operator's DM.
- **Batch sending with one confirmation**, in Team overhaul: prepare a summary, confirm, send the
  selected liked offers, track each attempt, refuse a retry that could double-send
  (`backend/overhaul_api.py:960-1010`; `docs/api-reference.md:1690-1710`). Turned **off** for
  launch on 2026-10-27 (`config/features.json:89-90`). It shows the batch pattern is buildable;
  its screens are tied to the overhaul flow and are not reusable as they stand.
- **A legacy bulk-send queue** (`useTradeQueue`, flag `trades.queue_2k` off,
  `config/features.json:18`) built Sleeper web links that Sleeper ignores
  (`docs/integrations/sleeper.md:79`). It is dead and should not be revived.
- **Earlier positions on record:** the competitor review rejected a mass-offer sender as "ToS
  exposure plus league-spam backlash" and recommended suggestions the user sends one by one, plus
  a share card for league chats (`docs/plans/competitor-feature-backlog-2026-06-11.md:94-96,363-365`).

## 2. What the evidence says

From [offer-history.md](../realtime-trade-engine/offer-history.md), one proposer, three leagues:

- A first offer was accepted 8% of the time; a thread that went on ended in a trade far more
  often (39% at three offers, 57% at five or more). Deals are negotiated.
- After an offer that was not accepted, **44% drew no further offer within a week**. That is the
  gap R10 targets: offers that die after one try.
- 103 of 612 offers were replaced by the same proposer within 15 minutes. Real proposers revise
  quickly; a list that makes resending easy must also make it easy not to send duplicates.
- Acceptance by recipient ranged from 0% to 36%. Some league-mates will receive many offers and
  accept none, which is exactly where a default message would feel like spam.

What it does not say: anything about how recipients react to a message alongside an offer, or
how many likes a Fleeced user makes per session. Neither is in the repository.

## 3. The four options

### Option 1: Nudge to send on the platform

**What the user sees.** After a like, the toast reads "Liked · Send in Sleeper" instead of
"Liked"; and when they have liked trades they have not sent, a count on the Matches tab ("3 liked,
not sent") that opens the list. No separate reminder push in the first version.

**What it needs.** Mobile copy and a count. To know "not sent", the server must join likes to
`trade_proposals` (same league, same counterparty, same assets); today nothing does
(section 1.2). Small.

**Sleeper's terms.** Unchanged: the send it leads to is the existing one.

**Risk.** Low. The main risk is nagging; a count on a tab is quieter than a push.

### Option 2: Push initial offers straight to Sleeper

**What the user sees.** A like becomes a real Sleeper offer, after one confirmation or none.

**What it needs.** Technically almost nothing: the deck already has a send button on every card.
The work is product: deciding that a swipe gesture sends.

**Sleeper's terms.** The same unofficial write, but at swipe volume rather than considered-send
volume, which is the pattern most likely to look automated to Sleeper. Every user would have to
hand over a full-account token before they could use the deck as designed.

**Risk.** High.
- **Volume and spam.** Decks are 8 to 30+ cards. A user who likes five in a session sends five
  real offers, often to the same few managers, many of them variants of one idea.
- **It breaks the learning loop.** Likes and passes train the user's board
  (`backend/server.py:22690-22700`). If a like sends, users will stop liking trades they would
  only half-accept, and the signal the engine learns from gets thinner.
- **It contradicts the app's promise** that proposals are sent only when the user taps send
  (`web/terms.html:102`), unless every like asks for confirmation, at which point it is the
  existing send button.

Not recommended. The send button already on every deck card is the version of this that keeps the
user's explicit tap.

### Option 3: A summary page of liked offers

**What the user sees.** A "Send list" (replacing or upgrading "Awaiting them"): every liked trade
that has not been sent, grouped by league-mate, newest first. Each row has "Send in Sleeper".
"Select" lets them tick several and tap "Send 3 offers", which shows one confirmation listing
each trade and recipient. Sent trades move to a "Sent" section showing the platform's answer
once WS2 records it (accepted, declined, countered, expired).

**What it needs.**
- Server: mark a like as sent by joining it to `trade_proposals`; a send-list read (or an
  extension of `GET /api/trades/awaiting`, `backend/server.py:27121`); the caps in question 4,
  enforced on the server.
- A batch send: either the app calls the existing propose route once per selected trade, or a
  small batch route runs `_sleeper_propose_core` per trade (the overhaul send already does this,
  `backend/overhaul_api.py:288,960`). Each trade succeeds or fails on its own; the confirmation
  reports each one.
- Guards: refuse a batch where one asset appears in two offers (they cannot both be accepted);
  at most one offer per league-mate per batch; re-check rosters per trade (already done in the
  core).
- New analytics events registered in the same commit as their emitters.
- Medium sized; mostly reuse.

**Sleeper's terms.** The same unofficial write as today. Batch sending increases the number of
writes per minute from one account; spacing them a few seconds apart costs little and looks less
automated (unverified whether Sleeper rate-limits writes; none is recorded in
`docs/integrations/sleeper.md`).

**Risk.** Moderate, and controlled by the caps. It keeps a deliberate decision between a like and
a send, and puts it where the user can see all their pending ideas at once.

### Option 4: A default direct message saying "This trade was built in Fleeced"

**What the user sees** (in the recommended form). After a successful send, a sheet: "Let them know
it's coming?" with a pre-written, editable message, for example "Sent you a trade offer in
[league]. This trade was built in Fleeced: <link>", and a "Send message" button that opens the
iPhone share sheet. The user picks Sleeper, Messages or anywhere else, and taps send there. "Not
now" and "Don't ask again" are one tap each. On MFL and ESPN the same text can go in the offer's
own comment field, shown and editable on the confirmation.

**What it needs (recommended form).** The existing share link (`/api/share/package`), the
existing share sheet code, new copy, an opt-out setting, and events. Small. Whether Sleeper
appears in the iPhone share sheet as a destination, and whether it lands in a specific chat, is
unverified: check on a phone with Sleeper installed. If it does not, the user pastes from the
clipboard, which is clumsier but still honest.

**What the automatic form would need.** The uncaptured `create_message` write (section 1.4),
message composition on the server, and a way to choose the conversation.

**Sleeper's terms (automatic form).** A second unofficial write, posting text into other people's
conversations under the user's account. The same prohibitions the repository already records
apply, and this one is visible to the recipient, who can report it. If Sleeper restricts an
account for it, the account is the user's, not Fleeced's.

**App Store (automatic form).** Unverified, from general knowledge: Apple's review guidelines
expect messages to other people to be visible to and sent by the user, and treat apps that message
people who did not ask (especially to promote the app) as spam. Check sections 4 (design, spam)
and 5.1.1 / 5.1.2 (data collection, use of other people's data) of the current App Store Review
Guidelines before building anything that sends automatically. The recommended form, where the
user composes and sends through the share sheet, is the ordinary pattern the share sheet exists
for.

**Recipients did not consent.** The league-mates are mostly not Fleeced users. WS2 already treats
them as people who did not consent (plan.md §3 WS2 "Constraints"). A promotional line arriving in
their messages every time a trade comes from a Fleeced user is advertising sent on Fleeced's
behalf, even if the user's account carries it.

**Volume per recipient.** In the offer history the proposer sent about 430 offers over roughly
four and a half years across three leagues, and 27 league-mates received eight or more. If every
offer carried a message, a heavily-targeted league-mate would see the same Fleeced line many times
a season, plus once per quick revision (103 offers were revised within 15 minutes). Starting
safeguards:
- the note offered at most **once per league-mate per seven days**, and never on a revision sent
  within an hour of the last offer to them;
- the link line ("built in Fleeced") offered at most **once per league-mate per season**; after
  that the note, if any, is the user's own words;
- per-user opt-out in Settings, and "Don't ask again" on the sheet itself.

**Reputation.** In a 12-team league everyone knows the sender. A line that reads as an ad, arriving
uninvited, lands on the user's reputation first and Fleeced's second, and a group of friends is
the audience most likely to mock it publicly. Shown sparingly, written by or editable by the user,
and with a real link to the trade (not just the app store), it reads as "I used a tool" rather
than spam. Automatic and repeated, it reads as spam.

**Safeguards that are not optional** (and that the recommended form satisfies by construction):
nothing is sent without an explicit tap; the user sees and can edit the full text before it goes;
per-recipient caps; one-tap opt-out; no message to anyone the user did not just send an offer to.

**Risk.** Recommended form: low. Automatic form: high, on terms, App Store review and reputation
at once.

## 4. How the options combine

The four options are not alternatives. The operator's direction reads naturally as one flow:
**like (private) → send list (option 3) → send (existing write, one tap and a confirmation) →
optional note (option 4, user-sent)**, with option 1 as the pointer to the list. Option 2 is the
one to leave out, and option 4's automatic form is the one to hold until the user-sent version
shows whether the note helps.

## 5. What "follow up after silence" becomes

R10's original idea was a nudge after silence. With WS2 Part A recording what happened to each
sent trade, the send list can show "No answer after 7 days" against a sent offer, with "Send a
revised offer" next to it once WS5's revision exists. That is the evidence-backed nudge (44% of
unanswered offers got no second try within a week), and it stays inside the list, not in a push.
It belongs after the first version, because it depends on WS2 and WS5.

## 6. Recommended first version

Small enough for the operator's three Sleeper leagues; behind its own flag (for example
`trade.send_list`, off), Sleeper only, and turned on for the operator's account only.

**In it**
1. **Send list** on the Matches screen in place of "Awaiting them": liked, not-yet-sent trades per
   league-mate, each with "Send in Sleeper"; "Select" and "Send N offers" with one confirmation
   listing every trade; a "Sent" section.
2. **Liked-and-sent joined** on the server, so a sent trade leaves the list and cannot be resent
   by accident.
3. **Caps** on the server: at most one offer per league-mate per batch, at most two per
   league-mate per seven days through the list, no asset in two offers of one batch, sends spaced
   a few seconds apart.
4. **"Liked · Send in Sleeper"** toast after a like, and a not-sent count on the Matches tab.
5. **After a send, the optional note**: pre-written, editable, sent by the user through the share
   sheet, using the existing package link; offered once per league-mate per week, link line once
   per league-mate per season; "Not now", "Don't ask again".

**What it measures** (ties to WS2: Part A's outcomes, flag `trade.outcome_tracking`, read off
`trade_proposals`)
- Like to send: share of liked trades sent within 7 days, and time from like to send.
- Sends per league-mate per week, and how often the caps bite.
- Outcome of each sent offer from WS2 (accepted, declined, countered, expired), compared with the
  offer history's 8% first-offer acceptance.
- **Whether threads continue**: share of unaccepted sent offers followed by another offer or a
  counter within 7 days, against the history's 56% (100% minus the 44% that died). This is the
  number R10 is about.
- Note uptake: share of sends where the note was opened, sent, edited, or turned off; and
  `invite_link_opened` / installs from the note's link.
- League-mates' reactions, asked directly by the operator (question 6). With three leagues and
  one proposer, this and the outcome log are the evidence; percentages will be too small to
  decide on alone.

**What it leaves out, on purpose**
- Automated Sleeper direct messages, and capturing `create_message`.
- Likes that send (option 2).
- Reminder pushes about unsent likes or silent offers.
- ESPN and MFL, including their comment fields (a cheap follow-on once the wording is settled).
- The "No answer after 7 days, send a revised offer" row (needs WS2 and WS5).
- Any change to the deck's existing send button or to how likes train the board.

**Before building:** the builder fills the feature scope block
([template](../../templates/feature-scope.md)) as `scope-send-on-platform.md` in this folder,
including the new events and the two Sleeper checks in section 7.

## 7. What could not be established from the repository

- Whether Sleeper notifies the recipient (push, in-app alert or chat message) when a trade is
  proposed through Fleeced's write. Check: send one in a test league and look at the other phone.
- Whether Sleeper's own propose screen posts the chat message always, or only when the proposer
  chooses to. Check: propose on sleeper.com in a test league.
- The shape of Sleeper's `create_message` call. Never captured.
- The current text of Sleeper's terms. The repository holds only the 2026-07-02 summary
  (`docs/plans/sleeper-write-capture-runbook.md:137`); read the live terms before deciding
  question 2.
- The current App Store Review Guidelines wording on messaging and spam. Not in the repository;
  section 3's reading is general knowledge.
- Whether Sleeper appears as a destination in the iPhone share sheet and lands in a chosen chat.
- Whether Sleeper limits how fast one account may propose trades, or how many pending offers one
  manager may hold from another.
- How many likes a Fleeced user makes per session, and how many go unsent. That needs a
  production read of `trade_decisions` against `trade_proposals`, not done here.
- Whether production overrides any flag cited here (Render's `FTF_FLAGS` beats
  `config/features.json` and is not in the repository).

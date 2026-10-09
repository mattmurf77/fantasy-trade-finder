# Dynasty Trade Lab — Dashboard page (operator logged in, 2026-10-09)

URL: https://dynastytradelab.com/dashboard/ — three columns.

**Left — LAB ANALYST (3 credits):** chat panel. Replies render as highlighted yellow blocks; the panel footer shows a per-conversation usage bar ("33% … 1 credit") and the input caption "This message is included in your current credit — no charge" — i.e. one credit buys a chat conversation with a usage budget, not one message. Account line "mattmurf77 · ADD A LEAGUE". Input "Ask Lab Analyst a question…" + Send. Replies deep-link to the Trade Generator for packaged offers.

**Middle — PLAYER STOCK MOVEMENT:** league-wide weekly value movers, each row = position badge, player, NFL team · rostering manager, value, weekly delta (green ▲ / red ▼). Top of list this week: Ollie Gordon ▲1,285 · Kyren Williams ▲1,171 · Omarion Hampton ▼1,133 · Justin Jefferson ▼1,054 · De'Von Achane ▼1,043 · Kenneth Walker ▲961 · Drake London ▲932 · Michael Wilson ▲881 · … Zay Flowers ▲679 · Jaylen Waddle ▼647 · Matthew Golden ▲619 · David Montgomery ▼607 · Javonte Williams ▲602 · DeVonta Smith ▼594 · TreVeyon Henderson ▼586 · Jaylen Warren ▲585. Scrollable list.

**Right — RISING FA STOCK:** unrostered risers in this league: Kalif Raymond 747 ▲175 · Jerry Jeudy 767 ▲155 · Tyson Bagent 521 ▲2.

**Credits:** the operator's balance read 5 credits on the Generator page and 3 on the Dashboard panel header during the same session — a credit was consumed by the chat conversation and (likely) one by a generation; to be confirmed when I drive.

Observation: the dashboard is a "what changed this week" surface (movers + FA risers) wrapped around the chat. Nothing on it is personalised beyond the league scope and the chat; there is no trade inbox, no suggestions feed, no notifications.

## Footer and credit rules (seen 2026-10-09 while driving)

- **Site footer:** "© 2026 Dynasty Trade Lab All rights reserved. Privacy Policy · Terms of Service · **Player values by FantasyCalc** · Contact Us" and "League data via **Sleeper** and **Fantrax**. Dynasty Trade Lab is not affiliated with, endorsed by, or sponsored by Sleeper (Blitz Studios, Inc.), Fantrax, or the NFL." → the value scale is FantasyCalc's, not a house model, despite the landing copy "not a static dynasty trade value chart".
- Stock-movement captions: "Value movement since 09-24-2026" (league movers) and "Value movement since 09-28-2026" (FA risers) — deltas are vs a dated snapshot, not rolling 7-day.
- **Chat credit rule (caption under the input):** "Starts a new 3-message credit — 1 credit now, then your next 2 messages are free." The usage bar (33% → 67% → 100%) is the message count inside the current credit. So 1 credit = 3 Lab Analyst messages; a generation presumably = 1 credit (to confirm).
- Chat transport: one `POST https://dynastytradelab.com/wp-json/dtl/v1/lab-analyst` per message (200, ~15 s round trip for a ~250-word answer); no streaming.

## Top of the Dashboard — TEAM STATUS and TEAM NEEDS (page text, 2026-10-09)

Header: "● 3 credits · Get more" · "VIEWING: Sleeper · Fantasy Football Version 3 · Switch".

**TEAM STATUS (mattmurf77): "2nd"** with per-position rank chips QB · RB · WR · TE · FLEX · Dynasty Value. "Record: 3-1 · League rank 2nd of 12." Explainer: "Each position rank compares your total positional value (all players at that position) to every other manager's; FLEX ranks your RB/WR/TE depth beyond starter slots."

**TEAM NEEDS (mattmurf77): BALANCED**
- **HOLD** — "No gaps and nothing thin. There is no hole to pay for, so buy value where you find it and let other managers come to you."
- **SPEND — TE Isaiah Likely** — "Stuck behind Trey McBride at TE. He is a real asset to somebody else and zero points to you."
- **TRADE BLOCK — WR Davante Adams** — "5 teams are short where he fits, so you can shop him against each other."
- **WHO TO CALL** — JohnStanfield "2-2, weakest at WR. Short where 2 of your spare pieces fit." · PaulSm3nis "1-3, weakest at WR/RB. Short where 2 of your spare pieces fit." · dondags20 "0-4, weakest at WR/TE. Short where 2 of your spare pieces fit."
- **HOLD (list)** — Drake Maye, Ashton Jeanty, De'Von Achane, Jaxon Smith-Njigba, Drake London, Trey McBride, Quinshon Judkins.
- **PLAYERS TO TARGET** — "Nobody in this league owns an upgrade on what you already start."

Observation: this block is DTL's actual "needs engine" — deterministic, template-copy output (hold / spend / trade block / who to call / targets) computed from positional value totals, starter-slot body floor, and other managers' shortfalls, with record used as a contender/seller cue. The Lab Analyst chat is layered on top of these same outputs. "Nobody owns an upgrade on what you already start" contradicts the chat's upgrade-candidate list (Gibbs, Bijan, Walker…) — the needs engine seems to define "upgrade" relative to the user's starters at a *startable* position gap, while the chat uses raw value rank.

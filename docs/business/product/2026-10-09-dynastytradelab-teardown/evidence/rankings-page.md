# Dynasty Trade Lab — Rankings page (logged in, 2026-10-09)

URL: https://dynastytradelab.com/rankings/ · "Dynasty Player Rankings · Updated Oct 8, 2026 10:42 AM EDT" (daily-ish refresh timestamp shown; values match the FantasyCalc attribution in the footer).

- Format toggle: **1QB | SF/2QB** (default 1QB even though the viewing league is "Sleeper · Fantasy Football Version 3"; the page does not auto-select the league's format).
- Position filters: ALL · QB · RB · WR · TE · **Free Agents** · **Rookie** (Free Agents = unrostered in the viewing league). Sort: Overall ▲ · Age · Position · Proj · Trend · Value. Player search box.
- Columns per row: rank, headshot, name, position, NFL team, **age to one decimal**, positional rank (#1 RB), **Proj (empty "—" for every player)**, Trend (weekly delta ▲/▼, same numbers as the dashboard movers), Value.
- **397 players listed** in 1QB/ALL; top 15: Gibbs 10,760 · Bijan 10,592 · JSN 9,628 · Chase 8,052 · ARSB 7,339 · Nacua 7,271 · K. Walker 7,179 · Lamb 6,855 · Bowers 6,743 · Jeanty 6,704 · J. Love 6,423 · J. Taylor 6,179 · McBride 5,909 · Jefferson 5,823 · Josh Allen 5,613 (#1 QB at overall #15 ⇒ 1QB scale). Bottom of list: values in the 9–60 range (Stetson Bennett 9).
- No draft picks on this page (picks only appear in the Generator's roster panel and the chat's round-level table).
- Players without an NFL team show a blank team cell (Tyreek Hill, Joe Mixon, Austin Ekeler, Zach Ertz, Will Levis, Henry Ruggs, Brandin Cooks…) — free agents/retired still carry values.
- Rookie filter and Proj column exist in the UI but Proj had no data on this date; the `me/projections` REST route exists in the bundle, so projections are a built-but-empty feature here.

## SF/2QB toggle (clicked 2026-10-09)

Switching to SF/2QB swaps in a second value table (FantasyCalc's superflex set): Josh Allen 10,998 · Gibbs 10,337 · Bijan 10,175 · JSN 10,087 · Chase 8,437 · Bowers 7,725 · ARSB 7,689 · Nacua 7,617 · Lamb 7,182 · Lamar 6,995 · K. Walker 6,896 · Caleb Williams 6,837 · McBride 6,769 · Jeanty 6,440 · Burrow 6,331 · J. Love 6,170 · Jefferson 6,101 · Maye 6,037 · J. Taylor 5,936 · Purdy 5,891 … Trend deltas differ from the 1QB table too, so both tables are refreshed independently.

The viewing league's Generator, chat and dashboard all used the **1QB** numbers (Josh Allen 5,613; Maye 3,081). Operator confirmed 2026-10-09 that "Fantasy Football Version 3" is a 1QB league, so this is correct; the chat's "QB min 2" body floor is a depth cushion, not a lineup slot. Untested: whether DTL auto-selects the SF table for a superflex league.

Nav links discovered (header/menu): Buy Credits → /credits/ · Dashboard · Rankings · My Account → /my-account/ (WooCommerce) · My Trade Lab → /account/ · History → /account/?section=trade-history · Login /login/ · Register /register/ · Generate Trades → /dynasty-trade-generator/.

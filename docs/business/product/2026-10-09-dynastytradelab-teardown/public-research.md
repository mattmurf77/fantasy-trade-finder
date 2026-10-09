# Dynasty Trade Lab — public-source research (2026-10-09)

Method: WebFetch of the site's own pages and the Product Hunt listing, WebSearch across the dynasty-tools landscape. Every claim cites the page opened; quotes are verbatim. Dead ends are listed so the next pass doesn't repeat them.

## 1. Company and launch

- **Operator:** the privacy policy names only "Dynasty Trade Lab ('DTL,' 'we,' 'us,' or 'our') operates the Dynasty Trade Lab website and application" — no legal entity type, no address; the contact page has a form only (subjects: Provide Feedback / Write a Review / Tech Support, plus "How did you hear about us?"). [privacy-policy](https://dynastytradelab.com/privacy-policy/) · [contact](https://dynastytradelab.com/contact/)
- **Maker:** Michael Chamberlin (Product Hunt maker page; no bio, location or socials shown). [PH makers](https://www.producthunt.com/products/dynasty-trade-lab/makers)
- **Launch:** Product Hunt post "Launched 2mo ago" / "Launched in 2026", maker's launch comment "3mo ago" (≈ July 2026); privacy policy "Last updated: June 15, 2026". So: built mid-2026, launched July–August 2026. [PH post](https://www.producthunt.com/posts/1204598)
- **Maker's own framing (PH launch comment):** "Built this after getting frustrated with trade calculators that ignore your actual roster construction and league settings." / "DTL pulls your real Sleeper/Fantrax team, runs FantasyCalc values against your specific format, and surfaces trades — including 3-team deals — that actually make sense for both sides." — i.e. the maker says FantasyCalc values in public, which the landing copy obscures. [PH product](https://www.producthunt.com/products/dynasty-trade-lab)
- **Tagline / description (PH):** "AI dynasty trade analyzer built around your actual roster" · "Built by a dynasty player who was tired of generic value charts." · "Get a weekly stock report on risers/fallers in your league, plus a League Analyzer that flags your team's real strengths and needs." · "5 free credits, no card required." Topics: Sports, SaaS, Artificial Intelligence. Pricing field: "Free."
- **Scale signals:** PH listing has **3 upvotes, 8 followers, 3 comments** (one is the maker's). Combined with the sequential report id (276) seen hands-on, this is a solo indie product with a very small user base. Domain registration date: RDAP lookup returned 403 (dead end).

## 2. What the site says about itself (FAQ, landing)

- "A dynasty trade calculator estimates trade value for players and draft picks in dynasty fantasy football leagues." / "Trade values are powered by continuously updated rankings." (the FAQ never says FantasyCalc; the footer does). [landing](https://dynastytradelab.com/)
- Superflex: "is built on true dynasty-specific logic covering Superflex, 2QB, 1QB, and PPR formats" and that its superflex rankings adjust QB values for two-QB lineups — consistent with the two FantasyCalc tables seen on the Rankings page.
- Free trial: 5 free credits, no card.
- **Privacy policy is partly boilerplate:** it says fantasy data comes from "Sleeper, ESPN, and Yahoo Fantasy, accessed via OAuth or API integration" and that billing retains "your subscription tier, billing period, and last-four card digits" — the product has no ESPN/Yahoo integration (Sleeper by username, Fantrax) and no subscriptions (credit packs). Payments: "processed by a third-party payment processor (such as Stripe)". No AI/LLM provider is named anywhere on the site.

## 3. Community and sentiment

- Only public discussion found: the three Product Hunt comments. User 1 (2mo ago, Superflex league): the 3-way suggestions "actually came back with players I'd realistically consider, not just a stack of value chart mismatches"; "The weekly stock report is the part I didn't expect to care about, but it's already helped me catch a buy-low window." User 2 (2mo ago, 2 upvotes): "Love that it handles 3-way trades since that is usually the hardest part of dynasty deals." — and asks for "do not trade" / "trade at a premium" tags on own players (DTL has a trade-block badge but no untouchables; Fleeced has untouchables). [PH product](https://www.producthunt.com/products/dynasty-trade-lab)
- **Dead ends:** Reddit is blocked to our crawler (search error), and no Reddit, X, YouTube, podcast or Discord mention surfaced in general search; "Dynasty Trade Lab" collides with unrelated names (The Dynasty Lab Podcast, Upper Hand's "Dynasty Lab" $199/yr product, Dynasty Data Lab, Rookie Draft Lab), which will also hurt their SEO.

## 4. Landscape

- FantasyPros' "Best Dynasty Fantasy Football Trade Tools (2026)" (Aug 1, 2026) ranks FantasyPros Trade Analyzer, FantasyPros Trade Finder, KeepTradeCut, DLF Trade Analyzer, FantasyCalc — **DTL is not mentioned**. [fantasypros](https://www.fantasypros.com/2026/08/best-dynasty-fantasy-football-trade-tools/)
- The closest analogue by positioning is [Dynasty Dealmaker](https://www.dynastydealmaker.com/) ("AI-Powered Fantasy Football Trade Generator", with its own 3-way trades post) — both sell "AI generator over your Sleeper roster". Also in the space: dynastydatalab.com (trade search over real Sleeper transactions), dynastytradecalculator.co (has a "Trade Lab" section), rosteraudit.com ("values from real trades"), dynatyze.com ("graded both ways"), the Tradyr Firefox extension (KTC+FantasyCalc composite on Sleeper trade pages).
- No App Store / Google Play / extension presence found for DTL; the site's phone mockups are the responsive web app.

## 5. What this adds to the hands-on teardown

Observation: an indie, ~2-month-old, FantasyCalc-based web tool with single-digit public traction, whose public pitch leans on three-team trades and the weekly stock report (both of which users mention), while the League Analyzer it advertises on PH has no entry point on the site today. Judgment: not a market threat; a useful mirror for what a solo dev can ship in a summer on WordPress + an LLM, and for which framings ("built around your actual roster", "3-way deals most tools skip") land with dynasty players. Recommendation routing is in [teardown.md](teardown.md) §7.

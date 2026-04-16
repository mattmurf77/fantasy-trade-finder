# Fantasy Trade Finder

A dynasty fantasy football app that helps you rank players and discover mutually beneficial trades with your leaguemates. Log in with your Sleeper username, import your roster, rank players through a swipe-based interface, and get personalized trade suggestions based on valuation mismatches between you and your league.

## How It Works

1. **Log in** with your Sleeper username (no account creation needed)
2. **Rank players** by ordering 3-player matchups — the app uses an Elo rating system to build your personal player valuations
3. **Find trades** once you've ranked enough players — the engine compares your rankings against your leaguemates to surface trades where both sides gain value
4. **Match trades** — when you and a leaguemate both like the same trade, it shows up in the Matches tab for you to accept or decline

## Features

- Elo-based ranking system seeded from DynastyProcess consensus values
- 3-player matchups that are 2.6x more efficient than simple pairwise comparisons
- Trade suggestions across 1-for-1, 2-for-1, 1-for-2, and 3-for-2 configurations
- Team outlook settings (championship, contender, rebuilder) that shape which trades surface
- KTC-style dynasty value display on all trade cards
- Mutual trade matching with accept/decline workflow
- Works with any Sleeper dynasty league

## Tech Stack

- **Backend:** Python / Flask
- **Database:** SQLite (local), designed to swap to PostgreSQL via `DATABASE_URL`
- **Frontend:** Vanilla HTML/CSS/JS
- **Data Sources:** Sleeper API, DynastyProcess consensus values

## Local Development

```bash
pip install -r requirements.txt
python run.py
```

Open http://localhost:5000 in your browser.

## Deployment

The app is configured for Render. Push to GitHub, connect the repo on [render.com](https://render.com), and the `render.yaml` handles the rest.

## License

MIT

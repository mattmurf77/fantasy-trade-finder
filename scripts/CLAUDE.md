# scripts/ — Notes for Claude

One-off utility / seeding scripts. Run from the repo root with the same Python env as the backend.

- `create_test_league.py` — fabricate a league for local testing
- `seed_test_user.py`, `seed_test_user_2.py` — seed users with rosters + rankings
- `publish_test_rankings.py` — push canned rankings into the DB
- `demo_matchup.py` — exercise the smart matchup generator end-to-end

These touch the local DB. Don't run against production.

import json, sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///data/trade_finder.db')
with engine.connect() as conn:
    # Check both league IDs - get member detail for the more recent one
    for league_id in ['1101407304802574336', '1312076055586050048']:
        print(f"\n=== LEAGUE {league_id} ===")
        rows = conn.execute(text(
            "SELECT user_id, username, display_name, roster_data FROM league_members WHERE league_id=:lid ORDER BY username"
        ), {"lid": league_id}).fetchall()
        for r in rows:
            roster = json.loads(r[3]) if r[3] else []
            print(f"  {r[1]} ({r[0]}) — {len(roster)} players")
            print(f"    first 5: {roster[:5]}")

    # Also show the leagues table opponent_data shape
    print("\n=== LEAGUES TABLE (opponent_data sample) ===")
    rows = conn.execute(text("SELECT sleeper_league_id, name, user_id, roster_data FROM leagues")).fetchall()
    for r in rows:
        rd = json.loads(r[3]) if r[3] else []
        print(f"  {r[1]} | league={r[0]} | owner={r[2]} | owner_roster_size={len(rd)}")

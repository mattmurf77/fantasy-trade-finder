import json, sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text

db_path = 'data/trade_finder.db'
engine = create_engine(f'sqlite:///{db_path}')

with engine.connect() as conn:
    leagues = conn.execute(text("SELECT sleeper_league_id, user_id, name, season FROM leagues")).fetchall()
    print("=== LEAGUES ===")
    for r in leagues:
        print(f"  id={r[0]} | user={r[1]} | name={r[2]} | season={r[3]}")

    print("\n=== LEAGUE MEMBERS (with roster sizes) ===")
    members = conn.execute(text("SELECT league_id, user_id, username, display_name, roster_data FROM league_members ORDER BY league_id")).fetchall()
    for r in members:
        roster = json.loads(r[4]) if r[4] else []
        print(f"  league={r[0]} | user={r[1]} | username={r[2]} | roster_size={len(roster)}")

    print("\n=== USERS ===")
    users = conn.execute(text("SELECT sleeper_user_id, username, display_name FROM users")).fetchall()
    for r in users:
        print(f"  id={r[0]} | username={r[1]} | display={r[2]}")

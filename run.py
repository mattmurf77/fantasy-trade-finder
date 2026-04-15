"""
run.py — Fantasy Trade Finder
===============================
Entry point. Launch the app from the project root:

    python run.py

Then open http://127.0.0.1:5000 in your browser.
"""

from backend.server import app, _load_sleeper_cache, _maybe_sync_players

# Pre-load Sleeper player cache from disk if available
_load_sleeper_cache()

# Sync player cache to DB (no-op if data is fresh, runs in ~1 s)
_maybe_sync_players()

if __name__ == "__main__":
    print("\n🏈 Fantasy Trade Finder — Dynasty Rankings")
    print("   Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=True, host='0.0.0.0', port=5000)

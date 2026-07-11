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
    import os
    # PORT override: the UI-test harness runs on :5001 because macOS AirPlay
    # Receiver (ControlCenter) squats on :5000 (see docs/runbook.md).
    port = int(os.environ.get("PORT", "5000"))
    # Under the UI-test harness the debug auto-reloader is a hazard: it
    # restarts Flask mid-run when files change (killing in-memory sessions).
    test_mode = os.environ.get("FTF_TEST_MODE") == "1"
    print("\n🏈 Fantasy Trade Finder — Dynasty Rankings")
    print(f"   Open http://127.0.0.1:{port} in your browser\n")
    app.run(debug=not test_mode, use_reloader=not test_mode,
            host='0.0.0.0', port=port)

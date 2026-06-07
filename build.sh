#!/usr/bin/env bash
# Render build script — runs on every deploy
set -o errexit

pip install -r requirements.txt

# Ensure the data directory exists (SQLite DB lives here)
mkdir -p data

# ── Bake the Sleeper player cache into the deploy image (best-effort) ──────────
# Render's free tier has no persistent disk, so a cold container would otherwise
# re-pay a synchronous ~5MB fetch from api.sleeper.app on the first session/init.
# We pre-warm data/.sleeper_players_cache.json here at build time by invoking the
# SAME runtime fetch+filter+write path (_ensure_sleeper_cache_populated), so the
# baked file is byte-for-byte the QB/RB/WR/TE-filtered shape the runtime writes —
# no risk of shape drift between the baked and runtime-refreshed cache.
#
# The file stays gitignored (data/) — it is produced at build time, never
# committed. It is a *floor*, not the source of truth: the nightly sync_players
# refresh still overwrites it with fresh data, bounding staleness to ~1 day, and
# the runtime lazy-load remains the fallback.
#
# Best-effort by design: if Sleeper is down or the network/import fails, the
# `|| true` (with errexit temporarily disabled) keeps the build green and the
# runtime lazy-load path takes over on first request, exactly as before.
echo "→ Baking Sleeper player cache (best-effort)…"
set +o errexit
python -c "from backend.server import _ensure_sleeper_cache_populated; _ensure_sleeper_cache_populated()" \
  && echo "✓ Sleeper player cache baked into data/.sleeper_players_cache.json" \
  || echo "⚠ Sleeper cache bake skipped (fetch/import failed) — runtime lazy-load will populate on first request"
set -o errexit

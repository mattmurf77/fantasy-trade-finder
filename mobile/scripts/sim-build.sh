#!/usr/bin/env bash
# sim-build.sh — build pipeline for the UI-test harness (C4).
# docs/plans/mobile-testing/lld.md §2.3
#
#   sim-build.sh [--api-base <url>] [--env test|prod-check] [--out <dir>]
#
#   --env test (default): Release-config simulator build with the JS bundle
#     embedded, FTF_API_BASE_URL baked in, Sentry DSN nulled. Emits
#     <out>/resolved-config.json for the runner's preflight (C9).
#   --env prod-check: statically evaluates app.config.js with NO env and
#     asserts the shipping config (Render URL + real DSN). Never builds.
#
# Exit codes: 0 ok · 2 xcodebuild/expo failure · 3 safety check failed · 4 bad args/missing workspace
set -uo pipefail

MOBILE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# The two variables prebuild regeneration could rename (lld.md §6):
WORKSPACE="$MOBILE_DIR/ios/DTFDynastyTradeFinder.xcworkspace"
SCHEME="DTFDynastyTradeFinder"

# :5001 not :5000 — macOS AirPlay Receiver (ControlCenter) squats on 5000 (runbook)
API_BASE="http://127.0.0.1:5001"
MODE="test"
OUT="$MOBILE_DIR/ios/build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base) API_BASE="$2"; shift 2 ;;
    --env)      MODE="$2"; shift 2 ;;
    --out)      OUT="$2"; shift 2 ;;
    *) echo "sim-build.sh: unknown arg $1" >&2; exit 4 ;;
  esac
done

resolved_config() {  # $1 = "test" | ""
  if [[ "$1" == "test" ]]; then
    FTF_ENV=test FTF_API_BASE_URL="$API_BASE" \
      npx --prefix "$MOBILE_DIR" expo config --type public --json 2>/dev/null
  else
    env -u FTF_ENV -u FTF_API_BASE_URL \
      npx --prefix "$MOBILE_DIR" expo config --type public --json 2>/dev/null
  fi
}

extra_field() {  # stdin: expo config json; $1: field
  python3 -c "import json,sys; print(json.load(sys.stdin).get('extra',{}).get('$1') or '')"
}

if [[ "$MODE" == "prod-check" ]]; then
  cfg="$(cd "$MOBILE_DIR" && resolved_config "")" || exit 2
  url="$(echo "$cfg" | extra_field apiBaseUrl)"
  dsn="$(echo "$cfg" | extra_field sentryDsn)"
  [[ "$url" == *onrender.com* ]] || { echo "prod-check FAIL: apiBaseUrl=$url (expected Render URL)" >&2; exit 3; }
  [[ -n "$dsn" ]] || { echo "prod-check FAIL: sentryDsn is empty in the shipping config" >&2; exit 3; }
  echo "prod-check OK: apiBaseUrl=$url, sentryDsn present"
  exit 0
fi

[[ "$MODE" == "test" ]] || { echo "sim-build.sh: --env must be test|prod-check" >&2; exit 4; }
[[ -d "$WORKSPACE" ]] || { echo "sim-build.sh: workspace not found: $WORKSPACE" >&2; exit 4; }

# --- Preflight rails (exit 3 before any build) — prd.md R-03/R-04 -----------
if [[ -n "${EXPO_PUBLIC_SENTRY_DSN:-}" ]]; then
  echo "FAIL: EXPO_PUBLIC_SENTRY_DSN is set in the build environment — the second DSN" >&2
  echo "source (mobile/src/observability/sentry.ts:31) would resurrect Sentry in a test build." >&2
  exit 3
fi
mkdir -p "$OUT"
cfg="$(cd "$MOBILE_DIR" && resolved_config test)" || exit 2
echo "$cfg" > "$OUT/resolved-config.json"
url="$(echo "$cfg" | extra_field apiBaseUrl)"
dsn="$(echo "$cfg" | extra_field sentryDsn)"
[[ "$url" == "$API_BASE" ]] || { echo "FAIL: resolved apiBaseUrl=$url != requested $API_BASE" >&2; exit 3; }
case "$url" in *onrender.com*) echo "FAIL: test build resolves to Render prod" >&2; exit 3 ;; esac
[[ -z "$dsn" ]] || { echo "FAIL: sentryDsn not nulled in test build" >&2; exit 3; }

# --- Build -------------------------------------------------------------------
echo "Building Release sim app (apiBaseUrl=$API_BASE) → $OUT"
( cd "$MOBILE_DIR" && \
  FTF_ENV=test FTF_API_BASE_URL="$API_BASE" \
  SENTRY_DISABLE_AUTO_UPLOAD=true \
  xcodebuild -workspace "$WORKSPACE" -scheme "$SCHEME" -configuration Release \
    -sdk iphonesimulator -derivedDataPath "$OUT" \
    ONLY_ACTIVE_ARCH=YES ARCHS=arm64 build ) || exit 2
  # ONLY_ACTIVE_ARCH: Release defaults to building x86_64 too, and ExpoFont's
  # Swift compile fails on that slice (2026-07-11) — local sims are arm64-only.

APP="$(find "$OUT/Build/Products" -maxdepth 2 -name "*.app" -path "*iphonesimulator*" | head -1)"
[[ -n "$APP" ]] || { echo "FAIL: built .app not found under $OUT" >&2; exit 2; }

# --- Post-build bundle safety check (lld.md §2.3) ----------------------------
# The EXConstants build phase serializes the app config the binary will see.
# Verify the EMBEDDED config, not just our own evaluation: if the baked
# apiBaseUrl still actively resolves to prod while we asked for localhost,
# the env didn't reach the bundling phase (S1 spike question) — hard fail.
EMBEDDED="$(find "$APP" -name "app.config" -o -name "EXConstants.plist" 2>/dev/null | head -1)"
if [[ -n "$EMBEDDED" ]]; then
  if grep -q "$API_BASE" "$EMBEDDED" 2>/dev/null; then
    echo "OK: embedded config carries $API_BASE"
  elif grep -q "onrender.com" "$EMBEDDED" 2>/dev/null; then
    echo "FAIL: embedded config still points at Render — FTF_API_BASE_URL did not reach the bundling phase" >&2
    echo "      (fallback: mobile/.env.test + dotenv in app.config.js — lld.md §2.3 open item)" >&2
    exit 3
  else
    echo "WARN: embedded config found but carries neither URL — inspect $EMBEDDED" >&2
  fi
else
  echo "WARN: no embedded app.config/EXConstants.plist found in $APP — verify env transport manually" >&2
fi

echo "APP=$APP"
echo "sim-build OK"

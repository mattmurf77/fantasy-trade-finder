#!/usr/bin/env bash
# sim-run.sh — single-cell executor (C6 unit). docs/plans/mobile-testing/lld.md §2.2
#
#   sim-run.sh --udid <UDID> --app <path/to/.app> --profile <name>
#              [--flags <json-or-@file>] [--seed <int>] [--flow <file-or-tag>]
#              [--keep-data] [--report-dir <dir>]
#
# Steps: seed → start Flask (test mode) → handshake → sim erase/boot → install
#        → maestro flows (if --flow given and maestro installed) → collect → stop.
# Exit codes (lld.md §2.1): 0 ok · 1 flow failure · 2 infra · 3 rails · 5 bad args
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
UDID="" APP="" PROFILE="" FLAGS="" SEED="1337" FLOW="" KEEP_DATA=0
REPORT_DIR="$REPO/mobile/test-artifacts/$(date +%Y%m%dT%H%M%S)-cell"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --udid) UDID="$2"; shift 2 ;;
    --app) APP="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --flags) FLAGS="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --flow) FLOW="$2"; shift 2 ;;
    --keep-data) KEEP_DATA=1; shift ;;
    --report-dir) REPORT_DIR="$2"; shift 2 ;;
    *) echo "sim-run.sh: unknown arg $1" >&2; exit 5 ;;
  esac
done
[[ -n "$UDID" && -n "$APP" && -n "$PROFILE" ]] || { echo "need --udid --app --profile" >&2; exit 5; }
mkdir -p "$REPORT_DIR"

# --- Rails: refuse a build that resolves off-localhost (prd.md R-03) --------
RC="$(dirname "$APP")/../../../resolved-config.json"   # emitted next to derivedData by sim-build
for cand in "$RC" "$(dirname "$APP")/resolved-config.json" "$REPO/mobile/ios/build/resolved-config.json"; do
  [[ -f "$cand" ]] && { RC="$cand"; break; }
done
if [[ -f "$RC" ]]; then
  URL="$(python3 -c "import json;print(json.load(open('$RC')).get('extra',{}).get('apiBaseUrl',''))")"
  case "$URL" in
    *onrender.com*) echo "RAILS: app resolves to Render prod — refusing (exit 3)" >&2; exit 3 ;;
    http://127.0.0.1*|http://localhost*) : ;;
    *) echo "RAILS: app resolves to non-localhost '$URL' — refusing (exit 3)" >&2; exit 3 ;;
  esac
  export PORT="${URL##*:}"   # Flask must listen where the app will call (default 5001; :5000 is AirPlay's)
else
  echo "RAILS: no resolved-config.json found near $APP — cannot verify base URL (exit 3)" >&2; exit 3
fi

# --- Seed + backend ----------------------------------------------------------
SEEDER="$REPO/backend/tests/fixtures/seed_ui_test_db.py"
[[ -f "$SEEDER" ]] || { echo "seeder missing: $SEEDER" >&2; exit 2; }
ENVBLOCK="$(cd "$REPO" && python3 "$SEEDER" --profile "$PROFILE" --seed "$SEED" --print-env)" || exit 2
set -a; eval "$ENVBLOCK"; set +a
[[ -n "$FLAGS" ]] && export FTF_FLAGS="$FLAGS"

( cd "$REPO" && PORT="$PORT" python3 run.py ) > "$REPORT_DIR/flask.log" 2>&1 &
FLASK_PID=$!
trap 'kill $FLASK_PID 2>/dev/null' EXIT

# Handshake (30 s budget): whoami reports our profile AND flags round-trip.
for i in $(seq 1 30); do
  WHO="$(curl -sf "$URL/__test__/whoami" 2>/dev/null)" && break
  sleep 1
done
[[ -n "${WHO:-}" ]] || { echo "INFRA: Flask handshake failed (see flask.log)" >&2; exit 2; }
echo "$WHO" | FLASK_PID="$FLASK_PID" python3 -c "
import json,sys,os
w=json.load(sys.stdin)
assert w['test_mode'] and w['fixtures'], 'not in fixture test mode'
assert w['profile']==os.environ.get('FTF_TEST_PROFILE'), 'profile mismatch'
assert str(w.get('pid'))==os.environ.get('FLASK_PID'), (
    'STALE FLASK: whoami pid %s != started pid %s — another instance holds the port' % (w.get('pid'), os.environ.get('FLASK_PID')))
" || { echo "INFRA: whoami mismatch (see above): $WHO" >&2; exit 2; }
PINNED="$(curl -sf "$URL/api/feature-flags")" || { echo "INFRA: flags fetch failed" >&2; exit 2; }
echo "$PINNED" > "$REPORT_DIR/flags.json"

# --- Simulator ---------------------------------------------------------------
if [[ "$KEEP_DATA" -eq 0 ]]; then
  xcrun simctl shutdown "$UDID" 2>/dev/null; xcrun simctl erase "$UDID" || { echo "INFRA: erase failed" >&2; exit 2; }
fi
xcrun simctl boot "$UDID" 2>/dev/null || true
xcrun simctl bootstatus "$UDID" -b || { echo "INFRA: boot failed" >&2; exit 2; }
xcrun simctl install "$UDID" "$APP" || { echo "INFRA: install failed" >&2; exit 2; }

# --- Flows (optional until Maestro lands) ------------------------------------
if [[ -n "$FLOW" ]]; then
  command -v maestro >/dev/null || { echo "INFRA: maestro not installed (brew install maestro)" >&2; exit 2; }
  maestro --device "$UDID" test "$FLOW" --format junit --output "$REPORT_DIR/junit.xml"
  RESULT=$?
  curl -sf -X POST "$URL/__test__/reset" >/dev/null
else
  xcrun simctl launch "$UDID" com.fantasytradefinder.app || { echo "INFRA: launch failed" >&2; exit 2; }
  echo "No --flow given: app launched against profile '$PROFILE' for manual/S2 verification."
  RESULT=0
fi

# --- Rails audit + collect ----------------------------------------------------
WHO_END="$(curl -sf "$URL/__test__/whoami")"; echo "$WHO_END" > "$REPORT_DIR/whoami-end.json"
echo "$WHO_END" | python3 -c "
import json,sys
c=json.load(sys.stdin)['counters']
bad={k:v for k,v in c.items() if k in ('vcr_misses','sleeper_live_egress_attempts','completed_proposes') and v>0}
sys.exit(4 if bad else 0)" || { echo "RAILS TRIPPED: $(echo "$WHO_END")" >&2; exit 4; }
exit "$RESULT"

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
# Flag pinning: profile manifest ∪ --flags, per key, --flags wins (lld.md §2.5
# "flags_base ∪ flag_overrides ∪ --flags"). The env block above already exported
# the profile's FULL seeded flag map; --flags MERGES over it. A bare replace
# silently dropped every profile flag_override, so a one-key override ran the
# cell against a flag state nobody asked for. `--flags` takes inline JSON or
# @path/to/file.json; anything unparseable is a hard exit 5, never a warning.
if [[ -n "$FLAGS" ]]; then
  if [[ "$FLAGS" == @* ]]; then
    FLAGS_FILE="${FLAGS#@}"
    [[ -f "$FLAGS_FILE" && -r "$FLAGS_FILE" ]] \
      || { echo "BAD ARGS: --flags @$FLAGS_FILE — file missing or unreadable" >&2; exit 5; }
    FLAGS="$(cat "$FLAGS_FILE")" \
      || { echo "BAD ARGS: --flags @$FLAGS_FILE — read failed" >&2; exit 5; }
  fi
  BASE_FLAGS="${FTF_FLAGS:-}"; [[ -n "$BASE_FLAGS" ]] || BASE_FLAGS='{}'
  MERGED_FLAGS="$(FTF_BASE="$BASE_FLAGS" FTF_OVER="$FLAGS" python3 -c '
import json, os, sys
def obj(label, raw):
    try:
        v = json.loads(raw)
    except Exception as e:
        sys.exit("%s is not valid JSON: %s" % (label, e))
    if not isinstance(v, dict):
        sys.exit("%s must be a JSON object of flag-key -> bool" % label)
    return v
base = obj("seeded profile flag map", os.environ["FTF_BASE"])
over = obj("--flags override", os.environ["FTF_OVER"])
bad = sorted(k for k, v in over.items() if not isinstance(v, bool))
if bad:
    sys.exit("--flags override values must be true/false; non-bool for %s" % bad)
base.update(over)
print(json.dumps(base, sort_keys=True, separators=(",", ":")))
')" || { echo "BAD ARGS: --flags rejected (see above) — refusing to run (exit 5)" >&2; exit 5; }
  export FTF_FLAGS="$MERGED_FLAGS"
fi

# `exec` is load-bearing: without it bash forks the subshell AND python, so $!
# is the subshell, not Flask. Two consequences, both false-PASS hazards — the
# stale-Flask pid assertion below could never pass (it fired on a clear port
# every time), and the EXIT trap killed the already-dead subshell, orphaning
# Flask on the port for the NEXT run's assertions to talk to.
# PYTHONUNBUFFERED: flask.log is block-buffered otherwise, so the tail of it —
# including feature_flags' parse warnings — is lost when the trap kills Flask.
( cd "$REPO" && export PORT="$PORT" PYTHONUNBUFFERED=1 && exec python3 run.py ) \
  > "$REPORT_DIR/flask.log" 2>&1 &
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
# ASSERT the round-trip (lld.md §2.5b: "a mis-pinned run must die here, not
# mid-flow"). This response used to be archived and never checked, so a cell
# whose flags never took effect asserted the OLD behaviour and exited 0.
echo "$PINNED" | python3 -c '
import json, os, sys
served = (json.load(sys.stdin) or {}).get("flags") or {}
raw = (os.environ.get("FTF_FLAGS") or "").strip()
if not raw:
    sys.exit("no FTF_FLAGS in the environment — this run pins no flags at all; "
             "the seeder env block did not export a flag map")
intended = json.loads(raw)
wrong, absent = [], []
for k in sorted(intended):
    want = bool(intended[k])
    if k not in served:
        absent.append("  %s: intended %s, ABSENT from /api/feature-flags "
                      "(key not in backend/feature_flags.py DEFAULT_FLAGS?)" % (k, want))
    elif bool(served[k]) != want:
        wrong.append("  %s: intended %s, served %s" % (k, want, bool(served[k])))
if wrong or absent:
    n = len(wrong) + len(absent)
    print("FLAG PIN MISMATCH — %d of %d intended flag(s) did not take effect:"
          % (n, len(intended)), file=sys.stderr)
    print("\n".join(wrong + absent), file=sys.stderr)
    sys.exit(1)
print("flags: %d intended flag(s) round-tripped via /api/feature-flags" % len(intended))
' || { echo "INFRA: flag pin round-trip failed (see above) — this run would have exercised a flag state nobody asked for; refusing (exit 2)" >&2; exit 2; }

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

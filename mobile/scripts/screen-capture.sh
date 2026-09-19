#!/usr/bin/env bash
# screen-capture.sh — the ONLY writer of screens/mobile/ and screens/manifest.json.
#
# Captures every mobile screen in every state from the real app on the canonical
# simulator, hermetically (seeded backend, zero live egress — all of that is
# sim-run.sh's job; this script is the sweep + collect + compress + manifest
# layer on top of it).
#
#   screen-capture.sh                          # full sweep
#   screen-capture.sh --screen trades          # one screen (incl. @profile variants)
#   screen-capture.sh --profile empty          # only flows declaring that profile
#   screen-capture.sh --app path/to/App.app    # skip the build
#   screen-capture.sh --no-compress            # keep raw PNGs
#   screen-capture.sh --prune                  # delete states no longer captured
#   screen-capture.sh --interactive --screen trades [--state loading]
#
# Exit: 0 ok · 1 a flow failed · 2 infra (build/sim/backend) · 5 bad args
set -uo pipefail

MOBILE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$MOBILE/.." && pwd)"
CAPTURE_DIR="$MOBILE/.maestro/capture"
SCREENS_DIR="$REPO/screens/mobile"
MANIFEST="$REPO/screens/manifest.json"
FLAGS_DIR="$REPO/backend/tests/fixtures/flags"

# Canonical device (docs/plans/mobile-testing): FTF-iOS18 / iOS 18.4.
UDID="${FTF_SIM_UDID:-89EEFD08-1237-4CEB-8583-30AAF44419AD}"
DEVICE_NAME="FTF-iOS18"
DEVICE_IOS="18.4"

SCREEN="" PROFILE_FILTER="" APP="" COMPRESS=1 PRUNE=0 INTERACTIVE=0 STATE=""
RUN_ID="$(date +%Y%m%dT%H%M%S)"
WORK="$MOBILE/test-artifacts/$RUN_ID-screens"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --screen)      SCREEN="$2"; shift 2 ;;
    --profile)     PROFILE_FILTER="$2"; shift 2 ;;
    --app)         APP="$2"; shift 2 ;;
    --no-compress) COMPRESS=0; shift ;;
    --prune)       PRUNE=1; shift ;;
    --interactive) INTERACTIVE=1; shift ;;
    --state)       STATE="$2"; shift 2 ;;
    --udid)        UDID="$2"; shift 2 ;;
    -h|--help)     sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "screen-capture.sh: unknown arg $1" >&2; exit 5 ;;
  esac
done

[[ -d "$CAPTURE_DIR" ]] || { echo "no capture flows at $CAPTURE_DIR" >&2; exit 5; }
if [[ "$INTERACTIVE" -eq 1 && -z "$SCREEN" ]]; then
  echo "--interactive requires --screen <name>" >&2; exit 5
fi
mkdir -p "$WORK" "$SCREENS_DIR"

# ── header parsing ───────────────────────────────────────────────────────────
# Capture flows carry the smoke grammar (# tc: / # profile: / # flags:) plus
# two capture-only directives:
#   # captures: <ordered state names>
#   # source:   <repo-relative files this screen's pixels depend on>
# and an optional  # interactive-stop: <state>  marker.
hdr() {  # $1 file, $2 key → value or ""
  sed -n "1,40p" "$1" | grep -m1 -E "^#[[:space:]]*$2:" | sed -E "s/^#[[:space:]]*$2:[[:space:]]*//"
}
screen_of() {  # signin.yaml → signin ; trades@empty.yaml → trades
  local b; b="$(basename "$1" .yaml)"; echo "${b%%@*}"
}

# ── flow selection ───────────────────────────────────────────────────────────
FLOWS=()
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  s="$(screen_of "$f")"
  [[ -n "$SCREEN" && "$s" != "$SCREEN" ]] && continue
  p="$(hdr "$f" profile)"; p="${p:-standard}"
  [[ -n "$PROFILE_FILTER" && "$p" != "$PROFILE_FILTER" ]] && continue
  FLOWS+=("$f")
done < <(find "$CAPTURE_DIR" -maxdepth 2 -name '*.yaml' -not -path '*/helpers/*' | sort)

[[ "${#FLOWS[@]}" -gt 0 ]] || { echo "no capture flows matched (screen='$SCREEN' profile='$PROFILE_FILTER')" >&2; exit 5; }

# ── app: reuse a fresh build, else build ─────────────────────────────────────
newest_src_mtime() { find "$MOBILE/src" -type f -newer "$1" -print -quit 2>/dev/null; }

if [[ -z "$APP" ]]; then
  RC="$MOBILE/ios/build/resolved-config.json"
  CAND="$(find "$MOBILE/ios/build/Build/Products" -maxdepth 2 -name '*.app' -path '*iphonesimulator*' 2>/dev/null | head -1)"
  if [[ -f "$RC" && -n "$CAND" && -z "$(newest_src_mtime "$RC")" ]]; then
    APP="$CAND"
    echo "reusing build: $APP (resolved-config.json newer than every file in mobile/src)"
  else
    echo "building sim app (mobile/src changed since the last build, or none found)…"
    BUILD_LOG="$WORK/sim-build.log"
    if ! bash "$MOBILE/scripts/sim-build.sh" > "$BUILD_LOG" 2>&1; then
      echo "INFRA: sim-build.sh failed — see $BUILD_LOG" >&2; exit 2
    fi
    APP="$(grep -m1 '^APP=' "$BUILD_LOG" | sed 's/^APP=//')"
    [[ -n "$APP" ]] || { echo "INFRA: sim-build.sh produced no APP= line ($BUILD_LOG)" >&2; exit 2; }
  fi
fi
[[ -d "$APP" ]] || { echo "INFRA: app not found: $APP" >&2; exit 2; }
APP_SHA="$(find "$APP" -type f -exec shasum -a 256 {} + 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"

# ── interactive mode ─────────────────────────────────────────────────────────
# Runs the flow only as far as the requested state, skips its screenshot and
# the end-of-cell reset, and leaves the simulator sitting in that state.
if [[ "$INTERACTIVE" -eq 1 ]]; then
  FLOW="${FLOWS[0]}"
  STOP="${STATE:-$(hdr "$FLOW" interactive-stop)}"
  [[ -n "$STOP" ]] || { echo "no --state given and no '# interactive-stop:' in $(basename "$FLOW")" >&2; exit 5; }
  PROF="$(hdr "$FLOW" profile)"; PROF="${PROF:-standard}"
  FLG="$(hdr "$FLOW" flags)"; FLG="${FLG:-release}"
  TRUNC="$WORK/interactive/$(basename "$FLOW")"
  mkdir -p "$WORK/interactive"
  ln -sfn "$CAPTURE_DIR/helpers" "$WORK/interactive/helpers"
  # Everything up to (but not including) the takeScreenshot for $STOP.
  awk -v marker="takeScreenshot: $(screen_of "$FLOW")__$STOP" \
      'index($0, marker) { exit } { print }' "$FLOW" > "$TRUNC"
  grep -q '^---' "$TRUNC" || { echo "truncation left no flow body — check --state '$STOP'" >&2; exit 5; }

  FLAGS_JSON=""
  [[ -f "$FLAGS_DIR/$FLG.json" ]] && FLAGS_JSON="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps({k:v for k,v in d.items() if not k.startswith('_')}))" "$FLAGS_DIR/$FLG.json")"
  echo "interactive: $(basename "$FLOW") → state '$STOP' (profile=$PROF flags=$FLG)"
  bash "$MOBILE/scripts/sim-run.sh" \
    --udid "$UDID" --app "$APP" --profile "$PROF" \
    ${FLAGS_JSON:+--flags "$FLAGS_JSON"} \
    --flow "$TRUNC" --keep-data \
    --report-dir "$WORK/interactive/report" \
    --maestro-output "$WORK/interactive"
  RC=$?
  API="http://127.0.0.1:5001"
  echo
  echo "── simulator left running, app parked in state '$STOP' ─────────────────"
  echo "injections this state was built with:"
  grep -A4 -E 'INJECT_KIND:' "$TRUNC" \
    | grep -E 'INJECT_(KIND|PATH|STATUS|MS|COUNT):' \
    | sed -E 's/^[[:space:]-]*/  /' || echo "  (none)"
  echo
  echo "NOTE: sim-run.sh POSTs /__test__/reset and stops Flask when the cell ends,"
  echo "      so the screen is frozen for inspection — the backend behind it is down."
  echo "      To poke the app live, restart the backend by hand:"
  echo "        cd $REPO && FTF_TEST_PROFILE=$PROF PORT=5001 python3 run.py"
  echo "      then re-arm/clear injections:  curl -X POST $API/__test__/reset"
  echo
  echo "truncated flow:  $TRUNC"
  echo "re-run a state:  $0 --interactive --screen $SCREEN --state <state>"
  exit $RC
fi

# ── group flows by (profile, flags) and run one sim cell per group ───────────
declare -a CELLS=()
for f in "${FLOWS[@]}"; do
  p="$(hdr "$f" profile)"; p="${p:-standard}"
  g="$(hdr "$f" flags)";   g="${g:-release}"
  CELLS+=("$p|$g")
done
UNIQ_GROUPS="$(printf '%s\n' "${CELLS[@]}" | sort -u)"

SHOTS="$WORK/shots"; mkdir -p "$SHOTS"
FAILED=()
declare -a RECORDS=()   # screen|state|flow|profile|flags|png

while IFS= read -r grp; do
  [[ -n "$grp" ]] || continue
  PROF="${grp%%|*}"; FLG="${grp##*|}"
  STAGE="$WORK/stage/$PROF-$FLG"
  mkdir -p "$STAGE"
  ln -sfn "$CAPTURE_DIR/helpers" "$STAGE/helpers"
  MEMBERS=()
  for i in "${!FLOWS[@]}"; do
    [[ "${CELLS[$i]}" == "$grp" ]] || continue
    ln -sfn "${FLOWS[$i]}" "$STAGE/$(basename "${FLOWS[$i]}")"
    MEMBERS+=("${FLOWS[$i]}")
  done

  FLAGS_JSON=""
  if [[ -f "$FLAGS_DIR/$FLG.json" ]]; then
    FLAGS_JSON="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps({k:v for k,v in d.items() if not k.startswith('_')}))" "$FLAGS_DIR/$FLG.json")"
  else
    echo "WARN: no flag fixture $FLAGS_DIR/$FLG.json — falling back to the seeder's defaults" >&2
  fi

  GSHOTS="$SHOTS/$PROF-$FLG"; mkdir -p "$GSHOTS"
  REPORT="$WORK/report/$PROF-$FLG"; mkdir -p "$REPORT"
  echo "── cell: profile=$PROF flags=$FLG (${#MEMBERS[@]} flow(s)) ────────────"
  bash "$MOBILE/scripts/sim-run.sh" \
    --udid "$UDID" --app "$APP" --profile "$PROF" \
    ${FLAGS_JSON:+--flags "$FLAGS_JSON"} \
    --flow "$STAGE" \
    --report-dir "$REPORT" \
    --maestro-output "$GSHOTS"
  CELL_RC=$?
  [[ "$CELL_RC" -ne 0 ]] && FAILED+=("$PROF/$FLG (sim-run exit $CELL_RC)")

  # Screenshots: maestro also drops its own debug artifacts; only take the
  # <screen>__<state>.png names our flows asked for.
  while IFS= read -r png; do
    [[ -n "$png" ]] || continue
    b="$(basename "$png" .png)"
    case "$b" in *__*) : ;; *) continue ;; esac
    scr="${b%%__*}"; st="${b#*__}"
    src_flow=""
    for m in "${MEMBERS[@]}"; do
      [[ "$(screen_of "$m")" == "$scr" ]] && src_flow="$m"
    done
    RECORDS+=("$scr|$st|${src_flow:-unknown}|$PROF|$FLG|$png")
  done < <(find "$GSHOTS" -maxdepth 2 -name '*__*.png' | sort)
done <<< "$UNIQ_GROUPS"

# ── compress ─────────────────────────────────────────────────────────────────
compress_png() {  # $1 = png path
  [[ "$COMPRESS" -eq 1 ]] || return 0
  if command -v pngquant >/dev/null 2>&1; then
    pngquant --quality 60-80 --force --ext .png "$1" 2>/dev/null || true
  else
    echo "WARN: pngquant not installed — falling back to a sips downscale to 1170px." >&2
    echo "      Captures will be lower fidelity than the spec. Fix: brew install pngquant" >&2
    sips --resampleWidth 1170 "$1" >/dev/null 2>&1 || true
  fi
}

# ── move into screens/mobile/<screen>/<state>.png + collect deltas ───────────
declare -a SUMMARY=()
declare -a SEEN=()
for rec in "${RECORDS[@]:-}"; do
  [[ -n "$rec" ]] || continue
  IFS='|' read -r scr st flow prof flg png <<< "$rec"
  compress_png "$png"
  dest_dir="$SCREENS_DIR/$scr"; mkdir -p "$dest_dir"
  dest="$dest_dir/$st.png"
  old=0; [[ -f "$dest" ]] && old="$(stat -f %z "$dest")"
  mv -f "$png" "$dest"
  new="$(stat -f %z "$dest")"
  SEEN+=("$scr/$st")
  SUMMARY+=("$scr|$st|$new|$((new - old))|$prof|$flg")
done

# ── prune ────────────────────────────────────────────────────────────────────
PRUNED=()
if [[ "$PRUNE" -eq 1 ]]; then
  while IFS= read -r existing; do
    [[ -n "$existing" ]] || continue
    key="$(basename "$(dirname "$existing")")/$(basename "$existing" .png)"
    # Only prune inside the scope we actually just captured.
    [[ -n "$SCREEN" && "${key%%/*}" != "$SCREEN" ]] && continue
    hit=0
    for s in "${SEEN[@]:-}"; do [[ "$s" == "$key" ]] && hit=1; done
    [[ "$hit" -eq 1 ]] || { rm -f "$existing"; PRUNED+=("$key"); }
  done < <(find "$SCREENS_DIR" -mindepth 2 -name '*.png' | sort)
fi

# ── manifest ─────────────────────────────────────────────────────────────────
MANIFEST_IN="$WORK/manifest-input.tsv"
: > "$MANIFEST_IN"
for rec in "${RECORDS[@]:-}"; do
  [[ -n "$rec" ]] || continue
  IFS='|' read -r scr st flow prof flg png <<< "$rec"
  srcs="$(hdr "$flow" source)"
  [[ -n "$srcs" ]] || srcs="mobile/src/screens/$(python3 - "$scr" <<'PY'
import sys
print(''.join(p.capitalize() for p in sys.argv[1].split('-')) + 'Screen.tsx')
PY
)"
  injs="$(grep -oE 'INJECT_KIND:[[:space:]]*[a-z_]+' "$flow" 2>/dev/null | sed -E 's/.*:[[:space:]]*//' | paste -sd, -)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$scr" "$st" "${flow#$REPO/}" "$prof" "$flg" "$srcs" "$injs" >> "$MANIFEST_IN"
done

REPO="$REPO" MANIFEST="$MANIFEST" APP_SHA="$APP_SHA" \
DEVICE_NAME="$DEVICE_NAME" DEVICE_UDID="$UDID" DEVICE_IOS="$DEVICE_IOS" \
python3 - "$MANIFEST_IN" <<'PY'
import datetime, hashlib, json, os, sys

repo = os.environ["REPO"]
mpath = os.environ["MANIFEST"]
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

manifest = {"generated_at": now, "app_sha": os.environ["APP_SHA"],
            "device": {"name": os.environ["DEVICE_NAME"],
                       "udid": os.environ["DEVICE_UDID"],
                       "ios": os.environ["DEVICE_IOS"]},
            "screens": {}}
if os.path.exists(mpath):
    try:
        prev = json.load(open(mpath))
        manifest["screens"] = prev.get("screens", {})
    except Exception:
        pass


def sha_of(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        fp = os.path.join(repo, p)
        h.update(p.encode())
        if os.path.exists(fp):
            h.update(open(fp, "rb").read())
        else:
            h.update(b"<missing>")
    return h.hexdigest()


touched = {}
for line in open(sys.argv[1]):
    line = line.rstrip("\n")
    if not line:
        continue
    scr, st, flow, prof, flg, srcs, injs = line.split("\t")
    sources = [s.strip() for s in srcs.split(",") if s.strip()]
    entry = manifest["screens"].setdefault(
        scr, {"source": [], "source_sha256": "", "captures": []})
    entry["source"] = sources
    entry["source_sha256"] = sha_of(sources)
    png = os.path.join(repo, "screens", "mobile", scr, st + ".png")
    cap = {"state": st,
           "file": "mobile/%s/%s.png" % (scr, st),
           "flow": flow, "profile": prof, "flags": flg,
           "injections": [i for i in injs.split(",") if i],
           "captured_at": now,
           "bytes": os.path.getsize(png) if os.path.exists(png) else 0}
    caps = [c for c in entry["captures"] if c.get("state") != st]
    caps.append(cap)
    entry["captures"] = sorted(caps, key=lambda c: c["state"])
    touched.setdefault(scr, set()).add(st)

# Drop manifest rows whose PNG no longer exists (i.e. --prune removed it).
for scr, entry in list(manifest["screens"].items()):
    entry["captures"] = [
        c for c in entry["captures"]
        if os.path.exists(os.path.join(repo, "screens", c["file"]))
    ]
    if not entry["captures"]:
        del manifest["screens"][scr]

os.makedirs(os.path.dirname(mpath), exist_ok=True)
with open(mpath, "w") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("manifest: %d screen(s) → %s" % (len(manifest["screens"]), mpath))
PY

# ── summary ──────────────────────────────────────────────────────────────────
echo
printf '%-14s %-16s %10s %10s  %s\n' SCREEN STATE BYTES DELTA "PROFILE/FLAGS"
for row in "${SUMMARY[@]:-}"; do
  [[ -n "$row" ]] || continue
  IFS='|' read -r scr st bytes delta prof flg <<< "$row"
  d="$delta"; [[ "$delta" -gt 0 ]] && d="+$delta"
  printf '%-14s %-16s %10s %10s  %s\n' "$scr" "$st" "$bytes" "$d" "$prof/$flg"
done
echo
echo "captures: ${#SUMMARY[@]}"
[[ "${#PRUNED[@]:-0}" -gt 0 ]] && echo "pruned:   ${PRUNED[*]}"

echo "rails counters (per cell):"
while IFS= read -r w; do
  [[ -n "$w" ]] || continue
  echo "  $(basename "$(dirname "$w")"): $(python3 -c "
import json,sys
print(json.load(open('$w'))['counters'])" 2>/dev/null)"
done < <(find "$WORK/report" -name 'whoami-end.json' 2>/dev/null | sort)

if [[ "${#FAILED[@]:-0}" -gt 0 ]]; then
  echo
  echo "FAILED cells: ${FAILED[*]}" >&2
  echo "artifacts: $WORK" >&2
  exit 1
fi
echo "artifacts: $WORK"
echo "screen-capture OK"

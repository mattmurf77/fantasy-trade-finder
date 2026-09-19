#!/usr/bin/env bash
# screen-freshness.sh — is the screen library still telling the truth?
#
# Recomputes the sha256 of each screen's declared source files and compares it
# to screens/manifest.json. No simulator, no build, < 1 s.
#
#   screen-freshness.sh            # human report
#   screen-freshness.sh --quiet    # exit code only (0 fresh · 1 stale · 2 no manifest)
#
# Exit: 0 everything fresh · 1 at least one stale screen · 2 no manifest yet
set -uo pipefail

MOBILE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$MOBILE/.." && pwd)"
MANIFEST="$REPO/screens/manifest.json"
QUIET=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quiet|-q) QUIET=1; shift ;;
    -h|--help)  sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "screen-freshness.sh: unknown arg $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$MANIFEST" ]]; then
  [[ "$QUIET" -eq 1 ]] || echo "screen-freshness: no manifest at $MANIFEST — run mobile/scripts/screen-capture.sh" >&2
  exit 2
fi

REPO="$REPO" MANIFEST="$MANIFEST" QUIET="$QUIET" python3 <<'PY'
import hashlib, json, os, sys

repo = os.environ["REPO"]
quiet = os.environ["QUIET"] == "1"
data = json.load(open(os.environ["MANIFEST"]))

def sha_of(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        fp = os.path.join(repo, p)
        h.update(p.encode())
        h.update(open(fp, "rb").read() if os.path.exists(fp) else b"<missing>")
    return h.hexdigest()

stale = 0
for screen in sorted(data.get("screens", {})):
    entry = data["screens"][screen]
    sources = entry.get("source") or []
    if not sources:
        continue
    if sha_of(sources) == entry.get("source_sha256"):
        continue
    stale += 1
    if quiet:
        continue
    when = min((c.get("captured_at", "?") for c in entry.get("captures", [])),
               default="?")
    print("STALE: %s (source changed since %s) — run "
          "mobile/scripts/screen-capture.sh --screen %s" % (screen, when, screen))

if not quiet and stale == 0:
    print("screen-freshness OK — %d screen(s) current" % len(data.get("screens", {})))
sys.exit(1 if stale else 0)
PY

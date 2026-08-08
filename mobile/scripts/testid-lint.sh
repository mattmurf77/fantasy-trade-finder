#!/usr/bin/env bash
# testid-lint.sh — flow ↔ source cross-check + banned-pattern lint.
# docs/plans/mobile-testing/lld.md §2.6
# Exit: 0 ok · 1 flows reference IDs missing from mobile/src · 2 banned patterns
set -uo pipefail
MOBILE="$(cd "$(dirname "$0")/.." && pwd)"
FLOWS="$MOBILE/.maestro"
[[ -d "$FLOWS" ]] || { echo "testid-lint: no flows yet ($FLOWS absent) — OK"; exit 0; }

status=0

# Banned patterns in flows: fixed sleeps, coordinate taps, text-selector taps.
# [[:space:]] not \s throughout: \s is GNU-only; BSD grep/sed on macOS silently
# fail to match it, which made this script false-pass (bans) and false-fail
# (extraction) on the operator's machine while behaving correctly in Linux CI.
if grep -rnE '^[[:space:]]*- (sleep|swipe:.*(start|end):.*[0-9]+%?,)|point:' "$FLOWS" --include='*.yaml' 2>/dev/null; then
  echo "testid-lint: banned pattern(s) above (fixed sleep / coordinate tap)" >&2
  status=2
fi
if grep -rnE 'tapOn:[[:space:]]*"[^"]+"$|tapOn:[[:space:]]*text:' "$FLOWS" --include='*.yaml' 2>/dev/null; then
  echo "testid-lint: text-selector taps above — use id: selectors (lld.md §4.4 rule 1)" >&2
  status=2
fi

# Every id referenced by a flow must exist as a testID in mobile/src.
# Dynamic qualifiers (foo.bar.<anything>) match on their static prefix.
# IDs the source constructs via template literals can't be grepped — they live
# in testid-lint-allow.txt (glob per line) with the constructing file noted.
ALLOW="$MOBILE/scripts/testid-lint-allow.txt"
_allowed() {
  [[ -f "$ALLOW" ]] || return 1
  local pat
  while IFS= read -r pat; do
    [[ -z "$pat" || "$pat" == \#* ]] && continue
    # shellcheck disable=SC2053  # glob match is the point
    [[ "$1" == $pat ]] && return 0
  done < "$ALLOW"
  return 1
}
missing=0
while IFS= read -r id; do
  _allowed "$id" && continue
  base="${id%%\**}"; base="${base%.}"
  if ! grep -rq "testID={\`\?[\"'\`]*${base}" "$MOBILE/src" 2>/dev/null \
     && ! grep -rq "testID=[\"'{]*.${base}" "$MOBILE/src" 2>/dev/null; then
    echo "testid-lint: flow references missing testID: $id" >&2
    missing=1
  fi
done < <(grep -rh --include='*.yaml' 'id:' "$FLOWS" 2>/dev/null \
         | grep -vE '^[[:space:]]*#' \
         | grep -oE 'id:[[:space:]]*"?[a-z0-9.*-]+' \
         | sed -E 's/id:[[:space:]]*"?//' | sort -u)
[[ "$missing" -eq 1 && "$status" -eq 0 ]] && status=1

[[ "$status" -eq 0 ]] && echo "testid-lint OK"
exit "$status"

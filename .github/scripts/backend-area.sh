#!/usr/bin/env bash
# Decide whether a pull request needs the backend pytest suite ("skip by area").
#
# Reads changed paths on stdin, one per line. Prints "true" (run the suite) or
# "false" (safe to skip) on stdout, and one line explaining why on stderr.
# The suite is skipped only when every changed path is in a skip-safe area.
# Any path not recognised runs the suite, and so does empty input.
#
# The list and the grep evidence behind it live in .github/CLAUDE.md under
# "Skip by area". If you add a backend test that reads a file outside the
# "run" areas, add that path to the first case branch below (and to the table
# in .github/CLAUDE.md) in the same PR.
set -euo pipefail

count=0
while IFS= read -r path || [[ -n "$path" ]]; do
  [[ -z "$path" ]] && continue
  count=$((count + 1))
  case "$path" in
    # Run: files inside otherwise skip-safe areas that backend tests read.
    docs/config-reference.md | docs/cross-client-invariants.md | docs/plans/* | \
    mobile/src/* | mobile/App.tsx | mobile/app.json | mobile/ios/* | \
    .claude/skills/feedback/scripts/* | \
    .github/workflows/ci.yml | .github/scripts/*)
      echo "backend suite needed: $path is read by backend tests or drives CI" >&2
      echo true
      exit 0
      ;;
    # Skip-safe areas.
    docs/* | living-memory/* | qa/* | extension/* | githooks/* | mockups/* | \
    reference/* | screens/* | archive/* | mobile/* | .claude/* | .github/*)
      ;;
    # Anything else inside a directory is not classified, so it runs.
    */*)
      echo "backend suite needed: $path is not in a skip-safe area" >&2
      echo true
      exit 0
      ;;
    # Root-level files: only Markdown, LICENSE and .easignore are skip-safe.
    *.md | LICENSE | .easignore)
      ;;
    *)
      echo "backend suite needed: $path is not in a skip-safe area" >&2
      echo true
      exit 0
      ;;
  esac
done

if [[ $count -eq 0 ]]; then
  echo "backend suite needed: no changed paths were given, so the change is unknown" >&2
  echo true
else
  echo "backend suite not needed: all $count changed paths are in skip-safe areas" >&2
  echo false
fi

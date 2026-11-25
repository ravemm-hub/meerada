#!/usr/bin/env bash
# Publish a locally produced Search Lab round to gh-pages (what the daily workflow does,
# for rounds run by hand — e.g. a 7-run test-case baseline).
#
#   bash scripts/publish_visibility.sh out/live_state.json out
#
# Arguments: the state file that was used for the run, and the folder holding
# visibility.html / visibility.json / cases.html. Never force-pushes; if gh-pages moved
# (the daily workflow ran meanwhile), the push fails and you re-fetch, re-run --report-only
# on the merged state, and publish again.
set -euo pipefail
STATE="${1:?state file}"
OUT="${2:?out dir}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -rf .ghpages-vis
git worktree prune
git fetch -q origin gh-pages
git worktree add -q .ghpages-vis origin/gh-pages
cp "$OUT/visibility.html" .ghpages-vis/visibility.html
cp "$OUT/visibility.json" .ghpages-vis/visibility.json
cp "$OUT/cases.html" .ghpages-vis/cases.html
cp "$STATE" .ghpages-vis/visibility_state.json
cd .ghpages-vis
git add visibility.html visibility.json cases.html visibility_state.json
git -c user.name="meerada-bot" -c user.email="bot@users.noreply.github.com" \
  commit -q -m "visibility (manual round) $(date -u +%FT%RZ)" || echo "no change"
git push -q origin HEAD:gh-pages
cd "$ROOT"
git worktree remove --force .ghpages-vis
echo "published to gh-pages"

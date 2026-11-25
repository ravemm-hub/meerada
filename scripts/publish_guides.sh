#!/usr/bin/env bash
# Publish the editorial guides (site/guides/), the profile pages (site/b/), the sitemap, the family bar and the
# IndexNow key file to gh-pages without rebuilding the whole site.
#
#   bash scripts/publish_guides.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -rf .ghpages-guides
git worktree prune
git fetch -q origin gh-pages
git worktree add -q .ghpages-guides origin/gh-pages
mkdir -p .ghpages-guides/guides .ghpages-guides/b .ghpages-guides/s .ghpages-guides/assets
cp site/guides/*.html .ghpages-guides/guides/
ls site/b/*.html >/dev/null 2>&1 && cp site/b/*.html .ghpages-guides/b/
ls site/s/*.html >/dev/null 2>&1 && cp site/s/*.html site/s/*.json .ghpages-guides/s/
cp site/search.html .ghpages-guides/search.html
cp site/assets/search.css .ghpages-guides/assets/search.css
cp site/sitemap.xml .ghpages-guides/sitemap.xml
cp site/assets/family.js .ghpages-guides/assets/family.js
for f in site/*.txt; do
  case "$(basename "$f")" in meerada-wheel.txt|robots.txt) ;; *) cp "$f" .ghpages-guides/ ;; esac
done
cd .ghpages-guides
git add guides b s search.html sitemap.xml assets/family.js assets/search.css ./*.txt
git -c user.name="meerada-bot" -c user.email="bot@users.noreply.github.com" \
  commit -q -m "guides $(date -u +%FT%RZ)" || echo "no change"
git push -q origin HEAD:gh-pages
cd "$ROOT"
git worktree remove --force .ghpages-guides
echo "guides published to gh-pages"

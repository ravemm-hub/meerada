#!/usr/bin/env bash
# Deploy the Meerada public site to GitHub Pages.
#
# One-time prerequisites (run once, by the user — they need YOUR GitHub auth):
#   winget install GitHub.cli          # or: brew install gh
#   gh auth login                      # authenticate this machine to GitHub
#
# Then this script, from the repo root:
#   bash scripts/deploy_pages.sh <github-user> <repo-name>
# e.g.
#   bash scripts/deploy_pages.sh ravemm-hub meerada
#
# It creates (or reuses) a PUBLIC repo, pushes the code, publishes ./site to the
# gh-pages branch, and enables Pages. Result: https://<user>.github.io/<repo>/
set -euo pipefail

USER="${1:?usage: deploy_pages.sh <github-user> <repo-name>}"
REPO="${2:?usage: deploy_pages.sh <github-user> <repo-name>}"

command -v gh >/dev/null || { echo "gh not found — install GitHub CLI and run 'gh auth login' first"; exit 1; }
gh auth status >/dev/null || { echo "not authenticated — run 'gh auth login' first"; exit 1; }

echo "==> rebuilding site/"
python scripts/build_site.py

echo "==> ensuring public repo ${USER}/${REPO}"
if ! gh repo view "${USER}/${REPO}" >/dev/null 2>&1; then
  gh repo create "${USER}/${REPO}" --public --source=. --remote=origin --push
else
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/${USER}/${REPO}.git"
  git push -u origin master
fi

echo "==> publishing ./site to gh-pages"
# Publish the site folder to the gh-pages branch via a temporary worktree.
rm -rf .ghpages-tmp
git fetch origin gh-pages >/dev/null 2>&1 || true
git worktree add -B gh-pages .ghpages-tmp origin/gh-pages >/dev/null 2>&1 || git worktree add .ghpages-tmp gh-pages
# The live-grade workflow writes grade_state.json + grade.html straight to
# gh-pages every hour (accumulated measurement history). NEVER wipe them —
# keep the branch's copies and only fall back to site/ if they don't exist yet.
mkdir -p .ghpages-keep
for f in grade_state.json grade.html; do
  [ -f ".ghpages-tmp/$f" ] && cp ".ghpages-tmp/$f" ".ghpages-keep/$f"
done
rm -rf .ghpages-tmp/*
cp -r site/* .ghpages-tmp/
cp -f .ghpages-keep/* .ghpages-tmp/ 2>/dev/null || true
rm -rf .ghpages-keep
touch .ghpages-tmp/.nojekyll
( cd .ghpages-tmp && git add -A && git commit -m "deploy site $(date -u +%Y-%m-%dT%H:%MZ)" && git push -f origin gh-pages )
git worktree remove --force .ghpages-tmp

echo "==> enabling Pages (gh-pages branch, root)"
gh api -X POST "repos/${USER}/${REPO}/pages" -f "source[branch]=gh-pages" -f "source[path]=/" 2>/dev/null || \
  gh api -X PUT "repos/${USER}/${REPO}/pages" -f "source[branch]=gh-pages" -f "source[path]=/" 2>/dev/null || true

echo "==> done. Site will be live shortly at: https://${USER}.github.io/${REPO}/"

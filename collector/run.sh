#!/usr/bin/env bash
# Uruchamia zbieracza i zapisuje wynik na osobnej gałęzi "data" (strona na gałęzi main nie jest ruszana).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config user.name "busola-collector"
git config user.email "collector@users.noreply.github.com"
ROOT="$(pwd)"
WT="$(mktemp -d)/dw"
# sprzątanie: usuń poprzednie (porzucone) katalogi robocze gałęzi cdata oraz ten po zakończeniu
git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/cdata$/{print p}' | while read -r old; do git worktree remove --force "$old" 2>/dev/null || true; done
trap 'cd "$ROOT"; git worktree remove --force "$WT" 2>/dev/null || true' EXIT
if git ls-remote --exit-code --heads origin data >/dev/null 2>&1; then
  git fetch --quiet origin data
  git worktree prune
  git worktree add --quiet -B cdata "$WT" FETCH_HEAD
else
  git worktree prune
  git worktree add --quiet --detach "$WT" HEAD
  (cd "$WT" && git checkout --quiet --orphan cdata && git rm -rf --quiet . >/dev/null 2>&1 || true)
fi
python3 collector/collect.py --out "$WT/data"
cd "$WT"
git add -A
if git diff --cached --quiet; then echo "brak zmian"; exit 0; fi
git commit --quiet -m "data $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push --quiet origin HEAD:data || { git pull --quiet --rebase origin data && git push --quiet origin HEAD:data; }
echo "zapisano na gałęzi data"

#!/usr/bin/env bash
# Snapshot the whole working tree (committed, staged, unstaged, untracked) without
# touching the working tree, the real index, or any branch.
#
#   backup.sh [label]   make a snapshot
#   backup.sh --list    list snapshots
#
# Each snapshot is stored twice:
#   - a git commit under refs/backups/<stamp>-<label>  (fast restore)
#   - a .tar.gz in $KAMI_BACKUP_DIR (default ~/kami-backups)  (survives a broken .git)
# Files matched by .gitignore (config.toml, .env, .venv) are never included.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
cd "$root"

if [[ "${1:-}" == "--list" ]]; then
  git for-each-ref --sort=-refname --format='%(refname:short)  %(contents:subject)' refs/backups/
  exit 0
fi

label=$(printf '%s' "${1:-manual}" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-*//; s/-*$//')
name="$(date +%Y%m%d-%H%M%S)-${label:-manual}"

git_dir=$(git rev-parse --git-dir)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
tmp_index="$tmp_dir/index"
[[ -f "$git_dir/index" ]] && cp "$git_dir/index" "$tmp_index"

GIT_INDEX_FILE="$tmp_index" git add -A
tree=$(GIT_INDEX_FILE="$tmp_index" git write-tree)
parent=$(git rev-parse -q --verify HEAD || true)
commit=$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "backup: $name")
git update-ref "refs/backups/$name" "$commit"

dest="${KAMI_BACKUP_DIR:-$HOME/kami-backups}"
mkdir -p "$dest"
archive="$dest/kami-$name.tar.gz"
git archive --format=tar.gz -o "$archive" "$commit"

echo "ref:     refs/backups/$name"
echo "archive: $archive"

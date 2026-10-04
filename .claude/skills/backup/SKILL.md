---
name: backup
description: Snapshot the Kami repo (including uncommitted work) or restore a snapshot.
disable-model-invocation: true
argument-hint: "[label] | list | restore <name> [path]"
allowed-tools: Bash(.claude/skills/backup/backup.sh:*)
---

# Backup

Arguments: `$ARGUMENTS`

The script [backup.sh](backup.sh) makes the snapshot. It never changes the working tree, the index, or any branch, so making a backup is always safe.

## Make a backup (no argument, or a label)

1. Run `.claude/skills/backup/backup.sh <label>`. Use the label the user gave; with no label, pick a 1–3 word slug describing the current work (e.g. `before-meeting-capture`).
2. Report the ref name and archive path it printed, and one line on what was captured (`git status --short` count of changed/untracked files).

## List backups (`list`)

Run `.claude/skills/backup/backup.sh --list` and show the result as a short table: name, date, subject.

## Restore (`restore <name> [path]`)

Restoring overwrites files, so it follows the confirm rule:

1. Show the user what will change: `git diff --stat refs/backups/<name> -- <path or .>`.
2. Explain in plain English which files will be overwritten and that current edits to them will be replaced. Wait for a clear yes.
3. Take a fresh backup first: `backup.sh before-restore`. This is the undo for the restore.
4. Restore with `git restore --source=refs/backups/<name> --worktree -- <path or .>`. Files that exist now but not in the snapshot are left alone; mention them if any.
5. Run `uvx pytest -q` and report the result.

If `.git` itself is damaged, the archive in `~/kami-backups/` (or `$KAMI_BACKUP_DIR`) is the fallback: `tar -xzf <archive> -C <empty dir>`.

## Deleting old backups

Only when the user asks: `git update-ref -d refs/backups/<name>` and remove the matching archive.

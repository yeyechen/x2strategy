#!/usr/bin/env bash
# setup_skill_link.sh — make `/x2strategy` slash command load the live repo.
#
# The Claude Code slash command /x2strategy resolves to
# ~/.claude/skills/x2strategy/SKILL.md. By default that's a stale copy
# of the upstream ALAGENT-HKU repo. We replace it with a symlink to the
# live working repo so every edit is immediately visible to the agent.
#
# Idempotent — safe to re-run after pulling, moving, or renaming the repo.
#
# Usage:
#   bash scripts/setup_skill_link.sh              # link to ../x2strategy (default)
#   bash scripts/setup_skill_link.sh /abs/path   # link to a specific path

set -euo pipefail

# Resolve the live repo path (the directory this script lives in)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE_REPO="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# Where Claude Code looks for skills
SKILL_DIR="$HOME/.claude/skills/x2strategy"
# Backups go OUTSIDE ~/.claude/skills/ — anything in that directory
# is auto-discovered as a slash command, so a backup named
# x2strategy.backup.<ts> would become /x2strategy.backup.<ts>.
# Putting backups under ~/.claude/backup/ keeps them discoverable
# to humans without polluting the slash-command list.
BACKUP_BASE="$HOME/.claude/backup/x2strategy"

# Sanity check: LIVE_REPO must contain SKILL.md
if [[ ! -f "$LIVE_REPO/SKILL.md" ]]; then
    echo "ERROR: $LIVE_REPO does not contain SKILL.md" >&2
    echo "Pass the repo path as the first arg: bash setup_skill_link.sh /path/to/x2strategy" >&2
    exit 1
fi

# Case 1: SKILL_DIR is already a symlink to LIVE_REPO — done
if [[ -L "$SKILL_DIR" ]] && [[ "$(readlink "$SKILL_DIR")" == "$LIVE_REPO" ]]; then
    echo "✓ Slash command already linked: $SKILL_DIR → $LIVE_REPO"
    exit 0
fi

# Case 2: SKILL_DIR is a symlink to somewhere else — fix it
if [[ -L "$SKILL_DIR" ]]; then
    echo "Slash command currently symlinked to: $(readlink "$SKILL_DIR")"
    echo "Repointing to: $LIVE_REPO"
    rm "$SKILL_DIR"
fi

# Case 3: SKILL_DIR is a real directory — back it up and replace with symlink
if [[ -d "$SKILL_DIR" ]]; then
    mkdir -p "$(dirname "$BACKUP_BASE")"
    BACKUP="${BACKUP_BASE}.$(date +%s)"
    echo "Backing up existing skill directory to: $BACKUP"
    mv "$SKILL_DIR" "$BACKUP"
fi

# Ensure parent dir exists
mkdir -p "$(dirname "$SKILL_DIR")"

# Create the symlink
ln -s "$LIVE_REPO" "$SKILL_DIR"
echo "✓ Linked: $SKILL_DIR → $LIVE_REPO"

# Sanity check: SKILL.md visible through the symlink
if [[ ! -f "$SKILL_DIR/SKILL.md" ]]; then
    echo "ERROR: SKILL.md not visible through the symlink" >&2
    exit 1
fi

echo
echo "Quick verification:"
echo "  symlink target: $(readlink "$SKILL_DIR")"
echo "  SKILL.md mtime: $(stat -c '%y' "$SKILL_DIR/SKILL.md")"
echo "  utils/ visible:  $(ls "$SKILL_DIR/utils/" 2>/dev/null | head -3 | tr '\n' ' ')"
echo
echo "Open a fresh Claude Code session in $LIVE_REPO and run /x2strategy."
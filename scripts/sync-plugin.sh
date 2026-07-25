#!/usr/bin/env bash
# scripts/sync-plugin.sh
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: sync-plugin.sh <path-to-dev-repo> <plugin-name>" >&2
  exit 1
fi

DEV_REPO="$1"
PLUGIN_NAME="$2"

if ! [[ "$PLUGIN_NAME" =~ ^[a-z0-9-]+$ ]]; then
  echo "error: plugin name must match ^[a-z0-9-]+\$, got: $PLUGIN_NAME" >&2
  exit 1
fi

if [ ! -d "$DEV_REPO" ]; then
  echo "error: dev repo not found: $DEV_REPO" >&2
  exit 1
fi

if [ ! -f "$DEV_REPO/.claude-plugin/plugin.json" ]; then
  echo "error: $DEV_REPO/.claude-plugin/plugin.json not found — is this a plugin repo?" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$MARKETPLACE_ROOT/plugins/$PLUGIN_NAME"

rm -rf "$DEST"
mkdir -p "$DEST/.claude-plugin"
cp "$DEV_REPO/.claude-plugin/plugin.json" "$DEST/.claude-plugin/plugin.json"

if [ -d "$DEV_REPO/skills" ]; then
  cp -R "$DEV_REPO/skills" "$DEST/skills"
fi

if [ -d "$DEV_REPO/scripts" ]; then
  cp -R "$DEV_REPO/scripts" "$DEST/scripts"
  rm -rf "$DEST/scripts/tests"
  find "$DEST/scripts" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
fi

for f in README.md LICENSE; do
  if [ -f "$DEV_REPO/$f" ]; then
    cp "$DEV_REPO/$f" "$DEST/$f"
  fi
done

echo "synced $PLUGIN_NAME from $DEV_REPO to $DEST"

#!/usr/bin/env bash
# scripts/tests/test-sync-plugin.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILURES=0

assert_exists() {
  if [ ! -e "$1" ]; then
    echo "FAIL: expected to exist: $1"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_missing() {
  if [ -e "$1" ]; then
    echo "FAIL: expected NOT to exist: $1"
    FAILURES=$((FAILURES + 1))
  fi
}

# --- Set up a fake marketplace root with the real script inside it ---
FAKE_MARKETPLACE="$(mktemp -d)"
mkdir -p "$FAKE_MARKETPLACE/scripts"
cp "$SCRIPT_DIR/../sync-plugin.sh" "$FAKE_MARKETPLACE/scripts/sync-plugin.sh"
chmod +x "$FAKE_MARKETPLACE/scripts/sync-plugin.sh"

# --- Set up a fake dev repo with a realistic public/dev-only mix ---
FAKE_DEV_REPO="$(mktemp -d)"
mkdir -p "$FAKE_DEV_REPO/.claude-plugin"
echo '{"name": "fake-plugin"}' > "$FAKE_DEV_REPO/.claude-plugin/plugin.json"
mkdir -p "$FAKE_DEV_REPO/skills/fake-plugin"
echo "# Fake Skill" > "$FAKE_DEV_REPO/skills/fake-plugin/SKILL.md"
mkdir -p "$FAKE_DEV_REPO/scripts/tests"
echo "print('lib')" > "$FAKE_DEV_REPO/scripts/fake_lib.py"
echo "print('test')" > "$FAKE_DEV_REPO/scripts/tests/test_fake_lib.py"
mkdir -p "$FAKE_DEV_REPO/docs/superpowers/specs"
echo "# design doc" > "$FAKE_DEV_REPO/docs/superpowers/specs/design.md"
echo "# Fake Plugin" > "$FAKE_DEV_REPO/README.md"
echo "MIT" > "$FAKE_DEV_REPO/LICENSE"
echo "# contributing" > "$FAKE_DEV_REPO/CONTRIBUTING.md"

# --- Test 1: a stray pre-existing file in the destination gets removed (mirror, not accumulate) ---
DEST="$FAKE_MARKETPLACE/plugins/fake-plugin"
mkdir -p "$DEST"
echo "stale" > "$DEST/stale.txt"

"$FAKE_MARKETPLACE/scripts/sync-plugin.sh" "$FAKE_DEV_REPO" fake-plugin

assert_missing "$DEST/stale.txt"

# --- Test 2: public files are copied ---
assert_exists "$DEST/.claude-plugin/plugin.json"
assert_exists "$DEST/skills/fake-plugin/SKILL.md"
assert_exists "$DEST/scripts/fake_lib.py"
assert_exists "$DEST/README.md"
assert_exists "$DEST/LICENSE"

# --- Test 3: dev-only content is excluded ---
assert_missing "$DEST/scripts/tests"
assert_missing "$DEST/docs"
assert_missing "$DEST/CONTRIBUTING.md"

# --- Test 4: invalid plugin name is rejected without touching the filesystem ---
# Test path traversal rejection: PLUGIN_NAME="../evil" becomes DEST="$MARKETPLACE_ROOT/plugins/../evil"
# which resolves to $MARKETPLACE_ROOT/evil. Create a file there to verify it's NOT deleted.
mkdir -p "$FAKE_MARKETPLACE/evil"
echo "important" > "$FAKE_MARKETPLACE/evil/important.txt"

if "$FAKE_MARKETPLACE/scripts/sync-plugin.sh" "$FAKE_DEV_REPO" "../evil" 2>/dev/null; then
  echo "FAIL: expected sync-plugin.sh to reject a plugin name containing '..'"
  FAILURES=$((FAILURES + 1))
fi
# These should not exist (normal checks)
assert_missing "$FAKE_MARKETPLACE/plugins/evil"
assert_missing "$FAKE_MARKETPLACE/../evil"
# The real test: $MARKETPLACE_ROOT/evil/important.txt should survive (validation prevented rm -rf)
assert_exists "$FAKE_MARKETPLACE/evil/important.txt"

# --- Test 5: missing dev repo is rejected ---
if "$FAKE_MARKETPLACE/scripts/sync-plugin.sh" "/nonexistent-dir-xyz" fake-plugin 2>/dev/null; then
  echo "FAIL: expected sync-plugin.sh to reject a nonexistent dev repo path"
  FAILURES=$((FAILURES + 1))
fi

rm -rf "$FAKE_MARKETPLACE" "$FAKE_DEV_REPO"

if [ "$FAILURES" -eq 0 ]; then
  echo "OK: all sync-plugin.sh tests passed"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) failed"
  exit 1
fi

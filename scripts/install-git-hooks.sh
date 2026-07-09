#!/usr/bin/env bash
# Install sv0-toolchain git hooks for the parent repo AND the sv0c submodule.
#
# Uses git's `core.hooksPath` so the tracked scripts/git-hooks/ directory is the
# single source of truth — edits take effect immediately, no copies to keep in
# sync. Re-run any time (idempotent). Hooks are repo-aware and bypassable with
# `--no-verify` or `SV0_SKIP_HOOKS=1`.
#
# Usage: ./scripts/install-git-hooks.sh   (from anywhere; resolves its own root)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$ROOT/scripts/git-hooks"

[[ -d "$HOOKS_DIR" ]] || { echo "install-git-hooks: missing $HOOKS_DIR" >&2; exit 1; }

# Ensure hook scripts are executable.
for h in commit-msg pre-commit pre-push; do
  [[ -f "$HOOKS_DIR/$h" ]] || { echo "install-git-hooks: missing hook $h" >&2; exit 1; }
  chmod +x "$HOOKS_DIR/$h"
done
chmod +x "$ROOT/scripts/verify_commit_msg_no_ai_signoff.py"

# Parent repo: relative hooksPath resolves against the work-tree root.
git -C "$ROOT" config core.hooksPath scripts/git-hooks
echo "installed: parent repo   -> core.hooksPath=scripts/git-hooks"

# sv0c submodule: its work tree has no scripts/, so point at the absolute
# path of the shared hooks dir. Hooks detect the submodule and adjust.
if [[ -d "$ROOT/sv0c" ]] && git -C "$ROOT/sv0c" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$ROOT/sv0c" config core.hooksPath "$HOOKS_DIR"
  echo "installed: sv0c submodule -> core.hooksPath=$HOOKS_DIR"
else
  echo "note: sv0c submodule not initialized; skipped (re-run after 'git submodule update --init')"
fi

# Sanity: the AI-signoff verifier must pass its own corpus.
python3 "$ROOT/scripts/verify_commit_msg_no_ai_signoff.py" --selftest >/dev/null \
  && echo "verified: commit-msg AI-signoff checker selftest OK"

echo "done. hooks active: commit-msg (no AI sign-off), pre-commit (fmt+lint+doc-pins), pre-push (full tests)."
echo "bypass once with --no-verify, or all hooks with SV0_SKIP_HOOKS=1."

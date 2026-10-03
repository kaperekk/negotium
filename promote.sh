#!/bin/bash
# Promote main -> release (fast-forward only)

set -e

git fetch origin

# Check if release can be fast-forwarded to main
if ! git merge-base --is-ancestor origin/release origin/main; then
    echo "❌ Cannot fast-forward: release has commits not in main"
    echo "   Run 'git log origin/release..origin/main' to see divergent commits"
    exit 1
fi

# Fast-forward release to main
git push origin origin/main:release --no-force

echo "✅ release fast-forwarded to main"
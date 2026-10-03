#!/bin/bash
# Promote main -> release (fast-forward only) with test verification

set -e

echo "🔍 Fetching latest..."
git fetch origin

# Check if release can be fast-forwarded to main
if ! git merge-base --is-ancestor origin/release origin/main; then
    echo "❌ Cannot fast-forward: release has commits not in main"
    echo "   Run 'git log origin/release..origin/main' to see divergent commits"
    exit 1
fi

echo "🧪 Running tests (skipping slow/network tests)..."
if ! python3.11 -m pytest tests/ -q --tb=short -m "not slow"; then
    echo "❌ Tests failed — promotion aborted"
    exit 1
fi

echo "✅ Tests passed"

# Fast-forward release to main
echo "🚀 Promoting main → release..."
git push origin origin/main:release --no-force

echo "✅ release fast-forwarded to main"
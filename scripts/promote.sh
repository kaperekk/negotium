#!/usr/bin/env bash
# Promotion script: runs all tests and fast-forwards source branch to target branch.
# Usage: ./promote.sh [SOURCE_BRANCH] [TARGET_BRANCH]
# Default: main -> release

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Handle help flag
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo "Usage: $0 [SOURCE_BRANCH] [TARGET_BRANCH]"
    echo "  Fast-forwards TARGET_BRANCH from SOURCE_BRANCH (default: main -> release)"
    echo ""
    echo "Examples:"
    echo "  $0              # main -> release"
    echo "  $0 main dev     # main -> dev"
    echo "  $0 feature main # feature -> main"
    exit 0
fi

echo "============================================================"
echo "🚀 Negotium Promotion Script"
echo "============================================================"

# Run tests
echo ""
echo "============================================================"
echo "Running tests..."
echo "============================================================"

if ! PYTHONPATH=src .venv/bin/python -m pytest tests/ \
    --ignore=tests/test_range_refresh_regression.py \
    -v --tb=short; then
    echo ""
    echo "❌ Tests failed!"
    exit 1
fi

echo ""
echo "✅ All tests passed!"
echo ""

# Fast-forward target branch from source branch (default: main -> release)
SOURCE_BRANCH="${1:-main}"
TARGET_BRANCH="${2:-release}"

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "⚠️  Warning: You have uncommitted changes. Commit or stash them first."
    echo "   Run: git status"
    exit 1
fi

echo "============================================================"
echo "Fast-forwarding $TARGET_BRANCH from $SOURCE_BRANCH..."
echo "============================================================"

# Fetch latest
echo "Fetching latest changes..."
git fetch origin

# Check if target branch exists locally or remotely
if ! git rev-parse --verify "$TARGET_BRANCH" >/dev/null 2>&1 && \
   ! git rev-parse --verify "origin/$TARGET_BRANCH" >/dev/null 2>&1; then
    echo "$TARGET_BRANCH branch doesn't exist. Creating it from $SOURCE_BRANCH..."
    git branch "$TARGET_BRANCH" "origin/$SOURCE_BRANCH"
elif git rev-parse --verify "origin/$TARGET_BRANCH" >/dev/null 2>&1 && \
     ! git rev-parse --verify "$TARGET_BRANCH" >/dev/null 2>&1; then
    # Create local tracking branch
    git branch --track "$TARGET_BRANCH" "origin/$TARGET_BRANCH"
fi

# Save current branch to restore later
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Checkout target branch
echo "Checking out $TARGET_BRANCH branch..."
git checkout "$TARGET_BRANCH"

# Fast-forward to source branch
echo "Fast-forwarding $TARGET_BRANCH to $SOURCE_BRANCH..."
if ! git merge --ff-only "origin/$SOURCE_BRANCH"; then
    echo "❌ Fast-forward failed!"
    git checkout "$ORIGINAL_BRANCH"
    exit 1
fi

# Push target branch
echo "Pushing $TARGET_BRANCH branch..."
git push origin "$TARGET_BRANCH"

# Restore original branch
if [[ "$ORIGINAL_BRANCH" != "$TARGET_BRANCH" ]]; then
    git checkout "$ORIGINAL_BRANCH"
fi

echo ""
echo "============================================================"
echo "🎉 Promotion successful!"
echo "============================================================"
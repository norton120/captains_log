#!/bin/bash
set -euo pipefail

MAIN_BRANCH="${MAIN_BRANCH:-main}"

if [ "${1:-}" = "--full" ]; then
    exit 1
fi

cd "${GIT_REPO_PATH:-/workspace}" 2>/dev/null || cd /src/data_manager

if git rev-parse --git-dir > /dev/null 2>&1 && \
   git rev-parse --verify "$MAIN_BRANCH" > /dev/null 2>&1; then

    MERGE_BASE=$(git merge-base HEAD "$MAIN_BRANCH" 2>/dev/null || echo "")

    if [ -n "$MERGE_BASE" ]; then
        COMMITTED_FILES=$(git diff --name-only --diff-filter=MAR "$MERGE_BASE" HEAD | grep '\.py$' || true)
        UNCOMMITTED_FILES=$(git diff --name-only HEAD | grep '\.py$' || true)
        CHANGED_FILES=$(echo -e "$COMMITTED_FILES\n$UNCOMMITTED_FILES" | sort -u | grep -v '^$' || true)

        if [ -n "$CHANGED_FILES" ]; then
            echo "$CHANGED_FILES" | sed 's|^|/src/|'
            exit 0
        else
            echo "No Python files changed relative to $MAIN_BRANCH" >&2
            exit 2
        fi
    fi
fi

exit 1

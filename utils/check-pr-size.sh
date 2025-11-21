#!/usr/bin/env bash
# Check if the current PR branch is becoming too large for effective review
# This script is designed to be called at the start of development work to prevent
# branches from growing too large before getting caught in review.
#
# Exit codes:
#   0 - PR size is acceptable, continue work
#   1 - PR is too large or should be split, stop work and address the issue

set -euo pipefail
# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Get the current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
MAIN_BRANCH="main"

echo "🔍 Checking PR size for branch: ${CURRENT_BRANCH}"
echo ""

# Check if we're on main branch
if [ "$CURRENT_BRANCH" = "$MAIN_BRANCH" ]; then
    echo -e "${GREEN}✓ On main branch, no PR size check needed${NC}"
    exit 0
fi

# Get diff statistics
FILES_CHANGED=$(git diff --numstat ${MAIN_BRANCH}...HEAD 2>/dev/null | wc -l | tr -d ' ')

# If no files changed, we're good
if [ "$FILES_CHANGED" -eq 0 ]; then
    echo -e "${GREEN}✓ No changes yet, PR size is acceptable${NC}"
    exit 0
fi

echo "📊 Files changed: ${FILES_CHANGED}"
echo ""

# Analyze the types of changes
echo "Analyzing change complexity..."

GENERATED_COUNT=0
REFORMAT_COUNT=0
MECHANICAL_COUNT=0
LOGIC_COUNT=0
NEW_FILES_COUNT=0

# Get list of all changed files
CHANGED_FILES=$(git diff --name-only ${MAIN_BRANCH}...HEAD)

# Function to check if a file is machine-generated
is_generated_file() {
    local file="$1"
    # VCR cassettes (test artifacts)
    [[ "$file" == */cassettes/*.yaml ]] && return 0
    [[ "$file" == */cassettes/*.yml ]] && return 0
    # Database migrations
    [[ "$file" == */migrations/versions/* ]] && return 0
    [[ "$file" == */alembic/versions/* ]] && return 0
    [[ "$file" == alembic/versions/* ]] && return 0
    # Lock files
    [[ "$file" == *package-lock.json ]] && return 0
    [[ "$file" == *poetry.lock ]] && return 0
    [[ "$file" == *Pipfile.lock ]] && return 0
    [[ "$file" == *yarn.lock ]] && return 0
    [[ "$file" == *pnpm-lock.yaml ]] && return 0
    # Generated code
    [[ "$file" == *_pb2.py ]] && return 0
    [[ "$file" == *_pb2.pyi ]] && return 0
    [[ "$file" == *.generated.* ]] && return 0
    return 1
}

# Analyze each file
while IFS= read -r file; do
    # Check if file is machine-generated (minimal weight)
    if is_generated_file "$file"; then
        GENERATED_COUNT=$((GENERATED_COUNT + 1))
        continue
    fi

    if [ ! -f "$file" ]; then
        # New file (deleted files are ignored in this check)
        if git diff ${MAIN_BRANCH}...HEAD -- "$file" 2>/dev/null | grep -q "new file"; then
            NEW_FILES_COUNT=$((NEW_FILES_COUNT + 1))
        fi
        continue
    fi

    # Check if changes are whitespace-only (reformatting)
    DIFF_WITH_WHITESPACE=$(git diff ${MAIN_BRANCH}...HEAD -- "$file" 2>/dev/null | wc -l | tr -d ' ')
    DIFF_WITHOUT_WHITESPACE=$(git diff -w ${MAIN_BRANCH}...HEAD -- "$file" 2>/dev/null | wc -l | tr -d ' ')

    if [ "$DIFF_WITH_WHITESPACE" -gt 0 ] && [ "$DIFF_WITHOUT_WHITESPACE" -eq 0 ]; then
        REFORMAT_COUNT=$((REFORMAT_COUNT + 1))
    else
        # Check if it's a mechanical change (simple pattern)
        # For now, we'll classify based on the diff size
        ADDED=$(git diff --numstat ${MAIN_BRANCH}...HEAD -- "$file" 2>/dev/null | awk '{print $1}')
        REMOVED=$(git diff --numstat ${MAIN_BRANCH}...HEAD -- "$file" 2>/dev/null | awk '{print $2}')

        # If changes are small and balanced, likely mechanical
        if [ -n "$ADDED" ] && [ -n "$REMOVED" ]; then
            TOTAL_CHANGES=$((ADDED + REMOVED))
            if [ "$TOTAL_CHANGES" -lt 50 ] && [ "$((ADDED - REMOVED))" -lt 20 ] && [ "$((REMOVED - ADDED))" -lt 20 ]; then
                MECHANICAL_COUNT=$((MECHANICAL_COUNT + 1))
            else
                LOGIC_COUNT=$((LOGIC_COUNT + 1))
            fi
        elif [ -n "$ADDED" ]; then
            LOGIC_COUNT=$((LOGIC_COUNT + 1))
        fi
    fi
done <<< "$CHANGED_FILES"

echo "  - Machine-generated: ${GENERATED_COUNT} files (migrations, VCR cassettes, lock files)"
echo "  - Reformatting only: ${REFORMAT_COUNT} files"
echo "  - Mechanical changes: ${MECHANICAL_COUNT} files"
echo "  - Logic changes: ${LOGIC_COUNT} files"
echo "  - New files: ${NEW_FILES_COUNT} files"
echo ""

# Calculate weighted complexity score
# Generated: 0.05, Reformatting: 0.1, Mechanical: 0.3, Logic: 1.0, New files: 1.0
COMPLEXITY_SCORE=$(echo "$GENERATED_COUNT * 0.05 + $REFORMAT_COUNT * 0.1 + $MECHANICAL_COUNT * 0.3 + $LOGIC_COUNT * 1.0 + $NEW_FILES_COUNT * 1.0" | bc)

echo "📈 Complexity score: ${COMPLEXITY_SCORE} (threshold: 15.0)"
echo ""

# Determine verdict
VERDICT="OK"
REASON=""
SUGGESTION=""

# Check if too large
if (( $(echo "$COMPLEXITY_SCORE > 15" | bc -l) )); then
    VERDICT="TOO_LARGE"
    REASON="Complexity score ${COMPLEXITY_SCORE} exceeds threshold of 15.0"
elif [ "$LOGIC_COUNT" -gt 10 ]; then
    VERDICT="TOO_LARGE"
    REASON="${LOGIC_COUNT} files with logic changes exceeds threshold of 10"
elif [ "$REFORMAT_COUNT" -gt 5 ] && [ "$LOGIC_COUNT" -gt 0 ]; then
    VERDICT="SHOULD_SPLIT"
    REASON="Large reformatting (${REFORMAT_COUNT} files) mixed with logic changes (${LOGIC_COUNT} files) makes review difficult"
    SUGGESTION="Split reformatting into a separate PR first, then rebase logic changes"
fi

# Output the verdict
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$VERDICT" = "OK" ]; then
    echo -e "${GREEN}✓ PR_SIZE_CHECK: OK${NC}"
    echo ""
    echo "PR size is acceptable. Continue development."
    exit 0
elif [ "$VERDICT" = "TOO_LARGE" ]; then
    echo -e "${RED}✗ PR_SIZE_CHECK: TOO_LARGE${NC}"
    echo ""
    echo -e "${RED}Reason: ${REASON}${NC}"
    echo ""
    echo "This PR has grown too large for effective review."
    echo "Please split it into smaller, focused PRs."
    echo ""
    echo "Suggested actions:"
    echo "  1. Identify logical boundaries in your changes"
    echo "  2. Create separate branches for each focused change"
    echo "  3. Submit smaller PRs that are easier to review"
    exit 1
elif [ "$VERDICT" = "SHOULD_SPLIT" ]; then
    echo -e "${YELLOW}⚠ PR_SIZE_CHECK: SHOULD_SPLIT${NC}"
    echo ""
    echo -e "${YELLOW}Reason: ${REASON}${NC}"
    echo ""
    echo -e "${YELLOW}Suggestion: ${SUGGESTION}${NC}"
    echo ""
    echo "This PR should be split to improve reviewability."
    exit 1
fi

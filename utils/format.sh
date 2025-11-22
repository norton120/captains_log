#!/usr/bin/env bash
# Code formatting script using Black
# Formats Python code in app/ and tests/ directories

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🎨 Running Black Code Formatter${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Parse command line arguments
CHECK_ONLY=false
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=true
  echo -e "${YELLOW}Running in check-only mode (no files will be modified)${NC}"
  echo ""
fi

# Run Black formatter
if [ "$CHECK_ONLY" = true ]; then
  docker compose run --rm format black --check app/ tests/
  EXIT_CODE=$?
else
  docker compose run --rm format black app/ tests/
  EXIT_CODE=$?
fi

echo ""

if [ $EXIT_CODE -eq 0 ]; then
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  if [ "$CHECK_ONLY" = true ]; then
    echo -e "${GREEN}✓ All files are properly formatted${NC}"
  else
    echo -e "${GREEN}✓ Code formatting completed successfully${NC}"
  fi
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  if [ "$CHECK_ONLY" = true ]; then
    echo -e "${RED}✗ Some files need formatting${NC}"
    echo -e "${RED}  Run './utils/format.sh' to format them${NC}"
  else
    echo -e "${RED}✗ Code formatting failed${NC}"
  fi
  echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  exit $EXIT_CODE
fi

#!/usr/bin/env bash
# Development app startup script
# Starts the app profile and opens the browser

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 Starting Development App${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Source PORT_OFFSET from .env if it exists
if [ -f .env ]; then
  # Extract PORT_OFFSET from .env file
  PORT_OFFSET=$(grep "^PORT_OFFSET=" .env | cut -d'=' -f2 || echo "0")
else
  PORT_OFFSET=0
fi

# Calculate the app port: ${PORT_OFFSET}8081
APP_PORT="${PORT_OFFSET}8082"

echo "Using PORT_OFFSET=${PORT_OFFSET}"
echo "App will be available at http://localhost:${APP_PORT}"
echo ""

# Start docker compose with app profile
docker compose --profile app up -d

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ App started successfully${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Open the browser
open "http://localhost:${APP_PORT}"

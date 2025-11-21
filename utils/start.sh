#!/usr/bin/env bash
# Development startup script
# Runs pre-flight checks before starting development work

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 Development Pre-flight Checks${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Run PR size check
if ! ./utils/check-pr-size.sh; then
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}❌ Pre-flight check failed: PR size limit exceeded${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Please address the PR size issue before continuing development."
    echo "This prevents the branch from growing even larger."
    exit 1
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ All pre-flight checks passed${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Get all ports currently in use by docker containers
used_ports=$(docker ps -q | xargs -r -n1 docker port 2>/dev/null | sed -nE 's/.*:([0-9]+)$/\1/p' | sort -n)
# Extract port offsets (first digit) from ports that match our pattern (X9XXX)
# Valid port offsets are 0-5 (because 6XXXX would exceed max port 65535)
# If any port starts with 6+, offset 0 is in use (0 is no offset, exposing base ports like 9XXX)
used_offsets=$(echo "$used_ports" | sed -nE 's/^([0-5])9[0-9]{3}$/\1/p' | sort -u)
if echo "$used_ports" | grep -qE '^[6-9]'; then
  used_offsets=$(echo -e "${used_offsets}\n0" | sort -u)
fi
echo "Used port offsets: $used_offsets"
# Find the lowest available port offset in the valid range (0-5)
PORT_OFFSET=""
for offset in {0..5}; do
  if ! echo "$used_offsets" | grep -q "^${offset}$"; then
    PORT_OFFSET=$offset
    break
  fi
done

# Error if no valid port offsets are available
if [[ -z $PORT_OFFSET ]]; then
  echo "ERROR: No valid port offsets available (0-5 all in use)" >&2
  echo "Used offsets: $used_offsets" >&2
  exit 1
fi

export PORT_OFFSET

# namespace the project name by the current git branch
# removing vibe prefix if it exists, then escape special chars for sed
COMPOSE_PROJECT_NAME=$(git branch --show-current | sed 's/vibe\///' | sed 's/[\/&\\]/\\&/g')

# Update or add COMPOSE_PROJECT_NAME in .env file
if [ -f .env ]; then
  # Set up trap to ensure .env.bak is always cleaned up
  trap 'rm -f .env.bak' EXIT

  # Ensure .env ends with a newline before appending
  if [ -n "$(tail -c 1 .env)" ]; then
    echo "" >> .env
  fi

  if grep -q "^COMPOSE_PROJECT_NAME=" .env; then
    # Update existing value
    sed -i.bak "s/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}/" .env || true
    rm -f .env.bak
  else
    # Append if not present
    echo "COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}" >> .env
  fi

  if grep -q "^PORT_OFFSET=" .env; then
    # Update existing value
    sed -i.bak "s/^PORT_OFFSET=.*/PORT_OFFSET=${PORT_OFFSET}/" .env || true
    rm -f .env.bak
  else
    # Append if not present
    echo "PORT_OFFSET=${PORT_OFFSET}" >> .env
  fi
else
  echo "WARNING: .env file not found, cannot persist COMPOSE_PROJECT_NAME or PORT_OFFSET" >&2
fi

export PORT_OFFSET
export COMPOSE_PROJECT_NAME

echo "Using PORT_OFFSET=${PORT_OFFSET} and COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}"
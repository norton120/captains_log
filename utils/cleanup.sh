#!/usr/bin/env bash
# Stop and tear down all docker compose services
# Removes containers, networks, and orphaned containers from all profiles

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🛑 Stopping Development Environment${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Source COMPOSE_PROJECT_NAME from .env if it exists
if [ -f .env ]; then
  # Extract COMPOSE_PROJECT_NAME from .env file
  COMPOSE_PROJECT_NAME=$(grep "^COMPOSE_PROJECT_NAME=" .env | cut -d'=' -f2 || echo "")
  if [ -n "$COMPOSE_PROJECT_NAME" ]; then
    export COMPOSE_PROJECT_NAME
    echo "Using project name: ${COMPOSE_PROJECT_NAME}"
  else
    echo -e "${YELLOW}WARNING: COMPOSE_PROJECT_NAME not found in .env${NC}"
  fi
else
  echo -e "${YELLOW}WARNING: .env file not found${NC}"
fi

echo ""

if [ -z "$COMPOSE_PROJECT_NAME" ]; then
  echo -e "${RED}ERROR: Cannot determine project name${NC}"
  exit 1
fi

echo "Tearing down all resources for project: ${COMPOSE_PROJECT_NAME}"
echo ""

# Stop and remove all containers for this project (both running and stopped)
echo "Stopping and removing containers..."
containers=$(docker ps -aq --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" 2>/dev/null || true)
if [ -n "$containers" ]; then
  echo "$containers" | xargs docker rm -f 2>/dev/null || true
fi

# Also catch any containers matching the project name pattern (for edge cases)
echo "Checking for containers by name pattern..."
name_containers=$(docker ps -aq --filter "name=^${COMPOSE_PROJECT_NAME}-" 2>/dev/null || true)
if [ -n "$name_containers" ]; then
  echo "$name_containers" | xargs docker rm -f 2>/dev/null || true
fi

# Remove all networks for this project
echo "Removing networks..."
networks=$(docker network ls -q --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" 2>/dev/null || true)
if [ -n "$networks" ]; then
  echo "$networks" | xargs docker network rm 2>/dev/null || true
fi

# Also catch networks by name pattern
echo "Checking for networks by name pattern..."
name_networks=$(docker network ls -q --filter "name=^${COMPOSE_PROJECT_NAME}" 2>/dev/null || true)
if [ -n "$name_networks" ]; then
  echo "$name_networks" | xargs docker network rm 2>/dev/null || true
fi

# Remove all volumes for this project
echo "Removing volumes..."
volumes=$(docker volume ls -q --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" 2>/dev/null || true)
if [ -n "$volumes" ]; then
  echo "$volumes" | xargs docker volume rm -f 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ All resources removed successfully${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

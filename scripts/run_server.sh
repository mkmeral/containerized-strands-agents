#!/bin/bash
# Run the MCP server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Ensure data directory exists
mkdir -p "$PROJECT_DIR/data/agents"

# Run the server
python -m containerized_strands_agents.server

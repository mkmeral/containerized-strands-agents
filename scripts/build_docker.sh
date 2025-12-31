#!/bin/bash
# Build the agent runner Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building agent-host-runner Docker image..."
docker build -t agent-host-runner -f "$PROJECT_DIR/docker/Dockerfile" "$PROJECT_DIR"

echo "Done! Image: agent-host-runner"

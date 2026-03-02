#!/bin/bash
# Start VS Code tunnel with the container's dev name
# This script is run inside the container

set -euo pipefail

# Get tunnel name from environment or argument
TUNNEL_NAME="${DEVCONTAINER_NAME:-${1:-devs-tunnel}}"

# Sanitize the tunnel name (replace invalid characters)
TUNNEL_NAME=$(echo "$TUNNEL_NAME" | tr -cd '[:alnum:]-_')

echo "🚇 Starting VS Code tunnel as '$TUNNEL_NAME'..."

# Check if code CLI is available
if ! command -v code &> /dev/null; then
    echo "❌ VS Code CLI not found. Please rebuild the container."
    exit 1
fi

# Start the tunnel
# --accept-server-license-terms: Skip the license acceptance prompt
# --name: Set the machine name that appears in VS Code
exec code tunnel --accept-server-license-terms --name "$TUNNEL_NAME"

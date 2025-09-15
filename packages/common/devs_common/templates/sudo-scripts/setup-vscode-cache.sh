#!/bin/bash
set -euo pipefail

echo "Setting up VS Code extensions cache..."

# Create VS Code server directory if it doesn't exist
mkdir -p /home/node/.vscode-server

# Ensure the cache volume directory exists and has correct permissions
chown node:node /home/node/.vscode-extensions-cache-volume

# Create symlink if it doesn't exist
if [ ! -L /home/node/.vscode-server/extensionsCache ]; then
    ln -sf /home/node/.vscode-extensions-cache-volume /home/node/.vscode-server/extensionsCache
    echo "✅ VS Code extensions cache symlink created"
else
    echo "✅ VS Code extensions cache symlink already exists"
fi
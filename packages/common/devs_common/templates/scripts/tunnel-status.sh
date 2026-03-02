#!/bin/bash
# Check VS Code tunnel status
# This script is run inside the container

set -euo pipefail

# Check if code CLI is available
if ! command -v code &> /dev/null; then
    echo "❌ VS Code CLI not found"
    exit 1
fi

# Check tunnel status
code tunnel status 2>/dev/null || echo "No tunnel running"

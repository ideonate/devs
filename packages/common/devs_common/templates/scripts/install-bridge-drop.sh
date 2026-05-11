#!/usr/bin/env bash
# Fetch the latest devs-bridge-drop.vsix from GitHub Releases and install it.
# Intended to be invoked from devcontainer postAttachCommand — by that point
# VS Code Server is up and 'code' resolves to the Server-aware shim that
# installs into ~/.vscode-server/extensions/.
set -uo pipefail

echo "Installing devs-bridge-drop extension..."

if ! command -v code >/dev/null 2>&1; then
    echo "⚠️  Skipping devs-bridge-drop install: 'code' CLI not on PATH"
    exit 0
fi

tmp_vsix="/tmp/devs-bridge-drop.vsix"
vsix_url="https://github.com/ideonate/devs/releases/latest/download/devs-bridge-drop.vsix"

if ! curl -fsSL "$vsix_url" -o "$tmp_vsix"; then
    echo "⚠️  Could not download $vsix_url (continuing)"
    exit 0
fi

if code --install-extension "$tmp_vsix" --force; then
    echo "✓ Installed devs-bridge-drop"
else
    echo "⚠️  'code --install-extension' failed for devs-bridge-drop (continuing)"
fi

rm -f "$tmp_vsix"
exit 0

#!/usr/bin/env bash
# Build the vscode-bridge-drop extension and stage the .vsix inside devs-common
# so it ships with the PyPI wheel and is mounted into every devcontainer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXT_SRC="$ROOT/packages/vscode-bridge-drop"
EXT_DEST="$ROOT/packages/common/devs_common/templates/extensions"

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm is required to build the VS Code extension" >&2
    exit 1
fi

echo "==> Building vscode-bridge-drop"
cd "$EXT_SRC"

if [ ! -d node_modules ]; then
    npm install
fi

npm run compile
npx vsce package --out devs-bridge-drop.vsix --allow-missing-repository

mkdir -p "$EXT_DEST"
rm -f "$EXT_DEST"/devs-bridge-drop*.vsix
mv devs-bridge-drop.vsix "$EXT_DEST/devs-bridge-drop.vsix"

echo "==> Staged $EXT_DEST/devs-bridge-drop.vsix"
ls -la "$EXT_DEST/devs-bridge-drop.vsix"

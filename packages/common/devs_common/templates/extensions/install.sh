#!/usr/bin/env bash
# Install every bundled .vsix in this directory.
# Intended to be invoked from a devcontainer postCreateCommand or postAttachCommand.
# Self-contained — does not depend on anything outside this directory.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

shopt -s nullglob
vsix_files=("$SCRIPT_DIR"/*.vsix)
shopt -u nullglob

if [ ${#vsix_files[@]} -eq 0 ]; then
    echo "[devs-extensions] no .vsix files found in $SCRIPT_DIR"
    exit 0
fi

install_with_code_cli() {
    local vsix="$1"
    code --install-extension "$vsix" --force
}

install_by_unpacking() {
    # Fallback when 'code' CLI isn't on PATH yet (e.g. third-party image that
    # doesn't bake in the CLI, when running before VS Code Server attaches).
    # VS Code Server scans ~/.vscode-server/extensions/<publisher>.<name>-<version>/
    local vsix="$1"
    local home_dir="${HOME:-/root}"
    local ext_root="$home_dir/.vscode-server/extensions"
    mkdir -p "$ext_root"

    local tmp
    tmp="$(mktemp -d)"
    if ! unzip -q "$vsix" -d "$tmp" 2>/dev/null; then
        if command -v python3 >/dev/null 2>&1; then
            python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$vsix" "$tmp" || {
                rm -rf "$tmp"; return 1
            }
        else
            rm -rf "$tmp"
            return 1
        fi
    fi

    # .vsix layout: extension/package.json + extension/...
    local manifest="$tmp/extension/package.json"
    if [ ! -f "$manifest" ]; then
        rm -rf "$tmp"
        return 1
    fi

    local publisher name version
    publisher=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['publisher'])" "$manifest")
    name=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['name'])" "$manifest")
    version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$manifest")

    local target="$ext_root/${publisher}.${name}-${version}"
    rm -rf "$target"
    mv "$tmp/extension" "$target"
    rm -rf "$tmp"
    echo "[devs-extensions] unpacked into $target"
}

for vsix in "${vsix_files[@]}"; do
    name="$(basename "$vsix")"
    echo "[devs-extensions] installing $name"
    if command -v code >/dev/null 2>&1; then
        if install_with_code_cli "$vsix"; then
            continue
        fi
        echo "[devs-extensions] 'code --install-extension' failed for $name; trying fallback unpack"
    fi
    if install_by_unpacking "$vsix"; then
        echo "[devs-extensions] installed $name via unpack fallback"
    else
        echo "[devs-extensions] ⚠️  failed to install $name (continuing)"
    fi
done
exit 0

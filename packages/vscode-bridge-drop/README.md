# devs-bridge-drop

VS Code extension that turns the `devs` bridge mount into a bidirectional drop target.

Drop a file from your host OS onto the **Bridge** panel and it lands in `/home/node/bridge/dropped/...` inside the container. Right-click a container-side file in the VS Code explorer → "Copy to Bridge" and it lands in the same place. Either way, the entry shows both the **container path** and the **host path** with copy buttons, and the container path is auto-copied to your clipboard.

See the project-root `CLAUDE.md` for design notes (why a webview rather than a TreeView, why drag-into-terminal isn't fixable, etc.).

## How it gets installed

Published to the VS Code Marketplace as `ideonate.devs-bridge-drop`. Add it to any `.devcontainer/devcontainer.json` like any other extension:

```jsonc
"customizations": {
  "vscode": {
    "extensions": ["ideonate.devs-bridge-drop"]
  }
}
```

VS Code installs it automatically on attach. No shell scripts, no mounts, no env-vars.

The `devs` template's `devcontainer.json` already includes it, so repos using the template need no changes.

### Offline / air-gapped fallback

Every release also publishes the raw `.vsix` to GitHub Releases at a stable URL:

```
https://github.com/ideonate/devs/releases/latest/download/devs-bridge-drop.vsix
```

If you can't reach the Marketplace (corporate firewall, air-gapped environment), wire this into a `postAttachCommand` instead. `postAttachCommand` rather than `postCreateCommand` is important: by `postAttachCommand` time, VS Code Server's `code` shim is on PATH and installs land in `~/.vscode-server/extensions/` where the attached editor actually reads from.

```jsonc
"postAttachCommand": "command -v code >/dev/null && curl -fsSL https://github.com/ideonate/devs/releases/latest/download/devs-bridge-drop.vsix -o /tmp/d.vsix && code --install-extension /tmp/d.vsix --force || true"
```

Or, fully offline: the `.vsix` ships inside the `devs-common` Python package at `devs_common/templates/extensions/devs-bridge-drop.vsix`, with a self-contained `install.sh` next to it.

**Pinning to a specific version**: the Marketplace path always serves the latest. To pin, use the GitHub-release URL with `download/vX.Y.Z` instead of `latest`.

## Building locally

```bash
./scripts/build-extension.sh    # from repo root
```

Stages the `.vsix` at `packages/common/devs_common/templates/extensions/devs-bridge-drop.vsix` (gitignored). CI runs this automatically before producing the GitHub Release and PyPI wheels.

## Behaviour

- Files are written to `/home/node/bridge/dropped/<YYYYMMDD-HHmmss>-<sanitized-name>` (collision-safe).
- The host-side path is derived from `DEVS_BRIDGE_MOUNT_PATH`, which the `devs` CLI passes through as a `remoteEnv` var. If unset (e.g. raw devcontainer CLI), only the container path is shown.
- Drop history is persisted in workspace state, capped at 50 entries.
- Folder drops are not supported — files only.

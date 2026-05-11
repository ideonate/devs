# devs-bridge-drop

VS Code extension that turns the `devs` bridge mount into a bidirectional drop target.

Drop a file from your host OS onto the **Bridge** panel and it lands in `/home/node/bridge/dropped/...` inside the container. Right-click a container-side file in the VS Code explorer → "Copy to Bridge" and it lands in the same place. Either way, the entry shows both the **container path** and the **host path** with copy buttons, and the container path is auto-copied to your clipboard.

See the project-root `CLAUDE.md` for design notes (why a webview rather than a TreeView, why drag-into-terminal isn't fixable, etc.).

## Why

The devcontainer has `~/.devs/bridge/<project>-<dev>/` bind-mounted to `/home/node/bridge`. This extension uses that mount as neutral ground so files can move between host and container without `docker cp` or fiddling with host-OS paths the container can't resolve.

## Install (dev)

```bash
cd packages/vscode-bridge-drop
npm install
npm run compile
npm run package   # produces devs-bridge-drop.vsix
```

Inside a running devcontainer:

```bash
code --install-extension /path/to/devs-bridge-drop.vsix
```

Or symlink into `~/.vscode-server/extensions/` for live development.

## Behaviour

- Files are written to `/home/node/bridge/dropped/<YYYYMMDD-HHmmss>-<sanitized-name>` (collision-safe).
- The host-side path is derived from `DEVS_BRIDGE_MOUNT_PATH`, which the `devs` CLI passes through as a `remoteEnv` var. If unset (e.g. raw devcontainer CLI), only the container path is shown.
- Drop history is persisted in workspace state, capped at 50 entries.
- Folder drops are not supported in v1 — files only.

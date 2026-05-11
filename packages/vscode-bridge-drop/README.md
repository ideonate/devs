# devs-bridge-drop

VS Code extension that turns the `devs` bridge mount into a bidirectional drop target.

Drop a file from your host OS onto the **Bridge** panel and it lands in `/home/node/bridge/dropped/...` inside the container. Right-click a container-side file in the VS Code explorer → "Copy to Bridge" and it lands in the same place. Either way, the entry shows both the **container path** and the **host path** with copy buttons, and the container path is auto-copied to your clipboard.

See the project-root `CLAUDE.md` for design notes (why a webview rather than a TreeView, why drag-into-terminal isn't fixable, etc.).

## How it gets installed

Each release is published as a GitHub Release asset at a stable URL:

```
https://github.com/ideonate/devs/releases/latest/download/devs-bridge-drop.vsix
```

A one-line `curl` + `code --install-extension` fetches and installs it. The `devs` template's `setup-workspace.sh` already does this on first container start, so repos using the template need no changes.

## Wiring it into a third-party `.devcontainer/devcontainer.json`

Add one entry, in any runtime hook of your choosing:

```jsonc
"postAttachCommand": "command -v code >/dev/null && curl -fsSL https://github.com/ideonate/devs/releases/latest/download/devs-bridge-drop.vsix -o /tmp/d.vsix && code --install-extension /tmp/d.vsix --force || true"
```

That's all. No mount, no env-var dependency, works regardless of whether `devs` started the container (or whether `devs` is installed at all).

### Why `postAttachCommand` specifically

`postCreateCommand` runs before VS Code Server attaches. Even if your image bakes the standalone `code` CLI onto PATH (the `devs` template does, for tunnel support), that CLI installs extensions into a different location than where VS Code Server reads from on attach. Installs at `postCreateCommand` time therefore appear to succeed but the extension never shows up.

`postAttachCommand` fires after VS Code Server is in place. By then `code` resolves to the Server-aware shim that installs into `~/.vscode-server/extensions/` — the location the attached VS Code actually scans. Use this hook unless you know exactly what you're doing.

### Notes

- **Chaining with an existing hook command**: `"postAttachCommand": "your-existing-command && curl ... && code --install-extension ..."`. Arrays also work per the devcontainer spec.
- **Pinning to a specific version**: replace `latest` with `download/vX.Y.Z` in the URL.
- **Offline / no internet in the container**: the `.vsix` is also bundled inside the `devs-common` Python package at `devs_common/templates/extensions/devs-bridge-drop.vsix`, alongside a self-contained `install.sh` you can copy into a container and run manually. Not part of the default install path; just a fallback.

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

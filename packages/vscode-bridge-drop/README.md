# devs-bridge-drop

VS Code extension that turns the `devs` bridge mount into a bidirectional drop target.

Drop a file from your host OS onto the **Bridge** panel and it lands in `/home/node/bridge/dropped/...` inside the container. Right-click a container-side file in the VS Code explorer → "Copy to Bridge" and it lands in the same place. Either way, the entry shows both the **container path** and the **host path** with copy buttons, and the container path is auto-copied to your clipboard.

See the project-root `CLAUDE.md` for design notes (why a webview rather than a TreeView, why drag-into-terminal isn't fixable, etc.).

## Auto-install when using the devs template

If your repo uses the `devs` devcontainer template (i.e. you don't have your own `.devcontainer/devcontainer.json`), there is nothing to do. The extension is bundled into the `devs-common` PyPI package, mounted into every container, and installed by the template's `setup-workspace.sh` on first start.

## Wiring it into a third-party `.devcontainer/devcontainer.json`

Two things are needed:

1. **Mount the extensions dir** so `install.sh` and the `.vsix` are reachable inside the container:

   ```jsonc
   "mounts": [
     "source=${localEnv:DEVS_EXTENSIONS_MOUNT_PATH},target=/usr/local/devs-extensions,type=bind,readonly"
   ]
   ```

2. **Invoke `/usr/local/devs-extensions/install.sh` from any runtime hook you like.** The script is self-contained — it finds every `.vsix` next to it, tries `code --install-extension --force`, and falls back to unzipping into `~/.vscode-server/extensions/` if `code` isn't on PATH. Some options:

   - **`postAttachCommand`** — fires after VS Code Server attaches, so the `code` CLI is reliably available. Best default for VS Code-attached workflows.
     ```jsonc
     "postAttachCommand": "bash /usr/local/devs-extensions/install.sh || true"
     ```
   - **`postCreateCommand`** — runs once on first container creation. Works if your image already has `code` on PATH, or if you're happy with the unzip fallback.
     ```jsonc
     "postCreateCommand": "bash /usr/local/devs-extensions/install.sh || true"
     ```
   - **From your own setup script** — if your devcontainer already has its own `setup-workspace.sh` (or similar) wired into a hook, just call `install.sh` from inside it: `bash /usr/local/devs-extensions/install.sh || true`. Same effect.
   - **`onCreateCommand` / `updateContentCommand`** — also fine. Anywhere that runs inside the container after the mount is live works.

### Notes

- **Bake into the image?** Not really viable from this mount, because the mount is only present at *runtime* (it's resolved from a `localEnv` var on container start). If you want the extension baked into your image, you'd have to `COPY` your own `.vsix` in at image build time, which defeats the point of the bundled-distribution approach. Stick to a runtime hook.
- **Chaining with an existing hook command**: `"postAttachCommand": "your-existing-command && bash /usr/local/devs-extensions/install.sh || true"`. Arrays also work per the devcontainer spec.
- **Container started outside `devs` (raw `devcontainer` CLI)**: `DEVS_EXTENSIONS_MOUNT_PATH` won't be set, so the mount source will resolve to empty and `devcontainer up` will error. Either start through `devs`, or guard the mount entry behind whatever conditional config mechanism you have.
- **Repos that copied from the `devs` template wholesale**: you already have the equivalent wiring — the template's `setup-workspace.sh` delegates to the same `install.sh`. No action needed.

## Building

```bash
./scripts/build-extension.sh    # from repo root
```

Stages the `.vsix` at `packages/common/devs_common/templates/extensions/devs-bridge-drop.vsix` (gitignored). Run before publishing devs-common to PyPI; `scripts/bump-and-publish.py` does this automatically.

## Behaviour

- Files are written to `/home/node/bridge/dropped/<YYYYMMDD-HHmmss>-<sanitized-name>` (collision-safe).
- The host-side path is derived from `DEVS_BRIDGE_MOUNT_PATH`, which the `devs` CLI passes through as a `remoteEnv` var. If unset (e.g. raw devcontainer CLI), only the container path is shown.
- Drop history is persisted in workspace state, capped at 50 entries.
- Folder drops are not supported — files only.

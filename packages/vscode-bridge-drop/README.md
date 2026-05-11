# devs-bridge-drop

VS Code extension that turns the `devs` bridge mount into a bidirectional drop target.

Drop a file from your host OS onto the **Bridge** panel and it lands in `/home/node/bridge/dropped/...` inside the container. Right-click a container-side file in the VS Code explorer → "Copy to Bridge" and it lands in the same place. Either way, the entry shows both the **container path** and the **host path** with copy buttons, and the container path is auto-copied to your clipboard.

See the project-root `CLAUDE.md` for design notes (why a webview rather than a TreeView, why drag-into-terminal isn't fixable, etc.).

## Auto-install when using the devs template

If your repo uses the `devs` devcontainer template (i.e. you don't have your own `.devcontainer/devcontainer.json`), there is nothing to do. The extension is bundled into the `devs-common` PyPI package, mounted into every container, and installed by the template's `setup-workspace.sh` on first start.

## Wiring it into a third-party `.devcontainer/devcontainer.json`

For repos that have their own committed devcontainer config (e.g. they diverged from the `devs` template, or never used it), add two lines:

```jsonc
{
  // ... your existing config ...
  "mounts": [
    // ... your existing mounts ...
    "source=${localEnv:DEVS_EXTENSIONS_MOUNT_PATH},target=/usr/local/devs-extensions,type=bind,readonly"
  ],
  "postAttachCommand": "bash /usr/local/devs-extensions/install.sh || true"
}
```

That's it. The `devs` CLI exports `DEVS_EXTENSIONS_MOUNT_PATH` automatically when it invokes `devcontainer up`, so the mount resolves at runtime. The mounted `install.sh` is the same self-contained installer the `devs` template uses internally — single source of truth.

### Notes

- **Already have a `postAttachCommand`?** Chain it: `"postAttachCommand": "your-existing-command && bash /usr/local/devs-extensions/install.sh || true"`. Or move both into an array if you prefer.
- **Why `postAttachCommand` and not `postCreateCommand`?** `postCreateCommand` fires before VS Code Server is installed, so the `code` CLI may not exist yet. `postAttachCommand` fires after Server is up. The installer has an `unzip`-into-`~/.vscode-server/extensions/` fallback for environments where `code` is still not on PATH, but `postAttachCommand` is the natural fit.
- **Container started outside `devs` (raw `devcontainer` CLI)**: `DEVS_EXTENSIONS_MOUNT_PATH` won't be set, so the mount source will be empty and `devcontainer up` will error. Either start through `devs`, or omit these two lines from your config in that environment.
- **Repos that copied from the template wholesale**: you've already got the equivalent wiring (the mount entry, plus the `setup-workspace.sh` delegation). No action needed.

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

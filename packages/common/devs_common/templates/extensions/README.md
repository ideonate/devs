# Bundled VS Code extensions

Built `.vsix` files placed in this directory are mounted into every devcontainer at `/usr/local/devs-extensions/` (read-only) and installed by `setup-workspace.sh` on container creation.

Build artifacts are gitignored. Produce them with:

```bash
./scripts/build-extension.sh
```

This compiles `packages/vscode-bridge-drop/` and drops the resulting `devs-bridge-drop.vsix` here. Re-run after editing the extension to pick up changes on the next `devs start`.

`scripts/bump-and-publish.py` runs the build script automatically before producing PyPI wheels, so released `devs-common` wheels always include the current `.vsix`.

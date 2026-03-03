# VS Code Tunnel Support in Devcontainers

This documents the changes needed to enable `devs tunnel` support in a devcontainer. If you're adapting a custom devcontainer (not using the devs template), apply these changes to your own Dockerfile and devcontainer.json.

## How Authentication Works

Authentication is handled on the **host machine**, not inside containers. The `devs tunnel --auth` command runs the VS Code CLI on the host and stores credentials in `~/.devs/vscode-cli/`. This directory is bind-mounted into all containers, so you authenticate once and every container picks it up — same pattern as `devs claude --auth`.

## Dockerfile Changes

### 1. Install the VS Code CLI

The standalone VS Code CLI (not the full VS Code) provides the `tunnel` command. Install it as root since it goes in `/usr/local/bin`:

```dockerfile
# Install VS Code CLI for tunnel support
USER root
RUN ARCH=$(dpkg --print-architecture) && \
  if [ "$ARCH" = "amd64" ]; then \
    curl -fSL 'https://update.code.visualstudio.com/latest/cli-linux-x64/stable' -o /tmp/vscode-cli.tar.gz; \
  elif [ "$ARCH" = "arm64" ]; then \
    curl -fSL 'https://update.code.visualstudio.com/latest/cli-linux-arm64/stable' -o /tmp/vscode-cli.tar.gz; \
  fi && \
  tar -xf /tmp/vscode-cli.tar.gz -C /usr/local/bin && \
  rm /tmp/vscode-cli.tar.gz && \
  chmod +x /usr/local/bin/code
```

Remember to switch back to your non-root user afterwards if needed (`USER node`).

### 2. Create the auth directory with correct ownership

The VS Code CLI stores tunnel state at `~/.vscode/cli/`. Create it in the Dockerfile so the bind mount has correct permissions:

```dockerfile
RUN mkdir -p /home/node/.vscode/cli && \
  chown -R node:node /home/node/.vscode
```

In the devs template, this is part of the existing `mkdir` block.

## devcontainer.json Changes

### 3. Bind-mount the host auth directory

Bind-mount `~/.devs/vscode-cli/` from the host into the container. This is where `devs tunnel --auth` stores credentials on the host.

```json
"mounts": [
  "source=${localEnv:HOME}/.devs/vscode-cli,target=/home/node/.vscode/cli,type=bind"
]
```

Key points:
- **Bind mount from host**: `~/.devs/vscode-cli/` on the host maps to `/home/node/.vscode/cli` in the container.
- **Shared across all containers**: every container on the host sees the same auth tokens.
- **Same pattern as Claude/Codex**: mirrors how `~/.devs/claudeconfig` and `~/.devs/codexconfig` are bind-mounted.

## Tunnel Name Limit

VS Code tunnel names have a **20 character limit**. The devs CLI generates names from `{prefix}-{project}-{devname}` and truncates to fit, keeping the dev name suffix intact. If you're setting tunnel names manually, keep this limit in mind.

## Usage

```bash
# One-time auth on the host (no project/container needed)
devs tunnel --auth

# Start tunnel in background (from within a project directory)
devs tunnel <name>

# Connect from your local machine (command shown in tunnel output)
code --remote tunnel+<tunnel-name> /workspaces/<workspace-name>

# Check status / stop
devs tunnel <name> --status
devs tunnel <name> --kill
```

## Adapting for Non-devs Devcontainers

If you want tunnel support in a standalone devcontainer (without devs CLI), the minimum changes are:

1. **Dockerfile**: Install the VS Code CLI (step 1 above)
2. **devcontainer.json**: Add the bind mount (step 3 above)
3. **Host setup**: Create `~/.devs/vscode-cli/` and run `VSCODE_CLI_DATA_DIR=~/.devs/vscode-cli code tunnel user login --provider github`
4. **Start the tunnel**: `code tunnel --accept-server-license-terms --name <name>`

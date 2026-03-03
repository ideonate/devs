# VS Code Tunnel Support in Devcontainers

This documents the changes needed to enable `devs tunnel` support in a devcontainer. If you're adapting a custom devcontainer (not using the devs template), apply these changes to your own Dockerfile and devcontainer.json.

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

The VS Code CLI stores tunnel authentication at `~/.vscode/cli/`. Create it in the Dockerfile so the volume mount has correct permissions:

```dockerfile
RUN mkdir -p /home/node/.vscode/cli && \
  chown -R node:node /home/node/.vscode
```

In the devs template, this is part of the existing `mkdir` block (line 90).

## devcontainer.json Changes

### 3. Add a shared volume for tunnel auth

Add a named Docker volume to persist tunnel authentication across container recreations. Using a fixed volume name (not per-workspace) means auth is shared across all containers on the same host — authenticate once, use everywhere.

```json
"mounts": [
  "source=devs-vscode-cli-tunnel,target=/home/node/.vscode/cli,type=volume"
]
```

Key points:
- **Fixed volume name** (`devs-vscode-cli-tunnel`): shared across all containers on the host, so one `devs tunnel --auth` authenticates for all dev environments.
- **Target path** (`/home/node/.vscode/cli`): where the VS Code CLI stores its auth tokens and tunnel state.
- **Named volume** (not bind mount): Docker manages the storage, persists across container stop/start/recreate.

## Tunnel Name Limit

VS Code tunnel names have a **20 character limit**. The devs CLI generates names from `{prefix}-{project}-{devname}` and truncates to fit, keeping the dev name suffix intact. If you're setting tunnel names manually, keep this limit in mind.

## Usage After Setup

```bash
# One-time auth (interactive, opens browser for GitHub device code)
devs tunnel <name> --auth

# Start tunnel in background
devs tunnel <name>

# Check status / stop
devs tunnel <name> --status
devs tunnel <name> --kill
```

## Adapting for Non-devs Devcontainers

If you want tunnel support in a standalone devcontainer (without devs CLI), the minimum changes are:

1. **Dockerfile**: Install the VS Code CLI (step 1 above)
2. **devcontainer.json**: Add the shared volume mount (step 3 above)
3. **Start the tunnel manually**: `code tunnel --accept-server-license-terms --name <name>`
4. **Auth manually**: `code tunnel user login --provider github`

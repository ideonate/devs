# VS Code Tunnel Support in Devcontainers

This documents the changes needed to enable `devs tunnel` support in a devcontainer. If you're adapting a custom devcontainer (not using the devs template), apply these changes to your own Dockerfile and devcontainer.json.

## How Authentication Works

Authentication runs inside a container via `devs tunnel <name> --auth`. The credentials are stored in the container's own filesystem and persist across stop/restart cycles (but not container removal/recreation). Each container authenticates independently.

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

## Tunnel Name Limit

VS Code tunnel names have a **20 character limit**. The devs CLI generates names from `{prefix}-{project}-{devname}` and truncates to fit, keeping the dev name suffix intact. If you're setting tunnel names manually, keep this limit in mind.

## Usage

```bash
# One-time auth per container (run from a project directory with a running container)
devs tunnel <name> --auth

# Start tunnel in background
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
2. **Auth**: Run `code tunnel user login --provider github` inside the container
3. **Start the tunnel**: `code tunnel --accept-server-license-terms --name <name>`

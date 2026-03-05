# devs-webadmin - Web Admin UI

A web-based admin interface for managing devcontainers on a server. Provides the same core functionality as the `devs` CLI but accessible from a browser -- useful for headless servers, remote machines, or when you want a visual overview of running containers.

## Features

- **Container Management**: Start, stop, and clean up devcontainers from a web UI
- **Repository-Based**: Enter any GitHub `org/repo` to start containers (uses RepoCache, no local checkout needed)
- **All Containers View**: See all devs-managed containers across all projects at a glance
- **VS Code Tunnels**: Start, stop, and authenticate tunnels directly from the browser
- **Tunnel Auth via Device Flow**: GitHub device code flow for tunnel authentication without needing a terminal

## Installation

```bash
# From the monorepo root
pip install -e packages/webadmin/

# Or when published
pip install devs-webadmin
```

## Quick Start

```bash
# Start the web admin server
devs-webadmin serve

# Open http://localhost:8080 in your browser
```

## Usage

### Starting the Server

```bash
# Default: 0.0.0.0:8080
devs-webadmin serve

# Custom host/port
devs-webadmin serve --host 127.0.0.1 --port 3000

# Development mode with auto-reload
devs-webadmin serve --reload
```

### Web UI

The UI has two main sections:

**Start Container Form** -- Enter a GitHub repository (e.g. `ideonate/devs`) and a dev name (e.g. `sally`), then click Start. The repo is cloned/updated via the shared repo cache at `~/.devs/repocache/`.

**Container List** -- Shows all devs-managed containers with:
- Status (running/exited) with color indicators
- Project name, mode (copy/live), creation time
- Stop (preserves container state) and Clean (removes container + workspace) buttons
- Tunnel controls for running containers

### Tunnel Controls

Each running container shows a tunnel panel:

- **Start tunnel** -- Launches a VS Code tunnel in the container. Once running, shows an "Open in browser" link to `vscode.dev`.
- **Kill tunnel** -- Stops a running tunnel.
- **Auth** -- Opens a modal with the GitHub device flow. A device code is displayed along with a link to `github.com/login/device`. Complete the login in your browser and the modal updates automatically when authentication succeeds. Auth persists across container stop/restart cycles.

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WEBADMIN_HOST` | `0.0.0.0` | Server bind address |
| `WEBADMIN_PORT` | `8080` | Server port |
| `DEVS_WORKSPACES_DIR` | `~/.devs/workspaces` | Workspace directory |
| `DEVS_REPO_CACHE_DIR` | `~/.devs/repocache` | Repository cache directory |
| `DEVS_CLAUDE_CONFIG_DIR` | `~/.devs/claudeconfig` | Claude config directory |
| `DEVS_CODEX_CONFIG_DIR` | `~/.devs/codexconfig` | Codex config directory |
| `GH_TOKEN` / `GITHUB_TOKEN` | (none) | GitHub token for private repos |

### Shared Directories

The webadmin shares the same directories as the CLI and webhook:

- `~/.devs/repocache/` -- Cached repository clones
- `~/.devs/workspaces/` -- Workspace copies for containers
- `~/.devs/claudeconfig/` -- Claude authentication

## Architecture

### Backend

- **FastAPI** + **Uvicorn** (same stack as the webhook package)
- Uses `devs-common` for all container/workspace/repo operations
- Synchronous common library calls wrapped with `asyncio.to_thread`
- Stop/clean operations work by Docker container name (no repo cloning needed)

### Frontend

- **Vue 3** loaded from CDN (no build step, no npm required)
- Single `index.html` served as a static file from the Python package
- Self-contained -- ships inside the pip package with no external build process

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/containers` | List all containers (optional `?repo=org/repo` filter) |
| `POST` | `/api/start` | Start container `{ repo, dev_name }` |
| `POST` | `/api/stop` | Stop container `{ container_name }` |
| `POST` | `/api/clean` | Remove container + workspace `{ container_name }` |
| `GET` | `/api/tunnel/status` | Tunnel status `?container_name=X` |
| `POST` | `/api/tunnel/start` | Start tunnel `{ container_name }` |
| `POST` | `/api/tunnel/kill` | Kill tunnel `{ container_name }` |
| `POST` | `/api/tunnel/auth` | Start device flow auth `{ container_name }` |
| `GET` | `/api/tunnel/auth/status` | Poll auth completion `?container_name=X` |

## Requirements

- **Python 3.8+**
- **Docker** running and accessible
- **DevContainer CLI**: `npm install -g @devcontainers/cli`
- **devs-common** package (installed automatically as a dependency)

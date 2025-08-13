# CLAUDE.md

This file provides guidance to Claude Code when working with the `devs` project - a DevContainer Management Toolkit with multiple Python packages for managing named devcontainers.

## Project Overview

`devs` is now a multi-package monorepo containing tools for managing multiple named devcontainers for any project. The main CLI tool allows developers to run commands like `devs start sally bob` to create multiple development environments with distinct names, then `devs vscode sally` to launch VS Code connected to specific containers.

## Repository Structure

This is a **multi-package monorepo** with the following structure:

```
devs/
├── packages/
│   ├── cli/                    # Main CLI tool (Python package)
│   ├── webhook/               # GitHub webhook handler (fully implemented)
│   └── common/                # Shared utilities between CLI and webhook
├── docs/                      # Documentation
├── scripts/                   # Development scripts
├── devs                       # Legacy zsh script (to be removed)
├── README.md                  # Monorepo overview
└── CLAUDE.md                  # This file
```

## Key Features

- **Multiple Named Containers**: Start multiple devcontainers with custom names (e.g., "sally", "bob", "charlie")
- **VS Code Integration**: Open containers in separate VS Code windows with clear titles
- **Project Isolation**: Containers are prefixed with git repository names (org-repo format)
- **Workspace Isolation**: Each dev environment gets its own workspace copy
- **Cross-Platform**: Works on any project with devcontainer configuration
- **Python Architecture**: Object-oriented design with proper error handling and testing

## Package Details

### CLI Package (`packages/cli/`)

**Installation**: `pip install devs` (when published) or `pip install -e packages/cli/` (development)

**Package Structure**:

```
packages/cli/
├── devs/
│   ├── __init__.py             # Package initialization
│   ├── cli.py                  # Click-based CLI interface
│   ├── config.py               # Configuration management
│   ├── exceptions.py           # Custom exception classes
│   ├── core/                   # Core business logic
│   │   ├── project.py          # Project detection and info
│   │   ├── container.py        # Docker container management
│   │   ├── workspace.py        # Workspace isolation
│   │   └── integration.py      # VS Code integration
│   └── utils/                  # Utility modules
│       ├── docker_client.py    # Docker API wrapper
│       ├── devcontainer.py     # DevContainer CLI wrapper
│       ├── git_utils.py        # Git operation utilities
│       └── file_utils.py       # File operation utilities
├── tests/                      # Test suite
├── pyproject.toml             # Package configuration
└── README.md                  # Package documentation
```

**Key Classes**:

- `Project`: Handles project detection, git info, naming conventions
- `ContainerManager`: Manages Docker container lifecycle using python-docker API
- `WorkspaceManager`: Handles workspace copying and isolation
- `VSCodeIntegration`: Manages VS Code launching and devcontainer URIs
- `DockerClient`: Docker API wrapper with comprehensive error handling

### Webhook Package (`packages/webhook/`)

**Installation**: `pip install devs-webhook` (when published) or `pip install -e packages/webhook/` (development)

**Key Components**:

- **GitHub Webhook Handler**: Processes @mentions in issues/PRs
- **Container Pool**: Manages named containers (eamonn, harry, darren by default)
- **Worker Architecture**: Subprocess-based worker for Docker safety
- **Claude Code Integration**: Uses Claude Code SDK for automated development
- **Repository Cache**: Shared cache with CLI for repository cloning

**Deployment Options**:
- Systemd service with setup script (`packages/webhook/systemd/`)
- Docker Compose for containerized deployment
- Standalone Flask application

### Common Package (`packages/common/`)

**Shared Components**:

- **Core Classes**: Project, WorkspaceManager, ContainerManager
- **Templates**: Devcontainer templates with post-creation scripts
- **Configuration**: Base configuration classes for both packages
- **Utilities**: Shared git, Docker, and file operations

## Architecture

### Container Naming

Containers follow the pattern: `dev-<org>-<repo>-<dev-name>`

Example: `dev-ideonate-devs-sally`, `dev-ideonate-devs-bob`

### Workspace Management

Each dev environment gets its own isolated workspace:

- **Location**: `~/.devs/workspaces/<project-name>-<dev-name>/`
- **Content**: Git-tracked files (or all files for non-git projects)
- **Special dirs**: `.git`, `.claude`, `.devcontainer` extras copied
- **Exclusions**: Build/cache directories excluded for non-git projects
- **Python venv**: Always created at `/home/node/.devs-venv/workspace-venv` to keep workspaces clean
- **No .python-version**: The container never creates/modifies `.python-version` files to avoid conflicts with host Python paths

#### Live Mode

The `--live` flag mounts the current directory directly into the container without creating a workspace copy:

- **Container workspace path**: Uses the host folder name (e.g., `/workspaces/myproject`) instead of the constructed name (e.g., `/workspaces/myorg-myrepo-alice`)
- **Reason**: The devcontainer CLI directly mounts the host folder and preserves its original name. We must match this behavior for VS Code to connect properly.
- **Example**: If working in `/Users/alice/projects/myapp`, the container sees `/workspaces/myapp` (not `/workspaces/myorg-myapp-alice`)

#### Python Environment in Containers

- **Location**: Virtual environments are always created at `/home/node/.devs-venv/workspace-venv`
- **Activation**: Run `source /home/node/.devs-venv/workspace-venv/bin/activate` in the terminal
- **VS Code**: Automatically configured via `.vscode/settings.devcontainer.json`
- **`.python-version` files**: If present from the host, they are ignored in the container
  - The container sets `PYENV_VERSION=system` to prevent pyenv from reading `.python-version`
  - This avoids errors from host-specific Python paths that don't exist in the container
- **Clean workspaces**: No `venv` folders or `.python-version` files are created in your workspace

### VS Code Integration

- **URI Format**: `vscode-remote://dev-container+${hex_path}/workspaces/${workspace_name}`
- **Unique Paths**: Each dev environment gets unique workspace path for VS Code separation
- **Window Titles**: Custom titles based on dev environment names

### Python Dependencies

- **Docker Operations**: `docker` package (native Python API)
- **Git Operations**: `GitPython` (robust git handling)
- **CLI Framework**: `click` (better argument parsing and help)
- **Terminal Output**: `rich` (beautiful terminal output and tables)
- **File Operations**: Native Python `pathlib` and `shutil`

## Commands

### Core Commands (CLI Package)

- `devs start <name...>` - Start named devcontainers
- `devs vscode <name...>` - Open devcontainers in VS Code
- `devs stop <name...>` - Stop and remove devcontainers
- `devs shell <name>` - Open shell in devcontainer
- `devs list` - List active devcontainers for current project
- `devs status` - Show project and dependency status
- `devs clean --unused` - Clean up unused workspaces
- `devs help` - Show usage information

**Live Mode**: Add `--live` flag to `start` or `vscode` commands to mount the current directory directly without creating a workspace copy.

### Example Workflow

```bash
# Start development environments
devs start frontend backend

# Open both in VS Code (separate windows)
devs vscode frontend backend

# Check status
devs status

# Work in a specific container
devs shell frontend

# Clean up when done
devs stop frontend backend

# Use live mode (no workspace copy)
devs vscode mydev --live
```

## Development

### Development Setup

```bash
# Quick setup for all packages
./scripts/setup-dev.sh

# Or manually for CLI package
cd packages/cli
pip install -e ".[dev]"
```

### Development Scripts

- `./scripts/setup-dev.sh` - Install all packages in development mode
- `./scripts/test-all.sh` - Run tests across all packages
- `./scripts/lint-all.sh` - Lint and format all packages
- `./scripts/clean.sh` - Clean build artifacts and cache files

### Testing

```bash
# Test all packages
./scripts/test-all.sh

# Test CLI package specifically
cd packages/cli && pytest -v
```

### Code Quality

```bash
# Lint all packages
./scripts/lint-all.sh

# Or for CLI package specifically
cd packages/cli
black devs tests        # Format code
mypy devs              # Type checking
flake8 devs tests      # Linting
```

## Configuration

### Environment Variables

#### Core Configuration

- `DEVS_WORKSPACES_DIR`: Custom workspace directory (default: `~/.devs/workspaces`)
- `DEVS_PROJECT_PREFIX`: Container name prefix (default: `dev`)
- `DEVS_CLAUDE_CONFIG_DIR`: Claude config directory (default: `~/.devs/claudeconfig`)

#### GitHub Integration

- `GH_TOKEN`: GitHub personal access token (for private repositories and GitHub CLI authentication)
  ```bash
  export GH_TOKEN=your_github_token_here
  devs start mydev  # Token automatically passed to container
  ```

#### Webhook Configuration

**Core Settings**:
- `GITHUB_WEBHOOK_SECRET`: GitHub webhook secret for validation
- `GITHUB_TOKEN`: GitHub personal access token (same as GH_TOKEN)
- `GITHUB_MENTIONED_USER`: GitHub username to watch for @mentions
- `CLAUDE_API_KEY`: Claude API key for webhook responses

**Container Pool**:
- `CONTAINER_POOL`: Comma-separated container names (default: eamonn,harry,darren)
- `CONTAINER_TIMEOUT_MINUTES`: Idle timeout for containers (default: 60)
- `MAX_CONCURRENT_TASKS`: Maximum parallel tasks (default: 3)

**Access Control**:
- `ALLOWED_ORGS`: Comma-separated GitHub organizations
- `ALLOWED_USERS`: Comma-separated GitHub usernames

**Server Settings**:
- `WEBHOOK_HOST`: Server bind address (default: 0.0.0.0)
- `WEBHOOK_PORT`: Server port (default: 8000)

### Project Configuration (DEVS.yml)

Projects can include a `DEVS.yml` file in their repository root:

```yaml
default_branch: develop  # Override default branch (default: main)
prompt_extra: |          # Additional Claude instructions
  This project uses specific coding standards...
```

### DevContainer Support

The devcontainer.json should support `DEVCONTAINER_NAME` for custom naming and `GH_TOKEN` for runtime GitHub access:

```json
{
  "name": "${localEnv:DEVCONTAINER_NAME:Default} - Project Name",
  "remoteEnv": {
    "GH_TOKEN": "${localEnv:GH_TOKEN}"
  }
}
```

### Migrating from .env Files

Previous versions required creating `.devcontainer/.env` files with `GH_TOKEN=...`. This is no longer needed:

**Old approach (deprecated):**

```bash
# Create .devcontainer/.env file
echo "GH_TOKEN=your_token" > .devcontainer/.env
devs start mydev
```

**New approach (recommended):**

```bash
# Set environment variable (persists across sessions if added to ~/.bashrc or ~/.zshrc)
export GH_TOKEN=your_github_token_here
devs start mydev  # Token automatically available in container at runtime
```

**How it works:**

- The `GH_TOKEN` is passed as a **runtime environment variable** (not build-time)
- Available inside the running container for tools like `gh` CLI
- More secure than storing tokens in Docker image layers
- No rebuilds needed when tokens change

Note: `.devcontainer/.env` files are still copied if they exist (for other custom environment variables), but `GH_TOKEN` is now passed directly from your environment.

## Dependencies

### Runtime Dependencies

- **Python 3.8+**: Required for the package
- **Docker**: Container runtime
- **VS Code**: With `code` command in PATH
- **DevContainer CLI**: `npm install -g @devcontainers/cli`
- **Project Requirements**: `.devcontainer/devcontainer.json` in target projects

### Development Dependencies

- `pytest>=6.0`: Testing framework
- `pytest-cov`: Coverage reporting
- `black`: Code formatting
- `mypy`: Type checking
- `flake8`: Linting

## Key Implementation Details

### Project Detection (Python)

Uses `GitPython` for robust git operations:

```python
# Extract org-repo format from git URL
def _extract_project_name_from_url(self, git_url: str) -> str:
    # Handles SSH and HTTPS formats
    # Converts to org-repo format
```

### Container Management (Python)

Uses `docker` Python package for native API access:

```python
# Direct Docker API calls instead of CLI
def ensure_container_running(self, dev_name: str, workspace_dir: Path) -> bool:
    # Check container status
    # Handle image rebuilds
    # Manage container lifecycle
```

### Workspace Creation (Python)

Uses native Python file operations:

```python
# Git-aware file copying
def create_workspace(self, dev_name: str) -> Path:
    # Copy git-tracked files or all files
    # Handle special directories
    # Exclude build/cache directories
```

## Error Handling

### Custom Exception Hierarchy

- `DevsError`: Base exception
- `ProjectNotFoundError`: Project detection issues
- `DevcontainerConfigError`: Missing devcontainer.json
- `ContainerError`: Container operation failures
- `WorkspaceError`: Workspace operation failures
- `VSCodeError`: VS Code integration failures
- `DependencyError`: Missing dependencies

### Dependency Checking

The CLI automatically checks for required dependencies and provides installation instructions for missing tools.

## Webhook Operation

### How It Works

1. **GitHub Event**: User @mentions the configured username in an issue/PR
2. **Webhook Reception**: Server validates signature and queues task
3. **Container Assignment**: Task assigned to available container from pool
4. **Repository Setup**: Repository cloned/updated in container
5. **Claude Execution**: Claude Code analyzes issue and implements solution
6. **Response**: Results posted back to GitHub issue/PR

### Worker Architecture

The webhook uses a subprocess-based worker system for Docker safety:

```bash
devs-webhook-worker --container-name eamonn --task-json-stdin < task.json
```

- **Process Isolation**: Prevents Docker operations from blocking web server
- **JSON Communication**: Large payloads passed via stdin
- **Timeout Protection**: 60-minute timeout for tasks
- **Deduplication**: Content hashing prevents duplicate processing

## Testing

The project now includes comprehensive test coverage:

```bash
# Test all packages
./scripts/test-all.sh

# Test webhook package  
pytest packages/webhook/tests/ -v

# Test CLI package
pytest packages/cli/tests/ -v
```

## Future Enhancements

### Potential Features

- **Plugin System**: Extensible plugin architecture
- **Configuration Files**: YAML/TOML configuration files
- **Container Templates**: Custom devcontainer templates per project
- **Resource Management**: CPU/memory limits and monitoring
- **Multi-Project Support**: Managing containers across multiple projects
- **Web Interface**: Optional web UI for container management

## Troubleshooting

### Python Package Issues

- **Import Errors**: Ensure package installed with `pip install -e packages/cli/`
- **Dependency Issues**: Run `devs status` to check dependency availability
- **Permission Issues**: Ensure Docker daemon is running and accessible

### Container Issues

- **Container not found**: Check `devs list` and verify project detection
- **VS Code connection issues**: Verify devcontainer configuration exists
- **Workspace issues**: Check `~/.devs/workspaces/` for workspace copies

### Development Issues

- **Test failures**: Run `./scripts/test-all.sh` to see detailed output
- **Linting failures**: Run `./scripts/lint-all.sh` to identify and fix issues
- **Type checking**: Use `mypy devs` in the CLI package directory

### Claude CLI Issues in Containers

#### `uv_cwd` Error in Bind-Mounted Directories

**Problem**: Claude CLI fails with `Error: ENOENT: no such file or directory, uv_cwd` when running in Docker containers with bind-mounted workspace directories.

**Root Cause**: This Node.js error occurs when the current working directory becomes inaccessible due to bind mount timing issues. The sequence is:
1. Container starts with empty `/workspaces/<workspace-name>` directory
2. Workspace files are copied to host directory 
3. Host directory is bind-mounted over the container directory
4. The original directory handle becomes stale (shows 0 links in `stat`)
5. Node.js `uv_cwd` system call fails when Claude tries to get current working directory

**Diagnosis**:
```bash
# Check if directory has stale mount (Links: 0 indicates problem)
docker exec <container> stat /workspaces/<workspace-name>

# Compare with host directory (should show Links: >0)
stat ~/.devs/workspaces/<workspace-name>

# Check if bind mount is empty in container
docker exec <container> ls -la /workspaces/<workspace-name>/
```

**Solutions**:

1. **Run Claude from stable directory** (recommended):
   ```bash
   # Instead of: cd /workspaces/project && claude
   # Use: cd /home/node && claude --project /workspaces/project
   docker exec -i container /bin/zsh -l -c "cd /home/node && claude [commands]"
   ```

2. **Container restart after workspace creation**:
   ```bash
   # After workspace copy, restart container to refresh mounts
   docker restart <container-name>
   ```

3. **Remount the directory**:
   ```bash
   docker exec container /bin/bash -c "umount /workspaces/<workspace> && mount --bind /host/path /workspaces/<workspace>"
   ```

**Technical Details**:
- Error occurs in Node.js libuv `uv_cwd` system call
- Affects Node.js applications that call `process.cwd()` at startup
- Claude CLI version with Node.js 22+ still affected
- Bind mounts over existing directories can create stale filesystem handles
- Common in Docker containers with dynamic workspace creation

**Prevention**:
- Ensure workspace directories are created before container starts
- Use consistent mount ordering in devcontainer configuration  
- Consider using named volumes instead of bind mounts for workspace data

This architecture provides a solid foundation for both the current CLI tool and future webhook handler while maintaining backward compatibility and providing a much more maintainable codebase.

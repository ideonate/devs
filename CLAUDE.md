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
│   ├── webhook/               # GitHub webhook handler (planned)
│   └── common/                # Shared utilities (planned)
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

- `GITHUB_WEBHOOK_SECRET`: GitHub webhook secret
- `GITHUB_TOKEN`: GitHub personal access token (same as GH_TOKEN)
- `GITHUB_MENTIONED_USER`: GitHub username to watch for @mentions
- `CLAUDE_API_KEY`: Claude API key for webhook responses

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

## Future Enhancements

### Planned Packages

- **Webhook Package** (`packages/webhook/`): GitHub App webhook handler for automated devcontainer operations
- **Common Package** (`packages/common/`): Shared utilities between CLI and webhook

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

This architecture provides a solid foundation for both the current CLI tool and future webhook handler while maintaining backward compatibility and providing a much more maintainable codebase.

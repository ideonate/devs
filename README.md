# devs - DevContainer Management Toolkit

A collection of tools for managing multiple named devcontainers for any project.

## Repository Structure

This is a multi-package monorepo containing:

### 📦 [CLI Tool](packages/cli/) - `devs`

The main command-line interface for managing devcontainers locally.

```bash
# Install the CLI tool
pip install devs

# Start development environments
devs start frontend backend

# Open in VS Code
devs vscode frontend backend
```

### 🔄 [Webhook Handler](packages/webhook/)

GitHub webhook handler for automated devcontainer operations in response to @mentions in issues and PRs.

### 🛠️ [Common Utilities](packages/common/)

Shared utilities between CLI and webhook packages including container management, workspace handling, and devcontainer templates.

## Quick Start

### Installation

```bash
# Install just the CLI tool
pip install devs

# Or install from source (development)
cd packages/cli
pip install -e .
```

### Basic Usage

```bash
# Start development environments
devs start sally bob charlie

# Open containers in VS Code (separate windows)
devs vscode sally bob

# Work in a specific container
devs shell sally

# List active containers
devs list

# Clean up when done
devs stop sally bob charlie
```

## Requirements

- **Docker**: Container runtime
- **VS Code**: With `code` command in PATH
- **DevContainer CLI**: `npm install -g @devcontainers/cli`
- **Project Requirements**: `.devcontainer/devcontainer.json` in target projects

## Features

- **Multiple Named Containers**: Start multiple devcontainers with custom names
- **VS Code Integration**: Open containers in separate VS Code windows with clear titles
- **Project Isolation**: Containers are prefixed with git repository names
- **Workspace Isolation**: Each dev environment gets its own workspace copy
- **Environment Variable Management**: Layered configuration system with user-specific overrides
- **GitHub Webhook Integration**: Automated CI and Claude Code responses to @mentions
- **Cross-Platform**: Works on any project with devcontainer configuration

## Configuration

### Environment Variables

devs supports a powerful layered configuration system for environment variables:

```bash
# Basic usage with repository DEVS.yml
devs start myenv

# CLI overrides for testing
devs start myenv --env DEBUG=true --env API_URL=http://localhost:3000
```

**Configuration priority (highest to lowest):**
1. CLI `--env` flags
2. `~/.devs/envs/{org-repo}/DEVS.yml` (user-specific project overrides)
3. `~/.devs/envs/default/DEVS.yml` (user defaults)
4. `{project-root}/DEVS.yml` (repository configuration)

**Example DEVS.yml:**
```yaml
env_vars:
  default:
    NODE_ENV: development
    API_URL: https://api.example.com
  
  myenv:  # Container-specific overrides
    DEBUG: "true"
    SPECIAL_FEATURE: "enabled"
```

**User-specific configuration:**
```bash
# Global defaults for all projects
mkdir -p ~/.devs/envs/default
echo 'env_vars:
  default:
    GLOBAL_SETTING: "user_preference"' > ~/.devs/envs/default/DEVS.yml

# Project-specific overrides (replace "/" with "-" in repo name)
mkdir -p ~/.devs/envs/myorg-myrepo
echo 'env_vars:
  myenv:
    SECRET_KEY: "user_secret"' > ~/.devs/envs/myorg-myrepo/DEVS.yml
```

📖 **[See example-usage.md for detailed examples and scenarios](example-usage.md)**

## Development

### Repository Structure

```
devs/
├── packages/
│   ├── cli/                    # Main CLI tool
│   ├── webhook/               # GitHub webhook handler
│   └── common/                # Shared utilities
├── docs/                      # Documentation
├── scripts/                   # Development scripts
├── devs                       # Legacy zsh script (to be removed)
└── README.md                  # This file
```

### Development Setup

```bash
# Install CLI package in development mode
cd packages/cli
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black devs tests

# Type checking
mypy devs
```

### Publishing Releases

Use the provided script to bump versions and publish all packages to PyPI:

```bash
# Patch version bump (e.g., 0.1.0 -> 0.1.1)
python scripts/bump-and-publish.py

# Minor version bump (e.g., 0.1.0 -> 0.2.0)
python scripts/bump-and-publish.py minor

# Major version bump (e.g., 0.1.0 -> 1.0.0)
python scripts/bump-and-publish.py major
```

The script will:
- Update version numbers in all three package `pyproject.toml` files
- Build packages in dependency order (common → cli → webhook)
- Upload to PyPI using `twine`

**Prerequisites:**
- `build` and `twine` packages installed
- PyPI authentication configured (API token or username/password)

## Architecture

### Container Naming

Containers follow the pattern: `dev-<org>-<repo>-<dev-name>`

Example: `dev-ideonate-devs-sally`, `dev-ideonate-devs-bob`

### VS Code Window Management

Each container gets unique workspace paths to ensure VS Code treats them as separate sessions.

### Workspace Isolation

Each dev environment gets its own workspace copy with:

- Git-tracked files (or all files for non-git projects)
- Special directories (.git, .claude, .devcontainer extras)
- Proper exclusion of build/cache directories

## Legacy Shell Script

The original zsh script is still available at the repository root (`./devs`) but will be removed in a future version. New users should use the Python CLI tool.

## License

MIT License - see individual package directories for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes in the appropriate package directory
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a Pull Request

## Support

- [Issues](https://github.com/ideonate/devs/issues)
- [CLI Documentation](packages/cli/README.md)

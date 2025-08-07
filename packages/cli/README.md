# devs - DevContainer Management Tool

A Python command-line tool that simplifies managing multiple named devcontainers for any project.

## Features

- **Multiple Named Containers**: Start multiple devcontainers with custom names (e.g., "sally", "bob", "charlie")
- **VS Code Integration**: Open containers in separate VS Code windows with clear titles
- **Project Isolation**: Containers are prefixed with git repository names (org-repo format)
- **Shared Authentication**: Claude credentials are shared between containers for the same project
- **Cross-Platform**: Works on any project with devcontainer configuration

## Installation

```bash
pip install devs
```

## Usage

```bash
# Start development environments
devs start frontend backend

# Open both in VS Code (separate windows)
devs vscode frontend backend

# Work in a specific container
devs shell frontend

# Run Claude in a container
devs claude frontend "Summarize this codebase"

# Set up Claude authentication (once per host)
devs claude-auth
# Or with API key
devs claude-auth --api-key <YOUR_API_KEY>

# Clean up when done
devs stop frontend backend

# List active containers
devs list
```

## Requirements

- **Docker**: Container runtime
- **VS Code**: With `code` command in PATH
- **DevContainer CLI**: `npm install -g @devcontainers/cli`
- **Project Requirements**: `.devcontainer/devcontainer.json` in target projects

## Architecture

### Container Naming
Containers follow the pattern: `dev-<org>-<repo>-<dev-name>`

Example: `dev-ideonate-devs-sally`, `dev-ideonate-devs-bob`

### VS Code Window Management
Each container gets unique workspace paths to ensure VS Code treats them as separate sessions.

### Claude Authentication Sharing
The tool creates symlinks so all containers for the same project share Claude authentication.

## Development

```bash
# Clone repository
git clone https://github.com/ideonate/devs.git
cd devs/python-devs

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black devs tests

# Type checking
mypy devs
```

## License

MIT License
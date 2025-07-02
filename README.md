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
devs open frontend backend
```

### 🔄 Webhook Handler *(Coming Soon)*
GitHub App webhook handler for automated devcontainer operations.

### 🛠️ Common Utilities *(Coming Soon)*
Shared utilities between CLI and webhook packages.

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
devs open sally bob

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
- **Cross-Platform**: Works on any project with devcontainer configuration

## Development

### Repository Structure
```
devs/
├── packages/
│   ├── cli/                    # Main CLI tool
│   ├── webhook/               # GitHub webhook handler (planned)
│   └── common/                # Shared utilities (planned)
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

## Migration from Shell Script

If you're upgrading from the original zsh script, see [MIGRATION.md](packages/cli/MIGRATION.md) for detailed migration information.

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
6. Submit a pull request

## Support

- [Issues](https://github.com/ideonate/devs/issues)
- [CLI Documentation](packages/cli/README.md)
- [Migration Guide](packages/cli/MIGRATION.md)
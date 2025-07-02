# Migration from Shell Script to Python Package

This document outlines the migration from the original zsh script to the new Python package.

## Key Improvements

### 1. **Better Architecture**
- Object-oriented design with clear separation of concerns
- Proper error handling with custom exceptions
- Type hints for better code quality
- Comprehensive logging and user feedback

### 2. **Enhanced Dependencies**
- **Docker operations**: Native Python API via `docker` package instead of CLI calls
- **Git operations**: `GitPython` library for robust git operations
- **File operations**: Native Python `pathlib` and `shutil` instead of shell commands
- **CLI framework**: `click` for better argument parsing and help generation
- **Terminal output**: `rich` for beautiful terminal output and progress indicators

### 3. **Better Error Handling**
- Custom exception hierarchy for different error types
- Graceful failure handling with informative error messages
- Dependency checking with helpful installation instructions

### 4. **Enhanced Features**
- Better workspace management with gitignore support
- Improved container lifecycle management
- More robust VS Code integration
- Configuration management via environment variables
- Status commands for debugging

## Migration Guide

### Installation

#### Old (Shell Script)
```bash
git clone https://github.com/ideonate/devs.git
cd devs
sudo ln -sf "$(pwd)/devs" /usr/local/bin/devs
```

#### New (Python Package)
```bash
# From source
cd python-devs
pip install -e .

# Or when published
pip install devs
```

### Command Compatibility

All original commands work identically:

| Command | Shell Script | Python Package | Status |
|---------|-------------|----------------|---------|
| `devs start <names>` | ✅ | ✅ | Identical |
| `devs open <names>` | ✅ | ✅ | Enhanced with better error handling |
| `devs stop <names>` | ✅ | ✅ | Identical |
| `devs shell <name>` | ✅ | ✅ | Identical |
| `devs list` | ✅ | ✅ | Enhanced with table output |
| `devs help` | ✅ | ✅ | Better help system |

### New Commands

The Python package adds several new commands:

```bash
# Show project and dependency status
devs status

# Clean up unused workspaces
devs clean --unused

# Clean specific workspaces
devs clean sally bob

# Enhanced list with better formatting
devs list
```

### Configuration

#### Environment Variables
Both versions support configuration via environment variables:

```bash
# Workspace directory (default: ~/.devs/workspaces)
export DEVS_WORKSPACES_DIR=/custom/path

# Container prefix (default: "dev")
export DEVS_PROJECT_PREFIX=mydev

# Claude config directory (default: ~/.devs/claudeconfig)
export DEVS_CLAUDE_CONFIG_DIR=/custom/claude
```

## Dependencies

### Runtime Dependencies
- **Python 3.8+**: Required for the package
- **Docker**: Container runtime (same as before)
- **VS Code**: With `code` command in PATH (same as before)
- **DevContainer CLI**: `npm install -g @devcontainers/cli` (same as before)

### Python Package Dependencies
- `click>=8.0.0`: CLI framework
- `docker>=6.0.0`: Docker Python API
- `GitPython>=3.1.0`: Git operations
- `rich>=12.0.0`: Terminal output
- `pathspec>=0.10.0`: Path specifications

### Development Dependencies
- `pytest>=6.0`: Testing framework
- `pytest-cov`: Coverage reporting
- `black`: Code formatting
- `mypy`: Type checking
- `flake8`: Linting

## Architecture Overview

```
devs/
├── devs/
│   ├── __init__.py              # Package initialization
│   ├── cli.py                   # Click-based CLI interface
│   ├── config.py                # Configuration management
│   ├── exceptions.py            # Custom exception classes
│   ├── core/                    # Core business logic
│   │   ├── project.py           # Project detection and info
│   │   ├── container.py         # Docker container management
│   │   ├── workspace.py         # Workspace isolation
│   │   └── integration.py       # VS Code and tool integration
│   └── utils/                   # Utility modules
│       ├── docker_client.py     # Docker API wrapper
│       ├── devcontainer.py      # DevContainer CLI wrapper
│       ├── git_utils.py         # Git operation utilities
│       └── file_utils.py        # File operation utilities
├── tests/                       # Test suite
├── pyproject.toml              # Package configuration
└── README.md                   # Documentation
```

## Key Classes

### Core Classes
- **`Project`**: Handles project detection, git info, naming conventions
- **`ContainerManager`**: Manages Docker container lifecycle
- **`WorkspaceManager`**: Handles workspace copying and isolation
- **`VSCodeIntegration`**: Manages VS Code launching and integration

### Utility Classes
- **`DockerClient`**: Docker API wrapper with error handling
- **`DevContainerCLI`**: DevContainer CLI wrapper
- **`ExternalToolIntegration`**: Dependency checking and management

## Testing

The Python package includes a comprehensive test suite:

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=devs

# Run specific test files
pytest tests/test_project.py

# Run with verbose output
pytest -v
```

## Development

### Setup Development Environment
```bash
cd python-devs
pip install -e ".[dev]"
```

### Code Quality
```bash
# Format code
black devs tests

# Type checking
mypy devs

# Linting
flake8 devs
```

### Running from Source
```bash
# Run CLI directly
python -m devs.cli --help

# Or use the installed command
devs --help
```

## Future Enhancements

The Python architecture enables several future enhancements:

1. **Plugin System**: Extensible plugin architecture for custom integrations
2. **Configuration Files**: YAML/TOML configuration files for complex setups
3. **Container Templates**: Custom devcontainer templates per project
4. **Resource Management**: CPU/memory limits and monitoring
5. **Multi-Project Support**: Managing containers across multiple projects
6. **Backup/Restore**: Container state persistence
7. **Web Interface**: Optional web UI for container management
8. **Integration APIs**: REST API for external tool integration

## Backwards Compatibility

The Python package maintains 100% command-line compatibility with the shell script. Users can switch between implementations without changing their workflows.

## Performance

The Python implementation may have slightly higher startup time due to Python initialization, but provides:

- Better error recovery and handling
- More robust container management
- Enhanced dependency checking
- Improved user feedback and progress indication
- Better resource cleanup
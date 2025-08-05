# devs CLI Test Suite

This directory contains comprehensive tests for the devs CLI tool.

## Test Structure

### Unit Tests
- `test_project.py` - Tests for Project class (git URL parsing, container naming)
- `test_container_manager.py` - Tests for ContainerManager class (Docker operations)
- `test_workspace_manager.py` - Tests for WorkspaceManager class (workspace isolation)
- `test_integration.py` - Tests for VSCodeIntegration and ExternalToolIntegration classes

### Integration Tests
- `test_cli.py` - Basic CLI command help and argument validation
- `test_cli_start.py` - Tests for `devs start` command
- `test_cli_vscode.py` - Tests for `devs vscode` command
- `test_cli_stop.py` - Tests for `devs stop` command
- `test_cli_clean.py` - Tests for `devs clean` command
- `test_cli_misc.py` - Tests for `list`, `status`, `shell`, and `claude` commands

### End-to-End Tests
- `test_e2e.py` - Full workflow tests using the devs project itself

## Test Fixtures

The `conftest.py` file provides shared fixtures:
- `cli_runner` - Click test runner
- `mock_docker_client` - Mocked Docker client
- `temp_project` - Temporary project with devcontainer config
- `mock_container_manager` - Mocked ContainerManager
- `mock_workspace_manager` - Mocked WorkspaceManager
- Various other mocks and utilities

## Running Tests

### All Tests
```bash
pytest -v
```

### Specific Test Files
```bash
pytest tests/test_container_manager.py -v
```

### Exclude E2E Tests (faster)
```bash
pytest -v -k "not e2e"
```

### With Coverage
```bash
pytest --cov=devs --cov-report=html
```

## Test Requirements

Tests require the following to be installed:
- pytest
- pytest-cov
- All CLI dependencies

Install with:
```bash
pip install -e ".[dev]"
```

## Mocking Strategy

The tests use extensive mocking to avoid:
- Docker daemon requirements
- File system operations
- External command execution
- VS Code installation requirements

This allows tests to run quickly in any environment, including CI/CD pipelines.

## Adding New Tests

When adding new features:
1. Add unit tests for new classes/methods
2. Add integration tests for new CLI commands
3. Update e2e tests if the workflow changes
4. Ensure all tests pass before submitting PR
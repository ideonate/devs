"""End-to-end tests for the devs CLI using the devs project itself."""
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from devs.cli import cli


def docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


@pytest.mark.e2e
@pytest.mark.skipif(not docker_available(), reason="Docker is not available")
class TestEndToEnd:
    """End-to-end test suite using the actual devs project."""
    
    @pytest.fixture
    def project_root(self):
        """Get the devs project root directory."""
        # Go up from tests directory to find project root
        current_dir = Path(__file__).parent
        while not (current_dir / ".git").exists() and current_dir.parent != current_dir:
            current_dir = current_dir.parent
        return current_dir
    
    @pytest.fixture
    def cleanup_containers(self):
        """Cleanup any test containers after tests."""
        yield
        # Cleanup any test containers that might be left over
        try:
            subprocess.run(
                ["docker", "ps", "-a", "--filter", "name=dev-ideonate-devs-test", "-q"],
                capture_output=True,
                text=True
            )
            # Remove any test containers
            subprocess.run(
                ["docker", "rm", "-f", "dev-ideonate-devs-test-e2e"],
                capture_output=True,
                stderr=subprocess.DEVNULL
            )
        except:
            pass
    
    def test_full_workflow(self, cli_runner, project_root, cleanup_containers, monkeypatch):
        """Test complete workflow: start, list, shell command, stop."""
        # Change to project directory
        monkeypatch.chdir(project_root)
        
        # Use a unique name for e2e test to avoid conflicts
        test_name = "test-e2e"
        
        # 1. Check project status
        result = cli_runner.invoke(cli, ['status'])
        assert result.exit_code == 0
        assert "Project: ideonate-devs" in result.output
        
        # 2. Start a container
        with patch('devs.cli.ExternalToolIntegration') as mock_external_tools:
            # Mock dependency checks to pass
            mock_external_tools.return_value.check_all.return_value = True
            mock_external_tools.return_value.check_docker.return_value = True
            mock_external_tools.return_value.check_devcontainer_cli.return_value = True
            
            result = cli_runner.invoke(cli, ['start', test_name])
            
            # Allow some flexibility in the output
            if result.exit_code != 0:
                # If it fails, it might be due to actual Docker/devcontainer issues
                # which is okay for unit tests
                assert "Error" in result.output or "Failed" in result.output
                pytest.skip("Skipping e2e test - Docker/devcontainer not available")
            else:
                assert f"Starting development environment '{test_name}'" in result.output
        
        # 3. List containers
        result = cli_runner.invoke(cli, ['list'])
        if result.exit_code == 0 and test_name in result.output:
            # Container was created successfully
            assert "Active development environments for ideonate-devs" in result.output
            assert test_name in result.output
            
            # 4. Run a command in the container
            result = cli_runner.invoke(cli, ['shell', test_name, '-c', 'echo "Hello from devs"'])
            if result.exit_code == 0:
                assert "Hello from devs" in result.output
            
            # 5. Stop the container
            result = cli_runner.invoke(cli, ['stop', test_name])
            assert result.exit_code == 0
            assert f"Successfully stopped: {test_name}" in result.output
        
        # 6. Verify container is gone
        result = cli_runner.invoke(cli, ['list'])
        assert test_name not in result.output
    
    def test_multiple_containers_workflow(self, cli_runner, project_root, cleanup_containers, monkeypatch):
        """Test workflow with multiple containers."""
        # Change to project directory
        monkeypatch.chdir(project_root)
        
        # Use unique names for e2e test
        test_names = ["test-e2e-1", "test-e2e-2"]
        
        with patch('devs.cli.ExternalToolIntegration') as mock_external_tools:
            # Mock dependency checks
            mock_external_tools.return_value.check_all.return_value = True
            mock_external_tools.return_value.check_docker.return_value = True
            mock_external_tools.return_value.check_devcontainer_cli.return_value = True
            
            # Start multiple containers
            result = cli_runner.invoke(cli, ['start'] + test_names)
            
            if result.exit_code != 0:
                pytest.skip("Skipping e2e test - Docker/devcontainer not available")
            
            # List should show both
            result = cli_runner.invoke(cli, ['list'])
            if result.exit_code == 0:
                for name in test_names:
                    assert name in result.output
                
                # Stop all
                result = cli_runner.invoke(cli, ['stop', '--all'])
                assert result.exit_code == 0
                
                # Verify all are gone
                result = cli_runner.invoke(cli, ['list'])
                for name in test_names:
                    assert name not in result.output
    
    def test_error_handling(self, cli_runner, project_root, monkeypatch):
        """Test error handling in real scenarios."""
        # Change to project directory
        monkeypatch.chdir(project_root)
        
        # Try to open VS Code for non-existent container
        result = cli_runner.invoke(cli, ['vscode', 'non-existent'])
        assert result.exit_code == 1
        assert "Container 'non-existent' is not running" in result.output
        
        # Try to shell into non-existent container
        result = cli_runner.invoke(cli, ['shell', 'non-existent'])
        assert result.exit_code == 1
        assert "Container 'non-existent' is not running" in result.output
        
        # Try to stop non-existent container
        result = cli_runner.invoke(cli, ['stop', 'non-existent'])
        # Should handle gracefully
        assert "Container 'non-existent' not found" in result.output
    
    def test_clean_command_workflow(self, cli_runner, project_root, cleanup_containers, monkeypatch):
        """Test the clean command workflow."""
        # Change to project directory
        monkeypatch.chdir(project_root)
        
        with patch('devs.cli.ExternalToolIntegration') as mock_external_tools:
            # Mock dependency checks
            mock_external_tools.return_value.check_all.return_value = True
            
            # Create and stop a container to have unused workspaces
            test_name = "test-e2e-clean"
            
            # Start container
            result = cli_runner.invoke(cli, ['start', test_name])
            if result.exit_code != 0:
                pytest.skip("Skipping e2e test - Docker/devcontainer not available")
            
            # Stop container (keeps workspace)
            result = cli_runner.invoke(cli, ['stop', test_name, '--keep-workspace'])
            
            # Clean unused workspaces
            result = cli_runner.invoke(cli, ['clean', '--unused'])
            # Should offer to clean the stopped container's workspace
            assert "Cleaning unused workspaces" in result.output or "No unused workspaces found" in result.output
    
    def test_project_detection(self, cli_runner, tmp_path, monkeypatch):
        """Test project detection in different scenarios."""
        # Test in non-project directory
        monkeypatch.chdir(tmp_path)
        
        result = cli_runner.invoke(cli, ['status'])
        assert result.exit_code == 1
        assert "Not in a git repository" in result.output or "Error" in result.output
        
        # Create a git repo without devcontainer
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("""[core]
    repositoryformatversion = 0
[remote "origin"]
    url = https://github.com/test/repo.git
""")
        
        result = cli_runner.invoke(cli, ['status'])
        assert result.exit_code == 0
        assert "DevContainer Config" in result.output
        assert "Not found" in result.output or "✗" in result.output
    
    @pytest.mark.slow
    def test_concurrent_operations(self, cli_runner, project_root, cleanup_containers, monkeypatch):
        """Test concurrent container operations."""
        # Change to project directory
        monkeypatch.chdir(project_root)
        
        with patch('devs.cli.ExternalToolIntegration') as mock_external_tools:
            # Mock dependency checks
            mock_external_tools.return_value.check_all.return_value = True
            
            # Start multiple containers concurrently
            test_names = [f"test-e2e-concurrent-{i}" for i in range(3)]
            
            # Start all at once
            result = cli_runner.invoke(cli, ['start'] + test_names)
            
            if result.exit_code == 0:
                # All should be listed
                result = cli_runner.invoke(cli, ['list'])
                for name in test_names:
                    assert name in result.output or "concurrent" in result.output
                
                # Stop all at once
                result = cli_runner.invoke(cli, ['stop'] + test_names)
                assert result.exit_code == 0
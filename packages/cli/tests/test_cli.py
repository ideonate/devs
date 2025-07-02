"""Tests for CLI interface."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, Mock

from devs.cli import cli


class TestCLI:
    """Test cases for CLI interface."""
    
    def test_cli_help(self):
        """Test that CLI help command works."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        
        assert result.exit_code == 0
        assert "DevContainer Management Tool" in result.output
        assert "start" in result.output
        assert "open" in result.output
        assert "stop" in result.output
        assert "shell" in result.output
        assert "list" in result.output
    
    def test_cli_version(self):
        """Test that CLI version command works."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--version'])
        
        assert result.exit_code == 0
        assert "0.1.0" in result.output
    
    def test_start_command_help(self):
        """Test start command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['start', '--help'])
        
        assert result.exit_code == 0
        assert "Start named devcontainers" in result.output
        assert "DEV_NAMES" in result.output
    
    def test_open_command_help(self):
        """Test open command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['open', '--help'])
        
        assert result.exit_code == 0
        assert "Open devcontainers in VS Code" in result.output
        assert "DEV_NAMES" in result.output
    
    def test_stop_command_help(self):
        """Test stop command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['stop', '--help'])
        
        assert result.exit_code == 0
        assert "Stop and remove devcontainers" in result.output
        assert "DEV_NAMES" in result.output
    
    def test_shell_command_help(self):
        """Test shell command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['shell', '--help'])
        
        assert result.exit_code == 0
        assert "Open shell in devcontainer" in result.output
        assert "DEV_NAME" in result.output
    
    def test_list_command_help(self):
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['list', '--help'])
        
        assert result.exit_code == 0
        assert "List active devcontainers" in result.output
    
    def test_status_command_help(self):
        """Test status command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['status', '--help'])
        
        assert result.exit_code == 0
        assert "Show project and dependency status" in result.output
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    def test_start_missing_args(self, mock_get_project, mock_check_deps):
        """Test start command with missing arguments."""
        runner = CliRunner()
        result = runner.invoke(cli, ['start'])
        
        assert result.exit_code != 0
        assert "Missing argument" in result.output
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    def test_open_missing_args(self, mock_get_project, mock_check_deps):
        """Test open command with missing arguments."""
        runner = CliRunner()
        result = runner.invoke(cli, ['open'])
        
        assert result.exit_code != 0
        assert "Missing argument" in result.output
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    def test_stop_missing_args(self, mock_get_project, mock_check_deps):
        """Test stop command with missing arguments."""
        runner = CliRunner()
        result = runner.invoke(cli, ['stop'])
        
        assert result.exit_code != 0
        assert "Missing argument" in result.output
    
    @patch('devs.cli.check_dependencies')
    @patch('devs.cli.get_project')
    def test_shell_missing_args(self, mock_get_project, mock_check_deps):
        """Test shell command with missing arguments."""
        runner = CliRunner()
        result = runner.invoke(cli, ['shell'])
        
        assert result.exit_code != 0
        assert "Missing argument" in result.output
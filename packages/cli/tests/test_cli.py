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
        assert "vscode" in result.output
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
    
    def test_vscode_command_help(self):
        """Test vscode command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['vscode', '--help'])
        
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
    def test_vscode_missing_args(self, mock_get_project, mock_check_deps):
        """Test vscode command with missing arguments."""
        runner = CliRunner()
        result = runner.invoke(cli, ['vscode'])
        
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
    
    def test_claude_command_help(self):
        """Test claude command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['claude', '--help'])

        assert result.exit_code == 0
        assert "Execute Claude CLI in devcontainer or set up authentication" in result.output
        assert "--auth" in result.output
        assert "--api-key" in result.output

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_claude_auth_with_api_key(self, mock_config, mock_subprocess):
        """Test claude --auth command with API key."""
        # Setup mocks
        mock_config.claude_config_dir = '/tmp/test-claude-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.return_value.returncode = 0

        runner = CliRunner()
        result = runner.invoke(cli, ['claude', '--auth', '--api-key', 'test-key-123'])

        assert result.exit_code == 0
        assert "Setting up Claude authentication" in result.output
        assert "Claude authentication configured successfully" in result.output

        # Verify subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert 'claude' in call_args[0][0]
        assert 'auth' in call_args[0][0]
        assert '--key' in call_args[0][0]
        assert 'test-key-123' in call_args[0][0]

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_claude_auth_interactive(self, mock_config, mock_subprocess):
        """Test claude --auth command in interactive mode."""
        # Setup mocks
        mock_config.claude_config_dir = '/tmp/test-claude-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.return_value.returncode = 0

        runner = CliRunner()
        result = runner.invoke(cli, ['claude', '--auth'])

        assert result.exit_code == 0
        assert "Setting up Claude authentication" in result.output
        assert "Starting interactive authentication" in result.output
        assert "Claude authentication configured successfully" in result.output

        # Verify subprocess was called for interactive auth
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert 'claude' in call_args[0][0]
        assert 'auth' in call_args[0][0]
        assert '--key' not in call_args[0][0]

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_claude_auth_command_not_found(self, mock_config, mock_subprocess):
        """Test claude --auth when claude CLI is not installed."""
        # Setup mocks
        mock_config.claude_config_dir = '/tmp/test-claude-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.side_effect = FileNotFoundError()

        runner = CliRunner()
        result = runner.invoke(cli, ['claude', '--auth'])

        assert result.exit_code == 1
        assert "Claude CLI not found" in result.output
        assert "npm install -g @anthropic-ai/claude-cli" in result.output

    def test_claude_missing_args(self):
        """Test claude command without required args (not using --auth)."""
        runner = CliRunner()
        result = runner.invoke(cli, ['claude'])

        assert result.exit_code != 0
        assert "DEV_NAME and PROMPT are required unless using --auth" in result.output

    def test_codex_command_help(self):
        """Test codex command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['codex', '--help'])

        assert result.exit_code == 0
        assert "Execute OpenAI Codex CLI in devcontainer or set up authentication" in result.output
        assert "--auth" in result.output
        assert "--api-key" in result.output

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_codex_auth_with_api_key(self, mock_config, mock_subprocess):
        """Test codex --auth command with API key."""
        # Setup mocks
        mock_config.codex_config_dir = '/tmp/test-codex-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.return_value.returncode = 0

        runner = CliRunner()
        result = runner.invoke(cli, ['codex', '--auth', '--api-key', 'test-key-123'])

        assert result.exit_code == 0
        assert "Setting up Codex authentication" in result.output
        assert "Codex authentication configured successfully" in result.output

        # Verify subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert 'codex' in call_args[0][0]
        assert 'auth' in call_args[0][0]
        assert '--api-key' in call_args[0][0]
        assert 'test-key-123' in call_args[0][0]

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_codex_auth_interactive(self, mock_config, mock_subprocess):
        """Test codex --auth command in interactive mode."""
        # Setup mocks
        mock_config.codex_config_dir = '/tmp/test-codex-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.return_value.returncode = 0

        runner = CliRunner()
        result = runner.invoke(cli, ['codex', '--auth'])

        assert result.exit_code == 0
        assert "Setting up Codex authentication" in result.output
        assert "Starting interactive authentication" in result.output
        assert "Codex authentication configured successfully" in result.output

        # Verify subprocess was called for interactive auth
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert 'codex' in call_args[0][0]
        assert 'auth' in call_args[0][0]
        assert '--api-key' not in call_args[0][0]

    @patch('devs.cli.subprocess.run')
    @patch('devs.cli.config')
    def test_codex_auth_command_not_found(self, mock_config, mock_subprocess):
        """Test codex --auth when codex CLI is not installed."""
        # Setup mocks
        mock_config.codex_config_dir = '/tmp/test-codex-config'
        mock_config.ensure_directories = Mock()
        mock_subprocess.side_effect = FileNotFoundError()

        runner = CliRunner()
        result = runner.invoke(cli, ['codex', '--auth'])

        assert result.exit_code == 1
        assert "Codex CLI not found" in result.output
        assert "npm install -g @openai/codex" in result.output

    def test_codex_missing_args(self):
        """Test codex command without required args (not using --auth)."""
        runner = CliRunner()
        result = runner.invoke(cli, ['codex'])

        assert result.exit_code != 0
        assert "DEV_NAME and PROMPT are required unless using --auth" in result.output
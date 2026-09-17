"""Tests for the coding agent registry and the commands generated from it."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from devs.cli import cli
from devs_common.agents import AGENTS, get_agent
from devs_common.core.container import ContainerManager


def test_every_registered_agent_has_a_cli_command():
    """Each AgentSpec gets a `devs <name>` command."""
    for name in AGENTS:
        assert name in cli.commands, f"missing `devs {name}` command"


@pytest.mark.parametrize("name", list(AGENTS))
def test_agent_command_help_uses_spec(name):
    result = CliRunner().invoke(cli, [name, '--help'])

    assert result.exit_code == 0
    assert f"Execute {AGENTS[name].description} in devcontainer" in result.output
    assert f"devs {name} sally" in result.output


def test_get_agent_unknown_name():
    with pytest.raises(ValueError, match="Unknown agent 'nope'"):
        get_agent('nope')


@pytest.mark.parametrize("name", list(AGENTS))
def test_exec_agent_runs_spec_command_with_prompt_on_stdin(name, tmp_path):
    # exec_agent only delegates to exec_command, so skip __init__ (which needs Docker)
    manager = ContainerManager.__new__(ContainerManager)
    with patch.object(manager, 'exec_command', return_value=(True, "ok", "", 0)) as exec_command:
        result = manager.exec_agent(name, dev_name='sally', workspace_dir=tmp_path,
                                    prompt='Fix the tests', live=True)

    assert result == (True, "ok", "", 0)
    kwargs = exec_command.call_args.kwargs
    assert kwargs['command'] == AGENTS[name].command
    assert kwargs['stdin_input'] == 'Fix the tests'
    assert kwargs['live'] is True

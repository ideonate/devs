"""Registry of the AI coding agents devs can run inside a devcontainer.

Adding an agent:

1. Install it in ``templates/Dockerfile`` (and add shell aliases next to the others).
2. Add an ``AgentSpec`` to ``AGENTS`` below — this gives ``ContainerManager.exec_agent``.
3. Register its ``devs <name>`` command with ``_add_agent_command`` in the CLI's ``cli.py``.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class AgentSpec:
    """How to run one coding agent non-interactively in a devs container.

    Attributes:
        name: Registry key and CLI subcommand (``devs <name> ...``).
        display_name: Human-readable name used in status messages.
        description: What gets executed, used in help text ("Execute <description> ...").
        command: Shell command run from the container workspace after ``~/.zshrc`` is
            sourced. The prompt is written to its stdin, so the command must read it
            from there and exit when done.
    """

    name: str
    display_name: str
    description: str
    command: str


AGENTS: Dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (
        AgentSpec(
            name="claude",
            display_name="Claude",
            description="Claude CLI",
            command="claude --dangerously-skip-permissions -p",
        ),
        AgentSpec(
            name="codex",
            display_name="Codex",
            description="OpenAI Codex CLI",
            # `--full-auto` was removed from the Codex CLI (passing it now aborts with
            # "unexpected argument"). This is the flag Codex intends for externally
            # sandboxed environments, which a devcontainer is — and it matches the
            # `claude --dangerously-skip-permissions` invocation beside it.
            command="codex --dangerously-bypass-approvals-and-sandbox",
        ),
        AgentSpec(
            name="hermes",
            display_name="Hermes",
            description="Hermes Agent (Nous Research)",
            # `--query-file -` reads the prompt from stdin; `--oneshot` answers and exits
            # rather than seeding an interactive session. `--yolo` skips dangerous-command
            # approvals, like the other agents. `hermes chat` ignores HERMES_INFERENCE_MODEL,
            # so forward it as --model when set; otherwise the model baked into the image's
            # Hermes config is used. Hermes picks OpenRouter from OPENROUTER_API_KEY.
            command=(
                "hermes --yolo chat --oneshot --query-file - "
                "${HERMES_INFERENCE_MODEL:+--model=$HERMES_INFERENCE_MODEL}"
            ),
        ),
    )
}


def get_agent(name: str) -> AgentSpec:
    """Look up an agent by name.

    Raises:
        ValueError: If no agent with that name is registered.
    """
    try:
        return AGENTS[name]
    except KeyError:
        raise ValueError(f"Unknown agent '{name}'. Available: {', '.join(AGENTS)}") from None

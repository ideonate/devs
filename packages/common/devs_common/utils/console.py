"""Console output utilities for devs packages."""

import os
import sys
from typing import Union
from rich.console import Console


class StderrConsole:
    """A console that writes plain text to stderr for webhook mode.

    In webhook mode, stdout is reserved for JSON protocol communication.
    This console writes to stderr instead, which is captured and logged
    via structlog to CloudWatch.
    """

    def print(self, *args, **kwargs):
        """Print to stderr, stripping Rich markup."""
        # Convert args to string, stripping any Rich markup
        message = " ".join(str(arg) for arg in args)
        # Remove common Rich markup patterns
        import re
        message = re.sub(r'\[/?[^\]]+\]', '', message)
        print(message, file=sys.stderr)


def get_console() -> Union[Console, StderrConsole]:
    """Get the appropriate console based on the environment.

    Returns:
        Console: A Rich Console instance for CLI mode
        StderrConsole: A stderr-writing console for webhook mode
    """
    if os.environ.get('DEVS_WEBHOOK_MODE') == '1':
        # In webhook mode, write to stderr (captured by structlog)
        return StderrConsole()
    else:
        # Normal CLI mode - return standard Rich console
        return Console()

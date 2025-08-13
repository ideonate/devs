"""Console output utilities for devs packages."""

import os
from typing import Union
from rich.console import Console


class SilentConsole:
    """A no-op console that suppresses all output."""
    
    def print(self, *args, **kwargs):
        """Suppress all print calls."""
        pass


def get_console() -> Union[Console, SilentConsole]:
    """Get the appropriate console based on the environment.
    
    Returns:
        Console: A Rich Console instance or SilentConsole if in webhook mode
    """
    if os.environ.get('DEVS_WEBHOOK_MODE') == '1':
        # In webhook mode, suppress all console output to avoid corrupting JSON
        return SilentConsole()
    else:
        # Normal mode - return standard Rich console
        return Console()
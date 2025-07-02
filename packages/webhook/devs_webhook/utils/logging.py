"""Logging configuration."""

import sys
import logging
import structlog
from typing import Any, Dict

from ..config import get_config


def setup_logging() -> None:
    """Set up structured logging."""
    config = get_config()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer() if config.log_format == "console" 
            else structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, config.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.WriteLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(**context: Any) -> structlog.BoundLogger:
    """Get a logger with context."""
    return structlog.get_logger().bind(**context)
import logging
import sys
from typing import Any

import structlog

from src.core.config import config

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.MODULE,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FILENAME,
            ]
        ),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
        if not config.app.is_development
        else structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def setup_logging() -> None:
    """Setup logging configuration"""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if config.app.is_development else logging.INFO,
    )
    logging.getLogger("uvicorn").setLevel(
        logging.DEBUG if config.app.is_development else logging.INFO
    )
    logging.getLogger("uvicorn.access").setLevel(
        logging.DEBUG if config.app.is_development else logging.INFO
    )
    logging.getLogger("motor").setLevel(logging.INFO)
    logging.getLogger("pymongo").setLevel(logging.INFO)
    logging.getLogger("pymongo.server").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("LiteLLM").setLevel(logging.INFO)


def get_logger(name: str = __name__) -> Any:
    """Get a logger instance"""
    return structlog.get_logger(name)


# Convenience function for backward compatibility
def logger(name: str = __name__) -> Any:
    """Get a logger instance (alias for get_logger)"""
    return structlog.get_logger(name)

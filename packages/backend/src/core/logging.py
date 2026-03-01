import logging
import sys
from typing import Any

import structlog

from src.core.config import config


def component_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Injects [component]: prefix if component is present in context."""
    component = event_dict.get("component")
    if component:
        event_dict["event"] = f"[{component}]: {event_dict['event']}"
    return event_dict


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
        component_processor,
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


def get_logger(name: str = __name__, component: str | None = None) -> Any:
    """Get a logger instance with optional component context."""
    logger = structlog.get_logger(name)
    if component:
        return logger.bind(component=component)
    return logger


# Convenience function for backward compatibility
def logger(name: str = __name__, component: str | None = None) -> Any:
    """Get a logger instance (alias for get_logger)"""
    return get_logger(name, component)

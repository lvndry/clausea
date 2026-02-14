"""Cancellation utilities for interrupting long-running operations."""

import asyncio
import signal
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)


class CancellationToken:
    """A cancellation token that can be used to interrupt async operations."""

    def __init__(self) -> None:
        self.cancelled = asyncio.Event()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Mark the token as cancelled."""
        if not self._is_cancelled:
            self._is_cancelled = True
            self.cancelled.set()
            logger.info("Cancellation token set - operations will be interrupted")

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._is_cancelled

    async def wait_if_cancelled(self) -> None:
        """Wait if cancelled, raising CancelledError."""
        if self._is_cancelled:
            raise asyncio.CancelledError("Operation cancelled")

    async def check_cancellation(self) -> None:
        """Check for cancellation and raise if cancelled."""
        if self.cancelled.is_set():
            raise asyncio.CancelledError("Operation cancelled")


# Global cancellation token for signal-based cancellation
_global_cancellation_token: CancellationToken | None = None


def get_global_cancellation_token() -> CancellationToken:
    """Get or create the global cancellation token."""
    global _global_cancellation_token
    if _global_cancellation_token is None:
        _global_cancellation_token = CancellationToken()
        _setup_signal_handlers()
    return _global_cancellation_token


def _setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle interrupt signals."""
        logger.info(f"Received signal {signum}, cancelling operations...")
        if _global_cancellation_token:
            _global_cancellation_token.cancel()

    try:
        # Register handlers for common interrupt signals
        # Note: signal handlers can only be set in the main thread
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except ValueError:
        # Signal handlers can only be set in the main thread
        # This is fine if called from a non-main thread
        logger.debug("Could not set signal handlers (not in main thread)")


async def cancellable_acompletion(
    acompletion_func: Any,
    cancellation_token: CancellationToken | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Wrap an async completion call to make it cancellable.

    Args:
        acompletion_func: The async completion function to wrap
        cancellation_token: Optional cancellation token. If None, uses global token.
        *args: Positional arguments for acompletion_func
        **kwargs: Keyword arguments for acompletion_func

    Returns:
        Result from acompletion_func

    Raises:
        asyncio.CancelledError: If cancellation is requested
    """
    token = cancellation_token or get_global_cancellation_token()

    # Check for cancellation before starting
    await token.check_cancellation()

    # Create a task that can be cancelled
    task = asyncio.create_task(acompletion_func(*args, **kwargs))

    try:
        # Wait for either completion or cancellation
        _, pending = await asyncio.wait(
            [task, asyncio.create_task(token.cancelled.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for p in pending:
            p.cancel()
            try:
                await p
            except asyncio.CancelledError:
                pass

        # If cancellation was requested, cancel the main task
        if token.is_cancelled():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise asyncio.CancelledError("LLM call cancelled")

        # Return the result
        return await task

    except asyncio.CancelledError:
        # Re-raise cancellation errors
        raise
    except Exception:
        # Cancel task on any other error
        if not task.done():
            task.cancel()
        raise

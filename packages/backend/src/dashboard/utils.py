import asyncio
import concurrent.futures
import os
import warnings
from collections.abc import Callable, Coroutine, Generator
from contextlib import contextmanager
from typing import Any, TypeVar

import httpx
import streamlit as st

from src.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@contextmanager
def suppress_streamlit_warnings() -> Generator[None, None, None]:
    """Context manager to suppress Streamlit ScriptRunContext warnings in worker threads."""
    warnings.filterwarnings("ignore", message="missing ScriptRunContext")
    try:
        yield
    finally:
        # Restore warnings if needed
        warnings.filterwarnings("default", message="missing ScriptRunContext")


def run_async(coro: Coroutine[None, None, T], timeout: int | None = 30) -> T | None:
    """Run async function in a completely isolated thread with its own event loop.

    This is a simple, robust implementation that ensures the event loop stays
    open for the entire duration of the coroutine execution.

    Args:
        coro: The coroutine to run
        timeout: Timeout in seconds (None for no timeout). Default is 30 seconds.

    Returns:
        The result of the coroutine with its original type preserved, or None if an error occurs
    """

    def run_in_thread() -> T | None:
        with suppress_streamlit_warnings():
            # Create a fresh event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Run the coroutine - this blocks until it completes
                result = loop.run_until_complete(coro)
                return result
            except Exception as e:
                logger.error(f"Error in async operation: {e}", exc_info=True)
                return None
            finally:
                # Simple cleanup: wait a moment for any final operations, then close
                try:
                    # Give any pending operations a moment to complete
                    if not loop.is_closed():
                        # Wait for any remaining tasks
                        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        if pending:
                            try:
                                loop.run_until_complete(
                                    asyncio.gather(*pending, return_exceptions=True)
                                )
                            except Exception:
                                pass  # Ignore errors during cleanup

                        # Shutdown async generators
                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except Exception:
                            pass

                        # Small delay to let executor tasks finish
                        try:
                            loop.run_until_complete(asyncio.sleep(0.1))
                        except Exception:
                            pass

                        # Close the loop
                        if not loop.is_closed():
                            loop.close()
                except Exception as e:
                    logger.debug(f"Error during loop cleanup: {e}")

    # Run in a separate thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        try:
            return future.result(timeout=timeout) if timeout else future.result()
        except concurrent.futures.TimeoutError:
            st.error(f"Operation timed out after {timeout} seconds. Please try again.")
            return None
        except Exception as e:
            logger.error(f"Error executing async operation: {str(e)}")
            st.error(f"Error: {str(e)}")
            return None


def run_async_with_retry(coro: Coroutine[None, None, T], max_retries: int = 3) -> T | None:
    """Run async function with retry logic for better reliability

    Args:
        coro: The coroutine to run
        max_retries: Maximum number of retry attempts

    Returns:
        The result of the coroutine, or None if all retries fail
    """
    for attempt in range(max_retries):
        try:
            result = run_async(coro)
            if result is not None:
                return result
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                st.error(f"Failed after {max_retries} attempts: {str(e)}")
            else:
                st.warning(f"Attempt {attempt + 1} failed, retrying...")
                import time

                time.sleep(1)  # Brief delay before retry

    return None


def run_in_thread_with_warning_suppression(
    func: Callable[..., Any], *args: Any, **kwargs: Any
) -> Any:
    """Run a function in a separate thread with Streamlit warning suppression

    Args:
        func: The function to run
        *args: Arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function
    """

    def run_in_thread() -> Any:
        with suppress_streamlit_warnings():
            return func(*args, **kwargs)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        try:
            return future.result()
        except Exception as e:
            logger.error(f"Error in threaded operation: {e}")
            return None


def get_streamlit_api_headers() -> dict[str, str]:
    """Get HTTP headers for Streamlit API requests, including service API key if configured

    Returns:
        Dictionary of headers to include in API requests
    """
    headers: dict[str, str] = {}
    service_api_key = os.getenv("SERVICE_API_KEY")
    if service_api_key:
        headers["X-CLAUSEA-API-KEY"] = service_api_key
    return headers


def get_streamlit_client_session() -> httpx.AsyncClient:
    """Create an httpx AsyncClient with Streamlit API headers pre-configured

    This ensures all API requests from Streamlit include the service API key header
    when configured. Use this instead of creating AsyncClient directly.

    Returns:
        Configured httpx.AsyncClient instance

    Example:
        async with get_streamlit_client_session() as client:
            response = await client.get(url)
            data = response.json()
    """
    headers = get_streamlit_api_headers()
    return httpx.AsyncClient(headers=headers)


async def make_api_request(
    url: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    """Make async HTTP requests with automatic API key handling

    This helper function automatically includes the service API key header
    (if configured) for all API requests from Streamlit.

    Args:
        url: The full URL to make the request to
        method: HTTP method (GET, POST, etc.)
        data: Optional JSON data to send with POST requests

    Returns:
        Tuple of (response_json, status_code)

    Example:
        result, status = await make_api_request("http://localhost:8000/api/endpoint")
        result, status = await make_api_request("http://localhost:8000/api/endpoint", "POST", {"key": "value"})
    """
    async with get_streamlit_client_session() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(url)
                return response.json(), response.status_code
            elif method.upper() == "POST":
                response = await client.post(url, json=data)
                return response.json(), response.status_code
            else:
                return {"error": f"Unsupported method: {method}"}, 400
        except Exception as e:
            return {"error": str(e)}, 500

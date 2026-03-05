"""
Shared async runtime for Streamlit sync code.

Streamlit scripts rerun often. Recreating/closing event loops per call causes
asyncpg/SQLAlchemy loop-affinity errors. This module keeps one background loop
alive and executes coroutines on it safely.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

from bots.shared.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

_runtime_loop: asyncio.AbstractEventLoop | None = None
_runtime_thread: threading.Thread | None = None
_runtime_lock = threading.Lock()


def _loop_thread_runner(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_runtime_loop() -> asyncio.AbstractEventLoop:
    global _runtime_loop, _runtime_thread

    with _runtime_lock:
        if _runtime_loop and _runtime_loop.is_running():
            return _runtime_loop

        loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=_loop_thread_runner,
            args=(loop,),
            name="streamlit-async-runtime",
            daemon=True,
        )
        thread.start()

        _runtime_loop = loop
        _runtime_thread = thread
        logger.info("Started shared Streamlit async runtime loop")
        return loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run a coroutine on the shared background event loop and return its result.
    """
    loop = _ensure_runtime_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

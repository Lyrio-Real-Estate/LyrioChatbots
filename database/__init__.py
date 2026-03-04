"""Database package exports.

Session-related exports are resolved lazily so tooling (e.g., Alembic)
can import ``database`` without requiring full application settings.
"""

from __future__ import annotations

from database import models  # noqa: F401
from database.base import Base

__all__ = ["Base", "async_engine", "AsyncSessionFactory", "get_async_session", "models"]


def __getattr__(name: str):
    if name in {"AsyncSessionFactory", "async_engine", "get_async_session"}:
        from database import session as _session

        return getattr(_session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

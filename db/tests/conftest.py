"""Pytest configuration: put the project root on sys.path for ``import db``."""

from __future__ import annotations

import pathlib
import sys

import pytest

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only (no trio dependency)."""
    return "asyncio"

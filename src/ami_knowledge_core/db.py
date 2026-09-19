"""PostgreSQL connection helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


@contextmanager
def connect(*, row_factory: Any = dict_row) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(database_url(), row_factory=row_factory) as connection:
        yield connection


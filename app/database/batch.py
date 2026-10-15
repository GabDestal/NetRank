"""Batched writes for bulk loading."""

from collections.abc import Sequence
from typing import Any

from neo4j import Driver

DEFAULT_BATCH_SIZE = 1000


def run_batched(driver: Driver, query: str, rows: Sequence[dict[str, Any]],
                batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Run an `UNWIND $rows AS row ...` query over rows, one transaction per batch.

    Batching keeps each transaction's memory bounded and sends one round trip per batch
    instead of one per row. Returns the number of rows sent.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    for start in range(0, len(rows), batch_size):
        driver.execute_query(query, {"rows": list(rows[start:start + batch_size])})
    return len(rows)

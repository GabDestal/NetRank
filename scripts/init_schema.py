"""Create the graph's constraints and indexes in Neo4j, then check they all exist.

Safe to run repeatedly: every statement uses IF NOT EXISTS.

Usage:
    python -m scripts.init_schema
"""

import logging

from neo4j import Driver

from app.database.schema import SCHEMA, apply_schema, missing_schema
from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("init_schema")


def _apply_and_check(driver: Driver) -> list[str]:
    apply_schema(driver)
    return missing_schema(driver)


def main() -> int:
    """Apply the schema and verify it. Returns a process exit code."""
    setup_logging()
    missing = run_with_driver(_apply_and_check, LOGGER)
    if missing is None:
        return 1
    if missing:
        LOGGER.error("schema items missing after apply: %s", ", ".join(missing))
        return 1
    for item in SCHEMA:
        LOGGER.info("%-10s %s", item.kind, item.name)
    LOGGER.info("schema ready: %d constraints and indexes", len(SCHEMA))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

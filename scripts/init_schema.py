"""Create the graph's constraints and indexes in Neo4j, then check they all exist.

Safe to run repeatedly: every statement uses IF NOT EXISTS.

Usage:
    python -m scripts.init_schema
"""

import logging

from neo4j.exceptions import DriverError, Neo4jError

from app.config import load_settings
from app.database.connection import close_driver, get_driver
from app.database.schema import SCHEMA, apply_schema, missing_schema

LOGGER = logging.getLogger("init_schema")


def main() -> int:
    """Apply the schema and verify it. Returns a process exit code."""
    logging.basicConfig(level=load_settings().log_level, format="%(asctime)s %(levelname)s %(message)s")
    driver = get_driver()
    try:
        apply_schema(driver)
        missing = missing_schema(driver)
    except (DriverError, Neo4jError) as exc:
        LOGGER.error("Neo4j error: %s", exc)
        return 1
    finally:
        close_driver()
    if missing:
        LOGGER.error("schema items missing after apply: %s", ", ".join(missing))
        return 1
    for item in SCHEMA:
        LOGGER.info("%-10s %s", item.kind, item.name)
    LOGGER.info("schema ready: %d constraints and indexes", len(SCHEMA))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

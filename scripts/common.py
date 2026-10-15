"""Helpers shared by the command-line scripts."""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from app.config import Settings, load_settings
from app.database.connection import close_driver, get_driver

T = TypeVar("T")

# One :ImportMeta node per source (D2), found through its uniqueness constraint: O(log n).
IMPORT_META_QUERY = (
    "MERGE (m:ImportMeta {source: $source}) "
    "SET m.version = $version, m.file = $file, m.sha256 = $sha256, m.imported_at = datetime()"
)


def read_manifest(raw_dir: Path) -> dict[str, Any]:
    """Return data/raw/manifest.json written by scripts.download, or {} if there is none."""
    path = raw_dir / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def record_import(driver: Driver, source: str, entry: dict[str, Any]) -> None:
    """Create or update the :ImportMeta node for source from its download manifest entry."""
    driver.execute_query(IMPORT_META_QUERY, {
        "source": source,
        "version": entry.get("version"),
        "file": entry.get("file"),
        "sha256": entry.get("sha256"),
    })


def check_counts(expected: dict[str, int], actual: dict[str, int], logger: logging.Logger) -> bool:
    """Log the graph's counts and return True if every expected count matches."""
    for name, count in expected.items():
        logger.info("%-16s %6d", name, actual.get(name, 0))
    mismatches = {name: (count, actual.get(name)) for name, count in expected.items() if actual.get(name) != count}
    if mismatches:
        logger.error("count mismatch (expected, in graph): %s", mismatches)
    return not mismatches


def setup_logging() -> Settings:
    """Configure logging from the settings and return them."""
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    return settings


def run_with_driver(work: Callable[[Driver], T], logger: logging.Logger) -> T | None:
    """Run work with the shared Neo4j driver and close it afterwards.

    Returns work's result, or None after logging the error if Neo4j is unreachable or rejects a query.
    """
    driver = get_driver()
    try:
        return work(driver)
    except (DriverError, Neo4jError) as exc:
        logger.error("Neo4j error: %s", exc)
        return None
    finally:
        close_driver()

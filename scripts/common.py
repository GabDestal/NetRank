"""Helpers shared by the command-line scripts."""

import logging
from collections.abc import Callable
from typing import TypeVar

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from app.config import Settings, load_settings
from app.database.connection import close_driver, get_driver

T = TypeVar("T")


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

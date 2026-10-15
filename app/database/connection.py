"""Neo4j driver lifecycle.

One driver per process: it owns a connection pool and is thread-safe, so the API and the
scripts share a single instance instead of opening a connection per request.
"""

import threading

from neo4j import Driver, GraphDatabase

from app.config import load_settings

_LOCK = threading.Lock()
_STATE: dict[str, Driver] = {}


def get_driver() -> Driver:
    """Return the process-wide Neo4j driver, creating it on first use.

    Creating the driver does not connect yet; the first query does.
    """
    with _LOCK:
        if "driver" not in _STATE:
            settings = load_settings()
            # Server notices such as "constraint already exists" are informational: report warnings and above.
            # "Unrecognized" warnings are off too: queries that look for INFERRED_MAPS_TO legitimately run
            # before any suggestion exists (D18), and would otherwise log a warning on every request.
            _STATE["driver"] = GraphDatabase.driver(settings.neo4j_uri,
                                                    auth=(settings.neo4j_user, settings.neo4j_password),
                                                    notifications_min_severity="WARNING",
                                                    notifications_disabled_categories=["UNRECOGNIZED"])
        return _STATE["driver"]


def close_driver() -> None:
    """Close the process-wide driver if one was created."""
    with _LOCK:
        driver = _STATE.pop("driver", None)
    if driver is not None:
        driver.close()

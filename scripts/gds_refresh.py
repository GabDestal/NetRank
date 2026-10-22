"""Run the GDS refresh from the command line (same work as POST /api/admin/gds/refresh).

Usage: python -m scripts.gds_refresh   (after make ingest; needs the GDS plugin)
"""

import json
import logging

from app.config import get_settings
from app.database.client import Neo4jClient
from app.services import gds


def main() -> None:
    """Recompute prestige, style vectors, SIMILAR_STYLE and styles, and print the report."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = Neo4jClient.from_settings(get_settings())
    try:
        print(json.dumps(gds.refresh(db), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()

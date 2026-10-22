"""Download Jeff Sackmann's ATP data at a pinned commit and verify every file.

Upstream `JeffSackmann/tennis_atp` was removed from GitHub in 2026. Its last commit,
712be0c5 ("thru 8 jun 2026"), survives unchanged in many forks. A Git commit hash covers the
whole tree, so fetching that exact commit from any fork returns the upstream bytes; each file is
also checked against its Git blob hash from the tree listing.

Licence: CC BY-NC-SA 4.0 (attribution: Jeff Sackmann / Tennis Abstract).

Usage: python -m scripts.download_sackmann [--first-year 1991] [--force]
"""

import argparse
import hashlib
import json
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

COMMIT = "712be0c5ade693cdab9e69c23a71a0edf5a23c44"
MIRROR = "Kadantte/tennis_atp"
TREE_URL = f"https://api.github.com/repos/{MIRROR}/git/trees/{COMMIT}"
RAW_URL = f"https://raw.githubusercontent.com/{MIRROR}/{COMMIT}/{{path}}"
LAST_YEAR = 2026
DEST = Path("data/raw/sackmann")
EXTRA_FILES = ("atp_players.csv", "matches_data_dictionary.txt", "README.md")

log = logging.getLogger(__name__)


def git_blob_sha(content: bytes) -> str:
    """Hash bytes the way Git hashes a blob: sha1(b"blob <len>\\0" + content)."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


def wanted_files(first_year: int) -> list[str]:
    """Yearly tour-level match files from `first_year` to the last year, plus players and docs."""
    return [f"atp_matches_{year}.csv" for year in range(first_year, LAST_YEAR + 1)] + list(EXTRA_FILES)


def fetch(url: str) -> bytes:
    """GET a URL and return the body (raises on HTTP errors)."""
    request = urllib.request.Request(url, headers={"User-Agent": "netrank-course-project"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def expected_hashes() -> dict[str, str]:
    """Map each path at the pinned commit to its Git blob hash."""
    tree = json.loads(fetch(TREE_URL))
    return {entry["path"]: entry["sha"] for entry in tree["tree"] if entry["type"] == "blob"}


def download(first_year: int, force: bool) -> list[dict]:
    """Download missing (or all, with force) files, verify them, and return manifest entries."""
    DEST.mkdir(parents=True, exist_ok=True)
    hashes = expected_hashes()
    entries = []
    for path in wanted_files(first_year):
        target = DEST / path
        if force or not target.exists() or git_blob_sha(target.read_bytes()) != hashes[path]:
            log.info(f"downloading {path}")
            target.write_bytes(fetch(RAW_URL.format(path=path)))
        content = target.read_bytes()
        if git_blob_sha(content) != hashes[path]:
            raise ValueError(f"{path}: content does not match commit {COMMIT[:8]}")
        entries.append({"file": path, "bytes": len(content), "git_blob_sha": hashes[path]})
    return entries


def main() -> None:
    """CLI entry point: download, verify, and write data/raw/sackmann/manifest.json."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first-year", type=int, default=1991)
    parser.add_argument("--force", action="store_true", help="re-download files already present")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = download(args.first_year, args.force)
    manifest = {
        "source": "Jeff Sackmann tennis_atp (CC BY-NC-SA 4.0)",
        "mirror": MIRROR,
        "commit": COMMIT,
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
    }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info(f"{len(files)} files verified against commit {COMMIT[:8]}")


if __name__ == "__main__":
    main()

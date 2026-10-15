"""Download the raw source datasets into data/raw/.

Sources, pinned wherever the publisher offers versions:

- attack: MITRE ATT&CK Enterprise 20.0 (STIX 2.1 bundle)
- kev:    CISA Known Exploited Vulnerabilities catalog (latest; its catalogVersion is recorded)
- ctid:   CTID Mappings Explorer, KEV -> ATT&CK 16.1 (mapping file kev-07.28.2025)
- nvd:    NVD API 2.0 records for every CVE in KEV

Every download is validated before it is kept, and recorded in data/raw/manifest.json
(url, version, sha256, size, time) so the import can cite exactly what it loaded.
Files that already exist are skipped unless --force is given.

Usage:
    python -m scripts.download                 # everything
    python -m scripts.download --only kev nvd  # selected sources
    python -m scripts.download --force         # re-download
"""

import argparse
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import load_settings

LOGGER = logging.getLogger("download")

ATTACK_VERSION = "20.0"
CTID_ATTACK_VERSION = "16.1"


@dataclass(frozen=True)
class Source:
    """A dataset published as a single JSON file."""

    name: str
    url: str
    filename: str


ATTACK = Source(
    "attack",
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/"
    f"enterprise-attack-{ATTACK_VERSION}.json",
    f"enterprise-attack-{ATTACK_VERSION}.json",
)
KEV = Source(
    "kev",
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "known_exploited_vulnerabilities.json",
)
CTID = Source(
    "ctid",
    "https://raw.githubusercontent.com/center-for-threat-informed-defense/mappings-explorer/main/mappings/kev/"
    "attack-16.1/kev-07.28.2025/enterprise/kev-07.28.2025_attack-16.1-enterprise.json",
    "kev-07.28.2025_attack-16.1-enterprise.json",
)

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_FILENAME = "nvd_kev_cves.json"
NVD_PAGE_SIZE = 500
# NVD allows 50 requests per rolling 30 s with an API key and 5 without one.
NVD_DELAY_WITH_KEY = 0.6
NVD_DELAY_WITHOUT_KEY = 6.0

# NVD answers 403 (not 429) when a client exceeds its rate limit.
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 2.0

ALL_SOURCES = ("attack", "kev", "ctid", "nvd")

Sleep = Callable[[float], None]


class DownloadError(RuntimeError):
    """A download failed, or its content is not what the import expects."""


def get_with_retry(client: httpx.Client, url: str, *, headers: dict[str, str] | None = None,
                   sleep: Sleep = time.sleep) -> httpx.Response:
    """GET url, retrying rate-limit and server errors with exponential backoff."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, headers=headers)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS:
                raise DownloadError(f"{url}: {exc}") from exc
            LOGGER.warning("%s: %s (attempt %d/%d)", url, exc, attempt, MAX_ATTEMPTS)
        else:
            if response.status_code == 200:
                return response
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise DownloadError(f"{url}: HTTP {response.status_code}")
            LOGGER.warning("%s: HTTP %d (attempt %d/%d)", url, response.status_code, attempt, MAX_ATTEMPTS)
        sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
    raise DownloadError(f"{url}: no attempts made")  # unreachable: MAX_ATTEMPTS >= 1


def validate_attack(data: dict[str, Any]) -> str:
    """Check an ATT&CK bundle is the pinned Enterprise version and return that version."""
    if data.get("type") != "bundle":
        raise DownloadError("attack: not a STIX bundle")
    collections = [o for o in data.get("objects", []) if o.get("type") == "x-mitre-collection"]
    version = collections[0].get("x_mitre_version") if collections else None
    if version != ATTACK_VERSION:
        raise DownloadError(f"attack: expected version {ATTACK_VERSION}, got {version}")
    return version


def validate_kev(data: dict[str, Any]) -> str:
    """Check a KEV catalog has vulnerabilities and return its catalog version."""
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or not vulnerabilities:
        raise DownloadError("kev: no vulnerabilities in catalog")
    if any("cveID" not in v for v in vulnerabilities):
        raise DownloadError("kev: entry without cveID")
    return str(data.get("catalogVersion", "unknown"))


def validate_ctid(data: dict[str, Any]) -> str:
    """Check a CTID mapping file targets the expected ATT&CK version and return it."""
    version = data.get("metadata", {}).get("attack_version")
    if version != CTID_ATTACK_VERSION:
        raise DownloadError(f"ctid: expected ATT&CK {CTID_ATTACK_VERSION}, got {version}")
    if not data.get("mapping_objects"):
        raise DownloadError("ctid: no mapping objects")
    return version


VALIDATORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "attack": validate_attack,
    "kev": validate_kev,
    "ctid": validate_ctid,
}


def write_atomic(path: Path, content: bytes) -> None:
    """Write content to path via a temporary file, so a failed run never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(path)


def manifest_entry(url: str, path: Path, version: str, **extra: Any) -> dict[str, Any]:
    """Describe one downloaded file for the manifest."""
    content = path.read_bytes()
    return {
        "url": url,
        "file": path.name,
        "version": version,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **extra,
    }


def update_manifest(raw_dir: Path, name: str, entry: dict[str, Any]) -> None:
    """Record entry under name in raw_dir/manifest.json."""
    path = raw_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest[name] = entry
    write_atomic(path, json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))


def download_file(client: httpx.Client, source: Source, raw_dir: Path, *, force: bool = False,
                  sleep: Sleep = time.sleep) -> Path:
    """Download, validate and record one single-file source. Returns its path."""
    path = raw_dir / source.name / source.filename
    if path.exists() and not force:
        LOGGER.info("%s: %s already present, skipping (use --force to refresh)", source.name, path)
        return path
    LOGGER.info("%s: downloading %s", source.name, source.url)
    response = get_with_retry(client, source.url, sleep=sleep)
    try:
        data = response.json()
    except ValueError as exc:
        raise DownloadError(f"{source.name}: response is not JSON") from exc
    version = VALIDATORS[source.name](data)
    write_atomic(path, response.content)
    update_manifest(raw_dir, source.name, manifest_entry(source.url, path, version))
    LOGGER.info("%s: saved %s (version %s, %d bytes)", source.name, path, version, len(response.content))
    return path


def kev_cve_ids(kev_path: Path) -> set[str]:
    """Return the CVE ids listed in a downloaded KEV catalog."""
    data = json.loads(kev_path.read_text(encoding="utf-8"))
    return {v["cveID"] for v in data["vulnerabilities"]}


def _fetch_nvd_has_kev(client: httpx.Client, headers: dict[str, str], page_size: int, delay: float,
                       sleep: Sleep) -> dict[str, dict[str, Any]]:
    """Page through every CVE NVD flags as being in KEV. Returns them keyed by CVE id."""
    found: dict[str, dict[str, Any]] = {}
    start, total = 0, None
    while total is None or start < total:
        url = f"{NVD_API_URL}?hasKev&resultsPerPage={page_size}&startIndex={start}"
        page = get_with_retry(client, url, headers=headers, sleep=sleep).json()
        total = page["totalResults"]
        found.update((item["cve"]["id"], item["cve"]) for item in page["vulnerabilities"])
        LOGGER.info("nvd: %d/%d CVEs flagged hasKev", min(start + page_size, total), total)
        start += page_size
        sleep(delay)
    return found


def fetch_nvd_kev(client: httpx.Client, api_key: str, kev_ids: Iterable[str], *,
                  page_size: int = NVD_PAGE_SIZE, sleep: Sleep = time.sleep) -> list[dict[str, Any]]:
    """Fetch NVD records for the given KEV CVEs.

    Pages through NVD's hasKev filter first, then fetches any KEV CVE that NVD did not flag
    one by one. Only CVEs in kev_ids are returned, sorted by id.
    """
    wanted = set(kev_ids)
    headers = {"apiKey": api_key} if api_key else {}
    delay = NVD_DELAY_WITH_KEY if api_key else NVD_DELAY_WITHOUT_KEY
    found = _fetch_nvd_has_kev(client, headers, page_size, delay, sleep)

    extra = sorted(set(found) - wanted)
    if extra:
        LOGGER.info("nvd: ignoring %d CVEs flagged hasKev but not in this KEV catalog: %s", len(extra), extra)
    for cve_id in sorted(wanted - set(found)):
        LOGGER.info("nvd: %s not flagged hasKev, fetching it directly", cve_id)
        page = get_with_retry(client, f"{NVD_API_URL}?cveId={cve_id}", headers=headers, sleep=sleep).json()
        found.update((item["cve"]["id"], item["cve"]) for item in page["vulnerabilities"])
        sleep(delay)

    still_missing = sorted(wanted - set(found))
    if still_missing:
        LOGGER.warning("nvd: %d KEV CVEs have no NVD record: %s", len(still_missing), still_missing)
    return [found[cve_id] for cve_id in sorted(wanted & set(found))]


def download_nvd(client: httpx.Client, raw_dir: Path, api_key: str, *, force: bool = False,
                 sleep: Sleep = time.sleep) -> Path:
    """Download NVD records for every CVE in the downloaded KEV catalog. Returns their path."""
    path = raw_dir / "nvd" / NVD_FILENAME
    if path.exists() and not force:
        LOGGER.info("nvd: %s already present, skipping (use --force to refresh)", path)
        return path
    kev_path = raw_dir / KEV.name / KEV.filename
    if not kev_path.exists():
        raise DownloadError("nvd: download kev first, NVD records are fetched for KEV CVEs only")
    if not api_key:
        LOGGER.warning("nvd: NVD_API_KEY is not set, requests are limited to 5 per 30 s")
    cves = fetch_nvd_kev(client, api_key, kev_cve_ids(kev_path), sleep=sleep)
    write_atomic(path, json.dumps({"cves": cves}).encode("utf-8"))
    retrieved = datetime.now(timezone.utc).date().isoformat()
    update_manifest(raw_dir, "nvd", manifest_entry(f"{NVD_API_URL}?hasKev", path, retrieved, cve_count=len(cves)))
    LOGGER.info("nvd: saved %d CVE records to %s", len(cves), path)
    return path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Download ThreatGraph source datasets into data/raw/.")
    parser.add_argument("--only", nargs="+", choices=ALL_SOURCES, default=list(ALL_SOURCES),
                        help="sources to download (default: all)")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    """Run the downloads. Returns a process exit code."""
    args = parse_args(argv)
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    raw_dir = settings.raw_dir
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(120.0), follow_redirects=True)
    try:
        for source in (ATTACK, KEV, CTID):
            if source.name in args.only:
                download_file(client, source, raw_dir, force=args.force, sleep=time.sleep)
        if "nvd" in args.only:
            download_nvd(client, raw_dir, settings.nvd_api_key, force=args.force, sleep=time.sleep)
    except DownloadError as exc:
        LOGGER.error("%s", exc)
        return 1
    finally:
        if own_client:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

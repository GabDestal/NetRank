"""Tests for scripts.download. All HTTP traffic goes to an in-process mock transport."""
# pylint: disable=missing-function-docstring

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from scripts import download
from scripts.download import DownloadError

ATTACK_BUNDLE = {
    "type": "bundle",
    "objects": [{"type": "x-mitre-collection", "x_mitre_version": download.ATTACK_VERSION}],
}
KEV_CATALOG = {
    "catalogVersion": "2026.10.14",
    "vulnerabilities": [{"cveID": "CVE-2024-0001"}, {"cveID": "CVE-2024-0002"}, {"cveID": "CVE-2024-0003"}],
}
CTID_FILE = {
    "metadata": {"attack_version": download.CTID_ATTACK_VERSION},
    "mapping_objects": [{"capability_id": "CVE-2024-0001", "attack_object_id": "T1190"}],
}


def no_sleep(_seconds):
    return None


def nvd_page(ids, total):
    return {"totalResults": total, "vulnerabilities": [{"cve": {"id": i}} for i in ids]}


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def static_handler(calls):
    """Serve the three single-file sources and NVD, recording every request."""

    def handler(request):
        calls.append(request)
        url = str(request.url)
        if url == download.ATTACK.url:
            return httpx.Response(200, json=ATTACK_BUNDLE)
        if url == download.KEV.url:
            return httpx.Response(200, json=KEV_CATALOG)
        if url == download.CTID.url:
            return httpx.Response(200, json=CTID_FILE)
        if url.startswith(download.NVD_API_URL):
            return httpx.Response(200, json=nvd_page(["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003"], 3))
        return httpx.Response(404)

    return handler


def test_get_with_retry_retries_then_succeeds():
    responses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, json={})])
    sleeps = []
    with make_client(lambda request: next(responses)) as client:
        response = download.get_with_retry(client, "https://example.test/x", sleep=sleeps.append)
    assert response.status_code == 200
    assert sleeps == [download.BACKOFF_SECONDS, download.BACKOFF_SECONDS * 2]


def test_get_with_retry_gives_up_after_max_attempts():
    with make_client(lambda request: httpx.Response(503)) as client:
        with pytest.raises(DownloadError, match="HTTP 503"):
            download.get_with_retry(client, "https://example.test/x", sleep=no_sleep)


def test_get_with_retry_does_not_retry_client_errors():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    with make_client(handler) as client:
        with pytest.raises(DownloadError, match="HTTP 404"):
            download.get_with_retry(client, "https://example.test/x", sleep=no_sleep)
    assert len(calls) == 1


def test_get_with_retry_retries_transport_errors():
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    with make_client(handler) as client:
        assert download.get_with_retry(client, "https://example.test/x", sleep=no_sleep).status_code == 200


def test_get_with_retry_transport_error_on_last_attempt():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    with make_client(handler) as client:
        with pytest.raises(DownloadError, match="down"):
            download.get_with_retry(client, "https://example.test/x", sleep=no_sleep)


@pytest.mark.parametrize(
    "validator, data, message",
    [
        (download.validate_attack, {"type": "x"}, "not a STIX bundle"),
        (download.validate_attack, {"type": "bundle", "objects": []}, "expected version"),
        (download.validate_kev, {"vulnerabilities": []}, "no vulnerabilities"),
        (download.validate_kev, {"vulnerabilities": [{"x": 1}]}, "without cveID"),
        (download.validate_ctid, {"metadata": {"attack_version": "15.1"}}, "expected ATT&CK"),
        (download.validate_ctid, {"metadata": {"attack_version": "16.1"}, "mapping_objects": []}, "no mapping"),
    ],
)
def test_validators_reject_unexpected_content(validator, data, message):
    with pytest.raises(DownloadError, match=message):
        validator(data)


def test_validators_return_versions():
    assert download.validate_attack(ATTACK_BUNDLE) == download.ATTACK_VERSION
    assert download.validate_kev(KEV_CATALOG) == "2026.10.14"
    assert download.validate_ctid(CTID_FILE) == download.CTID_ATTACK_VERSION


def test_download_file_saves_records_and_skips_existing(tmp_path):
    calls = []
    with make_client(static_handler(calls)) as client:
        path = download.download_file(client, download.KEV, tmp_path, sleep=no_sleep)
        download.download_file(client, download.KEV, tmp_path, sleep=no_sleep)
    assert len(calls) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == KEV_CATALOG
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kev"]["version"] == "2026.10.14"
    assert manifest["kev"]["bytes"] == path.stat().st_size
    assert len(manifest["kev"]["sha256"]) == 64


def test_download_file_force_downloads_again(tmp_path):
    calls = []
    with make_client(static_handler(calls)) as client:
        download.download_file(client, download.KEV, tmp_path, sleep=no_sleep)
        download.download_file(client, download.KEV, tmp_path, force=True, sleep=no_sleep)
    assert len(calls) == 2


def test_download_file_rejects_invalid_content_and_keeps_nothing(tmp_path):
    with make_client(lambda request: httpx.Response(200, json={"type": "bundle", "objects": []})) as client:
        with pytest.raises(DownloadError):
            download.download_file(client, download.ATTACK, tmp_path, sleep=no_sleep)
    assert not (tmp_path / "attack").exists()


def test_download_file_rejects_non_json(tmp_path):
    with make_client(lambda request: httpx.Response(200, text="<html>")) as client:
        with pytest.raises(DownloadError, match="not JSON"):
            download.download_file(client, download.KEV, tmp_path, sleep=no_sleep)


def test_fetch_nvd_kev_paginates_fills_gaps_and_filters():
    requests = []
    pages = {0: ["CVE-2024-0001", "CVE-9999-0001"], 2: ["CVE-2024-0002"]}

    def handler(request):
        requests.append(request)
        query = parse_qs(urlparse(str(request.url)).query, keep_blank_values=True)
        if "cveId" in query:
            return httpx.Response(200, json=nvd_page(query["cveId"], 1))
        assert "hasKev" in query
        return httpx.Response(200, json=nvd_page(pages[int(query["startIndex"][0])], 3))

    kev_ids = {"CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003"}
    with make_client(handler) as client:
        cves = download.fetch_nvd_kev(client, "secret", kev_ids, page_size=2, sleep=no_sleep)

    assert [c["id"] for c in cves] == sorted(kev_ids)
    assert len(requests) == 3  # two hasKev pages, one direct lookup for CVE-2024-0003
    assert all(r.headers["apiKey"] == "secret" for r in requests)


def test_fetch_nvd_kev_without_key_sends_no_key_and_reports_missing():
    sleeps = []

    def handler(request):
        if "cveId" in str(request.url):
            return httpx.Response(200, json=nvd_page([], 0))
        assert "apiKey" not in request.headers
        return httpx.Response(200, json=nvd_page(["CVE-2024-0001"], 1))

    with make_client(handler) as client:
        cves = download.fetch_nvd_kev(client, "", {"CVE-2024-0001", "CVE-2024-0002"}, sleep=sleeps.append)
    assert [c["id"] for c in cves] == ["CVE-2024-0001"]
    assert sleeps == [download.NVD_DELAY_WITHOUT_KEY, download.NVD_DELAY_WITHOUT_KEY]


def test_download_nvd_requires_kev(tmp_path):
    with make_client(static_handler([])) as client:
        with pytest.raises(DownloadError, match="download kev first"):
            download.download_nvd(client, tmp_path, "key", sleep=no_sleep)


def test_main_downloads_everything_then_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NVD_API_KEY", "key")
    monkeypatch.setattr(download.time, "sleep", no_sleep)
    calls = []
    with make_client(static_handler(calls)) as client:
        assert download.main([], client=client) == 0
        first_run = len(calls)
        assert download.main([], client=client) == 0
    assert first_run == 4
    assert len(calls) == first_run
    raw = tmp_path / "raw"
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"attack", "kev", "ctid", "nvd"}
    assert manifest["nvd"]["cve_count"] == 3
    nvd = json.loads((raw / "nvd" / download.NVD_FILENAME).read_text(encoding="utf-8"))
    assert [c["id"] for c in nvd["cves"]] == ["CVE-2024-0001", "CVE-2024-0002", "CVE-2024-0003"]


def test_main_returns_error_code_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(download.time, "sleep", no_sleep)
    with make_client(lambda request: httpx.Response(404)) as client:
        assert download.main(["--only", "kev"], client=client) == 1

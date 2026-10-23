"""Unit tests for the pinned, hash-verified Sackmann download (network stubbed)."""

import json
import subprocess
import sys

import pytest

from scripts import download_sackmann as dl


def test_git_blob_sha_matches_git():
    """Our blob hash equals `git hash-object` for the same bytes."""
    content = b"tourney_id,winner_id\n1991-7,1\n"
    expected = (
        subprocess.run(["git", "hash-object", "--stdin"], input=content, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    assert dl.git_blob_sha(content) == expected


def test_wanted_files_cover_years_and_extras():
    """Yearly files from first_year to the last year, then players and docs."""
    files = dl.wanted_files(2025)
    assert files[:2] == ["atp_matches_2025.csv", "atp_matches_2026.csv"]
    assert files[2:] == list(dl.EXTRA_FILES)


@pytest.fixture(name="fake_remote")
def fixture_fake_remote(monkeypatch, tmp_path):
    """Serve a fake tree and fake files; DEST points at a temp directory."""
    files = {path: f"content of {path}".encode() for path in dl.wanted_files(2026)}
    tree = {"tree": [{"path": p, "type": "blob", "sha": dl.git_blob_sha(c)} for p, c in files.items()]}
    fetched = []

    def fetch(url):
        fetched.append(url)
        if url == dl.TREE_URL:
            return json.dumps(tree).encode()
        return files[url.rsplit("/", 1)[1]]

    monkeypatch.setattr(dl, "fetch", fetch)
    monkeypatch.setattr(dl, "DEST", tmp_path)
    return files, fetched


def test_download_verifies_and_skips_files_already_correct(fake_remote, tmp_path):
    """First run downloads everything; a second run only fetches the tree."""
    files, fetched = fake_remote
    entries = dl.download(2026, force=False)
    assert {e["file"] for e in entries} == set(files)
    assert (tmp_path / "atp_matches_2026.csv").read_bytes() == files["atp_matches_2026.csv"]
    fetched.clear()
    dl.download(2026, force=False)
    assert fetched == [dl.TREE_URL]


def test_download_rejects_tampered_content(fake_remote, monkeypatch):
    """A file whose bytes differ from the pinned commit raises."""
    _, _ = fake_remote
    original = dl.fetch
    monkeypatch.setattr(dl, "fetch", lambda url: b"tampered" if url.endswith("README.md") else original(url))
    with pytest.raises(ValueError, match="README.md"):
        dl.download(2026, force=True)


def test_main_writes_manifest(fake_remote, tmp_path, monkeypatch):
    """The CLI writes a manifest with the commit and one entry per file."""
    monkeypatch.setattr(sys, "argv", ["download_sackmann", "--first-year", "2026"])
    dl.main()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == dl.COMMIT
    assert len(manifest["files"]) == len(fake_remote[0])

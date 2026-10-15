"""Tests for app.config."""
# pylint: disable=missing-function-docstring

from pathlib import Path

from app import __version__
from app.config import load_settings


def test_version_is_set():
    assert __version__


def test_defaults(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    settings = load_settings(env_file=None)
    assert settings.log_level == "INFO"
    assert settings.data_dir == Path("data")


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("DATA_DIR", "/tmp/cti")
    settings = load_settings(env_file=None)
    assert settings.log_level == "DEBUG"
    assert settings.data_dir == Path("/tmp/cti")


def test_api_key_is_read_but_never_shown(monkeypatch):
    monkeypatch.setenv("NVD_API_KEY", "super-secret")
    monkeypatch.setenv("DATA_DIR", "/tmp/cti")
    settings = load_settings(env_file=None)
    assert settings.nvd_api_key == "super-secret"
    assert "super-secret" not in repr(settings)
    assert settings.raw_dir == Path("/tmp/cti") / "raw"


def test_reads_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=warning\n", encoding="utf-8")
    settings = load_settings(env_file=str(env_file))
    assert settings.log_level == "WARNING"

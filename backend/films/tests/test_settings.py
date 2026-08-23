"""
Tests for settings behavior that only matters in production.

These exercise the helper functions directly rather than re-importing the settings
module, which pytest-django has already configured for the test run.
"""

import importlib

import pytest

from config import settings as settings_module


def test_required_returns_a_present_value(monkeypatch):
    monkeypatch.setenv("SOME_REQUIRED_VALUE", "present")

    assert settings_module._required("SOME_REQUIRED_VALUE") == "present"


def test_required_raises_with_an_actionable_message(monkeypatch):
    """A misconfigured deploy should fail at startup, naming the fix."""
    monkeypatch.delenv("SOME_REQUIRED_VALUE", raising=False)

    with pytest.raises(settings_module.ImproperlyConfigured) as exc:
        settings_module._required("SOME_REQUIRED_VALUE")

    message = str(exc.value)
    assert "SOME_REQUIRED_VALUE" in message
    assert ".env.example" in message


def test_required_treats_empty_string_as_missing(monkeypatch):
    # An unset secret often arrives as "" rather than absent.
    monkeypatch.setenv("SOME_REQUIRED_VALUE", "")

    with pytest.raises(settings_module.ImproperlyConfigured):
        settings_module._required("SOME_REQUIRED_VALUE")


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
     ("0", False), ("false", False), ("", False), ("nonsense", False)],
)
def test_bool_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_FLAG", raw)

    assert settings_module._bool("SOME_FLAG") is expected


def test_int_falls_back_when_malformed(monkeypatch):
    """A bad numeric env var must not crash the process at import time."""
    monkeypatch.setenv("SOME_NUMBER", "not-a-number")

    assert settings_module._int("SOME_NUMBER", 15) == 15


def test_csv_splits_and_drops_blanks(monkeypatch):
    monkeypatch.setenv("SOME_LIST", " a.com , ,b.com ")

    assert settings_module._csv("SOME_LIST") == ["a.com", "b.com"]


def test_dotenv_does_not_override_real_environment(monkeypatch, tmp_path):
    """
    Regression: settings loaded .env with override=True, so a file inside a
    container would shadow the secrets the platform injected — and the
    fail-fast check for a missing SECRET_KEY could never fire, because .env
    always supplied the development one.
    """
    from dotenv import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("PLATFORM_INJECTED=from-dotenv\n")
    monkeypatch.setenv("PLATFORM_INJECTED", "from-platform")

    load_dotenv(env_file, override=False)

    import os

    assert os.environ["PLATFORM_INJECTED"] == "from-platform"


def test_settings_module_imports_cleanly():
    """Guards against a syntax or import-order error reaching a deploy."""
    importlib.reload(settings_module)

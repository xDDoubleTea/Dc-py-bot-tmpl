"""Tests for reading configuration out of the environment."""

import pytest

from config.secrets import secret_flag, secret_with_default


@pytest.mark.parametrize("value", ["True", "true", "TRUE", "1", "yes", "on", " on "])
def test_truthy_values(monkeypatch, value):
    monkeypatch.setenv("SOME_FLAG", value)

    assert secret_flag("SOME_FLAG") is True


@pytest.mark.parametrize("value", ["False", "false", "0", "no", "off", "", "banana"])
def test_falsy_values(monkeypatch, value):
    """
    Everything that is not an explicit yes is off. A bare string would make
    "False" truthy, which is the whole reason this helper exists.
    """
    monkeypatch.setenv("SOME_FLAG", value)

    assert secret_flag("SOME_FLAG") is False


def test_missing_variable_uses_the_default(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)

    assert secret_flag("SOME_FLAG") is False
    assert secret_flag("SOME_FLAG", default=True) is True


def test_secret_with_default(monkeypatch):
    monkeypatch.delenv("SOME_VALUE", raising=False)
    assert secret_with_default("SOME_VALUE", "fallback") == "fallback"

    monkeypatch.setenv("SOME_VALUE", "set")
    assert secret_with_default("SOME_VALUE", "fallback") == "set"

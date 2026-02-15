"""Tests for UI style token and theme utilities."""
import warnings

import pytest

from keyvox.ui.styles import utils
from keyvox.ui.styles.tokens import get_tokens


class _FakeApp:
    def __init__(self):
        self.styles = []

    def setStyleSheet(self, value):
        self.styles.append(value)


def test_get_tokens_contains_expected_keys_for_themes():
    dark = get_tokens("dark")
    light = get_tokens("light")
    assert "BG_PRIMARY" in dark and "BG_PRIMARY" in light
    assert dark["BG_PRIMARY"] != light["BG_PRIMARY"]


def test_load_qss_existing_file():
    qss = utils.load_qss("base.qss")
    assert "QMainWindow" in qss


def test_load_qss_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        utils.load_qss("nope.qss")


def test_replace_tokens_replaces_known_values():
    out = utils.replace_tokens("color: {{ACCENT_PRIMARY}};", theme="dark")
    assert "{{ACCENT_PRIMARY}}" not in out
    assert "#" in out


def test_replace_tokens_warns_on_missing_token():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = utils.replace_tokens("color: {{MISSING_TOKEN}};", theme="dark")
    assert "{{MISSING_TOKEN}}" in out
    assert any("Missing theme tokens" in str(w.message) for w in caught)


def test_apply_theme_uses_cache(monkeypatch):
    app = _FakeApp()
    calls = {"count": 0}
    utils.clear_cache()

    def fake_load(filename):
        calls["count"] += 1
        return f"/* {filename} */\nQWidget {{ color: {{TEXT_PRIMARY}}; }}"

    monkeypatch.setattr(utils, "load_qss", fake_load)

    utils.apply_theme(app, theme="dark")
    first = app.styles[-1]
    utils.apply_theme(app, theme="dark")
    second = app.styles[-1]

    assert first == second
    # First run loads base + theme + 4 components.
    assert calls["count"] == 6


def test_apply_theme_skips_missing_optional_components(monkeypatch):
    app = _FakeApp()
    utils.clear_cache()

    def fake_load(filename):
        if filename.startswith("components/"):
            raise FileNotFoundError(filename)
        return "QWidget { color: {{TEXT_PRIMARY}}; }"

    monkeypatch.setattr(utils, "load_qss", fake_load)
    utils.apply_theme(app, theme="light")
    assert app.styles[-1]


def test_get_color_and_clear_cache():
    utils.clear_cache()
    assert utils.get_color("ACCENT_PRIMARY", theme="dark").startswith("#")
    with pytest.raises(KeyError):
        utils.get_color("NOPE", theme="dark")


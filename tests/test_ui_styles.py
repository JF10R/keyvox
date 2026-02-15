"""Tests for UI style token and theme utilities."""
import builtins
import warnings

import pytest

from keyvox.ui.styles import utils
from keyvox.ui.styles.tokens import get_tokens, resolve_profile


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


def test_resolve_profile_auto_windows(monkeypatch):
    monkeypatch.setattr("keyvox.ui.styles.tokens.sys.platform", "win32", raising=False)
    assert resolve_profile("auto") == "windows-crisp"


def test_resolve_profile_default_non_windows(monkeypatch):
    monkeypatch.setattr("keyvox.ui.styles.tokens.sys.platform", "linux", raising=False)
    assert resolve_profile("auto") == "default"
    assert resolve_profile("default") == "default"
    assert resolve_profile("windows-crisp") == "windows-crisp"
    assert resolve_profile("invalid-profile") == "default"


def test_get_tokens_windows_crisp_overrides_font_stack():
    default_tokens = get_tokens("dark", profile="default")
    crisp_tokens = get_tokens("dark", profile="windows-crisp")
    assert "Segoe UI" in crisp_tokens["FAMILY_PRIMARY"]
    assert crisp_tokens["FAMILY_PRIMARY"] != default_tokens["FAMILY_PRIMARY"]
    assert crisp_tokens["SIZE_BODY"] != default_tokens["SIZE_BODY"]


def test_load_qss_existing_file():
    qss = utils.load_qss("base.qss")
    assert "QMainWindow" in qss


def test_load_qss_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        utils.load_qss("nope.qss")


def test_replace_tokens_replaces_known_values():
    out = utils.replace_tokens("color: {{ACCENT_PRIMARY}};", theme="dark", profile="default")
    assert "{{ACCENT_PRIMARY}}" not in out
    assert "#" in out


def test_replace_tokens_warns_on_missing_token():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = utils.replace_tokens("color: {{MISSING_TOKEN}};", theme="dark", profile="default")
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
    monkeypatch.setattr(utils, "_load_application_fonts", lambda: 0)

    utils.apply_theme(app, theme="dark", profile="default")
    first = app.styles[-1]
    utils.apply_theme(app, theme="dark", profile="default")
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
    monkeypatch.setattr(utils, "_load_application_fonts", lambda: 0)
    utils.apply_theme(app, theme="light", profile="default")
    assert app.styles[-1]


def test_get_color_and_clear_cache():
    utils.clear_cache()
    assert utils.get_color("ACCENT_PRIMARY", theme="dark", profile="default").startswith("#")
    with pytest.raises(KeyError):
        utils.get_color("NOPE", theme="dark", profile="default")


def test_font_files_discovers_manrope_bundle():
    files = utils._font_files()
    assert any("manrope" in p.name.lower() for p in files)


def test_apply_theme_loads_fonts_once(monkeypatch):
    app = _FakeApp()
    utils.clear_cache()
    calls = {"fonts": 0}

    monkeypatch.setattr(utils, "_load_application_fonts", lambda: calls.__setitem__("fonts", calls["fonts"] + 1))
    monkeypatch.setattr(utils, "load_qss", lambda filename: "QWidget { color: {{TEXT_PRIMARY}}; }")

    utils.apply_theme(app, theme="dark", profile="default")
    utils.apply_theme(app, theme="dark", profile="default")
    assert calls["fonts"] == 1


def test_font_files_returns_empty_when_fonts_dir_missing(monkeypatch, tmp_path):
    fake_utils = tmp_path / "x" / "y" / "utils.py"
    fake_utils.parent.mkdir(parents=True, exist_ok=True)
    fake_utils.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(utils, "__file__", str(fake_utils))
    assert utils._font_files() == []


def test_load_application_fonts_returns_zero_when_qt_missing(monkeypatch):
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PySide6.QtGui":
            raise ImportError("missing")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert utils._load_application_fonts() == 0


def test_load_application_fonts_counts_loaded_and_ignores_errors(monkeypatch, tmp_path):
    class FakeFontDb:
        calls = 0

        @classmethod
        def addApplicationFont(cls, _path):
            cls.calls += 1
            if cls.calls == 1:
                return 7
            if cls.calls == 2:
                return -1
            raise RuntimeError("bad font")

    class FakeQtGui:
        QFontDatabase = FakeFontDb

    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PySide6.QtGui":
            return FakeQtGui
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        utils,
        "_font_files",
        lambda: [tmp_path / "a.ttf", tmp_path / "b.ttf", tmp_path / "c.ttf"],
    )

    assert utils._load_application_fonts() == 1

"""Theme loader and utility functions for Keyvox UI.

This module handles loading QSS stylesheets and replacing token placeholders
with actual design values from tokens.py.
"""

import re
import warnings
from pathlib import Path
from typing import Optional

from .tokens import get_tokens, resolve_profile


_qss_cache: dict[tuple[str, str], str] = {}
_fonts_loaded = False


def load_qss(filename: str) -> str:
    """Load a QSS stylesheet file from the styles directory.

    Args:
        filename: Name of the QSS file (relative to styles/ directory)

    Returns:
        Raw QSS content as string

    Raises:
        FileNotFoundError: If the QSS file doesn't exist
    """
    styles_dir = Path(__file__).parent
    file_path = styles_dir / filename

    if not file_path.exists():
        raise FileNotFoundError(f"QSS file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def _font_files() -> list[Path]:
    """Return bundled font files shipped with Keyvox UI."""
    fonts_dir = Path(__file__).resolve().parents[1] / "fonts"
    if not fonts_dir.exists():
        return []
    return sorted(p for p in fonts_dir.iterdir() if p.suffix.lower() in {".ttf", ".otf"})


def _load_application_fonts() -> int:
    """Load bundled fonts into Qt application font database.

    Returns:
        Number of fonts loaded successfully.
    """
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:
        return 0

    loaded = 0
    for font_path in _font_files():
        try:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id != -1:
                loaded += 1
        except Exception:
            continue
    return loaded


def replace_tokens(qss: str, theme: str = "dark", profile: str = "auto") -> str:
    """Replace {{TOKEN}} placeholders in QSS with actual design values.

    Args:
        qss: QSS stylesheet content with {{TOKEN}} placeholders
        theme: Theme name to use for token values

    Returns:
        QSS content with all tokens replaced

    Example:
        Input:  "background-color: {{BG_PRIMARY}};"
        Output: "background-color: #1e1e1e;"
    """
    tokens = get_tokens(theme, profile=profile)
    missing = []

    def replacer(match):
        token_name = match.group(1)
        if token_name in tokens:
            return tokens[token_name]
        missing.append(token_name)
        return match.group(0)

    result = re.sub(r"\{\{([A-Z_]+)\}\}", replacer, qss)

    if missing:
        warnings.warn(
            f"Missing theme tokens: {', '.join(sorted(set(missing)))}",
            stacklevel=2,
        )

    return result


def apply_theme(app, theme: str = "dark", profile: str = "auto") -> None:
    """Apply a complete theme to a QApplication.

    This loads all QSS files (base + theme + components), replaces tokens,
    and applies the final stylesheet to the application.

    Args:
        app: QApplication instance
        theme: Theme name ("dark" or "light")

    Raises:
        FileNotFoundError: If required QSS files are missing
    """
    global _fonts_loaded
    if not _fonts_loaded:
        _load_application_fonts()
        _fonts_loaded = True

    effective_profile = resolve_profile(profile)
    cache_key = ("combined", theme, effective_profile)
    if cache_key in _qss_cache:
        app.setStyleSheet(_qss_cache[cache_key])
        return

    # Load base styles
    base_qss = load_qss("base.qss")

    # Load theme-specific styles
    theme_qss = load_qss(f"themes/{theme}.qss")

    # Load component styles
    components = ["buttons", "inputs", "tables", "cards"]
    component_qss = []
    for component in components:
        try:
            qss = load_qss(f"components/{component}.qss")
            component_qss.append(qss)
        except FileNotFoundError:
            # Components are optional - skip if missing
            pass

    # Combine all stylesheets
    combined_qss = "\n\n".join([base_qss, theme_qss] + component_qss)

    # Replace token placeholders
    final_qss = replace_tokens(combined_qss, theme, profile=effective_profile)

    _qss_cache[cache_key] = final_qss
    app.setStyleSheet(final_qss)


def get_color(color_name: str, theme: str = "dark", profile: str = "auto") -> str:
    """Get a specific color value from the current theme.

    Useful for programmatic color access (e.g., drawing operations).

    Args:
        color_name: Name of the color token (e.g., "ACCENT_PRIMARY")
        theme: Theme name

    Returns:
        Hex color code (e.g., "#007acc")

    Raises:
        KeyError: If color name doesn't exist
    """
    tokens = get_tokens(theme, profile=profile)
    return tokens[color_name]


def clear_cache() -> None:
    """Clear the QSS cache. Useful during development."""
    global _fonts_loaded
    _qss_cache.clear()
    _fonts_loaded = False


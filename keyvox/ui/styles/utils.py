"""Theme loader and utility functions for KeyVox UI.

This module handles loading QSS stylesheets and replacing token placeholders
with actual design values from tokens.py.
"""

import re
import warnings
from pathlib import Path
from typing import Optional

from .tokens import get_tokens


_qss_cache: dict[tuple[str, str], str] = {}


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


def replace_tokens(qss: str, theme: str = "dark") -> str:
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
    tokens = get_tokens(theme)
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


def apply_theme(app, theme: str = "dark") -> None:
    """Apply a complete theme to a QApplication.

    This loads all QSS files (base + theme + components), replaces tokens,
    and applies the final stylesheet to the application.

    Args:
        app: QApplication instance
        theme: Theme name ("dark" or "light")

    Raises:
        FileNotFoundError: If required QSS files are missing
    """
    cache_key = ("combined", theme)
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
    final_qss = replace_tokens(combined_qss, theme)

    _qss_cache[cache_key] = final_qss
    app.setStyleSheet(final_qss)


def get_color(color_name: str, theme: str = "dark") -> str:
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
    tokens = get_tokens(theme)
    return tokens[color_name]


def clear_cache() -> None:
    """Clear the QSS cache. Useful during development."""
    _qss_cache.clear()

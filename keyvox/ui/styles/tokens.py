"""Design tokens - single source of truth for all design values.

These tokens define the visual language of Keyvox UI. They are used by the
theme loader to generate QSS stylesheets with consistent values across all components.
"""
import sys

# Color Palette - Dark Theme (Modern product, high legibility)
COLORS_DARK = {
    # Backgrounds
    "BG_PRIMARY": "#0f1115",      # Window background
    "BG_SECONDARY": "#151922",    # Cards/panels
    "BG_TERTIARY": "#1d2430",     # Inputs and controls
    "BG_ELEVATED": "#232b39",     # Elevated surfaces
    "BG_HOVER": "#263247",        # Hover states
    "BG_ACTIVE": "#31405a",       # Active/pressed
    "BG_DISABLED": "#1b2230",     # Disabled elements

    # Borders
    "BORDER_DEFAULT": "#2a3446",
    "BORDER_FOCUS": "#4c8eff",
    "BORDER_HOVER": "#3c4b66",
    "BORDER_DISABLED": "#243046",

    # Text
    "TEXT_PRIMARY": "#edf2fb",
    "TEXT_SECONDARY": "#b4c0d4",
    "TEXT_TERTIARY": "#8b98ad",
    "TEXT_DISABLED": "#657389",
    "TEXT_ON_ACCENT": "#ffffff",

    # Accent Colors
    "ACCENT_PRIMARY": "#4c8eff",
    "ACCENT_HOVER": "#63a0ff",
    "ACCENT_ACTIVE": "#2f73e4",
    "SUCCESS": "#34d399",
    "ERROR": "#fb7185",
    "WARNING": "#fbbf24",
    "TINT_ACCENT": "#17243c",
    "TINT_SUCCESS": "#142b26",
    "TINT_ERROR": "#341d26",
    "TINT_WARNING": "#3a3019",

    # Focus
    "FOCUS_RING": "#63a0ff",
    "FOCUS_SHADOW": "rgba(99, 160, 255, 0.45)",
}

# Color Palette - Light Theme (Soft neutral, professional contrast)
COLORS_LIGHT = {
    # Backgrounds
    "BG_PRIMARY": "#f3f6fb",
    "BG_SECONDARY": "#f8fafd",
    "BG_TERTIARY": "#ecf1f8",
    "BG_ELEVATED": "#ffffff",
    "BG_HOVER": "#e2eaf5",
    "BG_ACTIVE": "#d8e2f1",
    "BG_DISABLED": "#f0f4fa",

    # Borders
    "BORDER_DEFAULT": "#cfd8e8",
    "BORDER_FOCUS": "#2f73e4",
    "BORDER_HOVER": "#bccbe0",
    "BORDER_DISABLED": "#dbe4f0",

    # Text
    "TEXT_PRIMARY": "#1b2940",
    "TEXT_SECONDARY": "#495a75",
    "TEXT_TERTIARY": "#72839c",
    "TEXT_DISABLED": "#9ba9bd",
    "TEXT_ON_ACCENT": "#ffffff",

    # Accent
    "ACCENT_PRIMARY": "#2f73e4",
    "ACCENT_HOVER": "#2563c9",
    "ACCENT_ACTIVE": "#1f52a3",
    "SUCCESS": "#0f9f6e",
    "ERROR": "#d63a62",
    "WARNING": "#c28b06",
    "TINT_ACCENT": "#e9f1fd",
    "TINT_SUCCESS": "#e7f6f1",
    "TINT_ERROR": "#fdebf1",
    "TINT_WARNING": "#fff6e6",

    # Focus
    "FOCUS_RING": "#2f73e4",
    "FOCUS_SHADOW": "rgba(47, 115, 228, 0.35)",
}

# Typography
FONTS = {
    # Font Families
    "FAMILY_PRIMARY": "Manrope, 'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif",
    "FAMILY_MONOSPACE": "Consolas, Monaco, 'Courier New', monospace",

    # Font Sizes (px)
    "SIZE_DISPLAY": "24px",       # Large headings
    "SIZE_H1": "20px",            # Section headings
    "SIZE_H2": "16px",            # Subsection headings
    "SIZE_BODY": "14px",          # Body text, buttons, inputs
    "SIZE_SMALL": "12px",         # Secondary text, labels
    "SIZE_TINY": "10px",          # Captions, metadata

    # Font Weights
    "WEIGHT_NORMAL": "400",
    "WEIGHT_MEDIUM": "500",
    "WEIGHT_BOLD": "700",

    # Line Heights
    "LINE_HEIGHT_TIGHT": "1.2",
    "LINE_HEIGHT_NORMAL": "1.5",
    "LINE_HEIGHT_LOOSE": "1.8",
}

FONTS_WINDOWS_CRISP = {
    # Windows-native stack for best hinting and ClearType-like rendering.
    "FAMILY_PRIMARY": "'Segoe UI Variable Text', 'Segoe UI', Tahoma, Arial, sans-serif",
    "FAMILY_MONOSPACE": "Consolas, 'Cascadia Mono', 'Courier New', monospace",
    # Slightly larger defaults for better legibility on desktop LCD.
    "SIZE_DISPLAY": "26px",
    "SIZE_H1": "21px",
    "SIZE_H2": "17px",
    "SIZE_BODY": "15px",
    "SIZE_SMALL": "13px",
    "SIZE_TINY": "11px",
    "WEIGHT_NORMAL": "400",
    "WEIGHT_MEDIUM": "600",
    "WEIGHT_BOLD": "700",
    "LINE_HEIGHT_TIGHT": "1.25",
    "LINE_HEIGHT_NORMAL": "1.55",
    "LINE_HEIGHT_LOOSE": "1.9",
}

# Spacing (8px base grid)
SPACING = {
    "TINY": "4px",       # Minimal gaps
    "SMALL": "8px",      # Compact spacing
    "MEDIUM": "16px",    # Standard spacing
    "LARGE": "24px",     # Section spacing
    "XLARGE": "32px",    # Major separations
}

# Border Radius (prefixed to avoid collision with SPACING keys)
RADIUS = {
    "RADIUS_SMALL": "6px",
    "RADIUS_MEDIUM": "8px",
    "RADIUS_LARGE": "12px",
}

# Shadows (prefixed to avoid collision with SPACING keys)
SHADOWS_DARK = {
    "SHADOW_SMALL": "0 1px 3px rgba(0, 0, 0, 0.4)",
    "SHADOW_MEDIUM": "0 2px 8px rgba(0, 0, 0, 0.5)",
    "SHADOW_LARGE": "0 4px 16px rgba(0, 0, 0, 0.6)",
    "SHADOW_FOCUS": "0 0 0 2px rgba(59, 130, 246, 0.4)",
}

SHADOWS_LIGHT = {
    "SHADOW_SMALL": "0 1px 3px rgba(0, 0, 0, 0.08)",
    "SHADOW_MEDIUM": "0 2px 8px rgba(0, 0, 0, 0.12)",
    "SHADOW_LARGE": "0 4px 16px rgba(0, 0, 0, 0.16)",
    "SHADOW_FOCUS": "0 0 0 2px rgba(59, 130, 246, 0.3)",
}

# Transitions (ms)
TRANSITIONS = {
    "FAST": "100ms",
    "NORMAL": "200ms",
    "SLOW": "300ms",
}

# Z-Index Layers
Z_INDEX = {
    "BASE": "0",
    "DROPDOWN": "100",
    "MODAL": "200",
    "TOOLTIP": "300",
}


def resolve_profile(profile: str = "auto") -> str:
    """Resolve effective token profile.

    Args:
        profile: "auto", "default", or "windows-crisp"
    """
    normalized = (profile or "auto").strip().lower()
    if normalized not in {"auto", "default", "windows-crisp"}:
        normalized = "auto"
    if normalized == "auto":
        return "windows-crisp" if sys.platform == "win32" else "default"
    return normalized


def get_tokens(theme: str = "dark", profile: str = "auto") -> dict:
    """Get all design tokens for a specific theme.

    Args:
        theme: Theme name ("dark" or "light")

    Returns:
        Dictionary containing all design tokens merged together
    """
    colors = COLORS_DARK if theme == "dark" else COLORS_LIGHT
    shadows = SHADOWS_DARK if theme == "dark" else SHADOWS_LIGHT
    effective_profile = resolve_profile(profile)
    fonts = FONTS_WINDOWS_CRISP if effective_profile == "windows-crisp" else FONTS

    return {
        **colors,
        **fonts,
        **SPACING,
        **RADIUS,
        **shadows,
        **TRANSITIONS,
        **Z_INDEX,
    }


"""Design tokens - single source of truth for all design values.

These tokens define the visual language of KeyVox UI. They are used by the
theme loader to generate QSS stylesheets with consistent values across all components.
"""

# Color Palette - Dark Theme
COLORS_DARK = {
    # Backgrounds
    "BG_PRIMARY": "#18181b",      # Main window (Zinc-900)
    "BG_SECONDARY": "#1f1f23",    # Cards/panels
    "BG_TERTIARY": "#27272a",     # Inputs, buttons (Zinc-800)
    "BG_ELEVATED": "#2c2c31",     # Popovers, dialogs (one step lighter)
    "BG_HOVER": "#303036",        # Hover states
    "BG_ACTIVE": "#3f3f46",       # Active/pressed (Zinc-700)
    "BG_DISABLED": "#27272a",     # Disabled elements

    # Borders
    "BORDER_DEFAULT": "#2e2e33",  # Subtler default borders
    "BORDER_FOCUS": "#3b82f6",    # Modern blue focus
    "BORDER_HOVER": "#3f3f46",    # Hover borders
    "BORDER_DISABLED": "#2e2e33", # Disabled borders

    # Text
    "TEXT_PRIMARY": "#e4e4e7",    # Primary text (Zinc-200)
    "TEXT_SECONDARY": "#a1a1aa",  # Secondary text (Zinc-400)
    "TEXT_TERTIARY": "#71717a",   # Tertiary text (Zinc-500)
    "TEXT_DISABLED": "#52525b",   # Disabled text (Zinc-600)
    "TEXT_ON_ACCENT": "#ffffff",  # Text on accent colors

    # Accent Colors
    "ACCENT_PRIMARY": "#3b82f6",  # Modern blue (Blue-500)
    "ACCENT_HOVER": "#60a5fa",    # Blue-400
    "ACCENT_ACTIVE": "#2563eb",   # Blue-600
    "SUCCESS": "#4ade80",         # Green-400
    "ERROR": "#f87171",           # Red-400
    "WARNING": "#fbbf24",         # Amber-400

    # Focus
    "FOCUS_RING": "#3b82f6",
    "FOCUS_SHADOW": "rgba(59, 130, 246, 0.4)",
}

# Color Palette - Light Theme
COLORS_LIGHT = {
    # Backgrounds (warm Stone scale)
    "BG_PRIMARY": "#fafaf9",      # Stone-50
    "BG_SECONDARY": "#f5f5f4",    # Stone-100
    "BG_TERTIARY": "#e7e5e4",     # Stone-200
    "BG_ELEVATED": "#ffffff",     # Pure white for elevated
    "BG_HOVER": "#f0efed",        # Between Stone-100 and 200
    "BG_ACTIVE": "#e7e5e4",       # Stone-200
    "BG_DISABLED": "#f5f5f4",     # Stone-100

    # Borders
    "BORDER_DEFAULT": "#e7e5e4",  # Stone-200
    "BORDER_FOCUS": "#3b82f6",    # Same accent blue
    "BORDER_HOVER": "#d6d3d1",    # Stone-300
    "BORDER_DISABLED": "#e7e5e4", # Stone-200

    # Text
    "TEXT_PRIMARY": "#1c1917",    # Stone-900
    "TEXT_SECONDARY": "#78716c",  # Stone-500
    "TEXT_TERTIARY": "#a8a29e",   # Stone-400
    "TEXT_DISABLED": "#d6d3d1",   # Stone-300
    "TEXT_ON_ACCENT": "#ffffff",

    # Accent (same hues, work on light bg)
    "ACCENT_PRIMARY": "#3b82f6",  # Blue-500
    "ACCENT_HOVER": "#2563eb",    # Blue-600 (darker on light bg)
    "ACCENT_ACTIVE": "#1d4ed8",   # Blue-700
    "SUCCESS": "#22c55e",         # Green-500
    "ERROR": "#ef4444",           # Red-500
    "WARNING": "#f59e0b",         # Amber-500

    # Focus
    "FOCUS_RING": "#3b82f6",
    "FOCUS_SHADOW": "rgba(59, 130, 246, 0.3)",
}

# Typography
FONTS = {
    # Font Families (platform-aware stack)
    "FAMILY_PRIMARY": "Segoe UI, -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
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
    "WEIGHT_BOLD": "600",

    # Line Heights
    "LINE_HEIGHT_TIGHT": "1.2",
    "LINE_HEIGHT_NORMAL": "1.5",
    "LINE_HEIGHT_LOOSE": "1.8",
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


def get_tokens(theme: str = "dark") -> dict:
    """Get all design tokens for a specific theme.

    Args:
        theme: Theme name ("dark" or "light")

    Returns:
        Dictionary containing all design tokens merged together
    """
    colors = COLORS_DARK if theme == "dark" else COLORS_LIGHT
    shadows = SHADOWS_DARK if theme == "dark" else SHADOWS_LIGHT

    return {
        **colors,
        **FONTS,
        **SPACING,
        **RADIUS,
        **shadows,
        **TRANSITIONS,
        **Z_INDEX,
    }

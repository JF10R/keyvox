"""Helpers for custom borderless window chrome behavior.

This module intentionally stays Qt-agnostic so resize and hit-test logic can
be unit tested without GUI dependencies.
"""

from dataclasses import dataclass

REGION_NONE = "none"
REGION_LEFT = "left"
REGION_RIGHT = "right"
REGION_TOP = "top"
REGION_BOTTOM = "bottom"
REGION_TOP_LEFT = "top_left"
REGION_TOP_RIGHT = "top_right"
REGION_BOTTOM_LEFT = "bottom_left"
REGION_BOTTOM_RIGHT = "bottom_right"


@dataclass(frozen=True)
class Rect:
    """Simple immutable rectangle."""

    x: int
    y: int
    width: int
    height: int


def detect_resize_region(x: int, y: int, width: int, height: int, margin: int = 8) -> str:
    """Return the resize region name for a point within a window rectangle."""
    near_left = x <= margin
    near_right = x >= width - margin
    near_top = y <= margin
    near_bottom = y >= height - margin

    if near_left and near_top:
        return REGION_TOP_LEFT
    if near_right and near_top:
        return REGION_TOP_RIGHT
    if near_left and near_bottom:
        return REGION_BOTTOM_LEFT
    if near_right and near_bottom:
        return REGION_BOTTOM_RIGHT
    if near_left:
        return REGION_LEFT
    if near_right:
        return REGION_RIGHT
    if near_top:
        return REGION_TOP
    if near_bottom:
        return REGION_BOTTOM
    return REGION_NONE


def cursor_name_for_region(region: str) -> str:
    """Return an abstract cursor name for a resize region."""
    if region in {REGION_LEFT, REGION_RIGHT}:
        return "size_h"
    if region in {REGION_TOP, REGION_BOTTOM}:
        return "size_v"
    if region in {REGION_TOP_LEFT, REGION_BOTTOM_RIGHT}:
        return "size_fdiag"
    if region in {REGION_TOP_RIGHT, REGION_BOTTOM_LEFT}:
        return "size_bdiag"
    return "arrow"


def resize_rect(
    start_rect: Rect,
    region: str,
    dx: int,
    dy: int,
    min_width: int = 900,
    min_height: int = 640,
) -> Rect:
    """Resize a rectangle based on edge/corner drag delta."""
    x = start_rect.x
    y = start_rect.y
    width = start_rect.width
    height = start_rect.height

    if region in {REGION_LEFT, REGION_TOP_LEFT, REGION_BOTTOM_LEFT}:
        x += dx
        width -= dx
    elif region in {REGION_RIGHT, REGION_TOP_RIGHT, REGION_BOTTOM_RIGHT}:
        width += dx

    if region in {REGION_TOP, REGION_TOP_LEFT, REGION_TOP_RIGHT}:
        y += dy
        height -= dy
    elif region in {REGION_BOTTOM, REGION_BOTTOM_LEFT, REGION_BOTTOM_RIGHT}:
        height += dy

    if width < min_width:
        if region in {REGION_LEFT, REGION_TOP_LEFT, REGION_BOTTOM_LEFT}:
            x -= min_width - width
        width = min_width

    if height < min_height:
        if region in {REGION_TOP, REGION_TOP_LEFT, REGION_TOP_RIGHT}:
            y -= min_height - height
        height = min_height

    return Rect(x=int(x), y=int(y), width=int(width), height=int(height))

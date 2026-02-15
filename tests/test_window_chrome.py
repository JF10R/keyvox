"""Tests for Qt-agnostic borderless window chrome helpers."""

from keyvox.ui.window_chrome import (
    Rect,
    REGION_BOTTOM,
    REGION_BOTTOM_LEFT,
    REGION_BOTTOM_RIGHT,
    REGION_LEFT,
    REGION_NONE,
    REGION_RIGHT,
    REGION_TOP,
    REGION_TOP_LEFT,
    REGION_TOP_RIGHT,
    cursor_name_for_region,
    detect_resize_region,
    resize_rect,
)


def test_detect_resize_region_returns_corners():
    assert detect_resize_region(0, 0, 1200, 800) == REGION_TOP_LEFT
    assert detect_resize_region(1199, 0, 1200, 800) == REGION_TOP_RIGHT
    assert detect_resize_region(0, 799, 1200, 800) == REGION_BOTTOM_LEFT
    assert detect_resize_region(1199, 799, 1200, 800) == REGION_BOTTOM_RIGHT


def test_detect_resize_region_returns_edges():
    assert detect_resize_region(0, 200, 1200, 800) == REGION_LEFT
    assert detect_resize_region(1199, 200, 1200, 800) == REGION_RIGHT
    assert detect_resize_region(200, 0, 1200, 800) == REGION_TOP
    assert detect_resize_region(200, 799, 1200, 800) == REGION_BOTTOM


def test_detect_resize_region_returns_none_inside():
    assert detect_resize_region(300, 300, 1200, 800) == REGION_NONE


def test_cursor_name_for_region_mapping():
    assert cursor_name_for_region(REGION_LEFT) == "size_h"
    assert cursor_name_for_region(REGION_TOP) == "size_v"
    assert cursor_name_for_region(REGION_TOP_LEFT) == "size_fdiag"
    assert cursor_name_for_region(REGION_TOP_RIGHT) == "size_bdiag"
    assert cursor_name_for_region(REGION_NONE) == "arrow"


def test_resize_rect_from_right_and_bottom():
    start = Rect(100, 100, 1200, 800)
    out = resize_rect(start, REGION_RIGHT, dx=50, dy=0)
    assert out == Rect(100, 100, 1250, 800)

    out2 = resize_rect(start, REGION_BOTTOM, dx=0, dy=40)
    assert out2 == Rect(100, 100, 1200, 840)


def test_resize_rect_from_left_and_top_adjusts_origin():
    start = Rect(100, 100, 1200, 800)

    out_left = resize_rect(start, REGION_LEFT, dx=30, dy=0)
    assert out_left == Rect(130, 100, 1170, 800)

    out_top = resize_rect(start, REGION_TOP, dx=0, dy=20)
    assert out_top == Rect(100, 120, 1200, 780)


def test_resize_rect_corner_resize():
    start = Rect(100, 100, 1200, 800)
    out = resize_rect(start, REGION_TOP_LEFT, dx=20, dy=15)
    assert out == Rect(120, 115, 1180, 785)


def test_resize_rect_clamps_min_size_from_left_and_top():
    start = Rect(100, 100, 920, 650)
    out = resize_rect(start, REGION_TOP_LEFT, dx=100, dy=100, min_width=900, min_height=640)
    # Width/height clamped; origin adjusted to preserve opposite edge.
    assert out == Rect(120, 110, 900, 640)


def test_resize_rect_clamps_min_size_from_right_and_bottom():
    start = Rect(100, 100, 920, 650)
    out = resize_rect(start, REGION_BOTTOM_RIGHT, dx=-100, dy=-100, min_width=900, min_height=640)
    assert out == Rect(100, 100, 900, 640)

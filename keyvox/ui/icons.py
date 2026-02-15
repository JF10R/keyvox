"""Programmatic icon rendering for Keyvox system tray.

Generates QIcon instances for each application state using QPainter.
No asset files required - all icons drawn programmatically.
"""

import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QBrush, QPainterPath, QColor
from keyvox.ui.styles.tokens import COLORS_DARK


def render_icon(state: str, phase: int = 0, size: int = 64) -> QIcon:
    """Render icon for given state.

    Args:
        state: One of "idle", "recording", "processing", "success", "error"
        phase: Animation phase (0-100 for pulse, 0-359 for rotation)
        size: Icon size in pixels (default 64, tray will scale)

    Returns:
        QIcon ready for QSystemTrayIcon.setIcon()

    Raises:
        ValueError: If state is not recognized
    """
    valid_states = {"idle", "recording", "processing", "success", "error"}
    if state not in valid_states:
        raise ValueError(f"Invalid state '{state}'. Must be one of {valid_states}")

    # Create transparent pixmap
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Render based on state
    if state == "idle":
        _draw_idle(painter, size)
    elif state == "recording":
        _draw_recording(painter, size, phase)
    elif state == "processing":
        _draw_processing(painter, size, phase)
    elif state == "success":
        _draw_success(painter, size)
    elif state == "error":
        _draw_error(painter, size)

    painter.end()
    return QIcon(pixmap)


def _draw_idle(painter: QPainter, size: int) -> None:
    """Draw idle state - green circle outline."""
    color = QColor(COLORS_DARK["SUCCESS"])  # #34d399
    pen = QPen(color, 3)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Center circle with margin
    margin = size // 6
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)


def _draw_recording(painter: QPainter, size: int, phase: int) -> None:
    """Draw recording state - blue pulsing filled circle.

    Args:
        phase: 0-100, controls opacity via sine wave
    """
    color = QColor(COLORS_DARK["ACCENT_PRIMARY"])  # #4c8eff

    # Calculate pulsing opacity: 0.4 to 1.0
    # opacity = 0.4 + 0.6 * (sin(phase/100 * 2π) + 1) / 2
    normalized_phase = phase / 100.0
    sine_value = math.sin(normalized_phase * 2 * math.pi)
    opacity = 0.4 + 0.6 * (sine_value + 1) / 2
    color.setAlphaF(opacity)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))

    # Filled circle
    margin = size // 6
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)


def _draw_processing(painter: QPainter, size: int, phase: int) -> None:
    """Draw processing state - yellow rotating arc (270° spinner).

    Args:
        phase: 0-359, rotation angle in degrees
    """
    color = QColor(COLORS_DARK["WARNING"])  # #fbbf24
    pen = QPen(color, 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Qt uses 1/16th degree units
    start_angle = phase * 16
    span_angle = 270 * 16  # 270° arc

    margin = size // 6
    painter.drawArc(margin, margin, size - 2 * margin, size - 2 * margin, start_angle, span_angle)


def _draw_success(painter: QPainter, size: int) -> None:
    """Draw success state - green checkmark."""
    color = QColor(COLORS_DARK["SUCCESS"])  # #34d399
    pen = QPen(color, 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    # Checkmark path (relative to size)
    path = QPainterPath()
    center_x = size / 2
    center_y = size / 2
    scale = size / 64.0  # Base size

    # Start point (left side of checkmark)
    path.moveTo(center_x - 12 * scale, center_y)
    # Middle point (bottom of checkmark)
    path.lineTo(center_x - 2 * scale, center_y + 10 * scale)
    # End point (top right)
    path.lineTo(center_x + 14 * scale, center_y - 10 * scale)

    painter.drawPath(path)


def _draw_error(painter: QPainter, size: int) -> None:
    """Draw error state - red X mark."""
    color = QColor(COLORS_DARK["ERROR"])  # #fb7185
    pen = QPen(color, 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    center = size / 2
    offset = size / 4

    # Draw X (two diagonal lines)
    painter.drawLine(
        int(center - offset), int(center - offset),
        int(center + offset), int(center + offset)
    )
    painter.drawLine(
        int(center + offset), int(center - offset),
        int(center - offset), int(center + offset)
    )


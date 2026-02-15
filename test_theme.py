#!/usr/bin/env python3
"""Professional theme showcase for Keyvox UI system.

Demonstrates the complete Keyvox theme system including color tokens,
typography, component variants, and runtime theme switching.

Usage:
    python test_theme.py

Features:
    - Runtime dark/light theme switching
    - Color palette showcase with hex values
    - Typography scale demonstration
    - All component variants in 2-column grid
    - No inline styles (theme-driven only)
"""

import os
import sys
from pathlib import Path

try:
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLineEdit,
        QLabel,
        QComboBox,
        QCheckBox,
        QRadioButton,
        QSlider,
        QProgressBar,
        QFrame,
        QScrollArea,
        QGridLayout,
    )
    from PySide6.QtCore import Qt, Signal, QEvent, QRect
    from PySide6.QtGui import QColor, QPainter, QFont
except ImportError:
    print("ERROR: PySide6 is not installed.")
    print("Install it with: pip install PySide6")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))

try:
    from keyvox.ui.styles import apply_theme
    from keyvox.ui.styles.utils import clear_cache
    from keyvox.ui.styles.tokens import COLORS_DARK, COLORS_LIGHT, FONTS
    from keyvox.ui.window_chrome import (
        Rect,
        cursor_name_for_region,
        detect_resize_region,
        resize_rect,
    )
except ImportError as e:
    print(f"ERROR: Could not import keyvox.ui.styles: {e}")
    print("Make sure you are running this from the keyvox repository root.")
    sys.exit(1)


class ColorSwatch(QWidget):
    """Small colored rectangle with label showing color name and hex value."""

    def __init__(self, color_hex: str, name: str):
        super().__init__()
        self.color_hex = color_hex
        self.name = name
        self.setFixedSize(150, 84)
        self.setToolTip(f"{name}: {color_hex}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Draw color rectangle
        painter.setBrush(QColor(self.color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), 46, 6, 6)

        # Draw label and hex value
        painter.setPen(QColor(self.palette().color(self.foregroundRole())))
        font = painter.font()
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.drawText(
            QRect(0, 52, self.width(), 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.name,
        )

        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(
            QRect(0, 66, self.width(), 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.color_hex,
        )


C_CURSOR_MAP = {
    "arrow": Qt.CursorShape.ArrowCursor,
    "size_h": Qt.CursorShape.SizeHorCursor,
    "size_v": Qt.CursorShape.SizeVerCursor,
    "size_fdiag": Qt.CursorShape.SizeFDiagCursor,
    "size_bdiag": Qt.CursorShape.SizeBDiagCursor,
}


class TitleBar(QFrame):
    """Custom title bar for frameless window controls and drag."""

    minimize_requested = Signal()
    maximize_restore_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str):
        super().__init__()
        self.setProperty("class", "titlebar")
        self.setFixedHeight(42)
        self._dragging = False
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setProperty("class", "titlebar-title")
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.min_btn = QPushButton("—")
        self.min_btn.setProperty("class", "window-control")
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setProperty("class", "window-control")
        self.max_btn.clicked.connect(self.maximize_restore_requested.emit)
        layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setProperty("class", "window-control")
        self.close_btn.setObjectName("WindowCloseControl")
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_btn)

    def _clicked_control(self, event) -> bool:
        target = self.childAt(event.position().toPoint())
        return isinstance(target, QPushButton)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._clicked_control(event):
            win = self.window()
            if win.isMaximized():
                self.maximize_restore_requested.emit()
                center = win.frameGeometry().width() // 2
                top_left = event.globalPosition().toPoint()
                win.move(top_left.x() - center, top_left.y() - 14)
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._clicked_control(event):
            self.maximize_restore_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class FramelessWindow(QMainWindow):
    """Borderless window with full desktop UX: drag, resize, controls."""

    def __init__(self, title: str):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(960, 680)
        self._frame_margin = 8

        self._resize_region = "none"
        self._is_resizing = False
        self._resize_start_global = None
        self._resize_start_rect = None
        self._resize_margin = 8

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        self._root_layout = QVBoxLayout(root)
        self._root_layout.setContentsMargins(self._frame_margin, self._frame_margin, self._frame_margin, self._frame_margin)
        self._root_layout.setSpacing(0)

        self.titlebar = TitleBar(title)
        self.titlebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.titlebar.setProperty("maximized", False)
        self.titlebar.minimize_requested.connect(self.showMinimized)
        self.titlebar.maximize_restore_requested.connect(self.toggle_maximize_restore)
        self.titlebar.close_requested.connect(self.close)
        self._root_layout.addWidget(self.titlebar)

        self.window_body = QFrame()
        self.window_body.setProperty("class", "window-body")
        self.window_body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.window_body.setProperty("maximized", False)
        body_layout = QVBoxLayout(self.window_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.content_host = QWidget()
        self.content_host.setObjectName("ShowcaseContent")
        self.content_layout = QVBoxLayout(self.content_host)
        self.content_layout.setContentsMargins(18, 18, 18, 18)
        self.content_layout.setSpacing(16)
        body_layout.addWidget(self.content_host)
        self._root_layout.addWidget(self.window_body, 1)
        self._apply_window_state_layout()

    def set_content_widget(self, widget: QWidget) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.content_layout.addWidget(widget)

    def toggle_maximize_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.titlebar.max_btn.setText("□")
        else:
            self.showMaximized()
            self.titlebar.max_btn.setText("❐")
        self._apply_window_state_layout()

    def _apply_window_state_layout(self) -> None:
        maximized = self.isMaximized() or self.isFullScreen()
        margin = 0 if maximized else self._frame_margin
        self._root_layout.setContentsMargins(margin, margin, margin, margin)
        for widget in (self.titlebar, self.window_body):
            widget.setProperty("maximized", maximized)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _current_region(self, local_pos) -> str:
        if self.isMaximized():
            return "none"
        return detect_resize_region(
            x=int(local_pos.x()),
            y=int(local_pos.y()),
            width=self.width(),
            height=self.height(),
            margin=self._resize_margin,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            region = self._current_region(event.position())
            if region != "none":
                self._is_resizing = True
                self._resize_region = region
                self._resize_start_global = event.globalPosition().toPoint()
                g = self.geometry()
                self._resize_start_rect = Rect(g.x(), g.y(), g.width(), g.height())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing and self._resize_start_global and self._resize_start_rect:
            delta = event.globalPosition().toPoint() - self._resize_start_global
            new_rect = resize_rect(
                self._resize_start_rect,
                self._resize_region,
                dx=delta.x(),
                dy=delta.y(),
                min_width=self.minimumWidth(),
                min_height=self.minimumHeight(),
            )
            self.setGeometry(new_rect.x, new_rect.y, new_rect.width, new_rect.height)
            event.accept()
            return

        region = self._current_region(event.position())
        self._resize_region = region
        self.setCursor(C_CURSOR_MAP[cursor_name_for_region(region)])
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        self._resize_start_global = None
        self._resize_start_rect = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not self._is_resizing:
            self.unsetCursor()
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._apply_window_state_layout()
        super().changeEvent(event)


class ThemeTestWindow(FramelessWindow):
    """Main theme showcase window with runtime theme switching."""

    def __init__(self):
        super().__init__("Keyvox Theme Showcase")
        self.current_theme = "dark"
        self.setGeometry(100, 100, 1200, 900)
        self._build_ui()

    def _build_ui(self):
        main = QWidget()
        main.setObjectName("ShowcaseContent")
        root = QVBoxLayout(main)
        root.setSpacing(16)
        root.setContentsMargins(8, 8, 8, 8)

        # Top bar: title + theme toggle
        top = QHBoxLayout()
        title = QLabel("Keyvox Theme Showcase")
        title.setProperty("class", "heading")
        top.addWidget(title)
        top.addStretch()
        self.toggle_btn = QPushButton("Switch to Light")
        self.toggle_btn.setProperty("class", "outline")
        self.toggle_btn.clicked.connect(self._toggle_theme)
        top.addWidget(self.toggle_btn)
        root.addLayout(top)

        # Scroll area with grid content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.showcase_grid = QGridLayout(content)
        self.showcase_grid.setSpacing(16)
        self.showcase_grid.setContentsMargins(0, 0, 0, 0)

        self._populate_content()

        scroll.setWidget(content)
        root.addWidget(scroll)
        self.set_content_widget(main)

    def _populate_content(self):
        """Populate the 2-column grid with all showcase sections."""
        while self.showcase_grid.count():
            item = self.showcase_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = 0
        self.showcase_grid.addWidget(self._create_color_swatches(), row, 0)
        self.showcase_grid.addWidget(self._create_typography(), row, 1)
        row += 1
        self.showcase_grid.addWidget(self._create_buttons_section(), row, 0)
        self.showcase_grid.addWidget(self._create_inputs_section(), row, 1)
        row += 1
        self.showcase_grid.addWidget(self._create_selectors_section(), row, 0)
        self.showcase_grid.addWidget(self._create_cards_section(), row, 1)
        row += 1
        self.showcase_grid.addWidget(self._create_status_section(), row, 0)
        self.showcase_grid.addWidget(self._create_other_section(), row, 1)

    def _toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.toggle_btn.setText(
            "Switch to Light" if self.current_theme == "dark" else "Switch to Dark"
        )
        clear_cache()
        apply_theme(QApplication.instance(), self.current_theme, profile="windows-crisp")
        self._populate_content()

    def _create_section_header(self, text: str) -> QLabel:
        header = QLabel(text)
        header.setProperty("class", "subheading")
        return header

    def _create_color_swatches(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Color Palette"))

        colors = COLORS_DARK if self.current_theme == "dark" else COLORS_LIGHT

        grid = QGridLayout()
        grid.setSpacing(8)

        col_count = 4
        idx = 0
        for name, hex_value in colors.items():
            # Skip rgba values that can't be painted as simple hex
            if hex_value.startswith("rgba"):
                continue
            swatch = ColorSwatch(hex_value, name)
            grid.addWidget(swatch, idx // col_count, idx % col_count)
            idx += 1

        layout.addLayout(grid)
        layout.addStretch()
        return section

    def _create_typography(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Typography"))

        samples = [
            ("Display", 24),
            ("Heading 1", 20),
            ("Heading 2", 16),
            ("Body", 14),
            ("Small", 12),
            ("Tiny", 10),
        ]

        for name, size in samples:
            label = QLabel(f"{name} ({size}px) - The quick brown fox")
            font = label.font()
            font.setPixelSize(size)
            label.setFont(font)
            layout.addWidget(label)

        # Font weights
        spacer = QLabel("")
        layout.addWidget(spacer)

        weight_label = QLabel("Font Weights:")
        weight_label.setProperty("class", "secondary")
        layout.addWidget(weight_label)

        for name, weight in [
            ("Regular", QFont.Weight.Normal),
            ("Medium", QFont.Weight.Medium),
            ("Semi-Bold", QFont.Weight.DemiBold),
        ]:
            label = QLabel(f"{name} ({int(weight)})")
            font = label.font()
            font.setWeight(weight)
            label.setFont(font)
            layout.addWidget(label)

        layout.addStretch()
        return section

    def _create_buttons_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Button Variants"))

        # Row 1: main variants
        row1 = QHBoxLayout()
        for label, cls in [("Default", None), ("Primary", "primary"),
                           ("Success", "success"), ("Danger", "error")]:
            btn = QPushButton(label)
            if cls:
                btn.setProperty("class", cls)
            row1.addWidget(btn)
        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: other variants
        row2 = QHBoxLayout()
        btn_ghost = QPushButton("Ghost")
        btn_ghost.setProperty("class", "ghost")
        row2.addWidget(btn_ghost)

        btn_outline = QPushButton("Outline")
        btn_outline.setProperty("class", "outline")
        row2.addWidget(btn_outline)

        btn_disabled = QPushButton("Disabled")
        btn_disabled.setDisabled(True)
        row2.addWidget(btn_disabled)

        btn_icon = QPushButton("\u2699")
        btn_icon.setProperty("class", "icon")
        btn_icon.setMaximumWidth(40)
        row2.addWidget(btn_icon)

        row2.addStretch()
        layout.addLayout(row2)

        layout.addStretch()
        return section

    def _create_inputs_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Input Fields"))

        input_label = QLabel("Text Input:")
        layout.addWidget(input_label)
        text_input = QLineEdit()
        text_input.setPlaceholderText("Enter text here...")
        layout.addWidget(text_input)

        password_label = QLabel("Password Input:")
        layout.addWidget(password_label)
        password_input = QLineEdit()
        password_input.setPlaceholderText("Password...")
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(password_input)

        disabled_label = QLabel("Disabled Input:")
        layout.addWidget(disabled_label)
        disabled_input = QLineEdit()
        disabled_input.setText("This input is disabled")
        disabled_input.setDisabled(True)
        layout.addWidget(disabled_input)

        layout.addStretch()
        return section

    def _create_selectors_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Selectors"))

        combo_label = QLabel("Combo Box:")
        layout.addWidget(combo_label)
        combo = QComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3", "Option 4"])
        layout.addWidget(combo)

        checkbox_label = QLabel("Checkboxes:")
        layout.addWidget(checkbox_label)
        checkbox_row = QHBoxLayout()
        for i in range(1, 4):
            cb = QCheckBox(f"Option {i}")
            if i == 1:
                cb.setChecked(True)
            checkbox_row.addWidget(cb)
        checkbox_row.addStretch()
        layout.addLayout(checkbox_row)

        radio_label = QLabel("Radio Buttons:")
        layout.addWidget(radio_label)
        radio_row = QHBoxLayout()
        for i in range(1, 4):
            rb = QRadioButton(f"Option {i}")
            if i == 1:
                rb.setChecked(True)
            radio_row.addWidget(rb)
        radio_row.addStretch()
        layout.addLayout(radio_row)

        disabled_combo_label = QLabel("Disabled Combo Box:")
        layout.addWidget(disabled_combo_label)
        disabled_combo = QComboBox()
        disabled_combo.addItems(["Disabled Option"])
        disabled_combo.setDisabled(True)
        layout.addWidget(disabled_combo)

        layout.addStretch()
        return section

    def _create_cards_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Card Variants"))

        for card_class, card_title in [
            ("card", "Default Card"),
            ("card-success", "Success Card"),
            ("card-error", "Error Card"),
            ("card-warning", "Warning Card"),
            ("card-highlight", "Highlighted Card"),
        ]:
            card = QFrame()
            card.setProperty("class", card_class)
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(card_title))
            layout.addWidget(card)

        layout.addStretch()
        return section

    def _create_status_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Status & Badges"))

        status_row = QHBoxLayout()
        for text, cls in [("Active", "status-active"), ("Inactive", "status-inactive"),
                          ("Error", "status-error")]:
            label = QLabel(f"  {text}")
            label.setProperty("class", cls)
            status_row.addWidget(label)
        status_row.addStretch()
        layout.addLayout(status_row)

        badge_row = QHBoxLayout()
        for text, cls in [("Default", "badge"), ("Primary", "badge-primary"),
                          ("Success", "badge-success"), ("Error", "badge-error")]:
            label = QLabel(text)
            label.setProperty("class", cls)
            badge_row.addWidget(label)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        layout.addStretch()
        return section

    def _create_other_section(self) -> QFrame:
        section = QFrame()
        section.setProperty("class", "panel")
        layout = QVBoxLayout(section)

        layout.addWidget(self._create_section_header("Other Components"))

        slider_label = QLabel("Slider:")
        layout.addWidget(slider_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(50)
        layout.addWidget(slider)

        progress_label = QLabel("Progress Bar:")
        layout.addWidget(progress_label)
        progress = QProgressBar()
        progress.setValue(75)
        layout.addWidget(progress)

        divider = QFrame()
        divider.setProperty("class", "divider")
        divider.setMaximumHeight(2)
        layout.addWidget(divider)

        section_frame = QFrame()
        section_frame.setProperty("class", "section")
        section_layout = QVBoxLayout(section_frame)
        section_layout.addWidget(QLabel("Section separator above"))
        layout.addWidget(section_frame)

        layout.addStretch()
        return section


def main():
    bundled_fonts = Path(__file__).parent / "keyvox" / "ui" / "fonts"
    if bundled_fonts.exists():
        os.environ.setdefault("QT_QPA_FONTDIR", str(bundled_fonts))

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.Round)
    app = QApplication(sys.argv)
    if sys.platform == "win32":
        crisp_font = QFont("Segoe UI")
        crisp_font.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
        crisp_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        app.setFont(crisp_font)

    try:
        apply_theme(app, "dark", profile="windows-crisp")
        print("[INFO] Dark theme applied successfully")
    except Exception as e:
        print(f"[ERROR] Failed to apply theme: {e}")
        sys.exit(1)

    window = ThemeTestWindow()
    window.show()

    print("[INFO] Theme showcase window opened")
    print("[INFO] Use the toggle button to switch between dark/light themes")
    print("[INFO] Close the window to exit")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


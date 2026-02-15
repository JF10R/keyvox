#!/usr/bin/env python3
"""Professional theme showcase for KeyVox UI system.

Demonstrates the complete KeyVox theme system including color tokens,
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
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter
except ImportError:
    print("ERROR: PySide6 is not installed.")
    print("Install it with: pip install PySide6")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))

try:
    from keyvox.ui.styles import apply_theme
    from keyvox.ui.styles.utils import clear_cache
    from keyvox.ui.styles.tokens import COLORS_DARK, COLORS_LIGHT, FONTS
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
        self.setFixedSize(140, 70)
        self.setToolTip(f"{name}: {color_hex}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw color rectangle
        painter.setBrush(QColor(self.color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), 45, 6, 6)

        # Draw label and hex value
        painter.setPen(QColor(self.palette().color(self.foregroundRole())))
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(0, 52, self.width(), 12, Qt.AlignmentFlag.AlignLeft, self.name)

        font.setPixelSize(9)
        painter.setFont(font)
        painter.drawText(0, 62, self.width(), 12, Qt.AlignmentFlag.AlignLeft, self.color_hex)


class ThemeTestWindow(QMainWindow):
    """Main theme showcase window with runtime theme switching."""

    def __init__(self):
        super().__init__()
        self.current_theme = "dark"
        self.setWindowTitle("KeyVox Theme Showcase")
        self.setGeometry(100, 100, 1200, 900)
        self._build_ui()

    def _build_ui(self):
        main = QWidget()
        self.setCentralWidget(main)
        root = QVBoxLayout(main)
        root.setSpacing(16)
        root.setContentsMargins(24, 24, 24, 24)

        # Top bar: title + theme toggle
        top = QHBoxLayout()
        title = QLabel("KeyVox Theme Showcase")
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
        self.content_layout = QGridLayout(content)
        self.content_layout.setSpacing(16)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        self._populate_content()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _populate_content(self):
        """Populate the 2-column grid with all showcase sections."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row = 0
        self.content_layout.addWidget(self._create_color_swatches(), row, 0)
        self.content_layout.addWidget(self._create_typography(), row, 1)
        row += 1
        self.content_layout.addWidget(self._create_buttons_section(), row, 0)
        self.content_layout.addWidget(self._create_inputs_section(), row, 1)
        row += 1
        self.content_layout.addWidget(self._create_selectors_section(), row, 0)
        self.content_layout.addWidget(self._create_cards_section(), row, 1)
        row += 1
        self.content_layout.addWidget(self._create_status_section(), row, 0)
        self.content_layout.addWidget(self._create_other_section(), row, 1)

    def _toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.toggle_btn.setText(
            "Switch to Light" if self.current_theme == "dark" else "Switch to Dark"
        )
        clear_cache()
        apply_theme(QApplication.instance(), self.current_theme)
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

        for name, weight in [("Regular", 400), ("Medium", 500), ("Semi-Bold", 600)]:
            label = QLabel(f"{name} ({weight})")
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
    app = QApplication(sys.argv)

    try:
        apply_theme(app, "dark")
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

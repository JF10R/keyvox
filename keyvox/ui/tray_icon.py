"""System tray icon with state-aware animations for Keyvox.

Provides visual feedback for recording/processing states via programmatic icons.
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtCore import QTimer, QCoreApplication
from PySide6.QtGui import QAction
from keyvox.ui.icons import render_icon


class KeyvoxTrayIcon(QSystemTrayIcon):
    """System tray icon with animated state feedback.

    States:
        - idle: Green circle outline (default)
        - recording: Blue pulsing circle (while holding hotkey)
        - processing: Yellow rotating spinner (during transcription)
        - success: Green checkmark flash (500ms after successful transcription)
        - error: Red X flash (500ms after transcription error)

    Animations run at 30fps (33ms intervals) when active.
    """

    def __init__(self, parent=None):
        """Initialize tray icon."""
        super().__init__(parent)
        self.setToolTip("Keyvox")

        self._state = "idle"
        self._phase = 0  # Animation phase (0-100 for pulse, 0-359 for rotation)
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._update_animation)
        self._flash_timer = QTimer()
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.set_state("idle"))

        # Set initial icon
        self._update_icon()

        # Create context menu
        self._create_menu()

        # Handle click events
        self.activated.connect(self._on_activated)

    def set_state(self, state: str) -> None:
        """Change icon state and manage animations.

        Args:
            state: One of "idle", "recording", "processing", "success", "error"
        """
        # Stop any ongoing flash
        if self._flash_timer.isActive():
            self._flash_timer.stop()

        self._state = state
        self._phase = 0

        # Manage animation timer
        if state in ("recording", "processing"):
            if not self._animation_timer.isActive():
                self._animation_timer.start(33)  # 30fps
        else:
            if self._animation_timer.isActive():
                self._animation_timer.stop()

        self._update_icon()

    def flash_success(self) -> None:
        """Show success icon for 500ms, then return to idle."""
        self.set_state("success")
        self._flash_timer.start(500)

    def flash_error(self) -> None:
        """Show error icon for 500ms, then return to idle."""
        self.set_state("error")
        self._flash_timer.start(500)

    def _update_animation(self) -> None:
        """Update animation phase and re-render icon.

        Called every 33ms (30fps) when animation is active.
        """
        if self._state == "recording":
            # Pulse: cycle 0-100
            self._phase = (self._phase + 5) % 101
        elif self._state == "processing":
            # Rotation: cycle 0-359
            self._phase = (self._phase + 15) % 360

        self._update_icon()

    def _update_icon(self) -> None:
        """Re-render icon based on current state and phase."""
        icon = render_icon(self._state, self._phase)
        self.setIcon(icon)

    def _create_menu(self) -> None:
        """Create right-click context menu."""
        menu = QMenu()

        # Show/Hide action (future: toggle main window)
        show_action = QAction("Show Window", menu)
        show_action.setEnabled(False)  # Disabled until main window implemented
        menu.addAction(show_action)

        menu.addSeparator()

        # Exit action
        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(self._on_exit)
        menu.addAction(exit_action)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation (click events).

        Args:
            reason: Why the icon was activated (Trigger, DoubleClick, etc.)
        """
        # Future: toggle main window on left-click
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            pass  # Reserved for show/hide main window

    def _on_exit(self) -> None:
        """Handle Exit menu action."""
        QCoreApplication.quit()


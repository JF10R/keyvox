"""Main entry point for KeyVox."""
import argparse
import sys
import warnings

# Suppress transformers FutureWarning about TRANSFORMERS_CACHE
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers.utils.hub")

from .config import load_config
from .recorder import AudioRecorder
from .backends import create_transcriber
from .hotkey import HotkeyManager
from .dictionary import DictionaryManager
from .text_insertion import TextInserter
from .setup_wizard import run_wizard


def _check_single_instance() -> bool:
    """Check if another instance is running (Windows only)."""
    try:
        import win32event
        import win32api
        import winerror

        mutex = win32event.CreateMutex(None, True, "KeyVox_SingleInstance")
        last_error = win32api.GetLastError()

        if last_error == winerror.ERROR_ALREADY_EXISTS:
            return False
        return True
    except ImportError:
        # pywin32 not installed, skip single instance check
        return True


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="KeyVox - Push-to-talk speech-to-text powered by Whisper"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI (CLI mode only)"
    )

    args = parser.parse_args()

    # Run setup wizard if requested
    if args.setup:
        run_wizard()
        return

    # Check for single instance
    if not _check_single_instance():
        print("[ERR] KeyVox is already running")
        print("[INFO] Only one instance can run at a time")
        sys.exit(1)

    # Load configuration
    config = load_config()

    # Initialize components
    print("\n[INFO] Initializing KeyVox...")

    try:
        # Initialize transcriber (loads model into VRAM)
        transcriber = create_transcriber(config)

        # Initialize recorder
        recorder = AudioRecorder(
            sample_rate=config["audio"]["sample_rate"],
            input_device=config["audio"]["input_device"]
        )

        # Initialize dictionary
        dictionary = DictionaryManager.load_from_config(config)

        # Initialize text inserter
        text_inserter_config = config.get("text_insertion", {})
        text_inserter = TextInserter(
            config=text_inserter_config,
            dictionary_corrections=dictionary.corrections
        )

        # Initialize hotkey manager
        hotkey_manager = HotkeyManager(
            hotkey_name=config["hotkey"]["push_to_talk"],
            recorder=recorder,
            transcriber=transcriber,
            dictionary=dictionary,
            auto_paste=config["output"]["auto_paste"],
            paste_method=config["output"]["paste_method"],
            double_tap_to_clipboard=config["output"]["double_tap_to_clipboard"],
            double_tap_timeout=config["output"]["double_tap_timeout"],
            text_inserter=text_inserter
        )

        # Start listening
        print("[OK] KeyVox initialized successfully\n")

        # Headless mode: original CLI-only behavior
        if args.headless:
            print("[INFO] Running in headless mode (no GUI)")
            hotkey_manager.run()
            return

        # GUI mode: system tray with visual feedback
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QSystemTrayIcon
            from keyvox.ui.tray_icon import KeyVoxTrayIcon
            import threading

            # Check system tray availability
            if not QSystemTrayIcon.isSystemTrayAvailable():
                print("[WARN] System tray not available on this platform")
                print("[INFO] Falling back to headless mode")
                hotkey_manager.run()
                return

            # Create Qt application
            app = QApplication(sys.argv)
            app.setQuitOnLastWindowClosed(False)

            # Create tray icon
            tray_icon = KeyVoxTrayIcon()
            tray_icon.setVisible(True)

            # Connect hotkey signals to tray icon
            hotkey_manager.recording_started.connect(lambda: tray_icon.set_state("recording"))
            hotkey_manager.transcription_started.connect(lambda: tray_icon.set_state("processing"))
            hotkey_manager.transcription_completed.connect(lambda text: tray_icon.flash_success())
            hotkey_manager.error_occurred.connect(lambda err: tray_icon.flash_error())

            # Start hotkey listener in background thread
            listener_thread = threading.Thread(target=hotkey_manager.run, daemon=True)
            listener_thread.start()

            print("[INFO] System tray active (right-click tray icon to exit)")
            # Run Qt event loop
            exit_code = app.exec()
            sys.exit(exit_code)

        except ImportError:
            print("[WARN] PySide6 not installed, falling back to headless mode")
            hotkey_manager.run()

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERR] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

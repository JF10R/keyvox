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

        # Initialize hotkey manager
        hotkey_manager = HotkeyManager(
            hotkey_name=config["hotkey"]["push_to_talk"],
            recorder=recorder,
            transcriber=transcriber,
            auto_paste=config["output"]["auto_paste"],
            paste_method=config["output"]["paste_method"]
        )

        # Start listening
        print("[OK] KeyVox initialized successfully\n")
        hotkey_manager.run()

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERR] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

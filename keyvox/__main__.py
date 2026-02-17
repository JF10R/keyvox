"""Main entry point for Keyvox."""
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

        mutex = win32event.CreateMutex(None, True, "Keyvox_SingleInstance")
        last_error = win32api.GetLastError()

        if last_error == winerror.ERROR_ALREADY_EXISTS:
            return False
        return True
    except ImportError:
        # pywin32 not installed, skip single instance check
        return True


def _run_server_mode(config, port: int) -> None:
    """Run Keyvox as WebSocket server."""
    try:
        from .server import KeyvoxServer

        server = KeyvoxServer(config=config, port=port)
        server.run()
    except ModuleNotFoundError as e:
        if getattr(e, "name", "") == "websockets":
            print("[ERR] Missing dependency for server mode: websockets")
            print("[INFO] Install with: pip install -e \".[server]\"")
            sys.exit(1)
        raise
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERR] Fatal error: {e}")
        sys.exit(1)


def _run_headless_mode(config) -> None:
    """Run manual CLI mode (hotkey -> local paste pipeline)."""
    print("\n[INFO] Initializing Keyvox (manual CLI mode)...")

    try:
        transcriber = create_transcriber(config)
        recorder = AudioRecorder(
            sample_rate=config["audio"]["sample_rate"],
            input_device=config["audio"]["input_device"]
        )
        dictionary = DictionaryManager.load_from_config(config)
        text_inserter = TextInserter(
            config=config.get("text_insertion", {}),
            dictionary_corrections=dictionary.corrections
        )
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

        print("[OK] Keyvox initialized successfully\n")
        hotkey_manager.run()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
    except Exception as e:
        print(f"\n[ERR] Fatal error: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Keyvox - Push-to-talk speech-to-text powered by Whisper"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup wizard"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--headless",
        action="store_true",
        help="Run manual CLI mode (hotkey + local paste) [default]"
    )
    mode_group.add_argument(
        "--server",
        action="store_true",
        help="Run as WebSocket server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9876,
        help="WebSocket server port (default: 9876, used with --server)"
    )

    args = parser.parse_args()

    # Run setup wizard if requested
    if args.setup:
        run_wizard()
        return

    # Check for single instance
    if not _check_single_instance():
        print("[ERR] Keyvox is already running")
        print("[INFO] Only one instance can run at a time")
        sys.exit(1)

    # Load configuration
    config = load_config()

    if args.server:
        _run_server_mode(config=config, port=args.port)
        return

    _run_headless_mode(config=config)


if __name__ == "__main__":
    main()

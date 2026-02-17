"""Setup wizard for initial configuration."""
import sounddevice as sd
from pathlib import Path
from .config import save_config
from .hardware import detect_hardware, recommend_model_config


def _list_microphones() -> None:
    """List available input devices."""
    print("\n[INFO] Available microphones:")
    devices = sd.query_devices()

    for idx, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            name = device['name']
            print(f"  [{idx}] {name}")

    print("  [default] System default microphone")


def run_wizard() -> None:
    """Run interactive setup wizard."""
    print("=" * 60)
    print("Keyvox Setup Wizard")
    print("=" * 60)

    hw_info = detect_hardware()
    recommendation = recommend_model_config(hw_info)

    if hw_info["gpu_available"]:
        print(f"[OK] GPU detected: {hw_info['gpu_name']}")
        print(f"[INFO] VRAM: {hw_info['gpu_vram_gb']:.1f} GB")
    else:
        print(f"[INFO] {hw_info['gpu_name']}")

    print(f"\n[INFO] Recommended: {recommendation['reason']}")
    model_input = input(f"Model name [default: {recommendation['name']}]: ").strip()
    model_name = model_input if model_input else recommendation["name"]
    backend = recommendation["backend"]
    device = recommendation["device"]
    compute_type = recommendation["compute_type"]

    # Microphone selection
    _list_microphones()
    mic_input = input("\nMicrophone device [default: default]: ").strip()
    input_device = mic_input if mic_input else "default"

    # Model cache path
    print("\n[INFO] Model cache stores downloaded Whisper models")
    print("[INFO] Leave empty to use default HuggingFace cache (~/.cache/huggingface)")
    cache_input = input("Cache directory [default: HuggingFace default]: ").strip()
    model_cache = cache_input if cache_input else ""

    # Hotkey selection
    print("\n[INFO] Available hotkeys: ctrl_r, ctrl_l, alt_r, alt_l, shift_r, shift_l")
    hotkey_input = input("Push-to-talk key [default: ctrl_r]: ").strip()
    hotkey = hotkey_input if hotkey_input else "ctrl_r"

    # Auto-paste option
    paste_input = input("\nAuto-paste transcription? [Y/n]: ").strip().lower()
    auto_paste = paste_input != 'n'

    # Build config
    config = {
        "model": {
            "backend": backend,
            "name": model_name,
            "device": device,
            "compute_type": compute_type,
        },
        "audio": {
            "input_device": input_device,
            "sample_rate": 16000,
        },
        "hotkey": {
            "push_to_talk": hotkey,
        },
        "paths": {
            "model_cache": model_cache,
        },
        "output": {
            "auto_paste": auto_paste,
        },
    }

    # Save config
    print("\n[INFO] Saving configuration...")
    config_path = Path.cwd() / "config.toml"
    save_config(config_path, config)

    # Download model (warm-up)
    print("\n[INFO] Downloading model (this may take a few minutes)...")
    try:
        import os
        if model_cache:
            os.environ['HF_HOME'] = model_cache
            os.environ['HF_HUB_CACHE'] = str(Path(model_cache) / 'hub')

        from faster_whisper import WhisperModel
        _ = WhisperModel(model_name, device=device, compute_type=compute_type)
        print("[OK] Model downloaded successfully")
    except Exception as e:
        print(f"[WARN] Model download failed: {e}")
        print("[INFO] Model will be downloaded on first run")

    print("\n" + "=" * 60)
    print("[OK] Setup complete!")
    print("Run 'keyvox' to start the application")
    print("=" * 60)


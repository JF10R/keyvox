"""Setup wizard for initial configuration."""
import sounddevice as sd
from pathlib import Path
from typing import Dict, Any
from .config import save_config


def _detect_gpu() -> Dict[str, Any]:
    """Detect GPU capabilities."""
    try:
        import torch

        if not torch.cuda.is_available():
            print("[INFO] No CUDA GPU detected")
            return {"available": False, "vram_gb": 0}

        device_name = torch.cuda.get_device_name(0)
        device_props = torch.cuda.get_device_properties(0)
        vram_bytes = device_props.total_memory
        vram_gb = vram_bytes / (1024 ** 3)

        print(f"[OK] GPU detected: {device_name}")
        print(f"[INFO] VRAM: {vram_gb:.1f} GB")

        return {
            "available": True,
            "name": device_name,
            "vram_gb": vram_gb
        }
    except ImportError:
        print("[WARN] PyTorch not installed, cannot detect GPU")
        return {"available": False, "vram_gb": 0}


def _recommend_model(vram_gb: float) -> str:
    """Recommend model based on VRAM."""
    if vram_gb >= 6:
        return "large-v3-turbo"
    elif vram_gb >= 4:
        return "medium"
    elif vram_gb >= 2:
        return "small"
    else:
        return "tiny"


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

    # Detect GPU
    gpu_info = _detect_gpu()

    # Model selection
    if gpu_info["available"]:
        recommended_model = _recommend_model(gpu_info["vram_gb"])
        print(f"\n[INFO] Recommended model for your GPU: {recommended_model}")
        model_input = input(f"Model name [default: {recommended_model}]: ").strip()
        model_name = model_input if model_input else recommended_model
        device = "cuda"
        compute_type = "float16"
    else:
        print("\n[WARN] No GPU detected, will use CPU (slower)")
        model_name = input("Model name [default: tiny]: ").strip() or "tiny"
        device = "cpu"
        compute_type = "int8"

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


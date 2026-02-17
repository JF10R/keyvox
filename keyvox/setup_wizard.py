"""Setup wizard for initial configuration."""
import os
import re
import sys
import subprocess
import sounddevice as sd
from pathlib import Path
from .config import get_platform_config_dir, save_config
from .hardware import detect_hardware, recommend_model_config


def _torch_installed() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_nvidia_smi() -> dict | None:
    try:
        header = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5
        )
        if header.returncode != 0:
            return None
        match = re.search(r"CUDA Version:\s*(\d+\.\d+)", header.stdout)
        cuda_version = match.group(1) if match else None

        name_out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        gpu_name = name_out.stdout.strip().splitlines()[0] if name_out.returncode == 0 else "Unknown GPU"

        return {"gpu_name": gpu_name, "cuda_version": cuda_version}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _torch_index_url(cuda_version: str | None) -> str:
    if cuda_version:
        major = int(cuda_version.split(".")[0])
        if major >= 12:
            return "https://download.pytorch.org/whl/cu124"
        if major >= 11:
            return "https://download.pytorch.org/whl/cu118"
    return "https://download.pytorch.org/whl/cpu"


def _pip_install(packages: list[str], index_url: str | None = None) -> bool:
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    if index_url:
        cmd += ["--index-url", index_url]
    result = subprocess.run(cmd)
    return result.returncode == 0


def _list_microphones() -> None:
    """List available input devices."""
    print("\n[INFO] Available microphones:")
    devices = sd.query_devices()

    for idx, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            name = device['name']
            print(f"  [{idx}] {name}")

    print("  [default] System default microphone")


def _resolve_hf_hub_cache(model_cache: str) -> Path:
    """Resolve the HuggingFace hub cache directory.

    Priority: HF_HUB_CACHE env > HF_HOME env > model_cache argument > default.
    Matches HuggingFace's own resolution order so we check the same place it writes.
    """
    if "HF_HUB_CACHE" in os.environ:
        return Path(os.environ["HF_HUB_CACHE"])
    if "HF_HOME" in os.environ:
        return Path(os.environ["HF_HOME"]) / "hub"
    if model_cache:
        return Path(model_cache) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _check_model_cached(model_name: str, model_cache: str) -> bool:
    """Return True if the faster-whisper model is already in the HF cache."""
    try:
        from faster_whisper.utils import _MODELS
    except ImportError:
        return False  # faster-whisper not installed, can't check

    # Resolve the actual HuggingFace repo ID for this model name
    repo_id = _MODELS.get(model_name, f"Systran/faster-whisper-{model_name}")

    hub_cache = _resolve_hf_hub_cache(model_cache)
    # HF cache dir name: "models--org--repo"
    repo_dir_name = "models--" + repo_id.replace("/", "--")
    snapshots_dir = hub_cache / repo_dir_name / "snapshots"

    if not snapshots_dir.exists():
        return False

    # Any snapshot that contains model.bin counts as cached
    for snapshot in snapshots_dir.iterdir():
        if snapshot.is_dir() and (snapshot / "model.bin").exists():
            return True

    return False


def run_wizard() -> None:
    """Run interactive setup wizard."""
    print("=" * 60)
    print("Keyvox Setup Wizard")
    print("=" * 60)

    # ── Step 0: torch availability ────────────────────────────────────────────
    if not _torch_installed():
        print("\n[INFO] PyTorch is not installed.")
        nvidia = _detect_nvidia_smi()
        if nvidia:
            print(f"  Detected: {nvidia['gpu_name']}  (CUDA {nvidia['cuda_version']})")
            index_url = _torch_index_url(nvidia["cuda_version"])
            build_tag = index_url.rsplit("/", 1)[-1]  # e.g. "cu124" or "cpu"
            answer = input(
                f"  Install torch (CUDA {build_tag} build)? [Y/n]: "
            ).strip().lower()
            if answer in ("", "y"):
                print(f"  Running: pip install torch --index-url {index_url}")
                if not _pip_install(["torch"], index_url):
                    print("[WARN] torch install failed. Continuing without GPU support.")
            else:
                print("[INFO] Skipping torch install.")
        else:
            answer = input(
                "  No NVIDIA GPU detected. Install CPU-only torch? [Y/n]: "
            ).strip().lower()
            if answer in ("", "y"):
                print("  Running: pip install torch --index-url https://download.pytorch.org/whl/cpu")
                if not _pip_install(["torch"], "https://download.pytorch.org/whl/cpu"):
                    print("[WARN] torch install failed.")

    hw_info = detect_hardware()
    recommendation = recommend_model_config(hw_info)

    if hw_info["gpu_available"]:
        cuda_ver = hw_info.get("cuda_version") or "unknown"
        print(f"[OK] GPU detected: {hw_info['gpu_name']}")
        print(f"[INFO] VRAM: {hw_info['gpu_vram_gb']:.1f} GB  |  CUDA {cuda_ver}")
    else:
        print(f"[INFO] {hw_info['gpu_name']}")

    # Check faster-whisper availability when it's the recommended backend
    fw_available = True
    if recommendation and recommendation.get("backend") == "faster-whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            fw_available = False

    if not fw_available:
        print("\n[WARN] faster-whisper is not installed.")
        answer = input("  Install it now? (pip install faster-whisper) [Y/n]: ").strip().lower()
        if answer in ("", "y"):
            if not _pip_install(["faster-whisper"]):
                print("[WARN] faster-whisper install failed. Transcription will not work.")
        else:
            print("[INFO] Skipping. Run: pip install faster-whisper")

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

    # Save config to platform config dir so it's found from any working directory
    # (e.g. when the backend is spawned by the desktop app rather than run from the repo root)
    print("\n[INFO] Saving configuration...")
    config_path = get_platform_config_dir() / "config.toml"
    save_config(config_path, config)

    # Model warm-up — skip if already cached
    if backend == "faster-whisper":
        if _check_model_cached(model_name, model_cache):
            print(f"\n[OK] Model '{model_name}' already cached — skipping download")
        else:
            print("\n[INFO] Downloading model (this may take a few minutes)...")
            try:
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

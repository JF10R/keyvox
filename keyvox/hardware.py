"""Hardware detection for GPU and VRAM-based model recommendations."""
from typing import Dict, Any, Optional


def detect_hardware() -> Dict[str, Any]:
    """Detect GPU capabilities and VRAM."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {
                "gpu_available": False,
                "gpu_vendor": "none",
                "gpu_name": "No GPU detected",
                "gpu_vram_gb": 0,
                "cuda_version": None,
            }

        device_name = torch.cuda.get_device_name(0)
        try:
            device_props = torch.cuda.get_device_properties(0)
            vram_bytes = device_props.total_memory
            vram_gb = vram_bytes / (1024 ** 3)
        except Exception:
            return {
                "gpu_available": True,
                "gpu_vendor": "nvidia",
                "gpu_name": device_name,
                "gpu_vram_gb": 0,
                "cuda_version": torch.version.cuda,
            }

        return {
            "gpu_available": True,
            "gpu_vendor": "nvidia",
            "gpu_name": device_name,
            "gpu_vram_gb": vram_gb,
            "cuda_version": torch.version.cuda,
        }
    except ImportError:
        return {
            "gpu_available": False,
            "gpu_vendor": "none",
            "gpu_name": "PyTorch not installed",
            "gpu_vram_gb": 0,
            "cuda_version": None,
        }


def recommend_model_config(hw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Recommend model config based on hardware."""
    if hw["gpu_available"] and hw["gpu_vendor"] == "nvidia":
        vram_gb = hw["gpu_vram_gb"]
        if vram_gb >= 6:
            model_name = "large-v3-turbo"
        elif vram_gb >= 4:
            model_name = "medium"
        elif vram_gb >= 2:
            model_name = "small"
        else:
            model_name = "tiny"

        return {
            "backend": "faster-whisper",
            "name": model_name,
            "device": "cuda",
            "compute_type": "float16",
            "reason": f"{hw['gpu_name']} ({vram_gb:.1f}GB) — faster-whisper optimized",
        }

    return {
        "backend": "faster-whisper",
        "name": "tiny",
        "device": "cpu",
        "compute_type": "int8",
        "reason": "No GPU detected — CPU-optimized configuration",
    }

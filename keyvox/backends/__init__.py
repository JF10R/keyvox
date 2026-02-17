"""Backend factory for model-agnostic transcription."""
from typing import Dict, Any
from .base import TranscriberBackend
from ..storage import resolve_model_cache_root


def _detect_best_backend() -> str:
    """Auto-detect the best available backend based on hardware."""
    try:
        import torch
        if torch.cuda.is_available():
            # NVIDIA GPU detected - faster-whisper is fastest
            return "faster-whisper"
    except ImportError:
        pass

    # TODO: Detect AMD/Intel GPU (ROCm, Vulkan, oneAPI)
    # For now, fall back to qwen-asr which works on CPU
    return "qwen-asr"


def create_transcriber(config: Dict[str, Any]) -> TranscriberBackend:
    """Factory function to create the appropriate transcriber backend.

    Args:
        config: Configuration dictionary with model settings

    Returns:
        TranscriberBackend instance

    Raises:
        ValueError: If backend is invalid or dependencies missing
    """
    backend = config["model"].get("backend", "auto")

    # Auto-detect if requested
    if backend == "auto":
        backend = _detect_best_backend()
        print(f"[INFO] Auto-detected backend: {backend}")

    # Model name and parameters
    model_name = config["model"]["name"]
    device = config["model"]["device"]
    compute_type = config["model"]["compute_type"]
    model_cache = str(resolve_model_cache_root(config))

    # Create backend instance
    if backend == "faster-whisper":
        try:
            from .faster_whisper import FasterWhisperBackend
            return FasterWhisperBackend(
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                model_cache=model_cache
            )
        except ImportError as e:
            raise ValueError(
                f"faster-whisper backend requires faster-whisper package. "
                f"Install with: pip install faster-whisper\n"
                f"Error: {e}"
            )

    elif backend == "qwen-asr":
        try:
            from .qwen_asr import QwenASRBackend
            return QwenASRBackend(
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                model_cache=model_cache
            )
        except ImportError as e:
            raise ValueError(
                f"qwen-asr backend requires qwen-asr package. "
                f"Install with: pip install qwen-asr\n"
                f"Error: {e}"
            )

    elif backend == "qwen-asr-vllm":
        try:
            from .qwen_asr_vllm import QwenASRVLLMBackend
            return QwenASRVLLMBackend(
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                model_cache=model_cache
            )
        except ImportError as e:
            raise ValueError(
                f"qwen-asr-vllm backend requires qwen-asr with vLLM (Linux only). "
                f"Install with: pip install qwen-asr[vllm]\n"
                f"Note: vLLM is not supported on Windows. Use 'qwen-asr' instead.\n"
                f"Error: {e}"
            )
        except RuntimeError as e:
            # Platform check failed (Windows)
            raise ValueError(str(e))

    else:
        raise ValueError(
            f"Unknown backend: {backend}. "
            f"Valid options: 'auto', 'faster-whisper', 'qwen-asr', 'qwen-asr-vllm'"
        )


__all__ = ["TranscriberBackend", "create_transcriber"]

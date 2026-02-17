"""Tests for hardware detection and model recommendations."""
import sys
import pytest
from unittest.mock import Mock, patch
from keyvox.hardware import detect_hardware, recommend_model_config


def test_detect_hardware_no_torch():
    """Test graceful fallback when PyTorch is not installed."""
    import importlib
    import keyvox.hardware
    with patch.dict(sys.modules, {"torch": None}):
        importlib.reload(keyvox.hardware)
        try:
            hw = detect_hardware()
            assert hw["gpu_available"] is False
            assert hw["gpu_vendor"] == "none"
            assert hw["gpu_name"] == "PyTorch not installed"
            assert hw["gpu_vram_gb"] == 0
        finally:
            importlib.reload(keyvox.hardware)


def test_detect_hardware_nvidia():
    """Test detection when CUDA GPU is available."""
    import importlib
    import keyvox.hardware
    mock_torch = Mock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.get_device_name.return_value = "NVIDIA RTX 4090"
    mock_props = Mock()
    mock_props.total_memory = 24 * 1024**3
    mock_torch.cuda.get_device_properties.return_value = mock_props

    with patch.dict(sys.modules, {"torch": mock_torch}):
        importlib.reload(keyvox.hardware)
        try:
            hw = detect_hardware()
            assert hw["gpu_available"] is True
            assert hw["gpu_vendor"] == "nvidia"
            assert hw["gpu_name"] == "NVIDIA RTX 4090"
            assert hw["gpu_vram_gb"] == pytest.approx(24.0, abs=0.1)
        finally:
            importlib.reload(keyvox.hardware)


def test_detect_hardware_cuda_no_vram():
    """Test graceful fallback when VRAM query fails."""
    import importlib
    import keyvox.hardware
    mock_torch = Mock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.get_device_name.return_value = "CUDA GPU"
    mock_torch.cuda.get_device_properties.side_effect = RuntimeError("Mock failure")

    with patch.dict(sys.modules, {"torch": mock_torch}):
        importlib.reload(keyvox.hardware)
        try:
            hw = detect_hardware()
            assert hw["gpu_available"] is True
            assert hw["gpu_vendor"] == "nvidia"
            assert hw["gpu_name"] == "CUDA GPU"
            assert hw["gpu_vram_gb"] == 0
        finally:
            importlib.reload(keyvox.hardware)


def test_recommend_nvidia_high_vram():
    """Test recommendation for high-VRAM NVIDIA GPU."""
    hw = {
        "gpu_available": True,
        "gpu_vendor": "nvidia",
        "gpu_name": "NVIDIA RTX 4090",
        "gpu_vram_gb": 8.0,
    }
    rec = recommend_model_config(hw)
    assert rec is not None
    assert rec["backend"] == "faster-whisper"
    assert rec["name"] == "large-v3-turbo"
    assert rec["device"] == "cuda"
    assert rec["compute_type"] == "float16"
    assert "4090" in rec["reason"]
    assert "8.0GB" in rec["reason"]


def test_recommend_nvidia_mid_vram():
    """Test recommendation for mid-VRAM NVIDIA GPU."""
    hw = {
        "gpu_available": True,
        "gpu_vendor": "nvidia",
        "gpu_name": "NVIDIA GTX 1060",
        "gpu_vram_gb": 4.0,
    }
    rec = recommend_model_config(hw)
    assert rec is not None
    assert rec["backend"] == "faster-whisper"
    assert rec["name"] == "medium"
    assert rec["device"] == "cuda"
    assert rec["compute_type"] == "float16"


def test_recommend_nvidia_low_vram():
    """Test recommendation for low-VRAM NVIDIA GPU."""
    hw = {
        "gpu_available": True,
        "gpu_vendor": "nvidia",
        "gpu_name": "NVIDIA GTX 1050",
        "gpu_vram_gb": 2.0,
    }
    rec = recommend_model_config(hw)
    assert rec is not None
    assert rec["backend"] == "faster-whisper"
    assert rec["name"] == "small"
    assert rec["device"] == "cuda"
    assert rec["compute_type"] == "float16"


def test_recommend_cpu_only():
    """Test recommendation when no GPU is available."""
    hw = {
        "gpu_available": False,
        "gpu_vendor": "none",
        "gpu_name": "No GPU detected",
        "gpu_vram_gb": 0,
    }
    rec = recommend_model_config(hw)
    assert rec is not None
    assert rec["backend"] == "faster-whisper"
    assert rec["name"] == "tiny"
    assert rec["device"] == "cpu"
    assert rec["compute_type"] == "int8"
    assert "No GPU" in rec["reason"]

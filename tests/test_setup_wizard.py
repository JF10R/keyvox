"""Tests for setup wizard flows with mocked input/hardware/deps."""
import builtins
import os
import types
from pathlib import Path
from unittest.mock import MagicMock

from keyvox import setup_wizard as wizard
from keyvox import hardware


def test_list_microphones_prints_input_devices(monkeypatch, capsys):
    devices = [
        {"name": "Output Only", "max_input_channels": 0},
        {"name": "Mic A", "max_input_channels": 1},
        {"name": "Mic B", "max_input_channels": 2},
    ]
    monkeypatch.setattr(wizard.sd, "query_devices", lambda: devices)
    wizard._list_microphones()
    out = capsys.readouterr().out
    assert "Mic A" in out
    assert "Mic B" in out
    assert "default" in out


def test_run_wizard_cpu_path_and_download_failure(monkeypatch, tmp_path):
    def fake_detect():
        return {"gpu_available": False, "gpu_vendor": "none", "gpu_name": "No GPU", "gpu_vram_gb": 0}

    def fake_recommend(hw):
        return {
            "backend": "faster-whisper",
            "name": "tiny",
            "device": "cpu",
            "compute_type": "int8",
            "reason": "CPU",
        }

    import keyvox.setup_wizard
    monkeypatch.setattr(keyvox.setup_wizard, "detect_hardware", fake_detect)
    monkeypatch.setattr(keyvox.setup_wizard, "recommend_model_config", fake_recommend)
    monkeypatch.setattr(wizard, "_list_microphones", lambda: None)
    monkeypatch.setattr(wizard, "get_platform_config_dir", lambda: tmp_path)
    monkeypatch.setattr(wizard, "_torch_installed", lambda: True)

    saved = {}

    def fake_save(path, cfg):
        saved["path"] = path
        saved["config"] = cfg

    monkeypatch.setattr(wizard, "save_config", fake_save)

    # "n" skips the faster-whisper install prompt; remaining answers are unchanged
    answers = iter(["n", "", "default", "", "ctrl_r", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("not installed")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    wizard.run_wizard()

    assert saved["path"] == tmp_path / "config.toml"
    assert saved["config"]["model"]["backend"] == "faster-whisper"
    assert saved["config"]["model"]["device"] == "cpu"
    assert saved["config"]["model"]["compute_type"] == "int8"
    assert saved["config"]["output"]["auto_paste"] is True


def test_run_wizard_gpu_path_and_download_success(monkeypatch, tmp_path):
    def fake_detect():
        return {"gpu_available": True, "gpu_vendor": "nvidia", "gpu_name": "RTX 4090", "gpu_vram_gb": 8.0}

    def fake_recommend(hw):
        return {
            "backend": "faster-whisper",
            "name": "large-v3-turbo",
            "device": "cuda",
            "compute_type": "float16",
            "reason": "GPU",
        }

    import keyvox.setup_wizard
    monkeypatch.setattr(keyvox.setup_wizard, "detect_hardware", fake_detect)
    monkeypatch.setattr(keyvox.setup_wizard, "recommend_model_config", fake_recommend)
    monkeypatch.setattr(wizard, "_list_microphones", lambda: None)
    monkeypatch.setattr(wizard, "get_platform_config_dir", lambda: tmp_path)
    monkeypatch.setattr(wizard, "_torch_installed", lambda: True)

    saved = {}
    whisper_calls = {}

    def fake_save(path, cfg):
        saved["path"] = path
        saved["config"] = cfg

    class FakeWhisperModel:
        def __init__(self, model_name, device, compute_type):
            whisper_calls["args"] = (model_name, device, compute_type)

    monkeypatch.setattr(wizard, "save_config", fake_save)
    monkeypatch.setattr(wizard, "_check_model_cached", lambda name, cache: False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    answers = iter(["", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    wizard.run_wizard()

    assert saved["config"]["model"]["backend"] == "faster-whisper"
    assert saved["config"]["model"]["name"] == "large-v3-turbo"
    assert saved["config"]["model"]["device"] == "cuda"
    assert whisper_calls["args"] == ("large-v3-turbo", "cuda", "float16")
    assert saved["config"]["output"]["auto_paste"] is False


def test_run_wizard_sets_hf_cache_env_when_model_cache_provided(monkeypatch, tmp_path):
    def fake_detect():
        return {"gpu_available": True, "gpu_vendor": "nvidia", "gpu_name": "RTX 4090", "gpu_vram_gb": 8.0}

    def fake_recommend(hw):
        return {
            "backend": "faster-whisper",
            "name": "large-v3-turbo",
            "device": "cuda",
            "compute_type": "float16",
            "reason": "GPU",
        }

    import keyvox.setup_wizard
    monkeypatch.setattr(keyvox.setup_wizard, "detect_hardware", fake_detect)
    monkeypatch.setattr(keyvox.setup_wizard, "recommend_model_config", fake_recommend)
    monkeypatch.setattr(wizard, "_list_microphones", lambda: None)
    monkeypatch.setattr(wizard, "get_platform_config_dir", lambda: tmp_path)
    monkeypatch.setattr(wizard, "_torch_installed", lambda: True)

    monkeypatch.setattr(wizard, "save_config", lambda path, cfg: None)
    monkeypatch.setattr(wizard, "_check_model_cached", lambda name, cache: False)

    class FakeWhisperModel:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

    answers = iter(["", "", "D:/models", "", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    wizard.run_wizard()

    assert os.environ["HF_HOME"] == "D:/models"
    assert os.environ["HF_HUB_CACHE"] == str(Path("D:/models") / "hub")


import pytest


@pytest.mark.parametrize("cuda_version,expected_suffix", [
    ("12.1", "cu124"),
    ("11.8", "cu118"),
    (None, "cpu"),
    ("10.2", "cpu"),
])
def test_torch_index_url(cuda_version, expected_suffix):
    url = wizard._torch_index_url(cuda_version)
    assert url.endswith(expected_suffix)


def test_detect_nvidia_smi_found(monkeypatch):
    nvidia_smi_header = (
        "Tue Feb 17 12:00:00 2026\n"
        "+-----------------------------------------------------------------------------+\n"
        "| NVIDIA-SMI 550.54   Driver Version: 550.54   CUDA Version: 12.4            |\n"
        "+-----------------------------------------------------------------------------+\n"
    )
    gpu_name_output = "NVIDIA GeForce RTX 4090\n"

    call_count = [0]

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        if "--query-gpu=name" in cmd:
            result.returncode = 0
            result.stdout = gpu_name_output
        else:
            result.returncode = 0
            result.stdout = nvidia_smi_header
        call_count[0] += 1
        return result

    monkeypatch.setattr(wizard.subprocess, "run", fake_run)
    info = wizard._detect_nvidia_smi()
    assert info is not None
    assert info["gpu_name"] == "NVIDIA GeForce RTX 4090"
    assert info["cuda_version"] == "12.4"


def test_detect_nvidia_smi_not_found(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr(wizard.subprocess, "run", fake_run)
    assert wizard._detect_nvidia_smi() is None


def test_run_wizard_installs_torch_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(wizard, "_torch_installed", lambda: False)
    monkeypatch.setattr(wizard, "_detect_nvidia_smi", lambda: {
        "gpu_name": "RTX 4090", "cuda_version": "12.4"
    })

    pip_calls = {}

    def fake_pip_install(packages, index_url=None):
        pip_calls["packages"] = packages
        pip_calls["index_url"] = index_url
        return True

    monkeypatch.setattr(wizard, "_pip_install", fake_pip_install)

    def fake_detect():
        return {"gpu_available": True, "gpu_vendor": "nvidia", "gpu_name": "RTX 4090", "gpu_vram_gb": 8.0}

    def fake_recommend(hw):
        return {
            "backend": "faster-whisper",
            "name": "large-v3-turbo",
            "device": "cuda",
            "compute_type": "float16",
            "reason": "GPU",
        }

    import keyvox.setup_wizard
    monkeypatch.setattr(keyvox.setup_wizard, "detect_hardware", fake_detect)
    monkeypatch.setattr(keyvox.setup_wizard, "recommend_model_config", fake_recommend)
    monkeypatch.setattr(wizard, "_list_microphones", lambda: None)
    monkeypatch.setattr(wizard, "get_platform_config_dir", lambda: tmp_path)
    monkeypatch.setattr(wizard, "save_config", lambda path, cfg: None)
    monkeypatch.setattr(wizard, "_check_model_cached", lambda name, cache: True)
    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        types.SimpleNamespace(WhisperModel=None),
    )

    # First answer "" accepts torch install; remaining answers fill the wizard
    answers = iter(["", "", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    wizard.run_wizard()

    assert pip_calls["packages"] == ["torch"]
    assert pip_calls["index_url"] == "https://download.pytorch.org/whl/cu124"


# ---------------------------------------------------------------------------
# _resolve_hf_hub_cache branches
# ---------------------------------------------------------------------------

def test_resolve_hf_hub_cache_prefers_hf_hub_cache_env(monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", "D:/hf/hub")
    monkeypatch.delenv("HF_HOME", raising=False)
    assert wizard._resolve_hf_hub_cache("") == Path("D:/hf/hub")


def test_resolve_hf_hub_cache_falls_back_to_hf_home(monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.setenv("HF_HOME", "D:/hf")
    assert wizard._resolve_hf_hub_cache("") == Path("D:/hf") / "hub"


def test_resolve_hf_hub_cache_uses_model_cache_argument(monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    assert wizard._resolve_hf_hub_cache("D:/models") == Path("D:/models") / "hub"


def test_resolve_hf_hub_cache_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    result = wizard._resolve_hf_hub_cache("")
    assert result == Path.home() / ".cache" / "huggingface" / "hub"


# ---------------------------------------------------------------------------
# _pip_install
# ---------------------------------------------------------------------------

def test_pip_install_builds_correct_command(monkeypatch):
    import sys as _sys
    import subprocess as _subprocess
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        import types as _types
        return _types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(wizard.subprocess, "run", fake_run)

    url = "https://download.pytorch.org/whl/cu124"
    result = wizard._pip_install(["torch"], index_url=url)

    assert result is True
    assert "torch" in calls["cmd"]
    assert "--index-url" in calls["cmd"]
    assert url in calls["cmd"]


def test_pip_install_returns_false_on_nonzero_exit(monkeypatch):
    import types as _types

    monkeypatch.setattr(
        wizard.subprocess,
        "run",
        lambda *args, **kwargs: _types.SimpleNamespace(returncode=1),
    )

    assert wizard._pip_install(["torch"]) is False


# ---------------------------------------------------------------------------
# _check_model_cached
# ---------------------------------------------------------------------------

def test_check_model_cached_returns_false_when_faster_whisper_missing(monkeypatch):
    import builtins as _builtins
    orig_import = _builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "faster_whisper.utils":
            raise ImportError("no faster_whisper")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", fake_import)
    assert wizard._check_model_cached("tiny", "") is False


def test_check_model_cached_finds_model_in_snapshots(tmp_path, monkeypatch):
    import sys as _sys
    import types as _types

    # Create cache structure: hub/models--Systran--faster-whisper-tiny/snapshots/abc123/model.bin
    snapshot_dir = tmp_path / "models--Systran--faster-whisper-tiny" / "snapshots" / "abc123"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "model.bin").write_bytes(b"model")

    # Inject fake faster_whisper.utils with _MODELS
    fake_utils = _types.SimpleNamespace(_MODELS={"tiny": "Systran/faster-whisper-tiny"})
    monkeypatch.setitem(_sys.modules, "faster_whisper.utils", fake_utils)

    # _resolve_hf_hub_cache → tmp_path
    monkeypatch.setattr(wizard, "_resolve_hf_hub_cache", lambda cache: tmp_path)

    assert wizard._check_model_cached("tiny", "") is True

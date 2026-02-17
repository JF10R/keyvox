"""Tests for setup wizard flows with mocked input/hardware/deps."""
import builtins
import os
import types
from pathlib import Path

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
    monkeypatch.setattr(wizard.Path, "cwd", lambda: tmp_path)

    saved = {}

    def fake_save(path, cfg):
        saved["path"] = path
        saved["config"] = cfg

    monkeypatch.setattr(wizard, "save_config", fake_save)

    answers = iter(["", "default", "", "ctrl_r", "y"])
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
    monkeypatch.setattr(wizard.Path, "cwd", lambda: tmp_path)

    saved = {}
    whisper_calls = {}

    def fake_save(path, cfg):
        saved["path"] = path
        saved["config"] = cfg

    class FakeWhisperModel:
        def __init__(self, model_name, device, compute_type):
            whisper_calls["args"] = (model_name, device, compute_type)

    monkeypatch.setattr(wizard, "save_config", fake_save)
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
    monkeypatch.setattr(wizard.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(wizard, "save_config", lambda path, cfg: None)

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

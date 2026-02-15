"""Tests for backend factory and backend auto-detection."""
import builtins
import sys
import types

import pytest

import keyvox.backends as backends


def _base_config(backend: str) -> dict:
    return {
        "model": {
            "backend": backend,
            "name": "model-name",
            "device": "cpu",
            "compute_type": "float32",
        },
        "paths": {"model_cache": ""},
    }


def test_detect_best_backend_prefers_faster_whisper_when_cuda_available(monkeypatch):
    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    assert backends._detect_best_backend() == "faster-whisper"


def test_detect_best_backend_falls_back_to_qwen_asr_without_cuda(monkeypatch):
    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    assert backends._detect_best_backend() == "qwen-asr"


def test_detect_best_backend_handles_missing_torch(monkeypatch):
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("torch missing")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert backends._detect_best_backend() == "qwen-asr"


def test_create_transcriber_faster_whisper_success(monkeypatch):
    class FakeBackend:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = types.SimpleNamespace(FasterWhisperBackend=FakeBackend)
    monkeypatch.setitem(__import__("sys").modules, "keyvox.backends.faster_whisper", module)

    result = backends.create_transcriber(_base_config("faster-whisper"))
    assert isinstance(result, FakeBackend)
    assert result.kwargs["model_name"] == "model-name"


def test_create_transcriber_auto_uses_detected_backend(monkeypatch):
    class FakeBackend:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = types.SimpleNamespace(QwenASRBackend=FakeBackend)
    monkeypatch.setitem(__import__("sys").modules, "keyvox.backends.qwen_asr", module)
    monkeypatch.setattr(backends, "_detect_best_backend", lambda: "qwen-asr")

    result = backends.create_transcriber(_base_config("auto"))
    assert isinstance(result, FakeBackend)


def test_create_transcriber_import_error_wrapped_for_faster_whisper(monkeypatch):
    monkeypatch.delitem(sys.modules, "keyvox.backends.faster_whisper", raising=False)
    monkeypatch.setitem(sys.modules, "keyvox.backends.faster_whisper", None)

    with pytest.raises(ValueError, match="Install with: pip install faster-whisper"):
        backends.create_transcriber(_base_config("faster-whisper"))


def test_create_transcriber_import_error_wrapped_for_qwen(monkeypatch):
    monkeypatch.delitem(sys.modules, "keyvox.backends.qwen_asr", raising=False)
    monkeypatch.setitem(sys.modules, "keyvox.backends.qwen_asr", None)

    with pytest.raises(ValueError, match="Install with: pip install qwen-asr"):
        backends.create_transcriber(_base_config("qwen-asr"))


def test_create_transcriber_vllm_runtime_error_wrapped(monkeypatch):
    class FakeBackend:
        def __init__(self, **kwargs):
            raise RuntimeError("linux only")

    module = types.SimpleNamespace(QwenASRVLLMBackend=FakeBackend)
    monkeypatch.setitem(__import__("sys").modules, "keyvox.backends.qwen_asr_vllm", module)

    with pytest.raises(ValueError, match="linux only"):
        backends.create_transcriber(_base_config("qwen-asr-vllm"))


def test_create_transcriber_vllm_import_error_wrapped(monkeypatch):
    monkeypatch.delitem(sys.modules, "keyvox.backends.qwen_asr_vllm", raising=False)
    monkeypatch.setitem(sys.modules, "keyvox.backends.qwen_asr_vllm", None)

    with pytest.raises(ValueError, match="Install with: pip install qwen-asr\\[vllm\\]"):
        backends.create_transcriber(_base_config("qwen-asr-vllm"))


def test_create_transcriber_unknown_backend_raises():
    with pytest.raises(ValueError, match="Unknown backend"):
        backends.create_transcriber(_base_config("bogus"))

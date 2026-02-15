"""Tests for backend implementation modules with mocked third-party deps."""
import os
import types

import numpy as np
import pytest

from keyvox.backends.faster_whisper import FasterWhisperBackend
from keyvox.backends.qwen_asr import QwenASRBackend
from keyvox.backends.qwen_asr_vllm import QwenASRVLLMBackend


def test_faster_whisper_backend_init_and_transcribe(monkeypatch):
    calls = {}

    class Seg:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def __init__(self, model_name, device, compute_type):
            calls["init"] = (model_name, device, compute_type)

        def transcribe(self, audio_array, language=None, vad_filter=False):
            calls["transcribe"] = (len(audio_array), language, vad_filter)
            return [Seg(" hello "), Seg("world")], None

    module = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", module)

    backend = FasterWhisperBackend(model_name="tiny", device="cpu", compute_type="int8")
    text = backend.transcribe(np.array([0.1, 0.2], dtype=np.float32))

    assert calls["init"] == ("tiny", "cpu", "int8")
    assert calls["transcribe"][1:] == (None, False)
    assert text == "hello world"
    assert backend.transcribe(None) == ""


def test_faster_whisper_backend_handles_errors(monkeypatch):
    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            raise RuntimeError("boom")

    module = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", module)
    backend = FasterWhisperBackend()
    assert backend.transcribe(np.array([1.0], dtype=np.float32)) == ""


def test_faster_whisper_backend_sets_model_cache_and_handles_no_speech(monkeypatch):
    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            return [types.SimpleNamespace(text="   ")], None

    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    backend = FasterWhisperBackend(model_cache="D:/cache")
    assert os.environ["HF_HOME"] == "D:/cache"
    assert os.environ["HF_HUB_CACHE"] == os.path.join("D:/cache", "hub")
    assert backend.transcribe(np.array([1.0], dtype=np.float32)) == ""


def test_qwen_backend_init_dtype_mapping_and_transcribe(monkeypatch):
    fake_torch = types.SimpleNamespace(
        float16="F16",
        bfloat16="BF16",
        float32="F32",
    )
    calls = {}

    class FakeModelObj:
        def transcribe(self, audio, language=None):
            calls["transcribe"] = (audio, language)
            return [types.SimpleNamespace(text=" hello qwen ")]

    class FakeQwenModel:
        @staticmethod
        def from_pretrained(model_name, dtype, device_map, max_inference_batch_size, max_new_tokens):
            calls["init"] = (model_name, dtype, device_map, max_inference_batch_size, max_new_tokens)
            return FakeModelObj()

    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))

    backend = QwenASRBackend(model_name="qwen", device="cuda", compute_type="float16")
    text = backend.transcribe(np.array([0.1], dtype=np.float32))

    assert calls["init"][1] == "F16"
    assert text == "hello qwen"
    assert backend.transcribe(None) == ""


def test_qwen_backend_unknown_dtype_falls_back_to_bfloat16(monkeypatch):
    fake_torch = types.SimpleNamespace(
        float16="F16",
        bfloat16="BF16",
        float32="F32",
    )
    calls = {}

    class FakeQwenModel:
        @staticmethod
        def from_pretrained(model_name, dtype, device_map, max_inference_batch_size, max_new_tokens):
            calls["dtype"] = dtype
            return types.SimpleNamespace(transcribe=lambda audio, language=None: [])

    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))
    QwenASRBackend(model_name="qwen", compute_type="unknown")
    assert calls["dtype"] == "BF16"


def test_qwen_backend_transcribe_handles_errors(monkeypatch):
    fake_torch = types.SimpleNamespace(float16="F16", bfloat16="BF16", float32="F32")

    class FakeModelObj:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("boom")

    class FakeQwenModel:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return FakeModelObj()

    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))
    backend = QwenASRBackend()
    assert backend.transcribe(np.array([1.0], dtype=np.float32)) == ""


def test_qwen_backend_sets_model_cache_and_handles_no_speech(monkeypatch):
    fake_torch = types.SimpleNamespace(float16="F16", bfloat16="BF16", float32="F32")

    class FakeModelObj:
        def transcribe(self, *args, **kwargs):
            return []

    class FakeQwenModel:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return FakeModelObj()

    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))
    backend = QwenASRBackend(model_cache="D:/hf")
    assert os.environ["HF_HOME"] == "D:/hf"
    assert os.environ["HF_HUB_CACHE"] == os.path.join("D:/hf", "hub")
    assert backend.transcribe(np.array([1.0], dtype=np.float32)) == ""


def test_qwen_vllm_backend_windows_raises(monkeypatch):
    import keyvox.backends.qwen_asr_vllm as mod

    monkeypatch.setattr(mod.sys, "platform", "win32", raising=False)
    with pytest.raises(RuntimeError, match="not supported on Windows"):
        QwenASRVLLMBackend()


def test_qwen_vllm_backend_success_on_linux(monkeypatch):
    import keyvox.backends.qwen_asr_vllm as mod

    calls = {}

    class FakeModelObj:
        def transcribe(self, audio, language=None):
            calls["transcribe"] = (audio, language)
            return [types.SimpleNamespace(text=" hello vllm ")]

    class FakeQwenModel:
        @staticmethod
        def LLM(model, gpu_memory_utilization, max_inference_batch_size, max_new_tokens):
            calls["init"] = (model, gpu_memory_utilization, max_inference_batch_size, max_new_tokens)
            return FakeModelObj()

    monkeypatch.setattr(mod.sys, "platform", "linux", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))

    backend = QwenASRVLLMBackend(model_name="qwen")
    assert calls["init"][0] == "qwen"
    assert backend.transcribe(np.array([0.2], dtype=np.float32)) == "hello vllm"
    assert backend.transcribe(None) == ""


def test_qwen_vllm_transcribe_handles_errors(monkeypatch):
    import keyvox.backends.qwen_asr_vllm as mod

    class FakeModelObj:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("boom")

    class FakeQwenModel:
        @staticmethod
        def LLM(**kwargs):
            return FakeModelObj()

    monkeypatch.setattr(mod.sys, "platform", "linux", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))

    backend = QwenASRVLLMBackend()
    assert backend.transcribe(np.array([0.1], dtype=np.float32)) == ""


def test_qwen_vllm_backend_sets_model_cache_and_handles_no_speech(monkeypatch):
    import keyvox.backends.qwen_asr_vllm as mod

    class FakeModelObj:
        def transcribe(self, *args, **kwargs):
            return []

    class FakeQwenModel:
        @staticmethod
        def LLM(**kwargs):
            return FakeModelObj()

    monkeypatch.setattr(mod.sys, "platform", "linux", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel))

    backend = QwenASRVLLMBackend(model_cache="D:/kv-cache")
    assert os.environ["HF_HOME"] == "D:/kv-cache"
    assert os.environ["HF_HUB_CACHE"] == os.path.join("D:/kv-cache", "hub")
    assert backend.transcribe(np.array([0.1], dtype=np.float32)) == ""

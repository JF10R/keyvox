"""Tests for audio recorder behavior with mocked sounddevice streams."""
import numpy as np
import pytest

from keyvox.recorder import AudioRecorder
from keyvox import recorder as recorder_module


class _FakeInputStream:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.closed = False
        _FakeInputStream.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def test_start_initializes_stream_and_starts(monkeypatch):
    _FakeInputStream.created.clear()
    monkeypatch.setattr(recorder_module.sd, "InputStream", _FakeInputStream)
    rec = AudioRecorder(sample_rate=22050, input_device="default")

    rec.start()

    assert rec.is_recording is True
    assert rec.input_device is None
    assert len(_FakeInputStream.created) == 1
    assert _FakeInputStream.created[0].started is True
    assert _FakeInputStream.created[0].kwargs["samplerate"] == 22050


def test_start_ignores_repeat_when_already_recording(monkeypatch):
    _FakeInputStream.created.clear()
    monkeypatch.setattr(recorder_module.sd, "InputStream", _FakeInputStream)
    rec = AudioRecorder()
    rec.start()
    rec.start()
    assert len(_FakeInputStream.created) == 1


def test_audio_callback_queues_frames_only_when_recording(monkeypatch):
    monkeypatch.setattr(recorder_module.sd, "InputStream", _FakeInputStream)
    rec = AudioRecorder()
    rec.start()

    chunk = np.array([[0.1], [0.2]], dtype=np.float32)
    rec._audio_callback(chunk, frames=2, time=None, status=None)
    queued = rec.audio_queue.get_nowait()

    assert np.array_equal(queued, chunk)


def test_stop_returns_none_when_not_recording():
    rec = AudioRecorder()
    assert rec.stop() is None


def test_stop_handles_empty_audio_queue(monkeypatch):
    _FakeInputStream.created.clear()
    monkeypatch.setattr(recorder_module.sd, "InputStream", _FakeInputStream)
    rec = AudioRecorder()
    rec.start()
    out = rec.stop()

    assert out is None
    assert rec.stream is None
    assert _FakeInputStream.created[0].stopped is True
    assert _FakeInputStream.created[0].closed is True


def test_start_portaudio_error_prints_devices_and_reraises(monkeypatch, capsys):
    class _ErrorInputStream:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise recorder_module.sd.PortAudioError("no device found")

    monkeypatch.setattr(recorder_module.sd, "InputStream", _ErrorInputStream)
    monkeypatch.setattr(recorder_module.sd, "query_devices", lambda: "device list")

    rec = AudioRecorder()
    with pytest.raises(recorder_module.sd.PortAudioError):
        rec.start()

    out = capsys.readouterr().out
    assert "[ERR]" in out
    assert "device list" in out
    assert "keyvox --setup" in out
    # State should be reset so start() can be retried
    assert rec.is_recording is False
    assert rec.audio_queue is None


def test_stop_concatenates_audio_and_squeezes(monkeypatch):
    _FakeInputStream.created.clear()
    monkeypatch.setattr(recorder_module.sd, "InputStream", _FakeInputStream)
    rec = AudioRecorder(input_device="2")
    rec.start()

    rec._audio_callback(np.array([[0.1], [0.2]], dtype=np.float32), 2, None, None)
    rec._audio_callback(np.array([[0.3]], dtype=np.float32), 1, None, None)
    out = rec.stop()

    assert isinstance(out, np.ndarray)
    assert out.shape == (3,)
    assert np.allclose(out, np.array([0.1, 0.2, 0.3], dtype=np.float32))
    assert rec.input_device == "2"

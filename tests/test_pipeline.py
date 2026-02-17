"""Tests for TranscriptionPipeline worker thread."""
import threading
import time

import numpy as np
import pytest

from keyvox.pipeline import TranscriptionPipeline


class _Transcriber:
    def __init__(self, result="hello"):
        self.result = result
        self.calls = 0
        self.barrier = None  # optional threading.Event to block transcription

    def transcribe(self, audio):
        self.calls += 1
        if self.barrier:
            self.barrier.wait()
        return self.result


class _Dictionary:
    def __init__(self, prefix=""):
        self.prefix = prefix
        self.corrections = {"x": "X"}

    def apply(self, text):
        return f"{self.prefix}{text}"

    @classmethod
    def load_from_config(cls, config):
        inst = cls(prefix="R:")
        return inst


class _TextInserter:
    def __init__(self, config=None, dictionary_corrections=None):
        self.config = config or {}
        self.dictionary_corrections = dictionary_corrections or {}

    def process(self, text):
        return f"P:{text}"


def _make_pipeline(transcriber=None, dictionary=None, text_inserter=None, output_fn=None):
    outputs = []
    if transcriber is None:
        transcriber = _Transcriber("hello")
    if dictionary is None:
        dictionary = _Dictionary()
    if output_fn is None:
        output_fn = lambda text: outputs.append(text)
    pipeline = TranscriptionPipeline(transcriber, dictionary, text_inserter, output_fn)
    return pipeline, outputs


def test_enqueue_triggers_transcription_started_and_completed():
    started = []
    completed = []
    transcriber = _Transcriber("world")
    pipeline, outputs = _make_pipeline(transcriber=transcriber)
    pipeline.transcription_started = lambda: started.append(True)
    pipeline.transcription_completed = lambda text: completed.append(text)

    pipeline.start()
    try:
        audio = np.array([0.1], dtype=np.float32)
        pipeline.enqueue(audio)
        # Wait for worker to process
        deadline = time.monotonic() + 2.0
        while not completed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        pipeline.stop()

    assert started == [True]
    assert completed == ["world"]
    assert outputs == ["world"]
    assert transcriber.calls == 1


def test_pipeline_applies_dictionary_and_text_inserter():
    transcriber = _Transcriber("test")
    dictionary = _Dictionary(prefix="D:")
    inserter = _TextInserter()
    pipeline, outputs = _make_pipeline(
        transcriber=transcriber,
        dictionary=dictionary,
        text_inserter=inserter,
    )

    pipeline.start()
    try:
        pipeline.enqueue(np.array([0.1], dtype=np.float32))
        deadline = time.monotonic() + 2.0
        while not outputs and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        pipeline.stop()

    assert outputs == ["P:D:test"]


def test_pipeline_skips_output_fn_when_transcription_is_empty():
    transcriber = _Transcriber("")
    pipeline, outputs = _make_pipeline(transcriber=transcriber)

    pipeline.start()
    try:
        pipeline.enqueue(np.array([0.1], dtype=np.float32))
        time.sleep(0.15)  # Give worker time to process
    finally:
        pipeline.stop()

    assert outputs == []


def test_replay_last_calls_output_fn_with_last_text():
    transcriber = _Transcriber("previous")
    replayed = []
    pipeline, outputs = _make_pipeline(
        transcriber=transcriber,
        output_fn=lambda text: outputs.append(text),
    )
    pipeline._pipeline = pipeline  # self-reference not needed; just override output_fn
    pipeline._output_fn = lambda text: replayed.append(text)

    pipeline.start()
    try:
        pipeline.enqueue(np.array([0.1], dtype=np.float32))
        deadline = time.monotonic() + 2.0
        while not replayed and time.monotonic() < deadline:
            time.sleep(0.01)

        replayed_before = len(replayed)
        pipeline.replay_last()
    finally:
        pipeline.stop()

    assert replayed_before == 1  # from initial transcription
    assert len(replayed) == 2    # replay added second call
    assert replayed[-1] == "previous"


def test_replay_last_does_nothing_when_no_previous_text(capsys):
    pipeline, outputs = _make_pipeline()
    pipeline.replay_last()
    captured = capsys.readouterr()
    assert "no previous transcription" in captured.out
    assert outputs == []


def test_error_in_transcription_calls_error_occurred():
    errors = []

    class _BoomTranscriber:
        def transcribe(self, audio):
            raise RuntimeError("gpu exploded")

    pipeline, outputs = _make_pipeline(transcriber=_BoomTranscriber())
    pipeline.error_occurred = lambda msg: errors.append(msg)

    pipeline.start()
    try:
        pipeline.enqueue(np.array([0.1], dtype=np.float32))
        deadline = time.monotonic() + 2.0
        while not errors and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        pipeline.stop()

    assert errors == ["gpu exploded"]
    assert outputs == []


def test_reload_config_updates_dictionary_and_inserter():
    completed = []
    transcriber = _Transcriber("word")
    dictionary = _Dictionary(prefix="OLD:")
    inserter = _TextInserter()
    pipeline, outputs = _make_pipeline(
        transcriber=transcriber,
        dictionary=dictionary,
        text_inserter=inserter,
    )
    pipeline.transcription_completed = lambda text: completed.append(text)

    # reload_config uses dictionary.__class__.load_from_config which gives prefix "R:"
    pipeline.reload_config({"text_insertion": {}})

    pipeline.start()
    try:
        pipeline.enqueue(np.array([0.1], dtype=np.float32))
        deadline = time.monotonic() + 2.0
        while not completed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        pipeline.stop()

    # After reload: dictionary prefix is "R:", inserter wraps with "P:"
    assert completed == ["P:R:word"]


def test_stop_joins_worker_thread():
    pipeline, _ = _make_pipeline()
    pipeline.start()
    thread = pipeline._thread
    assert thread is not None and thread.is_alive()
    pipeline.stop()
    assert not thread.is_alive()
    assert pipeline._thread is None


def test_multiple_items_processed_in_order():
    results = []
    transcriber = _Transcriber("")
    call_count = [0]

    def fake_transcribe(audio):
        call_count[0] += 1
        return f"item{call_count[0]}"

    transcriber.transcribe = fake_transcribe
    pipeline, outputs = _make_pipeline(transcriber=transcriber)

    pipeline.start()
    try:
        for _ in range(3):
            pipeline.enqueue(np.array([0.1], dtype=np.float32))
        deadline = time.monotonic() + 3.0
        while len(outputs) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        pipeline.stop()

    assert outputs == ["item1", "item2", "item3"]

"""Basic tests for backend protocol module importability."""
from keyvox.backends.base import TranscriberBackend


def test_transcriber_backend_protocol_exposes_transcribe():
    assert hasattr(TranscriberBackend, "transcribe")


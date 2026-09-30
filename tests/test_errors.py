import pytest
from pipecat.frames.frames import ErrorFrame, OutputImageRawFrame, TTSAudioRawFrame
from pipecat.tests.utils import SleepFrame, run_test
from pipecat.utils.errors import ErrorCategory

from pipecat_bithuman import BitHumanServiceError, BitHumanVideoService

from .fakes import FakeRuntime, factory_for, failing_factory, voiced_pcm
from .test_flow import _tts

SECRET = "sk-test-not-a-real-secret-123456"


class TokenValidationError(Exception):
    """Same name as the SDK's auth error; matched by class name."""


def _errors(up):
    return [f for f in up if isinstance(f, ErrorFrame)]


async def test_start_failure_reports_auth_error_and_passes_audio(monkeypatch):
    monkeypatch.setenv("BITHUMAN_API_SECRET", SECRET)
    service = BitHumanVideoService(
        runtime_factory=failing_factory(TokenValidationError(f"bad secret {SECRET}"))
    )
    down, up = await run_test(service, frames_to_send=[_tts(100)])
    errors = _errors(up)
    assert len(errors) == 1
    assert errors[0].category == ErrorCategory.AUTHENTICATION
    assert SECRET not in errors[0].error
    assert isinstance(errors[0].exception, BitHumanServiceError)
    assert SECRET not in str(errors[0].exception)
    passed = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert sum(len(f.audio) for f in passed) == len(voiced_pcm(100))
    assert not service.is_avatar_ready


async def test_start_failure_without_passthrough_drops_audio():
    service = BitHumanVideoService(
        runtime_factory=failing_factory(RuntimeError("boom")),
        audio_passthrough_on_error=False,
    )
    down, up = await run_test(service, frames_to_send=[_tts(100)])
    assert len(_errors(up)) == 1
    assert not any(isinstance(f, TTSAudioRawFrame) for f in down)


async def test_push_failure_falls_back_once():
    runtime = FakeRuntime(fail_push=RuntimeError("socket closed"))
    service = BitHumanVideoService(runtime_factory=factory_for(runtime))
    down, up = await run_test(service, frames_to_send=[_tts(100), _tts(100)])
    assert len(_errors(up)) == 1
    assert runtime.shutdowns == 1
    assert sum(isinstance(f, TTSAudioRawFrame) for f in down) == 2


async def test_render_crash_reports_error():
    runtime = FakeRuntime(fail_run_after=3)
    service = BitHumanVideoService(runtime_factory=factory_for(runtime))
    down, up = await run_test(service, frames_to_send=[SleepFrame(sleep=0.1)])
    assert "stopped rendering" in _errors(up)[0].error
    assert any(isinstance(f, OutputImageRawFrame) for f in down)
    assert runtime.shutdowns == 1


async def test_stream_end_reports_error():
    service = BitHumanVideoService(runtime_factory=factory_for(FakeRuntime(end_stream=True)))
    _, up = await run_test(service, frames_to_send=[SleepFrame(sleep=0.1)])
    assert "ended unexpectedly" in _errors(up)[0].error


def test_missing_model_path_raises(monkeypatch):
    monkeypatch.delenv("BITHUMAN_MODEL_PATH", raising=False)
    with pytest.raises(ValueError, match="BITHUMAN_MODEL_PATH"):
        BitHumanVideoService()

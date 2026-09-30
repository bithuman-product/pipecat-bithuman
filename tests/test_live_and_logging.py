import os

import pytest
from loguru import logger
from pipecat.frames.frames import OutputImageRawFrame
from pipecat.tests.utils import SleepFrame, run_test

from pipecat_bithuman import BitHumanVideoService

from .fakes import failing_factory
from .test_flow import _tts

SECRET = "sk-test-not-a-real-secret-987654"


async def test_secret_never_logged(monkeypatch):
    monkeypatch.setenv("BITHUMAN_API_SECRET", SECRET)
    lines = []
    sink = logger.add(lines.append, level="TRACE")
    try:
        service = BitHumanVideoService(
            api_secret=SECRET, runtime_factory=failing_factory(RuntimeError(f"denied {SECRET}"))
        )
        await run_test(service, frames_to_send=[_tts(50)])
    finally:
        logger.remove(sink)
    assert lines
    assert not any(SECRET in str(line) for line in lines)


@pytest.mark.live
@pytest.mark.skipif(
    not (os.getenv("BITHUMAN_API_SECRET") and os.getenv("BITHUMAN_MODEL_PATH"))
    or os.getenv("PIPECAT_BITHUMAN_LIVE") != "1",
    reason="live test: set PIPECAT_BITHUMAN_LIVE=1, BITHUMAN_API_SECRET and "
    "BITHUMAN_MODEL_PATH (bills a few seconds of session time)",
)
async def test_live_sdk_renders_frames():
    service = BitHumanVideoService()
    down, _ = await run_test(
        service, frames_to_send=[_tts(1000), SleepFrame(sleep=2.0)], start_timeout=60.0
    )
    assert any(isinstance(f, OutputImageRawFrame) for f in down)

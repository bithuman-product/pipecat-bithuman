from pipecat.frames.frames import (
    CancelFrame,
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

from pipecat_bithuman import BitHumanVideoService

from .fakes import FakeRuntime, factory_for, voiced_pcm
from .test_flow import _tts


async def test_interruption_drops_reply_and_recovers():
    runtime = FakeRuntime()
    service = BitHumanVideoService(runtime_factory=factory_for(runtime))
    down, _ = await run_test(
        service,
        frames_to_send=[
            _tts(2000, ctx="old"),
            SleepFrame(sleep=0.02),
            InterruptionFrame(),
            SleepFrame(sleep=0.05),
            _tts(100, ctx="new"),
            TTSStoppedFrame(context_id="new"),
            SleepFrame(sleep=0.3),
        ],
    )
    assert runtime.interrupts == 1
    assert any(isinstance(f, InterruptionFrame) for f in down)
    old = sum(
        len(f.audio) for f in down if isinstance(f, TTSAudioRawFrame) and f.context_id == "old"
    )
    new = sum(
        len(f.audio) for f in down if isinstance(f, TTSAudioRawFrame) and f.context_id == "new"
    )
    assert old < len(voiced_pcm(2000))  # most of the old reply never played
    assert new == len(voiced_pcm(100))  # the next reply plays in full
    assert sum(isinstance(f, TTSStoppedFrame) for f in down) == 1


async def test_end_frame_drains_then_shuts_down_once():
    runtime = FakeRuntime()
    service = BitHumanVideoService(runtime_factory=factory_for(runtime))
    down, _ = await run_test(service, frames_to_send=[_tts(200)])  # EndFrame right away
    played = sum(len(f.audio) for f in down if isinstance(f, TTSAudioRawFrame))
    assert played == len(voiced_pcm(200))
    assert runtime.flushes == 1
    assert runtime.shutdowns == 1
    assert not service.is_avatar_ready
    await service.cleanup()  # idempotent
    assert runtime.shutdowns == 1


async def test_cancel_closes_without_draining():
    runtime = FakeRuntime()
    service = BitHumanVideoService(runtime_factory=factory_for(runtime))
    await run_test(
        service,
        frames_to_send=[_tts(3000), SleepFrame(sleep=0.02), CancelFrame()],
        send_end_frame=False,
    )
    assert runtime.shutdowns == 1
    assert runtime.pushed  # queued speech was dropped, not played out


def test_stereo_input_is_downmixed():
    import numpy as np

    from pipecat_bithuman.video import _to_mono_int16

    stereo = np.array([100, 300, -200, 0], dtype=np.int16).tobytes()
    mono = np.frombuffer(_to_mono_int16(stereo, 2), dtype=np.int16)
    assert mono.tolist() == [200, -100]

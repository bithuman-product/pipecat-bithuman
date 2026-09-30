from pipecat.frames.frames import (
    OutputImageRawFrame,
    TextFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

from pipecat_bithuman import BitHumanVideoService

from .fakes import SAMPLE_RATE, FakeRuntime, factory_for, voiced_pcm


def _service(runtime, **kwargs):
    return BitHumanVideoService(runtime_factory=factory_for(runtime), **kwargs)


def _tts(ms, ctx="c1", rate=SAMPLE_RATE, channels=1):
    return TTSAudioRawFrame(
        audio=voiced_pcm(ms), sample_rate=rate, num_channels=channels, context_id=ctx
    )


async def test_audio_in_video_and_audio_out():
    runtime = FakeRuntime()
    service = _service(runtime)
    down, up = await run_test(
        service,
        frames_to_send=[
            TTSStartedFrame(context_id="c1"),
            _tts(100),
            _tts(100),
            TTSStoppedFrame(context_id="c1"),
            SleepFrame(sleep=0.3),
        ],
    )
    images = [f for f in down if isinstance(f, OutputImageRawFrame)]
    audio = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert images, "avatar pushed no video"
    assert images[0].format == "RGB" and images[0].size == (6, 4)
    assert images[0].image[:3] == bytes([0, 0, 255])  # BGR blue -> RGB blue
    assert images[0].sync_with_audio is True
    assert sum(len(f.audio) for f in audio) == len(voiced_pcm(200))
    assert all(f.context_id == "c1" for f in audio)
    assert runtime.flushes == 1
    assert not up
    assert service.frame_size == (6, 4)


async def test_stop_frame_held_until_speech_ends():
    service = _service(FakeRuntime())
    down, _ = await run_test(
        service,
        frames_to_send=[_tts(200), TTSStoppedFrame(context_id="c1"), SleepFrame(sleep=0.3)],
    )
    stop_at = next(i for i, f in enumerate(down) if isinstance(f, TTSStoppedFrame))
    last_audio = max(i for i, f in enumerate(down) if isinstance(f, TTSAudioRawFrame))
    assert stop_at > last_audio


async def test_other_frames_pass_through():
    down, _ = await run_test(
        _service(FakeRuntime()),
        frames_to_send=[TextFrame(text="hello"), SleepFrame(sleep=0.05)],
    )
    assert any(isinstance(f, TextFrame) and f.text == "hello" for f in down)

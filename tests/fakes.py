"""A fake bitHuman runtime: no network, no key, no model file."""

import asyncio
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000
CHUNK_BYTES = 640  # 20 ms of 16 kHz int16 mono per avatar frame


@dataclass
class FakeChunk:
    bytes: bytes
    sample_rate: int = SAMPLE_RATE


@dataclass
class FakeFrame:
    bgr_image: np.ndarray | None
    audio_chunk: FakeChunk | None = None
    end_of_speech: bool = False


class FakeRuntime:
    """Speaks pushed audio back 20 ms per frame, then idles."""

    def __init__(self, *, fail_push=None, fail_run_after=None, end_stream=False, tick=0.002):
        self.pushed = bytearray()
        self.push_calls = 0
        self.flushes = 0
        self.interrupts = 0
        self.shutdowns = 0
        self._flushed = False
        self._fail_push = fail_push
        self._fail_run_after = fail_run_after
        self._end_stream = end_stream
        self._tick = tick
        self._image = np.zeros((4, 6, 3), dtype=np.uint8)
        self._image[..., 0] = 255  # pure blue in BGR

    async def push_audio(self, data, sample_rate, last_chunk=True):
        self.push_calls += 1
        if self._fail_push is not None:
            raise self._fail_push
        self.pushed.extend(data)
        self._flushed = False

    async def flush(self):
        self.flushes += 1
        self._flushed = True

    def interrupt(self):
        self.interrupts += 1
        self.pushed.clear()
        self._flushed = False

    async def run(self):
        frames = 0
        while True:
            await asyncio.sleep(self._tick)
            frames += 1
            if self._fail_run_after is not None and frames > self._fail_run_after:
                raise RuntimeError("render crashed")
            if self._end_stream and frames > 3:
                return
            chunk = None
            end = False
            if self.pushed:
                data = bytes(self.pushed[:CHUNK_BYTES])
                del self.pushed[:CHUNK_BYTES]
                chunk = FakeChunk(data)
            if not self.pushed and self._flushed:
                end = True
                self._flushed = False
            yield FakeFrame(self._image, chunk, end)

    async def shutdown(self):
        self.shutdowns += 1


def factory_for(runtime):
    async def _create():
        return runtime

    return _create


def failing_factory(exc):
    async def _create():
        raise exc

    return _create


def voiced_pcm(ms, value=1000):
    samples = SAMPLE_RATE * ms // 1000
    return np.full(samples, value, dtype=np.int16).tobytes()

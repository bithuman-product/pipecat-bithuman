#
# Copyright (c) 2026, bitHuman, Inc.
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""bitHuman video service for Pipecat.

``BitHumanVideoService`` sits between a TTS (or speech-to-speech) service and
the output transport. It sends the bot's speech to a bitHuman avatar that
renders in this process, and pushes the avatar's frames downstream: the
picture as ``OutputImageRawFrame`` and the speech that goes with each picture
as ``TTSAudioRawFrame``, so the mouth and the voice leave together.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterruptionFrame,
    OutputImageRawFrame,
    StartFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.ai_service import AIService
from pipecat.services.settings import ServiceSettings
from pipecat.utils.errors import ErrorCategory

from .runtime import (
    API_SECRET_ENV,
    BitHumanRuntime,
    RuntimeFactory,
    resolve_model_path,
    sdk_runtime_factory,
)

# Exception class names raised by the bitHuman SDK, matched by name so this
# module does not import the SDK (and so wrapped runtimes classify the same way).
_AUTHENTICATION_ERRORS = frozenset(
    {
        "NotAuthorised",
        "TokenError",
        "TokenExpiredError",
        "TokenValidationError",
        "TokenRequestError",
    }
)
_AUTHORIZATION_ERRORS = frozenset({"AccountStatusError"})
_INVALID_REQUEST_ERRORS = frozenset(
    {
        "InvalidAvatar",
        "NotSupported",
        "ModelError",
        "ModelNotFoundError",
        "ModelLoadError",
        "ModelSecurityError",
        "FileNotFoundError",
    }
)
_MISSING_SECRET_HINTS = ("api_secret is required", "no api secret")

_REDACTED = "***"


class BitHumanServiceError(Exception):
    """An error from the bitHuman avatar, with any API secret removed from its text."""


@dataclass
class BitHumanVideoSettings(ServiceSettings):
    """Settings for the bitHuman video service.

    The service has no runtime-updatable settings yet. The avatar model is
    chosen at construction time with ``model_path``.
    """

    pass


@dataclass
class _Reply:
    """One bot reply on its way through the avatar.

    Parameters:
        context_id: The TTS context the reply's audio came from.
        flushed: Whether the end of the reply was sent to the avatar.
        flushed_at: Monotonic time of the flush.
        voiced: Whether the avatar has emitted non-silent audio for it.
        stop_frames: ``TTSStoppedFrame`` s held until the reply finishes playing.
    """

    context_id: str | None
    flushed: bool = False
    flushed_at: float = 0.0
    voiced: bool = False
    stop_frames: list[Frame] = field(default_factory=list)


class BitHumanVideoService(AIService):
    """Lip-synced bitHuman avatar video for a Pipecat bot.

    Place it after the TTS service (or a speech-to-speech LLM) and before
    ``transport.output()``. It consumes ``TTSAudioRawFrame`` and pushes:

    - ``OutputImageRawFrame`` (RGB) for every avatar frame, while talking and
      while idle.
    - ``TTSAudioRawFrame`` (16 kHz mono) with the speech that plays with each
      frame. The input TTS audio is not forwarded, so the voice is the
      avatar's copy and stays paired with the picture.
    - ``TTSStoppedFrame`` only after the avatar has finished speaking the reply.

    On ``InterruptionFrame`` (barge-in) the avatar drops the reply in flight
    and goes back to idle. The avatar opens on ``StartFrame`` and closes on
    ``EndFrame``, ``CancelFrame`` or cleanup, whichever comes first.

    If the avatar cannot start or fails mid-session, the service pushes an
    ``ErrorFrame`` upstream and, by default, passes TTS audio through unchanged
    so the bot keeps talking without video.

    Rendering runs in this process on this machine through the ``bithuman``
    Python SDK, and is metered by active session time (talking or idle).
    """

    Settings = BitHumanVideoSettings
    _settings: Settings

    def __init__(
        self,
        *,
        model_path: str | os.PathLike[str] | None = None,
        api_secret: str | None = None,
        runtime_factory: RuntimeFactory | None = None,
        sync_video_to_audio: bool = True,
        audio_passthrough_on_error: bool = True,
        stop_frame_timeout_s: float = 2.0,
        end_drain_timeout_s: float = 30.0,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the bitHuman video service.

        Args:
            model_path: Path to the avatar's ``.imx`` model file. Defaults to
                the ``BITHUMAN_MODEL_PATH`` environment variable.
            api_secret: bitHuman API secret. Defaults to the
                ``BITHUMAN_API_SECRET`` environment variable (read by the SDK).
                It is never logged.
            runtime_factory: Advanced. An async callable returning an object
                that implements ``BitHumanRuntime``. Replaces the default,
                which opens ``model_path`` with ``bithuman.AsyncBithuman``.
                Useful for tests and for wrapping the SDK.
            sync_video_to_audio: Mark each image with ``sync_with_audio`` so
                the output transport shows it only after the audio before it
                has been sent. Keep the transport's ``video_out_is_live`` off
                (its default) when this is on.
            audio_passthrough_on_error: If the avatar fails, forward TTS audio
                unchanged so the bot still speaks. When False, the audio is
                dropped.
            stop_frame_timeout_s: Release a held ``TTSStoppedFrame`` if the
                avatar has been idle this long after the end of a reply
                without reporting the end of speech.
            end_drain_timeout_s: On ``EndFrame``, the longest wait for queued
                speech to finish playing before the avatar closes.
            settings: Runtime-updatable settings. The service has none yet.
            **kwargs: Additional arguments passed to ``AIService``.

        Raises:
            ValueError: If no avatar model is given and ``runtime_factory`` is
                not set.
        """
        default_settings = self.Settings(model=None)
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(settings=default_settings, **kwargs)

        if runtime_factory is None:
            self._model_path: str | None = resolve_model_path(model_path)
            runtime_factory = sdk_runtime_factory(self._model_path, api_secret)
        else:
            self._model_path = os.fspath(model_path) if model_path is not None else None

        self._runtime_factory = runtime_factory
        # Kept only to scrub secrets out of error text; never logged.
        self._secrets = tuple(
            s
            for s in {api_secret, os.getenv(API_SECRET_ENV), os.getenv("BITHUMAN_API_KEY")}
            if s and s.strip()
        )

        self._sync_video_to_audio = sync_video_to_audio
        self._audio_passthrough_on_error = audio_passthrough_on_error
        self._stop_frame_timeout_s = stop_frame_timeout_s
        self._end_drain_timeout_s = end_drain_timeout_s

        self._runtime: BitHumanRuntime | None = None
        self._render_task: asyncio.Task | None = None
        self._failed = False
        self._closing = False

        self._replies: deque[_Reply] = deque()
        self._drained = asyncio.Event()
        self._drained.set()
        self._discard_audio = False
        self._pending_audio_s = 0.0
        self._last_voiced_at = 0.0
        self._awaiting_first_voice = False
        self._frame_size: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def is_avatar_ready(self) -> bool:
        """Whether the avatar is open and rendering.

        Returns:
            True between a successful start and teardown or failure.
        """
        return self._runtime is not None and not self._failed

    @property
    def frame_size(self) -> tuple[int, int] | None:
        """The avatar's frame size as ``(width, height)``.

        Returns:
            The size of the first frame the avatar produced, or None before it.
        """
        return self._frame_size

    def can_generate_metrics(self) -> bool:
        """Check if this service can generate processing metrics.

        Returns:
            True. TTFB is the time from a reply's first audio in to its first
            voiced avatar frame out.
        """
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, frame: StartFrame):
        """Open the avatar and start pushing its frames.

        Args:
            frame: The start frame.
        """
        await super().start(frame)
        self._closing = False
        await self._open_runtime()

    async def stop(self, frame: EndFrame):
        """Let queued speech finish playing, then close the avatar.

        Args:
            frame: The end frame.
        """
        await super().stop(frame)
        await self._drain_speech()
        await self._teardown()

    async def cancel(self, frame: CancelFrame):
        """Close the avatar now, dropping queued speech.

        Args:
            frame: The cancel frame.
        """
        await super().cancel(frame)
        await self._teardown()

    async def cleanup(self):
        """Release the avatar. Safe to call more than once."""
        await super().cleanup()
        await self._teardown()

    async def _open_runtime(self):
        if self._runtime is not None or self._failed:
            return
        started = time.monotonic()
        try:
            runtime = await self._runtime_factory()
        except Exception as e:
            await self._fail("the bitHuman avatar could not start", e)
            return
        self._runtime = runtime
        logger.debug(f"{self}: avatar ready in {time.monotonic() - started:.2f} s")

    def _start_render_task(self):
        # Started only after StartFrame has gone downstream, so nothing below
        # receives an avatar frame before it has started.
        runtime = self._runtime
        if runtime is None or self._render_task is not None:
            return
        self._render_task = self.create_task(self._render_loop(runtime), name="bithuman_render")

    async def _teardown(self):
        """Idempotent teardown shared by stop(), cancel() and cleanup()."""
        self._closing = True
        await self._cancel_render_task()
        await self._close_runtime()
        self._forget_replies()

    async def _cancel_render_task(self):
        task, self._render_task = self._render_task, None
        if task is not None and task is not asyncio.current_task():
            await self.cancel_task(task)

    async def _close_runtime(self):
        runtime, self._runtime = self._runtime, None
        if runtime is None:
            return
        try:
            await runtime.shutdown()
        except Exception as e:
            logger.warning(f"{self}: closing the avatar failed: {self._redact(str(e))}")

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Route TTS audio to the avatar and pass everything else on.

        Args:
            frame: The frame to process.
            direction: The direction of frame processing.
        """
        await super().process_frame(frame, direction)

        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
        elif isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            self._start_render_task()
        elif isinstance(frame, TTSAudioRawFrame):
            await self._handle_tts_audio(frame)
        elif isinstance(frame, TTSStoppedFrame):
            await self._handle_tts_stopped(frame)
        elif isinstance(frame, InterruptionFrame):
            await self._handle_interruption()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _handle_tts_audio(self, frame: TTSAudioRawFrame):
        runtime = self._runtime
        if runtime is None or self._failed:
            if self._failed and self._audio_passthrough_on_error:
                await self.push_frame(frame)
            return

        audio = _to_mono_int16(frame.audio, frame.num_channels)
        if not audio:
            return

        is_new_reply = not self._replies or self._replies[-1].flushed
        self._open_reply(frame.context_id)
        if is_new_reply and len(self._replies) == 1:
            # TTFB: this reply's first audio in -> its first voiced frame out.
            self._awaiting_first_voice = True
            await self.start_ttfb_metrics()
        self._discard_audio = False
        self._pending_audio_s += len(audio) / 2.0 / float(frame.sample_rate or 1)

        try:
            await runtime.push_audio(audio, frame.sample_rate, last_chunk=False)
        except Exception as e:
            await self._fail("sending audio to the bitHuman avatar failed", e)
            if self._audio_passthrough_on_error:
                await self.push_frame(frame)

    async def _handle_tts_stopped(self, frame: TTSStoppedFrame):
        runtime = self._runtime
        if runtime is None or self._failed or not self._replies:
            await self.push_frame(frame)
            return

        last = self._replies[-1]
        last.stop_frames.append(frame)
        if last.flushed:
            # A stop with no new audio: keep it behind the speech still playing.
            return
        last.flushed = True
        last.flushed_at = time.monotonic()
        try:
            await runtime.flush()
        except Exception as e:
            await self._fail("ending the reply on the bitHuman avatar failed", e)

    async def _handle_interruption(self):
        # The transport stops the bot on interruption, so held stop frames go.
        self._forget_replies()
        self._discard_audio = True
        self._awaiting_first_voice = False
        runtime = self._runtime
        if runtime is None or self._failed:
            return
        try:
            runtime.interrupt()
        except Exception as e:
            await self._fail("interrupting the bitHuman avatar failed", e)

    def _open_reply(self, context_id: str | None) -> _Reply:
        if not self._replies or self._replies[-1].flushed:
            self._replies.append(_Reply(context_id=context_id))
            self._drained.clear()
        return self._replies[-1]

    # ------------------------------------------------------------------
    # Avatar output
    # ------------------------------------------------------------------

    async def _render_loop(self, runtime: BitHumanRuntime):
        try:
            async for avatar_frame in runtime.run():
                await self._handle_avatar_frame(avatar_frame)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self._runtime is runtime:
                await self._fail("the bitHuman avatar stopped rendering", e)
            return
        if self._runtime is runtime and not self._closing:
            await self._fail("the bitHuman avatar stream ended unexpectedly", None)

    async def _handle_avatar_frame(self, avatar_frame: Any):
        image = getattr(avatar_frame, "bgr_image", None)
        chunk = getattr(avatar_frame, "audio_chunk", None)
        end_of_speech = bool(getattr(avatar_frame, "end_of_speech", False))
        now = time.monotonic()

        if image is not None:
            await self.push_frame(self._to_output_image(image))

        head = self._replies[0] if self._replies else None
        voiced = False
        if chunk is not None and head is not None and not self._discard_audio:
            data, sample_rate = _chunk_bytes(chunk)
            if data:
                voiced = bool(np.any(np.frombuffer(data, dtype=np.int16)))
                # Leading silence (the avatar filling before it speaks) is
                # dropped; once the reply is voiced every chunk is kept, so
                # pauses inside the reply keep their length.
                if voiced or head.voiced:
                    if voiced and not head.voiced:
                        head.voiced = True
                        if self._awaiting_first_voice:
                            self._awaiting_first_voice = False
                            await self.stop_ttfb_metrics()
                    await self.push_frame(
                        TTSAudioRawFrame(
                            audio=data,
                            sample_rate=sample_rate,
                            num_channels=1,
                            context_id=head.context_id,
                        )
                    )
                    seconds = len(data) / 2.0 / float(sample_rate or 1)
                    self._pending_audio_s = max(0.0, self._pending_audio_s - seconds)
                if voiced:
                    self._last_voiced_at = now

        if head is None or not head.flushed:
            return
        if end_of_speech and not self._discard_audio:
            await self._release_head()
        elif not voiced:
            quiet_since = max(head.flushed_at, self._last_voiced_at)
            if now - quiet_since >= self._stop_frame_timeout_s:
                logger.debug(f"{self}: no end of speech from the avatar; releasing TTSStoppedFrame")
                await self._release_head()

    def _to_output_image(self, bgr: np.ndarray) -> OutputImageRawFrame:
        rgb = np.ascontiguousarray(bgr[:, :, ::-1])
        height, width = rgb.shape[0], rgb.shape[1]
        if self._frame_size is None:
            self._frame_size = (width, height)
            logger.info(
                f"{self}: avatar frames are {width}x{height}; set the transport's "
                f"video_out_width={width} and video_out_height={height} to avoid resizing"
            )
        frame = OutputImageRawFrame(image=rgb.tobytes(), size=(width, height), format="RGB")
        frame.sync_with_audio = self._sync_video_to_audio
        return frame

    async def _release_head(self):
        if not self._replies:
            return
        reply = self._replies.popleft()
        for stop in reply.stop_frames:
            await self.push_frame(stop)
        if not self._replies:
            self._pending_audio_s = 0.0
            self._drained.set()

    async def _release_all(self):
        while self._replies:
            await self._release_head()
        self._drained.set()

    def _forget_replies(self):
        self._replies.clear()
        self._pending_audio_s = 0.0
        self._drained.set()

    async def _drain_speech(self):
        runtime = self._runtime
        if runtime is None or self._failed or not self._replies:
            return
        last = self._replies[-1]
        if not last.flushed:
            last.flushed = True
            last.flushed_at = time.monotonic()
            try:
                await runtime.flush()
            except Exception as e:
                await self._fail("ending the reply on the bitHuman avatar failed", e)
                return
        timeout = min(
            self._end_drain_timeout_s,
            self._pending_audio_s + self._stop_frame_timeout_s + 1.0,
        )
        try:
            await asyncio.wait_for(self._drained.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(f"{self}: queued speech did not finish in {timeout:.1f} s; closing")
            await self._release_all()

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    async def _fail(self, message: str, exception: Exception | None):
        """Report an avatar failure once, close the avatar and fall back."""
        already_failed = self._failed
        self._failed = True
        self._awaiting_first_voice = False
        await self._release_all()

        runtime = self._runtime
        if runtime is not None:
            self._runtime = None
            try:
                await runtime.shutdown()
            except Exception as e:
                logger.warning(f"{self}: closing the avatar failed: {self._redact(str(e))}")

        if already_failed:
            return

        category = self._classify_error(exception) if exception is not None else None
        detail = self._redact(f"{type(exception).__name__}: {exception}") if exception else ""
        error_msg = f"{message}: {detail}" if detail else message
        if self._audio_passthrough_on_error:
            error_msg += " (TTS audio now passes through without video)"

        reported: Exception | None = exception
        if exception is not None and self._contains_secret(exception):
            reported = BitHumanServiceError(detail)
        await self.push_error(error_msg, exception=reported, category=category)

    def _classify_error(self, exception: Exception) -> ErrorCategory | None:
        """Map bitHuman SDK exceptions to Pipecat error categories.

        Args:
            exception: The exception to classify.

        Returns:
            The category, or None to let Pipecat classify it.
        """
        names = {cls.__name__ for cls in type(exception).__mro__}
        if names & _AUTHENTICATION_ERRORS:
            return ErrorCategory.AUTHENTICATION
        if names & _AUTHORIZATION_ERRORS:
            return ErrorCategory.AUTHORIZATION
        if names & _INVALID_REQUEST_ERRORS:
            return ErrorCategory.INVALID_REQUEST
        text = str(exception).lower()
        if any(hint in text for hint in _MISSING_SECRET_HINTS):
            return ErrorCategory.AUTHENTICATION
        return super()._classify_error(exception)

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, _REDACTED)
        return text

    def _contains_secret(self, exception: Exception) -> bool:
        text = f"{exception!s} {exception!r}"
        return any(secret in text for secret in self._secrets)


def _to_mono_int16(audio: bytes, num_channels: int) -> bytes:
    """Downmix interleaved int16 PCM to mono."""
    if num_channels <= 1 or not audio:
        return audio
    samples = np.frombuffer(audio, dtype=np.int16)
    usable = len(samples) - (len(samples) % num_channels)
    frames = samples[:usable].reshape(-1, num_channels).astype(np.int32)
    return frames.mean(axis=1).astype(np.int16).tobytes()


def _chunk_bytes(chunk: Any) -> tuple[bytes, int]:
    """Return ``(int16 bytes, sample_rate)`` from an SDK audio chunk."""
    sample_rate = int(getattr(chunk, "sample_rate", 16000) or 16000)
    data = getattr(chunk, "bytes", None)
    if data is None:
        array = getattr(chunk, "data", None)
        data = b"" if array is None else np.asarray(array, dtype=np.int16).tobytes()
    elif callable(data):
        data = data()
    return bytes(data), sample_rate

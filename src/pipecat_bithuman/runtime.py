#
# Copyright (c) 2026, bitHuman, Inc.
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""The seam between the Pipecat service and the bitHuman Python SDK.

``BitHumanVideoService`` talks to the avatar only through the small
:class:`BitHumanRuntime` protocol below. The default factory builds it from
``bithuman.AsyncBithuman``, the SDK's live-streaming class. Tests (and anyone
who wants to wrap the SDK) pass their own ``runtime_factory`` instead.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

API_SECRET_ENV = "BITHUMAN_API_SECRET"
MODEL_PATH_ENV = "BITHUMAN_MODEL_PATH"


@runtime_checkable
class BitHumanRuntime(Protocol):
    """What the service needs from a live bitHuman avatar.

    ``bithuman.AsyncBithuman`` satisfies this protocol as is.
    """

    async def push_audio(self, data: bytes, sample_rate: int, last_chunk: bool = True) -> None:
        """Queue int16 little-endian mono PCM for the avatar to speak.

        Args:
            data: Raw int16 PCM bytes, mono.
            sample_rate: Sample rate of ``data`` in hertz. The SDK resamples.
            last_chunk: Whether this chunk ends the current reply.
        """
        ...

    async def flush(self) -> None:
        """Mark the end of the current reply."""
        ...

    def interrupt(self) -> None:
        """Drop the reply in flight (barge-in) and stay ready for the next one."""
        ...

    def run(self) -> AsyncIterator[Any]:
        """Yield frames at the model's play rate.

        Each frame has ``bgr_image`` (an ``(H, W, 3)`` uint8 BGR array or
        None), ``audio_chunk`` (the audio that plays with this frame, or None
        when idle) and ``end_of_speech`` (True on the last frame of a reply).

        Returns:
            An async iterator of frames.
        """
        ...

    async def shutdown(self) -> None:
        """Stop rendering and release the model and the credential."""
        ...


RuntimeFactory = Callable[[], Awaitable[BitHumanRuntime]]


def resolve_model_path(model_path: str | os.PathLike[str] | None) -> str:
    """Return the avatar model path, from the argument or ``BITHUMAN_MODEL_PATH``.

    Args:
        model_path: Path to an ``.imx`` avatar model, or None to read the
            environment.

    Returns:
        The model path as a string.

    Raises:
        ValueError: If neither the argument nor the environment names a model.
    """
    value = os.fspath(model_path) if model_path is not None else os.getenv(MODEL_PATH_ENV, "")
    value = value.strip()
    if not value:
        raise ValueError(
            "BitHumanVideoService needs an avatar model: pass model_path='path/to/avatar.imx' "
            f"or set {MODEL_PATH_ENV}. Download one with the Agents API "
            "(https://docs.bithuman.ai/platforms/python)."
        )
    return value


def sdk_runtime_factory(model_path: str, api_secret: str | None = None) -> RuntimeFactory:
    """Build a factory that opens ``model_path`` with ``bithuman.AsyncBithuman``.

    The avatar renders in this process, on this machine. When ``api_secret``
    is None the SDK reads ``BITHUMAN_API_SECRET`` from the environment.

    Args:
        model_path: Path to an ``.imx`` avatar model.
        api_secret: bitHuman API secret, or None to use the environment.

    Returns:
        An async callable that returns a ready :class:`BitHumanRuntime`.
    """

    async def _create() -> BitHumanRuntime:
        try:
            from bithuman import AsyncBithuman
        except ImportError as e:
            raise ImportError(
                "The bitHuman Python SDK is not installed. Install it with "
                "`pip install pipecat-bithuman` (Expression 2 avatars: `pip install "
                '"pipecat-bithuman[expression-2]"`).'
            ) from e

        return await AsyncBithuman.create(model_path=model_path, api_secret=api_secret)

    return _create

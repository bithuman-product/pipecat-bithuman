#
# Copyright (c) 2026, bitHuman, Inc.
#
# SPDX-License-Identifier: BSD-2-Clause
#

"""bitHuman real-time avatar video service for Pipecat.

TTS audio goes in; lip-synced avatar video and the matching audio come out.
See ``BitHumanVideoService``.
"""

from importlib.metadata import PackageNotFoundError, version

from .runtime import (
    API_SECRET_ENV,
    MODEL_PATH_ENV,
    BitHumanRuntime,
    RuntimeFactory,
    resolve_model_path,
    sdk_runtime_factory,
)
from .video import BitHumanServiceError, BitHumanVideoService, BitHumanVideoSettings

try:
    __version__ = version("pipecat-bithuman")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"

__all__ = [
    "API_SECRET_ENV",
    "MODEL_PATH_ENV",
    "BitHumanRuntime",
    "BitHumanServiceError",
    "BitHumanVideoService",
    "BitHumanVideoSettings",
    "RuntimeFactory",
    "resolve_model_path",
    "sdk_runtime_factory",
    "__version__",
]

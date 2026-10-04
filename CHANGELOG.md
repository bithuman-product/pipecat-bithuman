# Changelog

All notable changes to this project are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The repository moved to GitLab: https://gitlab.com/bithuman/sdk/pipecat-bithuman (source, issues, changelog). The package name and `pip install pipecat-bithuman` are unchanged; the GitHub copy is archived and stays readable.

## [0.1.0] - 2026-09-30

### Added

- `BitHumanVideoService`: TTS audio in; lip-synced avatar video (`OutputImageRawFrame`, RGB)
  and paired 16 kHz audio (`TTSAudioRawFrame`) out, rendered in-process by the
  `bithuman` Python SDK.
- `TTSStoppedFrame` is held until the avatar has finished speaking the reply.
- Barge-in: `InterruptionFrame` drops the reply in flight and returns the avatar to idle.
- Lifecycle: the avatar opens on `StartFrame`; `EndFrame` drains queued speech, then closes;
  `CancelFrame` and cleanup close at once. Teardown is idempotent.
- Errors: one `ErrorFrame` per failure with a Pipecat error category; the API secret is
  scrubbed from error text and never logged; TTS audio passes through by default.
- `BitHumanRuntime` protocol and `runtime_factory` for tests and SDK wrappers.
- Minimal Daily example (`examples/bot.py`) and a fake-runtime test suite.
- Tested with Pipecat v1.12.0 and `bithuman` 2.11.18.

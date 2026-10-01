# pipecat-bithuman

A [bitHuman](https://www.bithuman.ai) avatar for your [Pipecat](https://github.com/pipecat-ai/pipecat) bot.
Your TTS audio goes in. A lip-synced avatar video, plus the audio that goes with it, comes out.

The avatar renders in your own process, on your own machine, through the
`bithuman` Python SDK. Both models run live on a standard Linux PC with no GPU.
Expression 2 animates a character from one portrait. Essence 2 is for photoreal people.

Maintained by bitHuman, Inc. (community integration, not maintained by the Pipecat team).

**Tested with Pipecat v1.12.0**, `bithuman` 2.11.18, Python 3.11 to 3.14.

**Demo (30 s):** [docs/demo.mp4](docs/demo.mp4), rendered through a Pipecat pipeline by
[`examples/render_demo.py`](examples/render_demo.py) with the Expression 2 sample avatar Wise Pup.

## Install

```bash
pip install pipecat-bithuman
# Expression 2 avatars (any character from one portrait):
pip install "pipecat-bithuman[expression-2]"
```

## Environment variables

| Variable | Needed | What it is |
| --- | --- | --- |
| `BITHUMAN_API_SECRET` | yes | Your bitHuman API secret. Get one at [www.bithuman.ai](https://www.bithuman.ai). The SDK reads it. This package never logs it. |
| `BITHUMAN_MODEL_PATH` | unless you pass `model_path` | Path to the avatar's `.imx` model file. |

Session time is metered while the avatar is open (talking or idle).
It closes on `EndFrame`, `CancelFrame` or cleanup.

Rendering bills active session time: 2 credits a minute on your own machine. From 2026-10-12, SDK use requires the Creator plan or higher. See docs.bithuman.ai/pricing.

## Usage

Put `BitHumanVideoService` after the TTS service and before `transport.output()`:

```python
from pipecat_bithuman import BitHumanVideoService

avatar = BitHumanVideoService(model_path="avatar.imx")  # secret from BITHUMAN_API_SECRET

pipeline = Pipeline([
    transport.input(), stt, user_aggregator, llm, tts,
    avatar,                      # TTS audio -> avatar video + audio
    transport.output(),
    assistant_aggregator,
])
```

Turn on video out in the transport (`video_out_enabled=True`). The service logs the
frame size on the first frame; set `video_out_width` / `video_out_height` to match.

### What the service does with frames

| In | Out |
| --- | --- |
| `TTSAudioRawFrame` | Sent to the avatar. Not forwarded as is. |
| (avatar frame) | `OutputImageRawFrame` (RGB), while talking and while idle. |
| (avatar audio) | `TTSAudioRawFrame` (16 kHz mono), paired with each picture. |
| `TTSStoppedFrame` | Held until the avatar has finished speaking the reply. |
| `InterruptionFrame` | The avatar drops the reply in flight and goes back to idle. |
| anything else | Passed on unchanged. |

If the avatar cannot start, or fails mid-session, the service pushes one
`ErrorFrame` upstream. By default TTS audio then passes through unchanged, so the bot
keeps talking without video (`audio_passthrough_on_error=False` turns this off).
Error text is scrubbed of the API secret.

### Options

| Argument | Default | Meaning |
| --- | --- | --- |
| `model_path` | `BITHUMAN_MODEL_PATH` | The `.imx` avatar model. |
| `api_secret` | `BITHUMAN_API_SECRET` | The API secret. |
| `sync_video_to_audio` | `True` | Sets `sync_with_audio` on each image. |
| `audio_passthrough_on_error` | `True` | Keep the voice if the avatar fails. |
| `stop_frame_timeout_s` | `2.0` | Release a held `TTSStoppedFrame` after this much quiet. |
| `end_drain_timeout_s` | `30.0` | Longest wait on `EndFrame` for queued speech. |
| `runtime_factory` | SDK | Advanced: your own `BitHumanRuntime` (tests, wrappers). |

## How it maps to the bitHuman Python SDK

| Pipecat | `bithuman.AsyncBithuman` |
| --- | --- |
| `StartFrame` | `AsyncBithuman.create(model_path=..., api_secret=...)`, then `run()` |
| `TTSAudioRawFrame` | `push_audio(pcm, sample_rate, last_chunk=False)` |
| `TTSStoppedFrame` | `flush()` |
| `InterruptionFrame` | `interrupt()` |
| `EndFrame` / `CancelFrame` / cleanup | `shutdown()` |

SDK docs: [docs.bithuman.ai/platforms/python](https://docs.bithuman.ai/platforms/python).

## Run the example

```bash
pip install "pipecat-bithuman[expression-2]" "pipecat-ai[daily,deepgram,openai,cartesia,silero]"
export BITHUMAN_API_SECRET=... BITHUMAN_MODEL_PATH=avatar.imx
export DAILY_ROOM_URL=... DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=... CARTESIA_VOICE_ID=...
python examples/bot.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest            # fakes only: no network, no API secret, no model file
```

One live test talks to the real SDK. It is skipped unless you set
`PIPECAT_BITHUMAN_LIVE=1`, `BITHUMAN_API_SECRET` and `BITHUMAN_MODEL_PATH`.
It opens the avatar for a few seconds, and that time is billed.

## Links

- bitHuman: [www.bithuman.ai](https://www.bithuman.ai)
- Docs: [docs.bithuman.ai](https://docs.bithuman.ai)
- Examples: [github.com/bithuman-product/bithuman-examples](https://github.com/bithuman-product/bithuman-examples)
- Contact: sgu@bithuman.ai

## Licence

BSD 2-Clause, the same as Pipecat. See [LICENSE](LICENSE).
Copyright (c) 2026, bitHuman, Inc.

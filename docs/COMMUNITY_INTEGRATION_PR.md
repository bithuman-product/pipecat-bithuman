# Pipecat docs PR: bitHuman video service (prepared, not submitted)

Target repo: https://github.com/pipecat-ai/docs (fork, then PR).
Rules source: https://github.com/pipecat-ai/pipecat/blob/main/COMMUNITY_INTEGRATIONS.md (checked 2026-09-30).
Template used: `api-reference/server/services/video/anam.mdx`, the community video page (checked 2026-09-30).

Nothing here has been posted. The repo, the PyPI package and the demo video must exist first
(see "Checklist" below).

## 1. Row in `api-reference/server/services/supported-services.mdx`

Add to the **Video** table, in alphabetical order (after Anam, before HeyGen):

```
| [bitHuman](/api-reference/server/services/video/bithuman)   | `uv add pipecat-bithuman`     | Community  |
```

## 2. Navigation in `docs.json`

In the video group's `"pages"` list (next to line 570 on 2026-09-30):

```json
"api-reference/server/services/video/anam",
"api-reference/server/services/video/bithuman",
"api-reference/server/services/video/heygen",
```

In `"redirects"`, following the Anam entry (line 1785 on 2026-09-30):

```json
{
  "source": "/server/services/video/bithuman",
  "destination": "/api-reference/server/services/video/bithuman"
},
```

## 3. New page `api-reference/server/services/video/bithuman.mdx`

Sections follow the Anam page: Overview, Installation, Prerequisites, Configuration, Usage,
Compatibility. The full file text is below (section 3a to 3c).

### 3a. Page head, overview, install, prerequisites

````mdx
---
title: "bitHuman Video Avatar"
sidebarTitle: "bitHuman"
description: "BitHumanVideoService renders a lip-synced bitHuman avatar in your own process from your Pipecat agent's TTS audio."
---

import { CommunityMaintained } from "/snippets/community-maintained.mdx";

<CommunityMaintained
  maintainer="bitHuman"
  maintainerUrl="https://gitlab.com/bithuman"
  repo="https://gitlab.com/bithuman/sdk/pipecat-bithuman"
/>

## Overview

`BitHumanVideoService` takes your bot's TTS audio and turns it into a talking avatar.
It pushes `OutputImageRawFrame` (RGB) and the matching `TTSAudioRawFrame`, so the mouth
and the voice leave together. The avatar renders in your own process through the
`bithuman` Python SDK. Expression 2 animates any character from one portrait;
Essence 2 renders a photoreal person from one portrait.

Interruptions are handled: on `InterruptionFrame` the avatar drops the reply in flight
and goes back to idle.

## Installation

```bash
uv add pipecat-bithuman
# Expression 2 avatars:
uv add "pipecat-bithuman[expression-2]"
```

## Prerequisites

### bitHuman account setup

1. Create an account at [www.bithuman.ai](https://www.bithuman.ai) and create an API secret.
2. Download an avatar model (`.imx`). See [docs.bithuman.ai](https://docs.bithuman.ai/platforms/python).

### Required environment variables

- `BITHUMAN_API_SECRET`: your bitHuman API secret.
- `BITHUMAN_MODEL_PATH`: path to the `.imx` model (or pass `model_path`).

Rendering bills active session time: 2 credits a minute on your own machine. From 2026-10-12, SDK use requires the Creator plan or higher. See docs.bithuman.ai/pricing.
````

### 3b. Configuration

````mdx
## Configuration

Constructor parameters for `BitHumanVideoService`:

<ParamField path="model_path" type="str" default="None">
  Path to the avatar's `.imx` model. Defaults to `BITHUMAN_MODEL_PATH`.
</ParamField>

<ParamField path="api_secret" type="str" default="None">
  bitHuman API secret. Defaults to `BITHUMAN_API_SECRET`. Never logged.
</ParamField>

<ParamField path="sync_video_to_audio" type="bool" default="True">
  Sets `sync_with_audio` on each image so the transport shows it after its audio.
</ParamField>

<ParamField path="audio_passthrough_on_error" type="bool" default="True">
  If the avatar fails, forward TTS audio unchanged so the bot keeps talking.
</ParamField>

<ParamField path="stop_frame_timeout_s" type="float" default="2.0">
  Release a held `TTSStoppedFrame` after this much quiet with no end-of-speech.
</ParamField>

<ParamField path="end_drain_timeout_s" type="float" default="30.0">
  On `EndFrame`, the longest wait for queued speech to finish.
</ParamField>

The service has no runtime-updatable `Settings` yet.

Session time is metered while the avatar is open (talking or idle). It closes on
`EndFrame`, `CancelFrame` or cleanup.
````

### 3c. Usage and compatibility

````mdx
## Usage

```python
from pipecat_bithuman import BitHumanVideoService

avatar = BitHumanVideoService(model_path="avatar.imx")

pipeline = Pipeline(
    [transport.input(), stt, user_aggregator, llm, tts, avatar, transport.output(),
     assistant_aggregator]
)
```

Enable `video_out_enabled=True` on the transport. The service logs the frame size on the
first frame; set `video_out_width` and `video_out_height` to match.

A complete example is in the
[repository](https://gitlab.com/bithuman/sdk/pipecat-bithuman/-/blob/main/examples/bot.py).

## Compatibility

Tested with Pipecat v1.12.0 (Python 3.11+). Check the source repository for the latest
tested version and changelog.
````

Note: the Anam page uses the same `<ParamField>` markup under Configuration (checked 2026-09-30).

## 4. PR title and description

Title: `Add bitHuman video service (community)`

```
Adds bitHuman as a community-maintained video service.

- New page: api-reference/server/services/video/bithuman.mdx
- Row in supported-services.mdx (Video, Community)
- docs.json navigation + redirect

Package: https://pypi.org/project/pipecat-bithuman/
Repo: https://gitlab.com/bithuman/sdk/pipecat-bithuman
Demo video (about 45 s, includes a barge-in): <LINK - main session>
Tested with Pipecat v1.12.0.
Maintainer: bitHuman, Inc. (sgu@bithuman.ai)
```

## 5. COMMUNITY_INTEGRATIONS.md checklist

| Item | Status |
| --- | --- |
| Source code following Pipecat patterns | DONE. `AIService` subclass, like Simli/Tavus |
| Foundational example (single file) | DONE. `examples/bot.py` (compiles; not run: needs Daily + keys) |
| README: intro, install, usage, how to run example | DONE |
| README: Pipecat version compatibility | DONE. "Tested with Pipecat v1.12.0" |
| README: company attribution | DONE. bitHuman, Inc. |
| LICENSE, permissive | DONE. BSD-2-Clause |
| Docstrings | DONE. ruff pydocstyle (google) passes |
| Changelog | DONE. `CHANGELOG.md` 0.1.0 |
| Naming `pipecat-{vendor}` | DONE. `pipecat-bithuman`, class `BitHumanVideoService` |
| setup/cleanup and start/stop/cancel, idempotent cleanup | DONE. Tested |
| Unit tests (optional) | DONE. 14 pass, 1 live test skipped by default |
| `pipecat eval run` on the example | TODO. Needs keys and a model; bills session time |
| Public repo | DONE. https://gitlab.com/bithuman/sdk/pipecat-bithuman (public; the GitHub copy is archived) |
| Published on PyPI | TODO. Owner/main session publishes 0.1.0 (twine by hand) |
| Demo video, 30-60 s, with an interruption | TODO. Main session |
| Docs PR (sections 1-3) | READY after: public repo, PyPI 0.1.0, one live test run (PIPECAT_BITHUMAN_LIVE=1, a few billed seconds on a house avatar), one bot.py run, and the demo video. Not submitted |
| Join Discord, post in `#community-integrations` | TODO. Human only, after the PR |

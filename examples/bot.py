"""Minimal Pipecat bot with a bitHuman avatar, over a Daily room.

Env: BITHUMAN_API_SECRET, BITHUMAN_MODEL_PATH, DAILY_ROOM_URL, DEEPGRAM_API_KEY,
OPENAI_API_KEY, CARTESIA_API_KEY, CARTESIA_VOICE_ID.
"""

import asyncio
import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.workers.runner import WorkerRunner

from pipecat_bithuman import BitHumanVideoService

SYSTEM = "You are Pip, a friendly red panda barista. Keep replies short and warm."


async def main():
    transport = DailyTransport(
        os.environ["DAILY_ROOM_URL"],
        None,
        "Pip",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_out_enabled=True,
            video_out_width=416,   # the wise-pup sample's frame size; the service logs yours
            video_out_height=720,
        ),
    )
    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"])
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id=os.environ["CARTESIA_VOICE_ID"],
    )
    avatar = BitHumanVideoService()  # BITHUMAN_MODEL_PATH + BITHUMAN_API_SECRET

    context = LLMContext([{"role": "system", "content": SYSTEM}])
    aggregators = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            avatar,
            transport.output(),
            aggregators.assistant(),
        ]
    )
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))

    @transport.event_handler("on_first_participant_joined")
    async def on_joined(transport, participant):
        await worker.queue_frame(LLMRunFrame())  # Pip says hello first

    @transport.event_handler("on_participant_left")
    async def on_left(transport, participant, reason):
        await worker.cancel()  # close the avatar: session time stops

    runner = WorkerRunner()
    await runner.add_workers(worker)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())

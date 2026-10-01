"""Render a short demo video through a Pipecat pipeline with BitHumanVideoService.

The speech in a WAV file goes in as TTSAudioRawFrame chunks (as a TTS service would send
them); the service's OutputImageRawFrame pictures and the 16 kHz speech that goes with
them come out and are written to an MP4 with ffmpeg.

    BITHUMAN_API_SECRET=...  BITHUMAN_MODEL_PATH=avatar.imx \
        python examples/render_demo.py speech.wav demo.mp4 [--repeat 2]

Bills the avatar's active session time (see docs.bithuman.ai/pricing). Needs ffmpeg.
"""
import argparse
import asyncio
import subprocess
import tempfile
import wave
from pathlib import Path

from pipecat.frames.frames import OutputImageRawFrame, TTSAudioRawFrame
from pipecat.tests.utils import SleepFrame, run_test

from pipecat_bithuman import BitHumanVideoService

CHUNK_S = 0.04  # 40 ms of speech per frame, like a streaming TTS


def speech_frames(path: Path, repeat: int) -> list[TTSAudioRawFrame]:
    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("speech must be 16-bit mono PCM WAV")
        rate, pcm = w.getframerate(), w.readframes(w.getnframes())
    step = int(rate * CHUNK_S) * 2
    frames = []
    for _ in range(repeat):
        frames += [TTSAudioRawFrame(audio=pcm[i:i + step], sample_rate=rate, num_channels=1,
                                    context_id="demo") for i in range(0, len(pcm), step)]
    return frames


async def render(speech: Path, out: Path, repeat: int) -> None:
    sent = speech_frames(speech, repeat)
    seconds = sum(len(f.audio) / 2 / f.sample_rate for f in sent)
    down, _ = await run_test(BitHumanVideoService(),
                             frames_to_send=sent + [SleepFrame(sleep=3.0)], start_timeout=60.0)
    images = [f for f in down if isinstance(f, OutputImageRawFrame)]
    audio = b"".join(f.audio for f in down if isinstance(f, TTSAudioRawFrame))
    if not images:
        raise SystemExit("no avatar frames came out")
    w, h = images[0].size
    fps = round(len(images) / max(seconds, 0.1))
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        with wave.open(str(wav), "wb") as o:
            o.setnchannels(1), o.setsampwidth(2), o.setframerate(16000), o.writeframes(audio)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-i", str(wav),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for f in images:
            proc.stdin.write(f.image)
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit("ffmpeg failed")
    print(f"{out}: {len(images)} frames at {fps} fps, {w}x{h}, {seconds:.1f} s of speech")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("speech", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    asyncio.run(render(a.speech, a.out, a.repeat))

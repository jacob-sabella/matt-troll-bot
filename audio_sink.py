"""
AudioSink that buffers per-user PCM audio, detects silence, and fires
a callback when an utterance is complete.
"""

import asyncio
import logging
import os
import time
from collections import defaultdict
from typing import Callable, Coroutine

import discord
from discord.ext.voice_recv import AudioSink, VoiceData

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000       # Hz
CHANNELS = 2              # stereo
BYTES_PER_SAMPLE = 2      # 16-bit PCM


class UserBuffer:
    """Accumulates raw PCM bytes and tracks the last time audio was received."""

    def __init__(self):
        self.chunks: list[bytes] = []
        self.last_audio_time: float = 0.0

    def append(self, data: bytes) -> None:
        self.chunks.append(data)
        self.last_audio_time = time.monotonic()

    def flush(self) -> bytes:
        buf = b"".join(self.chunks)
        self.chunks.clear()
        return buf

    def duration(self) -> float:
        """Approximate buffered audio duration in seconds."""
        total_bytes = sum(len(c) for c in self.chunks)
        return total_bytes / (SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE)

    def silence_duration(self) -> float:
        if not self.last_audio_time:
            return 0.0
        return time.monotonic() - self.last_audio_time


# Callback type: async fn(user, pcm_bytes)
TranscriptCallback = Callable[[discord.User | discord.Member, bytes], Coroutine]


class TranscribingSink(AudioSink):
    """
    Receives per-user Opus audio (decoded to PCM by discord-ext-voice-recv),
    buffers it, and invokes `on_utterance` whenever a speaker pauses.
    """

    def __init__(self, on_utterance: TranscriptCallback, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._on_utterance = on_utterance
        self._loop = loop
        self._buffers: dict[int, UserBuffer] = defaultdict(UserBuffer)
        self._silence_threshold = float(os.getenv("SILENCE_THRESHOLD", "1.5"))
        self._min_duration = float(os.getenv("MIN_AUDIO_DURATION", "0.5"))
        self._flush_task: asyncio.Task | None = None

    # --- AudioSink interface ---

    def wants_opus(self) -> bool:
        return False  # Ask discord-ext-voice-recv to decode Opus → PCM for us

    def write(self, user: discord.User | discord.Member, data: VoiceData) -> None:
        if user is None or getattr(user, "bot", False):
            return
        pcm = getattr(data, "pcm", None)
        if not pcm:
            return
        self._buffers[user.id].append(pcm)

    def cleanup(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._buffers.clear()

    # --- Background flush loop ---

    def start_flush_loop(self) -> None:
        """Call after attaching the sink so the polling loop begins."""
        self._flush_task = self._loop.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        """Periodically check each user buffer and flush after silence."""
        while True:
            try:
                await asyncio.sleep(0.05)
                for user_id, buf in list(self._buffers.items()):
                    if not buf.chunks:
                        continue
                    silent_for = buf.silence_duration()
                    if silent_for >= self._silence_threshold:
                        duration = buf.duration()
                        pcm = buf.flush()
                        if duration < self._min_duration:
                            log.debug("Skipping short audio (%.2fs) from user %s", duration, user_id)
                            continue
                        # Resolve user object from the voice client's channel members
                        user = self._resolve_user(user_id)
                        log.debug("Flushing %.2fs of audio from %s", duration, user_id)
                        task = self._loop.create_task(self._on_utterance(user, pcm))
                        task.add_done_callback(self._log_utterance_task_failure)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Transcribing sink flush loop hit an error; continuing.")

    @staticmethod
    def _log_utterance_task_failure(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Utterance callback failed; continuing.")

    @property
    def last_audio_at(self) -> float:
        """Monotonic timestamp of the most recent audio from any user (0 if none yet)."""
        if not self._buffers:
            return 0.0
        return max((b.last_audio_time for b in self._buffers.values()), default=0.0)

    def _resolve_user(self, user_id: int) -> discord.Object:
        """Return the User/Member if available, else a bare Object with the id."""
        if self.voice_client and self.voice_client.channel:
            for member in self.voice_client.channel.members:
                if member.id == user_id:
                    return member
        return discord.Object(id=user_id)

"""Whisper-based audio transcription using faster-whisper."""

import io
import logging
import os
import wave

import numpy as np
from faster_whisper import WhisperModel

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000  # Discord sends audio at 48kHz
CHANNELS = 2         # Discord sends stereo audio


class Transcriber:
    def __init__(self):
        model_size = os.getenv("WHISPER_MODEL", "base")
        device = os.getenv("WHISPER_DEVICE", "auto")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        log.info("Loading Whisper model '%s' on %s (%s)...", model_size, device, compute_type)
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        log.info("Whisper model ready.")

    def transcribe(self, pcm_bytes: bytes) -> str | None:
        """
        Transcribe raw PCM audio bytes (48kHz, stereo, 16-bit signed int).
        Returns the transcribed text, or None if nothing intelligible was detected.
        """
        if not pcm_bytes:
            return None

        # Convert raw PCM to a numpy float32 mono array for Whisper
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        audio /= 32768.0  # Normalize to [-1, 1]

        # Mix stereo down to mono
        if CHANNELS > 1:
            audio = audio.reshape(-1, CHANNELS).mean(axis=1)

        # Resample from 48kHz to 16kHz (Whisper expects 16kHz)
        audio = self._resample(audio, SAMPLE_RATE, 16000)

        segments, info = self.model.transcribe(
            audio,
            language=None,   # auto-detect
            vad_filter=True, # skip non-speech segments
            vad_parameters={"min_silence_duration_ms": 500},
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        if text:
            log.debug("Transcribed (lang=%s, p=%.2f): %s", info.language, info.language_probability, text)
        return text or None

    @staticmethod
    def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple linear interpolation resampling."""
        if orig_sr == target_sr:
            return audio
        ratio = target_sr / orig_sr
        new_len = int(len(audio) * ratio)
        indices = np.linspace(0, len(audio) - 1, new_len)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

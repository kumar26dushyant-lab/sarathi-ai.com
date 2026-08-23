"""
Cached Gemini text-to-speech (WAV) for on-page "Listen" buttons.

Founder rule (Aug 23 2026): use the higher-quality Gemini voice, but avoid ongoing cost. So we
generate each narration ONCE and cache the WAV to disk keyed by the text — replays are then free,
and the only cost is a tiny one-time synth whenever the text actually changes (i.e. when the feature
registry changes). Returns None on ANY failure so callers fall back to the browser's built-in voice
(SpeechSynthesis), which is free and needs no server.

Cache dir lives under the app dir (shared across web workers; PrivateTmp-safe — same lesson as the
doc-splitter fix), gitignored via `var/`.
"""
from __future__ import annotations

import os
import struct
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("sarathi.tts")

_BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR") or os.path.join(_BASE, "var", "tts_cache"))
MAX_CHARS = 6000  # keep well within the TTS model's input window


def _pcm_to_wav(pcm: bytes, rate: int = 24000, ch: int = 1, bits: int = 16) -> bytes:
    br = rate * ch * bits // 8
    ba = ch * bits // 8
    ds = len(pcm)
    return (b"RIFF" + struct.pack("<I", 36 + ds) + b"WAVE" + b"fmt "
            + struct.pack("<IHHIIHH", 16, 1, ch, rate, br, ba, bits)
            + b"data" + struct.pack("<I", ds) + pcm)


def _key(text: str, voice: str) -> str:
    return hashlib.sha256((voice + "|" + text).encode("utf-8")).hexdigest()[:32]


async def _gemini_wav(text: str, voice: str, model: str) -> Optional[bytes]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or not text:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    try:
        async with httpx.AsyncClient(timeout=90.0) as c:
            r = await c.post(url, json=body)
        d = r.json()
        part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
        rate = 24000
        mt = part.get("mimeType", "")
        if "rate=" in mt:
            try:
                rate = int(mt.split("rate=")[1].split(";")[0])
            except Exception:
                pass
        pcm = base64.b64decode(part["data"])
    except Exception as e:  # noqa: BLE001
        logger.info("tts gemini failed: %s", e)
        return None
    return _pcm_to_wav(pcm, rate)


async def cached_wav(text: str, voice: str = "Kore", model: str = "") -> Optional[bytes]:
    """WAV bytes for `text` in `voice`, generated once then served from disk cache. None on failure."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        return None
    model = model or os.getenv("TTS_MODEL", "gemini-2.5-flash-preview-tts")
    fp = CACHE_DIR / (_key(text, voice) + ".wav")
    try:
        if fp.exists():
            return fp.read_bytes()
    except Exception:
        pass
    wav = await _gemini_wav(text, voice, model)
    if wav:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(wav)
        except Exception:
            pass
    return wav

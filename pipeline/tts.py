"""edge-tts (tekin) orqali ovoz yaratish va subtitr bo'laklarini hisoblash."""
import asyncio
import re
import subprocess

import edge_tts


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def synthesize(text, out_path, voice, rate, retries=3):
    for attempt in range(retries):
        try:
            asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(out_path)))
            return audio_duration(out_path)
        except Exception:
            if attempt == retries - 1:
                raise


def caption_chunks(text, duration, max_words=8):
    """Matnni qisqa bo'laklarga bo'lib, har biriga vaqt beradi (harf soniga mutanosib)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    for s in sentences:
        words = s.split()
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))
    chunks = [c for c in chunks if c]
    total = sum(len(c) for c in chunks) or 1
    t, timed = 0.0, []
    for c in chunks:
        d = duration * len(c) / total
        timed.append((t, t + d, c))
        t += d
    return timed

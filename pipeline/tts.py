"""edge-tts (tekin) orqali ovoz yaratish, qahramon gaplarini bola ovozida o'qish va subtitr bo'laklarini hisoblash."""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

import edge_tts

CHILD_VOICE = {"voice": "en-US-AnaNeural", "pitch": "+0Hz"}  # ro'yxatda yo'q qahramonlar uchun
QUOTE = re.compile(r'"([^"]+)"|“([^”]+)”|(?<!\w)\'(.+?[.!?,])\'(?!\w)')


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def synthesize(text, out_path, voice, rate, retries=3, premium=None):
    if premium:
        try:
            premium.speech(text, out_path, voice)
            dur = audio_duration(out_path)
            premium.add_speech_cost(text, dur)
            return dur
        except Exception as e:
            print(f"  ! OpenAI ovozi ishlamadi ({e}), tekin ovozga o'tildi")
    for attempt in range(retries):
        try:
            asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(out_path)))
            return audio_duration(out_path)
        except Exception:
            if attempt == retries - 1:
                raise


def split_dialogue(text, names=(), speaker=None):
    """Matnni bo'laklarga ajratadi: [(matn, gapiruvchi yoki None=ertakchi)], gaplar qo'shtirnoqdan olinadi."""
    quotes = list(QUOTE.finditer(text))
    parts, pos, last = [], 0, speaker if speaker in names else None

    def named(chunk, take_last=False):
        found = sorted((m.start(), n) for n in names for m in re.finditer(rf"\b{re.escape(n.split()[-1])}\b", chunk))
        return (found[-1] if take_last else found[0])[1] if found else None

    for i, q in enumerate(quotes):
        end = quotes[i + 1].start() if i + 1 < len(quotes) else len(text)
        after = re.split(r"(?<=[.!?])\s", text[q.end():end].lstrip())[0]
        before = re.split(r"(?<=[.!?])\s", text[pos:q.start()])[-1]
        last = named(after) or named(before, take_last=True) or last
        if text[pos:q.start()].strip():
            parts.append((text[pos:q.start()].strip(), None))
        parts.append(((q.group(1) or q.group(2) or q.group(3)).strip(), last or "child"))
        pos = q.end()
    if text[pos:].strip():
        parts.append((text[pos:].strip(), None))
    return parts


def speak_scene(text, out_path, voice, rate, premium=None, cast=None, speaker=None):
    """Ertakchi o'z ovozida, qahramon gaplari bola ovozida; bola ovozi ishlamasa butun matnni ertakchi o'qiydi."""
    names = {c["name"]: c for c in cast or [] if c.get("voice")}
    parts = [p for p in split_dialogue(text, names, speaker) if re.search(r"\w", p[0])]
    if not any(who for _, who in parts):
        return synthesize(text, out_path, voice, rate, premium=premium)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for i, (chunk, who) in enumerate(parts):
                f = Path(tmp) / f"{i:02d}.mp3"
                if who:
                    kid = names.get(who, CHILD_VOICE)
                    asyncio.run(edge_tts.Communicate(chunk, kid["voice"], rate=rate, pitch=kid["pitch"]).save(str(f)))
                else:
                    synthesize(chunk, f, voice, rate, premium=premium)
                files.append(f)
            # Ertakchi va bola ovozi balandligi teng bo'lsin, gaplar orasida qisqa nafas
            inputs = [a for f in files for a in ("-i", str(f))]
            chains = "".join(f"[{i}:a]loudnorm=I=-16:TP=-1.5,aresample=44100,aformat=channel_layouts=mono,"
                             f"apad=pad_dur=0.15[a{i}];" for i in range(len(files)))
            mix = "".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[out]"
            subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", chains + mix,
                            "-map", "[out]", "-q:a", "2", str(out_path)], check=True)
        return audio_duration(out_path)
    except Exception as e:
        print(f"  ! Bola ovozi ishlamadi ({e}), matnni ertakchi o'qiydi")
        return synthesize(text, out_path, voice, rate, premium=premium)


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

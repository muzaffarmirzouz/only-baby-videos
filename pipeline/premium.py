"""Pullik rejim: OpenAI rasmlari (gpt-image-2) va OpenAI ovozi (gpt-4o-mini-tts), xarajat hisobi bilan.

Narxlar (USD, 1M token uchun) — https://developers.openai.com/api/docs/pricing (2026-11).
"""
import base64
import io

from openai import OpenAI
from PIL import Image, ImageOps

PRICES = {
    "gpt-image-2": {"text_in": 5.0, "image_out": 30.0},
    "gpt-image-1-mini": {"text_in": 2.0, "image_out": 8.0},
    "gpt-image-1.5": {"text_in": 5.0, "image_out": 32.0},
    "gpt-4o-mini-tts": {"text_in": 0.6, "audio_out": 12.0},
}
# 1 soniya nutq ≈ 20 audio token (gpt-4o-mini-tts ≈ $0.015/daqiqa)
AUDIO_TOKENS_PER_SECOND = 20

# Paneldagi edge-tts ovozlari → OpenAI ovozlari
VOICE_MAP = {
    "en-US-JennyNeural": "coral",
    "en-US-AnaNeural": "shimmer",
    "en-US-AriaNeural": "nova",
    "en-GB-SoniaNeural": "fable",
    "en-US-GuyNeural": "ash",
    "en-US-AndrewNeural": "onyx",
}


class Premium:
    def __init__(self, cfg):
        self.cfg = cfg
        # Standart kutish 10 daqiqa — osilib qolgan so'rov butun videoni to'xtatmasin
        self.client = OpenAI(timeout=180, max_retries=2)
        self.cost = 0.0  # shu video uchun taxminiy xarajat, USD

    # ---------- Rasm ----------

    def image(self, prompt, out_path, width, height):
        model = self.cfg["image_model"]
        size = "1024x1024" if height == width else "1024x1536" if height > width else "1536x1024"
        r = self.client.images.generate(model=model, prompt=prompt[:4000], size=size,
                                        quality=self.cfg["image_quality"], n=1)
        img = Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
        # Video o'lchamiga moslab kesish (3:2 → 16:9 yoki 9:16)
        ImageOps.fit(img, (width, height), Image.LANCZOS).save(out_path, "JPEG", quality=93)
        p = PRICES.get(model, PRICES["gpt-image-2"])
        if r.usage:
            self.cost += (r.usage.input_tokens * p["text_in"] + r.usage.output_tokens * p["image_out"]) / 1e6
        return True

    def sprite(self, look, style, out_path, obj=False):
        """Multik qahramoni yoki narsa (obj=True) — fonsiz shaffof PNG. gpt-image-2 shaffof fonni qo'llamaydi."""
        model = self.cfg["sprite_model"]
        if obj:
            prompt = (f"A single toy-like object, side view facing right, whole object visible: {look}. "
                      f"Style: {style}. Isolated object, nobody in it, transparent background, no ground, no shadow, no text.")
        else:
            prompt = (f"Full body character, standing, facing slightly right, cheerful pose: {look}. "
                      f"Style: {style}. Isolated single character, transparent background, no ground, no shadow, no text.")
        r = self.client.images.generate(model=model, prompt=prompt, size="1024x1536", quality=self.cfg["image_quality"],
                                        background="transparent", output_format="png", n=1)
        img = Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGBA")
        bbox = img.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
        (img.crop(bbox) if bbox else img).save(out_path)  # bo'sh chetlarni kesamiz
        p = PRICES.get(model, PRICES["gpt-image-1.5"])
        if r.usage:
            self.cost += (r.usage.input_tokens * p["text_in"] + r.usage.output_tokens * p["image_out"]) / 1e6
        return True

    # ---------- Ovoz ----------

    def speech(self, text, out_path, voice):
        model = self.cfg["tts_model"]
        with self.client.audio.speech.with_streaming_response.create(
            model=model,
            voice=VOICE_MAP.get(voice, voice if voice in VOICE_MAP.values() else "coral"),
            input=text,
            instructions=self.cfg["tts_instructions"],
            response_format="mp3",
        ) as r:
            r.stream_to_file(str(out_path))

    def add_speech_cost(self, text, seconds):
        p = PRICES[self.cfg["tts_model"]]
        self.cost += (len(text) / 4 * p["text_in"] + seconds * AUDIO_TOKENS_PER_SECOND * p["audio_out"]) / 1e6

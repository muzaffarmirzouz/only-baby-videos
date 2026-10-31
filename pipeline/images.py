"""Pollinations.ai orqali sahna rasmlarini yaratish.

Tekin rejim: IP uchun 45 soniyada 1 ta rasm. POLLINATIONS_KEY (.env) bo'lsa limit yo'q.
"""
import os
import random
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw

URL = "https://image.pollinations.ai/prompt/{prompt}"
FREE_INTERVAL = 46
_last_request = 0.0


def generate(prompt, out_path, width, height, seed=None, retries=4):
    global _last_request
    key = os.getenv("POLLINATIONS_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params = {
        "width": width,
        "height": height,
        "seed": seed if seed is not None else random.randint(1, 10**9),
        "nologo": "true",
    }
    url = URL.format(prompt=urllib.parse.quote(prompt[:1500]))
    for attempt in range(retries):
        if not key:
            wait = FREE_INTERVAL - (time.time() - _last_request)
            if wait > 0:
                time.sleep(wait)
        _last_request = time.time()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                out_path.write_bytes(r.content)
                Image.open(out_path).convert("RGB").resize((width, height)).save(out_path, "JPEG", quality=92)
                return True
            print(f"  rasm xizmati javobi {r.status_code}, qayta urinish ({attempt + 1}/{retries})")
        except requests.RequestException as e:
            print(f"  rasm xizmatiga ulanib bo'lmadi: {e}")
        time.sleep(15 * (attempt + 1))  # server band bo'lsa tobora uzoqroq kutish
    placeholder(out_path, width, height)
    return False


def placeholder(out_path, width, height):
    """Rasm xizmati ishlamasa video to'xtab qolmasligi uchun rangli fon."""
    top, bottom = random.choice([((255, 200, 220), (180, 220, 255)), ((255, 240, 180), (190, 255, 210))])
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        k = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)))
    img.save(out_path, "JPEG", quality=92)

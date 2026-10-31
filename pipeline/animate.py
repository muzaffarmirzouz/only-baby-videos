"""Haqiqiy AI animatsiya: Google Gemini Omni (rasm → video). GEMINI_API_KEY kerak.

Narx: 360p da ~$0.034/soniya (5 soniyalik klip ≈ $0.17). Tekin limit yo'q.
"""
import base64
import os
import subprocess

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OUTPUT_PRICE = 17.5  # USD / 1M video tokeni
INPUT_PRICE = 0.5


class Animator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.key = os.getenv("GEMINI_API_KEY")
        self.cost = 0.0

    @property
    def enabled(self):
        return bool(self.key) and self.cfg.get("enabled", False)

    def animate(self, start_image, action_prompt, out_path, vertical):
        """start_image dan klip yasaydi; davomiyligini (soniya) qaytaradi yoki xato bo'lsa None."""
        seconds = self.cfg.get("seconds", 5)
        prompt = (f"A {seconds} second clip. Animate this cozy 3D cartoon scene for a kids animated show: {action_prompt} "
                  "Smooth, gentle, bouncy character animation. Keep the exact same characters, faces, colors and art "
                  "style. Static camera. No dialogue, no speech, no text, no new characters.")
        body = {
            "model": self.cfg.get("model", "gemini-omni-1.1-flash"),
            "input": [
                {"type": "image", "data": base64.b64encode(open(start_image, "rb").read()).decode(),
                 "mime_type": "image/jpeg"},
                {"type": "text", "text": prompt},
            ],
            "response_format": {"type": "video", "aspect_ratio": "9:16" if vertical else "16:9",
                                "resolution": self.cfg.get("resolution", "360p")},
            "generation_config": {"video_config": {"task": "image_to_video"}},
            "background": False, "store": False, "stream": False,
        }
        try:
            r = requests.post(URL, headers={"x-goog-api-key": self.key}, json=body, timeout=300)
            data = r.json()
            if r.status_code != 200:
                raise RuntimeError(data.get("error", {}).get("message", r.status_code))
            video = _find_video(data)
            if not video:
                raise RuntimeError("javobda video yo'q")
            out_path.write_bytes(base64.b64decode(video["data"]))
            u = data.get("usage", {})
            self.cost += (u.get("total_output_tokens", 0) * OUTPUT_PRICE
                          + u.get("total_input_tokens", 0) * INPUT_PRICE) / 1e6
            return _duration(out_path)
        except Exception as e:
            print(f"  ! animatsiya bo'lmadi ({e}) — qo'g'irchoq animatsiya qoladi")
            return None


def _find_video(o):
    if isinstance(o, dict):
        if o.get("type") == "video" and o.get("data"):
            return o
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            found = _find_video(v)
            if found:
                return found
    return None


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())

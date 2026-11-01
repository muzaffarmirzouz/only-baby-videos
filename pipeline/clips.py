"""Botga yuborilgan (masalan Google Flow) kliplarni Telegram'dan yuklab olish.

Kliplar workdir ga clip_000.mp4, clip_001.mp4 ... bo'lib saqlanadi, har biridan o'rta kadr img_XXX.jpg olinadi —
shunda asosiy jarayon ularni tayyor sahna videolari sifatida ishlatadi.
"""
import os
import subprocess

import requests

API = "https://api.telegram.org"


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "default=nw=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    info = dict(line.split("=", 1) for line in out.split() if "=" in line)
    return float(info["duration"]), int(info["width"]), int(info["height"])


def download(file_ids, workdir):
    """[(davomiylik, eni, bo'yi)] qaytaradi."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    infos = []
    for i, fid in enumerate(f for f in file_ids if f):
        meta = requests.get(f"{API}/bot{token}/getFile", params={"file_id": fid}, timeout=60).json()
        if not meta.get("ok"):
            raise RuntimeError(f"Klip #{i + 1} yuklab olinmadi: {meta.get('description')}")
        clip = workdir / f"clip_{i:03d}.mp4"
        r = requests.get(f"{API}/file/bot{token}/{meta['result']['file_path']}", timeout=300)
        r.raise_for_status()
        clip.write_bytes(r.content)
        dur, w, h = _probe(clip)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur / 2:.2f}", "-i", str(clip),
                        "-frames:v", "1", "-q:v", "2", str(workdir / f"img_{i:03d}.jpg")], check=True)
        print(f"  Klip #{i + 1}: {dur:.1f} s, {w}x{h}")
        infos.append((dur, w, h))
    return infos

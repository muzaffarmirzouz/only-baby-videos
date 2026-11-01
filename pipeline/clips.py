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
        _normalize_audio(clip)
        dur, w, h = _probe(clip)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur / 2:.2f}", "-i", str(clip),
                        "-frames:v", "1", "-q:v", "2", str(workdir / f"img_{i:03d}.jpg")], check=True)
        print(f"  Klip #{i + 1}: {dur:.1f} s, {w}x{h}")
        infos.append((dur, w, h))
    return infos


def _normalize_audio(clip, target=-20):
    """Flow kliplarining effektlari ko'pincha juda past yozilgan — ovozni bir xil darajaga ko'taramiz (video o'zgarmaydi)."""
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", str(clip)], capture_output=True, text=True).stdout.strip()
    if not has_audio:
        return
    tmp = clip.with_suffix(".norm.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-c:v", "copy",
                    "-af", f"loudnorm=I={target}:TP=-2:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(tmp)],
                   check=True)
    tmp.replace(clip)

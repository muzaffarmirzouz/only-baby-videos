"""YouTube kunlik limiti tugaganda tayyor videolar navbati.

Navbat — GitHub Actions artifact'lari: limit tugagan run'ning artifact'i "queued-<raqam>" deb nomlanadi (7 kun saqlanadi).
Keyingi ishga tushishda ular yuklab olinadi, YouTube'ga yuklanadi va artifact o'chiriladi.
`gh` va GH_TOKEN (github.token, actions: write) kerak.
"""
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import requests


def is_limit_error(e):
    return "uploadLimitExceeded" in str(e) or "exceeded the number of videos" in str(e)


def _repo():
    return os.getenv("GITHUB_REPOSITORY") or subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True, check=True).stdout.strip()


def _api(path, *args):
    return subprocess.run(["gh", "api", f"repos/{_repo()}/{path}", *args], capture_output=True, check=True)


def queued():
    data = json.loads(_api("actions/artifacts?per_page=100").stdout)
    return sorted((a for a in data.get("artifacts", [])
                   if a["name"].startswith("queued-") and not a.get("expired")), key=lambda a: a["created_at"])


def upload_all(yt_cfg, upload_fn):
    """Navbatdagi videolarni yuklaydi (+ Instagram); limit yana tugasa to'xtaydi. [(title, url, ig_url)]."""
    done = []
    for art in queued():
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "a.zip"
            zpath.write_bytes(_api(f"actions/artifacts/{art['id']}/zip").stdout)
            with zipfile.ZipFile(zpath) as z:
                z.extractall(tmp)
            for video in Path(tmp).rglob("final.mp4"):
                script = json.loads((video.parent / "script.json").read_text())
                thumb = video.parent / "thumbnail.jpg"
                short = script.get("format") == "short"
                try:
                    vid = upload_fn(video, script, None if short or not thumb.exists() else thumb, yt_cfg)
                except Exception as e:
                    if is_limit_error(e):
                        print("  YouTube limiti hali tiklanmagan — navbat keyinroq yuklanadi")
                        return done
                    raise
                print(f"  Navbatdan yuklandi: {script['title']} → https://youtu.be/{vid}")
                from pipeline import instagram
                ig_url = instagram.share(video, script, f"https://youtu.be/{vid}", video.parent)
                done.append((script["title"], f"https://youtu.be/{vid}", ig_url))
        _api(f"actions/artifacts/{art['id']}", "-X", "DELETE")
    return done


def notify(text):
    """Telegram xabari (GitHub Actions'da TELEGRAM_* secret'lari bo'lsa)."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text}, timeout=30)

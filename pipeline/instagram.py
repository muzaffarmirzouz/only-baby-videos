"""Instagram Reels joylash (Graph API, Facebook Login for Business — sahifa tokeni muddatsiz).

Kerak: INSTAGRAM_TOKEN (Facebook sahifa tokeni) va INSTAGRAM_USER_ID (Instagram professional akkaunt ID).
Video fayl to'g'ridan-to'g'ri yuklanadi (resumable upload) — ochiq havola kerak emas.
"""
import os
import subprocess
import time
from pathlib import Path

import requests

VERSION = os.getenv("INSTAGRAM_API_VERSION", "v26.0")
GRAPH = f"https://graph.facebook.com/{VERSION}"
RUPLOAD = f"https://rupload.facebook.com/ig-api-upload/{VERSION}"


def enabled():
    return bool(os.getenv("INSTAGRAM_TOKEN") and os.getenv("INSTAGRAM_USER_ID"))


def _check(r):
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"Instagram: {data.get('error', {}).get('message', r.text[:200])}")
    return data


def _prepare(video_path):
    """Instagram uchun ixcham nusxa: H.264 Main, ~5 Mbit/s, ovoz video uzunligida, faststart."""
    out = Path(video_path).with_name("instagram_upload.mp4")
    vdur = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                           "-of", "csv=p=0", str(video_path)], capture_output=True, text=True).stdout.strip()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_path), "-c:v", "libx264", "-profile:v", "main",
                    "-preset", "veryfast", "-crf", "22", "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p",
                    "-r", "30", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t", vdur or "90",
                    "-movflags", "+faststart", str(out)], check=True)
    return out


def _upload(token, ig, data, caption, tries=6):
    """Instagram rupload ba'zan sababsiz rad etadi (ProcessingFailedError) — yangi konteyner bilan qayta urinamiz."""
    last = ""
    for attempt in range(tries):
        c = _check(requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
            "share_to_feed": "true", "access_token": token}))
        up = requests.post(c.get("uri") or f"{RUPLOAD}/{c['id']}", data=data, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))})
        if up.ok and up.json().get("success"):
            return c["id"]
        last = up.text[:200]
        time.sleep(30 * (attempt + 1))  # jami ~7 daqiqa: xato vaqtincha bo'lsa o'tib ketadi, Meta'ga ham yumshoq
    raise RuntimeError(f"Instagram: video {tries} urinishda ham yuklanmadi ({last})")


def publish_reel(video_path, caption):
    """Reel joylaydi va havolasini qaytaradi."""
    token, ig = os.environ["INSTAGRAM_TOKEN"], os.environ["INSTAGRAM_USER_ID"]
    data = _prepare(video_path).read_bytes()
    container = _upload(token, ig, data, caption)
    for _ in range(30):  # Instagram videoni qayta ishlaydi (odatda 1-3 daqiqa)
        status = _check(requests.get(f"{GRAPH}/{container}", timeout=60,
                                     params={"fields": "status_code,status", "access_token": token}))
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram videoni qabul qilmadi: {status.get('status')}")
        time.sleep(20)
    else:
        raise RuntimeError("Instagram videoni 10 daqiqada qayta ishlamadi")
    media = _check(requests.post(f"{GRAPH}/{ig}/media_publish", timeout=60,
                                 data={"creation_id": container, "access_token": token}))["id"]
    info = _check(requests.get(f"{GRAPH}/{media}", timeout=60, params={"fields": "permalink", "access_token": token}))
    return info.get("permalink", f"https://www.instagram.com/reel/{media}")


def vertical_excerpt(video, out_path, start=3.0, seconds=45):
    """Uzun gorizontal epizoddan vertikal (1080x1920) parcha: markazdagi 3:4 qism katta, orqada xira fon."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(seconds), "-i", str(video),
        "-filter_complex",
        "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];"
        "[b]crop=ih*3/4:ih,scale=1080:1440[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]",
        "-map", "[v]", "-map", "0:a?", "-af", "afade=t=out:st=" + str(seconds - 1.5) + ":d=1.5",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(out_path)], check=True)
    return out_path


def caption_for(script, youtube_url=None, excerpt=False):
    tags = " ".join("#" + "".join(ch for ch in t.replace("'", "").title() if ch.isalnum())
                    for t in (script.get("tags") or [])[:8])
    title = script["title"].replace("#Shorts", "").strip()
    lines = [title, "", script.get("description", "").strip()]
    if excerpt and youtube_url:
        lines += ["", f"▶️ Full episode on YouTube: {youtube_url}"]
    lines += ["", f"{tags} #kidscartoon #kidsvideos #toddlers #parenting #OnlyBaby"]
    return "\n".join(lines)


def share(final, script, youtube_url, workdir):
    """YouTube'dan keyin Instagram'ga: Shorts → Reel, uzun epizod → 45 soniyalik vertikal parcha."""
    if not enabled():
        return None
    short = script.get("format") == "short"
    try:
        video = final if short else vertical_excerpt(final, workdir / "instagram_excerpt.mp4")
        url = publish_reel(video, caption_for(script, youtube_url, excerpt=not short))
        print(f"  Instagram: {url}")
        return url
    except Exception as e:  # Instagram xatosi YouTube'ga ta'sir qilmasin
        print(f"  ! Instagram'ga joylanmadi: {e}")
        from pipeline import pending
        pending.notify(f"⚠️ YouTube'ga chiqdi, lekin Instagram'ga joylanmadi.\n\n{script['title']}\n{youtube_url}\n\nSabab: {' '.join(str(e).split())[:300]}")
        return None

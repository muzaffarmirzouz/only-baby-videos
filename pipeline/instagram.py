"""Instagram Reels joylash (Graph API, Facebook Login for Business — sahifa tokeni muddatsiz).

Kerak: INSTAGRAM_TOKEN (Facebook sahifa tokeni) va INSTAGRAM_USER_ID (Instagram professional akkaunt ID).
Video fayl to'g'ridan-to'g'ri yuklanadi (resumable upload) — ochiq havola kerak emas.
"""
import os
import subprocess
import time

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


def publish_reel(video_path, caption):
    """Reel joylaydi va havolasini qaytaradi."""
    token, ig = os.environ["INSTAGRAM_TOKEN"], os.environ["INSTAGRAM_USER_ID"]
    container = _check(requests.post(f"{GRAPH}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token}))["id"]
    data = open(video_path, "rb").read()
    up = requests.post(f"{RUPLOAD}/{container}", data=data, timeout=600, headers={
        "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(data))})
    if not up.ok or not up.json().get("success"):
        raise RuntimeError(f"Instagram: video yuklanmadi ({up.text[:200]})")
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
        return None

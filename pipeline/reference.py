"""Namuna YouTube videosi haqida ma'lumot: sarlavha, tavsif, teglar va (iloji bo'lsa) matni."""
import re

ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")


def video_id(url):
    url = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = ID_RE.search(url)
    if not m:
        raise ValueError(f"YouTube havolasi tanilmadi: {url}")
    return m.group(1)


def _minutes(iso):
    h, m, s = (int(x or 0) for x in re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso).groups())
    return round(h * 60 + m + s / 60, 1)


def _transcript(vid):
    """Matnni olishga harakat qiladi; YouTube serverlardan (masalan GitHub) ko'pincha bloklaydi — unda bo'sh."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        fetched = YouTubeTranscriptApi().fetch(vid, languages=["en", "en-US", "en-GB"])
        return " ".join(s.text for s in fetched)
    except Exception as e:
        print(f"  (namuna matni olinmadi: {type(e).__name__} — faqat sarlavha va tavsif ishlatiladi)")
        return ""


def fetch(url):
    from pipeline.uploader import get_service

    vid = video_id(url)
    items = get_service().videos().list(part="snippet,contentDetails", id=vid).execute().get("items", [])
    if not items:
        raise ValueError(f"Video topilmadi yoki yopiq: {url}")
    sn = items[0]["snippet"]
    return {
        "id": vid,
        "url": f"https://youtu.be/{vid}",
        "title": sn["title"],
        "channel": sn.get("channelTitle", ""),
        "description": sn.get("description", ""),
        "tags": sn.get("tags", []),
        "minutes": _minutes(items[0]["contentDetails"]["duration"]),
        "transcript": _transcript(vid),
    }

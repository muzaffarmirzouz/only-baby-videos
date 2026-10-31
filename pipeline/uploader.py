"""YouTube Data API v3 orqali video yuklash (OAuth — parol kerak emas)."""
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
ROOT = Path(__file__).resolve().parent.parent
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN = ROOT / "token.json"


def get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if os.getenv("CI"):
                raise RuntimeError("YouTube token yaroqsiz — Mac'da `python auth.py` ni qayta ishga tushirib, "
                                   "yangi token.json ni YOUTUBE_TOKEN secret'iga qo'ying.")
            if not CLIENT_SECRET.exists():
                raise FileNotFoundError("client_secret.json topilmadi — docs/SETUP_UZ.md, 3-qadamga qarang.")
            # Brauzer ochiladi: o'zingiz Google akkauntga kirib "Allow" bosasiz
            creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(video_path, script, thumb_path, yt_cfg):
    yt = get_service()
    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": script["description"][:4900],
            "tags": script.get("tags", [])[:30],
            "categoryId": yt_cfg["category_id"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": yt_cfg["privacy"],
            "selfDeclaredMadeForKids": yt_cfg["made_for_kids"],
            # YouTube talabi: AI bilan yaratilgan realistik kontentni belgilash
            "containsSyntheticMedia": True,
        },
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  yuklanmoqda: {int(status.progress() * 100)}%")
    video_id = resp["id"]

    if thumb_path:
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumb_path))).execute()
        except HttpError as e:
            # Thumbnail uchun kanal telefon orqali tasdiqlangan bo'lishi kerak
            print(f"  thumbnail o'rnatilmadi (kanalni tasdiqlang): {e.reason}")
    return video_id

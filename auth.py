"""YouTube ruxsatini bir marta berish: brauzer ochiladi, kanal akkauntini tanlab "Allow" bosasiz.

Natijada token.json yaratiladi (GitHub Actions uchun ham shu fayl kerak bo'ladi).
"""
from pipeline.uploader import get_service

yt = get_service()
channels = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
for c in channels:
    print(f"Ulangan kanal: {c['snippet']['title']}  (id: {c['id']})")
if not channels:
    print("Bu akkauntda YouTube kanal topilmadi — boshqa akkaunt yoki Brand kanalni tanlang.")

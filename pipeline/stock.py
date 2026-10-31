"""Pixabay (tekin, PIXABAY_API_KEY) dan rasm va video kliplar olish."""
import os

import requests

API = "https://pixabay.com/api/"


class Pixabay:
    def __init__(self):
        self.key = os.getenv("PIXABAY_API_KEY")
        self.used = set()  # bitta videoda bir xil rasm/klip takrorlanmasin

    @property
    def enabled(self):
        return bool(self.key)

    def _search(self, url, query, **params):
        r = requests.get(url, params={"key": self.key, "q": query[:100], "safesearch": "true",
                                      "per_page": 30, **params}, timeout=30)
        r.raise_for_status()
        return [h for h in r.json().get("hits", []) if h["id"] not in self.used]

    def _download(self, url, out_path):
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        out_path.write_bytes(r.content)

    def image(self, query, out_path, image_type="all"):
        """Topilsa True. image_type: all | photo | illustration."""
        for q in (query, " ".join(query.split()[:1])):  # topilmasa birinchi so'z bilan qayta qidirish
            hits = self._search(API, q, image_type=image_type, orientation="horizontal", min_width=1280)
            if hits:
                hit = hits[0]
                self._download(hit["largeImageURL"], out_path)
                self.used.add(hit["id"])
                return True
        return False

    def video(self, query, out_path):
        """Gorizontal klip topilsa uning davomiyligini (soniya) qaytaradi, aks holda None."""
        for q in (query, " ".join(query.split()[:1])):
            for hit in self._search(API + "videos/", q, min_width=1280):
                v = hit["videos"].get("large") or {}
                if not v.get("url"):
                    v = hit["videos"].get("medium") or {}
                if v.get("url") and v.get("width", 0) > v.get("height", 1):
                    self._download(v["url"], out_path)
                    self.used.add(hit["id"])
                    return float(hit["duration"])
        return None

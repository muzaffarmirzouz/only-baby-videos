"""Boshqaruv paneli: video buyurtmasini GitHub Actions'ga yuboradi, holat va kanal videolarini ko'rsatadi.

Ishga tushirish:  .venv/bin/python panel/server.py   →  http://localhost:8770
Video Mac'da emas, GitHub serverida yasaladi.
"""
import asyncio
import json
import re
import subprocess
import sys
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = 8770
WORKFLOW = "daily-video.yml"
TYPES = {"auto", "story", "education", "facts", "cartoon", "games"}
YT_RE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/\S+$")
STYLES = {"auto", "stock", "ai"}
PRIVACY = {"public", "unlisted", "private"}
VOICES = {
    "en-US-JennyNeural": "Jenny — ayol, AQSh",
    "en-US-AnaNeural": "Ana — bola ovozi, AQSh",
    "en-US-AriaNeural": "Aria — ayol, AQSh",
    "en-GB-SoniaNeural": "Sonia — ayol, Britaniya",
    "en-US-GuyNeural": "Guy — erkak, AQSh",
    "en-US-AndrewNeural": "Andrew — erkak, AQSh",
}
SAMPLE_TEXT = "Hello, little friends! Today we have a wonderful story for you. Are you ready?"
SAMPLES_DIR = Path(tempfile.gettempdir()) / "only-baby-voice-samples"


def gh(*args):
    proc = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "gh xatosi")
    return proc.stdout


def create_video(data):
    vtype = data.get("type", "auto")
    style = data.get("style", "auto")
    voice = data.get("voice", "en-US-JennyNeural")
    privacy = data.get("privacy", "public")
    fmt = data.get("format", "long")
    length = "" if fmt == "short" else str(data.get("length", "3"))
    topic = " ".join(str(data.get("topic", "")).split())[:2000]
    reference = str(data.get("reference", "")).strip()
    if reference and not YT_RE.match(reference):
        raise ValueError("Namuna YouTube havolasi bo'lishi kerak")
    if vtype not in TYPES or style not in STYLES or voice not in VOICES or privacy not in PRIVACY:
        raise ValueError("Noto'g'ri qiymat tanlangan")
    if fmt not in ("long", "short"):
        raise ValueError("Noto'g'ri format")
    if fmt == "long" and (not length.isdigit() or not 1 <= int(length) <= 30):
        raise ValueError("Uzunlik 1–30 daqiqa bo'lishi kerak")
    gh("workflow", "run", WORKFLOW, "-f", f"format={fmt}", "-f", f"type={vtype}", "-f", f"length={length}", "-f", f"topic={topic}", "-f", f"reference={reference}",
       "-f", f"style={style}", "-f", "review=true", "-f", f"voice={voice}", "-f", f"privacy={privacy}")
    return {"ok": True}


def list_runs():
    out = gh("run", "list", "--workflow", WORKFLOW, "--limit", "12", "--json",
             "databaseId,displayTitle,status,conclusion,createdAt,updatedAt,url,event")
    return json.loads(out)


def list_videos():
    from pipeline.uploader import get_service

    yt = get_service()
    ch = yt.channels().list(part="contentDetails,snippet", mine=True).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=12).execute()["items"]
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return {"channel": ch["snippet"]["title"], "videos": []}
    vids = yt.videos().list(part="snippet,status,statistics,contentDetails", id=",".join(ids)).execute()["items"]
    return {
        "channel": ch["snippet"]["title"],
        "videos": [{
            "id": v["id"],
            "title": v["snippet"]["title"],
            "published": v["snippet"]["publishedAt"],
            "thumb": v["snippet"]["thumbnails"].get("medium", {}).get("url"),
            "privacy": v["status"]["privacyStatus"],
            "views": int(v.get("statistics", {}).get("viewCount", 0)),
            "duration": v["contentDetails"]["duration"],
        } for v in vids],
    }


def voice_sample(voice):
    if voice not in VOICES:
        raise ValueError("Noma'lum ovoz")
    SAMPLES_DIR.mkdir(exist_ok=True)
    path = SAMPLES_DIR / f"{voice}.mp3"
    if not path.exists():
        import edge_tts
        asyncio.run(edge_tts.Communicate(SAMPLE_TEXT, voice, rate="-10%").save(str(path)))
    return path.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, fn):
        try:
            self._send(200, fn())
        except Exception as e:  # xatoni panelda ko'rsatish uchun
            self._send(500, {"error": str(e)})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, (ROOT / "panel" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/options":
            self._send(200, {"voices": VOICES})
        elif path == "/api/runs":
            self._guard(list_runs)
        elif path == "/api/videos":
            self._guard(list_videos)
        elif path == "/api/voice-sample":
            voice = self.path.partition("voice=")[2]
            try:
                self._send(200, voice_sample(voice), "audio/mpeg")
            except Exception as e:
                self._send(500, {"error": str(e)})
        else:
            self._send(404, {"error": "topilmadi"})

    def do_POST(self):
        if self.path != "/api/create":
            return self._send(404, {"error": "topilmadi"})
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")
        self._guard(lambda: create_video(data))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Panel ishlayapti: {url}  (to'xtatish: Ctrl+C)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()

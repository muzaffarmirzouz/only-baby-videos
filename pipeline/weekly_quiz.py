"""Hafta oxiridagi to'plam: hafta davomidagi "Toping!" Shorts savollari bitta 16:9 videoga yig'iladi.

Har bir o'yin Shorts'ining fayllari (ssenariy, ovozlar, rasmlar) "quiz-<raqam>" artifact bo'lib 9 kun saqlanadi
(.github/workflows/daily-video.yml). Bu yerda oxirgi 7 kunniki yuklab olinadi va yangi ssenariy papkasi tuziladi;
keyin main.py uni oddiy --from-script kabi 16:9 formatda yig'adi (ovoz va rasmlar qayta yasalmaydi).
"""
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.pending import _api, _repo

INTRO = ("Hello, friends! Welcome to the big Find It challenge! Look at the four pictures, find the right one "
         "before the timer ends, and shout it out loud. Are you ready? Let's play!")
OUTRO = ("Wow, you found them all! You are a super finder! Come back next week for a brand new Find It challenge. "
         "Bye-bye, friends!")
MIN_QUESTIONS = 9  # kamida 3 ta Shorts; birinchi hafta yarim bo'lsa keyingi shanbaga qoladi
PICTURE = ("Four cute toys, fruits and little animals arranged playfully on a bright sunny table, cheerful game "
           "show feeling, confetti and stars")


def recent_artifacts(days=7):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{_repo()}/actions/artifacts?per_page=100",
                          "-q", ".artifacts[]"], capture_output=True, text=True, check=True).stdout
    arts = [json.loads(line) for line in out.splitlines() if line.strip()]
    arts = [a for a in arts if a["name"].startswith("quiz-") and not a.get("expired")
            and datetime.fromisoformat(a["created_at"].replace("Z", "+00:00")) >= since]
    return sorted(arts, key=lambda a: a["created_at"])


def collect_dirs(tmp, local_dirs=None):
    """Shorts papkalari (eskisidan yangisiga). local_dirs — sinov uchun mahalliy papkalar."""
    if local_dirs:
        return [Path(d) for d in local_dirs]
    dirs = []
    for art in recent_artifacts():
        dest = Path(tmp) / art["name"]
        dest.mkdir()
        zpath = dest / "a.zip"
        zpath.write_bytes(_api(f"actions/artifacts/{art['id']}/zip").stdout)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
        dirs += sorted(p.parent for p in dest.rglob("script.json"))
    return dirs


def build(output_root, local_dirs=None):
    """Yangi papka: script.json + ko'chirilgan ovoz/rasm fayllari. Papka yo'lini qaytaradi (savol bo'lmasa None)."""
    workdir = Path(output_root) / f"{datetime.now():%Y%m%d-%H%M}-weekly-find-it"
    with tempfile.TemporaryDirectory() as tmp:
        scenes = [{"narration": INTRO, "image_prompt": PICTURE, "search_query": "toys fruits"}]
        files = []
        for d in collect_dirs(tmp, local_dirs):
            script = json.loads((d / "script.json").read_text())
            for i, sc in enumerate(script["scenes"]):
                quiz = sc.get("quiz") or {}
                voice, answer = d / f"voice_{i:03d}.mp3", d / f"answer_{i:03d}.mp3"
                tiles = [d / f"item_{i:03d}_{k}.jpg" for k in range(len(quiz.get("items") or []))]
                if not quiz.get("items") or not voice.exists() or not answer.exists() or not all(t.exists() for t in tiles):
                    continue
                j = len(scenes)
                files += [(voice, f"voice_{j:03d}.mp3"), (answer, f"answer_{j:03d}.mp3"),
                          (tiles[quiz["answer"]], f"img_{j:03d}.jpg")]
                files += [(t, f"item_{j:03d}_{k}.jpg") for k, t in enumerate(tiles)]
                scenes.append(sc)
        n = len(scenes) - 1
        if n < MIN_QUESTIONS:
            print(f"  Hafta davomida savollar kam ({n}) — to'plam yasalmadi")
            return None
        workdir.mkdir(parents=True)
        for src, name in files:
            shutil.copy2(src, workdir / name)
    scenes.append({"narration": OUTRO, "image_prompt": PICTURE + ", waving goodbye balloons", "search_query": "balloons"})
    week = datetime.now().isocalendar()[1]
    script = {
        "topic": f"Weekly Find It challenge, week {week}",
        "title": f"Find It! 🔎 {n} Fun Picture Quiz Questions for Kids | Weekly Challenge #{week}",
        "description": (f"Can your little one find them all? {n} quick picture questions: look at the four pictures, "
                        "find the right one before the 5-second timer ends, and shout it out loud!\n\n"
                        "Great for ages 3-6: colors, shapes, animals, fruits and everyday things. "
                        "A new Find It challenge every week on Only Baby!"),
        "tags": ["kids quiz", "find it", "picture quiz", "quiz for kids", "preschool learning", "toddler games",
                 "colors for kids", "animals for kids", "shapes for kids", "brain games for kids", "only baby"],
        "characters": "",
        "type": "games",
        "format": "long",
        "minutes": round(n * 16 / 60, 1),
        "weekly": True,
        "scenes": scenes,
    }
    (workdir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    print(f"  Haftalik to'plam: {n} ta savol → {workdir}")
    return workdir

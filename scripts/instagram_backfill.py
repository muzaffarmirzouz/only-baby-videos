"""O'tib ketgan videolarni Instagram'ga bittadan joylaydi (backfill.json bo'yicha, eng eskisidan).

Workflow kuniga 2 marta ishga tushiradi. Video fayli run artifact'idan olinadi (7 kun saqlanadi).
Muvaffaqiyatsiz bo'lsa video ro'yxatda qoladi va keyingi safar qayta uriniladi.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import instagram, pending  # noqa: E402

LIST = ROOT / "backfill.json"


def main():
    items = json.loads(LIST.read_text())
    todo = [x for x in items if not x.get("instagram")]
    if not todo:
        print("Ro'yxat tugagan")
        return
    item = todo[0]
    with tempfile.TemporaryDirectory() as tmp:
        got = subprocess.run(["gh", "run", "download", str(item["run_id"]), "-n", item["artifact"], "-D", tmp],
                             capture_output=True, text=True)
        videos = list(Path(tmp).rglob("final.mp4"))
        if got.returncode != 0 or not videos:
            pending.notify(f"⚠️ Eski videoni Instagram uchun olib bo'lmadi:\n{item['title']}\n{got.stderr[:200]}")
            sys.exit(1)
        video = videos[0]
        script = json.loads((video.parent / "script.json").read_text())
        url = instagram.share(video, script, item["url"], video.parent)  # xatoni o'zi Telegram'ga yozadi
    if not url:
        sys.exit(1)
    item["instagram"] = url
    LIST.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    left = len(todo) - 1
    pending.notify(f"📸 Eski video Instagram'ga joylandi:\n\n{item['title']}\n{url}\n\nYana {left} ta qoldi.")


if __name__ == "__main__":
    main()

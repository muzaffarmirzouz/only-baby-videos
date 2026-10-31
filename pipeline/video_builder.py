"""Remotion (video/ papkasi) orqali video montaj va Pillow bilan thumbnail."""
import json
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
REMOTION_DIR = ROOT / "video"
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux (GitHub Actions)
]


def font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(script, scenes, workdir, out_path, music=None, music_volume=0.12, concurrency=2, crf=16):
    """scenes: [{image, audio, duration, captions}] — workdir ichidagi fayllar.

    Remotion faqat public/ papkadagi fayllarni ko'radi, shuning uchun ular public/jobs/<nom>/ ga ko'chiriladi.
    """
    job = workdir.name
    public = REMOTION_DIR / "public" / "jobs" / job
    public.mkdir(parents=True, exist_ok=True)

    def publish(path):
        shutil.copy2(path, public / Path(path).name)
        return f"jobs/{job}/{Path(path).name}"

    props = {
        "title": script["title"],
        "kind": script.get("type", "story"),
        "music": publish(music) if music else None,
        "musicVolume": music_volume,
        "scenes": [
            {
                "image": publish(s["image"]),
                "video": publish(s["video"]) if s.get("video") else None,
                "videoDuration": s.get("video_duration"),
                "audio": publish(s["audio"]),
                "duration": s["duration"],
                "captions": [{"start": a, "end": b, "text": t} for a, b, t in s["captions"]],
                "motion": i % 4,
                "quiz": {**s["quiz"], "answerAudio": publish(s["quiz"]["answerAudio"])} if s.get("quiz") else None,
            }
            for i, s in enumerate(scenes)
        ],
    }
    props_file = workdir / "props.json"
    props_file.write_text(json.dumps(props, indent=2, ensure_ascii=False))

    proc = subprocess.run(
        ["npx", "remotion", "render", "src/index.ts", "KidsVideo", str(out_path.resolve()),
         f"--props={props_file.resolve()}", "--codec=h264", f"--crf={crf}", f"--concurrency={concurrency}"],
        cwd=REMOTION_DIR,
    )
    shutil.rmtree(public, ignore_errors=True)
    if proc.returncode != 0:
        raise RuntimeError("Remotion render xatosi (yuqoridagi logga qarang)")


def extract_frame(video, out_path, at=1.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(video), "-frames:v", "1",
                    "-q:v", "2", str(out_path)], check=True)


def thumbnail(image, title, out_path):
    img = Image.open(image).convert("RGB").resize((1280, 720))
    draw = ImageDraw.Draw(img)
    f = font(92)
    y = 40
    for line in textwrap.wrap(title.upper(), width=20)[:3]:
        w = draw.textlength(line, font=f)
        draw.text(((1280 - w) / 2, y), line, font=f, fill=(255, 230, 0), stroke_width=8, stroke_fill=(30, 30, 120))
        y += 110
    img.save(out_path, "JPEG", quality=90)

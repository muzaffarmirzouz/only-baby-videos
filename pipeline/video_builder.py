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


def render(script, scenes, workdir, out_path, music=None, music_volume=0.12, concurrency=2, crf=16, captions=False):
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
        "showCaptions": captions,
        "clipMode": bool(script.get("clip_mode")),
        "vertical": script.get("format") == "short",
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
                "puppets": [{**pp, "src": publish(pp["src"])} for pp in s.get("puppets") or []],
                "effect": s.get("effect"),
                "word": s.get("word"),
                "clipVolume": s.get("clip_volume", 0),
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
    master_loudness(out_path)


def master_loudness(path, target=-14.0):
    """Ovozni YouTube standartiga (-14 LUFS) keltiradi; video qayta kodlanmaydi. Ikki bosqichli loudnorm."""
    measure = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
         "-vn", "-f", "null", "-"], capture_output=True, text=True)
    start = measure.stderr.rindex("{")
    m = json.loads(measure.stderr[start:measure.stderr.index("}", start) + 1])
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    tmp = Path(path).with_suffix(".loud.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-c:v", "copy", "-af", af,
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(tmp)], check=True)
    tmp.replace(path)
    print(f"  Ovoz: {float(m['input_i']):.1f} → {target:.0f} LUFS")


def preview(video, out_path, max_mb=45):
    """Telegram uchun siqilgan nusxa (bot 50 MB dan katta fayl yubora olmaydi)."""
    for crf in (28, 33, 38):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
                        "-vf", "scale='if(gt(iw,ih),1280,720)':-2", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", str(crf), "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out_path)],
                       check=True)
        if Path(out_path).stat().st_size < max_mb * 1024 * 1024:
            break
    return out_path


def extract_frame(video, out_path, at=1.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(video), "-frames:v", "1",
                    "-q:v", "2", str(out_path)], check=True)


def compose_cover(background, puppets, out_path):
    """Multik muqovasi: fon + qahramonlar (Remotion'dagi joylashuvga yaqin)."""
    bg = Image.open(background).convert("RGBA")
    w, h = bg.size
    xs = {"left": 0.25, "center": 0.5, "right": 0.75}
    for pp in puppets:
        sp = Image.open(pp["src"]).convert("RGBA")
        k = h * (0.42 if h > w else 0.62) / sp.height
        sp = sp.resize((int(sp.width * k), int(sp.height * k)))
        if pp["position"] == "right":
            sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
        bg.alpha_composite(sp, (int(w * xs[pp["position"]] - sp.width / 2), int(h * 0.97 - sp.height)))
    bg.convert("RGB").save(out_path, "JPEG", quality=92)


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

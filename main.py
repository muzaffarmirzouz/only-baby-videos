"""Bolalar uchun YouTube video yaratish va yuklash.

Misollar:
  python main.py --type story --length 3
  python main.py --type education --length 10 --topic "the alphabet A to Z"
  python main.py --type facts --length 20 --no-upload
  python main.py --from-script output/xxx/script.json   # tayyor ssenariydan (OpenAI'siz)
"""
import argparse
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pipeline import images, stock, tts, video_builder

ROOT = Path(__file__).resolve().parent
TOPICS_FILE = ROOT / "topics_used.json"
STYLE_SOURCES = {
    "stock": ["pixabay_video", "pixabay_photo", "pixabay_illustration", "ai"],
    "ai": ["ai", "pixabay_illustration"],
}


def load_topics():
    return json.loads(TOPICS_FILE.read_text()) if TOPICS_FILE.exists() else []


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def main():
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["auto", "story", "education", "facts"], default="story",
                    help="auto = kun bo'yicha navbat bilan: story → education → facts")
    ap.add_argument("--length", type=float, default=3, help="daqiqa: 3, 10, 15, 20 ...")
    ap.add_argument("--topic", help="mavzu (bo'lmasa AI o'zi tanlaydi)")
    ap.add_argument("--no-upload", action="store_true", help="faqat video yaratish, yuklamaslik")
    ap.add_argument("--from-script", help="tayyor script.json dan video yasash")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"])
    ap.add_argument("--voice", help="edge-tts ovozi, masalan en-US-AnaNeural (bo'lmasa config.yaml dagisi)")
    ap.add_argument("--style", choices=["auto", "stock", "ai"], default="auto",
                    help="stock = Pixabay video/rasm, ai = AI rasm, auto = config.yaml dagi tartib")
    args = ap.parse_args()
    if args.privacy:
        cfg["youtube"]["privacy"] = args.privacy
    if args.voice:
        cfg["voice"] = args.voice
    if args.type == "auto":
        args.type = ["story", "education", "facts"][datetime.now().timetuple().tm_yday % 3]

    # 1. Ssenariy
    if args.from_script:
        script = json.loads(Path(args.from_script).read_text())
    else:
        from pipeline.script_writer import ScriptWriter
        print(f"[1/5] Ssenariy yozilmoqda ({args.type}, {args.length} daqiqa)...")
        script = ScriptWriter(cfg).write(args.type, args.length, args.topic, load_topics())

    if args.from_script:
        workdir = Path(args.from_script).resolve().parent  # qayta ishga tushirishda tayyor fayllar qayta ishlatiladi
    else:
        workdir = ROOT / "output" / f"{datetime.now():%Y%m%d-%H%M}-{slug(script['title'])}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    print(f"  Sarlavha: {script['title']}  ({len(script['scenes'])} sahna)\n  Papka: {workdir}")

    vcfg = cfg["video"]
    style = cfg["image_style"]
    characters = script.get("characters") or ""
    base_seed = random.randint(1, 10**8)  # ketma-ket seed — rasmlar uslubi izchilroq
    pixabay = stock.Pixabay()
    sources = STYLE_SOURCES.get(args.style) or cfg["media"].get(script.get("type", "story"), ["ai"])
    if not pixabay.enabled:
        sources = [s for s in sources if not s.startswith("pixabay")] or ["ai"]

    def fetch_media(scene, i, img, clip):
        """Sozlamadagi tartibda manbalarni sinaydi. Video bo'lsa davomiyligini qaytaradi."""
        query = scene.get("search_query") or scene["image_prompt"]
        for src in sources:
            try:
                if src == "pixabay_video":
                    clip_dur = pixabay.video(query, clip)
                    if clip_dur:
                        # Thumbnail va zaxira uchun klipdan bitta kadr
                        video_builder.extract_frame(clip, img)
                        return clip_dur
                elif src.startswith("pixabay_"):
                    if pixabay.image(query, img, image_type=src.split("_", 1)[1]):
                        return None
                elif src == "ai":
                    prompt = f"{scene['image_prompt']}. {characters}. {style}"
                    if images.generate(prompt, img, vcfg["width"], vcfg["height"], seed=base_seed + i):
                        return None
            except Exception as e:
                print(f"  ! {src} xatosi: {e}")
        images.placeholder(img, vcfg["width"], vcfg["height"])
        print("  ! media topilmadi, zaxira fon ishlatildi")
        return None

    scenes = []
    n = len(script["scenes"])
    for i, scene in enumerate(script["scenes"]):
        print(f"[2-3/5] Sahna {i + 1}/{n}: ovoz va media ({', '.join(sources)})...")
        audio = workdir / f"voice_{i:03d}.mp3"
        img = workdir / f"img_{i:03d}.jpg"
        clip = workdir / f"clip_{i:03d}.mp4"
        if audio.exists():
            dur = tts.audio_duration(audio)
        else:
            dur = tts.synthesize(scene["narration"], audio, cfg["voice"], cfg["voice_rate"])
        if clip.exists():
            clip_dur = tts.audio_duration(clip)
        elif img.exists():
            clip_dur = None
        else:
            clip_dur = fetch_media(scene, i, img, clip)
        scenes.append({"image": img, "audio": audio, "duration": dur,
                       "video": clip if clip_dur else None, "video_duration": clip_dur,
                       "captions": tts.caption_chunks(scene["narration"], dur)})

    print("[4/5] Remotion bilan video montaj qilinmoqda...")
    tracks = sorted((ROOT / "assets" / "music").glob("*.mp3"))
    final = workdir / "final.mp4"
    video_builder.render(script, scenes, workdir, final, random.choice(tracks) if tracks else None,
                         vcfg["music_volume"], vcfg.get("render_concurrency", 2), vcfg.get("crf", 16))
    thumb = workdir / "thumbnail.jpg"
    video_builder.thumbnail(workdir / "img_000.jpg", script["title"], thumb)
    print(f"  Tayyor: {final}  ({tts.audio_duration(final) / 60:.1f} daqiqa)")

    topics = load_topics()
    topics.append(script.get("topic", script["title"]))
    TOPICS_FILE.write_text(json.dumps(topics, indent=2, ensure_ascii=False))

    if args.no_upload:
        return
    from pipeline.uploader import upload
    print("YouTube'ga yuklanmoqda...")
    vid = upload(final, script, thumb, cfg["youtube"])
    print(f"  Yuklandi: https://youtu.be/{vid}  (holat: {cfg['youtube']['privacy']})")
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output:  # keyingi qadam (Telegram xabarnomasi) uchun
        with open(gh_output, "a") as f:
            f.write(f"video_url=https://youtu.be/{vid}\nthumbnail={thumb}\n")
            f.write(f"title<<__EOT__\n{script['title']}\n__EOT__\n")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### {script['title']}\n\nhttps://youtu.be/{vid} ({cfg['youtube']['privacy']}, {args.type})\n")


if __name__ == "__main__":
    main()

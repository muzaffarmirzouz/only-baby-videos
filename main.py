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
VIDEO_TYPES = ["story", "education", "facts", "cartoon", "games"]
QUIZ_COUNTDOWN = 5  # soniya
STYLE_SOURCES = {
    "stock": ["pixabay_video", "pixabay_photo", "pixabay_illustration", "ai"],
    "ai": ["ai", "pixabay_illustration"],
}


def load_topics():
    return json.loads(TOPICS_FILE.read_text()) if TOPICS_FILE.exists() else []


def _rotation_index():
    """Kun va soat bo'yicha: bir kundagi 4 ta video (06, 10, 14, 18 UTC) har xil turda bo'ladi."""
    now = datetime.utcnow()
    return now.timetuple().tm_yday * 24 + now.hour


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def main():
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["auto", *VIDEO_TYPES], default="story",
                    help="auto = kun bo'yicha navbat bilan (namuna berilsa — namunaga mos tur)")
    ap.add_argument("--format", choices=["long", "short"], default="long",
                    help="long = oddiy gorizontal video, short = YouTube Shorts (tik, ~45 soniya)")
    ap.add_argument("--length", type=float, help="daqiqa: 3, 10, 15, 20 ... (Shorts uchun 0.75)")
    ap.add_argument("--topic", help="mavzu (bo'lmasa AI o'zi tanlaydi)")
    ap.add_argument("--no-upload", action="store_true", help="faqat video yaratish, yuklamaslik")
    ap.add_argument("--from-script", help="tayyor script.json dan video yasash")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"])
    ap.add_argument("--voice", help="edge-tts ovozi, masalan en-US-AnaNeural (bo'lmasa config.yaml dagisi)")
    ap.add_argument("--reference", help="yoqqan YouTube video havolasi — shu formatda original video yasaladi")
    ap.add_argument("--style", choices=["auto", "stock", "ai"], default="auto",
                    help="stock = Pixabay video/rasm, ai = AI rasm, auto = config.yaml dagi tartib")
    args = ap.parse_args()
    if args.length is None:
        args.length = 0.75 if args.format == "short" else 3
    if args.privacy:
        cfg["youtube"]["privacy"] = args.privacy
    if args.voice:
        cfg["voice"] = args.voice

    # 1. Ssenariy
    if args.from_script:
        script = json.loads(Path(args.from_script).read_text())
    else:
        from pipeline.script_writer import ScriptWriter
        writer = ScriptWriter(cfg)
        ref = None
        if args.reference:
            from pipeline import reference
            ref = reference.fetch(args.reference)
            print(f"  Namuna: {ref['title']} ({ref['channel']}, {ref['minutes']} daq)")
        if args.type == "auto":
            args.type = writer.pick_type(ref) if ref else VIDEO_TYPES[_rotation_index() % len(VIDEO_TYPES)]
        print(f"[1/5] Ssenariy yozilmoqda ({args.type}, {args.length} daqiqa)...")
        script = writer.write(args.type, args.length, args.topic, load_topics(), reference=ref,
                              short=args.format == "short")
        if ref:
            script["reference"] = ref["url"]

    if args.from_script:
        workdir = Path(args.from_script).resolve().parent  # qayta ishga tushirishda tayyor fayllar qayta ishlatiladi
    else:
        workdir = ROOT / "output" / f"{datetime.now():%Y%m%d-%H%M}-{slug(script['title'])}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))
    print(f"  Sarlavha: {script['title']}  ({len(script['scenes'])} sahna)\n  Papka: {workdir}")

    vcfg = cfg["video"]
    short = script.get("format") == "short"
    if short:
        vcfg["width"], vcfg["height"] = 1080, 1920
    style = cfg["cartoon_style"] if script.get("type") == "cartoon" else cfg["image_style"]
    characters = script.get("characters") or ""
    base_seed = random.randint(1, 10**8)  # ketma-ket seed — rasmlar uslubi izchilroq
    pixabay = stock.Pixabay(vertical=short)
    sources = STYLE_SOURCES.get(args.style) or cfg["media"].get(script.get("type", "story"), ["ai"])
    if not pixabay.enabled:
        sources = [s for s in sources if not s.startswith("pixabay")] or ["ai"]

    def fetch_media(scene, i, img, clip):
        """Sozlamadagi tartibda manbalarni sinaydi. Video bo'lsa davomiyligini qaytaradi."""
        query = scene.get("search_query") or scene["image_prompt"]
        # Viktorinada rasm javob ochilguncha xiralashtiriladi — video klip kerak emas
        for src in [s for s in sources if not (scene.get("quiz") and s == "pixabay_video")]:
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
        item = {"image": img, "audio": audio, "duration": dur,
                "video": clip if clip_dur else None, "video_duration": clip_dur,
                "captions": tts.caption_chunks(scene["narration"], dur)}
        if scene.get("quiz"):
            # Savol → taymer → javob: javob ovozi alohida, taymerdan keyin boshlanadi
            answer_audio = workdir / f"answer_{i:03d}.mp3"
            if answer_audio.exists():
                a_dur = tts.audio_duration(answer_audio)
            else:
                a_dur = tts.synthesize(scene["answer_narration"], answer_audio, cfg["voice"], cfg["voice_rate"])
            reveal_at = dur + 0.3 + QUIZ_COUNTDOWN
            item.update({
                "duration": reveal_at + a_dur,
                "video": None,
                "captions": [(a + reveal_at, b + reveal_at, t)
                             for a, b, t in tts.caption_chunks(scene["answer_narration"], a_dur)],
                "quiz": {**scene["quiz"], "revealAt": reveal_at, "countdown": QUIZ_COUNTDOWN,
                         # "A. Sheep" → "Sheep": harfni Remotion o'zi qo'yadi
                         "options": [re.sub(r"^\s*[A-Ca-c][.)]\s*", "", o) for o in scene["quiz"]["options"]],
                         "answerAudio": answer_audio},
            })
        scenes.append(item)

    print("[4/5] Remotion bilan video montaj qilinmoqda...")
    tracks = sorted((ROOT / "assets" / "music").glob("*.mp3"))
    final = workdir / "final.mp4"
    video_builder.render(script, scenes, workdir, final, random.choice(tracks) if tracks else None,
                         vcfg["music_volume"], vcfg.get("render_concurrency", 2), vcfg.get("crf", 16))
    if short:
        thumb = workdir / "img_000.jpg"  # Shorts'ga YouTube o'z muqovasini qo'yadi; bu faqat Telegram uchun
    else:
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
    vid = upload(final, script, None if short else thumb, cfg["youtube"])
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

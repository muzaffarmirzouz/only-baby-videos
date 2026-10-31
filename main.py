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

from pipeline import animate, images, premium as premium_mod, stock, tts, video_builder

ROOT = Path(__file__).resolve().parent
TOPICS_FILE = ROOT / "topics_used.json"
VIDEO_TYPES = ["story", "education", "facts", "cartoon", "games"]
QUIZ_COUNTDOWN = 5  # soniya
PREMIUM_FIRST = {"story", "cartoon", "education"}  # pullik rejimda OpenAI rasmi birinchi
STYLE_SOURCES = {
    "stock": ["pixabay_video", "pixabay_photo", "pixabay_illustration", "ai"],
    "ai": ["ai", "pixabay_illustration"],
}


def load_topics():
    return json.loads(TOPICS_FILE.read_text()) if TOPICS_FILE.exists() else []


# Kunlik taqsimot (UTC soat → turlar navbati): asosan multik
SCHEDULE_TYPES = {
    6: ["cartoon"],                      # Shorts, Toshkent 11:00
    10: ["games", "education"],          # Shorts, Toshkent 15:00
    14: ["cartoon", "story"],            # uzun video, Toshkent 19:00
    18: ["cartoon"],                     # Shorts, Toshkent 23:00
}


def auto_type():
    """Jadval bo'yicha tur; qo'lda ishga tushirilganda — kun bo'yicha asosan multik."""
    now = datetime.utcnow()
    day = now.timetuple().tm_yday
    cron = os.getenv("SCHEDULE_CRON", "")  # GitHub jadvali kechiksa ham to'g'ri slot ("0 6 * * *" → 6)
    hour = int(cron.split()[1]) if cron else now.hour
    options = SCHEDULE_TYPES.get(hour) or ["cartoon", "cartoon", "story", "games", "education", "facts"]
    return options[day % len(options)]


CHARACTERS_DIR = ROOT / "assets" / "characters"


ACTION_WORDS = {"walk_in": "walks in", "run_across": "runs happily", "hop": "hops with joy", "wave": "waves hello",
                "bounce": "bounces", "spin": "spins around", "peek": "peeks out shyly", "idle": "sways gently"}


def animate_scenes(script, scenes, workdir, animator, short):
    """Multikning 1-sahnasi va eng harakatli sahnasini haqiqiy AI animatsiyaga aylantiradi."""
    candidates = [i for i, s in enumerate(scenes) if s.get("puppets")]
    if not candidates:
        return
    def liveliness(i):
        return sum(pp["action"] != "idle" for pp in scenes[i]["puppets"]) + any(pp["speaking"] for pp in scenes[i]["puppets"])
    chosen = [candidates[0]] + sorted(candidates[1:], key=liveliness, reverse=True)
    chosen = chosen[:animator.cfg.get("scenes_per_video", 2)]
    for i in chosen:
        item, scene = scenes[i], script["scenes"][i]
        clip = workdir / f"anim_{i:03d}.mp4"
        if not clip.exists():
            start = workdir / f"anim_start_{i:03d}.jpg"
            video_builder.compose_cover(item["image"], item["puppets"], start)
            feel = {"sad": "looks sad", "crying": "is crying with tears", "angry": "pouts grumpily", "happy": "is happy"}
            acts = ", ".join(f"{c['name']} {ACTION_WORDS.get(c.get('action', 'idle'), 'smiles')} and "
                             f"{feel.get(c.get('emotion'), 'is happy')}" for c in scene.get("cast") or [])
            mood = scene["narration"].split(".")[0][:160]
            print(f"  Animatsiya: sahna {i + 1} ({acts})")
            if not animator.animate(start, f"{acts}. Moment: {mood}.", clip, short):
                continue
        item["video"], item["video_duration"] = clip, tts.audio_duration(clip)


def load_series():
    f = CHARACTERS_DIR / "cast.yaml"
    return yaml.safe_load(f.read_text()) if f.exists() else None


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def main():
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["auto", *VIDEO_TYPES], default="auto",
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
    ap.add_argument("--free", action="store_true", help="pullik rejimni o'chirish (faqat tekin xizmatlar)")
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
            print(f"  G'oya: {writer.analyze_reference(ref).get('idea', '?')}")
        if args.type == "auto":
            # Mavzu (prompt) yoki namuna berilsa — o'z qahramonlarimiz bilan multik
            if (ref or args.topic) and load_series():
                args.type = "cartoon"
            else:
                args.type = writer.pick_type(ref) if ref else auto_type()
        print(f"[1/5] Ssenariy yozilmoqda ({args.type}, {args.length} daqiqa)...")
        script = writer.write(args.type, args.length, args.topic, load_topics(), reference=ref,
                              short=args.format == "short", series=load_series())
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
    series = load_series()
    if script.get("type") == "cartoon":
        style = series["style"] if series and script.get("series") else cfg["cartoon_style"]
    else:
        style = cfg["image_style"]
    characters = script.get("characters") or ""
    base_seed = random.randint(1, 10**8)  # ketma-ket seed — rasmlar uslubi izchilroq
    pixabay = stock.Pixabay(vertical=short)
    premium = None
    if cfg["premium"]["enabled"] and not args.free:
        premium = premium_mod.Premium(cfg["premium"])
        print(f"  Pullik rejim: {cfg['premium']['image_model']} rasm + {cfg['premium']['tts_model']} ovoz")
    sources = STYLE_SOURCES.get(args.style) or cfg["media"].get(script.get("type", "story"), ["ai"])
    if premium:
        # Pollinations o'rniga OpenAI; chizilgan turlarda OpenAI birinchi
        sources = ["openai" if s == "ai" else s for s in sources]
        if script.get("type") in PREMIUM_FIRST and args.style != "stock":
            sources = ["openai"] + [s for s in sources if s != "openai"]
        sources.append("ai")  # OpenAI xato bersa — tekin zaxira
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
                elif src == "openai":
                    prompt = f"{scene['image_prompt']}. Characters: {characters}. Style: {style}"
                    if premium.image(prompt, img, vcfg["width"], vcfg["height"]):
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

    # Multik: qahramonlar bir marta, fonsiz chiziladi va har sahnada harakatlantiriladi
    sprites = {}
    if script.get("type") == "cartoon" and script.get("cast") and (
            premium or all(c.get("image") for c in script["cast"])):  # doimiy qahramonlar tekin rejimda ham
        print(f"  Qahramonlar chizilmoqda: {', '.join(c['name'] for c in script['cast'])}")
        try:
            for c in script["cast"]:
                if c.get("image") and (CHARACTERS_DIR / c["image"]).exists():
                    sprites[c["name"]] = CHARACTERS_DIR / c["image"]  # serialning doimiy qahramoni
                    continue
                path = workdir / f"sprite_{slug(c['name'])}.png"
                if not path.exists():
                    premium.sprite(c["look"], style, path)
                sprites[c["name"]] = path
        except Exception as e:
            print(f"  ! qahramonlarni chizib bo'lmadi ({e}) — oddiy rasmlar ishlatiladi")
            sprites = {}

    # Rekvizitlar (mashinacha, aravacha, shar...) — epizod uchun bir marta, fonsiz chiziladi
    prop_sprites = {}
    if sprites and premium:
        for pr in script.get("props") or []:
            path = workdir / f"prop_{slug(pr['name'])}.png"
            try:
                if not path.exists():
                    premium.sprite(pr["look"], style, path, obj=True)
                prop_sprites[pr["name"]] = path
            except Exception as e:
                print(f"  ! {pr['name']} chizilmadi ({e})")

    def puppets_for(scene):
        cast = [c for c in scene.get("cast") or [] if c.get("name") in sprites][:3]
        def sprite_for(c):
            # Kayfiyatga mos rasm: baby.png → baby_sad.png (bo'lsa)
            base = sprites[c["name"]]
            emo = c.get("emotion")
            alt = base.with_name(f"{base.stem}_{emo}.png") if emo in ("sad", "crying", "angry") else None
            return alt if alt and alt.exists() else base
        return [{"src": sprite_for(c),
                 "position": c.get("position") if c.get("position") in ("left", "center", "right") else "center",
                 "action": c.get("action") or "idle",
                 "speaking": c["name"] == scene.get("speaker")} for c in cast] + [
                {"src": prop_sprites[pr["name"]],
                 "position": pr.get("position") if pr.get("position") in ("left", "center", "right") else "center",
                 "action": pr.get("action") or "idle", "speaking": False, "prop": True}
                for pr in (scene.get("props") or [])[:2] if pr.get("name") in prop_sprites]

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
            dur = tts.synthesize(scene["narration"], audio, cfg["voice"], cfg["voice_rate"], premium=premium)
        puppets = puppets_for(scene) if sprites and scene.get("background_prompt") else []
        if clip.exists():
            clip_dur = tts.audio_duration(clip)
        elif img.exists():
            clip_dur = None
        elif puppets:
            clip_dur = None
            bg_prompt = (f"{scene['background_prompt']}. Empty background scene with NO characters, animals or "
                         f"people, room in the lower half for characters to stand. Style: {style}")
            try:
                if premium:
                    premium.image(bg_prompt, img, vcfg["width"], vcfg["height"])
                elif not images.generate(bg_prompt, img, vcfg["width"], vcfg["height"], seed=base_seed + i):
                    raise RuntimeError("tekin rasm xizmati javob bermadi")
            except Exception as e:
                print(f"  ! fon chizilmadi ({e}) — oddiy rasm")
                puppets = []
                clip_dur = fetch_media(scene, i, img, clip)
        else:
            clip_dur = fetch_media(scene, i, img, clip)
        item = {"image": img, "audio": audio, "duration": dur,
                "video": clip if clip_dur else None, "video_duration": clip_dur,
                "captions": tts.caption_chunks(scene["narration"], dur),
                "puppets": puppets,
                "effect": scene.get("effect") if puppets else None}
        if scene.get("quiz"):
            # Savol → taymer → javob: javob ovozi alohida, taymerdan keyin boshlanadi
            answer_audio = workdir / f"answer_{i:03d}.mp3"
            if answer_audio.exists():
                a_dur = tts.audio_duration(answer_audio)
            else:
                a_dur = tts.synthesize(scene["answer_narration"], answer_audio, cfg["voice"], cfg["voice_rate"],
                                       premium=premium)
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

    animator = animate.Animator(cfg.get("animate", {}))
    if animator.enabled and not args.free:
        animate_scenes(script, scenes, workdir, animator, short)

    print("[4/5] Remotion bilan video montaj qilinmoqda...")
    tracks = sorted((ROOT / "assets" / "music").glob("*.mp3"))
    final = workdir / "final.mp4"
    video_builder.render(script, scenes, workdir, final, random.choice(tracks) if tracks else None,
                         vcfg["music_volume"], vcfg.get("render_concurrency", 2), vcfg.get("crf", 16),
                         vcfg.get("captions", False))
    cover = workdir / "img_000.jpg"
    if scenes and scenes[0]["puppets"]:  # multikda fon + qahramonlar
        cover = workdir / "cover.jpg"
        video_builder.compose_cover(scenes[0]["image"], scenes[0]["puppets"], cover)
    if short:
        thumb = cover  # Shorts'ga YouTube o'z muqovasini qo'yadi; bu faqat Telegram uchun
    else:
        thumb = workdir / "thumbnail.jpg"
        video_builder.thumbnail(cover, script["title"], thumb)
    print(f"  Tayyor: {final}  ({tts.audio_duration(final) / 60:.1f} daqiqa)")
    cost = (premium.cost if premium else 0.0) + animator.cost
    if premium:
        print(f"  Rasm va ovoz xarajati: ~${cost:.2f} (+ ssenariy ~$0.01)")

    if args.no_upload:
        return  # sinov — mavzular ro'yxatiga yozilmaydi

    topics = load_topics()
    topics.append(script.get("topic", script["title"]))
    TOPICS_FILE.write_text(json.dumps(topics, indent=2, ensure_ascii=False))
    from pipeline.uploader import upload
    print("YouTube'ga yuklanmoqda...")
    vid = upload(final, script, None if short else thumb, cfg["youtube"])
    print(f"  Yuklandi: https://youtu.be/{vid}  (holat: {cfg['youtube']['privacy']})")
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output:  # keyingi qadam (Telegram xabarnomasi) uchun
        with open(gh_output, "a") as f:
            f.write(f"video_url=https://youtu.be/{vid}\nthumbnail={thumb}\ncost={cost:.2f}\n")
            f.write(f"title<<__EOT__\n{script['title']}\n__EOT__\n")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### {script['title']}\n\nhttps://youtu.be/{vid} ({cfg['youtube']['privacy']}, {args.type})\n")


if __name__ == "__main__":
    main()

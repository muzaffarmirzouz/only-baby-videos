"""OpenAI orqali bolalar videosi ssenariysini yozish."""
import json
import math
import random
from datetime import datetime

from openai import OpenAI

SAFETY_RULES = """You write YouTube video scripts for children aged 3-8, in simple English.
Rules (strict):
- No violence, no scary content, no danger, no bad words, no brand names or copyrighted characters.
- Short, simple sentences. Warm, cheerful, encouraging tone.
- Positive lessons (kindness, sharing, curiosity, honesty, friendship).
- Every scene needs an image_prompt describing ONE clear picture (no text in images).
- Every scene also needs a search_query: 1-3 concrete English words to find a matching stock photo or video (e.g. "dolphin ocean", "red apple", "rocket launch").
- Narration is read aloud by a voice actor: no stage directions, no emojis, no sound effects in brackets."""

TYPE_GUIDES = {
    "story": "An original bedtime-style fairy tale with a clear beginning, problem, solution and a gentle moral at the end.",
    "education": "A fun learning video (for example the alphabet, numbers, colors, shapes, animals, days of the week). Repeat key words, ask the child to say things out loud, and review at the end.",
    "facts": "Amazing fun facts for kids about one theme (animals, space, ocean, dinosaurs, nature, the human body). Each fact is explained simply with a comparison a child understands.",
    "cartoon": "An original animated cartoon episode with a recurring cute duo of characters (invent them, e.g. a little fox and a bunny), a fun adventure with gentle humor, short lines of dialogue inside the narration ('Wow!' said Pip.), and a happy ending.",
    "games": "An interactive quiz game for kids (e.g. guess the animal, which color, count the objects, what sound, odd one out). The first scene welcomes kids and explains the game; the last scene praises them and says goodbye. Every scene in between is one quiz question.",
}

# O'yin (viktorina) sahnalari uchun qo'shimcha maydonlar
QUIZ_FORMAT = """For quiz scenes add:
  "quiz": {"question": short question (max 8 words), "options": [exactly 3 short answers, max 3 words each], "answer": index 0-2 of the correct option},
  "answer_narration": cheerful reveal, about 20 words, e.g. "It's the cow! Moo! Cows give us milk. Great job!".
For quiz scenes, "narration" reads the question and the three options (A, B, C) and ends with "Think fast!" (about 25 words).
The image_prompt / search_query must show the CORRECT answer (it is revealed after the countdown).
Intro and goodbye scenes have no "quiz" field."""

# Multik: qahramonlar alohida chiziladi va Remotion'da harakatlantiriladi ("qo'g'irchoq" animatsiya)
CARTOON_ACTIONS = ["walk_in", "run_across", "hop", "wave", "bounce", "spin", "peek", "idle"]
SCENE_EFFECTS = ["leaves", "snow", "sparkles", "bubbles", "butterflies", "petals", "stars", "none"]
CARTOON_FORMAT = """This is an animated cartoon: characters are separate puppets moved over a background.
For EVERY scene also add:
  "background_prompt": the place only, with NO characters or animals in it (e.g. "sunny meadow with a big apple tree and a picnic blanket"),
  "cast": 1-3 characters on screen, each {"name": exact name from the cast list, "position": "left" | "center" | "right",
          "action": one of %s, "emotion": "happy" | "sad" | "crying" | "angry"},
  "speaker": name of the character who talks in this scene, or "narrator",
  "effect": animated ambience that fits the place and mood, one of %s (stars only at night, snow only in winter),
  "props": objects from the props list visible in this scene (or []), each {"name": exact prop name, "position": "left" | "center" | "right",
           "action": one of ["drive_across", "roll", "float", "bounce", "idle"]}.
Props are drawn separately: keep them OUT of background_prompt.
Choose actions that match the story (walk_in when arriving, hop when happy, wave when greeting, peek when shy or hiding).
Emotions follow the story: sad or crying when something goes wrong, angry (a grumpy pout) only briefly in a small quarrel,
and everyone happy again by the end.""" % (
    CARTOON_ACTIONS, SCENE_EFFECTS)

SCENE_SECONDS = {"games": 22}  # savol + 5 soniya taymer + javob

SHORT_WORDS_PER_SCENE = 22
SHORT_GUIDE = """
This is a vertical YouTube Short for kids, 40-55 seconds long. Grab attention in the first 2 seconds,
no long greeting, one clear idea, fast pace, playful energy. Title: max 60 characters.
Description: 1-2 sentences plus hashtags #Shorts #kids #forkids."""


class ScriptWriter:
    def __init__(self, cfg):
        self.client = OpenAI()
        self.model = cfg["openai_model"]
        self.wpm = cfg["words_per_minute"]
        self.wps = cfg["words_per_scene"]

    def _ask(self, system, user, temperature=0.9):
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content)

    def analyze_reference(self, reference):
        """Namunaning muqovasi va ma'lumotlaridan g'oyasini aniqlaydi (video matnini YouTube bloklaydi)."""
        content = [{"type": "text", "text": f"""This is a kids YouTube video the creator likes:
{reference_text(reference)}
Describe its IDEA so we can make our own original episode inspired by it.
Return JSON: {{"idea": one sentence, "theme": short, "setting": where it happens,
  "format": how it is told (song, story, race, learning...), "fun_objects": list of toys/vehicles/objects that make it fun}}"""}]
        if reference.get("thumbnail"):
            content.append({"type": "image_url", "image_url": {"url": reference["thumbnail"]}})
        resp = self.client.chat.completions.create(
            model=self.model, temperature=0.3, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}])
        reference["analysis"] = json.loads(resp.choices[0].message.content)
        return reference["analysis"]

    def plan_episode(self, series, past):
        """Davomli serialning bugungi epizodi: oldingilarni davom ettiradi + Flow uchun 3-4 ta klip prompti."""
        roster = "\n".join(f"- {c['name']}: {c['look']}. Personality: {c['personality']}. Skill: {c.get('skill', '')}"
                           for c in series["characters"])
        prev = "\n".join(f"Ep {e.get('number')}: {e['title']} — {e['summary']} (lesson: {e.get('lesson', '')})"
                         for e in past) or "(this is the first episode of the season)"
        data = self._ask(SAFETY_RULES, f"""You are the head writer of the kids animated series "{series['series']}".
Characters:
{roster}

Previous episodes (most recent last):
{prev}

Write TODAY's episode ({datetime.now():%B %d}). It must continue the season naturally: characters remember what
happened and what they learned before; reuse running jokes; sometimes refer back to a past episode.
Each episode one character teaches the friends something new and useful for small kids — for example simple English
words (colors, animals, greetings), counting, shapes, how to ride a toy car safely, brushing teeth, sharing, tidying up,
being kind — mixed with a small problem, a rescue or help, and a happy ending. Do not repeat a previous lesson.
Return JSON:
{{"title": catchy episode title under 60 characters,
  "summary": 2-3 sentences,
  "lesson": the one thing kids learn,
  "beats": 8-10 short story beats in order,
  "flow_prompts": exactly 4 prompts for an image-to-video tool (each ~8 seconds) showing the 4 most visual moments.
     Each prompt in English: start with "Use the saved characters <names> exactly as in their references."
     then the place, the action step by step, camera (e.g. slow push-in), "Soft glossy 3D cartoon style, bright warm
     colors.", and end with "Audio: natural sound effects only, no dialogue, no music."}}""")
        return data

    def write_from_clips(self, frames, durations, topic=None, series=None, short=False):
        """Tayyor kliplar (Flow) uchun: har klip kadriga qarab unga mos ertakchi matnini yozadi."""
        import base64
        roster = ""
        if series:
            roster = "Our characters: " + "; ".join(f"{c['name']} ({c['look']})" for c in series["characters"])
        words = [max(6, round(d * 2.0)) for d in durations]  # bolalar uchun ~2 so'z/soniya
        content = [{"type": "text", "text": f"""These are {len(frames)} consecutive clips of one episode of a kids animated show
{f'"{series["series"]}"' if series else ""}. {roster}
Creator's idea: {topic or "(not given — tell the story you see)"}.
Write a warm storyteller narration that matches what happens in each clip, in simple English for kids aged 3-8.
Narration for clip k must be about {words} words (clip k takes that long), so it fits the clip.
Return JSON: {{"topic": short topic, "title": catchy YouTube title under {60 if short else 70} characters,
  "description": 2-3 short kid and parent friendly sentences, "tags": 10-15 tags,
  "scenes": [{{"narration": "..."}} for each clip in order]}}"""}]
        for f in frames:
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(open(f, "rb").read()).decode()}})
        resp = self.client.chat.completions.create(
            model=self.model, temperature=0.7, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SAFETY_RULES}, {"role": "user", "content": content}])
        out = json.loads(resp.choices[0].message.content)
        out["scenes"] = [{"narration": sc["narration"], "image_prompt": "", "user_clip": True}
                         for sc in out["scenes"][:len(frames)]]
        self._moderate(out["scenes"])
        out.update({"type": "cartoon", "format": "short" if short else "long", "minutes": round(sum(durations) / 60, 2),
                    "clip_mode": True})  # kliplar ketma-ket: sarlavhasiz, o'tishlarsiz
        if series:
            out["series"] = series["series"]
            if series["series"].lower() not in out["title"].lower() and len(out["title"]) + len(series["series"]) < 85:
                out["title"] = f"{out['title']} | {series['series']}"
        if short and "#shorts" not in out["title"].lower():
            out["title"] = f"{out['title'][:90]} #Shorts"
        return out

    def pick_type(self, reference):
        """Namuna video uchun eng mos turni tanlaydi."""
        data = self._ask(
            "You classify kids YouTube videos.",
            f"""Reference video:\n{reference_text(reference)}\n
Which of these formats is closest: {json.dumps(TYPE_GUIDES)}
Return JSON: {{"type": one of {list(TYPE_GUIDES)}}}""",
            temperature=0,
        )
        return data.get("type") if data.get("type") in TYPE_GUIDES else "story"

    def write(self, video_type, minutes, topic=None, avoid_topics=(), reference=None, short=False, series=None):
        """series: doimiy qahramonlar (assets/characters/cast.yaml) — multik shu qahramonlar bilan yoziladi."""
        games = video_type == "games"
        series = series if video_type == "cartoon" else None
        wps = SHORT_WORDS_PER_SCENE if short else self.wps
        if short:
            # Shorts: tez sahnalar; o'yinda 1 gaplik kirish + 2 ta savol
            total_scenes = 3 if games else max(3, math.ceil(minutes * self.wpm / wps))
        elif video_type in SCENE_SECONDS:
            total_scenes = max(5, math.ceil(minutes * 60 / SCENE_SECONDS[video_type]))
        else:
            total_scenes = max(6, math.ceil(minutes * self.wpm / wps))
        # Uzun videolar bo'limlarga bo'linadi, shunda bitta javob juda uzun bo'lmaydi
        n_parts = max(1, math.ceil(total_scenes / 12))
        scenes_per_part = math.ceil(total_scenes / n_parts)

        avoid = ", ".join(list(avoid_topics)[-40:]) or "none"
        ref = ""
        if reference:
            # Formatni o'rganamiz, mazmunni ko'chirmaymiz (mualliflik huquqi)
            ref = f"""
The creator likes this reference video. Take its general IDEA, theme, setting and format, and make a NEW ORIGINAL
episode {"with OUR series characters" if series else "of your own"}. Do NOT copy its story beats, characters, names,
songs, catchphrases or sentences. You may add fun objects like toy cars, carts, trains or balloons if they fit the idea.
Reference:
{reference_text(reference)}
"""
        fmt = SHORT_GUIDE if short else ""
        cartoon = video_type == "cartoon"
        guide = TYPE_GUIDES[video_type]
        if series:
            genre = random.choice(series["genres"])
            pattern = random.choice(series.get("story_patterns") or ["a small friendly adventure"])
            # Har epizodda boshqa qahramonlar va boshqa "qutqaruvchi" — hamma navbat bilan chiqadi
            # Promptda ismi aytilgan qahramonlar albatta epizodga kiradi
            named = [c for c in series["characters"] if topic and c["name"].lower() in topic.lower()]
            hero = named[-1] if named else random.choice(series["characters"])
            rest = [c for c in series["characters"] if c is not hero and c not in named]
            today = [hero] + [c for c in named if c is not hero]
            if len(today) < 2:  # promptda bitta (yoki hech) qahramon bo'lsa — 1-2 ta do'st qo'shamiz
                today += random.sample(rest, k=min(len(rest), random.choice([1, 2])))
            roster = "\n".join(f"- {c['name']}: {c['look']}. Personality: {c['personality']}. "
                               f"Special skill: {c.get('skill', 'kindness')}" for c in series["characters"])
            names = [c["name"] for c in series["characters"]]
            guide = (f"An episode of the kids animated series \"{series['series']}\". Genre: {genre}. "
                     f"Story: {pattern}. Characters in this episode: {', '.join(c['name'] for c in today)}. "
                     f"Today's hero is {hero['name']}: the problem is solved by {hero['name']}'s special skill "
                     f"({hero.get('skill', 'kindness')}) — show that moment clearly in its own scene. "
                     f"Structure: a clear small problem in the beginning, a first try that does not work, "
                     f"the hero's skill saves the day, everyone celebrates, one simple lesson. "
                     f"The problem MUST be solved before the video ends. "
                     f"Gentle and never scary — nobody is ever hurt or in real danger. "
                     f"Today is {datetime.now():%B %d}.\nMain characters (use 2-4 of them, keep their personalities, "
                     f"do NOT invent new main characters; tiny side characters like a butterfly are fine):\n{roster}")
        props_field = ('\n  "props": 0-2 fun objects that appear in the episode (toy car, cart, train, ball, balloon...), '
                       'each {"name": short name, "look": visual description},') if cartoon else ""
        cast_field = ('\n  "cast": list of 2-3 main characters, each {"name": short name, "look": full visual description '
                      '(species, colors, clothes, accessories)},') if cartoon else ""
        if series:
            cast_field = f'\n  "cast": list of the character names used in this episode, chosen from {json.dumps(names)},'
        outline = self._ask(
            SAFETY_RULES,
            f"""Plan a {"YouTube Short (vertical, under 60 seconds)" if short else f"{minutes}-minute"} kids video. Type: {guide}{fmt}{ref}
Topic: {topic or "choose a fresh, original topic"}. Do NOT reuse these topics: {avoid}.
Return JSON:
{{"topic": short topic name,
  "title": catchy YouTube title under 70 characters,
  "description": YouTube description, 2-3 short paragraphs, kid and parent friendly,
  "tags": list of 10-15 tags,
  "characters": visual description of the main characters (species, colors, clothes) to keep images consistent, or "" if none,{cast_field}{props_field}
  "parts": list of exactly {n_parts} objects {{"summary": what happens or is taught in this part}}}}""",
        )

        if series:
            # Ismlar ro'yxatini to'liq qahramon ma'lumotiga (rasm bilan) almashtiramiz
            by_name = {c["name"].lower(): c for c in series["characters"]}
            cast = [by_name[n.lower()] for n in outline.get("cast", []) if isinstance(n, str) and n.lower() in by_name]
            outline["cast"] = cast or series["characters"][:3]
            outline["characters"] = "; ".join(f"{c['name']}: {c['look']}" for c in outline["cast"])
            outline["series"] = series["series"]
        # Model ba'zan so'ralganidan ko'p bo'lim qaytaradi — video uzunligi oshib ketmasin
        outline["parts"] = outline["parts"][:n_parts]
        scenes = []
        for i, part in enumerate(outline["parts"]):
            start = ("(this is the very beginning; open with a one-sentence hook — a question or a surprising fact, no greeting)"
                     if short else "(this is the very beginning; start with a warm hello)")
            prev = scenes[-1]["narration"] if scenes else start
            is_last = i == len(outline["parts"]) - 1
            if short:
                ending = "Keep it fast. The very last sentence of the video is: Follow for more!"
            elif is_last:
                ending = "End the video with a short recap and a friendly goodbye asking kids to come back for more."
            else:
                ending = "Do not end the video yet."
            example = ('{"narration": "...", "quiz": {"question": "...", "options": ["...", "...", "..."], "answer": 1}, '
                       '"answer_narration": "...", "image_prompt": "...", "search_query": "..."}' if games
                       else '{"narration": "...", "image_prompt": "...", "search_query": "..."}')
            rules = ""
            has_intro = games and i == 0
            has_outro = games and not short and is_last
            if games:
                first = ""
                if has_intro:
                    first = ("Scene 1 is a one-sentence hook that invites kids to play (no quiz, max 12 words). " if short
                             else "Scene 1 is a short welcome that explains the game (no quiz). ")
                last = "The final scene is a short goodbye (no quiz). " if has_outro else ""
                rules = f"{QUIZ_FORMAT}\n{first}{last}EVERY other scene MUST be a quiz scene with the quiz and answer_narration fields."
            if short:
                rules += "\nimage_prompt: vertical portrait composition, subject in the center."
            if cartoon:
                names = [c["name"] for c in outline.get("cast", [])]
                props = [p["name"] for p in outline.get("props") or []]
                rules += f"\n{CARTOON_FORMAT}\nCast list: {json.dumps(names)}\nProps list: {json.dumps(props)}"
                example = example[:-1] + ', "background_prompt": "...", "cast": [{"name": "...", "position": "left", "action": "hop", "emotion": "happy"}], "speaker": "...", "effect": "sparkles", "props": []}' 
            data = self._ask_scenes(games, has_intro, has_outro,
                SAFETY_RULES,
                f"""Video title: {outline["title"]}
Characters: {outline.get("characters") or "none"}
Full plan: {json.dumps([p["summary"] for p in outline["parts"]])}
Now write part {i + 1} of {n_parts}: {part["summary"]}
The previous narration was: {prev}
Write exactly {scenes_per_part} scenes, each narration about {wps} words. {ending}
{rules}
Return JSON: {{"scenes": [{example}]}}""",
            )
            # Oxirgi bo'limdan boshqasini kesamiz; oxirgisida xayrlashuv bor
            scenes.extend(data["scenes"] if is_last else data["scenes"][:scenes_per_part])

        self._moderate(scenes)
        outline.pop("parts", None)
        outline["scenes"] = scenes
        outline["type"] = video_type
        outline["minutes"] = minutes
        outline["format"] = "short" if short else "long"
        if series and series["series"].lower() not in outline["title"].lower():
            branded = f"{outline['title']} | {series['series']}"
            if len(branded) <= (85 if short else 100):
                outline["title"] = branded
        if short and "#shorts" not in outline["title"].lower():
            outline["title"] = f"{outline['title'][:90]} #Shorts"
        return outline

    def _ask_scenes(self, games, has_intro, has_outro, system, user, tries=3):
        """O'yinda savol sahnalari bo'lishi shart — bo'lmasa qayta so'raymiz."""
        for _ in range(tries):
            data = self._ask(system, user)
            if not games:
                return data
            scenes = data.get("scenes", [])
            middle = scenes[1 if has_intro else 0:len(scenes) - (1 if has_outro else 0)]
            if middle and all(_valid_quiz(sc) for sc in middle):
                return data
            print("  (savollar to'liq emas — ssenariy qayta so'ralmoqda)")
        raise RuntimeError("OpenAI viktorina savollarini to'g'ri yozmadi, qayta urinib ko'ring.")

    def _moderate(self, scenes):
        text = "\n".join(s["narration"] + " " + s.get("answer_narration", "") for s in scenes)
        result = self.client.moderations.create(model="omni-moderation-latest", input=text)
        if result.results[0].flagged:
            raise RuntimeError("Ssenariy moderatsiyadan o'tmadi — qayta urinib ko'ring yoki mavzuni o'zgartiring.")


def _valid_quiz(scene):
    q = scene.get("quiz") or {}
    return (isinstance(q.get("options"), list) and len(q["options"]) == 3 and q.get("question")
            and q.get("answer") in (0, 1, 2) and scene.get("answer_narration"))


def reference_text(ref):
    parts = [f"Title: {ref.get('title', '')}",
             f"Duration: {ref.get('minutes', '?')} min",
             f"Description: {ref.get('description', '')[:1500]}",
             f"Tags: {', '.join(ref.get('tags', [])[:20])}"]
    if ref.get("analysis"):
        parts.append(f"Idea analysis (from title, description and thumbnail): {json.dumps(ref['analysis'])}")
    if ref.get("transcript"):
        parts.append(f"Transcript (beginning): {ref['transcript'][:4000]}")
    return "\n".join(parts)

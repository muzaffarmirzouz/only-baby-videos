"""OpenAI orqali bolalar videosi ssenariysini yozish."""
import json
import math

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

SCENE_SECONDS = {"games": 22}  # savol + 5 soniya taymer + javob


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

    def write(self, video_type, minutes, topic=None, avoid_topics=(), reference=None):
        if video_type in SCENE_SECONDS:
            total_scenes = max(5, math.ceil(minutes * 60 / SCENE_SECONDS[video_type]))
        else:
            total_scenes = max(6, math.ceil(minutes * self.wpm / self.wps))
        # Uzun videolar bo'limlarga bo'linadi, shunda bitta javob juda uzun bo'lmaydi
        n_parts = max(1, math.ceil(total_scenes / 12))
        scenes_per_part = math.ceil(total_scenes / n_parts)

        avoid = ", ".join(list(avoid_topics)[-40:]) or "none"
        ref = ""
        if reference:
            # Formatni o'rganamiz, mazmunni ko'chirmaymiz (mualliflik huquqi)
            ref = f"""
The creator likes this reference video. Study its FORMAT only: hook, pacing, structure, tone, type of humor, how it talks to kids.
Make a NEW ORIGINAL video in the same format. Do NOT copy its story, characters, names, songs or sentences.
Reference:
{reference_text(reference)}
"""
        outline = self._ask(
            SAFETY_RULES,
            f"""Plan a {minutes}-minute kids video. Type: {TYPE_GUIDES[video_type]}{ref}
Topic: {topic or "choose a fresh, original topic"}. Do NOT reuse these topics: {avoid}.
Return JSON:
{{"topic": short topic name,
  "title": catchy YouTube title under 70 characters,
  "description": YouTube description, 2-3 short paragraphs, kid and parent friendly,
  "tags": list of 10-15 tags,
  "characters": visual description of the main characters (species, colors, clothes) to keep images consistent, or "" if none,
  "parts": list of exactly {n_parts} objects {{"summary": what happens or is taught in this part}}}}""",
        )

        # Model ba'zan so'ralganidan ko'p bo'lim qaytaradi — video uzunligi oshib ketmasin
        outline["parts"] = outline["parts"][:n_parts]
        scenes = []
        for i, part in enumerate(outline["parts"]):
            prev = scenes[-1]["narration"] if scenes else "(this is the very beginning; start with a warm hello)"
            is_last = i == len(outline["parts"]) - 1
            ending = "End the video with a short recap and a friendly goodbye asking kids to come back for more." if is_last else "Do not end the video yet."
            games = video_type == "games"
            example = ('{"narration": "...", "quiz": {"question": "...", "options": ["...", "...", "..."], "answer": 1}, '
                       '"answer_narration": "...", "image_prompt": "...", "search_query": "..."}' if games
                       else '{"narration": "...", "image_prompt": "...", "search_query": "..."}')
            rules = ""
            if games:
                first = "Scene 1 is a short welcome that explains the game (no quiz). " if i == 0 else ""
                last = "The final scene is a short goodbye (no quiz). " if is_last else ""
                rules = f"{QUIZ_FORMAT}\n{first}{last}EVERY other scene MUST be a quiz scene with the quiz and answer_narration fields."
            data = self._ask_scenes(games, i == 0, is_last,
                SAFETY_RULES,
                f"""Video title: {outline["title"]}
Characters: {outline.get("characters") or "none"}
Full plan: {json.dumps([p["summary"] for p in outline["parts"]])}
Now write part {i + 1} of {n_parts}: {part["summary"]}
The previous narration was: {prev}
Write exactly {scenes_per_part} scenes, each narration about {self.wps} words. {ending}
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
    if ref.get("transcript"):
        parts.append(f"Transcript (beginning): {ref['transcript'][:4000]}")
    return "\n".join(parts)

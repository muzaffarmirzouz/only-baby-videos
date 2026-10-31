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
}


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

    def write(self, video_type, minutes, topic=None, avoid_topics=()):
        total_scenes = max(6, math.ceil(minutes * self.wpm / self.wps))
        # Uzun videolar bo'limlarga bo'linadi, shunda bitta javob juda uzun bo'lmaydi
        n_parts = max(1, math.ceil(total_scenes / 12))
        scenes_per_part = math.ceil(total_scenes / n_parts)

        avoid = ", ".join(list(avoid_topics)[-40:]) or "none"
        outline = self._ask(
            SAFETY_RULES,
            f"""Plan a {minutes}-minute kids video. Type: {TYPE_GUIDES[video_type]}
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
            data = self._ask(
                SAFETY_RULES,
                f"""Video title: {outline["title"]}
Characters: {outline.get("characters") or "none"}
Full plan: {json.dumps([p["summary"] for p in outline["parts"]])}
Now write part {i + 1} of {n_parts}: {part["summary"]}
The previous narration was: {prev}
Write exactly {scenes_per_part} scenes, each narration about {self.wps} words. {ending}
Return JSON: {{"scenes": [{{"narration": "...", "image_prompt": "...", "search_query": "..."}}]}}""",
            )
            # Oxirgi bo'limdan boshqasini kesamiz; oxirgisida xayrlashuv bor
            scenes.extend(data["scenes"] if is_last else data["scenes"][:scenes_per_part])

        self._moderate(scenes)
        outline.pop("parts", None)
        outline["scenes"] = scenes
        outline["type"] = video_type
        outline["minutes"] = minutes
        return outline

    def _moderate(self, scenes):
        text = "\n".join(s["narration"] for s in scenes)
        result = self.client.moderations.create(model="omni-moderation-latest", input=text)
        if result.results[0].flagged:
            raise RuntimeError("Ssenariy moderatsiyadan o'tmadi — qayta urinib ko'ring yoki mavzuni o'zgartiring.")

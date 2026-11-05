"""Davomli serial: har kuni yangi epizod, qahramonlar oldingi epizodlarni "eslaydi".

Har kunning rejasi episodes/YYYY-MM-DD.json da: 13:00 da tuziladi (Flow promptlari Telegram'ga), 23:00 da shu reja
asosida uzun video yasaladi va natija (YouTube havolasi) shu faylga yoziladi.
"""
import html
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
TASHKENT = timezone(timedelta(hours=5))


def today():
    return datetime.now(TASHKENT).strftime("%Y-%m-%d")


def plan_path(day=None):
    return EPISODES / f"{day or today()}.json"


def history(limit=10):
    """Oldingi epizodlar (eng yangisi oxirida)."""
    files = sorted(EPISODES.glob("*.json"))
    return [json.loads(f.read_text()) for f in files if f.stem != today()][-limit:]


def load_or_create(writer, series):
    path = plan_path()
    if path.exists():
        return json.loads(path.read_text())
    past = history()
    plan = writer.plan_episode(series, past)
    plan["date"] = today()
    plan["number"] = (past[-1].get("number", len(past)) if past else 0) + 1
    EPISODES.mkdir(exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    return plan


def topic_for(plan):
    """23:00 dagi uzun video uchun batafsil prompt."""
    beats = " ".join(f"{i + 1}) {b}" for i, b in enumerate(plan.get("beats", [])))
    return (f"Episode {plan.get('number', '')} of the season: \"{plan['title']}\". {plan['summary']} "
            f"Story beats: {beats} Lesson: {plan.get('lesson', '')}")


def record(plan, video_url=None, title=None):
    plan["video"] = video_url
    if title:
        plan["video_title"] = title
    plan_path(plan.get("date")).write_text(json.dumps(plan, indent=2, ensure_ascii=False))


def send_flow_prompts(plan):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("Telegram sozlanmagan — promptlar yuborilmadi")
        return
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    head = (f"🎬 <b>Bugungi epizod #{plan.get('number', '')}: {html.escape(plan['title'])}</b>\n\n"
            f"📖 {html.escape(plan['summary'])}\n\n🎓 Saboq: {html.escape(plan.get('lesson', ''))}\n\n"
            f"Bu epizod soat 23:00 da 2–3 daqiqalik video bo'lib o'zi chiqadi.\n"
            f"Vaqtingiz bo'lsa, quyidagi {len(plan.get('flow_prompts', []))} ta promptni Flow'da yasang "
            f"(Shorts uchun 9:16), kliplarni ketma-ket botga yuborib /epizod yozing 👇")
    requests.post(api, data={"chat_id": chat, "text": head, "parse_mode": "HTML"}, timeout=30)
    for i, p in enumerate(plan.get("flow_prompts", []), 1):
        requests.post(api, data={"chat_id": chat, "parse_mode": "HTML",
                                 "text": f"📋 <b>{i}-klip</b>\n<code>{html.escape(p)}</code>"}, timeout=30)

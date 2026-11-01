"""Meta vaqtinchalik tokenini muddatsiz Facebook sahifa tokeniga almashtiradi va Instagram ID'ni topadi.

.env da kerak: META_APP_ID, META_APP_SECRET, META_SHORT_TOKEN (Graph API Explorer'dan).
Natija .env ga yoziladi: INSTAGRAM_TOKEN, INSTAGRAM_USER_ID. Tokenlar ekranga chiqarilmaydi.
"""
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
GRAPH = "https://graph.facebook.com/v26.0"


def set_env(key, value):
    env = ROOT / ".env"
    lines = [l for l in env.read_text().splitlines() if not l.startswith(f"{key}=")]
    env.write_text("\n".join(lines + [f"{key}={value}"]) + "\n")


def main():
    env = dotenv_values(ROOT / ".env")
    # System User tokeni (Business sozlamalari, "Никогда") almashtirishsiz ishlaydi;
    # Graph API Explorer tokeni esa avval uzoq muddatliga almashtiriladi
    token = env["META_SHORT_TOKEN"]
    long = requests.get(f"{GRAPH}/oauth/access_token", timeout=30, params={
        "grant_type": "fb_exchange_token", "client_id": env["META_APP_ID"],
        "client_secret": env["META_APP_SECRET"], "fb_exchange_token": token}).json()
    if "access_token" in long:
        token = long["access_token"]
    pages = requests.get(f"{GRAPH}/me/accounts", timeout=30, params={
        "fields": "name,access_token,instagram_business_account{id,username}",
        "access_token": token}).json()
    found = [p for p in pages.get("data", []) if p.get("instagram_business_account")]
    if not found:
        raise SystemExit("Instagram professional akkauntga ulangan Facebook sahifa topilmadi "
                         f"(sahifalar: {[p.get('name') for p in pages.get('data', [])]})")
    page = found[0]
    ig = page["instagram_business_account"]
    # Uzoq muddatli foydalanuvchi tokenidan olingan sahifa tokeni muddatsiz
    set_env("INSTAGRAM_TOKEN", page["access_token"])
    set_env("INSTAGRAM_USER_ID", ig["id"])
    debug = requests.get(f"{GRAPH}/debug_token", timeout=30, params={
        "input_token": page["access_token"], "access_token": f"{env['META_APP_ID']}|{env['META_APP_SECRET']}"}).json()
    expires = debug.get("data", {}).get("expires_at", "?")
    print(f"Tayyor: sahifa '{page['name']}', Instagram @{ig.get('username')}, "
          f"token muddati: {'muddatsiz' if expires == 0 else expires}")


if __name__ == "__main__":
    main()

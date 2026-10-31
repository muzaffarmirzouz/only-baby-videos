#!/bin/zsh
# .env, client_secret.json va token.json dagi kalitlarni GitHub Secrets'ga qo'yadi.
# Kalitlar ekranda ko'rinmaydi. Ishga tushirish: zsh scripts/set_github_secrets.sh
set -e
cd "$(dirname "$0")/.."

for name in OPENAI_API_KEY PIXABAY_API_KEY POLLINATIONS_KEY GEMINI_API_KEY; do
  value=$(grep "^$name=" .env | cut -d= -f2- | tr -d '\n')
  if [ -n "$value" ]; then
    printf '%s' "$value" | gh secret set "$name" >/dev/null
    echo "  $name: qo'yildi"
  fi
done
gh secret set YOUTUBE_CLIENT_SECRET < client_secret.json >/dev/null && echo "  YOUTUBE_CLIENT_SECRET: qo'yildi"
gh secret set YOUTUBE_TOKEN < token.json >/dev/null && echo "  YOUTUBE_TOKEN: qo'yildi"
echo
gh secret list
echo
echo "TAYYOR! Endi chatga 'bo'ldi' deb yozing."

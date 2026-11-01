#!/bin/zsh
# Telegram botni Cloudflare'ga joylaydi va ulaydi. Kalitlar .env dan olinadi, ekranda ko'rinmaydi.
# Oldin: npx wrangler login (bir marta). Ishga tushirish: zsh scripts/setup_bot.sh
set -e
cd "$(dirname "$0")/.."

env_get() { grep "^$1=" .env | cut -d= -f2- | tr -d '\n'; }
TG_TOKEN=$(env_get TELEGRAM_BOT_TOKEN)
TG_CHAT=$(env_get TELEGRAM_CHAT_ID)
GH_TOKEN_BOT=$(env_get GITHUB_BOT_TOKEN)
for v in TG_TOKEN TG_CHAT GH_TOKEN_BOT; do
  if [ -z "${(P)v}" ]; then echo "❌ .env da $v yo'q"; exit 1; fi
done
WEBHOOK_SECRET=$(env_get WEBHOOK_SECRET)
if [ -z "$WEBHOOK_SECRET" ]; then
  WEBHOOK_SECRET=$(openssl rand -hex 24)
  echo "WEBHOOK_SECRET=$WEBHOOK_SECRET" >> .env
fi

echo "1/4 Cloudflare'ga joylanmoqda..."
cd bot
[ -d node_modules ] || npm install --silent
# Birinchi marta Cloudflare workers.dev nomini so'rashi mumkin — savolga javob bering
npx wrangler deploy --var "ALLOWED_USER_ID:$TG_CHAT"
URL=$(npx wrangler deploy --var "ALLOWED_USER_ID:$TG_CHAT" 2>&1 | grep -o 'https://[a-zA-Z0-9.-]*\.workers\.dev' | head -1)
if [ -z "$URL" ]; then echo "❌ Worker manzili topilmadi (yuqoridagi xatoga qarang)"; exit 1; fi
echo "   Manzil: $URL"

echo "2/4 Worker kalitlari..."
printf '%s' "$TG_TOKEN" | npx wrangler secret put TELEGRAM_BOT_TOKEN >/dev/null
printf '%s' "$GH_TOKEN_BOT" | npx wrangler secret put GITHUB_TOKEN >/dev/null
printf '%s' "$WEBHOOK_SECRET" | npx wrangler secret put WEBHOOK_SECRET >/dev/null
cd ..

echo "3/4 Telegram ulanmoqda..."
API="https://api.telegram.org/bot$TG_TOKEN"
curl -s -o /dev/null "$API/setWebhook" -d url="$URL/tg" -d secret_token="$WEBHOOK_SECRET" \
  --data-urlencode 'allowed_updates=["message","callback_query"]'
curl -s -o /dev/null "$API/setChatMenuButton" -H 'Content-Type: application/json' \
  -d "{\"menu_button\":{\"type\":\"web_app\",\"text\":\"Studio\",\"web_app\":{\"url\":\"$URL/app\"}}}"
curl -s -o /dev/null "$API/setMyCommands" -H 'Content-Type: application/json' \
  -d '{"commands":[{"command":"new","description":"Yangi video"},{"command":"epizod","description":"Yuborilgan kliplardan epizod"},{"command":"bekor","description":"Kliplarni tozalash"},{"command":"status","description":"Videolar holati"},{"command":"help","description":"Yordam"}]}'

echo "4/4 GitHub xabarnoma kalitlari..."
printf '%s' "$TG_TOKEN" | gh secret set TELEGRAM_BOT_TOKEN >/dev/null
printf '%s' "$TG_CHAT" | gh secret set TELEGRAM_CHAT_ID >/dev/null

echo
echo "✅ TAYYOR! Telegram'da botga /start yozing."

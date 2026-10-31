#!/bin/zsh
# assets/music ni yopiq GitHub repoga (only-baby-music) yuklaydi va workflow uchun MUSIC_TOKEN secret'ini qo'yadi.
# Oldin: only-baby-bot fine-grained tokeniga only-baby-music repo uchun "Contents: Read-only" ruxsatini qo'shing.
# Ishga tushirish: zsh scripts/setup_music.sh
set -e
cd "$(dirname "$0")/.."

cd assets/music
git add -A
git diff --cached --quiet || git commit -q -m "Musiqa yangilandi"
if git remote get-url origin >/dev/null 2>&1; then
  git push -q origin main
else
  gh repo create only-baby-music --private --source . --remote origin --push
fi
echo "  Musiqa yopiq repoga yuklandi: $(gh repo view muzaffarmirzouz/only-baby-music --json visibility -q .visibility)"
cd ../..

grep '^GITHUB_BOT_TOKEN=' .env | cut -d= -f2- | tr -d '\n' | gh secret set MUSIC_TOKEN >/dev/null
echo "  MUSIC_TOKEN secret qo'yildi"
echo
echo "TAYYOR! Chatga 'bo'ldi' deb yozing."

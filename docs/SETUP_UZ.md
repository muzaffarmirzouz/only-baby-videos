# O'rnatish qo'llanmasi (tekin bosqich)

Tizim nima qiladi: **mavzu → ssenariy (OpenAI) → ovoz (edge-tts) → rasmlar (Pollinations) → montaj (Remotion, `video/` papka) → YouTube'ga yuklash (YouTube API)**.
Faqat OpenAI pullik (~$0.01–0.05 bir video uchun). Qolgani tekin.

## 1. OpenAI API kaliti
1. https://platform.openai.com/api-keys → **Create new secret key**.
2. Billing bo'limiga $5 qo'shing (yuzlab videoga yetadi).
3. Loyiha papkasida:
   ```bash
   cp .env.example .env
   ```
   `.env` faylini ochib `OPENAI_API_KEY=sk-...` qatoriga kalitni qo'ying.

## 2. Birinchi video (yuklamasdan)
Bir marta o'rnatish (Python va Remotion paketlari):
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
cd video && npm install && cd ..
```

```bash
.venv/bin/python main.py --type story --length 3 --no-upload
```
Natija: `output/<sana-nom>/final.mp4` va `thumbnail.jpg`. Ochib ko'ring.

## 3. YouTube API (bir marta, ~10 daqiqa) — parol kerak emas
1. https://console.cloud.google.com → yangi loyiha yarating (masalan `kids-videos`).
2. **APIs & Services → Library** → "YouTube Data API v3" → **Enable**.
3. **APIs & Services → OAuth consent screen** → External → ilova nomi, emailingiz → saqlang.
   **Audience / Test users** bo'limiga o'zingizning Gmail'ingizni qo'shing.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → turi **Desktop app**.
5. JSON faylni yuklab oling, nomini `client_secret.json` qilib loyiha papkasiga (`baby/`) qo'ying.
6. Birinchi yuklashda brauzer ochiladi — kanalingiz akkauntiga **o'zingiz** kirib "Allow" bosasiz.
   Keyin `token.json` saqlanadi va tizim boshqa so'ramaydi.

> Eslatma: Google tekshirmagan (unverified) ilova orqali yuklangan videolar avtomatik `private` bo'lib qolishi mumkin.
> Buni ochish uchun Google Cloud'da "API audit" so'rovini yuborish kerak — yoki videolarni YouTube Studio'da qo'lda `public` qilasiz.

## 4. Yuklash bilan ishga tushirish
```bash
.venv/bin/python main.py --type story --length 3
.venv/bin/python main.py --type education --length 10 --topic "numbers 1 to 20"
.venv/bin/python main.py --type facts --length 20 --privacy unlisted
```
Turlari: `story` (ertak), `education` (ABC, sonlar, ranglar), `facts` (qiziqarli faktlar).
Uzunlik: istalgan daqiqa (`3`, `10`, `15`, `20`).

## 5. Fon musiqasi (ixtiyoriy)
YouTube Studio → **Audio Library** yoki https://pixabay.com/music/ dan bolalarga mos 3–5 ta tekin trek yuklab,
`assets/music/` papkasiga `.mp3` qilib qo'ying. Tizim har videoga tasodifiy birini tanlaydi.

## Tezlik (tekin rejim)
Pollinations tekin rejimda 45 soniyada 1 ta rasm beradi:
3 daqiqalik video ≈ 12 rasm ≈ 10 daqiqa; 20 daqiqalik video ≈ 60 rasm ≈ 50 daqiqa.
Tezlashtirish uchun `.env` ga `POLLINATIONS_KEY` qo'ying. Rasm o'ng pastki burchagida kichik Pollinations belgisi bo'ladi.

## Montajni ko'rish/tahrirlash (Remotion Studio)
```bash
cd video && npm run dev
```
Dizayn `video/src/Composition.tsx` da: intro sarlavha, Ken Burns harakati, subtitrlar, o'tishlar.

## Sozlamalar — `config.yaml`
- `voice` — ovoz (masalan `en-US-AnaNeural` bola ovozi).
- `youtube.privacy` — `private` / `unlisted` / `public`.
- `image_style` — rasmlar uslubi.

## Muhim qoidalar
- **Made for kids** har doim yoqilgan (COPPA qonuni talabi).
- YouTube takroriy, ommaviy AI kontentni monetizatsiyadan chiqaradi. Har videoni ko'rib chiqing, mavzular turlicha bo'lsin.
- API kvotasi: kuniga taxminan 6 ta video yuklash mumkin (tekin).
- Agar video yarmida to'xtasa — o'sha buyruqni `--from-script output/.../script.json` bilan qayta ishga tushiring, tayyor sahnalar qayta qilinmaydi.

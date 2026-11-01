// Only Baby Telegram bot + Mini App (Cloudflare Worker).
// Bot faqat ALLOWED_USER_ID ga javob beradi; videolar GitHub Actions'da yasaladi.
import APP_HTML from "./app.html";

const WORKFLOW = "daily-video.yml";
const TYPES = { auto: "Avto", story: "Ertak", education: "Ta'limiy", facts: "Faktlar", cartoon: "Multik", games: "O'yin" };
const YT_RE = /https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/\S+/;
const LENGTHS = ["3", "5", "10", "15", "20"];
const STYLES = ["auto", "stock", "ai"];
const PRIVACY = ["public", "unlisted", "private"];
const VOICES = [
  "en-US-JennyNeural", "en-US-AnaNeural", "en-US-AriaNeural",
  "en-GB-SoniaNeural", "en-US-GuyNeural", "en-US-AndrewNeural",
];
const NO_TOPIC = "AI o'zi tanlaydi";
const MAX_TOPIC = 2000; // prompt uzunligi (Telegram xabari 4096 belgigacha)

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      if (url.pathname === "/tg" && req.method === "POST") {
        if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
          return new Response("forbidden", { status: 403 });
        }
        await handleUpdate(await req.json(), env, url.origin);
        return new Response("ok");
      }
      if (url.pathname === "/" || url.pathname === "/app") {
        return new Response(APP_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
      }
      if (url.pathname.startsWith("/api/")) {
        const user = await verifyInitData(req.headers.get("X-Telegram-Init-Data"), env.TELEGRAM_BOT_TOKEN);
        if (!user || String(user.id) !== String(env.ALLOWED_USER_ID)) return json({ error: "Ruxsat yo'q" }, 403);
        if (url.pathname === "/api/runs") return json(await listRuns(env));
        if (url.pathname === "/api/create" && req.method === "POST") {
          await createVideo(env, await req.json());
          return json({ ok: true });
        }
      }
      return new Response("not found", { status: 404 });
    } catch (e) {
      console.error(e);
      return json({ error: String(e.message || e) }, 500);
    }
  },
};

// ---------- GitHub ----------

async function github(env, path, init = {}) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "only-baby-bot",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.status === 204 ? null : r.json();
}

async function createVideo(env, o) {
  const inputs = {
    topic: String(o.topic || "").replace(/\s+/g, " ").trim().slice(0, MAX_TOPIC),
    reference: YT_RE.test(String(o.reference || "")) ? String(o.reference).match(YT_RE)[0] : "",
    type: TYPES[o.type] ? o.type : "auto",
    format: o.format === "short" ? "short" : "long",
    length: o.format === "short" ? "" : LENGTHS.includes(String(o.length)) ? String(o.length) : "3",
    style: STYLES.includes(o.style) ? o.style : "auto",
    voice: VOICES.includes(o.voice) ? o.voice : VOICES[0],
    privacy: PRIVACY.includes(o.privacy) ? o.privacy : "public",
    review: "true", // buyurtmalar avval Telegram'da ko'rsatiladi, "Joyla" bosilganda yuklanadi
    clips: String(o.clips || "").replace(/[^A-Za-z0-9_\-,]/g, ""), // Flow kliplari (Telegram file_id)
  };
  await github(env, `/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main", inputs }),
  });
  return inputs;
}

async function listRuns(env, limit = 10) {
  const data = await github(env, `/actions/workflows/${WORKFLOW}/runs?per_page=${limit}`);
  return data.workflow_runs.map((r) => ({
    title: r.display_title,
    status: r.status,
    conclusion: r.conclusion,
    created: r.created_at,
    url: r.html_url,
    event: r.event,
  }));
}

// ---------- Telegram ----------

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

const studioButton = (origin) => [{ text: "🎬 Studio", web_app: { url: `${origin}/app` } }];

function typeKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "🎲 Avto", callback_data: "t:auto" }, { text: "📖 Ertak", callback_data: "t:story" }],
      [{ text: "🔤 Ta'limiy", callback_data: "t:education" }, { text: "🦋 Faktlar", callback_data: "t:facts" }],
      [{ text: "🎨 Multik", callback_data: "t:cartoon" }, { text: "🎮 O'yin", callback_data: "t:games" }],
    ],
  };
}

function lengthKeyboard(type) {
  return {
    inline_keyboard: [
      [{ text: "📱 Shorts (~45 soniya)", callback_data: `go:${type}:short` }],
      LENGTHS.map((l) => ({ text: `${l} daq`, callback_data: `go:${type}:${l}` })),
      [{ text: "← Orqaga", callback_data: "back" }],
    ],
  };
}

const referenceFrom = (text) => (/Namuna: (\S+)/.exec(text || "") || [])[1] || "";

const topicFrom = (text) => {
  const m = /Mavzu: (.+)/.exec(text || "");
  return !m || m[1] === NO_TOPIC ? "" : m[1].trim();
};

async function handleUpdate(update, env, origin) {
  const from = update.message?.from || update.callback_query?.from;
  if (!from) return;
  const allowed = String(from.id) === String(env.ALLOWED_USER_ID);

  if (update.message) {
    const chat_id = update.message.chat.id;
    const text = (update.message.text || "").trim();
    if (!allowed) {
      return tg(env, "sendMessage", { chat_id, text: "Bu shaxsiy bot. Kechirasiz 🙏" });
    }
    // Flow (yoki boshqa) kliplar: /epizod buyrug'igacha yig'iladi
    const media = update.message.video ||
      (update.message.document?.mime_type?.startsWith("video/") ? update.message.document : null);
    if (media) return receiveClip(env, chat_id, media);
    if (text.startsWith("/epizod")) return makeEpisode(env, chat_id, text.slice(7).trim());
    if (text === "/bekor") {
      await env.CLIPS.delete(`clips:${chat_id}`);
      return tg(env, "sendMessage", { chat_id, text: "🗑 Yuborilgan kliplar tozalandi." });
    }
    if (text === "/start" || text === "/help") {
      return tg(env, "sendMessage", {
        chat_id,
        text:
          "👋 Only Baby Studio\n\n" +
          "• Mavzuni shunchaki yozing — video yasayman\n" +
          "• YouTube havolasini yuboring — g'oyasi asosida bizning qahramonlar bilan video\n" +
          "• Flow kliplarini yuboring, keyin /epizod [prompt] — ulardan epizod yasayman\n" +
          "   (istak qo'shsa bo'ladi: havola + \"mashinachalar qo'sh\")\n" +
          "• /new — yangi video (AI mavzu tanlaydi)\n" +
          "• /status — oxirgi videolar holati\n" +
          "• 🎬 Studio — to'liq panel\n\n" +
          "Video tayyor bo'lganda o'zim xabar beraman.",
        reply_markup: { inline_keyboard: [studioButton(origin)] },
      });
    }
    if (text === "/status") {
      const runs = await listRuns(env, 5);
      const lines = runs.map((r) => `${runIcon(r)} ${r.title}\n    ${runLabel(r)} · ${ago(r.created)}`);
      return tg(env, "sendMessage", {
        chat_id,
        text: lines.length ? lines.join("\n\n") : "Hali video yo'q.",
        reply_markup: { inline_keyboard: [studioButton(origin)] },
      });
    }
    // YouTube havola → namuna asosida video
    const link = text.match(YT_RE);
    if (link) {
      // Havoladan tashqari yozilgan matn — istak (masalan "mashinachalar qo'sh")
      const wish = text.replace(link[0], "").replace(/^\/new/, "").replace(/\s+/g, " ").trim().slice(0, MAX_TOPIC);
      return tg(env, "sendMessage", {
        chat_id,
        text: `🔗 Shu g'oya asosida bizning qahramonlar bilan yangi video\nNamuna: ${link[0]}\nMavzu: ${wish || NO_TOPIC}\n\nTurini tanlang (Avto — multik):`,
        reply_markup: typeKeyboard(),
        link_preview_options: { is_disabled: true },
      });
    }
    // /new [mavzu] yoki oddiy matn → mavzu
    let topic = text.startsWith("/new") ? text.slice(4).trim() : text;
    if (topic.startsWith("/")) {
      return tg(env, "sendMessage", { chat_id, text: "Bunday buyruq yo'q. /help ni bosing." });
    }
    // Ko'p qatorli prompt bitta qatorga (xabardan qayta o'qilganda to'liq olinsin)
    topic = topic.replace(/\s+/g, " ").slice(0, MAX_TOPIC);
    return tg(env, "sendMessage", {
      chat_id,
      text: `🎬 Yangi video\nMavzu: ${topic || NO_TOPIC}\n\nTurini tanlang:`,
      reply_markup: typeKeyboard(),
    });
  }

  const cq = update.callback_query;
  if (!allowed) return tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "Ruxsat yo'q" });

  // Ko'rib chiqilgan video: "✅ Joyla" / "🗑 O'chir"
  const review = /^(pub|del):(\d+)$/.exec(cq.data || "");
  if (review) return handleReview(env, cq, review[1], review[2]);
  const chat_id = cq.message.chat.id;
  const message_id = cq.message.message_id;
  const topic = topicFrom(cq.message.text);
  const reference = referenceFrom(cq.message.text);
  const head = reference
    ? `🔗 Shu g'oya asosida bizning qahramonlar bilan yangi video\nNamuna: ${reference}\nMavzu: ${topic || NO_TOPIC}`
    : `🎬 Yangi video\nMavzu: ${topic || NO_TOPIC}`;
  const [kind, type, length] = cq.data.split(":");

  if (kind === "t") {
    await tg(env, "editMessageText", {
      chat_id, message_id, text: `${head}\nTuri: ${TYPES[type]}\n\nShorts yoki uzunligini tanlang:`,
      reply_markup: lengthKeyboard(type),
    });
  } else if (kind === "back") {
    await tg(env, "editMessageText", { chat_id, message_id, text: `${head}\n\nTurini tanlang:`, reply_markup: typeKeyboard() });
  } else if (kind === "go") {
    try {
      const short = length === "short";
      await createVideo(env, { topic, type, length, reference, format: short ? "short" : "long" });
      await tg(env, "editMessageText", {
        chat_id, message_id,
        text: `${head}\nTuri: ${TYPES[type]} · ${short ? "Shorts" : `${length} daqiqa`}\n\n✅ Buyurtma qabul qilindi! Tayyor bo'lganda videoni shu yerga yuboraman — ko'rib, "Joyla" deb tasdiqlaysiz.`,
      });
    } catch (e) {
      await tg(env, "editMessageText", { chat_id, message_id, text: `${head}\n\n❌ Xato: ${e.message}` });
    }
  }
  return tg(env, "answerCallbackQuery", { callback_query_id: cq.id });
}

const MAX_CLIP_MB = 20; // Telegram bot 20 MB dan katta faylni yuklab ololmaydi

async function receiveClip(env, chat_id, media) {
  if (media.file_size && media.file_size > MAX_CLIP_MB * 1024 * 1024) {
    return tg(env, "sendMessage", {
      chat_id,
      text: `⚠️ Klip juda katta (${Math.round(media.file_size / 1048576)} MB). Telegram bot ${MAX_CLIP_MB} MB gacha qabul qiladi — Flow'da 720p qilib yuklab oling.`,
    });
  }
  const key = `clips:${chat_id}`;
  const list = JSON.parse((await env.CLIPS.get(key)) || "[]");
  list.push({ id: media.file_id, w: media.width || 0, h: media.height || 0, d: media.duration || 0 });
  await env.CLIPS.put(key, JSON.stringify(list), { expirationTtl: 86400 * 3 });
  return tg(env, "sendMessage", {
    chat_id,
    text: `🎞 Klip #${list.length} qabul qilindi${media.duration ? ` (${media.duration} s)` : ""}.\n\nYana yuboring yoki /epizod yozing (yoniga prompt qo'shsa bo'ladi). /bekor — tozalash.`,
  });
}

async function makeEpisode(env, chat_id, prompt) {
  const key = `clips:${chat_id}`;
  const list = JSON.parse((await env.CLIPS.get(key)) || "[]");
  if (!list.length) {
    return tg(env, "sendMessage", { chat_id, text: "Avval Flow kliplarini yuboring, keyin /epizod yozing." });
  }
  const vertical = list.some((c) => c.h > c.w);
  try {
    await createVideo(env, {
      clips: list.map((c) => c.id).join(","),
      topic: prompt,
      type: "cartoon",
      format: vertical ? "short" : "long",
    });
  } catch (e) {
    return tg(env, "sendMessage", { chat_id, text: `❌ Xato: ${e.message}` });
  }
  await env.CLIPS.delete(key);
  return tg(env, "sendMessage", {
    chat_id,
    text: `✅ ${list.length} ta klipdan ${vertical ? "Shorts" : "video"} yasalmoqda: ovoz, musiqa va ulash.\nTayyor bo'lganda shu yerga yuboraman — ko'rib, "Joyla" deysiz.`,
  });
}

async function handleReview(env, cq, action, runId) {
  const chat_id = cq.message.chat.id;
  const message_id = cq.message.message_id;
  const title = (cq.message.caption || "").split("\n").filter(Boolean)[1] || "Video";
  const setCaption = (caption) =>
    tg(env, "editMessageCaption", { chat_id, message_id, caption, reply_markup: { inline_keyboard: [] } });
  try {
    if (action === "pub") {
      await github(env, "/actions/workflows/publish.yml/dispatches", {
        method: "POST",
        body: JSON.stringify({ ref: "main", inputs: { run_id: runId } }),
      });
      await setCaption(`${title}\n\n⏳ YouTube'ga joylanmoqda... Tayyor bo'lganda havolasini yuboraman.`);
      return tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "Joylanmoqda ✅" });
    }
    const arts = await github(env, `/actions/runs/${runId}/artifacts`);
    for (const a of arts.artifacts.filter((x) => x.name.startsWith("review-"))) {
      await github(env, `/actions/artifacts/${a.id}`, { method: "DELETE" });
    }
    await setCaption(`${title}\n\n🗑 O'chirildi — kanalga joylanmaydi.`);
    return tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "O'chirildi" });
  } catch (e) {
    return tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: `Xato: ${String(e.message).slice(0, 150)}`, show_alert: true });
  }
}

function runIcon(r) {
  if (r.status !== "completed") return "⏳";
  return r.conclusion === "success" ? "✅" : r.conclusion === "cancelled" ? "⚪" : "❌";
}

function runLabel(r) {
  if (r.status === "queued") return "Navbatda";
  if (r.status !== "completed") return "Yasalmoqda…";
  return r.conclusion === "success" ? "Tayyor" : r.conclusion === "cancelled" ? "Bekor qilindi" : "Xato";
}

function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "hozirgina";
  if (m < 60) return `${m} daq oldin`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} soat oldin` : `${Math.round(h / 24)} kun oldin`;
}

// ---------- Mini App xavfsizligi ----------

// https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
async function verifyInitData(initData, botToken) {
  if (!initData) return null;
  const params = new URLSearchParams(initData);
  const hash = params.get("hash");
  params.delete("hash");
  const check = [...params.entries()].map(([k, v]) => `${k}=${v}`).sort().join("\n");
  const enc = new TextEncoder();
  const hmac = async (key, msg) => {
    const k = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
  };
  const secret = await hmac(enc.encode("WebAppData"), botToken);
  const sig = [...(await hmac(secret, check))].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (sig !== hash) return null;
  if (Date.now() / 1000 - Number(params.get("auth_date")) > 86400) return null;
  return JSON.parse(params.get("user") || "null");
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

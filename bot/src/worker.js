// Only Baby Telegram bot + Mini App (Cloudflare Worker).
// Bot faqat ALLOWED_USER_ID ga javob beradi; videolar GitHub Actions'da yasaladi.
import APP_HTML from "./app.html";

const WORKFLOW = "daily-video.yml";
const TYPES = { auto: "Avto", story: "Ertak", education: "Ta'limiy", facts: "Faktlar" };
const LENGTHS = ["3", "5", "10", "15", "20"];
const STYLES = ["auto", "stock", "ai"];
const PRIVACY = ["public", "unlisted", "private"];
const VOICES = [
  "en-US-JennyNeural", "en-US-AnaNeural", "en-US-AriaNeural",
  "en-GB-SoniaNeural", "en-US-GuyNeural", "en-US-AndrewNeural",
];
const NO_TOPIC = "AI o'zi tanlaydi";

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
    topic: String(o.topic || "").trim().slice(0, 200),
    type: TYPES[o.type] ? o.type : "auto",
    length: LENGTHS.includes(String(o.length)) ? String(o.length) : "3",
    style: STYLES.includes(o.style) ? o.style : "auto",
    voice: VOICES.includes(o.voice) ? o.voice : VOICES[0],
    privacy: PRIVACY.includes(o.privacy) ? o.privacy : "public",
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
    ],
  };
}

function lengthKeyboard(type) {
  return {
    inline_keyboard: [
      LENGTHS.map((l) => ({ text: `${l} daq`, callback_data: `go:${type}:${l}` })),
      [{ text: "← Orqaga", callback_data: "back" }],
    ],
  };
}

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
    if (text === "/start" || text === "/help") {
      return tg(env, "sendMessage", {
        chat_id,
        text:
          "👋 Only Baby Studio\n\n" +
          "• Mavzuni shunchaki yozing — video yasayman\n" +
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
    // /new [mavzu] yoki oddiy matn → mavzu
    let topic = text.startsWith("/new") ? text.slice(4).trim() : text;
    if (topic.startsWith("/")) {
      return tg(env, "sendMessage", { chat_id, text: "Bunday buyruq yo'q. /help ni bosing." });
    }
    topic = topic.slice(0, 200);
    return tg(env, "sendMessage", {
      chat_id,
      text: `🎬 Yangi video\nMavzu: ${topic || NO_TOPIC}\n\nTurini tanlang:`,
      reply_markup: typeKeyboard(),
    });
  }

  const cq = update.callback_query;
  if (!allowed) return tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: "Ruxsat yo'q" });
  const chat_id = cq.message.chat.id;
  const message_id = cq.message.message_id;
  const topic = topicFrom(cq.message.text);
  const head = `🎬 Yangi video\nMavzu: ${topic || NO_TOPIC}`;
  const [kind, type, length] = cq.data.split(":");

  if (kind === "t") {
    await tg(env, "editMessageText", {
      chat_id, message_id, text: `${head}\nTuri: ${TYPES[type]}\n\nUzunligini tanlang:`,
      reply_markup: lengthKeyboard(type),
    });
  } else if (kind === "back") {
    await tg(env, "editMessageText", { chat_id, message_id, text: `${head}\n\nTurini tanlang:`, reply_markup: typeKeyboard() });
  } else if (kind === "go") {
    try {
      await createVideo(env, { topic, type, length });
      await tg(env, "editMessageText", {
        chat_id, message_id,
        text: `${head}\nTuri: ${TYPES[type]} · ${length} daqiqa\n\n✅ Buyurtma qabul qilindi! Tayyor bo'lganda xabar beraman.`,
      });
    } catch (e) {
      await tg(env, "editMessageText", { chat_id, message_id, text: `${head}\n\n❌ Xato: ${e.message}` });
    }
  }
  return tg(env, "answerCallbackQuery", { callback_query_id: cq.id });
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

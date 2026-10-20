/**
 * Palautteiden välittäjä.
 * Äänet ja opitut painot ovat vain tässä tallennuksessa, ei julkisella sivulla.
 */

const VOTES = new Set(["up", "down", "going", "click"]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(request) });
    }
    try {
      if (url.pathname === "/v" && request.method === "GET") return await voteFromLink(url, env);
      if (url.pathname === "/v" && request.method === "POST") return await votePost(request, env);
      if (url.pathname === "/c" && request.method === "GET") return await clickFromLink(url, env);
      if (url.pathname === "/personal" && request.method === "GET") return await personal(request, env);
      if (url.pathname === "/reset" && request.method === "POST") return await reset(request, env);
      if (url.pathname === "/admin/bundle" && request.method === "GET") return await adminGet(request, env);
      if (url.pathname === "/admin/bundle" && request.method === "PUT") return await adminPut(request, env);
      if (url.pathname === "/") return text("Helsingin viikko", 200);
      return text("Sivua ei löydy", 404);
    } catch (error) {
      return text("Tapahtui virhe", 500);
    }
  },
};

async function voteFromLink(url, env) {
  const token = url.searchParams.get("k") || "";
  const payload = await verify(token, env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "vote" || !VOTES.has(payload.v) || payload.v === "click") {
    return text("Linkki ei kelpaa tai se on vanhentunut.", 400);
  }
  const labels = { up: "Pidän", down: "Ei kiinnosta", going: "Menen tai kävin" };
  const label = labels[payload.v] || "Palaute";
  return html(
    `<!doctype html><html lang="fi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${escapeAttr(label)}</title>
    <body style="font-family:Georgia,serif;background:#f3efe6;color:#1a1814;padding:32px;max-width:36rem">
    <h1>${escapeAttr(label)}</h1>
    <p>Tallennetaanko tämä valinta? Se vaikuttaa seuraavaan Helsingin viikkoon. Viimeisin valinta samasta tapahtumasta korvaa aiemman.</p>
    <form method="post" action="/v">
      <input type="hidden" name="k" value="${escapeAttr(token)}">
      <button style="font:inherit;background:#14352c;color:#f3efe6;border:0;border-radius:999px;padding:12px 18px">Tallenna</button>
    </form>
    </body></html>`
  );
}

async function votePost(request, env) {
  const type = request.headers.get("content-type") || "";
  if (type.includes("application/json")) return await voteFromPage(request, env);
  return await voteFromForm(request, env);
}

async function voteFromForm(request, env) {
  const params = new URLSearchParams(await request.text());
  const payload = await verify(params.get("k") || "", env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "vote" || !VOTES.has(payload.v) || payload.v === "click") {
    return text("Linkki ei kelpaa tai se on vanhentunut.", 400);
  }
  await remember(env, { event_id: String(payload.e || ""), vote: payload.v });
  const bundle = await load(env);
  const count = explicitVotes(bundle.votes).length;
  const site = await ownerLink(env);
  return html(
    `<!doctype html><html lang="fi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>Kiitos</title>
    <body style="font-family:Georgia,serif;background:#f3efe6;color:#1a1814;padding:32px">
    <h1>Kiitos, palaute tallennettiin.</h1>
    <p>Selkeitä peukutuksia on nyt ${count}. Seuraava viikkokirje ottaa ne huomioon.</p>
    ${site ? `<p><a href="${escapeAttr(site)}">Palaa viikkosivulle</a></p>` : ""}
    </body></html>`
  );
}

async function voteFromPage(request, env) {
  const body = await readJson(request);
  const payload = await verify(body.k || "", env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "owner") return json({ error: "Ei lupaa" }, 403, request);
  if (!VOTES.has(body.vote)) return json({ error: "Tuntematon palaute" }, 400, request);
  await remember(env, {
    event_id: String(body.e || ""),
    vote: body.vote,
    features: cleanFeatures(body.features),
    label: cleanLabel(body.label),
  });
  return json({ ok: true }, 200, request);
}

async function clickFromLink(url, env) {
  const payload = await verify(url.searchParams.get("k") || "", env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "click") return text("Linkki ei kelpaa.", 400);
  const target = String(payload.to || "");
  if (!safeTarget(target)) return text("Kohde ei kelpaa.", 400);
  await remember(env, { event_id: String(payload.e || ""), vote: "click" });
  return Response.redirect(target, 302);
}

async function personal(request, env) {
  const url = new URL(request.url);
  const payload = await verify(url.searchParams.get("k") || "", env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "owner") return json({ error: "Ei lupaa" }, 403, request);
  const bundle = await load(env);
  const week = url.searchParams.get("week");
  const weeks = bundle.weeks || {};
  const chosen = (week && weeks[week] ? weeks[week] : latestWeek(weeks)) || {
    learning_active: false,
    explicit_count: 0,
    scores: {},
    recommended_ids: [],
    learned: { positive: [], negative: [] },
  };
  const mine = explicitVotes(bundle.votes);
  return json(
    {
      ...chosen,
      explicit_count: mine.length,
      my_votes: Object.fromEntries(mine.map((vote) => [vote.event_id, vote.vote])),
    },
    200,
    request
  );
}

async function reset(request, env) {
  const body = await readJson(request);
  const payload = await verify(body.k || "", env.FEEDBACK_SECRET || "");
  if (!payload || payload.role !== "owner") return json({ error: "Ei lupaa" }, 403, request);
  await env.DATA.put("bundle", JSON.stringify({ votes: [], weights: {}, labels: {}, weeks: {} }));
  return json({ ok: true }, 200, request);
}

async function adminGet(request, env) {
  if (!adminOk(request, env)) return text("Ei lupaa", 403);
  return json(await load(env));
}

async function adminPut(request, env) {
  if (!adminOk(request, env)) return text("Ei lupaa", 403);
  const body = await readJson(request);
  const current = await load(env);
  const next = {
    votes: Array.isArray(body.votes) ? body.votes.slice(-5000) : current.votes,
    weights: body.weights && typeof body.weights === "object" ? body.weights : current.weights,
    labels: body.labels && typeof body.labels === "object" ? body.labels : current.labels,
    weeks: body.weeks && typeof body.weeks === "object" ? body.weeks : current.weeks,
  };
  await env.DATA.put("bundle", JSON.stringify(next));
  return json({ ok: true });
}

async function remember(env, entry) {
  const eventId = String(entry.event_id || "").slice(0, 80);
  if (!eventId || !VOTES.has(entry.vote)) return;
  const bundle = await load(env);
  const fresh = {
    event_id: eventId,
    vote: entry.vote,
    ts: new Date().toISOString(),
    features: cleanFeatures(entry.features),
    label: cleanLabel(entry.label),
  };
  let votes = Array.isArray(bundle.votes) ? bundle.votes : [];
  if (fresh.vote === "click") {
    votes = votes.filter((vote) => !(vote.event_id === eventId && vote.vote === "click"));
  } else {
    votes = votes.filter((vote) => vote.event_id !== eventId);
  }
  votes.push(fresh);
  bundle.votes = votes.slice(-5000);
  await env.DATA.put("bundle", JSON.stringify(bundle));
}

async function load(env) {
  if (!env.DATA) return { votes: [], weights: {}, labels: {}, weeks: {} };
  const raw = await env.DATA.get("bundle");
  if (!raw) return { votes: [], weights: {}, labels: {}, weeks: {} };
  try {
    const parsed = JSON.parse(raw);
    parsed.votes = parsed.votes || [];
    parsed.weights = parsed.weights || {};
    parsed.labels = parsed.labels || {};
    parsed.weeks = parsed.weeks || {};
    return parsed;
  } catch {
    return { votes: [], weights: {}, labels: {}, weeks: {} };
  }
}

function explicitVotes(votes) {
  const byEvent = new Map();
  const ordered = [...(votes || [])].sort((a, b) => String(a.ts || "").localeCompare(String(b.ts || "")));
  for (const vote of ordered) {
    if (!vote || !vote.event_id || vote.vote === "click") continue;
    if (!["up", "down", "going"].includes(vote.vote)) continue;
    byEvent.set(String(vote.event_id), vote);
  }
  return [...byEvent.values()];
}

function latestWeek(weeks) {
  const keys = Object.keys(weeks || {}).sort();
  if (!keys.length) return null;
  return weeks[keys[keys.length - 1]];
}

function adminOk(request, env) {
  const header = request.headers.get("Authorization") || "";
  const got = header.startsWith("Bearer ") ? header.slice(7) : "";
  const expected = env.ADMIN_SECRET || "";
  if (!got || !expected || got.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

function cleanFeatures(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => typeof item === "string" && item.length < 80).slice(0, 30);
}

function cleanLabel(value) {
  return typeof value === "string" ? value.slice(0, 180) : "";
}

function safeTarget(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

async function ownerLink(env) {
  const site = env.SITE_URL || "";
  const secret = env.FEEDBACK_SECRET || "";
  if (!site || !secret) return "";
  const token = await sign({ role: "owner" }, secret);
  const join = site.includes("?") ? "&" : "?";
  return `${site.replace(/\/$/, "")}${join}k=${token}`;
}

async function sign(payload, secret) {
  const raw = stableString(payload);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(raw)));
  return `${b64e(new TextEncoder().encode(raw))}.${b64e(sig)}`;
}

async function verify(token, secret) {
  if (!token || !secret || !token.includes(".")) return null;
  const [rawB64, sigB64] = token.split(".", 2);
  let raw;
  let signature;
  try {
    raw = b64d(rawB64);
    signature = b64d(sigB64);
  } catch {
    return null;
  }
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const expected = new Uint8Array(await crypto.subtle.sign("HMAC", key, raw));
  if (!timingSafeEqual(expected, signature)) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(raw));
    if (!payload || typeof payload !== "object") return null;
    if (payload.exp && Number(payload.exp) < Date.now() / 1000) return null;
    return payload;
  } catch {
    return null;
  }
}

function stableString(value) {
  if (Array.isArray(value)) return `[${value.map(stableString).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableString(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function b64e(bytes) {
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64d(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function cors(request) {
  const origin = request.headers.get("Origin") || "";
  const ok =
    origin.endsWith(".github.io") ||
    origin.startsWith("http://127.0.0.1") ||
    origin.startsWith("http://localhost") ||
    origin.endsWith(".grok.com") ||
    origin.endsWith(".grok-sandbox.com");
  if (!ok) return { Vary: "Origin" };
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    Vary: "Origin",
  };
}

function json(payload, status = 200, request = null) {
  const headers = { "Content-Type": "application/json; charset=utf-8" };
  if (request) Object.assign(headers, cors(request));
  return new Response(JSON.stringify(payload), { status, headers });
}

function text(message, status) {
  return new Response(message, { status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}

function html(body) {
  return new Response(body, { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export { verify, sign };

function escapeAttr(value) {
  return String(value)
    .replace(/&/g, "\u0026amp;")
    .replace(/</g, "\u0026lt;")
    .replace(/>/g, "\u0026gt;")
    .replace(/"/g, "\u0026quot;")
    .replace(/'/g, "\u0026#39;");
}

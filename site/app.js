const app = document.querySelector("#app");
const state = {
  weeks: [],
  weekId: "",
  data: null,
  personal: null,
  token: "",
  filters: { text: "", topic: "", free: false, day: "", sort: "time" },
  message: "",
};

const GENERIC = new Set([
  "osallistuminen", "tapahtumat", "kulttuuritapahtumat", "hyvinvointi",
  "helsinki", "suomi", "ruotsi", "englanti", "keskustelu",
]);

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "\u0026amp;")
    .replace(/</g, "\u0026lt;")
    .replace(/>/g, "\u0026gt;")
    .replace(/"/g, "\u0026quot;")
    .replace(/'/g, "\u0026#39;");
}

function tokenFromUrl() {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("k") || "";
  if (fromUrl) {
    localStorage.setItem("hv_token", fromUrl);
    params.delete("k");
    const next = params.toString();
    history.replaceState({}, "", location.pathname + (next ? `?${next}` : "") + location.hash);
    return fromUrl;
  }
  return localStorage.getItem("hv_token") || "";
}

async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(url);
  return response.json();
}

async function boot() {
  state.token = tokenFromUrl();
  try {
    state.weeks = await loadJson("data/weeks.json");
  } catch {
    app.innerHTML = "<main class='wrap'><p>Viikon tietoja ei vielä ole. Ne ilmestyvät, kun ensimmäinen kooste on valmis.</p></main>";
    return;
  }
  const params = new URLSearchParams(location.search);
  state.weekId = params.get("viikko") || (state.weeks[0] && state.weeks[0].id) || "";
  if (state.data && state.data.preferences && state.data.preferences.free_only) state.filters.free = true;
  await showWeek(state.weekId);
  window.addEventListener("hashchange", () => render());
}

async function showWeek(id) {
  state.weekId = id;
  state.message = "";
  try {
    state.data = await loadJson(`data/${id}.json`);
  } catch {
    app.innerHTML = "<main class='wrap'><p>Tätä viikkoa ei löytynyt.</p></main>";
    return;
  }
  if (state.data.preferences && state.data.preferences.free_only) state.filters.free = true;
  state.personal = await loadPersonal();
  const params = new URLSearchParams(location.search);
  if (params.get("viikko") !== id) {
    params.set("viikko", id);
    history.replaceState({}, "", `${location.pathname}?${params.toString()}${location.hash}`);
  }
  render();
}

async function loadPersonal() {
  const worker = (state.data && state.data.worker_url) || "";
  if (state.token && worker) {
    try {
      const response = await fetch(`${worker.replace(/\/$/, "")}/personal?k=${encodeURIComponent(state.token)}&week=${encodeURIComponent(state.weekId)}`);
      if (response.ok) return response.json();
    } catch {
      /* sivu toimii silti aikajärjestyksessä */
    }
  }
  const local = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  if (!local) return null;
  try {
    const response = await fetch("personal.preview.json", { cache: "no-store" });
    if (response.ok) return response.json();
  } catch {
    return null;
  }
  return null;
}

function byId() {
  const map = new Map();
  for (const event of state.data.events || []) map.set(event.id, event);
  return map;
}

function topics() {
  const counts = new Map();
  for (const event of state.data.events || []) {
    for (const keyword of event.keywords || []) {
      const key = keyword.toLowerCase();
      if (GENERIC.has(key)) continue;
      counts.set(keyword, (counts.get(keyword) || 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24).map((row) => row[0]);
}

function filteredEvents() {
  const filters = state.filters;
  const personal = state.personal;
  const scores = (personal && personal.scores) || {};
  let events = [...(state.data.events || [])];
  if (filters.day === "spanning") events = events.filter((event) => event.spanning);
  else if (filters.day) events = events.filter((event) => event.date === filters.day);
  if (filters.free) events = events.filter((event) => event.free);
  if (filters.topic) {
    const needle = filters.topic.toLowerCase();
    events = events.filter((event) => (event.keywords || []).some((keyword) => keyword.toLowerCase() === needle));
  }
  if (filters.text) {
    const needle = filters.text.toLowerCase();
    events = events.filter((event) =>
      [event.name, event.place, event.organiser, event.description, ...(event.keywords || [])]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }
  if (filters.sort === "score" && personal && personal.learning_active) {
    events.sort((a, b) => (scores[b.id] || 0) - (scores[a.id] || 0) || (a.start || "").localeCompare(b.start || ""));
  } else {
    events.sort((a, b) => (a.start || "").localeCompare(b.start || "") || a.id.localeCompare(b.id));
  }
  return events;
}

function card(event, options = {}) {
  const personal = state.personal || {};
  const scores = personal.scores || {};
  const novel = (personal.novel_ids || []).includes(event.id) || options.novel;
  const reason = options.reason || (personal.reasons || {})[event.id] || "";
  const badges = [];
  if (event.free) badges.push("Ilmainen");
  else if (event.price_label) badges.push(event.price_label);
  if (novel) badges.push("Uutta sinulle");
  if (event.rescheduled) badges.push("Aikataulu muuttunut");
  const when = event.spanning ? "Koko viikko" : `${event.time_label || ""}${event.end_time_label ? "–" + event.end_time_label : ""}`;
  const place = [event.place || "Paikka ei tiedossa", event.address].filter(Boolean).join(", ");
  const score = personal.learning_active && scores[event.id] != null
    ? `<span class="badge">${scores[event.id]} pistettä</span>` : "";
  return `<article class="card${novel ? " novel" : ""}">
    <div class="when">${esc(when)}</div>
    <div class="badges">${badges.map((badge) => `<span class="badge${badge.includes("muuttunut") ? " warn" : ""}">${esc(badge)}</span>`).join("")}${score}</div>
    <a class="name" href="${esc(event.url)}" target="_blank" rel="noopener">${esc(event.name)}</a>
    <div>${esc(place)}</div>
    ${event.organiser ? `<div class="muted">${esc(event.organiser)}</div>` : ""}
    ${event.description ? `<p>${esc(event.description)}</p>` : ""}
    <div class="badges">${(event.keywords || []).slice(0, 4).map((keyword) => `<span class="badge">${esc(keyword)}</span>`).join("")}</div>
    ${reason ? `<div class="reason">${esc(reason)}</div>` : ""}
    <div class="actions">
      <button type="button" data-vote="up" data-id="${esc(event.id)}">Pidän</button>
      <button type="button" data-vote="down" data-id="${esc(event.id)}">Ei kiinnosta</button>
      <button type="button" data-vote="going" data-id="${esc(event.id)}">Menen tai kävin</button>
    </div>
  </article>`;
}

function weatherHtml() {
  const days = (state.data.weather && state.data.weather.days) || [];
  if (!days.length) return "<p class='warn-banner'>Sääennuste puuttuu tältä viikolta.</p>";
  return `<div class="weather">${days.map((day) => `<article>
    <div class="muted">${esc(day.weekday)} ${esc(day.date.slice(8))}.${esc(day.date.slice(5, 7))}.</div>
    <strong>${esc(day.temp_max)}° / ${esc(day.temp_min)}°</strong>
    <div>${esc(day.description)}</div>
    <div class="muted">Sade ${day.precip_prob == null ? "–" : esc(day.precip_prob)}&nbsp;%</div>
    <div class="muted">${day.precip_mm == null ? "–" : esc(day.precip_mm)}&nbsp;mm · tuuli ${day.wind == null ? "–" : esc(day.wind)}&nbsp;m/s</div>
  </article>`).join("")}</div>
  <p class="muted">Sää: ${esc(state.data.weather.source_label || "")}. ${esc(state.data.weather.summary || "")}</p>`;
}

function render() {
  const data = state.data;
  const personal = state.personal;
  const active = Boolean(personal && personal.learning_active);
  const count = personal ? personal.explicit_count || 0 : 0;
  const map = byId();
  const events = filteredEvents();
  const topicOptions = topics().map((topic) => `<option ${state.filters.topic === topic ? "selected" : ""}>${esc(topic)}</option>`).join("");
  const dayOptions = (data.days || []).map((day) => `<option value="${esc(day.date)}" ${state.filters.day === day.date ? "selected" : ""}>${esc(day.title)} (${day.event_ids.length})</option>`).join("");
  const weekOptions = state.weeks.map((week) => `<option value="${esc(week.id)}" ${week.id === state.weekId ? "selected" : ""}>${esc(week.label)}</option>`).join("");
  const warnings = (data.warnings || []).map((warning) => `<p class="warn-banner">${esc(warning)}</p>`).join("");
  let top = "";
  if (location.hash === "#opittu") {
    top = learnedHtml(personal, count);
  } else if (!active) {
    const sample = (data.calibration_ids || []).map((id) => map.get(id)).filter(Boolean);
    top = `<section class="section" id="kalibrointi">
      <h2>Auta suodatinta alkuun</h2>
      <p class="muted">Selkeitä peukutuksia on ${count}/10. Ennen sitä tapahtumat ovat aikajärjestyksessä. Valitse alta noin parikymmentä erilaista tapahtumaa, niin seuraava viikko osuu paremmin. Mitään ei piiloteta.</p>
      <div class="grid">${sample.map((event) => card(event)).join("")}</div>
    </section>
    ${interestHtml(map)}`;
  } else {
    const recommended = (personal.recommended_ids || []).map((id) => map.get(id)).filter(Boolean);
    top = `<section class="section"><h2>Sinulle suositeltua</h2>
      <p class="muted">Noin viidesosa paikoista on varattu aiheille, joita et ole vielä arvioinut. Ne on merkitty sanalla ”Uutta sinulle”.</p>
      <div class="grid">${recommended.map((event) => card(event, { novel: (personal.novel_ids || []).includes(event.id), reason: (personal.reasons || {})[event.id] })).join("")}</div>
    </section>`;
  }
  const grouped = state.filters.day ? "" : daysHtml(events);
  app.innerHTML = `
    <header class="hero">
      <div class="wrap hero-row">
        <div>
          <p class="kicker">Helsingin viikko</p>
          <h1>${esc(data.week.label)}</h1>
          <p class="lede">${esc((data.weather && data.weather.summary) || "Tulevan viikon tapahtumat Helsingissä.")}</p>
        </div>
        <label>Arkisto<br><select class="week-select" id="week">${weekOptions}</select></label>
      </div>
    </header>
    <main class="wrap">
      ${warnings}
      ${weatherHtml()}
      <p class="status" id="status">${esc(state.message)}</p>
      ${top}
      <section class="section" id="ohjelma">
        <h2>Koko ohjelma</h2>
        <p class="muted">${data.events.length} tapahtumaa. Rajaa listaa, jos haluat nähdä vähemmän. Mikään ei katoa pysyvästi.</p>
        <div class="filters">
          <input id="q" placeholder="Hae nimellä, paikalla tai sanalla" value="${esc(state.filters.text)}">
          <select id="topic"><option value="">Kaikki aiheet</option>${topicOptions}</select>
          <select id="day"><option value="">Kaikki päivät</option><option value="spanning" ${state.filters.day === "spanning" ? "selected" : ""}>Koko viikon kestävät</option>${dayOptions}</select>
          <select id="sort">
            <option value="time" ${state.filters.sort === "time" ? "selected" : ""}>Aikajärjestys</option>
            <option value="score" ${state.filters.sort === "score" ? "selected" : ""} ${active ? "" : "disabled"}>Suosituspisteet</option>
          </select>
          <label class="text-btn"><input id="free" type="checkbox" ${state.filters.free ? "checked" : ""}> Vain ilmaiset</label>
        </div>
        ${state.filters.day ? `<div class="list">${events.map((event) => card(event)).join("") || "<p class='empty'>Ei tapahtumia näillä rajauksilla.</p>"}</div>` : grouped}
      </section>
      ${location.hash === "#opittu" ? "" : learnedHtml(personal, count)}
      <footer>
        <p><a href="#opittu">Mitä suodatin on oppinut</a> · <a href="#kalibrointi">Pikavalinnat</a> · <a href="#ohjelma">Ohjelma</a></p>
        <p>Mieltymyksesi eivät ole tällä julkisella sivulla. Henkilökohtainen järjestys näkyy vain sinulle, kun tulet sähköpostin linkistä.</p>
      </footer>
    </main>`;
  bind();
}

function interestHtml(map) {
  const ids = state.data.interest_ids || [];
  const events = ids.map((id) => map.get(id)).filter(Boolean);
  if (!events.length) return "";
  return `<section class="section"><h2>Valitsemistasi aiheista</h2>
    <p class="muted">Tämä perustuu asetuksiin, ei vielä peukutuksiin. Aiheita voi muuttaa myöhemmin.</p>
    <div class="grid">${events.map((event) => card(event)).join("")}</div></section>`;
}

function daysHtml(events) {
  const spanning = events.filter((event) => event.spanning);
  const blocks = (state.data.days || []).map((day) => {
    const list = events.filter((event) => event.date === day.date);
    return `<section class="day-block">
      <div class="day-head"><h3>${esc(day.title)}</h3><span class="muted">${esc(day.weather_line || "")}</span></div>
      <div class="list">${list.map((event) => card(event)).join("") || "<p class='muted'>Ei tapahtumia näillä rajauksilla.</p>"}</div>
    </section>`;
  }).join("");
  const span = spanning.length ? `<section class="day-block"><div class="day-head"><h3>Koko viikon kestävät</h3></div><div class="list">${spanning.map((event) => card(event)).join("")}</div></section>` : "";
  return span + blocks;
}

function learnedHtml(personal, count) {
  const learned = (personal && personal.learned) || { positive: [], negative: [] };
  const positive = learned.positive || [];
  const negative = learned.negative || [];
  const active = personal && personal.learning_active;
  return `<section class="section" id="opittu">
    <h2>Mitä suodatin on oppinut</h2>
    <p class="muted">${active ? `Peukutuksia ${count}. Alla vahvimmat ja heikoimmat merkit.` : `Peukutuksia ${count}/10. Kymmenen jälkeen sivu alkaa selittää suosituksia.`}</p>
    <div class="learned">
      <div class="panel" style="padding:14px"><h3>Nostaa</h3><div class="chips">${positive.map((row) => `<span class="chip">${esc(row.label)} (${esc(row.weight)})</span>`).join("") || "<span class='muted'>Ei vielä</span>"}</div></div>
      <div class="panel" style="padding:14px"><h3>Laskee</h3><div class="chips">${negative.map((row) => `<span class="chip">${esc(row.label)} (${esc(row.weight)})</span>`).join("") || "<span class='muted'>Ei vielä</span>"}</div></div>
    </div>
    <p><button type="button" id="reset" class="text-btn">Nollaa oppiminen</button></p>
  </section>`;
}

function bind() {
  const week = document.querySelector("#week");
  if (week) week.addEventListener("change", () => showWeek(week.value));
  const q = document.querySelector("#q");
  if (q) q.addEventListener("input", () => { state.filters.text = q.value; rerenderKeepFocus(); });
  for (const id of ["topic", "day", "sort"]) {
    const el = document.querySelector("#" + id);
    if (el) el.addEventListener("change", () => { state.filters[id] = el.value; render(); });
  }
  const free = document.querySelector("#free");
  if (free) free.addEventListener("change", () => { state.filters.free = free.checked; render(); });
  app.querySelectorAll("[data-vote]").forEach((button) => {
    button.addEventListener("click", () => vote(button.dataset.id, button.dataset.vote, button));
  });
  const reset = document.querySelector("#reset");
  if (reset) reset.addEventListener("click", resetLearning);
}

let focusTimer = 0;
function rerenderKeepFocus() {
  clearTimeout(focusTimer);
  focusTimer = setTimeout(() => {
    const pos = (document.querySelector("#q") || {}).selectionStart;
    render();
    const field = document.querySelector("#q");
    if (field) {
      field.focus();
      if (pos != null) field.setSelectionRange(pos, pos);
    }
  }, 180);
}

async function vote(id, kind, button) {
  const worker = state.data.worker_url || "";
  const event = byId().get(id);
  if (!state.token || !worker) {
    state.message = "Peukutus tallentuu, kun avaat sivun sähköpostissa olevasta linkistä.";
    const status = document.querySelector("#status");
    if (status) status.textContent = state.message;
    return;
  }
  button.disabled = true;
  try {
    const response = await fetch(worker.replace(/\/$/, "") + "/v", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ k: state.token, e: id, vote: kind, features: event.features || [], label: event.name }),
    });
    if (!response.ok) throw new Error("tallennus");
    button.setAttribute("aria-pressed", "true");
    state.message = "Tallennettu. Seuraava viikkokirje ottaa tämän huomioon. Viimeisin valinta korvaa aiemman.";
  } catch {
    state.message = "Palautetta ei saatu tallennettua. Yritä hetken päästä uudestaan.";
  }
  button.disabled = false;
  const status = document.querySelector("#status");
  if (status) status.textContent = state.message;
}

async function resetLearning() {
  if (!confirm("Poistetaanko kaikki peukutukset? Suositukset palaavat alkuun seuraavassa viikkokirjeessä.")) return;
  const worker = state.data.worker_url || "";
  if (!state.token || !worker) {
    state.message = "Nollaus onnistuu sivulta, jonka avaat sähköpostin linkistä.";
    render();
    return;
  }
  const response = await fetch(worker.replace(/\/$/, "") + "/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ k: state.token }),
  });
  if (!response.ok) {
    state.message = "Nollaus ei onnistunut.";
    render();
    return;
  }
  state.personal = { learning_active: false, explicit_count: 0, scores: {}, recommended_ids: [], learned: { positive: [], negative: [] } };
  state.message = "Oppiminen nollattiin.";
  render();
}

boot();

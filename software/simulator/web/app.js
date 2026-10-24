// SPDX-License-Identifier: MIT
// Strona symulatora: stacja w skali z panelem z wybranego układu, pętla czasu, panele ćwiczeń,
// stanowiska odbiorczego, warunków, konsoli, projektu i dziennika. Stacja i węzeł to obraz bench-b
// oprogramowania (wici-station.mjs) na wirtualnej płytce; strona zmienia tylko poziomy pinów (przyciski,
// przełącznik), zasilanie i warunki świata, a pokazuje piksele panelu Sharp, diodę i brzęczyk.
import { Simulation } from "./sim.js";
import { R02, LABELS, ACTIVE, labelOf } from "./layouts.js";
import { SCENARIOS, Exercise } from "./scenarios.js";

// ---- teksty strony ------------------------------------------------------------------------------

const T = {
  pl: {
    title: "symulator stacji", feedback: "Zgłoś uwagę",
    simTime: "czas symulacji", pause: "pauza", soundOff: "dźwięk wył.", soundOn: "dźwięk wł.", realSize: "skala 1:1", card: "karta płatnicza 85,6 × 54 mm",
    calibrate: "Dopasuj ramkę do prawdziwej karty przyłożonej do ekranu",
    keys: "Klawiatura: ↑ GÓRA, ↓ DÓŁ, Enter OK, Backspace albo Esc WSTECZ. Przytrzymanie działa jak na stacji. WYŁĄCZNIK: krótko włącza, 2 s wyłącza. SERWIS: kliknięcie przebija naklejkę, a przytrzymanie przycisku pod nią przez 3 s włącza tryb serwisowy.",
    tabTrain: "Ćwiczenia", tabRx: "Dyżurny", tabEnv: "Warunki", tabConsole: "Konsola", tabLog: "Dziennik",
    preparing: "Przygotowanie sieci (stanowisko, węzeł, stacja) przez protokół USB…", starting: "Przygotowanie ćwiczenia…",
    freeTitle: "Praca swobodna", freeText: "Stacja jest włączona i ma trasę do stanowiska. Wysyłaj zgłoszenia, odpowiadaj jako dyżurny i zmieniaj warunki łącza. Ćwiczenie zaczyna się od tego samego obrazu sieci.",
    exercises: "Ćwiczenia gospodarza", again: "Powtórz", list: "Lista ćwiczeń", stop: "Przerwij", hint: "Podpowiedź",
    done: "Ćwiczenie ukończone", totalTime: "czas symulacji", presses: "naciśnięcia", hints: "podpowiedzi",
    rxTitle: "Stanowisko odbiorcze", rxOn: "port węzła otwarty", identity: "tożsamość", main: "główna", backup: "zapasowa",
    autoRead: "potwierdzaj odczyt po", autoDecide: "decyzja automatyczna", none: "brak", after: "po", min: "min",
    noRequests: "Stanowisko nie ma jeszcze zgłoszeń. Wyślij zgłoszenie ze stacji albo TEST.", copies: "kopii", reply: "Odpowiedź",
    send: "Wyślij", bulletin: "Komunikat do stacji", bulletinPh: "np. Punkt wydawania wody: Szkoła nr 1, 10:00–14:00.", outbox: "czeka na dowód od stacji",
    changed: "nowa wersja", received: "stacja wie o zapisie", stations: "znane stacje",
    linkTitle: "Łącze stacja–węzeł", linkUp: "łącze działa", loss: "tłumienie trasy", rssi: "średni poziom odbioru",
    margin: "zapas ponad czułość (−112 dBm)", fading: "zanik: rozkład normalny, σ = 4 dB na ramkę",
    faults: "Awarie stacji", radioFault: "awaria układu radiowego (S2-LP przestaje odpowiadać)", framFault: "awaria pamięci FRAM (zapisy nie trafiają do układu)",
    faultNote: "Awaria działa od razu i trwa po wyłączeniu; oprogramowanie wykrywa ją samo (sprawdzenie układów, TEST, odczyt po zapisie).",
    node: "Węzeł stanowiska", nodeOn: "węzeł zasilany",
    power: "Zasilanie", powerNote: "Obraz bench-b nie mierzy napięcia (ekran podaje 12 V: 0,0 V). Zanik zasilania: WYŁĄCZNIK albo wtyk USB.",
    panel: "Panel", switchPos: "przełącznik CISZA", swOn: "wł.", swOff: "wył.",
    station: "Stacja", resetStation: "Nowa sieć (praca swobodna)", on: "włączona", off: "wyłączona", uptime: "od uruchomienia", restarts: "restarty",
    radioState: "radio", transmitting: "nadaje",
    consoleTitle: "Port diagnostyki USB", consoleNote: "Polecenia jak z terminala na porcie diagnostyki płytki (HELP, INFO, RNS, STORE, JOURNAL, SCREEN, VTEST…). Port pozostaje otwarty, jak podłączony laptop.",
    device: "urządzenie", command: "polecenie", clear: "Wyczyść", disconnect: "Odłącz",
    logEmpty: "Brak zdarzeń.", logAir: "pokaż ramki radiowe", sealTorn: "naklejka serwisowa przebita (VOID)",
  },
  en: {
    title: "station simulator", feedback: "Send feedback",
    simTime: "simulated time", pause: "pause", soundOff: "sound off", soundOn: "sound on", realSize: "1:1 scale", card: "payment card 85.6 × 54 mm",
    calibrate: "Match the frame to a real card held against the screen",
    keys: "Keyboard: ↑ UP, ↓ DOWN, Enter OK, Backspace or Esc BACK. Holding works as on the station. POWER: short press turns on, 2 s turns off. SERVICE: a click pierces the sticker; holding the button under it for 3 s enters service mode.",
    tabTrain: "Exercises", tabRx: "Duty officer", tabEnv: "Conditions", tabConsole: "Console", tabLog: "Log",
    preparing: "Preparing the network (post, node, station) over the USB protocol…", starting: "Preparing the exercise…",
    freeTitle: "Free play", freeText: "The station is on and has a path to the post. Send requests, answer as the duty officer and change link conditions. Exercises start from the same network image.",
    exercises: "Warden exercises", again: "Repeat", list: "All exercises", stop: "Stop", hint: "Hint",
    done: "Exercise complete", totalTime: "simulated time", presses: "presses", hints: "hints",
    rxTitle: "Receiving post", rxOn: "node port open", identity: "identity", main: "main", backup: "backup",
    autoRead: "confirm reading after", autoDecide: "automatic decision", none: "none", after: "after", min: "min",
    noRequests: "No requests at the post yet. Send a request or a TEST from the station.", copies: "copies", reply: "Reply",
    send: "Send", bulletin: "Bulletin to the station", bulletinPh: "e.g. Water point: School no. 1, 10:00–14:00.", outbox: "waiting for proof from the station",
    changed: "new version", received: "station knows it is saved", stations: "known stations",
    linkTitle: "Station–node link", linkUp: "link up", loss: "path loss", rssi: "mean received level",
    margin: "margin over sensitivity (−112 dBm)", fading: "fading: normal, σ = 4 dB per frame",
    faults: "Station faults", radioFault: "radio chip failure (S2-LP stops responding)", framFault: "FRAM failure (writes do not reach the chip)",
    faultNote: "A fault applies at once and survives power-off; the firmware detects it on its own (chip checks, TEST, read-back).",
    node: "Post node", nodeOn: "node powered",
    power: "Power", powerNote: "The bench-b image does not measure voltage (the screen shows 12 V: 0.0 V). Power loss: POWER button or USB plug.",
    panel: "Panel", switchPos: "SILENCE switch", swOn: "on", swOff: "off",
    station: "Station", resetStation: "Fresh network (free play)", on: "on", off: "off", uptime: "since start", restarts: "restarts",
    radioState: "radio", transmitting: "transmitting",
    consoleTitle: "USB diagnostic port", consoleNote: "Commands as from a terminal on the board’s diagnostic port (HELP, INFO, RNS, STORE, JOURNAL, SCREEN, VTEST…). The port stays open, like a connected laptop.",
    device: "device", command: "command", clear: "Clear", disconnect: "Disconnect",
    logEmpty: "No events.", logAir: "show radio frames", sealTorn: "service sticker pierced (VOID)",
  },
};
const CATEGORIES = {
  pl: ["pomoc medyczna", "leki i sprzęt medyczny", "ewakuacja, transport", "woda pitna", "żywność", "ogrzewanie, energia", "sanitarne", "bezpieczeństwo obiektu", "informacja, poszukiwanie", "inne"],
  en: ["medical help", "medicines, equipment", "evacuation, transport", "drinking water", "food", "heating, energy", "sanitation", "building safety", "information, search", "other"],
};
const URGENCY = { pl: ["w ciągu doby", "pilne", "zagrożenie życia"], en: ["within a day", "urgent", "life threat"] };
const STATES = {
  pl: ["", "zapisane", "przeczytane", "pomoc skierowana", "przekazane dalej", "nie może pomóc", "zamknięte"],
  en: ["", "saved", "read", "help dispatched", "passed on", "cannot help", "closed"],
};
const SENSITIVITY_DBM = -112;   // S2-LP, profil P1: 2-GFSK 4,8 kBd (model odbiornika, hal/s2lp_chip.cpp)
const TX_DBM = 13;              // moc profilu p1

const pref = {
  get(key, fallback) { try { const v = localStorage.getItem("wici-sim." + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("wici-sim." + key, JSON.stringify(value)); } catch { /* bez pamięci przeglądarki */ } },
};

// ---- stan strony --------------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let lang = pref.get("lang", "pl");
const t = (key) => T[lang][key] ?? key;
let sim = null;
let ready = false;
let s = {};                 // obserwacja: ekran (OCR), stanowisko, płytka stacji
let speed = 1;
let tab = pref.get("tab", "train");
let exercise = null;
let showHint = false;
const held = new Set();
let logItems = [];
let showAir = pref.get("logAir", false);
let soundOn = false;
let audio = null;
let lastFrame = -1;
let panelKey = "";
let busyText = "";
let lastLoss = 100;
const consoles = { stacja: "", "węzeł": "" };
let consoleDevice = "stacja";
let postPort = true;   // aplikacja stanowiska ma otwarty port danych węzła
let sealBroken = false;   // naklejka serwisowa R02 przebita w tej sesji (nowa sieć i ćwiczenie: nowa naklejka)
let buildStamp = "";   // wersja obrazu z build.json (do zgłoszeń)

// Zadania na symulacji idą po kolei (przebieg czasu, start ćwiczenia, polecenia stanowiska).
let chain = Promise.resolve();
let working = false;
function serial(fn) {
  const run = chain.then(async () => { working = true; try { return await fn(); } finally { working = false; } });
  chain = run.catch((err) => fail(err));
  return run;
}
function fail(err) {
  console.error(err);
  const p = document.createElement("p");
  p.className = "warning";
  p.textContent = `${err.message ?? err}`;
  document.querySelector(".bench").append(p);
}

// ---- start --------------------------------------------------------------------------------------

async function main() {
  applyLang();
  bind();
  buildDevice();
  selectTab(tab);
  busy(t("preparing"));
  try {
    const b = await (await fetch("build.json")).json();
    buildStamp = `${b.env} wici-station.mjs ${b.outputs["wici-station.mjs"].sha256.slice(0, 12)}`;
    const o = b.outputs["wici-station.mjs"];
    $("build-info").textContent = `${b.env} · ${b.firmware.length} plików firmware/src · wici-station.mjs ${o.bytes} B, sha256 ${o.sha256.slice(0, 12)}… · ${b.emscripten.split(" ").slice(-2, -1)[0] ?? ""}`;
  } catch { /* opis budowy jest opcjonalny */ }
  sim = await Simulation.prepare({ seed: 3 });
  sim.on(onWorld);
  await serial(freePlay);
  ready = true;
  requestAnimationFrame(loop);
}

function busy(text) {
  busyText = text;
  $("busy").hidden = !text;
  $("busy").textContent = text;
}

async function freePlay() {
  ledOff();
  releaseAll();
  exercise = null;
  logItems = [];
  busy(t("preparing"));
  await sim.reset();
  postPort = true;
  resetSeal();
  lastLoss = sim.world.defaultLoss;
  for (const line of ["boot", "post auto 1 2 0 5"]) await sim.act(line);
  sim.takeEvents();
  busy("");
  lastFrame = -1;
  await poll(true);
}

async function startExercise(scenario) {
  ledOff();
  releaseAll();
  showHint = false;
  logItems = [];
  exercise = new Exercise(sim, scenario);
  selectTab("train");
  busy(t("starting"));
  postPort = true;
  resetSeal();
  await exercise.start((f) => busy(`${t("starting")} ${Math.round(f * 100)} %`));
  lastLoss = sim.world.defaultLoss;
  busy("");
  lastFrame = -1;
  await poll(true);
}

// ---- pętla czasu --------------------------------------------------------------------------------

let last = performance.now();
let acc = 0;
let lastPoll = 0;
function loop(now) {
  const dt = Math.min(250, now - last);
  last = now;
  // Przy trzymanym przycisku czas biegnie normalnie: przytrzymanie 2-3 s ma znaczenie na stacji.
  const rate = held.size ? Math.min(speed, 1) : speed;
  if (!busyText) acc = Math.min(acc + dt * rate, 60000);   // najwyżej minuta symulacji zaległości
  if (!working && !busyText) {
    const ms = Math.floor(acc);
    const doPoll = now - lastPoll > 200;
    if (ms > 0 || doPoll) {
      acc -= ms;
      serial(async () => {
        if (ms > 0) await sim.advance(ms * 1000);
        drain();
        if (doPoll) { lastPoll = performance.now(); await poll(false); }
      });
    }
  }
  draw();
  requestAnimationFrame(loop);
}

function skip(ms) {
  if (!ready) return;
  releaseAll();
  serial(async () => {
    busy(`+${Math.round(ms / 60000)} min…`);
    for (let left = ms; left > 0; left -= 10000) { await sim.advance(Math.min(left, 10000) * 1000); drain(); }
    busy("");
    await poll(true);
  });
}

// Zdarzenia świata: restarty płytek i ramki w eterze (dziennik).
function onWorld(e) {
  if (e.kind === "restart" && e.source === "stacja") ledOff();
  if (e.kind === "restart") logItems.push({ t: e.t, kind: "restart", source: e.source, text: { 3: "restart programowy", 6: "watchdog", 1: "włączenie" }[e.reason] ?? `przyczyna ${e.reason}` });
  else if (e.kind === "air") {
    const f = e.frame;
    logItems.push({ t: f.start, kind: "air", source: e.source, text: `${f.payload.length / 2} B, ${((f.end - f.start) / 1000).toFixed(1)} ms${f.aborted ? ", przerwana" : ""}` });
  }
}

function drain() {
  let changed = false;
  for (const e of sim.takeEvents()) {
    if (e.source === "stacja") {
      if (e.kind === "tone") { beep(e.ms); continue; }
      if (e.kind === "led") { led(e.on); continue; }
      if (e.kind === "disp") continue;
    } else if (e.source === "węzeł" && ["tone", "led", "disp"].includes(e.kind)) continue;
    logItems.push(e);
    changed = true;
  }
  for (const d of [sim.station, sim.node]) {
    if (!d.powered || !d.usbOpen[0]) continue;
    const text = new TextDecoder().decode(d.usbRead(0));
    if (text) { consoles[d.name] = (consoles[d.name] + text).slice(-20000); changed = true; }
  }
  if (logItems.length > 600) logItems = logItems.slice(-500);
  if (changed && (tab === "log" || tab === "console")) renderPanel(true);
}

// ---- ekran Sharp --------------------------------------------------------------------------------

let lcdCtx = null, lcdImage = null;
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function rgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function draw(force = false) {
  if (!lcdCtx || !sim || !ready) return;
  const st = sim.station;
  const version = st.powered ? st.lcdVersion() : -2;
  if (!force && version === lastFrame) return;
  lastFrame = version;
  const bits = st.lcd();
  const paper = rgb(css("--lcd") || "#bfc2b8"), ink = rgb(css("--lcd-ink") || "#1e211d"), off = rgb(css("--lcd-off") || "#9a9d95");
  const px = lcdImage.data;
  for (let y = 0; y < 240; y++) {
    for (let x = 0; x < 400; x++) {
      const white = bits ? (bits[y * 50 + (x >> 3)] >> (x & 7)) & 1 : 1;
      const c = !bits ? off : white ? paper : ink, i = (y * 400 + x) * 4;
      px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255;
    }
  }
  lcdCtx.putImageData(lcdImage, 0, 0);
}

// ---- dioda i brzęczyk ---------------------------------------------------------------------------

let ledSince = 0;
function ledOff() { document.querySelector(".ctl.led")?.classList.remove("on"); }
function led(on) {
  const el = document.querySelector(".ctl.led");
  if (!el) return;
  if (on) { el.classList.add("on"); ledSince = performance.now(); }
  else setTimeout(() => el.classList.remove("on"), Math.max(0, 120 - (performance.now() - ledSince)));
}

let lastBeep = 0;
function beep(ms) {
  if (!ms) return;
  const el = document.querySelector(".ctl.buzzer");
  if (el) { el.classList.add("on"); setTimeout(() => el.classList.remove("on"), 200); }
  const now = performance.now();
  if (!soundOn || !audio || now - lastBeep < 120) return;
  lastBeep = now;
  const osc = audio.createOscillator(), gain = audio.createGain();
  osc.type = "square";
  osc.frequency.value = 2048;   // board_bench_b.h: BUZZER_HZ
  gain.gain.value = 0.04;
  osc.connect(gain).connect(audio.destination);
  osc.start();
  osc.stop(audio.currentTime + Math.min(ms, 400) / 1000);
}

// ---- panel stacji -------------------------------------------------------------------------------

const layout = () => R02;   // obudowa R02 według renderu koncepcyjnego
const pctX = (L, x) => `${(x / L.w) * 100}%`;
const pctY = (L, y) => `${(y / L.h) * 100}%`;

function place(el, L, x, y, w, h) {
  el.style.left = pctX(L, x);
  el.style.top = pctY(L, y);
  if (w !== undefined) el.style.width = pctX(L, w);
  if (h !== undefined) el.style.height = pctY(L, h);
}

function buildDevice() {
  const L = layout();
  const dev = $("device");
  dev.innerHTML = "";
  dev.className = "device case foil-case";
  dev.style.aspectRatio = `${L.w} / ${L.h}`;
  const body = document.createElement("div");
  body.className = "body";
  body.style.borderRadius = `${(L.radius / L.w) * 100}% / ${(L.radius / L.h) * 100}%`;
  dev.append(body);
  dev.insertAdjacentHTML("beforeend", foilSvg(L));
  const w = L.window;
  const canvas = document.createElement("canvas");
  canvas.className = "lcd";
  canvas.width = 400;
  canvas.height = 240;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Sharp LS027B7DH01A");
  place(canvas, L, w.cx - ACTIVE.w / 2, w.cy - ACTIVE.h / 2, ACTIVE.w, ACTIVE.h);
  dev.append(canvas);
  lcdCtx = canvas.getContext("2d");
  lcdImage = lcdCtx.createImageData(400, 240);
  for (const e of L.edge) {   // złącza na dolnej ściance; nazwy są na folii
    const d = document.createElement("div");
    d.className = `edge part ${e.part}`;
    d.innerHTML = `<span class="stub"></span>`;
    d.setAttribute("aria-hidden", "true");
    d.style.left = pctX(L, e.x);
    d.style.width = pctX(L, { usb: 13, en3: 18, sma: 9.2 }[e.part]);
    dev.append(d);
  }
  for (const c of L.controls) dev.append(control(L, c));
  sizeDevice();
  lastFrame = -1;
  draw(true);
  reflect();
}

// ---- folia panelu R02 (render koncepcyjny hardware/obudowa/render/stacja.html) -------------------

const FOIL = { ink: "#15181c", paper: "#ebe8e1", zone: "#dcd8cf", red: "#b3261e", muted: "#4a4f57", hint: "#3b3f45", rim: "#2c3035" };

function foilText(text, x, y, size, weight = 800, color = FOIL.ink, anchor = "middle") {
  return `<text xml:space="preserve" x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}">${esc(text)}</text>`;
}

function foilSymbol(id, x, y) {
  const s = 2.6, k = `fill="${FOIL.ink}"`, st = `fill="none" stroke="${FOIL.ink}" stroke-width="0.9" stroke-linecap="round" stroke-linejoin="round"`;
  if (id === "UP") return `<path ${k} d="M${x} ${y - s}L${x + s} ${y + s * 0.7}L${x - s} ${y + s * 0.7}Z"/>`;
  if (id === "DOWN") return `<path ${k} d="M${x} ${y + s}L${x + s} ${y - s * 0.7}L${x - s} ${y - s * 0.7}Z"/>`;
  if (id === "OK") return `<path ${st} d="M${x - s} ${y}L${x - s * 0.25} ${y + s * 0.8}L${x + s * 1.1} ${y - s * 0.9}"/>`;
  return `<path ${st} d="M${x + s} ${y}H${x - s * 0.9}"/><path ${k} d="M${x - s * 1.2} ${y}L${x - s * 0.1} ${y - s * 0.8}L${x - s * 0.1} ${y + s * 0.8}Z"/>`;
}

function foilSvg(L) {
  const r = L.recess, f = L.foil, w = L.window;
  const out = [`<svg class="foil" viewBox="0 0 ${L.w} ${L.h}" aria-hidden="true" font-family="'Nunito Sans', var(--font)">`,
    `<rect x="${r.x - 1.2}" y="${r.y - 1.2}" width="${r.w + 2.4}" height="${r.h + 2.4}" rx="3" fill="${FOIL.rim}"/>`,
    `<rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${FOIL.paper}"/>`,
    `<rect x="${f.column.x}" y="${f.column.y}" width="${f.column.w}" height="${f.column.h}" rx="3" fill="${FOIL.zone}"/>`,
    `<rect x="${w.cx - w.w / 2 - 3.5}" y="${w.cy - w.h / 2 - 3.5}" width="${w.w + 7}" height="${w.h + 7}" rx="2.5" fill="${FOIL.ink}"/>`,
    `<rect x="${w.cx - w.w / 2}" y="${w.cy - w.h / 2}" width="${w.w}" height="${w.h}" fill="#9da197"/>`,
    foilText(f.hint, w.cx, w.cy + w.h / 2 + 10, 3.2, 700, FOIL.hint),
    `<image href="wici-logo.svg" x="${f.brand.x}" y="${f.brand.y}" height="${f.brand.h}" width="${(f.brand.h * 2407) / 1050}"/>`,
    foilText("STACJA ŁĄCZNOŚCI AWARYJNEJ", f.brand.x, 33, 3.0, 800, FOIL.ink, "start"),
    foilText("СТАНЦІЯ АВАРІЙНОГО ЗВ'ЯЗКУ · EMERGENCY RADIO", f.brand.x, 37.6, 2.2, 600, FOIL.muted, "start")];
  for (const c of L.controls) {
    const { x, y } = c;
    if (NAV.includes(c.id)) {
      out.push(`<circle cx="${x}" cy="${y}" r="12" fill="${FOIL.zone}"/>`, foilSymbol(c.id, x, y - 16.5),
        foilText(LABELS.pl[c.id], x, y + 17, 4.6, 900), foilText(`${LABELS.uk[c.id]} · ${LABELS.en[c.id]}`, x, y + 21.6, 2.5, 700, FOIL.muted));
    }
    if (c.type === "led") out.push(foilText("ALARM", x, y + 9.5, 3.6, 900, FOIL.red));
    if (c.type === "toggle") out.push(foilText("CISZA RADIOWA", x, y + 25.5, 3.3, 900));
    if (c.type === "power") out.push(foilText("WYŁĄCZNIK", x, y + 18.5, 3.4, 900), foilText("WYŁĄCZ: TRZYMAJ 2 s", x, y + 22.6, 2.3, 700, FOIL.muted));
    if (c.type === "seal") out.push(foilText(labelOf(c, "pl"), x, y - c.h / 2 - 1.6, 2.4, 800, FOIL.muted));
  }
  for (const e of L.edge ?? []) out.push(foilText(`${e.label} ▾`, e.x, r.y + r.h - 1.6, 2.4, 800, FOIL.muted));
  out.push("</svg>");
  return out.join("");
}

// Naklejka serwisowa 22 × 12 mm nad otworem przycisku przygotowania: cała albo przebita (VOID).
function sealSvg(c) {
  const { w, h } = c;
  const voids = [];
  for (let i = -1; i < 4; i++) for (let j = 0; j < 3; j++) voids.push(`<text x="${i * 9 + (j % 2) * 4.5}" y="${j * 4.5 + 3.4}">VOID</text>`);
  if (sealBroken) {
    return `<svg viewBox="0 0 ${w} ${h}" aria-hidden="true" font-family="'Nunito Sans', var(--font)">
      <g font-size="3.2" font-weight="900" fill="#aeb2b7" opacity="0.9">${voids.join("")}</g>
      <circle cx="${w / 2}" cy="${h / 2}" r="${c.hole / 2}" fill="#0a0b0c"/><circle cx="${w / 2}" cy="${h / 2}" r="${c.hole / 2 - 0.6}" fill="#2b2e31"/></svg>`;
  }
  return `<svg viewBox="0 0 ${w} ${h}" aria-hidden="true" font-family="'Nunito Sans', var(--font)">
    <rect width="${w}" height="${h}" fill="#c9ccd0"/>
    <g font-size="3.2" font-weight="900" fill="#fff" opacity="0.35">${voids.join("")}</g>
    <g fill="#15181c" text-anchor="middle"><text x="${w / 2}" y="4.4" font-size="2.6" font-weight="900">PLOMBA WICI</text>
    <text x="${w / 2}" y="8.6" font-size="3" font-weight="700" font-family="var(--mono)">Nr 000123</text>
    <text x="${w / 2}" y="11" font-size="1.5" font-weight="600">NIE ZRYWAĆ</text></g></svg>`;
}

function resetSeal() {
  sealBroken = false;
  const el = document.querySelector('.ctl.seal');
  if (el) { el.classList.remove("broken"); el.innerHTML = sealSvg(layout().controls.find((c) => c.id === "PREP")); }
}

function control(L, c) {
  const interactive = ["button", "power", "toggle", "seal"].includes(c.type);
  const el = document.createElement(interactive ? "button" : "div");
  if (interactive) el.type = "button";
  el.className = `ctl ${c.type} ${c.shape ?? ""}`;
  el.dataset.id = c.id;
  place(el, L, c.x, c.y);
  // Obrys części jest większy niż otwór: pierścień przycisku Ø19,4, kołnierz wyłącznika Ø26, oprawka
  // diody Ø8,6 (stacja.html).
  const visual = { button: 19.4, power: 26, led: 8.6 }[c.type];
  el.style.width = pctX(L, visual ?? c.d ?? c.w);
  if (c.h && !c.d) el.style.height = pctY(L, c.h);
  const name = labelOf(c, lang === "en" ? "en" : "pl");
  el.setAttribute("aria-label", name);
  if (c.type === "toggle") el.innerHTML = `<span class="base"></span><span class="lever"></span><span class="pos top">I</span><span class="pos bottom">${lang === "en" ? "S" : "C"}</span>${c.guard ? '<span class="cover"></span>' : ""}`;
  if (c.type === "seal") { el.innerHTML = sealSvg(c); el.classList.toggle("broken", sealBroken); }
  if (c.type === "button") el.innerHTML = `<span class="cap"></span>`;
  if (c.type === "power") el.innerHTML = `<span class="bezel"><span class="cap"></span></span>`;
  if (interactive) {
    el.addEventListener("pointerdown", (ev) => onDown(ev, el, c));
    el.addEventListener("pointerup", (ev) => onUp(ev, el, c));
    el.addEventListener("pointercancel", (ev) => onUp(ev, el, c));
    el.addEventListener("keydown", (ev) => { if ((ev.key === " " || ev.key === "Enter") && !ev.repeat) { ev.preventDefault(); ev.stopPropagation(); press(c, true, el); } });
    el.addEventListener("keyup", (ev) => { if (ev.key === " " || ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); press(c, false, el); } });
  }
  return el;
}

function sizeDevice() {
  const L = layout();
  const dev = $("device");
  const real = $("real-size").checked;
  dev.classList.toggle("real", real);
  dev.style.width = real ? `${L.w * ppmm()}px` : "100%";
  $("calib").hidden = !real;
  const card = $("card-outline");
  card.style.width = `${85.6 * ppmm()}px`;
  card.style.height = `${53.98 * ppmm()}px`;
  card.style.maxWidth = "100%";
  $("ppmm").value = ppmm();
  $("ppmm-out").textContent = `${ppmm().toFixed(2)} px/mm`;
}
const ppmm = () => pref.get("ppmm", 96 / 25.4);

// Stan elementów: dźwignia CISZA (poziom pinu), ekran bez zasilania.
function reflect() {
  const on = !!s.power;
  const lines = s.screen?.lines ?? [], inv = s.screen?.inverted ?? [];
  const row = Math.max(0, inv.lastIndexOf(true));   // kursor (pasek trybu serwisowego jest w wierszu 0)
  $("station-state").textContent = on ? `${t("on")}${s.board?.tx ? " · " + t("transmitting") : ""} · ${(lines[row] ?? "").trim()}`.trim() : t("off");
  if (!on) ledOff();
  // Czytnik ekranu: tekst odczytany z pikseli panelu.
  document.querySelector("canvas.lcd")?.setAttribute("aria-label", on ? lines.filter((l) => l.trim()).join(". ") : t("off"));
  const sw = document.querySelector(".ctl.toggle");
  if (sw) sw.classList.toggle("on", !!s.switch);
  document.querySelector("canvas.lcd")?.classList.toggle("off", !on || !s.board?.lcd_on);
}

// ---- obsługa przycisków -------------------------------------------------------------------------

let powerTimer = null;
let guardTimer = null;
const NAV = ["UP", "DOWN", "OK", "BACK"];

function onDown(ev, el, c) {
  el.setPointerCapture?.(ev.pointerId);
  ev.preventDefault();
  press(c, true, el);
}
function onUp(ev, el, c) {
  press(c, false, el);
}
// Przyciski zmieniają tylko poziom pinu; czy program go odczyta, zależy od programu (pętla stoi
// w czasie nadawania ramki i rysowania ekranu, jak na płytce).
function press(c, down, el) {
  // Zwolnienie przechodzi zawsze (także w czasie przeskoku czasu), żeby pin nie został w stanie niskim.
  if (!ready || (busyText && down)) return;
  if (NAV.includes(c.id)) {
    if (down === held.has(c.id)) return;
    if (down) {
      held.add(c.id);
      exercise?.press();
    } else held.delete(c.id);
    el?.classList.toggle("pressed", down);
    sim.setButton(c.id, down);
    return;
  }
  if (c.type === "power") {
    el?.classList.toggle("pressed", down);
    if (down) {
      held.add("POWER");
      el.dataset.wasOn = sim.station.powered ? "1" : "";
      clearTimeout(powerTimer);
      if (el.dataset.wasOn) powerTimer = setTimeout(() => { if (held.has("POWER")) serial(async () => { await sim.power(false); await poll(true); }); }, 2000);
    } else {
      held.delete("POWER");
      clearTimeout(powerTimer);
      if (!el.dataset.wasOn && !sim.station.powered) serial(async () => { await sim.power(true); lastFrame = -1; await poll(true); });
    }
    return;
  }
  if (c.type === "toggle") {
    if (!down) return;
    if (c.guard && !el.classList.contains("open")) {
      el.classList.add("open");
      clearTimeout(guardTimer);
      guardTimer = setTimeout(() => el.classList.remove("open"), 6000);
      return;
    }
    sim.setSwitch(!sim.switchOn());
    clearTimeout(guardTimer);
    guardTimer = setTimeout(() => el.classList.remove("open"), 1500);
    s.switch = sim.switchOn();
    reflect();
    return;
  }
  if (c.type === "seal" && !sealBroken) {
    // Naklejka VOID jest jednorazowa: pierwsze dotknięcie przebija ją rysikiem (zostaje napis VOID), dopiero
    // potem można wcisnąć przycisk przygotowania w otworze Ø4 mm (oprogramowanie.md, F113).
    if (!down) return;
    sealBroken = true;
    el?.classList.add("broken");
    if (el) el.innerHTML = sealSvg(c);
    logItems.push({ t: sim.nowUs, kind: "seal", source: "stacja", text: t("sealTorn") });
    return;
  }
  if (c.type === "seal") {
    el?.classList.toggle("pressed", down);
    if (down) held.add("PREP"); else held.delete("PREP");
    sim.station.setInput(sim.pins.PREP, down ? 0 : 1);
  }
}

function releaseAll() {
  if (sim?.world) {
    for (const id of held) {
      if (NAV.includes(id)) sim.setButton(id, false);
      if (id === "PREP") sim.station.setInput(sim.pins.PREP, 1);
    }
  }
  held.clear();
  clearTimeout(powerTimer);
  document.querySelectorAll(".ctl.power").forEach((e) => { e.dataset.wasOn = "1"; });   // zwolnienie po utracie fokusu nie włącza
  document.querySelectorAll(".ctl.pressed").forEach((e) => e.classList.remove("pressed"));
}

const KEYS = { ArrowUp: "UP", ArrowDown: "DOWN", Enter: "OK", Backspace: "BACK", Escape: "BACK" };
function typing(target) { return target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName); }
function keyboard(ev, down) {
  if (typing(ev.target) || ev.target?.closest?.(".tabs") || ev.altKey || ev.ctrlKey || ev.metaKey) return;
  const id = KEYS[ev.key];
  if (!id || ev.repeat) { if (id) ev.preventDefault(); return; }
  if (ev.target?.closest?.(".side") && (ev.key === "Enter")) return;
  ev.preventDefault();
  const c = layout().controls.find((x) => x.id === id);
  press(c, down, document.querySelector(`.ctl[data-id="${id}"]`));
}

// ---- panele -------------------------------------------------------------------------------------

async function poll(force) {
  const st = sim.station;
  s = {
    screen: sim.screen(), post: sim.postState(), power: st.powered, switch: sim.switchOn(), t: sim.nowUs,
    board: st.board(), restarts: st.restarts, bootUs: st.bootUs, loss: sim.loss(), nodeOn: sim.node.powered,
    radioFault: st.radioFault, framFault: st.framFault,
  };
  $("clock").textContent = clock(sim.nowUs / 1000);
  reflect();
  if (exercise && await exercise.update(s)) force = true;
  renderPanel(force);
}

function clock(ms) {
  const total = Math.floor(ms / 1000), d = Math.floor(total / 86400);
  const hh = String(Math.floor((total % 86400) / 3600)).padStart(2, "0");
  const mm = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${d ? d + " d " : ""}${hh}:${mm}:${ss}`;
}
const minutes = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`;

function selectTab(name) {
  if (!["train", "rx", "env", "console", "log"].includes(name)) name = "train";
  tab = name;
  if (exercise) exercise.panel = name;
  pref.set("tab", name);
  for (const b of document.querySelectorAll(".tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const p of document.querySelectorAll(".panel")) p.hidden = p.id !== `panel-${name}`;
  renderPanel(true);
}

// Panel rysowany od nowa tylko przy zmianie danych; pola formularzy zachowują treść i fokus.
function renderPanel(force) {
  const panel = $(`panel-${tab}`);
  if (!panel) return;
  if (!ready) { panel.innerHTML = ""; return; }
  const html = { train: trainPanel, rx: rxPanel, env: envPanel, console: consolePanel, log: logPanel }[tab]();
  if (!force && html === panelKey) return;
  if (!force && panel.contains(document.activeElement) && typing(document.activeElement)) return;
  panelKey = html;
  const values = {};
  for (const f of panel.querySelectorAll("input[id], textarea[id], select[id]")) values[f.id] = f.type === "checkbox" ? null : f.value;
  const focus = document.activeElement?.id;
  panel.innerHTML = html;
  for (const [id, v] of Object.entries(values)) {
    const f = $(id);
    if (f && v !== null && f.dataset.keep !== undefined) f.value = v;
  }
  if (focus && $(focus)) $(focus).focus();
  const out = $("console-out");
  if (out) out.scrollTop = out.scrollHeight;
}

function trainPanel() {
  if (!exercise) {
    return `<div class="group"><h2>${t("freeTitle")}</h2><p class="muted">${t("freeText")}</p></div>
      <div class="group"><h2>${t("exercises")}</h2><div class="scenarios">${SCENARIOS.map((sc) =>
        `<button type="button" class="scenario" data-start="${sc.id}"><strong>${esc(sc.title[lang])}</strong><span>${esc(sc.brief[lang])}</span></button>`).join("")}</div></div>`;
  }
  const sc = exercise.scenario;
  const steps = sc.steps.map((st, i) => {
    const rec = exercise.records.find((r) => r.step === i);
    const cls = i < exercise.index ? "done" : i === exercise.index ? "current" : "";
    const meta = rec ? `${minutes(rec.simS * 1000)} · ${rec.presses}×` : "";
    return `<li class="${cls}"><span>${esc(st[lang])}</span><span class="meta">${meta}</span></li>`;
  }).join("");
  const step = exercise.current;
  const hint = !exercise.finished && step?.hint
    ? (showHint ? `<p class="hint">${esc(step.hint[lang])}</p>` : `<div class="row"><button type="button" class="btn" data-act="hint">${t("hint")}</button></div>`) : "";
  const warn = exercise.warnings.map((w) => `<p class="warning">⚠ ${esc(w[lang])}</p>`).join("");
  let end = "";
  if (exercise.finished) {
    end = `<div class="group"><h2>${t("done")}</h2><div class="summary">
      <div><b>${minutes(exercise.totalS * 1000)}</b><span>${t("totalTime")}</span></div>
      <div><b>${exercise.presses}</b><span>${t("presses")}</span></div>
      <div><b>${exercise.hints}</b><span>${t("hints")}</span></div></div></div>`;
  }
  return `<div class="group"><h2>${esc(sc.title[lang])}</h2><p class="muted">${esc(sc.brief[lang])}</p></div>
    <div class="group"><ol class="steps">${steps}</ol>${hint}${warn}</div>${end}
    <div class="row"><button type="button" class="btn" data-act="again">${t("again")}</button>
    <button type="button" class="btn" data-act="list">${exercise.finished ? t("list") : t("stop")}</button></div>`;
}

function copyLabel(n) {
  if (lang !== "pl") return n === 1 ? "copy" : "copies";
  return n === 1 ? "kopia" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "kopie" : "kopii";
}

function rxPanel() {
  const r = s.post ?? { requests: [], auto: {}, stations: [] };
  const a = r.auto ?? {};
  const decisions = [0, 3, 4, 5, 6].map((v) => `<option value="${v}"${a.decision === v ? " selected" : ""}>${v ? STATES[lang][v] : t("none")}</option>`).join("");
  const list = [...r.requests].reverse().map((q) => {
    const actions = [2, 3, 4, 5, 6].map((v) => `<button type="button" class="btn" data-decide="${q.number}" data-state="${v}"${q.state === v || (v === 5 && !q.reply_acked) ? " disabled" : ""}${v === 5 ? ` title="${lang === "pl" ? "Najpierw wyślij instrukcję i poczekaj na potwierdzenie odbioru" : "First send instructions and wait for delivery confirmation"}"` : ""}>${STATES[lang][v]}</button>`).join("");
    return `<div class="req u${q.urgency}">
      <div class="req-head"><b>${String(q.number).padStart(4, "0")}</b>${q.type === "test" ? '<span class="chip">TEST</span>' : ""}
        <span>${esc(CATEGORIES[lang][q.category] ?? "")}, ${q.people}</span><span class="chip u${q.urgency}">${URGENCY[lang][q.urgency] ?? ""}</span>
        <span class="chip s${q.state}">${STATES[lang][q.state]}</span>${q.changed ? `<span class="chip s2">${t("changed")}</span>` : ""}
        ${q.received_acked >= 0 ? `<span class="chip s3">✓ ${t("received")}</span>` : ""}${q.identity ? `<span class="chip">${t("backup")}</span>` : ""}</div>
      <p class="muted">${esc(q.location)}${q.text ? " · " + esc(q.text) : ""} · ${lang === "pl" ? "wersja" : "revision"} ${q.revision} · ${q.copies} ${copyLabel(q.copies)} · ${clock(q.first_ms)}</p>
      ${q.type === "test" ? "" : `<div class="req-actions">${actions}</div>
      ${q.reply ? `<p>↳ ${esc(q.reply)}${q.reply_acked ? " ✓" : ""}</p>` : ""}
      <div class="row"><input type="text" id="reply-${q.number}" data-keep maxlength="96" placeholder="${t("reply")}" aria-label="${t("reply")} ${q.number}">
      <button type="button" class="btn" data-reply="${q.number}">${t("send")}</button></div>`}</div>`;
  }).join("");
  return `<div class="group"><h2>${t("rxTitle")}</h2>
      <div class="row"><label><input type="checkbox" id="rx-on"${postPort ? " checked" : ""}> ${t("rxOn")}</label>
      <label>${t("identity")} <select id="rx-identity"><option value="main"${r.identity === 0 ? " selected" : ""}>${t("main")}</option><option value="backup"${r.identity === 1 ? " selected" : ""}>${t("backup")}</option></select></label></div>
      <div class="row"><label><input type="checkbox" id="auto-read"${a.read ? " checked" : ""}> ${t("autoRead")}</label> <input type="number" id="auto-read-min" min="0" max="600" value="${a.read_min}"> ${t("min")}</div>
      <div class="row"><label>${t("autoDecide")} <select id="auto-decision">${decisions}</select></label> ${t("after")} <input type="number" id="auto-decide-min" min="0" max="600" value="${a.decide_min}"> ${t("min")}</div>
      <p class="muted">${r.outbox} ${t("outbox")} · ${(r.stations ?? []).length} ${t("stations")}</p></div>
    <div class="group">${list || `<p class="empty">${t("noRequests")}</p>`}</div>
    <div class="group"><label for="bulletin-text"><h3>${t("bulletin")}</h3></label>
      <textarea id="bulletin-text" data-keep rows="2" maxlength="192" placeholder="${t("bulletinPh")}"></textarea>
      <div class="row"><button type="button" class="btn primary" data-act="bulletin">${t("send")}</button></div></div>`;
}

function envPanel() {
  const up = isFinite(s.loss);
  const loss = up ? s.loss : lastLoss;
  const rssi = TX_DBM - loss;
  const b = s.board ?? {};
  const uptime = s.power ? clock((b.uptime_us ?? 0) / 1000) : "";
  return `<div class="group"><h2>${t("linkTitle")}</h2>
      <label class="check"><input type="checkbox" id="link-up"${up ? " checked" : ""}> ${t("linkUp")}</label>
      <div class="field"><label for="link-loss">${t("loss")}</label><output class="num">${loss} dB</output></div>
      <input type="range" id="link-loss" min="70" max="140" step="1" value="${loss}"${up ? "" : " disabled"}>
      <div class="field"><span>${t("rssi")}</span><span class="num">${rssi} dBm</span></div>
      <div class="field"><span>${t("margin")}</span><span class="num ${rssi - SENSITIVITY_DBM < 8 ? "fail" : ""}">${rssi - SENSITIVITY_DBM} dB</span></div>
      <p class="muted">${t("fading")}</p></div>
    <div class="group"><h2>${t("faults")}</h2>
      <label class="check"><input type="checkbox" id="fault-radio"${s.radioFault ? " checked" : ""}> ${t("radioFault")}</label>
      <label class="check"><input type="checkbox" id="fault-fram"${s.framFault ? " checked" : ""}> ${t("framFault")}</label>
      <p class="muted">${t("faultNote")}</p></div>
    <div class="group"><h2>${t("node")}</h2>
      <label class="check"><input type="checkbox" id="node-on"${s.nodeOn ? " checked" : ""}> ${t("nodeOn")}</label></div>
    <div class="group"><h2>${t("power")}</h2><p class="muted">${t("powerNote")}</p></div>
    <div class="group"><h2>${t("station")}</h2>
      <div class="field"><span>${t("panel")}: ${t("switchPos")}</span><span class="chip">${s.switch ? t("swOn") : t("swOff")}</span></div>
      <div class="field"><span>${s.power ? t("on") : t("off")}</span><span class="num">${s.power ? `${t("uptime")} ${uptime}` : ""}</span></div>
      ${s.power ? `<div class="field"><span>${t("radioState")}</span><span class="num">${(b.radio_mhz ?? 0).toFixed(3)} MHz · ${b.radio_dbm} dBm${b.tx ? " · " + t("transmitting") : ""}</span></div>` : ""}
      <div class="field"><span>${t("restarts")}</span><span class="num">${s.restarts ?? 0}</span></div>
      <div class="row"><button type="button" class="btn danger" data-act="fresh">${t("resetStation")}</button></div></div>`;
}

function consolePanel() {
  const devices = ["stacja", "węzeł"];
  return `<div class="group"><h2>${t("consoleTitle")}</h2><p class="muted">${t("consoleNote")}</p>
      <div class="row"><label>${t("device")} <select id="console-device">${devices.map((d) => `<option value="${esc(d)}"${d === consoleDevice ? " selected" : ""}>${esc(d)}</option>`).join("")}</select></label>
      <button type="button" class="btn" data-act="console-clear">${t("clear")}</button>
      <button type="button" class="btn" data-act="console-close">${t("disconnect")}</button></div>
      <pre class="console num" id="console-out">${esc(consoles[consoleDevice] ?? "")}</pre>
      <form class="row" id="console-form"><input type="text" id="console-cmd" data-keep placeholder="INFO" aria-label="${t("command")}" autocomplete="off" spellcheck="false">
      <button type="submit" class="btn primary">${t("send")}</button></form></div>`;
}

function logPanel() {
  const items = logItems.filter((e) => showAir || e.kind !== "air");
  const head = `<label class="check"><input type="checkbox" id="log-air"${showAir ? " checked" : ""}> ${t("logAir")}</label>`;
  if (!items.length) return `${head}<p class="empty">${t("logEmpty")}</p>`;
  return `${head}<ol class="log">${[...items].reverse().slice(0, 300).map((e) =>
    `<li><span class="t">${clock(e.t / 1000)}</span><span class="k ${esc(e.kind)}">${esc(e.source ?? "")} ${esc(e.kind)}</span><span>${esc(e.text ?? "")}</span></li>`).join("")}</ol>`;
}

// ---- zgłoszenie uwagi --------------------------------------------------------------------------

// Nowe zgłoszenie w GitHub Issues (formularz .github/ISSUE_TEMPLATE/uwaga-symulator.yml) z polem
// „Dane z symulatora”: ćwiczenie i krok, ekran stacji, czas, układ, wersja obrazu, przeglądarka.
const ISSUE_URL = "https://github.com/tmierzwa/WICI/issues/new";
function feedbackContext() {
  const lines = [
    `obraz: ${buildStamp || "?"}`,
    `język strony: ${lang}, tempo: ${speed}×`,
    `czas symulacji: ${sim?.world ? clock(sim.nowUs / 1000) : "-"}`,
    exercise ? `ćwiczenie: ${exercise.scenario.id}, krok ${Math.min(exercise.index + 1, exercise.scenario.steps.length)}/${exercise.scenario.steps.length}${exercise.finished ? " (ukończone)" : ""}`
      : "praca swobodna",
    `stacja: ${s.power ? "włączona" : "wyłączona"}, CISZA ${s.switch ? "wł." : "wył."}${sealBroken ? ", naklejka SERWIS przebita" : ""}`,
    ...(s.power && s.screen ? ["ekran:", ...s.screen.lines.map((l, i) => `  ${s.screen.inverted?.[i] ? ">" : " "} ${l}`)] : []),
    `przeglądarka: ${navigator.userAgent}`,
  ];
  return lines.join("\n");
}
function updateFeedbackLink() {
  const params = new URLSearchParams({ template: "uwaga-symulator.yml", labels: "symulator", context: feedbackContext() });
  $("feedback").href = `${ISSUE_URL}?${params}`;
}

// ---- zdarzenia strony ---------------------------------------------------------------------------

function bind() {
  document.addEventListener("keydown", (ev) => keyboard(ev, true));
  document.addEventListener("keyup", (ev) => keyboard(ev, false));
  window.addEventListener("blur", releaseAll);
  for (const b of document.querySelectorAll("[data-speed]")) b.addEventListener("click", () => {
    speed = Number(b.dataset.speed);
    document.querySelectorAll("[data-speed]").forEach((x) => x.classList.toggle("on", x === b));
  });
  for (const b of document.querySelectorAll("[data-skip]")) b.addEventListener("click", () => skip(Number(b.dataset.skip)));
  for (const b of document.querySelectorAll(".tabs button")) b.addEventListener("click", () => selectTab(b.dataset.tab));
  // Link aktualizowany tuż przed otwarciem (także środkowym przyciskiem i z klawiatury).
  for (const ev of ["pointerdown", "focus", "mouseenter"]) $("feedback").addEventListener(ev, updateFeedbackLink);
  $("sound").addEventListener("click", () => {
    soundOn = !soundOn;
    if (soundOn && !audio) { try { audio = new AudioContext(); } catch { soundOn = false; } }
    audio?.resume?.();
    $("sound").setAttribute("aria-pressed", String(soundOn));
    $("sound").textContent = t(soundOn ? "soundOn" : "soundOff");
  });
  $("lang").addEventListener("click", () => { lang = lang === "pl" ? "en" : "pl"; pref.set("lang", lang); applyLang(); buildDevice(); renderPanel(true); });
  $("real-size").addEventListener("change", () => { sizeDevice(); $("device-wrap").classList.toggle("real", $("real-size").checked); });
  $("ppmm").addEventListener("input", () => { pref.set("ppmm", Number($("ppmm").value)); sizeDevice(); });
  for (const id of ["train", "rx", "env", "console", "log"]) {
    $(`panel-${id}`).addEventListener("click", panelClick);
    $(`panel-${id}`).addEventListener("change", panelChange);
    $(`panel-${id}`).addEventListener("submit", panelSubmit);
  }
}

function applyLang() {
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
  $("lang").textContent = lang === "pl" ? "EN" : "PL";
  $("sound").textContent = t(soundOn ? "soundOn" : "soundOff");
}

// Polecenie aplikacji stanowiska; błąd pokazany przy polu, z którego przyszedł tekst.
function postCommand(line, field) {
  const out = sim.post.cmd(line);
  if (out.startsWith("err")) {
    if (field) { field.setCustomValidity(out.slice(4)); field.reportValidity(); setTimeout(() => field.setCustomValidity(""), 3000); }
    return false;
  }
  return true;
}
const clean = (text) => text.trim().replace(/\s+/g, " ").replace(/"/g, "„").replace(/\\/g, "/");

function panelClick(ev) {
  const b = ev.target.closest("button");
  if (!b || !ready || busyText || b.type === "submit") return;
  if (b.dataset.start) { serial(() => startExercise(SCENARIOS.find((x) => x.id === b.dataset.start))); return; }
  if (b.dataset.decide) postCommand(`decide ${b.dataset.decide} ${b.dataset.state}`);
  else if (b.dataset.reply) {
    const input = $(`reply-${b.dataset.reply}`);
    const text = clean(input.value);
    if (text && postCommand(`reply ${b.dataset.reply} ${text}`, input)) input.value = "";
  } else {
    switch (b.dataset.act) {
      case "hint": showHint = true; exercise.hints++; break;
      case "again": serial(() => startExercise(exercise.scenario)); return;
      case "list": case "fresh": serial(freePlay); return;
      case "bulletin": {
        const area = $("bulletin-text");
        const text = clean(area.value);
        if (text && postCommand(`bulletin ${text}`, area)) area.value = "";
        break;
      }
      case "console-clear": consoles[consoleDevice] = ""; break;
      case "console-close": {
        const d = consoleDevice === "stacja" ? sim.station : sim.node;
        d.setUsb(0, false);
        break;
      }
      default: return;
    }
  }
  serial(() => poll(true));
}

function panelSubmit(ev) {
  if (ev.target.id !== "console-form") return;
  ev.preventDefault();
  if (!ready) return;
  const input = $("console-cmd");
  const line = input.value.trim();
  if (!line) return;
  const d = consoleDevice === "stacja" ? sim.station : sim.node;
  if (!d.powered) return;
  if (!d.usbOpen[0]) d.setUsb(0, true);
  consoles[consoleDevice] += `> ${line}\n`;
  d.usbWrite(0, line + "\n");
  input.value = "";
  renderPanel(true);
  $("console-cmd")?.focus();
}

function panelChange(ev) {
  const el = ev.target;
  if (!ready) return;
  switch (el.id) {
    case "rx-on":
      postPort = el.checked;
      sim.post.cmd(`port ${postPort ? "open" : "close"}`);
      sim.node.setUsb(1, postPort);   // aplikacja zamyka port: węzeł widzi rozłączenie, nic nie płynie w żadną stronę
      break;
    case "rx-identity": postCommand(`identity ${el.value}`); break;
    case "auto-read": case "auto-read-min": case "auto-decision": case "auto-decide-min":
      postCommand(`auto ${$("auto-read").checked ? 1 : 0} ${Number($("auto-read-min").value) || 0} ${$("auto-decision").value} ${Number($("auto-decide-min").value) || 0}`);
      break;
    case "link-up": sim.setLoss(el.checked ? lastLoss : Infinity); break;
    case "link-loss": lastLoss = Number(el.value); sim.setLoss(lastLoss); break;
    case "fault-radio": sim.station.fault("radio", el.checked); break;
    case "fault-fram": sim.station.fault("fram", el.checked); break;
    case "node-on": serial(async () => { if (el.checked) await sim.node.powerOn(sim.nowUs); else sim.node.powerOff(sim.nowUs); }); break;
    case "console-device": consoleDevice = el.value; renderPanel(true); return;
    case "log-air": showAir = el.checked; pref.set("logAir", showAir); renderPanel(true); return;
    default: return;
  }
  serial(() => poll(true));
}

main().catch((err) => {
  busy("");
  fail(new Error(`Nie udało się uruchomić symulatora (${err.message}). Otwórz stronę przez serwer HTTP, np. python3 -m http.server -d software/simulator/web`));
});

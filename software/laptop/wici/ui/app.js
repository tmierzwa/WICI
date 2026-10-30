// SPDX-License-Identifier: MIT
// Panel przygotowania stacji WICI. Bez bibliotek i bez kroku budowania: zwykły JavaScript (ES2017),
// który działa w przeglądarkach z ostatnich lat. Stan stacji przychodzi długim odpytywaniem /api/state;
// sprawdzenie konfiguracji robi aplikacja (/api/config/check), więc reguły są w jednym miejscu.
"use strict";

const $ = (id) => document.getElementById(id);
const LANGS = ["PL", "UK", "EN"];
const enc = new TextEncoder();
const bytes = (s) => enc.encode(String(s).normalize("NFC")).length;

let state = { v: -1, station: { phase: "searching" }, session: {}, journal: [], app: {} };
let offline = false, stopped = false, showAll = false, lastCard = null, checkTimer = null, checkSeq = 0;
let envelopesShown = false;
let limits = null;                      // z aplikacji (configdoc): formularz powstaje po pierwszym stanie

// ---- Komunikacja z aplikacją ----------------------------------------------------------------

async function api(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}), credentials: "same-origin",
  });
  let data = {};
  try { data = await r.json(); } catch (e) { /* pusta odpowiedź */ }
  return { ok: r.ok, status: r.status, data };
}

async function poll() {
  let failures = 0;
  while (!stopped) {
    try {
      const r = await fetch(`/api/state?v=${state.v}`, { credentials: "same-origin", cache: "no-store" });
      if (r.status === 403) { setOffline("Sesja panelu wygasła. Uruchom START ponownie."); return; }
      if (!r.ok) throw new Error(String(r.status));
      state = await r.json();
      failures = 0;
      if (offline) setOffline(null);
      render();
    } catch (e) {
      failures++;
      if (failures >= 2) setOffline("Aplikacja WICI została zamknięta albo przestała odpowiadać. Uruchom START ponownie.");
      await sleep(2000);
    }
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function setOffline(text) {
  offline = !!text;
  $("offline").hidden = !offline;
  if (text) {
    $("offline-text").textContent = text;
    setPill("pill-alarm", "Brak połączenia z aplikacją");
  }
}

// ---- Stan stacji ------------------------------------------------------------------------------

// Tylko przy zmianie: #conn ma role="status", więc czytnik ekranu ogłasza każdą zmianę tekstu.
function setPill(kind, text) {
  const p = $("conn");
  if (p.className !== "pill " + kind) p.className = "pill " + kind;
  if (p.textContent !== text) p.textContent = text;
}

function station() { return state.station || {}; }
function connected() { return station().phase === "connected"; }
function configured() {
  const s = station(), st = s.status || {};
  return "configured" in st ? st.configured : (s.hello || {}).configured;
}
function prepMode() {
  const s = station();
  return !!((s.status && "prep" in s.status) ? s.status.prep : s.hello && s.hello.prep);
}

function uptime(sec) {
  if (typeof sec !== "number") return "–";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

function volts(mv) { return (mv / 1000).toLocaleString("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " V"; }

const POWER_ALARMS = { wymien_ogniwa: "wymień ogniwa", odlaczone_12v: "12 V odłączone", za_wysokie_12v: "12 V za wysokie, odłączone" };

function power(p) {
  if (!p) return "–";
  let text = p.source === "aa" ? "ogniwa AA" : "źródło 12 V";
  const mv = p.source === "aa" ? p.mv_aa : p.mv_12v;
  if (typeof mv === "number" && mv > 0) text += " · " + volts(mv);
  if (POWER_ALARMS[p.alarm]) text += " · " + POWER_ALARMS[p.alarm];
  return text;
}

const PROBLEMS = {
  permission: (p) => [`Brak uprawnień do portu `, code(p.port), `. W terminalu wpisz `, code("sudo usermod -aG dialout $USER"),
    ` (w Arch Linux grupa `, code("uucp"), `), wyloguj się i zaloguj ponownie. Bez hasła administratora tego komputera użyj innego laptopa.`],
  busy: (p) => [`Port `, code(p.port), ` jest zajęty przez inny program, np. monitor portu szeregowego. Zamknij go.`],
  other: (p) => [`Nie udało się otworzyć portu `, code(p.port), `: ${p.detail || "nieznany błąd"}.`],
  missing: (p) => [`Nie ma portu `, code(p.port), `. Sprawdź przewód USB i nazwę portu.`],
};

function code(text) { const c = document.createElement("code"); c.textContent = text; return c; }

function render() {
  if (stopped) return;                  // po „Zakończ” albo „Oddaj laptop” spóźniona odpowiedź nie zmienia ekranu
  if (!limits && state.app && state.app.limits) {
    limits = state.app.limits;
    initForm();
  }
  const s = station(), h = s.hello || {}, st = s.status || {};
  $("search").hidden = s.phase === "connected" || s.phase === "incompatible";
  $("station").hidden = !$("search").hidden;
  const problem = $("search-problem");
  problem.hidden = !s.problem;
  if (s.problem) problem.replaceChildren(...(PROBLEMS[s.problem.kind] || PROBLEMS.other)(s.problem));
  const skipped = $("search-skipped");
  skipped.hidden = !(s.skipped && s.skipped.length);
  if (!skipped.hidden) {
    skipped.textContent = `Porty bez odpowiedzi stacji: ${s.skipped.join(", ")}. Panel nie otwiera ich ponownie, dopóki nie ` +
      "zostaną odłączone, bo otwarcie portu resetuje niektóre urządzenia. Węzeł stanowiska odpowiada tylko w trybie " +
      "przygotowania: włącz go i kliknij „Szukaj ponownie”.";
  }

  if (s.phase === "connected") setPill("pill-ok", "Połączono: " + (h.name || "stacja"));
  else if (s.phase === "incompatible") setPill("pill-alarm", "Niezgodna wersja stacji");
  else setPill("pill-wait", "Szukam stacji…");

  if (!$("station").hidden) {
    const node = (st.role || h.role) === "wezel";
    $("st-role").textContent = node ? "Węzeł stanowiska" : "Stacja schronienia";
    $("st-name").textContent = h.name || "WICI-······";
    const prep = prepMode();
    const pill = $("st-prep");
    pill.className = "pill " + (prep ? "pill-ok" : "pill-warn");
    pill.textContent = prep ? "Tryb przygotowania" : "Zwykła praca";
    $("st-config").textContent = configured() ? `nr ${st.config_seq != null ? st.config_seq : "?"}` : "brak (nowa stacja)";
    $("st-power").textContent = power(st.power);
    $("st-uptime").textContent = uptime(st.uptime);
    $("st-fw").textContent = h.fw || st.fw || "–";
    $("st-port").textContent = s.port || "–";
    const banner = $("st-banner");
    banner.className = "banner";
    if (s.phase === "incompatible") {
      banner.classList.add("banner-alarm");
      banner.textContent = `Stacja obsługuje protokół w wersji ${(h.contracts || []).join(", ") || "?"}, a ta aplikacja wersję ${(state.app || {}).contract || "?"}. Potrzebna jest zgodna wersja aplikacji albo oprogramowania stacji.`;
    } else if (!prep) {
      banner.textContent = "Konfiguracja i karta wymagają trybu przygotowania: przytrzymaj ok. 3 s przycisk pod naklejką serwisową. Panel zauważy to sam.";
    }
    banner.hidden = s.phase !== "incompatible" && prep;
  }
  renderSession();
  renderJournal();
  const a = state.app || {};
  $("foot").textContent = `WICI ${a.version || ""} · Python ${a.python || ""} · ${a.platform || ""}`;
}

// ---- Zestaw, logowanie i kopia bazy ---------------------------------------------------------

function session() { return state.session || {}; }
function loggedIn() { return !!session().user; }

function fillAccounts(select, accounts) {
  const list = accounts || [];
  if (list.length === select.options.length && list.every((a, i) => select.options[i].value === a.id)) return;   // otwarta lista zostaje
  const keep = select.value;
  select.replaceChildren(...list.map((a) => {
    const o = document.createElement("option");
    o.value = a.id;
    o.textContent = a.label;
    return o;
  }));
  if (keep && [...select.options].some((o) => o.value === keep)) select.value = keep;
}

function clock(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderSession() {
  const s = session(), kit = s.kit;
  const user = loggedIn();
  $("kit-missing").hidden = kit !== "missing";
  $("destroyed").hidden = kit !== "destroyed";
  if (kit === "destroyed") {
    $("destroyed-usb").hidden = s.destroyed_usb === false;
    $("destroyed-no-usb").hidden = s.destroyed_usb !== false;
    const d = state.destroy || {};
    $("destroyed-station").textContent = DESTROY_STATION[d.state || "pending"](d);
  }
  $("kit-missing-path").textContent = s.usb || "";
  $("kit-new").hidden = kit !== "new" || envelopesShown;
  $("recover").hidden = kit !== "broken" || envelopesShown;
  $("conflict").hidden = !s.conflict;
  $("login").hidden = !(kit === "ready" && !user && !s.conflict);
  $("tabs").hidden = !user || envelopesShown;
  showTabs();
  fillAccounts($("login-account"), s.accounts);
  fillAccounts($("kit-account"), s.accounts);
  const who = $("who");
  who.hidden = !user;
  who.className = "pill pill-ok";
  who.textContent = s.user_label || "";
  if (s.conflict) {
    for (const side of ["disk", "usb"]) {
      const c = s.conflict[side];
      $(`choose-${side}`).textContent = `${side === "disk" ? "Kopia z dysku" : "Kopia z pamięci USB"} (zapis ${c.gen}, ${new Date(c.at).toLocaleString("pl-PL")})`;
    }
  }
  const copyStatus = $("copy-status"), db = s.db || {};
  copyStatus.hidden = !user;
  if (user) {
    const last = db.usb_at ? ` Ostatnia kopia: ${new Date(db.usb_at).toLocaleString("pl-PL")}.` : " Brak potwierdzonego zapisu w tej sesji.";
    copyStatus.classList.toggle("notice-alarm", !db.usb_saved);
    copyStatus.textContent = db.disk_error ? "Błąd zapisu na dysku laptopa. Nie ma potwierdzenia utrwalenia ostatnich zmian." :
      db.usb_problem ? `${db.usb_problem}. Włóż właściwą pamięć zestawu.${last}` :
      db.usb_error ? `Błąd zapisu kopii na USB. Najnowsze dane nie są gotowe do przeniesienia.${last}` :
      db.usb_saved ? `Kopia na USB jest aktualna.${last}` : `Trwa zapis kopii na USB. Nie wyjmuj pamięci.${last}`;
  }
  if (!user) return;
  $("kit-user").textContent = s.user_label || "–";
  $("kit-disk").textContent = db.disk_error ? "błąd: " + db.disk_error : (db.saved ? "zapisana" : "zapisuję…");
  $("kit-usb").textContent = db.usb_problem ? db.usb_problem : db.usb_error ? "błąd zapisu" : db.usb_saved ? `zapisana o ${clock(db.usb_at)}` : (db.usb_at ? `zapisuję… (ostatnia o ${clock(db.usb_at)})` : "zapisuję…");
  $("kit-path").textContent = s.usb || "–";
  const warn = $("kit-warning");
  warn.hidden = !(db.usb_problem || db.usb_error || db.disk_error);
  if ((db.usb_problem || db.usb_error) === "inna pamięć USB niż pamięć zestawu") warn.textContent = "Pod ścieżką pamięci zestawu jest inna pamięć USB: panel nic na niej nie zapisuje. Włóż pamięć zestawu, z której uruchomiono START.";
  else if (db.usb_problem || db.usb_error) warn.textContent = "Kopia na pamięci USB się nie zapisuje. Sprawdź, czy pamięć zestawu jest włożona; po ponownym włożeniu uruchom z niej START, a panel zapisze kopię na niej także pod nową literą dysku. Bez pamięci nowy laptop nie przejmie najnowszych danych, a „Oddaj laptop” nie zadziała.";
  if (db.disk_error) warn.textContent = "Kopia na dysku laptopa się nie zapisuje (" + db.disk_error + "). Zmiany nie są potwierdzane; zwolnij miejsce na dysku albo użyj innego laptopa.";
}

function showEnvelopes(list, intro) {
  envelopesShown = true;
  const ol = $("envelope-list");
  ol.replaceChildren(...list.map((e) => {
    const li = document.createElement("li");
    li.className = "envelope";
    const head = document.createElement("p");
    head.className = "eyebrow";
    head.textContent = (e.no ? `Koperta ${e.no} · ` : "") + e.label;
    const pw = document.createElement("p");
    pw.className = "password mono";
    pw.textContent = e.password;
    li.append(head, pw);
    return li;
  }));
  $("envelopes").querySelector(".notice-text").textContent = intro;
  $("envelopes").hidden = false;
  render();
  $("envelopes").scrollIntoView();
}

function envelopesDone() {
  if (!confirm("Czy każde hasło jest w kopercie o swoim numerze? Panel nie pokaże ich ponownie.")) return;
  $("envelope-list").replaceChildren();
  $("envelopes").hidden = true;
  envelopesShown = false;
  render();
}

async function kitCreate() {
  const n = Number($("kit-deputies").value);
  if (!confirm(`Utworzyć konto gospodarza, ${n} ${n === 1 ? "konto zastępcy" : "konta zastępców"} i hasło odtworzenia na tej pamięci USB?`)) return;
  await busy($("kit-create"), async () => {
    const r = await api("/api/kit/create", { deputies: n });
    if (!r.ok) return toast(r.data.error || "Nie udało się utworzyć kont.");
    showEnvelopes(r.data.envelopes, "Hasła widać tylko teraz. Przepisz każde do koperty o tym numerze albo wydrukuj tę stronę, a potem zaklej koperty. Hasło odtworzenia otwiera kopię bazy, gdy plik kont zginie.");
  });
}

async function login(event) {
  event.preventDefault();
  await busy($("login-send"), async () => {
    const r = await api("/api/login", { account: $("login-account").value, password: $("login-password").value });
    $("login-error").textContent = r.ok || r.data.code === "conflict" ? "" : (r.data.error || "Nie udało się zalogować.");
    if (r.ok || r.data.code === "conflict") $("login-password").value = "";
  });
}

async function recover(event) {
  event.preventDefault();
  await busy($("recover-send"), async () => {
    const r = await api("/api/recover", { password: $("recover-password").value, deputies: Number($("recover-deputies").value) });
    $("recover-error").textContent = r.ok ? "" : (r.data.error || "Nie udało się otworzyć kopii.");
    if (!r.ok) return;
    $("recover-password").value = "";
    showEnvelopes(r.data.envelopes, "Kopia bazy jest otwarta, a konta są nowe. Stare koperty zniszcz. Przepisz nowe hasła do kopert o tych numerach albo wydrukuj tę stronę; nowe hasło odtworzenia zastępuje użyte.");
  });
}

async function choose(prefer) {
  const other = prefer === "disk" ? "z pamięci USB" : "z dysku";
  if (!confirm(`Pracować dalej z wybraną kopią? Kopia ${other} zostanie zapisana na pamięci USB jako plik „konflikt” i nie będzie widoczna w panelu.`)) return;
  const r = await api("/api/copy/choose", { prefer });
  if (!r.ok) toast(r.data.error || "Nie udało się otworzyć kopii.");
}

async function newPassword() {
  const sel = $("kit-account");
  const name = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent : "";
  if (!confirm(`Nadać nowe hasło kontu „${name}”? Stare hasło przestanie działać.`)) return;
  await busy($("kit-password"), async () => {
    const r = await api("/api/password/new", { account: sel.value });
    if (!r.ok) return toast(r.data.error || "Nie udało się zmienić hasła.");
    showEnvelopes(r.data.envelopes, "Nowe hasło widać tylko teraz. Włóż je do nowej koperty z numerem otwartej koperty i zaklej ją.");
  });
}

async function logout() {
  const r = await api("/api/logout");
  if (!r.ok) toast(r.data.error || "Wylogowano, ale ostatnia kopia nie trafiła na pamięć USB.");
}

const DESTROY_STATION = {
  pending: () => "Sprawdzam, czy stacja jest podłączona…",
  absent: () => "Stacja nie była podłączona. Zniszcz dane na stacji: STAN → USŁUGI → ZNISZCZ DANE, potem GÓRA, DÓŁ, GÓRA, OK.",
  asking: () => "Wysyłam polecenie do stacji…",
  confirm: (d) => `Stacja pyta o zniszczenie danych: naciśnij na niej OK w ciągu ${d.confirm_s || 30} s.`,
  ok: () => "Stacja zniszczyła swoje dane i uruchomiła się bez konfiguracji.",
  refused: (d) => `Stacja nie zniszczyła danych: ${d.message || "brak odpowiedzi stacji."} Zniszcz je na stacji: STAN → USŁUGI → ZNISZCZ DANE.`,
};

async function destroyData() {
  if (!confirm("ZNISZCZYĆ DANE? Tylko przy groźbie przejęcia stacji albo laptopa. Laptop usunie dane zestawu z dysku i z pamięci USB, a podłączona stacja po potwierdzeniu przyciskiem OK usunie swoje dane i uruchomi się bez konfiguracji. Ponowne użycie wymaga przygotowania stacji.")) return;
  if (!confirm("To nieodwracalne. Na pewno zniszczyć dane?")) return;
  await busy($("destroy"), async () => {
    const r = await api("/api/destroy", { confirm: "ZNISZCZ" });
    if (!r.ok) toast(r.data.error || "Nie udało się usunąć wszystkich plików. Zniszcz pamięć USB fizycznie.", 12000);
  });
}

async function handBack() {
  if (!confirm("Oddać laptop? Aplikacja zapisze ostatnią kopię na pamięci USB, usunie dane zestawu z dysku tego laptopa i zakończy pracę. Stacja pracuje dalej.")) return;
  await busy($("hand-back"), async () => {
    const r = await api("/api/hand-back");
    if (!r.ok) return toast(r.data.error || "Nie udało się zapisać kopii na pamięci USB; dane zostają na dysku.", 9000);
    stopped = true;
    setOffline("Kopia jest na pamięci USB, a dane zestawu zniknęły z dysku tego laptopa. Wyjmij pamięć USB i oddaj laptop. Możesz zamknąć tę kartę.");
    setPill("pill-wait", "Laptop oddany");
  });
}

const OPS = {
  configure: "Wysłanie konfiguracji", config_get: "Odczyt konfiguracji", card: "Odczyt karty", selftest: "Autotest",
  kit_create: "Utworzenie kont zestawu", kit_recover: "Nowe konta po haśle odtworzenia", login: "Logowanie",
  logout: "Wylogowanie", password_new: "Nowe hasło do koperty", hand_back: "Oddanie laptopa", copy_choose: "Wybór kopii bazy",
  usb_moved: "Pamięć USB pod nową ścieżką",
};
const ACCOUNT_OPS = new Set(["login", "logout", "password_new", "hand_back"]);

function accountLabel(id) {
  const a = (session().accounts || []).find((x) => x.id === id);
  return a ? a.label : id;
}

function renderJournal() {
  const body = $("journal");
  const rows = (state.journal || []).map((e) => {
    const tr = document.createElement("tr");
    const when = new Date(e.at);
    const detail = ACCOUNT_OPS.has(e.op) ? accountLabel(e.detail) : e.op === "copy_choose" ? (e.detail === "disk" ? "z dysku" : "z pamięci USB") : e.detail;
    const cells = [isNaN(when) ? e.at : when.toLocaleString("pl-PL"), e.station || "–", OPS[e.op] || e.op,
      (e.ok ? "✓ " : "✗ ") + (detail || "")];
    cells.forEach((text, i) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 1) td.className = "mono";
      if (i === 3) td.className = e.ok ? "ok" : "fail";
      tr.appendChild(td);
    });
    return tr;
  });
  body.replaceChildren(...rows);
  $("journal-empty").hidden = rows.length > 0;
}

// ---- Formularz konfiguracji -----------------------------------------------------------------

function counter(input, max) {
  const c = document.createElement("span");
  c.className = "count";
  const update = () => {
    const n = bytes(input.value);
    c.textContent = `${n} / ${max} B`;
    c.classList.toggle("over", n > max);
  };
  input.addEventListener("input", update);
  update();
  return c;
}

function removeButton(label, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "remove";
  b.textContent = "✕";
  b.setAttribute("aria-label", label);
  b.addEventListener("click", onClick);
  return b;
}

function addAddress(value) {
  if (!limits) return;                  // formularz powstaje dopiero z limitami z aplikacji
  const list = $("addresses");
  if (list.children.length >= limits.addresses) return toast(`Najwyżej ${limits.addresses} adresów.`);
  const row = document.createElement("div");
  row.className = "row";
  const cell = document.createElement("div");
  cell.className = "cell";
  const input = document.createElement("input");
  input.value = value || "";
  input.maxLength = 80;
  input.placeholder = "np. Szkoła Podstawowa nr 2, ul. Szkolna 4, wejście B";
  const err = document.createElement("p");
  err.className = "field-error";
  cell.append(input, counter(input, limits.address), err);
  row.append(cell, removeButton("Usuń adres", () => { row.remove(); renumber(); changed(); }));
  list.appendChild(row);
  renumber();
}

function addPhrase(values) {
  if (!limits) return;
  const list = $("phrases");
  if (list.children.length >= limits.phrases) return toast(`Najwyżej ${limits.phrases} fraz.`);
  const row = document.createElement("div");
  row.className = "row row-phrase";
  LANGS.forEach((lang, i) => {
    const cell = document.createElement("div");
    cell.className = "cell";
    const label = document.createElement("label");
    label.className = "lang";
    label.textContent = lang + (i === 0 ? " (do zgłoszenia)" : "");
    const input = document.createElement("input");
    input.value = (values && values[i]) || "";
    input.maxLength = 120;
    input.setAttribute("aria-label", `Fraza, wersja ${lang}`);
    const err = document.createElement("p");
    err.className = "field-error";
    cell.append(label, input, counter(input, limits.phrase), err);
    row.appendChild(cell);
  });
  row.appendChild(removeButton("Usuń frazę", () => { row.remove(); renumber(); changed(); }));
  list.appendChild(row);
  renumber();
}

// Nazwy pól po usunięciu wiersza: addresses.N, phrases.N.L (takie same jak w odpowiedzi sprawdzenia).
function renumber() {
  [...$("addresses").children].forEach((row, i) => {
    const input = row.querySelector("input");
    input.dataset.field = `addresses.${i}`;
    input.setAttribute("aria-label", i === 0 ? "Adres domyślny" : `Adres ${i + 1}`);
    row.querySelector(".field-error").dataset.error = `addresses.${i}`;
  });
  [...$("phrases").children].forEach((row, i) => {
    row.querySelectorAll("input").forEach((input, l) => { input.dataset.field = `phrases.${i}.${l}`; });
    row.querySelectorAll(".field-error").forEach((e, l) => { e.dataset.error = `phrases.${i}.${l}`; });
  });
}

const field = (name) => document.querySelector(`[name="${name}"]`);

function role() { return document.querySelector('input[name="role"]:checked').value; }

function readForm() {
  const r = role();
  const doc = { role: r, ifac: field("ifac").value, radio: { profile: field("radio").value } };
  if (r === "stacja") {
    doc.addresses = [...$("addresses").querySelectorAll("input")].map((i) => i.value);
    const n = field("stations").value.trim();
    doc.stations = n === "" ? null : Number(n);
    doc.phrases = [...$("phrases").children].map((row) => [...row.querySelectorAll("input")].map((i) => i.value));
    doc.receiver = {};
    for (const w of ["main", "backup"]) {
      doc.receiver[w] = { lxmf: field(`receiver.${w}.lxmf`).value, key: field(`receiver.${w}.key`).value };
    }
  }
  return doc;
}

function fillForm(doc, only) {
  const has = (k) => doc[k] !== undefined && (!only || only.includes(k));
  if (has("role")) {
    document.querySelectorAll('input[name="role"]').forEach((i) => { i.checked = i.value === doc.role; });
  }
  if (has("addresses") && Array.isArray(doc.addresses)) {
    $("addresses").replaceChildren();
    (doc.addresses.length ? doc.addresses : [""]).forEach((a) => addAddress(a));
  }
  if (has("phrases") && Array.isArray(doc.phrases)) {
    $("phrases").replaceChildren();
    doc.phrases.forEach((p) => addPhrase(p));
  }
  if (has("stations")) field("stations").value = doc.stations == null ? "" : doc.stations;
  if (has("ifac")) field("ifac").value = doc.ifac || "";
  if (has("radio") && doc.radio && doc.radio.profile) field("radio").value = doc.radio.profile;
  if (has("receiver") && doc.receiver) {
    for (const w of ["main", "backup"]) {
      const c = doc.receiver[w] || {};
      field(`receiver.${w}.lxmf`).value = c.lxmf || "";
      field(`receiver.${w}.key`).value = c.key || "";
    }
  }
  roleChanged();
  showAll = true;
  changed();
}

function roleChanged() {
  const station = role() === "stacja";
  document.querySelectorAll(".only-station").forEach((el) => { el.hidden = !station; });
  document.querySelectorAll(".choice").forEach((el) => el.classList.toggle("on", el.querySelector("input").checked));
}

function changed() {
  $("result").hidden = true;
  clearTimeout(checkTimer);
  checkTimer = setTimeout(check, 250);
}

async function check() {
  const seq = ++checkSeq;
  const entered = readForm();
  let r;
  try { r = await api("/api/config/check", { doc: entered }); } catch (e) { return null; }
  if (seq !== checkSeq || !r.ok || JSON.stringify(entered) !== JSON.stringify(readForm())) return null;
  showProblems(r.data.problems);
  $("doc-size").textContent = r.data.size != null
    ? `Konfiguracja: ${r.data.size.toLocaleString("pl-PL")} B z ${r.data.max.toLocaleString("pl-PL")} B`
    : `Do poprawienia: ${r.data.problems.length}`;
  return r.data;
}

function showProblems(problems) {
  document.querySelectorAll(".bad").forEach((el) => { el.classList.remove("bad"); el.removeAttribute("aria-invalid"); });
  document.querySelectorAll("[data-error]").forEach((el) => { el.textContent = ""; });
  for (const p of problems) {
    const el = document.querySelector(`[data-field="${p.field}"]`);
    const visible = showAll || (el && el.dataset.touched);
    if (!visible) continue;
    if (el) { el.classList.add("bad"); el.setAttribute("aria-invalid", "true"); }
    let key = p.field, box = null;
    while (key && !(box = document.querySelector(`[data-error="${key}"]`))) key = key.split(".").slice(0, -1).join(".");
    if (box && !box.textContent) box.textContent = p.message;
  }
}

// ---- Czynności ------------------------------------------------------------------------------

function toast(text, ms) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, ms || 5000);
}

async function busy(button, fn) {
  if (button.getAttribute("aria-busy") === "true") return;
  button.setAttribute("aria-busy", "true");
  try {
    return await fn();
  } catch (e) {
    toast("Aplikacja WICI nie odpowiedziała. Sprawdź, czy działa, i spróbuj ponownie.");
  } finally {
    button.removeAttribute("aria-busy");
  }
}

function needStation(withPrep) {
  if (!loggedIn()) { toast("Najpierw zaloguj się hasłem z koperty."); return false; }
  if (!connected()) { toast("Najpierw podłącz stację przewodem USB."); return false; }
  if (withPrep && !prepMode()) { toast("Włącz tryb przygotowania: przytrzymaj przycisk pod naklejką serwisową."); return false; }
  return true;
}

function showResult(ok, title, lines) {
  const box = $("result");
  box.className = "result" + (ok ? "" : " result-bad");
  const strong = document.createElement("strong");
  strong.textContent = title;
  box.replaceChildren(strong, ...lines.map((l) => { const p = document.createElement("p"); p.textContent = l; return p; }));
  box.hidden = false;
}

async function send(event) {
  event.preventDefault();
  if (!needStation(true)) return;
  const result = await checkedConfig();
  if (!result) return;
  const s = station(), h = s.hello || {}, st = s.status || {};
  const doc = result.doc, replaced = configured();
  if (replaced && !confirm(`Zastąpić konfigurację stacji ${h.name || ""}? Poprzednia konfiguracja nie zostanie zachowana.`)) return;
  const roleChange = replaced && (st.role || h.role) && (st.role || h.role) !== doc.role;
  await busy($("send"), async () => {
    const r = await api("/api/config/write", { doc });
    if (!r.ok) return showResult(false, "Stacja nie przyjęła konfiguracji", [r.data.error || `Błąd ${r.status}`]);
    const lines = [`Konfiguracja nr ${r.data.config_seq}, skrót SHA-256 ${r.data.sha256.slice(0, 16)}…`];
    if (doc.role === "stacja" && r.data.worst_request != null) {
      lines.push(`Najdłuższe zgłoszenie z przycisków: ${r.data.worst_request} B z ${limits.message} B.`);
    }
    if (roleChange) lines.push("Zmieniła się rola, więc stacja uruchomi się ponownie. Panel połączy się sam.");
    lines.push("Wyłącz tryb przygotowania tym samym przyciskiem, gdy skończysz.");
    showResult(true, `Zapisano w stacji ${h.name || ""}`, lines);
  });
}

async function readConfig() {
  if (!needStation(true)) return;
  await busy($("read-config"), async () => {
    const r = await api("/api/config/read");
    if (!r.ok) return toast(r.data.error || "Nie udało się odczytać konfiguracji.");
    fillForm(r.data.doc);
    toast("Wczytano konfigurację ze stacji.");
  });
}

let fileMode = "config";

function pickFile(mode) {
  fileMode = mode;
  $("file").value = "";
  $("file").click();
}

async function fileChosen() {
  const f = $("file").files[0];
  if (!f) return;
  if (f.size > 64 * 1024) return toast("Plik jest za duży jak na konfigurację WICI.");
  let doc;
  try { doc = JSON.parse(await f.text()); } catch (e) { return toast("To nie jest plik JSON."); }
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return toast("Plik nie zawiera konfiguracji WICI.");
  if (doc.fingerprint && doc.key && doc.name) return toast("To jest karta stacji, nie konfiguracja ani karta odbiorcy.");
  if (doc.main && doc.backup) doc = { receiver: { main: doc.main, backup: doc.backup } };
  if (fileMode === "receiver") {
    if (!doc.receiver) return toast("Plik nie zawiera karty odbiorcy.");
    fillForm(doc, ["receiver"]);
    return toast("Wczytano kartę odbiorcy.");
  }
  const known = ["role", "addresses", "receiver", "stations", "phrases", "ifac", "radio"].filter((k) => k in doc);
  if (!known.length) return toast("Plik nie zawiera pól konfiguracji WICI.");
  fillForm(doc, known);
  toast(`Wczytano z pliku: ${f.name}`);
}

function download(name, value) {
  const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function today() { return new Date().toISOString().slice(0, 10); }

// Eksport i wysyłka zatwierdzają tę samą konfigurację. Zmieniony tekst najpierw wraca
// do formularza; dopiero ponowne kliknięcie zatwierdza postać widoczną dla operatora.
async function checkedConfig() {
  showAll = true;
  clearTimeout(checkTimer);
  const result = await check();
  if (!result) { toast("Nie udało się sprawdzić konfiguracji. Spróbuj ponownie."); return null; }
  const entered = readForm(), doc = result.doc, changedTexts = [];
  if (doc && doc.role === "stacja") {
    (doc.addresses || []).forEach((text, i) => {
      if (text !== (entered.addresses || [])[i]) changedTexts.push(`Adres ${i + 1}: ${text}`);
    });
    (doc.phrases || []).forEach((phrase, i) => phrase.forEach((text, l) => {
      if (text !== ((entered.phrases || [])[i] || [])[l]) changedTexts.push(`Fraza ${i + 1}, ${LANGS[l]}: ${text}`);
    }));
  }
  if (changedTexts.length) {
    fillForm(doc);
    showProblems(result.problems);
    showResult(true, "Sprawdź poprawioną postać tekstu", [
      "Formularz pokazuje teraz tekst po ujednoliceniu odstępów i znaków. Sprawdź go, popraw ewentualne błędy i ponownie wybierz zapis do pliku albo wysłanie do stacji.",
      ...changedTexts,
    ]);
    toast("Zmieniono postać tekstu. Sprawdź formularz przed zapisem.", 7000);
    return null;
  }
  if (result.problems.length) {
    const first = document.querySelector(".bad");
    if (first) first.focus();
    toast("Popraw zaznaczone pola.");
    return null;
  }
  return result;
}

async function saveFile() {
  const result = await checkedConfig();
  if (!result) return;
  const name = (station().hello || {}).name || "siec";
  download(`wici-konfiguracja-${name}-${today()}.json`, result.doc);
  toast("Zapisano plik. Zawiera kod dostępu sieci: przechowuj go jak hasło.", 7000);
}

async function newIfac() {
  if (field("ifac").value && !confirm("Nowy kod tworzy nową sieć: stacje z innym kodem przestaną się słyszeć. Użyć nowego kodu?")) return;
  const r = await api("/api/ifac/new");
  if (r.ok) {
    field("ifac").value = r.data.ifac;
    field("ifac").dataset.touched = "1";
    changed();
  }
}

async function readCard() {
  if (!needStation(true)) return;
  await busy($("read-card"), async () => {
    const r = await api("/api/card");
    if (!r.ok) return toast(r.data.error || "Nie udało się odczytać karty.");
    lastCard = r.data.card;
    $("card-fp").textContent = lastCard.fingerprint || "";
    $("card-name").textContent = lastCard.name || "";
    $("card-lxmf").textContent = lastCard.lxmf || "";
    $("card-address").textContent = (lastCard.address || []).join(" · ");
    $("card-key").textContent = lastCard.key || "";
    $("card-view").hidden = false;
  });
}

function selectTab(id) {
  document.querySelectorAll('[role="tab"]').forEach((t) => {
    const on = t.id === id;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
  });
  showTabs();
}

// Zakładka widoczna, gdy wybrana, ktoś jest zalogowany i nie ma haseł do kopert na ekranie.
function showTabs() {
  document.querySelectorAll('[role="tab"]').forEach((t) => {
    $(t.getAttribute("aria-controls")).hidden = t.getAttribute("aria-selected") !== "true" || !loggedIn() || envelopesShown;
  });
}

const ENVELOPES_OPEN = "Hasła do kopert są na ekranie i panel nie pokaże ich ponownie. ";

async function quit() {
  if (!confirm((envelopesShown ? ENVELOPES_OPEN : "") + "Zakończyć aplikację WICI? Stacja pracuje dalej bez laptopa.")) return;
  stopped = true;
  let r = null;
  try { r = await api("/api/quit"); } catch (e) { /* aplikacja już się zamyka */ }
  const lost = r && r.data.usb_error ? ` Ostatnia kopia nie trafiła na pamięć USB (${r.data.usb_error}): jest na dysku tego laptopa, a następny START z pamięci zestawu ją przejmie.` : "";
  setOffline("Aplikacja WICI została zakończona." + lost + " Możesz zamknąć tę kartę przeglądarki.");
  setPill("pill-wait", "Zakończono");
}

// ---- Start ------------------------------------------------------------------------------------

function initForm() {
  addAddress("");
  roleChanged();
  check();
}

function init() {
  const form = $("form");
  form.addEventListener("input", (e) => { if (e.target.dataset) e.target.dataset.touched = "1"; changed(); });
  form.addEventListener("change", (e) => {
    if (e.target.name === "role") roleChanged();
    if (e.target.dataset) e.target.dataset.touched = "1";
    changed();
  });
  form.addEventListener("submit", send);
  $("add-address").addEventListener("click", () => { addAddress(""); changed(); });
  $("add-phrase").addEventListener("click", () => { addPhrase(["", "", ""]); changed(); });
  $("read-config").addEventListener("click", readConfig);
  $("load-file").addEventListener("click", () => pickFile("config"));
  $("load-receiver").addEventListener("click", () => pickFile("receiver"));
  $("save-file").addEventListener("click", saveFile);
  $("new-ifac").addEventListener("click", newIfac);
  $("file").addEventListener("change", fileChosen);
  $("read-card").addEventListener("click", readCard);
  $("save-card").addEventListener("click", () => { if (lastCard) download(`${lastCard.name || "WICI"}-karta.json`, lastCard); });
  $("quit").addEventListener("click", quit);
  $("kit-create").addEventListener("click", kitCreate);
  $("login-form").addEventListener("submit", login);
  $("recover-form").addEventListener("submit", recover);
  $("choose-disk").addEventListener("click", () => choose("disk"));
  $("choose-usb").addEventListener("click", () => choose("usb"));
  $("envelopes-print").addEventListener("click", () => window.print());
  $("envelopes-done").addEventListener("click", envelopesDone);
  $("kit-password").addEventListener("click", newPassword);
  $("logout").addEventListener("click", logout);
  $("hand-back").addEventListener("click", handBack);
  $("destroy").addEventListener("click", destroyData);
  $("rescan").addEventListener("click", () => busy($("rescan"), async () => {
    await api("/api/rescan");
    toast("Szukam stacji na wszystkich portach USB.");
  }));
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => selectTab(t.id));
    t.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!d) return;
      const next = tabs[(i + d + tabs.length) % tabs.length];
      selectTab(next.id);
      next.focus();
    });
  });
  // Zamknięcie karty albo odświeżenie z hasłami na ekranie: przeglądarka pyta, bo haseł nie da się pokazać ponownie.
  window.addEventListener("beforeunload", (e) => { if (envelopesShown && !stopped) { e.preventDefault(); e.returnValue = ""; } });
  selectTab("tab-config");
  poll();
}

document.addEventListener("DOMContentLoaded", init);

// SPDX-License-Identifier: MIT
// Panel dyżurnego stanowiska odbiorczego (wici/stanowisko/panel.py). Bez bibliotek; treść tylko przez textContent.
"use strict";

var CATEGORIES = ["POMOC MEDYCZNA", "LEKI I SPRZĘT MED.", "EWAKUACJA, TRANSPORT", "WODA PITNA", "ŻYWNOŚĆ",
  "OGRZEWANIE, ENERGIA", "SANITARNE, HIGIENA", "ZAGROŻENIE BUDYNKU", "POSZUKIWANIE, INFO", "INNE"];
var URGENCY = ["zwykła", "pilna", "NATYCHMIAST"];
var STATES = {1: "przyjęte", 2: "przeczytane", 3: "pomoc skierowana", 4: "przekazane dalej", 5: "instrukcja wysłana", 6: "zamknięte"};
var TABS = [["reports", "Zgłoszenia"], ["tests", "TEST"], ["quarantine", "Kwarantanna"], ["stations", "Stacje"],
  ["node", "Węzeł i wysyłka"], ["handover", "Przekazanie zmiany"], ["accounts", "Hasła"], ["log", "Dziennik"]];
var state = null, version = -1, tab = "reports", silenced = {}, lastTouch = 0, audio = null;

function el(tag, attrs) {
  var node = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (k === "text") node.textContent = attrs[k];
    else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), attrs[k]);
    else node.setAttribute(k, attrs[k]);
  });
  for (var i = 2; i < arguments.length; i++) if (arguments[i]) node.appendChild(arguments[i]);
  return node;
}
function $(id) { return document.getElementById(id); }
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
function time(s) { return s ? new Date(s * 1000).toLocaleString("pl-PL") : "—"; }
function ago(s) { return s == null ? "—" : s < 120 ? Math.round(s) + " s" : Math.round(s / 60) + " min"; }

function post(path, body) {
  return fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})})
    .then(function (r) { return r.json().then(function (v) { if (!r.ok) throw new Error(v.error || r.status); return v; }); });
}
function action(path, body, errorNode) {
  if (errorNode) errorNode.textContent = "";
  return post(path, body).then(function (v) { force = true; return v; }).catch(function (e) { if (errorNode) errorNode.textContent = e.message; else alert(e.message); throw e; });
}

// Aktywność przesuwa blokadę po 5 min; serwer i tak liczy czas od ostatniego żądania.
["keydown", "click"].forEach(function (name) {
  document.addEventListener(name, function () {
    if (state && state.user && Date.now() - lastTouch > 30000) { lastTouch = Date.now(); post("/api/operator/touch").catch(function () {}); }
  });
});

function beep() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    var o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = 880; g.gain.value = 0.2; o.connect(g); g.connect(audio.destination);
    o.start(); o.stop(audio.currentTime + 0.4);
  } catch (e) { /* bez dźwięku przeglądarka nadal pokazuje alarm */ }
}
setInterval(function () { if (alarms().length) beep(); }, 2000);
function alarms() {
  return state && state.reports ? state.reports.filter(function (r) { return r.urgency === 2 && r.state === 1 && !silenced[r.id]; }) : [];
}

function poll() {
  fetch("/api/operator/queue?v=" + version).then(function (r) { return r.json(); }).then(function (v) {
    var changed = v.v !== version;
    state = v; version = v.v;
    if (changed || pending) render();
    poll();
  }).catch(function () { setTimeout(poll, 2000); });
}

// Widok nie przerysowuje się pod ręką: pole w trakcie wpisywania albo otwarty formularz czekają na koniec.
var pending = false;
function busy() {
  var a = document.activeElement, view = $("view");
  return view.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName) || !!view.querySelector("details[open]");
}
document.addEventListener("focusout", function () { setTimeout(function () { if (pending && !busy()) render(); }, 0); });
document.addEventListener("toggle", function () { if (pending && !busy()) render(); }, true);

function render() {
  $("login").hidden = !!state.user;
  $("work").hidden = !state.user;
  $("recovery").hidden = !(state.user && state.recovery);
  $("recovery-clock").textContent = new Date().toLocaleString("pl-PL");
  var select = $("login-account");
  if (select.options.length !== state.accounts.length) {
    clear(select);
    state.accounts.forEach(function (a) { select.appendChild(el("option", {value: a, text: a})); });
  }
  clear($("who"));
  clear($("badges"));
  if (!state.user) return;
  $("who").appendChild(el("span", {text: state.user + " "}));
  $("who").appendChild(el("button", {text: "Wyloguj", onclick: function () { action("/api/operator/logout"); }}));
  badge(state.saved ? "zapis na nośniku: OK" : "ZAPIS NA NOŚNIKU NIE DZIAŁA", state.saved);
  badge(state.node.online ? "stacja połączona" : "BRAK STACJI", state.node.online);
  if (alarms().length) {
    $("badges").appendChild(el("button", {class: "alarm", text: "Wycisz alarm (" + alarms().length + ")", onclick: function () {
      alarms().forEach(function (r) { silenced[r.id] = true; }); render(); }}));
  }
  var nav = clear($("tabs"));
  TABS.forEach(function (t) {
    var count = t[0] === "quarantine" ? state.quarantine.length + state.removed.length : t[0] === "tests" ? state.tests.filter(function (x) { return x.state === 1; }).length : 0;
    nav.appendChild(el("button", {class: t[0] === tab ? "on" : "", text: t[1] + (count ? " (" + count + ")" : ""),
      onclick: function () { tab = t[0]; force = true; render(); }}));
  });
  if (busy() && !force) { pending = true; return; }
  pending = force = false;
  var view = clear($("view"));
  VIEWS[tab](view);
}
var force = false;
function badge(text, ok) { $("badges").appendChild(el("span", {class: ok ? "ok" : "bad", text: text})); }

function reportRow(r, withActions) {
  var row = el("div", {class: "report u" + r.urgency + " s" + r.state});
  row.appendChild(el("div", {class: "head", text: r.number + " · " + r.station + " · " + CATEGORIES[r.category] + " · osób: " + r.people +
    " · " + URGENCY[r.urgency] + " · " + time(r.at) + " · rew. " + r.revision}));
  row.appendChild(el("div", {class: "addr", text: r.address}));
  if (r.text) row.appendChild(el("div", {class: "text", text: r.text}));
  row.appendChild(el("div", {class: "state", text: "Stan: " + STATES[r.state] + (r.reply ? " · odpowiedź wysłana" : "")}));
  r.decisions.forEach(function (d) {
    row.appendChild(el("div", {class: "decision", text: "stan " + d.state + ": " + Object.keys(d.detail).map(function (k) { return k + " " + d.detail[k]; }).join(", ") + " (" + d.account + ")"}));
  });
  if (withActions) row.appendChild(decisionForm(r));
  return row;
}

function decisionForm(r) {
  var box = el("div", {class: "actions"}), error = el("p", {class: "error"});
  var key = {source: r.source, id: r.id, revision: r.revision};
  function send(extra) { return action("/api/operator/status", Object.assign({}, key, extra), error); }
  if (r.state === 1) box.appendChild(el("button", {class: "primary", text: "PRZECZYTANE", onclick: function () { send({state: 2}); }}));
  var fields = {};
  function input(name, label) { fields[name] = el("input", {placeholder: label}); return fields[name]; }
  function values(names) { var v = {}; names.forEach(function (n) { v[n] = fields[n].value; }); return v; }
  var three = el("details", {}, el("summary", {text: "Stan 3: pomoc skierowana"}),
    input("podmiot", "podmiot dysponujący siłami"), input("funkcja", "funkcja osoby"), input("kanal", "kanał"), input("czas", "czas potwierdzenia"),
    el("button", {text: "Wyślij stan 3", onclick: function () { send(Object.assign({state: 3}, values(["podmiot", "funkcja", "kanal", "czas"]))); }}));
  var four = el("details", {}, el("summary", {text: "Stan 4: przekazane dalej"}),
    input("adresat", "komu przekazano"), input("czas4", "kiedy"),
    el("button", {text: "Wyślij stan 4", onclick: function () { send({state: 4, adresat: fields.adresat.value, czas: fields.czas4.value}); }}));
  var text = el("input", {placeholder: "instrukcja dla schronienia (do 96 bajtów)", maxlength: "96"});
  var five = el("details", {}, el("summary", {text: "Odpowiedź REPLY / stan 5"}), text,
    el("button", {text: "Wyślij odpowiedź", onclick: function () { action("/api/operator/reply", Object.assign({text: text.value}, key), error); }}),
    el("button", {text: "Odpowiedź i stan 5", onclick: function () { send({state: 5, reply: text.value}); }}));
  box.appendChild(three); box.appendChild(four); box.appendChild(five);
  box.appendChild(el("button", {text: "Stan 6: zamknięte", onclick: function () { if (confirm("Zamknąć zgłoszenie " + r.number + "?")) send({state: 6}); }}));
  box.appendChild(error);
  return box;
}

function secondPerson() {
  var account = el("select", {});
  state.accounts.filter(function (a) { return a !== state.user; }).forEach(function (a) { account.appendChild(el("option", {value: a, text: a})); });
  var password = el("input", {type: "password", placeholder: "hasło drugiego dyżurnego", autocomplete: "off"});
  return {node: el("div", {class: "second"}, el("span", {text: "Zgoda drugiego dyżurnego: "}), account, password),
    values: function () { return {account2: account.value, password2: password.value}; }};
}

var VIEWS = {
  reports: function (view) {
    if (!state.reports.length) view.appendChild(el("p", {text: "Brak zgłoszeń."}));
    state.reports.forEach(function (r) { view.appendChild(reportRow(r, true)); });
  },
  tests: function (view) {
    var marks = [], error = el("p", {class: "error"});
    view.appendChild(el("p", {text: "TEST nie są potrzebami. Sprawdź adres każdego, zaznacz i potwierdź PRZECZYTANE."}));
    state.tests.forEach(function (t) {
      var box = el("input", {type: "checkbox"});
      if (t.state === 1) marks.push([box, t]);
      view.appendChild(el("label", {class: "test"}, t.state === 1 ? box : null,
        el("span", {text: " " + t.station + " · " + t.address + " · " + time(t.at) + " · " + STATES[t.state]})));
    });
    view.appendChild(el("button", {class: "primary", text: "Potwierdź zaznaczone", onclick: function () {
      var items = marks.filter(function (m) { return m[0].checked; }).map(function (m) { return {source: m[1].source, id: m[1].id, revision: m[1].revision}; });
      action("/api/operator/tests", {items: items}, error);
    }}));
    view.appendChild(error);
  },
  quarantine: function (view) {
    state.removed.forEach(function (s) {
      view.appendChild(el("p", {class: "alarm", text: "MOŻLIWE PRZEJĘCIE STACJI " + s.station + ": " + s.messages + " wiadomości od usuniętej stacji"}));
    });
    if (!state.quarantine.length) view.appendChild(el("p", {text: "Kwarantanna pusta."}));
    state.quarantine.forEach(function (q) {
      var c = q.content, error = el("p", {class: "error"});
      var key = {source: q.source, id: q.id, revision: q.revision};
      view.appendChild(el("div", {class: "report"},
        el("div", {class: "head", text: "do weryfikacji · nadawca " + q.source.slice(0, 8) + " · " + q.number + " · " + (c[1] === 5 ? "TEST" : CATEGORIES[c[4]]) + " · osób: " + c[5]}),
        el("div", {class: "addr", text: c[6]}), c[7] ? el("div", {class: "text", text: c[7]}) : null,
        el("button", {text: "Zatwierdź tę wiadomość", onclick: function () { action("/api/operator/quarantine", Object.assign({decision: "approve"}, key), error); }}),
        el("button", {text: "Odrzuć", onclick: function () { action("/api/operator/quarantine", Object.assign({decision: "reject"}, key), error); }}),
        error));
    });
  },
  stations: function (view) {
    state.trusted.forEach(function (t) {
      view.appendChild(el("div", {class: "station"}, el("span", {text: t.station + " · " + t.address.join("; ") + " "}),
        el("button", {text: "Usuń z zaufanych", onclick: function () {
          if (confirm("Usunąć " + t.station + " z listy zaufanych? Jej wiadomości trafią do kwarantanny.")) action("/api/operator/trust/remove", {source: t.source});
        }})));
    });
    var card = null, error = el("p", {class: "error"}), info = el("p", {});
    var file = el("input", {type: "file", accept: ".json,application/json", onchange: function () {
      var reader = new FileReader();
      reader.onload = function () {
        try { card = JSON.parse(reader.result); info.textContent = "Karta: " + (card.name || "?") + " · " + (card.address || []).join("; "); }
        catch (e) { card = null; info.textContent = "To nie jest karta stacji."; }
      };
      reader.readAsText(file.files[0]);
    }});
    var fp = el("input", {placeholder: "odcisk z ekranu stacji (16 cyfr)"});
    var second = secondPerson();
    view.appendChild(el("h3", {text: "Dodaj stację z karty"}));
    view.appendChild(file); view.appendChild(info); view.appendChild(fp); view.appendChild(second.node);
    view.appendChild(el("button", {class: "primary", text: "Dodaj do zaufanych", onclick: function () {
      action("/api/operator/trust", Object.assign({card: card, fingerprint: fp.value}, second.values()), error);
    }}));
    view.appendChild(error);
  },
  node: function (view) {
    var n = state.node;
    [["Połączenie ze stacją", n.online ? "tak" : "NIE"], ["Od ostatniego pakietu z radia", ago(n.since_rx)],
     ["Wiadomości w drodze", n.in_flight], ["W oczekiwaniu", n.waiting], ["Najstarsza intencja", ago(n.oldest_s)]]
      .forEach(function (p) { view.appendChild(el("p", {text: p[0] + ": " + p[1]})); });
    view.appendChild(el("button", {text: "Ogłoś adres odbiorcy", onclick: function () { action("/api/operator/announce"); }}));
  },
  handover: function (view) {
    var h = state.handover, error = el("p", {class: "error"});
    [["Otwarte zgłoszenia", h.open], ["Stan 4 bez potwierdzenia skierowania pomocy", h.forwarded_unconfirmed],
     ["Niewysłane intencje", h.unsent], ["Kwarantanna", h.quarantine], ["Alarmy przejęcia stacji", h.removed_alarm],
     ["Najnowsza kopia na dysku komputera", ago(state.copy_age_s) + " temu"]]
      .forEach(function (p) { view.appendChild(el("p", {text: p[0] + ": " + p[1]})); });
    var path = el("input", {placeholder: "katalog drugiego nośnika, np. /media/drugi albo E:\\"});
    view.appendChild(path);
    view.appendChild(el("button", {text: "Kopia na drugi nośnik", onclick: function () { action("/api/operator/backup", {path: path.value}, error); }}));
    view.appendChild(el("button", {class: "primary", text: "Przekaż zmianę i wyloguj", onclick: function () {
      action("/api/operator/handover", path.value ? {path: path.value} : {}, error); }}));
    view.appendChild(error);
  },
  accounts: function (view) {
    var out = el("p", {class: "password"}), error = el("p", {class: "error"});
    view.appendChild(el("p", {text: "Nowe hasło po otwarciu koperty. Hasło pokazuje się raz: przepisz je do nowej koperty."}));
    state.accounts.concat(["stanowisko"]).forEach(function (a) {
      view.appendChild(el("button", {text: "Nowe hasło: " + a, onclick: function () {
        if (confirm("Nadać nowe hasło " + a + "? Stare przestanie działać.")) action("/api/operator/password", {account: a}, error).then(function (v) {
          out.textContent = v.account + ": " + v.password; });
      }}));
    });
    view.appendChild(out); view.appendChild(error);
  },
  log: function (view) {
    state.log.forEach(function (e) { view.appendChild(el("p", {class: "log", text: time(e.at) + " · " + (e.account || "aplikacja") + " · " + e.op + " " + e.detail})); });
  }
};

$("login-button").addEventListener("click", function () {
  action("/api/operator/login", {account: $("login-account").value, password: $("login-password").value}, $("login-error"))
    .then(function () { $("login-password").value = ""; });
});
$("recovery-button").addEventListener("click", function () {
  action("/api/operator/recovery", {clock_ok: $("recovery-clock-ok").checked, recoveries: parseInt($("recovery-n").value, 10)}, $("recovery-error"));
});
poll();

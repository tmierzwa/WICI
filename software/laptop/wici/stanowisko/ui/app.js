// SPDX-License-Identifier: MIT
// Panel dyżurnego stanowiska odbiorczego (wici/stanowisko/panel.py). Bez bibliotek; treść tylko przez textContent.
"use strict";

var CATEGORIES = ["POMOC MEDYCZNA", "LEKI I SPRZĘT MED.", "EWAKUACJA, TRANSPORT", "WODA PITNA", "ŻYWNOŚĆ",
  "OGRZEWANIE, ENERGIA", "SANITARNE, HIGIENA", "ZAGROŻENIE BUDYNKU", "POSZUKIWANIE, INFO", "INNE"];
var URGENCY = ["zwykła", "pilna", "NATYCHMIAST"];
var URGENCY_PILL = ["", "pill-warn", "pill-alarm"];
var STATES = {1: "przyjęte", 2: "przeczytane", 3: "pomoc skierowana", 4: "przekazane dalej", 5: "instrukcja wysłana", 6: "zamknięte"};
var STATE_PILL = {1: "pill-warn", 3: "pill-ok", 5: "pill-ok", 6: "pill-ok"};
var TABS = [["reports", "Zgłoszenia"], ["tests", "TEST"], ["quarantine", "Kwarantanna"], ["stations", "Stacje"], ["bulletins", "Komunikaty"],
  ["node", "Węzeł i wysyłka"], ["handover", "Przekazanie zmiany"], ["accounts", "Hasła"], ["log", "Dziennik"],
  ["closing", "Zakończenie"]];
var state = null, version = -1, tab = "reports", silenced = {}, lastTouch = 0, audio = null;
var shown = null;   // hasło pokazywane raz: zostaje nad widokiem, aż dyżurny potwierdzi przepisanie

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

// Klocki widoku: klasy z wspólnego arkusza (wici/ui/app.css) i z app.css stanowiska.
function button(text, kind, onclick) { return el("button", {type: "button", class: "btn" + (kind ? " btn-" + kind : ""), text: text, onclick: onclick}); }
function pill(text, kind) { return el("span", {class: "pill" + (kind ? " " + kind : ""), text: text}); }
function field(label, input, kind) { return el("label", {class: "field" + (kind ? " " + kind : "")}, el("span", {text: label}), input); }
function errorBox() { return el("p", {class: "field-error"}); }
function hint(text) { return el("p", {class: "hint", text: text}); }
function card(title, kind) {
  var node = el("section", {class: "card stack" + (kind ? " " + kind : "")}, title ? el("h2", {text: title}) : null);
  for (var i = 2; i < arguments.length; i++) if (arguments[i]) node.appendChild(arguments[i]);
  return node;
}
function row() {
  var node = el("div", {class: "buttons"});
  for (var i = 0; i < arguments.length; i++) if (arguments[i]) node.appendChild(arguments[i]);
  return node;
}
function grid() {
  var node = el("div", {class: "grid"});
  for (var i = 0; i < arguments.length; i++) if (arguments[i]) node.appendChild(arguments[i]);
  return node;
}
// pairs: [etykieta, wartość, "good" | "bad" | brak]
function facts(pairs) {
  var dl = el("dl", {class: "facts"});
  pairs.forEach(function (p) {
    dl.appendChild(el("div", {}, el("dt", {text: p[0]}), el("dd", {class: p[2] === "bad" ? "bad-value" : p[2] || "", text: String(p[1])})));
  });
  return dl;
}

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

// Liczba przy zakładce: sprawy czekające na dyżurnego.
function tabCount(name) {
  if (name === "reports") return state.reports.filter(function (r) { return r.state === 1; }).length;
  if (name === "quarantine") return state.quarantine.length + state.removed.length;
  if (name === "tests") return state.tests.filter(function (x) { return x.state === 1; }).length;
  return 0;
}

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
  $("who").appendChild(el("span", {class: "user", text: state.user}));
  $("who").appendChild(button("Wyloguj", "ghost", function () { action("/api/operator/logout"); }));
  badge(state.saved ? "Zapis na nośniku" : "ZAPIS NA NOŚNIKU NIE DZIAŁA", state.saved);
  badge(state.node.online ? "Stacja połączona" : "BRAK STACJI", state.node.online);
  if (state.node.info && state.node.info.silence) badge("CISZA NA WĘŹLE", false);
  if (state.silence) badge("CISZA RADIOWA (" + state.silence.organ + ", " + state.silence.kiedy + ")", false);
  if (alarms().length) {
    $("badges").appendChild(button("Wycisz alarm (" + alarms().length + ")", "alarm", function () {
      alarms().forEach(function (r) { silenced[r.id] = true; }); render(); }));
  }
  var nav = clear($("tabs"));
  TABS.forEach(function (t) {
    var count = tabCount(t[0]);
    nav.appendChild(el("button", {type: "button", role: "tab", "aria-selected": String(t[0] === tab), class: t[0] === "closing" ? "tab-end" : "",
      onclick: function () { tab = t[0]; force = true; render(); }},
      document.createTextNode(t[1]), count ? el("span", {class: "tab-count" + (t[0] === "tests" ? " quiet" : ""), text: String(count)}) : null));
  });
  if (busy() && !force) { pending = true; return; }
  pending = force = false;
  var view = clear($("view"));
  if (shown) {
    view.appendChild(el("section", {class: "card shown"}, el("p", {class: "eyebrow", text: shown.label}),
      el("p", {class: "password", text: shown.text}),
      button("Przepisane do koperty: ukryj", "primary", function () { shown = null; force = true; render(); })));
  }
  VIEWS[tab](view);
}
var force = false;
function badge(text, ok) { $("badges").appendChild(pill(text, ok ? "pill-ok" : "pill-alarm")); }

function reportRow(r, withActions) {
  var row_ = el("article", {class: "report u" + r.urgency + " s" + r.state},
    el("div", {class: "report-top"}, pill(URGENCY[r.urgency], URGENCY_PILL[r.urgency]), el("span", {class: "category", text: CATEGORIES[r.category]}),
      pill(STATES[r.state] + (r.reply ? " · odpowiedź wysłana" : ""), STATE_PILL[r.state])),
    el("div", {class: "addr", text: r.address}),
    r.text ? el("div", {class: "text", text: r.text}) : null,
    el("div", {class: "meta"}, el("span", {class: "mono", text: r.number}), el("span", {text: r.station}), el("span", {text: "osób: " + r.people}),
      el("span", {text: time(r.at)}), el("span", {text: "rew. " + r.revision})));
  if (r.decisions.length) {
    var list = el("ul", {class: "decisions"});
    r.decisions.forEach(function (d) {
      list.appendChild(el("li", {}, el("strong", {text: "Stan " + d.state + ": "}),
        el("span", {text: Object.keys(d.detail).map(function (k) { return k + " " + d.detail[k]; }).join(", ") + " (" + d.account + ")"})));
    });
    row_.appendChild(list);
  }
  if (withActions) row_.appendChild(decisionForm(r));
  return row_;
}

function fold(title) {
  var body = el("div", {class: "fold-body"});
  for (var i = 1; i < arguments.length; i++) if (arguments[i]) body.appendChild(arguments[i]);
  return el("details", {class: "fold"}, el("summary", {text: title}), body);
}

function decisionForm(r) {
  var box = el("div", {class: "report-actions"}), error = errorBox();
  var key = {source: r.source, id: r.id, revision: r.revision};
  function send(extra) { return action("/api/operator/status", Object.assign({}, key, extra), error); }
  if (r.state === 1) box.appendChild(button("PRZECZYTANE", "primary", function () { send({state: 2}); }));
  var fields = {};
  function input(name, label) { fields[name] = el("input", {}); return field(label, fields[name]); }
  function values(names) { var v = {}; names.forEach(function (n) { v[n] = fields[n].value; }); return v; }
  box.appendChild(fold("Stan 3: pomoc skierowana",
    grid(input("podmiot", "Podmiot dysponujący siłami"), input("funkcja", "Funkcja osoby"), input("kanal", "Kanał"), input("czas", "Czas potwierdzenia")),
    row(button("Wyślij stan 3", "primary", function () { send(Object.assign({state: 3}, values(["podmiot", "funkcja", "kanal", "czas"]))); }))));
  box.appendChild(fold("Stan 4: przekazane dalej",
    grid(input("adresat", "Komu przekazano"), input("czas4", "Kiedy")),
    row(button("Wyślij stan 4", "primary", function () { send({state: 4, adresat: fields.adresat.value, czas: fields.czas4.value}); }))));
  var text = el("input", {maxlength: "96"});
  box.appendChild(fold("Odpowiedź REPLY / stan 5",
    field("Instrukcja dla schronienia (do 96 bajtów)", text),
    row(button("Wyślij odpowiedź", "", function () { action("/api/operator/reply", Object.assign({text: text.value}, key), error); }),
      button("Odpowiedź i stan 5", "primary", function () { send({state: 5, reply: text.value}); }))));
  box.appendChild(button("Stan 6: zamknięte", "", function () { if (confirm("Zamknąć zgłoszenie " + r.number + "?")) send({state: 6}); }));
  box.appendChild(error);
  return box;
}

function secondPerson() {
  var account = el("select", {});
  state.accounts.filter(function (a) { return a !== state.user; }).forEach(function (a) { account.appendChild(el("option", {value: a, text: a})); });
  var password = el("input", {type: "password", autocomplete: "off"});
  return {node: grid(field("Zgoda drugiego dyżurnego: konto", account), field("Hasło drugiego dyżurnego", password)),
    values: function () { return {account2: account.value, password2: password.value}; }};
}

// Cisza radiowa wpisywana przez dyżurnego: polecenie, włączenie na węźle, odwołanie (wiersz „cisza” w rejestrze).
function silenceForm(view) {
  var s = state.silence, error = errorBox();
  var organ = el("input", {placeholder: "np. wójt gminy"}), when = el("input", {placeholder: "np. 30.10 13:50"});
  var send = el("input", {type: "checkbox"});
  send.checked = true;
  var state_ = el("select", {});
  [["polecenie", "polecenie ciszy otrzymane"], ["wlaczona", "cisza włączona na węźle"], ["odwolana", "cisza odwołana"]]
    .forEach(function (o) { state_.appendChild(el("option", {value: o[0], text: o[1]})); });
  if (s) state_.value = "odwolana";
  view.appendChild(card("Cisza radiowa", s ? "notice-alarm" : "",
    hint(s ? "Wpisana: " + s.organ + ", " + s.kiedy + " (" + s.account + ", " + time(s.at) + "). Przełącznik CISZA na węźle przestawia się ręcznie."
      : "Brak wpisanej ciszy. Polecenie ciszy wydaje i odwołuje wójt; przełącznik CISZA na węźle przestawia się ręcznie."),
    grid(field("Wpis", state_), field("Kto wydał polecenie", organ), field("Od kiedy", when)),
    el("label", {class: "check"}, send, el("span", {text: "Wyślij komunikat do wszystkich zaufanych stacji"})),
    row(button("Wpisz", "primary", function () {
      action("/api/operator/silence", {state: state_.value, organ: organ.value, kiedy: when.value, bulletin: send.checked}, error);
    })),
    error));
}

var BEARERS = {wici: "WICI-Link", reticulum: "Reticulum"};

var VIEWS = {
  reports: function (view) {
    if (!state.reports.length) view.appendChild(card(null, "", hint("Brak zgłoszeń.")));
    state.reports.forEach(function (r) { view.appendChild(reportRow(r, true)); });
  },
  tests: function (view) {
    var marks = [], error = errorBox(), list = el("div", {class: "list"});
    state.tests.forEach(function (t) {
      var box = el("input", {type: "checkbox"});
      if (t.state === 1) marks.push([box, t]);
      list.appendChild(el("label", {class: "check"}, t.state === 1 ? box : null,
        el("span", {class: "item-head"}, el("strong", {text: t.station}), el("span", {text: t.address}),
          el("span", {class: "hint", text: time(t.at)}), pill(STATES[t.state], STATE_PILL[t.state]))));
    });
    view.appendChild(card("Wiadomości TEST", "",
      hint("TEST nie są potrzebami. Sprawdź adres każdego, zaznacz i potwierdź PRZECZYTANE."),
      state.tests.length ? list : hint("Brak wiadomości TEST."),
      row(button("Potwierdź zaznaczone", "primary", function () {
        var items = marks.filter(function (m) { return m[0].checked; }).map(function (m) { return {source: m[1].source, id: m[1].id, revision: m[1].revision}; });
        action("/api/operator/tests", {items: items}, error);
      })),
      error));
  },
  quarantine: function (view) {
    state.removed.forEach(function (s) {
      view.appendChild(el("p", {class: "banner banner-alarm", text: "MOŻLIWE PRZEJĘCIE STACJI " + s.station + ": " + s.messages + " wiadomości od usuniętej stacji"}));
    });
    if (!state.quarantine.length) view.appendChild(card(null, "", hint("Kwarantanna pusta.")));
    state.quarantine.forEach(function (q) {
      var c = q.content, error = errorBox();
      var key = {source: q.source, id: q.id, revision: q.revision};
      view.appendChild(el("article", {class: "report"},
        el("div", {class: "report-top"}, pill("do weryfikacji", "pill-warn"), el("span", {class: "category", text: c[1] === 5 ? "TEST" : CATEGORIES[c[4]]})),
        el("div", {class: "addr", text: c[6]}), c[7] ? el("div", {class: "text", text: c[7]}) : null,
        el("div", {class: "meta"}, el("span", {class: "mono", text: q.number}), el("span", {text: "nadawca " + q.source.slice(0, 8)}),
          el("span", {text: "osób: " + c[5]})),
        el("div", {class: "report-actions"},
          button("Zatwierdź tę wiadomość", "primary", function () { action("/api/operator/quarantine", Object.assign({decision: "approve"}, key), error); }),
          button("Odrzuć", "", function () { action("/api/operator/quarantine", Object.assign({decision: "reject"}, key), error); }),
          error)));
    });
  },
  stations: function (view) {
    var list = el("div", {class: "list"});
    state.trusted.forEach(function (t) {
      var info = el("div", {class: "item-head"}, el("strong", {text: t.station}), el("span", {text: t.address.join("; ")}));
      var line = el("div", {class: "station"}, info);
      if (state.bearers && state.bearers.length > 1) {
        var select = el("select", {"aria-label": "Nośnik odpowiedzi dla " + t.station});
        select.appendChild(el("option", {value: "auto", text: "automatycznie"}));
        state.bearers.forEach(function (name) { select.appendChild(el("option", {value: name, text: BEARERS[name] || name})); });
        select.value = t.override || "auto";
        line.appendChild(el("div", {class: "bearer"}, el("span", {text: "Ostatni nośnik: " + (BEARERS[t.bearer] || "nieznany") + ". Odpowiedzi:"}),
          select, button("Ustaw", "", function () { action("/api/operator/bearer", {source: t.source, bearer: select.value}); })));
      }
      line.appendChild(button("Usuń z zaufanych", "quiet-danger", function () {
        if (confirm("Usunąć " + t.station + " z listy zaufanych? Jej wiadomości trafią do kwarantanny.")) action("/api/operator/trust/remove", {source: t.source});
      }));
      list.appendChild(line);
    });
    view.appendChild(card("Zaufane stacje", "", state.trusted.length ? list : hint("Brak zaufanych stacji.")));
    var card_ = null, error = errorBox(), info = hint("");
    var file = el("input", {type: "file", accept: ".json,application/json", onchange: function () {
      var reader = new FileReader();
      reader.onload = function () {
        try { card_ = JSON.parse(reader.result); info.textContent = "Karta: " + (card_.name || "?") + " · " + (card_.address || []).join("; "); }
        catch (e) { card_ = null; info.textContent = "To nie jest karta stacji."; }
      };
      reader.readAsText(file.files[0]);
    }});
    var fp = el("input", {inputmode: "numeric"});
    var second = secondPerson();
    view.appendChild(card("Dodaj stację z karty", "",
      grid(field("Plik karty stacji", file), field("Odcisk z ekranu stacji (16 cyfr)", fp)), info, second.node,
      row(button("Dodaj do zaufanych", "primary", function () {
        action("/api/operator/trust", Object.assign({card: card_, fingerprint: fp.value}, second.values()), error);
      })),
      error));
  },
  bulletins: function (view) {
    silenceForm(view);
    var text = el("input", {maxlength: "192"});
    var error = errorBox();
    view.appendChild(card("Komunikat", "",
      hint("Komunikat idzie osobno do każdej zaufanej stacji, po kolei (dla 50 stacji kilka minut)."),
      field("Treść do wszystkich zaufanych stacji (do 192 bajtów)", text),
      row(button("Wyślij komunikat", "primary", function () {
        if (confirm("Wysłać komunikat do " + state.trusted.length + " stacji?")) action("/api/operator/bulletin", {text: text.value}, error);
      })),
      error));
    if (!state.bulletins.length) return;
    var list = el("div", {class: "list"});
    state.bulletins.forEach(function (b) {
      list.appendChild(el("div", {class: "stack"},
        el("div", {class: "item-head"}, el("strong", {text: b.number}), el("span", {text: b.text})),
        el("progress", {max: String(b.total), value: String(b.done)}),
        el("div", {class: "meta"}, el("span", {text: "dostarczono " + b.done + " z " + b.total}),
          b.retrying ? el("span", {text: "ponawiane: " + b.retrying}) : null)));
    });
    view.appendChild(card("Wysłane komunikaty", "", list));
  },
  node: function (view) {
    var n = state.node, info = n.info;
    view.appendChild(card("Węzeł i wysyłka", "",
      facts([["Połączenie ze stacją", n.online ? "tak" : "NIE", n.online ? "good" : "bad"], ["Od ostatniego pakietu z radia", ago(n.since_rx)],
        ["Przełącznik CISZA węzła", !n.diagnostics ? "nieznany (brak portu diagnostyki)" : !info ? "czekam na odczyt" : info.silence ? "WŁĄCZONY" : "wyłączony",
          info && info.silence ? "bad" : ""],
        ["Radio węzła", info ? (info.radio_ok ? "sprawne" : "AWARIA") + (info.tx_wait_s ? ", dług ciszy " + ago(info.tx_wait_s) : "") : "—",
          info ? (info.radio_ok ? "good" : "bad") : ""],
        ["Wiadomości w drodze", n.in_flight], ["W oczekiwaniu", n.waiting], ["Najstarsza intencja", ago(n.oldest_s)]]),
      row(button("Ogłoś adres odbiorcy", "", function () { action("/api/operator/announce"); }))));
  },
  handover: function (view) {
    var h = state.handover, error = errorBox();
    function count(n) { return [n, n ? "bad" : "good"]; }
    var path = el("input", {placeholder: "np. /media/drugi albo E:\\"});
    view.appendChild(card("Przekazanie zmiany", "",
      facts([["Otwarte zgłoszenia", h.open], ["Stan 4 bez potwierdzenia skierowania pomocy"].concat(count(h.forwarded_unconfirmed)),
        ["Niewysłane intencje", h.unsent], ["Kwarantanna"].concat(count(h.quarantine)), ["Alarmy przejęcia stacji"].concat(count(h.removed_alarm)),
        ["Najnowsza kopia na dysku komputera", ago(state.copy_age_s) + " temu"],
        ["Cisza radiowa", state.silence ? state.silence.organ + ", " + state.silence.kiedy : "nie"],
        ["Przełącznik CISZA węzła", state.node.info ? (state.node.info.silence ? "włączony" : "wyłączony") : "nieznany"]]),
      field("Katalog drugiego nośnika", path, "narrow"),
      row(button("Kopia na drugi nośnik", "", function () { action("/api/operator/backup", {path: path.value}, error); }),
        button("Przekaż zmianę i wyloguj", "primary", function () { action("/api/operator/handover", path.value ? {path: path.value} : {}, error); })),
      error));
  },
  accounts: function (view) {
    var error = errorBox();
    var second = secondPerson();
    var buttons = row();
    state.accounts.concat(["stanowisko"]).forEach(function (a) {
      buttons.appendChild(button("Nowe hasło: " + a, "", function () {
        var body = Object.assign({account: a}, a === state.user ? {} : second.values());
        if (confirm("Nadać nowe hasło " + a + "? Stare przestanie działać.")) action("/api/operator/password", body, error).then(function (v) {
          shown = {label: "Nowe hasło: " + v.account + (v.copies_failed ? " (kopie na dysku nieprzepakowane: " + v.copies_failed + ")" : ""),
                   text: v.password}; render(); });
      }));
    });
    view.appendChild(card("Hasła", "",
      hint("Nowe hasło po otwarciu koperty. Hasło pokazuje się raz: przepisz je do nowej koperty. " +
        "Hasło innego konta i hasło stanowiska tylko za zgodą drugiego dyżurnego."),
      second.node, buttons, error));
  },
  log: function (view) {
    var body = el("tbody", {});
    state.log.forEach(function (e) {
      body.appendChild(el("tr", {}, el("td", {class: "when", text: time(e.at)}), el("td", {text: e.account || "aplikacja"}),
        el("td", {class: "mono", text: e.station}), el("td", {class: "mono", text: e.number}), el("td", {text: e.op}), el("td", {text: e.detail || ""})));
    });
    var head = el("tr", {});
    ["Czas", "Konto", "Stacja", "Numer", "Czynność", "Szczegóły"].forEach(function (h) { head.appendChild(el("th", {text: h})); });
    view.appendChild(card("Dziennik", "", hint("Ostatnie 50 wpisów, najnowsze na górze."),
      el("div", {class: "table-wrap"}, el("table", {}, el("thead", {}, head), body))));
  },
  closing: function (view) {
    var error = errorBox();
    var path = el("input", {placeholder: "puste: nośnik stanowiska"}), second = secondPerson();
    view.appendChild(card("Eksport rejestru (CSV)", "",
      hint("Plik CSV nie jest szyfrowany: zawiera treść zgłoszeń. Domyślnie trafia do katalogu eksport na nośniku stanowiska."),
      el("div", {class: "field narrow"}, field("Inny katalog (wymaga drugiego dyżurnego)", path)), second.node,
      row(button("Eksportuj rejestr", "", function () {
        action("/api/operator/export", path.value ? Object.assign({path: path.value}, second.values()) : {}, error)
          .then(function (v) { alert("Zapisano: " + v.file); });
      }))));
    if (state.closed) {
      view.appendChild(card("Zamknij zdarzenie", "", hint("Zdarzenie zamknięte " + time(state.closed) + ". Treść zgłoszeń usunięta z bazy; archiwum w katalogu eksport.")));
      if (state.copies_purged) view.appendChild(card("Usuń kopie", "", hint("Kopie usunięte " + time(state.copies_purged) + ".")));
      else {
        var who = el("input", {}), when = el("input", {});
        var other = el("input", {placeholder: "jeśli podłączony"});
        view.appendChild(card("Usuń kopie", "",
          hint("Dopiero po potwierdzeniu odbioru archiwum przez administratora danych."),
          grid(field("Kto potwierdził odbiór archiwum", who), field("Kiedy", when), field("Katalog drugiego nośnika", other)),
          row(button("Usuń kopie", "danger", function () {
            action("/api/operator/backup/purge", {kto: who.value, kiedy: when.value, path: other.value}, error)
              .then(function (v) { if (v.failed.length) alert("Nie usunięto: " + v.failed.join(", ")); });
          }))));
      }
    } else {
      var close = el("input", {autocomplete: "off"});
      view.appendChild(card("Zamknij zdarzenie", "",
        hint("Archiwum z bazą i rejestrem trafia do katalogu eksport, potem treść zgłoszeń znika z bazy. Hasło archiwum pokaże się raz: przepisz je do koperty dla administratora danych."),
        field("Na potwierdzenie wpisz: ZAMKNIJ ZDARZENIE", close, "narrow"),
        row(button("Zamknij zdarzenie", "primary", function () {
          action("/api/operator/close", {confirm: close.value}, error).then(function (v) {
            shown = {label: "Hasło archiwum " + v.file, text: v.password}; render(); });
        }))));
    }
    var destroy = el("input", {autocomplete: "off"}), copies = el("input", {placeholder: "jeśli podłączony"});
    view.appendChild(card("Zniszcz dane", "notice-alarm",
      hint("Usuwa bazę, tożsamość, konta i kopie bez archiwum; aplikacja kończy pracę. Potem oba nośniki zniszcz fizycznie według instrukcji."),
      grid(field("Na potwierdzenie wpisz: ZNISZCZ DANE", destroy), field("Katalog drugiego nośnika", copies)),
      row(button("ZNISZCZ DANE", "danger", function () {
        if (confirm("Zniszczyć dane stanowiska? Tego nie da się cofnąć.")) action("/api/operator/destroy", {confirm: destroy.value, path: copies.value}, error)
          .then(function (v) { document.body.textContent = "Dane zniszczone." + (v.failed.length ? " Nie usunięto: " + v.failed.join(", ") : ""); });
      }))));
    view.appendChild(error);
  }
};

$("login-button").addEventListener("click", function () {
  action("/api/operator/login", {account: $("login-account").value, password: $("login-password").value}, $("login-error"))
    .then(function () { $("login-password").value = ""; });
});
$("login-password").addEventListener("keydown", function (e) { if (e.key === "Enter") $("login-button").click(); });
$("recovery-button").addEventListener("click", function () {
  action("/api/operator/recovery", {clock_ok: $("recovery-clock-ok").checked, recoveries: parseInt($("recovery-n").value, 10)}, $("recovery-error"));
});
poll();

// SPDX-License-Identifier: MIT
// Ćwiczenia opiekuna według karty obsługi (docs/obsluga/karta-stacji.html) i instrukcji opiekuna
// (docs/spec/instrukcja.md), na prawdziwym oprogramowaniu stacji (sim.js). Warunki kroków sprawdzają
// tylko to, co widzi człowiek albo stanowisko odbiorcze: tekst ekranu odczytany z pikseli panelu,
// położenie przełącznika, zasilanie i zapisy aplikacji stanowiska (w tym dowody dostarczenia od stacji).
// Każde ćwiczenie ma `solution`: przykładowy przebieg, którym test_scenarios.mjs je sprawdza.

// Kreator zgłoszenia przyciskami z ekranu głównego. people: indeks listy 1, 2, 5, 10, 20, 50, 100
// albo liczba do wpisania przez INNA LICZBA (dwie cyfry, pole wstępnie 001); urgency: 0 zagrożenie życia,
// 1 pilne, 2 w ciągu doby.
export function wizard({ category, people, urgency }) {
  const presses = ["press OK", "press OK", ...Array(category).fill("press DOWN"), "press OK"];
  if (typeof people === "number" && people >= 0 && people <= 6) {
    presses.push(...Array(people).fill("press DOWN"), "press OK");
  } else {
    const [tens, ones] = [Math.floor(people.value / 10) % 10, people.value % 10];
    presses.push(...Array(7).fill("press DOWN"), "press OK", "press OK", ...Array(tens).fill("press UP"), "press OK");
    presses.push(...(ones >= 1 ? Array(ones - 1).fill("press UP") : ["press DOWN"]), "press OK");
  }
  presses.push(...Array(urgency + 1).fill("press DOWN"), "press OK");
  if (urgency === 0) presses.push("press OK");   // potwierdzenie pilności 2
  presses.push("press OK", ...Array(4).fill("press DOWN"), "press OK", "wait 3", "press BACK");
  return presses;
}

const MESSAGES = ["press OK", "press DOWN", "press OK", "wait 0.3", "press OK", "wait 0.3"];   // menu → WIADOMOŚCI → najnowsza
const up = (text) => text.toLocaleUpperCase("pl");
const shown = (o, text) => up(o.screen.lines.join(" ")).includes(up(text));
const requests = (o) => o.post.requests.filter((r) => r.type === "request");
const tests = (o) => o.post.requests.filter((r) => r.type === "test");
// Ekran pokazał tekst, a potem (przy włączonej stacji) przeszedł dalej; pusty ekran wyłączonej stacji
// nie zalicza kroku.
const seenThenGone = (o, ctx, key, text) => {
  if (shown(o, text)) ctx[key] = true;
  return !!ctx[key] && o.power && o.screen.on !== false && !shown(o, text);
};

export const SCENARIOS = [
  {
    id: "start",
    title: { pl: "Uruchomienie stacji", en: "Starting the station" },
    brief: {
      pl: "Pierwsze uruchomienie w schronieniu według strony 1 karty: włączenie, język, kontrola adresu i TEST.",
      en: "First start in a shelter, following page 1 of the card: power, language, address check and TEST.",
    },
    setup: ["post auto 1 2 0 5"],
    steps: [
      { pl: "Naciśnij WYŁĄCZNIK.", en: "Press POWER.", done: (o) => o.power && o.screen.on },
      { pl: "Wybierz język ekranu (GÓRA, DÓŁ) i zatwierdź OK.", en: "Choose the screen language (UP, DOWN) and confirm with OK.",
        done: (o, ctx) => seenThenGone(o, ctx, "lang", "ENGLISH") },
      { pl: "Sprawdź adres na ekranie. Zgadza się z tym miejscem: OK.", en: "Check the address on the screen. If it matches this place: OK.",
        done: (o, ctx) => seenThenGone(o, ctx, "address", "CZY TO TO MIEJSCE") },
      { pl: "Stacja proponuje TEST: przyjmij go (OK).", en: "The station offers a TEST: accept it (OK).",
        done: (o) => shown(o, "TEST ZAPLANOWANY") || shown(o, "TEST WYSŁANY") || tests(o).length > 0 },
      { pl: "Czekaj na „ODBIORCA ZAPISAŁ”. TEST wychodzi w ciągu kilku minut; czas możesz przyspieszyć.",
        en: "Wait for “RECIPIENT SAVED”. The TEST goes out within a few minutes; you can speed up time.",
        hint: { pl: "Użyj +1 min albo ×10 na pasku czasu.", en: "Use +1 min or ×10 on the time bar." },
        done: (o) => tests(o).some((t) => t.received_acked >= 0) },
      { pl: "Czekaj na „ODBIORCA PRZECZYTAŁ”: dyżurny potwierdza TEST.", en: "Wait for “RECIPIENT READ”: the duty officer confirms the TEST.",
        done: (o) => tests(o).some((t) => t.state_acked >= 2) },
    ],
    solution: ["power on", "wait 1.5", "press OK", "press OK", "press OK", "wait 400"],
  },
  {
    id: "request",
    title: { pl: "Pierwsze zgłoszenie", en: "First request" },
    brief: {
      pl: "W schronieniu brakuje wody dla 40 osób, potrzeba jest pilna. Wyślij jedno zgłoszenie i śledź jego etapy.",
      en: "The shelter lacks water for 40 people and it is urgent. Send one request and follow its stages.",
    },
    setup: ["boot", "post auto 1 1 3 4"],
    steps: [
      { pl: "Otwórz menu (OK) i wybierz ZGŁOSZENIE.", en: "Open the menu (OK) and choose REQUEST.", done: (o) => shown(o, "WODA PITNA") && shown(o, "POMOC MEDYCZNA") },
      { pl: "Kategoria WODA PITNA, liczba osób 40 (INNA LICZBA i wpis cyfr), pilność PILNE – KILKA GODZIN, bez frazy. Na podsumowaniu OK = WYŚLIJ.",
        en: "Category DRINKING WATER, 40 people (OTHER NUMBER and digit entry), urgency URGENT – A FEW HOURS, no phrase. On the summary OK = SEND.",
        hint: { pl: "Cyfry: GÓRA i DÓŁ zmieniają cyfrę, OK przechodzi do następnej.", en: "Digits: UP and DOWN change the digit, OK moves to the next one." },
        done: (o, ctx) => {
          if (shown(o, "WODA PITNA") && shown(o, "40 PILNE")) ctx.summary = true;
          return !!ctx.summary && (shown(o, "ZAPISANE W STACJI") || requests(o).some((r) => r.category === 3));
        } },
      { pl: "Zapisz krótki numer zgłoszenia w dzienniku. Czekaj na „ODBIORCA ZAPISAŁ”.", en: "Write the short request number in the log. Wait for “RECIPIENT SAVED”.",
        done: (o) => requests(o).some((r) => r.category === 3 && r.people === 40 && r.urgency === 1 && r.received_acked >= 0) },
      { pl: "Czekaj na decyzję dyżurnego i sprawdź ją w WIADOMOŚCI.", en: "Wait for the duty officer’s decision and check it in MESSAGES.",
        done: (o) => requests(o).some((r) => r.category === 3 && r.state_acked === 3) },
    ],
    solution: [...wizard({ category: 3, people: { value: 40 }, urgency: 1 }), "wait 400"],
  },
  {
    id: "revise",
    title: { pl: "Zmiana liczby osób", en: "Changing the number of people" },
    brief: {
      pl: "Zgłoszenie „woda pitna, 40 osób” jest u odbiorcy. Przyszło 15 kolejnych osób. Zmień zgłoszenie zamiast wysyłać nowe.",
      en: "The request “drinking water, 40 people” is with the recipient. 15 more people arrived. Change the request instead of sending a new one.",
    },
    setup: ["boot", "post auto 0 0 0 0", ...wizard({ category: 3, people: { value: 40 }, urgency: 1 }), "wait 60"],
    steps: [
      { pl: "WIADOMOŚCI → zgłoszenie → ZMIEŃ LICZBĘ OSÓB, wpisz 55 i wyślij.", en: "MESSAGES → the request → CHANGE NUMBER OF PEOPLE, enter 55 and send.",
        done: (o) => shown(o, "ZAPISANE W STACJI") || requests(o).some((r) => r.revision >= 1) },
      { pl: "Czekaj, aż odbiorca zapisze nową wersję. Krótki numer się nie zmienia.", en: "Wait until the recipient saves the new version. The short number stays the same.",
        done: (o) => requests(o).some((r) => r.revision >= 1 && r.people === 55 && r.received_acked >= 1) },
      { pl: "Sprawdź na stanowisku (panel Dyżurny), że to wciąż jedno zgłoszenie.", en: "Check at the receiving post (Duty officer panel) that it is still one request.",
        done: (o) => requests(o).length === 1 },
    ],
    solution: [...MESSAGES, "press OK", "wait 0.3", "press OK", "wait 0.3", ...Array(7).fill("press DOWN"), "press OK", "press OK", "press UP", "press OK",
      ...Array(5).fill("press UP"), "press OK", "wait 0.3", "press OK", "wait 3", "press BACK", "wait 120"],
  },
  {
    id: "alarm",
    title: { pl: "Zagrożenie życia bez łączności", en: "Life threat without a link" },
    brief: {
      pl: "Mieszkaniec traci przytomność. Telefony nie działają. Radio nie ma połączenia z odbiorcą (nie wiesz o tym).",
      en: "A resident loses consciousness. Phones are down. The radio has no link to the recipient (you do not know that).",
    },
    setup: ["boot", "link down"],
    steps: [
      { pl: "Najpierw pierwsza pomoc. Równolegle wyślij POMOC MEDYCZNA, 1 osoba, ZAGROŻENIE ŻYCIA.", en: "First aid first. In parallel send MEDICAL HELP, 1 person, LIFE THREAT.",
        done: (o, ctx) => {
          if (shown(o, "POMOC MEDYCZNA") && shown(o, "1 ZAGROŻENIE")) ctx.summary = true;
          return !!ctx.summary && shown(o, "ZAPISANE W STACJI");
        } },
      { pl: "Przyspiesz czas (+15 min) i obserwuj ekran oraz diodę ALARM.", en: "Speed up time (+15 min) and watch the screen and the ALARM LED.",
        done: (o) => shown(o, "BRAK POTWIERDZENIA") },
      { pl: "Potwierdź alarm (OK). Według karty: formularz w dwóch egzemplarzach i goniec, jeśli droga jest bezpieczna.",
        en: "Acknowledge the alarm (OK). Per the card: paper form in two copies and a runner if the route is safe.",
        done: (o, ctx) => seenThenGone(o, ctx, "alarm", "GONIEC Z FORMULARZEM") },
      { pl: "Łączność wróciła. Stacja sama ponawia wysyłkę: nie wysyłaj zgłoszenia drugi raz. Czekaj na „ODBIORCA ZAPISAŁ”.",
        en: "The link is back. The station retries by itself: do not send the request again. Wait for “RECIPIENT SAVED”.",
        enter: ["link up"],
        done: (o) => requests(o).some((r) => r.category === 0 && r.urgency === 2 && r.received_acked >= 0),
        check: (o) => requests(o).filter((r) => r.category === 0).length > 1
          ? { pl: "Wysłano drugie zgłoszenie o tej samej potrzebie.", en: "A second request for the same need was sent." } : null },
    ],
    solution: [...wizard({ category: 0, people: 0, urgency: 0 }), "wait 960", "press OK", "wait 3", "wait 1500"],
  },
  {
    id: "silence",
    title: { pl: "Cisza radiowa", en: "Radio silence" },
    brief: {
      pl: "Odbiorca przekazuje polecenie ciszy radiowej. Stacja ma zapisywać zgłoszenia, ale nic nie nadawać.",
      en: "The recipient passes on a radio silence order. The station must store requests but transmit nothing.",
    },
    setup: ["boot", "post bulletin Wójt poleca ciszę radiową do odwołania. Włączcie przełącznik CISZA. Pilne sprawy gońcem.", "wait 90"],
    steps: [
      { pl: "Przyszedł komunikat (dioda miga). Przeczytaj go w WIADOMOŚCI.", en: "A bulletin arrived (the LED flashes). Read it in MESSAGES.",
        done: (o) => shown(o, "CISZĘ RADIOWĄ") },
      { pl: "Włącz przełącznik CISZA pod osłoną.", en: "Turn on the SILENCE switch under its guard.", done: (o) => o.switch },
      { pl: "Wyślij ŻYWNOŚĆ, 20 osób, W CIĄGU DOBY. Przeczytaj ekran wyniku.", en: "Send FOOD, 20 people, WITHIN A DAY. Read the result screen.",
        done: (o) => shown(o, "NIE WYJDZIE DO KOŃCA") },
      { pl: "Odbiorca odwołał ciszę (nowy komunikat). Przeczytaj go i wyłącz CISZĘ.", en: "The recipient lifted the silence (new bulletin). Read it and turn SILENCE off.",
        enter: ["post bulletin Cisza radiowa odwołana. Wyłączcie przełącznik CISZA."],
        done: (o, ctx) => { if (shown(o, "ODWOŁANA")) ctx.read = true; return !!ctx.read && !o.switch; } },
      { pl: "Czekaj, aż zgłoszenie zapisane w ciszy dotrze do odbiorcy.", en: "Wait until the request stored during silence reaches the recipient.",
        done: (o) => requests(o).some((r) => r.category === 4 && r.received_acked >= 0) },
    ],
    solution: [...MESSAGES, "press BACK", "press BACK", "press BACK", "switch on",
      ...wizard({ category: 4, people: 4, urgency: 2 }).slice(0, -2), "wait 3", "press BACK", "wait 300",
      ...MESSAGES, "press BACK", "press BACK", "press BACK", "switch off", "wait 900"],
  },
  {
    id: "reply",
    title: { pl: "Odbiorca nie może pomóc", en: "The recipient cannot help" },
    brief: {
      pl: "Zgłoszenie ewakuacji 10 osób dotarło. Dyżurny nie ma teraz transportu i odpowiada instrukcją.",
      en: "An evacuation request for 10 people arrived. The duty officer has no transport now and replies with instructions.",
    },
    setup: ["boot", "post auto 0 0 0 0", ...wizard({ category: 2, people: 3, urgency: 1 }), "wait 60", "post decide last 5",
      "post reply last Brak transportu do 18:00. Osoby chodzące: punkt w Szkole nr 1, jeśli droga bezpieczna.", "wait 60"],
    steps: [
      { pl: "Sprawdź etap zgłoszenia w WIADOMOŚCI i przeczytaj odpowiedź dyżurnego.", en: "Check the request stage in MESSAGES and read the duty officer’s reply.",
        done: (o) => shown(o, "BRAK TRANSPORTU") },
    ],
    solution: [...MESSAGES],
  },
  {
    id: "backup",
    title: { pl: "Klucz zapasowy odbiorcy", en: "Recipient backup key" },
    brief: {
      pl: "Komputer stanowiska przepadł; gmina uruchomiła tożsamość zapasową. Goniec przynosi polecenie przełączenia. Radiem to polecenie nigdy nie przychodzi.",
      en: "The receiving post’s computer was lost; the municipality started the backup identity. A runner brings the order to switch. It never comes by radio.",
    },
    setup: ["boot", "post identity backup", "wait 30", ...wizard({ category: 3, people: 4, urgency: 2 })],
    steps: [
      { pl: "STAN → USŁUGI → KLUCZ ZAPASOWY, potwierdź sekwencją GÓRA, DÓŁ, GÓRA, OK. Zgłoszenie dotrze wtedy do tożsamości zapasowej.",
        en: "STATUS → SERVICES → BACKUP KEY, confirm with UP, DOWN, UP, OK. The request then reaches the backup identity.",
        done: (o) => requests(o).some((r) => r.identity === 1 && r.received_acked >= 0) },
    ],
    solution: ["press OK", ...Array(3).fill("press DOWN"), "press OK", "wait 0.3", ...Array(20).fill("press DOWN"), "press OK", "wait 0.3",
      "press DOWN", "press DOWN", "press OK", "wait 0.3", "press UP", "press DOWN", "press UP", "press OK", "wait 2", "press BACK", "wait 1200"],
  },
  {
    id: "power",
    title: { pl: "Zanik zasilania", en: "Power loss" },
    brief: {
      pl: "Zgłoszenie czeka w stacji na wysyłkę, gdy znika zasilanie. Po powrocie zasilania zgłoszenie jest nadal w pamięci FRAM. Stacja nie wie, jak długo była wyłączona, więc od razu alarmuje o braku potwierdzenia.",
      en: "A request is waiting in the station when power is lost. After power returns the request is still in FRAM. The station does not know how long it was off, so it raises the no-confirmation alarm at once.",
    },
    setup: ["boot", "link down", ...wizard({ category: 4, people: 4, urgency: 1 })],
    steps: [
      { pl: "Przytrzymaj WYŁĄCZNIK 2 s (albo odłącz zasilanie).", en: "Hold POWER for 2 s (or disconnect power).", done: (o) => !o.power },
      { pl: "Włącz stację.", en: "Switch the station on.", done: (o) => o.power && o.screen.on },
      { pl: "Potwierdź alarm braku potwierdzenia (OK), przejdź start (język, adres; TEST możesz pominąć: WSTECZ) i znajdź zgłoszenie w WIADOMOŚCI.",
        en: "Acknowledge the no-confirmation alarm (OK), go through the start (language, address; you may skip TEST: BACK) and find the request in MESSAGES.",
        // Pozycja w WIADOMOŚCIACH: numer zgłoszenia i kategoria („0918 ŻYWNOŚĆ”), nie lista kategorii kreatora.
        done: (o) => o.screen.lines.some((l) => /^\d{4} ŻYWNOŚĆ/.test(l)) },
    ],
    solution: ["power off", "wait 5", "power on", "wait 1.5", "press OK", "press OK", "press OK", "press BACK", "wait 5", "press OK", "press DOWN", "press OK", "wait 0.3"],
  },
];

// Przebieg ćwiczenia: kroki po kolei, czas symulacji i naciśnięcia na krok, ostrzeżenia z `check`.
export class Exercise {
  constructor(sim, scenario) {
    this.sim = sim;
    this.scenario = scenario;
    this.ctx = {};
    this.index = 0;
    this.records = [];
    this.warnings = [];
    this.presses = 0;
    this.hints = 0;
  }

  observe() {
    const sim = this.sim;
    return { screen: sim.screen(), post: sim.postState(), power: sim.station.powered, switch: sim.switchOn(), t: sim.nowUs };
  }

  async start(onProgress) {
    await this.sim.reset();
    const steps = this.scenario.setup;
    for (let i = 0; i < steps.length; i++) {
      await this.sim.act(steps[i]);
      onProgress?.((i + 1) / steps.length);
    }
    this.sim.takeEvents();
    const o = this.observe();
    this.startT = o.t;
    await this.enter(o);
    return this.update(this.observe());
  }

  async enter(o) {
    for (const line of this.current?.enter ?? []) await this.sim.act(line);
    this.stepT = o.t;
    this.stepPresses = this.presses;
  }

  press() { this.presses++; }
  get finished() { return this.index >= this.scenario.steps.length; }
  get current() { return this.scenario.steps[this.index]; }

  // Sprawdza bieżący krok; zwraca true, gdy coś się zmieniło.
  async update(o) {
    let moved = false;
    while (!this.finished) {
      const warn = this.current.check?.(o, this.ctx);
      if (warn && !this.warnings.some((w) => w.pl === warn.pl)) this.warnings.push(warn);
      if (!this.current.done(o, this.ctx)) break;
      this.records.push({ step: this.index, simS: (o.t - this.stepT) / 1e6, presses: this.presses - this.stepPresses });
      this.index++;
      moved = true;
      if (!this.finished) { await this.enter(o); o = this.observe(); }
    }
    if (moved && this.finished) this.totalS = (o.t - this.startT) / 1e6;
    return moved;
  }
}

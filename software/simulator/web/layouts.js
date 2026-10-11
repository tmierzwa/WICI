// SPDX-License-Identifier: MIT
// Układy panelu stacji w milimetrach, od lewego górnego narożnika, X w prawo, Y w dół.
// R02: propozycja obudowy Hammond 1599KBAT (hardware/r02/obudowa.md, „Układ panelu”) w wersji renderu
// koncepcyjnego z 2026-10-11 (hardware/obudowa/render/uklad.json i stacja.html z gałęzi obudowa-szkielet:
// folia panelu, kolumna boczna, przycisk przygotowania pod naklejką VOID zamiast pokrywy, F113).
// N1: płytka nośna stanowiska deweloperskiego (hardware/dev-bench/tools/design.py: PANEL_X/Y,
// BUTTONS, SW5, SW6, D1, BZ1; środki elementów THT z footprintów). Ekran Sharp LS027B7DH01A:
// szkło 62,8 × 42,82 mm, pole aktywne 58,8 × 35,28 mm (400 × 240 px, piksel 0,147 mm).

export const ACTIVE = { w: 58.8, h: 35.28 };

export const LAYOUTS = {
  r02: {
    name: { pl: "R02 – obudowa Hammond 1599KBAT (koncepcja 2026-10-11)", en: "R02 – Hammond 1599KBAT case (concept 2026-10-11)" },
    short: "R02",
    kind: "case",
    w: 220, h: 140, radius: 6,
    recess: { x: 6.875, y: 6.75, w: 206.25, h: 126.5 },
    window: { cx: 52, cy: 42, w: 61.5, h: 38 },
    // Nadruk folii (stacja.html): logo i nazwa, kolumna boczna, podpowiedź pod ekranem, opisy złączy.
    foil: { brand: { x: 97, y: 15, h: 11 }, column: { x: 164, y: 11, w: 42, h: 118 }, hint: "OK = TAK      WSTECZ = NIE" },
    controls: [
      { id: "BACK", type: "button", shape: "round", d: 16, x: 30, y: 98 },
      { id: "UP", type: "button", shape: "round", d: 16, x: 62, y: 98 },
      { id: "DOWN", type: "button", shape: "round", d: 16, x: 94, y: 98 },
      { id: "OK", type: "button", shape: "round", d: 16, x: 126, y: 98 },
      { id: "LED", type: "led", d: 5, x: 185, y: 22 },
      { id: "SILENCE", type: "toggle", guard: true, w: 20, h: 38, x: 185, y: 58 },
      { id: "POWER", type: "power", shape: "round", d: 16, x: 185, y: 100 },
      { id: "PREP", type: "seal", w: 22, h: 12, hole: 4, x: 150, y: 122, label: { pl: "SERWIS", uk: "СЕРВІС", en: "SERVICE" } },   // pole naklejki na folii (uklad.json: SERWIS)
    ],
    edge: [{ label: "USB-C", x: 60, part: "usb" }, { label: "12 V", x: 110, part: "en3" }, { label: "ANTENA", x: 170, part: "sma" }],
  },
  n1: {
    name: { pl: "N1 – płytka nośna stanowiska deweloperskiego", en: "N1 – development bench carrier board" },
    short: "N1",
    kind: "pcb",
    w: 170, h: 100, radius: 1,
    glass: { x: 8.6, y: 4.0, w: 62.8, h: 42.82 },
    window: { cx: 8.6 + 62.8 / 2, cy: 4.0 + 42.82 / 2 - 1.2, w: 58.8, h: 35.28 },
    controls: [
      { id: "UP", type: "button", shape: "square", d: 12, x: 14, y: 70 },
      { id: "DOWN", type: "button", shape: "square", d: 12, x: 30, y: 70 },
      { id: "OK", type: "button", shape: "square", d: 12, x: 46, y: 70 },
      { id: "BACK", type: "button", shape: "square", d: 12, x: 62, y: 70 },
      { id: "SILENCE", type: "toggle", guard: false, w: 8, h: 13, x: 14, y: 89 },
      { id: "PREP", type: "tact", d: 6, x: 28.25, y: 89 },
      { id: "LED", type: "led", d: 5, x: 37.27, y: 89 },
      { id: "BUZZER", type: "buzzer", d: 12, x: 52, y: 89 },
      { id: "POWER", type: "power", shape: "round", d: 9, x: 160, y: 92, virtual: true },   // N1 nie ma wyłącznika: wtyk USB DevKit
    ],
    holes: [[4, 4], [166, 4], [4, 96], [166, 96]],
    zones: [{ x: 101.42, y: 22.99, w: 68.58, h: 53.34, pl: "pole Arduino: ESP32-S3 / moduł radiowy", en: "Arduino field: ESP32-S3 / radio module" }],
    edge: [{ label: "USB (DevKit)", x: 86 }],
  },
};

export const LABELS = {
  pl: { UP: "GÓRA", DOWN: "DÓŁ", OK: "OK", BACK: "WSTECZ", SILENCE: "CISZA", POWER: "WYŁĄCZNIK", PREP: "PRZYGOTOWANIE", LED: "ALARM", BUZZER: "BRZĘCZYK" },
  uk: { UP: "ВГОРУ", DOWN: "ВНИЗ", OK: "OK", BACK: "НАЗАД", SILENCE: "ТИША", POWER: "ВИМИКАЧ", PREP: "ПІДГОТОВКА", LED: "ТРИВОГА", BUZZER: "ЗУМЕР" },
  en: { UP: "UP", DOWN: "DOWN", OK: "OK", BACK: "BACK", SILENCE: "SILENCE", POWER: "POWER", PREP: "PREPARATION", LED: "ALARM", BUZZER: "BUZZER" },
};

// Napis przy elemencie: własny napis układu (R02: SERWIS nad naklejką) albo wspólny z LABELS.
export const labelOf = (c, lang) => c.label?.[lang] ?? LABELS[lang][c.id];

const NAV = ["UP", "DOWN", "OK", "BACK"];
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const extent = (c) => (c.d ?? Math.max(c.w ?? 0, c.h ?? 0)) / 2;

// Zasady z hardware/r02/obudowa.md; każda zwraca { ok, value } do pokazania w panelu projektu.
export const RULES = [
  {
    id: "gap",
    pl: "Odstęp między przyciskami nawigacji ≥16 mm (rękawice)",
    en: "Gap between navigation buttons ≥16 mm (gloves)",
    test(layout) {
      const nav = layout.controls.filter((c) => NAV.includes(c.id));
      let min = Infinity;
      for (let i = 0; i < nav.length; i++) for (let j = i + 1; j < nav.length; j++) min = Math.min(min, dist(nav[i], nav[j]) - extent(nav[i]) - extent(nav[j]));
      return { ok: min >= 16, value: `${min.toFixed(1)} mm` };
    },
  },
  {
    id: "size",
    pl: "Przyciski nawigacji Ø ≥15 mm",
    en: "Navigation buttons Ø ≥15 mm",
    test(layout) {
      const min = Math.min(...layout.controls.filter((c) => NAV.includes(c.id)).map((c) => c.d));
      return { ok: min >= 15, value: `${min} mm` };
    },
  },
  {
    id: "column",
    pl: "CISZA i wyłącznik ≥30 mm od rzędu nawigacji",
    en: "SILENCE and power ≥30 mm from the navigation row",
    test(layout) {
      const nav = layout.controls.filter((c) => NAV.includes(c.id));
      const far = layout.controls.filter((c) => (c.id === "SILENCE" || c.id === "POWER") && !c.virtual);
      const min = Math.min(...far.flatMap((f) => nav.map((n) => dist(f, n))));
      return { ok: min >= 30, value: `${min.toFixed(1)} mm` };
    },
  },
  {
    id: "guard",
    pl: "CISZA pod osłoną, najbliższy przycisk ≥20 mm od jej osi",
    en: "SILENCE under a guard, nearest button ≥20 mm from its axis",
    test(layout) {
      // Obrysu klapki GT-4R nie ma jeszcze w dokumentacji: odległość od osi przełącznika do krawędzi przycisku.
      const s = layout.controls.find((c) => c.id === "SILENCE");
      const others = layout.controls.filter((c) => (c.type === "button" || c.type === "power") && !c.virtual);
      const min = Math.min(...others.map((o) => dist(s, o) - extent(o)));
      return { ok: s.guard && min >= 20, value: s.guard ? `${min.toFixed(1)} mm` : "—" };
    },
  },
  {
    id: "order",
    pl: "WSTECZ po lewej, OK po prawej (OK = TAK, WSTECZ = NIE)",
    en: "BACK on the left, OK on the right (OK = YES, BACK = NO)",
    test(layout) {
      const back = layout.controls.find((c) => c.id === "BACK");
      const ok = layout.controls.find((c) => c.id === "OK");
      return { ok: back.x < ok.x, value: back.x < ok.x ? "◀ BACK · OK ▶" : "◀ OK · BACK ▶" };
    },
  },
  {
    id: "window",
    pl: "Elementy panelu poza oknem ekranu",
    en: "Panel controls clear of the screen window",
    test(layout) {
      const w = layout.window;
      const hit = layout.controls.filter((c) => Math.abs(c.x - w.cx) < w.w / 2 + extent(c) && Math.abs(c.y - w.cy) < w.h / 2 + extent(c));
      return { ok: hit.length === 0, value: hit.length ? hit.map((c) => c.id).join(", ") : "0" };
    },
  },
];

// Koszt sekwencji naciśnięć na danym układzie: droga palca i czas ruchu z prawa Fittsa
// (MT = a + b·log2(D/W + 1), a = 0,2 s, b = 0,1 s/bit; wartości typowe dla dotyku, do kalibracji w T1).
export function sequenceCost(layout, presses, a = 0.2, b = 0.1) {
  const byId = Object.fromEntries(layout.controls.map((c) => [c.id, c]));
  let travel = 0, time = 0, prev = null;
  for (const id of presses) {
    const c = byId[id];
    if (!c) continue;
    const width = c.d ?? Math.min(c.w, c.h);
    if (prev) {
      const d = dist(prev, c);
      travel += d;
      time += d > 0 ? a + b * Math.log2(d / width + 1) : a * 0.6;   // powtórzenie tego samego przycisku: samo naciśnięcie
    } else time += a;
    prev = c;
  }
  return { travel, time, presses: presses.length };
}

export function cloneLayout(layout) {
  return JSON.parse(JSON.stringify(layout));
}

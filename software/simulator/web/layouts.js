// SPDX-License-Identifier: MIT
// Panel stacji R02 w milimetrach, od lewego górnego narożnika, X w prawo, Y w dół: propozycja obudowy
// Hammond 1599KBAT (hardware/r02/obudowa.md, „Układ panelu”) w wersji renderu koncepcyjnego
// (hardware/obudowa/render/uklad.json i stacja.html: folia panelu, kolumna boczna, przycisk
// przygotowania pod naklejką VOID, F113). Ekran Sharp LS027B7DH01A: szkło 62,8 × 42,82 mm, pole aktywne
// 58,8 × 35,28 mm (400 × 240 px, piksel 0,147 mm).

export const ACTIVE = { w: 58.8, h: 35.28 };

export const R02 = {
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
};

export const LABELS = {
  pl: { UP: "GÓRA", DOWN: "DÓŁ", OK: "OK", BACK: "WSTECZ", SILENCE: "CISZA", POWER: "WYŁĄCZNIK", PREP: "PRZYGOTOWANIE", LED: "ALARM" },
  uk: { UP: "ВГОРУ", DOWN: "ВНИЗ", OK: "OK", BACK: "НАЗАД", SILENCE: "ТИША", POWER: "ВИМИКАЧ", PREP: "ПІДГОТОВКА", LED: "ТРИВОГА" },
  en: { UP: "UP", DOWN: "DOWN", OK: "OK", BACK: "BACK", SILENCE: "SILENCE", POWER: "POWER", PREP: "PREPARATION", LED: "ALARM" },
};

// Napis przy elemencie: własny napis układu (R02: SERWIS nad naklejką) albo wspólny z LABELS.
export const labelOf = (c, lang) => c.label?.[lang] ?? LABELS[lang][c.id];

const NAV = ["UP", "DOWN", "OK", "BACK"];
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const extent = (c) => (c.d ?? Math.max(c.w ?? 0, c.h ?? 0)) / 2;

// Zasady z hardware/r02/obudowa.md; każda zwraca { ok, value } (tests/test_simulator.py sprawdza R02).
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
      const far = layout.controls.filter((c) => (c.id === "SILENCE" || c.id === "POWER"));
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
      const others = layout.controls.filter((c) => (c.type === "button" || c.type === "power"));
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

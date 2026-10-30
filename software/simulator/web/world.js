// SPDX-License-Identifier: MIT
// Świat symulatora: urządzenia z obrazem oprogramowania stacji (stacje i węzeł stanowiska), komputer
// stanowiska odbiorczego, eter między układami S2-LP i przewód USB węzeł–komputer. Wszystkie urządzenia
// biegną krokami po QUANTUM_US czasu wspólnego; ramka nadana w kroku trafia do innych odbiorników z mocą
// = moc nadawania − tłumienie trasy + zanik (rozkład normalny, FADING_DB). Przygotowanie stacji i węzła
// idzie jak z laptopa przygotowania: przytrzymanie przycisku przygotowania, protokół USB "usb":2
// (`configure`), ponowne przytrzymanie (docs/spec/protokol-usb.md).
import { Device, encodeCommand } from "./device.js";
import createPost from "./wici-post.mjs";

export const QUANTUM_US = 5000;
export const FADING_DB = 4;
export const IFAC = "5749434953494d554c41544f52305f30";   // „WICISIMULATOR0_0”: klucz sieci ćwiczeniowej, nie polowy

// Komputer stanowiska odbiorczego (post/post.cpp) jako urządzenie z własnym zegarem.
export class Post {
  constructor(seed) { this.seed = seed; this.mod = null; this.disk = null; }
  async start(worldUs) {
    const mod = await createPost();
    this.mod = mod;
    this.bootUs = worldUs;
    this.board(`boot ${Math.round(worldUs)} 1 ${this.seed}`);
    if (this.disk) mod.HEAPU8.set(this.disk, mod._post_disk());
  }
  board(line) {
    const bytes = encodeCommand(line);
    this.mod.HEAPU8.set(bytes, this.mod._sim_input());
    return this.mod.UTF8ToString(this.mod._sim_command());
  }
  cmd(line) {
    const bytes = encodeCommand(line);
    const ptr = this.mod._sim_input();
    this.mod.HEAPU8.set(bytes, ptr);
    return this.mod.UTF8ToString(this.mod._post_command(ptr));
  }
  run(untilUs) { if (this.mod) this.mod._sim_run(untilUs); }
  saveDisk() { this.disk = new Uint8Array(this.mod.HEAPU8.subarray(this.mod._post_disk(), this.mod._post_disk() + this.mod._post_disk_size())); }
  state() { return JSON.parse(this.cmd("state")); }
}

const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (text) => Uint8Array.from(text.match(/../g) ?? [], (h) => parseInt(h, 16));
function gauss(rand) {
  const u = Math.max(rand(), 1e-12), v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export class World {
  constructor(seed = 1) {
    this.seed = seed;
    this.nowUs = 0;
    this.devices = [];           // urządzenia z radiem (Device)
    this.post = null;
    this.node = null;            // węzeł stanowiska (Device), port danych do komputera
    this.loss = new Map();       // "a|b" -> tłumienie trasy [dB]; Infinity = brak trasy
    this.defaultLoss = 100;
    this.rngState = seed >>> 0 || 1;
    this.listeners = [];
  }

  rand() {
    // xorshift32: powtarzalny zanik dla danego ziarna świata
    let x = this.rngState;
    x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0;
    this.rngState = x;
    return x / 4294967296;
  }

  key(a, b) { return [a.name, b.name].sort().join("|"); }
  setLoss(a, b, db) { this.loss.set(this.key(a, b), db); }
  lossOf(a, b) { return this.loss.has(this.key(a, b)) ? this.loss.get(this.key(a, b)) : this.defaultLoss; }

  add(device) {
    this.devices.push(device);
    device.on((d, e) => this.emit(d, e));
    return device;
  }

  on(fn) { this.listeners.push(fn); }
  emit(source, e) { for (const fn of this.listeners) fn(source, e); }

  // Krok świata: wszystkie urządzenia do tej samej chwili, potem eter i USB.
  async advance(us) {
    const end = this.nowUs + us;
    while (this.nowUs < end) {
      const t = Math.min(end, this.nowUs + QUANTUM_US);
      for (const d of this.devices) await d.run(t);
      if (this.post) this.post.run(t);
      this.nowUs = t;
      this.air();
      this.usb();
    }
  }

  // Id ramki w eterze: urządzenie, instancja (po restarcie licznik układu zaczyna od 1) i licznik układu.
  frameId(tx, f) { return (this.devices.indexOf(tx) + 1) * 100000000 + (f.gen % 100) * 1000000 + (f.id % 1000000); }

  send(tx, f, id) {
    for (const rx of this.devices) {
      if (rx === tx || !rx.powered) continue;
      const loss = this.lossOf(tx, rx);
      if (!isFinite(loss)) continue;
      // Ten sam zanik dla aktualizacji przerwanej ramki (to samo id): pamiętany przy ramce.
      tx.fades ??= new Map();
      const keyFade = `${id}|${rx.name}`;
      let fade = tx.fades.get(keyFade);
      if (fade === undefined) {
        fade = gauss(() => this.rand()) * FADING_DB;
        tx.fades.set(keyFade, fade);
        if (tx.fades.size > 2000) tx.fades.delete(tx.fades.keys().next().value);   // najstarszy wpis
      }
      rx.putAir({ ...f, id, dbm: Math.round(f.dbm - loss + fade) });
    }
  }

  air() {
    for (const tx of this.devices) {
      tx.onAir ??= new Map();   // id -> ramka nadawana (do urwania przy restarcie lub wyłączeniu)
      for (const f of tx.takeAir()) {
        const id = this.frameId(tx, f);
        this.emit(tx, { kind: "air", frame: f });
        if (f.aborted) tx.onAir.delete(id); else tx.onAir.set(id, f);
        this.send(tx, f, id);
      }
      if (tx.cutAt !== null) {
        // Restart albo wyłączenie w czasie nadawania: odbiorcy dostają ramkę urwaną w tej chwili.
        for (const [id, f] of tx.onAir) {
          // Ramka zaczęta (według zegara płytki) po wyłączeniu nie istnieje: długość zero.
          if (f.end > tx.cutAt) this.send(tx, { ...f, end: Math.max(f.start, tx.cutAt), aborted: true }, id);
        }
        tx.onAir.clear();
        tx.cutAt = null;
      }
      for (const [id, f] of tx.onAir) if (f.end <= this.nowUs) tx.onAir.delete(id);
    }
  }

  usb() {
    if (!this.node || !this.post || !this.node.powered) return;
    if (this.node.usbOpen[1] && this.node.kissMode) {
      const fromNode = this.node.usbRead(1);
      // Kawałkami: zaległość portu (do 8 KB) jako tekst szesnastkowy przekroczyłaby bufor poleceń;
      // dekoder KISS komputera zachowuje stan między kawałkami.
      const text = hex(fromNode);
      for (let i = 0; i < text.length; i += 8000) this.post.cmd(`kissin ${text.slice(i, i + 8000)}`);
      const toNode = this.post.cmd("kissout");
      if (toNode) this.node.usbWrite(1, unhex(toNode));
    }
  }

  // ---- laptop przygotowania: protokół "usb":2 na porcie danych ----

  async usbSession(device) {
    device.setUsb(1, true);
    const session = { device, seq: 0, buffer: "", decoder: new TextDecoder() };
    await this.waitLine(session, (m) => m.type === "hello", 5e6);
    return session;
  }

  async waitLine(session, match, timeoutUs) {
    const start = this.nowUs;
    for (;;) {
      session.buffer += session.decoder.decode(session.device.usbRead(1), { stream: true });
      let nl;
      while ((nl = session.buffer.indexOf("\n")) >= 0) {
        const line = session.buffer.slice(0, nl).trim();
        session.buffer = session.buffer.slice(nl + 1);
        if (!line.startsWith("{")) continue;
        const message = JSON.parse(line);
        if (match(message)) return message;
      }
      if (this.nowUs - start > timeoutUs) throw new Error(`${session.device.name}: brak odpowiedzi USB`);
      await this.advance(20000);
    }
  }

  async request(session, type, fields = {}, timeoutUs = 15e6) {
    const seq = ++session.seq;
    session.device.usbWrite(1, JSON.stringify({ usb: 2, seq, type, ...fields }) + "\n");
    const reply = await this.waitLine(session, (m) => m.re === seq && m.type !== "pending", timeoutUs);
    if (reply.type === "rejected") throw new Error(`${session.device.name}: ${type} odrzucone (${reply.reason}${reply.detail ? ", " + reply.detail : ""})`);
    return reply;
  }

  // Naciśnięcie przycisku panelu (stan niski przy naciśnięciu, podciągnięcie na N1).
  async press(device, button, ms = 120) {
    const pin = device.pins[button];
    device.setInput(pin, 0);
    await this.advance(ms * 1000);
    device.setInput(pin, 1);
    await this.advance(150000);
  }

  async holdPrep(device) {
    const pin = device.pins.PREP;
    device.setInput(pin, 0);
    await this.advance(3200000);
    device.setInput(pin, 1);
    await this.advance(200000);
  }

  async configure(device, doc) {
    const text = JSON.stringify(doc);
    const bytes = new TextEncoder().encode(text);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const session = await this.usbSession(device);
    let status = await this.request(session, "status");
    if (!status.prep) await this.holdPrep(device);
    status = await this.request(session, "status");
    if (!status.prep) throw new Error(`${device.name}: tryb przygotowania nie włączony`);
    const begin = await this.request(session, "xfer_begin", { op: "configure", size: bytes.length, sha256: hex(digest) });
    for (let offset = 0; offset < bytes.length; offset += 384) {
      const part = bytes.subarray(offset, offset + 384);
      await this.request(session, "xfer_part", { xfer: begin.xfer, offset, data: btoa(String.fromCharCode(...part)) });
    }
    const result = await this.request(session, "xfer_commit", { xfer: begin.xfer });
    // Konfiguracja może restartować stację (zmiana roli: po restarcie węzeł ma na porcie danych ramki
    // KISS), więc tryb przygotowania sprawdza się w INFO na porcie diagnostyki; wyłącza go przycisk.
    device.setUsb(1, false);
    await this.advance(3000000);
    if ((await this.info(device)).prep) await this.holdPrep(device);
    if ((await this.info(device)).prep) throw new Error(`${device.name}: tryb przygotowania nie wyłączony`);
    return result;
  }

  // INFO z portu diagnostyki (main.cpp, printInfo).
  async info(device) {
    const wasOpen = device.usbOpen[0];
    device.setUsb(0, true);
    device.usbRead(0);
    device.usbWrite(0, "INFO\n");
    let text = "";
    for (let i = 0; i < 50; i++) {
      await this.advance(20000);
      text += new TextDecoder().decode(device.usbRead(0));
      const line = text.split("\n").find((l) => l.startsWith('{"contract"'));
      if (line) {
        if (!wasOpen) device.setUsb(0, false);
        return JSON.parse(line);
      }
    }
    throw new Error(`${device.name}: brak INFO`);
  }
}

// Sieć ćwiczeniowa: komputer stanowiska z węzłem (stacja w roli `wezel`) i stacje schronień.
// configured = false: stacje zostają bez konfiguracji (swiat.mjs konfiguruje je z plików albo z laptopa).
// receiver: karta odbiorcy aplikacji stanowiska spoza świata ({main, backup}); wtedy świat nie ma modelu
// post.cpp, a port danych węzła otwiera ta aplikacja (swiat.mjs --stanowisko).
export async function prepareNetwork({ seed = 1, stations = 1, addresses, phrases, diag = false, configured = true, receiver } = {}) {
  const world = new World(seed);
  if (!receiver) {
    world.post = new Post(seed * 7 + 3);
    await world.post.start(0);
    await world.post.run(500000);
  }
  const cards = receiver ?? JSON.parse(world.post.cmd("card"));
  world.node = world.add(new Device("węzeł", seed * 7 + 11));
  await world.node.powerOn(world.nowUs);
  if (diag) world.node.setUsb(0, true);
  for (let i = 0; i < stations; i++) {
    const d = world.add(new Device(stations > 1 ? `stacja ${i + 1}` : "stacja", seed * 7 + 20 + i));
    await d.powerOn(world.nowUs);
  }
  await world.advance(2e6);
  await world.configure(world.node, { role: "wezel", ifac: IFAC, radio: { profile: "p1" } });
  for (const d of configured ? world.devices.slice(1) : []) {
    await world.configure(d, {
      role: "stacja",
      addresses: addresses ?? ["Szkoła Podstawowa nr 3, ul. Polna 12, wejście B"],
      receiver: cards,
      stations: Math.max(2, stations + 1),
      phrases: phrases ?? [["osoba na wózku", "людина на візку", "wheelchair user"], ["dzieci do 3 lat", "діти до 3 років", "children under 3"]],
      ifac: IFAC,
      radio: { profile: "p1" },
    });
  }
  // Węzeł: port danych otwarty przez komputer stanowiska (ramki KISS poza trybem przygotowania).
  world.node.kissMode = true;
  if (world.post) {
    world.node.setUsb(1, true);
    world.post.cmd("port open");   // komputer otwiera port węzła: kontrola przepływu i ogłoszenie celu
  }
  await world.advance(1e6);
  return world;
}

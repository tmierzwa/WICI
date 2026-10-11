// SPDX-License-Identifier: MIT
// Jedno urządzenie z obrazem oprogramowania stacji (wici-station.mjs, obraz bench-b na wirtualnej
// płytce): instancja WebAssembly, polecenia płytki (hal/vboard.cpp), porty USB, ekran, praca w czasie.
// Wyłączenie zasilania i restart tworzą nową instancję (wszystkie zmienne globalne od nowa) i przenoszą
// pamięć nieulotną: FRAM i flash NVS zawsze, segment wici_noinit tylko przy restarcie programowym.
import createStation from "./wici-station.mjs";

// Bufor poleceń płytki (sim_input w hal/vboard.cpp) ma 16384 B łącznie z zerem kończącym.
export const INPUT_BYTES = 16384;
export function encodeCommand(line) {
  const bytes = new TextEncoder().encode(line + "\0");
  if (bytes.length > INPUT_BYTES) throw new Error(`polecenie płytki za długie: ${bytes.length} B`);
  return bytes;
}

const RESET = { POWERON: 1, SW: 3, TASK_WDT: 6 };

export class Device {
  constructor(name, seed) {
    this.name = name;
    this.seed = seed;
    this.mod = null;
    this.powered = false;
    this.inputs = {};              // pin -> poziom (przyciski, przełącznik): stan fizyczny, przetrwa wyłączenie
    this.usbOpen = [false, false];
    this.fram = null;              // kopia FRAM poza instancją (wyłączona stacja)
    this.nvs = "";
    this.restarts = 0;
    this.generation = 0;           // kolejna instancja (włączenie, restart): składnik id ramek w eterze
    this.pendingAir = [];          // ramki i zdarzenia poprzedniej instancji, jeszcze nieodebrane
    this.pendingEvents = [];
    this.cutAt = null;             // chwila utraty zasilania układu radiowego (restart, wyłączenie)
    this.radioFault = false;
    this.framFault = false;
    this.listeners = [];
  }

  async powerOn(worldUs, reason = RESET.POWERON, noinit = null) {
    const mod = await createStation();
    this.mod = mod;
    this.generation++;
    this.cmd(`boot ${Math.round(worldUs)} ${reason} ${this.seed}`);
    const ram = mod._sim_fram(), size = mod._sim_fram_size();
    if (this.fram) mod.HEAPU8.set(this.fram, ram);
    if (this.nvs) this.cmd(`nvs ${this.nvs}`);
    if (noinit) mod.HEAPU8.set(noinit.subarray(0, mod._sim_noinit_size()), mod._sim_noinit());
    for (const [pin, level] of Object.entries(this.inputs)) this.cmd(`pin ${pin} ${level ? 1 : 0}`);
    this.usbOpen.forEach((open, i) => { if (open) this.cmd(`usb ${i} open`); });
    if (this.radioFault) this.cmd("fault radio 1");
    if (this.framFault) this.cmd("fault fram 1");
    this.framView = () => mod.HEAPU8.subarray(ram, ram + size);
    this.powered = true;
    this.bootUs = worldUs;
    this.pins = JSON.parse(this.cmd("pins"));
  }

  // Wyłączenie: pamięć nieulotna zostaje poza instancją.
  // `atUs`: chwila wyłączenia w czasie świata. Zegar płytki może ją wyprzedzać (pętla programu stoi w czasie
  // nadawania), więc ramka urywa się w chwili wyłączenia, a nie według zegara płytki.
  powerOff(atUs) {
    if (!this.powered) return;
    this.drain();
    const boardUs = JSON.parse(this.cmd("state")).world_us;
    this.cutAt = atUs === undefined ? boardUs : Math.min(atUs, boardUs);
    this.saveNonvolatile();
    this.mod = null;
    this.powered = false;
  }

  saveNonvolatile() {
    this.fram = new Uint8Array(this.framView());
    this.nvs = this.cmd("nvs");
  }

  cmd(line) {
    const mod = this.mod;
    const bytes = encodeCommand(line);
    mod.HEAPU8.set(bytes, mod._sim_input());
    return mod.UTF8ToString(mod._sim_command());
  }

  // Praca do chwili `untilUs` czasu bezwzględnego; restart programowy albo watchdog: nowa instancja.
  async run(untilUs) {
    if (!this.powered) return;
    if (this.mod._sim_run(untilUs) === 0) return;
    const reason = this.mod._sim_reboot_reason();
    const noinit = new Uint8Array(this.mod.HEAPU8.subarray(this.mod._sim_noinit(), this.mod._sim_noinit() + this.mod._sim_noinit_size()));
    const world = JSON.parse(this.cmd("state")).world_us;
    this.drain();
    this.cutAt = world;   // restart zeruje układ radiowy: trwające nadawanie urywa się
    this.saveNonvolatile();
    this.restarts++;
    this.emit({ kind: "restart", reason, t: world });
    await this.powerOn(world, reason, noinit);
    await this.run(untilUs);
  }

  setInput(pin, level) {
    this.inputs[pin] = level;
    if (this.powered) this.cmd(`pin ${pin} ${level ? 1 : 0}`);
  }

  setUsb(itf, open) {
    this.usbOpen[itf] = open;
    if (this.powered) this.cmd(`usb ${itf} ${open ? "open" : "close"}`);
  }

  usbWrite(itf, data) {
    if (!this.powered) return;
    const bytes = typeof data === "string" ? new TextEncoder().encode(data) : data;
    let hex = "";
    for (const b of bytes) hex += b.toString(16).padStart(2, "0");
    for (let i = 0; i < hex.length; i += 8000) this.cmd(`usbin ${itf} ${hex.slice(i, i + 8000)}`);
  }

  usbRead(itf) {
    if (!this.powered) return new Uint8Array(0);
    const hex = this.cmd(`usbout ${itf}`);
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(2 * i, 2), 16);
    return out;
  }

  fault(kind, on) {
    if (kind === "radio") this.radioFault = on;
    if (kind === "fram") this.framFault = on;
    if (this.powered) this.cmd(`fault ${kind} ${on ? 1 : 0}`);
  }

  lcd() { return this.powered ? this.mod.HEAPU8.subarray(this.mod._sim_lcd(), this.mod._sim_lcd() + 50 * 240) : null; }
  lcdVersion() { return this.powered ? this.mod._sim_lcd_version() : 0; }
  board() { return this.powered ? JSON.parse(this.cmd("state")) : null; }
  // Ramki i zdarzenia odebrane z instancji przed jej zastąpieniem (restart, wyłączenie).
  drain() {
    this.pendingAir.push(...JSON.parse(this.cmd("air")).map((f) => ({ ...f, gen: this.generation })));
    this.pendingEvents.push(...JSON.parse(this.cmd("events")));
  }
  takeEvents() {
    const out = this.pendingEvents.splice(0);
    if (this.powered) out.push(...JSON.parse(this.cmd("events")));
    return out;
  }
  takeAir() {
    const out = this.pendingAir.splice(0);
    if (this.powered) out.push(...JSON.parse(this.cmd("air")).map((f) => ({ ...f, gen: this.generation })));
    return out;
  }
  putAir(frame) { if (this.powered) this.cmd(`airin ${JSON.stringify(frame)}`); }

  on(fn) { this.listeners.push(fn); }
  emit(e) { for (const fn of this.listeners) fn(this, e); }
}

export { RESET };

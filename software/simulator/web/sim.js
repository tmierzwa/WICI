// SPDX-License-Identifier: MIT
// Symulacja do ćwiczeń i pokazu: przygotowana sieć (komputer stanowiska, węzeł, stacja) zapisana jako
// obraz pamięci nieulotnych (FRAM, NVS, dysk komputera), z którego każde ćwiczenie startuje od nowa.
// Stację obsługuje się wyłącznie fizycznie (przyciski, przełącznik, zasilanie), a obserwuje jak człowiek:
// ekran odczytany z pikseli panelu, dioda, brzęczyk; stanowisko odbiorcze przez jego aplikację.
import { Device } from "./device.js";
import { World, Post, prepareNetwork } from "./world.js";

export const BUTTONS = ["UP", "DOWN", "OK", "BACK"];

function capture(world, station) {
  for (const d of world.devices) if (d.powered) d.saveNonvolatile();
  world.post.saveDisk();
  return {
    nowUs: world.nowUs,
    rng: world.rngState,
    seed: world.seed,
    devices: world.devices.map((d) => ({ name: d.name, seed: d.seed, fram: d.fram, nvs: d.nvs, powered: d.powered && d !== station,
                                         inputs: { ...d.inputs }, kiss: !!d.kissMode })),
    post: { seed: world.post.seed, disk: world.post.disk, stations: world.post.state().stations },
  };
}

export class Simulation {
  // Przygotowanie sieci jak przed kryzysem (kilka sekund czasu ściennego), potem stacja wyłączona.
  static async prepare(options = {}) {
    const world = await prepareNetwork(options);
    const station = world.devices[1];
    // Stacja poznaje trasę do stanowiska z ogłoszenia przekazanego przez węzeł (trasy w FRAM stacji),
    // a stanowisko poznaje tożsamość stacji z jej ogłoszenia (znane tożsamości na dysku komputera).
    await world.advance(30e6);
    for (let i = 0; i < 180 && world.post.state().stations.length < world.devices.length - 1; i++) await world.advance(10e6);
    if (world.post.state().stations.length < world.devices.length - 1) throw new Error("stanowisko nie usłyszało ogłoszeń stacji");
    station.powerOff();
    return new Simulation(capture(world, station));
  }

  constructor(image) {
    this.image = image;
    this.world = null;
    this.listeners = [];
  }

  async reset() {
    const img = this.image;
    const world = new World(img.seed);
    world.nowUs = img.nowUs;
    world.rngState = img.rng;
    world.post = new Post(img.post.seed);
    world.post.disk = new Uint8Array(img.post.disk);
    await world.post.start(world.nowUs);
    for (const spec of img.devices) {
      const d = world.add(new Device(spec.name, spec.seed));
      d.fram = new Uint8Array(spec.fram);
      d.nvs = spec.nvs;
      d.inputs = { ...spec.inputs };
      if (spec.powered) await d.powerOn(world.nowUs);
      d.kissMode = spec.kiss;
      if (spec.kiss) d.setUsb(1, true);
    }
    world.node = world.devices[0];
    world.on((source, e) => this.emit({ ...e, source: source.name }));
    this.world = world;
    world.post.run(world.nowUs + 1000);
    world.post.cmd("port open");
    for (const address of img.post.stations ?? []) world.post.cmd(`station ${address}`);   // wykaz stacji stanowiska
    await world.advance(200000);
    return this;
  }

  get station() { return this.world.devices[1]; }
  get node() { return this.world.devices[0]; }
  get post() { return this.world.post; }
  get nowUs() { return this.world.nowUs; }

  on(fn) { this.listeners.push(fn); }
  emit(e) { for (const fn of this.listeners) fn(e); }

  // Zdarzenia płytek (dioda, brzęczyk, ekran) i aplikacji stanowiska od ostatniego odczytu.
  takeEvents() {
    const out = [];
    for (const d of this.world.devices) for (const e of d.takeEvents()) out.push({ ...e, source: d.name });
    for (const e of JSON.parse(this.post.cmd("log"))) out.push({ ...e, source: "stanowisko", t: e.t * 1000 + this.post.bootUs });
    return out;
  }

  async advance(us) { await this.world.advance(us); }

  // Numery pinów panelu z board.h (te same na każdej płytce N1; węzeł jest zawsze włączony).
  get pins() { return this.node.pins; }

  // ---- obsługa stacji ----

  setButton(button, down) { this.station.setInput(this.pins[button], down ? 0 : 1); }

  // Naciśnięcie w działaniach ćwiczeń: przytrzymanie co najmniej `ms` i do trzech odczytów pinu przez
  // program (eliminacja drgań: dwie próbki co 10 ms), potem tak samo zwolnienie i czas na odświeżenie
  // ekranu. Pętla stacji stoi w czasie nadawania ramki i rysowania ekranu, więc krótkie naciśnięcie
  // człowieka może wtedy przepaść jak na płytce; skrypt naciska jak ktoś, kto patrzy na reakcję.
  async sampled(pin, ms) {
    const st = this.station;
    const reads = () => (st.powered ? Number(st.cmd(`reads ${pin}`)) : 0);
    const start = reads();
    for (let t = 0; t < ms || (st.powered && reads() - start < 3 && t < 5000); t += 10) await this.advance(10000);
  }

  async hold(button, ms) {
    const pin = this.pins[button];
    this.setButton(button, true);
    await this.sampled(pin, ms);
    this.setButton(button, false);
    await this.sampled(pin, 300);
  }

  async press(button, ms = 120) { await this.hold(button, ms); }

  // Przełącznik CISZA: zwarcie do masy = cisza (board_bench_b.h, SW_SILENCE).
  setSwitch(silence) { this.station.setInput(this.pins.SILENCE, silence ? 0 : 1); }
  switchOn() { return this.station.inputs[this.pins.SILENCE] === 0; }

  async power(on) {
    const st = this.station;
    if (on && !st.powered) await st.powerOn(this.nowUs);
    if (!on && st.powered) st.powerOff();
  }

  screen() {
    const st = this.station;
    if (!st.powered) return { on: false, lines: ["", "", "", "", ""], inverted: [false, false, false, false, false] };
    return JSON.parse(st.cmd("screen"));
  }

  postState() { return this.post.state(); }

  // Tłumienie trasy stacja–węzeł [dB] (Infinity: brak łączności).
  setLoss(db) { this.world.setLoss(this.station, this.node, db); }
  loss() { return this.world.lossOf(this.station, this.node); }

  // ---- język działań ćwiczeń (przygotowanie i przykładowe przebiegi) ----
  // press B [ms] | hold B ms | wait s | power on|off | switch on|off | link up|down | loss dB |
  // fault radio|fram on|off | post <polecenie aplikacji stanowiska> (np. decide last 3, bulletin tekst) | boot
  async act(line) {
    const [cmd, ...args] = line.split(" ");
    const rest = args.join(" ");
    switch (cmd) {
      case "press": await this.press(args[0], Number(args[1] ?? 120)); break;
      case "hold": await this.hold(args[0], Number(args[1])); break;
      case "wait": await this.advance(Number(args[0]) * 1e6); break;
      case "power": await this.power(args[0] === "on"); await this.advance(200000); break;
      case "switch": this.setSwitch(args[0] === "on"); await this.advance(200000); break;
      case "link": this.setLoss(args[0] === "down" ? Infinity : this.world.defaultLoss); break;
      case "loss": this.setLoss(Number(args[0])); break;
      case "fault": this.station.fault(args[0], args[1] === "on"); break;
      case "post": {
        const latest = this.postState().requests.filter((r) => r.type === "request").at(-1);
        const out = this.post.cmd(rest.replace(/\blast\b/, latest ? String(latest.number) : "0"));
        if (out.startsWith("err")) throw new Error(`post ${rest}: ${out}`);
        break;
      }
      case "boot":
        // Włączenie i start bez TEST: język, adres, WSTECZ przy propozycji TEST.
        await this.act("power on");
        await this.advance(1500000);
        for (const b of ["OK", "OK", "BACK"]) await this.press(b);
        await this.advance(5e6);
        break;
      default: throw new Error(`nieznane działanie: ${line}`);
    }
  }
}

export { Device };

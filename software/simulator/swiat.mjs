// SPDX-License-Identifier: MIT
// Świat symulatora jako osobny proces w czasie rzeczywistym (README, „Osobne elementy”): stacje, węzeł
// stanowiska z komputerem stanowiska i eter z web/world.js. Port danych USB każdej stacji jest na porcie
// TCP, tak jak przewód USB do laptopa, a strona świata (swiat.html) pokazuje ekrany stacji i ma ich
// przyciski, przycisk przygotowania, wyłącznik, przełącznik CISZA i tłumienie trasy do węzła. Węzeł
// i stanowisko są przygotowane jak w terenie. Narzędzie deweloperskie i szkoleniowe, nie trafia na USB.
//
//   node software/simulator/swiat.mjs [--station konfiguracja.json]... [--stations N] [--port 7300]
//                                     [--http 7380] [--card karta.json] [--seed S]
//   python3 -m wici --port tcp:127.0.0.1:7300        (z katalogu software/laptop)
//
// --station: stacja skonfigurowana z pliku w formacie „Zapisz do pliku” panelu laptopa (dokument
// `configure`); kolejne stacje, w kolejności podania. --stations N: tyle stacji bez konfiguracji, po nich
// (domyślnie 1, gdy nie ma --station). Stacja k ma port danych <port> + k − 1; --port 0 i --http 0: wolne
// porty. --card zapisuje kartę odbiorcy stanowiska do wczytania w panelu laptopa; kod dostępu sieci
// ćwiczeniowej (IFAC) jest w pierwszym wierszu wyjścia. Stacja z innym kodem albo inną kartą odbiorcy
// nie dogada się ze stanowiskiem świata (ostrzeżenie przy starcie).
// Wyjście: `IFAC …`, `stacja <k> tcp:127.0.0.1:<port>`, `strona http://127.0.0.1:<port>/`, potem `gotowe`.
// Polecenia na stdin (k: numer stacji, domyślnie 1): prep [k], press [k] OK|BACK|UP|DOWN, screen [k],
// power [k] on|off, loss [k] <dB>|off, post, quit.
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import readline from "node:readline";
import { IFAC, prepareNetwork } from "./web/world.js";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
};
const files = args.flatMap((a, i) => (a === "--station" ? [args[i + 1]] : []));
const fresh = Number(opt("--stations", files.length ? 0 : 1));
const basePort = Number(opt("--port", 7300));
const httpPort = Number(opt("--http", 7380));
const cardPath = opt("--card", null);
const PRESS_US = 120000, PREP_US = 3200000, BUTTONS = ["UP", "DOWN", "OK", "BACK"];

const docs = files.map((f) => JSON.parse(fs.readFileSync(f, "utf8")));
const world = await prepareNetwork({ seed: Number(opt("--seed", 1)), stations: docs.length + fresh, configured: false });
const stations = world.devices.slice(1);
const cards = JSON.parse(world.post.cmd("card"));
console.log(`IFAC (kod dostępu sieci ćwiczeniowej): ${IFAC}`);
for (const [i, doc] of docs.entries()) {
  if (doc.ifac !== IFAC) console.log(`uwaga: ${files[i]}: inny kod dostępu sieci niż węzeł świata, stanowisko jej nie usłyszy`);
  if (doc.role === "stacja" && JSON.stringify(doc.receiver?.main) !== JSON.stringify(cards.main)) {
    console.log(`uwaga: ${files[i]}: inna karta odbiorcy niż stanowisko świata (--card)`);
  }
  await world.configure(stations[i], doc);
}
if (cardPath) {
  fs.writeFileSync(cardPath, JSON.stringify({ wici: "karta-odbiorcy", v: 1, ...cards }, null, 1) + "\n");
  console.log(`karta odbiorcy stanowiska: ${cardPath}`);
}

// Czas świata biegnie za zegarem ściennym; przyciski z poleceń puszcza się w zaplanowanej chwili.
const startWall = performance.now(), startUs = world.nowUs;
const releases = [];   // [czas świata µs, urządzenie, pin]
const links = stations.map(() => ({ socket: null, input: [], port: 0 }));
const servers = [], watchers = new Set();
let running = true;

function hold(device, pin, us) {
  device.setInput(pin, 0);
  releases.push([world.nowUs + us, device, pin]);
}

async function tick() {
  if (!running) return;
  const target = startUs + Math.floor((performance.now() - startWall) * 1000);
  while (world.nowUs < target) {
    const step = Math.min(target - world.nowUs, 10000);
    stations.forEach((d, i) => {
      for (const data of links[i].input.splice(0)) d.usbWrite(1, data);
    });
    await world.advance(step);
    for (let r = releases.length - 1; r >= 0; r--) {
      if (world.nowUs >= releases[r][0]) {
        releases[r][1].setInput(releases[r][2], 1);
        releases.splice(r, 1);
      }
    }
  }
  stations.forEach((d, i) => {
    const out = d.usbRead(1);
    if (out.length && links[i].socket) links[i].socket.write(Buffer.from(out));
  });
  setTimeout(tick, 5);
}

const listening = stations.map((d, i) => new Promise((resolve) => {
  const server = net.createServer((socket) => {
    const link = links[i];
    if (link.socket) { socket.destroy(); return; }   // jeden komputer naraz, jak jeden przewód
    link.socket = socket;
    socket.setNoDelay(true);
    d.usbRead(1);                                   // zaległe bajty poprzedniej sesji przepadają
    d.setUsb(1, true);
    socket.on("data", (data) => link.input.push(new Uint8Array(data)));
    const close = () => { if (link.socket === socket) { link.socket = null; link.input = []; d.setUsb(1, false); } };
    socket.on("close", close);
    socket.on("error", close);
  });
  servers.push(server);
  server.listen(basePort ? basePort + i : 0, "127.0.0.1", () => {
    links[i].port = server.address().port;
    console.log(`stacja ${i + 1} tcp:127.0.0.1:${links[i].port}`);
    resolve();
  });
}));
await Promise.all(listening);

// ---- strona świata: stan co 250 ms (EventSource), działania przez POST z JSON ---------------------

function screen(d) {
  if (!d.powered) return { on: false, lines: [], inverted: [] };
  return JSON.parse(d.cmd("screen"));
}

function snapshot() {
  return {
    seconds: Math.round((world.nowUs - startUs) / 1e6),
    stations: stations.map((d, i) => ({
      n: i + 1, port: links[i].port, laptop: Boolean(links[i].socket), powered: d.powered,
      silence: d.inputs[d.pins.SILENCE] === 0, loss: world.lossOf(d, world.node), screen: screen(d),
    })),
    post: world.post.state().stations.length,
  };
}

function act(body) {
  const d = stations[Number(body.station) - 1];
  if (!d) return false;
  const { action, value } = body;
  if (action === "button" && BUTTONS.includes(value?.button)) d.setInput(d.pins[value.button], value.down ? 0 : 1);
  else if (action === "prep") hold(d, d.pins.PREP, PREP_US);
  else if (action === "power" && value === false && d.powered) d.powerOff(world.nowUs);
  else if (action === "power" && value === true && !d.powered) d.powerOn(world.nowUs);
  else if (action === "silence") d.setInput(d.pins.SILENCE, value ? 0 : 1);
  else if (action === "loss") world.setLoss(d, world.node, value === null ? Infinity : Number(value));
  else return false;
  return true;
}

const page = fs.readFileSync(new URL("./swiat.html", import.meta.url));
const web = http.createServer((req, res) => {
  const local = /^(127\.0\.0\.1|localhost):\d+$/.test(req.headers.host ?? "");   // bez podszycia nazwą (DNS rebinding)
  if (!local) { res.writeHead(403).end(); return; }
  if (req.method === "GET" && req.url === "/") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" }).end(page);
  } else if (req.method === "GET" && req.url === "/events") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
    watchers.add(res);
    req.on("close", () => watchers.delete(res));
  } else if (req.method === "POST" && req.url === "/act" && req.headers["content-type"] === "application/json") {
    // Content-Type application/json wymusza zapytanie wstępne CORS, na które serwer nie odpowiada:
    // inna strona w tej samej przeglądarce nie naciśnie przycisków stacji.
    let body = "";
    req.on("data", (c) => { body += c; if (body.length > 4096) req.destroy(); });
    req.on("end", () => {
      let ok = false;
      try { ok = act(JSON.parse(body)); } catch { ok = false; }
      res.writeHead(ok ? 204 : 400).end();
    });
  } else {
    res.writeHead(404).end();
  }
});
servers.push(web);
await new Promise((resolve) => web.listen(httpPort, "127.0.0.1", resolve));
console.log(`strona http://127.0.0.1:${web.address().port}/`);
const push = setInterval(() => {
  if (!watchers.size) return;
  const data = `data: ${JSON.stringify(snapshot())}\n\n`;
  for (const res of watchers) res.write(data);
}, 250);

console.log("gotowe");
tick();

// Bez process.exit(): Node potrafi się na nim zakleszczyć (test_scenarios.mjs); pętla, serwery i gniazda
// się kończą, więc proces wychodzi sam.
function stop() {
  running = false;
  clearInterval(push);
  for (const res of watchers) res.end();
  for (const link of links) link.socket?.destroy();
  for (const server of servers) { server.close(); server.closeAllConnections?.(); }
  process.stdin.destroy();                          // otwarte stdin trzymałoby proces po `quit`
}

function station(word) {
  const numbered = /^\d+$/.test(word ?? "");
  return [stations[(numbered ? Number(word) : 1) - 1], numbered];
}

readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const words = line.trim().split(/\s+/);
  const [cmd] = words;
  const [device, numbered] = station(words[1]);
  const rest = words.slice(numbered ? 2 : 1);
  if (!device && cmd !== "post" && cmd !== "quit") return console.log("nie ma takiej stacji");
  if (cmd === "prep") {
    hold(device, device.pins.PREP, PREP_US);
    console.log("prep held");
  } else if (cmd === "press" && BUTTONS.includes(rest[0])) {
    hold(device, device.pins[rest[0]], PRESS_US);
    console.log("pressed");
  } else if (cmd === "screen") {
    console.log(JSON.stringify(screen(device)));
  } else if (cmd === "power" && (rest[0] === "on" || rest[0] === "off")) {
    act({ station: stations.indexOf(device) + 1, action: "power", value: rest[0] === "on" });
    console.log(`power ${rest[0]}`);
  } else if (cmd === "loss" && rest[0]) {
    world.setLoss(device, world.node, rest[0] === "off" ? Infinity : Number(rest[0]));
    console.log(`loss ${rest[0]}`);
  } else if (cmd === "post") {
    const s = world.post.state();
    console.log(JSON.stringify({ stations: s.stations, requests: s.requests }));
  } else if (cmd === "quit") {
    stop();
  } else {
    console.log("polecenia: prep [k], press [k] OK|BACK|UP|DOWN, screen [k], power [k] on|off, loss [k] dB|off, post, quit");
  }
}).on("close", stop);

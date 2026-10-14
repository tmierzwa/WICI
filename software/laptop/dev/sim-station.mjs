// SPDX-License-Identifier: MIT
// Stacja z symulatora (obraz bench-b w WebAssembly, software/simulator) z portem danych USB na TCP:
// do pracy nad aplikacją laptopa i do jej testów bez płytki. Narzędzie deweloperskie, nie trafia na USB.
//
//   node software/laptop/dev/sim-station.mjs [port TCP, domyślnie 7300; 0 = dowolny]
//   python3 -m wici --port tcp:127.0.0.1:7300        (z katalogu software/laptop)
//
// Zegar stacji biegnie w czasie rzeczywistym. Połączenie TCP = port otwarty przez komputer (DTR).
// Polecenia na stdin: `prep` (przytrzymanie przycisku przygotowania 3,2 s), `screen`, `state`, `quit`.
// Pierwszy wiersz na stdout: `listening <port>`.
import net from "node:net";
import readline from "node:readline";
import { Device } from "../../simulator/web/device.js";

const QUANTUM_US = 10000;
const device = new Device("stacja", Number(process.env.WICI_SIM_SEED || 1));
await device.powerOn(0);
const started = performance.now();
let nowUs = 0, client = null, holdUntil = 0;

function worldUs() { return Math.floor((performance.now() - started) * 1000); }

async function tick() {
  const target = worldUs();
  while (nowUs < target) {
    nowUs = Math.min(target, nowUs + QUANTUM_US);
    await device.run(nowUs);
    if (holdUntil && nowUs >= holdUntil) {
      device.setInput(device.pins.PREP, 1);
      holdUntil = 0;
    }
  }
  const out = device.usbRead(1);
  if (out.length && client) client.write(Buffer.from(out));
  setTimeout(tick, 5);
}

const server = net.createServer((socket) => {
  if (client) { socket.destroy(); return; }   // jeden komputer naraz, jak jeden przewód
  client = socket;
  socket.setNoDelay(true);
  device.usbRead(1);                           // zaległe bajty poprzedniej sesji przepadają
  device.setUsb(1, true);
  socket.on("data", (data) => device.usbWrite(1, new Uint8Array(data)));
  const close = () => { if (client === socket) { client = null; device.setUsb(1, false); } };
  socket.on("close", close);
  socket.on("error", close);
});

server.listen(Number(process.argv[2] ?? 7300), "127.0.0.1", () => {
  console.log(`listening ${server.address().port}`);
  tick();
});

readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const cmd = line.trim();
  if (cmd === "prep") {
    device.setInput(device.pins.PREP, 0);
    holdUntil = nowUs + 3200000;
    console.log("prep held");
  } else if (cmd === "screen") {
    console.log(device.cmd("screen"));
  } else if (cmd === "state") {
    console.log(device.cmd("state"));
  } else if (cmd === "quit") {
    process.exit(0);
  }
}).on("close", () => process.exit(0));

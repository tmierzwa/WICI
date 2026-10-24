// SPDX-License-Identifier: MIT
// Próba ćwiczeń na prawdziwym oprogramowaniu stacji (web/wici-station.mjs) i komputerze stanowiska
// (web/wici-post.mjs): każde ćwiczenie z web/scenarios.js przechodzi swoim przykładowym przebiegiem
// (`solution`) do końca, bez ostrzeżeń. Uruchamia tests/test_simulator.py.
// Użycie: node software/simulator/test_scenarios.mjs [id ćwiczenia ...]
import { Simulation } from "./web/sim.js";
import { SCENARIOS, Exercise } from "./web/scenarios.js";

const only = process.argv.slice(2);
const t0 = performance.now();
const sim = await Simulation.prepare({ seed: 3 });
console.log(`sieć przygotowana: ${(performance.now() - t0).toFixed(0)} ms`);
let failed = 0;
for (const scenario of SCENARIOS) {
  if (only.length && !only.includes(scenario.id)) continue;
  const t = performance.now();
  const ex = new Exercise(sim, scenario);
  await ex.start();
  for (const line of scenario.solution) {
    if (ex.finished) break;
    if (line.startsWith("wait ")) {
      let left = Number(line.slice(5));
      while (left > 0 && !ex.finished) {
        const chunk = Math.min(left, 5);
        await sim.act(`wait ${chunk}`);
        left -= chunk;
        await ex.update(ex.observe());
      }
      continue;
    }
    if (line.startsWith("view ")) ex.panel = line.slice(5);
    else await sim.act(line);
    if (line.startsWith("press")) ex.press();
    await ex.update(ex.observe());
  }
  const o = ex.observe();
  const wall = ((performance.now() - t) / 1000).toFixed(1);
  if (ex.finished && !ex.warnings.length) {
    console.log(`ok ${scenario.id}: ${ex.presses} naciśnięć, ${Math.round(ex.totalS)} s symulacji, ${wall} s`);
  } else {
    failed++;
    console.log(`FAIL ${scenario.id}: krok ${ex.index + 1}/${scenario.steps.length} ${ex.current?.pl ?? ""} (${wall} s)`);
    for (const w of ex.warnings) console.log(`  ostrzeżenie: ${w.pl}`);
    console.log(`  ekran: ${JSON.stringify(o.screen.lines)} zasilanie=${o.power} cisza=${o.switch}`);
    console.log(`  stanowisko: ${JSON.stringify(o.post.requests.map((r) => [r.number, r.type, r.category, r.people, r.urgency, r.revision, r.received_acked, r.state_acked, r.identity]))}`);
  }
}
// Bez process.exit(): Node potrafi się na nim zakleszczyć, gdy V8 kompiluje w tle
// (wątek kompilatora czeka na odśmiecanie, które ma zrobić kończący się wątek główny).
process.exitCode = failed ? 1 : 0;

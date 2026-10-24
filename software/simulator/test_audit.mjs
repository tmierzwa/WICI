// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { Simulation } from './web/sim.js';
import { SCENARIOS, wizard } from './web/scenarios.js';

const sim = await Simulation.prepare({ seed: 3 });
await sim.reset();
await sim.act('boot');
await sim.act('post auto 0 0 0 0');
for (const line of wizard({ category: 3, people: { value: 40 }, urgency: 1 })) await sim.act(line);
await sim.act('wait 60');
const request = () => sim.postState().requests.find(r => r.type === 'request');
const number = request().number;
const command = text => sim.post.cmd(text.replace('last', String(number)));
assert.match(command('decide last 5'), /^err/);
assert.notEqual(request().state, 5);
assert.equal(command('reply last Bezpieczna instrukcja'), 'ok');
assert.match(command('decide last 5'), /^err/, 'must wait until this instruction is delivered');
await sim.act('wait 90');
assert.equal(request().reply_acked, true);
assert.equal(command('decide last 5'), 'ok');
assert.equal(command('reply last Zmieniona instrukcja'), 'ok');
assert.equal(request().reply_acked, false, 'old receipt cannot cover a new reply');
assert.match(command('decide last 5'), /^err/);
console.log('ok refusal: missing, pending, delivered and replaced instruction');

// A new revision must not reuse the instruction for the preceding version.
const revise = SCENARIOS.find(s => s.id === 'revise');
await sim.reset();
for (const line of revise.setup) await sim.act(line);
const currentNumber = sim.postState().requests.find(r => r.type === 'request').number;
assert.equal(sim.post.cmd(`reply ${currentNumber} Instrukcja dla starej wersji`), 'ok');
await sim.act('wait 90');
for (const [i, line] of revise.solution.entries()) {
  if (i === 4) await sim.act('press DOWN'); // skip the newer incoming reply and open our request
  if (!line.startsWith('view ')) await sim.act(line);
}
const updated = sim.postState().requests.find(r => r.type === 'request');
assert.equal(updated.revision, 1);
assert.equal(updated.reply, '');
assert.match(sim.post.cmd(`decide ${currentNumber} 5`), /^err/);
console.log('ok refusal: instruction cannot be reused after revision');

// A refused request can be revised while its STATUS is still waiting for the route.
// Neither automatic STATUS replay nor a late receipt may carry refusal to that revision.
await sim.reset();
for (const line of revise.setup) await sim.act(line);
const refusedNumber = request().number;
assert.equal(sim.post.cmd(`reply ${refusedNumber} Instrukcja poprzedniej wersji`), 'ok');
await sim.act('wait 90');
assert.equal(request().reply_acked, true);
await sim.act('link down');
assert.equal(sim.post.cmd(`decide ${refusedNumber} 5`), 'ok');
for (const [i, line] of revise.solution.entries()) {
  if (i === 4) await sim.act('press DOWN');
  if (!line.startsWith('view ')) await sim.act(line);
}
await sim.act('link up');
await sim.act('wait 180');
assert.equal(request().revision, 1);
assert.equal(request().reply, '');
assert.equal(request().reply_acked, false);
assert.equal(request().state, 1, 'the new revision must await a new decision');
assert.notEqual(request().state_acked, 5, 'a receipt for the old revision must not confirm refusal of the new one');
assert.match(sim.post.cmd(`decide ${refusedNumber} 5`), /^err/);
await sim.act('wait 180');
assert.notEqual(request().state_acked, 5, 'retries must not replay refusal for the new revision');
assert.equal(sim.post.cmd(`reply ${refusedNumber} Instrukcja aktualnej wersji`), 'ok');
assert.match(sim.post.cmd(`decide ${refusedNumber} 5`), /^err/);
await sim.act('wait 90');
assert.equal(request().reply_acked, true);
assert.equal(sim.post.cmd(`decide ${refusedNumber} 5`), 'ok');
await sim.act('wait 90');
assert.equal(request().state_acked, 5);
console.log('ok refusal: revision clears refusal, rejects old receipts and requires a newly delivered instruction');

const observation = (lines = []) => ({ screen: { lines }, post: { requests: [
  { type: 'request', category: 3, state_acked: 3, number: 1234 },
] } });
const decision = SCENARIOS.find(s => s.id === 'request').steps.at(-1).done;
const context = {};
assert.equal(decision(observation(), context), false, 'transport status does not prove opening the message');
assert.equal(decision(observation(['POMOC SKIEROWANA']), context), false);
assert.equal(decision(observation(['ZAPISZ NUMER 1234']), context), true);
const inspect = revise.steps.at(-1).done;
assert.equal(inspect(observation()), false, 'must actually open the receiver panel');
assert.equal(inspect({ ...observation(), panel: 'rx' }), true);
const reply = SCENARIOS.find(s => s.id === 'reply').steps[0].done;
const replyContext = {};
assert.equal(reply(observation(['BRAK TRANSPORTU']), replyContext), false);
assert.equal(reply(observation(['JEŚLI DROGA BEZPIECZNA']), replyContext), true);
console.log('ok training: negative and positive interaction conditions');

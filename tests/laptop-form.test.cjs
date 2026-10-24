// SPDX-License-Identifier: MIT
// Run: node --test tests/laptop-form.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { TextEncoder } = require('node:util');
const source = fs.readFileSync(path.join(__dirname, '../software/laptop/wici/ui/app.js'), 'utf8');

function panel(entered, response) {
  const output = { downloads: [], sent: [], notices: [], results: [], focus: 0, elements: {} };
  const context = vm.createContext({ TextEncoder, setTimeout, clearTimeout,
    document: { addEventListener() {}, getElementById(id) { return output.elements[id] ||= {}; },
      querySelector() { return { focus() { output.focus++; } }; } },
    entered: structuredClone(entered), response, output,
  });
  vm.runInContext(source, context);
  vm.runInContext(`
    readForm = () => entered;
    api = async (route, body) => {
      if (route === '/api/config/check') {
        if (response === null) throw new Error('offline');
        return { ok: true, data: response };
      }
      output.sent.push({ route, body });
      return { ok: true, data: { config_seq: 1, sha256: '1234567890123456' } };
    };
    fillForm = doc => { entered = JSON.parse(JSON.stringify(doc)); };
    showProblems = () => {};
    showResult = (...args) => output.results.push(args);
    toast = text => output.notices.push(text);
    download = (name, doc) => output.downloads.push({ name, doc });
    needStation = () => true;
    configured = () => false;
    busy = async (button, fn) => fn();
    limits = { message: 256 };
  `, context);
  return { context, output, run: code => vm.runInContext(code, context) };
}
const config = { role: 'stacja', addresses: ['Szkoła'], phrases: [], stations: 2 };
const result = (doc = config, problems = []) => ({ doc, problems, size: 250, max: 7680 });

test('invalid configuration is neither exported nor sent', async () => {
  const p = panel(config, result(config, [{ field: 'addresses.0', message: 'za długie' }]));
  await p.run('saveFile()');
  await p.run('send({ preventDefault() {} })');
  assert.equal(p.output.downloads.length, 0);
  assert.equal(p.output.sent.length, 0);
  assert.equal(p.output.focus, 2);
});

test('failed validation never falls back to exporting raw form data', async () => {
  const p = panel(config, null);
  await p.run('saveFile()');
  assert.equal(p.output.downloads.length, 0);
  assert.match(p.output.notices[0], /Nie udało się sprawdzić/);
});

test('changed address is shown before export and requires another action', async () => {
  const p = panel({ ...config, addresses: ['Szko\u200bła'] }, result());
  await p.run('saveFile()');
  assert.equal(p.output.downloads.length, 0);
  assert.equal(p.run('readForm().addresses[0]'), 'Szkoła');
  assert.match(p.output.results[0][2].join(' '), /Adres 1: Szkoła/);
  await p.run('saveFile()');
  assert.equal(p.output.downloads.length, 1);
  assert.equal(p.output.downloads[0].doc.addresses[0], 'Szkoła');
});

test('changed phrase cannot be silently sent to the station', async () => {
  const doc = { ...config, phrases: [['Woda pitna', '', '']] };
  const p = panel({ ...config, phrases: [['Woda\npitna', '', '']] }, result(doc));
  await p.run('send({ preventDefault() {} })');
  assert.equal(p.output.sent.length, 0);
  assert.match(p.output.results[0][2].join(' '), /Fraza 1, PL: Woda pitna/);
  await p.run('send({ preventDefault() {} })');
  assert.equal(p.output.sent.length, 1);
  assert.equal(p.output.sent[0].body.doc.phrases[0][0], 'Woda pitna');
});

test('edits during validation invalidate the response', async () => {
  const p = panel(config, result());
  p.run(`api = async () => { entered = { ...entered, addresses: ['Inny adres'] }; return { ok: true, data: response }; };`);
  await p.run('saveFile()');
  assert.equal(p.output.downloads.length, 0);
});

test('unchanged valid configuration exports in a single action', async () => {
  const p = panel(config, result());
  await p.run('saveFile()');
  assert.equal(p.output.downloads.length, 1);
  assert.equal(p.output.results.length, 0);
});


test('changing the form hides a stale normalization or operation result', () => {
  const p = panel(config, result());
  p.run(`$("result").hidden = false; changed(); clearTimeout(checkTimer);`);
  assert.equal(p.output.elements.result.hidden, true);
  assert.equal(p.run('readForm().addresses[0]'), 'Szkoła');
  assert.equal(p.output.downloads.length, 0);
});

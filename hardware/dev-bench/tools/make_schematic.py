# SPDX-License-Identifier: MIT
"""Generate the carrier schematic, symbol subset, BOM and connection list.

usage: make_schematic.py <KiCad symbols dir>
Every connected pin gets a short wire and a net label; unused pins get a
no-connect flag. The schematic is generated from design.py, never edited by hand.
"""
from copy import deepcopy
import csv
import math
from pathlib import Path
import sys
import uuid

from design import PARTS, FLAGS, SIGNALS, ARDUINO_PIN, DEVKIT_GPIO, check
from sexpr import Atom as A, parse, dump, children, child, walk

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('9b1f0b57-36c4-4f4e-9d0c-2f6a1c8f2a10')
PROJECT = 'plytka-nosna'
LIB = None


def uid(name):
    """Give each design object a stable UUID."""
    return str(uuid.uuid5(NS, name))


def symbol(lib_id):
    """Resolve library inheritance while preserving child properties."""
    lib, name = lib_id.split(':')
    defs = {s[1]: s for s in children(parse((LIB / (lib + '.kicad_sym')).read_text()), 'symbol')}

    def resolve(key):
        own = deepcopy(defs[key])
        ext = children(own, 'extends')
        if not ext:
            return own
        base = resolve(ext[0][1])
        old = base[1]
        base[1] = key
        for s in children(base, 'symbol'):
            s[1] = key + s[1][len(old):]
        for p in children(own, 'property'):
            base[:] = [x for x in base if not (isinstance(x, list) and x[0] == 'property' and x[1] == p[1])]
            base.append(p)
        return base
    result = resolve(name)
    result[1] = lib_id
    return result


def effects(size=1.27, hide=False, justify=None):
    e = [A('effects'), [A('font'), [A('size'), size, size]]]
    if hide:
        e.append([A('hide'), A('yes')])
    if justify:
        e.append([A('justify'), A(justify)])
    return e


# Schematic grid: groups in columns, top to bottom (mm, multiples of 2.54).
GROUPS = [
    ['J1', 'J2', 'J3', 'J4'],
    ['J5', 'J6', 'JP1', 'JP2'],
    ['J9', 'J10', 'C1', 'C2', 'R11', 'R12', 'J11'],
    ['J7', 'C4', 'R13', 'J8', 'C3', 'J12', 'R14', 'R15', 'C5'],
    ['SW1', 'SW2', 'SW3', 'SW4', 'SW5', 'SW6', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10'],
    ['D1', 'R1', 'BZ1', 'R2', 'D2', 'Q1', 'R3', 'R4'],
    ['H%d' % i for i in range(1, 16)],
]


def layout(symbols):
    """Place groups in columns; height from the symbol's pin extent."""
    at = {}
    x = 30.48
    for group in GROUPS:
        y = 30.48
        for ref in group:
            p = next(q for q in PARTS if q['ref'] == ref)
            s = symbols[p['lib_id']]
            ys = [float(child(pin, 'at')[2]) for pin in walk(s) if pin and pin[0] == 'pin'] or [0]
            top, bottom = max(ys), min(ys)
            y += max(top, 2.54) + 7.62
            y = round(y / 2.54) * 2.54
            at[ref] = (x, y)
            y += -bottom + 7.62
        x += 76.2
    return at


def generate():
    root_id = uid('root')
    lib_ids = sorted({p['lib_id'] for p in PARTS} | {'power:PWR_FLAG'})
    symbols = {i: symbol(i) for i in lib_ids}
    at = layout(symbols)
    sch = [A('kicad_sch'), [A('version'), 20250114], [A('generator'), 'eeschema'],
           [A('uuid'), root_id], [A('paper'), 'A2'],
           [A('title_block'), [A('title'), 'WICI płytka nośna stanowiska N1'],
            [A('date'), '2026-10-07'], [A('rev'), 'N1'],
            [A('comment'), 1, 'Stanowisko A: nRF52840-DK + CC1120EM. Stanowisko B: ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2.'],
            [A('comment'), 2, 'Nigdy oba MCU ani oba moduły radiowe naraz. Bez toru RF i bez stabilizatora.'],
            [A('comment'), 3, 'Generowane z tools/design.py; nie edytować ręcznie.']],
           [A('lib_symbols'), *symbols.values()]]
    items = [dict(p, at=at[p['ref']]) for p in PARTS]
    fx = 30.48 + 76.2 * len(GROUPS)
    for i, net in enumerate(FLAGS):
        items.append(dict(ref=f'#FLG{i + 1}', lib_id='power:PWR_FLAG', value='PWR_FLAG', footprint='',
                          nets={'1': net}, at=(fx, 30.48 + 15.24 * i), bom=False))
    for p in items:
        s = symbols[p['lib_id']]
        pins = [x for x in walk(s) if x and x[0] == 'pin']
        numbers = {child(x, 'number')[1] for x in pins}
        if not set(p['nets']) <= numbers:
            raise ValueError(f"{p['ref']}: missing pins {set(p['nets']) - numbers}")
        x, y = p['at']
        flag = p['ref'].startswith('#')
        inst = [A('symbol'), [A('lib_id'), p['lib_id']], [A('at'), x, y, 0], [A('unit'), 1],
                [A('exclude_from_sim'), A('no')],
                [A('in_bom'), A('yes' if p.get('bom', True) and not flag else 'no')],
                [A('on_board'), A('no' if flag else 'yes')], [A('dnp'), A('no')],
                [A('uuid'), uid(p['ref'])]]
        props = [('Reference', p['ref'], False), ('Value', p['value'], False),
                 ('Footprint', p['footprint'], True), ('Datasheet', '', True)]
        if not flag:
            props += [('Manufacturer', p.get('manufacturer', ''), True), ('MPN', p.get('mpn', ''), True),
                      ('Variant', {'A': 'tylko A', 'B': 'tylko B', 'AB': 'A i B'}[p['variant']], True)]
        ys = [float(child(pin, 'at')[2]) for pin in pins] or [0]
        for k, (name, value, hidden) in enumerate(props):
            dy = -max(max(ys), 2.54) - 5.08 + 2.54 * min(k, 1) if not hidden else 0
            inst.append([A('property'), name, value, [A('at'), x, round(y + dy, 4), 0], effects(1.27, hidden)])
        for num in sorted(numbers, key=lambda n: (len(n), n)):
            inst.append([A('pin'), num, [A('uuid'), uid(f"{p['ref']}.pin.{num}")]])
        inst.append([A('instances'), [A('project'), PROJECT,
                     [A('path'), '/' + root_id, [A('reference'), p['ref']], [A('unit'), 1]]]])
        sch.append(inst)
        seen = {}
        for pin in pins:
            num = child(pin, 'number')[1]
            px, py, angle = map(float, child(pin, 'at')[1:])
            gx, gy = round(x + px, 4), round(y - py, 4)
            if num not in p['nets']:
                sch.append([A('no_connect'), [A('at'), gx, gy], [A('uuid'), uid(f"{p['ref']}.nc.{num}")]])
                continue
            net = p['nets'][num]
            if (gx, gy) in seen:
                if seen[gx, gy] != net:
                    raise ValueError('stacked pin net mismatch')
                continue
            seen[gx, gy] = net
            ex = round(gx - 5.08 * math.cos(math.radians(angle)), 4)
            ey = round(gy + 5.08 * math.sin(math.radians(angle)), 4)
            sch.append([A('wire'), [A('pts'), [A('xy'), gx, gy], [A('xy'), ex, ey]],
                        [A('stroke'), [A('width'), 0], [A('type'), A('default')]],
                        [A('uuid'), uid(f"{p['ref']}.wire.{num}")]])
            rot = {0: 180, 180: 0, 90: 270, 270: 90}[int(angle)]
            sch.append([A('label'), net, [A('at'), ex, ey, rot],
                        effects(1.27, justify='right' if rot in (180, 90) else 'left'),
                        [A('uuid'), uid(f"{p['ref']}.label.{num}")]])
    (ROOT / 'cad' / f'{PROJECT}.kicad_sch').write_text(dump(sch) + '\n')
    # Symbol subset and table
    grouped = {}
    for lib_id, s in symbols.items():
        lib, name = lib_id.split(':')
        libsym = deepcopy(s)
        libsym[1] = name
        grouped.setdefault(lib, []).append(libsym)
    (ROOT / 'cad/symbols').mkdir(parents=True, exist_ok=True)
    for lib, defs in grouped.items():
        (ROOT / 'cad/symbols' / (lib + '.kicad_sym')).write_text(dump(
            [A('kicad_symbol_lib'), [A('version'), 20251024], [A('generator'), 'kicad_symbol_editor'], *defs]) + '\n')
    table = [A('sym_lib_table'), [A('version'), 7]]
    for lib in sorted(grouped):
        table.append([A('lib'), [A('name'), lib], [A('type'), 'KiCad'],
                      [A('uri'), '${KIPRJMOD}/symbols/' + lib + '.kicad_sym'], [A('options'), ''],
                      [A('descr'), 'KiCad 10.0.6 subset, see KICAD-LIBRARY-LICENSE.md']])
    (ROOT / 'cad/sym-lib-table').write_text(dump(table) + '\n')
    write_bom()
    write_connections()
    print(f'{len(PARTS)} board items; schematic written')


def write_bom():
    rows = [p for p in PARTS if p['bom']]
    groups = {}
    for p in rows:
        groups.setdefault((p['manufacturer'], p['mpn'], p['value'] if p['ref'][0] in 'RC' else '',
                           p['footprint'], p['variant']), []).append(p)
    with (ROOT / 'bom.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['oznaczenia', 'ilość', 'wartość', 'producent', 'MPN', 'specyfikacja', 'footprint',
                    'stanowisko', 'uwagi'])
        for key, items in groups.items():
            p = items[0]
            refs = [i['ref'] for i in items]
            qty = len(items)
            if p['mpn'] == 'Adafruit 85':
                qty = 1  # one kit covers J1-J4
            w.writerow([' '.join(refs), qty, p['value'], p['manufacturer'], p['mpn'], p['spec'],
                        p['footprint'], {'A': 'A', 'B': 'B', 'AB': 'A i B'}[p['variant']], p['note']])


def write_connections():
    by_net = {}
    for p in PARTS:
        for pin, net in p['nets'].items():
            by_net.setdefault(net, []).append(f"{p['ref']}.{pin}")
    lines = ['# WICI: połączenia płytki nośnej N1', '',
             'Plik generuje `tools/make_schematic.py` z `tools/design.py`; nie edytować ręcznie. '
             'Opis płytki, stanowisk i przypisania: [płytka nośna](plytka-nosna.md).', '',
             '## Sygnały MCU', '',
             '| Sieć | Arduino (złącze.pin) | nRF52840 (A) | ESP32-S3 (B, złącze.pin) | Pozostałe piny sieci |',
             '|---|---|---|---|---|']
    for net, ard, nrf, gpio in SIGNALS:
        c = ARDUINO_PIN[ard]
        dk = next(f'{r}.{n}' for (r, n), g in DEVKIT_GPIO.items() if g == gpio)
        rest = [m for m in by_net[net] if m not in (f'{c[0]}.{c[1]}', dk)]
        lines.append(f'| {net} | {ard} ({c[0]}.{c[1]}) | {nrf} | {gpio} ({dk}) | {", ".join(rest)} |')
    lines += ['', '## Wszystkie sieci', '', '| Sieć | Piny |', '|---|---|']
    for net in sorted(by_net):
        lines.append(f'| {net} | {", ".join(by_net[net])} |')
    lines += ['', '## Złącza', '']
    for p in PARTS:
        if not p['ref'].startswith('J'):
            continue
        lines += [f"### {p['ref']}: {p['value']}", '', f"{p['note']}" if p['note'] else '', '',
                  '| Pin | Sieć |', '|---:|---|']
        count = {'Conn_01x08': 8, 'Conn_01x06': 6, 'Conn_01x10': 10, 'Conn_01x09': 9, 'Conn_01x22': 22,
                 'Conn_02x10_Odd_Even': 20, 'Conn_01x02': 2, 'Screw_Terminal_01x02': 2}[p['lib_id'].split(':')[1]]
        for n in range(1, count + 1):
            extra = DEVKIT_GPIO.get((p['ref'], n))
            net = p['nets'].get(str(n), '—')
            lines.append(f"| {n} | {net}{f' ({extra})' if extra else ''} |")
        lines.append('')
    (ROOT / 'polaczenia.md').write_text('\n'.join(l for l in lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    check()
    LIB = Path(sys.argv[1])
    generate()

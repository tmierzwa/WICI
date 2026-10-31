# SPDX-License-Identifier: MIT
"""Generate the preliminary v2 schematic, symbol subset, BOM and connection list from design.py.

usage: make_schematic.py <KiCad symbols dir>
Same scheme as hardware/dev-bench/tools/make_schematic.py: every connected pin gets a short wire and a
net label, unused pins a no-connect flag. Never edited by hand.
"""
from copy import deepcopy
import csv
import math
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT.parent / 'dev-bench' / 'tools'))  # sexpr only; design must stay this board's
from sexpr import Atom as A, parse, dump, children, child, walk  # noqa: E402
from design import PARTS, FLAGS, SIGNALS, DEVKIT_GPIO, EXTRAS, check  # noqa: E402

NS = uuid.UUID('4d0c3a2e-8b1f-4f7e-9a51-6c2b7e0d9f31')
PROJECT = 'plytka-v2'
LIB = None


def uid(name):
    return str(uuid.uuid5(NS, name))


# Own symbols (library WICI). Pin numbers and names from the data sheets named in design.py.
def own_symbol(name, description, footprint, left, right, top=(), bottom=()):
    """Rectangle symbol; left/right/top/bottom are lists of (kind, name, number); '' leaves a gap."""
    rows = max(len(left), len(right), 1)
    h = 2.54 * (rows + 1)
    w = 2.54 * max(6, 2 * max(len(top), len(bottom)) + 2)
    pins = []
    for side, items in (('L', left), ('R', right)):
        for i, item in enumerate(items):
            if not item:
                continue
            kind, pname, num = item
            y = round(h / 2 - 2.54 * (i + 1), 2)
            x, rot = (-w / 2 - 2.54, 0) if side == 'L' else (w / 2 + 2.54, 180)
            pins.append((kind, x, y, rot, pname, num))
    for side, items in (('T', top), ('B', bottom)):
        for i, (kind, pname, num) in enumerate(items):
            x = round(-2.54 * (len(items) - 1) + 5.08 * i, 2)
            y, rot = (h / 2 + 2.54, 270) if side == 'T' else (-h / 2 - 2.54, 90)
            pins.append((kind, x, y, rot, pname, num))
    body = ' '.join(
        f'(pin {k} line (at {x} {y} {r}) (length 2.54) (name "{n}" (effects (font (size 1.27 1.27)))) '
        f'(number "{num}" (effects (font (size 1.27 1.27)))))' for k, x, y, r, n, num in pins)
    return (f'(symbol "{name}" (exclude_from_sim no) (in_bom yes) (on_board yes) '
            f'(property "Reference" "U" (at {-w / 2} {h / 2 + 1.27} 0) (effects (font (size 1.27 1.27)) (justify left))) '
            f'(property "Value" "{name}" (at {-w / 2} {-h / 2 - 1.27} 0) (effects (font (size 1.27 1.27)) (justify left))) '
            f'(property "Footprint" "{footprint}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(property "Description" "{description}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))) '
            f'(symbol "{name}_0_1" (rectangle (start {-w / 2} {h / 2}) (end {w / 2} {-h / 2}) '
            f'(stroke (width 0.254) (type default)) (fill (type background)))) '
            f'(symbol "{name}_1_1" {body}))')


P, I, O, W = 'passive', 'input', 'output', 'power_in'
OWN_SYMBOLS = '(kicad_symbol_lib ' + ' '.join([
    # TI SNVSB03E figure 5-2 (DBV): as hardware/dev-bench.
    own_symbol('TPS3840PH', 'Supervisor, push-pull active-high RESET, SOT-23-5', 'Package_TO_SOT_SMD:SOT-23-5',
               [(I, 'MR', 4), (P, 'CT', 5)], [(O, 'RESET', 1)], [(W, 'VDD', 2)], [(W, 'GND', 3)]),
    # TI SNOSD95C table 6-1 (DRR-12): RTN (thermal pad, 13) stays floating.
    own_symbol('LM74800-Q1', 'Ideal diode and load switch controller, 3-65 V, WSON-12',
               'Package_SON:WSON-12-1EP_3x3mm_P0.5mm_EP1.5x2.5mm',
               [(P, 'A', 2), (P, 'VSNS', 3), (P, 'SW', 4), (I, 'OV', 5), (I, 'EN/UVLO', 6), '', (P, 'RTN', 13)],
               [(O, 'DGATE', 1), (P, 'C', 12), (W, 'VS', 10), (P, 'CAP', 11), (O, 'HGATE', 8), (P, 'OUT', 9)],
               bottom=[(W, 'GND', 7)]),
    # ADI LTC2955 rev. A page 3, TS8 package.
    own_symbol('LTC2955-2', 'Pushbutton on/off controller, active-low enable, TSOT-23-8', 'Package_TO_SOT_SMD:TSOT-23-8',
               [(I, 'PB', 5), (I, 'ON', 1), (I, 'KILL', 2), (P, 'TMR', 3)], [(O, '~{EN}', 7), (O, 'INT', 8)],
               [(W, 'VIN', 6)], [(W, 'GND', 4)]),
    # ADI LTC3115-1 rev. C, pin functions, FE20 (same pin map as the JLC test board).
    own_symbol('LTC3115-1', '40 V buck-boost DC/DC, TSSOP-20 with exposed pad', 'WICI:LTC3115-1_FE20_CA',
               [(W, 'PVIN', 17), (W, 'VIN', 13), (I, 'RUN', 2), (I, 'PWM/SYNC', 19), (P, 'RT', 9), '',
                (P, 'VC', 7), (I, 'FB', 8)],
               [(P, 'SW1', 18), (P, 'BST1', 16), (P, 'SW2', 3), (P, 'BST2', 15), (P, 'PVOUT', 4), '',
                (P, 'PVCC', 14), (P, 'VCC', 12)],
               bottom=[(W, 'PGND', 1), (W, 'GND', 5), (W, 'GND', 6), (W, 'PGND', 10), (W, 'PGND', 11),
                       (W, 'PGND', 20), (W, 'PGND', 21)]),
    # SOIC-8 single N-MOSFET (AO4264E): S 1-3, G 4, D 5-8.
    own_symbol('NMOS_SO8', 'N-MOSFET, SOIC-8, S 1-3, G 4, D 5-8', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
               [(I, 'G', 4)], [(P, 'D', 5), (P, 'D', 6), (P, 'D', 7), (P, 'D', 8)],
               bottom=[(P, 'S', 1), (P, 'S', 2), (P, 'S', 3)]),
]) + ')'


def symbol(lib_id):
    """Resolve library inheritance while preserving child properties."""
    lib, name = lib_id.split(':')
    text = OWN_SYMBOLS if lib == 'WICI' else (LIB / (lib + '.kicad_sym')).read_text()
    defs = {s[1]: s for s in children(parse(text), 'symbol')}

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


# Columns by block, top to bottom.
GROUPS = [
    ['J2', 'F1', 'D4', 'U5', 'Q2', 'Q3', 'C30', 'C31', 'R30', 'R31', 'R32', 'C32'],
    ['Q4', 'R33', 'D5', 'R34', 'Q5', 'R35', 'R36', 'D15', 'R37', 'R38', 'R39', 'C33', 'D6'],
    ['J1', 'R40', 'D7', 'Q6', 'R41', 'Q7', 'R43', 'R44', 'R45', 'C34', 'D11', 'C50'],
    ['U6', 'J3', 'C37', 'R70', 'R71', 'C53', 'D13', 'D8', 'D9', 'R46', 'C35', 'D10', 'C36', 'R47', 'R48', 'D16', 'Q11', 'R72', 'Q8', 'R49', 'R50', 'D12'],
    ['U7', 'L2', 'C40', 'C41', 'C42', 'C43', 'C44', 'C45', 'C46', 'C47', 'R60', 'R61', 'R62', 'C48', 'C49',
     'R67', 'C51', 'R68', 'R63'],
    ['Q9', 'R51', 'Q10', 'R53', 'R54', 'D14', 'R55', 'C52', 'J4', 'R65', 'R66', 'U8', 'R73', 'R74', 'D17', 'Q12', 'R75'],
    ['J5', 'J6', 'R18', 'J8', 'J9', 'JP3', 'C1', 'C2', 'R11', 'R12', 'R64'],
    ['J7', 'C4', 'C6', 'C7', 'R13', 'R19', 'U2', 'L1', 'C8', 'C9', 'R21', 'R22', 'C10'],
    ['U1', 'C3', 'R20', 'U4', 'C11', 'U3', 'C12', 'C13'],
    ['SW1', 'SW2', 'SW3', 'SW4', 'SW5', 'SW6', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R16'],
    ['D1', 'R1', 'BZ1', 'R2', 'D2', 'Q1', 'R3', 'R4', 'H1', 'H2', 'H3', 'H4'],
]


def pin_ys(s):
    return [float(child(pin, 'at')[2]) for pin in walk(s) if pin and pin[0] == 'pin'] or [0]


def layout(symbols):
    at = {}
    x = 30.48
    for group in GROUPS:
        y = 30.48
        for ref in group:
            p = next(q for q in PARTS if q['ref'] == ref)
            ys = pin_ys(symbols[p['lib_id']])
            y += max(max(ys), 2.54) + 7.62
            y = round(y / 2.54) * 2.54
            at[ref] = (x, y)
            y += -min(ys) + 7.62
        x += 76.2
    return at


def generate():
    placed = [r for g in GROUPS for r in g]
    missing = {p['ref'] for p in PARTS} ^ set(placed)
    if missing or len(placed) != len(set(placed)):
        raise ValueError(f'schematic groups do not match design.py: {sorted(missing)}')
    root_id = uid('root')
    lib_ids = sorted({p['lib_id'] for p in PARTS} | {'power:PWR_FLAG'})
    symbols = {i: symbol(i) for i in lib_ids}
    at = layout(symbols)
    sch = [A('kicad_sch'), [A('version'), 20250114], [A('generator'), 'eeschema'],
           [A('uuid'), root_id], [A('paper'), 'A0'],
           [A('title_block'), [A('title'), 'WICI płytka v2 (stacja pilotażowa), schemat wstępny'],
            [A('date'), '2026-10-31'], [A('rev'), 'v2-wstępny'],
            [A('comment'), 1, 'ESP32-S3-DevKitC-1 v1.1 przez piny 3V3, Wio SX1262 na listwach, USB-C bez VBUS.'],
            [A('comment'), 2, 'Zasilanie: 4 × AA przez 1 Ω i Schottky, 12 V przez LM74800-Q1, LTC2955-2, LTC3115-1.'],
            [A('comment'), 3, 'Generowane z tools/design.py; nie edytować ręcznie. Nie zamawiać: schemat wstępny.']],
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
            props += [('Manufacturer', p.get('manufacturer', ''), True), ('MPN', p.get('mpn', ''), True)]
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
                if (gx, gy) not in seen:
                    sch.append([A('no_connect'), [A('at'), gx, gy], [A('uuid'), uid(f"{p['ref']}.nc.{num}")]])
                continue
            net = p['nets'][num]
            if (gx, gy) in seen:
                if seen[gx, gy] != net:
                    raise ValueError(f"{p['ref']}: stacked pin net mismatch")
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
    (ROOT / 'cad').mkdir(exist_ok=True)
    (ROOT / 'cad' / f'{PROJECT}.kicad_sch').write_text(dump(sch) + '\n')
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
                      [A('descr'), 'own symbols, CERN-OHL-P-2.0' if lib == 'WICI'
                       else 'KiCad 10.0.6 subset, see KICAD-LIBRARY-LICENSE.md']])
    (ROOT / 'cad/sym-lib-table').write_text(dump(table) + '\n')
    write_bom()
    write_connections()
    print(f'{len(PARTS)} items; schematic written')


def write_bom():
    groups = {}
    for p in (q for q in PARTS if q['bom']):
        groups.setdefault((p['manufacturer'], p['mpn'], p['value'] if p['ref'][0] in 'RC' else '',
                           p['footprint']), []).append(p)
    with (ROOT / 'bom.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['oznaczenia', 'ilość', 'wartość', 'producent', 'MPN', 'specyfikacja', 'footprint', 'uwagi'])
        for items in groups.values():
            p = items[0]
            notes = [i['note'] for i in items]
            note = notes[0] if len(set(notes)) == 1 else '; '.join(f"{i['ref']}: {i['note']}" for i in items if i['note'])
            w.writerow([' '.join(i['ref'] for i in items), len(items),
                        ' / '.join(dict.fromkeys(i['value'] for i in items)), p['manufacturer'], p['mpn'],
                        p['spec'], p['footprint'], note])
        for refs, qty, manufacturer, mpn, spec, note in EXTRAS:
            w.writerow([refs, qty, '', manufacturer, mpn, spec, 'bez footprintu', note])


def write_connections():
    by_net = {}
    for p in PARTS:
        for pin, net in p['nets'].items():
            by_net.setdefault(net, []).append(f"{p['ref']}.{pin}")
    lines = ['# WICI: połączenia płytki v2 (schemat wstępny)', '',
             'Plik generuje `tools/make_schematic.py` z `tools/design.py`; nie edytować ręcznie. '
             'Założenia i otwarte sprawy: [README](README.md).', '',
             '## Sygnały MCU (ESP32-S3-DevKitC-1 v1.1)', '',
             '| Sieć | GPIO (złącze.pin) | Rola | Pozostałe piny sieci |', '|---|---|---|---|']
    for net, gpio, role in SIGNALS:
        dk = next(f'{r}.{n}' for (r, n), g in DEVKIT_GPIO.items() if g == gpio)
        rest = [m for m in by_net[net] if m != dk]
        lines.append(f'| {net} | {gpio} ({dk}) | {role} | {", ".join(rest)} |')
    lines += ['', '## Wszystkie sieci', '', '| Sieć | Piny |', '|---|---|']
    for net in sorted(by_net):
        lines.append(f'| {net} | {", ".join(by_net[net])} |')
    (ROOT / 'polaczenia.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    check()
    LIB = Path(sys.argv[1])
    generate()

#!/usr/bin/env python3
"""RF_SW1 probe: one kit beacons, the other receives with RF_SW1 high, low and as after reset.

The reset configuration is valid only after a power-on or USB-Serial-JTAG reset; on macOS
opening the port gives the latter, otherwise unplug and replug both kits.
Run from hardware/radio-pair (its .venv has pyserial):
  .venv/bin/python rfsw-probe/tools/rfsw_test.py --tx PORT_B --rx PORT_A
"""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'rfsw-0.3'
STATES = {'H': 'RF_SW1 wysoki', 'RH': 'jak po resecie, po H', 'L': 'RF_SW1 niski',
          'RL': 'jak po resecie, po L'}
# esp_rom_get_reset_reason(): both reset the digital GPIO and IO_MUX. On macOS opening the
# USB-Serial-JTAG port itself gives 21, which esp_reset_reason() in core 2.0.17 reports as 0.
CHIP_RESETS = {1: 'power-on', 21: 'USB-Serial-JTAG'}
CRC_ERROR = -7  # RadioLib RADIOLIB_ERR_CRC_MISMATCH
WINDOW_S = 1.5


def decode(line):
    parts = line.split()
    try:
        if parts[0] == 'INFO' and parts[1] == VERSION and len(parts) == 17:
            fields = dict(p.split('=', 1) for p in parts[5:])
            return {'kind': 'info', 'id': parts[2], 'ready': parts[3] == '1',
                    'reset': int(parts[4]), **fields}
        if parts[0] == 'INFO':
            return {'kind': 'error', 'message': 'Unexpected INFO (other program?): ' + line}
        if parts[0] == 'RX' and len(parts) == 5 and parts[1] in STATES and parts[4].startswith('RFSW'):
            return {'kind': 'rx', 'state': parts[1], 'rssi': float(parts[2]),
                    'snr': float(parts[3]), 'seq': int(parts[4][4:])}
        if parts[0] == 'MISS' and len(parts) == 2 and parts[1] in STATES:
            return {'kind': 'miss', 'state': parts[1]}
        if parts[0] == 'BAD' and len(parts) == 3 and parts[1] in STATES:
            return {'kind': 'bad', 'state': parts[1], 'code': int(parts[2])}
        if parts[0] == 'TX' and len(parts) == 3:
            return {'kind': 'tx', 'status': int(parts[1]), 'payload': parts[2]}
        if parts[0] == 'ERR':
            return {'kind': 'error', 'message': line}
    except (IndexError, ValueError):
        return {'kind': 'error', 'message': 'Malformed serial record: ' + line}
    if parts and parts[0] in ('RX', 'MISS', 'BAD', 'TX'):
        return {'kind': 'error', 'message': 'Malformed serial record: ' + line}
    return {'kind': 'other', 'message': line}


def windows(events):
    return [e for e in events if e['kind'] in ('rx', 'miss', 'bad')]


def summarize(events):
    """Per state: beacons received, misses, CRC errors, foreign packets, RSSI and SNR."""
    result = {}
    for state in STATES:
        mine = [e for e in events if e.get('state') == state]
        rx = [e for e in mine if e['kind'] == 'rx']
        bad = [e for e in mine if e['kind'] == 'bad']
        row = {'received': len(rx),
               'missed': sum(e['kind'] == 'miss' for e in mine),
               'crc': sum(e['code'] == CRC_ERROR for e in bad),
               'foreign': sum(e['code'] != CRC_ERROR for e in bad)}
        for key in ('rssi', 'snr'):
            values = [e[key] for e in rx]
            row[key] = ({'median': statistics.median(values), 'min': min(values), 'max': max(values)}
                        if values else None)
        result[state] = row
    return result


def grid_mismatches(events):
    """Windows that do not match the beacon counter: between two received beacons a and b
    there must be exactly b - a - 1 windows without a beacon (MISS or BAD)."""
    mismatches, last, empty = 0, None, 0
    for e in windows(events):
        if e['kind'] != 'rx':
            empty += 1
            continue
        if last is not None and e['seq'] - last - 1 != empty:
            mismatches += 1
        last, empty = e['seq'], 0
    return mismatches


def open_serial(path):
    """Avoid DTR/RTS reset pulses by setting both before opening native USB (as pair_test)."""
    import serial
    port = serial.Serial()
    port.port = path
    port.baudrate = 115200
    port.timeout = .1
    port.write_timeout = 2
    port.dtr = port.rts = False
    port.open()
    return port


class Lines:
    """Whole lines from a port; a read timeout never splits a record."""
    def __init__(self, port, log):
        self.port, self.log, self.buffer = port, log, b''

    def read(self):
        self.buffer += self.port.read(self.port.in_waiting or 1)
        lines = []
        while b'\n' in self.buffer:
            raw, self.buffer = self.buffer.split(b'\n', 1)
            line = raw.decode(errors='replace').strip()
            if line:
                self.log.append({'t': time.time(), 'port': self.port.port, 'line': line})
                lines.append(line)
        return lines


def ask_info(lines):
    """Opening the port resets the kit: its boot INFO and the reply to INFO may both arrive,
    so after the first one the port is drained for a second before the test starts."""
    lines.port.write(b'INFO\n')
    found, deadline = None, time.time() + 3
    while time.time() < deadline:
        for line in lines.read():
            event = decode(line)
            if event['kind'] == 'error':
                raise OSError(f'{lines.port.port}: {event["message"]}')
            if event['kind'] == 'info' and found is None:
                found, deadline = event, time.time() + 1
    if found is None:
        raise OSError(f'{lines.port.port}: no INFO {VERSION}; flash rfsw-probe first')
    return found


def measure(tx, rx, count, info, events):
    if info['tx']['id'] == info['rx']['id']:
        raise ValueError('--tx and --rx are the same board')
    i = info['rx']
    print(f"RX {i['id']}: GPIO38 po resecie mux={i['mux']} mcu_sel={i['mcu_sel']} ie={i['ie']} "
          f"pu={i['pu']} pd={i['pd']} oe={i['oe']}; odczyt z podciąganiem w górę {i['up']}, w dół "
          f"{i['down']}, bez sterowania po stanie wysokim {i['fh']}, po niskim {i['fl']}")
    if i['reset'] not in CHIP_RESETS:
        raise OSError(f"{rx.port.port}: reset {i['reset']}, nie po włączeniu zasilania ani przez USB; "
                      'odłącz i podłącz USB odbiornika, potem uruchom ponownie')
    rx.port.write(b'RECEIVE\n')
    tx.port.write(b'BEACON\n')
    want = count * len(STATES)
    deadline = time.time() + want * WINDOW_S + 30
    while len(windows(events)) < want:
        if time.time() > deadline:
            raise OSError('Przekroczony czas próby; sprawdź nadajnik i odległość')
        for lines in (rx, tx):
            for line in lines.read():
                event = decode(line)
                if event['kind'] == 'info':
                    raise OSError(f'{lines.port.port}: płytka zrestartowała się w trakcie próby')
                if event['kind'] == 'error' or (event['kind'] == 'tx' and event['status']):
                    raise OSError(f'{lines.port.port}: {event.get("message", line)}')
                if lines is rx and event['kind'] in ('rx', 'miss', 'bad'):
                    events.append(event)


def stop(port):
    try:
        port.write(b'STOP\n')
    except OSError:
        pass
    finally:
        port.close()


def run(args):
    log, events, info, error = [], [], {}, None
    tx = rx = None
    try:
        tx, rx = Lines(open_serial(args.tx), log), Lines(open_serial(args.rx), log)
        info = {'tx': ask_info(tx), 'rx': ask_info(rx)}
        measure(tx, rx, args.count, info, events)
    except (ValueError, OSError) as exc:
        error = str(exc)
    finally:
        for lines in (tx, rx):
            if lines:
                stop(lines.port)
    summary = summarize(events)
    mismatches = grid_mismatches(events)
    for state, row in summary.items():
        rssi, snr = row['rssi'], row['snr']
        stats = (f"RSSI mediana {rssi['median']:.1f} ({rssi['min']:.1f}..{rssi['max']:.1f}) dBm, "
                 f"SNR mediana {snr['median']:.1f} ({snr['min']:.1f}..{snr['max']:.1f}) dB") if rssi else 'brak odbioru'
        print(f"{state} {STATES[state]}: odebrane {row['received']}, brak {row['missed']}, "
              f"CRC {row['crc']}, obce {row['foreign']}; {stats}")
    print(f'Okna niezgodne z licznikiem pakietów: {mismatches}')
    if log:
        args.output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        name = info.get('rx', {}).get('id', 'unknown')
        path = args.output / f'rfsw-{stamp}-{name}.json'
        path.write_text(json.dumps({'version': VERSION, 'notes': args.notes, 'completed': error is None,
                                    'error': error, 'info': info, 'summary': summary,
                                    'grid_mismatches': mismatches, 'log': log},
                                   indent=1, ensure_ascii=False))
        print(f'Raport: {path}')
    if error:
        raise OSError(error)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tx', required=True, help='port of the beaconing kit')
    parser.add_argument('--rx', required=True, help='port of the receiving kit')
    parser.add_argument('--count', type=int, default=50, help='windows per state')
    parser.add_argument('--notes', default='')
    parser.add_argument('--output', type=Path, default=Path('results'))
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, ImportError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

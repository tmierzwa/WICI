#!/usr/bin/env python3
"""One Mac, two USB ports; no retransmission, session-specific exact payloads."""
import argparse
import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROFILE = ['869.525', '125', '7', '5', '0', '1.8']


def decode(line):
    parts = line.split()
    try:
        if parts[0] == 'INFO' and len(parts) == 12:
            return {'kind': 'info', 'version': parts[1], 'id': parts[2],
                    'ready': parts[3] == '1', 'reset': int(parts[4]),
                    'boot': parts[5], 'profile': parts[6:]}
        if parts[0] == 'TX' and len(parts) == 3:
            return {'kind': 'tx', 'status': int(parts[1]), 'payload': parts[2]}
        if parts[0] == 'RX' and len(parts) == 4:
            return {'kind': 'rx', 'rssi': float(parts[1]), 'snr': float(parts[2]),
                    'payload': parts[3]}
        if parts[0] == 'ERR':
            return {'kind': 'error', 'message': line}
    except (IndexError, ValueError):
        pass
    return {'kind': 'other', 'message': line}


def judge(events, sender, payload):
    receiver = 'B' if sender == 'A' else 'A'
    tx = [e for node, e in events if node == sender and e['kind'] == 'tx'
          and e['payload'] == payload]
    rx = [e for node, e in events if node == receiver and e['kind'] == 'rx'
          and e['payload'] == payload]
    errors = [e for _, e in events if e['kind'] == 'error']
    return {'ok': len(tx) == 1 and tx[0]['status'] == 0 and len(rx) == 1 and not errors,
            'tx_records': len(tx), 'rx_records': len(rx),
            'tx_status': tx[0]['status'] if tx else None,
            'rssi': rx[0]['rssi'] if rx else None,
            'snr': rx[0]['snr'] if rx else None, 'errors': errors}


def run(args):
    import serial
    from serial.tools import list_ports
    if args.list:
        ports = [p for p in list_ports.comports() if p.device.startswith('/dev/cu.usb')]
        for port in ports:
            print(f'{port.device} | {port.description} | {port.hwid}')
        if not ports:
            print('Brak urządzeń USB. Podłącz jeden zestaw przewodem z transmisją danych.')
        return 0
    if not args.a or not args.b or args.a == args.b:
        raise ValueError('Podaj dwa różne porty: --a /dev/cu... --b /dev/cu...')
    if not 1 <= args.count <= 100:
        raise ValueError('--count musi wynosić od 1 do 100.')
    args.output.mkdir(parents=True, exist_ok=True)
    session = uuid.uuid4().hex[:16]
    base = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-') + session)
    events = queue.Queue()
    stop = threading.Event()
    ports = {}
    report = {'session': session, 'started_utc': datetime.now(timezone.utc).isoformat(),
              'hardware_test': True, 'requested_each_direction': args.count,
              'ports': {'A': args.a, 'B': args.b}, 'nodes': {}, 'packets': [],
              'passed': False, 'completed': False, 'issues': []}
    raw = base.with_suffix('.jsonl').open('w', encoding='utf8')

    def reader(node, port):
        try:
            while not stop.is_set():
                data = port.readline()
                if data:
                    events.put((node, data.decode('ascii', errors='replace').strip()))
        except serial.SerialException as exc:
            events.put((node, 'ERR disconnected ' + str(exc)))

    def collect(seconds):
        batch = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                node, line = events.get(timeout=min(.1, max(.001, deadline-time.monotonic())))
            except queue.Empty:
                continue
            raw.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(),
                                  'node': node, 'line': line}) + '\n')
            raw.flush()
            item = decode(line)
            batch.append((node, item))
            if item['kind'] == 'error':
                report['issues'].append({'node': node, 'error': line})
            if item['kind'] == 'info' and node in report['nodes']:
                original = report['nodes'][node]
                if item != original:
                    raise RuntimeError(f'{node}: restart lub zmiana konfiguracji podczas testu.')
        return batch

    try:
        for node, path in report['ports'].items():
            port = serial.Serial()
            port.port, port.baudrate, port.timeout, port.write_timeout = path, 115200, .1, 2
            port.dtr = False
            port.rts = False
            port.open()
            ports[node] = port
            threading.Thread(target=reader, args=(node, port), daemon=True).start()
        collect(2)
        for port in ports.values():
            port.write(b'INFO\n')
        for node, item in collect(3):
            if item['kind'] == 'info':
                report['nodes'][node] = item
        if len(report['nodes']) != 2:
            raise RuntimeError('Brak INFO z obu płytek. Sprawdź wgranie programu i porty USB.')
        for node, item in report['nodes'].items():
            if not item['ready'] or item['version'] != 'pair-0.1' or item['profile'] != PROFILE:
                raise RuntimeError(f'{node}: radio niegotowe lub niewłaściwy program/profil: {item}')
        if report['nodes']['A']['id'] == report['nodes']['B']['id']:
            raise RuntimeError('Porty wskazują ten sam procesor.')
        print('Obie płytki gotowe. Test trwa około 10 minut dla 100 wiadomości w każdą stronę.')
        for seq in range(1, args.count + 1):
            for sender in ('A', 'B'):
                # INFO is an identity/boot continuity check, not a radio acknowledgment.
                for port in ports.values():
                    port.write(b'INFO\n')
                payload = f'WICI0:{session}:{sender}:{seq:03d}:0123456789ABCDEF'
                ports[sender].write(('TX ' + payload + '\n').encode('ascii'))
                batch = collect(3)
                result = judge(batch, sender, payload)
                result.update({'sender': sender, 'seq': seq, 'payload': payload})
                report['packets'].append(result)
                infos = {node for node, event in batch if event['kind'] == 'info'}
                if infos != {'A', 'B'}:
                    raise RuntimeError('Utracono kontakt USB z płytką podczas testu.')
                print(f'{sender} {seq}/{args.count}: ' + ('OK' if result['ok'] else 'BŁĄD'), flush=True)
                if report['issues']:
                    raise RuntimeError('Błąd urządzenia; zatrzymano próbę. Szczegóły w raporcie.')
        report['completed'] = True
        report['passed'] = args.count == 100 and all(p['ok'] for p in report['packets']) and not report['issues']
    except (RuntimeError, serial.SerialException, KeyboardInterrupt) as exc:
        report['issues'].append({'error': str(exc) or 'Przerwano test.'})
        print('Test zatrzymany:', exc)
    finally:
        stop.set()
        for port in ports.values():
            port.close()
        raw.close()
        report['received_unique'] = {node: sum(p['ok'] for p in report['packets'] if p['sender'] == node)
                                     for node in ('A', 'B')}
        base.with_suffix('.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
        print('Raport:', base.with_suffix('.json'))
    print('WYNIK: ' + ('POZYTYWNY' if report['passed'] else
                       'PRÓBA SKRÓCONA - bez kwalifikacji' if report['completed'] and args.count < 100
                       else 'NEGATYWNY / NIEUKOŃCZONY'))
    return 0 if report['passed'] or (report['completed'] and args.count < 100 and all(p['ok'] for p in report['packets'])) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--a')
    parser.add_argument('--b')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--output', type=Path, default=Path('results'))
    try:
        raise SystemExit(run(parser.parse_args()))
    except (ValueError, ImportError) as exc:
        parser.error(str(exc))

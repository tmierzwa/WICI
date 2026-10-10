#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Two offline Macs: A probes, B replies once; merge both logs after the trial."""
import argparse
import json
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pair_test import PROFILE, decode, open_serial

R0_VERSION = 'pair-0.3'
PACKET = re.compile(r'^WICIR:([0-9a-f]{16}):([AB]):([0-9]{3}):0123456789ABCDEF$')


def payload(session, node, seq):
    return f'WICIR:{session}:{node}:{seq:03d}:0123456789ABCDEF'


def summarize(a, b):
    if a['role'] != 'A' or b['role'] != 'B' or a['point'] != b['point']:
        raise ValueError('Wybierz raporty A i B z tego samego punktu.')
    for report in (a, b):
        info = report.get('node', {})
        if info.get('version') != R0_VERSION or not info.get('ready') or info.get('profile') != PROFILE:
            raise ValueError('Brak potwierdzenia właściwego firmware/profilu.')
    if a['node']['id'] == b['node']['id']:
        raise ValueError('Raporty dotyczą tej samej płytki.')
    if not a['session'] or b['session'] not in (None, a['session']) or a['count'] != b['count']:
        raise ValueError('Niezgodna sesja lub liczba pakietów.')
    online = a.get('mode') == b.get('mode') == 'online'
    if (a.get('mode') == 'online') != (b.get('mode') == 'online'):
        raise ValueError('Nie łącz raportów online i offline.')
    directions = {}
    for sender, source, target in [('A', a, b), ('B', b, a)]:
        records = []
        for seq in range(1, a['count'] + 1):
            text = payload(a['session'], sender, seq)
            tx = [e for e in source['events'] if e.get('kind') == 'tx' and e['payload'] == text]
            rx = [e for e in target['events'] if e.get('kind') == 'rx' and e['payload'] == text]
            records.append({'seq': seq, 'tx_ok': len(tx) == 1 and tx[0]['status'] == 0,
                            'rx_ok': len(rx) == 1, 'tx_records': len(tx), 'rx_records': len(rx),
                            'rssi': rx[0]['rssi'] if rx else None, 'snr': rx[0]['snr'] if rx else None})
        sent = sum(p['tx_ok'] for p in records)
        received = sum(p['tx_ok'] and p['rx_ok'] for p in records)
        # Only the sender transmits to this target, so its CRC failures belong to this direction.
        corrupt = sum(e.get('kind') == 'corrupt' for e in target['events'])
        directions[sender + '->' + ('B' if sender == 'A' else 'A')] = {
            'sent': sent, 'received': received, 'lost': sent - received, 'corrupt_received': corrupt,
            'delivery_percent': 100 * received / sent if sent else None, 'packets': records}
    issues = a['issues'] + b['issues']
    valid = a['completed'] and not issues and directions['A->B']['sent'] == a['count']
    if online:
        valid = valid and b['completed'] and directions['B->A']['sent'] == a['count']
    return {'session': a['session'], 'point': a['point'], 'count': a['count'],
            'valid_trial': valid, 'issues': issues, 'directions': directions,
            'passed': valid and a['count'] == 100 and all(d['received'] == 100 for d in directions.values()),
            'note': 'Online: niezależne transmisje obu urządzeń, potwierdzenie odbioru wyłącznie przez USB radia.' if online else 'B odpowiada tylko na odebrane A. Wynik B->A jest warunkowy; brak odpowiedzi sam nie wskazuje kierunku straty.',
            'metadata': {'A': a['notes'], 'B': b['notes']}}


def run(args):
    if not 1 <= args.count <= 100 or not 6 <= args.interval <= 60:
        raise ValueError('Liczba 1..100; odstęp 6..60 sekund.')
    import serial
    args.output.mkdir(parents=True, exist_ok=True)
    base = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-') + args.role + '-' + uuid.uuid4().hex[:8])
    report = {'role': args.role, 'point': args.point, 'notes': args.notes, 'count': args.count,
              'session': uuid.uuid4().hex[:16] if args.role == 'A' else None,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'interval_s': args.interval,
              'node': None, 'events': [], 'issues': [], 'completed': False}
    port = None
    thread = None
    stop = threading.Event()
    incoming = queue.Queue()
    raw = base.with_suffix('.jsonl').open('w')
    seen = set()
    next_probe = 0
    seq = 0
    last_info = 0
    last_info_rx = time.monotonic()
    last_reply = 0
    finish_at = None

    def reader():
        try:
            while not stop.is_set():
                data = port.readline(512)
                if data:
                    incoming.put(data.decode('ascii', errors='replace').strip())
        except (serial.SerialException, OSError) as exc:
            if not stop.is_set():
                incoming.put('ERR disconnected ' + str(exc))

    def send(command):
        port.write((command + '\n').encode('ascii'))

    try:
        port = open_serial(args.port)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        print('Raport:', base.with_suffix('.json'), flush=True)
        print('Nie przemieszczaj urządzeń podczas jednej próby. B zakończ Ctrl+C po zakończeniu A.', flush=True)
        while True:
            now = time.monotonic()
            if now - last_info >= 2:
                send('INFO')
                last_info = now
            if now - last_info_rx > 10:
                raise RuntimeError('Brak odpowiedzi USB INFO przez 10 s.')
            if report['node'] and args.role == 'A' and now >= next_probe and seq < args.count:
                seq += 1
                send('TX ' + payload(report['session'], 'A', seq))
                next_probe = now + args.interval
                if seq == args.count:
                    finish_at = next_probe
                print(f'A: wysłano polecenie {seq}/{args.count}', flush=True)
            if finish_at is not None and now >= finish_at:
                report['completed'] = True
                break
            try:
                line = incoming.get(timeout=.1)
            except queue.Empty:
                continue
            raw.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'line': line}) + '\n')
            raw.flush()
            event = decode(line)
            report['events'].append(event)
            if event['kind'] in ('error', 'blocked'):
                raise RuntimeError(event.get('message', line))
            if event['kind'] == 'info':
                last_info_rx = time.monotonic()
                if not event['ready'] or event['version'] != R0_VERSION or event['profile'] != PROFILE:
                    raise RuntimeError('Niewłaściwy program/profil albo radio niegotowe.')
                if report['node'] is not None and report['node'] != event:
                    raise RuntimeError('Restart lub zmiana konfiguracji płytki.')
                if report['node'] is None:
                    print('GOTOWE: radio i USB potwierdzone.', flush=True)
                report['node'] = event
            if event['kind'] == 'tx' and event['status'] != 0:
                raise RuntimeError('Nadawanie zakończone błędem.')
            if event['kind'] != 'rx':
                continue
            match = PACKET.fullmatch(event['payload'])
            if not match:
                continue
            session, sender, number = match.groups()
            number = int(number)
            if args.role == 'B' and sender == 'A' and 1 <= number <= args.count:
                if report['node'] is None:
                    raise RuntimeError('Pakiet przed potwierdzeniem INFO; uruchom B przed A.')
                if report['session'] is None:
                    report['session'] = session
                if session != report['session']:
                    raise RuntimeError('Inna sesja radiowa; uruchom nową próbę dla każdego punktu.')
                if number in seen:
                    raise RuntimeError('Duplikat pakietu A; odpowiedź nie będzie ponowiona.')
                if time.monotonic() - last_reply < 3:
                    raise RuntimeError('Pakiety zbyt blisko siebie; zatrzymano próbę.')
                seen.add(number)
                send('INFO')
                send('TX ' + payload(session, 'B', number))
                last_reply = time.monotonic()
                print(f'B: odebrano {number}; odpowiedź', flush=True)
            elif args.role == 'A' and session == report['session'] and sender == 'B':
                print(f'A: odpowiedź {number}, RSSI {event["rssi"]}, SNR {event["snr"]}', flush=True)
    except KeyboardInterrupt:
        if args.role == 'A':
            report['issues'].append('Przerwano A przed ukończeniem.')
    except (RuntimeError, OSError, serial.SerialException) as exc:
        report['issues'].append(str(exc))
        print('BŁĄD:', exc, flush=True)
    finally:
        stop.set()
        if port is not None:
            try:
                port.cancel_read()
            except (OSError, serial.SerialException):
                pass
            if thread is not None:
                thread.join(timeout=1)
            port.close()
        raw.close()
        report['ended_utc'] = datetime.now(timezone.utc).isoformat()
        base.with_suffix('.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        print('Zapisano:', base.with_suffix('.json'))
    return 1 if report['issues'] or report['node'] is None else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    trial = sub.add_parser('run')
    trial.add_argument('--port', required=True)
    trial.add_argument('--role', choices=['A', 'B'], required=True)
    trial.add_argument('--point', required=True)
    trial.add_argument('--notes', required=True, help='Położenie, dystans, przeszkody, wysokość i orientacja anten.')
    trial.add_argument('--count', type=int, default=100)
    trial.add_argument('--interval', type=float, default=6)
    trial.add_argument('--output', type=Path, default=Path('results'))
    merge = sub.add_parser('summarize')
    merge.add_argument('--a', type=Path, required=True)
    merge.add_argument('--b', type=Path, required=True)
    merge.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'run':
            return run(args)
        result = summarize(json.loads(args.a.read_text()), json.loads(args.b.read_text()))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        for name, direction in result['directions'].items():
            print(f'{name}: {direction["received"]}/{direction["sent"]} wysłanych odebrano')
        print('Pełny test 100/100:', result['passed'], '| Próba poprawnie wykonana:', result['valid_trial'])
        return 0 if result['valid_trial'] else 1
    except (ValueError, OSError, ImportError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

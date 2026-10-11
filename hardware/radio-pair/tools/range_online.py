#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Live two-Mac LoRa trial over private Tailscale TCP; RF receipts come only from USB.

Mac A is an unattended station serving trials; Mac B starts each trial and sets its point and count."""
import argparse
import ipaddress
import json
import math
import queue
import secrets
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pair_test import PROFILE, decode, judge, open_serial, tx_records
from range_test import R0_VERSION, payload, summarize

PROTOCOL = 'WICI-RANGE-ONLINE-4'
MAX_LINE = 262144


def private_address(text):
    address = ipaddress.ip_address(text)
    if address.version != 4 or not (address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')):
        raise ValueError('Użyj adresu IPv4 Tailscale 100.64.0.0/10 lub 127.0.0.1 do próby lokalnej.')
    return text


def check_plan(point, count, slot):
    if not isinstance(point, str) or not 1 <= len(point) <= 64 or not point.isprintable():
        raise ValueError('Nazwa punktu: 1..64 znaki.')
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
        raise ValueError('Liczba 1..100.')
    if isinstance(slot, bool) or not isinstance(slot, (int, float)) or not math.isfinite(slot) or not 3 <= slot <= 30:
        raise ValueError('Slot 3..30 sekund.')


class PeerFailure(RuntimeError):
    def __init__(self, item):
        super().__init__('Partner: ' + str(item.get('message', 'błąd')))
        self.category = 'peer-' + str(item.get('category', 'unknown'))


class Channel:
    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(15)
        self.file = sock.makefile('rb')

    def send(self, item):
        data = json.dumps(item, allow_nan=False).encode() + b'\n'
        if len(data) > MAX_LINE:
            raise ValueError('Zbyt duży komunikat kontrolny.')
        self.sock.sendall(data)

    def receive(self, kind):
        data = self.file.readline(MAX_LINE + 1)
        if not data or len(data) > MAX_LINE or not data.endswith(b'\n'):
            raise ConnectionError('Kanał internetowy zamknięty lub nieprawidłowy.')
        item = json.loads(data)
        if isinstance(item, dict) and item.get('kind') == 'abort':
            raise PeerFailure(item)
        if not isinstance(item, dict) or item.get('kind') != kind:
            raise ValueError('Nieoczekiwany komunikat kanału sterowania.')
        return item

    def close(self):
        self.file.close()
        self.sock.close()


class Device:
    def __init__(self, path, report, raw):
        self.report, self.raw = report, raw
        self.port = open_serial(path)
        self.stop = threading.Event()
        self.queue = queue.Queue()
        self.last_info = 0
        self.last_received = time.monotonic()
        self.thread = threading.Thread(target=self.reader, daemon=True)
        self.thread.start()

    def reader(self):
        try:
            while not self.stop.is_set():
                data = self.port.readline(512)
                if data:
                    self.queue.put(data.decode('ascii', errors='replace').strip())
        except OSError as exc:
            if not self.stop.is_set():
                self.queue.put('ERR disconnected ' + str(exc))

    def write(self, text):
        self.port.write((text + '\n').encode('ascii'))

    def collect(self, duration):
        events = []
        self.write('INFO')
        self.last_info = self.last_received = time.monotonic()
        end = time.monotonic() + duration
        while time.monotonic() < end:
            now = time.monotonic()
            if now - self.last_info >= 2:
                self.write('INFO')
                self.last_info = now
            if now - self.last_received > 10:
                raise RuntimeError('Brak odpowiedzi USB przez 10 s.')
            try:
                line = self.queue.get(timeout=.05)
            except queue.Empty:
                continue
            self.raw.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'line': line}) + '\n')
            self.raw.flush()
            event = decode(line)
            self.report['events'].append(event)
            events.append(event)
            if event['kind'] in ('error', 'blocked') or (event['kind'] == 'tx' and event['status'] != 0):
                raise RuntimeError('Błąd płytki: ' + line)
            if event['kind'] == 'info':
                self.last_received = time.monotonic()
                if event['version'] != R0_VERSION or not event['ready'] or event['profile'] != PROFILE:
                    raise RuntimeError('Niewłaściwy firmware/profil lub radio niegotowe.')
                if self.report['node'] is not None and self.report['node'] != event:
                    raise RuntimeError('Restart lub zmiana konfiguracji płytki.')
                self.report['node'] = event
        if not any(e['kind'] == 'info' for e in events):
            raise RuntimeError('Brak odpowiedzi USB INFO podczas próby.')
        return events

    def prepare(self):
        self.collect(2)
        if self.report['node'] is None:
            raise RuntimeError('Brak INFO z płytki.')

    def close(self):
        self.stop.set()
        try:
            self.port.cancel_read()
        except OSError:
            pass
        self.thread.join(timeout=1)
        self.port.close()


def validate_peer(peer, local):
    if peer.get('mode') != 'online' or peer.get('role') != ('B' if local['role'] == 'A' else 'A'):
        raise ValueError('Niewłaściwy tryb/rola partnera.')
    for key in ('point', 'count', 'slot_s'):
        if peer.get(key) != local[key]:
            raise ValueError('Niezgodne parametry obu Maców: ' + key)
    node = peer.get('node') or {}
    if node.get('version') != R0_VERSION or not node.get('ready') or node.get('profile') != PROFILE:
        raise ValueError('Radio partnera niegotowe lub niewłaściwy profil.')
    if node.get('id') == local['node']['id']:
        raise ValueError('Oba Maki wskazują tę samą płytkę.')
    if local['role'] == 'B':
        session = peer.get('session', '')
        if len(session) != 16 or any(c not in '0123456789abcdef' for c in session):
            raise ValueError('Nieprawidłowa sesja.')
        local['session'] = session
    peer['events'], peer['issues'], peer['completed'] = [], [], False


def feedback(local, remote, sender, seq, own, other):
    events = [(local['role'], e) for e in own] + [(remote['role'], e) for e in other]
    result = judge(events, sender, payload(local['session'], sender, seq))
    receiver = 'B' if sender == 'A' else 'A'
    if result['tx_records'] != 1 or result['tx_status'] != 0:
        raise RuntimeError('Brak pojedynczego potwierdzenia TX z płytki; próba nieprawidłowa.')
    print(f'{sender}->{receiver} {seq}/{local["count"]}: '
          f'{"ODEBRANO" if result["ok"] else "USZKODZONY (CRC)" if result["corrupt_records"] else "STRATA / DUPLIKAT"} '
          f'RSSI={result["rssi"]} SNR={result["snr"]}', flush=True)
    return result


def run(args):
    address = private_address(args.address)
    token = args.key_file.read_text().strip()
    if len(token) < 32:
        raise ValueError('Nieprawidłowy klucz sesji.')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.role == 'B':
        check_plan(args.point, args.count, args.slot)
        try:
            sock = socket.create_connection((address, args.tcp_port), timeout=15)
        except OSError as exc:
            raise OSError(f'Brak połączenia ze stacją A ({exc}); czy stacja A działa?') from exc
        return trial(args, token, sock)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((address, args.tcp_port))
    listener.listen(1)
    code, served = 0, 0
    try:
        while not args.trials or served < args.trials:
            print('Stacja A czeka na próbę z Maca B:', address, args.tcp_port, '(Ctrl+C kończy)', flush=True)
            sock, _ = listener.accept()
            served += 1
            code = trial(args, token, sock)
    except KeyboardInterrupt:
        print('Zatrzymano stację A.', flush=True)
    finally:
        listener.close()
    return code


def trial(args, token, sock):
    base = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-') + args.role + '-online-' + uuid.uuid4().hex[:8])
    local = {'mode': 'online', 'role': args.role, 'point': args.point, 'notes': args.notes,
             'count': args.count, 'slot_s': args.slot, 'node': None, 'events': [], 'issues': [],
             'completed': False, 'session': uuid.uuid4().hex[:16] if args.role == 'A' else None,
             'started_utc': datetime.now(timezone.utc).isoformat()}
    peer, channel, device, interrupted = None, None, None, False
    raw = base.with_suffix('.jsonl').open('w')
    phase = 'internet'
    try:
        channel = Channel(sock)
        if args.role == 'A':
            hello = channel.receive('hello')
            if hello.get('protocol') != PROTOCOL or not secrets.compare_digest(str(hello.get('token', '')), token):
                raise ValueError('Nieprawidłowy klucz lub protokół partnera.')
            peer = hello.get('report')
            if not isinstance(peer, dict):
                raise ValueError('Nieprawidłowy raport partnera.')
            check_plan(peer.get('point'), peer.get('count'), peer.get('slot_s'))
            local.update(point=peer['point'], count=peer['count'], slot_s=peer['slot_s'])
            print(f'Próba z Maca B: punkt {local["point"]}, {local["count"]} pakietów.', flush=True)
        phase = 'usb'
        device = Device(args.port, local, raw)
        device.prepare()
        print('GOTOWE USB. Raport:', base.with_suffix('.json'), flush=True)
        phase = 'internet'
        if args.role == 'A':
            validate_peer(peer, local)
            channel.send({'kind': 'hello', 'protocol': PROTOCOL, 'report': local})
        else:
            channel.send({'kind': 'hello', 'protocol': PROTOCOL, 'token': token, 'report': local})
            hello = channel.receive('hello')
            if hello.get('protocol') != PROTOCOL:
                raise ValueError('Niewłaściwy protokół.')
            peer = hello['report']
            validate_peer(peer, local)
        phase = 'usb'
        device.collect(2)  # Detect restarts queued during the network handshake.
        print('Oba Maki połączone. Przewidywany czas: co najmniej '
              f'{2 * local["count"] * local["slot_s"] / 60:.1f} min. Internet nie zastępuje odbioru LoRa.', flush=True)
        for seq in range(1, local['count'] + 1):
            for sender in 'AB':
                phase = 'internet'
                if args.role == 'A':
                    channel.send({'kind': 'task', 'sender': sender, 'seq': seq})
                    channel.receive('ready')
                    channel.send({'kind': 'go'})
                else:
                    task = channel.receive('task')
                    if (task.get('sender'), task.get('seq')) != (sender, seq):
                        raise ValueError('Nieprawidłowa kolejność próby.')
                    channel.send({'kind': 'ready'})
                    channel.receive('go')
                phase = 'usb'
                if sender == args.role:
                    device.write('TX ' + payload(local['session'], sender, seq))
                own = device.collect(local['slot_s'])
                if sender == args.role and not tx_records(own, payload(local['session'], sender, seq))[0]:
                    device.write('LAST')
                    own += device.collect(1)
                phase = 'internet'
                if args.role == 'B':
                    channel.send({'kind': 'observed', 'events': own})
                    other = channel.receive('observed')['events']
                else:
                    other = channel.receive('observed')['events']
                    channel.send({'kind': 'observed', 'events': own})
                peer['events'].extend(other)
                phase = 'usb'
                feedback(local, peer, sender, seq, own, other)
        phase = 'internet'
        if args.role == 'A':
            channel.send({'kind': 'finish'})
            channel.receive('finished')
        else:
            channel.receive('finish')
            channel.send({'kind': 'finished'})
        local['completed'] = peer['completed'] = True
    except KeyboardInterrupt:
        local['issues'].append({'category': 'operator', 'message': 'Przerwano próbę.'})
        interrupted = True
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        category = exc.category if isinstance(exc, PeerFailure) else phase
        local['issues'].append({'category': category, 'message': str(exc)})
        if channel is not None and not isinstance(exc, PeerFailure):
            try:
                channel.send({'kind': 'abort', 'category': category, 'message': str(exc)})
            except OSError:
                pass
        print(f'BŁĄD ({category}): {exc}. Zatrzymano próbę; logi pozostają lokalnie.', flush=True)
    finally:
        if device is not None:
            device.close()
        if channel is not None:
            channel.close()
        raw.close()
        local['ended_utc'] = datetime.now(timezone.utc).isoformat()
        base.with_suffix('.json').write_text(json.dumps(local, indent=2, ensure_ascii=False) + '\n')
        if peer is not None:
            base.with_name(base.name + '-peer').with_suffix('.json').write_text(json.dumps(peer, indent=2, ensure_ascii=False) + '\n')
        if local['completed'] and peer is not None:
            a, b = (local, peer) if args.role == 'A' else (peer, local)
            result = summarize(a, b)
            base.with_name(base.name + '-summary').with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
            print('Pełny test 100/100:', result['passed'], '| Próba poprawnie wykonana:', result['valid_trial'])
        print('Zapisano lokalny raport:', base.with_suffix('.json'), flush=True)
    if interrupted and args.role == 'A':
        raise KeyboardInterrupt
    return 0 if local['completed'] and not local['issues'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-key', type=Path, help='Utwórz klucz; skopiuj ten plik na drugi Mac.')
    parser.add_argument('--role', choices=['A', 'B'])
    parser.add_argument('--address', help='IPv4 Tailscale Maca A; A nasłuchuje, B łączy się.')
    parser.add_argument('--tcp-port', type=int, default=8765)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--port')
    parser.add_argument('--point', help='Tylko B: nazwa punktu.')
    parser.add_argument('--notes', help='Opis położenia tej płytki.')
    parser.add_argument('--count', type=int, help='Tylko B: liczba pakietów (domyślnie 100).')
    parser.add_argument('--slot', type=float, help='Tylko B: okno odbioru w s (domyślnie 3).')
    parser.add_argument('--trials', type=int, default=0, help='Tylko A: zakończ po tylu próbach (0 = bez końca).')
    parser.add_argument('--output', type=Path, default=Path('results'))
    args = parser.parse_args()
    try:
        if args.make_key:
            args.make_key.parent.mkdir(parents=True, exist_ok=True)
            with args.make_key.open('x') as file:
                args.make_key.chmod(0o600)
                file.write(secrets.token_hex(32) + '\n')
            print('Utworzono klucz. Skopiuj plik na drugi Mac; nie dodawaj go do Git.')
            return 0
        if any(getattr(args, key) is None for key in ('role', 'address', 'key_file', 'port', 'notes')):
            raise ValueError('Podaj --role, --address, --key-file, --port i --notes.')
        if args.role == 'A':
            if any(getattr(args, key) is not None for key in ('point', 'count', 'slot')):
                raise ValueError('Na A punkt, liczbę i slot ustawia Mac B.')
            if args.trials < 0:
                raise ValueError('Nieprawidłowe --trials.')
        else:
            if args.point is None:
                raise ValueError('Podaj --point.')
            args.count = 100 if args.count is None else args.count
            args.slot = 3 if args.slot is None else args.slot
        if not 1 <= args.tcp_port <= 65535:
            raise ValueError('Nieprawidłowy port TCP.')
        return run(args)
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Live two-Mac LoRa trial over private Tailscale TCP; RF receipts come only from USB."""
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

PROTOCOL = 'WICI-RANGE-ONLINE-3'
MAX_LINE = 262144


def private_address(text):
    address = ipaddress.ip_address(text)
    if address.version != 4 or not (address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')):
        raise ValueError('Użyj adresu IPv4 Tailscale 100.64.0.0/10 lub 127.0.0.1 do próby lokalnej.')
    return text


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
    if not 1 <= args.count <= 100 or not math.isfinite(args.slot) or not 3 <= args.slot <= 30:
        raise ValueError('Liczba 1..100; slot 3..30 sekund.')
    token = args.key_file.read_text().strip()
    if len(token) < 32:
        raise ValueError('Nieprawidłowy klucz sesji.')
    args.output.mkdir(parents=True, exist_ok=True)
    base = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-') + args.role + '-online-' + uuid.uuid4().hex[:8])
    local = {'mode': 'online', 'role': args.role, 'point': args.point, 'notes': args.notes,
             'count': args.count, 'slot_s': args.slot, 'node': None, 'events': [], 'issues': [],
             'completed': False, 'session': uuid.uuid4().hex[:16] if args.role == 'A' else None,
             'started_utc': datetime.now(timezone.utc).isoformat()}
    peer, channel, listener, device = None, None, None, None
    raw = base.with_suffix('.jsonl').open('w')
    phase = 'usb'
    try:
        device = Device(args.port, local, raw)
        device.prepare()
        print('GOTOWE USB. Raport:', base.with_suffix('.json'), flush=True)
        phase = 'internet'
        if args.role == 'A':
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((address, args.tcp_port))
            listener.listen(1)
            listener.settimeout(120)
            print('Czekam na Mac B:', address, args.tcp_port, flush=True)
            sock, _ = listener.accept()
            channel = Channel(sock)
            hello = channel.receive('hello')
            if hello.get('protocol') != PROTOCOL or not secrets.compare_digest(str(hello.get('token', '')), token):
                raise ValueError('Nieprawidłowy klucz lub protokół partnera.')
            peer = hello['report']
            validate_peer(peer, local)
            channel.send({'kind': 'hello', 'protocol': PROTOCOL, 'report': local})
        else:
            channel = Channel(socket.create_connection((address, args.tcp_port), timeout=15))
            channel.send({'kind': 'hello', 'protocol': PROTOCOL, 'token': token, 'report': local})
            hello = channel.receive('hello')
            if hello.get('protocol') != PROTOCOL:
                raise ValueError('Niewłaściwy protokół.')
            peer = hello['report']
            validate_peer(peer, local)
        phase = 'usb'
        device.collect(2)  # Detect restarts queued during the network handshake.
        print('Oba Maki połączone. Przewidywany czas: co najmniej '
              f'{2 * args.count * args.slot / 60:.1f} min. Internet nie zastępuje odbioru LoRa.', flush=True)
        for seq in range(1, args.count + 1):
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
                own = device.collect(args.slot)
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
        if listener is not None:
            listener.close()
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
    return 0 if local['completed'] and not local['issues'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make-key', type=Path, help='Utwórz klucz; skopiuj ten plik na drugi Mac.')
    parser.add_argument('--role', choices=['A', 'B'])
    parser.add_argument('--address', help='IPv4 Tailscale Maca A; A nasłuchuje, B łączy się.')
    parser.add_argument('--tcp-port', type=int, default=8765)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--port')
    parser.add_argument('--point')
    parser.add_argument('--notes')
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--slot', type=float, default=3)
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
        if any(getattr(args, key) is None for key in ('role', 'address', 'key_file', 'port', 'point', 'notes')):
            raise ValueError('Podaj --role, --address, --key-file, --port, --point i --notes.')
        if not 1 <= args.tcp_port <= 65535:
            raise ValueError('Nieprawidłowy port TCP.')
        return run(args)
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())

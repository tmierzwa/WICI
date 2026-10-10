#!/usr/bin/env python3
"""L0 USB diagnostics; physical measurements/visual checks remain separate."""
import argparse
import functools
import json
import math
import re
import sys
import time
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

import radio_test

FRAM_SIZE = 512 * 1024
MIX_DURATION_MS = 900000
MIX_MAX_GAP_MS = 1000


def write_report(path, report):
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def check_command(command, end):
    if (not command or command != command.strip() or len(command) > 90 or
            any(not 32 <= ord(c) <= 126 for c in command)):
        raise RuntimeError('Polecenie: jedna linia ASCII, 1–90 znaków, bez CR/LF.')
    if not end or not end.strip() or any(not 32 <= ord(c) <= 126 for c in end):
        raise RuntimeError('Potrzebne niepuste, jednoliniowe potwierdzenie --end.')


def transact(port, command, end, timeout, output, validator=None, require_ready=False):
    check_command(command, end)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
              'records': [], 'software_command_completed': False, 'physical_acceptance': False}
    events = report['records']
    try:
        with radio_test.open_serial(port) as device:
            device.reset_input_buffer()
            device.write(b'INFO\n')
            deadline = time.monotonic() + 5
            ready = None
            handshake_acked = False
            while time.monotonic() < deadline:
                line = device.readline(512).decode('ascii', errors='replace').strip()
                if not line:
                    continue
                events.append(line)
                item = radio_test.decode(line)
                if line == 'CMD INFO':
                    handshake_acked = True
                    continue
                if item['kind'] == 'info':
                    if item['version'] != radio_test.L0_VERSION or item['profile'] != radio_test.PROFILE:
                        raise RuntimeError('Niewłaściwy obraz/profil L0: ' + line)
                    if not handshake_acked:
                        continue
                    if require_ready and not item['ready']:
                        raise RuntimeError('L0 niegotowe do testu mieszanego: ' + line)
                    ready = item
                    report['node'] = item
                    break
                # Startup diagnostics are retained; STATUS/FRAM can diagnose a board
                # even when another peripheral failed its initialization.
            if ready is None:
                raise RuntimeError('Brak INFO z L0.')
            device.write((command + '\n').encode('ascii'))
            deadline = time.monotonic() + timeout
            acknowledged = False
            response_start = 0
            while time.monotonic() < deadline:
                line = device.readline(512).decode('ascii', errors='replace').strip()
                if not line:
                    continue
                events.append(line)
                print(line, flush=True)
                item = radio_test.decode(line)
                if item['kind'] == 'info' and item != ready:
                    raise RuntimeError('Restart lub zmiana konfiguracji podczas polecenia.')
                if line == 'CMD ' + command:
                    acknowledged = True
                    response_start = len(events)
                    continue
                if not acknowledged:
                    continue  # Do not accept stale boot/previous-command output.
                if item['kind'] == 'error' or (item['kind'] == 'blocked' and not line.startswith(end)):
                    raise RuntimeError(line)
                if line.startswith(end):
                    command_records = events[response_start:]
                    if validator is not None:
                        validator(command_records)
                    report['software_command_completed'] = True
                    return report
            raise RuntimeError('Brak końcowego potwierdzenia dla ' + command)
    except (RuntimeError, OSError, ValueError, KeyboardInterrupt) as exc:
        report['error'] = str(exc) or 'Przerwano test.'
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_report(output, report)


@functools.lru_cache(maxsize=16)
def expected_crc(pass_number, seed):
    """Independent Python/zlib reference for the firmware's whole-memory patterns."""
    if pass_number < 4:
        return zlib.crc32(bytes(([0, 255, 170, 85][pass_number],)) * FRAM_SIZE)
    pattern = bytearray(FRAM_SIZE)
    for address in range(FRAM_SIZE):
        value = address ^ seed
        value ^= value >> 16
        value = (value * 0x7FEB352D) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x846CA68B) & 0xFFFFFFFF
        value ^= value >> 16
        pattern[address] = value & 0xFF
    return zlib.crc32(pattern)


def validate_fram(records, seed, verify):
    passes = []
    done = []
    for line in records:
        if line.startswith('ERR '):
            raise RuntimeError(line)
        if line.startswith('FRAM_PASS '):
            match = re.fullmatch(r'FRAM_PASS ([0-4]) (\d+) ([0-9A-F]{8}) ([0-9A-F]{8})', line)
            if match is None:
                raise RuntimeError('Nieprawidłowy raport FRAM: ' + line)
            number, errors, want, got = match.groups()
            number = int(number)
            if int(errors) or int(want, 16) != expected_crc(number, seed) or want != got:
                raise RuntimeError('Błąd wzorca/CRC FRAM: ' + line)
            passes.append(number)
        elif line.startswith('FRAM_DONE '):
            done.append(line)
    if passes != ([4] if verify else list(range(5))):
        raise RuntimeError('Niepełny zestaw wzorców FRAM.')
    expected = f'FRAM_DONE {seed:08X} ' + ('VERIFY' if verify else 'WRITE')
    if done != [expected] or not records or records[-1] != expected:
        raise RuntimeError('Niezgodny seed/tryb lub niejednoznaczne zakończenie FRAM.')


def validate_mixed(raw_path):
    try:
        records = [json.loads(line) for line in raw_path.read_text().splitlines()]
        if any(not isinstance(r, dict) or r.get('node') not in ('A', 'B') or
               not isinstance(r.get('line'), str) for r in records):
            raise ValueError('record shape')
        done = [r for r in records if r['node'] == 'A' and r['line'].startswith('MIX_DONE ')]
        if len(done) != 1:
            raise ValueError('completion count')
        fields = done[0]['line'].split()
        if len(fields) != 6:
            raise ValueError('completion fields')
        cycles, errors, frames, elapsed_ms, max_gap_ms = map(int, fields[1:])
        if (cycles < MIX_DURATION_MS // MIX_MAX_GAP_MS or errors != 0 or frames != cycles or
                elapsed_ms < MIX_DURATION_MS or not 0 < max_gap_ms <= MIX_MAX_GAP_MS or
                not math.isfinite(done[0]['elapsed_s']) or done[0]['elapsed_s'] < 880):
            raise ValueError('duration/activity/errors')
        if any(radio_test.decode(r['line'])['kind'] in ('error', 'blocked') for r in records):
            raise ValueError('device errors')
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError('Niepełny/błędny 15-minutowy test SPI; sprawdź logi.') from exc
    return {'cycles': cycles, 'errors': errors, 'lcd_frames': frames,
            'elapsed_ms': elapsed_ms, 'max_gap_ms': max_gap_ms}


def run_mixed(args, base):
    try:
        report = transact(args.port, 'MIXSTART ERASE', 'MIX_START ', 5,
                           base.with_suffix('.json'), require_ready=True)
        ready = report['node']
        folder = base.with_name(base.name + '-radio')
        runner_args = argparse.Namespace(a=args.port, b=args.peer, list=False, count=100,
                                        version_a=radio_test.L0_VERSION, version_b='pair-0.4',
                                        interval=4.5, output=folder, expected_nodes={'A': ready})
        if radio_test.run(runner_args):
            raise RuntimeError('Test radiowy niezaliczony; szczegóły w logach.')
        logs = list(folder.glob('*.jsonl'))
        if len(logs) != 1:
            raise RuntimeError('Niejednoznaczne logi próby.')
        mix = validate_mixed(logs[0])
        write_report(base.with_suffix('.mixed.json'),
                     {'mixed': mix, 'radio_100_each': True, 'physical_acceptance': False})
        print('SPI + radio zakończone. Pomiary/oględziny są osobnym warunkiem odbioru.')
    except (RuntimeError, OSError, ValueError, KeyboardInterrupt):
        try:
            transact(args.port, 'STOP', 'STOPPED', 2, base.with_suffix('.stop.json'))
        except (RuntimeError, OSError, ValueError):
            print('Nie udało się zatrzymać L0 przez USB. Przed kolejną próbą naciśnij RESET.')
        raise


def command_end(command):
    for prefix, end in (
        ('INFO', 'INFO '), ('STATUS', 'STATUS '), ('RDID', 'FRAM_ID '), ('STOP', 'STOPPED'),
        ('HELP', 'COMMANDS '), ('LED ', 'LED_SET'), ('BUZZ ', 'BUZZ_SET'), ('LCD ', 'LCD_DONE'),
        ('PAUSE 10000', 'PAUSE_DONE'), ('GUARD ERASE', 'GUARD_START '), ('TX ', 'TX '),
    ):
        if command == prefix or (prefix.endswith(' ') and command.startswith(prefix)):
            return end
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='L0 USB/OTG')
    parser.add_argument('--output', type=Path, default=Path('results'))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--fram-write', metavar='SEED_HEX', help='DESTRUCTIVE: writes all 512KiB')
    group.add_argument('--fram-verify', metavar='SEED_HEX', help='Read-only retention verification')
    group.add_argument('--mixed', action='store_true', help='DESTRUCTIVE: uses last 256 bytes')
    group.add_argument('--command', help='One firmware command, e.g. STATUS or LCD 2')
    parser.add_argument('--end', help='Final line prefix; inferred for known --command values')
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--peer', help='R0 XIAO partner for --mixed')
    args = parser.parse_args(argv)
    if args.mixed and (not args.peer or args.peer == args.port):
        parser.error('--mixed wymaga drugiego, różnego portu --peer.')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('Timeout musi być dodatni i skończony.')
    seed_text = args.fram_write if args.fram_write is not None else args.fram_verify
    seed = None
    if seed_text is not None:
        if re.fullmatch(r'[0-9a-fA-F]{1,8}', seed_text) is None:
            parser.error('Seed: 1–8 cyfr szesnastkowych, od 0 do FFFFFFFF.')
        seed = int(seed_text, 16)
    if args.command is not None:
        args.end = args.end if args.end is not None else command_end(args.command)
        try:
            check_command(args.command, args.end)
        except RuntimeError as exc:
            parser.error(str(exc))
        if args.command.startswith(('FRAMTEST', 'FRAMVERIFY', 'MIXSTART')):
            parser.error('Dla FRAM/MIX użyj --fram-write, --fram-verify lub --mixed: pełna walidacja.')
    args.output.mkdir(parents=True, exist_ok=True)
    base = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    try:
        if seed is not None:
            verify = args.fram_verify is not None
            command = ('FRAMVERIFY ' if verify else 'FRAMTEST ERASE ') + f'{seed:08X}'
            transact(args.port, command, 'FRAM_DONE ', args.timeout, base.with_suffix('.json'),
                     validator=lambda records: validate_fram(records, seed, verify))
        elif args.mixed:
            run_mixed(args, base)
        else:
            transact(args.port, args.command, args.end, args.timeout, base.with_suffix('.json'))
    except (RuntimeError, OSError, ValueError, KeyboardInterrupt) as exc:
        write_report(base.with_suffix('.error.json'),
                     {'error': str(exc) or 'Przerwano test.', 'physical_acceptance': False})
        print('NIEZALICZONE / NIEUKOŃCZONE:', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

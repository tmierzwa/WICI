"""Próba 13: sygnał do ręcznego odcięcia A (P001) w chwili zdarzenia z podsłuchu.
python cut13.py TRYB N   TRYB: req | hack | part1 | bulletin | idle
Sygnał: "TERAZ" na wyjściu i głos. Właściciel odłącza USB P001, liczy do 5 i podłącza.
Opóźnienie ręki = chwila '## port lost' w log/P001.log minus chwila sygnału. Chwile odcięć: log/cut13-marks.txt."""
import json, os, subprocess, sys, time

D = os.path.expanduser('~/WICI-L0/proby')
CAP = os.path.expanduser('~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/'
                         'hardware/xiao-wici/evidence/podsluch-l0-2026-11-15.jsonl')
A, B = 20, 10
PY = os.path.expanduser('~/WICI-L0/stvenv/bin/python')


def ts(t=None):
    t = time.time() if t is None else t
    return time.strftime('%H:%M:%S', time.localtime(t)) + f'.{int(t * 1000) % 1000:03d}'


def say(text):
    print(f'{ts()} {text}', flush=True)


def cmd(name, line):
    with open(f'{D}/cmd/{name}', 'w') as f:
        f.write(line + '\n')


class Capture:
    def __init__(self):
        self.f = open(CAP, encoding='utf-8')
        self.f.seek(0, 2)

    def frames(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            line = self.f.readline()
            if not line:
                time.sleep(0.02)
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('v3') and r.get('mac_ok'):
                yield r
        return


def part(r):
    raw = bytes.fromhex(r['hex'])
    if len(raw) <= 11 or raw[11] & 0x0F:
        return -1  # nie SA1 (np. dowód doręczenia)
    return (raw[11] >> 4) & 3


def wait_hack(cap, src, dst, want_part, timeout=600):
    """DATA src->dst with the wanted envelope part, then HACK dst->src for its seq."""
    seq = None
    for r in cap.frames(timeout):
        v = r['v3']
        if v['type'] == 0 and v['l_src'] == src and v['l_dst'] == dst and (want_part is None or part(r) == want_part):
            seq = v['seq']
            say(f'DATA {src}->{dst} seq {seq} part {part(r)}')
        elif seq is not None and v['type'] == 1 and v['l_src'] == dst and v['l_dst'] == src and v['seq'] == seq:
            return r
    return None


def app_intents():
    log = f'{D}/log/P001.log'
    size = os.path.getsize(log)
    cmd('P001', 'APP')
    time.sleep(1.2)
    with open(log, encoding='utf-8', errors='replace') as f:
        f.seek(size)
        for line in f:
            if '"intents"' in line:
                return json.loads(line.split(' ', 1)[1])['intents']
    return None


def req(line):
    """REQ on A; stop the run when nothing was created (full register)."""
    log = f'{D}/log/P001.log'
    size = os.path.getsize(log)
    cmd('P001', line)
    end = time.time() + 3
    while time.time() < end:
        with open(log, encoding='utf-8', errors='replace') as f:
            f.seek(size)
            for l in f:
                if '"created"' in l:
                    d = json.loads(l.split(' ', 1)[1])
                    if not d.get('created'):
                        say(f'REQ NIE UTWORZYŁ ZGŁOSZENIA: {d.get("error")}; przerywam')
                        sys.exit(2)
                    say(f'REQ numer {d["numbers"]} sa1 {d["sa1_bytes"]}')
                    return d
        time.sleep(0.05)
    say('REQ bez odpowiedzi; przerywam')
    sys.exit(2)


def warn():
    say('ZARAZ')
    subprocess.Popen(['say', '-v', 'Zosia', 'zaraz'])
    time.sleep(3)


def signal():
    global POS
    POS = os.path.getsize(f'{D}/log/P001.log')
    t = time.time()
    print(f'{ts(t)} TERAZ', flush=True)
    subprocess.Popen(['say', '-v', 'Zosia', 'teraz'])
    return t


def after_cut(t_signal, pos):
    log = f'{D}/log/P001.log'
    lost = back = None
    end = time.time() + 120
    while time.time() < end and back is None:
        with open(log, encoding='utf-8', errors='replace') as f:
            f.seek(pos)
            for line in f:
                hms = line[:12]
                if '## port lost' in line and lost is None:
                    lost = line
                elif '## port back' in line and lost is not None:
                    back = line
            pos = f.tell()
        time.sleep(0.2)
    if lost is None:
        say('BRAK ODCIĘCIA w 120 s')
        return None
    h, m, s = lost[:12].split(':')
    lt = time.mktime(time.strptime(time.strftime('%Y-%m-%d ') + f'{h}:{m}:00', '%Y-%m-%d %H:%M:%S')) + float(s)
    say(f'odcięcie {lost[:12]}, opóźnienie ręki {lt - t_signal:.2f} s; powrót {back[:12] if back else "brak"}')
    with open(f'{D}/log/cut13-marks.txt', 'a') as f:
        f.write(f'{lt:.3f} {MODE} signal {t_signal:.3f}\n')
    time.sleep(12)
    for c in ('LOG', 'JOURNAL', 'STORE', 'APP'):
        cmd('P001', c)
        time.sleep(1.5)
    return lt


def settle(limit=900):
    end = time.time() + limit
    while time.time() < end:
        n = app_intents()
        if n == 0:
            say('intents 0')
            return True
        time.sleep(20)
    say('intents nie zeszły do 0')
    return False


MODE, N = sys.argv[1], int(sys.argv[2])
for i in range(1, N + 1):
    say(f'== {MODE} {i}/{N}')
    if MODE != 'idle':
        settle()
    warn()
    cap = Capture()
    if MODE == 'req':
        req('REQ 1')
        t = signal()
    elif MODE == 'hack':
        req('REQ 1')
        r = wait_hack(cap, A, B, 0)
        t = signal() if r else None
    elif MODE == 'part1':
        req('REQ 1 96')
        r = wait_hack(cap, A, B, 1)
        t = signal() if r else None
    elif MODE == 'bulletin':
        text = f'Komunikat probny {i} ' + 'x' * 150
        subprocess.run([PY, f'{D}/panel.py', 'login'], capture_output=True)
        out = subprocess.run([PY, f'{D}/panel.py', 'bulletin', text], capture_output=True, text=True).stdout
        say(f'biuletyn {out.strip()[:80]}')
        r = wait_hack(cap, B, A, 1)
        t = signal() if r else None
    elif MODE == 'idle':
        settle()
        t = signal()
    else:
        sys.exit('tryb?')
    if t is None:
        say('zdarzenie nie wystąpiło')
        continue
    after_cut(t, POS)
    settle()
say('koniec')

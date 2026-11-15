"""Próba 12, kroki 1 i 2: REQ 10 na A przez trzy skoki, potem 20 decyzji w dół (PRZECZYTANE i ZAMKNIĘTE).
Przy CUTS pierwszych decyzjach: "zaraz", decyzja, "teraz" po rozsyłaniu przez B (DATA 10 -> 65535); właściciel
odcina P002 na ~5 s. python p12.py [CUTS]"""
import json, os, subprocess, sys, time

D = os.path.expanduser('~/WICI-L0/proby')
CAP = os.path.expanduser('~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/'
                         'hardware/xiao-wici/evidence/podsluch-l0-2026-11-15.jsonl')
PY = os.path.expanduser('~/WICI-L0/stvenv/bin/python')
CUTS = int(sys.argv[1]) if len(sys.argv) > 1 else 5


def ts(t=None):
    t = time.time() if t is None else t
    return time.strftime('%H:%M:%S', time.localtime(t)) + f'.{int(t * 1000) % 1000:03d}'


def say(text):
    print(f'{ts()} {text}', flush=True)


def voice(word):
    subprocess.Popen(['say', '-v', 'Zosia', word])


def console(name, line, wait=1.2):
    log = f'{D}/log/{name}.log'
    size = os.path.getsize(log)
    with open(f'{D}/cmd/{name}', 'w') as f:
        f.write(line + '\n')
    time.sleep(wait)
    with open(log, encoding='utf-8', errors='replace') as f:
        f.seek(size)
        return f.read()


def panel(*args):
    subprocess.run([PY, f'{D}/panel.py', 'login'], capture_output=True)
    return subprocess.run([PY, f'{D}/panel.py', *args], capture_output=True, text=True).stdout


def intents():
    out = console('P001', 'APP')
    for line in out.splitlines():
        if '"intents"' in line:
            return json.loads(line.split(' ', 1)[1])['intents']
    return None


def settle(limit=1200):
    end = time.time() + limit
    while time.time() < end:
        if intents() == 0:
            return True
        time.sleep(15)
    return False


def wait_flood(timeout=120):
    f = open(CAP, encoding='utf-8')
    f.seek(0, 2)
    end = time.time() + timeout
    while time.time() < end:
        line = f.readline()
        if not line:
            time.sleep(0.02)
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        v = r.get('v3')
        if v and r.get('mac_ok') and v['type'] == 0 and v['l_src'] == 10 and v['l_dst'] == 65535:
            return r
    return None


def wait_cut(pos, limit=120):
    log = f'{D}/log/P002.log'
    end = time.time() + limit
    lost = back = None
    while time.time() < end and back is None:
        with open(log, encoding='utf-8', errors='replace') as f:
            f.seek(pos)
            for line in f:
                if '## port lost' in line and lost is None:
                    lost = line[:12]
                elif '## port back' in line and lost:
                    back = line[:12]
            pos = f.tell()
        time.sleep(0.2)
    return lost, back


out = console('P001', 'REQ 10', 2)
nums = next(json.loads(l.split(' ', 1)[1])['numbers'] for l in out.splitlines() if '"numbers"' in l)
say(f'REQ 10: {nums}')
say(f'intents 0: {settle()}')
q = json.loads(panel('queue'))
reports = [r for r in q['reports'] if r['number'] in {f'{n:04d}' for n in nums}]
say(f'w panelu {len(reports)} z {len(nums)}')
steps = [(r, 2) for r in reports] + [(r, 6) for r in reports]
marks = open(f'{D}/log/p12-marks.txt', 'a')
for k, (r, state) in enumerate(steps, 1):
    cut = k <= CUTS
    if cut:
        say('ZARAZ'); voice('zaraz'); time.sleep(3)
        pos = os.path.getsize(f'{D}/log/P002.log')
    say(f'decyzja {k}/{len(steps)}: {r["number"]} stan {state} {panel("status", r["source"], r["id"], str(r["revision"]), str(state)).strip()[:40]}')
    if cut:
        f = wait_flood()
        if f is None:
            say('BRAK ROZSYŁANIA B w 120 s')
            continue
        t = time.time(); say(f'TERAZ (rozsyłanie seq {f["v3"]["seq"]})'); voice('teraz')
        lost, back = wait_cut(pos)
        say(f'odcięcie {lost}, powrót {back}')
        marks.write(f'{t:.3f} decyzja {r["number"]} stan {state} odcięcie {lost}\n'); marks.flush()
        time.sleep(30)
    else:
        time.sleep(20)
say('decyzje wysłane; czekam 10 min na doręczenie')
time.sleep(600)
q = json.loads(panel('queue'))
say('stany: ' + str({r['number']: r['state'] for r in q['reports'] if r['number'] in {x['number'] for x in reports}}))
say('P12 DONE')

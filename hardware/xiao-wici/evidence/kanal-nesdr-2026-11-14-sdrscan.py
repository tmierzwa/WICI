"""Pomiar kanału NESDR: rtl_sdr -f 869300000 -s 1024000 -g G - | python sdrscan.py OUT_PREFIX SECONDS
Bloki 10 ms (10 widm FFT 1024, 1 kHz na pas). Zapis:
  OUT_PREFIX-events.jsonl: emisje (ciąg bloków z mocą w paśmie ≥ szum + 8 dB): start, czas, częstotliwość szczytu, szerokość −10 dB, szczyt nad szumem
  OUT_PREFIX-minutes.jsonl: co minutę zajętość (udział bloków z emisją) w 869,40–869,65 MHz, w naszym kanale 869,4625–869,5875 i poza nim, poziom szumu."""
import sys, time, json, numpy as np
FC, FS, N = 869.300e6, 1.024e6, 1024
out, dur = sys.argv[1], float(sys.argv[2])
freqs = FC + np.fft.fftshift(np.fft.fftfreq(N, 1 / FS))
win = np.hanning(N)
sub = (freqs >= 869.40e6) & (freqs <= 869.65e6)
ours = (freqs >= 869.4625e6) & (freqs <= 869.5875e6)
rest = sub & ~ours
guard = np.abs(freqs - FC) < 5e3  # prążek DC
sub &= ~guard
BLK = 10 * N  # 10 ms
ev = open(out + '-events.jsonl', 'a', buffering=1); mn = open(out + '-minutes.jsonl', 'a', buffering=1)
noise = None; cur = None; t0 = time.time(); minute = None; mstat = None
def close_event(e):
    e['dur_ms'] = round((e['end'] - e['start']) * 1000); e['start_ts'] = e['start']
    e['start'] = time.strftime('%H:%M:%S', time.localtime(e['start'])) + f".{int(e['start']*1000)%1000:03d}"
    del e['end']; ev.write(json.dumps(e) + '\n')
src = sys.stdin.buffer
while time.time() - t0 < dur:
    raw = src.read(BLK * 2)
    if len(raw) < BLK * 2: break
    now = time.time()
    x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 127.5) / 127.5
    iq = (x[0::2] + 1j * x[1::2]).reshape(10, N)
    p = np.mean(np.abs(np.fft.fftshift(np.fft.fft(iq * win, axis=1), axes=1)) ** 2, axis=0)
    db = 10 * np.log10(p + 1e-12)
    floor = np.median(db[sub])
    noise = floor if noise is None else (0.999 * noise + 0.001 * floor if floor < noise + 3 else noise)
    hot = db > noise + 8
    hs, ho, hr = hot[sub].sum(), hot[ours].sum(), hot[rest & ~guard].sum()
    active = hs >= 5  # co najmniej 5 kHz ponad szumem
    m = int(now // 60)
    if m != minute:
        if mstat: mn.write(json.dumps(mstat) + '\n')
        minute = m; mstat = {'minute': time.strftime('%H:%M', time.localtime(now)), 'blocks': 0, 'busy_sub': 0, 'busy_ours': 0, 'busy_rest': 0, 'noise_db': None}
    mstat['blocks'] += 1; mstat['noise_db'] = round(float(noise), 1)
    mstat['busy_sub'] += int(active); mstat['busy_ours'] += int(ho >= 5); mstat['busy_rest'] += int(hr >= 5)
    if active:
        k = int(np.argmax(np.where(sub, db, -1e9))); pk = float(db[k] - noise)
        above = np.where(sub & (db > db[k] - 10))[0]
        bw = float(freqs[above.max()] - freqs[above.min()] + 1e3) if len(above) else 0
        if cur is None: cur = {'start': now - 0.01, 'end': now, 'peak_db': pk, 'f_mhz': round(freqs[k] / 1e6, 4), 'bw_khz': round(bw / 1e3)}
        else:
            cur['end'] = now
            if pk > cur['peak_db']: cur.update(peak_db=pk, f_mhz=round(freqs[k] / 1e6, 4), bw_khz=round(bw / 1e3))
    elif cur is not None and now - cur['end'] > 0.03:
        cur['peak_db'] = round(cur['peak_db'], 1); close_event(cur); cur = None
if mstat: mn.write(json.dumps(mstat) + '\n')

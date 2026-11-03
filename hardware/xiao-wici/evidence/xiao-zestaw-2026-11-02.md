# Zestaw prób 2026-11-02: dwa XIAO, jeden przeskok

Wspólny opis dla raportów prób 2, 4, 5 i 11 z tego dnia ([v3-ramki](v3-ramki-2026-11-02.md), [hack](hack-2026-11-02.md), [w10](w10-2026-11-02.md), [cisza](cisza-2026-11-02.md)).

## Sprzęt i obrazy

| Urządzenie | Rola | Numer USB | Obraz |
|---|---|---|---|
| XIAO nr 1 (Seeed 102010611) | root, `role: "wezel"`, numer 1 | `44B176AD28A0` | `xiao` (`fw` `xiao-0.1`), wersja niżej |
| XIAO nr 2 (Seeed 102010611) | stacja schronienia A, numer 20, rodzic 1, bez rodzica zapasowego | `68EE8F60D16C` | jak wyżej |
| RAK4631 nr 1 | podsłuch, `tools/monitor.py` | `usbmodem101` | `lora-raw-0.2` |

Obrazy XIAO według czasu:

- do 20:55 (próby 2, 4a, 11): firmware z commitu `7dcf4be` (PR #181, pierwszy commit);
- od 21:15 (próby 4b, 5): firmware z commitu `d7a33ae` (sprawdzanie podpisu BEACON w zadaniu w tle, stacja bez nieudanej próby przy zajętym miejscu, nauka dróg w dół po KISS 0).

Aplikacja stanowiska: `python -m wici.stanowisko start` z czystej kopii commitu (`7dcf4be`, od próby 4b z kodem laptopa `d7a33ae`, w próbie 5 `544e097`), nośnik testowy, port danych roota `usbmodem44B176AD28A03`, panel 8780, `--diagnostyka brak`.

## Plan sieci (bez kluczy)

Sieć `id` 100, root 1, odbiorca główny 2, zapasowy 3. Root ma w `priority_keys` stację 20 (bez `behind`), stacja 20 ma roota 1. Profil LoRa pilotażu (869,525 MHz, SF7, 125 kHz, CR 4/5, preambuła 24). Moc stacji 13 dBm, podsłuch −9 dBm (tylko odbiór). Urządzenia na stole w odległości kilkudziesięciu centymetrów; RSSI w podsłuchu od −35 do −25 dBm.

## Odchylenia od procedury

- Tylko dwa XIAO: root i stacja A w jednym przeskoku. Przekaźnika B (l0 nr 2) nie ma, więc kryteria dla B dotyczą tu roota.
- Zestaw XIAO nie zastępuje prób na prototypie (README, „Role”).
- Podsłuch dwa razy stracił połączenie USB z komputerem: o 20:51:48 (monitor bez ponownego łączenia zakończył pracę; przerwa do 20:52:14) i w próbie 5 (wiersz `gap` w `podsluch-2026-11-02e.jsonl`). `lora-raw-0.1` zawieszał się w takiej chwili (`Serial.write` czekał bez końca), dlatego w tej sesji wgrano `lora-raw-0.2` (zapis bez blokowania, watchdog) i `monitor.py` z ponownym łączeniem.

## Surowe logi

- `podsluch-2026-11-02c.jsonl`: 20:45–20:51 (próby 2, 4a i początek 11), urwany utratą USB o 20:51:48;
- `podsluch-2026-11-02d.jsonl`: 20:52–21:21 (dalsza część próby 11, próba 4b);
- `podsluch-2026-11-02e.jsonl`: 21:31–21:38 (próba 5);
- `stanowisko-2026-11-02{c,e,f}.log`: czasy przyjęcia każdej koperty na stanowisku (kolejka i przyjęcie w ms).

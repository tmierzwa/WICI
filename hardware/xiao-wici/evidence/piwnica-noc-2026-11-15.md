# Noc w piwnicy: kandydaci CHANNEL i próba 17 (2026-11-15, 20:38–00:29)

Procedura: [próba 17](../README.md#próba-17-alarm-zagłuszania-kanału) i kandydaci `CHANNEL` (PR 222). Obrazy z `main` `ac5893e4` (z PR 220, 222 i 224). Plan łańcucha z próby 12: A (P001, 20) → XIAO nr 2 (30) → B (P002, 10) → root (XIAO nr 1).

Węzeł wrogi: RAK4631 bez klucza sieci, śmieciowe ramki, −9 dBm, wkład przewodzony (`tools/hostile.py --mode junk --conducted`). Każdy przebieg ma własny podsłuch (RAK4631 nr 1) i własny zapis węzła wrogiego. Co około 10 s skrypt czytał `P1`, `INFO` i `APP` ze wszystkich czterech węzłów.

Dowody:
- przebieg całej nocy: `piwnica-noc-l0-2026-11-15.out`, skrypt `piwnica-noc-skrypt.sh`;
- węzeł wrogi: `wrogi-{kand00,kand11,jam50,jam70,jam90}-l0-2026-11-15.jsonl`;
- podsłuch: `podsluch-{kand11,jam50,jam70,jam90}-l0-2026-11-15.jsonl`.

**Odstępstwa od planu.**
- Przebiegi z kandydatami skrócono z 2 h do około 45 min (kand00: 44 min, kand11: 45 min). Właściciel uznał, że po doręczeniu zgłoszeń dalsze czekanie nic nie wnosi na tym etapie.
- Przebieg kand00 nie ma podsłuchu, bo ścieżka zapisu w skrypcie była względna. Liczniki z węzłów są pełne. Porównanie czasów HACK z podsłuchu jest więc tylko dla kand11.

## Kandydaci `CHANNEL 0 0` i `CHANNEL 1 1` przy zajętości 50%

Na A `REQ 20`. Zajętość kanału przez węzeł wrogi wynosiła 0,500 w obu przebiegach.

| | `CHANNEL 0 0` (kand00) | `CHANNEL 1 1` (kand11) |
|---|---|---|
| 20 zgłoszeń na stanowisku, `intents` 0 na A | po 701 s | po 590 s |
| B: nadane / odmowy CAD / ponowienia CAD przed HACK | 51 / 96 / – | 67 / 50 / 27 |
| root: nadane / odmowy / ponowienia | 37 / 37 / – | 47 / 22 / 10 |
| XIAO nr 2: nadane / odmowy / ponowienia | 18 / 32 / – | 28 / 19 / 9 |
| A: nadane / odmowy / ponowienia | 8 / 17 / – | 17 / 15 / 4 |
| B: `qfull` (kolejka pełna) | 32 / 26 | 75 / 52 |
| HACK z podsłuchu: najdłuższy czas od DATA | brak podsłuchu | 200,3 ms (jeden powyżej 200 ms z 160); `end_ms_max` w węzłach 175–189 ms |
| restarty, `loop_max_ms` | bez zmian w przebiegu; `loop_max_ms` do 381 ms | bez zmian |

`CHANNEL 1 1` doręczył 20 zgłoszeń o 16% szybciej i z mniej więcej połową odmów CAD. Ponowienia CAD przed HACK mieszczą się w oknie HACK: jeden HACK z 160 przyszedł po 200,3 ms. Ceną jest częstsza pełna kolejka na B. To jeden przebieg na kandydata, z innym ziarnem węzła wrogiego, więc różnica 16% jest wskazówką, nie pomiarem.

## Próba 17: alarm zagłuszania przy 50, 70 i 90%

`CHANNEL 0 0`, na A `REQ 5`, węzeł wrogi 20 min, przerwa 10 min między przebiegami. `JAM_ALARM_MS` 5 min.

| Zajętość | `intents` 0 na A | Najdłuższy `no_gap_ms` (A / B / root / XIAO nr 2) | `channel_jammed` |
|---|---|---|---|
| 0,500 | po 234 s | 5,0 / 3,1 / 2,7 / 4,4 s | nigdzie |
| 0,700 | po 393 s | 13,4 / 13,4 / 14,9 / 9,8 s | nigdzie |
| 0,900 | po 1254 s, 82 s po końcu zagłuszania | 1171 / 14,9 / 0 / 16,3 s | tylko A, 00:04:30–00:19:01, 88 odczytów |

Przy 90% A podniosła alarm około 5 min po starcie węzła wrogiego (23:59:06) i zdjęła go po jego końcu. Węzeł wrogi przy 90% nadaje ramki niemal bez przerw. A miała zgłoszenia do wysłania i przez 19,5 min nie znalazła wolnego okna. Pięć zgłoszeń doszło po końcu zagłuszania, każde raz.

**Alarm tylko z ruchem do wysłania.** B, root i XIAO nr 2 nie podniosły alarmu przy 90%, choć słyszały ten sam kanał. Nie miały nic do wysłania, więc nie szukały wolnego okna. Root miał `no_gap_ms` 0 przez cały przebieg. W tym obrazie alarm zagłuszania mówi o tym, że stacja nie może nadać, nie o samym stanie kanału.

**Rozbieżność na B: usterka licznika.** `no_gap_ms_max` na B skoczył z 17,1 s do 361,4 s o 00:19:18, po końcu zagłuszania, w stanie `wait_debt`. `channel_jammed` był cały czas `false`. Sesja od programu ustaliła, że licznik połączył zajęty kanał z czasu zagłuszania z jednym zajętym kanałem kilka minut później. W tej przerwie B niczego nie próbował nadać. Czekanie na limit czasu nadawania samo się nie liczy. Poprawka: po przerwie bez prób dłuższej niż `JAM_ALARM_MS` czas liczy się od nowa. Wartość 361,4 s jest więc zawyżona i nie wchodzi do progu. Wynik na A jest prawidłowy.

**Pamięć B.** `heap_free` i `heap_min` na B spadły w przebiegu jam90 o około 6,3 kB (z 147948 / 142368 do 141612 / 136032). W poprzednich przebiegach nie zmieniały się. Sprawdzić przy dłuższym ruchu, czy wracają.

## Próg alarmu

Przy zajętości do 70% najdłuższa przerwa bez wolnego okna wyniosła 15 s, a przy 50% (zwykły ruch) 3–8 s. Próg 5 min ma więc zapas 20 razy względem 70% i 40 razy względem 50%. Przy 90% A przekroczyła próg i alarm był prawdziwy. Zostawiam `JAM_ALARM_MS` 5 min.

Górną granicę `no_gap_ms` przy zwykłym ruchu bez węzła wrogiego da 24 h ruchu przy stole. Ta próba jeszcze się nie odbyła.

## Wynik

- Próba 17: **spełniona częściowo**. Na A alarm przy 90% po około 5 min i brak alarmu przy 50 i 70%. Przekaźnik i root bez ruchu nie alarmują, zgodnie z R3-43. Rozbieżność `no_gap_ms_max` na B to usterka licznika, poprawka w programie. Do zamknięcia brakuje:
  - decyzji specyfikacji, czy alarm na B i roocie bez własnego ruchu jest wymagany (kryterium odbioru tego wymaga, R3-43 nie; ewentualnie R3-44);
  - odczytu alarmu w panelu stanowiska przy 90% (krok 2), krótki przebieg w piwnicy;
  - 24 h zwykłego ruchu bez węzła wrogiego (krok 3), na obrazie z poprawką licznika.
- Kandydaci: `CHANNEL 1 1` szybszy i z mniejszą liczbą odmów CAD, bez przekroczenia okna HACK poza jednym przypadkiem 200,3 ms. Wybór kandydata należy do sesji od programu.

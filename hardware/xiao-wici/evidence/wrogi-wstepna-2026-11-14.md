# Wstępna próba 9 w eterze: węzeł wrogi przy 10% zajętości (2026-11-14)

**To nie jest próba 9.** Próba 9 wymaga 50% czasu kanału przez 2 h w każdym przebiegu, w torze przewodowym albo w komorze. W eterze podzakres 869,4–869,65 MHz pozwala nadawać najwyżej 10% czasu, więc węzeł wrogi pracował z celem 10% (`hostile.py` bez `--conducted`) i po 30 min w każdym przebiegu, na prośbę właściciela. Wynik pokazuje zachowanie łańcucha przy słabszym obciążeniu i nie zalicza kryterium próby 9 ani punktu 2 warunku przyjęcia D21.

Sprzęt, obrazy i plan sieci (łańcuch A → B → root): [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md). Węzeł wrogi: RAK4631 nr 2 z `lora-raw-0.2` (wgrany przed próbą w miejsce `lora-raw-0.1`), antena, na stole obok B, −9 dBm. Przebieg skryptem: `wrogi-junk-l0-2026-11-14.out`, `wrogi-keyed-l0-2026-11-14.out` (`APP` A co 25 s, `RNS` B co minutę, `HACK`, `RNS`, `INFO`, `P1`, `LOG` B przed i po). Ramki wrogie: `wrogi-junk-l0-2026-11-14.jsonl`, `wrogi-keyed-l0-2026-11-14.jsonl`. Podsłuch: `podsluch-l0-2026-11-14.jsonl`.

## Przebiegi

| | (a) bez klucza | (b) z kluczem sieci |
|---|---|---|
| polecenie | `hostile.py --mode junk --occupancy 0.1 --duration 1800 --power -9 --seed 91401` | `hostile.py --mode keyed --occupancy 0.1 --duration 1800 --power -9 --seed 91402 --net-id 100 --dst 10` (kod sieci z pliku) |
| czas | 11:51:05–12:21:10 | 12:21:45–12:51:50 |
| ramki wrogie | 738 losowych, 180,3 s nadawania | 329 rozsyłanych DATA z losowymi kopertami, 158 BEACON z błędnymi podpisami, 155 jednoadresowych DATA z ACKREQ do B, 152 HACK z błędnym tagiem pary; 180,5 s |
| osiągnięta zajętość (skrypt) | 10,01% | 10,02% |
| `REQ 20` na A | 11:51:25 | 12:22:06 |
| przyjęte na stanowisku | 20/20, każde raz, 11:51:27–11:57:11 (5 min 44 s) | 20/20, każde raz, 12:22:08–12:26:41 (4 min 33 s) |
| HACK B / root / A (podsłuch, najdłużej) | 101,0 / 114,3 / 117,4 ms | 105,5 / 115,3 / 109,5 ms |
| `HACK` B na końcu | `hack_sent` 88, `end_ms_max` 100, `hack_late` 0, `hack_refused` 0 | `hack_sent` 75, `end_ms_max` 105, `hack_late` 0, `hack_refused` 8 (CAD 7, odbiór w toku 1; nadawca ponowił) |
| BEACON w B | – | `beacon_checks` 8 w 30 min, `beacon_check_ms_max` 69, `beacon_dropped` 0 |
| restart B | brak (`restarts` 10 przez cały czas) | brak |
| RAM B (`heap_min` / `heap_size`) | 142 544 / 206 160 B (69%), bez zmian | 142 544 / 206 160 B (69%), bez zmian |
| `rx_bad` B | 1 → 5 | 5 → 8 |

Podsłuch w przebiegu (a): klasa `other` (ramki wrogie bez bitów wersji v3) 705 ramek, 170,9 s; sieć: DATA 54,8 s, HACK 14,7 s, BEACON 2,5 s; razem 13,5% czasu kanału.

## Wynik

Przy 10% zajętości łańcuch przeniósł 20/20 zgłoszeń w obu przebiegach w czasie porównywalnym z czystym kanałem ([próba 4](hack-2026-11-14.md): około 5 min). B się nie restartowało, sterta nie zmalała, każdy HACK w podsłuchu kończył się najwyżej 117,4 ms po swojej DATA. Fałszywe BEACON-y nie wymusiły kosztownych sprawdzeń podpisu (8 sprawdzeń na 158 fałszywych BEACON-ów i BEACON-y sieci).

Nie sprawdzono: 50% zajętości, 2 h na przebieg, udziałów klas K1/K2 na B w oknie godzinnym, liczników odrzuceń ramek z błędnym tagiem pary (program ich nie wypisuje w `HACK` ani `P1`), RAM i FRAM ±5% po 2 h.

`loop_max_ms` B wynosiło 285 ms już przed przebiegiem (a) i nie zmieniło się w obu przebiegach.

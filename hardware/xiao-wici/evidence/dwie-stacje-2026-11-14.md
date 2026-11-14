# Próba 8: dwie stacje schronienia przez jeden przekaźnik l0 (2026-11-14)

Sprzęt, obrazy i plan sieci: [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md). Przebieg skryptem: `dwie-stacje-l0-2026-11-14.out` (`APP` A i C co 20 s, na końcu `HACK`, `P1`, `RNS` B oraz `P1` A i C). Podsłuch: `podsluch-l0-2026-11-14.jsonl` (10:56–11:09:40). Przyjęcia: `kolejka-dwie-stacje-l0-2026-11-14.json`.

Stacja A: P001 (l0), numer 20, rodzic 10. Stacja C: XIAO nr 2, numer 30, rodzic 10. Obie z kluczem B (10) i roota (1) w `priority_keys`; B ma klucze 1, 20 i 30, root ma B z `behind` [20, 30]. Stacja 30 zaufana w panelu kartą numerowaną o 10:18:59.

## Przebieg

`HACK 0` na B, `REQ 25` na A o 10:56:07,2 i `REQ 25` na C o 10:56:07,7 (`sa1_bytes` 81). `APP` na obu co 20 s do `intents` 0 (11:09:36).

## Wynik

| | A (20) | C (30) |
|---|---|---|
| przyjęte na stanowisku | 25/25, każde jeden raz | 25/25, każde jeden raz |
| pierwsze / mediana / ostatnie przyjęcie | 10:56:09 / 10:59:59 / 11:06:38 | 10:56:16 / 10:59:05 / 11:04:58 |
| `APP`: `delivered` / `failed` | +25 / 0 | 25 / 1 (próba bez potwierdzenia, ponowiona) |
| HACK stacji w dół (podsłuch, średnio / najdłużej) | 105,3 / 109,4 ms (56) | 98,6 / 101,1 ms (53) |
| DATA do B (z ponowieniami) | 167 | 162 |
| DATA do roota z pominięciem B (bez HACK) | 80 | 77 |

Przyjęcia na minutę (A, C): 10:56 (4, 4), 10:57 (2, 3), 10:58 (2, 5), 10:59 (5, 1), 11:00 (1, 3), 11:01 (4, 2), 11:02 (2, 1), 11:03 (1, 3), 11:04 (1, 3), 11:06 (3, 0). Obie stacje przechodzą na przemian przez cały czas; żadna nie czeka, aż druga skończy.

B: `hack_sent` 203, `end_ms_max` 106, `hack_late` 0, `hack_over_200ms` 0; podsłuch: HACK B 204, średnio 98,5 ms, najdłużej 106,5 ms. Root: HACK 93, najdłużej 114,2 ms. `P1` B: `deferrals` 122 (`long_deferrals` 23), `cad_busy` 2, `tx_drop` 0, `rx_bad` 0.

Kryterium spełnione: 50/50 RECEIVED, żadna stacja nie blokuje drugiej, czasy obu źródeł zapisane osobno (wyżej i w migawce kolejki).

## Uwagi

- Obie stacje, jak A w [próbie 4](hack-2026-11-14.md#ponowienia), po odrzuceniach przez B przełączają się na roota, który nie zna ich kluczy i nie potwierdza. Na stole kosztuje to około 157 ramek bez HACK.
- 50 zgłoszeń z dwóch stacji szło 10,5 min; 50 zgłoszeń z jednej stacji w próbie 5 szło 13 min.

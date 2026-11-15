# Próba 10: trzy skoki A → C → B → root (2026-11-14)

Sprzęt i obrazy: [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md). Przebieg skryptem: `trzy-skoki-l0-2026-11-14.out` (`APP` A co 20 s, na końcu `HACK` i `P1` na C, B i roocie). Podsłuch: `podsluch-l0-2026-11-14.jsonl` (13:39:28–13:44). Przyjęcia: `kolejka-trzy-skoki-l0-2026-11-14.json`.

## Plan sieci (bez kluczy)

Sieć 100, root 1, odbiorca 2 i 3, rodzic zapasowy 0. Tryb przygotowania na P001, P002 (PRZYGOT 3 s) i XIAO nr 2 (`PREP 1` i BOOT), `configure` o 13:38–13:39, `PREP 0`, `rns_state` `running` na wszystkich czterech. Root bez zmian.

| Stacja | `network` | `priority_keys` |
|---|---|---|
| root (XIAO nr 1) | 1, rodzic 0 | 10 z `behind` [20, 30] (bez zmian) |
| B (P002, l0) | 10, rodzic 1 | 1, 30 (bez A: A nie dostanie HACK od B) |
| C (XIAO nr 2), przekaźnik | 30, rodzic 10 | 10, 20, 1 |
| A (P001, l0) | 20, rodzic 30 | 30, 1 |

## Przebieg

`HACK 0` na C, B i roocie, `REQ 10` na A o 13:39:28 (`sa1_bytes` 81). `APP` na A: 10 dostarczonych, `failed` 0, `intents` 0 o 13:43:40.

## Wynik

| | Wynik |
|---|---|
| przyjęte na stanowisku | 10/10, każde raz, 13:39:31–13:43:04 |
| koperty zgłoszeń w podsłuchu | 10/10 przechodzą 20 → 30, 30 → 10, 10 → 1, każdy skok z HACK (dopasowanie po treści koperty bez nagłówka i znaczników) |
| `HACK` C (XIAO nr 2) | `hack_sent` 33, `end_ms_max` 99, `hack_late` 0, `hack_refused` 0 |
| `HACK` B (P002) | `hack_sent` 72, `end_ms_max` 101, `hack_late` 0, `hack_refused` 0 |
| `HACK` root | `hack_sent` 31, `end_ms_max` 111, `hack_late` 0 |
| HACK w podsłuchu (najdłużej) | C 99,8 ms (34), B 101,5 ms (74), root 111,8 ms (31) |
| DATA bez HACK | A → C 4, C → B 1 |

Kryterium spełnione: 10/10 RECEIVED, każda koperta zgłoszenia przechodzi trzy skoki z HACK na każdym. Wyniki C jako przekaźnika (XIAO) zapisane osobno od wyników B (l0), zgodnie z README.

## Droga w dół

RECEIVED ze stanowiska idzie root → B (DATA 98 B do 10, z HACK B). B nie zna drogi w dół do 20 (A nie jest jego sąsiadem, a stacja nie ma `behind`), więc rozsyła ramkę (16 DATA z `l_dst` 65535). C przekazuje ją do A (3 DATA 30 → 20). Na stole A słyszy też rozesłaną ramkę B bezpośrednio.

Koperty potwierdzeń A (56–64 B) przechodzą trzy skoki z HACK na każdym, poza 4 kopertami 56 B, które podsłuch widział tylko na skoku A → C bez HACK (do 13:44:13). Wszystkie 10 zgłoszeń ma na stanowisku jeden wiersz przyjęcia, a A skończyła z `intents` 0, więc te koperty nie zatrzymały zgłoszeń; nie sprawdzono, czy ich liczniki wyszły później w innej kopercie potwierdzeń.

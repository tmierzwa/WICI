# Próba 12: rozsyłanie w dół i utrata drogi w górę, trzy skoki (2026-11-15, 14:01–15:17)

Procedura: [próba 12](../README.md#próba-12-rozsyłanie-w-dół-i-utrata-drogi-w-górę). Obrazy z `main` `ac5893e4`. Podsłuch: `podsluch-l0-2026-11-15.jsonl`.

Plan trzech skoków (jak w próbie 10): A (P001, 20) → XIAO nr 2 (30, przekaźnik) → B (P002, 10) → root (XIAO nr 1). `behind` ma tylko root, więc B nie zna drogi do A i każdą wiadomość do A rozsyła. W kroku 3 A dostała B jako rodzica zapasowego (B i A mają się nawzajem w `priority_keys`).

Dowody:
- przebieg kroków 1 i 2: `rozsylanie-l0-2026-11-15.out`, skrypt `rozsylanie-p12.py`, chwile odcięć B `rozsylanie-chwile-l0-2026-11-15.txt`;
- koperty z podsłuchu: `rozsylanie-koperty-l0-2026-11-15.json` (`tools/envelopes.py`, cały podsłuch do 15:17);
- przebieg kroku 3: `utrata-drogi-l0-2026-11-15.out`.

## Krok 1 i 2: rozsyłanie w dół z restartem B

`REQ 10` na A o 14:01:10: 10 zgłoszeń, wszystkie na stanowisku raz, `intents` 0 o 14:04:10. Potem 20 decyzji w dół, co 20 s: PRZECZYTANE (stan 2) i ZAMKNIĘTE (stan 6) dla każdego zgłoszenia. Przy pierwszych pięciu skrypt czekał na rozsyłanie przez B (DATA od 10 z `l_dst` 65535) i dawał sygnał. Właściciel odłączał P002 0,8–0,9 s po rozsyłaniu, na 7 s.

| Kryterium | Wynik |
|---|---|
| każdy węzeł rozsyła kopertę najwyżej raz, także po restarcie w oknie 120 s | spełnione: 68 rozsyłanych kopert, `repeated_floods` 0; po pięciu restartach B żadnej z nich nie rozesłał drugi raz |
| żaden nonce się nie powtarza | spełnione: 522 koperty, `nonce_reuse` 0 |
| zgłoszenia dokładnie raz | spełnione: 10/10 |
| decyzje doszły do A | stanowisko: wszystkie 20 wysłane (`unsent` 0), jedna wiadomość bez dowodu doręczenia (`forwarded_unconfirmed` 1); licznik `received` na A od 0 po konfiguracji do 61 |
| tranzyt i BEACON-y przekaźnika ≤60% godziny, BEACON-y ≤2% | spełnione: w godzinie 14–15 B nadawał przez 0,80%, XIAO nr 2 przez 0,78%, root przez 0,67%; BEACON-y każdego 0,03% |

**Co robi sieć, gdy B jest wyłączony.** Root nie dostaje HACK od B i po nieudanych nadaniach sam rozsyła decyzję w dół (DATA od 1 z `l_dst` 65535, np. 14:04:24–14:04:29 przy pierwszym odcięciu). B po starcie przekazuje rozsyłaną kopertę od swojego rodzica najwyżej raz. XIAO nr 2 dostaje rozsyłanie od swojego rodzica B i przekazuje je do A jednoadresowo.

**Ograniczenie.** Licznik `received` na A obejmuje też RECEIVED dla 10 zgłoszeń i resztę decyzji z porannego zamykania starych zgłoszeń, więc nie wykazuje osobno każdej z 20 decyzji. Obraz stacji nie ma polecenia, które wypisze stan każdego wpisu rejestru. Doręczenie każdej decyzji wykazuje stanowisko (dowody doręczenia), z jednym wyjątkiem w toku.

## Krok 3: utrata drogi w górę

`SILENCE 1` na XIAO nr 2 (rodzic A z planu) o 15:14:50, `REQ 5` na A.

| Sprawdzenie | Wynik |
|---|---|
| A nadaje do XIAO nr 2 bez HACK | 9 DATA 20 → 30 od 15:14:51; XIAO nr 2 nie nadał nic do 15:16:59 (po zdjęciu ciszy) |
| przejście na rodzica zapasowego | pierwsza DATA 20 → 10 o 15:15:03, 12 s po pierwszej próbie; B potwierdza HACK |
| brak rozsyłania w górę | w podsłuchu żadnej DATA od A z `l_dst` 65535 |
| zgłoszenia | 5/5 na stanowisku raz; `intents` 0 o 15:16:57, po 127 s |

Decyzje i RECEIVED do A szły w tym kroku od B jednoadresowo, bo A jest w tym planie sąsiadem B.

## Wynik

Kryteria spełnione: rozsyłanie w dół najwyżej raz na węzeł, także po restarcie przekaźnika w oknie 120 s; po utracie rodzica stacja przechodzi na rodzica zapasowego bez rozsyłania w górę; zgłoszenia dokładnie raz; czas nadawania przekaźników daleko poniżej limitów. Zakres 15 skoków i rozsyłania w długim łańcuchu zostaje dla emulatora.

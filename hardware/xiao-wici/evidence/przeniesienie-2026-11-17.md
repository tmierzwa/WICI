# Próba 16: przeniesienie stacji B między prototypami L0 (2026-11-17, 15:33–17:08)

Procedura: [próba 16](../README.md#próba-16-przeniesienie-stacji), wersja uproszczona: jedno przerwanie na krok zamiast dwóch z planu pilotażu. Przy stole po przeniesieniu sprzętu z piwnicy, bez węzła wrogiego.

Plan łańcucha: A (P001, 20) → B (P002, 10) → root (XIAO nr 1), XIAO nr 2 (30) z rodzicem B. Oba XIAO przygotowane od nowa tego dnia (nowe karty), więc numer 30 przepięty w stanowisku na nowy klucz. Obrazy bez zmian od próby 17: root z `main` `86c0e44a`, reszta z `29d15b10`. Przeniesienie poleceniem `python -m wici --migrate-source-port … --migrate-target-port …`. Przebiegi z przerwaniem zatrzymywał po wybranym kroku pomocniczy skrypt `mig.py`, który wywołuje te same kroki protokołu. Wznowienie albo wycofanie zawsze szło zwykłym poleceniem, ponawianym po `not_confirmed`, gdy nikt nie zdążył nacisnąć OK w 30 s.

Dowody: przebieg i odpowiedzi poleceń `przeniesienie-l0-2026-11-17.out`, skrypty `przeniesienie-skrypt.txt`, podsłuch `podsluch-przeniesienie-l0-2026-11-17.jsonl`, wynik `tools/envelopes.py --src 10` z chwilami aktywacji jako `--mark` w pliku `przeniesienie-koperty-l0-2026-11-17.json`.

## Przygotowanie

- `destroy` na P001 (A) i OK na P001: A bez tożsamości i konfiguracji. Przed każdym kolejnym przebiegiem cel w stanie `retired` czyszczono tak samo; stacja w `retired` nie przyjmuje `receive_key` (`migration: target`).
- B (numer 10) nie był na liście zaufanych stanowiska, bo w poprzednich próbach zgłoszenia wysyłały tylko A i XIAO nr 2. Stanowisko odrzucało koperty B z powodem „unknown station number”. Numer 10 dodano kartą numerowaną (tryb przygotowania na B, `card`, zaufanie przez dwóch dyżurnych) o 15:57:25.

## Przebiegi

| Przebieg | Kierunek B | Przerwanie | Aktywacja | Stan po przebiegu |
|---|---|---|---|---|
| 0 | P002 → P001 | brak | 15:48:54 | B na P001, P002 pusty (`retired`) |
| 1 | P001 → P002 | po kroku 1, odłączony cel P002 | 16:12:10 | B na P002, P001 pusty |
| 2 | P002 → P001 | po kroku 2 (eksport), odłączone źródło P002 | 16:39:46 | B na P001, P002 pusty |
| 3 | P001 → P002 | po kroku 3 (import), odłączony cel P002 | 16:55:39 | B na P002, P001 pusty |
| 4 | P002 → P001 | po kroku 4 (`retire`), odłączone źródło P002 | 16:58:51 | B na P001, P002 pusty |
| 5 | P001 → P002 | po kroku 4, przed aktywacją, odłączony cel P002 | 17:01:46 | B na P002, P001 pusty |
| 6 | P002 → P001 | wycofanie `--migrate-abort` po kroku 2 | – (wycofanie 17:03:14) | B na P002 w zwykłej pracy, P001 pusty |

- Po każdym odłączeniu prototyp po ponownym podłączeniu miał ten sam stan przeniesienia i ten sam `mid` (`receiving`, `export`, `imported`, `retired`), a ponowione polecenie dokończyło przeniesienie bez dodatkowych kroków. W przebiegu 2 źródło po odłączeniu wydało tę samą paczkę (SHA-256 `5e22e2f6…` przed i po), bez ponownego OK.
- W przebiegu 6 cel był w `receiving` bez importu, więc wycofanie nie wymagało potwierdzenia na celu. Po nim B na P002 wyszedł z trybu przygotowania i dalej nadawał z tą samą tożsamością.
- Po każdym przebiegu `INFO`, `RNS` i `migrate` `status`: dokładnie jeden prototyp z tożsamością B (`6be96288…`) w zwykłej pracy, drugi pusty (tożsamość zerowa, tryb przygotowania).

**Zgłoszenia czekające przy przeniesieniu.**
- Przebieg 0: `REQ 3` na B tuż przed przeniesieniem nie dał zgłoszeń czekających w kolejce. Tryb przygotowania nie wstrzymuje nadawania, więc B wysłał wszystkie trzy w 7 s (15:46:46–53), zanim operator nacisnął OK. Stanowisko je odrzuciło, bo B nie był jeszcze zaufany, więc w chwili eksportu czekały na RECEIVED. Nowy B na P001 ponowił je po 10 min (15:57:08–14), na kilkanaście sekund przed dodaniem numeru 10, i dalej co 30–60 min.
- Przebieg 2: na B `SILENCE 1` i `REQ 3` przed eksportem, więc trzy zgłoszenia (7807, 5138, 9461) w chwili eksportu nie były wysłane (`unsent` 3). Nowy B na P001 wysłał je 2 s po aktywacji (16:39:48–58).
- Na końcu w panelu jest wszystkich 7 zgłoszeń B (7518, 7493, 5817, 7807, 5138, 9461 i 6868 wysłane po wycofaniu), każde raz; B nie ma zgłoszeń czekających (`intents` 0).

**Liczniki kopert** (`envelopes.py`, para B → odbiorca 2): ostatni licznik przed przeniesieniem i pierwszy po nim.

| Chwila | Przed | Po |
|---|---|---|
| przebieg 0 | 2 | 64 |
| przebieg 1 | 66 | 128 |
| przebieg 2 | 129 | 192 |
| przebiegi 3, 4, 5 i wycofanie w przebiegu 6 | 197 | 256 |

Między przebiegami 3 i 6 B nie nadał żadnej koperty, więc pierwsza koperta po każdej z tych chwil to ta sama 256. 23 koperty, żaden nonce się nie powtórzył.

**Stary prototyp po eksporcie nie nadaje.** Między eksportem a aktywacją podsłuch nie odebrał żadnej ramki z adresem łącza B (10). Po aktywacji ramki B pojawiały się tylko z nowego prototypu (koperty z nowym blokiem licznika).

**Alarm na ekranie po odłączeniu w trakcie przeniesienia.** W każdym przebiegu 1–5 odłączony prototyp po ponownym podłączeniu pokazywał w trybie serwisowym „BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE” i piszczał (cel w `receiving` i `imported`, źródło w `export` i `retired`). Alarm znikał po dokończeniu przeniesienia. Stan przeniesienia był za każdym razem cały, więc to nie uszkodzenie pamięci. Komunikat jednak myli osobę przy stacji: sugeruje utratę zgłoszenia, gdy stacja czeka tylko na dokończenie przeniesienia. Do oceny przez program.

## Przywrócenie A

Pusty P001 dostał nową kartę jako A (`WICI-D7E2C5`, numer 20). Jego klucz trafił do `priority_keys` B (`configure`, plan łańcucha na P002 i P001), a numer 20 w stanowisku przepięto ze starego klucza `WICI-374C8F` na nowy (dwóch dyżurnych). Zgłoszenie 1372 z nowego A dotarło do panelu o 17:08.

## Odstępstwa

- Jedno przerwanie na krok zamiast dwóch (wersja uproszczona procedury).
- Przerwania między krokami, nie w trakcie przesyłania paczki. Krok 5 przerwano przed aktywacją (odłączenie celu po `retire`), bo sama aktywacja trwa ułamek sekundy.
- Za każdym razem odłączano P002. Raz był źródłem (przebiegi 2 i 4), raz celem (1, 3 i 5).
- W przebiegu 0 zgłoszenia nie czekały w kolejce B w chwili eksportu (patrz wyżej); warunek sprawdzono w przebiegu 2 z ciszą na B.

## Wynik

- Pierwsza koperta B z nowego prototypu ma licznik powyżej zarezerwowanej granicy, wielokrotność 64, większy od każdego ze starego: spełnione po każdym przeniesieniu.
- Żaden nonce się nie powtarza: spełnione.
- Stary prototyp po eksporcie nie nadaje: spełnione.
- Zgłoszenia czekające przy przeniesieniu RECEIVED dokładnie raz: spełnione (przebieg 2 oraz zgłoszenia z przebiegu 0, które czekały na RECEIVED).
- Po każdym przerwaniu ponowione polecenie kończy albo wycofuje przeniesienie, nigdy dwie stacje z tą samą tożsamością: spełnione.
- Próba 16 **przeszła** w wersji uproszczonej. Do oceny przez program: alarm „BŁĄD PAMIĘCI STACJI” na prototypie w trakcie przeniesienia.

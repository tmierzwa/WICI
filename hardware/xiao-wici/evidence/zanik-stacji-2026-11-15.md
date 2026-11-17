# Próba 13: zanik zasilania stacji A, łańcuch A → B → root (2026-11-15, 13:01–13:28)

Procedura: [próba 13](../README.md#próba-13-zanik-zasilania-stacji). Obrazy `l0` i `xiao` z `main` `ac5893e4` na wszystkich czterech urządzeniach. Plan łańcucha jak w [zestawie z 14 listopada](l0-zestaw-2026-11-14.md): A = l0 nr 1 (P001, numer 20), B = l0 nr 2 (P002, 10), root = XIAO nr 1, C = XIAO nr 2 (30, rodzic B). Przed próbą A dostała dłuższy adres (64 B, `configure` w trybie przygotowania), żeby `REQ 1 96` dawało SA1 214 B, czyli kopertę w dwóch częściach.

Dowody:
- podsłuch: `podsluch-l0-2026-11-15.jsonl` (cały dzień);
- przebieg skryptem: `zanik-stacji-l0-2026-11-15.out` (sygnały, numery zgłoszeń, chwile odcięć, opóźnienie ręki);
- skrypt: `zanik-stacji-cut13.py`;
- chwile odcięć: `zanik-stacji-chwile-l0-2026-11-15.txt`;
- liczniki kopert: `zanik-stacji-koperty-l0-2026-11-15.json` (`tools/envelopes.py --src 20 --mark …`);
- wpisy panelu: `zanik-stacji-kolejka-l0-2026-11-15.json`.

## Przebieg

Właściciel odłączał przewód USB P001 na głosowy sygnał „teraz” z laptopa (3 s wcześniej „zaraz”) i podłączał go po około 5 s. Prototyp nie ma innego zasilania, więc odłączenie USB to całkowity zanik. Chwilę odcięcia wyznacza zniknięcie portu w logu konsoli. Opóźnienie ręki od sygnału: 0,67–1,97 s, w 16 z 18 przypadków poniżej 1 s.

| Chwila odcięcia | Sygnał | Odcięcia |
|---|---|---|
| zaraz po utworzeniu zgłoszenia (`REQ 1`) | odpowiedź na `REQ` | 3 |
| po HACK całej koperty od B, przed RECEIVED | podsłuch: HACK 10 → 20 | 3 |
| po HACK części 1/2 własnej koperty, przed częścią 2/2 | podsłuch: DATA 20 → 10 z częścią 1, HACK 10 → 20 z jej `seq` | 5 |
| po HACK części 1/2 biuletynu do A, przed częścią 2/2 | podsłuch: DATA 10 → 20 z częścią 1, HACK 20 → 10 | 5 |
| bez ruchu | 3 s po „zaraz” | 2 |

Dwa wcześniejsze odcięcia o 12:54 nie liczą się: rejestr A był pełny (256), więc `REQ` nie utworzył zgłoszenia. Po zamknięciu 80 starych zgłoszeń decyzją 6 próba ruszyła od nowa.

## Wyniki

| Kryterium | Wynik |
|---|---|
| każde zgłoszenie RECEIVED dokładnie raz | spełnione: 11 z 11 zgłoszeń utworzonych w próbie jest w panelu dokładnie raz; `intents` 0 na A po każdym cyklu |
| każdy biuletyn na A dokładnie raz | spełnione: 5 z 5 biuletynów z `done` 2/2 (A i C), skrzynka A `inbox` 5 |
| licznik koperty po starcie powyżej zarezerwowanej granicy | spełnione: we wszystkich 16 odcięciach, po których A nadała nową kopertę, pierwszy `ctr` jest wielokrotnością 64 i większy od każdego wcześniejszego (np. 1129 → 1152, 2048 → 2112) |
| żaden nonce się nie powtarza | spełnione: 380 kopert w podsłuchu, `nonce_reuse` 0 |
| rejestr bez uszkodzeń | spełnione: `STORE` `corrupt_slots` 0, `journal_ok` true, `restarts` 31 |

**Biuletyn po odcięciu w środku.** Na przykład biuletyn 1: A potwierdziła część 1/2 o 13:24:39 i sekundę później straciła zasilanie. B nadał część 2/2 o 13:24:45, gdy A była wyłączona, i ponowił o 13:24:48. A po starcie potwierdziła ją o 13:24:49, złożyła biuletyn z części 1 zapisanej w FRAM i o 13:24:50 wysłała dowód doręczenia.

**Zgłoszenie po odcięciu w środku.** Po odcięciu po części 1/2 A wysyła zgłoszenie od nowa z nowym licznikiem (następny blok 64), a stanowisko przyjmuje je raz.

## Spostrzeżenia

- Po każdym zaniku z czekającym zgłoszeniem A włącza alarm „BRAK POTWIERDZENIA – CZAS OCZEKIWANIA NIEZNANY. GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA” z dźwiękiem, do OK. Po zaniku stacja nie wie, ile minęło od nadania, więc to wersja alarmu bez liczby minut ([teksty ekranu](../../../docs/spec/oprogramowanie.md)).
- Po każdym zaniku pierwszy ekran to wybór języka. Zgodnie ze specyfikacją („Start”: po włączeniu wyłącznikiem głównym pierwszy ekran to wybór języka; po restarcie przez watchdog język z FRAM). Właściciel spodziewał się wyboru języka tylko w menu serwisowym. Pytanie do specyfikacji: czy po zaniku zasilania stacja ma zaczynać od wyboru języka, czy od języka zapisanego w FRAM.
- Rejestr 256 zgłoszeń zapełnia się w kilku dniach prób, bo wpis zwalnia tylko zamknięte zgłoszenie. Przed próbami z wieloma zgłoszeniami trzeba zamykać stare w panelu.

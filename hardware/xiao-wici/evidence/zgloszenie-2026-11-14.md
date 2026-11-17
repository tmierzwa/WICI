# Próba 3: jedno zgłoszenie do końca na l0, łańcuch A → B → root (2026-11-14)

Sprzęt, obrazy i plan sieci: [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md). Eksport rejestru stanowiska: `rejestr-l0-2026-11-14.csv`. Logi konsoli A: `l0-2026-11-14-P001.log`.

Przyciski: właściciel na prawdziwych przyciskach P001 (ekran po angielsku). Panel: API panelu z kontem `dyzurny-1`, jak przeglądarka dyżurnego (`panel.py` w katalogu prób).

## Przebieg

| Krok | Wynik |
|---|---|
| MENU → REQUEST → WATER, 1 osoba, URGENT – A FEW HOURS, bez frazy, OK = SEND (10:23) | ekran wyniku z numerem 0214 |
| przyjęcie na stanowisku | 10:23:27, `odbior`, kategoria 3, 1 osoba, pilność 1, „Schronienie testowe A” |
| panel: PRZECZYTANE (stan 2), 10:24:32 | – |
| panel: PRZEKAZANE DALEJ (stan 4, adresat „PSP / POGOTOWIE / POWIAT”), 10:24:52 | – |
| stacja: MESSAGES → 0214 (10:26) | „FORWARDED (FIRE SERVICE / AMBULANCE / COUNTY)”, DRINKING WATER, 1, URGENT – A FEW HOURS (potwierdził właściciel na ekranie i `SCREEN`) |
| `APP` na A, 10:26:13 | `delivered` 3 (+1), `received` 7 (+2: PRZECZYTANE i decyzja), `failed` 0, `intents` 0 |

W bazie stanowiska jest jedno zgłoszenie 0214 z trzema wierszami (`odbior`, `stan_2`, `stan_4`).

## Wynik

Kryterium spełnione: RECEIVED, PRZECZYTANE i decyzja doszły do A przez przekaźnik B; `intents` 0; jedno zgłoszenie w bazie.

## Usterka: ekran wyniku po dostarczeniu

Po wysłaniu ekran wyniku pokazuje „SAVED IN STATION – WAITING TO SEND” (PL: „ZAPISANE W STACJI – CZEKA NA WYSŁANIE”) i nie zmienia się, gdy zgłoszenie dojdzie. O 10:25:17, ponad półtorej minuty po przyjęciu na stanowisku i po decyzji dyżurnego, ekran nadal mówił „czeka na wysłanie”. Ekran wyniku jest stały (`firmware/src/ui.cpp`, `Screen::RESULT`, `Submit::STORED`), a stan dostarczenia widać tylko w MENU → WIADOMOŚCI. Napis wprowadza w błąd: osoba w schronieniu czyta, że zgłoszenie nie wyszło, choć odbiorca już je przeczytał i przekazał. Zgłoszenie do sesji programu w [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md#zgłoszenia-do-sesji-programu).

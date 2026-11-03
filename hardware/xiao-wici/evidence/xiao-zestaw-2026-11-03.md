# Zestaw prób 2026-11-03: dwa XIAO, jeden przeskok

Ciąg dalszy [prób z 2026-11-02](xiao-zestaw-2026-11-02.md): próba 11 w pełnej długości, próby 4 i 5 przed poprawką dostępu do kanału i po niej, próba 3 z panelem dyżurnego. Pomiary i poprawkę dostępu do kanału opisuje [cca-cad-2026-11-03.md](cca-cad-2026-11-03.md).

## Sprzęt, obrazy i plan sieci

Te same urządzenia, ten sam plan sieci i ta sama aplikacja stanowiska co 2026-11-02 (root `44B176AD28A0`, stacja 20 `68EE8F60D16C`, RAK4631 z `lora-raw-0.2` jako podsłuch, sieć 100, root 1). Stanowisko z commitu `72d4089`, nośnik testowy, panel 8780. Zestaw XIAO trzyma konfigurację w PSRAM: przetrwa wgranie obrazu i restart, nie przetrwa odłączenia zasilania ([README](../README.md#wgranie-i-przygotowanie)). Rano płytki trzeba było więc skonfigurować od nowa.

Obrazy XIAO według czasu:

- od 08:22: firmware z `72d4089`, potem obraz diagnostyczny do pomiarów z [cca-cad-2026-11-03.md](cca-cad-2026-11-03.md);
- od 09:44: poprawka dostępu do kanału, punkty 1 i 2 (RSSI po SetRx, potwierdzony CAD);
- od 10:09: dodatkowo punkt 3 (RSSI zajmuje kanał tylko w oknie ślepoty odbiornika);
- od 10:25: dodatkowo poprawka czasu bezczynności ekranu (niżej, próba 3);
- od 12:40: obraz z `d5d364b` (poprawki przeglądu końcowego, grupa A: okno ślepoty od wygaśnięcia preambuły, termin HACK z zapasem na start TCXO, błąd drugiego CAD odracza, drogi w dół), stanowisko z tego samego commitu.

Przed obrazem z `d5d364b` płytki były odłączone od zasilania. Zestaw XIAO stracił wtedy konfigurację i tożsamość (nowe nazwy: root WICI-E64309, stacja WICI-D17A28), więc trzeba było przygotować je od nowa. Stanowisko trzyma numer 20 związany z kluczem porannej stacji i nie ma operacji, która zwolni numer dla nowego klucza (usunięcie zaufania go nie zwalnia). Nowa stacja dostała więc numer 21. Na l0 i v2 tożsamość jest w FRAM i przetrwa zanik zasilania, ale wymiana albo utrata stacji zestawu XIAO kończy się tak samo.

## Próba 2: ramki v3 (`72d4089`)

| Krok | Wynik |
|---|---|
| `REQ 1 0` na A, 08:25:48 | DATA 119 B od 20, HACK 27 B od roota; bez RECEIVED, bo stanowisko nie ufało jeszcze stacji 20 („nieznany numer stacji”) |
| zaufanie stacji 20 w panelu (dwóch dyżurnych) | – |
| `REQ 1 0`, 08:35:47 | DATA 119 B, HACK; RECEIVED: DATA 98 B od roota, HACK 27 B od A |
| `REQ 1 96`, 08:36:05 | DATA 215 B, HACK; RECEIVED 98 B, HACK od A |
| `RX 255` / `TXPKT 1 255`, `RXPER` | w trybie przygotowania na obu XIAO (potwierdzenie przyciskiem BOOT), obraz od 10:25: |
| A → root, 10:34:01 | A: `sent` 1, `tx_ms` 417 (oczekiwane 416); root: `RXPER` `rx_ok` 1, `rx_bad` 0, `len` 255, RSSI −17 dBm, SNR 12,5 dB; podsłuch: 255 B, CRC poprawne |
| root → A, 10:34:18 | root: `sent` 1, `tx_ms` 417; A: `RXPER` `rx_ok` 1, `rx_bad` 0, `len` 255, RSSI −17 dBm, SNR 13,3 dB; podsłuch: 255 B, CRC poprawne |
| `PREP 0` na obu | `prep` false, `APP` `link` true |

Wszystkie ramki v3 z `mac_ok` w podsłuchu, 0 ramek z błędem CRC. Wynik: kryterium spełnione. Ramka DATA ma 215 B (S + 96 + 52 przy `sa1_bytes` 67), bo `REQ` ma najwyżej 96 B tekstu; procedura przewiduje ten przypadek.

## Próba 11: cisza radiowa, pełne 30 min (`72d4089`)

| Krok | Wynik |
|---|---|
| `SILENCE 1` na roocie, 08:45:45 | `{"silence":true}` |
| `REQ 5` na A, 08:45:47 | 5 zgłoszeń |
| 30 min ciszy | w podsłuchu żadnej ramki od roota; A nadała 150 DATA (25 numerów seq: ponowienia i ponowienia SA1), ostatnią o 09:12:15; root przekazywał je stanowisku bez HACK |
| `SILENCE 0`, 09:15:49 | BEACON roota od razu, 5/5 RECEIVED od 09:15:53 do 09:16:05, każdy z HACK od A |

Wynik: kryterium spełnione. Podsłuch działał przez cały czas ciszy (bez wiersza `gap`).

## Próby 4 i 5: czas HACK i W10

Czas HACK z podsłuchu jak 2026-11-02 (koniec DATA do końca HACK, zegar podsłuchu).

| | `72d4089` | punkty 1 i 2 | punkty 1–3 | `d5d364b` (12:50) |
|---|---|---|---|---|
| Próba 4 (`REQ 20`) | 20/20 w 68 s, 2 ponowienia DATA (odmowy HACK przez CAD), root: 1 `tx_drop` | 20/20 w 82 s, 0 ponowień | – | – |
| Próba 5 (`REQ 10` co minutę, 5 razy) | 50/50 w 330 s, 2 DATA bez HACK | 50/50 w 330 s, 0 ponowień | 50/50 w 331 s, 0 ponowień | 50/50 w 330 s, 0 ponowień, każda DATA z HACK |
| Najdłuższy HACK roota (podsłuch) | 111,9 ms | 121,5 ms | 140,9 ms | 112,4 ms |
| HACK powyżej 200 ms, `hack_late` | 0, 0 | 0, 0 | 0, 0 | 0, 0 |
| Odroczenia nadania, root | +139 w próbie 5 | 0 w próbie 5 | 2 | 2 (stacja 1) |
| `rssi_ignored` / `cad_unconfirmed` | – | – / stacja 3 | root 1 / stacja 3 | 0 / stacja 2 |

Najdłuższy HACK po punkcie 3 (140,9 ms) mieści się w kryterium 200 ms. Na obrazie z `d5d364b` (stacja 21, nowa konfiguracja) root odpowiadał po 107 ms średnio (`end_ms_mean`), najdłużej 112 ms według roota i 112,4 ms w podsłuchu; HACK stacji za RECEIVED najdłużej 105,3 ms. Podsłuch nie widział żadnej ramki z błędem CRC. Średnio root odpowiadał po 109 ms (`end_ms_mean`), jak przed poprawką. Przyczyny odroczeń i ponowień na `72d4089` opisuje [cca-cad-2026-11-03.md](cca-cad-2026-11-03.md).

## Próba 3: zgłoszenie z przycisków i decyzja w panelu (obraz od 10:25)

Przyciski stacji: polecenie `KEY` na porcie diagnostyki (XIAO ma tylko BOOT jako OK). Panel: API panelu z kontem `dyzurny-1`, jak przeglądarka dyżurnego.

| Krok | Wynik |
|---|---|
| MENU → ZGŁOSZENIE → WODA PITNA, 1 osoba, PILNE – KILKA GODZIN, bez frazy, OK = WYŚLIJ (10:27) | ekran wyniku z numerem 2334; DATA od 20, HACK od roota; koperta przyjęta na stanowisku w 12,5 ms |
| RECEIVED | DATA 98 B od roota, HACK od A |
| panel: PRZECZYTANE (stan 2), po 20 s decyzja PRZEKAZANE DALEJ (stan 4, adresat i czas) | dwie DATA od roota, każda z HACK od A |
| stacja: WIADOMOŚCI → 2334 | „PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)”, WODA PITNA, 1, PILNE – KILKA GODZIN |
| `APP` na A | `sent` 1, `delivered` 1, `received` 3, `failed` 0, `intents` 0 |
| baza stanowiska | jedno zgłoszenie 2334, stan 4, jedna decyzja |

Wynik: kryterium spełnione.

Błąd znaleziony w tej próbie: menu wracało samo do ekranu głównego zaraz po `KEY OK`. `loop()` odczytuje `now` na początku obiegu, a `KEY` w `pollSerial()` zapisuje czas naciśnięcia z późniejszego `millis()`. `tick(now)` liczył wtedy `now - lastPressMs_` bez znaku: wynik około 49 dni, więc bezczynność od razu odesłała ekran do MAIN. Fizyczne przyciski dostają `now` obiegu, dlatego błąd dotyczył tylko poleceń z USB. Poprawka: `elapsed()` w `ui.cpp` daje 0, gdy chwila odniesienia jest późniejsza (bezczynność, przytrzymanie, powtarzanie); test hosta `test_press_after_loop_time_does_not_trigger_idle`.

## Dowód doręczenia (E1, obraz z `41f43ba`, 15:55–15:59)

Obraz z dowodem doręczenia stacji ([wici-link.md](../../../docs/spec/wici-link.md#dowód-doręczenia)) wgrany na obie płytki; konfiguracja w PSRAM przetrwała wgranie (stacja 21). Stanowisko z tego samego commitu. Zestaw ma tylko dwa węzły WICI-Link, więc drogi przez przekaźnik (wynik „przekazane”, 35 min, K2 u przekaźnika) ta próba nie sprawdza; sprawdzają je testy natywne i stanowiska.

| Krok | Wynik |
|---|---|
| T1: zgłoszenie z A (`REQ 1 0`), potem odpowiedź z panelu | REQUEST 119 B od 21; dwie DATA 98 B (RECEIVED i otwarta wcześniej intencja do 21, wysłana od razu po świeżej kopercie od stacji) i REPLY 127 B od roota, każda z HACK od 21; żadnej koperty dowodu w eterze; intencje zamknięte (czekające 2 → 1) |
| T2: `SILENCE 1` na A, odpowiedź z panelu | trzy DATA 122 B od roota bez HACK (15:57:05, :17, :30); root zapomina drogę; ponowienie stanowiska po 1 min jako rozsyłanie (114 B, 15:58:25) |
| T2: `SILENCE 0` na A | DATA 60 B od 21 (15:58:58): koperta rodzaju 1 (`kind` 0x41), 21 → 2, dwa liczniki (kopia jednoadresowa i rozsyłanie); HACK roota po 234 ms od początku DATA; stanowisko: `koperta WICI proof`, przyjęcie 7,5 ms; REPLY zamknięta (czekające 2 → 1); `proofs_dropped` 0 |

Wynik: kryterium spełnione dla jednego przeskoku i rozsyłania. Pozostała otwarta intencja jest sprzed tej próby. Zgłoszenie czeka za dowodem najwyżej jedno przekazanie, tu 234 ms do HACK.

Poprawka znaleziona przed próbą: stacja pomijała dowód, gdy rozstrzygającą ramkę podał root z ACKREQ, także gdy radio odrzuciło jej HACK (cisza, termin). Root go wtedy nie dostał, a wiadomość zamykało dopiero ponowienie stanowiska. Teraz dowód pomija tylko HACK przyjęty przez radio; w T2 dowód objął też tę pierwszą kopię.

## Obraz z grupą B (`65b53fb`, 21:09–21:20)

Obraz z całą grupą B przeglądu końcowego (między innymi HACK z echem 2 B MAC potwierdzanej DATA, 29 B, wstrzymanie kanału do ostatniej chwili startu HACK, ponowne HACK poza limitem) wgrany na obie płytki; konfiguracja w PSRAM przetrwała wgranie (root WICI-E64309, stacja 21 WICI-D17A28). Stanowisko z `68a5335` na tym samym nośniku testowym, podsłuch jak wyżej. Echo sprawdza skrypt laptopa: bajty 11–12 HACK równe bajtom MAC sieci ramki DATA o tym samym `seq` (8 B MAC przed 8 B tagu pary).

| Próba | Wynik |
|---|---|
| 2: `REQ 1 0` na A (21:10) | DATA 119 B od 21, HACK 29 B od roota, RECEIVED jako DATA 98 B, HACK 29 B od 21; CRC i MAC sieci poprawne; echo w obu HACK zgodne; stanowisko: przyjęcie 12,5 ms |
| 5: `REQ 10` co minutę, 5 razy (21:11–21:17) | 50/50 w 330 s, 0 ponowień (50 DATA od 21, 50 różnych `seq`); 100 HACK, każdy z echem swojej DATA; najdłuższy HACK roota w podsłuchu 115,4 ms (`end_ms_max` 115), stacji 101,6 ms; `hack_late` 0 i `hack_refused` 0 na obu; przyjęcie na stanowisku mediana 6,0 ms, najwięcej 14,7 ms |
| Wstrzymanie wysyłki (21:17) | stanowisko miało od rana otwartą intencję do porannej stacji 20 (WICI-B97DB3, tożsamość utracona przy odłączeniu zasilania), ponawianą przez WICI-Link od 8,5 h; po usunięciu jej z zaufanych w panelu: czekające 1 → 0, wstrzymane 0 → 1, także przy przekazaniu zmiany |
| Dowód doręczenia: `SILENCE 1` na A, odpowiedź z panelu (21:17) | trzy DATA 142 B od roota z ACKREQ bez HACK (stacja: `refused_by.state` 3), ponowienie jako rozsyłanie (134 B) |
| `SILENCE 0` na A | jedna DATA 60 B od 21 (dowód doręczenia), HACK roota 29 B z echem; stanowisko: `koperta WICI proof`, przyjęcie 23,2 ms; REPLY zamknięta (czekające 1 → 0); na ekranie A 3 nowe wiadomości (było 2) |

Start HACK po końcu DATA (metoda jak niżej, HACK 29 B w tych samych symbolach, 83,2 ms w eterze): 103 HACK, mediana 19,0 ms, p95 27,8 ms, p99 32,2 ms, najwięcej 39,5 ms, żaden ponad 50 ms. Wynik: wszystkie cztery próby zaliczone na jednym przeskoku. Przekaźnika zestaw nie ma (dwa XIAO), więc trasy wieloskokowe sprawdzają nadal tylko testy natywne i symulator.

## Obraz po poprawkach przeglądu niezależnego (`3cefe2a`, 22:57–23:04)

Obraz z poprawkami 1–11 przeglądu niezależnego (między innymi klucz odbiorcy tylko aktywnej tożsamości, wstrzymanie do sąsiada kończone tylko HACK albo BEACON, ponowienie roota tymi samymi bajtami, spóźniony HACK przed ponowieniem) wgrany na obie płytki; konfiguracja w PSRAM przetrwała wgranie. Stanowisko z tego samego commitu na tym samym nośniku testowym, podsłuch jak wyżej. Oprogramowanie płytek podaje tylko `xiao-0.1`, więc obraz potwierdzają logi budowania i wgrania z drzewa roboczego na `3cefe2a`.

| Próba | Wynik |
|---|---|
| 2: `REQ 1 0` na A (22:58) | DATA 119 B od 21, HACK 29 B od roota, RECEIVED jako DATA 98 B, HACK 29 B od 21; CRC i MAC sieci poprawne; echo w obu HACK zgodne; stanowisko: przyjęcie 13,0 ms |
| 5: `REQ 10` co minutę, 5 razy (22:59–23:04) | 50/50 w 330 s, 0 ponowień (50 DATA od 21 i 50 od roota, po 50 różnych `seq`); 100 HACK, każdy z echem swojej DATA; najdłuższy HACK roota w podsłuchu 122,2 ms (`end_ms_max` 121), stacji 105,8 ms; `hack_late` 0 i `hack_refused` 0 na obu; przyjęcie na stanowisku mediana 6,2 ms, najwięcej 23,1 ms |

Start HACK po końcu DATA (metoda jak niżej): 102 HACK, mediana 21,0 ms, p95 27,6 ms, p99 37,2 ms, najwięcej 39,0 ms, żaden ponad 50 ms. Wynik: obie próby zaliczone na jednym przeskoku, bez regresji względem `65b53fb`. Bez zgubionego HACK nie było ponowień, więc ponowienia roota tymi samymi bajtami i spóźnionego HACK ta sesja nie pokazuje; sprawdzają je testy natywne i laptopa. Przekaźnika zestaw nie ma (dwa XIAO).

## Start HACK po DATA (R2)

Ile po końcu ramki DATA zaczyna się HACK, z podsłuchów RAK4631 z 2026-11-02 i 2026-11-03 (wszystkie z zestawami XIAO). Para DATA–HACK to ten sam `seq`, z `l_src` i `l_dst` zamienionymi. Start HACK to różnica znaczników końca odbioru minus czas HACK w eterze (27 B, SF7/125 kHz, 24 symbole preambuły: 83,2 ms). Ten sam zegar podsłuchu mierzy obie ramki, więc opóźnienie odbioru się znosi.

| Podsłuch | HACK | mediana [ms] | p95 [ms] | p99 [ms] | najwięcej [ms] | ponad 50 ms |
|---|---|---|---|---|---|---|
| `podsluch-2026-11-02c.jsonl` | 44 | 17,3 | 34,2 | 40,6 | 40,6 | 0 |
| `podsluch-2026-11-02d.jsonl` | 50 | 15,9 | 26,5 | 26,8 | 26,8 | 0 |
| `podsluch-2026-11-02e.jsonl` | 115 | 16,9 | 27,5 | 32,6 | 35,5 | 0 |
| `podsluch-2026-11-03.jsonl` | 151 | 18,2 | 26,8 | 28,4 | 28,7 | 0 |
| `podsluch-2026-11-03b.jsonl` | 245 | 19,3 | 29,1 | 38,3 | 57,7 | 1 |
| `podsluch-2026-11-03d.jsonl` | 103 | 21,0 | 27,5 | 29,2 | 32,8 | 0 |
| `podsluch-2026-11-03e.jsonl` | 5 | 17,1 | 38,3 | 38,3 | 38,3 | 0 |
| razem | 713 | 17,5 | 27,6 | 35,9 | 57,7 | 1 |

Okno wolnego kanału (50 ms) nie obejmuje więc każdego HACK, a termin pozwala zacząć HACK do 103 ms po DATA. Stąd wstrzymanie własnych ramek do 113 ms po usłyszanej DATA z ACKREQ ([WICI-Link](../../../docs/spec/wici-link.md#potwierdzenie-na-każdym-skoku), reguła 2). Podsłuchy z 2026-11-02 leżą obok [zestawu z 2026-11-02](xiao-zestaw-2026-11-02.md).

## Surowe logi

- `podsluch-2026-11-03.jsonl`: 08:25–09:23 (próby 2, 4, 5, 11 na `72d4089`, potem pomiary z RAK jako nadajnikiem);
- `podsluch-2026-11-03b.jsonl`: od 09:45 (próby po poprawce, próba 3);
- `diag-root-2026-11-03*.log`, `diag-a-2026-11-03*.log`: porty diagnostyki z czasem laptopa (sekundy Unix): bez sufiksu do 09:23, `b` 09:45–10:09, `c` od 10:09;
- `stanowisko-2026-11-03.log`: przyjęcia kopert na stanowisku (kolejka i przyjęcie w ms);
- `podsluch-2026-11-03d.jsonl`, `diag-root-2026-11-03d.log`, `diag-a-2026-11-03d.log`, `stanowisko-2026-11-03d.log`: obraz z `d5d364b` od 12:40 (próba 5 12:50–12:56).
- `podsluch-2026-11-03e.jsonl`, `diag-root-2026-11-03e.log`, `diag-a-2026-11-03e.log`, `stanowisko-2026-11-03e.log`: obraz z `41f43ba` (dowód doręczenia, 15:55–15:59).
- `podsluch-2026-11-03f.jsonl`, `diag-root-2026-11-03f.log`, `diag-a-2026-11-03f.log`, `stanowisko-2026-11-03f.log`: obraz z `65b53fb` (grupa B, 21:09–21:20).
- `podsluch-2026-11-03g.jsonl`, `diag-root-2026-11-03g.log`, `diag-a-2026-11-03g.log`, `stanowisko-2026-11-03g.log`: obraz z `3cefe2a` (po przeglądzie niezależnym, 22:57–23:04).

Licencja tego pliku: CC-BY-4.0 ([LICENSE.md](../../../LICENSE.md)).

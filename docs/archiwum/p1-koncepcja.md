# P1 i warianty sprzętu w koncepcji (archiwum)

P1 był własnym profilem radiowym FSK WICI (2-GFSK 4800 bit/s, fragmenty do 86 B) na dwóch niezależnych wykonaniach radia, TI CC1120 i ST S2-LP, z płytką stacji R02 projektowaną przed pilotażem i stanowiskami deweloperskimi A/B do prób programu. Przegląd praktyczny wstrzymał go 2026-10-08 (F99), bo LoRa SF7 na gotowych modułach SX1262 ma w modelu lepszą czułość i krótszy czas obsługi zgłoszenia bez własnego toru RF; od 2026-10-29 treść jest tu, a nie w rozdziałach koncepcji (F119).

Liczby pochodzą z modelu ([`obliczenia.py`](../../software/reference/obliczenia.py), [`wyniki.json`](../../software/reference/wyniki.json)): pozycje `radio`, `relay_w10`, `network_capacity`, `lxmf_retry`, `cold_start_announces` i `station_level1` liczą P1 i odbiornik CC1120. Profil P1 opisuje [specyfikacja radia](../spec/radio.md) do czasu jej porządku. Bieżący plan: [koncepcja, rozdział 08](../concept/08-plan-weryfikacji-i-decyzje.html).

## Porównanie z LoRa SF7 (dawniej rozdział 04)

| Wielkość | LoRa SF7 | P1 |
|---|---|---|
| czułość na złączu (model, 3 dB strat toru) | −121 dBm (katalog SX1262 −124 dBm) | cel −110 dBm, wymaga układu −113 dBm |
| zapas łącza na 1 km, model Haty, anteny 10 m i 3 m | +7,5 dB | −3,5 dB |
| przepływność w eterze | około 5,5 kbit/s, ramka do 254 B | 4,8 kbit/s, 29 B narzutu na każde 86 B |
| 50 zgłoszeń przez przekaźnik (W10, 30 min) | 16,4–17,2 min | 22,6–24,0 min |
| ogłoszenie trasy | 0,36 s | 0,51 s |

Wcześniejsze odczytanie W14 (dwie rodziny układów radiowych już w pierwszym wykonaniu) wykluczało LoRa i pociągało za sobą dwa projekty torów RF, sterowniki P1 dla obu układów i mieszaną kwalifikację układów TI i ST. To była największa część pracy sprzętowej, wykonywana przed jakimkolwiek dowodem, że sieć i stanowisko odbiorcze działają. Dlatego W14 rozdzielono: w pilotażu wystarczą części z dwóch źródeł zakupu, a drugie niezależne wykonanie jest wymaganiem wyrobu.

Opcja systemu „samodzielna stacja MCU + Reticulum/LXMF + własny FSK P1” miała jawny profil i dwóch kandydatów RF od niezależnych producentów, a sterowniki P1 i stanowiska deweloperskie już istniały. Kosztem były dwa projekty torów RF, dwie rodziny MCU, mieszana kwalifikacja TI–ST, badania RED każdego wykonania i ujemny zapas łącza w modelu przy niskich antenach. Wariant 0.4 (laptop jako węzeł z modemem P1) wymagał adaptera czasu dla protokołu KISS, bo kontrola przepływu KISS ma limit 5 s, a P1 może wymagać ponad 16 s samej ciszy.

**Mikrokontroler w wariancie P1.** Z odbiornikiem CC1120 (22 mA) ESP32-S3 spełniał W23 tylko przy średnim poborze MCU około 30 mA, czyli przy lekkim uśpieniu z odbiornikiem stale włączonym; przy 45–60 mA dawał 33–39 h. Wycofany kontroler R01.3 miał STM32F103, który nie mieści stosu Reticulum. Port microReticulum zostawiał na nRF52840 w odtworzeniu ruchu 3,5% wolnej RAM w szczycie i 12,5% w stanie ustalonym, bez LXMF ([pomiar](../../firmware/README.md#pamięć-ram)); rdzeń stacji zastąpił port w obrazach.

## Budżet czasu antenowego P1 (dawniej rozdział 06)

Dla datagramu o długości B bajtów liczba fragmentów wynosi `n = ceil(B/86)`, liczba bajtów w eterze `B + 29n`, a czas nadawania `t = 8(B + 29n)/4800`. Dług ciszy wynosi `12t`, cykl `13t`. Model ma parametr narastania mocy na fragment (`ramp_ms`); przy 2 ms cykl datagramu 600 B rośnie z 17,40 do 17,58 s.

| Datagram B | Fragmenty | Bajty w eterze | TX [s] | TX + cisza [s] | Pełne cykle w 30 min |
|---:|---:|---:|---:|---:|---:|
| 100 | 2 | 158 | 0,263 | 3,423 | 525 |
| 250 | 3 | 337 | 0,562 | 7,302 | 246 |
| 500 | 6 | 674 | 1,123 | 14,603 | 123 |
| 600 | 7 | 803 | 1,338 | 17,398 | 103 |

Dla 600 B przepustowość wynosi około 34,5 B/s danych wejściowych interfejsu. Narzut ramki (29 B na fragment 86 B) to około 25% czasu TX; dłuższa ramka wymagałaby uzupełniania bufora nadawczego podczas nadawania w obu układach. Sterownik P1 miał cztery miejsca na datagramy i osiem kontekstów składania. Największy dług ciszy po restarcie bez poprawnego rekordu wynosił około 16 s (12 × 1,338 s).

## Próba W10 w P1

| Pakiet nadawany przez przekaźnik | Datagram [B] | Fragmenty | TX + cisza [s] |
|---|---:|---:|---:|
| REQUEST typowy, treść 174 B | 403 | 5 | 11,873 |
| REQUEST z maksymalnymi polami, 222 B | 451 | 6 | 13,542 |
| RECEIVED, 50 B | 275 | 4 | 8,472 |
| potwierdzenie pakietu | 99 | 2 | 3,402 |

Obsługa jednego zgłoszenia zajmowała przekaźnikowi 27,1–28,8 s, a 50 zgłoszeń 1357–1441 s, czyli 22,6–24,0 min z 30 min przy zerowych stratach. Kod IFAC wydłużał ten czas o około 10%, bo potwierdzenie pakietu przestawało mieścić się w jednym fragmencie. Z „ODBIORCA PRZECZYTAŁ” i decyzją: 52,6 s na zgłoszenie, około 44 min na 50 zgłoszeń; próba ruchu mieszanego z 55 rewizjami około 48 min z 60 min (około 20% zapasu). Każde ponowione zgłoszenie zabierało 11,9–13,5 s. Potwierdzenie przez jeden przekaźnik wracało na pustej sieci po ≥13 s.

Odstęp ponowień LXMF dla największego własnego datagramu (499 B, cykl 14,6 s): 60 s dla 1 i 2 skoków na pustej sieci, około 115 s (1 skok) i 144 s (2 skoki) przy największym długu ciszy i pełnej kolejce 4 × 600 B.

**Pojemność sieci.** Stacja stanowiska: potwierdzenie, RECEIVED i dwa STATUS (29,9 s z ciszą), około 121 zgłoszeń/h. Przekaźnik przed stanowiskiem: 52,6 s, około 68 zgłoszeń/h. BULLETIN do 50 stacji około 11,9 min (14,2 s na stację). Zimny start 50 stacji: ogłoszenia około 21 min czasu kanału i 5,6 min nadawania w każdej stacji, zapytania o trasę 0,6–8,6 min, wymiana TEST około 3,3 min; razem 25–33 min, czyli 61–80% okna 42 min (dla 30 stacji 40–52%, dla 10 stacji 20–24%).

## Zasięg P1

Względem celu −110 dBm na złączu wolna przestrzeń dawała na 1 km 34,07 dB zapasu (13 dBm, dwa dipole, po 1 dB przewodu). Model Haty dla małego miasta: −0,7 dB (antena 30 m i 1,5 m), −3,5 dB (10 m i 3 m), −7,3 dB (10 m i 1,5 m); przy instalacji stałej (2,5 dB strat na końcu) 31,1 dB w wolnej przestrzeni oraz −3,7, −6,5 i −10,3 dB, a z antenami kolinearnymi +3,0, +0,2 i −3,6 dB. Gdyby układ osiągał tylko −110 dBm na własnym wejściu, zapasy spadały o kolejne 3 dB. CC1120 i S2-LP nadają do około +16 dBm na złączu; większa moc wymagała zewnętrznego wzmacniacza, czyli nowej konstrukcji RF ([CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), [S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf)). Przy niespełnionym W23 rozważano wersję P1 z dłuższą preambułą i nasłuchem z próbkowaniem.

## Energia z odbiornikiem CC1120

Założenia jak w rozdziale 06 koncepcji, z odbiornikiem zawsze włączonym 22 mA (CC1120; S2-LP pobiera mniej).

| Wariant MCU | Prąd 3V3 | Moc z ogniw | Energia 24 h z rezerwą, ogniwa / 12 V | 4 ogniwa AA, 14,4 Wh | Akumulator 12 V, 360 Wh |
|---|---:|---:|---:|---:|---:|
| nRF52840, 3 mA | 32 mA | 0,132 W | 3,8 / 4,0 Wh | 91 h | 91 dni |
| ESP32-S3, 30 mA | 59 mA | 0,243 W | 7,0 / 7,2 Wh | 49 h | 50 dni |
| ESP32-S3, 45 mA | 74 mA | 0,305 W | 8,8 / 8,9 Wh | 39 h | 40 dni |
| ESP32-S3, 60 mA | 89 mA | 0,367 W | 10,6 / 10,7 Wh | 33 h | 34 dni |

Przekaźnik stały z akumulatorem bufora: 7 Ah na około 255 h (nRF52840) albo 94 h (ESP32-S3, 60 mA), 17 Ah na około 620 h albo 228 h. Laptop jako przekaźnik (wariant 0.4, 788–2312 Wh na dobę) zużywał od około 75 do 610 razy więcej energii niż stacja w tym modelu.

## Zasilanie poziomu 3

Własny blok zasilania poziomu 3 (przetwornica 230 V, wejścia A/B dla laptopa i routera, osobna pula C dla ładowarki telefonów) wypadł z zakresu projektu po zamknięciu D05 (2026-10-08); poziom 3 używa kupionej stacji zasilania. Model bloku: 35 W AC dla laptopa i routera, sprawność 0,85, 8 W poboru własnego przetwornicy i 1,7 W strat diod, czyli 50,88 W; 1465 Wh na dobę z rezerwą. Ładowarka miała osiem portów i najwyżej 60 W na wyjściu (375 Wh na dobę z rezerwą). Razem 1840 Wh, czyli 6–7 akumulatorów 12 V 60 Ah przy wykorzystaniu 50% (360 Wh każdy). Przy sztywnym przydzieleniu akumulatorów do obu pul zaokrąglenia dawały 7 sztuk zamiast 6. W nieogrzewanym schronieniu pojemność akumulatora kwasowo-ołowiowego spada w 0 °C o około 20%. Gniazdo zapalniczki ograniczało prąd; nominalne 150 W wymagało odpowiednich zacisków i przewodów, a każde źródło A lub B musiało samodzielnie utrzymać dozwolone obciążenie.

## Ocena wykonania wariantów (stan sprzed porządku 2026-10-29)

- **Stanowiska deweloperskie A i B** (nRF52840-DK z CC1120EM; ESP32-S3-DevKitC-1 z X-NUCLEO-S2868A2 na płytce nośnej N1): lista części, podział prób między stanowisko a R02, płytka nośna N1 (ERC 0, DRC 0, pliki produkcyjne) i obrazy oprogramowania (zbudowane, bez prób na sprzęcie). Pomiary T4 toru RF producenta dotyczyły tylko P1. Kontroler R01.3 wycofano (CAD i raporty w historii Git, lekcje w [`hardware/r02/lekcje.md`](../../hardware/r02/lekcje.md)).
- **Tory RF TI i ST:** wspólny kontrakt i kandydaci układów; brakowało dwóch projektów płytek RF, potwierdzenia tablic rejestrów i sterowników P1 obu układów na sprzęcie, emisji, czułości na złączu z pełnym torem wejściowym i próby mieszanej na stanowiskach A i B, potem na płytkach R02.
- **Stacja R02:** wymagania w specyfikacji 0.5 i założenia płytki w [`hardware/r02`](../../hardware/r02/README.md); projekt wstrzymany do decyzji po pilotażu. Filtr SAW 868 MHz (osobny tor RX za przełącznikiem albo wspólny tor) miał być wybrany przy R02. W wykonaniu A (nRF52840) stacja pobierała z VBUS tylko prąd warstwy fizycznej USB, około 2,5 mA; zegar Y1 kontrolera R01.3 mógł we wstrzymaniu USB przekroczyć ten budżet (do 7 mA, F77, F78).

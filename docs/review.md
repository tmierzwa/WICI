# WICI — stan przeglądu technicznego

Ocena: 2026-10-06. Zakres: koncepcja, pięć rozdziałów specyfikacji, model kontraktów, BOM, kontroler R01.3, raporty CAD, eksporty, procedury odbioru, licencje i narzędzia publikacji.

**Projekt nadaje się do dalszego prototypowania. Nie nadaje się jeszcze do zamówienia kompletnego sprzętu ani pracy w schronieniu. Kontroler R01.3 pozostaje HOLD i wymaga zmiany elektrycznej.**

Podział na lokalną stronę, osobny transport, trwałą kolejkę aplikacji i osobne zasilanie telefonów jest logiczny. Ogranicza skutki awarii strony i ładowarki. Nie usuwa wspólnych punktów awarii: laptopa, pojedynczej trasy i dyżurnego odbiorcy.

## Ustalenia i ich stan

| ID | Problem | Stan / warunek zamknięcia |
|---|---|---|
| F01 | Stale włączony Y1 nie pozwala zagwarantować budżetu suspend USB | otwarte; nowa rewizja kontrolera i pomiary pełnego modemu |
| F02 | 900 s adaptera nie zapewnia zgodności timeoutów Reticulum/LXMF | otwarte; próba T3 z rzeczywistym stosem i kolejkami |
| F03 | Dobór MIC2007 nie zamyka tolerancji; TPS2553 wymaga uwzględnienia rezystora | niekwalifikowany MIC2007 usunięty z listy wariantów; drugi wykonawczy wariant nadal otwarty |
| F04 | BOM stacji wskazywał inny MCU niż CAD; rodzina S2-LP nie identyfikowała pasma | poprawione: STM32F103CBT6 i S2-LPQTR; brak dowodu gotowego firmware i radia |
| F05 | Walidacja przyjmowała C1 i niewidoczne znaki formatujące | poprawione w modelu i SA1; przypadki wejścia oraz niezależnie zakodowanego JSON |
| F06 | Specyfikacja nie rozdzielała jednoznacznie RECEIVED i STATUS | poprawiona; STATUS ma event ≥2 i state 2/3, zgodnie z modelem |
| F07 | Nieokreślony zakres próby obciążenia i brak wymogu utrzymania hosta w pracy | doprecyzowane; próby terenowe i pakiet START nadal niewykonane |
| F08 | Dodatkowe warunki licencji zależności wymagają oceny przyszłego pakietu GPL | otwarte przed dystrybucją START; repozytorium nie zawiera kodu zależności |

## F01 — kontroler USB

W [połączeniach kontrolera](../hardware/radio-test-r01/connections.csv) Y1.1 jest połączone z V3. To wejście standby oscylatora ASE-8.000MHZ-L-C-T. Stały stan wysoki utrzymuje oscylacje. Karta ASE dla 8 MHz podaje typowo 2,5 mA i maksymalnie 7 mA; cały modem USB 2.0 ma w suspend budżet 2,5 mA. Nawet zatrzymanie MCU i radia nie zamyka gwarantowanego bilansu. Odłączenie D+ przez Q1 nie odłącza Y1. [ASE, wydanie 2022-02-18, s. 1–2](https://abracon.com/Oscillators/ASEseries.pdf), [USB 2.0](https://www.usb.org/document-library/usb-20-specification), [ECN suspend — kopia dokumentu USB-IF](https://git.nefarius.at/nefarius/USB-Bluetooth-Specs/media/branch/master/usb_20_0702115/Suspend%20Current%20ECN.pdf).

Potrzebny jest sterowany tor zegara/zasilania i firmware uwzględniający suspend/resume. Zmiana wymaga nowej rewizji CAD, ERC/DRC, eksportów i kontroli paczki. Nie wykonano jej w R01.3; jego Gerbery nie są poprawioną wersją.

Odbiór obejmuje prąd przed konfiguracją, deklarowany budżet po konfiguracji, suspend, resume i udar przy podłączeniu. C1=1 µF nie opisuje całej pojemności pobierającej energię z USB: są kondensatory za LDO oraz przyszły moduł RF. Nie stwierdzono przekroczenia udaru pomiarem; trzeba go zmierzyć w kompletnym urządzeniu. [Warunki przed produkcją](../hardware/radio-test-r01/przed-produkcja.md), [odbiór](spec/odbior.md).

## F02 — czasy stosu i cisza nadajnika

Analiza dotyczy Reticulum `e40191b3d193b46b7f2d8a44424a594cd758839b`. Ten commit jest punktem analizy, nie zatwierdzoną zależnością wydania. MTU wynosi 500 B, podstawowy timeout odcinka 6 s. Dla znanej trasy długości dwóch odcinków i interfejsu raportującego 240 bit/s inicjator linku dostaje:

```text
timeout = 500 × 8 / 240 + 6 + 2 × 6 = 34,67 s
```

Zegar linku i watchdog ruszają przed `packet.send()`. Oczekiwanie w adapterze zużywa więc czas zestawiania, nawet przed pierwszym TX. Zasób ma odrębny mechanizm timeoutów oparty m.in. na RTT. Sam timeout READY=900 s nie zmienia tych mechanizmów. [Reticulum: stałe](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Reticulum.py), [Transport.first_hop_timeout](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Transport.py), [Link](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Link.py), [Resource](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Resource.py).

Kontrprzykład analityczny: pakiet linku czeka w adapterze za trzema datagramami po 500 B. Każdy zajmuje sześć fragmentów P1 i 674 B w eterze:

```text
TX = (500 + 6 × 29) × 8 / 4800 = 1,1233 s
TX + cisza = 13 × TX = 14,6033 s
trzy cykle = 43,81 s > 34,67 s
```

To dolne oszacowanie czasu bez kolizji, zajętego kanału i rampowania. Kolejka z takim ruchem może wygasić link przed nadaniem jego żądania. Kontrprzykład nie jest pomiarem istniejącego adaptera: adapter i firmware nie zostały wykonane. Pokazuje, że sama deklaracja bitrate i timeoutu READY nie wystarcza do zapewnienia zgodności. Jedna zgoda READY ogranicza modem; nie usuwa oczekiwania po stronie hosta za ruchem przekazywanym.

Przed projektowaniem kolejnych PCB wykonać T3: przypięty Reticulum/LXMF, emulator TX/ciszy/CCA, ograniczone kolejki, zimna i ustalona trasa, link, zasób, potwierdzenia, restarty i ruch przekaźnika. Rejestrować wiek pakietu oraz wszystkie ponowienia. Rozstrzygnąć planowanie i timeouty całego stosu; nie uznawać zwiększenia samego READY za rozwiązanie. [Kontrakt radia](spec/radio.md), [plan prób](conception/08-plan-weryfikacji-i-decyzje.md).

## F03 — ładowarka i tolerancje

MIC2007: przy pozycji IOUT=2 A karta podaje CLF=210–286 V. Z I=CLF/R i wymagań progu 1,6–2,1 A wynikają:

```text
R ≤ 210 / 1,6 = 131,25 Ω
R ≥ 286 / 2,1 = 136,19 Ω
```

Przedział jest pusty jeszcze bez tolerancji rezystora. Dobór na wartość typową nie kwalifikuje wariantu. Potrzebny jest inny niezależny element albo odrębna kwalifikacja całego rozwiązania; nie ma teraz zatwierdzonego drugiego wariantu. [Microchip DS20006486B, s. 6 i 20](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/MIC20XX-Fixed-and-Adjustable-Current-Limiting-Power-Distribution-Switches-DS20006486B.pdf).

TPS2553: tabela doboru dla 15 kΩ /1% podaje minimum 1594,5 mA, poniżej wymaganych 1600 mA. Wskazano rezystor 0,1% jako punkt wyjścia. Nadal trzeba zamknąć tolerancje, temperaturę złącza i pomiary portu. Próg ograniczania dotyczy stanu przed foldback i wyłączeniem termicznym; nie jest obietnicą stałego prądu zwarcia. Koordynacja F1/F2 i crowbar pozostają do odbioru. [TI SLVS841F, s. 7, 15 i 20](https://www.ti.com/lit/ds/symlink/tps2553.pdf), [specyfikacja elektroniki](spec/elektronika.md).

## F04–F07 — poprawione kontrakty i dane

- **Części:** BOM stacji jest zgodny z MCU kontrolera: STM32F103CBT6. C8 wymaga odrębnego obrazu mieszczącego się w 64 KiB. Wariant ST radia to S2-LPQTR; S2-LPCBQTR nie obejmuje 869,525 MHz w górnym paśmie. Żaden wariant RF nie jest jeszcze odebrany. [BOM](../bom.csv), [warianty S2-LP, rev. 13](https://www.st.com/resource/en/datasheet/s2-lp.pdf).
- **Tekst:** model odrzuca kategorie Unicode Cc i Cf, również przy odbiorze JSON z sekwencjami `\u`. Polskie litery pozostają dozwolone. Nie jest to implementacja ochrony HTML przyszłej strony.
- **Statusy:** RECEIVED rezerwuje event=1/state=1; STATUS wymaga event ≥2 i state 2/3. Starsze statusy i konflikty nadal podlegają regułom modelu.
- **Próba obciążenia:** 50 zgłoszeń łącznie z A w pierwszych pięciu minutach, droga A–B–OSP i powrót przez B. RECEIVED ma wrócić na A do 30 min od pierwszego COMMIT. ≥99% z 50 oznacza 50/50. Próba nie kwalifikuje sieci tysiąca stacji.
- **Host i USB:** START ma zapobiegać automatycznemu uśpieniu hosta, także podczas restartu strony. Doprecyzowano DATA/READY i zakaz automatycznego wznowienia TX bez zgody. Są to wymagania przyszłego pakietu i firmware, nie działające już funkcje.

## F08 — licencje pakietu START

Analizowane LICENSE Reticulum i LXMF zawierają dodatkowe ograniczenia użycia oraz tworzenia zbiorów do treningu AI. Nie należy traktować ich jako niezmodyfikowanej MIT ani zakładać zgodności z własnym kodem GPL. Przed połączeniem i dystrybucją START rozstrzygnąć warunki konkretnych wersji oraz sposób ich połączenia. Samo dołączenie tekstów licencji nie zamyka zgodności. [Reticulum LICENSE](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/LICENSE), [LXMF LICENSE](https://github.com/markqvist/LXMF/blob/c3ff2d6dc2f256daab896dadc044dd5a913ecbb7/LICENSE), [mapa licencji WICI](../LICENSE.md).

Repozytorium zawiera własny model i dokumentację; nie dołącza kodu tych zależności. Publikacja obecnych źródeł i kwalifikacja przyszłej paczki START są osobnymi ocenami.

## Dowody i granice przeglądu

Model obejmuje 17 testów, w tym nową walidację Unicode i zastrzeżone numery STATUS. [Zapis weryfikacji](../software/reference/weryfikacja.json) wiąże wynik z hashami czterech źródeł. Sześć regresji publikacji sprawdza m.in. pustą, niepełną i nieaktualną paczkę oraz odrzucanie błędu bez przepisywania dowodów. Kontrola repozytorium sprawdza linki, sumy źródeł, aktualność obliczeń, powiązanie raportów CAD i zgodność archiwum z eksportami.

Przejrzano połączenia i widoki kontrolera oraz raporty i ich wyłączenia. CAD i pliki produkcyjne R01.3 nie zostały zmienione. Kontrola ich sum nie jest nowym uruchomieniem ERC/DRC, niezależnym przeglądem elektrycznym ani próbą płytki. Nie ma fizycznego dopasowania złączy, pomiaru USB/RF, działającego firmware, strony, pendrive'a ani odbioru zasilania.

Pozostałe blokady pozostają aktualne: udar A/B, ochrona telefonu, regulacja i izolacja przetwornicy, PE/RCBO dla przypadkowych zasilaczy klasy I, zgodność dwóch wykonań radia, terenowe 1 km i energia 24 h. Nie ma podstaw do deklaracji „military grade”, określonego MTBF ani kosztu odebranej serii. [Pełna lista odbioru](spec/odbior.md).

Kolejność rozstrzygnięć: T3 na emulatorze i decyzja o zależnościach; poprawka USB i kontrola mechaniki; dwa modemy oraz próby RF; kwalifikacja zasilania; kompletny pilotaż 24 h. Nie zdejmować HOLD przez zaliczenie testów modelu lub CI.

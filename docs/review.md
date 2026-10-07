# WICI: stan przeglądu technicznego

Ocena: 2026-10-06, uzupełnienie 2026-10-07 po zmianie architektury na wersję 0.5 i po przeglądzie z czterech perspektyw: językowej, elektronicznej, ochrony ludności i kontrybutora. Przegląd jest wewnętrzny: wykonał go autor projektu z pomocą AI. Nie jest niezależnym audytem ani opinią uprawnionego inżyniera. Zakres: koncepcja, pięć rozdziałów specyfikacji, zmiana architektury 0.5 (samodzielna stacja), model kontraktów, BOM, kontroler R01.3, raporty CAD, eksporty, procedury odbioru, licencje i narzędzia publikacji.

**Projekt nadaje się do dalszego prototypowania. Nie nadaje się jeszcze do zamówienia kompletnego sprzętu ani pracy w schronieniu. Kontroler R01.3 pozostaje HOLD i wymaga zmiany elektrycznej; w 0.5 jest stanowiskiem laboratoryjnym P1, a nie kontrolerem stacji.**

Podział na lokalną stronę, osobny transport, trwałą kolejkę aplikacji i osobne zasilanie telefonów jest logiczny. Ogranicza skutki awarii strony i ładowarki. W 0.5 samodzielna stacja usuwa laptopa i przetwornicę z drogi krytycznej łączności. Pozostają wspólne punkty awarii: pojedyncza trasa radiowa i jeden dyżurny u odbiorcy. Nowym głównym ryzykiem jest dojrzałość stosu sieciowego na mikrokontrolerze.

## Ustalenia i ich stan

| ID | Problem | Stan / warunek zamknięcia |
|---|---|---|
| F01 | Stale włączony Y1 nie pozwala zagwarantować budżetu prądu w stanie wstrzymania USB (suspend) | otwarte dla R01.3 jako modemu zasilanego z USB (HOLD); stanowiska T4 z zasilacza laboratoryjnego i stacji R02 nie dotyczy |
| F02 | 900 s adaptera nie zapewnia zgodności limitów czasu Reticulum/LXMF | otwarte w nowej postaci: w 0.5 stos zna dług ciszy, ale limity linku i zasobu nadal wymagają T3 na MCU |
| F03 | Dobór MIC2007 nie zamyka tolerancji; TPS2553 wymaga uwzględnienia rezystora | niekwalifikowany MIC2007 usunięty z listy wariantów; drugi wykonawczy wariant nadal otwarty |
| F04 | BOM stacji wskazywał inny MCU niż CAD; rodzina S2-LP nie identyfikowała pasma | poprawione: S2-LPQTR; w 0.5 MCU stacji to nRF52840 lub ESP32-S3 (D14), a STM32F103CBT6 zostaje na stanowisku; brak dowodu gotowego firmware i radia |
| F05 | Walidacja przyjmowała C1 i niewidoczne znaki formatujące | poprawione w modelu i SA1; przypadki wejścia oraz niezależnie zakodowanego JSON |
| F06 | Specyfikacja nie rozdzielała jednoznacznie RECEIVED i STATUS | poprawiona; STATUS ma event ≥2 i state 2/3, zgodnie z modelem |
| F07 | Nieokreślony zakres próby obciążenia i brak wymogu utrzymania hosta w pracy | doprecyzowane; próby terenowe i pakiet START nadal niewykonane |
| F08 | Dodatkowe warunki licencji zależności były niezgodne z GPL własnego kodu | rozstrzygnięte 2026-10-07: kod WICI na MIT; pakiet START dołącza licencje Reticulum/LXMF i podlega ich warunkom |
| F09 | Łączność zależała od znalezionego laptopa; przekaźnik z laptopem zużywał 788–2312 Wh na dobę | zmienione w 0.5: samodzielna stacja z przekaźnikiem 3,6–10,0 Wh na dobę w modelu; laptop i router jako rozszerzenia |
| F10 | Dojrzałość microReticulum i LXMF na mikrokontrolerze; znane restarty przy zasobach po stratnym łączu | otwarte; T3 na obu rodzinach MCU, D14; jeden pakiet na wiadomość (D01) omija zasoby |
| F11 | Ujemny zapas łącza 1 km przy antenach na wysokości okien (model: −0,7 do −7,3 dB, bez 10 dB na zaniki) | otwarte; T5 z zapisem wysokości i zysku anten; antena kolinearna, wyższe położenie lub przekaźnik; W08 może wymagać zmiany |
| F12 | Blokowanie odbiornika przez telefony LTE 800 i GSM 900 | otwarte; T4; filtr SAW 868 MHz do oceny |
| F13 | Wyładowania atmosferyczne i ESD na złączu anteny | otwarte; warunki montażu w specyfikacji radia; T6 |
| F14 | Zima: pojemność ogniw i akumulatorów, czytelność ekranu | otwarte; model z obniżeniem pojemności o 20% w 0 °C; T6 w −10 °C |
| F15 | Tlenek węgla, wodór i pożar akumulatorów | wymagania organizacyjne w specyfikacji i na karcie stacji; T8 |
| F16 | Cisza radiowa, szyfrowanie bazy, ZNISZCZ DANE i status prawny nadawania | kontrakt w specyfikacji; uzgodnienia z gminą D12/D13 otwarte |
| F17 | RECEIVED nie był ograniczony do przypiętej OSP; kwarantanna była opcjonalna | poprawione w specyfikacji i modelu: zaufanie stacji i obowiązkowa kwarantanna bez RECEIVED |
| F18 | Odłączenie 12 V przez wejście EN jednotranzystorowej idealnej diody nie działa (dioda w strukturze tranzystora); dioda TVS ogranicza napięcie do około 29 V przy maksimum przetwornicy 16 V | specyfikacja: łącznik dwukierunkowy z odcięciem nadnapięciowym około 17 V; wymaga projektu R02 i prób T6 |
| F19 | Pobór stacji pomijał TCXO, zasilanie 5 V ekranu, podświetlenie i prądy spoczynkowe; ESP32-S3 przy 30 mA był optymistyczny | model: 3,6–10,0 Wh na dobę; nRF52840 około 96 h na AA, ESP32-S3 35–52 h; W23 wymaga średnio ≤64 mA z 3,3 V; pomiar w T6 |
| F20 | Czułość −110 dBm podana na układzie, bez strat filtra SAW, filtra harmonicznych i ochrony ESD | czułość definiowana na złączu antenowym; zapas 1 km spada o około 3 dB, jeśli układ osiąga tylko −110 dBm; T4 i D10 |
| F21 | Brak wymagań cyberbezpieczeństwa RED (EN 18031) i ryzyko badań EN 300 328 dla wyłączonego radia 2,4 GHz w MCU | dopisane do W17, odbioru i D14 |
| F22 | Zewnętrzna FRAM była nieszyfrowana; po wylutowaniu zawierała tożsamość i kolejkę | szyfrowanie rekordów kluczem w chronionej pamięci MCU; ZNISZCZ DANE usuwa klucz |
| F23 | Wystawienie anteny przez okno nie działa w piwnicy ani w budowli ochronnej | antena z przepustem montowana na stałe w przygotowaniu; okno jako procedura zapasowa |
| F24 | Cisza radiowa: brak organu wydającego polecenie; wyjątek opiekuna mógł naruszać zakaz nadawania | polecenie wydaje wójt na podstawie decyzji uprawnionych organów; wyjątek tylko przy ciszy operacyjnej, gdy polecenie go dopuszcza |
| F25 | Ramy zarządzania kryzysowego, terminologia obiektów, RODO, kategorie potrzeb i stany zgłoszeń były zbyt ogólne | koncepcja i specyfikacja: ustawa o zarządzaniu kryzysowym, 10 kategorii, 6 stanów, D18 dla meldunku o stanie obiektu; uzgodnienia z gminą D07, D12, D13 |
| F26 | Brak ścieżki dla kontrybutorów oprogramowania układowego i licencji kodu C/C++ | CONTRIBUTING: zadania na start; REUSE i LICENSE.md obejmują `firmware/`; licencja microReticulum do potwierdzenia przed D14 |
| F27 | Sprawdzenie części i przepisów w źródłach: TPS25947 ma maksimum 28 V, TPS3840 nie mierzy VSYS do 16 V, TPS61222 w wyłączeniu przepuszcza napięcie, MAX16150 wymaga szyny 1,3–5,5 V, LM74502 nie blokuje prądu wstecznego; rozporządzenie Dz.U. 2022 poz. 567 nie obejmuje pasma 869,4–869,65 MHz, a podstawą pracy bez pozwolenia jest art. 145 ust. 2 pkt 5 Pke; logo używało kroju Avenir Next bez prawa do rozpowszechniania kształtów liter | poprawione w specyfikacji, koncepcji i BOM; logo przerysowane krojem Nunito Sans (SIL OFL 1.1) |

## F01: kontroler USB

W [połączeniach kontrolera](../hardware/radio-test-r01/connections.csv) pin Y1.1 jest połączony z V3. Jest to wejście standby oscylatora ASE-8.000MHZ-L-C-T. Stały stan wysoki utrzymuje oscylacje. Karta ASE dla 8 MHz podaje typowo 2,5 mA i maksymalnie 7 mA; cały modem USB 2.0 ma w suspend budżet 2,5 mA. Nawet po zatrzymaniu MCU i radia nie da się zagwarantować bilansu. Odłączenie D+ przez Q1 nie odłącza Y1. [ASE, wydanie 2022-02-18, s. 1–2](https://abracon.com/Oscillators/ASEseries.pdf), [USB 2.0](https://www.usb.org/document-library/usb-20-specification), [ECN suspend, kopia dokumentu USB-IF](https://git.nefarius.at/nefarius/USB-Bluetooth-Specs/media/branch/master/usb_20_0702115/Suspend%20Current%20ECN.pdf).

Potrzebne są sterowany tor zegara/zasilania i firmware obsługujący suspend/resume. Zmiana wymaga nowej rewizji CAD, ERC/DRC, eksportów i kontroli paczki. W R01.3 jej nie wykonano, więc Gerbery R01.3 nie są wersją poprawioną. W 0.5 problem dotyczy wyłącznie R01.3 jako modemu zasilanego z VBUS (HOLD); stanowisko do T4 zasila się z zasilacza laboratoryjnego, więc go nie blokuje. Stacja R02 nie zasila się z VBUS (VSYS niezależne); wykonanie A pobiera z VBUS tylko prąd PHY USB ≈2,5 mA.

Odbiór obejmuje prąd przed konfiguracją, deklarowany budżet po konfiguracji, suspend, resume i udar przy podłączeniu. C1=1 µF nie opisuje całej pojemności pobierającej energię z USB: są kondensatory za LDO oraz przyszły moduł RF. Nie stwierdzono przekroczenia udaru pomiarem; trzeba go zmierzyć w kompletnym urządzeniu. [Warunki przed produkcją](../hardware/radio-test-r01/przed-produkcja.md), [odbiór](spec/odbior.md).

## F02: czasy stosu i cisza nadajnika

Analiza dotyczy Reticulum `e40191b3d193b46b7f2d8a44424a594cd758839b`. Ten commit wyznacza punkt analizy i nie jest zatwierdzoną zależnością wydania. MTU wynosi 500 B, podstawowy limit czasu odcinka 6 s. Dla znanej trasy o długości dwóch odcinków i interfejsu raportującego 240 bit/s inicjator linku dostaje:

```text
timeout = 500 × 8 / 240 + 6 + 2 × 6 = 34,67 s
```

Zegar linku i watchdog ruszają przed `packet.send()`. Oczekiwanie w adapterze zużywa więc czas zestawiania, nawet przed pierwszym TX. Zasób ma odrębny mechanizm limitów czasu oparty m.in. na RTT. Sam limit czasu READY=900 s nie zmienia tych mechanizmów. [Reticulum: stałe](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Reticulum.py), [Transport.first_hop_timeout](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Transport.py), [Link](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Link.py), [Resource](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/RNS/Resource.py).

Kontrprzykład analityczny: pakiet linku czeka w adapterze za trzema datagramami po 500 B. Każdy zajmuje sześć fragmentów P1 i 674 B w eterze:

```text
TX = (500 + 6 × 29) × 8 / 4800 = 1,1233 s
TX + cisza = 13 × TX = 14,6033 s
trzy cykle = 43,81 s > 34,67 s
```

To dolne oszacowanie czasu bez kolizji, zajętego kanału i narastania mocy nadajnika. Kolejka z takim ruchem może wygasić link przed nadaniem jego żądania. Kontrprzykład nie jest pomiarem, bo adaptera i firmware jeszcze nie wykonano. Pokazuje, że do zgodności nie wystarczy sama deklaracja przepływności i limitu czasu READY. Jedna zgoda READY ogranicza modem, ale nie usuwa oczekiwania po stronie hosta za ruchem przekazywanym.

Przed projektowaniem kolejnych PCB wykonać T3: przypięty Reticulum/LXMF, emulator TX/ciszy/CCA, ograniczone kolejki, zimna i ustalona trasa, link, zasób, potwierdzenia, restarty i ruch przekaźnika. Rejestrować wiek pakietu oraz wszystkie ponowienia. Rozstrzygnąć planowanie i limity czasu całego stosu; nie uznawać zwiększenia samego READY za rozwiązanie.

W 0.5 interfejs P1 jest częścią stosu w stacji, więc adapter i READY znikają, a stos zna dług ciszy i stan kolejki radiowej. Kontrprzykład pozostaje jednak ważny dla kolejki wewnątrz stacji: pakiet linku za trzema przekazywanymi datagramami po 500 B nadal czeka 43,81 s. Stos musi więc planować wysyłkę z uwzględnieniem kolejki albo wydłużać limity czasu; rozstrzyga to T3 na mikrokontrolerze. Jeden pakiet okazjonalny na wiadomość SA1 (D01) usuwa z ruchu aplikacji zestawianie linku i zasoby. [Kontrakt radia](spec/radio.md), [plan prób](conception/08-plan-weryfikacji-i-decyzje.html).

## F03: ładowarka i tolerancje

MIC2007: przy pozycji IOUT=2 A karta podaje CLF=210–286 V. Z zależności I=CLF/R i wymaganego progu 1,6–2,1 A wynika:

```text
R ≤ 210 / 1,6 = 131,25 Ω
R ≥ 286 / 2,1 = 136,19 Ω
```

Przedział jest pusty jeszcze bez tolerancji rezystora. Dobór na wartość typową nie kwalifikuje wariantu. Potrzebny jest inny niezależny element albo odrębna kwalifikacja całego rozwiązania. Obecnie nie ma zatwierdzonego drugiego wariantu. [Microchip DS20006486B, s. 6 i 20](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/MIC20XX-Fixed-and-Adjustable-Current-Limiting-Power-Distribution-Switches-DS20006486B.pdf).

TPS2553: tabela doboru dla 15 kΩ /1% podaje minimum 1594,5 mA, poniżej wymaganych 1600 mA. Punktem wyjścia jest rezystor 0,1%. Nadal trzeba zamknąć tolerancje, temperaturę złącza i pomiary portu. Próg ograniczania dotyczy stanu przed foldback i wyłączeniem termicznym, a nie stałego prądu zwarcia. Koordynacja F1/F2 i crowbar pozostają do odbioru. [TI SLVS841F, s. 7, 15 i 20](https://www.ti.com/lit/ds/symlink/tps2553.pdf), [specyfikacja elektroniki](spec/elektronika.md).

## F04–F07: poprawione kontrakty i dane

- **Części:** w 0.4 BOM stacji był zgodny z MCU kontrolera: STM32F103CBT6. W 0.5 ten MCU zostaje na stanowisku laboratoryjnym, a stacja używa nRF52840 lub ESP32-S3. Wariant ST radia to S2-LPQTR; S2-LPCBQTR nie obejmuje 869,525 MHz w górnym paśmie. Żaden wariant RF nie jest jeszcze odebrany. [BOM](spec/bom-stacji.csv), [warianty S2-LP, rev. 13](https://www.st.com/resource/en/datasheet/s2-lp.pdf).
- **Tekst:** model odrzuca kategorie Unicode Cc i Cf, również przy odbiorze JSON z sekwencjami `\u`. Polskie litery pozostają dozwolone. Nie jest to implementacja ochrony HTML przyszłej strony.
- **Statusy:** RECEIVED rezerwuje event=1/state=1; STATUS wymaga event ≥2 i state 2/3. Starsze statusy i konflikty nadal podlegają regułom modelu.
- **Próba obciążenia:** 50 zgłoszeń łącznie z A w pierwszych pięciu minutach, droga A–B–OSP i powrót przez B. RECEIVED ma wrócić na A do 30 min od pierwszego COMMIT. ≥99% z 50 oznacza 50/50. Próba nie kwalifikuje sieci tysiąca stacji.
- **Host i USB:** START ma zapobiegać automatycznemu uśpieniu hosta, także podczas restartu strony. W 0.5 uśpienie hosta wyłącza tylko stronę i panel; stacja pracuje dalej. Protokół USB laptop–stacja jest idempotentny (D17). Są to wymagania dla przyszłego pakietu i firmware; te funkcje jeszcze nie działają.

## F08: licencje pakietu START

Analizowane LICENSE Reticulum i LXMF zawierają dodatkowe ograniczenia użycia oraz tworzenia zbiorów do treningu AI. Nie są więc niezmodyfikowaną licencją MIT. GPL nie dopuszcza takich dodatkowych ograniczeń w rozpowszechnianym połączonym dziele, dlatego 2026-10-07 kod WICI przeniesiono na MIT. Pakiet START dołącza teksty licencji Reticulum i LXMF przypiętych wersji; jego użytkownicy podlegają ich warunkom, a pakiet jako całość nie jest oprogramowaniem otwartym w rozumieniu OSI. [Reticulum LICENSE](https://github.com/markqvist/Reticulum/blob/e40191b3d193b46b7f2d8a44424a594cd758839b/LICENSE), [LXMF LICENSE](https://github.com/markqvist/LXMF/blob/c3ff2d6dc2f256daab896dadc044dd5a913ecbb7/LICENSE), [mapa licencji WICI](../LICENSE.md).

Repozytorium zawiera własny model i dokumentację; nie dołącza kodu tych zależności. Publikacja obecnych źródeł i kwalifikacja przyszłej paczki START są osobnymi ocenami.

## Dowody i granice przeglądu

Model obejmuje 24 testy, w tym walidację Unicode, zastrzeżone numery STATUS, typ TEST z konfliktem względem REQUEST, kwarantannę nieznanego nadawcy i przyjmowanie wiadomości przez stację tylko od przypiętej OSP. [Zapis weryfikacji](../software/reference/weryfikacja.json) wiąże wynik z hashami czterech źródeł. Dziesięć regresji publikacji sprawdza m.in. pustą, niepełną i nieaktualną paczkę, odrzucanie błędu bez przepisywania dowodów, linki i kotwice stron HTML, linki strony Pages, zakres archiwum bez filmów i tryb manifestu dla PR. Kontrola repozytorium sprawdza linki, sumy źródeł, aktualność obliczeń, powiązanie raportów CAD i zgodność archiwum z eksportami.

Przejrzano połączenia i widoki kontrolera oraz raporty i ich wyłączenia. CAD i plików produkcyjnych R01.3 nie zmieniano. Kontrola ich sum nie jest nowym uruchomieniem ERC/DRC, niezależnym przeglądem elektrycznym ani próbą płytki. Nie ma fizycznego dopasowania złączy, pomiaru USB/RF, działającego firmware, strony, pamięci USB ani odbioru zasilania.

Nadal aktualne są pozostałe blokady: stos na mikrokontrolerze (F10), ujemny zapas 1 km przy niskich antenach (F11), decyzja P1 wobec LoRa (D10), kanał współdzielony z LoRaWAN RX2 i Meshtastic (D11), uzgodnienia z gminą (D12, D13), udar A/B, ochrona telefonu, regulacja i izolacja przetwornicy, PE/RCBO dla przypadkowych zasilaczy klasy I, zgodność dwóch wykonań radia, terenowe 1 km i energia 24 h. Nie ma podstaw do deklaracji „military grade”, określonego MTBF ani kosztu odebranej serii. [Pełna lista odbioru](spec/odbior.md).

Kolejność rozstrzygnięć według [planu weryfikacji](conception/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac): stacja poziomu 1 na płytkach rozwojowych z T3 na obu MCU (D14); wiadomości i czas radia z emulatorem P1 (D01); laptop, protokół USB i strona; RF na stanowisku R01.3, potem na płytce R02; sieć terenowa z przekaźnikiem na ogniwach; zasilanie poziomu 3; kompletny pilotaż 24 h. Uzgodnienia z gminą (D12, D13) prowadzi się równolegle i kończy przed pilotażem. Nie zdejmować HOLD przez zaliczenie testów modelu lub CI.

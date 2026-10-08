# WICI R02: tor RF i stos warstw

**Status: 2026-10-08, przed schematem. Nie zamawiać.** Dokument zbiera referencje producentów, wybiera stos warstw, geometrię linii 50 Ω i części toru RF obu wykonań oraz oddziela to, co da się ustalić teraz, od tego, co rozstrzyga T4 (D10). Wymagania są w [radiu](../../docs/spec/radio.md) i [BOM stacji](../../docs/spec/bom-stacji.csv), lekcje z R01.3 w [lekcjach](lekcje.md#tor-rf). Materiały producentów czytano lokalnie i nie są w repozytorium. Oznaczenie „do sprawdzenia” dotyczy danych, których nie potwierdzono w karcie producenta.

## Referencje producentów

**Wykonanie A (TI CC1120).** Referencja to CC1120EM 868/915: archiwum [SWRR091](https://www.ti.com/lit/zip/swrr091) (to samo co SWRC222, rewizja 1.1 z 2011-05-09), schemat [TIDR240](https://www.ti.com/lit/pdf/tidr240) i BOM [TIDR241](https://www.ti.com/lit/pdf/tidr241).
- **Stos według pliku readme archiwum:** 4 warstwy, 1,24 mm, miedź 4 × 35 µm, dielektryki 0,4 mm (2 × prepreg 7628), 0,3 mm (2 × 2157) i 0,4 mm, laminat DE104iML, Er 4,45, tg δ 0,016.
- **Uwaga o lokalnym imporcie:** import KiCad w `reference-private/` ma błędny stos (dielektryki 0,48 mm, Er 4,5), więc stosu nie bierze się z importu.
- **Linia od sieci dopasowania do SMA:** 0,457 mm szerokości ze szczeliną 0,254 mm do wylewki na 0,4 mm dielektryka, co daje około 60 Ω, a nie 50 Ω. Dopasowanie zestrojono na tej geometrii, więc przenosi się je razem z geometrią i dielektrykiem L1–L2 około 0,4 mm.
- **Topologia nadajnika:** zasilanie PA przez dławik, potem 15 pF, pułapka na drugiej harmonicznej (7,5 nH ∥ 1 pF) i filtr dolnoprzepustowy 18 nH / 3 pF / 12 nH do złącza.
- **Odbiornik:** dyskretny symetryzator LC dołączony do tego samego węzła przez TRX_SW.
- **Części toru:** wszystkie w obudowie 0402, cewki drutowe LQW15AN, kondensatory NP0 ±0,1/0,25 pF.
- **Wersje IPC:** SWRR106 (2 warstwy, 0,8 mm) i SWRR107 (4 warstwy) mają tę samą listę części, bo zintegrowany element bierny Murata nie zależy od stosu. Tego elementu nie sprawdzono pod kątem dostępności.

**TCXO w referencji TI.** Na footprincie X2 (Epson TG-5021CG, 2,5 × 2,0 mm) montuje się C321, C322 i R322, a C301 = 0 Ω; X1, C311, R12 i R321 zostają puste. CC1120 przyjmuje 31,25–33,6 MHz, przebieg sinusoidalny obcięty 0,8–1,5 Vpp przez kondensator szeregowy ([karta CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), SWRS112H, rozdział 4.8). TI nie ma osobnej noty o stosie; wzorcem jest sam projekt referencyjny.

**Wykonanie B (ST S2-LP).**
- **Wytyczne PCB:** nota [AN4947](https://www.st.com/resource/en/application_note/an4947-pcb-design-guidelines-for-the-s2lp-transceiver-stmicroelectronics.pdf) (rewizja 2) zaleca płytkę trzy- albo czterowarstwową z masą tuż pod warstwą górną, w odległości około 0,3 mm, oraz linie współpłaszczyznowe 50 Ω z masą od złącza do sieci dopasowania.
- **Płytki ST:** X-NUCLEO-S2868A2 i STEVAL-FKI868V2 mają po trzy warstwy miedzi (góra, wewnętrzna masa, dół). ST nie podaje grubości żadnej z nich. Linia X-NUCLEO do SMA (0,508 mm, szczelina około 0,25 mm) daje 50 Ω przy około 0,29 mm dielektryka, co zgadza się z AN4947.
- **Tor X-NUCLEO:** S2-LP, element BALF-SPI2-01D3 (symetryzator z filtrem harmonicznych w jednym układzie, nieczuły na stos), 100 pF, puste pola na filtr π i złącze SMA.
- **Parametry BALF-SPI2-01D3** (karta DocID030877 rewizja 1):
  - straty 1,7 dB typowo i 2,1 dB maksymalnie w nadawaniu;
  - tłumienie drugiej harmonicznej ≥40 dB, trzeciej ≥47 dB;
  - moc wejściowa do 20 dBm;
  - obudowa flip-chip o rastrze 0,4 mm.
- **Moc PA:** 13 dBm na złączu wymaga około 15–15,5 dBm na wyjściu PA, czyli trybu boost S2-LP (do 16 dBm, [karta S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf) DS11896 rewizja 13).
- **Zegar:** obie płytki ST mają kwarc 50 MHz (NDK NX1612SA), nie TCXO. S2-LP przyjmuje 24–26 albo 48–52 MHz. Zegar zewnętrzny na XIN: ≥0,4 Vpp w zakresie 0–1,4 V, a ST zaleca sprzężenie stałoprądowe z poziomem ≥0,2 V.

## Stos warstw

Jeden stos obsługuje oba wykonania. Geometria TI zależy od stosu, a BALF w wykonaniu B nie zależy, więc stos dobiera się do TI, a linie w B wymiaruje na nowo.

**Propozycja: JLCPCB JLC04161H-7628E** albo jego odpowiednik, potwierdzony na piśmie u innego wykonawcy. Grubości z lokalnej kopii strony JLC z 2026-10-06:

| Warstwa | Materiał | Grubość | Rola |
|---|---|---|---|
| L1 | miedź 35 µm | | RF i elementy |
| | prepreg 7628 + 7628 (Dk 4,4) | 0,218 + 0,2104 = 0,428 mm | dielektryk RF, jak 2 × 7628 w TI (0,4 mm) |
| L2 | miedź 15,2 µm | | ciągła masa |
| | rdzeń | 0,6 mm | |
| L3 | miedź 15,2 µm | | zasilanie i masa |
| | prepreg 7628 + 7628 | 0,428 mm | |
| L4 | miedź 35 µm | | |
| Razem | | około 1,6 mm | standardowe gniazda SMA krawędziowe na 1,6 mm |

**Domyślny stos JLC04161H-7628 odpada.** Ma między L1 a L2 tylko 0,2104 mm, więc geometria TI dałaby tam 36–40 Ω. To jest ten sam stos co w R01.3 ([lekcje](lekcje.md#zasady-layoutu)). W `checks/stackup.json` zapisuje się:
- miedź 35 / 15,2 / 15,2 / 35 µm;
- prepreg 0,428 mm, rdzeń 0,6 mm, prepreg 0,428 mm;
- Dk prepregów 4,4, a rdzenia według JLC;
- tg δ z karty laminatu (TI użył 0,016), a nie domyślne 0,02 z KiCad.

**Linia 50 Ω (współpłaszczyznowa z masą na L2):** szerokość 0,65 mm, szczelina 0,20 mm; wariant 0,69 / 0,25 mm też daje 50 Ω. Rząd przelotek masy po obu stronach co 1,5–2 mm, ciągła masa na L2 pod całym torem RF. Wynik pochodzi ze wzoru zamkniętego, bez grubości miedzi i bez maski. Miedź i maska obniżają impedancję o 1–3 Ω, a zwykłe tolerancje wykonania dają około ±3 Ω. Wymiary potwierdza się kalkulatorem wykonawcy i kuponem testowym na panelu (TDR).

## Części

| Element | Kandydat 1 | Kandydat 2 | Ocena |
|---|---|---|---|
| Sieć RF A | dyskretna sieć TI z SWRR091 bez zmian, na stosie powyżej | | pola na dodatkowy filtr π przed SMA (puste) |
| Sieć RF B | BALF-SPI2-01D3 z pustymi polami π jak na X-NUCLEO | dyskretna sieć z karty S2-LP, jeśli wykonawca nie montuje flip-chip | sieć dyskretną ST zestrojono na nieopisanym stosie 3-warstwowym, więc trzeba ją przestroić analizatorem sieci |
| TCXO A | Epson TG2520SMN 32 MHz, ±0,5 ppm (2,5 × 2,0 mm, jak X2 w TI; zgodność wyprowadzeń z TG-5021CG do sprawdzenia) | Rakon RST2016N (wariant 32 MHz do sprawdzenia) | wyjście ≥0,8 Vpp jest równe minimum CC1120, więc mierzy się amplitudę na EXT_XOSC; zapasowo TCXO z wyjściem CMOS |
| TCXO B | Epson TG2520SMN 26 MHz | Rakon RST2016N 26 MHz | **26 MHz zamiast 50 MHz z X-NUCLEO**, bo Epson podaje starzenie w pierwszym roku ±0,5 ppm dla 24–40 MHz, a ±1,5 ppm dla 40–55 MHz. Wymaga nowego zestawu rejestrów (`firmware/tools/s2lp_p1_registers.py` zakłada 50 MHz) i próby P1 z zegarem 26 MHz. Sprzężenie obciętego sinusa z XIN potwierdza się z ST |
| ESD na złączu antenowym | Infineon ESD101-B1-02EL (0,1 pF, ±5,5 V) | ESD131-B1-W0201 (0,23 pF); drugi producent: tłumik polimerowy Littelfuse albo Murata (do sprawdzenia) | 13 dBm w 50 Ω to 2,0 V szczytowo, a przy rozwartej albo zwartej antenie do około 4 V, więc ±5,5 V wystarcza przy 13 dBm. W trybie boost (16 dBm) zapas znika. ESD leży po stronie złącza; harmoniczne mierzy się z nim zamontowanym |
| SMA-F krawędziowe | Cinch 142-0701-881 (na X-NUCLEO) | Amphenol RF albo Molex na płytkę 1,6 mm (do sprawdzenia) | grubość płytki, kształt przejścia i środkowy pin wobec linii 0,65 mm sprawdza się w rysunku producenta |
| Przełącznik SPDT (tylko osobny tor RX) | pSemi PE4259: 0,35 dB i izolacja 30 dB przy 1 GHz, P1dB +33,5 dBm, karta z 07/2026 | Infineon BGS12SN6 (karta do sprawdzenia) | oba wytrzymują ≥+20 dBm |
| Filtr SAW 869 MHz | Microchip TFS869N | TAI-SAW TA1457A albo Raltron RSF-869.000 | patrz niżej |

**Filtr SAW: żaden katalogowy filtr nie spełnia wiersza BOM.**

| Wymaganie BOM | Co dają katalogowe filtry |
|---|---|
| strata ≤2,5 dB | 3–4 dB maksymalnie |
| ≥20 dB przy 862 MHz | 15–20 dB (przy 862 i 880 MHz) |
| ≥30 dB przy 880–915 MHz | 15–20 dB przy 880 MHz; najlepszy przy 883–915 MHz jest TFS869N z ≥45 dB |
| wytrzymałość ≥+20 dBm we wspólnym torze | 10–15 dBm |

Wspólny tor z SAW (wariant b) odpada więc przy dostępnych częściach. Zostaje filtr tylko w torze odbiorczym za przełącznikiem SPDT (wariant a). Strata takiego toru (około 4 dB filtru, 0,3 dB przełącznika i 0,2 dB ESD) oznacza, że układ radiowy musi osiągać około −114,5 dBm, żeby na złączu było −110 dBm. RF360 B4316 nie ma stanu u dystrybutorów, a minimalne zamówienie to 5000 sztuk. Wiersz BOM przepisuje się na wartości osiągalne po pomiarze w T4.

## Ustalić teraz

| Decyzja | Propozycja |
|---|---|
| Liczba warstw i stos | 4 warstwy, L1–L2 około 0,43 mm (2 × 7628), ciągła masa na L2, razem 1,6 mm; zapis w `checks/stackup.json` |
| Linie RF | 50 Ω: 0,65 / 0,20 mm z rzędem przelotek; odcinek TI przeniesiony bez zmian geometrii |
| Sieć A | TI SWRR091 bez zmian, z pustymi polami filtru π |
| Sieć B | BALF-SPI2-01D3 z pustymi polami π; budżet mocy z trybem boost |
| Zegar | A: TCXO 32 MHz na EXT_XOSC; B: TCXO 26 MHz na XIN z nowym zestawem rejestrów |
| Kalibracja | pomiar i korekta częstotliwości przy produkcji i co rok zostają obowiązkowe. Bez kalibracji sama tolerancja początkowa ±1,5 ppm zużywa budżet. Z kalibracją TCXO 26 albo 32 MHz daje ±1,5 ppm wobec ±2,0 ppm z [radia](../../docs/spec/radio.md) |
| Złącze antenowe | pola ESD poniżej 0,3 pF przy SMA; gniazdo krawędziowe na płytkę 1,6 mm |
| Rezerwa | miejsce i pola na przełącznik i filtr SAW w torze RX (zworki 0 Ω i elementy puste), żeby wynik T4 nie wymagał nowego stosu ani obrysu |
| Dostęp pomiarowy | punkt pomiarowy (złącze U.FL albo 0 Ω) mocy po stronie układu; kupon 50 Ω na panelu |

## Czeka na T4 (D10)

| Sprawa | Pomiar | Reguła |
|---|---|---|
| Dodatkowy filtr harmonicznych A | 2. i 3. harmoniczna (1739 i 2609 MHz) CC1120EM przy 13 dBm i przy mocy maksymalnej, z elementem ESD i bez niego | filtr π tylko przy poziomie bliższym niż 6 dB do granicy EN 300 220-2 |
| Harmoniczne B | to samo na X-NUCLEO-S2868A2 (BALF) | pola π puste, jeśli BALF wystarcza |
| SAW i przełącznik | PER ≤1% przy −110 dBm z zakłóceniem −30 dBm przy 862 i 880 MHz (i modulowanym LTE i GSM), z filtrem i bez niego | bez filtru, jeśli same układy spełniają blokowanie kategorii 1,5; wariant a, jeśli dopiero filtr pomaga |
| Wiersz SAW w BOM | zmierzona strata i tłumienie kandydatów w −20…+45 °C | wymaganie na wartości osiągalne |
| Budżet czułości | czułość układu w P1 i strata toru wejściowego | wymagana czułość układu = −110 dBm minus strata toru wejściowego; zapis w radiu |
| Amplituda TCXO | przebieg na EXT_XOSC i XIN z wybranym TCXO | obcięty sinus albo TCXO z wyjściem CMOS |
| Niedopasowanie anteny | 60 s przy rozwartym i 60 s przy zwartym złączu z docelowym ESD i filtrem | moc i widmo bez zmian |
| D10 (P1 albo LoRa) | całe T4 i T5 | przy LoRa zmieniają się referencje i TCXO, a stos 0,43 mm zostaje |

## Źródła

- TI CC1120EM-868-915-RD: https://www.ti.com/tool/CC1120EM-868-915-RD; SWRR091: https://www.ti.com/lit/zip/swrr091; SWRR106 i SWRR107: https://www.ti.com/lit/zip/SWRR106, https://www.ti.com/lit/zip/SWRR107; TIDR240, TIDR241; karta CC1120 SWRS112H.
- ST: karta S2-LP DS11896 rewizja 13 (2025-10-08); AN4947 rewizja 2; X-NUCLEO-S2868A2 (UM2638 rewizja 2, BOM rewizja 2, Gerber 1.0); STEVAL-FKI868V2; BALF-SPI2-01D3 DocID030877 rewizja 1: https://www.st.com/en/wireless-connectivity/balf-spi2-01d3.html
- JLCPCB, stosy: https://jlcpcb.com/impedance (lokalna kopia z 2026-10-06 w `reference-private/source/`).
- Microchip TFS869N: https://ww1.microchip.com/downloads/aemdocuments/documents/RFSP/ProductDocuments/DataSheets/TFS869N.pdf; TAI-SAW TA1457A rewizja 1.0; Raltron RSF-869.000-4000-3838-TR rewizja A.
- pSemi PE4259 DOC-03694-5.01: https://www.psemi.com/pdf/datasheets/pe4259ds.pdf; Infineon ESD101-B1 rewizja 1.4.
- Epson TG2016SMN/TG2520SMN: https://download.epsondevice.com/td/pdf/brief/TG2520SMN_en.pdf (starzenie w pierwszym roku ±0,5 ppm dla 24–40 MHz, ±1,5 ppm dla 40–55 MHz).

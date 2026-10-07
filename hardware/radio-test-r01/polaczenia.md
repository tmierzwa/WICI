# WICI: połączenia R01

## Kontroler

U1: STM32F103CBT6, LQFP48, 128 KiB flash. C8 z 64 KiB nie jest zatwierdzonym zamiennikiem bez kompilacji firmware. Zgodna obudowa nie oznacza zgodności mikrokontrolera innego producenta.

| Funkcja | Pin U1 | Połączenie |
|---|---:|---|
| Zasilanie 3,3 V | 1, 9, 24, 36, 48 | VBAT, VDDA i trzy VDD; kondensatory C3–C8 |
| Masa | 8, 23, 35, 47 | VSSA i VSS |
| Zegar MCU | 5 | Y1: ASE-8.000MHZ-L-C-T, 8 MHz; HSE bypass; pin 6 NC |
| USB D− / D+ | 32 / 33 | R2 / R1 = 0 Ω; USBLC6; złącze USB B |
| Podłączenie USB | 25 | LOW włącza Q1 i rezystor 1,5 kΩ do D+ |
| SPI CS / SCK / MISO / MOSI | 14 / 15 / 16 / 17 | J2; poziomy 3,3 V |
| Radio IRQ0 / IRQ2 | 18 / 19 | J2; oba wejścia przerwań |
| Reset radia | 21 | J2; R9 utrzymuje LOW podczas startu MCU |
| SWDIO / SWCLK / NRST | 34 / 37 / 7 | J3 |
| BOOT0 / BOOT1 | 44 / 20 | R6 / R7, po 10 kΩ do masy |
| UART TX / RX | 30 / 31 | J4; logika 3,3 V |
| EEPROM SCL / SDA | 42 / 43 | M24C64-RMN6TP, adres 0x50; 4,7 kΩ do 3,3 V |

GPIO niewymienione w tabeli są NC. Firmware musi korzystać z podanych pinów. Zegar radia 32 MHz znajduje się na module RF; Y1 go nie zastępuje.

USB zasila cały kontroler i moduł radiowy. J2.2 jest wyjściem 3,3 V. Nie podłączać drugiego zasilacza do J2. Nie łączyć napięcia 5 V ani 12 V z pinami sygnałowymi. J3.1 jest odniesieniem napięcia dla programatora, a nie wejściem zasilania.

U2: AP2112K-3.3TRG1. TI TLV75533PDBVR ma zgodną kolejność pinów w SOT23-5: VIN, GND, EN, NC, OUT. Po zamianie nadal wymaga próby stabilności i temperatury. C2 musi mieć co najmniej 1 µF efektywnej pojemności przy 3,3 V i w zakresie temperatur. Rezystory i kondensatory mają obudowy 0805. R3: 1%, pozostałe rezystory: 1%; kondensatory: X7R, 16 V. Nie ma zatwierdzonych zamienników całego kontrolera ani radia.

USB B: własny footprint dla Würth 61400416121, rysunek 001.003, 2024-01-30. Otwory sygnałowe 0,92 mm; ekran 2,50 mm. Pobrany model CAD miał otwory ekranu 2,30 mm, dlatego nie użyto go w projekcie. Fizyczne dopasowanie trzeba jeszcze sprawdzić.

## Przewód J2 → referencja CC112xEM 868/915

Numery poniżej są elektrycznymi numerami pinów, a nie numerami kolejnych żył widzianych od strony kabla. Złącza P1/P2 modułu TI są na spodzie płytki, a widok od spodu odwraca obraz. Najpierw sprawdzić przewód miernikiem, bez zasilania. Długość maksymalna przyjęta do prototypu: 5 cm. Pierwsza próba SPI: około 1 MHz.

| J2 kontrolera | Sygnał | Złącze modułu TI | Pin CC1120 |
|---:|---|---|---:|
| 1 | GND | P1.1 | masa modułu |
| 2 | 3,3 V | P2.7 | zasilanie modułu |
| 3 | SCK | P1.16 | 8 |
| 4 | GND | P1.19 | masa modułu |
| 5 | MOSI | P1.18 | 7 |
| 6 | MISO | P1.20 | 9 |
| 7 | CS_N | P1.14 | 11 |
| 8 | RESET_N | P2.15 | 2 |
| 9 | GPIO0 / IRQ0 | P1.10 | 10 |
| 10 | GPIO2 / IRQ2 | P1.12 | 4 |

P2.9 jest połączony z tym samym 3,3 V co P2.7. P2.2 również jest masą. Pozostałych pinów nie wolno dowolnie traktować jako masy. Typ i orientacja wtyków pasujących do złączy TI wymagają zatwierdzenia mechanicznego przed zamówieniem wiązki.

## Złącza serwisowe

J3: 1 = VTref 3,3 V, 2 = SWDIO, 3 = GND, 4 = SWCLK, 5 = NRST. Pierwsze programowanie wymaga SWD; ten STM32 nie ma fabrycznego USB DFU. Programator nie może podawać własnego 3,3 V na pin 1.

J4: 1 = GND, 2 = TX kontrolera, 3 = RX kontrolera. Adapter UART musi mieć poziomy 3,3 V; nie jest to interfejs RS-232.

TP1 = VBUS za F1, TP2 = 3,3 V, TP3 = GND, TP4 = NRST, TP5 = 8 MHz MCU, TP6 = reset radia, TP7 = CS_N.

## Zasilanie R01.2

J1.1 → VBUS_USB → F1.1; F1.2 → VBUS → U2.1 / U2.3 oraz C1.1 i TP1. U3.5 i C14.1 są po stronie USB przed F1. Bezpiecznik nie ma polaryzacji. Ścieżki obu sieci VBUS: 0,5 mm.

F1: MF-NSMF050-2 (Bourns), 0,5 A hold przy 23 °C, 1 A trip. Alternatywa: 1206L050/15YR (Littelfuse), 0,5 A hold przy 20 °C. Zamiennik wymaga sprawdzenia montażu, spadku napięcia i deratingu. F1 chroni gałąź zasilania przed przetężeniem i nie jest ogranicznikiem 500 mA.

Wszystkie kondensatory 3,3 V mają własne przelotki do płaszczyzny i masy. C1, C14 i C12 mają osobne przelotki masy. H1–H4: otwory nieplaterowane 3,2 mm, izolacyjne dystanse M3. [Wydruk](mechanika-1-do-1.pdf) przedstawia widok od strony elementów. Fizycznego dopasowania części nie potwierdzono.

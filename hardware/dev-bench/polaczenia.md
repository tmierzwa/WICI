# WICI: połączenia płytki nośnej N1

Plik generuje `tools/make_schematic.py` z `tools/design.py`; nie edytować ręcznie. Opis płytki, stanowisk i przypisania: [płytka nośna](plytka-nosna.md).

## Sygnały MCU

| Sieć | Arduino (złącze.pin) | nRF52840 (A) | ESP32-S3 (B, złącze.pin) | Pozostałe piny sieci |
|---|---|---|---|---|
| SPI_SCK | D3 (J3.4) | P1.04 | GPIO12 (J5.18) | J9.16, J7.1, U1.6, J11.2, R17.2, R18.2, R17.1, R18.1 |
| SPI_MOSI | D11 (J4.4) | P1.13 | GPIO11 (J5.17) | J9.18, J7.2, U1.5, J11.3 |
| SPI_MISO | D12 (J4.5) | P1.14 | GPIO13 (J5.19) | J9.20, U1.2, J11.4 |
| RF_CS | A1 (J2.2) | P0.04 | GPIO10 (J5.16) | J9.14, J11.5, R11.2 |
| RF_RESET | D7 (J3.8) | P1.08 | GPIO9 (J5.15) | J10.15, R12.1 |
| RF_GPIO0 | A0 (J2.1) | P0.03 | GPIO14 (J5.20) | J9.10, J11.8 |
| RF_GPIO1 | A2 (J2.3) | P0.28 | GPIO21 (J6.18) |  |
| RF_GPIO2 | A3 (J2.4) | P0.29 | GPIO4 (J5.4) | J9.12, J11.9 |
| RF_GPIO3 | A5 (J2.6) | P0.31 | GPIO42 (J6.6) | J10.18 |
| FRAM_CS | D9 (J4.2) | P1.11 | GPIO8 (J5.12) | U1.1, J11.6, R20.2 |
| LCD_CS | D4 (J3.5) | P1.05 | GPIO7 (J5.7) | J7.3, J11.7, R13.1 |
| LCD_EXTCOMIN | D6 (J3.7) | P1.07 | GPIO17 (J5.10) | J7.4 |
| LCD_DISP | D8 (J4.1) | P1.10 | GPIO16 (J5.9) | J7.5, R19.1, C7.1 |
| LED_ALARM | D10 (J4.3) | P1.12 | GPIO18 (J5.11) | R1.1 |
| BUZZER | D2 (J3.3) | P1.03 | GPIO15 (J5.8) | R3.1 |
| BTN_UP | D0 (J3.1) | P1.01 | GPIO41 (J6.7) | SW1.1, R5.2 |
| BTN_DOWN | D1 (J3.2) | P1.02 | GPIO40 (J6.8) | SW2.1, R6.2 |
| BTN_OK | SDA (J4.9) | P0.26 | GPIO39 (J6.9) | SW3.1, R7.2 |
| BTN_BACK | SCL (J4.10) | P0.27 | GPIO2 (J6.5) | SW4.1, R8.2 |
| SW_CISZA | D13 (J4.6) | P1.15 | GPIO1 (J6.4) | R16.2, R9.2 |
| BTN_PREP | AREF (J4.8) | P0.02 | GPIO6 (J5.6) | SW6.1, R10.2 |
| VTEST | A4 (J2.5) | P0.30 | GPIO5 (J5.5) | D3.3, R14.2, R15.1, C5.1 |

## Wszystkie sieci

| Sieć | Piny |
|---|---|
| +3V3 | J1.4, U1.3, U1.7, U1.8, JP1.1, JP3.1, R20.1, D3.2, R5.1, R6.1, R7.1, R8.1, R9.1, R10.1, R11.1, C3.1, U2.3, U2.6, L1.1, C8.1 |
| +3V3_DEVKIT | J5.1, J5.2, JP1.2 |
| +3V3_RF | J10.7, J10.9, JP3.2, C1.1, C2.1 |
| +5V | J1.5, JP2.1, R2.1 |
| +5V_DEVKIT | J5.21, JP2.2 |
| +5V_LCD | J7.6, J7.7, J7.8, C4.1, C6.1, U2.5, C9.1, R21.1, C10.1 |
| BST_FB | U2.4, R21.2, R22.1, C10.2 |
| BST_SW | U2.1, L1.2 |
| BTN_BACK | J4.10, J6.5, SW4.1, R8.2 |
| BTN_DOWN | J3.2, J6.8, SW2.1, R6.2 |
| BTN_OK | J4.9, J6.9, SW3.1, R7.2 |
| BTN_PREP | J4.8, J5.6, SW6.1, R10.2 |
| BTN_UP | J3.1, J6.7, SW1.1, R5.2 |
| BUZZER | J3.3, J5.8, R3.1 |
| BZ_N | BZ1.2, D2.2, Q1.3 |
| BZ_P | BZ1.1, R2.2, D2.1 |
| FRAM_CS | J4.2, J5.12, U1.1, J11.6, R20.2 |
| GND | J1.6, J1.7, J4.7, J9.1, J9.19, J10.2, J5.22, J6.1, J6.21, J6.22, J7.9, J7.10, J7.MP, U1.4, J11.1, J12.2, SW1.2, SW2.2, SW3.2, SW4.2, SW5.1, SW6.2, D1.1, Q1.2, R4.2, R19.2, D3.1, R12.2, R13.2, R15.2, C1.2, C2.2, C3.2, C4.2, C6.2, C7.2, C5.2, U2.2, C8.2, C9.2, R22.2 |
| LCD_CS | J3.5, J5.7, J7.3, J11.7, R13.1 |
| LCD_DISP | J4.1, J5.9, J7.5, R19.1, C7.1 |
| LCD_EXTCOMIN | J3.7, J5.10, J7.4 |
| LED_A | D1.2, R1.2 |
| LED_ALARM | J4.3, J5.11, R1.1 |
| Q_B | Q1.1, R3.2, R4.1 |
| RF_CS | J2.2, J9.14, J5.16, J11.5, R11.2 |
| RF_GPIO0 | J2.1, J9.10, J5.20, J11.8 |
| RF_GPIO1 | J2.3, J6.18 |
| RF_GPIO2 | J2.4, J9.12, J5.4, J11.9 |
| RF_GPIO3 | J2.6, J10.18, J6.6 |
| RF_RESET | J3.8, J10.15, J5.15, R12.1 |
| SPI_MISO | J4.5, J9.20, J5.19, U1.2, J11.4 |
| SPI_MOSI | J4.4, J9.18, J5.17, J7.2, U1.5, J11.3 |
| SPI_SCK | J9.16, J7.1, U1.6, J11.2, R17.2, R18.2 |
| SPI_SCK_DEVKIT | J5.18, R18.1 |
| SPI_SCK_DK | J3.4, R17.1 |
| SW_CISZA | J4.6, J6.4, R16.2, R9.2 |
| SW_COM | SW5.2, R16.1 |
| VTEST | J2.5, J5.5, D3.3, R14.2, R15.1, C5.1 |
| VTEST_IN | J12.1, R14.1 |

## Złącza

### J1: ARDUINO POWER

wyprowadzenia od spodu wchodzą w gniazda Arduino nRF52840-DK

| Pin | Sieć |
|---:|---|
| 1 | — |
| 2 | — |
| 3 | — |
| 4 | +3V3 |
| 5 | +5V |
| 6 | GND |
| 7 | GND |
| 8 | — |

### J2: ARDUINO A0-A5

wyprowadzenia od spodu wchodzą w gniazda Arduino nRF52840-DK

| Pin | Sieć |
|---:|---|
| 1 | RF_GPIO0 |
| 2 | RF_CS |
| 3 | RF_GPIO1 |
| 4 | RF_GPIO2 |
| 5 | VTEST |
| 6 | RF_GPIO3 |

### J3: ARDUINO D0-D7

wyprowadzenia od spodu wchodzą w gniazda Arduino nRF52840-DK

| Pin | Sieć |
|---:|---|
| 1 | BTN_UP |
| 2 | BTN_DOWN |
| 3 | BUZZER |
| 4 | SPI_SCK_DK |
| 5 | LCD_CS |
| 6 | — |
| 7 | LCD_EXTCOMIN |
| 8 | RF_RESET |

### J4: ARDUINO D8-SCL

wyprowadzenia od spodu wchodzą w gniazda Arduino nRF52840-DK

| Pin | Sieć |
|---:|---|
| 1 | LCD_DISP |
| 2 | FRAM_CS |
| 3 | LED_ALARM |
| 4 | SPI_MOSI |
| 5 | SPI_MISO |
| 6 | SW_CISZA |
| 7 | GND |
| 8 | BTN_PREP |
| 9 | BTN_OK |
| 10 | BTN_BACK |

### J9: CC1120EM P1

moduł CC1120EM-868-915 wpina się od góry; pin 1 od strony SMA modułu

| Pin | Sieć |
|---:|---|
| 1 | GND |
| 2 | — |
| 3 | — |
| 4 | — |
| 5 | — |
| 6 | — |
| 7 | — |
| 8 | — |
| 9 | — |
| 10 | RF_GPIO0 |
| 11 | — |
| 12 | RF_GPIO2 |
| 13 | — |
| 14 | RF_CS |
| 15 | — |
| 16 | SPI_SCK |
| 17 | — |
| 18 | SPI_MOSI |
| 19 | GND |
| 20 | SPI_MISO |

### J10: CC1120EM P2

moduł CC1120EM-868-915 wpina się od góry; pin 1 od strony SMA modułu

| Pin | Sieć |
|---:|---|
| 1 | — |
| 2 | GND |
| 3 | — |
| 4 | — |
| 5 | — |
| 6 | — |
| 7 | +3V3_RF |
| 8 | — |
| 9 | +3V3_RF |
| 10 | — |
| 11 | — |
| 12 | — |
| 13 | — |
| 14 | — |
| 15 | RF_RESET |
| 16 | — |
| 17 | — |
| 18 | RF_GPIO3 |
| 19 | — |
| 20 | — |

### J5: DEVKITC J1

ESP32-S3-DevKitC-1 wpina się od góry; pin 1 od strony anteny

| Pin | Sieć |
|---:|---|
| 1 | +3V3_DEVKIT (3V3) |
| 2 | +3V3_DEVKIT (3V3) |
| 3 | — (EN) |
| 4 | RF_GPIO2 (GPIO4) |
| 5 | VTEST (GPIO5) |
| 6 | BTN_PREP (GPIO6) |
| 7 | LCD_CS (GPIO7) |
| 8 | BUZZER (GPIO15) |
| 9 | LCD_DISP (GPIO16) |
| 10 | LCD_EXTCOMIN (GPIO17) |
| 11 | LED_ALARM (GPIO18) |
| 12 | FRAM_CS (GPIO8) |
| 13 | — (GPIO3) |
| 14 | — (GPIO46) |
| 15 | RF_RESET (GPIO9) |
| 16 | RF_CS (GPIO10) |
| 17 | SPI_MOSI (GPIO11) |
| 18 | SPI_SCK_DEVKIT (GPIO12) |
| 19 | SPI_MISO (GPIO13) |
| 20 | RF_GPIO0 (GPIO14) |
| 21 | +5V_DEVKIT (5V) |
| 22 | GND (GND) |

### J6: DEVKITC J3

ESP32-S3-DevKitC-1 wpina się od góry; pin 1 od strony anteny

| Pin | Sieć |
|---:|---|
| 1 | GND (GND) |
| 2 | — (GPIO43) |
| 3 | — (GPIO44) |
| 4 | SW_CISZA (GPIO1) |
| 5 | BTN_BACK (GPIO2) |
| 6 | RF_GPIO3 (GPIO42) |
| 7 | BTN_UP (GPIO41) |
| 8 | BTN_DOWN (GPIO40) |
| 9 | BTN_OK (GPIO39) |
| 10 | — (GPIO38) |
| 11 | — (GPIO37) |
| 12 | — (GPIO36) |
| 13 | — (GPIO35) |
| 14 | — (GPIO0) |
| 15 | — (GPIO45) |
| 16 | — (GPIO48) |
| 17 | — (GPIO47) |
| 18 | RF_GPIO1 (GPIO21) |
| 19 | — (GPIO20) |
| 20 | — (GPIO19) |
| 21 | GND (GND) |
| 22 | GND (GND) |

### J7: SHARP LS027B7DH01A

panel Sharp LS027B7DH01A ekranem do góry, taśma FPC płasko; styk 1 panelu (SCLK) na padzie 1 po prawej

| Pin | Sieć |
|---:|---|
| 1 | SPI_SCK |
| 2 | SPI_MOSI |
| 3 | LCD_CS |
| 4 | LCD_EXTCOMIN |
| 5 | LCD_DISP |
| 6 | +5V_LCD |
| 7 | +5V_LCD |
| 8 | +5V_LCD |
| 9 | GND |
| 10 | GND |
| MP | GND (uchwyty mocujące) |

### J11: ANALIZATOR

analizator stanów logicznych (8 kanałów); pin 1 = GND

| Pin | Sieć |
|---:|---|
| 1 | GND |
| 2 | SPI_SCK |
| 3 | SPI_MOSI |
| 4 | SPI_MISO |
| 5 | RF_CS |
| 6 | FRAM_CS |
| 7 | LCD_CS |
| 8 | RF_GPIO0 |
| 9 | RF_GPIO2 |

### JP1: 3V3 DEVKITC

założona tylko w stanowisku B; pomiar prądu 3,3 V

| Pin | Sieć |
|---:|---|
| 1 | +3V3 |
| 2 | +3V3_DEVKIT |

### JP2: 5V DEVKITC

założona tylko w stanowisku B; zasila brzęczyk, pomiar prądu 5 V

| Pin | Sieć |
|---:|---|
| 1 | +5V |
| 2 | +5V_DEVKIT |

### JP3: 3V3 RADIO A

założona w stanowisku A (zasila CC1120EM); amperomierz zamiast zworki mierzy prąd radia (zakres ≥200 mA); poza obrysem X-NUCLEO, bo listwa ze zworką (8,9 mm) sięga spodu nakładki w stanowisku B

| Pin | Sieć |
|---:|---|
| 1 | +3V3 |
| 2 | +3V3_RF |

### J12: VTEST 0-15V

napięcie z zasilacza laboratoryjnego do prób progów ogniw i 12 V; najwyżej 15 V

| Pin | Sieć |
|---:|---|
| 1 | VTEST_IN |
| 2 | GND |


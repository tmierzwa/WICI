# WICI: połączenia płytki v2 (schemat wstępny)

Plik generuje `tools/make_schematic.py` z `tools/design.py`; nie edytować ręcznie. Założenia i otwarte sprawy: [README](README.md).

## Sygnały MCU (ESP32-S3-DevKitC-1 v1.1)

| Sieć | GPIO (złącze.pin) | Rola | Pozostałe piny sieci |
|---|---|---|---|
| SPI_SCK_DEVKIT | GPIO12 (J5.18) | SCK (przez R18 na SPI_SCK) | R18.1 |
| SPI_MOSI | GPIO11 (J5.17) | MOSI | J9.4, J7.2, U1.5 |
| SPI_MISO | GPIO13 (J5.19) | MISO | J9.5, U1.2 |
| RF_CS | GPIO10 (J5.16) | NSS Wio | J8.4, R11.2 |
| RF_RESET | GPIO9 (J5.15) | RESET Wio | J8.3, R12.1 |
| RF_GPIO0 | GPIO14 (J5.20) | BUSY Wio | J8.2 |
| RF_GPIO1 | GPIO21 (J6.18) | DIO1 Wio | J8.1 |
| RF_GPIO3 | GPIO42 (J6.6) | RXEN Wio | J8.5, R64.1 |
| FRAM_CS | GPIO8 (J5.12) | CS FRAM | U4.1, R20.2 |
| LCD_CS | GPIO7 (J5.7) | CS ekranu | J7.3, R13.1 |
| LCD_EXTCOMIN | GPIO17 (J5.10) | EXTCOMIN | J7.4 |
| LCD_DISP | GPIO16 (J5.9) | DISP | J7.5, R19.1, C7.1 |
| LED_ALARM | GPIO18 (J5.11) | dioda alarmu | R1.1 |
| BUZZER | GPIO15 (J5.8) | brzęczyk | R3.1 |
| BTN_UP | GPIO41 (J6.7) | GÓRA | SW1.1, R5.2 |
| BTN_DOWN | GPIO40 (J6.8) | DÓŁ | SW2.1, R6.2 |
| BTN_OK | GPIO39 (J6.9) | OK | SW3.1, R7.2 |
| BTN_BACK | GPIO2 (J6.5) | WSTECZ | SW4.1, R8.2 |
| SW_CISZA | GPIO1 (J6.4) | CISZA | R9.2, R16.2 |
| BTN_PREP | GPIO6 (J5.6) | przygotowanie | SW6.1, R10.2 |
| V_AA_ADC | GPIO4 (J5.4) | nowy: napięcie ogniw (ADC1) | R44.2, R45.1, C34.1, D11.3 |
| V_12_ADC | GPIO5 (J5.5) | nowy: napięcie 12 V (ADC1; dawniej VTEST) | R38.2, R39.1, C33.1, D6.3 |
| DIV_EN | GPIO46 (J5.14) | nowy: klucz dzielnika ogniw | Q7.1, R43.1 |
| PWM_SYNC | GPIO45 (J6.15) | nowy: PWM przetwornicy na czas TX | U7.19, R63.1 |
| PWR_INT | GPIO48 (J6.16) | nowy: INT sterownika przycisku | U6.8, R47.2 |
| KILL_MCU | GPIO47 (J6.17) | nowy: wyłączenie stacji przez KILL (Q11) | Q11.1, R72.1 |
| USB_LAPTOP | GPIO3 (J5.13) | nowy: laptop podłączony (stan niski), wybudzenie z czuwania | Q12.3, R75.2 |
| USB_DP | GPIO20 (J6.19) | nowy: USB D+ do gniazda USB-C | J4.A6, J4.B6, U8.1, U8.6 |
| USB_DN | GPIO19 (J6.20) | nowy: USB D− do gniazda USB-C | J4.A7, J4.B7, U8.3, U8.4 |

## Wszystkie sieci

| Sieć | Piny |
|---|---|
| +3V3 | J5.1, J5.2, JP3.1, R11.1, R75.1, U8.5, U1.3, U1.7, U1.8, U3.2, U4.5, R20.1, C3.1, C11.1, C12.1, C13.1, R5.1, R6.1, R7.1, R8.1, R9.1, R10.1, U2.3, U2.6, L1.1, C8.1, D6.2, D11.2, R47.1, U7.4, C42.1, C43.1, R61.1, R68.2 |
| +3V3_RF | J9.3, JP3.2, C1.1, C2.1 |
| +5V | J7.6, J7.7, J7.8, C4.1, C6.1, R2.1, U2.5, C9.1, R21.1, C10.1 |
| 12V_IN | J2.1, F1.1 |
| BAT_IN | J1.1, R40.1, Q6.2, R41.1 |
| BAT_R | R40.2, D7.2, D8.2 |
| BST_FB | U2.4, R21.2, R22.1, C10.2 |
| BST_SW | U2.1, L1.2 |
| BTN_BACK | J6.5, SW4.1, R8.2 |
| BTN_DOWN | J6.8, SW2.1, R6.2 |
| BTN_OK | J6.9, SW3.1, R7.2 |
| BTN_PREP | J5.6, SW6.1, R10.2 |
| BTN_UP | J6.7, SW1.1, R5.2 |
| BUZZER | J5.8, R3.1 |
| BZ_N | BZ1.2, D2.2, Q1.3 |
| BZ_P | BZ1.1, R2.2, D2.1 |
| CONV_BST1 | U7.16, C44.1 |
| CONV_BST2 | U7.15, C45.1 |
| CONV_CMP1 | C49.2, R67.1 |
| CONV_CMP2 | C51.2, R68.1 |
| CONV_FB | U7.8, R61.2, R62.1, C48.1, C49.1, C51.1 |
| CONV_RT | U7.9, R60.1 |
| CONV_SW1 | U7.18, L2.2, C44.2 |
| CONV_SW2 | U7.3, L2.1, C45.2 |
| CONV_VC | U7.7, C48.2, R67.2 |
| CONV_VCC | U7.12, U7.14, C47.1 |
| DIV_EN | J5.14, Q7.1, R43.1 |
| FRAM_CS | J5.12, U4.1, R20.2 |
| FRAM_CS_U1 | U1.1, U4.4 |
| FRAM_GUARD | U3.1, U4.2 |
| GND | J5.22, J6.1, J6.21, J6.22, J9.2, C1.2, C2.2, R12.2, R64.2, J4.A1, J4.A12, J4.B1, J4.B12, J4.SH, R65.2, R66.2, R74.2, D17.2, Q12.2, U8.2, J7.9, J7.10, J7.MP, R13.2, R19.2, C4.2, C6.2, C7.2, U1.4, U3.3, U4.3, C3.2, C11.2, C12.2, C13.2, SW1.2, SW2.2, SW3.2, SW4.2, SW5.1, SW6.2, D1.1, Q1.2, R4.2, U2.2, C8.2, C9.2, R22.2, J2.2, D4.2, U5.7, C30.2, R31.2, C32.2, Q5.2, R36.2, D15.2, R39.2, C33.2, D6.1, J1.2, Q7.2, R43.2, R45.2, C34.2, D11.1, C35.2, D10.2, C36.2, U6.4, R71.2, C53.2, D13.2, C37.2, J3.2, D16.2, Q11.2, R72.2, Q10.2, R54.2, D14.2, R55.2, C52.2, C50.2, U7.1, U7.5, U7.6, U7.10, U7.11, U7.20, U7.21, C40.2, C41.2, C42.2, C43.2, C46.2, C47.2, R60.2, R62.2, R63.2 |
| KILL_MCU | J6.17, Q11.1, R72.1 |
| LCD_CS | J5.7, J7.3, R13.1 |
| LCD_DISP | J5.9, J7.5, R19.1, C7.1 |
| LCD_EXTCOMIN | J5.10, J7.4 |
| LED_A | D1.2, R1.2 |
| LED_ALARM | J5.11, R1.1 |
| ON | R35.1, Q8.3, R53.1 |
| PWM_SYNC | J6.15, U7.19, R63.1 |
| PWR_ENB | U6.7, R50.2 |
| PWR_INT | J6.16, U6.8, R47.2 |
| PWR_KILL | U6.2, R48.2, D16.1, Q11.3 |
| PWR_ON | U6.1, R70.2, R71.1, C53.1, D13.1 |
| PWR_PB | U6.5, J3.1 |
| PWR_TMR | U6.3, C37.1 |
| Q10_G | Q10.1, R53.2, R54.1, D14.1 |
| Q12_G | R73.2, R74.1, D17.1, Q12.1 |
| Q1_B | Q1.1, R3.2, R4.1 |
| Q4_G | Q4.1, R33.2, D5.2, R34.1 |
| Q5_D | R34.2, Q5.3 |
| Q5_G | Q5.1, R35.2, R36.1, D15.1 |
| Q6_G | Q6.1, R41.2, Q7.3 |
| Q8_G | Q8.1, R49.2, R50.1, D12.2 |
| Q9_G | Q9.1, R51.2, Q10.3 |
| RF_CS | J5.16, J8.4, R11.2 |
| RF_GPIO0 | J5.20, J8.2 |
| RF_GPIO1 | J6.18, J8.1 |
| RF_GPIO3 | J6.6, J8.5, R64.1 |
| RF_RESET | J5.15, J8.3, R12.1 |
| RUN | Q9.3, R55.1, C52.1, U7.2 |
| S12_CAP | U5.11, C31.1 |
| S12_DGATE | U5.1, Q2.4 |
| S12_DVDT | C32.1, R32.2 |
| S12_EN | U5.6, R37.2, R38.1 |
| S12_HGATE | U5.8, Q3.4, R32.1 |
| S12_OV | U5.5, R30.2, R31.1 |
| S12_SW | U5.4, R30.1 |
| SPI_MISO | J5.19, J9.5, U1.2 |
| SPI_MOSI | J5.17, J9.4, J7.2, U1.5 |
| SPI_SCK | R18.2, J9.6, J7.1, U1.6 |
| SPI_SCK_DEVKIT | J5.18, R18.1 |
| SW_CISZA | J6.4, R9.2, R16.2 |
| SW_COM | SW5.2, R16.1 |
| USB_CC1 | J4.A5, R65.1 |
| USB_CC2 | J4.B5, R66.1 |
| USB_DN | J6.20, J4.A7, J4.B7, U8.3, U8.4 |
| USB_DP | J6.19, J4.A6, J4.B6, U8.1, U8.6 |
| USB_LAPTOP | J5.13, Q12.3, R75.2 |
| USB_VBUS | J4.A4, J4.B4, J4.A9, J4.B9, R73.1 |
| V12_F | F1.2, D4.1, U5.2, Q2.1, Q2.2, Q2.3, Q4.2, R33.1, D5.1, R70.1 |
| V12_FLT | D9.2, R46.2, C35.1, D10.1 |
| V12_MID | U5.3, U5.10, U5.12, Q2.5, Q2.6, Q2.7, Q2.8, Q3.5, Q3.6, Q3.7, Q3.8, C30.1, C31.2, R46.1 |
| V12_SW | Q4.3, R37.1 |
| VAA_SW | Q6.3, R44.1 |
| VCTL | D8.1, D9.1, C36.1, U6.6, Q8.2, R49.1, D12.1, R48.1 |
| VSYS | U5.9, Q3.1, Q3.2, Q3.3, D7.1, Q9.2, R51.1, C50.1, U7.13, U7.17, C40.1, C41.1, C46.1 |
| V_12_ADC | J5.5, R38.2, R39.1, C33.1, D6.3 |
| V_AA_ADC | J5.4, R44.2, R45.1, C34.1, D11.3 |

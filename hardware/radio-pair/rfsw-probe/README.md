# Sonda RF_SW1 (`rfsw-0.3`)

Program dla zestawów Seeed 102010611 (XIAO ESP32-S3 + Wio-SX1262). Sprawdza bez przyrządów pomiarowych, jak przełącznik anteny RF_SW1 (GPIO38: wysoki w odbiorze, niski poza nim) wpływa na odbiór. Wynik próby z 2026-10-31 jest w [dowodzie](../evidence/rnode-xiao-2026-10-31.txt).

Po resecie, zanim cokolwiek ustawi, program zapisuje konfigurację GPIO38 z rejestrów ESP32-S3: funkcję, wejście, wyjście i podciąganie. To stan, w jakim pracuje RNode 1.86, który tego pinu nie rusza. Potem czyta stan pinu z wewnętrznym podciąganiem w górę i w dół oraz bez sterowania, 200 ms po stanie wysokim (`fh`) i niskim (`fl`). Odczyt jest ważny tylko po włączeniu zasilania albo po resecie przez USB-Serial-JTAG (przyczyna z ROM 1 albo 21); na macOS ten drugi daje samo otwarcie portu. Przy innej przyczynie skrypt odmawia pomiaru.

Jeden zestaw nadaje co 1 s pakiet z numerem. Drugi w każdym odstępie między pakietami zmienia stan RF_SW1: H (wysoki), RH (jak po resecie), L (niski), RL (jak po resecie). Okna są przypięte do odstępu pakietów, a skrypt sprawdza je z numerami pakietów. Profil jest taki jak w `pair-0.4`: 869,525 MHz, 125 kHz, SF7, CR 4/5, 0 dBm.

Z katalogu `hardware/radio-pair`, z jego `.venv`:

```sh
.venv/bin/pio run -d rfsw-probe --target upload --upload-port PORT_A   # i to samo dla PORT_B
.venv/bin/python rfsw-probe/tools/rfsw_test.py --tx PORT_B --rx PORT_A --notes 'odległość, anteny, przeszkody'
.venv/bin/python rfsw-probe/tools/rfsw_test.py --tx PORT_A --rx PORT_B --notes 'odległość, anteny, przeszkody'
```

Skrypt wypisuje konfigurację GPIO38 i dla każdego stanu liczbę odebranych i brakujących pakietów, błędów CRC i obcych pakietów oraz medianę i zakres RSSI i SNR. Raport JSON z surowymi wierszami zapisuje w `results/`, także gdy próba się nie skończy. Różnica RSSI między L i H to strata odbioru przy linii niskiej; RH i RL pokazują, czy linia bez sterowania trzyma poprzedni stan.

Testy (prawdziwy pyserial przez porty PTY, bez radia): `.venv/bin/python -m unittest discover -s rfsw-probe/tests`.

## Łatka RNode

[`../rnode-xiao-rf-sw1.patch`](../rnode-xiao-rf-sw1.patch) zmienia RNode 1.86 (tag `9b39b6c`) dla tej płytki: `pin_rxen = 38`, linia wysoka tylko w odbiorze, niska w standby, nadawaniu i uśpieniu. Inne płytki bez zmian. Łatka jest na licencji GPL-3.0-or-later, bo zmienia `Boards.h` RNode (GPL-3.0-or-later) oraz `sx126x.cpp` i `sx126x.h` (MIT). Budowa i wgranie: [dowód](../evidence/rnode-xiao-2026-10-31.txt), punkt „Programy”.

# WICI — radio

## Profil P1 do prototypu

To wspólny kontrakt dwóch modemów, a nie ustawienia istniejącego RNode. Zmiana profilu wymaga zmiany całej sieci.

| Parametr | Wartość |
|---|---|
| Nośna | 869,525 MHz |
| Modulacja | 2-GFSK, BT 0,5 |
| Szybkość | 4800 bit/s |
| Dewiacja | ±4 kHz |
| Moc na złączu | 13 dBm, tolerancja po kalibracji ±1 dB |
| Referencja częstotliwości | TCXO; całkowity błąd nadajnika ≤±2,5 ppm w zakresie pracy |
| Filtr RX | najbliższa nastawa 24–32 kHz, zweryfikowana przy krańcowym błędzie częstotliwości |
| Czułość odbioru | cel ≤−110 dBm przy PER ≤1%, mierzony z tym profilem |
| Bajty i bity | kolejność bajtów big endian; MSB pierwszy |
| Preambuła i sync | 8 × 0xAA, potem D3 91 D3 91 |
| Whitening, Manchester, FEC | wyłączone |
| CRC | programowe CRC-16/CCITT-FALSE; sprzętowe CRC wyłączone |
| Rozmiar datagramu z USB | 1–600 B |

4800 bit/s zastępuje wcześniejszy kandydat 1200 bit/s. Daje czterokrotnie większą szybkość surową kosztem czułości. Jeśli próba 1 km nie przejdzie, najpierw zmienia się położenie anten i dodaje przekaźnik. Obniżenie szybkości jest nową wersją profilu, a nie ukrytą lokalną opcją.

## Ramka w eterze

`AA×8 | D391D391 | LEN u8 | BODY | CRC u16`

LEN to długość BODY, 15–100 B. CRC obejmuje LEN i BODY: wielomian 0x1021, inicjalizacja 0xFFFF, brak odbicia, xorout 0. Wynik dla ASCII `123456789`: 0x29B1. BODY:

| Offset | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 1 | wersja ramki = 1 |
| 1 | 1 | flags = 0, inne wartości odrzucane |
| 2 | 8 | losowy identyfikator datagramu |
| 10 | 1 | numer fragmentu, od 0 |
| 11 | 1 | liczba fragmentów, 1–7 |
| 12 | 2 | długość całego datagramu, 1–600 |
| 14 | 1–86 | dane fragmentu |

Liczba fragmentów = ceil(długość/86). Każdy oprócz ostatniego ma 86 B danych. Ostatni ma dokładną resztę. Nie przyjmujemy dowolnego podziału. LEN + BODY + CRC zajmuje najwyżej 103 B; obsługa pakietu mieści się w FIFO 128 B obu kandydatów. Preambułę i synchronizację obsługuje radio. [CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), [S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf).

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu usuwa całą próbę składania. Zmiana długości lub liczby fragmentów również ją usuwa. Po przepełnieniu odrzucana jest najstarsza próba. Komplet dostaje KISS do laptopa. Firmware nie wykonuje ACK, trasowania ani kryptografii; robią to wyższe warstwy.

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisujemy w pamięci nieulotnej dług ciszy równy 12 × zarezerwowany czas TX. Błąd zapisu blokuje TX.
3. Wysyłamy jego fragmenty jako jeden burst. Po nim czekamy zapisany dług ciszy. To około 7,7% aktywności dla powtarzanego ruchu, z rezerwą względem limitu 10%.
4. Po restarcie czekamy cały ostatni zapisany dług. Czyścimy go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed burstem kanał musi pozostawać wolny przez 50 ms; próg początkowy CCA −100 dBm. Kanał zajęty: losowe odroczenie 100–1000 ms. CCA nie zastępuje limitu czasu TX.

Rezerwacja obejmuje preambuły, synchronizację, długości, CRC oraz zmierzony czas rampowania nadajnika. Pamięć to pierścieniowy dziennik EEPROM z numerem, długiem, CRC i znacznikiem zatwierdzenia; co najmniej dwa poprawne rekordy. Kandydaci ST M24C64 i Microchip AT24C64, z odrębnymi parametrami sterownika. Brak poprawnego dziennika blokuje nadawanie do diagnostyki. Odbiór pozostaje czynny.

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10%; do użytkowania w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105).

## USB i Reticulum

USB CDC ACM, zasilanie 5 V, pobór ≤500 mA, przewód do 2 m. USB-C ma osobny rezystor 5,1 kΩ na każdym CC do masy. VID/PID musi zostać legalnie przydzielony projektowi przed wydaniem. Nie kopiujemy identyfikatorów cudzego urządzenia.

KISS DATA = 0x00, READY = 0x0F, FEND = C0, FESC = DB. C0 zamienia się na DB DC, DB na DB DD. Pozostałe komendy nie zmieniają profilu P1. Modem ma kolejkę 4 datagramów; przy pełnej odrzuca nowy datagram i zgłasza licznik odrzutów przez kanał diagnostyczny. Brak potwierdzenia Reticulum powoduje ponowienie; odrzut nie może potwierdzić zgłoszenia mieszkańcowi.

Warstwa `ShelterKISSInterface` jest wymaganym adapterem do przygotowania, ładowanym jako interfejs użytkownika Reticulum. Rozpoznaje modem po kontrakcie diagnostycznym, raportuje efektywną szybkość 240 bit/s, używa READY i czasu oczekiwania 900 s oraz ma ograniczone bufory. Zwykły KISSInterface ma inne założenia czasowe i nie jest automatycznie zgodny z długimi przerwami TX. [Interfejsy użytkownika](https://reticulum.network/manual/interfaces.html), [KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py).

Polecenie diagnostyczne na osobnym interfejsie CDC: `INFO\n`; odpowiedź jedna linia JSON do 256 B: `{"contract":1,"profile":"P1","radio":"CC1120","fw":"...","tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0}`. Drugie CDC usuwa ryzyko pomylenia diagnostyki z ramkami danych. Wariant ST podaje `S2LP`. Aktualizacja firmware nie odbywa się przy uruchamianiu w schronieniu.

## Dwa wykonania

| Funkcja | Modem A | Modem B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LP |
| MCU USB | STM32F103C8 | Microchip SAMD21G18 |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Referencja RF | zgodna z dokumentacją CC1120 | zgodna z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym zasilaniu, 10 µF przy radiu | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz, potem złącze 50 Ω | osobne dopasowanie S2-LP |

Dopasowanie RF i wartości oscylatora są właściwe dla konkretnego układu. Nie wolno skopiować wartości TI na ST. Obie płytki wymagają osobnego layoutu RF i nastaw rejestrów; nie zostały jeszcze narysowane. Wspólna ramka w tym pakiecie zamyka format, lecz nie dowodzi zgodności obu fizycznych modemów.

Dipol pionowy: ramiona początkowo po 82 mm, zasilanie symetryzowane dławikiem prądu wspólnego, kabel 50 Ω. Długość końcowa po strojeniu: SWR ≤2 w zamontowanej pozycji. Budżet swobodnej przestrzeni na 1 km wynosi około 91 dB; straty budynków mogą zużyć cały zapas. Nie wyprowadzamy obietnicy zasięgu z samej czułości katalogowej.

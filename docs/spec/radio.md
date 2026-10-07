# WICI — radio

## Profil P1 do prototypu

To wspólny kontrakt dwóch modemów, a nie ustawienia istniejącego RNode. Zmiana profilu wymaga zmiany całej sieci.

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz |
| Modulacja | 2-GFSK, BT 0,5 |
| Szybkość transmisji | 4800 bit/s |
| Dewiacja | ±4 kHz |
| Moc na złączu | 13 dBm, tolerancja po kalibracji ±1 dB |
| Wzorzec częstotliwości | TCXO; całkowity błąd nadajnika nie większy niż ±2,5 ppm w zakresie pracy |
| Filtr odbiornika | najbliższa nastawa 24–32 kHz, sprawdzona przy granicznym błędzie częstotliwości |
| Czułość odbioru | cel: ≤−110 dBm przy PER ≤1%, mierzona w tym profilu |
| Kolejność bajtów i bitów | najbardziej znaczący bajt pierwszy (big endian); najbardziej znaczący bit pierwszy (MSB) |
| Preambuła i słowo synchronizacji | 8 × 0xAA, następnie D3 91 D3 91 |
| Wybielanie danych, kodowanie Manchester, FEC | wyłączone |
| CRC | programowe CRC-16/CCITT-FALSE; sprzętowe CRC wyłączone |
| Rozmiar datagramu z USB | 1–600 B |

Profil P1 używa 4800 bit/s. Jeśli próba na 1 km zakończy się niepowodzeniem, najpierw zmienia się położenie anten i dodaje przekaźnik. Obniżenie szybkości jest nową wersją profilu, a nie ukrytą lokalną opcją.

## Ramka w eterze

`AA×8 | D391D391 | LEN u8 | BODY | CRC u16`

LEN to długość BODY, 15–100 B. CRC obejmuje LEN i BODY: wielomian 0x1021, wartość początkowa 0xFFFF, bez odwracania bitów, końcowy XOR 0. Wartość kontrolna dla ciągu ASCII `123456789`: 0x29B1. Pola BODY:

| Przesunięcie | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 1 | wersja ramki = 1 |
| 1 | 1 | znaczniki (flags) = 0; inne wartości są odrzucane |
| 2 | 8 | losowy identyfikator datagramu |
| 10 | 1 | numer fragmentu, od 0 |
| 11 | 1 | liczba fragmentów, 1–7 |
| 12 | 2 | długość całego datagramu, 1–600 |
| 14 | 1–86 | dane fragmentu |

Liczba fragmentów = ceil(długość/86). Każdy oprócz ostatniego ma 86 B danych. Ostatni ma dokładną resztę. Nie przyjmujemy dowolnego podziału. LEN, BODY i CRC zajmują łącznie najwyżej 103 B, więc pakiet mieści się w 128-bajtowej kolejce FIFO obu układów. Preambułę i słowo synchronizacji obsługuje układ radiowy. [CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), [S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf).

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu usuwa całą próbę składania. Zmiana długości lub liczby fragmentów również ją usuwa. Po przepełnieniu odrzucana jest najstarsza próba. Kompletny datagram trafia przez KISS do laptopa. Oprogramowanie układowe modemu nie wysyła potwierdzeń, nie wyznacza tras i nie szyfruje; robią to wyższe warstwy.

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisujemy w pamięci nieulotnej dług ciszy równy dwunastokrotności zarezerwowanego czasu nadawania. Błąd zapisu blokuje nadawanie.
3. Fragmenty datagramu wysyłamy jedną serią. Następnie odczekujemy zapisany dług ciszy. Przy ruchu ciągłym daje to około 7,7% czasu nadawania, z rezerwą względem limitu 10%.
4. Po ponownym uruchomieniu odczekujemy cały ostatni zapisany dług. Kasujemy go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed serią kanał musi pozostawać wolny przez 50 ms; początkowy próg CCA wynosi −100 dBm. Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms. CCA nie zastępuje limitu czasu TX.

Rezerwacja obejmuje preambuły, słowa synchronizacji, pola długości, CRC oraz zmierzony czas narastania mocy nadajnika. Pamięć to pierścieniowy dziennik EEPROM z numerem, długiem, CRC i znacznikiem zatwierdzenia; co najmniej dwa poprawne rekordy. Kandydaci: ST M24C64 i Microchip AT24C64, z odrębnymi parametrami sterownika. Brak poprawnego dziennika blokuje nadawanie do czasu diagnostyki. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania CCA; wyłączony jest na czas własnego nadawania oraz wstrzymania USB. Dług ciszy zabrania nadawania, nie odbioru.

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10%; przed użytkowaniem w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105).

## USB i Reticulum

USB CDC ACM, zasilanie 5 V, przewód do 2 m. Pobór prądu całego modemu: przed konfiguracją ≤100 mA, po przyznaniu mocy ≤500 mA i nie więcej, niż deklaruje deskryptor; w stanie wstrzymania (suspend) ≤2,5 mA, łącznie z zegarami, radiem i rezystorem podciągającym. Nadawanie przed konfiguracją i podczas wstrzymania jest zabronione. Odbiór podczas wstrzymania może zostać wyłączony; po wznowieniu (resume) modem wraca do pracy bez zerowania długu ciszy. Wymagane są pomiary prądu udarowego przy podłączeniu i całego cyklu zasilania, także z modułem RF. [USB 2.0](https://www.usb.org/document-library/usb-20-specification), [ECN Suspend Current Limit Changes — kopia dokumentu USB-IF](https://git.nefarius.at/nefarius/USB-Bluetooth-Specs/media/branch/master/usb_20_0702115/Suspend%20Current%20ECN.pdf). Złącze USB-C ma na każdej linii CC osobny rezystor 5,1 kΩ do masy. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem. Nie kopiujemy identyfikatorów cudzego urządzenia.

KISS: DATA = 0x00, READY = 0x0F, FEND = 0xC0, FESC = 0xDB. Bajt 0xC0 w danych zamienia się na 0xDB 0xDC, a 0xDB na 0xDB 0xDD. Pozostałe polecenia nie zmieniają profilu P1. Modem ma kolejkę na 4 datagramy; gdy jest pełna, odrzuca nowy datagram i zgłasza licznik odrzutów przez kanał diagnostyczny. Brak potwierdzenia Reticulum powoduje ponowienie; odrzut nie może potwierdzić zgłoszenia mieszkańcowi.

READY daje zgodę na jedną następną ramkę DATA; nie potwierdza nadania ani zapisu w OSP. Początkowe READY wymaga konfiguracji USB, ważnego dziennika, spłaconego długu ciszy i możliwości przyjęcia datagramu. DATA zużywa zgodę. Następne READY modem wysyła dopiero po zakończeniu serii i odczekaniu ciszy. Powtórzone READY nie mnoży zgód. Kolejka 4 datagramów jest zabezpieczeniem przed nadmiarem danych, nie pozwoleniem na pomijanie READY. Po restarcie adapter usuwa starą zgodę i czeka na nową. Przekroczenie limitu czasu oczekiwania powoduje zgłoszenie błędu; nie odblokowuje nadawania bez READY.

Warstwa `ShelterKISSInterface` jest wymaganym, jeszcze nieprzygotowanym adapterem, ładowanym jako własny interfejs Reticulum (custom interface). Rozpoznaje modem po kontrakcie diagnostycznym, zgłasza efektywną szybkość 240 bit/s, używa READY i czasu oczekiwania 900 s oraz ma ograniczone bufory. Zwykły KISSInterface ma inne założenia czasowe i nie jest automatycznie zgodny z długimi przerwami TX. [Własne interfejsy Reticulum](https://reticulum.network/manual/interfaces.html), [KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py).

Limit 900 s dotyczy adaptera, a nie limitów czasu całego stosu. Wymagane osobne sprawdzenie wyszukiwania trasy, zestawiania linku, przesyłania zasobu i potwierdzeń, także gdy pakiet czeka za ruchem przekazywanym. Samo podanie przepływności 240 bit/s nie przesądza o tej zgodności; [kontrprzykład czasowy i stan przeglądu](../review.md).

Polecenie diagnostyczne na osobnym interfejsie CDC: `INFO\n`; odpowiedź: jeden wiersz JSON do 256 B: `{"contract":1,"profile":"P1","radio":"CC1120","fw":"...","tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0}`. Drugi interfejs CDC usuwa ryzyko pomylenia diagnostyki z ramkami danych. Wariant ST podaje `S2LP`. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

## Dwa wykonania

| Funkcja | Modem A | Modem B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 826–958 MHz |
| MCU USB | ST STM32F103CBT6, jak w kontrolerze R01.3; C8 wymaga odrębnego obrazu 64 KiB | Microchip SAMD21G18 |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Wzorzec częstotliwości RF | zgodny z dokumentacją CC1120 | zgodny z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym wyprowadzeniu zasilania, 10 µF przy układzie radiowym | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz, potem złącze 50 Ω | osobne dopasowanie S2-LP |

Dopasowanie RF i wartości oscylatora są właściwe dla konkretnego układu. Nie wolno przenosić wartości z projektu TI do projektu ST. Obie płytki wymagają osobnego projektu toru RF i nastaw rejestrów; żadna jeszcze nie powstała. Wspólna ramka w tym pakiecie ustala format, lecz nie dowodzi zgodności obu fizycznych modemów.

S2-LPCBQTR obsługuje w górnym paśmie 904–1055 MHz i nie jest kandydatem dla 869,525 MHz. Sama nazwa rodziny S2-LP nie wystarcza przy zamawianiu. [Warianty w karcie katalogowej](https://www.st.com/resource/en/datasheet/s2-lp.pdf).

Dipol pionowy: ramiona początkowo po 82 mm, symetryzacja dławikiem współbieżnym, przewód 50 Ω. Długość końcowa po strojeniu: WFS (SWR) ≤2 w miejscu montażu. Tłumienie swobodnej przestrzeni na 1 km wynosi około 91 dB; straty budynków mogą zużyć cały zapas. Nie wyprowadzamy obietnicy zasięgu z samej czułości katalogowej.

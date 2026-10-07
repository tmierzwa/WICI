# WICI: radio

## Profil P1 do prototypu

P1 jest wspólnym kontraktem dwóch modemów, a nie ustawieniami istniejącego RNode. Zmiana profilu obejmuje całą sieć.

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz |
| Modulacja | 2-GFSK, BT 0,5 |
| Szybkość transmisji | 4800 bit/s |
| Dewiacja | ±4 kHz |
| Moc na złączu | 13 dBm, tolerancja po kalibracji ±1 dB |
| Wzorzec częstotliwości | TCXO; całkowity błąd nadajnika nie większy niż ±2,5 ppm w zakresie temperatur pracy, łącznie ze starzeniem do następnego przeglądu |
| Filtr odbiornika | najbliższa nastawa 24–32 kHz, sprawdzona przy granicznym błędzie częstotliwości |
| Czułość odbioru | cel: ≤−110 dBm przy PER ≤1% dla ramek o maksymalnej długości (103 B), mierzona w tym profilu |
| Kolejność bajtów i bitów | najbardziej znaczący bajt pierwszy (big endian); najbardziej znaczący bit pierwszy (MSB) |
| Preambuła i słowo synchronizacji | 8 × 0xAA, następnie D3 91 D3 91 |
| Wybielanie danych, kodowanie Manchester, FEC | wyłączone |
| CRC | programowe CRC-16/CCITT-FALSE; sprzętowe CRC wyłączone |
| Rozmiar datagramu z USB | 1–600 B |

Jeśli próba na 1 km się nie powiedzie, najpierw zmienia się położenie anten i dodaje przekaźnik. Obniżenie szybkości wymaga nowej wersji profilu; nie może być lokalną opcją.

Indeks modulacji wynosi 2 × 4 kHz / 4,8 kbit/s ≈ 1,67, a pasmo Carsona około 12,8 kHz. Przy błędzie ±2,5 ppm obu stron wzajemne odstrojenie sięga około 4,3 kHz, więc filtr 24–32 kHz zachowuje zapas. Wybielanie danych jest wyłączone, ponieważ większość pakietów Reticulum jest szyfrowana i pseudolosowa. Odporność na długie ciągi jednakowych bitów sprawdza się mimo to ramkami wzorcowymi z samych zer i samych jedynek.

## Współdzielenie kanału

Częstotliwość 869,525 MHz jest środkiem kanału RX2 LoRaWAN w Europie (125 kHz, bramki nadają tam odpowiedzi z mocą do 500 mW ERP) oraz domyślną częstotliwością sieci Meshtastic w regionie EU_868, zajmującej całe podpasmo 869,4–869,65 MHz. Sygnały LoRa mogą mieć poziom poniżej progu CCA, a mimo to zakłócać odbiór ramek P1. Nie można więc zakładać, że kanał jest wolny.

Przed pilotażem w każdym miejscu mierzy się zajętość podpasma w różnych porach doby, a w pracy próbnej zapisuje liczniki CCA i błędów CRC. Jeżeli zajętość pogarsza wynik prób, rozważa się kanał poza zakresem RX2 LoRaWAN (869,4625–869,5875 MHz), np. 869,425 lub 869,625 MHz, z zachowaniem zapasu do krawędzi podpasma na pasmo zajmowane i błąd częstotliwości. Zmiana kanału jest nową wersją P1 dla całej sieci.

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

Liczba fragmentów = ceil(długość/86). Każdy fragment oprócz ostatniego ma 86 B danych, ostatni zawiera resztę. Inny podział jest niedozwolony. LEN, BODY i CRC zajmują łącznie najwyżej 103 B, więc pakiet mieści się w 128-bajtowej kolejce FIFO obu układów. Preambułę i słowo synchronizacji obsługuje układ radiowy ([CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), [S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf)).

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu albo zmiana długości lub liczby fragmentów usuwa całą próbę składania. Po przepełnieniu odrzucana jest najstarsza próba. Kompletny datagram trafia przez KISS do laptopa. CRC-16 nie wykrywa wszystkich przekłamań; uszkodzone pakiety szyfrowane i podpisane odrzuca dodatkowo kontrola integralności Reticulum. Oprogramowanie układowe modemu nie wysyła potwierdzeń, nie wyznacza tras i nie szyfruje; robią to wyższe warstwy.

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisujemy w pamięci nieulotnej dług ciszy równy dwunastokrotności zarezerwowanego czasu nadawania. Błąd zapisu blokuje nadawanie.
3. Fragmenty datagramu wysyłamy jedną serią. Następnie odczekujemy zapisany dług ciszy. Przy ruchu ciągłym daje to około 7,7% czasu nadawania, z rezerwą względem limitu 10%.
4. Po ponownym uruchomieniu odczekujemy cały ostatni zapisany dług. Kasujemy go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed serią kanał musi być wolny przez 50 ms; początkowy próg CCA wynosi −100 dBm. Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms. CCA nie zastępuje limitu czasu TX.

Rezerwacja obejmuje preambuły, słowa synchronizacji, pola długości, CRC oraz zmierzony czas narastania mocy nadajnika. Dług przechowuje pierścieniowy dziennik EEPROM. Każdy rekord zawiera numer, dług, CRC i znacznik zatwierdzenia; dziennik utrzymuje co najmniej dwa poprawne rekordy. W najgorszym przypadku, przy ciągłym nadawaniu najkrótszych datagramów, zapis następuje co 0,65 s, czyli około 133 000 razy na dobę. Pierścień obejmujący wszystkie 256 stron 32-bajtowych pamięci 8 KiB przy trwałości 1 mln cykli wystarcza na około 5 lat takiej pracy. Oprogramowanie układowe musi rozkładać zapisy na cały pierścień. Kandydaci: ST M24C64 i Microchip AT24C64, z odrębnymi parametrami sterownika. Brak poprawnego dziennika blokuje nadawanie do czasu diagnostyki. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania CCA; wyłącza się go na czas własnego nadawania, a podczas wstrzymania USB można go wyłączyć.

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10%; przed użyciem w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. Zestaw przekazywany innym osobom podlega dyrektywie RED 2014/53/UE. Celem kwalifikacji są badania według EN 300 220-2 (widmo radiowe, w tym kategoria odbiornika), EN 301 489-1 i -3 (EMC), EN 62368-1 (bezpieczeństwo) oraz EN 62479 (ekspozycja na pole), a następnie deklaracja zgodności. Tor nadawczy ma filtr dolnoprzepustowy tłumiący harmoniczne (1739 i 2609 MHz) do poziomu emisji niepożądanych wymaganego przez EN 300 220. [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105).

## USB i Reticulum

USB CDC ACM, zasilanie 5 V, przewód do 2 m. Pobór prądu całego modemu: przed konfiguracją ≤100 mA, po przyznaniu mocy ≤500 mA i nie więcej, niż deklaruje deskryptor; w stanie wstrzymania (suspend) ≤2,5 mA, łącznie z zegarami, radiem i rezystorem podciągającym. Nadawanie przed konfiguracją i podczas wstrzymania jest zabronione. Odbiór podczas wstrzymania może zostać wyłączony; po wznowieniu (resume) modem wraca do pracy bez zerowania długu ciszy. Wymagane są pomiary prądu udarowego przy podłączeniu i całego cyklu zasilania, także z modułem RF. [USB 2.0](https://www.usb.org/document-library/usb-20-specification), [ECN Suspend Current Limit Changes (kopia dokumentu USB-IF)](https://git.nefarius.at/nefarius/USB-Bluetooth-Specs/media/branch/master/usb_20_0702115/Suspend%20Current%20ECN.pdf). Złącze USB-C ma na każdej linii CC osobny rezystor 5,1 kΩ do masy. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem; nie wolno używać identyfikatorów cudzego urządzenia.

KISS: DATA = 0x00, READY = 0x0F, FEND = 0xC0, FESC = 0xDB. Bajt 0xC0 w danych zamienia się na 0xDB 0xDC, a 0xDB na 0xDB 0xDD. Pozostałe polecenia nie zmieniają profilu P1. Modem ma kolejkę na 4 datagramy; gdy jest pełna, odrzuca nowy datagram i zgłasza licznik odrzutów przez kanał diagnostyczny. Brak potwierdzenia Reticulum powoduje ponowienie; odrzut nie może potwierdzić zgłoszenia mieszkańcowi.

READY daje zgodę na jedną następną ramkę DATA; nie potwierdza nadania ani zapisu w OSP. Początkowe READY wymaga konfiguracji USB, ważnego dziennika, spłaconego długu ciszy i możliwości przyjęcia datagramu. DATA zużywa zgodę. Następne READY modem wysyła dopiero po zakończeniu serii i odczekaniu ciszy. Powtórzone READY nie mnoży zgód. Kolejka 4 datagramów chroni przed nadmiarem danych i nie zwalnia z czekania na READY. Po restarcie adapter usuwa starą zgodę i czeka na nową. Przekroczenie czasu oczekiwania zgłasza błąd i nie odblokowuje nadawania bez READY.

Warstwa `ShelterKISSInterface` jest wymaganym adapterem, który jeszcze nie powstał. Ładuje się go jako własny interfejs Reticulum (custom interface). Adapter rozpoznaje modem po kontrakcie diagnostycznym, zgłasza efektywną szybkość 240 bit/s, używa READY i czasu oczekiwania 900 s oraz ma ograniczone bufory. Zwykły KISSInterface ma inne założenia czasowe; jego zgodność z długimi przerwami TX nie jest zapewniona. [Własne interfejsy Reticulum](https://reticulum.network/manual/interfaces.html), [KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py).

Limit 900 s dotyczy adaptera, a nie limitów czasu całego stosu. Osobno trzeba sprawdzić wyszukiwanie trasy, zestawianie linku, przesyłanie zasobu i potwierdzenia, także gdy pakiet czeka za ruchem przekazywanym. Samo podanie przepływności 240 bit/s nie przesądza o zgodności; zob. [kontrprzykład czasowy i stan przeglądu](../review.md).

Polecenie diagnostyczne na osobnym interfejsie CDC: `INFO\n`; odpowiedź: jeden wiersz JSON do 256 B: `{"contract":1,"profile":"P1","radio":"CC1120","fw":"...","tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0}`. Wariant ST podaje `S2LP`. Drugi interfejs CDC usuwa ryzyko pomylenia diagnostyki z ramkami danych. Urządzenie złożone z dwoma interfejsami CDC ACM używa deskryptorów IAD (Interface Association Descriptor), aby Windows 10 i nowsze przypisały oba interfejsy wbudowanemu sterownikowi bez instalowania dodatkowego. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

## Dwa wykonania

| Funkcja | Modem A | Modem B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 826–958 MHz |
| MCU USB | ST STM32F103CBT6, jak w kontrolerze R01.3; C8 wymaga odrębnego obrazu 64 KiB | Microchip SAMD21G18 |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Wzorzec częstotliwości RF | zgodny z dokumentacją CC1120 | zgodny z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym wyprowadzeniu zasilania, 10 µF przy układzie radiowym | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz, filtr harmonicznych, ochrona ESD o małej pojemności, potem złącze 50 Ω | osobne dopasowanie S2-LP, te same wymagania filtru i ochrony |

Nadajnik musi przetrwać nadawanie przy rozwartym i zwartym złączu antenowym, ponieważ odłączona lub uszkodzona antena to typowy błąd obsługi w terenie. Dopasowanie RF i wartości oscylatora dotyczą konkretnego układu; nie wolno przenosić ich z projektu TI do projektu ST. Obie płytki wymagają osobnego projektu toru RF i nastaw rejestrów; żadna jeszcze nie powstała. Wspólny format ramki nie dowodzi zgodności obu fizycznych modemów.

S2-LPCBQTR obsługuje w górnym paśmie zakres 904–1055 MHz i nie nadaje się do 869,525 MHz. Przy zamawianiu nie wystarcza sama nazwa rodziny S2-LP ([warianty w karcie katalogowej](https://www.st.com/resource/en/datasheet/s2-lp.pdf)).

Dipol pionowy: ramiona początkowo po 82 mm, symetryzacja dławikiem współbieżnym, przewód 50 Ω o łącznym tłumieniu ≤1 dB przy 869,5 MHz, łącznie ze złączami (np. 2 m LMR-240 lub H-155, około 0,25 dB/m). RG-58 ma przy tej częstotliwości około 0,55 dB/m i z dwoma złączami przekracza warunek już przy 2 m; RG-174 tym bardziej. Przy dłuższym przewodzie do anteny umieszczonej wyżej, np. 10 m LMR-240 (około 2,5 dB), zysk z wysokości zwykle przeważa nad stratą; budżet łącza przelicza się wtedy dla rzeczywistego przewodu. Długość końcowa po strojeniu: WFS (SWR) ≤2 w miejscu montażu. Antena na zewnątrz nie jest montowana ani obsługiwana podczas burzy.

Tłumienie swobodnej przestrzeni na 1 km wynosi około 91 dB, co przy 13 dBm, dwóch dipolach i 1 dB strat przewodu na każdym końcu daje 34 dB zapasu względem −110 dBm. Model Okumury-Haty dla małego lub średniego miasta daje jednak na 1 km 126–133 dB, czyli zapas od −1 dB (antena na 30 m) do −7 dB (antena na 10 m i odbiorca na 1,5 m). Promień pierwszej strefy Fresnela w połowie drogi wynosi około 9,3 m, więc anteny przy oknach niskich kondygnacji pracują zwykle bez widoczności. Cel 1 km w zabudowie wymaga więc wysoko umieszczonych anten lub przekaźników; zysk z większej mocy (do około +16 dBm w obu układach) jest mały. Obliczenia: [wyniki modelu](../../software/reference/wyniki.json). Nie wolno obiecywać zasięgu na podstawie samej czułości katalogowej.

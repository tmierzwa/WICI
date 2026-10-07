# WICI: radio

## Profil P1 do prototypu

P1 jest wspólnym kontraktem dwóch wykonań stacji, a nie ustawieniami istniejącego RNode. Zmiana profilu obejmuje całą sieć. P1 jest wyborem bazowym warunkowym: warunki powrotu do LoRa ustala decyzja D10 przed zamówieniem RF ([koncepcja, rozdział 04](../conception/04-analiza-opcji.html)).

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

Jeśli próba na 1 km się nie powiedzie, najpierw podnosi się antenę (dach, wyższa kondygnacja, z zachowaniem warunków ochrony odgromowej), stosuje antenę kolinearną albo dodaje przekaźnik. Obniżenie szybkości wymaga nowej wersji profilu; nie może być lokalną opcją.

Indeks modulacji wynosi 2 × 4 kHz / 4,8 kbit/s ≈ 1,67, a pasmo Carsona około 12,8 kHz. Przy błędzie ±2,5 ppm obu stron wzajemne odstrojenie sięga około 4,3 kHz, więc filtr 24–32 kHz zachowuje zapas. Wybielanie danych jest wyłączone, ponieważ większość pakietów Reticulum jest szyfrowana i pseudolosowa. Odporność na długie ciągi jednakowych bitów sprawdza się mimo to ramkami wzorcowymi z samych zer i samych jedynek.

## Współdzielenie kanału

Częstotliwość 869,525 MHz jest środkiem kanału RX2 LoRaWAN w Europie (125 kHz, bramki nadają tam odpowiedzi z mocą do 500 mW ERP) oraz domyślną częstotliwością sieci Meshtastic w regionie EU_868, zajmującej całe podpasmo 869,4–869,65 MHz. Sygnały LoRa mogą mieć poziom poniżej progu CCA, a mimo to zakłócać odbiór ramek P1. Nie można więc zakładać, że kanał jest wolny.

Przed pilotażem w każdym miejscu mierzy się zajętość podpasma w różnych porach doby, a w pracy próbnej zapisuje liczniki CCA i błędów CRC. Jeżeli zajętość pogarsza wynik prób, rozważa się kanał poza zakresem RX2 LoRaWAN (869,4625–869,5875 MHz), np. 869,425 lub 869,625 MHz, z zachowaniem zapasu do krawędzi podpasma na pasmo zajmowane i błąd częstotliwości. Zmiana kanału jest nową wersją P1 dla całej sieci (decyzja D11).

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

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu albo zmiana długości lub liczby fragmentów usuwa całą próbę składania. Po przepełnieniu odrzucana jest najstarsza próba. Kompletny datagram trafia do interfejsu Reticulum w oprogramowaniu stacji. CRC-16 nie wykrywa wszystkich przekłamań; uszkodzone pakiety szyfrowane i podpisane odrzuca dodatkowo kontrola integralności Reticulum. Sterownik P1 nie wysyła potwierdzeń, nie wyznacza tras i nie szyfruje; robi to Reticulum w tym samym oprogramowaniu.

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisujemy w pamięci nieulotnej dług ciszy równy dwunastokrotności zarezerwowanego czasu nadawania. Błąd zapisu blokuje nadawanie.
3. Fragmenty datagramu wysyłamy jedną serią. Następnie odczekujemy zapisany dług ciszy. Przy ruchu ciągłym daje to około 7,7% czasu nadawania, z rezerwą względem limitu 10%.
4. Po ponownym uruchomieniu odczekujemy cały ostatni zapisany dług. Kasujemy go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed serią kanał musi być wolny przez 50 ms; początkowy próg CCA wynosi −100 dBm. Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms. CCA nie zastępuje limitu czasu TX.

Rezerwacja obejmuje preambuły, słowa synchronizacji, pola długości, CRC oraz zmierzony czas narastania mocy nadajnika. Dług przechowuje dziennik w pamięci FRAM stacji, tej samej co kolejka zgłoszeń. Każdy rekord zawiera numer, dług, CRC i znacznik zatwierdzenia; dziennik utrzymuje co najmniej dwa poprawne rekordy. W najgorszym przypadku, przy ciągłym nadawaniu najkrótszych datagramów, zapis następuje co 0,65 s, czyli około 133 000 razy na dobę. Trwałość FRAM (co najmniej 10¹³ cykli według kart katalogowych kandydatów) nie ogranicza czasu pracy, więc rozkładanie zapisów nie jest potrzebne. Brak poprawnego dziennika blokuje nadawanie do czasu diagnostyki. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania CCA; wyłącza się go tylko na czas własnego nadawania, bo stacja jest przekaźnikiem.

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10%; przed użyciem w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. Zestaw przekazywany innym osobom podlega dyrektywie RED 2014/53/UE. Nadajniki Wi-Fi i Bluetooth mikrokontrolera stacji są trwale wyłączone w oprogramowaniu układowym; gdyby były czynne, doszłyby badania według EN 300 328. Celem kwalifikacji są badania według EN 300 220-2 (widmo radiowe, w tym kategoria odbiornika), EN 301 489-1 i -3 (EMC), EN 62368-1 (bezpieczeństwo) oraz EN 62479 (ekspozycja na pole), a następnie deklaracja zgodności. Tor nadawczy ma filtr dolnoprzepustowy tłumiący harmoniczne (1739 i 2609 MHz) do poziomu emisji niepożądanych wymaganego przez EN 300 220. [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105).

## Interfejs P1 w stosie Reticulum

Sterownik P1 jest interfejsem Reticulum w oprogramowaniu stacji, opartym na porcie microReticulum ([koncepcja, rozdział 03](../conception/03-dostepne-rozwiazania.html#reticulum-i-lxmf-w-tym-projekcie)). Przyjmuje datagram tylko wtedy, gdy kolejka radiowa na 4 datagramy ma wolne miejsce; inaczej zgłasza stosowi zajętość, a odrzut liczy w diagnostyce. Odrzut nie może potwierdzić zgłoszenia. Stos zna dług ciszy i przewidywany czas oczekiwania kolejki radiowej, więc może je uwzględnić w limitach czasu i ponowieniach. Szybkość efektywną zgłaszaną stosowi ustala się pomiarem w T3; sama wartość nie przesądza o zgodności czasów.

Znajomość długu ciszy nie zmienia limitów czasu całego stosu. Osobno trzeba sprawdzić wyszukiwanie trasy, zestawianie linku, przesyłanie zasobu i potwierdzenia, także gdy pakiet czeka za ruchem przekazywanym; zob. [kontrprzykład czasowy i stan przeglądu](../review.md). Wszystkie stacje sieci, w tym OSP, używają tego samego oprogramowania stacji. Zgodność z implementacją Reticulum i LXMF w Pythonie sprawdza się w T3, bo tylko ona definiuje protokół.

Tryb ciszy radiowej blokuje w sterowniku P1 każde nadawanie, także ruchu przekazywanego. Sterownik ma osobną flagę dla pojedynczego zgłoszenia wyjętego spod ciszy.

## USB do laptopa

USB CDC ACM, przewód do 2 m, złącze USB-C stacji jako urządzenie (rezystory 5,1 kΩ na liniach CC). Stacja jest urządzeniem samozasilanym: nie pobiera zasilania z VBUS i nie podaje na nie napięcia; VBUS służy wyłącznie do wykrycia hosta, a rezystor podciągający linię danych włącza się dopiero przy obecnym VBUS. Wstrzymanie, uśpienie lub odłączenie hosta nie zmienia pracy stacji. Urządzenie ma dwa interfejsy CDC ACM, danych i diagnostyki, z deskryptorami IAD (Interface Association Descriptor), aby Windows 10 i nowsze przypisały oba wbudowanemu sterownikowi bez instalowania dodatkowego. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem; nie wolno używać identyfikatorów cudzego urządzenia. Protokół danych między laptopem a stacją opisuje [specyfikacja oprogramowania](oprogramowanie.md#protokół-usb-laptopstacja).

Polecenie diagnostyczne na interfejsie diagnostyki: `INFO\n`; odpowiedź: jeden wiersz JSON do 256 B: `{"contract":2,"profile":"P1","radio":"CC1120","mcu":"nRF52840","fw":"...","src":"AA","mv":5800,"tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0,"restarts":0}`. Wariant ST podaje `S2LP`, a wariant Espressif `ESP32-S3`. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

## Stanowisko laboratoryjne R01.3

Kontroler [R01.3](../../hardware/radio-test-r01/README.md) (STM32F103 z modułem CC1120) ma za mało pamięci na stos Reticulum i nie jest stacją. Służy jako stanowisko do pomiarów P1 w T4: ramki, czułość, emisje, dług ciszy i próby mieszane TI–ST. Na stanowisku obowiązuje wcześniejszy kontrakt modemu USB:

- USB CDC ACM, zasilanie 5 V z VBUS. Pobór prądu całego modemu: przed konfiguracją ≤100 mA, po przyznaniu mocy ≤500 mA i nie więcej, niż deklaruje deskryptor; w stanie wstrzymania (suspend) ≤2,5 mA, łącznie z zegarami, radiem i rezystorem podciągającym. Nadawanie przed konfiguracją i podczas wstrzymania jest zabronione. [USB 2.0](https://www.usb.org/document-library/usb-20-specification), [ECN Suspend Current Limit Changes (kopia dokumentu USB-IF)](https://git.nefarius.at/nefarius/USB-Bluetooth-Specs/media/branch/master/usb_20_0702115/Suspend%20Current%20ECN.pdf).
- KISS: DATA = 0x00, READY = 0x0F, FEND = 0xC0, FESC = 0xDB. Bajt 0xC0 w danych zamienia się na 0xDB 0xDC, a 0xDB na 0xDB 0xDD. READY daje zgodę na jedną następną ramkę DATA i nie potwierdza nadania. Następne READY modem wysyła dopiero po zakończeniu serii i odczekaniu ciszy. Kolejka 4 datagramów; przy pełnej kolejce nowy datagram jest odrzucany i liczony.
- Dług ciszy w pierścieniowym dzienniku EEPROM (ST M24C64 lub Microchip AT24C64), z zapisami rozłożonymi na wszystkie 256 stron; przy najgorszym ruchu wystarcza na około 5 lat.

Zwykły KISSInterface Reticulum ma limit czasu kontroli przepływu 5 s, krótszy niż cisza P1, więc do prób stosu przez stanowisko potrzebny byłby własny adapter. Nie jest on częścią wydania; próby stosu wykonuje się na stacji. [KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py).

## Dwa wykonania

Dwa wykonania stacji mają wspólny P1, wspólny protokół USB do laptopa i to samo zachowanie ekranu i przycisków, ale różne układy RF i rodziny MCU (W14). Wybór MCU zamyka D14, a ekranu D15.

| Funkcja | Wykonanie A | Wykonanie B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 826–958 MHz |
| MCU stacji | Nordic nRF52840; Bluetooth trwale wyłączony | Espressif ESP32-S3 z pamięcią PSRAM; Wi-Fi i Bluetooth trwale wyłączone |
| Pamięć RAM | 256 KiB na port microReticulum, LXMF, tablicę tras i bufory; zapas sprawdzony w T3 | 512 KiB SRAM i PSRAM; zapas sprawdzony w T3 |
| Pamięć nieulotna | FRAM SPI 2 Mbit: Infineon FM25V20A | FRAM SPI 2 Mbit: Fujitsu MB85RS2MT |
| Ekran | graficzny monochromatyczny z pamięcią obrazu (memory LCD) lub e-papier, cyrylica i piktogramy | wykonanie innego producenta, ten sam układ treści |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Wzorzec częstotliwości RF | zgodny z dokumentacją CC1120 | zgodny z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym wyprowadzeniu zasilania, 10 µF przy układzie radiowym | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz, filtr harmonicznych, ochrona ESD o małej pojemności, potem złącze 50 Ω | osobne dopasowanie S2-LP, te same wymagania filtru i ochrony |

Nadajnik musi przetrwać nadawanie przy rozwartym i zwartym złączu antenowym, ponieważ odłączona lub uszkodzona antena to typowy błąd obsługi w terenie. Dopasowanie RF i wartości oscylatora dotyczą konkretnego układu; nie wolno przenosić ich z projektu TI do projektu ST. Obie płytki wymagają osobnego projektu toru RF i nastaw rejestrów; żadna jeszcze nie powstała. Wspólny format ramki nie dowodzi zgodności obu fizycznych stacji. Do oceny pozostaje filtr pasmowy SAW 868 MHz na wejściu odbiornika, który ogranicza blokowanie przez telefony LTE 800 i GSM 900 ([koncepcja, rozdział 07](../conception/07-zagrozenia-i-odpornosc.html)); jego tłumienie wtrąceniowe obniża czułość i wymaga pomiaru.

S2-LPCBQTR obsługuje w górnym paśmie zakres 904–1055 MHz i nie nadaje się do 869,525 MHz. Przy zamawianiu nie wystarcza sama nazwa rodziny S2-LP ([warianty w karcie katalogowej](https://www.st.com/resource/en/datasheet/s2-lp.pdf)).

Dipol pionowy: ramiona początkowo po 82 mm, symetryzacja dławikiem współbieżnym, przewód 50 Ω o łącznym tłumieniu ≤1 dB przy 869,5 MHz, łącznie ze złączami (np. 2 m LMR-240 lub H-155, około 0,25 dB/m). RG-58 ma przy tej częstotliwości około 0,55 dB/m i z dwoma złączami przekracza warunek już przy 2 m; RG-174 tym bardziej. Przy dłuższym przewodzie do anteny umieszczonej wyżej, np. 10 m LMR-240 (około 2,5 dB), zysk z wysokości zwykle przeważa nad stratą; budżet łącza przelicza się wtedy dla rzeczywistego przewodu. Długość końcowa po strojeniu: WFS (SWR) ≤2 w miejscu montażu. Antena na zewnątrz nie jest montowana ani obsługiwana podczas burzy. Antenę umieszcza się poniżej krawędzi dachu; maszt na szczycie budynku wymaga oceny jego instalacji odgromowej. Ochrona ESD wyjścia RF nie zastępuje ochrony odgromowej.

Wariant anteny: kolinearna antena dookólna o zysku 5–6 dBi, w pionie. Na obu końcach łącza daje około 7 dB więcej niż dwa dipole, bez zmiany P1. ERP rośnie do około 15,5 dBm, nadal poniżej limitu 27 dBm. Kosztem jest węższa wiązka w płaszczyźnie pionowej, więc antena musi stać pionowo i nie nadaje się do łącza o dużej różnicy wysokości na krótkim dystansie. Zysk anteny wpisuje się do raportu próby.

Tłumienie swobodnej przestrzeni na 1 km wynosi około 91 dB, co przy 13 dBm, dwóch dipolach i 1 dB strat przewodu na każdym końcu daje 34 dB zapasu względem −110 dBm. Model Okumury-Haty dla małego miasta daje jednak na 1 km 126–133 dB, czyli zapas około −0,7 dB (antena na 30 m), −3,5 dB (anteny na 10 m i 3 m) i −7,3 dB (anteny na 10 m i 1,5 m). To wartości medianowe: łącze, które ma przenieść 99 ze 100 zgłoszeń, potrzebuje dodatkowo około 10 dB zapasu na zaniki, a rozrzut tłumienia między miejscami sięga 6–8 dB. Promień pierwszej strefy Fresnela w połowie drogi wynosi około 9,3 m, więc anteny przy oknach niskich kondygnacji pracują zwykle bez widoczności. Cel 1 km w zabudowie wymaga więc wysoko umieszczonych anten lub przekaźników; zysk z większej mocy (do około +16 dBm w obu układach) jest mały. Z dipolami ERP wynosi około 12 dBm (16 mW), około 15 dB poniżej limitu 500 mW; większa moc wymaga zewnętrznego wzmacniacza, nowej konstrukcji RF, pomiaru emisji i nowego budżetu energii stacji. Obliczenia: [wyniki modelu](../../software/reference/wyniki.json). Nie wolno obiecywać zasięgu na podstawie samej czułości katalogowej.

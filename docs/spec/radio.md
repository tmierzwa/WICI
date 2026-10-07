# WICI: radio

## Profil P1 do prototypu

P1 jest wspólnym kontraktem dwóch wykonań stacji, a nie ustawieniami istniejącego RNode. Zmiana profilu obejmuje całą sieć. P1 jest wyborem bazowym, ale warunkowym: warunki powrotu do LoRa ustala decyzja D10 przed zamówieniem RF ([koncepcja, rozdział 04](../concept/04-analiza-opcji.html)).

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz |
| Modulacja | 2-GFSK, BT 0,5 |
| Szybkość transmisji | 4800 bit/s |
| Dewiacja | ±4 kHz |
| Moc na złączu | 13 dBm, tolerancja po kalibracji ±1 dB |
| Wzorzec częstotliwości | TCXO ±0,5 ppm w zakresie temperatur, starzenie w pierwszym roku ≤±1 ppm, określony co najmniej dla −20…+55 °C (zapas nad celem stacji −20…+45 °C). Budżet błędu nadajnika do następnego pomiaru: temperatura ±0,5 + kalibracja ±0,3 + zasilanie i obciążenie ±0,2 + starzenie ±1,0 = ±2,0 ppm (około ±1,7 kHz), z zapasem do granicy ±2,5 ppm. Pomiar i korekta częstotliwości przy produkcji i w każdym corocznym przeglądzie technicznym, przyrządem o dokładności ≤0,1 ppm, przez producenta lub serwis; w dniu przeglądu stacje dowozi się do jednego miejsca (około 20 min na stację) |
| Filtr odbiornika | najbliższa nastawa 24–32 kHz, sprawdzona przy granicznym błędzie częstotliwości |
| Czułość odbioru | cel: ≤−110 dBm na złączu antenowym stacji, z pełnym torem wejściowym (SAW lub filtr, ESD, przełącznik RF), przy PER ≤1% dla ramek o maksymalnej długości (103 B), mierzona w tym profilu. Przy około 3 dB strat toru wejściowego układ radiowy musi osiągać około −113 dBm; do wyniku T4 cel jest zagrożony i stanowi wejście do D10 |
| Kolejność bajtów i bitów | najbardziej znaczący bajt pierwszy (big endian); najbardziej znaczący bit pierwszy (MSB) |
| Preambuła i słowo synchronizacji | 8 × 0xAA, następnie D3 91 D3 91 |
| Wybielanie danych, kodowanie Manchester, FEC | wyłączone |
| CRC | programowe CRC-16/CCITT-FALSE; sprzętowe CRC wyłączone |
| Rozmiar datagramu (z interfejsu Reticulum w stacji) | 1–600 B; HW_MTU interfejsu 500 B plus kod dostępu IFAC; autokonfiguracja MTU linku wyłączona |
| Maksymalny deklarowany zysk anteny | 6 dBi; wpisywany do deklaracji zgodności i karty stacji |

Jeśli próba na 1 km się nie powiedzie, najpierw podnosi się antenę (dach, wyższa kondygnacja, z zachowaniem warunków ochrony odgromowej), stosuje antenę kolinearną albo dodaje przekaźnik. Obniżenie szybkości wymaga nowej wersji profilu; nie może być lokalną opcją.

Indeks modulacji wynosi 2 × 4 kHz / 4,8 kbit/s ≈ 1,67, a pasmo Carsona około 12,8 kHz. Przy błędzie ±2,5 ppm obu stron wzajemne odstrojenie sięga około 4,3 kHz, więc filtr 24–32 kHz zachowuje zapas. Wybielanie danych jest wyłączone, ponieważ większość pakietów Reticulum jest szyfrowana i pseudolosowa. Odporność na długie ciągi jednakowych bitów sprawdza się mimo to ramkami wzorcowymi z samych zer i samych jedynek.

## Współdzielenie kanału

Częstotliwość 869,525 MHz jest środkiem kanału RX2 LoRaWAN w Europie (125 kHz, bramki nadają tam odpowiedzi z mocą do 500 mW ERP) oraz domyślną częstotliwością sieci Meshtastic w regionie EU_868, zajmującej całe podpasmo 869,4–869,65 MHz. Sygnały LoRa mogą mieć poziom poniżej progu CCA, a mimo to zakłócać odbiór ramek P1. Nie można więc zakładać, że kanał jest wolny. Pobliska bramka LoRaWAN (do 27 dBm ERP) może w promieniu setek metrów blokować odbiornik stacji i stale zajmować CCA; T5 obejmuje pomiar RSSI tła i blokowania w pobliżu znanej bramki.

Przed pilotażem w każdym miejscu mierzy się zajętość podpasma w różnych porach doby, a w pracy próbnej zapisuje liczniki CCA i błędów CRC. Jeżeli zajętość pogarsza wynik prób, rozważa się kanał poza zakresem RX2 LoRaWAN (869,4625–869,5875 MHz), np. 869,425 lub 869,625 MHz, z zachowaniem zapasu do krawędzi podpasma na pasmo zajmowane i błąd częstotliwości. Zmiana kanału jest nową wersją P1 dla całej sieci (decyzja D11).

## Ramka w eterze

`AA×8 | D391D391 | LEN u8 | BODY | CRC u16`

LEN to liczba bajtów po nim, czyli BODY i CRC łącznie, 17–102 B (zmiana z F79: wcześniej LEN liczył tylko BODY). Silniki pakietów CC1120 i S2-LP w trybie zmiennej długości odbierają po LEN dokładnie tyle bajtów, więc CRC trafia do kolejki układu razem z BODY. CRC liczy oprogramowanie stacji, nie układ radiowy, bo oba układy mają inną wartość początkową CRC. CRC obejmuje LEN i BODY: wielomian 0x1021, wartość początkowa 0xFFFF, bez odwracania bitów, końcowy XOR 0. Wartość kontrolna dla ciągu ASCII `123456789`: 0x29B1. Pola BODY:

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

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu albo zmiana długości lub liczby fragmentów usuwa całą próbę składania. Po przepełnieniu odrzucana jest próba z najmniejszą liczbą odebranych fragmentów. Ramka P1 w wersji 1 nie niesie adresu nadawcy, więc limitu prób składania na nadawcę nie da się w niej wyegzekwować; przed zalewem fragmentami chroni tylko limit 8 prób i zasada usuwania próby z najmniejszą liczbą fragmentów. Pole nadawcy (np. 2 B skrótu tożsamości) wymaga wersji ramki 2 dla całej sieci; decyzję o nim podejmuje się po próbie „wrogi węzeł” w T3, ale przed zamówieniem płytek R02, póki nie ma stacji w terenie. Pamięć identyfikatorów ostatnio złożonych datagramów odrzuca spóźnione duplikaty fragmentów. Kompletny datagram trafia do interfejsu Reticulum w oprogramowaniu stacji. CRC-16 nie wykrywa wszystkich przekłamań; uszkodzone pakiety szyfrowane i podpisane odrzuca dodatkowo kontrola integralności Reticulum. Sterownik P1 nie wysyła potwierdzeń, nie wyznacza tras i nie szyfruje; robi to Reticulum w tym samym oprogramowaniu.

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisuje się w pamięci nieulotnej dług ciszy równy dwunastokrotności zarezerwowanego czasu nadawania. Błąd zapisu blokuje nadawanie.
3. Fragmenty datagramu wysyła się jedną serią. Następnie odczekuje się zapisany dług ciszy. Przy ruchu ciągłym daje to około 7,7% czasu nadawania, z rezerwą względem limitu 10%.
4. Po ponownym uruchomieniu odczekuje się cały ostatni zapisany dług. Kasuje się go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed serią kanał musi być wolny przez 50 ms; kanał jest zajęty, gdy RSSI przekracza próg CCA albo trwa odbiór po wykryciu słowa synchronizacji. Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms; licznik długich odroczeń trafia do diagnostyki. CCA nie zastępuje limitu czasu TX. Początkowy próg −100 dBm leży 10 dB powyżej czułości −110 dBm, więc słabsi sąsiedzi pozostają dla CCA niewidoczni (ukryte węzły); próg wyznacza się w T4.
6. Co najmniej 50% budżetu TX jest zarezerwowane dla ruchu do i od przypiętej OSP. Ogłoszenia i zapytania o trasę mają na interfejsie osobne limity częstości (ogłoszenia początkowo 2% czasu nadawania; [ogłoszenia](oprogramowanie.md#tryby-kryzysowe)). W kolejce P1 zapytania o trasę idą razem z potwierdzeniami pakietów przed danymi, bo bez trasy dane nie wyjdą; ogłoszenia mają najniższy priorytet ([kolejność w kolejce](oprogramowanie.md#trwałość-i-potwierdzenia)).

Rezerwacja obejmuje preambuły, słowa synchronizacji, pola długości, CRC oraz zmierzony czas narastania mocy i przełączenia nadajnika dla każdego fragmentu; model przyjmuje go jako parametr (`ramp_ms`), a dowód limitu 10% opiera się na wartości zmierzonej. Dług zapisuje się przed pierwszym fragmentem serii; zachowanie przy zaniku zasilania w trakcie zapisu sprawdza się z kondensatorem podtrzymania i komparatorem zaniku ([elektronika](elektronika.md#zasilanie-stacji)). Dług przechowuje dziennik w pamięci FRAM stacji, tej samej co kolejka zgłoszeń. Każdy rekord zawiera numer, dług, CRC i znacznik zatwierdzenia; dziennik utrzymuje co najmniej dwa poprawne rekordy. W najgorszym przypadku, przy ciągłym nadawaniu najkrótszych datagramów, zapis następuje co 0,65 s, czyli około 133 000 razy na dobę. Trwałość FRAM (co najmniej 10¹³ cykli według kart katalogowych kandydatów) nie ogranicza czasu pracy, więc rozkładanie zapisów nie jest potrzebne. Dziennik długu ciszy nie jest szyfrowany i przetrwa ZNISZCZ DANE. Gdy przy starcie brak poprawnego rekordu, stacja odczekuje największy możliwy dług (12 × czas TX datagramu 600 B z narastaniem mocy; około 16 s przy założonych 2 ms na fragment, do potwierdzenia pomiarem w T4), zakłada nowy dziennik i zlicza zdarzenie w diagnostyce; nie blokuje nadawania do czasu diagnostyki. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania CCA; wyłącza się go tylko na czas własnego nadawania, bo stacja jest przekaźnikiem.

## Warunki prawne i zgodność

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10% (pasmo h1.4 według ERC/REC 70-03, [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105)); przed użyciem w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. Zestaw przekazywany innym osobom podlega dyrektywie RED 2014/53/UE. Gmina może używać stacji wyłącznie jako produktów z deklaracją zgodności UE wystawioną przez producenta; samodzielne złożenie stacji przez gminę lub wolontariuszy czyni ich producentem ze wszystkimi obowiązkami.

Wykaz do kwalifikacji i deklaracji zgodności:

- EN 300 220-2 w aktualnej wersji: widmo radiowe; cel: kategoria odbiornika 1,5. T4 mierzy blokowanie i selektywność kanału sąsiedniego na poziomach tej kategorii oraz czułość przy PER ≤1% w obecności CW −30 dBm na 862 i 880 MHz (poziom do potwierdzenia wobec telefonu w odległości 1 m);
- EN 301 489-1 i -3: kompatybilność elektromagnetyczna;
- EN 62368-1: bezpieczeństwo; EN 62479: ekspozycja na pole;
- rozporządzenie delegowane (UE) 2022/30 i normy zharmonizowane EN 18031-1 i -2:2024 (art. 3 ust. 3 lit. d i e RED, cyberbezpieczeństwo), stosowane od 1 sierpnia 2025; normy opublikowano decyzją wykonawczą (UE) 2025/138 z ograniczeniami w załączniku I;
- RoHS (EN IEC 63000), WEEE (dla wszystkich modułów zestawu) oraz rozporządzenie bateryjne (UE) 2023/1542;
- maksymalny deklarowany zysk anteny 6 dBi, wpisany do deklaracji i karty stacji.

Nadajniki Wi-Fi i Bluetooth mikrokontrolera stacji są wyłączone, ale radio 2,4 GHz wyłączone tylko w oprogramowaniu układowym może być nadal traktowane jako zamierzony nadajnik. Opcje do rozstrzygnięcia w D14: (a) trwała blokada (eFuse lub konfiguracja startowa, gdzie MCU ją zapewnia), bezpieczny rozruch (secure boot) i pisemna argumentacja RED; (b) budżet badań według EN 300 328 i EN 301 489-17; (c) MCU bez radia, np. RP2350 (520 KiB RAM) albo STM32U5.

Moduły poziomu 3 bez nadajnika (przetwornica 230 V, ładowarka) podlegają dyrektywom LVD 2014/35/UE i EMC 2014/30/UE; normy ustala jednostka badawcza ([elektronika](elektronika.md#przetwornica-poziom-3)).

Tor nadawczy musi tłumić harmoniczne (1739 i 2609 MHz) do poziomu emisji niepożądanych wymaganego przez EN 300 220. Dla toru według referencji TI zmierzyć 2. i 3. harmoniczną; dodatkowy filtr dolnoprzepustowy tylko przy przekroczeniu. Płytka S2-LP ma filtr harmonicznych jako wymaganie.

## Interfejs P1 w stosie Reticulum

Sterownik P1 jest interfejsem Reticulum w oprogramowaniu stacji, opartym na porcie microReticulum ([koncepcja, rozdział 03](../concept/03-dostepne-rozwiazania.html#reticulum-i-lxmf-w-tym-projekcie)). Przyjmuje datagram tylko wtedy, gdy kolejka radiowa na 4 datagramy ma wolne miejsce; inaczej zgłasza stosowi zajętość, a odrzut liczy w diagnostyce. Odrzut nie może potwierdzić zgłoszenia. Stos zna dług ciszy i przewidywany czas oczekiwania kolejki radiowej i musi je uwzględnić w limitach czasu i ponowieniach. Dla wiadomości okazjonalnych LXMF odstęp ponowienia wynosi co najmniej max(60 s, 2 × liczba skoków × 13 × czas TX największego datagramu + bieżący dług ciszy + czas opróżnienia kolejki P1); na jedno ponowienie intencji przypadają najwyżej 2 próby LXMF. Na pustej sieci potwierdzenie przez jeden przekaźnik wraca najwcześniej po około 13–15 s, a domyślne ponowienie LXMF po 10 s podwajałoby ruch i łamało W10. W modelu odstęp wynosi 60 s dla 1 i 2 skoków na pustej sieci oraz około 115 s (1 skok) i 144 s (2 skoki) przy największym długu i pełnej kolejce 4 × 600 B ([wyniki modelu](../../software/reference/wyniki.json)).

Interfejs deklaruje stosowi jawną przepływność (wartość wyznacza się pomiarem w T3; sama wartość nie przesądza o zgodności czasów) i osobny limit ogłoszeń. Każdy pakiet na interfejsie P1 niesie kod dostępu sieci (IFAC Reticulum, 16 B) ustawiany przy przygotowaniu; pakiety bez poprawnego kodu są odrzucane przed przetwarzaniem. Zgodność IFAC w microReticulum potwierdza T3. Próba „wrogi węzeł” (zalew ogłoszeniami, zapytaniami o trasę i fragmentami) należy do T3 i T5.

Znajomość długu ciszy nie zmienia limitów czasu całego stosu. Osobno trzeba sprawdzić wyszukiwanie trasy, zestawianie linku, przesyłanie zasobu i potwierdzenia, także gdy pakiet czeka za ruchem przekazywanym; zob. [kontrprzykład czasowy i stan przeglądu](../review.md). Wszystkie stacje sieci, w tym OSP, używają tego samego oprogramowania stacji. Zgodność z implementacją Reticulum i LXMF w Pythonie sprawdza się w T3, bo to implementacja w Pythonie definiuje protokół.

Tryb ciszy radiowej blokuje w sterowniku P1 każde nadawanie, także ruchu przekazywanego. Sterownik ma osobną flagę dla pojedynczego zgłoszenia wyjętego spod ciszy.

## USB do laptopa

USB CDC ACM, przewód do 2 m, złącze USB-C stacji jako urządzenie (rezystory 5,1 kΩ na liniach CC). Stacja jest urządzeniem samozasilanym: nie zasila się z VBUS (VSYS niezależne od VBUS) ani nie podaje napięcia na VBUS. Wykonanie A pobiera z VBUS tylko prąd PHY USB nRF52840, około 2,5 mA; w wykonaniu B VBUS służy wyłącznie do wykrycia hosta. Rezystor podciągający linię danych włącza się dopiero przy obecnym VBUS. Wstrzymanie, uśpienie lub odłączenie hosta nie zmienia pracy stacji. Urządzenie ma dwa interfejsy CDC ACM, danych i diagnostyki (w ESP32-S3 przez USB-OTG i TinyUSB, nie USB-Serial-JTAG), z deskryptorami IAD (Interface Association Descriptor), aby Windows 10 i nowsze przypisały oba wbudowanemu sterownikowi bez instalowania dodatkowego. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem; nie wolno używać identyfikatorów cudzego urządzenia. Protokół danych między laptopem a stacją opisuje [specyfikacja oprogramowania](oprogramowanie.md#protokół-usb-laptopstacja).

Polecenie diagnostyczne na interfejsie diagnostyki: `INFO\n`; odpowiedź: jeden wiersz JSON do 256 B: `{"contract":2,"profile":"P1","radio":"CC1120","mcu":"nRF52840","fw":"...","src":"AA","mv":5800,"tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0,"restarts":0}`. Wariant ST podaje `S2LP`, a wariant Espressif `ESP32-S3`. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

Polecenia pomiarowe na interfejsie diagnostyki działają wyłącznie w trybie przygotowania i służą próbom T4 na [stanowisku deweloperskim](../../hardware/dev-bench/README.md) i na R02: `TXCW <s>` nadaje nośną bez modulacji przez ≤10 s (pomiar częstotliwości i mocy); `TXPKT <n> <len> [<ms>]` nadaje `n` ramek o długości `len` B z numerem porządkowym w treści i odstępem `ms`; `RXPER` zwraca i zeruje liczniki ramek odebranych, z błędem CRC i brakujących numerów; `FOFF <Hz>` ustawia korektę częstotliwości do restartu. Odpowiedź: jeden wiersz JSON. Limit czasu nadawania i cisza radiowa obowiązują także dla tych poleceń; serię dłuższą niż limit dopuszcza tylko argument `conducted`, przeznaczony wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego, potwierdzony przyciskiem OK na stacji w ciągu 30 s i zapisany w dzienniku zdarzeń.

## Stanowisko deweloperskie

Próby T1–T4 przed płytką R02 wykonuje się na [stanowisku deweloperskim](../../hardware/dev-bench/README.md): płytki rozwojowe obu rodzin MCU (nRF52840-DK, ESP32-S3-DevKitC-1) z modułami radiowymi producentów (TI CC1120EM-868-915; ST X-NUCLEO-S2868A2 albo płytka z zestawu STEVAL-FKI868V2), pamięć FRAM i ekran na modułach Adafruit, połączone [płytką nośną N1](../../hardware/dev-bench/plytka-nosna.md) bez własnego toru RF, wzorca częstotliwości i stabilizatora, uruchamiające oprogramowanie układowe stacji. Płytką stacji jest R02; N1 jest narzędziem stanowiska. Kontroler R01.3 (STM32F103 z modułem CC1120) miał za mało pamięci na stos Reticulum i nie był stacją; został wycofany, a jego ustalenia są w [lekcjach projektu R02](../../hardware/r02/lekcje.md). Wcześniejszy kontrakt modemu USB/KISS nie obowiązuje: zwykły KISSInterface Reticulum ma limit czasu kontroli przepływu 5 s, krótszy niż cisza P1, a próby stosu wykonuje się bezpośrednio na stanowisku i na stacji ([KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py)).

Wyniki czułości i emisji ze stanowiska dotyczą toru RF producenta bez toru wejściowego stacji; wynik na złączu stacji z pełnym torem daje dopiero R02. Wzorzec częstotliwości modułów nie spełnia budżetu P1, więc na stanowisku błąd częstotliwości mierzy się i koryguje poleceniem `FOFF`, a budżet z TCXO sprawdza się na R02. Nastawy rejestrów CC1120 dla P1 (częstotliwość, szybkość, dewiacja, filtr 25 kHz, moc, preambuła i słowo synchronizacji) są w [oprogramowaniu stanowiska](../../firmware/README.md#rejestry-profilu-p1) jako tablica generowana ze wzorów instrukcji układu i z eksportu SmartRF Studio; pole LEN ramki liczy BODY i CRC, więc pasuje do silnika pakietów obu układów ([przegląd, F79](../review.md)).

## Dwa wykonania

Dwa wykonania stacji mają wspólny P1, wspólny protokół USB do laptopa i to samo zachowanie ekranu i przycisków, ale różne układy RF i rodziny MCU (W14). Wybór MCU zamyka D14, a ekranu D15.

| Funkcja | Wykonanie A | Wykonanie B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 413–479 i 826–958 MHz |
| MCU stacji | Nordic nRF52840; Bluetooth wyłączony, sposób trwałego wyłączenia i argumentacja RED w D14 | Espressif ESP32-S3 z pamięcią PSRAM; Wi-Fi i Bluetooth wyłączone, sposób trwałego wyłączenia i argumentacja RED w D14 |
| Pamięć RAM | ≥256 KiB na port microReticulum, LXMF, tablicę tras i bufory; nRF52840 ma 256 KiB, czyli jest na granicy szacowanego zapotrzebowania, więc wymagany zmierzony zapas ≥30% w T3, przed projektem płytki R02; wariant zapasowy z większą pamięcią: nRF5340 (rdzeń aplikacyjny 512 KiB), RP2350 lub STM32U5 (D14) | 512 KiB SRAM i PSRAM; zmierzony zapas ≥30% w T3 |
| Pamięć nieulotna | FRAM SPI 4 Mbit we wszystkich stacjach, także OSP ([pamięć według roli](oprogramowanie.md#trwałość-i-potwierdzenia)): Infineon CY15B104Q (rodzina 4 Mbit; wariant i status do potwierdzenia przed R02); rekordy szyfrowane | FRAM SPI 4 Mbit: RAMXEED (dawniej Fujitsu) MB85RS4MT (wariant i status do potwierdzenia przed R02); rekordy szyfrowane |
| Ekran | graficzny monochromatyczny z pamięcią obrazu (memory LCD) lub e-papier, cyrylica i piktogramy | wykonanie innego producenta, ten sam układ treści |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Wzorzec częstotliwości RF | zgodny z dokumentacją CC1120 | zgodny z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym wyprowadzeniu zasilania, 10 µF przy układzie radiowym | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz; filtr harmonicznych według wyniku pomiaru; ochrona ESD o małej pojemności, potem złącze SMA-F 50 Ω | osobne dopasowanie S2-LP z filtrem harmonicznych, ta sama ochrona i złącze |

Nadajnik musi przetrwać nadawanie przy rozwartym i zwartym złączu antenowym, ponieważ odłączona lub uszkodzona antena to typowy błąd obsługi w terenie. Dopasowanie RF i wartości oscylatora dotyczą konkretnego układu; nie wolno przenosić ich z projektu TI do projektu ST. Obie płytki wymagają osobnego projektu toru RF i nastaw rejestrów; żadna jeszcze nie powstała. Wspólny format ramki nie dowodzi zgodności obu fizycznych stacji. Do oceny pozostaje filtr pasmowy SAW 868 MHz, który ogranicza blokowanie przez telefony LTE 800 i GSM 900 ([koncepcja, rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)). W topologiach referencyjnych TI i ST nadajnik i odbiornik mają wspólny węzeł RF, więc filtru nie da się umieścić „na wejściu odbiornika” bez przełącznika. Do rozstrzygnięcia przy R02: (a) osobna ścieżka odbiorcza przez przełącznik RF SPDT, z filtrem SAW tylko w torze RX; (b) filtr SAW we wspólnym torze, o wytrzymałości ≥+20 dBm, dopuszczalny tylko wtedy, gdy strata całego toru nadawczego wynosi ≤1,5 dB; inaczej wariant (a). Wymagania filtru: pasmo 869,4–869,65 MHz z zapasem na temperaturę, strata ≤2,5 dB w −20…+45 °C, tłumienie ≥20 dB przy 862 MHz i ≥30 dB przy 880–915 MHz. W obu wariantach strata wtrąceniowa wchodzi do czułości na złączu i wymaga pomiaru. Prąd TX w modelu energii liczy się dla mocy na wyjściu układu (13 dBm plus strata toru do złącza), nie dla mocy na złączu.

Tryb nasłuchu z próbkowaniem (RX sniff) CC1120 zmniejszyłby pobór w odbiorze, ale wymaga dłuższej preambuły niż w P1. Jeżeli W23 nie zostanie spełnione, możliwa jest przyszła wersja P1 z dłuższą preambułą; zmiana obejmuje całą sieć.

S2-LPCBQTR obsługuje w górnym paśmie zakres 904–1055 MHz i nie nadaje się do 869,525 MHz. Przy zamawianiu nie wystarcza sama nazwa rodziny S2-LP ([warianty w karcie katalogowej](https://www.st.com/resource/en/datasheet/s2-lp.pdf)).

Dipol pionowy: ramiona początkowo po 82 mm, symetryzacja dławikiem współbieżnym, przewód 50 Ω o łącznym tłumieniu ≤1 dB przy 869,5 MHz, łącznie ze złączami (np. 2 m LMR-240 lub H-155, około 0,25 dB/m). RG-58 ma przy tej częstotliwości około 0,55 dB/m i z dwoma złączami przekracza warunek już przy 2 m; RG-174 tym bardziej. Przy dłuższym przewodzie do anteny umieszczonej wyżej zysk z wysokości zwykle przeważa nad stratą; budżet łącza przelicza się wtedy dla rzeczywistej instalacji: przewód zewnętrzny, odgromnik GDT (≤0,2 dB), przepust, przejściówki (≤0,1 dB każda) i przewód wewnętrzny. Model przyjmuje dla instalacji stałej 2,5 dB na każdym końcu (np. około 6 m LMR-240 z odgromnikiem i przejściami), obok 1 dB dla anteny przy oknie bez odgromnika. Długość końcowa po strojeniu: WFS (SWR) ≤2 w miejscu montażu. Antena zewnętrzna jest zwarta dla prądu stałego (dipol pętlowy albo dipol ze zwierającym odcinkiem ćwierćfalowym), a przewód przy wejściu do budynku ma odgromnik gazowy (GDT) ze złączami N lub SMA, połączony z uziemieniem budynku. Przewody zewnętrzne mają złącza N, stacja złącze SMA-F. Antena na zewnątrz nie jest montowana ani obsługiwana podczas burzy. Antenę umieszcza się poniżej krawędzi dachu; maszt na szczycie budynku wymaga oceny jego instalacji odgromowej. Ochrona ESD wyjścia RF nie zastępuje ochrony odgromowej.

Wariant anteny: kolinearna antena dookólna o zysku 5–6 dBi, w pionie. Na obu końcach łącza daje około 7 dB więcej niż dwa dipole, bez zmiany P1. ERP rośnie do około 15,5 dBm, nadal poniżej limitu 27 dBm. Kosztem jest węższa wiązka w płaszczyźnie pionowej, więc antena musi stać pionowo i nie nadaje się do łącza o dużej różnicy wysokości na krótkim dystansie. Zysk anteny wpisuje się do raportu próby; nie może przekraczać deklarowanych 6 dBi.

Tłumienie swobodnej przestrzeni na 1 km wynosi około 91 dB, co przy 13 dBm, dwóch dipolach i 1 dB strat przewodu na każdym końcu daje 34 dB zapasu względem −110 dBm na złączu. Model Okumury-Haty dla małego miasta daje jednak na 1 km 126–133 dB, czyli zapas około −0,7 dB (antena na 30 m), −3,5 dB (anteny na 10 m i 3 m) i −7,3 dB (anteny na 10 m i 1,5 m). Jeżeli układ radiowy osiągnie −110 dBm tylko na własnym wejściu, około 3 dB strat toru wejściowego obniża te wartości do −3,7, −6,5 i −10,3 dB. To mediany: łącze, które ma przenieść 99 ze 100 zgłoszeń, potrzebuje dodatkowo około 10 dB zapasu na zaniki, a rozrzut tłumienia między miejscami sięga 6–8 dB. Promień pierwszej strefy Fresnela w połowie drogi wynosi około 9,3 m, więc anteny przy oknach niskich kondygnacji pracują zwykle bez widoczności. Cel 1 km w zabudowie wymaga więc wysoko umieszczonych anten lub przekaźników; zysk z większej mocy (do około +16 dBm w obu układach) jest mały. Z dipolami ERP wynosi około 12 dBm (16 mW), około 15 dB poniżej limitu 500 mW; większa moc wymaga zewnętrznego wzmacniacza, nowej konstrukcji RF, pomiaru emisji i nowego budżetu energii stacji. Przy instalacji stałej (2,5 dB strat na każdym końcu) zapas spada o 3 dB: 31,1 dB w wolnej przestrzeni oraz −3,7, −6,5 i −10,3 dB w modelu Haty (−6,7, −9,5 i −13,3 dB, jeśli układ osiąga −110 dBm tylko na własnym wejściu); z antenami kolinearnymi na obu końcach +3,0, +0,2 i −3,6 dB. ERP z dipolem wynosi wtedy około 10,5 dBm. Obliczenia: [wyniki modelu](../../software/reference/wyniki.json). Nie wolno obiecywać zasięgu na podstawie samej czułości katalogowej.

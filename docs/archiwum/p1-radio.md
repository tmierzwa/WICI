# P1, dwa wykonania radia i stanowiska deweloperskie (archiwum)

Ten plik zawiera części dawnej specyfikacji radia, które opisywały własny profil radiowy P1 (2-GFSK 4800 bit/s), dwa wykonania stacji na układach TI CC1120 i ST S2-LP, stanowiska deweloperskie A/B i warunki powrotu z LoRa do P1. Przegląd praktyczny wstrzymał ten kierunek 2026-10-08 (F99), bo LoRa SF7 na gotowych modułach SX1262 ma lepszą czułość i nie wymaga własnych torów RF; od porządku dokumentów 2026-10-29 (F119) treść jest tutaj, a obowiązujący profil opisuje [specyfikacja radia](../spec/radio.md).

Tekst przeniesiono bez zmian merytorycznych, z wyjątkiem poprawek z przeglądu 2026-10-29 oznaczonych jako „Poprawka 2026-10-29”. Odnośniki do „profilu LoRa” prowadzą do bieżącej specyfikacji. Wnioski z koncepcji (porównanie P1 z LoRa, budżet czasu, energia z CC1120) są w [archiwum koncepcji](p1-koncepcja.md).

## Porównanie z profilem LoRa

Czułość katalogowa SX1262 w SF7 (−124 dBm, na złączu −121 dBm przy 3 dB strat toru) jest o 11 dB lepsza niż cel P1 (−110 dBm). Zapas modelu Okumury-Haty na 1 km dla P1 wynosi −0,7, −7,3 i −3,5 dB (anteny na 30 m i 1,5 m, 10 m i 1,5 m, 10 m i 3 m), a przy instalacji stałej −3,7, −10,3 i −6,5 dB; LoRa daje w tych przypadkach +10,3, +3,7 i +7,5 dB. Model ruchu w P1: 50 zgłoszeń przez przekaźnik 22,6–24,0 min nadawania z 30 min (LoRa 16,4–17,2 min); z PRZECZYTANE i decyzją 43,8 min (LoRa 31,5 min); próba ruchu mieszanego około 48 min z 60 (LoRa około 34,6 min). Pojemność w P1: przekaźnik przed stanowiskiem około 68 zgłoszeń/h, stacja stanowiska około 121/h. Odbiornik CC1120 pobiera 22 mA, SX1262 4,6 mA.

## Warunki powrotu do P1

Do 2026-10-29 specyfikacja przewidywała powrót do P1 tylko wtedy, gdy:

1. w T5 LoRa SF7 nie daje 99/100 na parze miejsc, na której P1 daje 99/100 (jeśli stanowiska P1 są zmontowane);
2. w T3 lub T5 profil LoRa nie mieści W10 przy zmierzonym ruchu, a P1 tak;
3. brak gotowych modułów SX1262 z deklaracją UE od co najmniej dwóch producentów.

Poprawka 2026-10-29: warunek 3 był wtedy formalnie spełniony, bo dla żadnej płytki z SX1262 nie znaleziono podpisanej deklaracji UE producenta ([dokumenty zgodności](elektronika-r02.md#dokumenty-zgodności-kandydatów), stan 2026-10-21), a specyfikacja tego nie odnotowywała. Decyzja D20 (zespół jest producentem konfiguracji pilotażowej i bada ją sam) usuwa ten warunek: deklaracja producenta modułu nie jest warunkiem pilotażu.

## Profil P1 do prototypu

P1 jest wspólnym kontraktem dwóch wykonań stacji, a nie ustawieniami istniejącego RNode. Zmiana profilu obejmuje całą sieć. Decyzja D10 z 2026-10-08 wybrała roboczo LoRa; warunki powrotu do P1 są [wyżej](#warunki-powrotu-do-p1) ([koncepcja, rozdział 04](../concept/04-analiza-opcji.html)).

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz |
| Modulacja | 2-GFSK, BT 0,5 |
| Szybkość transmisji | 4800 bit/s |
| Dewiacja | ±4 kHz |
| Moc na złączu | 13 dBm, tolerancja po kalibracji ±1 dB |
| Wzorzec częstotliwości | TCXO ±0,5 ppm w zakresie temperatur, starzenie w pierwszym roku ≤±1 ppm, określony co najmniej dla −20…+55 °C (zapas nad celem stacji −20…+45 °C). Budżet błędu nadajnika do następnego pomiaru: temperatura ±0,5 + kalibracja ±0,3 + zasilanie i obciążenie ±0,2 + starzenie ±1,0 = ±2,0 ppm (około ±1,7 kHz), z zapasem do granicy ±2,5 ppm. Pomiar i korekta częstotliwości przy produkcji i w każdym corocznym przeglądzie technicznym, przyrządem o dokładności ≤0,1 ppm, przez producenta lub serwis; w dniu przeglądu stacje dowozi się do jednego miejsca (około 20 min na stację) |
| Filtr odbiornika | najbliższa nastawa 24–32 kHz, sprawdzona przy granicznym błędzie częstotliwości |
| Czułość odbioru | cel: ≤−110 dBm na złączu antenowym stacji, z pełnym torem wejściowym (SAW lub filtr, ESD, przełącznik RF), przy PER ≤1% dla ramek o maksymalnej długości (103 B), mierzona w tym profilu. Przy około 3 dB strat toru wejściowego układ radiowy musi osiągać około −113 dBm; do wyniku T4 cel jest zagrożony; wynik wchodził do warunków powrotu do P1 (poprawka 2026-10-29: D10 rozstrzygnięto roboczo 2026-10-08) |
| Kolejność bajtów i bitów | najbardziej znaczący bajt pierwszy (big endian); najbardziej znaczący bit pierwszy (MSB) |
| Preambuła i słowo synchronizacji | 8 × 0xAA, następnie D3 91 D3 91 |
| Wybielanie danych, kodowanie Manchester, FEC | wyłączone |
| CRC | programowe CRC-16/CCITT-FALSE; sprzętowe CRC wyłączone |
| Rozmiar datagramu (z interfejsu Reticulum w stacji) | 1–600 B; HW_MTU interfejsu 500 B plus kod dostępu IFAC; autokonfiguracja MTU linku wyłączona |
| Maksymalny deklarowany zysk anteny | 6 dBi; wpisywany do deklaracji zgodności i karty stacji |

Jeśli próba na 1 km się nie powiedzie, najpierw podnosi się antenę (dach, wyższa kondygnacja, z zachowaniem warunków ochrony odgromowej), stosuje antenę kolinearną albo dodaje przekaźnik. Obniżenie szybkości wymaga nowej wersji profilu; nie może być lokalną opcją.

Indeks modulacji wynosi 2 × 4 kHz / 4,8 kbit/s ≈ 1,67, a pasmo Carsona około 12,8 kHz. Przy błędzie ±2,5 ppm obu stron wzajemne odstrojenie sięga około 4,3 kHz, więc filtr 24–32 kHz zachowuje zapas. Wybielanie danych jest wyłączone, ponieważ większość pakietów Reticulum jest szyfrowana i pseudolosowa. Odporność na długie ciągi jednakowych bitów sprawdza się mimo to ramkami wzorcowymi z samych zer i samych jedynek.

Szczegóły P1 w częściach wspólnych dawnej specyfikacji:

- dostęp do kanału: w P1 kanał był zajęty, gdy RSSI przekracza próg CCA albo trwa odbiór po wykryciu słowa synchronizacji; początkowy próg −100 dBm leżał 10 dB powyżej czułości −110 dBm, więc słabsi sąsiedzi pozostawali dla CCA niewidoczni (ukryte węzły). Sygnały LoRa mogą mieć poziom poniżej progu CCA, a mimo to zakłócać odbiór ramek P1;
- największy możliwy dług ciszy w P1 wynosił około 16 s przy założonych 2 ms narastania mocy na fragment (do potwierdzenia pomiarem w T4);
- kanały 869,425 i 869,625 MHz pochodziły z węższego P1 i przy 125 kHz wychodzą poza podpasmo (F100);
- odstęp ponowień LXMF w P1 (datagram 600 B): 60 s, 115 s i 144 s dla przypadków z [tabeli ponowień](../spec/radio.md#ponowienia-i-limity-prób) ([wyniki modelu](../../software/reference/wyniki.json));
- tor nadawczy musiał tłumić harmoniczne (1739 i 2609 MHz) do poziomu EN 300 220: dla toru według referencji TI zmierzyć 2. i 3. harmoniczną, dodatkowy filtr dolnoprzepustowy tylko przy przekroczeniu; płytka S2-LP miała filtr harmonicznych jako wymaganie;
- polecenie `INFO` stanowisk odpowiadało np. `{"contract":2,"profile":"P1","radio":"CC1120","mcu":"nRF52840",…}`; stanowisko ST podawało `S2LP`, wariant Espressif `ESP32-S3`;
- USB w R02: stacja samozasilana, nie zasila się z VBUS (VSYS niezależne od VBUS) ani nie podaje napięcia na VBUS; złącze USB-C jako urządzenie (rezystory 5,1 kΩ na CC); wykonanie A pobiera z VBUS tylko prąd PHY USB nRF52840, około 2,5 mA; w wykonaniu B VBUS służy wyłącznie do wykrycia hosta; rezystor podciągający linię danych włącza się dopiero przy obecnym VBUS.

Budżet łącza P1: tłumienie swobodnej przestrzeni na 1 km (około 91 dB) przy 13 dBm, dwóch dipolach i 1 dB strat przewodu na każdym końcu dawało 34 dB zapasu względem −110 dBm na złączu, a przy instalacji stałej 31,1 dB. Jeżeli układ radiowy osiąga −110 dBm tylko na własnym wejściu, około 3 dB strat toru wejściowego obniża zapas modelu Okumury-Haty do −3,7, −6,5 i −10,3 dB (instalacja stała: −6,7, −9,5 i −13,3 dB); z antenami kolinearnymi na obu końcach przy instalacji stałej +3,0, +0,2 i −3,6 dB. Zysk z większej mocy był mały (do około +16 dBm w obu układach).

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

Odbiornik składa najwyżej 8 datagramów, maksymalnie 600 B każdy, przez 120 s. Poprawne duplikaty są ignorowane. Inna treść tego samego fragmentu albo zmiana długości lub liczby fragmentów usuwa całą próbę składania. Po przepełnieniu odrzucana jest próba z najmniejszą liczbą odebranych fragmentów. Ramka P1 w wersji 1 nie niesie adresu nadawcy, więc limitu prób składania na nadawcę nie da się w niej wyegzekwować. Przed zalewem fragmentami chroni tylko limit 8 prób i zasada usuwania próby z najmniejszą liczbą fragmentów. Pole nadawcy (np. 2 B skrótu tożsamości) wymaga wersji ramki 2 dla całej sieci. Decyzję o nim podejmuje się po próbie „wrogi węzeł” w T3, ale przed zamówieniem płytek R02, póki nie ma stacji w terenie. Pamięć identyfikatorów ostatnio złożonych datagramów odrzuca spóźnione duplikaty fragmentów. Kompletny datagram trafia do interfejsu Reticulum w oprogramowaniu stacji. CRC-16 nie wykrywa wszystkich przekłamań. Uszkodzone pakiety szyfrowane i podpisane odrzuca dodatkowo kontrola integralności Reticulum. Sterownik P1 nie wysyła potwierdzeń, nie wyznacza tras i nie szyfruje. Robi to Reticulum w tym samym oprogramowaniu.

## Interfejs P1 w stosie Reticulum

Sterownik P1 jest interfejsem Reticulum według [interfejsu radiowego](../spec/radio.md#interfejs-radiowy-w-stosie-reticulum), w stosie stacji ([koncepcja, rozdział 03](../concept/03-dostepne-rozwiazania.html#reticulum-i-lxmf-w-tym-projekcie)). Odstęp ponowień i limit prób są w części [ponowienia i limity prób](../spec/radio.md#ponowienia-i-limity-prób); w P1 na pustej sieci potwierdzenie przez jeden przekaźnik wraca najwcześniej po około 13–15 s.

Interfejs deklaruje stosowi jawną przepływność (wartość wyznacza się pomiarem w T3; sama wartość nie przesądza o zgodności czasów) i osobny limit ogłoszeń. Każdy pakiet na interfejsie P1 niesie kod dostępu sieci (IFAC Reticulum, 16 B) ustawiany przy przygotowaniu; pakiety bez poprawnego kodu są odrzucane przed przetwarzaniem. Zgodność IFAC potwierdzają wektory z Reticulum w Pythonie i T3. Próba „wrogi węzeł” (zalew ogłoszeniami, zapytaniami o trasę, pakietami K2 i w P1 fragmentami) należy do T3 i T5; natężenie, czas i kryteria są w [odbiorze](../spec/odbior.md#próby).

## Stanowisko deweloperskie

Próby T1–T4 przed płytką R02 wykonuje się na [stanowisku deweloperskim](../../hardware/dev-bench/README.md). Stanowisko tworzą:

- płytki rozwojowe obu rodzin MCU (nRF52840-DK, ESP32-S3-DevKitC-1);
- moduły radiowe producentów (TI CC1120EM-868-915; ST X-NUCLEO-S2868A2);
- pamięć FRAM (zegar 8 MHz) i panel ekranu na [płytce nośnej N1](../../hardware/dev-bench/plytka-nosna.md).

Stanowisko nie ma własnego toru RF, wzorca częstotliwości ani stabilizatora modułów. N1 ma tylko przetwornicę 5 V panelu. Płytki uruchamiają oprogramowanie układowe stacji. Płytką stacji jest R02; N1 jest narzędziem stanowiska. Kontroler R01.3 (STM32F103 z modułem CC1120) miał za mało pamięci na stos Reticulum i nie był stacją. Został wycofany, a jego ustalenia są w [lekcjach projektu R02](../../hardware/r02/lekcje.md). Wcześniejszy kontrakt modemu USB/KISS nie obowiązuje. Zwykły KISSInterface Reticulum ma limit czasu kontroli przepływu 5 s, krótszy niż cisza P1, a próby stosu wykonuje się bezpośrednio na stanowisku i na stacji ([KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py)).

Wyniki czułości i emisji ze stanowiska dotyczą toru RF producenta bez toru wejściowego stacji; wynik na złączu stacji z pełnym torem daje dopiero R02. Wzorzec częstotliwości modułów nie spełnia budżetu P1, więc na stanowisku błąd częstotliwości mierzy się i koryguje poleceniem `FOFF`, a budżet z TCXO sprawdza się na R02. Nastawy rejestrów CC1120 i S2-LP dla P1 (częstotliwość, szybkość, dewiacja, filtr 25,0 kHz i 25,5 kHz, moc, preambuła i słowo synchronizacji) są w oprogramowaniu stanowiska ([CC1120](../../firmware/README.md#rejestry-profilu-p1), [S2-LP](../../firmware/README.md#rejestry-profilu-p1-dla-s2-lp)) jako tablice generowane ze wzorów kart układów, z eksportu SmartRF Studio i z biblioteki ST; pole LEN ramki liczy BODY i CRC, więc pasuje do silnika pakietów obu układów ([przegląd, F79](../review.md)).

## Dwa wykonania

Dwa wykonania stacji mają wspólny P1, wspólny protokół USB do laptopa i to samo zachowanie ekranu i przycisków, ale różne układy RF i rodziny MCU (W14). Wybór MCU zamyka D14, a ekranu D15.

| Funkcja | Wykonanie A | Wykonanie B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 413–479 i 826–958 MHz |
| MCU stacji | Nordic nRF52840; Bluetooth wyłączony, sposób trwałego wyłączenia i argumentacja RED w D14 | Espressif ESP32-S3FN8 (8 MB flash w obudowie; ESP32-S3R2 z flash QSPI 8 MiB, jeśli D14 wymaga PSRAM); Wi-Fi i Bluetooth wyłączone, sposób trwałego wyłączenia i argumentacja RED w D14 |
| Pamięć RAM | ≥256 KiB na stos Reticulum z LXMF, tablicę tras i bufory; nRF52840 ma 256 KiB; z portem microReticulum odtworzenie na komputerze daje 3,5% wolnej RAM w szczycie (warunek niespełniony), rdzeń stacji ma cel ≤56 KB statycznie ([budżet](../../firmware/reticulum-core.md#wymagania-konstrukcyjne)); wymagany zmierzony zapas ≥30% w T3, przed projektem płytki R02; wariant zapasowy z większą pamięcią: nRF5340 (rdzeń aplikacyjny 512 KiB), RP2350 lub STM32U5 (D14) | 512 KiB SRAM (ESP32-S3FN8 bez PSRAM; ESP32-S3R2 z PSRAM 2 MiB tylko wtedy, gdy D14 tego wymaga; płytka pilotażowa może mieć PSRAM, ale zapas liczy się bez niej); zmierzony zapas ≥30% w T3.  |
| Pamięć nieulotna | FRAM SPI 4 Mbit we wszystkich stacjach ([pamięć FRAM](../spec/oprogramowanie.md#trwałość-i-potwierdzenia)): Infineon CY15B104QN-50SXI (SOIC-8, w sprzedaży; sprawdzany na płytce nośnej N1); rekordy szyfrowane | FRAM SPI 4 Mbit: RAMXEED (dawniej Fujitsu) MB85RS4MTPF-G-BCERE1 (SOIC-8, w sprzedaży; ten sam footprint co w A); rekordy szyfrowane |
| Ekran | graficzny monochromatyczny z pamięcią obrazu (memory LCD) lub e-papier, cyrylica i piktogramy | wykonanie innego producenta, ten sam układ treści |
| Połączenie MCU–radio | SPI: SCK, MOSI, MISO, CS; IRQ; reset/shutdown | ten sam podział funkcji, inne piny |
| Wzorzec częstotliwości RF | zgodny z dokumentacją CC1120 | zgodny z dokumentacją S2-LP |
| Zasilanie RF | filtrowane 3,3 V, 100 nF przy każdym wyprowadzeniu zasilania, 10 µF przy układzie radiowym | takie samo wymaganie |
| Wyjście RF | układ dopasowania producenta dla 868/915 MHz; filtr harmonicznych według wyniku pomiaru; ochrona ESD o małej pojemności, potem złącze SMA-F 50 Ω | osobne dopasowanie S2-LP z filtrem harmonicznych, ta sama ochrona i złącze |

Nadajnik musi przetrwać nadawanie przy rozwartym i zwartym złączu antenowym, ponieważ odłączona lub uszkodzona antena to typowy błąd obsługi w terenie. Dopasowanie RF i wartości oscylatora dotyczą konkretnego układu. Nie wolno przenosić ich z projektu TI do projektu ST. Obie płytki wymagają osobnego projektu toru RF i nastaw rejestrów; żadna jeszcze nie powstała. Wspólny format ramki nie dowodzi zgodności obu fizycznych stacji.

Do oceny pozostaje filtr pasmowy SAW 868 MHz, który ogranicza blokowanie przez telefony LTE 800 i GSM 900 ([koncepcja, rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)). W topologiach referencyjnych TI i ST nadajnik i odbiornik mają wspólny węzeł RF, więc filtru nie da się umieścić „na wejściu odbiornika” bez przełącznika. Do rozstrzygnięcia przy R02 były dwa warianty:

- (a) osobna ścieżka odbiorcza przez przełącznik RF SPDT, z filtrem SAW tylko w torze RX;
- (b) filtr SAW we wspólnym torze, o wytrzymałości ≥+20 dBm, dopuszczalny tylko wtedy, gdy strata całego toru nadawczego wynosi ≤1,5 dB. Inaczej wariant (a).

Wymagania filtru: pasmo 869,4–869,65 MHz z zapasem na temperaturę, strata ≤2,5 dB w −20…+45 °C, tłumienie ≥20 dB przy 862 MHz i ≥30 dB przy 880–915 MHz. W obu wariantach strata wtrąceniowa wchodzi do czułości na złączu i wymaga pomiaru. Poprawka 2026-10-29: przegląd katalogów 2026-10-08 (BOM, wiersz filtra SAW) nie znalazł filtru spełniającego wariant (b), więc zostawał tylko wariant (a) z przełącznikiem RF ([BOM R02](bom-r02.md)). Prąd TX w modelu energii liczy się dla mocy na wyjściu układu (13 dBm plus strata toru do złącza), nie dla mocy na złączu.

Tryb nasłuchu z próbkowaniem (RX sniff) CC1120 zmniejszyłby pobór w odbiorze, ale wymaga dłuższej preambuły niż w P1. Jeżeli W23 nie zostanie spełnione, możliwa jest przyszła wersja P1 z dłuższą preambułą; zmiana obejmuje całą sieć.

S2-LPCBQTR obsługuje w górnym paśmie zakres 904–1055 MHz i nie nadaje się do 869,525 MHz. Przy zamawianiu nie wystarcza sama nazwa rodziny S2-LP ([warianty w karcie katalogowej](https://www.st.com/resource/en/datasheet/s2-lp.pdf)).

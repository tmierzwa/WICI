# WICI: radio

**Pilotaż używa LoRa** (decyzja D10, rozstrzygnięta roboczo 2026-10-08; przegląd praktyczny, F99 w [przeglądzie](../review.md)). Profil pilotażu opisuje część [Profil LoRa pilotażu](#profil-lora-pilotażu). Profil P1 i dwa wykonania TI/ST opisane dalej są wariantem zapasowym i pytaniem do wydania. Prace nad torami RF płytki R02 są wstrzymane do decyzji po pilotażu.

## Profil LoRa pilotażu

Stacje pilotażowe używają gotowych modułów lub płytek z układem Semtech SX1262 i deklaracją zgodności UE. Interfejs LoRa jest interfejsem Reticulum w porcie microReticulum, tak jak interfejs P1. Format w eterze jest zgodny z RNode; zgodność potwierdza T3 (wymiana z Reticulum w Pythonie przez RNode; [odbiór](odbior.md#minimum-pilotażu), wiersz „Interfejs LoRa stacji”).

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz (D11 bez zmian) |
| Szerokość kanału | 125 kHz |
| Współczynnik rozpraszania | SF7; SF8 tylko do porównania zasięgu w etapie 0 |
| Kodowanie (CR) | 4/5 |
| Nagłówek LoRa | jawny |
| CRC | włączone |
| Preambuła | 18 symboli (założenie modelu, do potwierdzenia w T3 wobec RNode) |
| Moc na złączu | 13 dBm; limit pasma 27 dBm ERP |
| Cisza po nadaniu | po każdym nadaniu (seria jednej albo dwóch ramek) cisza 12t (limit pasma 10%); wszystkie punkty [dostępu do kanału](#dostęp-do-kanału) obowiązują na interfejsie LoRa; zajętość kanału w punkcie 5 wykrywa się wykrywaniem aktywności kanału (CAD) SX1262 i RSSI, z progami z T4 |
| Kod dostępu sieci | IFAC Reticulum, 16 B, jak na interfejsie P1 |
| Rozmiar pakietu | datagram (pakiet Reticulum z kodem IFAC 16 B) ≤508 B, czyli pakiet ≤492 B przed IFAC; do 254 B datagramu w jednej ramce LoRa, większy w dwóch ramkach nadawanych jedną serią; dłuższy pakiet interfejs odrzuca przed nadaniem i liczy w diagnostyce; model przyjmuje 1 B nagłówka ramki, jak w RNode. Wiadomości WICI (SA1 ≤256 B w jednym pakiecie okazjonalnym LXMF) mieszczą się w limicie z zapasem; LXMF nie przechodzi na link ani zasób ([oprogramowanie](oprogramowanie.md#wiadomości-sa1)) |
| Sprzęt | gotowa płytka MCU (ESP32-S3) z SX1262 albo moduł SX1262, z deklaracją zgodności UE |

Czas nadawania w SF7 według modelu ([wyniki modelu](../../software/reference/wyniki.json), `lora_pilot`): typowe zgłoszenie 0,67 s, zgłoszenie z najdłuższymi polami 0,74 s, RECEIVED 0,48 s, dowód pakietu 0,18 s, ogłoszenie 0,36 s, największy datagram (508 B) w dwóch ramkach 0,82 s.

Czułość katalogowa SX1262 w SF7 wynosi −124 dBm. Przy 3 dB strat toru wejściowego daje to −121 dBm na złączu, czyli 11 dB lepiej niż cel P1 (−110 dBm). Zapas modelu Okumury-Haty na 1 km wynosi +10,3 dB (anteny na 30 m i 1,5 m), +3,7 dB (10 m i 1,5 m) i +7,5 dB (10 m i 3 m); przy instalacji stałej +7,3, +0,7 i +4,5 dB. Dla P1 te same przypadki dają −0,7, −7,3 i −3,5 dB oraz −3,7, −10,3 i −6,5 dB. To nadal mediany, bez zapasu na zaniki (zob. budżet łącza na końcu tego rozdziału); o zasięgu rozstrzyga etap 0 i T5.

Model ruchu w SF7: 50 zgłoszeń przez przekaźnik B zajmuje 16,4–17,2 min nadawania z 30 min (P1: 22,6–24,0 min); z PRZECZYTANE i decyzją (dwa STATUS) 31,5 min (P1: 43,8 min); próba ruchu mieszanego 55 rewizji około 34,6 min z 60 (P1: około 48 min). Pojemność: przekaźnik przed stanowiskiem około 95 zgłoszeń/h (P1: około 68), stacja stanowiska około 164/h (P1: około 121).

SF8 daje 2 dB czułości więcej (−126 dBm), ale 50 zgłoszeń zajmuje 29,1–30,4 min, więc W10 nie mieści się w 30 min, a próba mieszana trwa około 61,6 min z 60. SF8 nie jest więc profilem bazowym.

Odbiornik SX1262 pobiera 4,6 mA zamiast 22 mA w CC1120. Przy założeniach przetwornicy R02 komplet ogniw AA Li-FeS2 daje ESP32-S3 około 70, 52 i 41 h przy 30, 45 i 60 mA poboru MCU (nRF52840 około 200 h). W23 (≥48 h) wymaga więc średnio najwyżej około 45 mA MCU. Stacja pilotażowa ma inny tor zasilania (gotowa przetwornica i regulator płytki, [elektronika](elektronika.md#stacja-pilotażowa)), więc o W23 rozstrzyga pomiar 48 h z minimum pilotażu, nie model.

Powrót do P1 następuje tylko wtedy, gdy: (1) w T5 LoRa SF7 nie daje 99/100 na parze miejsc, na której P1 (jeśli stanowiska P1 są zmontowane) daje 99/100; (2) w T3 lub T5 profil LoRa nie mieści W10 przy zmierzonym ruchu, a P1 tak; (3) brak gotowych modułów SX1262 z deklaracją UE od co najmniej dwóch producentów.

## Profil P1 do prototypu

Wariant zapasowy (przegląd praktyczny 2026-10-08, F99): ta część i dalsze części o P1, ramce P1 i dwóch wykonaniach nie są potrzebne do pilotażu i nie są dalej rozwijane. Sterowniki P1 i stanowiska deweloperskie A/B zostają do prób stosu i opcjonalnego porównania. Części ogólne (współdzielenie kanału, dostęp do kanału, warunki prawne, USB) dotyczą także profilu LoRa.

P1 jest wspólnym kontraktem dwóch wykonań stacji, a nie ustawieniami istniejącego RNode. Zmiana profilu obejmuje całą sieć. Decyzja D10 z 2026-10-08 wybrała roboczo LoRa; warunki powrotu do P1 są w [profilu LoRa](#profil-lora-pilotażu) ([koncepcja, rozdział 04](../concept/04-analiza-opcji.html)).

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

W T5 w każdym miejscu pilotażu mierzy się zajętość podpasma przez ≥2 tygodnie w różnych porach doby, a w pracy próbnej zapisuje liczniki CCA (CAD), odroczeń i błędów CRC. Gotowej częstotliwości zapasowej nie ma: kanał 125 kHz mieści się w podpaśmie 869,40–869,65 MHz tylko ze środkiem w 869,4625–869,5875 MHz, a każdy taki kanał pokrywa kanał RX2 LoRaWAN (869,4625–869,5875 MHz). Wcześniej wymieniane kanały 869,425 i 869,625 MHz pochodziły z węższego P1 i przy 125 kHz wychodzą poza podpasmo (F100). Ucieczka od RX2 oznacza więc węższą szerokość pasma (dłuższy czas nadawania i ponowne przeliczenie W10) albo inne podpasmo z innymi limitami mocy i cyklu pracy. Zmiana kanału jest nową wersją profilu dla całej sieci (decyzja D11, przed wdrożeniem; [plan](../concept/08-plan-weryfikacji-i-decyzje.html)).

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
5. Przed serią kanał musi być wolny przez 50 ms; kanał jest zajęty, gdy RSSI przekracza próg CCA albo trwa odbiór po wykryciu słowa synchronizacji (w LoRa: po wykryciu preambuły przez CAD). Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms; licznik długich odroczeń trafia do diagnostyki. CCA nie zastępuje limitu czasu TX. W P1 początkowy próg −100 dBm leży 10 dB powyżej czułości −110 dBm, więc słabsi sąsiedzi pozostają dla CCA niewidoczni (ukryte węzły). W LoRa CAD wykrywa preambuły poniżej poziomu szumu, ale nie sygnały FSK ani LoRa o innym SF; próg RSSI i liczbę symboli CAD wyznacza się w T4.
6. **Podział czasu kanału.** Czas kanału to czas nadawania wraz z jego długiem ciszy (13t na serię), liczony w przesuwnym oknie 3600 s. Stacja dzieli nadawane pakiety na trzy klasy:
   - **K0:** własne pakiety stacji, dowody pakietów (potwierdzenia), zapytania o trasę i odpowiedzi na nie; przekazywane zapytania o trasę mają osobny limit: najwyżej 1 na cel na 60 s i łącznie ≤5% czasu kanału, ponad limit są odrzucane i liczone;
   - **K1:** przekazywane pakiety danych do przypiętego odbiorcy (adres docelowy to aktywna tożsamość odbiorcy z karty); w konfiguracji węzła stanowiska pakiety do celów osiągalnych przez interfejs USB i pakiety z tego interfejsu;
   - **K2:** pozostałe przekazywane pakiety danych (liczba przeskoków większa od zera), także RECEIVED, STATUS, REPLY i BULLETIN od odbiorcy do innych stacji, bo przekaźnik nie odróżni ich od cudzego ruchu (w nagłówku jest tylko adres docelowy).

   K2 zajmuje łącznie z ogłoszeniami (niżej) najwyżej 60% czasu kanału w oknie; pakiet K2 ponad ten limit stacja odrzuca przed kolejką i liczy w diagnostyce, i nie oddaje mu ostatniego miejsca w kolejce radiowej. Drugi limit, 25% czasu kanału dla jednego celu w K2, działa tylko wtedy, gdy w kolejce radiowej czeka pakiet K0 lub K1; bez takiej rywalizacji jeden cel może zająć cały limit K2. Dzięki temu schronienie za przekaźnikiem, do którego płyną wszystkie odpowiedzi odbiorcy (w próbie „Odpowiedzi dyżurnego” około 26% czasu kanału, przy pełnym ruchu mieszanym około 50%), nie traci odpowiedzi, a zalew jednym celem nie wypiera ruchu do odbiorcy. Ogłoszenia (własne i przekazywane) mają limit 2% czasu zegarowego liczony z czasu nadawania ([ogłoszenia](oprogramowanie.md#tryby-kryzysowe)); z długiem ciszy to do 26% czasu kanału. Ich czas kanału wlicza się do tej samej puli co K2: **K2 i ogłoszenia razem zajmują najwyżej 60% czasu kanału w oknie**; ogłoszenie ponad ten limit czeka w kolejce ogłoszeń interfejsu radiowego stacji (limit `announce_cap` Reticulum tej puli nie widzi), a nie jest odrzucane. K0 (poza limitem zapytań o trasę) i K1 nie mają limitu, więc gwarancja brzmi: w każdym oknie 3600 s co najmniej 40% czasu kanału pozostaje dla K0 i K1, także przy zalewie ruchem obcym i pełnym limicie ogłoszeń. Udział zapewnia limit, a kolejność w kolejce radiowej skraca oczekiwanie: najpierw dowody pakietów i zapytania o trasę (bez trasy dane nie wyjdą), potem dane K0 i K1, potem dane K2, na końcu ogłoszenia ([kolejność w kolejce](oprogramowanie.md#wysyłanie)); pakiet K0 lub K1 czeka więc najwyżej na zakończenie bieżącej serii i jej długu ciszy (w LoRa ≤13 × 0,82 s ≈ 10,7 s), na dowody, zapytania o trasę i wcześniejsze pakiety K0 i K1 w kolejce oraz na odroczenia CCA. W modelu ruchu mieszanego przekaźnik przed stanowiskiem przy pełnym obciążeniu nadaje w K2 około 51% czasu kanału, a ogłoszenia co 6 h dodają poniżej 1%, więc pula 60% nie ogranicza ruchu w modelu; przy zimnym starcie sieci ogłoszenia zajmują do 26%, a RECEIVED dla TEST startowych przekazywane w K2 (dla 50 stacji 50 × 6,2 s ≈ 5,2 min, około 9% godziny przekaźnika) razem z nimi około 35%, poniżej puli. T5 sprawdza progi na zmierzonym ruchu.

Rezerwacja obejmuje preambuły, słowa synchronizacji, pola długości, CRC oraz zmierzony czas narastania mocy i przełączenia nadajnika dla każdego fragmentu; model przyjmuje go jako parametr (`ramp_ms`), a dowód limitu 10% opiera się na wartości zmierzonej. Dług zapisuje się przed pierwszym fragmentem serii; zapis ma znacznik zatwierdzenia zapisywany na końcu, więc zanik zasilania w trakcie zapisu zostawia poprzedni poprawny rekord, a nadanie bez zatwierdzonego długu nie następuje ([zanik zasilania](elektronika.md#zanik-zasilania-i-zapis)). Dług przechowuje dziennik w pamięci FRAM stacji, tej samej co kolejka zgłoszeń. Każdy rekord zawiera numer, dług, CRC i znacznik zatwierdzenia; dziennik utrzymuje co najmniej dwa poprawne rekordy. W najgorszym przypadku, przy ciągłym nadawaniu najkrótszych datagramów, zapis następuje co 0,65 s, czyli około 133 000 razy na dobę. Trwałość FRAM (co najmniej 10¹³ cykli według kart katalogowych kandydatów) nie ogranicza czasu pracy, więc rozkładanie zapisów nie jest potrzebne. Dziennik długu ciszy nie jest szyfrowany i przetrwa ZNISZCZ DANE. Gdy przy starcie brak poprawnego rekordu, stacja odczekuje największy możliwy dług (12 × czas TX największego datagramu z narastaniem mocy; w LoRa 12 × 0,82 s ≈ 10 s, w P1 około 16 s przy założonych 2 ms na fragment; do potwierdzenia pomiarem w T4), zakłada nowy dziennik i zlicza zdarzenie w diagnostyce; nie blokuje nadawania do czasu diagnostyki. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania CCA; wyłącza się go tylko na czas własnego nadawania, bo stacja jest przekaźnikiem.

## Warunki prawne i zgodność

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10% (pasmo h1.4 według ERC/REC 70-03, [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105)); przed użyciem w Polsce trzeba jeszcze potwierdzić warunki krajowe oraz emisje gotowego urządzenia. Sama częstotliwość nie stanowi dopuszczenia nadajnika. Zestaw przekazywany innym osobom podlega dyrektywie RED 2014/53/UE. Gmina może używać stacji wyłącznie jako produktów z deklaracją zgodności UE wystawioną przez producenta; samodzielne złożenie stacji przez gminę lub wolontariuszy czyni ich producentem ze wszystkimi obowiązkami.

Wykaz do kwalifikacji i deklaracji zgodności:

- EN 300 220-2 w aktualnej wersji: widmo radiowe; cel: kategoria odbiornika 1,5. T4 mierzy blokowanie i selektywność kanału sąsiedniego na poziomach tej kategorii oraz czułość przy PER ≤1% w obecności CW −30 dBm na 862 i 880 MHz (poziom do potwierdzenia wobec telefonu w odległości 1 m);
- EN 301 489-1 i -3: kompatybilność elektromagnetyczna;
- EN 62368-1: bezpieczeństwo; EN 62479: ekspozycja na pole;
- rozporządzenie delegowane (UE) 2022/30 i normy zharmonizowane EN 18031-1 i -2:2024 (art. 3 ust. 3 lit. d i e RED, cyberbezpieczeństwo), stosowane od 1 sierpnia 2025; normy opublikowano decyzją wykonawczą (UE) 2025/138 z ograniczeniami w załączniku I;
- RoHS (EN IEC 63000), WEEE (dla wszystkich modułów zestawu) oraz rozporządzenie bateryjne (UE) 2023/1542;
- maksymalny deklarowany zysk anteny 6 dBi, wpisany do deklaracji i karty stacji.

Nadajniki Wi-Fi i Bluetooth mikrokontrolera stacji są wyłączone, ale radio 2,4 GHz wyłączone tylko w oprogramowaniu układowym może być nadal traktowane jako zamierzony nadajnik. W pilotażu Wi-Fi i Bluetooth ESP32-S3 są wyłączone programowo; stacje pilotażowe są urządzeniami badanymi, własnością zespołu, więc ta kwestia wraca przy wydaniu. Opcje do rozstrzygnięcia w D14 dla wydania: (a) trwała blokada (eFuse lub konfiguracja startowa, gdzie MCU ją zapewnia), bezpieczny rozruch (secure boot) i pisemna argumentacja RED; (b) budżet badań według EN 300 328 i EN 301 489-17; (c) MCU bez radia, np. RP2350 (520 KiB RAM) albo STM32U5.

Poziom 3 używa kupionej stacji zasilania i ładowarki USB z deklaracją zgodności UE producenta ([elektronika](elektronika.md#poziom-3-kupiona-stacja-zasilania)); WICI nie jest ich producentem.

Tor nadawczy musi tłumić harmoniczne (1739 i 2609 MHz) do poziomu emisji niepożądanych wymaganego przez EN 300 220. Dla toru według referencji TI zmierzyć 2. i 3. harmoniczną; dodatkowy filtr dolnoprzepustowy tylko przy przekroczeniu. Płytka S2-LP ma filtr harmonicznych jako wymaganie.

## Interfejs radiowy w stosie Reticulum

Interfejs radiowy (w pilotażu LoRa, w wariancie zapasowym P1) jest interfejsem Reticulum w porcie microReticulum. Przyjmuje datagram tylko wtedy, gdy kolejka radiowa na 4 datagramy ma wolne miejsce; inaczej zgłasza stosowi zajętość, a odrzut liczy w diagnostyce. Odrzut nie może potwierdzić zgłoszenia. Stos zna dług ciszy i przewidywany czas oczekiwania kolejki radiowej i uwzględnia je w limitach czasu i ponowieniach. Każdy pakiet niesie kod dostępu sieci (IFAC Reticulum, 16 B) ustawiany przy przygotowaniu; pakiety bez poprawnego kodu są odrzucane przed przetwarzaniem. Zgodność IFAC i formatu ramek LoRa z RNode w microReticulum potwierdza T3. Tryb ciszy radiowej blokuje w interfejsie każde nadawanie, także ruchu przekazywanego; interfejs ma osobną flagę dla pojedynczego zgłoszenia wyjętego spod ciszy.

### Ponowienia i limity prób

Odstęp ponowienia wiadomości okazjonalnej LXMF wynosi co najmniej max(60 s, 2 × liczba skoków × 13 × czas TX największego datagramu + bieżący dług ciszy + czas opróżnienia kolejki radiowej). Na pustej sieci potwierdzenie przez jeden przekaźnik wraca w LoRa po kilku sekundach, ale przy kolejce i długu ciszy po ponad minucie; zbyt wczesne ponowienie podwaja ruch i łamie W10.

| Przypadek (LoRa SF7, datagram 508 B: 0,82 s) | Odstęp |
|---|---|
| pusta sieć, 1 lub 2 skoki | 60 s |
| 1 skok, największy dług i pełna kolejka 4 datagramów | około 74 s (21,3 + 9,8 + 42,6 s) |
| 2 skoki, największy dług i pełna kolejka | około 95 s |
| P1 dla porównania (datagram 600 B) | 60 s, 115 s, 144 s ([wyniki modelu](../../software/reference/wyniki.json)) |

| Nadawca | Próby LXMF na jedno ponowienie intencji | Odstęp prób | Ponowienia intencji |
|---|---|---|---|
| stacja schronienia (microReticulum, wybrana implementacja LXMF) | ≤2 | według tabeli wyżej | [wysyłanie](oprogramowanie.md#wysyłanie): po FAILED 1, 2, 5, 15 min, po 6 h co 60 min; po DELIVERED bez RECEIVED co 30–60 min |
| aplikacja stanowiska (LXMF w Pythonie, `c3ff2d6`) | 3: najmniejsza liczba, jaką LXMF w Pythonie stosuje przy odstępie ponad 10 s; mniej wymagałoby zmiany kodu stosu (D19) | ≥196 s przy `bitrate` ≤42 b/s interfejsu KISS ([stanowisko](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)) | jak stacja schronienia, dla RECEIVED, STATUS, REPLY i BULLETIN |

Domyślny LXMF w Pythonie wykonuje do 5 prób co 10 s (`MAX_DELIVERY_ATTEMPTS`, `DELIVERY_RETRY_WAIT`); gdy szacowany czas obiegu przekracza 10 s, liczba prób spada do max(3, round(50 / czas obiegu)), ale nigdy poniżej 3, a odstęp do czasu obiegu = 2 × max(limit pierwszego skoku − 6 s, 0) + 6 s, gdzie limit pierwszego skoku = 500 × 8 / przepływność interfejsu + 6 s. Zależnie od przepływności zgłoszonej przez interfejs (LoRa SF7 około 5,5 kbit/s, domyślny interfejs KISS 1,2 kbit/s) daje to 3–5 prób co 10–13 s, czyli nadania szybsze od potwierdzeń. Aplikacja stanowiska ustawia więc w interfejsie KISS niską przepływność (`bitrate`), tak by limit potwierdzenia pakietu (500 × 8 / `bitrate` + 6 s + 6 s na skok) nie był krótszy od odstępu z tabeli dla 2 skoków, czyli `bitrate` ≤42 b/s w LoRa ([stanowisko](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Odstęp prób LXMF wynosi wtedy ≥196 s, liczba prób spada do 3, a trzecia próba wychodzi po około 6,5 min, gdy pierwsze potwierdzenie na pewno nie wróciło. Stacja schronienia ma 2 próby, bo jej implementację LXMF wybiera się w D14 i limit ustawia się w niej wprost; różnica dotyczy tylko liczby nadań wiadomości, której potwierdzenie zaginęło. Że wystarcza do tego konfiguracja, sprawdza T3 jako warunek utrzymania D19.

## Interfejs P1 w stosie Reticulum

Wariant zapasowy. Sterownik P1 jest interfejsem Reticulum według [interfejsu radiowego](#interfejs-radiowy-w-stosie-reticulum), opartym na porcie microReticulum ([koncepcja, rozdział 03](../concept/03-dostepne-rozwiazania.html#reticulum-i-lxmf-w-tym-projekcie)). Odstęp ponowień i limit prób są w części [ponowienia i limity prób](#ponowienia-i-limity-prób); w P1 na pustej sieci potwierdzenie przez jeden przekaźnik wraca najwcześniej po około 13–15 s.

Interfejs deklaruje stosowi jawną przepływność (wartość wyznacza się pomiarem w T3; sama wartość nie przesądza o zgodności czasów) i osobny limit ogłoszeń. Każdy pakiet na interfejsie P1 niesie kod dostępu sieci (IFAC Reticulum, 16 B) ustawiany przy przygotowaniu; pakiety bez poprawnego kodu są odrzucane przed przetwarzaniem. Zgodność IFAC w microReticulum potwierdza T3. Próba „wrogi węzeł” (zalew ogłoszeniami, zapytaniami o trasę, pakietami K2 i w P1 fragmentami) należy do T3 i T5; natężenie, czas i kryteria są w [odbiorze](odbior.md#próby).

Znajomość długu ciszy nie zmienia limitów czasu całego stosu. Osobno trzeba sprawdzić wyszukiwanie trasy, zestawianie linku, przesyłanie zasobu i potwierdzenia, także gdy pakiet czeka za ruchem przekazywanym; zob. [kontrprzykład czasowy i stan przeglądu](../review.md). Wszystkie stacje sieci, także stacja stanowiska, używają tego samego oprogramowania stacji. Komputer stanowiska używa implementacji Reticulum i LXMF w Pythonie (D19), więc zgodność z nią, sprawdzana w T3, jest warunkiem działania sieci, a nie tylko próbą laboratoryjną.

## Interfejs Reticulum przez USB (węzeł stanowiska)

Stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)) ma w stosie drugi interfejs Reticulum: interfejs danych CDC poza trybem przygotowania przenosi pakiety Reticulum do komputera stanowiska i z powrotem. W trybie przygotowania ten sam interfejs przenosi [protokół USB](oprogramowanie.md#protokół-usb-laptopstacja), aby można było zmienić konfigurację i oprogramowanie.

- **Ramki:** KISS (FEND, FESC), jedna ramka danych to jeden pakiet Reticulum do 500 B; zgodne z interfejsem KISS Reticulum w Pythonie z kontrolą przepływu. Polecenia konfiguracji KISS od komputera (TXDELAY, P, SLOTTIME, TXTAIL) stacja przyjmuje i pomija, bo dostęp do kanału określa interfejs radiowy stacji.
- **Kontrola przepływu:** komputer włącza ją przy starcie poleceniem KISS 0x0F z wartością 1. Stacja wysyła ramkę gotowości (0x0F, jak RNode) po przyjęciu pakietu do bufora USB na co najmniej 8 pakietów po 500 B; komputer wysyła następny pakiet dopiero po niej. Reticulum w Pythonie (`e40191b`) sam zwalnia blokadę po 5 s bez gotowości (stała `flow_control_timeout` interfejsu KISS), więc wstrzymanie gotowości nie zatrzyma komputera na czas długu ciszy. Pakiet ponad bufor stacja odrzuca i liczy, a ponowienie zapewnia LXMF; aplikacja stanowiska ogranicza ruch do 4 wiadomości w drodze, aby bufor wystarczał.
- **Kierunek do komputera:** stacja przekazuje pakiety, które transport kieruje do interfejsu USB: ruch do tożsamości odbiorcy, ogłoszenia i zapytania o trasę.
- **Limity:** pakiety z USB przechodzą przez interfejs radiowy z jego priorytetami, długiem ciszy, limitem ogłoszeń i ciszą radiową. IFAC dotyczy tylko interfejsu radiowego; pakiet z USB dostaje kod dostępu sieci przy nadaniu, a pakiet z radia bez poprawnego kodu nie trafia do komputera. W konfiguracji węzła stanowiska klasa K1 z punktu 6 w [dostępie do kanału](#dostęp-do-kanału) obejmuje pakiety do celów osiągalnych przez interfejs USB i pakiety z tego interfejsu, bo stacja nie ma karty odbiorcy; ruch od odbiorcy do stacji schronień jest tu więc w K1, nie w K2.
- **Diagnostyka:** liczniki pakietów w obu kierunkach i czas od ostatniego pakietu od komputera (`komputer_osp` na ekranie, pola w `INFO` i `RNS`).

Ramki, polecenia i kontrolę przepływu sprawdzono w kodzie interfejsu KISS Reticulum `e40191b`; działanie ze stacją i wartość `bitrate` po stronie komputera ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)) potwierdza T3. Interfejs przez USB nie jest dostępny w stacji schronienia.

## USB do laptopa

USB CDC ACM, przewód do 2 m, złącze USB-C stacji jako urządzenie (rezystory 5,1 kΩ na liniach CC). Stacja R02 jest urządzeniem samozasilanym: nie zasila się z VBUS (VSYS niezależne od VBUS) ani nie podaje napięcia na VBUS. Stacja pilotażowa przy podłączonym laptopie może pobierać zasilanie z VBUS przez diodę płytki ([elektronika](elektronika.md#stacja-pilotażowa)); w pilotażu laptop łączy się tylko w trybie przygotowania, a odłączenie przewodu nie powoduje restartu dzięki szynie 5 V z własnych źródeł. Wykonanie A pobiera z VBUS tylko prąd PHY USB nRF52840, około 2,5 mA; w wykonaniu B VBUS służy wyłącznie do wykrycia hosta. Rezystor podciągający linię danych włącza się dopiero przy obecnym VBUS. Wstrzymanie, uśpienie lub odłączenie hosta nie zmienia pracy stacji. Urządzenie ma dwa interfejsy CDC ACM, danych i diagnostyki (w ESP32-S3 przez USB-OTG i TinyUSB, nie USB-Serial-JTAG), z deskryptorami IAD (Interface Association Descriptor), aby Windows 10 i nowsze przypisały oba wbudowanemu sterownikowi bez instalowania dodatkowego. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem; nie wolno używać identyfikatorów cudzego urządzenia. Protokół danych między laptopem a stacją opisuje [specyfikacja oprogramowania](oprogramowanie.md#protokół-usb-laptopstacja).

Polecenie diagnostyczne na interfejsie diagnostyki: `INFO\n`; odpowiedź: jeden wiersz JSON zaczynający się od pól kontraktu: `{"contract":2,"profile":"P1","radio":"CC1120","mcu":"nRF52840","fw":"...","src":"AA","mv":5800,"tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0,"restarts":0}`. Wariant ST podaje `S2LP`, a wariant Espressif `ESP32-S3`. Dalsze pola diagnostyczne stanowiska opisuje [oprogramowanie](../../firmware/README.md#polecenia); wiersz mieści się w limicie 1024 B interfejsu. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

Polecenia pomiarowe na interfejsie diagnostyki działają wyłącznie w trybie przygotowania i służą próbom T4 na [stanowisku deweloperskim](../../hardware/dev-bench/README.md) i na R02: `TXCW <s>` nadaje nośną bez modulacji przez ≤10 s (pomiar częstotliwości i mocy); `TXPKT <n> <len> [<ms>] [ZEROS|ONES]` nadaje `n` ramek o długości `len` B z numerem porządkowym w treści i odstępem `ms`, z wypełnieniem pseudolosowym albo z samych zer lub samych jedynek; `RX [<len>]` uruchamia odbiór ramek wzorcowych, a `STOP` przerywa serię; `RXPER` zwraca i zeruje liczniki ramek odebranych, z błędem CRC i brakujących numerów; `FOFF <Hz>` ustawia korektę częstotliwości do restartu. Odpowiedź: jeden wiersz JSON. Limit czasu nadawania i cisza radiowa obowiązują także dla tych poleceń; serię dłuższą niż limit dopuszcza tylko argument `conducted`, przeznaczony wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego, potwierdzony przyciskiem OK na stacji w ciągu 30 s i zapisany w dzienniku zdarzeń.

## Stanowisko deweloperskie

Próby T1–T4 przed płytką R02 wykonuje się na [stanowisku deweloperskim](../../hardware/dev-bench/README.md): płytki rozwojowe obu rodzin MCU (nRF52840-DK, ESP32-S3-DevKitC-1) z modułami radiowymi producentów (TI CC1120EM-868-915; ST X-NUCLEO-S2868A2), pamięć FRAM (zegar 8 MHz) i panel ekranu na samej [płytce nośnej N1](../../hardware/dev-bench/plytka-nosna.md), bez własnego toru RF, wzorca częstotliwości i stabilizatora modułów (N1 ma tylko przetwornicę 5 V panelu), uruchamiające oprogramowanie układowe stacji. Płytką stacji jest R02; N1 jest narzędziem stanowiska. Kontroler R01.3 (STM32F103 z modułem CC1120) miał za mało pamięci na stos Reticulum i nie był stacją; został wycofany, a jego ustalenia są w [lekcjach projektu R02](../../hardware/r02/lekcje.md). Wcześniejszy kontrakt modemu USB/KISS nie obowiązuje: zwykły KISSInterface Reticulum ma limit czasu kontroli przepływu 5 s, krótszy niż cisza P1, a próby stosu wykonuje się bezpośrednio na stanowisku i na stacji ([KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py)).

Wyniki czułości i emisji ze stanowiska dotyczą toru RF producenta bez toru wejściowego stacji; wynik na złączu stacji z pełnym torem daje dopiero R02. Wzorzec częstotliwości modułów nie spełnia budżetu P1, więc na stanowisku błąd częstotliwości mierzy się i koryguje poleceniem `FOFF`, a budżet z TCXO sprawdza się na R02. Nastawy rejestrów CC1120 i S2-LP dla P1 (częstotliwość, szybkość, dewiacja, filtr 25,0 kHz i 25,5 kHz, moc, preambuła i słowo synchronizacji) są w oprogramowaniu stanowiska ([CC1120](../../firmware/README.md#rejestry-profilu-p1), [S2-LP](../../firmware/README.md#rejestry-profilu-p1-dla-s2-lp)) jako tablice generowane ze wzorów kart układów, z eksportu SmartRF Studio i z biblioteki ST; pole LEN ramki liczy BODY i CRC, więc pasuje do silnika pakietów obu układów ([przegląd, F79](../review.md)).

## Dwa wykonania

Wariant zapasowy i pytanie do wydania (F99): pilotaż używa jednej rodziny, ESP32-S3 na gotowej płytce z SX1262, w [profilu LoRa](#profil-lora-pilotażu). Drugie niezależne wykonanie (inna rodzina MCU albo inny układ radiowy) to decyzja po pilotażu.

Dwa wykonania stacji mają wspólny P1, wspólny protokół USB do laptopa i to samo zachowanie ekranu i przycisków, ale różne układy RF i rodziny MCU (W14). Wybór MCU zamyka D14, a ekranu D15.

| Funkcja | Wykonanie A | Wykonanie B |
|---|---|---|
| Radio | TI CC1120 | ST S2-LPQTR; wariant dla 413–479 i 826–958 MHz |
| MCU stacji | Nordic nRF52840; Bluetooth wyłączony, sposób trwałego wyłączenia i argumentacja RED w D14 | Espressif ESP32-S3 z pamięcią PSRAM; Wi-Fi i Bluetooth wyłączone, sposób trwałego wyłączenia i argumentacja RED w D14 |
| Pamięć RAM | ≥256 KiB na port microReticulum, LXMF, tablicę tras i bufory; nRF52840 ma 256 KiB, a odtworzenie na komputerze daje 4,5% wolnej RAM w szczycie (warunek niespełniony); wymagany zmierzony zapas ≥30% w T3, przed projektem płytki R02; wariant zapasowy z większą pamięcią: nRF5340 (rdzeń aplikacyjny 512 KiB), RP2350 lub STM32U5 (D14) | 512 KiB SRAM i PSRAM; zmierzony zapas ≥30% w T3. Pilotaż używa jednej rodziny: ESP32-S3 na gotowej płytce z SX1262 (D14 dla pilotażu) |
| Pamięć nieulotna | FRAM SPI 4 Mbit we wszystkich stacjach ([pamięć FRAM](oprogramowanie.md#trwałość-i-potwierdzenia)): Infineon CY15B104QN-50SXI (SOIC-8, w sprzedaży; sprawdzany na płytce nośnej N1); rekordy szyfrowane | FRAM SPI 4 Mbit: RAMXEED (dawniej Fujitsu) MB85RS4MTPF-G-BCERE1 (SOIC-8, w sprzedaży; ten sam footprint co w A); rekordy szyfrowane |
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

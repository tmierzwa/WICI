# WICI: stanowisko deweloperskie

Stanowisko deweloperskie to zestaw kupnych płytek rozwojowych i modułów producentów, na którym powstaje oprogramowanie układowe stacji i wykonuje się próby T1–T4 przed płytką stacji. Pierwszą drukowaną płytką projektu jest płytka stacji [R02](../../docs/spec/elektronika.md#płytka-stacji-r02-wymagania). Wcześniejszy kontroler R01.3 nie jest budowany; jego ustalenia są w [lekcjach R02](../r02/lekcje.md), a pliki w historii Git.

Pierwszy obraz oprogramowania dla stanowiska A, z okablowaniem i poleceniami, jest w [firmware/](../../firmware/README.md).

Zasada: do prób nie projektuje się ani nie zamawia własnych płytek. Stanowisko składa się z elementów dostępnych u dystrybutorów, połączonych przewodami, i uruchamia to samo oprogramowanie układowe co stacja, z własnym plikiem opisu płytki (przypisanie wyprowadzeń). Nie ma osobnego oprogramowania stanowiska ani osobnego kontraktu modemu.

## Dwa stanowiska

Stanowiska odpowiadają dwóm wykonaniom stacji ([specyfikacja radia](../../docs/spec/radio.md#dwa-wykonania)), więc wynik prób przenosi się na R02 w zakresie MCU, radia, stosu i interfejsu użytkownika. Do prób mieszanych TI–ST potrzeba po jednym stanowisku każdego rodzaju; do sieci A–B–OSP z zapasem potrzeba czterech (dwa A i dwa B), co odpowiada dwóm modułom w zestawie CC1120EMK.

| Element | Stanowisko A (TI) | Stanowisko B (ST) | Uwagi |
|---|---|---|---|
| Płytka MCU | Nordic nRF52840-DK (PCA10056) | Espressif ESP32-S3-DevKitC-1 z modułem ESP32-S3-WROOM-1-N8R2 | obie zasilane i programowane przez USB; nRF52840-DK ma złącza Arduino i zworki pomiaru prądu MCU; stacja R02 używa ESP32-S3FH4R2, DevKit ma flash w module |
| Moduł radiowy | TI CC1120EM-868-915 z zestawu [CC1120EMK-868-915](https://www.ti.com/tool/CC1120EMK-868-915) (dwa moduły, tor RF według referencji TI, złącze SMA) | ST [X-NUCLEO-S2868A2](https://www.st.com/en/evaluation-tools/x-nucleo-s2868a2.html) albo płytka radiowa z zestawu [STEVAL-FKI868V2](https://www.st.com/en/evaluation-tools/steval-fki868v2.html) (S2-LP 826–958 MHz, złącze SMA) | połączenie A: adapter [BOOST-CCEMADAPTER](https://www.ti.com/tool/BOOST-CCEMADAPTER) albo przewody przylutowane do złączy EM; połączenie B: przewody ze złącza Arduino płytki ST do DevKit; wszystkie sygnały 3,3 V |
| Wzorzec częstotliwości radia | kwarc modułu; pola X2 na TCXO według referencji TI (przeróbka opcjonalna) | wzorzec płytki ST według jej schematu | na stanowisku błąd częstotliwości mierzy się i koryguje poleceniem `FOFF`; budżet ±2,0 ppm z TCXO sprawdza dopiero R02 |
| Pamięć FRAM | [Adafruit 4719](https://www.adafruit.com/product/4719) (RAMXEED MB85RS4MT, 4 Mbit, SPI) | ta sama | ten sam układ co kandydat B w [BOM stacji](../../docs/spec/bom-stacji.csv) |
| Ekran | [Adafruit 4694](https://www.adafruit.com/product/4694) (Sharp LS027B7DH01, 400 × 240) | ten sam | płytka ma przetwornicę 5 V i translację poziomów, więc zasila się z 3,3 V; EXTCOMIN z wyjścia licznika MCU, nie z programu (na nRF52840 RTC2 przez PPI i GPIOTE); zworka EXTMODE w położeniu H; piny w [firmware/README.md](../../firmware/README.md#okablowanie-stanowiska-a) |
| Przyciski i sygnalizacja | 4 przyciski menu, przełącznik CISZA, przycisk trybu przygotowania, dioda alarmu, brzęczyk na płytce stykowej | te same | wejścia z podciąganiem w MCU; eliminacja drgań w oprogramowaniu jak w stacji |
| Zasilanie | USB z laptopa albo zasilacz laboratoryjny | to samo | zasilanie jest narzędziem; nie mierzy budżetu energii stacji (T6) ani niezależności od VBUS |
| Antena i tor pomiarowy | dipol z [BOM stacji](../../docs/spec/bom-stacji.csv) do prób w eterze; tłumiki 30–40 dB, przewody koncentryczne i obciążenie sztuczne do prób przewodowych | to samo | pomiar czułości tylko przewodowo, w ekranowanym pudełku; płytki rozwojowe przepuszczają sygnał poza złącze |

Przyrządy: analizator widma, generator sygnałowy z modulacją (czułość, blokowanie), miernik częstotliwości o dokładności ≤0,1 ppm, miernik mocy albo analizator z tłumikiem. Zewnętrzny filtr SAW 868 MHz w torze koncentrycznym pozwala zmierzyć blokowanie z filtrem i bez niego przed decyzją o torze wejściowym R02.

Moduł CC1120 innego producenta nadaje się tylko do uruchomienia oprogramowania i prób ramek: jego dopasowanie i wzorzec częstotliwości są nieznane, więc nie daje wyniku czułości, emisji ani błędu częstotliwości.

## Co sprawdza stanowisko, a co dopiero R02

| Grupa | Na stanowisku | Dopiero na R02 |
|---|---|---|
| T1, T2, T8 | stos, kolejka w FRAM, ekran, przyciski, protokół USB laptop–stacja, obsługa według karty na makiecie obudowy | zachowanie przy odłączeniu VBUS i samozasilanie (stanowisko zasila się z USB) |
| T3 | microReticulum i LXMF na obu rodzinach MCU, zapas RAM, zgodność z implementacją referencyjną, emulator P1 i prawdziwy tor P1 | nic |
| T4 | ramki, zgodność TI→ST i ST→TI, czułość na złączu modułu (bez toru wejściowego stacji), harmoniczne toru referencyjnego, blokowanie z zewnętrznym filtrem SAW i bez niego, dług ciszy, limit czasu nadawania, CCA, cisza radiowa, błąd częstotliwości z korektą | budżet częstotliwości z TCXO, pełny tor wejściowy (filtr, ESD, przełącznik), nadawanie przy rozwartym i zwartym złączu, emisje gotowej konfiguracji w obudowie |
| T5 | wczesne próby zasięgu: stanowisko w pudełku zasilane z powerbanku (narzędzie prób, nie źródło stacji) | odbiór 1 km, przekaźnik na ogniwach, zimny start sieci |
| T6, T7 | nic | energia, bezpieczeństwo, odtworzenie i dostawcy |

Wyniki czułości i emisji ze stanowiska dotyczą toru RF producenta, nie stacji. Pokazują, czy układ radiowy i profil P1 w ogóle osiągają cel (około −113 dBm na złączu układu), zanim powstanie projekt R02 z własnym torem wejściowym.

## Pomiary

Polecenia pomiarowe interfejsu diagnostyki (`TXCW`, `TXPKT`, `RXPER`, `FOFF`) działają tylko w trybie przygotowania i są opisane w [specyfikacji radia](../../docs/spec/radio.md#usb-do-laptopa). Czułość przy PER ≤1% wymaga ≥2000 ramek 103 B na punkt, czyli więcej nadawania, niż dopuszcza limit 10% w godzinie; takie serie nadaje się wyłącznie przewodowo do tłumika, po potwierdzeniu przyciskiem na stanowisku, z zapisem w dzienniku. Procedura pomiarów T4 i warunki zaliczenia są w [odbiorze](../../docs/spec/odbior.md).

## Złącza modułu CC1120EM

Stanowisko nie ma własnego CAD: połączenia opisuje tabela, a nie schemat. Mapa złączy P1/P2 modułu TI CC112xEM 868/915 pochodzi z projektu R01.3. Numery są elektrycznymi numerami pinów; złącza są na spodzie modułu, a widok od spodu odwraca obraz. Przed zasilaniem sprawdzić każdą żyłę miernikiem. Długość przewodów do 5 cm w pierwszej próbie, SPI około 1 MHz.

| Sygnał | Złącze modułu TI | Pin CC1120 |
|---|---|---:|
| GND | P1.1, P1.19, P2.2 | masa modułu |
| 3,3 V | P2.7 (P2.9 to ten sam węzeł) | zasilanie modułu |
| SCK | P1.16 | 8 |
| MOSI | P1.18 | 7 |
| MISO | P1.20 | 9 |
| CS_N | P1.14 | 11 |
| RESET_N | P2.15 | 2 |
| GPIO0 / IRQ0 | P1.10 | 10 |
| GPIO2 / IRQ2 | P1.12 | 4 |

Pozostałych pinów nie wolno traktować jako masy. Adapter BOOST-CCEMADAPTER wyprowadza te same sygnały na złącza BoosterPack; bez adaptera przewody lutuje się do pól złączy EM. Linię RESET_N trzyma się w stanie niskim do czasu startu MCU.

## Co zostaje z R01.3

Z kontrolera R01.3 przechodzą do R02 tylko wnioski toru RF i procesu: dopasowanie i stos według referencji TI, wybór TCXO i budżet błędu, pomiar harmonicznych, ochrona ESD, ocena filtru SAW, zasady layoutu i kontroli ([lekcje R02](../r02/lekcje.md)). Kontroler STM32F103, jego PCB, kontrakt KISS i dziennik w EEPROM nie są używane.

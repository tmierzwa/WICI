# WICI: obsługa stanowiska z płytką nośną N1

Instrukcja dla osoby, która prowadzi próby T1–T4 na zmontowanym stanowisku. Dotyczy sztuki płytki N1, która przeszła [uruchomienie](uruchomienie.md); montaż, kontrola przed zasilaniem i pierwsze włączenie są tam. Opis płytki: [płytka nośna](plytka-nosna.md), polecenia oprogramowania: [firmware/README.md](../../firmware/README.md#polecenia), granice pomiarów stanowiska: [README stanowiska](README.md#co-sprawdza-stanowisko-a-co-dopiero-r02).

## Zasady

- **Nigdy oba MCU ani oba moduły radiowe naraz.** Sieci sygnałowe płytki są wspólne dla stanowisk A i B.
- Moduły wpina się i wyjmuje, a zworki zmienia, tylko bez zasilania: przewody USB odłączone, zacisk VTEST bez napięcia.
- Przed każdym wpięciem sprawdza się orientację modułu według opisu na płytce: ekran szkłem do góry z pinem VIN nad napisem VIN, złącze SMA modułu CC1120EM nad kółkiem, USB DevKitC w stronę napisu USB. Każdy z tych modułów wchodzi w gniazda także obrócony.
- Na DK wpiętą w N1 nie wgrywa się obrazu okablowania przewodami `bench-a` ([uruchomienie](uruchomienie.md#oprogramowanie)). Stanowisko A używa obrazu `bench-n1`, stanowisko B obrazu `bench-b`.
- Przed każdym poleceniem nadawania złącze SMA modułu musi być obciążone: antena z [BOM stacji](../../docs/spec/bom-stacji.csv) albo tłumik i obciążenie 50 Ω. Odporność na nadawanie przy rozwartym i zwartym złączu sprawdza się dopiero na R02.
- W eterze nadaje się tylko profilem P1 na 869,525 MHz, w limicie czasu nadawania, który pilnuje oprogramowanie. Serie z argumentem `CONDUCTED` nadaje się wyłącznie przewodowo do tłumika albo obciążenia ([pomiary](README.md#pomiary)).
- Na zacisk VTEST podaje się najwyżej 15 V z zasilacza z ograniczeniem prądu. Minus zacisku jest masą płytki, a przez nią masą USB laptopa.
- Płytkę obsługuje się na macie antystatycznej. W stanowisku B długie piny J1–J4 wystają od spodu: płytka stoi tylko na dystansach, nigdy na metalowym podłożu.

## Konfiguracja

| | Stanowisko A (TI) | Stanowisko B (ST) |
|---|---|---|
| Płytka MCU | nRF52840-DK pod płytką nośną (długie piny J1–J4 w gniazdach Arduino DK) | ESP32-S3-DevKitC-1 w J5/J6 |
| Moduł radiowy | CC1120EM-868-915 w J9/J10 | X-NUCLEO-S2868A2 w J1–J4, z założoną zworką JP1 na X-NUCLEO |
| Ekran i FRAM | Adafruit 4694 w J7, Adafruit 4719 w J8 | te same |
| Zworki N1 | JP3 założona; JP1 i JP2 zdjęte | JP1 i JP2 założone; JP3 bez znaczenia |
| Puste gniazda | J5, J6 | J9, J10 |
| Podparcie | lewa część płytki na dystansach H1, H2, H5, tak by leżała poziomo | dziewięć dystansów H1–H9 |
| Obraz | `bench-n1` ([opis](../../firmware/README.md#płytka-nośna-n1-bench-n1)) | `bench-b` ([opis](../../firmware/README.md#stanowisko-b-na-płytce-n1-bench-b)) |
| Zasilanie i wgrywanie | USB płytki DK; J-Link na złączu J2 DK | złącze „USB” DevKitC (nie „UART”) |
| Porty do laptopa | dwa porty szeregowe na złączu nRF USB (J3) DK: diagnostyka i dane | dwa porty szeregowe na złączu „USB” DevKitC: diagnostyka i dane |
| Przełączniki płytki MCU | ustawione przed nałożeniem N1: SW8 włączony, SW9 w położeniu fabrycznym, TRACE (SW7) „Default” | brak |

Zmiana stanowiska z A na B (powrót do A: te same kroki w odwrotnej kolejności, z JP3 zamiast JP1 i JP2):
1. Odłączyć USB. Wyjąć CC1120EM z J9/J10 i zdjąć N1 z płytki DK.
2. Zdjąć JP3; założyć JP1 i JP2.
3. Postawić N1 na dziewięciu dystansach H1–H9.
4. Wpiąć DevKitC w J5/J6 i X-NUCLEO-S2868A2 w J1–J4.
5. Podłączyć USB DevKitC i sprawdzić poleceniem `INFO` (`bench: "B"`) i `RADIO` (`partnumber: 0x03`).

Ta sama sztuka N1 może służyć obu stanowiskom; każdą zmianę konfiguracji wpisuje się do zapisu sztuki ([uruchomienie](uruchomienie.md)).

## Elementy płytki

| Element | Oznaczenie | Działanie |
|---|---|---|
| Przyciski menu | SW1–SW4: GÓRA, DÓŁ, OK, WSTECZ | menu stacji ([ekran i przyciski](../../firmware/README.md#ekran-i-przyciski)) |
| Przełącznik ciszy radiowej | SW5, opis „CISZA: 1-2” | styki 1–2 zwarte = cisza radiowa; przełącznik ma pierwszeństwo przed poleceniami z USB. Położenie sprawdza się poleceniem `BTN` (`silence_switch: true` = cisza) |
| Przycisk trybu przygotowania | SW6, „PRZYGOT.” | przytrzymanie 3 s włącza albo wyłącza tryb przygotowania, w którym działają polecenia pomiarowe |
| Dioda alarmu | D1, „ALARM” | świeci, dopóki trwa przyczyna alarmu, i w ciszy radiowej |
| Brzęczyk | BZ1 | 2048 Hz na ekranie alarmu, do potwierdzenia OK; cisza radiowa nie daje dźwięku |
| Wejście pomiaru napięcia | J12, „VTEST 0-15 V”, „+” po lewej | dzielnik 1/6 do wejścia ADC MCU; polecenie `VTEST` podaje napięcie na zacisku. Do prób progów napięcia ogniw i 12 V z zasilaczem laboratoryjnym |
| Złącze analizatora stanów logicznych | J11, pin 1 = GND | piny 1–9: GND, SCK, MOSI, MISO, CS radia, CS FRAM, CS ekranu, GPIO0 radia, GPIO2 radia (na płytce: „GND SCK MO MI RF FR LCD G0 G2”) |
| Zworki zasilania | JP1 „3V3 (B)”, JP2 „5V (B)”, JP3 „RADIO (A)” | zasilanie z DevKitC (B) i zasilanie modułu CC1120EM (A); w miejsce zworki wpina się amperomierz |

## Pomiar prądu

Amperomierz wpina się w miejsce zworki przy odłączonym zasilaniu, na zakresie co najmniej 200 mA. Zmiana zakresu amperomierza przerywa obwód i restartuje zasilany układ, więc zakres wybiera się przed włączeniem.

| Zworka | Stanowisko | Co mierzy |
|---|---|---|
| JP3 | A | prąd samego modułu CC1120EM (nadawanie +14 dBm około 45 mA według karty układu) |
| JP1 | B | prąd szyny 3,3 V z DevKitC: X-NUCLEO-S2868A2, FRAM i rezystory podciągające, bez samego ESP32-S3 |
| JP2 | B | prąd szyny 5 V z DevKitC: ekran i brzęczyk |

Te pomiary służą uruchomieniu i porównaniu modułów. Budżetu energii stacji (T6) na stanowisku się nie mierzy.

## Typowe problemy

| Objaw | Prawdopodobna przyczyna | Co sprawdzić |
|---|---|---|
| `RADIO`: `partnumber` 0x00 albo 0xFF | moduł radiowy niewpięty albo obrócony; w A zdjęta JP3; w B zdjęta zworka JP1 na X-NUCLEO | orientacja modułu, zworki, sygnały SCK, MISO i CS radia na J11 |
| Ekran pusty | ekran obrócony; w B zdjęta JP2; obraz nie uruchomił ekranu | orientacja według napisów przy J7, napięcie na J7.1 (VIN) wobec J7.3 (GND), `DISPLAY` |
| Obraz ekranu blednie albo zostają cienie | brak przebiegu EXTCOMIN | `DISPLAY`: `counter` rośnie, a `level` zmienia się co 0,5 s; pin EMD ekranu (J7.7) w stanie wysokim (3,3 V wobec J7.3) |
| `FRAM` nie rozpoznaje układu | moduł FRAM obrócony albo niewpięty | napisy przy J8, CS FRAM na J11 |
| Cisza radiowa nie daje się wyłączyć | przełącznik CISZA w położeniu „cisza” | `BTN`: `silence_switch` |
| Polecenia pomiarowe odrzucane | brak trybu przygotowania, cisza radiowa albo radio nieskonfigurowane | `INFO` (`prep`, `silence`), `RADIO` (`p1_ok`); w razie potrzeby `CONFIG` |
| W B system nie widzi dwóch portów | przewód w złączu „UART” DevKitC albo przewód tylko do ładowania | złącze „USB” DevKitC, inny przewód |
| `VTEST` daje około 0 mV przy podanym napięciu | odwrócona polaryzacja na J12 | „+” zacisku po lewej, miernik |
| Restart przy nadawaniu | słabe zasilanie z portu USB | koncentrator USB z własnym zasilaniem albo inny port |

Błędy, których nie wyjaśnia ta tabela, zgłasza się w [Issues](https://github.com/tmierzwa/WICI/issues) formularzem raportu z próby, z numerem sztuki, stanowiskiem, obrazem (`INFO`) i wynikiem poleceń diagnostycznych.

## Przechowywanie i transport

Moduły przewozi się wyjęte z gniazd, w opakowaniach antystatycznych. Zworki zostawia się założone w ostatniej konfiguracji, a konfigurację zapisuje w zapisie sztuki. Stanowiska B nie odkłada się na długie piny J1–J4.

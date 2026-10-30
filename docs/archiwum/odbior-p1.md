# Próby P1, stanowisk deweloperskich i bloku zasilania poziomu 3 (archiwum)

Plik przechowuje warunki prób z dawnego planu: własnego profilu radiowego P1 (2-GFSK na TI CC1120 i ST S2-LP), stanowisk deweloperskich A/B i własnego bloku zasilania poziomu 3. Profil P1 i stanowiska wstrzymał przegląd praktyczny 2026-10-08 (F99), a blok zasilania decyzja D05 z tego samego dnia; od 2026-10-29 wiersze są tu, a nie w [odbiorze](../spec/odbior.md) (F119).

Wiersze nie są warunkami pilotażu ani wyrobu. Gdyby decyzja D10 wróciła jako otwarta albo własny blok poziomu 3 wrócił do zakresu, są punktem wyjścia ([archiwum](README.md)). Odnośniki prowadzą do bieżących plików specyfikacji, które mogą już nie zawierać opisu P1.

## Wiersze tabeli prób

| Próba | Grupa | Warunek zaliczenia | Stan |
|---|---|---|---|
| Kodowanie ramek | T3, T4 | niezależny wektor CRC; długości 1–600 B; odwrócona kolejność fragmentów; błędy CRC i konflikt duplikatu | model wykonywalny; kodek w oprogramowaniu stanowiska (`firmware/src/p1frame.cpp`) zgodny z modelem bajt po bajcie w testach na komputerze, bez prób w eterze |
| Stacje mieszane | T4 | TI→ST, ST→TI, 10 000 pakietów każdego rozmiaru granicznego; brak różnic formatu | niewykonana |
| Stanowisko deweloperskie | T3, T4 | stanowiska A (nRF52840-DK + CC1120EM-868-915) i B (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 na płytce nośnej N1) według [opisu](../../hardware/dev-bench/README.md) uruchamiają oprogramowanie stacji; TI→ST i ST→TI; czułość na złączu modułu mierzona przewodowo i oznaczona jako wynik toru producenta, nie stacji; błąd częstotliwości zmierzony i skorygowany `FOFF`; polecenia pomiarowe tylko w trybie przygotowania, serie ponad limit nadawania tylko przewodowo po potwierdzeniu przyciskiem i z zapisem w dzienniku | niewykonana |
| Czułość (dawne brzmienie) | T4 | każde wykonanie, 3 egzemplarze w −20, +20 i +45 °C, ≥2000 pakietów na punkt: ≤−110 dBm przy PER ≤1% dla ramek 103 B; wynik gorszy niż −107 dBm otwiera D10; zmierzone na złączu antenowym stacji z pełnym torem wejściowym, w profilu P1; strona ST na stanowisku B (ESP32-S3-DevKitC-1 z X-NUCLEO-S2868A2 na płytce nośnej N1) albo na R02; moc i częstotliwość w tolerancji P1 | niewykonana |
| Porównanie P1 i LoRa w terenie | T5 | etap 0, przed pilotażem: 3 pary rzeczywistych miejsc, te same anteny, przewody, wysokości i pory doby; gotowe moduły LoRa SX1262 z deklaracją UE, 125 kHz, w profilu pilotażu SF7 i w SF8 (SF8 tylko do porównania zasięgu); stanowiska deweloperskie A i B (moduły producentów w profilu P1) tylko wtedy, gdy są zmontowane, bo N1 nie jest wymagane do pilotażu; na każdą parę i tor 100 pakietów rozmiaru TEST z potwierdzeniem, RSSI i SNR; wynik dotyczy torów producentów bez toru wejściowego stacji; raport jest wejściem do warunków powrotu do P1 w D10; [procedura](../spec/odbior.md#krok-5-pomiar-w-gminie) | niewykonana |
| Radio 1 km (dawne brzmienie) | T5 | 3 pary rzeczywistych miejsc, każda o dwóch porach doby, anteny na zewnątrz; wysokości, zyski anten, przewody i rewizje zapisane w raporcie; ≥99 ze 100 TEST z RECEIVED w 5 min na każdej parze, przy ruchu jednej stacji, bez innych nadawców; raport obejmuje wszystkie pary; w pilotażu w profilu LoRa SF7; na parze z wynikiem poniżej 99/100 porównanie z LoRa SF8 i, jeśli stanowiska P1 są zmontowane, z P1, z tymi samymi antenami (warunki powrotu do P1 w D10) | niewykonana |

## Fragmenty P1 usunięte z bieżących wierszy

Bieżące wiersze odbioru zostały w profilu LoRa. Z wierszy tabeli prób i minimum pilotażu usunięto następujące warunki i liczby P1; dawne pełne wiersze „Czułość”, „Porównanie P1 i LoRa w terenie” i „Radio 1 km” są w tabeli wyżej (stan z 2026-10-28):

- minimum pilotażu, pozycja c: „Porównanie P1 i LoRa w terenie” (etap 0) przed pilotażem;
- „Stos na MCU”: datagram P1 600 B; „Węzeł stanowiska”: pakiet z P1 bez IFAC nie dociera do komputera; „Wrogi węzeł”: w P1 dodatkowo zalew fragmentami bez blokady składania; „Laptop i USB”: wykonanie A pobiera z VBUS tylko prąd PHY USB ≈2,5 mA; „Skala sieci”, „Obciążenie sieci”, „Ruch mieszany z dyżurnym” i „Pojemność stanowiska”: wartości modelu P1 (121 i 68 zgłoszeń/h, 8700 zgłoszeń w 72 h, 22,6–24,0 min, 43,8 min, około 44 i 48 min).
- plan powtórzeń, wiersz „Porównanie P1 i LoRa (T5)”: etap 0, 3 pary miejsc × 2 tory LoRa (SF7, SF8) × 100 pakietów, każda para o dwóch porach doby; tory P1 (stanowiska A i B) tylko wtedy, gdy są zmontowane; bez progu zaliczenia, wynik do warunków powrotu do P1 (D10).

## Własny blok zasilania poziomu 3 (D05)

D05 zamknięto 2026-10-08: poziom 3 używa kupionej stacji zasilania i ładowarki USB z deklaracją zgodności UE ([elektronika](../spec/elektronika.md)).

| Próba | Grupa | Warunek zaliczenia | Stan |
|---|---|---|---|
| A/B | T6 | oba kierunki, napięcia 11,5 i 16 V, każdy tryb mocy, 100 zmian; brak resetów routera, laptopa i przetwornicy | niewykonana |
| Odłączenie podnapięciowe | T6 | archiwum; wejścia A/B i C: ostrzeżenie przy 11,8 V, wyłączenie przy 11,5 V ±0,1 V na złączu niezależnie od prądu i temperatury diody; ponowne załączenie wyłącznie ręczne i nie niżej niż 12,4 V; brak samoczynnego załączenia po odbiciu napięcia akumulatora kwasowo-ołowiowego i LiFePO4 | niewykonana |
| Udar A/B | T6 | prąd i I²t poniżej limitu każdego elementu; brak uszkodzeń oraz zgrzewania styków | niewykonana |
| Ładowarka | T6 | 8 × 1,5 A przez 2 h w temperaturze otoczenia 40 °C; 4,75–5,25 V na każdym porcie; skok obciążenia 1,5 A → 0 A w 0 °C i 40 °C bez zadziałania zwieracza | niewykonana |
| Zwarcie portu | T6 | pozostałe porty, laptop, router i stacja pracują; zwarcie trwające godzinę nie uszkadza sekcji | niewykonana |
| Ochrona telefonu przed przepięciem (OVP) | T6 | wymuszone zwarcie VIN–VREG regulatora; VUSB nigdy nie przekracza 5,5 V; po odłączeniu regulatora uszkodzona sekcja pozostaje wyłączona | niewykonana |
| Przetwornica | T6 | 150 W obciążenia rezystancyjnego na odpowiednim źródle, 230 V ±5%, THD <5%; rzeczywiste zasilacze, rozruch i skoki obciążenia; podłączenie zasilacza pod napięciem bez uszkodzenia mostka; brak jednostronnego nasycenia rdzenia | niewykonana |
| Ochrona AC | T6 | izolacja, PE, prąd dotykowy, uziemienie i reakcja RCBO sprawdzone zgodnie z przyjętą normą i konfiguracją | niewykonana |

Próbę OVP wykonuje się bez telefonu, z obciążeniem zastępczym i oscyloskopem o odpowiednim paśmie. Jeżeli zwieracz zabezpieczający nie utrzyma napięcia poniżej 5,5 V podczas impulsu, wymagana jest niezależna szybka ochrona szeregowa. Nie wolno zwiększać dopuszczalnego napięcia, aby zaliczyć próbę. Obecny zwieracz jest tylko kandydatem. Przed produkcją muszą też powstać schemat PE, projekt płytki, ostateczny dobór izolacji i pełna lista zakwalifikowanych zamienników.

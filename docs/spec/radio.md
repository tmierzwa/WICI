# WICI: radio

Radio stacji to LoRa SF7 na układzie Semtech SX1262 (decyzja D10, [koncepcja, rozdział 08](../concept/08-plan-weryfikacji-i-decyzje.html#otwarte-decyzje-i-warunki-zamkniecia)). Ten sam profil mają prototyp na płytce v1, stacje pilotażowe na płytce v2 i radia RNode, którymi mierzy się zasięg w krokach 2, 3 i 5. Wcześniejszy własny profil P1, dwa wykonania radia (TI CC1120 i ST S2-LP) i stanowiska deweloperskie są w [archiwum](../archiwum/p1-radio.md).

## Profil LoRa pilotażu

Interfejs LoRa jest interfejsem Reticulum w stosie stacji ([rdzeń](../../firmware/reticulum-core.md)). Format w eterze jest zgodny z RNode; zgodność potwierdza T3, czyli wymiana z Reticulum w Pythonie przez [radio RNode](#radia-rnode) ([odbiór](odbior.md#minimum-pilotażu), wiersz „Interfejs LoRa stacji”).

| Parametr | Wartość |
|---|---|
| Częstotliwość nośna | 869,525 MHz (D11) |
| Szerokość kanału | 125 kHz |
| Współczynnik rozpraszania | SF7; SF8 tylko do porównania zasięgu w krokach 3 i 5 |
| Kodowanie (CR) | 4/5 |
| Nagłówek LoRa | jawny |
| CRC | włączone |
| Preambuła | 18 symboli (program stacji, `lora_profile.h`, i model; zgodność z RNode potwierdza T3) |
| Słowo synchronizacji | 0x12 (sieć prywatna; program stacji, `lora_profile.h`; zgodność z RNode potwierdza T3) |
| Moc na złączu | 13 dBm; limit pasma 27 dBm ERP |
| Wzmocnienie odbiornika | tryb ze wzmocnieniem (Rx Boosted gain, rejestr 0x08AC = 0x96; przy uśpieniu z zachowaniem konfiguracji rejestr trzeba dopisać do listy zachowywanych, karta SX1261/2, rozdz. 9.6). Po resecie układ pracuje w trybie oszczędnym (0x94), w którym czułość jest mniejsza. Katalogowa czułość −124 dBm (SF7, 125 kHz) dotyczy trybu ze wzmocnieniem; prąd odbioru wynosi wtedy 5,3 mA zamiast 4,6 mA (karta SX1261/2, DC-DC). T4 potwierdza czułość i pobór |
| Cisza po nadaniu | po każdym nadaniu (seria jednej albo dwóch ramek) cisza 12t (limit pasma 10%); obowiązują wszystkie punkty [dostępu do kanału](#dostęp-do-kanału); zajętość kanału w punkcie 5 ustala się przez CAD (wykrycie aktywności kanału) SX1262 i RSSI, z progami z T4 |
| Kod dostępu sieci | IFAC Reticulum, 16 B. Po stronie Reticulum w Pythonie trzeba ustawić `ifac_size = 128` (w bitach) wprost, bo interfejs RNode ma domyślnie 8 B (`RNodeInterface.py`, `DEFAULT_IFAC_SIZE = 8`); z domyślną wartością ramki stacji i radia RNode się nie wymieniają ([radia RNode](#radia-rnode)) |
| Rozmiar pakietu | datagram (pakiet Reticulum z kodem IFAC 16 B) ≤508 B, czyli pakiet ≤492 B przed IFAC; do 254 B datagramu w jednej ramce LoRa, większy w dwóch ramkach nadawanych jedną serią; dłuższy pakiet interfejs odrzuca przed nadaniem i liczy w diagnostyce; 1 B nagłówka ramki, jak w RNode. Wiadomości WICI (SA1 ≤256 B w jednym pakiecie okazjonalnym LXMF) mieszczą się w limicie z zapasem; LXMF nie przechodzi na link ani zasób ([oprogramowanie](oprogramowanie.md#wiadomości-sa1)) |
| Sprzęt | moduł Seeed Wio SX1262 na prototypie i na płytce v2 ([elektronika](elektronika.md#stacja-pilotażowa)); RAK4631 w radiach RNode; bez zewnętrznego wzmacniacza nadajnika, bo 13 dBm go nie wymaga |

Czas nadawania w SF7 według modelu ([wyniki modelu](../../software/reference/wyniki.json), `lora_pilot`): typowe zgłoszenie 0,67 s, zgłoszenie z najdłuższymi polami 0,74 s, RECEIVED 0,48 s, dowód pakietu 0,18 s, ogłoszenie 0,36 s, największy datagram (508 B) w dwóch ramkach 0,82 s.

Czułość katalogowa SX1262 w SF7 wynosi −124 dBm. Przy 3 dB strat toru wejściowego daje to −121 dBm na złączu. Zapas modelu Okumury-Haty na 1 km wynosi +10,3 dB (anteny na 30 m i 1,5 m), +3,7 dB (10 m i 1,5 m) i +7,5 dB (10 m i 3 m); przy instalacji stałej +7,3, +0,7 i +4,5 dB. To mediany, bez zapasu na zaniki ([antena i budżet łącza](#antena-i-budżet-łącza)); o zasięgu rozstrzygają pomiary w krokach 3 i 5 oraz T5.

Model ruchu w SF7: 50 zgłoszeń przez przekaźnik zajmuje 16,4–17,2 min nadawania z 30 min; z PRZECZYTANE i decyzją (dwa STATUS) 31,5 min; próba ruchu mieszanego 55 rewizji około 34,6 min z 60. Pojemność: przekaźnik przed stanowiskiem około 95 zgłoszeń/h, stacja stanowiska około 164/h.

SF8 daje 2 dB czułości więcej (−126 dBm), ale 50 zgłoszeń zajmuje 29,1–30,4 min, więc W10 nie mieści się w 30 min, a próba mieszana trwa około 61,6 min z 60. SF8 nie jest więc profilem stacji.

Odbiornik SX1262 pobiera w modelu 4,6 mA, w trybie ze wzmocnieniem 5,3 mA, czyli o 0,7 mA więcej, poniżej 2% dopuszczalnego poboru dla W23. Przy założeniach przetwornicy z [projektu zasilania](../../hardware/r02/zasilanie.md) komplet ogniw AA Li-FeS2 daje ESP32-S3 około 70, 52 i 41 h przy 30, 45 i 60 mA poboru MCU. W23 (≥48 h) wymaga więc średnio najwyżej około 49 mA MCU (przy 45 mA model daje 52 h). Tor zasilania płytki v2 jest inny ([elektronika](elektronika.md#zasilanie-stacji)), więc o W23 rozstrzyga pomiar 48 h z minimum pilotażu, nie model.

## Radia RNode

Radia RNode są wzorcem profilu i narzędziem kroków 2, 3 i 5 ([koncepcja, rozdział 08](../concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)). To dwa zestawy RAK19007 z RAK4631 (nRF52840 i SX1262) z oficjalnym firmware RNode, podłączone przez USB do laptopów z Reticulum w Pythonie. Firmware wgrywa `rnodeconf --autoinstall` (opcja RAK4631, pasmo 779–928 MHz; autor RNode oznacza tę płytkę jako eksperymentalną). Przy odbiorze zestawów sprawdza się, że to wersja na pasmo 868 MHz.

Interfejs w konfiguracji Reticulum (`~/.reticulum/config`) ustawia profil z tabeli wyżej i kod dostępu sieci:

```ini
[[WICI LoRa]]
  type = RNodeInterface
  enabled = yes
  port = /dev/ttyACM0
  frequency = 869525000
  bandwidth = 125000
  spreadingfactor = 7
  codingrate = 5
  txpower = 13
  network_name = <nazwa sieci próby>
  passphrase = <hasło sieci próby>
  ifac_size = 128
  airtime_limit_long = 10
```

- `ifac_size` podaje się w bitach: 128 b to 16 B, jak w stacji. Bez tego wiersza RNode używa 8 B i nie wymienia ramek ze stacją.
- `txpower` ustawia moc układu; moc na złączu RAK4631 przy tej nastawie potwierdza pomiar w kroku 2, zanim radio wyjdzie w teren.
- RNode nie zna ciszy 12t. `airtime_limit_long = 10` ogranicza długookresowy udział nadawania do 10%. Limit liczy firmware RNode, nie Reticulum (`RNodeInterface` tylko przekazuje wartość): okno ma 3600 s (`AIRTIME_LONGTERM` w [`Config.h`](https://github.com/markqvist/RNode_Firmware/blob/master/Config.h), sprawdzone 2026-10-30), czyli tyle, ile okres obserwacji cyklu pracy w paśmie. Zachowanie po przekroczeniu i moc RAK4631 przy `txpower = 13` sprawdza się w kroku 2. W pomiarach zasięgu ruch jest mały (`rnprobe` co kilka sekund), więc limit pasma ma zapas.
- Do porównania SF8 zmienia się tylko `spreadingfactor` na obu radiach.

Próba przy stole (krok 2): oba laptopy widzą nawzajem swoje ogłoszenia (`rnstatus`, `rnpath`), a `rnprobe` przechodzi w obie strony. Wynik zapisuje się w raporcie z wersjami Reticulum i firmware RNode. Raport kroku 3 i procedura kroku 5 używają tej samej konfiguracji ([odbiór](odbior.md#próby)).

## Współdzielenie kanału

Częstotliwość 869,525 MHz jest środkiem kanału RX2 LoRaWAN w Europie (125 kHz, bramki nadają tam odpowiedzi z mocą do 500 mW ERP) oraz domyślną częstotliwością sieci Meshtastic w regionie EU_868, zajmującej całe podpasmo 869,4–869,65 MHz. CAD widzi tylko preambuły LoRa o tym samym SF i szerokości pasma, więc ramki Meshtastic i LoRaWAN o innych parametrach mogą zakłócać odbiór ramek WICI, choć kanał wygląda na wolny. Pobliska bramka LoRaWAN (do 27 dBm ERP) może w promieniu setek metrów blokować odbiornik stacji; T5 obejmuje pomiar RSSI tła i blokowania w pobliżu znanej bramki.

W kroku 5 radio RNode w profilu WICI i drugie urządzenie w lokalnym presecie Meshtastic zapisują zajętość kanału: pierwsze widzi ramki o tym samym SF i szerokości pasma, czyli to, co odracza CAD, drugie ruch, który może zagłuszyć ramki WICI. Mierzy się też tło szumowe (RSSI bez nadawania), także przy włączonym zasilaniu awaryjnym obiektu (UPS, przetwornice, falowniki PV). W pilotażu (T5) zajętość podpasma mierzy się w każdym miejscu przez ≥2 tygodnie w różnych porach doby, a stacje zapisują liczniki CAD, odroczeń i błędów CRC. Wstępny próg istotnego zajęcia podaje D11. Pierwszą ocenę ruchu dają publiczne statystyki społeczności (np. lorastats.pl dla Warszawy).

Gotowej częstotliwości zapasowej nie ma: kanał 125 kHz mieści się w podpaśmie 869,40–869,65 MHz tylko ze środkiem w 869,4625–869,5875 MHz, a każdy taki kanał pokrywa kanał RX2 LoRaWAN (869,4625–869,5875 MHz). Ucieczka od RX2 oznacza więc węższą szerokość pasma (dłuższy czas nadawania i ponowne przeliczenie W10) albo inne podpasmo z innymi limitami mocy i cyklu pracy. Węższy kanał nie omija ruchu Meshtastic (250 kHz, całe podpasmo); od niego uciec można tylko do innego podpasma. Zmiana kanału jest nową wersją profilu dla całej sieci (decyzja D11, przed wdrożeniem; [plan](../concept/08-plan-weryfikacji-i-decyzje.html)).

## Dostęp do kanału

1. Cały ruch, w tym ogłoszenia i pakiety przekazywane, przechodzi przez jeden licznik czasu TX.
2. Przed nadaniem datagramu zapisuje się w pamięci nieulotnej dług ciszy równy dwunastokrotności zarezerwowanego czasu nadawania. Błąd zapisu blokuje nadawanie.
3. Ramki datagramu wysyła się jedną serią. Następnie odczekuje się zapisany dług ciszy. Przy ruchu ciągłym daje to około 7,7% czasu nadawania, z rezerwą względem limitu 10%.
4. Po ponownym uruchomieniu odczekuje się cały ostatni zapisany dług. Kasuje się go dopiero po odczekaniu; restart nie zeruje budżetu.
5. Przed serią kanał musi być wolny przez 50 ms; kanał jest zajęty, gdy RSSI przekracza próg albo CAD wykrył preambułę i trwa odbiór. Gdy kanał jest zajęty, nadawanie zostaje odroczone o losowy czas 100–1000 ms; licznik długich odroczeń trafia do diagnostyki. Sprawdzenie kanału nie zastępuje limitu czasu TX. CAD wykrywa preambuły poniżej poziomu szumu, ale nie sygnały FSK ani LoRa o innym SF; próg RSSI i liczbę symboli CAD wyznacza się w T4.
6. **Podział czasu kanału.** Czas kanału to czas nadawania wraz z jego długiem ciszy (13t na serię), liczony w przesuwnym oknie 3600 s. Stacja dzieli nadawane pakiety na trzy klasy:
   - **K0:** własne pakiety stacji, dowody pakietów (potwierdzenia), zapytania o trasę i odpowiedzi na nie. Dwa osobne limity:
     - przekazywane zapytania o trasę: najwyżej 1 na cel na 60 s i łącznie ≤5% czasu kanału; ponad limit są odrzucane i liczone;
     - odpowiedzi na zapytania o trasę (własne i przekazywane): łącznie ≤5% czasu kanału; ponad limit są odrzucane bez odkładania (pytający ponawia) i liczone. Bez tego węzeł z kluczem sieci mógłby zalać stację zapytaniami i zająć kanał odpowiedziami przed K1. Reticulum odpowiedzi nie ogranicza; wartość do pomiaru na płytce;
   - **K1:** przekazywane pakiety danych do przypiętego odbiorcy (adres docelowy to aktywna tożsamość odbiorcy z karty); w konfiguracji węzła stanowiska pakiety do celów osiągalnych przez interfejs USB i pakiety z tego interfejsu;
   - **K2:** pozostałe przekazywane pakiety danych (liczba przeskoków większa od zera), także RECEIVED, STATUS, REPLY i BULLETIN od odbiorcy do innych stacji, bo przekaźnik nie odróżni ich od cudzego ruchu (w nagłówku jest tylko adres docelowy).

   K2 zajmuje łącznie z ogłoszeniami (niżej) najwyżej 60% czasu kanału w oknie. Pakiet K2 ponad ten limit stacja odrzuca przed kolejką i liczy w diagnostyce. Ostatnie wolne miejsce w kolejce radiowej stacja zostawia dla K0 i K1; pakiet K2 go nie zajmuje. Drugi limit, 25% czasu kanału dla jednego celu w K2, działa tylko wtedy, gdy w kolejce radiowej czeka pakiet K0 lub K1. Bez takiej rywalizacji jeden cel może zająć cały limit K2. Do schronienia za przekaźnikiem płyną wszystkie odpowiedzi odbiorcy: w próbie „Odpowiedzi dyżurnego” około 26% czasu kanału, przy pełnym ruchu mieszanym około 50%. Dzięki temu schronienie nie traci odpowiedzi, a zalew jednym celem nie wypiera ruchu do odbiorcy.

   Ogłoszenia (własne i przekazywane) mają limit 2% czasu zegarowego liczony z czasu nadawania ([ogłoszenia](oprogramowanie.md#tryby-kryzysowe)); z długiem ciszy to do 26% czasu kanału. Ich czas kanału wlicza się do tej samej puli co K2: **K2 i ogłoszenia razem zajmują najwyżej 60% czasu kanału w oknie**. Ogłoszenie ponad ten limit czeka w kolejce ogłoszeń interfejsu radiowego stacji i nie jest odrzucane. Limit `announce_cap` Reticulum tej puli nie widzi.

   K0 (poza limitami zapytań o trasę i odpowiedzi na nie) i K1 nie mają limitu. Gwarancja brzmi więc: w każdym oknie 3600 s co najmniej 40% czasu kanału pozostaje dla K0 i K1, także przy zalewie ruchem obcym i pełnym limicie ogłoszeń. Udział zapewnia limit, a kolejność w kolejce radiowej skraca oczekiwanie: najpierw dowody pakietów i zapytania o trasę (bez trasy dane nie wyjdą), potem dane K0 i K1, potem dane K2, na końcu ogłoszenia ([kolejność w kolejce](oprogramowanie.md#wysyłanie)). Pakiet K0 lub K1 czeka więc najwyżej na:

   - zakończenie bieżącej serii i jej długu ciszy (≤13 × 0,82 s ≈ 10,7 s);
   - dowody, zapytania o trasę i wcześniejsze pakiety K0 i K1 w kolejce;
   - odroczenia przy zajętym kanale.

   W modelu ruchu mieszanego przekaźnik przed stanowiskiem przy pełnym obciążeniu nadaje w K2 około 51% czasu kanału, a ogłoszenia co 6 h dodają poniżej 1%, więc pula 60% nie ogranicza ruchu w modelu. Przy zimnym starcie sieci ogłoszenia zajmują do 26%. RECEIVED dla TEST startowych przekazywane w K2 zajmują dla 50 stacji 50 × 6,2 s ≈ 5,2 min, około 9% godziny przekaźnika. Razem z ogłoszeniami daje to około 35%, poniżej puli. T5 sprawdza progi na zmierzonym ruchu.

Rezerwacja obejmuje preambuły, nagłówki, CRC oraz zmierzony czas narastania mocy i przełączenia nadajnika dla każdej ramki. Model przyjmuje ten czas jako parametr (`ramp_ms`), a dowód limitu 10% opiera się na wartości zmierzonej. Dług zapisuje się przed pierwszą ramką serii. Znacznik zatwierdzenia zapisuje się na końcu zapisu. Zanik zasilania w trakcie zapisu zostawia więc poprzedni poprawny rekord, a nadanie bez zatwierdzonego długu nie następuje ([zanik zasilania](elektronika.md#zanik-zasilania-i-zapis)). Dług przechowuje dziennik w pamięci FRAM stacji, tej samej co kolejka zgłoszeń. Każdy rekord zawiera numer, dług, CRC i znacznik zatwierdzenia. Dziennik utrzymuje co najmniej dwa poprawne rekordy. W najgorszym przypadku, przy ciągłym nadawaniu najkrótszych datagramów, zapis następuje co 0,65 s, czyli około 133 000 razy na dobę. Trwałość FRAM (co najmniej 10¹³ cykli według kart katalogowych obu układów) nie ogranicza czasu pracy, więc rozkładanie zapisów nie jest potrzebne. Dziennik długu ciszy nie jest szyfrowany i przetrwa ZNISZCZ DANE. Gdy przy starcie brak poprawnego rekordu, stacja odczekuje największy możliwy dług, zakłada nowy dziennik i zlicza zdarzenie w diagnostyce. Nadawanie nie czeka na diagnostykę. Największy możliwy dług to 12 × czas TX największego datagramu z narastaniem mocy, 12 × 0,82 s ≈ 10 s. Odbiór pozostaje czynny także podczas długu ciszy i oczekiwania na wolny kanał. Stacja jest przekaźnikiem, więc odbiór wyłącza się tylko na czas własnego nadawania.

## Warunki prawne i zgodność

Warunki UE w tym paśmie obejmują do 500 mW ERP i profil z aktywnością do 10% (pasmo h1.4 według ERC/REC 70-03, [Decyzja UE 2025/105](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32025D0105)); przed użyciem w Polsce trzeba jeszcze potwierdzić warunki krajowe (D11) oraz emisje gotowego urządzenia. Sama częstotliwość nie oznacza dopuszczenia nadajnika.

Praca stacji pilotażowych w terenie to oddanie do użytku w rozumieniu dyrektywy RED 2014/53/UE (D20). Zespół jest producentem konfiguracji pilotażowej: płytki v2 z modułami, programu stacji, anteny zewnętrznej, profilu LoRa i wyłączonego Wi-Fi i Bluetooth. Konfigurację bada się według norm zharmonizowanych przed pracą w terenie; deklaracje producentów modułów pomagają, ale nie zastępują badań. Gmina używa stacji wyłącznie jako wyrobów z deklaracją zgodności UE producenta; samodzielne złożenie stacji przez gminę lub wolontariuszy czyni ich producentem ze wszystkimi obowiązkami.

Wykaz do badań i deklaracji zgodności:

- EN 300 220-2 w aktualnej wersji: widmo radiowe, cel: kategoria odbiornika 1,5. T4 mierzy na poziomach tej kategorii blokowanie i selektywność kanału sąsiedniego. Mierzy też czułość przy PER ≤1% w obecności CW −30 dBm na 862 i 880 MHz (poziom do potwierdzenia wobec telefonu w odległości 1 m); emisje niepożądane obejmują 2. i 3. harmoniczną (1739 i 2609 MHz);
- EN 301 489-1 i -3: kompatybilność elektromagnetyczna;
- EN 62368-1: bezpieczeństwo; EN 62479: ekspozycja na pole;
- rozporządzenie delegowane (UE) 2022/30 i normy zharmonizowane EN 18031-1 i -2:2024 (art. 3 ust. 3 lit. d i e RED, cyberbezpieczeństwo), stosowane od 1 sierpnia 2025; normy opublikowano decyzją wykonawczą (UE) 2025/138 z ograniczeniami w załączniku I;
- RoHS (EN IEC 63000), WEEE (dla wszystkich modułów zestawu) oraz rozporządzenie bateryjne (UE) 2023/1542;
- maksymalny deklarowany zysk anteny 6 dBi, wpisany do deklaracji i karty stacji.

Nadajniki Wi-Fi i Bluetooth ESP32-S3 są w pilotażu wyłączone programowo, ale radio 2,4 GHz wyłączone tylko w oprogramowaniu może być nadal traktowane jako zamierzony nadajnik. Sposób wyłączenia rozstrzyga się przed badaniami konfiguracji pilotażowej (D20), bo od niego zależy zakres badań. Opcje (D14): (a) trwała blokada (eFuse albo konfiguracja startowa), bezpieczny rozruch (secure boot) i pisemna argumentacja RED; (b) badania według EN 300 328 i EN 301 489-17; (c) w wyrobie MCU bez radia, np. RP2350 albo STM32U5.

Poziom 3 używa kupionej stacji zasilania i ładowarki USB z deklaracją zgodności UE producenta ([elektronika](elektronika.md#poziom-3-kupiona-stacja-zasilania)); WICI nie jest ich producentem.

## Interfejs radiowy w stosie Reticulum

Interfejs LoRa jest interfejsem Reticulum w stosie stacji. Przyjmuje datagram tylko wtedy, gdy kolejka radiowa na 4 datagramy ma wolne miejsce; inaczej zgłasza stosowi zajętość, a odrzut liczy w diagnostyce. Odrzut nie może potwierdzić zgłoszenia. Stos zna dług ciszy i przewidywany czas oczekiwania kolejki radiowej i uwzględnia je w limitach czasu i ponowieniach. Interfejs deklaruje stosowi jawną przepływność i osobny limit ogłoszeń. Każdy pakiet niesie kod dostępu sieci (IFAC Reticulum, 16 B) ustawiany przy przygotowaniu; pakiety bez poprawnego kodu są odrzucane przed przetwarzaniem. Zgodność IFAC i formatu ramek z RNode potwierdzają wektory z Reticulum w Pythonie i T3 z radiem RNode. Tryb ciszy radiowej blokuje w interfejsie każde nadawanie, także ruchu przekazywanego; interfejs ma osobną flagę dla pojedynczego zgłoszenia wyjętego spod ciszy.

Znajomość długu ciszy nie zmienia limitów czasu całego stosu. Osobno trzeba sprawdzić wyszukiwanie trasy i potwierdzenia, także gdy pakiet czeka za ruchem przekazywanym (łącza i zasoby Reticulum nie występują w sieci WICI); zob. [kontrprzykład czasowy i stan przeglądu](../review.md). Wszystkie stacje sieci, także stacja stanowiska, używają tego samego programu stacji. Komputer stanowiska używa implementacji Reticulum i LXMF w Pythonie (D19), więc zgodność z nią, sprawdzana w T3, jest warunkiem działania sieci. Próba „wrogi węzeł” (zalew ogłoszeniami, zapytaniami o trasę i pakietami K2) należy do T3 i T5; natężenie, czas i kryteria są w [odbiorze](odbior.md#próby).

### Ponowienia i limity prób

Odstęp ponowienia wiadomości okazjonalnej LXMF wynosi co najmniej max(60 s, 2 × liczba skoków × 13 × czas TX największego datagramu + bieżący dług ciszy + czas opróżnienia kolejki radiowej). Na pustej sieci potwierdzenie przez jeden przekaźnik wraca po kilku sekundach, ale przy kolejce i długu ciszy po ponad minucie; zbyt wczesne ponowienie podwaja ruch i łamie W10.

| Przypadek (SF7, datagram 508 B: 0,82 s) | Odstęp |
|---|---|
| pusta sieć, 1 lub 2 skoki | 60 s |
| 1 skok, największy dług i pełna kolejka 4 datagramów | około 74 s (21,3 + 9,8 + 42,6 s) |
| 2 skoki, największy dług i pełna kolejka | około 95 s |

| Nadawca | Próby LXMF na jedno ponowienie intencji | Odstęp prób | Ponowienia intencji |
|---|---|---|---|
| stacja schronienia (rdzeń Reticulum stacji z LXMF) | ≤2 | według tabeli wyżej | [wysyłanie](oprogramowanie.md#wysyłanie): po FAILED po 1, 2 i 5 min, potem co 15 min, każdy odstęp ±20%, od 6 h co 60 min ±20%; po DELIVERED bez RECEIVED po 10 min, potem co losowe 30–60 min (`firmware/src/station.cpp`, `retryDelayS`) |
| aplikacja stanowiska (LXMF w Pythonie, `c3ff2d6`) | 3: najmniejsza liczba, jaką LXMF w Pythonie stosuje przy odstępie ponad 10 s; mniej wymagałoby zmiany kodu stosu (D19) | ≥196 s przy `bitrate` ≤42 b/s interfejsu KISS | według [stanowiska odbiorczego](stanowisko-osp.md#komputer-i-aplikacja-stanowiska), dla RECEIVED, STATUS, REPLY i BULLETIN |

Domyślny LXMF w Pythonie wykonuje do 5 prób co 10 s (`MAX_DELIVERY_ATTEMPTS`, `DELIVERY_RETRY_WAIT`). Gdy szacowany czas obiegu przekracza 10 s, liczba prób spada do max(3, round(50 / czas obiegu)), ale nigdy poniżej 3, a odstęp rośnie do czasu obiegu = 2 × max(limit pierwszego skoku − 6 s, 0) + 6 s, gdzie limit pierwszego skoku = 500 × 8 / przepływność interfejsu + 6 s. Przy przepływności zgłaszanej przez interfejs (LoRa SF7 około 5,5 kbit/s, domyślny interfejs KISS 1,2 kbit/s) daje to 3–5 prób co 10–13 s, czyli nadania szybsze od potwierdzeń.

**Kryterium `bitrate`** (jedyna definicja; [stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska) do niej odsyła): aplikacja stanowiska ustawia w interfejsie KISS niską przepływność `bitrate`, tak by 500 × 8 / `bitrate` nie było krótsze od odstępu z tabeli dla 2 skoków (około 95 s) ani od najdłuższego czasu powrotu potwierdzenia przez interfejs radiowy zmierzonego w T3. Z tabeli wychodzi `bitrate` ≤42 b/s (4000 / 95 ≈ 42,1); dłuższy zmierzony czas obniża tę wartość. Pełny limit pierwszego skoku (z dodatkowymi 6 s) ma wtedy zapas. Odstęp prób LXMF wynosi przy 42 b/s około 196 s, liczba prób spada do 3, a trzecia próba wychodzi po około 6,5 min, gdy pierwsze potwierdzenie na pewno nie wróciło. Stacja schronienia ma 2 próby, bo rdzeń stacji ma własną implementację LXMF i limit ustawia się w niej wprost; różnica dotyczy tylko liczby nadań wiadomości, której potwierdzenie zaginęło. T3 sprawdza, jako warunek utrzymania D19, czy sama konfiguracja `bitrate` wystarcza, by aplikacja stanowiska nie ponawiała przed powrotem potwierdzenia.

## Interfejs Reticulum przez USB (węzeł stanowiska)

Stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)) ma w stosie drugi interfejs Reticulum: interfejs danych CDC poza trybem przygotowania przenosi pakiety Reticulum do komputera stanowiska i z powrotem. W trybie przygotowania ten sam interfejs przenosi [protokół USB](oprogramowanie.md#protokół-usb-laptopstacja), aby można było zmienić konfigurację i oprogramowanie.

- **Ramki:** KISS (FEND, FESC), jedna ramka danych to jeden pakiet Reticulum do 500 B; zgodne z interfejsem KISS Reticulum w Pythonie z kontrolą przepływu. Polecenia konfiguracji KISS od komputera (TXDELAY, P, SLOTTIME, TXTAIL) stacja przyjmuje i pomija, bo dostęp do kanału określa interfejs radiowy stacji.
- **Kontrola przepływu:** komputer włącza ją przy starcie poleceniem KISS 0x0F z wartością 1. Stacja wysyła ramkę gotowości (0x0F, jak RNode) po przyjęciu pakietu do bufora USB na co najmniej 8 pakietów po 500 B; komputer wysyła następny pakiet dopiero po niej. Reticulum w Pythonie (`e40191b`) sam zwalnia blokadę po 5 s bez gotowości (stała `flow_control_timeout` interfejsu KISS), więc wstrzymanie gotowości nie zatrzyma komputera na czas długu ciszy. Pakiet ponad bufor stacja odrzuca i liczy, a ponowienie zapewnia LXMF; aplikacja stanowiska ogranicza ruch do 4 wiadomości w drodze, aby bufor wystarczał.
- **Kierunek do komputera:** stacja przekazuje pakiety, które transport kieruje do interfejsu USB: ruch do tożsamości odbiorcy, ogłoszenia i zapytania o trasę. Zakodowane ramki czekają w buforze 1 KiB; stacja oddaje portowi tyle, ile przyjmie, bez czekania w pętli pracy, i usuwa z bufora tylko bajty przyjęte (zapis częściowy nie ucina ramki). Komputer, który nie czyta, traci tylko pakiety ponad bufor (liczone), a ponowienie zapewnia LXMF; przekazywanie przez radio działa dalej.
- **Limity:** pakiety z USB przechodzą przez interfejs radiowy z jego priorytetami, długiem ciszy, limitem ogłoszeń i ciszą radiową. IFAC dotyczy tylko interfejsu radiowego; pakiet z USB dostaje kod dostępu sieci przy nadaniu, a pakiet z radia bez poprawnego kodu nie trafia do komputera. W konfiguracji węzła stanowiska klasa K1 z punktu 6 w [dostępie do kanału](#dostęp-do-kanału) obejmuje pakiety do celów osiągalnych przez interfejs USB i pakiety z tego interfejsu, bo stacja nie ma karty odbiorcy; ruch od odbiorcy do stacji schronień jest tu więc w K1, nie w K2.
- **Diagnostyka:** liczniki pakietów w obu kierunkach i czas od ostatniego pakietu od komputera (`komputer_osp` na ekranie, pola w `INFO` i `RNS`).

Ramki, polecenia i kontrolę przepływu sprawdzono w kodzie interfejsu KISS Reticulum `e40191b`; działanie ze stacją i wartość `bitrate` po stronie komputera ([kryterium](#ponowienia-i-limity-prób)) potwierdza T3. Interfejs przez USB nie jest dostępny w stacji schronienia.

## USB do laptopa

USB CDC ACM, przewód do 2 m. Prototyp używa złącza USB/OTG (natywnego USB) płytki ESP32-S3-DevKitC; złącze UART tej płytki nie służy do pracy. Prototyp na płytce v1 zasila się wyłącznie z USB. Płytka v2 ma własne gniazdo z liniami danych natywnego USB i bez VBUS ([elektronika](elektronika.md#gniazdo-usb-do-laptopa)). Stacja pilotażowa na płytce v2 nie zależy od zasilania z VBUS: pracuje z ogniw albo z 12 V, a odłączenie przewodu nie powoduje restartu ([elektronika](elektronika.md#zasilanie-stacji)). W pilotażu laptop łączy się ze stacją schronienia tylko w trybie przygotowania; stacja stanowiska pracuje z komputerem stanowiska stale. Wstrzymanie, uśpienie lub odłączenie hosta nie zmienia pracy stacji. Urządzenie ma dwa interfejsy CDC ACM, danych i diagnostyki (w ESP32-S3 przez USB-OTG i TinyUSB, nie USB-Serial-JTAG), z deskryptorami IAD (Interface Association Descriptor), aby Windows 10 i nowsze przypisały oba wbudowanemu sterownikowi bez instalowania dodatkowego. Identyfikatory VID/PID muszą zostać legalnie przydzielone projektowi przed wydaniem; nie wolno używać identyfikatorów cudzego urządzenia. Protokół danych między laptopem a stacją opisuje [specyfikacja oprogramowania](oprogramowanie.md#protokół-usb-laptopstacja).

Polecenie diagnostyczne na interfejsie diagnostyki: `INFO\n`; odpowiedź: jeden wiersz JSON zaczynający się od pól kontraktu, np. `{"contract":2,"profile":"LoRa","radio":"SX1262","mcu":"ESP32-S3","fw":"...","src":"AA","mv":5800,"tx_wait_ms":0,"rx_ok":0,"rx_bad":0,"tx_drop":0,"restarts":0}` (pola profilu i układu według `firmware/src/main.cpp` i `radio_console.h`). Dalsze pola diagnostyczne opisuje [oprogramowanie](../../firmware/README.md#polecenia); wiersz mieści się w limicie 1024 B interfejsu. Oprogramowania układowego nie aktualizuje się podczas uruchamiania stacji w schronieniu.

Polecenia pomiarowe na interfejsie diagnostyki działają wyłącznie w trybie przygotowania i służą próbom T4 na prototypie i stacji pilotażowej:

- `TXCW <s>` nadaje nośną bez modulacji przez ≤10 s (pomiar częstotliwości i mocy);
- `TXPKT <n> <len> [<ms>] [ZEROS|ONES]` nadaje `n` ramek o długości `len` B z numerem porządkowym w treści i odstępem `ms`, z wypełnieniem pseudolosowym albo z samych zer lub samych jedynek;
- `RX [<len>]` uruchamia odbiór ramek wzorcowych, a `STOP` przerywa serię;
- `RXPER` zwraca i zeruje liczniki ramek odebranych, z błędem CRC i brakujących numerów;
- `FOFF <Hz>` ustawia korektę częstotliwości do restartu;
- `EMC <s> <len>` włącza tryb pracy do badań EMC: ramka wzorcowa `len` B co `s` s, nie częściej niż co 13 × czas ramki (dług ciszy 12 × przed każdą ramką, bez sprawdzania kanału, jak `TXPKT`), i odbiór ramek wzorcowych między nimi.

Tryb EMC jako jedyny trwa po wyjściu z trybu przygotowania: zapisany w dzienniku FRAM wraca sam po restarcie, żeby badanie odporności pokazało powrót funkcji bez obsługi. Przez cały tryb stacja daje `radio_awaria`, bo zgłoszenia nie wychodzą. Kończy go `EMC 0` albo `STOP`. Odpowiedź: jeden wiersz JSON.

Limit czasu nadawania i cisza radiowa obowiązują także dla tych poleceń. Serię dłuższą niż limit dopuszcza tylko argument `conducted`. Jest on przeznaczony wyłącznie do nadawania przewodowego do tłumika lub obciążenia sztucznego, wymaga potwierdzenia przyciskiem OK na stacji w ciągu 30 s i jest zapisywany w dzienniku zdarzeń.

## Sprzęt do prób radia

Każdy krok planu ma swój sprzęt radiowy ([koncepcja, rozdział 08](../concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)):

- **radia RNode** (kroki 2, 3 i 5): profil, IFAC i pomiary zasięgu oraz zajętości kanału;
- **prototyp na płytce v1** (krok 4): program stacji z interfejsem LoRa, T3 z radiem RNode, wstępne pomiary T4 poleceniami pomiarowymi; moduł Wio ma własny tor RF, więc wyniki dotyczą tego modułu z przewodem i anteną prototypu;
- **stacja pilotażowa na płytce v2** (krok 6): moc, częstotliwość, czułość i emisje na złączu antenowym stacji w obudowie (T4, minimum pilotażu) oraz badania konfiguracji pilotażowej (D20).

Radia testowe z kroku 1 (XIAO ESP32-S3 z Wio SX1262, program radiowy `pair`) nie są narzędziem planu; nadawały przy 0 dBm ([wyniki](../../hardware/radio-pair/README.md)).

## Antena i budżet łącza

Nadajnik musi przetrwać nadawanie przy rozwartym i zwartym złączu antenowym, ponieważ odłączona lub uszkodzona antena to typowy błąd obsługi w terenie; sprawdza to T4.

Dipol pionowy: ramiona początkowo po 82 mm, symetryzacja dławikiem współbieżnym, przewód 50 Ω o łącznym tłumieniu ≤1 dB przy 869,5 MHz, łącznie ze złączami (np. 2 m LMR-240 lub H-155, około 0,25 dB/m). RG-58 ma przy tej częstotliwości około 0,55 dB/m i z dwoma złączami przekracza warunek już przy 2 m; RG-174 tym bardziej. Przy dłuższym przewodzie do anteny umieszczonej wyżej zysk z wysokości zwykle przeważa nad stratą. Budżet łącza przelicza się wtedy dla rzeczywistej instalacji: przewód zewnętrzny, odgromnik GDT (≤0,2 dB), przepust, przejściówki (≤0,1 dB każda) i przewód wewnętrzny. Model przyjmuje dla instalacji stałej 2,5 dB na każdym końcu (np. około 6 m LMR-240 z odgromnikiem i przejściami), obok 1 dB dla anteny przy oknie bez odgromnika. Długość końcowa po strojeniu: WFS (SWR) ≤2 w miejscu montażu.

Antena zewnętrzna jest zwarta dla prądu stałego (dipol pętlowy albo dipol ze zwierającym odcinkiem ćwierćfalowym). Przewód przy wejściu do budynku ma odgromnik gazowy (GDT) ze złączami N lub SMA, połączony z uziemieniem budynku. Przewody zewnętrzne mają złącza N, stacja złącze SMA-F. Złącza zewnętrzne uszczelnia się taśmą samowulkanizującą z warstwą odporną na UV. Smar silikonowy daje się tylko na gwint, nie na styk środkowy. Przewód schodzi do złącza od dołu z pętlą ociekową. Antena na zewnątrz nie jest montowana ani obsługiwana podczas burzy. Antenę umieszcza się poniżej krawędzi dachu; maszt na szczycie budynku wymaga oceny jego instalacji odgromowej. Ochrona ESD wyjścia RF nie zastępuje ochrony odgromowej.

Wariant anteny: kolinearna antena dookólna o zysku 5–6 dBi, w pionie. Na obu końcach łącza daje około 7 dB więcej niż dwa dipole, bez zmiany profilu. ERP rośnie do około 15,5 dBm, nadal poniżej limitu 27 dBm. Kosztem jest węższa wiązka w płaszczyźnie pionowej, więc antena musi stać pionowo i nie nadaje się do łącza o dużej różnicy wysokości na krótkim dystansie. Zysk anteny wpisuje się do raportu próby; nie może przekraczać deklarowanych 6 dBi.

Tłumienie swobodnej przestrzeni na 1 km wynosi około 91 dB, co przy 13 dBm, dwóch dipolach i 1 dB strat przewodu na każdym końcu daje około −76 dBm na złączu, czyli 45 dB zapasu względem −121 dBm. Model Okumury-Haty dla małego miasta daje jednak na 1 km 126–133 dB, a zapas spada do wartości z [profilu](#profil-lora-pilotażu): +10,3, +7,5 i +3,7 dB dla anten na 30 m i 1,5 m, 10 m i 3 m oraz 10 m i 1,5 m. To mediany: łącze, które ma przenieść 99 ze 100 zgłoszeń, potrzebuje dodatkowo około 10 dB zapasu na zaniki, a rozrzut tłumienia między miejscami sięga 6–8 dB. Promień pierwszej strefy Fresnela w połowie drogi wynosi około 9,3 m, więc anteny przy oknach niskich kondygnacji pracują zwykle bez widoczności. Cel 1 km w zabudowie wymaga więc wysoko umieszczonych anten lub przekaźników; zysk z większej mocy jest mały. Z dipolami ERP wynosi około 12 dBm (16 mW), około 15 dB poniżej limitu 500 mW. SX1262 daje do +22 dBm bez zewnętrznego wzmacniacza, ale większa moc wymaga nowego pomiaru emisji i nowego budżetu energii stacji, a zysk w zasięgu jest mały. Przy instalacji stałej (2,5 dB strat na każdym końcu) zapas spada o 3 dB: +7,3, +4,5 i +0,7 dB w modelu Okumury-Haty; ERP z dipolem wynosi wtedy około 10,5 dBm, a anteny kolinearne na obu końcach dodają około 7 dB. Obliczenia: [wyniki modelu](../../software/reference/wyniki.json). Nie wolno obiecywać zasięgu na podstawie samej czułości katalogowej.

## Archiwum

Profil P1 (parametry, wzorzec częstotliwości, ramka w eterze, interfejs P1 w stosie), warunki powrotu do P1, stanowiska deweloperskie A/B, dwa wykonania radia z filtrem SAW oraz porównania LoRa z P1 są w [archiwum radia](../archiwum/p1-radio.md).

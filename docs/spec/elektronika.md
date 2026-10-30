# WICI: elektronika

Stacja pilotażowa to płytka v2 z linii prototypu, z modułami w kupionej obudowie (krok 6 planu, [koncepcja, rozdział 08](../concept/08-plan-weryfikacji-i-decyzje.html#stacje-pilotazowe)). Płytka v2 powstaje z płytki v1 prototypu i dodaje tor zasilania z ogniw AA i z 12 V; poziom 3 zasila kupiona stacja zasilania (D05). Wcześniejsze wymagania własnej płytki R02, porównanie gotowych płytek z SX1262 i własny blok zasilania poziomu 3 są w [archiwum](#archiwum-płytka-r02-i-gotowe-płytki).

Podane wartości służą do projektu, wykonania i pomiaru stacji pilotażowej. Zamienniki innych producentów wymagają oddzielnego sprawdzenia tolerancji i nie zawsze mają zgodne wyprowadzenia. Schemat połączeń nie zastępuje projektu płytki drukowanej (PCB).

## Stacja pilotażowa

Płytka v2 to płytka v1 prototypu ([`hardware/dev-bench`](../../hardware/dev-bench/plytka-nosna.md), projekt v1.1 z poprawioną taśmą ekranu, F118) z trzema grupami zmian:

1. **wnioski z prototypu:** taśma ekranu z v1.1, rezystor R12 = 1 kΩ zamiast 10 kΩ; dalsze przyjdą z kroku 4;
2. **zmiany pod pilotaż:** bez gniazd na moduły TI, ST i Nordic (J1–J4, J9, J10, JP3), moduł Wio osadzony na płytce zamiast przewodów, obrys i otwory pod obudowę, własne gniazdo USB do laptopa bez linii VBUS ([USB do laptopa](#gniazdo-usb-do-laptopa));
3. **tor zasilania** z ogniw AA i z 12 V ([zasilanie stacji](#zasilanie-stacji)), którego wymaga minimum pilotażu.

Płytkę v2 zamawia się w pełni zmontowaną w JLCPCB (SMD i THT, części podstawowe montażowni; wycenę pełnego montażu sprawdzono w zamkniętym [PR #129](https://github.com/tmierzwa/WICI/pull/129)). Montaż mieszany w JLCPCB wymaga, żeby każdy pad SMD leżał co najmniej 2,5 mm od padu przewlekanego (od krawędzi do krawędzi miedzi). Na v1.1 tego nie spełniają R17–J3 (1,75 mm) i R18–J5 (1,96 mm); pozostałe pary mają ≥3 mm (pomiar wszystkich par na pliku płytki 2026-10-30). R17 i J3 wypadają z v2 razem z gniazdami Nordic, R18 przy gnieździe DevKitC zostaje do przesunięcia. Odstęp sprawdza się dla wszystkich par na projekcie v2 przed zamówieniem. Moduły (DevKitC, Wio, panel), obudowa, antena, program i próba każdej sztuki są poza montażownią. Zamówienie obejmuje 10 płytek, z których zmontowanych jest 8: sieć pilotażu 3, zapas w gminie 1–2, egzemplarz u autora 1, badania zgodności 1–2. Zasada: v2 nie zamyka drogi do wydania, ale nie dostaje niczego na zapas. Otwarta decyzja projektowa, do podjęcia po kroku 4: moduły wpinane jak w prototypie czy przylutowany moduł ESP32-S3 i układ radiowy na płytce. Złącze analizatora (J11), wejście VTEST (J12) i zworki pomiarowe v1 zostają albo wypadają według tej samej zasady; rozstrzyga projekt v2.

Konfigurację pilotażową (płytka, moduły, program stacji, antena, profil LoRa, wyłączone Wi-Fi i Bluetooth) zespół bada według norm zharmonizowanych przed pracą w terenie (D20, [radio](radio.md#warunki-prawne-i-zgodność)). Części i kandydaci są w [BOM stacji](bom-stacji.csv).

| Element | Wymaganie | Część (prototyp na v1; v2) |
|---|---|---|
| moduł MCU | ESP32-S3; flash 8 MiB (dwa gniazda obrazu po 3 MiB, [aktualizacja](oprogramowanie.md#aktualizacja-oprogramowania-stacji)); natywne USB-OTG ([dwa interfejsy CDC](radio.md#usb-do-laptopa)); PSRAM niepotrzebny, a zapas RAM liczy się bez niego | Espressif ESP32-S3-DevKitC-1-N8R8 rev. 1.1 w gniazdach J5/J6; obraz przyjmuje też wersje N8 i N8R2 |
| radio | SX1262 z TCXO, [profil LoRa](radio.md#profil-lora-pilotażu); zasilanie 3,3 V z płytki z punktem pomiaru prądu; 100 nF i 10 µF przy module; RXEN 10 kΩ do masy; złącze anteny u.FL i przewód do SMA-F w ściance obudowy | Seeed Wio SX1262 (z zestawu 102010611); w prototypie na adapterze przewodowym obok płytki ([zlecenie](../../hardware/l0-diagnostic/ZLECENIE.md)), w v2 osadzony na płytce |
| FRAM | SPI 4 Mbit (magazyny stacji zajmują około 413 KiB, [pamięć FRAM](oprogramowanie.md#pamięć-fram)), 3,3 V, zegar SPI ≥8 MHz, osobny CS, zasada [zaniku zasilania](#zanik-zasilania-i-zapis); rozpoznawana przez `src/fram_id.h` | U1: Infineon CY15B104QN-50SXI albo RAMXEED MB85RS4MTPF-G-BCERE1 (SOIC-8 208 mil, wspólny footprint; na płytkach v1 z JLC osadzono MB85RS4MTPF) |
| nadzór zasilania FRAM | CS pamięci zwolniony, zanim zasilanie spadnie poniżej minimum FRAM | U3 TI TPS3840PH27 (próg 2,7 V) i U4 bramka OR 74LVC1G32: CS = CS z MCU lub RESET nadzorcy |
| ekran | panel Sharp LS027B7DH01A 2,7" 400 × 240: złącze FPC 10 pin 0,5 mm, kondensatory według karty Sharp (LCP-1112041, rysunek 9-1); VDD i VDDA 4,8–5,5 V z przetwornicy 5 V zasilanej z 3,3 V; EXTMODE = H, EXTCOMIN z licznika sprzętowego MCU; wejścia logiczne bez translatora (VIH od 2,7 V przy 3,3 V) | Hirose FH12-10S-0.5SH(55); U2 Microchip MCP1640 z dzielnikiem 1 MΩ / 309 kΩ (4,90–5,36 V w najgorszym przypadku, [płytka v1](../../hardware/dev-bench/plytka-nosna.md#zasilanie)) |
| przyciski i przełącznik | GÓRA, DÓŁ, OK, WSTECZ (duże, w rękawicach), przełącznik CISZA z osłoną, przycisk przygotowania za otworem pod numerowaną naklejką serwisową | Omron B3F-4055 z nasadkami B32-1310, E-Switch 100SP1T1B4M2QE, Omron B3F-1000 |
| dioda alarmu i brzęczyk | sterowane z MCU; brzęczyk z szyny 5 V przez tranzystor | Kingbright WP7113ID; Same Sky CEM-1203(42) z kluczem MMBT3904 |
| zasilanie | ogniwa 4 × AA i wejście 12 V bez restartu przy przełączaniu ([zasilanie stacji](#zasilanie-stacji)) | do projektu v2 |
| obudowa | kupiona, IP40 lub lepsza, z przepustem anteny i 12 V, z odciążeniem przewodów; koszyk 4 × AA dostępny bez narzędzi | wymiary z przymiarki prototypu ([obudowa](../../hardware/obudowa/README.md)) |
| antena | zewnętrzna 868 MHz, zysk ≤6 dBi, zwarta dla prądu stałego, z odgromnikiem przy wejściu do budynku | [antena i budżet łącza](radio.md#antena-i-budżet-łącza) |

Stacji pilotażowej używa się tylko w temperaturach dopuszczonych przez karty wszystkich modułów, ogniw i ekranu (zwykle od 0 °C dla modułów z elektrolitem, −20 °C dla panelu). Miejsce chłodniejsze wymaga wcześniejszej próby w tej temperaturze.

## Zasilanie stacji

Tor zasilania jest jedyną nową częścią elektroniki v2. Wymagania wynikają z minimum pilotażu ([odbiór](odbior.md#minimum-pilotażu)): ≥48 h na ogniwach AA w temperaturze pokojowej, podłączenie 12 V bez resetu, brak utraty zgłoszeń przy wyjęciu ogniw.

```text
4 × AA Li-FeS2 ─ koszyk z kluczowaniem ─ D1 ──────────────────────┐
                                                                  ├─ VSYS ─ C ─ przetwornica 3,3 V (EN ← ON) ─ piny 3V3 płytki DevKitC
12 V ─ F T1A ─ TVS 33 V ─ łącznik 12 V (UV 11,5/12,4 V, OVP 17 V) ┘
sterownik wyłącznika (zasilany przez diody z AA i z 12 V za łącznikiem) ─ ON;  INT ─ MCU;  MCU ─ KILL
dzielniki AA i 12 V (odłączane) ─ ADC
```

Schemat pokazuje funkcje, nie układy. Architektura (decyzja z 2026-10-30): jak w [projekcie zasilania R02](../../hardware/r02/zasilanie.md), ogniwa przez diodę i 12 V przez łącznik na wspólną szynę VSYS, jedna przetwornica podwyższająco-obniżająca 3,3 V podłączona do pinów 3V3 i G płytki DevKitC. Instrukcja płytki dopuszcza zasilanie przez 3V3 i G jako jeden z trzech sposobów, które się wykluczają ([instrukcja DevKitC-1 v1.1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)). Płytki DevKitC nie przerabia się.

Odrzucony wariant: dwie przetwornice 5 V z diodami na pin 5V płytki. Regulator liniowy płytki (SGM2212-3.3) traci wtedy około jednej trzeciej energii i szacunek dla 45 mA poboru MCU spada z około 52 h do około 45 h, poniżej W23; kandydaci byli tylko modułami Pololu, których montażownia nie osadza.

Przed schematem v2:

1. **pobór przez 3V3 bez USB, pomiar na jednej płytce DevKitC.** Napięcie 3,3 V trafia przez R24 (0 Ω) także na wyjście regulatora płytki. Karta SGM2212 (rew. A.2) nie opisuje zachowania przy napięciu wyjścia wyższym od wejścia; prąd wsteczny zatrzymują dalej diody D1 i D7 ([schemat v1.1](https://dl.espressif.com/dl/schematics/SCH_ESP32-S3-DevKitC-1_V1.1_20221130.pdf)). Gdyby pobór był istotny wobec W23, R24 się usuwa;
2. **sprawność LTC3115-1 przy 3,3 V** na płytce ewaluacyjnej (Z11 w projekcie zasilania): model liczy 85%, wykresy dają około 82–85%, co przy 82% daje około 50 h;
3. **wejście 12 V odporne na 24 V.** Względem projektu R02 (TVS 18 V, części za nim do 30–40 V) v2 zmienia trzy rzeczy: TVS SMBJ33CA zamiast SMBJ18CA, łącznik LM74800-Q1 (praca 3–65 V, odwrotna polaryzacja do −65 V, [LM7480-Q1](https://www.ti.com/product/lm7480-q1)) z tranzystorami ≥60 V zamiast BUK7Y12-40E, bo przy odciętym łączniku widzą pełne napięcie wejścia z impulsem do 53,3 V, oraz zasilanie sterownika wyłącznika (LTC2955, praca do 36 V), nadzorcy UV i logiki tylko z 12 V za łącznikiem albo z ogniw. Przed łącznikiem zostają tylko bezpiecznik, TVS, łącznik i dzielnik pomiaru;
4. **dostępność LTC3115-1** w LCSC: sprawdzona 2026-10-30, jest na stanie tylko w puli extended (LTC3115EFE-1#PBF C580689, TSSOP-20; LTC3115EDHD-1#PBF C580688, DFN-16). W puli basic JLC nie ma przetwornicy podwyższająco-obniżającej tej klasy (jest tylko MC34063). Przed zamówieniem stan sprawdza się ponownie; przy braku inna przetwornica 3,3 V tej klasy (TPS63070 odpada z powodów opisanych w projekcie zasilania).

Części wejścia 12 V w LCSC (sprawdzone 2026-10-30): LM74800QDRRRQ1 C3215600 (extended); tranzystory AO4264E C334232 (60 V, 9,8 mΩ, SOIC-8, pula basic), zapasowo BUK7Y15-60EX C549911 (LFPAK56, extended); TVS SMBJ33CA C19077587 (pula promocyjna, bez opłaty za podajnik), zapasowo Littelfuse C83325. W puli basic nie ma TVS 33 V. Tranzystor 60 V ma wobec impulsu 53,3 V zapas około 11%; jeśli pomiar przy podłączaniu przewodu pokaże przerzut ponad ograniczenie TVS, wybiera się tranzystor 80–100 V.

| Element | Wymaganie | Kandydaci do projektu v2 |
|---|---|---|
| ogniwa | 4 × AA Li-FeS2 1,5 V (wymagane do przechowywania i do W23); alkaliczne lub NiMH tylko awaryjnie; koszyk z kluczowaniem przeciw odwrotnemu włożeniu; ogniwa ani wejście 12 V nie łączą się z VBUS ani z ładowarką modułu | Energizer L91 |
| przetwornica z ogniw | wejście co najmniej 3–8 V (4 × Li-FeS2: do 7,3 V świeże, około 4,0 V na końcu, minus spadek diody), wyjście ≥0,5 A, prąd spoczynkowy ≤0,2 mA, wejście EN | ADI LTC3115-1 |
| przetwornica z 12 V | wejście co najmniej 10–20 V (akumulator przy ładowaniu do 14,8 V i przepięcia), wyjście ≥0,5 A, prąd spoczynkowy ≤0,1 mA, wejście EN | wspólna przetwornica LTC3115-1 za łącznikiem 12 V TI LM74800-Q1 z dwoma Nexperia BUK7Y12-40E |
| diody | Schottky ≥1 A; dioda wejścia 12 V VR ≥40 V (odwrotna polaryzacja), dioda ogniw VR ≥20 V i mały prąd wsteczny przy 16 V i 45 °C, bo płynie do pierwotnych ogniw litowych | np. SS14, SS54; suma diodowa sterownika: Nexperia BAS116H |
| wybór źródła | przy obecnym 12 V (za odcięciem UV) ogniwa nie oddają energii i nigdy jej nie dostają | suma diodowa jak w projekcie zasilania |
| odcięcie UV 12 V | wyłącza zasilanie z 12 V poniżej 11,5 V, włącza powyżej 12,4 V (histereza, bez stanu zapamiętanego w MCU); oba progi mierzone na złączu, przed diodą, bo spadek na niej (około 0,3 V) przesunąłby je do 11,8/12,7 V i pełny akumulator w spoczynku (12,6 V) nie uruchomiłby stacji; pobór ≤50 µA | nadzorca napięcia z histerezą na EN; TI TPS3701 albo ADI LTC2965 |
| sterownik wyłącznika | krótkie naciśnięcie włącza, przytrzymanie 2 s zgłasza MCU żądanie wyłączenia (`wylaczanie`, potem `mozna_wyjac`, KILL), przytrzymanie ≥5 s wyłącza bez MCU; KILL w stanie wysokim najpóźniej 304 ms po włączeniu; zasilanie przez diody z obu źródeł | ADI LTC2955-2 z tranzystorem PMOS jak w projekcie zasilania |
| kondensator szyny | przełączenie z 12 V na ogniwa (start przetwornicy z ogniw) bez restartu modułu; mały upływ, bo szyna wisi na ogniwach | według [projektu zasilania](../../hardware/r02/zasilanie.md) |
| wejście 12 V | 11,5–16 V w pracy. Od 17 V do 33 V w sposób ciągły (instalacja 24 V wozu strażackiego albo ciężarówki, ładowanie 28,8 V, uszkodzony regulator alternatora) łącznik odcina wejście bez uszkodzeń, stacja pracuje z ogniw, a ekran pokazuje `za_wysokie_12v`; po spadku poniżej progu OVP wejście wraca samo. Odwrotne podłączenie do 33 V przez 60 s bez przepalenia bezpiecznika i uszkodzeń. Impulsy z instalacji pojazdu ogranicza TVS. Ochrona nie zależy od zakazu w instrukcji: wtyk do gniazda zapalniczki jest w zestawie, a w kryzysie stacja trafi też do pojazdu 24 V | Schurter 0001.2504; TVS SMBJ33CA (dwukierunkowy: praca do 33 V, przebicie od 36,7 V, ograniczenie 53,3 V, karta Vishay 88392) |
| progi ogniw | ostrzeżenie przy 4,4 V (1,1 V na ogniwo), kontrolowane wyłączenie przy 4,0 V po zakończeniu zapisu FRAM; progi na filtrowanej średniej z okresów samego odbioru, bo impulsy TX chwilowo obniżają napięcie zimnych ogniw | program stacji |
| pomiar | ADC napięcia ogniw (przed diodą) i wejścia 12 V (przed diodą i łącznikiem) przez dzielniki odłączane między pomiarami; błąd ≤2%; wynik na ekranie i w `INFO`; zakres pomiaru 12 V do co najmniej 36 V, żeby odróżnić 24 V od zwykłego zaniku; wejście ADC ograniczone tak, by impuls 53,3 V (granica TVS) go nie uszkodził | dzielnik 0,1% jak VTEST na v1 |
| pobór | w pracy przekaźnika tyle, by komplet ogniw dał ≥48 h (W23; model: [radio](radio.md#profil-lora-pilotażu)); w stanie wyłączonym ≤0,1 mA z każdego źródła | pomiar w RX, TX i przy pracy ekranu |

Zasady: o W23 rozstrzyga pomiar z minimum pilotażu, a niespełnione wymaganie zmienia tor przed zamówieniem v2. Napięcie 3,3 V przy nadawaniu sprawdza pomiar przy TX. Na czas przechowywania ogniwa wyjmuje się ze stacji. Powerbank przez USB nie jest dopuszczonym źródłem: wiele powerbanków wyłącza się przy prądzie rzędu kilkudziesięciu miliamperów, czyli przy poborze stacji.

### Stany zasilania 12 V

| Sytuacja | Ogniwa w stacji | Zachowanie |
|---|---|---|
| pierwsze podłączenie 12 V albo powrót źródła, napięcie ≥12,4 V | tak lub nie | zasilanie z 12 V startuje; przy ogniwach przejście z ogniw na 12 V bez restartu (szyna podtrzymana przez kondensator) |
| podłączenie źródła 11,5–12,4 V | tak lub nie | zasilanie z 12 V nie startuje (histereza); stacja pracuje z ogniw albo pozostaje wyłączona; ekran przy ogniwach pokazuje `odlaczone_12v` |
| podłączenie źródła powyżej progu OVP (np. instalacja 24 V, do 33 V ciągle) | tak lub nie | łącznik nie załącza wejścia, nic się nie uszkadza; stacja pracuje z ogniw albo pozostaje wyłączona; ekran przy ogniwach pokazuje `za_wysokie_12v`; po spadku poniżej progu wejście załącza się samo |
| spadek 12 V poniżej 11,5 V w pracy | tak | odcięcie 12 V, start przetwornicy z ogniw, praca z ogniw bez restartu, `odlaczone_12v` |
| spadek 12 V poniżej 11,5 V w pracy | nie | stacja traci zasilanie jak przy zaniku ([zanik zasilania](#zanik-zasilania-i-zapis)); odbudowa napięcia akumulatora bez obciążenia (zwykle do 12,0–12,3 V) nie włącza jej z powrotem; włącza się sama dopiero przy ≥12,4 V (np. po naładowaniu) |
| restart przez watchdog | tak lub nie | tor zasilania i stan sterownika wyłącznika bez zmian |
| wyłączenie wyłącznikiem głównym | tak lub nie | oba źródła odłączone; ponowne włączenie przyciskiem przy ≥12,4 V albo z ogniw |
| odwrotna polaryzacja 12 V (do 16 V przez 60 s) | tak lub nie | dioda albo łącznik blokuje; bez uszkodzeń i bez przepalenia bezpiecznika |
| ogniwa włożone odwrotnie | – | kluczowany koszyk, dioda blokuje |

Te stany sprawdza próba „Tor zasilania stacji pilotażowej” w [minimum pilotażu](odbior.md#minimum-pilotażu): brak prądu do ogniw (pomiar prądu w gałęzi ogniw przy 12 V, ≤1 µA), odwrotne podłączenie, napięcia graniczne 11,4/11,6/12,3/12,5/14,8/16 V, przełączenia bez restartu i zanik przy zapisie.


### Gniazdo USB do laptopa

Płytka v2 ma własne gniazdo USB-C (z rezystorami 5,1 kΩ na CC1 i CC2, bez których laptop z USB-C nie wykryje urządzenia), połączone tylko z liniami danych natywnego USB modułu (GPIO19 i GPIO20, piny 19 i 20 listwy J3 płytki DevKitC) i z masą, z ochroną ESD. Linii VBUS gniazdo nie ma, więc laptop połączony dowolnym przewodem nigdy nie zasila stacji, także wyłączonej, i nie walczy z przetwornicą 3,3 V. Nic nie zależy od pamiętania o przejściówce ani o przeróbce. Złącza micro USB płytki DevKitC służą tylko do programowania przy stole, przy odłączonym zasilaniu stacji.

## Zanik zasilania i zapis

Poprawność zapisu nie zależy od czasu podtrzymania: każda transakcja FRAM ma znacznik zatwierdzenia zapisywany na końcu, a niezatwierdzona transakcja jest po restarcie odrzucana albo dokańczana z rekordu transakcji ([zapis w FRAM](oprogramowanie.md#trwałość-i-potwierdzenia)). Dług ciszy jest zatwierdzany przed nadaniem ([radio](radio.md#dostęp-do-kanału)). Zanik w dowolnej chwili może więc najwyżej odrzucić zapis, który nie został jeszcze potwierdzony (`zapisane_w_stacji`, `stored`, RECEIVED).

Sprzęt musi zapewnić tylko, że zanik nie uszkodzi zawartości pamięci poza bieżącym zapisem:

1. Zapis FRAM idzie seriami SPI po ≤256 B przy zegarze ≥8 MHz (≤0,3 ms na serię). Przy 1 MHz seria 256 B trwałaby 2,05 ms, więc wolniejszy zegar jest niedopuszczalny.
2. Układ nadzoru zwalnia linię CS pamięci, zanim napięcie zasilania FRAM spadnie poniżej jej minimum (MB85RS4MT i CY15B104QN: 1,8 V). Na płytce v1 robi to nadzorca U3 (TPS3840PH27, próg 2,66–2,74 V) przez bramkę OR na CS, niezależnie od MCU ([płytka v1](../../hardware/dev-bench/plytka-nosna.md)); v2 przejmuje ten układ.
3. Stacja pilotażowa nie ma komparatora zaniku ani kondensatora podtrzymania przed przetwornicą; wystarczają punkty 1–2 i kondensator szyny zasilania. Dlatego minimum pilotażu sprawdza 100 odcięć podczas zapisu i nadawania bez fałszywego `zapisane_w_stacji` i bez uszkodzonego rekordu, a odbiór wydania 1000 odcięć.

## Poziom 3: kupiona stacja zasilania

Poziom 3 (laptop i router dla telefonów) zasila kupiona przenośna stacja zasilania z wyjściem 230 V i portami USB oraz kupiona ładowarka USB do telefonów, każda z deklaracją zgodności UE (D05 zamknięte 2026-10-08). WICI nie projektuje własnej przetwornicy 230 V ani ładowarki. Stacja WICI ma własne zasilanie (ogniwa AA i wejście 12 V) i nie zależy od stacji zasilania; może korzystać z jej wyjścia 12 V DC tylko wtedy, gdy wyjście spełnia wymagania wejścia 12 V stacji.

| Wymaganie | Wartość |
|---|---|
| energia | ≥1,8 kWh na dobę poziomu 3 w jednym schronieniu albo wymiana lub ładowanie co dobę ([model energii](../concept/06-wykonalnosc-i-budzet-zasobow.html#energia-dwa-niezalezne-zasoby)); pojemność dobiera się do zmierzonego poboru laptopa i routera |
| wyjście 230 V | sinusoida, moc ciągła ≥2 × pobór laptopa i routera; zasilacze laptopa i routera klasy II albo klasa I tylko przy sprawdzonym PE stacji zasilania (instrukcja producenta) |
| ładowanie telefonów | osobna ładowarka USB z deklaracją UE, zasilana z wyjścia stacji zasilania albo z osobnego źródła; wyłączenie ładowarki nie wpływa na laptop i router |
| dokumenty | deklaracja zgodności UE, instrukcja w języku polskim, warunki pracy w pomieszczeniu (temperatura, wentylacja) i przechowywania akumulatora (LiFePO4 preferowany) |
| odbiór | po pilotażu: pomiar 24 h z realnym laptopem i routerem, porównanie z wariantem DC (USB-C PD) i warunki przechowywania między przeglądami ([odbiór](odbior.md#próby), wiersz „Poziom 3: kupiona stacja zasilania”) |

## Archiwum: płytka R02 i gotowe płytki

Wymagania własnej płytki stacji R02 (zasilanie z komparatorem zaniku i zatrzaskiem 12 V, MCU dwóch wykonań, ekran z podświetleniem, ochrona ESD i odgromowa), dawny wariant stacji pilotażowej z gotowej płytki ESP32-S3 z SX1262 połączonej przewodami oraz porównanie kandydatów (RAK3312 na RAK19007, Heltec, LILYGO, Seeed) z dokumentami zgodności są w [archiwum elektroniki](../archiwum/elektronika-r02.md). Stary BOM R02 jest w [archiwum BOM](../archiwum/bom-r02.md).

## Archiwum: własny blok zasilania poziomu 3

Własna przetwornica 230 V, wejścia A/B i ładowarka telefonów poziomu 3 wypadły z zakresu po D05; opis jest w [archiwum zasilania poziomu 3](../archiwum/zasilanie-poziomu-3.md).

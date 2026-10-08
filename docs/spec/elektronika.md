# WICI: elektronika

Podane wartości służą do wykonania i pomiaru prototypu. Warianty różnych producentów wymagają oddzielnego sprawdzenia tolerancji i nie zawsze mają zgodne wyprowadzenia. Schemat połączeń nie zastępuje projektu płytki drukowanej (PCB) ani odbioru części 230 V.

## Zasilanie stacji

```text
4 × AA ─ R 1 Ω ─ dioda Schottky’ego DAA ──────────────────────────────────────────────────┐
12 V ─ F T1A ─ TVS SMBJ18CA ─ tłumik RC ─ łącznik S12 ────────────────────────────────────┴─ VSYS ─ C ≥680 µF (mały upływ) ─ przetwornica podwyższająco-obniżająca ─ 3V3
            │                                       (polaryzacja, OVP, UV 11,5 V z zatrzaskiem,      │                                    │
            │                                        narastanie ≤1 A; EN = ON i brak zatrzasku UV)    komparator VSYS 3,4 V ─ przerwanie MCU   EN = ON
            └─ dzielnik 12 V z kluczem ≥40 V ─ ADC        zatrzask UV 12 V (zasilany z wyjścia ON) ─ EN S12
AA i 12 V (przed S12) ─ dwie diody Schottky’ego ─ sterownik wyłącznika LTC2954 ─ ON ─ EN S12 i EN przetwornicy
                                                   przycisk wyłącznika głównego ─┘   INT ─ MCU;  MCU ─ KILL
```

| Element | Wymaganie prototypu |
|---|---|
| Ogniwa | 4 × AA: litowe Li-FeS2 1,5 V (wymagane do przechowywania i do W23), alkaliczne lub NiMH tylko awaryjnie; koszyk z kluczowaniem przeciw odwrotnemu włożeniu. W23 i praca w −10 °C dotyczą wyłącznie ogniw Li-FeS2; ogniwa alkaliczne i NiMH tracą w −10…−20 °C około 50–80% pojemności |
| Wyłącznik główny | przycisk ze sterownikiem z zatrzaskiem (soft-latch), np. ADI LTC2954 (2,7–26,4 V); drugi kandydat innego producenta do wyboru przy R02 (W14); MAX16150 się nie nadaje, bo wymaga stale obecnej szyny 1,3–5,5 V. Krótkie naciśnięcie włącza; przytrzymanie 2 s zgłasza MCU żądanie wyłączenia (INT), MCU pokazuje `wylaczanie`, kończy transakcję FRAM i nadawanie, pokazuje `mozna_wyjac` i dopiero wtedy wyłącza (KILL); bez odpowiedzi MCU wyłączenie wymusza przytrzymanie przycisku przez czas ustawiony kondensatorem na ≥5 s (LTC2954 nie wyłącza się sam po puszczeniu przycisku; 2 s do INT odmierza program, a KILL musi być w stanie wysokim najpóźniej 400 ms po włączeniu, [zasilanie R02](../../hardware/r02/zasilanie.md)). Wyjście ON steruje EN łącznika S12 i EN przetwornicy 3V3; tor ogniw nie ma łącznika, bo przy wyłączonej przetwornicy VSYS obciążają tylko prądy spoczynkowe. Łącznik mechaniczny odpada: odcina zasilanie natychmiast, a podtrzymanie (2 ms) wystarcza tylko na zakończenie jednego zapisu, więc procedura wymiany ogniw z karty nie byłaby wykonalna. LTC2954 zasila się z sumy diodowej obu źródeł przed S12 (dwie diody Schottky’ego), nie z VSYS, bo VSYS znika po wyłączeniu. Prąd pobierany w stanie wyłączonym z każdego źródła ≤20 µA, do zmierzenia |
| VSYS | 3,4–16 V; źródło o wyższym napięciu zasila stację, przełączenie bez spadku 3V3 poniżej progu resetu |
| Dioda DAA (ogniwa) | dioda Schottky’ego (decyzja F87): bez prądu spoczynkowego, więc prąd z ogniw w stanie wyłączonym spada z około 24 do około 12 µA typowo; idealna dioda LTC4412 pobierała 11–19 µA stale. VR ≥30 V (VSYS ogranicza OVP łącznika S12); spadek około 0,35 V przy 40–120 mA, liczony w modelu energii i w progach ogniw (ogniwa mierzy się przed diodą); prąd wsteczny przy 16 V i 45 °C płynie do pierwotnych ogniw litowych, gdy stacja pracuje z 12 V, więc dioda o małym upływie, a wartość dopuszczalną bierze się z karty ogniw (do sprawdzenia). Rezystor 1 Ω impulsowy przed diodą ogranicza udar przy wkładaniu ogniw do ≤5 A |
| Łącznik S12 (12 V) | odłączenie 12 V realizuje łącznik dwukierunkowy (dwa tranzystory MOSFET połączone przeciwstawnie, źródłami do siebie), o wytrzymałości ≥40 V; wejście EN pojedynczego sterownika idealnej diody nie odłącza źródła, bo prąd płynie dalej przez diodę podłożową. Narastanie napięcia przy załączeniu sterowane, prąd ładowania kondensatorów ≤1 A. Kandydaci: sterownik TI LM74800-Q1 z dwoma tranzystorami N-MOSFET ≥40 V (blokada prądu wstecznego, regulowany OVP; prąd spoczynkowy około 0,4 mA do modelu energii) albo eFuse z blokadą prądu wstecznego, OVP i UVLO, np. TI TPS25947, który ma maksimum 28 V i wymaga dodatkowego ogranicznika przed wejściem. LM74502 nie blokuje prądu wstecznego, więc nadaje się tylko do ochrony przed odwrotną polaryzacją. Obaj kandydaci pochodzą od TI; potrzebny kandydat innego producenta (W14) |
| Ochrona przepięciowa | S12 odcina VSYS powyżej zakresu pracy (OVP): próg nominalnie 17 V z LTC3115-1 (praca do 16 V), 15,5 V w wariancie TPS63070 (praca do 15 V); ten wariant nie spełnia reguły poniżej (0,9 × 16 V = 14,4 V), więc wymaga dodatkowego ogranicznika przed wejściem przetwornicy. Wymaganiem jest reguła, nie tolerancja progu (decyzja F87): dolna granica progu powyżej maksimum pracy (16 V), a górna łącznie z przerzutem ≤0,9 × maksimum wejścia przetwornicy i ≤0,9 × maksimum zasilania komparatora zaniku. LM74800-Q1 z dzielnikiem 255 kΩ / 20,0 kΩ (0,1%) daje 16,40–17,45 V, a z przerzutem ≤18,3 V wobec 36 V dla LTC3115-1. Przy TPS3710 (maksimum 18 V) zasilanym z VSYS granica wynosi 16,2 V, co przy pracy do 16 V nie zostawia miejsca na tolerancję; komparator zasila się więc z 3V3 (wejście SENSE przez dzielnik z VSYS) albo wybiera komparator o wyższym napięciu zasilania (do oceny w R02). TVS SMBJ18CA (dwukierunkowy, bo przy odwrotnym podłączeniu jednokierunkowy przewodziłby i przepalał bezpiecznik) ogranicza impuls dopiero do około 29 V, więc nie chroni sam przetwornicy. Tłumienie na wejściu 12 V: tłumik RC, czyli ceramika 10–22 µF/50 V X7R z rezystorem 0,5–1 Ω (decyzja F87); bipolarny elektrolit 47 µF/35 V ma gwarantowany upływ 49–52 µA, ponad budżet stanu wyłączonego. Bez tłumienia przepięcie przy podłączaniu przewodu sięga około 2 × Vin; wartość R dobiera się do indukcyjności przewodu i sprawdza pomiarem |
| Przetwornica 3V3 | podwyższająco-obniżająca, wejście 2,7–16 V w pracy, ≥500 mA, sprawność ≥85% przy 30–60 mA z ogniw (6 V) i ≥80% z 12,8 V, prąd spoczynkowy ≤50 µA. Kandydat podstawowy: ADI LTC3115-1 (do 40 V). TI TPS63070 (maksimum wejścia 16 V) tylko przy zawężeniu pracy wejścia 12 V do 11,5–15 V i progu OVP 15,5 V ±2%; zgodność tego progu z regułą 0,9 × maksimum wejścia wymaga sprawdzenia wobec karty katalogowej (do oceny) |
| Wejście 12 V | 11,5–16 V w pracy (11,5–15 V w wariancie TPS63070); pierwsze i ponowne załączenie przy ≥12,4 V (jeden próg, decyzja F87); złącze IP67 kluczowane; bezpiecznik zwłoczny T1A 32 V DC przy wtyku; TVS SMBJ18CA; ochrona przed odwrotną polaryzacją w S12; odwrotne podłączenie 16 V przez 60 s bez przepalenia bezpiecznika i uszkodzeń. Nie podłączać do instalacji pojazdu z pracującym silnikiem, dopóki próby impulsami według ISO 7637-2 nie wykażą odporności |
| Odłączenie 12 V | wyłączenie przy 11,5 V z zatrzaskiem; ani LM74800, ani TPS25947 nie ma zatrzasku UV, więc osobny komparator z zatrzaskiem jest wymagany zawsze. Zatrzask zasilany z wyjścia ON sterownika wyłącznika głównego, więc wyłączenie stacji go kasuje; pobór ≤20 µA. Ekran pokazuje wtedy `odlaczone_12v`. Ponowne załączenie po odłączeniu i ponownym podłączeniu źródła, wyłączeniu wyłącznika głównego albo przytrzymaniu OK, zawsze tylko przy V12 ≥12,4 V; przycisk OK kasuje zatrzask przez tranzystor z izolacją poziomów 3V3↔12 V. Stacja pracuje wtedy z ogniw |
| Wykrycie zaniku zasilania | komparator VSYS z wyjściem na przerwanie MCU, próg 3,4 V ±2% (np. TI TPS3710: zasilanie 1,8–18 V, próg ustawiany dzielnikiem na wejściu SENSE; TPS3840 ma maksimum 10 V i mierzy tylko własne zasilanie). Po przerwaniu MCU najpierw gasi podświetlenie, diodę alarmu i brzęczyk. Czas podtrzymania od progu 3,4 V do zatrzymania przetwornicy przy 2,7 V ≥2 ms przy maksymalnym poborze (TX, aktywny MCU) w −20 °C: C ≥ 2·P·t/(3,4² − 2,7²); model daje P ≈0,42 W i C ≥ około 393 µF, a przy najgorszym progu komparatora (3,325 V) ≥450 µF; po tolerancji −20% i spadku w −20 °C kondensator ≥680 µF/25 V o małym upływie (decyzja F87). Kondensator polimerowy odpada: VSYS jest stale połączone z ogniwami, a jego gwarantowany upływ sięga 352 µA; elektrolit o małym upływie (np. Nichicon UKL, 0,002 CV) z ceramiką równolegle, upływ przy 6 V do zmierzenia. Czas do końca transakcji FRAM i wyłączenia TX mierzy się w T6 wyjęciem ogniw podczas zapisu i nadawania |
| Progi ogniw | ostrzeżenie przy 4,4 V (1,1 V na ogniwo), kontrolowane wyłączenie przy 4,0 V po zakończeniu zapisu FRAM; ogniwa Li-FeS2 mają płaską charakterystykę i szybki spadek pod koniec, więc T6 sprawdza, że od ostrzeżenia `wymien_ogniwa` do wyłączenia zostaje ≥1 h pracy przekaźnika w 20 °C i −10 °C, a w razie potrzeby podnosi próg ostrzeżenia; progi ocenia się na filtrowanej średniej z okresów samego odbioru, bo impulsy TX chwilowo obniżają napięcie zimnych ogniw |
| Pomiar | ADC napięcia ogniw i wejścia 12 V przez dzielniki odłączane między pomiarami; błąd ≤2%; wynik na ekranie i w `INFO`. Dzielnik 12 V mierzy przed S12, klucz górny dzielnika ≥40 V; wejście ADC ograniczone tak, by impuls 29 V (granica TVS) go nie uszkodził |
| Pobór | cel średni z 3V3 w pracy przekaźnika: wykonanie A ≤35 mA (model 32 mA), wykonanie B ≤60 mA (W23 dopuszcza w modelu najwyżej około 61 mA, ze spadkiem na diodzie DAA). Dla ESP32-S3 W23 zależy od lekkiego uśpienia MCU przy stale włączonym odbiorniku; prąd aktywny MCU 45–60 mA daje w modelu tylko 33–39 h na ogniwach. Model: 3,8–10,6 Wh na dobę z ogniw i 4,0–10,7 Wh z 12 V, z rezerwą 20%. Pomiar w RX, TX, przy włączonym ekranie i podświetleniu (W23) |
| Szyna 5 V ekranu | Sharp LS027B7DH01 wymaga zasilania 4,8–5,5 V (VDD i VDDA; zakres pracy −20…+70 °C, temperatura powierzchni panelu); wejścia logiczne przyjmują 3,3 V (VIH od 2,7 V). Szyna 5 V: włączana przetwornica o małym prądzie spoczynkowym z odłączeniem wyjścia, np. TI TPS61099 w wersji regulowanej (DRV) ustawiony dzielnikiem na 5 V (TPS610995 to wersja 3,6 V, a wersja 5 V TPS610997 jest tylko w obudowie WCSP); TPS61222 w wyłączeniu przepuszcza napięcie wejścia na wyjście i wymaga dodatkowego łącznika. EXTCOMIN steruje wyjście sprzętowego licznika lub RTC, nie program. JDI LPM027M128C (8 kolorów, zasilanie 3 V) nie jest zamiennikiem bez zmian |
| Podświetlenie ekranu | diody LED krawędziowe (front light), włączane przyciskiem i wyłączane po czasie, bo schronienia bywają ciemne; sterownik prądowy diod, najlepiej z szyny 5 V; w modelu 15 mA przez 30 min na dobę |
| Dioda alarmu i brzęczyk | dioda LED „NOWA WIADOMOŚĆ / ALARM” i brzęczyk sterowane z MCU krótkimi impulsami; w modelu dioda 5 mA przez 1% czasu i brzęczyk 20 mA przez 0,25% czasu, łącznie około 0,1 mA |
| USB | stacja nie zasila się z VBUS (VSYS niezależne od VBUS); brak połączenia VBUS z VSYS. Wykonanie A: VBUS bezpośrednio do wyprowadzenia VBUS nRF52840 (4,35–5,5 V), które zasila wyłącznie PHY USB; pobór z VBUS około 2,5 mA. Wykonanie B: VBUS tylko do wykrycia hosta: rezystor szeregowy ≥100 kΩ z ograniczeniem do VDD albo bufor z Ioff (np. 74LVC1G17), aby VBUS nie zasilał MCU przez wejście przy wyłączonej stacji. Ochrona ESD linii USB (np. ST USBLC6-2 lub TI TPD4E05U06) |

Powerbank przez USB nie jest dopuszczonym źródłem: wiele powerbanków wyłącza się przy prądzie rzędu kilkudziesięciu miliamperów, czyli przy poborze stacji. Na czas przechowywania ogniwa wyjmuje się ze stacji, a ich stan sprawdza się w przeglądzie. Przetwornica ma pracować z obu źródłami w pełnym zakresie temperatur stacji. Liczby poboru są założeniami [modelu](../../software/reference/wyniki.json), nie pomiarem: model obejmuje TCXO radia (2 mA), szynę 5 V ekranu, podświetlenie, diodę alarmu i brzęczyk oraz osobno dla każdego źródła prądy po stronie wejścia: z ogniw TPS3710, LTC2954 i dzielniki (razem około 0,022 mA; dioda DAA nie pobiera prądu, a jej spadek 0,35 V zwiększa moc pobieraną z ogniw o około 6%), z 12 V LM74800, zatrzask UV, TPS3710, LTC2954 i dzielniki (razem około 0,44 mA). Sprawność przetwornicy 0,85 przy 6 V i 0,80 przy 12,8 V obejmuje jej prąd spoczynkowy, którego nie dolicza się drugi raz.

## Płytka stacji R02: wymagania

R02 łączy mikrokontroler, tor RF jednego wykonania, FRAM, ekran, przyciski i zasilanie stacji. Schemat i PCB jeszcze nie powstały; R02 jest pierwszą płytką stacji, a [folder projektu](../../hardware/r02/README.md) podaje wejścia i kolejność prac oraz [lekcje z wycofanego kontrolera R01.3](../../hardware/r02/lekcje.md). Do tego czasu oprogramowanie i próby T1–T4 prowadzi się na [stanowisku deweloperskim](../../hardware/dev-bench/README.md) z płytek rozwojowych i modułów producentów.

| Funkcja | Wymaganie |
|---|---|
| MCU | dwa wykonania według [specyfikacji radia](radio.md#dwa-wykonania); Wi-Fi i Bluetooth wyłączone; sposób wyłączenia i argumentacja RED według [specyfikacji radia](radio.md#warunki-prawne-i-zgodność) (D14); ochrona odczytu pamięci; nRF52840 tylko w rewizji 3 (kod wykonania Fx0, np. nRF52840-QIAA-F0) z ochroną APPROTECT według Nordic IN-141, która utrudnia znaną metodę wstrzykiwania błędów (IN-133); oprogramowanie budowane z MDK ≥8.40.2 |
| Zegar | TCXO radia według P1; kwarc 32 MHz (HFXO nRF52840) albo 40 MHz (ESP32-S3); kwarc 32,768 kHz dla licznika czasu w uśpieniu |
| Czas | opcjonalny RTC z podtrzymaniem (np. Micro Crystal RV-3028-C7); bez niego czas stacji po zaniku zasilania jest niezaufany i tak oznaczany |
| Pamięć | FRAM SPI 4 Mbit we wszystkich stacjach (stacja zajmuje około 205 KiB; przy 2 Mbit nie zostaje miejsca na kompaktowanie dziennika, [pamięć FRAM](oprogramowanie.md#trwałość-i-potwierdzenia)), na wspólnej magistrali z ekranem albo osobnej, z zapisem zakończonym przed wyłączeniem. Rekordy FRAM szyfrowane kluczem przechowywanym w chronionej pamięci MCU, bo zewnętrzną FRAM da się odczytać po wylutowaniu; ZNISZCZ DANE usuwa klucz (kryptograficzne wymazanie) i nadpisuje FRAM poza jawnym dziennikiem długu ciszy. Wykonanie B bez zewnętrznej pamięci flash QSPI wymaga ESP32-S3FH4R2 (4 MB flash i 2 MB PSRAM w obudowie); wersje ESP32-S3R2/R8/R16V mają w obudowie tylko PSRAM |
| Ekran | graficzny, czytelny w świetle dziennym i na mrozie, z cyrylicą; złącze dla dwóch wykonań (D15); szyna 5 V i podświetlenie według tabeli zasilania. Przy −20 °C ekran pracuje na granicy zakresu, bez zapasu: czytelność w −20 °C sprawdza T6 |
| Przyciski | GÓRA, DÓŁ, OK, WSTECZ; przełącznik CISZA z osłoną; przycisk konfiguracji (tryb przygotowania) pod plombowaną pokrywą serwisową, która daje dostęp tylko do niego, nie do płytki; przycisk podświetlenia może być jednym z nich; dioda alarmu i brzęczyk według tabeli zasilania |
| Odporność ESD | EN 61000-4-2: ±4 kV kontaktowo i ±8 kV w powietrzu na złączu anteny, USB-C, wejściu 12 V i przyciskach; bez resetu i utraty danych |
| Programowanie | złącze SWD (pola Tag-Connect) lub UART na płytce, niedostępne bez otwarcia obudowy |
| Nadzór | sprzętowy watchdog; układ nadzoru resetu; komparator zaniku zasilania; licznik restartów w FRAM |
| USB | gniazdo USB-C (rezystory 5,1 kΩ na CC) z ochroną ESD; ESP32-S3: USB-OTG z TinyUSB (dwa porty CDC), nie USB-Serial-JTAG |
| Ochrona odgromowa | antena zwarta dla prądu stałego (dipol pętlowy albo dipol ze zwierającym odcinkiem ćwierćfalowym), odgromnik gazowy (GDT) na przewodzie antenowym przy wejściu do budynku, połączony z uziemieniem budynku; dla poziomów 2–3 opcjonalna izolacja USB (np. ADI ADuM4160 lub TI ISOUSB211). W wykonaniu A izolator wymaga izolowanego 5 V dla wyprowadzenia VBUS nRF52840 (PHY USB po stronie stacji); bez niego izolację stosuje się tylko w wykonaniu B |
| Temperatura | cel: −20 °C do +45 °C dla gotowej stacji z ogniwami litowymi; do kwalifikacji |
| Obudowa | do pracy w pomieszczeniu, IP40, bez wentylacji, z odciążeniem przewodu antenowego i 12 V; masa z ogniwami ≤1 kg jako cel; powłoka ochronna płytki (conformal coating) przeciw kondensacji po wyjęciu z zimnego magazynu. Złącza przewodów zewnętrznych IP67 albo uszczelnione taśmą |

## Wejścia A/B (poziom 3)

Wejścia A/B zasilają przetwornicę laptopa i routera. Stacja ma własne zasilanie opisane wyżej.

```text
A+ ─ FA przy zacisku ─ przewód ─ JA+ ─ [DA: A→K] ─┐
                               │               │
                              TVSA           BUS+
                               │               │
                              GND              │
B+ ─ FB przy zacisku ─ przewód ─ JB+ ─ [DB: A→K] ─┘
                               │
                              TVSB
                               │
                              GND
A−, B−, JA−, JB− i minus Cbus połączone z GND.
BUS+ ─ wyłącznik DC ≥30 A (znamionowany dla prądu stałego) ─ mostek przetwornicy
```

DA i DB: osobne podwójne diody Schottky’ego ze wspólną katodą; obie anody danego elementu są połączone. Katody dołączone do BUS+. Jednego elementu nie wolno używać dla dwóch wejść 20 A. Kandydaci: ST STPS3045CT lub Vishay VS-MBR3045CT-M3, dwa elementy w zestawie. [ST](https://www.st.com/en/diodes-and-rectifiers/stps3045c.html), [Vishay](https://www.vishay.com/doc/?96257=).

| Element | Wymaganie prototypu |
|---|---|
| FA/FB, przewód do gniazda zapalniczki | bezpiecznik 10 A; praca ≤8 A i nie więcej, niż dopuszcza instalacja pojazdu |
| FA/FB, przewód zaciskowy | bezpiecznik 25 A; praca ≤20 A |
| Przewód do gniazda zapalniczki | do 2 m, 2 × 2,5 mm²; styk i dopuszczalna temperatura wtyku dobrane do prądu |
| Przewód zaciskowy | do 2 m, 2 × 6 mm²; złącze uniemożliwiające odwrotne podłączenie, ≥30 A DC |
| TVSA/TVSB | SMCJ18CA, dwukierunkowy, po bezpieczniku, przed diodą |
| DA/DB | ≥45 V, po 20 A dla całego toru w wymaganej temperaturze |
| Radiator DA/DB | punkt wyjścia: ≤3 K/W na tor; mocowanie izolowane elektrycznie |
| Cbus | punkt wyjścia: 8 × 2200 µF/35 V; łączny dopuszczalny prąd tętnień ≥24 A |
| Napięcie wejściowe | 11,5–16 V przy złączu, z uwzględnieniem spadku przewodów |

Kondensatory Cbus należą do stopnia mocy; wyłącznik DC odłącza mostek, nie przewody akumulatorów. Wspólna masa oznacza brak izolacji źródeł. Metalowe obudowy diod są połączone z katodą, czyli z BUS+, więc wspólny radiator może mieć ten sam potencjał. Nie zwiera to wejść A/B, ale radiator trzeba odizolować od dostępnej obudowy i GND.

Diody nie zapewniają ograniczenia udaru. Przy 17,6 mF, skoku napięcia 5,5 V i założonej rezystancji pętli 40 mΩ model daje początkowy prąd około 138 A. Rezystancja 40 mΩ jest założeniem do próby, a nie gwarantowaną wartością znalezionego akumulatora. Trzeba zmierzyć prąd udarowy oraz sprawdzić całkę Joule’a (I²t) bezpieczników i dopuszczalny impuls prądowy diod i styków. Jeśli wynik będzie negatywny, potrzebny jest układ ograniczający prąd udarowy; nie wolno dopuścić modułu do pracy samym zwiększeniem wartości bezpiecznika.

Lampka wejścia potwierdza wyłącznie obecność napięcia o prawidłowej polaryzacji. Każde wejście A, B i C ma ponadto woltomierz cyfrowy o błędzie ≤1%, mierzący napięcie przed diodą; bez niego opiekun nie zaplanuje wymiany źródeł. Ciągłość zasilania ma zapewniać jednoczesne podłączenie obu źródeł podczas wymiany, a nie energia zgromadzona w Cbus. Ochrona podczas pracy alternatora i rozruchu silnika wymaga osobnych prób motoryzacyjnych; sama dioda TVS nie dowodzi takiej odporności.

Ochrona przed głębokim rozładowaniem: regulator przetwornicy mierzy napięcie obu złączy przed diodami (JA+ i JB+) i wyłącza mostek, gdy wyższe z nich spadnie poniżej 11,5 V. Pomiar za diodą obarczałby wynik zmiennym spadkiem napięcia diody, 0,3–0,55 V zależnie od prądu i temperatury. Przy 11,8 V regulator włącza ostrzeżenie (dioda świecąca i brzęczyk), aby opiekun zdążył wymienić źródło. Wyłączenie jest zatrzaskiwane: ponowne załączenie następuje dopiero po zamknięciu wyłącznika DC albo naciśnięciu przycisku RESTART, i tylko przy napięciu co najmniej 12,4 V. Samo odbicie napięcia po zdjęciu obciążenia nie może uruchomić przetwornicy; rozładowany akumulator LiFePO4 bez obciążenia wraca do około 12,5–12,8 V i bez zatrzasku powodowałby cykliczne załączanie. Ten sam próg, ostrzeżenie, zatrzask i osobny przycisk RESTART dotyczą wejścia C ładowarki. Głęboko rozładowany akumulator kwasowo-ołowiowy traci pojemność, a akumulator rozruchowy przestaje uruchamiać pojazd. Dla niego opiekun wymienia źródło wcześniej, przy około 12,2 V. Akumulator LiFePO4 ma własny BMS, który nie zastępuje tego progu.

Akumulatory stoją na tacy odpornej na elektrolit, z dala od dróg ewakuacyjnych i od wlotów powietrza. Uszkodzony akumulator rozruchowy może wydzielać wodór, dlatego nie ładuje się go w pomieszczeniu z ludźmi, a przy stacji jest gaśnica.

## Jedna sekcja ładowarki (poziom 3)

Sekcję powiela się 8 razy. Każda sekcja ma własny regulator, dławik, diodę, bezpieczniki i ogranicznik portu. Obwód C nie ma wspólnej masy z A/B. Wspólny dla wszystkich sekcji jest odłącznik podnapięciowy wejścia C (11,5 V / 12,4 V); sam LM2596 pracuje do około 7 V wejścia i rozładowałby akumulator do zera.

```text
C+ ─ główny F10 A ─ magistrala ─ F1 1,5 A ─ dioda polaryzacji ─ VIN regulatora
VIN ─ Cin ─ GND_C
LM2596 SW ─ L1 68 µH ─ VREG około 5,12 V ─ F2 szybki 3,15 A ─ VSAFE
GND_C ─ anoda D1; katoda D1 ─ SW
VREG ─ Cout ─ GND_C
VREG ─ Rtop 3,16 kΩ ─ FB ─ Rbottom 1,00 kΩ ─ GND_C
VSAFE ─ ogranicznik prądu ─ VUSB ─ USB-A pin 1
GND_C ─ USB-A pin 4; USB-A piny 2 i 3 zwarte
VSAFE ─ niezależny układ przepięciowy ─ GND_C
```

| Element | Wartość początkowa lub wymagana cecha |
|---|---|
| Regulator | LM2596-ADJ, TI lub onsemi; radiator dobrany na podstawie pomiaru strat |
| L1 | 68 µH, Isat ≥6 A, Irms ≥3 A, DCR ≤40 mΩ |
| D1 i ochrona polaryzacji | dioda Schottky’ego ≥3 A/40 V, np. 1N5822 różnych producentów |
| Cin | 470 µF/35 V oraz 100 nF |
| Cout | 470 µF/16 V; kondensator elektrolityczny o ESR zgodnej z kartą katalogową regulatora |
| FB | Rbottom 1,00 kΩ, Rtop początkowo 3,16 kΩ; kontrola napięcia po montażu |
| Ogranicznik portu A | TPS2553, limit początkowo RILIM 15 kΩ, 0,1%; pełny budżet tolerancji nadal do odbioru; temperatura złącza ≤105 °C |
| Ogranicznik portu B | niewybrany; niezależny wariant musi zamknąć gwarantowany budżet prądu i temperatury |
| Prąd roboczy | 1,5 A na złączu, także po nagrzaniu |
| Próg ograniczania prądu | zakwalifikowany przedział 1,6–2,1 A przed ograniczeniem zwrotnym (foldback) lub wyłączeniem termicznym; zwarcie nie wyłącza innych sekcji |
| DCP | D+ i D− zwarte bez dodatkowego układu identyfikacji |

Nominalne 5,12 V nie gwarantuje poprawnego napięcia: bez strojenia rezystorem FB tolerancja źródła odniesienia LM2596 daje do 5,27 V, tylko 30 mV poniżej najniższego progu zwieracza. Strojenie każdej sekcji jest więc obowiązkowe. Przy montażu dobiera się stały rezystor FB; potencjometr regulacyjny jest niedozwolony. Odbiór na złączu: 4,75–5,25 V przy 0–1,5 A, 11,5–16 V na wejściu, 0–40 °C w otoczeniu. Nie wolno zastąpić wymaganych kondensatorów elektrolitycznych samymi ceramicznymi bez sprawdzenia stabilności. Przeskok napięcia po nagłym odłączeniu obciążenia 1,5 A nie może zbliżyć VREG do progu zwieracza, ponieważ jego zadziałanie trwale wyłącza sekcję. [TI LM2596](https://www.ti.com/lit/ds/symlink/lm2596.pdf), [onsemi LM2596](https://www.onsemi.com/download/data-sheet/pdf/lm2596-d.pdf).

TPS2553 dopuszcza 1,5 A prądu ciągłego przy temperaturze złącza do 105 °C. Dla rezystora o wartości dokładnie 15 kΩ karta katalogowa podaje próg 1,610–1,800 A, bez uwzględnienia tolerancji rezystora; rezystor 1% nie zapewnia wystarczającego zapasu powyżej 1,6 A. Punktem wyjścia jest więc rezystor 0,1%; cały budżet trzeba sprawdzić.

Dla MIC2007 nie da się dobrać stałego rezystora w gwarantowanych granicach karty katalogowej: przy warunku IOUT = 2 A i CLF = 210–286 V wymagania 1,6–2,1 A dają jednocześnie RSET ≤131,25 Ω oraz RSET ≥136,19 Ω. Przedział jest pusty nawet bez tolerancji rezystora, więc MIC2007 nie jest gotowym drugim wariantem. Inny element albo indywidualna kwalifikacja całego wariantu wymaga odrębnego projektu i dowodu. Nie wolno zwiększać limitu prądu tylko po to, by zaakceptować część. [TPS2553](https://www.ti.com/lit/ds/symlink/tps2553.pdf), [MIC2007](https://www.microchip.com/content/dam/mchp/documents/APID/ProductDocuments/DataSheets/MIC20XX-Fixed-and-Adjustable-Current-Limiting-Power-Distribution-Switches-DS20006486B.pdf).

### Ochrona przed podaniem 12 V na telefon

Kandydat do próby: zwieracz zabezpieczający (crowbar) TL431B + BC327 + tyrystor (SCR), przed ogranicznikiem USB. Anoda TL431 do GND_C, wejście REF przez dzielnik VSAFE–9,31 kΩ–REF–8,20 kΩ–GND_C. Katoda przez 1 kΩ do bazy tranzystora PNP; emiter PNP do VSAFE, rezystor baza–emiter 2,2 kΩ. Kolektor przez 47 Ω do bramki tyrystora; bramka przez 1 kΩ do GND_C. Anoda tyrystora do VSAFE, katoda do GND_C. Tyrystor: TYN612 albo BT151 z dopasowanym prądem bramki i I²t. Różne wykonania wymagają przeliczenia sterowania.

Próg nominalny 5,328 V. Wymagany zakres po tolerancjach i temperaturze 5,30–5,45 V. TL431B i rezystory 0,1% ograniczają rozrzut, lecz nie zastępują próby dynamicznej. F1/F2 mają odłączyć uszkodzoną gałąź z zachowaniem dopuszczalnej wartości I²t tyrystora, przewodów i regulatora. Nie wolno zakładać, że F2 zadziała przed F1, bo mają różne prądy znamionowe i charakterystyki. Koordynację F1, F2 i głównego F10 A trzeba zmierzyć. Gdy sprawny regulator ogranicza prąd, bezpiecznik może się nie przepalić; tyrystor i jego chłodzenie muszą wtedy wytrzymać ten stan. Przed podłączeniem telefonów trzeba wymusić zwarcie wejścia z wyjściem przetwornicy obniżającej oraz zmierzyć szczytowe VUSB i energię impulsu. Sama dioda TVS opisana jako „5 V” nie zapewnia ochrony telefonu.

## Przetwornica (poziom 3)

Cel sprawności i poboru własnego: pobór bez obciążenia ≤8 W, sprawność ≥0,85 przy 35 W AC; te wartości przyjmuje [model energii](../concept/06-wykonalnosc-i-budzet-zasobow.html#energia-dwa-niezalezne-zasoby) i sprawdza odbiór. Wybrana topologia prototypu: transformator 50 Hz, mostek H po stronie dolnego napięcia, unipolarna modulacja SPWM 20 kHz, bez magistrali 350 V DC. Zasada jest znana ([TI SLAA602A](https://www.ti.com/lit/an/slaa602a/slaa602a.pdf)); wartości elementów tego stopnia wymagają osobnego projektu.

```text
BUS+ ─ dreny Q1 i Q3
Q1 źródło = LEFT = dren Q2
Q3 źródło = RIGHT = dren Q4
T1 uzwojenie DN między LEFT i RIGHT
Q2/Q4 źródła = BRIDGE_RETURN ─ Rshunt 5 mΩ ─ GND
Cbus między BUS+ i GND; nie między BUS+ i BRIDGE_RETURN
T1 uzwojenie GN ─ filtr LC ─ ochrona AC ─ dwa wyjścia zasilaczy
```

| Część | Dobór do prototypu |
|---|---|
| Q1–Q4 | 4 × ST STP220N6F7 lub Infineon IPP030N06NF2S, ≥60 V, RDS(on) ≤3,1 mΩ przy 10 V |
| Sterowanie mostkiem | dwa UCC27211 albo dwa LTC4444; różne układy zasilania i bootstrapu |
| Napięcie sterowników | stabilizowane, około 10 V; nie bezpośrednio z instalacji pojazdu |
| MCU | STM32F103 z TIM1 albo dsPIC33CK z komplementarnym PWM i wejściem FAULT |
| Czas martwy | początkowo 1 µs; pomiar obu bramek pod obciążeniem |
| Rezystory bramek | 10 Ω, rezystor ściągający 10 kΩ; korekta na podstawie przebiegów |
| Kondensator bootstrap | początkowo 1 µF/25 V na półmostek; dobór na podstawie Qg i prądów upływu |
| Ograniczenie modulacji | m ≤0,9; zapewniony czas doładowania kondensatora bootstrap |
| Bocznik | 5 mΩ, ≥10 W, połączenie Kelvin |
| Szybkie wyłączenie | komparator sprzętowy, próg początkowo 0,375 V, czyli 75 A; zatrzask FAULT |
| Logika blokowania | H AND NOT L, L AND NOT H; następnie AND ENABLE; bez polegania tylko na MCU |
| Komparator | TLV3201 lub MCP6561, z uwzględnieniem błędu i opóźnienia |
| Logika | 74HC04, 74HC08, zatrzask CD4013; dostępne u różnych producentów |
| Temperatura | termistor NTC na radiatorze; zatrzymanie przy 85 °C, ręczny restart po ostygnięciu |
| Profil prądu ciągłego | 8 A lub 20 A, dodatkowy pomiar uśredniony; bezpiecznik chroni przewód |

Masa odniesienia sterownika musi być dołączona przy źródle dolnego tranzystora MOSFET. Podłączenie minusa Cbus do BRIDGE_RETURN, przed bocznikiem, ominęłoby pomiar prądu zwarcia mostka. Jednoczesne wysterowanie obu tranzystorów półmostka ma sprzętowo wyłączyć oba. FAULT zeruje ENABLE i wejście BREAK niezależnie od obsługi przerwania. Podczas startu i resetu MCU bramki pozostają wyłączone.

Uzwojenie DN ma rezystancję około 12 mΩ, więc niesymetria wysterowania mostka rzędu 10 mV daje prąd stały blisko 1 A i podmagnesowanie rdzenia. Regulator mierzy składową stałą prądu uzwojenia DN i ją kompensuje; próba obejmuje prąd magnesowania bez oznak jednostronnego nasycenia, także po skokach obciążenia.

Tranzystory MOSFET firm ST i Infineon mają odpowiednie napięcie i rezystancję katalogową; straty i chłodzenie oblicza się dla nagrzanych tranzystorów, a nie na podstawie prądu z nagłówka karty katalogowej ([ST](https://www.st.com/resource/en/datasheet/stp220n6f7.pdf), [Infineon](https://www.infineon.com/part/IPP030N06NF2S)). Sterowniki nie są zamienne bez zmian w układzie ([TI](https://www.ti.com/lit/ds/symlink/ucc27211.pdf), [ADI](https://www.analog.com/media/en/technical-documentation/data-sheets/4444fb.pdf)).

### Transformator i filtr

Moc 150 W dotyczy obciążenia rezystancyjnego i nie obejmuje dowolnego zestawu zasilaczy impulsowych. Ich współczynnik mocy, szczyty prądu i rozruch wymagają osobnej kwalifikacji. Przy minimalnym napięciu model daje tylko około 0,27 V zapasu po stronie DN, bez prądu magnesowania i strat przełączania. Jeśli próba zawiedzie, trzeba zmienić transformator lub obniżyć dopuszczalną moc; nie wolno podnosić progu zwarcia.

Zasilacz impulsowy bez PFC pobiera prąd szczytowy około trzykrotnie większy od wartości skutecznej. Laptop 60 W daje po stronie DN szczyty rzędu 50 A, a prąd ładowania kondensatora wejściowego zasilacza podłączanego pod napięcie wielokrotnie przekracza próg 75 A. Zasilacze podłącza się więc przed zamknięciem wyłącznika DC, a przetwornica rusza z łagodnym startem napięcia. Podłączenie pod napięciem może wyzwolić zatrzask FAULT; wymaga wtedy ręcznego restartu, ale nie może uszkodzić mostka.

T1 do pierwszej próby: rdzeń stalowy 50 Hz, Ae ≥14 cm², pole okna na uzwojenia ≥1200 mm². Uzwojenie dolnego napięcia (DN): 20 zwojów, cztery równoległe druty 1,8 mm; uzwojenie górnego napięcia (GN): 840 zwojów drutem 0,50 mm. Przekładnia: 42. Izolacja i odstępy muszą zapewniać separację od sieci; konstrukcję karkasu oraz barierę izolacyjną zatwierdza wykonawca transformatora.

Wymagany odbiór T1: rezystancja uzwojenia DN ≤12 mΩ, uzwojenia GN ≤25 Ω w temperaturze pracy; wytrzymałość izolacji i temperatura potwierdzone według dobranej normy. Same wymiary rdzenia nie gwarantują tych rezystancji. Przy 230 V i 150 W wartość skuteczna prądu uzwojenia DN wynosi w przypadku idealnym 27,4 A; trzeba doliczyć prąd magnesowania i prąd filtru.

Filtr początkowy po stronie 230 V: L = 10 mH, ≥1 A (wartość skuteczna), nienasycający się przy szczytach prądu zasilaczy; C = 1 µF/630 V DC, kondensator foliowy dopuszczony do pracy przy napięciu przemiennym. Równoległa gałąź tłumiąca: 100 Ω/2 W szeregowo z 0,47 µF/630 V. Rezystory rozładowujące: 2 × 150 kΩ/0,5 W połączone szeregowo. L, C i tłumienie wymagają pomiaru bez obciążenia oraz z rzeczywistymi zasilaczami; rezonans LC około 1,59 kHz nie jest dowodem stabilności ani THD.

Sprzężenie zwrotne napięcia: osobny transformator pomiarowy 230/6 V, ≥1 VA, za filtrem. Regulator mierzy wartość skuteczną; dzielnik ADC kalibruje się na stanowisku. Regulator podaje wstępne m = 230√2/(42×VBUS), z ograniczeniem 0,9 i powolnym startem. Mostek wyłączają: brak danych z ADC, zadziałanie układu nadzorującego (watchdog), przegrzanie, przetężenie, przepięcie po stronie AC i zbyt niskie napięcie BUS. Konkretne stałe regulatora i próg przepięciowy AC wymagają modelu oraz próby; oprogramowanie układowe sterownika jeszcze nie powstało.

### Wyjścia 230 V i PE

Wariant do odbioru elektrycznego: jeden punkt N–PE po stronie źródła, przed osobnymi dwubiegunowymi wyłącznikami RCBO typu A 30 mA dla każdego gniazda. PE obu gniazd i metalowej obudowy na wspólnej szynie; zewnętrzny zacisk do sprawdzonego układu uziemienia. Przewód PE nigdy nie jest przerywany przez wyłącznik. Dobór charakterystyki nadprądowej musi uwzględniać prąd rozruchu zasilaczy i ograniczenie samej przetwornicy. Układ zasila wyłącznie swoje gniazda, bez połączenia z obwodami zasilającymi budynku.

Wariant wymaga sprawdzonego PE lub zaprojektowanego lokalnego uziemienia. Jest to dodatkowy warunek dla zasilaczy klasy I, którego samo założenie „mamy samochód” nie zapewnia. Ani samo zwarcie N z PE, ani przycisk testowy wyłącznika różnicowoprądowego nie potwierdzają ochrony w schronieniu. Bez takiego uziemienia wariant dla przypadkowych zasilaczy klasy I pozostaje niezamknięty. Próby na stanowisku z zasilaczami klasy II nie dowodzą spełnienia całego wymagania. [Wytyczne HSE (nie jest to polska norma)](https://www.hse.gov.uk/pubns/priced/hsg141.pdf).

Do odbioru potrzebne są pomiary izolacji, ciągłości PE, prądu dotykowego, reakcji na uszkodzenie i działania ochrony przy źródle o ograniczonej wydajności prądowej. Moduły poziomu 3 (przetwornica 230 V, ładowarka, wejścia A/B) nie są urządzeniami radiowymi: podlegają dyrektywom LVD 2014/35/UE i EMC 2014/30/UE oraz WEEE, jak wszystkie moduły zestawu. Normy ustala jednostka badawcza (np. EN IEC 62477-1 lub EN 62368-1, EN 61558, EN IEC 61000-6-1/-3, EN 55032/55035). Przetwornica nie jest obecnie modułem do samodzielnego złożenia przez niewykwalifikowaną osobę. Po ukończeniu tej części otwarty projekt pozwoli różnym warsztatom ją wytwarzać, ale nie zwolni ich z obowiązku bezpiecznego wykonania.

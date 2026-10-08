# WICI R02: ustalenia i lekcje z R01.3

**Wstrzymane do decyzji po pilotażu (przegląd praktyczny 2026-10-08, F99):** pilotaż używa stacji z gotowej płytki MCU z układem LoRa SX1262 ([koncepcja 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html)).

Kontroler R01.3 (STM32F103 z modułem CC1120 według referencji TI, modem USB/KISS) powstał w wersji 0.4, gdy węzłem sieci był laptop. W 0.5 stacja jest samodzielna, więc kontroler stracił rolę: za mało RAM na stos Reticulum (D14), zasilanie z VBUS i kontrakt KISS z limitem 5 s nie pasują do stacji. Rewizje R01.2 i R01.3 doszły do zweryfikowanych plików produkcyjnych kontrolera, ale płytki nigdy nie zamówiono ani nie uruchomiono. Poniżej jest wszystko, co z tej pracy ma wartość dla R02. Pliki CAD, raporty i skrypty R01.3 są w historii Git do commitu `53a075a`.

## Tor RF

Referencja TI CC112xEM 868/915 ([archiwum projektu swrr091](https://www.ti.com/lit/zip/swrr091), [schemat tidr240](https://www.ti.com/lit/pdf/tidr240), [BOM tidr241](https://www.ti.com/lit/pdf/tidr241), [karta CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf)) ma cztery warstwy o grubości około 1,24 mm: miedź 4 × 35 µm, dielektryki 0,4 / 0,3 / 0,4 mm. Toru RF nie wolno przenosić na dwie warstwy ani na dowolny stos FR-4; dopasowanie zależy od geometrii i stosu. Dla R02 tor RF przenosi się razem ze stosem referencji, a parametry materiału uzgadnia z wykonawcą.

Konwersja archiwum CADSTAR do KiCad daje zero brakujących połączeń, lecz gubi reguły, obszary ograniczeń i priorytety pól miedzi; DRC importu zgłosił 204 naruszenia (172 wierceń, 4 stosów padów). Porównanie oryginalnych archiwów CSA i CPA obejmuje 156 wspólnych pinów bez różnic połączeń; 13 pól U1.34–U1.46 to masa pod układem. Import nadaje się jako wzór geometrii, nie jako plik do produkcji. Materiały TI podlegają warunkom TI i pozostają w lokalnym `reference-private/`; publikuje się własny projekt, nie kopię referencji.

Zegar radia: zwykły kwarc referencji nie spełnia P1. TI przewiduje opcjonalny TCXO X2 w obudowie 2,5 × 2,0 mm: X2, R322 = 0 Ω, C321 = 100 nF, C322 = 22 pF; nie montować X1, C311, R12 ani R321; C301 = 0 Ω zwiera XOSC_Q1, XOSC_Q2 zostaje niepodłączone. Te wartości nie kwalifikują dowolnego TCXO: poziom i kształt sygnału na EXT_XOSC oraz pojemność sprzęgająca wymagają sprawdzenia z wybranym układem. Przykładowy ATX-14-F-32.000MHZ-E05-T nie jest zatwierdzony: inna obudowa, a jego ±0,5 ppm dotyczy tylko temperatury; z tolerancją początkową po lutowaniu, starzeniem, zasilaniem i obciążeniem budżet dochodzi do ±3,9 ppm. Sama etykieta „TCXO ±0,5 ppm” nie spełnia budżetu ±2,0 ppm z [radio.md](../../docs/spec/radio.md); liczy się pełny budżet błędu i kalibracja ([karta ATX-14](https://abracon.com/datasheets/ATX-14.pdf)).

Harmoniczne: referencja TI nie ma filtru poza siecią dopasowania; 2. i 3. harmoniczną (1739 i 2609 MHz) mierzy się na stanowisku deweloperskim, a dodatkowy filtr dolnoprzepustowy wchodzi do R02 tylko przy przekroczeniu poziomu EN 300 220. Płytka S2-LP ma filtr harmonicznych jako wymaganie. Ochrona wyjścia RF: element ESD o małej pojemności przed złączem 50 Ω, z pomiarem wpływu na dopasowanie i moc. Filtr SAW 868 MHz: w topologiach TI i ST nadajnik i odbiornik mają wspólny węzeł RF, więc filtr wchodzi tylko w osobny tor odbiorczy za przełącznikiem SPDT albo we wspólny tor o wytrzymałości ≥+20 dBm; decyzję wyznacza pomiar blokowania LTE 800 i GSM 900 z filtrem i bez niego oraz strata wtrąceniowa wobec celu czułości.

Pomiary RF nigdy bez tłumika i ekranowania: nadajnika nie łączy się bezpośrednio z wejściem odbiornika; próby przewodowe w układzie 50 Ω z dobranym tłumikiem; 60 s nadawania przy rozwartym i 60 s przy zwartym złączu antenowym, a po nich moc i widmo bez zmian.

## Zasilanie i USB

Ustalenie F01 z [przeglądu](../../docs/review.md#f01-kontroler-usb): oscylator Y1 (ASE 8 MHz) miał pin standby na stałe w stanie wysokim, więc sam pobierał do 7 mA, gdy cały modem zasilany z USB miał w stanie wstrzymania budżet 2,5 mA. Odłączenie rezystora podciągającego D+ nie wyłączało zegara. Lekcja dla R02: każdy układ z pinem sterującym (standby, enable, shutdown) ma ten pin pod kontrolą MCU albo świadomie zapisany stan, a bilans prądu w każdym stanie urządzenia liczy się przed layoutem, nie po. R02 nie zasila się z VBUS: wykonanie A podaje VBUS tylko do PHY USB nRF52840, wykonanie B tylko do wykrycia hosta ([elektronika](../../docs/spec/elektronika.md)).

Udar przy podłączeniu: C1 = 1 µF przy wejściu nie opisuje całej pojemności, która pobiera energię z zasilania; są kondensatory za regulatorem i moduł RF. Dla R02 liczy się całą pojemność za sumą diodową i przetwornicą dla wejścia 12 V i podłączania pod napięciem (T6).

Bezpiecznik PPTC: „0,5 A” to prąd podtrzymania przy temperaturze katalogowej, prąd zadziałania wynosi 1 A, a podtrzymanie maleje z temperaturą. PPTC chroni gałąź przed przetężeniem, nie jest ogranicznikiem prądu ani ochroną przepięciową. Pomiar spadku napięcia, temperatury i deratingu należy do odbioru, nie do karty katalogowej.

Regulatory: AP2112K-3.3 i TLV75533 mają zgodną kolejność pinów SOT23-5, ale zamiana wymaga próby stabilności i temperatury; kondensator wyjściowy musi mieć wymaganą pojemność efektywną przy napięciu pracy i w zakresie temperatur, nie nominalną. Katalogowy prąd regulatora nie określa możliwości cieplnych płytki; temperaturę mierzy się przy ciągłym odbiorze i najwyższym dozwolonym cyklu nadawania.

## Zasady layoutu

- Ścieżki zasilania ≥0,5 mm; wyprowadzenia do pinów MCU 0,2 mm tylko na odcinkach poniżej 2 mm, policzone i zapisane w raporcie.
- Każdy kondensator odsprzęgający ma własną przelotkę do płaszczyzny zasilania i własną przelotkę masy; także filtr resetu.
- Warstwy wewnętrzne: In1 = masa, In2 = zasilanie, bez ścieżek; sygnały na warstwach zewnętrznych. W R02 tor RF ma własne wymagania co do masy pod układem i przelotek obwodowych, nadrzędne wobec tej zasady.
- Otwory montażowe nieplaterowane 3,2 mm, środki 4 mm od krawędzi, wokół każdego strefa bez miedzi, ścieżek i przelotek Ø6,4 mm; dystanse izolacyjne M3, bez metalowych podkładek większych niż strefa.
- Stos warstw zapisany jawnie w PCB i w `checks/stackup.json`: grubości miedzi i dielektryków, Dk, materiał. Wzorzec R01.3: JLC04161H-7628, nominalnie 1,6 mm (miedź 35 / 15,2 / 15,2 / 35 µm; prepreg 7628 0,2104 mm, rdzeń 1,065 mm, prepreg 0,2104 mm; Dk 4,4 / 4,6 / 4,4). Zapis stosu nie jest kwalifikacją impedancji; inny wykonawca potwierdza równoważną konstrukcję, nie podstawia dowolnej. KiCad zapisuje domyślny tangens strat 0,02, który nie jest parametrem materiału.
- Impedancja USB: dla stosu i geometrii trzeba ją policzyć i zapisać; DRC jej nie sprawdza.
- Reguły projektowe jawnie w `.kicad_dru` (odstęp 0,2 mm, ścieżka min 0,18 mm, przelotka 0,6/0,3 mm w R01.3); nie dodaje się wyjątków do naruszeń, a domyślne pominięcia KiCad wymienia się w raportach.

## Mechanika i złącza

- Przed zamówieniem drukuje się arkusz 1:1 (100%, bez dopasowania do strony, bez odbicia) z kreską kontrolną 50 mm i obrysem; mierzy kreskę, obrys i otwory, przymierza rzeczywiste złącza, przyciski, ekran i obudowę; wynik z MPN, osobą i datą zapisuje w `checks/`. Zgodny rozstaw otworów nie potwierdza numeracji styków.
- Pobrany model CAD złącza USB-B miał otwory ekranu 2,30 mm zamiast 2,50 mm z rysunku producenta; footprinty złączy rysuje się z rysunku wymiarowego, a nie z pobranego modelu.
- Przycisk: grupy padów w bibliotece KiCad nie muszą odpowiadać numeracji wyprowadzeń producenta (Omron B3F: pady grupy 1 to wyprowadzenia 3 i 4); sprawdza się, które nóżki są wspólne, a które zwiera naciśnięcie.
- Złącze IDC: otwory pinów 1,1 mm według karty, klucz i pin 1 potwierdzone z rysunkiem montażowym i rzeczywistym przewodem; widok od spodu odwraca obraz, więc tabele połączeń podają numery elektryczne, nie kolejność żył.
- Rysunek montażowy w skali 2:1 służy do montażu, a osobny arkusz 1:1 do przymiarki; plik pozycji używa początków i obrotów footprintów KiCad i nie jest programem maszyny.

## Części i zamienniki

- MCU wybiera się od pamięci: STM32F103 (20 KiB RAM) odpadł, bo port Reticulum potrzebuje kilkuset kilobajtów; R02 wymaga ≥256 KiB z zapasem ≥30% zmierzonym w T3.
- Każda część ma dwóch producentów w BOM ze stanem kwalifikacji; zgodna obudowa nie oznacza zgodności układu; zamiennik wymaga próby, nie tylko porównania kart.
- Rezystory 1%, kondensatory X7R o napięciu z zapasem; zapisuje się pojemność efektywną, nie nominalną.
- Źródła kart katalogowych zapisuje się z adresem, datą pobrania i sumą SHA-256 (`sources.json` w R01.3); karty, których nie da się pobrać, oznacza się jako przeczytane online.

## Proces kontroli i dowody

- ERC i DRC z `kicad-cli` z opcjami `--severity-all`, `--exit-code-violations`, `--schematic-parity`, `--refill-zones`; wynik 0 bez wyjątków; raporty JSON w `checks/`. DRC po zapisie pól miedzi może zmienić bajty PCB, więc dalsze sumy liczy się z tego zapisu.
- Odtworzenie: skrypty i zachowana sesja trasowania dają identyczną geometrię, schemat, BOM i połączenia; porównanie pomija UUID i pamięć wypełnienia pól. Zmieniona geometria wymaga przeglądu i nowej rewizji, nie dopisania „PASS”.
- Eksporty porównuje się z geometrią PCB niezależnym parserem (gerbonara): pady warstwy górnej, obrys, wiercenia z dokładnością zaokrąglenia Excellon 1 µm, pozycje i BOM z MPN. Eksporty KiCad zawierają czas, więc porównuje się geometrię, nie bajty.
- Paczka produkcyjna zawiera README dla wykonawcy, NOTICE z sumami źródeł, pełne teksty licencji, stos i arkusz 1:1; kontrola paczki ma tryb `--check`, który niczego nie przepisuje, a status i manifest sum aktualizuje się tylko po przeglądzie poprawnych raportów.
- Pliki DSN/SES/XML z narzędzi przechowują ścieżki bezwzględne; przed publikacją zamienia się je na względne, a kontrola repozytorium odrzuca ścieżki `/Users` i `/private/tmp`.
- DRC KiCad na macOS w ograniczonym środowisku kończył się błędem inicjalizacji aplikacji; uruchamia się go poza takim środowiskiem. Nie uruchamia się dwóch procesów KiCad naraz; Python KiCad (`pcbnew` z instalacji) jest osobny od Pythona narzędzi i nie zastępuje go pakiet `pcbnew` z PyPI.
- CI nie uruchamia KiCad; sprawdza sumy, składnię, linki i spójność dowodów. Status HOLD zdejmuje odbiór fizyczny, nie zielone CI.

## Uruchomienie

Kolejność z R01.3 przeniesiona na samozasilaną stację; szczegóły i warunki zaliczenia w [odbiorze](../../docs/spec/odbior.md).

| Krok | Czynność | Warunek przejścia |
|---:|---|---|
| 1 | Oględziny płytki bez ogniw i 12 V: orientacja układów, mostki, pomiar rezystancji szyn względem masy | brak mostków i utrzymującego się zwarcia |
| 2 | Zasilanie z zasilacza laboratoryjnego z limitem prądu najpierw na wejście ogniw, potem 12 V; MCU bez programu | szyna 3V3 ±5%, szyna 5 V ekranu po włączeniu, brak nagrzewania; sterownik wyłącznika i komparator zaniku zasilania reagują na progi |
| 3 | SWD bez podawania zasilania z programatora; obraz testowy | właściwy MCU, poprawna weryfikacja, reset wraca do pracy; ochrona odczytu pamięci włączona dopiero po uruchomieniu |
| 4 | Zegary: kwarc MCU, 32,768 kHz, TCXO radia; pomiar częstotliwości przyrządem ≤0,1 ppm | stabilny start; błąd TCXO w budżecie ±2,0 ppm po kalibracji |
| 5 | USB-C: dwa interfejsy CDC na Windows, Linux i macOS; 100 odłączeń przewodu; uśpienie hosta | brak zawieszeń, stacja nie zasila się z VBUS, praca niezależna od hosta |
| 6 | Radio pierwszy raz tylko w RX/IDLE: identyfikator układu, rejestry, reset, przerwania; SPI około 1 MHz | zgodne odczyty, obie linie przerwań działają; nie nadawać przy błędzie |
| 7 | Dwa egzemplarze: próba przewodowa w ekranowanym układzie 50 Ω z tłumikiem; potem 60 s TX przy rozwartym i 60 s przy zwartym złączu | częstotliwość, moc, widmo z harmonicznymi i czułość w granicach P1; po niedopasowaniu moc i widmo bez zmian |
| 8 | 1000 datagramów w obu kierunkach o długościach 1/86/87/600 B; przerwania zasilania w trakcie zapisu FRAM | brak uszkodzonej treści; raport utrat i ponowień; brak TX po restarcie bez ważnego dziennika długu ciszy |
| 9 | Pomiar zajętości podpasma 869,4–869,65 MHz w miejscu próby, próba antenowa, pomiar w obudowie | zapis odległości, wysokości i typu anten, przewodów, rewizji, RSSI, PER, liczników CCA i CRC, temperatury; wniosku o 1 km nie wyciąga się z próby na stole |

Montaż QFN i elementów RF 0402 lepiej zlecić. Każdy egzemplarz dostaje zapis: numer, rewizje PCB i oprogramowania, użyte części, pomiary, wynik i osobę. Dwie sztuki to minimum do próby łączności; ich wynik nie potwierdza serii.

## Co z R01.3 nie przechodzi

Schemat i PCB kontrolera (STM32F103, USB-B, EEPROM M24C64, LDO AP2112, programator SWD, złącze IDC do modułu TI), kontrakt modemu USB/KISS z dziennikiem długu ciszy w EEPROM, paczka produkcyjna `wici-controller-R01.3.zip` oraz skrypty eksportu i kontroli związane z tym projektem. Wszystko to pozostaje w historii Git (commit `53a075a`, folder `hardware/radio-test-r01/`). Mapa połączeń modułu CC1120EM z tamtego projektu jest w opisie [stanowiska deweloperskiego](../dev-bench/README.md#złącza-modułu-cc1120em).

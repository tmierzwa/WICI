# WICI: płytka v2, schemat wstępny

**Status 2026-10-31: schemat i rozmieszczenie wstępne, bez ścieżek. Nie zamawiać.** Schemat zbiera w jednym projekcie KiCad płytkę v1.1 prototypu i tor zasilania stacji pilotażowej ([elektronika](../../docs/spec/elektronika.md#stacja-pilotażowa)). Wartości elementów pochodzą z [projektu zasilania](../r02/zasilanie.md) i z [płytki testowej przetwornicy](../przetwornica-3v3/README.md). Obrys i rozmieszczenie są wstępne i opierają się na założeniach obudowy ([Rozmieszczenie wstępne](#rozmieszczenie-wstępne)). Ścieżki czekają na model Hammonda, wyniki pomiarów i krok 4 (sekcja [Przed płytką drukowaną](#przed-płytką-drukowaną)).

| Plik | Zawartość |
|---|---|
| [schemat.pdf](schemat.pdf) | schemat (arkusz A0, połączenia przez etykiety sieci, jak w v1) |
| [polaczenia.md](polaczenia.md) | sygnały MCU i wszystkie sieci |
| [bom.csv](bom.csv) | lista części z producentami i numerami, tam gdzie są już wybrane |
| `cad/plytka-v2.kicad_sch`, `cad/plytka-v2.kicad_pcb` | projekt KiCad 10.0.6: schemat i płytka z rozmieszczeniem wstępnym, bez ścieżek |
| `checks/erc.json`, `checks/netlist.xml`, `checks/drc.json` | ERC (0 naruszeń), lista połączeń i DRC rozmieszczenia (tylko uwagi o sitodruku i niepołączone pady) |
| `tools/design.py` | jedyne źródło: części, piny, sieci i sprawdzenia przydziału pinów |
| `tools/make_pcb.py` | obrys, otwory i rozmieszczenie: założenia, położenia stałe i obszary bloków |

Odtworzenie: `hardware/plytka-v2/tools/build.sh` (KiCad 10.0.6). Skrypt sprawdza przydział pinów, generuje schemat, BOM i listę połączeń, uruchamia ERC, rysuje PDF, rozmieszcza elementy na płytce i uruchamia DRC. Plików w `cad/` nie edytuje się ręcznie.

## Co zmienia się względem v1.1

| Blok | v1.1 (prototyp L0) | v2 |
|---|---|---|
| MCU | DevKitC w J5/J6, zasilana z USB | ta sama DevKitC v1.1 (N8R8) w J5/J6, zasilana przez piny 3V3 z przetwornicy; pin 5V wolny |
| Radio | Wio na przewodach obok płytki | Wio w gniazdach J8/J9 (2 × 1x7, 2,54 mm), zasilanie przez zworkę pomiarową JP3, przy module C1, C2 i RXEN 10 kΩ (R64); SCK za R18, jak ekran i FRAM |
| Gniazda TI, ST, Nordic | J1–J4, J9, J10, JP3, R17, otwory Arduino | wypadają |
| USB do laptopa | złącze micro USB DevKitC | gniazdo USB-C J4 bez zasilania z VBUS (VBUS tylko na bramkę Q12 wykrywania laptopa), CC1 i CC2 przez 5,1 kΩ, ochrona ESD U8 |
| Ekran, FRAM, przyciski, dioda | bez zmian | bez zmian (te same oznaczenia) |
| Brzęczyk | z pinu 5V DevKitC przez JP2 | z szyny 5 V ekranu (U2), bo pin 5V DevKitC jest martwy przy zasilaniu przez 3V3 |
| Pomiar | VTEST (J12) i złącze analizatora J11 | J11, J12 i dzielnik VTEST wypadają; pomiar ogniw i 12 V na GPIO4 i GPIO5 |
| Zasilanie | brak | ogniwa 4 × AA i 12 V na wspólną szynę VSYS, sterownik przycisku, przetwornica 3,3 V |

## Tor zasilania

```text
J1 4×AA ─ R40 1 Ω ─ D7 Schottky ─────────────────────────────┬─ VSYS ─ C50 ─ U7 LTC3115-1 (RUN ← Q9) ─ +3V3
J2 12 V ─ F1 T1A ─ D4 TVS 33 V ─ Q2 ─(wspólny dren)─ Q3 ───────┘
                                  └ U5 LM74800-Q1: DGATE, HGATE, OVP 16,8 V, EN/UVLO ← dzielnik przez Q4
suma diodowa D8 (ogniwa) i D9 (wspólny dren przez R46, C35, D10 33 V) ─ VCTL ─ U6 LTC2955-2 ─ Q8 ─ szyna ON
V12 ─ R70/R71 ─ ON U6 (zbocze narastające przez około 9 V włącza)
VCTL ─ R48/D16 ─ KILL U6 ← Q11 ← GPIO47
ON ─ Q5 ─ Q4: dzielnik 12 V (EN/UVLO U5 i ADC)    ON ─ Q10 ─ Q9: RUN przetwornicy z VSYS
```

- **Włączenie z samego 12 V (bez ogniw):** wspólny dren Q2/Q3 dostaje napięcie przez diodę podłożową Q2 także przy wyłączonym U5 (karta LM7480-Q1, 9.4). Z niego przez R46 i D9 zasilany jest sterownik U6. Naciśnięcie przycisku (J3) daje szynę ON. ON podłącza przez Q4 dzielnik 12 V do EN/UVLO U5, a przy V12 ≥11,9 V (najwyżej 12,3 V) U5 włącza Q3 i zasila VSYS. Równolegle ON przez Q10 i Q9 podaje VSYS na RUN przetwornicy.
- **Samoczynne włączenie z 12 V:** stacja ma być włączona zawsze, kiedy to możliwe (decyzja 4). Dzielnik R70/R71 (309 kΩ / 30,1 kΩ, 0,1%) podaje 12 V na wejście ON sterownika. Zbocze narastające przy 8,56–9,46 V (nominalnie 9,01 V; próg ON 0,76–0,84 V, upływ D13 dodaje do około 0,3 V) włącza stację jak przycisk. Próg leży poniżej napięcia każdego działającego źródła, więc każde podłączenie i każdy powrót 12 V po zaniku włącza stację, także akumulator 12,6 V w spoczynku i napięcie narastające powoli z panelu. Próg może leżeć poniżej progu włączenia UV: sterownik zostaje włączony i czeka, a U5 załącza 12 V, gdy napięcie dojdzie do około 11,9 V. W obudowie TSOT-23 opadające zbocze ON nic nie robi, a stałe 12 V nie włącza stacji z powrotem po wyłączeniu przyciskiem. Wyłączenie ręczne trwa więc do następnego podłączenia albo powrotu 12 V; rozruch silnika, przy którym napięcie spada poniżej około 9 V, też włączy stację. Dzielnik pobiera z podłączonego 12 V 35 µA także przy wyłączonej stacji.
- **Podtrzymanie bez 3,3 V:** KILL jest podciągnięty z VCTL, czyli z zasilania U6 (R48 470 kΩ, Zener D16 5,1 V wobec 6 V dopuszczalnych), a nie z +3V3 ani z szyny ON. Gdy 12 V spadnie poniżej progu UV bez ogniw, znika 3,3 V, ale sterownik zostaje włączony i stacja wraca sama, gdy tylko 12 V da się znów użyć. Po całkowitym zaniku 12 V bez ogniw KILL idzie za VCTL do około 0,8 V, więc U6 traci stan przez podnapięcie zasilania (0,8–1,3 V), a nie przez KILL. Po powrocie 12 V startuje z wysokim ON i włącza stację po około 1 s (karta LTC2955, „ON Pin Initial Turn-On”). Z KILL na szynie ON zanik trwający 0,2–1,6 s kończyłby się w blokadzie 0,6–1,4 s po zwolnieniu EN i stacja zostałaby wyłączona. Przy VCTL około 3,6 V (słabe ogniwa) KILL zostaje powyżej 2 V przy upływie Zenera 2 µA i Q11 1 µA w 25 °C. Czekający sterownik pobiera z rozładowanego akumulatora do około 0,4 mA (U5 i dzielnik UV).
- **Włączenie z ogniw:** U6 zasilany przez D8, dalej tak samo. U5 zostaje wyłączony, bo dzielnik 12 V leży przed Q2, więc bez 12 V daje 0 V.
- **Wyłączenie:** program ściąga KILL przez Q11 (GPIO47; pin MCU nie widzi napięcia KILL, a R72 trzyma Q11 wyłączony przy resecie, w uśpieniu i bez zasilania MCU), a bez MCU wyłącza przytrzymanie przycisku przez 5–19 s (C37 2,2 µF, nominalnie około 11,5 s). Szyna ON znika, Q4 odłącza dzielnik (U5 w wyłączeniu 2,87 µA), a Q9 zdejmuje RUN.
- **Stan wyłączony z ogniw:** LTC2955 1,2/3 µA, LTC3115-1 3/10 µA, LM74800 przez diodę podłożową Q3 2,9/5 µA i upływy kluczy. To ten sam bilans co w [projekcie zasilania](../r02/zasilanie.md#bilans-prądu-w-stanie-wyłączonym), około 7/19 µA, plus upływ C50 i podciągnięcie KILL z VCTL (R48, około 3–6 µA przy świeżych ogniwach, zależnie od kolana D16). Z 12 V przy wyłączonej stacji dochodzą dzielnik ON (35 µA) i R48 (około 15 µA).
- **RUN ≤ VIN + 0,3 V:** RUN dostaje napięcie z VSYS przez Q9, a nie z szyny ON. ON idzie za stroną 12 V także przy otwartym łączniku (np. przy 24 V), a VSYS jest wtedy z ogniw. R55 220 kΩ ściąga RUN, a prąd histerezy RUN (0,5 µA, wypływa z pinu w pracy) daje na nim tylko 0,11 V, więc przetwornica naprawdę się wyłącza. Na płytce testowej 10 MΩ tego nie zapewniało.
- **Klucze przy końcu ogniw:** przy ogniwach około 4 V szyna ON ma około 3,3 V. Bramki Q5 i Q10 dostają więc 91% ON przez dzielnik 100 kΩ / 1 MΩ, a Q8 91% VCTL, czyli około 3 V wobec progu 2N7002 do 2,5 V. Zenery 15 V (D12, D14, D15) ograniczają VGS przy stronie 12 V do 35 V.
- **Wykrywanie laptopa (czuwanie):** uśpiony MCU nie obsługuje USB, więc VBUS laptopa przez R73/R74 (100 kΩ / 1 MΩ, Zener D17 15 V) włącza Q12, który ściąga USB_LAPTOP (GPIO3, R75 100 kΩ do +3V3). Stan niski budzi stację z [czuwania](../../docs/spec/oprogramowanie.md#czuwanie) i nie pozwala jej zasnąć. VBUS zasila tylko bramkę (około 5 µA), więc laptop nie zasila stacji, także wyłączonej, i nie podnosi 3,3 V przez diody ochronne MCU.
- **Pomiar:** ogniwa przed R40 przez klucz Q6 (DIV_EN, GPIO46), 7,3 V daje 1,49 V. 12 V z dzielnika UV (0,0625 × V12, 36 V daje 2,25 V), tylko przy włączonej stacji. Oba wejścia ADC mają BAT54S.

## Przydział pinów

Przypisania v1.1 zostają. Nowe sygnały są w tabeli „Sygnały MCU” w [polaczenia.md](polaczenia.md): V_AA_ADC (GPIO4, dawniej RF_GPIO2, którego Wio nie używa), V_12_ADC (GPIO5, dawniej VTEST), DIV_EN (GPIO46), PWM_SYNC (GPIO45), PWR_INT (GPIO48), KILL_MCU (GPIO47, wyłączenie przez Q11), USB_LAPTOP (GPIO3, wykrywanie laptopa) i USB D+/D− (GPIO20/19).

Wszystkie inne piny DevKitC są zajęte, dlatego użyto pinów konfiguracji startu GPIO45 i GPIO46. Każdy ma rezystor do masy (R63, R43), który daje ich domyślny niski stan przy resecie: GPIO45 wybiera 3,3 V dla pamięci flash, a GPIO46 nie może być wysoki razem z niskim GPIO0. GPIO47 i GPIO48 mają poziom 3,3 V w module WROOM-1 (N8R8); w modułach WROOM-2 z 1,8 V by go nie miały, więc płytka wymaga DevKitC-1-N8R8 v1.1 (dioda RGB na GPIO38). `design.py` sprawdza te zasady przy każdym generowaniu. GPIO3 (USB_LAPTOP) jest pinem konfiguracji startu tylko po zapisaniu bezpiecznika STRAP_JTAG_SEL, którego stacja nie zapisuje. Wolnych pinów nie ma.

## Rozmieszczenie wstępne

Płytka ma obrys i rozmieszczenie wszystkich 152 elementów, bez ścieżek. Służy do sprawdzenia, czy całość mieści się w obudowie, i do renderu, a nie do zamówienia. `make_pcb.py` ustawia elementy panelu i złącza na sztywno, a małe elementy każdego bloku układa automatycznie w jego obszarze, każdy najbliżej poprzedniego. Zatrzymuje się, gdy coś nachodzi na inny element, na strefę albo na krawędź, i gdy element ochronny lub odsprzęgający leży za daleko od swojego układu (sprawdzenia `CLOSE`, odległość pad–pad):
- ESD U8 ≤10 mm od USB-C J4, TVS D4 ≤10 mm od J2 (zasada z [obudowy R02](../r02/obudowa.md#płyta-bazowa-obrys-i-ograniczenia));
- kondensatory wejściowe i wyjściowe przetwornicy ≤5–6 mm od U7;
- C1 i C2 ≤8 mm od gniazda Wio, C36 ≤5 mm od U6, C11 ≤5 mm od U4.

Każdy element jest powiązany ze swoim symbolem w schemacie (ścieżka z tego samego UUID co w `make_schematic.py`), więc KiCad widzi płytkę i schemat jako jeden projekt. Wynik jest powtarzalny: dwa przebiegi dają ten sam plik. DRC zgłasza tylko uwagi o sitodruku i niepołączone pady, bo ścieżek jeszcze nie ma. Bez sieci są celowo: pad termiczny U5 (karta LM74800, tabela 6-1), wolny styk 3 przełącznika SW5 i piny 4 i 5 U3, których schemat nie używa.

Założenia, do sprawdzenia na modelu STEP Hammonda i na przymiarce:

- **Obrys:** 200 × 120 mm z narożnikami R4 i wycięciami 12 × 12 mm na słupki śrub pokrywy. Płytka zajmuje obszar pokrywy Hammond 1599KBAT x 10–210 mm i y 10–130 mm ([obudowa R02](../r02/obudowa.md#płyta-bazowa-obrys-i-ograniczenia)), więc współrzędne płytki to współrzędne pokrywy minus 10 mm.
- **Panel od strony pokrywy:** środek okna ekranu, rząd WSTECZ–GÓRA–DÓŁ–OK w rozstawie 32 mm, dioda alarmu, CISZA i przycisk przygotowania leżą na pozycjach z [założeń obudowy](../obudowa/zalozenia.py) (`PANEL`). Wyłącznik główny PV6 jest w pokrywie i łączy się przewodem z J3, więc pod nim płytka ma wolną strefę Ø22 mm. Złącze FPC J7 leży 13,8 mm pod krawędzią panelu, jak na v1.1.
- **Strefy panelu od góry:** okno ekranu 64 × 45 mm; strefa 22 × 22 mm wokół każdego przycisku rzędu; osłona CISZA 30 × 40 mm (tylko SW5); bez padów w promieniu 10 mm od otworu przycisku przygotowania (tylko SW6 i otwór H4 w jej skraju).
- **Złącza na dolnej krawędzi:** USB-C J4 pod otworem w ścianie (pokrywa x 60). EN3 (x 110) i SMA (x 170) są w ścianie: EN3 łączy się przewodem z J2, a SMA krótkim przewodem koncentrycznym z u.FL Wio.
- **Moduły od spodu (decyzja 6):** DevKitC i Wio siedzą w gniazdach od spodu płytki. Patrząc z góry, rzędy gniazd zamieniają się stronami (J6 po lewej, J5 po prawej), żeby moduł widziany od spodu stał jak na v1.1. Rozstaw rzędów Wio przyjęto 15,24 mm, do potwierdzenia na rysunku Seeed. Zworka pomiarowa JP3 leży od góry tuż obok gniazd Wio.
- **Tylko THT od spodu:** wszystkie elementy SMD są od góry, więc montaż SMT jest jednostronny (jeden szablon, jeden przebieg pieca). Od spodu są tylko gniazda modułów, F1 i C50, lutowane ręcznie albo na fali.
- **Strefa koszyka ogniw:** BH4AAW leży w podstawie pod płytką (x 10–72, y 58–116), około 19 mm pod nią. Od spodu w tej strefie są tylko końcówki wyprowadzeń THT i otwór H3.
- **Wysokości od góry:** płytka około 12 mm za frontem. Elementy górne poza panelem mają do około 9 mm (brzęczyk CEM-1203 do sprawdzenia). Wysoki kondensator C50 i oprawka bezpiecznika F1 są od spodu, poza strefą koszyka.
- **Otwory montażowe:** H1 i H2 przy górnej krawędzi w rozstawie 80 mm. H3 leży nad koszykiem ogniw, więc łeb śruby albo tuleja od spodu mogą mieć najwyżej około 3 mm. H4 jest 12 mm od przycisku przygotowania, na skraju jego strefy. Właściwe położenia daje model STEP.

## Decyzje (2026-10-31)

Schemat i rozmieszczenie odchodzą od wcześniejszej specyfikacji i założeń w sześciu miejscach. Autor przyjął wszystkie, a [elektronika](../../docs/spec/elektronika.md#zasilanie-stacji), [projekt](../../docs/spec/projekt.md), [instrukcja](../../docs/spec/instrukcja.md), [odbiór](../../docs/spec/odbior.md) i [BOM stacji](../../docs/spec/bom-stacji.csv) zostały do nich dopasowane.

1. **Odcięcie UV z komparatora LM74800, bez osobnego nadzorcy.** Elektronika wymagała wyłączenia poniżej 11,5 V i włączenia powyżej 12,4 V, a akumulator 12,6 V w spoczynku musi uruchomić stację. EN/UVLO U5 ma stałą histerezę (1,231/1,132 V, czyli 8%) i tolerancję ±2,9%, więc obu warunków naraz nie spełni. Przyjęte progi:
   - włączenie 11,94 V (11,59–12,29 V), więc pełny akumulator zawsze zasili stację;
   - wyłączenie 10,98 V (10,58–11,24 V).

   Do tego dochodzi do 0,04 V od upływu pinu EN/UVLO (do 200 nA na dzielniku 246 kΩ). Mniejszy dzielnik zmniejszyłby błąd, ale pobierałby więcej niż 50 µA z 12 V przy włączonej stacji.

   Odrzucony wariant: nadzorca ADI LTC2965 z progami 11,5/12,4 V. Dodaje układ i 3–4 rezystory, a stacja pobiera z 12 V kilkadziesiąt miliamperów i ma ogniwa jako zapas, więc różnica 0,4 V w progu wyłączenia niewiele zmienia dla akumulatora. LTC2965 wraca na EN/UVLO, jeśli pilotaż pokaże za głębokie rozładowanie.
2. **Sterownik przycisku zasilany ze wspólnego drenu, a nie „tylko z 12 V za łącznikiem albo z ogniw”.** Włączony LM74800 pobiera 397 µA, więc przy wyłączonej stacji musi być w stanie wyłączenia (2,87 µA). Wtedy za łącznikiem nie ma napięcia, a bez ogniw stacja nie włączyłaby się z samego 12 V. Wspólny dren ma napięcie przez diodę podłożową Q2, ale idzie za wejściem do 33 V ciągle i do 53,3 V w impulsie. Dlatego przed sumą diodową są:
   - R46 1 kΩ w obudowie 2512;
   - C35 1 µF;
   - Zener 33 V (D10, 31–35 V).

   LTC2955 widzi najwyżej około 35 V (praca do 36 V). Przy instalacji 24 V (do 28,8 V) D10 nie przewodzi. Przy 33 V ciągle może przewodzić do około 2 mA, ale to już stan awaryjny poza zakresem pracy.

   Odrzucone warianty:
   - dosłownie według specyfikacji: bez ogniw nie ma startu z 12 V;
   - LM74800 stale włączony: około 0,4 mA z 12 V przy wyłączonej stacji, a limit to 0,1 mA.
3. **Brzęczyk z szyny 5 V ekranu.** Impulsy 2 kHz (do około 75 mA) idą po tej samej szynie co VDD panelu. Tętnienia przy pracy brzęczyka mierzy się oscyloskopem, tak jak na v1. Gdyby były za duże, przed panelem dochodzi filtr RC albo dławik.

   Odrzucone warianty:
   - brzęczyk z +3V3: impulsy na szynie radia i MCU;
   - osobna przetwornica 5 V dla brzęczyka.

4. **Stacja włączona zawsze, kiedy to możliwe.** Przekaźnik ma wartość tylko wtedy, gdy działa. Koncepcja wymaga samoczynnego startu po całkowitym zaniku i powrocie 12 V ([rozdział 03](../../docs/concept/03-dostepne-rozwiazania.html#spolecznosci-meshcore-i-meshtastic)), a przekaźnik stały nie może wymagać wizyty. Dlatego ON reaguje na każde podłączenie i powrót 12 V (próg około 9 V), a KILL nie zależy od 3,3 V (podtrzymanie wyżej). Wyłączenie ręczne trwa do następnego podłączenia albo powrotu 12 V.

   Odrzucone warianty:
   - próg ON powyżej progu UV (13,2 V, najwyżej 13,9 V): akumulator w spoczynku nie włącza stacji, a po spadku poniżej progu UV bez ogniw stacja czeka na ładowanie albo przycisk;
   - bez samoczynnego włączenia: po każdym zaniku bez ogniw stacja czeka na wizytę;
   - sam niski próg ON z KILL podciągniętym do +3V3: przy powoli narastającym 12 V sterownik wyłącza się po 0,5 s wygaszania, zanim U5 załączy 12 V;
   - KILL z szyny ON: zanik 12 V bez ogniw trwający 0,2–1,6 s kończy się w blokadzie po zwolnieniu EN, więc zbocze ON przepada i stacja zostaje wyłączona;
   - stacja włączona zawsze, bez wyłączenia ręcznego przy 12 V: nie da się jej wyłączyć do transportu ani przechowania.
5. **Wykrywanie laptopa dla czuwania.** Przekaźnik śpi między pakietami ([koncepcja, rozdział 06](../../docs/concept/06-wykonalnosc-i-budzet-zasobow.html#czuwanie-przekaznika)), a uśpiony MCU nie obsługuje USB. Q12 z VBUS na GPIO3 budzi stację i trzyma ją bez uśpienia przy laptopie.

   Odrzucony wariant: rozpoznawanie laptopa tylko w programie (TinyUSB). Nie wymaga części, ale uśpiony MCU może nie odpowiedzieć laptopowi przy pierwszym połączeniu, a poprawka po zamówieniu płytek jest droga.

6. **DevKitC i Wio od spodu płytki.** Panel Sharp leży kilka milimetrów za pokrywą, a DevKitC w gniazdach sięga około 16 mm nad płytkę (gniazdo 8,5 mm, listwa 2,5 mm, płytka modułu i WROOM). Moduły od spodu wiszą w głębi skrzynki (33 mm wnętrza), a pokrywa zostaje płaska.

   Odrzucony wariant: moduły od góry, jak na v1.1. Prostszy dostęp do modułów, ale pokrywa potrzebuje garbu nad DevKitC albo wgłębionego okna ekranu ([obudowa](../obudowa/README.md#co-jest-znane-a-co-trzeba-zmierzyć)). Kosztem wybranego wariantu jest dostęp do DevKitC i jego micro USB dopiero po wyjęciu płytki; program wgrywa się i tak przez USB-C stacji.

Do tego dochodzą zmiany w zakresie, które specyfikacja zostawia projektowi v2: J11 (analizator), J12 i dzielnik VTEST oraz zworki JP1/JP2 wypadają według zasady „nic na zapas”. JP3 zostaje, bo specyfikacja wymaga punktu pomiaru prądu radia.

## Przed płytką drukowaną

Otwarte w schemacie:
- D7 (dioda toru ogniw): część po sprawdzeniu dopuszczalnego prądu wstecznego ogniw L91;
- C50 (kondensator szyny VSYS): wartość i część po próbie przełączania 12 V ↔ ogniwa;
- R32 (rezystor szeregowy C_dVdT): karta nie podaje wartości;
- Wio: rozstaw rzędów J8/J9 i funkcje pinów J1.6, J1.7, J2.7 z rysunku i schematu Seeed (na razie niepodłączone);
- oprawka bezpiecznika F1 i numery LCSC części spoza puli JLC (SI2309CDS, BSS84AK, BAS116H, BZT52, USBLC6-2SC6, gniazdo USB-C);
- przyciski: rozmiar i rozstaw pod obudowę i rękawice;
- Q2 przy odwróconym impulsie i świeżych ogniwach widzi około 59,7 V (wspólny dren trzyma około VSYS − 0,6 V przez Q3, wejście −53,3 V): tranzystor 60 V nie ma zapasu, rozważyć 80–100 V;
- upływ U5 z C do A przy pracy z ogniw: wejście 12 V obciążają tylko dzielniki (246 kΩ równolegle z 329 kΩ, około 140 kΩ), więc EN/UVLO dojdzie do 0,3 V dopiero przy kilkunastu µA upływu; napięcie EN mierzy się na płytce przy pracy z ogniw bez 12 V;
- upływ BAT54S (D6, D11) i BAT54H (D13) w podwyższonej temperaturze: około 1 µA na węźle ADC 12 V (około 13 kΩ) to około 0,2 V na wejściu 12 V, czyli część budżetu błędu ADC ≤2%; na węźle ON (około 27 kΩ) podnosi próg samoczynnego włączenia o około 0,3 V (próg 8,56–9,46 V bez upływu, do około 9,8 V z upływem). Do sprawdzenia w karcie wybranej diody
- prąd w stanie wyłączonym z ogniw: typowo około 13 µA z R48 (około 4% pojemności ogniw na rok przechowywania); z wartości maksymalnych kart i upływu C50 najgorszy przypadek przekracza 20 µA (cel z projektu zasilania), mieści się w 0,1 mA ze specyfikacji;
- zasilanie +3V3 od tyłu w stanie czekania bez 3,3 V: dzielnik 12 V zostaje podłączony (Q4), więc węzeł V_12_ADC (0,0625 × V12) przez D6 i diody ochronne GPIO5 podnosi martwą szynę 3,3 V. Przy 10–11,9 V to około 0,5 V. Przy 24–33 V bez ogniw (OVP) to około 1,3–1,8 V, a wtedy reset przy późniejszym włożeniu ogniw może nie być czysty. Pomiar +3V3 w obu stanach i 10 startów po włożeniu ogniw w stanie 24 V; gdyby zawiodły, pomiar 12 V dostaje osobny dzielnik z kluczem DIV_EN, jak ogniwa;
- KILL przy słabych ogniwach i w 60 °C: upływ D16 i Q11 rośnie z temperaturą, a przy około 5,5 µA KILL spada do 0,8 V i stacja się wyłącza. Pomiar na ciepło przy VCTL 3,6 V;
- ON przy odwróconym 33 V: przez D13 płynie około 107 µA, a spadek BAT54H na zimno sięga −0,3 V, granicy dla ON. Bez zapasu; rozważyć diodę o mniejszym spadku albo większy R70 (zmiana progu);
- Burst Mode U7 (typowo poniżej 50 mA) przy starcie ESP32-S3, panelu i 4 V na wejściu: sprawdzić na płytce testowej razem z progiem nadzorcy FRAM 2,7 V.

Poza schematem:
- obudowa (pomiary z przymiarki, model Hammond 1599KBAT): potwierdzenie obrysu, otworów, wysokości złączy na dolnej krawędzi i odstępu do ściany (dziś płytka kończy się około 7 mm przed ścianą, a złącza mają leżeć 0–1 mm od niej); rozstaw rzędów Wio;
- ścieżki po potwierdzeniu rozmieszczenia: tor RF krótko od Wio, przetwornica z dala od ekranu, ESD i TVS ≤10 mm od złączy;
- pomiary z [elektroniki](../../docs/spec/elektronika.md#zasilanie-stacji): sprawność LTC3115-1 przy 3,3 V (Z11), pobór DevKitC przez 3V3, próby na płytkach ewaluacyjnych;
- wnioski z kroku 4 i decyzja: moduły wpinane czy przylutowany ESP32-S3 i układ radiowy;
- program stacji: piny GPIO3, GPIO4, GPIO5 i GPIO45–48, ADC ogniw i 12 V, KILL i INT, [czuwanie](../../docs/spec/oprogramowanie.md#czuwanie);
- pobór DevKitC przez 3V3 w lekkim uśpieniu MCU (dioda zasilania, dioda RGB, CP2102N, stabilizator zasilany od wyjścia; szacunek 1–2 mA).

## Źródła

- TI LM7480-Q1 (SNOSD95C): tabela 6-1 (wyprowadzenia DRR), 7.5 (prądy, progi EN/UVLO i OV), 9.3.2–9.4 (ograniczenie prądu włączania, wyłączenie, dioda podłożowa).
- ADI LTC2955 rew. A: s. 3 (wyprowadzenia TS8), opis pinów (EN̄ podciągany do VIN przez 900 kΩ, VIN >20 V przez 1 kΩ, TMR 5,2 s/µF).
- ADI LTC3115-1 rew. C: opis pinów FE20, prąd histerezy RUN 500 nA i filtr RUN 1000 pF.
- Wio SX1262 for XIAO: dwie listwy 1x7 2,54 mm (schemat KiCad strony trzeciej, [comet.bg](https://store.comet.bg/download-file.php?id=30873)); wyprowadzenia według [zlecenia L0](../l0-diagnostic/ZLECENIE.md#połączenia-wio).

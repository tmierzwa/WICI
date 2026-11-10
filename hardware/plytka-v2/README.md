# WICI: płytka v2, schemat wstępny

**Status 2026-11-10: schemat, rozmieszczenie i komplet ścieżek z czystym DRC, przed niezależnym przeglądem ([Ścieżki](#ścieżki-2026-11-10)). Nie zamawiać.** Schemat zbiera w jednym projekcie KiCad płytkę v1.1 prototypu i tor zasilania stacji pilotażowej ([elektronika](../../docs/spec/elektronika.md#stacja-pilotażowa)). Wartości elementów pochodzą z [projektu zasilania](../r02/zasilanie.md) i z [płytki testowej przetwornicy](../przetwornica-3v3/README.md). Obrys i rozmieszczenie są wstępne. Obrys, otwory i złącza na dolnej krawędzi są dopasowane do modelu STEP obudowy Hammond 1599KBAT ([Dopasowanie do obudowy](#dopasowanie-do-obudowy-2026-11-09)). Ścieżki czekają na przymiarkę, wyniki pomiarów i krok 4 (sekcja [Przed ścieżkami i zamówieniem](#przed-zamówieniem)).

| Plik | Zawartość |
|---|---|
| [schemat.pdf](schemat.pdf) | schemat (arkusz A0, połączenia przez etykiety sieci, jak w v1) |
| [polaczenia.md](polaczenia.md) | sygnały MCU i wszystkie sieci |
| [bom.csv](bom.csv) | lista części z producentami, numerami i numerami LCSC, tam gdzie są już wybrane |
| `cad/plytka-v2.kicad_sch`, `cad/plytka-v2.kicad_pcb`, `cad/plytka-v2.kicad_dru` | projekt KiCad 10.0.6: schemat, płytka 4-warstwowa ze ścieżkami i reguły projektu |
| `checks/erc.json`, `checks/netlist.xml`, `checks/drc.json` | ERC (0 naruszeń), lista połączeń i DRC (0 naruszeń poza sitodrukiem, 0 niepołączonych; [Ścieżki](#ścieżki-2026-11-10)) |
| `checks/routing*.dsn`, `checks/routing*.ses`, `checks/routing*.ses.sha256`, `checks/routing*.log`, `checks/routing-anchors.json` | dla każdego etapu routera: zadanie dla Freeroutingu, zachowana sesja ścieżek, suma zadania, z którego powstała, i dziennik przebiegu; lista punktów, w których router może dołączyć do miedzi ręcznej |
| [render-sciezki-gora.png](render-sciezki-gora.png), [render-sciezki-spod.png](render-sciezki-spod.png) | render płytki ze ścieżkami od góry i od spodu |
| `tools/design.py` | jedyne źródło: części, piny, sieci i sprawdzenia przydziału pinów |
| `tools/make_pcb.py` | obrys, otwory i rozmieszczenie: założenia, położenia stałe i obszary bloków |
| `tools/route_pcb.py`, `tools/route.sh` | klasy sieci, reguły, warstwy, miedź ręczna i płaszczyzny, zadania dla routera; uruchomienie Freeroutingu etapami |

Odtworzenie: `hardware/plytka-v2/tools/build.sh` (KiCad 10.0.6). Skrypt sprawdza przydział pinów, generuje schemat, BOM i listę połączeń, uruchamia ERC, rysuje PDF, rozmieszcza elementy na płytce, dokłada miedź ręczną, wczytuje zachowaną sesję ścieżek (gdy pasuje do zadania) i uruchamia DRC. Plików w `cad/` nie edytuje się ręcznie.

## Co zmienia się względem v1.1

| Blok | v1.1 (prototyp L0) | v2 |
|---|---|---|
| MCU | DevKitC w J5/J6, zasilana z USB | ta sama DevKitC v1.1 (N8R8) w J5/J6, zasilana przez piny 3V3 z przetwornicy; pin 5V wolny |
| Radio | Wio na przewodach obok płytki | Wio w gniazdach J8/J9 (2 × 1x7, 2,54 mm), zasilanie przez zworkę pomiarową JP3, przy module C1, C2 i RXEN 10 kΩ (R64); SCK za R18, jak ekran i FRAM |
| Gniazda TI, ST, Nordic | J1–J4, J9, J10, JP3, R17, otwory Arduino | wypadają |
| USB do laptopa | złącze micro USB DevKitC | gniazdo USB-C J4 bez zasilania z VBUS (VBUS tylko na bramkę Q12 wykrywania laptopa), CC1 i CC2 przez 5,1 kΩ, ochrona ESD U8 |
| Ekran, FRAM, dioda | bez zmian | bez zmian (te same oznaczenia) |
| Przyciski i CISZA | B3F na płytce (SW1–SW4), przełącznik na płytce (SW5) | panelowe PV6F240SS i 100SP1T8B13M1QEH z osłoną GT-4R na wiązkach do J10 i J11, ochrona ESD U9 i filtry RC ([front w wariancie 2](#front-w-wariancie-2-2026-11-09)) |
| Brzęczyk | z pinu 5V DevKitC przez JP2 | z szyny 5 V ekranu (U2), bo pin 5V DevKitC jest martwy przy zasilaniu przez 3V3 |
| Pomiar | VTEST (J12) i złącze analizatora J11 | J11, J12 i dzielnik VTEST wypadają; pomiar ogniw i 12 V na GPIO4 i GPIO5 |
| Zasilanie | brak | ogniwa 4 × AA i 12 V na wspólną szynę VSYS, sterownik przycisku, przetwornica 3,3 V |

## Tor zasilania

```text
J1 4×AA ─ R40 1 Ω ─ D7 Schottky ─────────────────────────────┬─ VSYS ─ C50 ─ U7 LTC3115-1 (RUN ← Q9) ─ +3V3
J2 12 V ─ F1 T1A ─ D4 TVS 33 V ─ Q2 ─(wspólny dren)─ Q3 ───────┘
                                  └ U5 LM74800-Q1: DGATE, HGATE, OVP 16,8 V, EN/UVLO ← dzielnik przez Q4
suma diodowa D8 (ogniwa) i D9 (wspólny dren przez R46, C35, D10 33 V) ─ VCTL ─ U6 LTC2955-2 ─ Q8 ─ szyna ON
V12 ─ D13 BAS116H ─ R70/R71 ─ ON U6 (zbocze narastające przez około 9 V włącza)
VCTL ─ R48/D16 ─ KILL U6 ← Q11 ← GPIO47
ON ─ Q5 ─ Q4: dzielnik 12 V (EN/UVLO U5 i ADC)    ON ─ Q10 ─ Q9: RUN przetwornicy z VSYS
```

- **Włączenie z samego 12 V (bez ogniw):** wspólny dren Q2/Q3 dostaje napięcie przez diodę podłożową Q2 także przy wyłączonym U5 (karta LM7480-Q1, 9.4). Z niego przez R46 i D9 zasilany jest sterownik U6. Naciśnięcie przycisku (J3) daje szynę ON. ON podłącza przez Q4 dzielnik 12 V do EN/UVLO U5, a przy V12 ≥11,9 V (najwyżej 12,3 V) U5 włącza Q3 i zasila VSYS. Równolegle ON przez Q10 i Q9 podaje VSYS na RUN przetwornicy.
- **Samoczynne włączenie z 12 V:** stacja ma być włączona zawsze, kiedy to możliwe (decyzja 4). Dzielnik R70/R71 (280 kΩ / 30,1 kΩ, 0,1%) podaje 12 V przez diodę D13 (BAS116H) na wejście ON sterownika. Zbocze narastające przy około 8,2–9,6 V włącza stację jak przycisk. To szacunek: próg ON 0,76–0,84 V (karta) × 10,28–10,32 (R70/R71 0,1%) daje 7,81–8,67 V, a do tego dochodzi spadek D13 przy około 27 µA, którego karta BAS116H nie podaje. Przyjęto 0,4–0,9 V: górna granica to ≤0,9 V przy 1 mA z karty, mniej przy 27 µA i więcej na zimno do −20 °C; dolna z wykresu na gorąco z zapasem. Próba odbiorcza wymaga zbocza nie poniżej 8,0 V i najpóźniej przy 9,8 V. Przy odwróconym 12 V D13 blokuje, więc ON zostaje na około 0 V (upływ ≤80 nA), a nie na granicy −0,3 V z karty LTC2955. Próg leży poniżej napięcia każdego działającego źródła, więc każde podłączenie i każdy powrót 12 V po zaniku włącza stację, także akumulator 12,6 V w spoczynku i napięcie narastające powoli z panelu. Próg może leżeć poniżej progu włączenia UV: sterownik zostaje włączony i czeka, a U5 załącza 12 V, gdy napięcie dojdzie do około 11,9 V. W obudowie TSOT-23 opadające zbocze ON nic nie robi, a stałe 12 V nie włącza stacji z powrotem po wyłączeniu przyciskiem. Wyłączenie ręczne trwa więc do następnego podłączenia albo powrotu 12 V; rozruch silnika, przy którym napięcie spada poniżej około 9 V, też włączy stację. Dzielnik pobiera z podłączonego 12 V około 37 µA także przy wyłączonej stacji.
- **Podtrzymanie bez 3,3 V:** KILL jest podciągnięty z VCTL, czyli z zasilania U6 (R48 470 kΩ, Zener D16 5,1 V wobec 6 V dopuszczalnych), a nie z +3V3 ani z szyny ON. Gdy 12 V spadnie poniżej progu UV bez ogniw, znika 3,3 V, ale sterownik zostaje włączony i stacja wraca sama, gdy tylko 12 V da się znów użyć. Po całkowitym zaniku 12 V bez ogniw KILL idzie za VCTL do około 0,8 V, więc U6 traci stan przez podnapięcie zasilania (0,8–1,3 V), a nie przez KILL. Po powrocie 12 V startuje z wysokim ON i włącza stację po około 1 s (karta LTC2955, „ON Pin Initial Turn-On”). Z KILL na szynie ON zanik trwający 0,2–1,6 s kończyłby się w blokadzie 0,6–1,4 s po zwolnieniu EN i stacja zostałaby wyłączona. Przy VCTL około 3,6 V (słabe ogniwa) KILL zostaje powyżej 2 V przy upływie Zenera 2 µA i Q11 0,5 µA w 25 °C. Czekający sterownik pobiera z rozładowanego akumulatora do około 0,55 mA (U5, dzielnik UV i R78, który przy szynie ON około 11 V bierze około 0,1 mA).
- **Włączenie z ogniw:** U6 zasilany przez D8, dalej tak samo. U5 zostaje wyłączony, bo dzielnik 12 V leży przed Q2, więc bez 12 V daje 0 V.
- **Wyłączenie:** program ściąga KILL przez Q11 (GPIO47; pin MCU nie widzi napięcia KILL, a R72 trzyma Q11 wyłączony przy resecie, w uśpieniu i bez zasilania MCU), a bez MCU wyłącza przytrzymanie przycisku przez 5–19 s (C37 2,2 µF, nominalnie około 11,5 s). Szyna ON znika, Q4 odłącza dzielnik (U5 w wyłączeniu 2,87 µA), a Q9 zdejmuje RUN.
- **Stan wyłączony z ogniw:** LTC2955 1,2/3 µA, LTC3115-1 3/10 µA, LM74800 przez diodę podłożową Q3 2,9/5 µA i upływy kluczy. To ten sam bilans co w [projekcie zasilania](../r02/zasilanie.md#bilans-prądu-w-stanie-wyłączonym), około 7/19 µA, plus upływ C50 i podciągnięcie KILL z VCTL (R48, około 3–6 µA przy świeżych ogniwach, zależnie od kolana D16). Z 12 V przy wyłączonej stacji dochodzą dzielnik ON (około 37 µA) i R48 (około 15 µA).
- **RUN ≤ VIN + 0,3 V:** RUN dostaje napięcie z VSYS przez Q9, a nie z szyny ON. ON idzie za stroną 12 V także przy otwartym łączniku (np. przy 24 V), a VSYS jest wtedy z ogniw. R55 220 kΩ ściąga RUN, a prąd histerezy RUN (0,5 µA, wypływa z pinu w pracy) daje na nim tylko 0,11 V, więc przetwornica naprawdę się wyłącza. Na płytce testowej 10 MΩ tego nie zapewniało.
- **Klucze przy końcu ogniw:** przy ogniwach około 4 V szyna ON ma około 3,3 V. Bramki Q5 i Q10 dostają więc 91% ON przez dzielnik 100 kΩ / 1 MΩ, a Q8 91% VCTL, czyli około 3 V wobec progu BSS138 (Q10) do 1,5 V i 2N7002 (Q5) do 2,5 V. Zenery 15 V (D12, D14, D15) ograniczają VGS przy stronie 12 V do 35 V.
- **Wykrywanie laptopa (czuwanie):** uśpiony MCU nie obsługuje USB, więc VBUS laptopa przez R73/R74 (100 kΩ / 1 MΩ, Zener D17 15 V) włącza Q12, który ściąga USB_LAPTOP (GPIO3, R75 100 kΩ do +3V3). Stan niski budzi stację z [czuwania](../../docs/spec/oprogramowanie.md#czuwanie) i nie pozwala jej zasnąć. VBUS zasila tylko bramkę (około 5 µA), więc laptop nie zasila stacji, także wyłączonej, i nie podnosi 3,3 V przez diody ochronne MCU.
- **Pomiar:** ogniwa przed R40 przez klucz Q6 (DIV_EN, GPIO46), 7,3 V daje 1,49 V. 12 V z dzielnika UV (0,0625 × V12, 36 V daje 2,25 V), tylko przy włączonej stacji. Oba węzły dzielników mają BAV199 (≤80 nA do 150 °C, więc upływ zmienia pomiar 12 V najwyżej o około 0,02 V), a do GPIO prowadzą przez 10 kΩ (R76, R77) i filtr 100 nF przy wejściu ADC (C33, C34; R76, R77, C33 i C34 leżą ≤10 mm od pinów J5.5 i J5.4, sprawdzenie `CLOSE`). Rezystory ograniczają prąd do pinu przy odwróconym 12 V albo ogniwach do ≤40 µA. Pomiar ogniw program robi co najmniej 20 ms po włączeniu DIV_EN (filtr (7,96 + 10) kΩ × 100 nF = 1,8 ms, 12 bitów to 8,3 τ = 15 ms).

## Przydział pinów

Przypisania v1.1 zostają. Nowe sygnały są w tabeli „Sygnały MCU” w [polaczenia.md](polaczenia.md): V_AA_ADC (GPIO4, dawniej RF_GPIO2, którego Wio nie używa), V_12_ADC (GPIO5, dawniej VTEST), DIV_EN (GPIO46), PWM_SYNC (GPIO45), PWR_INT (GPIO48), KILL_MCU (GPIO47, wyłączenie przez Q11), USB_LAPTOP (GPIO3, wykrywanie laptopa) i USB D+/D− (GPIO20/19).

Wszystkie inne piny DevKitC są zajęte, dlatego użyto pinów konfiguracji startu GPIO45 i GPIO46. Każdy ma rezystor do masy (R63, R43), który daje ich domyślny niski stan przy resecie: GPIO45 wybiera 3,3 V dla pamięci flash, a GPIO46 nie może być wysoki razem z niskim GPIO0. GPIO47 i GPIO48 mają poziom 3,3 V w module WROOM-1 (N8R8); w modułach WROOM-2 z 1,8 V by go nie miały, więc płytka wymaga DevKitC-1-N8R8 v1.1 (dioda RGB na GPIO38). `design.py` sprawdza te zasady przy każdym generowaniu. GPIO3 (USB_LAPTOP) jest pinem konfiguracji startu tylko po zapisaniu bezpiecznika STRAP_JTAG_SEL, którego stacja nie zapisuje. Wolnych pinów nie ma.

## Rozmieszczenie wstępne

Płytka ma obrys i rozmieszczenie wszystkich 164 elementów (ścieżki opisuje [Ścieżki](#ścieżki-2026-11-10)). Zamówienie dopiero po przeglądzie ścieżek i przymiarce obudowy. `make_pcb.py` ustawia elementy panelu i złącza na sztywno, a małe elementy każdego bloku układa automatycznie w jego obszarze, każdy najbliżej poprzedniego. Zatrzymuje się, gdy coś nachodzi na inny element, na strefę albo na krawędź, i gdy element ochronny lub odsprzęgający leży za daleko od swojego układu (sprawdzenia `CLOSE`, odległość pad–pad):
- ESD U8 ≤10 mm od USB-C J4, ESD U9 ≤10 mm od J10, TVS D4 ≤10 mm od J2 (zasada z [obudowy R02](../r02/obudowa.md#płyta-bazowa-obrys-i-ograniczenia));
- przetwornica U7 jest stałą grupą według rysunku 17 karty LTC3115-1, przeniesioną z płytki testowej (`CONVERTER` w `make_pcb.py`); kondensatory C44–C47 ≤5–6 mm od U7, C40–C43 ≤7,5–11,5 mm;
- C31 ≤4 mm i C30 ≤5 mm od U5;
- C1 i C2 ≤8 mm od gniazda Wio, C36 ≤5 mm od U6, C11 ≤5 mm od U4.

Każdy element jest powiązany ze swoim symbolem w schemacie (ścieżka z tego samego UUID co w `make_schematic.py`), więc KiCad widzi płytkę i schemat jako jeden projekt. Wynik jest powtarzalny: dwa przebiegi dają ten sam plik. Bez sieci są celowo: pad termiczny U5 (karta LM74800, tabela 6-1) i piny 4 i 5 U3, których schemat nie używa.

Nazwy stron obudowy są jak u Hammonda: **skrzynka** („Box”) ma front ze wgłębieniem na folię panelu, a **pokrywa** („Lid”) to tył z klapką ogniw, przykręcany do skrzynki od tyłu. Współrzędne obudowy liczy się od zewnętrznego lewego górnego narożnika frontu, patrząc od frontu. Założenia (liczby z modelu STEP Hammonda, do potwierdzenia na przymiarce):

- **Obrys:** 200 × 120 mm z narożnikami R4 i wycięciami 12 × 12 mm na słupki śrub pokrywy. Płytka zajmuje obszar frontu Hammond 1599KBAT x 10–210 mm i y 10–130 mm ([obudowa R02](../r02/obudowa.md#płyta-bazowa-obrys-i-ograniczenia)), więc współrzędne płytki to współrzędne frontu minus 10 mm. W płaszczyźnie płytki ściany są 6,3 mm dalej. Pod USB-C płytka ma język 12 × 4,5 mm w stronę ściany, pod gniazdem EN3 wycięcie 17 × 12 mm (x 91,5–108,5, y 108–120), a pod każdym z sześciu elementów panelu (cztery przyciski, wyłącznik, CISZA) otwór Ø20 mm.
- **Panel od strony frontu:** środek okna ekranu, rząd WSTECZ–GÓRA–DÓŁ–OK w rozstawie 32 mm, wyłącznik w linii rzędu, CISZA, dioda alarmu z kratką brzęczyka i przycisk przygotowania leżą na pozycjach z [założeń obudowy](../obudowa/zalozenia.py) (`PANEL`, front w wariancie 2). Przyciski, wyłącznik i przełącznik CISZY są w panelu i przechodzą przez otwory Ø20 mm w płytce; ich przewody idą pod płytką do J10, J3 i J11 ([front w wariancie 2](#front-w-wariancie-2-2026-11-09)). Złącze FPC J7 leży 13,8 mm pod krawędzią panelu, jak na v1.1.
- **Strefy panelu od góry:** okno ekranu 64 × 45 mm; 1 mm wolnego pola wokół każdego otworu Ø20 mm z obu stron (`make_pcb.py` sprawdza je jako koło); bez padów w promieniu 10 mm od otworu przycisku przygotowania (tylko SW6 i otwór H5 w jej skraju, bez miedzi).
- **Złącza na dolnej krawędzi:** USB-C J4 na języku płytki, czołem 0,5–0,65 mm za wewnętrzną powierzchnią ściany (wymaganie 0–1 mm), oś około 1,6 mm nad płytką od strony frontu; otwór w ścianie pod frontem x 60. Ściana ma tam 3,8 mm, więc wtyk musi wejść w nią razem z osłoną: otwór 13,2 × 7,2 mm z zaokrąglonymi narożnikami (R3) przepuszcza osłonę do 12,5 × 6,6 mm. To wymiar, który Amphenol dopuszcza dla gniazd panelowych USB-C; w samej specyfikacji USB Type-C go nie sprawdzono. Język kończy się 1,1 mm przed czołem gniazda, żeby osłona w pełni włożonego wtyku nie oparła się o płytkę. EN3 (x 110) i SMA (x 170) są w ścianie. EN3 łączy się przewodem z J2 obok wycięcia, a SMA krótkim przewodem koncentrycznym z u.FL Wio pod płytką. Wymiary EN3 z biuletynu Switchcraft 602: za ścianą kołnierz Ø20,6 × 3 mm, korpus Ø14 × 4,5 mm i kubki lutownicze 5,6 mm, razem 13,1 mm. Oś EN3 leży 0,8 mm pod spodem płytki (od strony pokrywy), więc korpus i kubki przechodzą przez płaszczyznę płytki w wycięciu; wycięcie mieści jeszcze 5 mm przewodu z lutem i koszulką. Oś SMA leży 6,3 mm pod spodem płytki, a nakrętka (9,2 mm po narożach) zostawia do płytki 1,7 mm; pod tyłem SMA od spodu jest wolna strefa.
- **Moduły od spodu (decyzja 6):** DevKitC i Wio siedzą w gniazdach od spodu płytki. Patrząc z góry, rzędy gniazd zamieniają się stronami (J6 po lewej, J5 po prawej), żeby moduł widziany od spodu stał jak na v1.1. Rozstaw rzędów Wio 15,24 mm i obrys modułu 17,78 × 21,44 mm (pin 1 2,92 mm od krótkiej krawędzi) z modelu STEP Seeed. Zworka pomiarowa JP3 leży od góry tuż obok gniazd Wio.
- **Tylko THT od spodu:** wszystkie elementy SMD są od góry, więc montaż SMT jest jednostronny (jeden szablon, jeden przebieg pieca). Od spodu są tylko gniazda modułów, złącza przewodów J1, J2, J3, J10 i J11, F1 i C50, lutowane ręcznie albo selektywnie. Pady SMD leżą co najmniej 2,5 mm od padów elementów przewlekanych (wymóg JLC dla lutowania THT po SMT); `make_pcb.py` pilnuje tego przy układaniu i sprawdza na końcu.
- **Strefa koszyka ogniw:** BH4AAW leży na klapce pokrywy, pod płytką. Klapka leży (w rzucie na front) w x 0,7–67,4 i y 40,5–99,5, więc strefa od spodu płytki to x 0,5–58, y 30–90 (cała klapka, bo miejsce przyklejenia koszyka ustala się przy montażu). Korpus koszyka (14,57 mm, rysunek Hammond BH4AAW) leży 6,3 mm pod spodem płytki, ale ogniwa AA (do Ø14,5 mm na dnie 1,5 mm) sięgają 16,0–16,4 mm nad klapkę, czyli 4,5 mm pod spód płytki. Do tego dochodzi podkładka klejąca Hammonda (grubość nieznana, przyjęto do 1,6 mm) i przechył: w osi v koszyk mieści się w otworze klapki (szczeliny przy v 41,5–41,9 i 98,1–98,6, powierzchnia z obu stron na tej samej wysokości), a w osi u płaska część ma około 59,6 mm przy 61,25 mm koszyka, więc koszyk opiera się o zaokrąglenie lewej ściany albo o podwyższenie zaczepu klapki po prawej (u ≥64,5, v 62–78, do 1,5 mm). Położony na środku podnosi się o około 0,6 mm; wtedy ogniwa są co najmniej 2,3 mm pod spodem płytki. Od spodu w tej strefie nie ma elementów, a przy przyciskach WSTECZ i GÓRA obowiązują zasady z [frontu w wariancie 2](#front-w-wariancie-2-2026-11-09). Pokrywę zakłada się klapką po lewej (patrząc od frontu), [Montaż w obudowie](#montaż-w-obudowie).
- **Wysokości:** słupki skrzynki mają 4,5 mm, a płytka leży na tulejkach 6 mm, więc jej wierzch jest 10,5 mm od wewnętrznej powierzchni frontu i 13,5 mm od dna wgłębienia na folię. Najwyższe elementy górne poza panelem zostawiają do frontu: dioda D1 0,95 mm (osadzona kołnierzem na płytce, z najgorszym przypadkiem z karty), zworka JP3 z założonym zwieraczem i brzęczyk BZ1 po około 1,96 mm. Tolerancje (słupek ±0,2 mm, tulejka ±0,1 mm, wysokość elementu ±0,3 mm, osadzenie THT do 0,2 mm, razem najwyżej 0,8 mm) zostawiają BZ1 i JP3 co najmniej 1,1 mm, a D1 0,45 mm. Od spodu do wewnętrznej powierzchni pokrywy jest 20,9 mm, a do wierzchu słupków pokrywy 16,4 mm; DevKitC w gniazdach sięga około 15,9 mm (5,0 mm do pokrywy), złącza J1–J3, J10 i J11 z wtyczką i zgiętymi przewodami około 15,8 mm (5,1 mm); końcówki PV6 do 2,7 mm, a przełącznik CISZY 2,0 mm. Wysoki kondensator C50 i zaciski bezpiecznika F1 są od spodu, poza strefą koszyka.
- **Otwory montażowe:** sześć otworów Ø3,5 mm na słupkach skrzynki: H1 (130, 20), H2 (190, 20), H3 (10, 100), H4 (70, 100), H5 (130, 100) i H6 (190, 100). Skrzynka ma osiem słupków w siatce x 20/80/140/200 i y 30/110 na froncie; dwa pod oknem ekranu, (20, 30) i (80, 30), szlifuje się przy obróbce skrzynki na równo z frontem. H5 jest 12,5 mm od przycisku przygotowania (wymaganie ≤25 mm). Między otworem montażowym a otworem panelu zostaje ≥2 mm płytki (`make_pcb.py`; najmniej H3 przy WSTECZ, 3,9 mm), a tulejka stoi 2,6 mm od brzegu otworu. Każdy otwór ma po obu stronach wolny kwadrat 8 × 8 mm na tulejkę (od góry) i łeb wkrętu (od spodu); wkręt wkręca się od spodu, a pod otworem nie ma wysokich elementów, więc wkrętak sięga prosto. Mocowanie: tulejka dystansowa Harwin R30-6700694 (nylon, 6,0 mm, otwór 3,2 mm, średnica 5,0 mm; DigiKey 952-1529-ND), wkręt do tworzyw Bossard BN 82428 3 × 12 (ecosyn-plast, łeb walcowy Ø5,6 × 2,4 mm, PZ1; TME B3X12/BN82428) i pod łbem podkładka poliamidowa Essentra 1340107 (1,0 mm, Ø6 mm, otwór 3,1 mm; TME 1340107). Tulejka stoi na słupku Ø4,75 mm i mieści się w wolnym kwadracie od góry, a podkładka z łbem w kwadracie od spodu. Otwór w słupku ma Ø2,36 mm i 4,6 mm głębokości, a pod nim front ma tylko 2,9 mm. Wkręt wchodzi w słupek na 12 − 1,6 − 6 − 1 = 3,4 mm i kończy się 1,2 mm nad dnem otworu. Z tolerancjami (płytka ±0,16 mm, tulejka ±0,1 mm, podkładka ±0,1 mm i przyjęte ±0,55 mm długości wkrętu, bo karta jej nie podaje) wchodzi 2,5–4,3 mm, więc nie dochodzi do dna. Otwór Ø2,36 mm to 0,79 średnicy wkrętu, a dla ABS wytyczne EJOT PT podają około 0,8 d. W najgorszym przypadku wkręt trzyma około jednym pełnym zwojem, a ścianka słupka ma tylko 1,6 średnicy wkrętu. Dlatego na pierwszej sztuce trzeba zmierzyć moment, przy którym gwint w słupku się zrywa, i dokręcać wyraźnie poniżej niego. Płytkę dociska tylko kilka elementów, a wkręt nie przenosi stałej siły. Podkładka jest poliamidowa jak tulejka. Nacisk pod łbem rozkłada się na około 17 mm² podkładki, a na tulejce tylko na 11,6 mm², więc bardziej pełznie tulejka, a nie podkładka. Najdłuższy dopuszczalny wkręt to 12,0 mm pod łbem bez podkładki i 13,0 mm z podkładką 1 mm (płytka 1,6 + tulejka 6 + otwór 4,6, bez 0,2 mm zapasu); dłuższy wypchnie albo przebije front pod folią. Otwór Ø3,5 mm przy wkręcie 3 mm daje ±0,25 mm luzu na tolerancję położenia sześciu słupków; tulejkę centruje wkręt, a łeb z podkładką i tulejka nie przechodzą przez otwór.

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

6. **DevKitC i Wio od spodu płytki.** Panel Sharp leży kilka milimetrów za frontem, a DevKitC w gniazdach sięga około 16 mm nad płytkę (gniazdo 8,5 mm, listwa 2,5 mm, płytka modułu i WROOM). Moduły od spodu wiszą w głębi skrzynki (33 mm wnętrza), a front zostaje płaski.

   Odrzucony wariant: moduły od góry, jak na v1.1. Prostszy dostęp do modułów, ale front potrzebuje garbu nad DevKitC albo wgłębionego okna ekranu ([obudowa](../obudowa/README.md#co-jest-znane-a-co-trzeba-zmierzyć)). Kosztem wybranego wariantu jest dostęp do DevKitC i jego micro USB dopiero po wyjęciu płytki; program wgrywa się i tak przez USB-C stacji.

Do tego dochodzą zmiany w zakresie, które specyfikacja zostawia projektowi v2: J11 (analizator), J12 i dzielnik VTEST oraz zworki JP1/JP2 wypadają według zasady „nic na zapas”. JP3 zostaje, bo specyfikacja wymaga punktu pomiaru prądu radia.

## Dopasowanie do obudowy (2026-11-09)

Płytkę z rozmieszczeniem wstępnym porównano z modelem STEP i rysunkiem Hammond 1599KBAT oraz rysunkiem koszyka BH4AAW. Otwory nie trafiały w słupki, słupki okazały się niższe (4,5 mm zamiast około 12 mm), złącza kończyły się 6,3 mm przed ścianą, a strefa koszyka leżała w innym miejscu. Po niezależnym przeglądzie doszły wysokości złączy z wtyczkami, dioda alarmu, wyłącznik PV6, wkręty i odstępy SMD–THT. Poprawki:
- otwory Ø3,5 mm na sześciu słupkach skrzynki z tulejkami 6 mm i wkrętem do tworzyw 3 × 12 mm z podkładką 1 mm (wyżej, „Otwory montażowe”). Bez tulejek płytka leżałaby 4,5 mm od frontu, a brzęczyk, złącza, U1 i przyciski wchodziłyby we front;
- złącza przewodów J1 (koszyk), J2 (EN3) i J3 (wyłącznik) od spodu: JST XH z wtyczką ma 9,8 mm wysokości (karta JST XH), a od spodu jest ponad 20 mm, i od spodu przychodzą wszystkie trzy wiązki;
- otwór Ø20 mm pod wyłącznikiem PV6;
- dioda D1 osadzona kołnierzem na płytce, pod otworem Ø5,5 mm we froncie;
- elementy na miejscach słupków (U1 i R20, D11 i R44, D5, D15 i Q4) i J3 przy H6 przesunięto, a pady SMD odsunięto od padów THT na ≥2,5 mm (wcześniej siedem par bliżej, np. R64 przy J8, C33 przy J5, D4 i U5 przy F1). Bloki układa skrypt jak dotąd, a wszystkie sprawdzenia odległości (`CLOSE`) i strefy panelu zostały;
- strefa koszyka według klapki z modelu;
- język pod USB-C, otwór w ścianie na osłonę wtyku i wycięcie pod EN3; J2 przeniesiono z x 100 na prawo od wycięcia (x 116), a TVS D4 leży przy nim (od 2026-11-10 J2, F1 i D4 są po lewej stronie wycięcia, [Ścieżki](#ścieżki-2026-11-10)).

Sprawdzenie: płytkę z `kicad-cli pcb export step` złożono z modelem obudowy razem z bryłami zastępczymi koszyka, EN3, SMA, PV6 (nakrętka, gwint, wyprowadzenia i przewody), osłony wtyku USB-C, tulejek, łbów wkrętów, wkrętaka, wtyczek z przewodami na J1–J3 i diody D1 według karty. Kolizji nie ma. Sam obrys płytki sprawdzono osobną bryłą (z otworami), a próba kontrolna z wydłużonym językiem wykrywa kolizję ze ścianą. Elementy bez modelu 3D sprawdzono bryłami o przyjętej wysokości: przyciski B3F 7,3 mm, USB-C 3,26 mm, F1 10 mm, moduły w gniazdach. SW5 nie ma bryły, więc jego wysokości nie sprawdzono.

Odrzucone warianty:
- tulejki 4,5 mm (pierwsza wersja): do frontu 9,0 mm, a dioda D1 sięga według karty do 9,55 mm, brzęczyk i JP3 ze zworką zostawiały 0,46 mm bez tolerancji. Tulejka 4,5 mm nie jest też typową długością. Kosztem 6 mm jest 1,5 mm mniej pod spodem (koszyk 6,3 mm zamiast 7,8 mm, DevKitC 5,0 mm do pokrywy), dłuższa droga taśmy ekranu i nasadek przycisków (do przymiarki);
- tulejki 5 mm: BZ1 miałby około 0,2 mm zapasu w najgorszym przypadku, a wkręt #4 × 3/8" wchodziłby w słupek tylko na 2,9 mm;
- wkręt #4 × 7/16" (11,1 mm) typu B, wybrany najpierw: nie ma go w DigiKey, Mouser ani TME (2026-11-10);
- wkręt 3 × 12 bez podkładki: wchodzi w słupek na 4,4 mm, czyli 0,2 mm od dna, a z tolerancjami do 5,3 mm. Wtedy opiera się o dno, zanim łeb dociśnie płytkę, albo pcha front pod folią. Ten sam wkręt z podkładką 1 mm daje 2,5–4,3 mm;
- wkręt 3 × 10 bez podkładki: wchodzi tylko na 1,6–3,2 mm;
- ST2,9 × 9,5 mm (ISO 7049, ostry koniec forma C): wchodzi w słupek na 1,9 mm, a sam niepełny gwint końcówki ma 2,6 mm (forma F 2,1 mm). ST2,9 × 13 mm (np. Bossard BN 33) i Keystone 689 (#4 × 1/2", 12,7 mm, ostry koniec AB) są za długie, z podkładką 1 mm też (do 5,2 i 4,9 mm w otworze 4,6 mm);
- EJOT PT K30 × 12 (Bossard BN 13578, TME B3X12/BN13578, łeb Ø6 × 2,1 mm): pasuje tak samo z podkładką, ale 2026-11-10 TME nie ma go na stanie. Zostaje zamiennikiem w BOM;
- stalowa podkładka 1 mm zamiast poliamidowej: jedyna w TME (Bossard DIN 7349, M3) ma Ø9 mm. Wystaje poza wolny kwadrat 8 × 8 mm pod otworem i zbliża się do F1 przy H5 na 0,25 mm. Pełzanie i tak zależy od nylonowej tulejki, która przenosi większy nacisk;
- zmiana długości tulejki zamiast podkładki: tulejka ustala wysokość płytki pod frontem (wyżej, „Wysokości”), więc krótsza zabiera zapas diodzie D1 i brzęczykowi, a dłuższa przesuwa całą płytkę;
- otwory Ø3,2 mm: przy sześciu słupkach z formy ±0,15 mm luzu nie wystarcza na tolerancję ich położenia;
- JP3 jako zworka lutowana albo kątowa: przy tulejkach 6 mm JP3 ze zwieraczem ma 1,96 mm do frontu, więc zostaje zwykła zworka, którą zdejmuje się bez lutownicy;
- złącza J1–J3 boczne (kątowe) od góry: niższe, ale przewody szłyby w 10,5 mm między płytką a frontem, a wszystkie trzy wiązki przychodzą od spodu;
- D1 w tulejce dystansowej, z kopułką w otworze frontu: wystawałaby nad folię albo wymagałaby dokładnej tulejki; przy 0,95 mm pod frontem i kącie świecenia 2 × 30° światło przechodzi przez otwór;
- płytka powiększona do około 211 × 131 mm, żeby wszystkie krawędzie sięgały ścian: zmienia układ współrzędnych całej płytki i panelu, a przy pochyleniu ścian zostawia około 0,8 mm luzu wszędzie. Przy ścianie musi być tylko USB-C, więc wystarcza język;
- pocienienie ściany przy USB-C od środka zamiast otworu na osłonę: wymaga frezowania wnętrza skrzynki, a otwór 13,2 × 7,2 mm robi się od zewnątrz;
- EN3 nad płytką (od frontu): między płytką a frontem jest 10,5 mm, a kołnierz ma Ø20,6 mm;
- EN3 cały pod płytką: otwór Ø15,5 mm sięgałby w miejsce, gdzie pokrywa zachodzi na skrzynkę (wpust 3,4–5,4 mm pod tylną krawędzią ściany);
- EN3 na płytce zamiast w ścianie: biuletyn 602 ma wersje kątowe do druku, ale gniazdo w ścianie przenosi siły od przewodu na obudowę, a nie na luty;
- przesunięcie ekranu, żeby ominąć dwa słupki pod oknem: koliduje z rzędem przycisków i J7;
- podparcie lewego górnego narożnika tulejkami ze słupków pokrywy (16,4 mm pod płytką): płytka byłaby ściśnięta między skrzynką a pokrywą z tolerancją obu. W lewym górnym rogu nie ma nic, co się naciska ani wpina, a ekran trzyma się frontu, więc sześć otworów wystarcza;
- blokada odwrotnego założenia pokrywy (np. kołek na pokrywie): pokrywa i słupki śrub są symetryczne, więc kołek musiałby zatrzymać pokrywę na DevKitC albo na płytce, zanim koszyk dotknie Wio, czyli przy około 7 mm szczeliny; to dodatkowa część do przyklejania w każdej stacji. Wystarcza oznaczenie i krok w montażu niżej.

## Front w wariancie 2 (2026-11-09)

Właściciel wybrał wariant 2 wyglądu frontu z przeglądu na modelu Hammonda. Pozycje są w `PANEL` w [założeniach obudowy](../obudowa/zalozenia.py), w rzucie na front:
- dioda ALARM (178,5; 20), a obok niej kratka brzęczyka: siedem otworów Ø1,5 mm w rozstawie 3 mm, środek (191,5; 20). Wspólny napis ALARM leży pod nimi i nad zawiasem osłony CISZY;
- CISZA (185, 62) pod osłoną GT-4R z zawiasem u góry, wyłącznik (185, 98) w linii rzędu nawigacji, naklejka serwisowa (151, 116);
- przyciski nawigacji bez zmian: (30/62/94/126, 98), otwór Ø16 mm. Logo i nazwa stacji są na środku nad rzędem.

Zmiany w płytce:
- **Przyciski nawigacji: E-Switch PV6F240SS w panelu**, jak wyłącznik: płaskie, ze stali nierdzewnej, bez podświetlenia, SPST-NO, IP65, końcówki lutowane, głowica 1,5 mm nad folią. SW1–SW4 (B3F) i nasadki B32-1310 wypadają. Przewody idą do J10 (JST XH, 5 styków, od spodu, między otworami DÓŁ i OK): 1 GÓRA, 2 DÓŁ, 3 OK, 4 WSTECZ, 5 wspólna masa.
- **CISZA: E-Switch 100SP1T8B13M1QEH w panelu**, pod osłoną CW Industries GT-4R, z przewodami do J11 (JST XH, 2 styki). SW5 na płytce (100SP1T1B4M2QE) odpadł, bo ma tuleję bez gwintu (opcja B4), a GT-4R trzyma nakrętka na tulei 15/32". Nowy przełącznik ma uszczelnienie epoksydowe, −40…85 °C i dźwignię T8 (17,56 mm w katalogu, 18,00 mm na rysunku ST111027; GT-4R jest na dźwignie 17,5 mm). Otwór we froncie: Ø11,91 mm z noskiem 1,65 × 0,79 mm pod wpust tulei (rysunek ST111027, montaż bez pierścienia blokującego), więc przełącznik się nie obraca. Tuleja ma 11,38 mm: korpus przylega do wewnętrznej strony frontu (bez nakrętki od środka), a front 3,0 mm, folia 0,2 mm, płytka osłony 0,8 mm, podkładka sprężysta około 0,8 mm i nakrętka około 2,4 mm zajmują 7,2 mm, więc za nakrętką zostaje około 4 mm gwintu. Koniec tulei wystaje wtedy 8,2 mm nad folię, a dźwignia około 26 mm, czyli poniżej 28,45 mm zamkniętej klapki nad folią.
- **Kierunek CISZY:** zamknięta klapka GT-4R (zawias u góry) spycha dźwignię od zawiasu, w dół, i to jest położenie pracy. CISZA to dźwignia do zawiasu, w górę; da się ją ustawić tylko przy otwartej klapce, a otwarta klapka z dźwignią w górze jest widocznym znakiem ciszy. Dźwignia zwiera styk środkowy z końcówką po przeciwnej stronie (ST111027: położenie 1 zwiera 2–3), więc masę z J11.2 lutuje się na końcówkę najdalej od zawiasu, przewód J11.1 na środkową, a końcówka przy zawiasie zostaje wolna.
- **Wejścia z przewodów:** każda linia ma przy swoim złączu ochronę ESD, rezystor szeregowy i kondensator do masy (zasada ≤10 mm od złącza z [obudowy R02](../r02/obudowa.md#płyta-bazowa-obrys-i-ograniczenia), sprawdzana w `CLOSE`):
  - przyciski: U9 TI TPD4E1U06DCKR przy J10 (cztery linie, napięcie pracy 5,5 V, upływ ≤10 nA, IEC 61000-4-2 ±15 kV; LCSC C194628, 23 295 sztuk 2026-11-10; zamiennik TECH PUBLIC TPD4E1U06DCKR, LCSC C2987062, 790 sztuk: według karty te same wyprowadzenia, napięcie pracy 5,5 V, przebicie ≥6,5 V i upływ ≤10 nA przy 2,5 V. Na rysunku karty pin 1 jest opisany „D2−”, ale schemat pokazuje cztery jednakowe linie do masy, więc przypisanie przycisków do pinów nie ma znaczenia), R80–R83 1 kΩ i C60–C63 100 nF. KiCad nie ma symbolu TPD4E1U06, więc w schemacie stoi symbol ESDA6V1-5SC6 o tych samych pinach 1–4 i 6; pin 5 (NC) jest wolny. Z podciągnięciem 10 kΩ przy MCU filtr ma 0,1 ms przy naciśnięciu i 1,1 ms przy puszczeniu, a naciśnięty przycisk daje na pinie 0,3 V;
  - CISZA: D19 TI TPD1E10B09 przy J11 (dwukierunkowa, napięcie pracy ±9 V, upływ ≤100 nA przy 5 V, IEC 61000-4-2 ±20 kV; LCSC C88031, 50 105 sztuk), R16 1 kΩ i C64 100 nF;
  - wyłącznik: D18 TPD1E10B09 przy J3, R84 1 kΩ i C65 10 nF przed wejściem PB sterownika U6. PB (LTC2955 rew. A) ma podciągnięcie 900 kΩ, przy otwartym przycisku 3,0–5,5 V i próg 0,6–1,0 V, zakres −36…36 V i ±25 kV tylko w modelu HBM. Dioda 9 V przy 5,5 V nie przewodzi (≤100 nA, czyli najwyżej 0,09 V spadku na 900 kΩ), a naciśnięcie daje na PB tylko 5 mV więcej przez R84. Karta zaleca parę 1 kΩ i 10 nF przy wejściu VIN przeciw zakłóceniom; tu ta sama para tłumi szybkie zbocze wyładowania.
  Program nie zmienia się: odczyt, polaryzacja i piny są jak dotąd.
- **Otwory Ø20 mm** pod każdym z sześciu elementów panelu, z 1 mm wolnego pola wokół z obu stron. PV6F240SS bez podświetlenia (karta E-Switch, s. 5): gwint 13,0 mm, korpus 14,0 mm, końcówki 2,0 × 0,5 mm w rozstawie 9,4 mm, 17,5 ± 0,5 mm za folią, czyli do 2,7 mm pod spód płytki. Przełącznik CISZY (ST111027): korpus 12,70 × 6,86 mm i 0,51 + 8,89 mm głębokości oraz końcówki 4,70 mm za wewnętrzną powierzchnią frontu, czyli 2,0 mm pod spód płytki. Otwór zostawia 2 mm luzu wokół gwintu PV6 i 2,8 mm wokół przekątnej korpusu przełącznika (14,4 mm) na tolerancję otworów we froncie.
- **Wyłącznik a przyciski nawigacji:** ten sam PV6F240SS; odróżnia go miejsce (kolumna z boku, 59 mm od OK), czarny pierścień i symbol zasilania nadrukowane na folii oraz napisy „WYŁĄCZNIK” i „WYŁĄCZ: TRZYMAJ 2 s”.
- **D1 (168,5; 10) i BZ1 (180,5; 9)** w rzucie na płytkę. Otwór dźwiękowy brzęczyka leży 1,4 mm od środka kratki, bo bliżej BZ1 wchodzi w wycięcie na słupek śruby pokrywy i w strefę tulejki H2. SW6 (141, 106) pod otworem naklejki, J3 (194, 88) przy wyłączniku, J11 (192, 52) przy CISZY. Blok przy SW6 (Q4–D6) dostał większy obszar, bo strefa otworu przygotowania przesunęła się w górę.

**Koszyk ogniw pod WSTECZ i GÓRA.** Te dwa przyciski stoją nad dolnym końcem koszyka (koszyk v 41,5–98,5 w otworze klapki, końcówki przycisków v 97,75–98,25). Ogniwa kończą się najdalej przy v 96,55 (ścianka końca 1,95 mm), więc pod końcówkami jest tylko ścianka końca koszyka (14,57 mm). Odstępy z modelu (końcówki 18,0 mm za folią, luty bokiem 1,5 mm wokół końcówki, podkładka t, przechył r):

| Podkładka t, przechył r | Końcówka do korpusu koszyka | Lut do ogniwa | Wiązka do korpusu |
|---|---|---|---|
| 0,3 mm, 0,6 mm (cienka taśma, koszyk na środku) | 2,7 mm | 1,5 mm | 2,5 mm |
| 1,0 mm, 0,6 mm | 2,0 mm | 0,9 mm | 1,8 mm |
| 1,6 mm, 0,6 mm (gruba podkładka, koszyk na środku) | 1,4 mm | 0,7 mm | 1,2 mm |
| 1,6 mm, 1,5 mm (koszyk wsparty na zaczepie) | 0,5 mm | 0,7 mm | 0,6 mm |

Ogniwa przyjęto dosunięte do końca koszyka pod przyciskami; przy grubej podkładce wierzch ogniwa jest wyżej niż koniec końcówki, ale leży obok lutu (0,7 mm w poziomie), nie pod nim. Zapas zostaje we wszystkich przypadkach, ale przy grubej podkładce jest za mały na tolerancje lutu i koszyka, więc w montażu obowiązują cztery zasady: koszyk przyklejony cienką taśmą dwustronną (≤0,3 mm) zamiast podkładki Hammonda o nieznanej grubości; koszyk na środku klapki w osi u (u 3,75–65, oba boki podniesione po około 0,6 mm), końcówki PV6 w linii rzędu (obie na v 98, nie jedna nad ogniwami), a przewody lutowane bokiem i odprowadzane wzdłuż rzędu, poza koszykiem (v ≥99).

Sprawdzenie: płytkę z `kicad-cli pcb export step` złożono z modelem obudowy. Do brył z [dopasowania do obudowy](#dopasowanie-do-obudowy-2026-11-09) doszły: pięć PV6 (nakrętka Ø22, korpus Ø16, końcówki i luty Ø12, głębiej niż w karcie), korpus i końcówki przełącznika CISZY, wiązka przycisków 3 mm pod płytką oraz wtyczki z przewodami na J10 i J11. Kolizji nie ma. Odstępy od koszyka z ogniwami liczono osobno (tabela wyżej), z prawdziwym kształtem końcówek PV6 i czterema ogniwami Ø14,5 mm. JP3 ze zworką stoi 16 mm od osi wyłącznika: karta PV6 nie podaje nakrętki, a nakrętki M16 × 1 mają 19–22 mm pod klucz, czyli do 12,7 mm do narożnika. Obrys płytki z sześcioma otworami Ø20 mm sprawdzono osobną bryłą, bez kolizji. Brył nie mają: osłona GT-4R i dźwignia (są przed frontem) oraz trasy przewodów poza wiązką przycisków.

Odrzucone warianty:
- B3F z nasadkami (dotychczas): wierzch nasadki B32-1310 wypadał 2,25 mm pod folią, a pół przekątnej nasadki (8,28 mm) jest większe niż promień otworu Ø16, więc narożniki tarłyby o ściankę otworu, a przez szczeliny widać płytkę;
- przyciski nawigacji lutowane na płytce z wyższą nasadką: wiążą wysokość płytki z frontem z dokładnością ±0,3 mm, a wygląd różni się od wyłącznika;
- przełącznik CISZY lutowany w płytkę z tuleją 15/32": korpus ma 12,7 mm, a między płytką a frontem jest 10,5 mm;
- PV6F240SS-341: ma niebieski pierścień podświetlenia i inne końcówki;
- jedno złącze na cały panel: przewody CISZY i wyłącznika szłyby pod płytką około 80 mm; złącza przy elementach są krótsze, a wyłącznik zostaje na J3;
- złącza wiązek od góry albo kątowe: przewody szłyby w 10,5 mm między płytką a frontem, a końcówki elementów panelu są pod płytką;
- rząd nawigacji niżej (front y 100), żeby końcówki WSTECZ i GÓRA wyszły poza koszyk: mostek H3–WSTECZ spada do 2,4 mm, a nakrętka PV6 (Ø22) zbliża się do słupka skrzynki na 0,8 mm; obie zasady montażu dają ten sam zapas bez zmiany wyglądu;
- przyciski o krótszym korpusie pod WSTECZ i GÓRA: inny wygląd i druga część w BOM, a przy koszyku na środku zapas zostaje;
- ESDA6V1-5SC6 (ST) na liniach przycisków: w LCSC brak na stanie (C6650), a upływ <1 µA karta gwarantuje tylko przy 3 V; TPD4E1U06 ma ≤10 nA i jest w LCSC; Leiditech TPD4E1U06DCKR (LCSC C2972551) jako zamiennik: upływ do 0,5 µA przy 5 V i napięcie pracy 5 V, a TECH PUBLIC (C2987062) ma parametry TI;
- jedna wspólna ochrona dla linii CISZY przy J10: od J11 do niej było około 90 mm ścieżki bez ochrony;
- dioda ESD z odprowadzeniem do szyny 3,3 V (np. USBLC6) na PB: przy wyłączonej stacji szyny nie ma, a PB ma do 5,5 V, więc dioda włączałaby stację;
- czarny PV6 jako wyłącznik: drugi numer części do sprawdzenia; odróżnia go nadruk.

## Montaż w obudowie

Kolejność dla jednej stacji (do sprawdzenia na pierwszej sztuce):
1. Obróbka skrzynki: otwory we froncie i w dolnej ścianie (otwór USB-C 13,2 × 7,2 mm), zeszlifowanie słupków (20, 30) i (80, 30) na równo z frontem.
2. EN3, SMA, pięć PV6 i przełącznik CISZY z osłoną GT-4R (zawias u góry) w otworach; EN3, SMA i PV6 z nakrętkami od środka, przełącznik z nakrętką na zewnątrz, na płytce osłony. Końcówki PV6 ustawia się w linii rzędu (obie na tej samej wysokości). Przewody do EN3 z koszulkami; do PV6 i przełącznika przewody lutuje się bokiem na końcówkach, tak żeby lut nie wystawał poza końcówkę, i odprowadza wzdłuż rzędu, równolegle do frontu. Wiązki kończą wtyki JST XHP:
   - 5-stykowy do przycisków: 1 GÓRA, 2 DÓŁ, 3 OK, 4 WSTECZ, 5 masa. Masa idzie łańcuchem po drugich końcówkach czterech przycisków i jednym przewodem do styku 5;
   - 2-stykowy do wyłącznika;
   - 2-stykowy do CISZY: 1 końcówka środkowa, 2 (masa) końcówka najdalej od zawiasu osłony. Sprawdzenie miernikiem między stykami wtyku: klapka zamknięta, przerwa; klapka otwarta i dźwignia do zawiasu, zwarcie.
3. Ekran i reszta panelu na froncie (stos ekranu do przymiarki).
4. Tulejki 6 mm na sześciu słupkach, płytka elementami do frontu: PV6 i przełącznik CISZY przechodzą przez otwory Ø20 mm, J4 staje przy otworze USB-C. Sześć wkrętów 3 × 12 do tworzyw od spodu, każdy przez podkładkę 1 mm; bez podkładki wkręt oprze się o dno otworu w słupku. Na pierwszej sztuce zmierzyć moment zerwania gwintu w słupku na jednym wkręcie, a dalej dokręcać do około połowy tego momentu.
5. Wtyczki EN3 do J2, wyłącznika do J3, przycisków do J10 i CISZY do J11, przewód SMA do u.FL Wio.
6. Koszyk BH4AAW przyklejony cienką taśmą dwustronną (≤0,3 mm, bez podkładki z kompletu) na klapce pokrywy, w otworze klapki i na środku w poziomie (z obu boków po równo, nie oparty o zaczep po prawej), wtyczka koszyka do J1.
7. **Pokrywa klapką po lewej, patrząc od frontu** (koszyk nad dolnym lewym obszarem płytki, z dala od Wio). Na wewnętrznej stronie pokrywy i na ścianie skrzynki przy lewym górnym narożniku są dwie strzałki „GÓRA”, które przy złożeniu mają leżeć obok siebie (naklejka albo marker). Obrócona o 180° pokrywa stawia koszyk pod Wio i C50 i nie zamknie się; nie dociskać jej wtedy śrubami.
8. Cztery śruby M3 pokrywy.

## Dobór części (2026-11-09)

Numery LCSC są w kolumnie „LCSC” w [bom.csv](bom.csv); stany sprawdzone 2026-11-09 w LCSC i JLC. Żadna z części toru zasilania, USB i diod nie jest w puli basic JLC (także AO4264E, wcześniej opisany jako basic), więc wszystkie idą jako extended albo, dla TVS, z puli promocyjnej.

- **Q2, Q3: AO4292E (100 V) zamiast AO4264E (60 V).** Przy odwróconym impulsie wejście ma −53,3 V, a wspólny dren zostaje około VSYS − 0,6 V (dioda podłożowa Q3, VSYS trzymają ogniwa albo C50), więc Q2 widzi VSYS + 53,3 V: około 59,7 V na świeżych ogniwach, a około 70 V, gdy impuls przyjdzie przy pracy z 12 V tuż pod progiem OVP (VSYS do 17,3 V). Przy dodatnim impulsie i otwartym łączniku Q3 widzi około 53 V. AO4292E (100 V) mieści oba przypadki. Granica LM74800 dla OUT, C i VSNS (SNOSD95C 7.1: ≤70 V + V(A), czyli 16,7 V przy V(A) = −53,3 V) jest spełniona w całym zakresie pracy, czyli przy wejściu do 16 V; przekracza ją o najwyżej 0,6 V tylko wejście 16–17,3 V, poza zakresem pracy ([na pierwszych sztukach v2](#na-pierwszych-sztukach-v2)). AO4292E: VGS ±20 V wobec napędu DGATE/HGATE 10–13 V (karta LM7480, 7.5 i 10.2.4: co najmniej 15 V), próg 1,6–2,7 V, ≤23 mΩ przy 10 V (6 mV przy 0,25 A wobec zalecanych <50 mV), Ciss 1,2 nF jak AO4264E, więc C31 100 nF nadal spełnia warunek ≥10 × (Ciss Q2 + Ciss Q3). Ta sama obudowa SOIC-8 i te same wyprowadzenia. Zapasowy BUK7Y15-60EX odpada: ma obudowę LFPAK56 i w LCSC nie ma go na stanie.
- **D7: ROHM RB168MM-40 (Schottky „super low IR”).** Prąd wsteczny diody płynie do ogniw, gdy stację zasila 12 V. Karta Energizer L91 (EBC-8915AP-D9X) dopuszcza 2 µA, próba odbiorcza wymaga ≤1 µA. RB168MM-40: najwyżej 0,55 µA przy 40 V w 25 °C (karta), z wykresu VR–IR przy 15 V typowo około 0,02 µA w 25 °C, 0,1 µA w 45 °C i 0,4 µA w 60 °C. Wartości maksymalnej na gorąco karta nie podaje. Szacunek dla najgorszej sztuki: wartość maksymalna z 25 °C × wzrost z wykresu (od typowych 0,05 µA przy 40 V w 25 °C), przy 15 V, czyli więcej niż na diodzie w pracy (VSYS − ogniwa, najwyżej około 13 V przy progu OVP i słabych ogniwach): około 0,8 µA w 40 °C, 1,2 µA w 45 °C, 1,8 µA w 50 °C, 2,7 µA w 55 °C i 4,1 µA w 60 °C. Granica 2 µA z karty L91 jest więc spełniona do około 50 °C także dla najgorszej sztuki, a typowo do 60 °C. Prąd wsteczny płynie tylko przy zasilaniu z 12 V. Stacja pracuje w pomieszczeniu (próby odbiorcze do +45 °C), a dioda prawie się nie nagrzewa (≤50 mW przy 120 mA tylko przy pracy z ogniw, kiedy prąd wsteczny nie płynie). Wybór zostaje z tym jawnym ograniczeniem. Odrzucone: idealna dioda (LTC4412 i podobne) z prądem spoczynkowym ≥11 µA z ogniw w stanie wyłączonym (decyzja Z7), układy ładowania wstecznego do 5,5 V (TI LM66100, MAX40200), bo świeże ogniwa Li-FeS2 mają do około 7,2 V, i dioda krzemowa (czas pracy na ogniwach poniżej 48 h). Spadek przy 120 mA z wykresu: typowo około 0,43 V w 25 °C i około 0,5 V w −25 °C (karta podaje wartość maksymalną tylko przy 1 A: 0,65 V wobec typowych 0,60 V) zamiast 0,35 V przyjętych w [projekcie zasilania](../r02/zasilanie.md#tor-ogniw). Model przy 6 V daje około 48,3 h w 20 °C (typowo 0,43 V), a dla najgorszej sztuki (około 0,48 V, szacunek z wykresu; karta gwarantuje tylko ≤0,65 V przy 1 A) około 47,9 h zamiast 49 h. Wymaganie ≥48 h dotyczy 20 °C, a w −10 °C obowiązuje ≥40 h. Typowa sztuka ma więc tylko około 0,3 h zapasu, a najgorsza wypada około 0,1 h poniżej wymagania; rozstrzyga pomiar T6. IFSM 40 A wobec ≤5 A udaru z R40. Zwykłe diody Schottky'ego 1 A (SS14, PMEG4010) mają w 25 °C 20–500 µA, a dioda krzemowa (0,8–1 V) skraca pracę na ogniwach poniżej 48 h. Footprint SOD-123F jak BAS116H.
- **F1: dwa zaciski Littelfuse 01110501Z (seria 111 501).** Pasują do obecnego footprintu (17,8 × 5,0 mm, otwory 1,17 mm), 10 A, zacisk około 7 mm nad płytką (rysunek Littelfuse). Oprawki zamknięte (Littelfuse 0PTF0078P, 11,5 mm) wymagałyby innego footprintu, a 12 V w zamkniętej obudowie nie wymaga osłony.
- **Tranzystory N małej mocy:** zamiast Diodes 2N7002-7-F (≤1 µA w 25 °C, ≤500 µA w 125 °C, czyli w 60 °C około 8,8 µA, więcej niż granica KILL 5,8 µA) onsemi BSS138LT1G na Q7, Q10, Q11 i Q12 (≤0,5 µA przy 50 V w 25 °C, ≤5 µA w 150 °C, w 60 °C około 1 µA; próg bramki do 1,5 V) i Nexperia 2N7002 na Q5 (≤1 µA w 25 °C, ≤10 µA w 150 °C), bo dren Q5 przy wyłączonej stacji widzi do 53,3 V, a BSS138 ma 50 V. Wartości w 60 °C to interpolacja wykładnicza między dwiema temperaturami z karty.
- **D6, D11: BAV199 zamiast BAT54S.** Te same piny SOT-23, 75 V ciągle (85 V szczytowo), ≤5 nA w 25 °C i ≤80 nA w 150 °C. BAT54S nie ma w karcie wartości na gorąco; typowo w 60 °C około 0,7 µA na diodę, a w najgorszym przypadku błąd pomiaru 12 V szacunkowo do około 1,2 V. Kosztem jest zacisk przy około −0,6…−0,9 V zamiast −0,3 V, więc wcześniej (około −0,5 V) przewodziłyby diody ochronne ESP32-S3, których prądu karta nie podaje. Dlatego węzeł dzielnika łączy się z GPIO5 i GPIO4 przez 10 kΩ (R76, R77): prąd do pinu ≤(0,9 − 0,5) V / 10 kΩ = 40 µA zamiast do 0,224 mA (−53,3 V przez 231 kΩ; −33 V ciągle: 0,137 mA). Filtr 100 nF (C33, C34) jest za rezystorem, przy wejściu ADC, tak jak w warunkach pomiaru charakterystyk ADC w karcie ESP32-S3 (5.5), więc próbkowanie bierze ładunek z kondensatora, a nie przez 10 kΩ. Prąd wejściowy pinu ≤50 nA (karta 5.4, tylko 25 °C) płynie przez 10 kΩ i opór dzielnika: dla 12 V 24,4 kΩ, czyli 1,2 mV na pinie i około 20 mV na pomiarze 12 V; dla ogniw 18 kΩ, czyli 0,9 mV i około 4 mV. Wartości na gorąco karta nie podaje. Elementy leżą przy pinach (`CLOSE` ≤10 mm), a długa ścieżka od dzielnika do R76/R77 ma po stronie pinu filtr 10 kΩ × 100 nF. Kosztem są dwa rezystory 10 kΩ z istniejącej pozycji BOM i dłuższe ustalanie pomiaru ogniw (≥20 ms po DIV_EN zamiast około 7 ms). Odrzucone: sam BAV199 bez rezystora (prąd przez diody ochronne ESP32-S3 bez danych w karcie), rezystor przed węzłem z kondensatorem bez kondensatora przy pinie (poza warunkami z karty 5.5).
- **Wejście ON: D13 BAS116H szeregowo zamiast zacisku BAT54H, R70 280 kΩ zamiast 309 kΩ.** BAT54H przy 0,1 mA ma 0,22 V w 25 °C i 0,335 V w −40 °C, więc na zimno dochodzi do granicy −0,3 V dla ON. Dioda szeregowa blokuje odwrotne napięcie i usuwa upływ Schottky'ego z węzła ON. 287 kΩ 0,1% nie ma w LCSC, a 280 kΩ (na stanie) daje próg około 8,2–9,6 V (szacunek, bo spadek BAS116H przy około 27 µA nie jest w karcie; próba odbiorcza: 8,0–9,8 V), prawie jak dotąd.
- **Szyna ON i bramka Q9 przy wyłączonej stacji: R78 100 kΩ (nowy) i R51 220 kΩ zamiast 1 MΩ.** Bez R78 szynę ON obciążają tylko dzielniki bramek (550 kΩ), a upływ Q8 (BSS84AK: ≤1 µA w 25 °C, ≤2 µA w 150 °C, w 60 °C około 1,2 µA, szacunek) podniósłby ją do około 0,66 V, a bramki Q5 i Q10 do około 0,6 V, czyli blisko progu BSS138 (minimum 0,5 V przy 1 mA w rew. 8, na gorąco około 0,07 V mniej). Q10 mógłby wtedy otworzyć Q9 i uruchomić przetwornicę wyłączonej stacji, co rozładowałoby ogniwa w przechowaniu. Z R78 szyna ma ≤0,1 V. Kosztuje to 60 µA z ogniw i około 0,13 mA z 12 V (do 0,33 mA przy zacisku 33 V), tylko przy włączonej stacji. Upływ Q10 (w 60 °C około 1 µA, szacunek) daje na R51 220 kΩ najwyżej 0,22 V wobec progu Q9 −1,1 V (karta, 25 °C); z 1 MΩ byłoby do 1 V. R51 pobiera przy włączonej stacji do 80 µA (VSYS 17,3 V).
- **D4 SMBJ33CA zostaje (LCSC C19077587, Hongjiacheng/R+O).** Karta tej części podaje te same wartości co Littelfuse: VRWM 33 V, VBR 36,7–40,6 V (40,6 V w opisie LCSC to maksimum przebicia), ograniczenie 53,3 V przy 11,26 A. Różni się tylko upływ przy 33 V (≤5 µA zamiast ≤1 µA); płynie on z wejścia 12 V, nie z ogniw, i przy 12–15 V jest dużo mniejszy.
- **R32 zostaje 1 kΩ.** Przy wyłączaniu C32 dokłada przez R32 najwyżej 14,5 mA (napęd HGATE do 14,5 V) do prądu, który musi ściągnąć HGATE, a źródło HGATE 39–75 µA daje na nim tylko 75 mV. Karta LM7480 (7.5) podaje ściąganie HGATE ≥168 mA tylko przy przepięciu (OV); dla wyłączenia przez EN/UVLO nie podaje prądu. Płytka TI LM74800EVM-CD ma 100 Ω z 10 nF, ale u nas 100 Ω pozwoliłoby C32 dokładać do 145 mA.
- **Bez zmian:** SI2309CDS, BSS84AK, BAS116H, BZT52C15/C33/C5V1 (Diodes Incorporated), USBLC6-2SC6 i gniazdo HRO TYPE-C-31-M-12 są w LCSC na stanie (od kilku do kilkuset tysięcy sztuk). Footprint gniazda w KiCad jest dla tej właśnie części; ma cztery przewlekane nóżki obudowy, lutowane razem z SMD. Zenery mają w puli preferowanej JLC odpowiedniki SOD-123 z tymi samymi granicami upływu w kartach; zostają części Diodes Incorporated, bo przy 10 płytkach różnica kosztu jest pomijalna.

## Ścieżki (2026-11-10)

Płytka ma komplet ścieżek. **Wynik: 0 niepołączonych, 0 naruszeń DRC (poza sitodrukiem), 0 naruszeń ERC**, przy pełnej regule odstępu wysokiego napięcia (0,6 mm od odsłoniętego padu, 0,3 mm pod maską). Żadnej reguły nie złagodzono, żeby DRC przeszło; dwie zmiany w sprawdzeniach są opisane niżej ([Reguły](#reguły)). Ścieżki są po pierwszym, własnym sprawdzeniu, przed niezależnym przeglądem. **Nie zamawiać** przed tym przeglądem i przed punktami z [Przed zamówieniem](#przed-zamówieniem).

### Liczba warstw: 4

| | 2 warstwy | 4 warstwy |
|---|---|---|
| masa | wylewki przecinane ścieżkami; prąd powrotny przetwornicy i 12 V szuka drogi naokoło | ciągła warstwa masy pod całą płytką |
| przetwornica | rysunek 17 karty LTC3115-1 zakłada masę pod układem; płytka testowa jest 4-warstwowa i tylko ten układ jest zmierzony | ten sam układ co na zmierzonej płytce testowej |
| USB (Full Speed) | działa, impedancja nie jest krytyczna | działa, ścieżka nad ciągłą masą |
| gęstość | 164 elementy, cztery tory napięć, sześć otworów Ø20 mm i wycięcie EN3: dwie warstwy na ścieżki i masę nie wystarczą | dwie warstwy na ścieżki, dwie na płaszczyzny |
| JLC, 200 × 120 mm, 1,6 mm, HASL, bez wysyłki (kalkulator 2026-11-10) | 5 szt. 15,60 USD, 10 szt. około 27 USD | 5 szt. 39,80 USD, 10 szt. 54,60 USD |

Wybór: **4 warstwy.** Dopłata to około 25–28 USD na całą serię, czyli około 3–5 USD na płytkę, a w zamian przetwornica ma ten sam układ co zmierzona płytka testowa i cała płytka ma ciągłą masę. Zdanie w [obudowie R02](../r02/obudowa.md), że płytka tej wielkości „opłaca się tylko jako dwuwarstwowa”, nie zgadza się z dzisiejszymi cenami JLC i trzeba je tam poprawić.

Warstwy: L1 (góra) elementy i ścieżki; In1 ciągła masa; In2 płaszczyzna +3V3 (przechodzą przez nią tylko krótkie ścieżki BST przetwornicy, jak na płytce testowej); L4 (spód) ścieżki. Stos JLC04161H-7628, 1,6 mm.

### Reguły

Reguły zapisuje `tools/route_pcb.py` (klasy sieci w projekcie, reguły własne w `cad/plytka-v2.kicad_dru`); w `cad/` nic nie zmienia się ręcznie.

| Klasa | Ścieżka | Przelotka (otwór) | Sieci | Skąd |
|---|---|---|---|---|
| 12 V | 0,6 mm | 0,8 (0,4) mm | 12V_IN, V12_F, V12_MID | do 1 A ciągle; IPC-2152 dla 1 oz daje przy 0,6 mm przyrost około 10 °C; impuls TVS około 190 A przez 1 ms ścieżka 0,6 mm wytrzymuje (wzór Onderdonka) |
| HV | 0,3 mm | 0,6 (0,3) mm | węzły sterowania 12 V: V12_FLT, V12_SW, bramki i dzielniki LM74800 i LTC4368, ON i inne | małe prądy, ale napięcie jak 12 V |
| VSYS | 0,8 mm | 0,8 (0,4) mm | VSYS, BAT_IN, BAT_R | prąd wejściowy przetwornicy rośnie przy niskim napięciu ogniw; szerzej niż 12 V |
| zasilanie | 0,5 mm | 0,6 (0,3) mm | +5V, +3V3_RF, brzęczyk, BST_SW, CONV_VCC | prądy do kilkuset mA |
| USB | 0,25 mm | 0,6 (0,3) mm | USB_DP, USB_DN | Full Speed; 0,25/0,15 mm nad masą daje około 90 Ω (szacunek ze wzoru), dla 12 Mb/s bez znaczenia |
| płaszczyzna | 0,4 mm | 0,6 (0,3) mm | GND, +3V3 | krótkie odcinki do przelotek |
| pozostałe | 0,2 mm | 0,6 (0,3) mm | sygnały 3,3 V | |

Najmniejsze wartości: odstęp 0,15 mm, ścieżka 0,15 mm, przelotka 0,6/0,3 mm, pierścień 0,15 mm, od krawędzi 0,5 mm, otwór od otworu 0,3 mm. JLC dopuszcza mniejsze wartości, więc płytka mieści się w podstawowym procesie bez dopłat.

**Odstęp wysokiego napięcia.** Dla sieci 12 V i HV obowiązuje **0,6 mm od odsłoniętego padu i 0,3 mm między miedzią pod maską**, na warstwach zewnętrznych. To wiersz 31–100 V tabeli 6-1 IPC-2221B (B2 dla odsłoniętych przewodników: 0,6 mm; B4 dla przewodników pod powłoką: 0,13 mm, wzięte z zapasem jako 0,3 mm). Napięcia, które pokrywa: 33 V ciągle (instalacja 24 V, ładowanie do 28,8 V), ograniczenie TVS 53,3 V w impulsie, −53,3 V przy odwrotnym podłączeniu i do około 70 V na Q2 (suma przy odwróceniu). Reguła nie dotyczy pary dwóch padów (rozstaw pinów jednej części ustala jej producent) ani miedzi wewnątrz obrysów U5 i U6 (rozstaw 0,5 i 0,65 mm). Ścieżki 12 V, VSYS i zasilania mają też najmniejszą szerokość w DRC (0,6, 0,6 i 0,4 mm).

Dwie zmiany w sprawdzeniach względem szkicu, obie z powodu geometrii części, nie po to, żeby ominąć błąd:

- najmniejsza szerokość ścieżki VSYS nie obowiązuje wewnątrz obrysu U5 (tak jak wcześniej wewnątrz U7 i C46): pin OUT układu U5 ma pad 0,25 mm i służy tylko do pomiaru napięcia, prąd VSYS płynie przez Q3;
- C30 może leżeć do 5 mm od U5 (było 4 mm; C31 zostaje przy 4 mm): C30 stoi za R31, jego pad masy jest 3,6 mm od pinu 7, a pad zasilania łączy się z pinem 12 szeroką miedzią wspólnego drenu na L4.

### Co zmieniło się w rozmieszczeniu

Szkic pokazał, że ścieżki 12 V nie mieszczą się w korytarzu przy wycięciu EN3 i że bloki 12 V są za gęste. Zmiany (wszystkie w `make_pcb.py`; pozycje panelu z [założeń obudowy](../obudowa/zalozenia.py) są bez zmian i test obudowy przechodzi):

- **Wejście 12 V po lewej stronie wycięcia EN3:** J2 (86, 115), bezpiecznik F1 (86, 103) i TVS D4 (86, 108) leżą teraz razem, 3 mm od siebie. Wcześniej J2 był po prawej, a F1 po lewej stronie wycięcia. D7 (dioda toru ogniw) przesunięta obok, do (71, 107).
- **Łącznik 12 V jako jedna stała grupa w prawym dolnym rogu** (środek U5 w (168, 108)): Q2, U5, Q3 w jednej linii, C31, R30, R31, C30, R32, C32 przy pinach U5, a filtr R46, C35, D10 tuż obok wspólnego drenu (wcześniej 70 mm dalej, przy U6). Miedź grupy jest narysowana ręcznie.
- **C50** przeniesiony do (132, 84), między łącznik, tor ogniw i przetwornicę.
- **Sterownik wyłącznika U6 z C36** jako stała grupa w wolnym miejscu u góry po prawej (152, 36), jego części i przełącznik zezwolenia przetwornicy (Q9, Q10) w tym samym obszarze, obok przetwornicy.
- **Dzielniki napięcia 12 V i samoczynnego startu** (Q4, Q5 i sąsiedzi) po prawej stronie wycięcia EN3, bezpośrednio nad linią 12 V na L4.
- **Większe odstępy:** części strony 12 V stoją co najmniej 1,3 mm od siebie (tranzystory SOT-23 1,7 mm, U6 2,6 mm), pozostałe małe części układane automatycznie 1,2 mm (było 0,6 mm). Wyjątek: filtry i ochrona ESD przy złączach zostają przy 0,6 mm, bo muszą leżeć do 10 mm od złącza.
- Obszar bloku toru ogniw powiększony w górę (y 80–119,5).
- Korpus części przewlekanej blokuje teraz tylko swoją stronę płytki; po drugiej stronie liczą się jej pady z odstępem 2,5 mm od padów SMD.

### Jak powstają ścieżki

`build.sh` dalej buduje płytkę od zera, a w `cad/` nic nie zmienia się ręcznie:

1. `make_pcb.py` rozmieszcza elementy.
2. `route_pcb.py prepare` ustawia 4 warstwy, klasy i reguły, rysuje miedź ręczną (niżej) i zapisuje pierwsze zadanie dla routera, `checks/routing.dsn`.
3. `route_pcb.py stage N` wczytuje wynik etapu N−1 i zapisuje zadanie etapu N (`checks/routing-N.dsn`). Gdy wszystko jest połączone, pisze „open nets: none” i etapy się kończą.
4. `route_pcb.py finish` usuwa nieużyte odcinki pomocnicze, wylewa płaszczyzny masy i +3V3.
5. DRC z regułami projektu; `build.sh` kończy się błędem także wtedy, gdy zostaje choć jedno niepołączone miejsce.

Ścieżki liczy osobno `tools/route.sh` (Freerouting 2.5.0, Java 25; około 6 minut). Wynik każdego etapu (`checks/routing*.ses`) jest zachowany razem z sumą zadania, z którego powstał. `build.sh` wczytuje sesję tylko wtedy, gdy suma się zgadza, więc po każdej zmianie rozmieszczenia albo miedzi ręcznej trzeba uruchomić `route.sh` od nowa; inaczej `build.sh` zbuduje płytkę bez ścieżek i zakończy się błędem. Dwa przebiegi `build.sh` dają ten sam plik.

Etapy routera:

1. sieci zasilania i wszystkie sieci, które mają pad w obszarach części 12 V;
2. reszta; sieci gotowe po etapie 1 są już stałą miedzią;
3. i dalej, tylko gdy coś zostało otwarte: sieci otwarte prowadzone od nowa razem z sieciami, których ścieżki leżą do 3 mm od ich padów. W tym wyniku wystarczyły dwa etapy.

Router nigdy nie dostaje sieci, która jest już kompletna (miedź ręczna albo wcześniejszy etap), więc nie dokłada drugiej drogi, na przykład na węzłach przetwornicy.

### Miedź ręczna (przed routerem)

- **Przetwornica** według rysunku 17 karty LTC3115-1, bez zmian względem płytki testowej: wylewki SW1 i SW2 pod cewką, wejście VSYS i wyjście +3V3 przy kondensatorach, wyspy masy z przelotkami do In1, BST1 i BST2 na In2, sprzężenie zwrotne pod układem.
- **Łącznik 12 V (U5, Q2, Q3):** pola miedzi na źródłach i drenach, wspólny dren na L4 przez trzy przelotki z każdej strony, ścieżki bramek i pomiarowe, kondensatory przy pinach.
- **Linie zasilania na L4:** 12 V z J2 do bezpiecznika 1,0 mm; 12 V za bezpiecznikiem 1,2 mm do źródeł Q2; VSYS 1,0 mm od Q3 przez C50 do przetwornicy; tor ogniw 0,8 mm od D7 do C50.
- **Odgałęzienia od tych linii:** Q4, R33, D5 i D13 mają własną przelotkę i odcinek 0,6 mm do linii 12 V; Q9 i R51 odcinek 0,6 mm do wejścia przetwornicy.
- **Wyjścia z pinów:** z każdego pinu tranzystora SOT-23 po stronie 12 V i z pinów U6 wychodzi krótki odcinek ustawiony tak, żeby był 0,62 mm od sąsiedniego padu; trzy piny +5V złącza ekranu (raster 0,5 mm) łączy wspólna szyna.
- **Płaszczyzny:** przelotka do In1 albo In2 przy każdym padzie SMD masy i +3V3 (razem 124 przelotki masy i +3V3), wylewki masy na L1 i L4.
- **Strefy bez miedzi:** otwory montażowe (wszystkie warstwy), otwory panelu i przycisk przygotowania (warstwy zewnętrzne), pas 0,5 mm przy krawędzi.

### Jak router trzyma odstęp wysokiego napięcia

Freerouting zna tylko jeden odstęp na klasę sieci, nie zna reguły „0,6 mm od padu”. Dlatego w zadaniu dla routera (tylko tam, płytka zostaje bez zmian):

- klasy 12 V i HV mają odstęp 0,31 mm (miedź pod maską);
- pady w obszarach części 12 V, pady wszystkich części przewlekanych i pady małych części (do trzech padów) na całej płytce są powiększone o 0,31 mm z każdej strony, co razem daje 0,62 mm od padu. Wyjątek: filtry przy złączach (stoją za gęsto, ścieżka HV tam nie wchodzi; DRC i tak to sprawdza);
- koniec każdego ręcznego odcinka wyjściowego jest dla routera zwykłym padem („kotwica”), bo router nie umie zacząć ścieżki od końca stałego odcinka.

DRC w KiCad liczy potem z prawdziwą regułą projektu i to ono jest sprawdzianem.

### Pułapki narzędzi

- Freerouting traktuje warstwy wewnętrzne bez płaszczyzny jako sygnałowe, a jego strefa zakazu blokuje też przelotki. `route_pcb.py` usuwa więc In1 i In2 z zadania i podaje routerowi tylko L1 i L4.
- Wylewki dostaje jako szerokie ścieżki zastępcze (niewypełnionej wylewki nie widzi, a strefa zakazu nad stałymi przelotkami odrzuca całe sieci).
- Nie łączy nowej ścieżki ze środkiem ani końcem stałej ścieżki. Stąd kotwice, ręczne odgałęzienia od linii zasilania i prowadzenie otwartej sieci od nowa zamiast jej uzupełniania.
- Kończy pracę po 10 przebiegach bez poprawy wyniku, a do wyniku liczy też sieci, których nie prowadzi (płaszczyzny). Stąd etapy.
- Zwężanie ścieżki przy cienkim pinie musi zostać włączone: bez niego zostawiał kilkanaście sieci otwartych. Po wczytaniu każda ścieżka dostaje z powrotem co najmniej najmniejszą szerokość swojej klasy, a DRC sprawdza odstępy poszerzonych ścieżek.
- Jeden kształt padu na nazwę obudowy: część z powiększonymi padami dostaje w zadaniu własną nazwę obudowy.
- W wyniku powtarza kawałki stałych ścieżek; `route_pcb.py` bierze z sesji tylko sieci, które przed etapem były otwarte.
- KiCad przy wczytaniu sesji usuwa wszystkie niezablokowane ścieżki i czyta przelotki routera jako ślepe. Dlatego po każdym etapie ścieżki są blokowane, a przelotki zamieniane na przelotowe; przelotki łączące tylko jedną warstwę są usuwane.
- Warunek reguły w `kicad_dru` rozbity na dwie linie sprawia, że `kicad-cli` cicho pomija cały plik reguł. `build.sh` sprawdza więc przed DRC, czy reguły w ogóle działają (reguła próbna).

### Wynik

- **Połączenia:** 0 niepołączonych. **DRC:** 0 naruszeń poza sitodrukiem (55 uwag o sitodruku: opisy na padach i na sobie, do poprawy razem z opisami). **ERC:** 0.
- **Warstwy:** L1 2,95 m ścieżek, L4 2,97 m, In1 ciągła masa bez ścieżek, In2 płaszczyzna +3V3 i 17 mm ścieżek BST przetwornicy. Razem 1474 odcinki i 320 przelotek (179 ręcznych, w tym 124 do płaszczyzn).
- **Szerokości torów prądowych:** 12V_IN 1,0 mm; V12_F 1,0–1,2 mm (odgałęzienia do dzielników 0,6 mm); V12_MID pola miedzi i 0,6–1,0 mm; VSYS 0,6–1,0 mm; BAT_IN i BAT_R 0,8 mm; +5V, +3V3_RF i brzęczyk 0,4–0,5 mm. Węższe (0,15–0,25 mm) są tylko odcinki pomiarowe przy pinach U5 i U7, wewnątrz ich obrysów.
- **Spadki napięcia (miedź 35 µm):** 12 V za bezpiecznikiem, około 105 mm przy 1,2 mm: 43 mΩ, czyli 43 mV przy 1 A. VSYS od Q3 przez C50 do przetwornicy, około 60 mm przy 1,0 mm: 29 mΩ, 16 mV przy 0,55 A. Tor ogniw od D7 do C50, około 70 mm przy 0,8 mm: 43 mΩ, 24 mV przy 0,55 A.
- **USB:** USB_DP 90,5 mm z 1 przelotką, USB_DN 83,2 mm z 2 przelotkami (różnica 7,3 mm, dla Full Speed bez znaczenia).
- Rendery: [od góry](render-sciezki-gora.png), [od spodu](render-sciezki-spod.png).

### Odrzucone warianty

- **Złagodzenie reguły HV albo wyłączenie jej w blokach 12 V:** odrzucone, reguła jest wymaganiem. Zamiast tego większe odstępy części i ręczne wyjścia z pinów.
- **Router z odstępem 0,6 mm dla klas HV:** nie wychodzi z pinów SOT-23 i U6. Stąd 0,31 mm w klasie i powiększone pady.
- **Jeden przebieg routera na całą płytkę:** zostawiał około 40 otwartych połączeń.
- **Wyłączone zwężanie przy pinach:** kilkanaście otwartych sieci (wyżej).
- **Starszy algorytm Freeroutingu (v19) i wyłączony etap „fanout”:** bez poprawy.
- **Ręczne dokańczanie ścieżek po routerze:** odrzucone, bo zależałoby od wyniku routera i nie dałoby się go powtórzyć. Ręczna miedź powstaje tylko przed routerem.
- **Wszystkie części toru 12 V w jednej grupie po lewej stronie wycięcia** (propozycja ze szkicu): wymagałaby przesunięcia toru ogniw i bloku USB. Wybrano mniejszą zmianę: wejście (J2, F1, D4) po lewej, łącznik w wolnym prawym dolnym rogu, a między nimi jedna linia 1,2 mm na L4.

### Ryzyka i co zostaje

- **Niezależny przegląd ścieżek** (ten PR zostaje szkicem do tego przeglądu).
- **Ścieżki są z automatu.** Elektrycznie spełniają reguły, ale nikt nie układał ich ręcznie pod zakłócenia: sygnały sterowania 12 V biegną daleko (S12_EN około 113 mm, V12_FLT 77 mm), a na L1 przy cewkach przechodzą dwa sygnały (RF_RESET przy L2, BTN_OK przy L1). Pod przetwornicą sygnały idą tylko po L4, pod dwiema płaszczyznami. Do oceny w przeglądzie i na pierwszych sztukach.
- **Wynik routera jest wrażliwy na drobne zmiany.** Po zmianie rozmieszczenia `route.sh` może potrzebować więcej etapów albo zostawić otwartą sieć; wtedy `build.sh` kończy się błędem i trzeba poprawić rozmieszczenie w tym miejscu. Zachowane sesje gwarantują tylko powtarzalność obecnego wyniku.
- **Wiązka 12 V:** J2 jest teraz po lewej stronie wycięcia EN3 i obrócony; długość i ułożenie przewodów od EN3 do J2 oraz kolejność żył we wtyczce sprawdzić na przymiarce ([polaczenia.md](polaczenia.md) podaje piny J2).
- **Sitodruk:** 55 uwag DRC, opisy części nachodzą na pady i na siebie, najgęściej przy U5.
- **Impedancja USB i stos warstw:** zapisać stos (`checks/stackup.json`) i policzyć w kalkulatorze JLC zamiast ze wzoru; dla Full Speed niekrytyczne.
- **Zdanie w [obudowie R02](../r02/obudowa.md)**, że płytka tej wielkości „opłaca się tylko jako dwuwarstwowa”, nie zgadza się z dzisiejszymi cenami JLC i trzeba je tam poprawić (osobna zmiana).
- Pomiary z [Na pierwszych sztukach v2](#na-pierwszych-sztukach-v2) bez zmian.

## Przed zamówieniem

Do rozstrzygnięcia przed pierwszym zamówieniem płytki:
- przyciski: obsługa PV6 w rękawicach przy rozstawie 32 mm;
- obudowa, przymiarka z prawdziwą skrzynką (obrys, otwory i wysokości są już dopasowane do modelu STEP, [Dopasowanie do obudowy](#dopasowanie-do-obudowy-2026-11-09)): mocowanie i położenie koszyka BH4AAW na klapce (płasko czy na obrzeżu); pięć PV6 i przełącznik CISZY w otworach Ø20 mm płytki; dźwignia przełącznika (18 mm) pod osłoną GT-4R (opis osłony: 17,5 mm) i zamykanie klapki; odstęp końcówek WSTECZ i GÓRA od koszyka z ogniwami (z modelu 1,4–2,7 mm przy koszyku na środku) przy cienkiej taśmie; kierunek CISZY miernikiem i czy sprężyna puszczonej klapki nie przerzuca dźwigni z położenia CISZA; tuleja przełącznika (do Ø12,24 mm) w otworze Ø12,2 mm płytki GT-4R; głośność BZ1 przez kratkę 7 × Ø1,5 mm; stos ekranu (szybka, światłowód, panel, pianka) i długość taśmy do J7; oś USB-C w otworze ściany, czoło gniazda 0–1 mm od niej i próba z kilkoma kablami o różnych osłonach wtyku (pełne włożenie, bez oporu o ścianę); oś EN3 0,8 mm pod płytką, korpus i przewody w wycięciu; oś SMA i przewód do u.FL; szlifowanie dwóch słupków pod oknem ekranu; tulejki 6 mm i wkręty 3 × 12 z podkładką (moment zerwania gwintu na pierwszej sztuce, czy słupek Ø4,75 mm nie pęka przy wkręcie 3 mm i czy płytka trzyma się po kilku miesiącach); D1 przez otwór Ø5,5 mm (widoczność z kilku metrów); oznaczenie strzałkami położenia pokrywy; zwrot Wio i położenie u.FL. Na obrazku Seeed od strony elementów J1 leży po lewej, pin 1 przy otworze Ø 2,2 mm, a u.FL przy pinie 7 J2. Gniazda (z góry J9 po lewej, J8 po prawej, piny 1 przy y 67,4) pasują, gdy listwy wychodzą od strony bez elementów, czyli moduł wisi elementami w dół; potwierdzić przymiarką;
- niezależny przegląd ścieżek ([Ścieżki](#ścieżki-2026-11-10)); po przymiarce obudowy ewentualne poprawki rozmieszczenia i nowy przebieg routera;
- wnioski z kroku 4 i decyzja: moduły wpinane czy przylutowany ESP32-S3 i układ radiowy;
- program stacji: piny GPIO3, GPIO4, GPIO5 i GPIO45–48, ADC ogniw i 12 V, KILL i INT, [czuwanie](../../docs/spec/oprogramowanie.md#czuwanie);
- pomiary na [płytce testowej przetwornicy](../przetwornica-3v3/README.md): sprawność LTC3115-1 przy 3,3 V (Z11, [elektronika](../../docs/spec/elektronika.md#zasilanie-stacji)) i Burst Mode U7 (typowo poniżej 50 mA) przy starcie ESP32-S3 i panelu oraz przy 4 V na wejściu: 3,3 V nie może przy tym spaść do progu nadzorcy FRAM 2,7 V (U3). Płytka testowa nie ma ESP32-S3, panelu ani nadzorcy, więc do tej próby podłącza się L0 (DevKitC na płytce v1.1, z panelem i nadzorcą U3) pinem 3V3 i G do VOUT płytki testowej, bez USB (DevKitC dopuszcza tylko jedno źródło zasilania). Gdyby 3,3 V spadało: najpierw program włącza PWM (GPIO45) zaraz po starcie, przed panelem i radiem; gdyby spadek był już w czasie ładowania programu (przed kodem stacji), większa pojemność na 3V3. Ostatecznie można rozdzielić sieć PWM_SYNC i GPIO45 (rezystor 0 Ω od PWM/SYNC do VCC przetwornicy, GPIO45 odłączony z R63 do masy), ale PWM bez obciążenia bierze około 12 mA (karta LTC3115-1, wykres „PWM Mode No-Load Input Current”, 1 MHz, 5 V; przy 750 kHz i 3,3 V niewiele mniej) zamiast 50 µA w Burst Mode, także w czuwaniu i przy wyłączonym radiu, czyli około 60 mW przy 6 V, co przy zapasie modelu poniżej 1 h spycha czas pracy na ogniwach wyraźnie poniżej 48 h. GPIO45 wysoki przy resecie (R63 do 3V3) odpada, bo wybiera 1,8 V dla flash, a WROOM-1 N8R8 ma flash 3,3 V; eFuse VDD_SPI_FORCE i VDD_SPI_TIEH, które to obchodzą, są nieodwracalne i zostają tylko jako ostateczność;
- pobór DevKitC przez 3V3 bez USB, na jednej płytce DevKitC zasilanej z zasilacza laboratoryjnego ([elektronika](../../docs/spec/elektronika.md#zasilanie-stacji), punkt 1): w pracy i w lekkim uśpieniu MCU (dioda zasilania, dioda RGB, CP2102N; szacunek 1–2 mA), w tym prąd wsteczny przez R24 (0 Ω) do wyjścia regulatora SGM2212, którego karta nie opisuje. Gdyby był istotny wobec W23, R24 się usuwa;
- próby na płytkach ewaluacyjnych z [projektu zasilania](../r02/zasilanie.md#próby-teraz-na-płytkach-ewaluacyjnych): do 2026-11-09 nie odbyły się (w repozytorium nie ma ich wyników). Zostaje tylko płytka testowa przetwornicy (wyżej). Próby łącznika LM74800 (LM74800EVM-CD), sterownika wyłącznika (DC1836A-B), toru ogniw i kondensatora szyny zastępuje prototyp v2 (niżej), bo ma te układy w docelowym połączeniu. Szyna 5 V panelu jest z v1.1 i działa na L0. Zatrzask UV z TPS3701 i LTC4368 do v2 nie weszły.

## Na pierwszych sztukach v2

Prototyp v2 w 2 sztukach, jak L0, przed zamówieniem serii pilotażowej. Poniższych punktów nie da się sprawdzić bez zmontowanego toru zasilania v2 (LM74800, D7, sterownik wyłącznika, dzielniki). Wynik każdego punktu decyduje o zapisanej przy nim poprawce przed zamówieniem serii.
- **C50 (kondensator szyny VSYS):** wartość i część po próbie 20 przełączeń 12 V ↔ ogniwa bez restartu ([T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby)). Płytka testowa przetwornicy nie ma toru 12 V ani diody ogniw, więc próba wymaga v2. Na prototyp 100 µF 25 V; gdyby moduł się restartował, większa pojemność albo dłuższy czas startu przetwornicy z ogniw. Większa pojemność wymaga przeliczenia C32 i upływu: C32 27 nF jest dobrany na około 120 µF na VSYS przy prądzie włączania około 250 mA, więc 1000 µF dałoby około 2 A wbrew „narastanie ≤1 A” ([BOM stacji](../../docs/spec/bom-stacji.csv), [elektronika](../../docs/spec/elektronika.md#zasilanie-stacji)), a większy elektrolit ma większy upływ w stanie wyłączonym;
- **napięcie EN/UVLO przy pracy z ogniw bez 12 V** (upływ U5 z C do A): wejście 12 V obciążają tylko dzielniki (246 kΩ równolegle z 329 kΩ, około 140 kΩ), więc EN/UVLO dojdzie do 0,3 V dopiero przy kilkunastu µA upływu. Pomiar EN i prądu z ogniw w 25 i 60 °C ([T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby), pobór w stanie wyłączonym i w czuwaniu). Gdyby EN zbliżało się do 0,3 V, dzielnik UV o mniejszej rezystancji (te same progi i ten sam stosunek pomiaru 12 V). Podnosi to pobór z 12 V przy włączonej stacji (dziś około 50 µA w [elektronice](../../docs/spec/elektronika.md#zasilanie-stacji)), więc tę liczbę trzeba wtedy zmienić;
- **prąd w stanie wyłączonym z ogniw:** typowo około 13 µA z R48 (około 4% pojemności ogniw na rok przechowywania); z wartości maksymalnych kart i upływu C50 najgorszy przypadek przekracza 20 µA (cel z projektu zasilania), mieści się w 0,1 mA ze specyfikacji. Pomiar w 25 i 60 °C ([T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby));
- **zasilanie +3V3 od tyłu w stanie czekania bez 3,3 V:** dzielnik 12 V zostaje podłączony (Q4), więc węzeł V_12_DIV (0,0625 × V12) przez D6 i przez R76 i diody ochronne GPIO5 podnosi martwą szynę 3,3 V. Przy 10–11,9 V to około 0,5 V. Przy 24–33 V bez ogniw (OVP) to około 1,3–1,8 V, a wtedy reset przy późniejszym włożeniu ogniw może nie być czysty. Pomiar +3V3 przy 11 i 24 V i 10 startów po włożeniu ogniw w stanie 24 V ([T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby)); gdyby zawiodły, pomiar 12 V dostaje osobny dzielnik z kluczem DIV_EN, jak ogniwa;
- **ujemne napięcie na GPIO4 i GPIO5:** przy odwróconym 12 V albo ogniwach BAV199 (D6, D11) trzyma węzły dzielników na około −0,6…−0,9 V, a R76 i R77 ograniczają prąd do pinu do ≤40 µA. Karta ESP32-S3 podaje VIL od −0,3 V i nie podaje dopuszczalnego prądu wstrzykiwanego. Pomiar napięcia na pinach w obu stanach i sprawdzenie ADC po nich ([T6 „Zasilanie stacji – progi”](../../docs/spec/odbior.md#próby): odwrotna polaryzacja, błąd ADC ≤2%). Gdyby ADC albo piny ucierpiały: dolną diodę BAV199 zastępuje dioda Schottky'ego do masy (około −0,25 V przy 40 µA), ale tylko o małym upływie, ≤0,2 µA przy 2 V w 60 °C według karty; na węźle 12 V (około 14 kΩ) to ≤3 mV na pinie, około 45 mV na pomiarze 12 V, a zwykły BAT54 (karta onsemi, rys. 3; maksimum ≤2 µA tylko w 25 °C) ma w 60 °C typowo około 0,7 µA, a w najgorszym przypadku kilka do kilkunastu µA (szacunek, bez wartości maksymalnej na gorąco). Typowe 0,7 µA daje na węźle 12 V około 10 mV na pinie, czyli około 0,16 V (1,3%) na pomiarze 12 V; już 2 µA to około 0,46 V (3,8%), a kilkanaście µA kilka V, więc BAT54 nie mieści się w błędzie ADC ≤2%. Wariant zapasowy: R76 i R77 47 kΩ ograniczają prąd do pinu do około 9 µA (napięcie pinu dalej ustala jego dioda ochronna), błąd od 50 nA rośnie do około 3 mV na pinie (około 50 mV na 12 V), a filtr 47 kΩ × 100 nF ma 4,7 ms, więc pomiar ogniw po DIV_EN co najmniej 30 ms;
- **KILL przy słabych ogniwach i w 60 °C:** przy łącznym upływie około 5,8 µA (R48 470 kΩ, VCTL 3,6 V) KILL spada do 0,84 V i stacja się wyłącza. Q11 (BSS138LT1G) ma w 60 °C około 1 µA (szacunek z wartości 25 °C i 150 °C), a upływu Zenera D16 przy 3,6 V żadna karta nie podaje. Pomiar KILL na ciepło przy VCTL 3,6 V; gdyby wypadł słabo, R48 330 kΩ (granica około 8,3 µA, 40% więcej prądu R48);
- **RUN przetwornicy w stanie wyłączonym w 60 °C:** z R78 i R51 220 kΩ upływ Q8, Q10 i Q9 nie powinien podnieść RUN ponad około 0,3 V (Q9 do około 1,2 µA na R55 220 kΩ, szacunek). Pomiar RUN i prądu z ogniw w stanie wyłączonym na ciepło ([T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby)); gdyby RUN zbliżał się do progu, R55 100 kΩ;
- **upływ D7 do ogniw na ciepło:** szacunek dla najgorszej sztuki mieści się w 2 µA z karty L91 do około 50 °C (1,2 µA w 45 °C), typowo do 60 °C. Pomiar prądu w gałęzi ogniw przy 12 V w 45 i 60 °C na obu sztukach ([T6 „Zasilanie stacji – progi”](../../docs/spec/odbior.md#próby) i [T6 „Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby): ≤1 µA); gdyby w 45 °C przekroczył 1 µA, wraca wybór diody;
- **spadek D13 i próg ON:** próg samoczynnego włączenia to 0,76–0,84 V wejścia ON przez dzielnik R70/R71 plus spadek BAS116H przy około 27 µA, szacunkowo 8,2–9,6 V. Pomiar zbocza włączenia na obu sztukach ([T6 „Zasilanie stacji – progi”](../../docs/spec/odbior.md#próby): nie poniżej 8,0 V, najpóźniej przy 9,8 V). Gdyby wypadło poza pasmo, zmienia się R70 (wartość E96 wyliczona z pomiaru spadku D13; musi być w LCSC w tolerancji 0,1%, jak dziś RT0805BRD07280KL);
- **ujemny impuls przy 16 V** ([T6 „Zasilanie stacji – progi”](../../docs/spec/odbior.md#próby)): granica OUT, C i VSNS LM74800 (SNOSD95C 7.1: ≤70 V + V(A), czyli 16,7 V przy V(A) = −53,3 V) jest spełniona w całym zakresie pracy do 16 V, także w próbie T6 z ujemnym impulsem przy 16 V. Przekracza ją o najwyżej 0,6 V tylko wejście 16–17,3 V, tuż pod progiem OVP. Taniej poprawki nie ma: próg OVP ma tolerancję ±2,9% (16,32–17,30 V), więc nie zmieści się w paśmie 16,0–16,7 V, a TVS jednokierunkowy zamiast SMBJ33CA przewodziłby przy odwróconym 33 V i przepaliłby bezpiecznik, czego T6 zabrania. Zostaje jako znane ograniczenie. Gdyby próba przy 16 V uszkodziła LM74800, wraca projekt ochrony wejścia 12 V.

Odrzucone: osobne stanowisko do pomiarów pojedynczych części (µA, podgrzewanie), bo daje wynik kilku sztuk, a nie najgorszy przypadek z kart, i kosztuje więcej, niż daje; części mierzy się na prototypach v2.

## Źródła

- TI LM7480-Q1 (SNOSD95C): tabela 6-1 (wyprowadzenia DRR), 7.5 (prądy, progi EN/UVLO i OV), 9.3.2–9.4 (ograniczenie prądu włączania, wyłączenie, dioda podłożowa).
- ADI LTC2955 rew. A: s. 3 (wyprowadzenia TS8), opis pinów (EN̄ podciągany do VIN przez 900 kΩ, VIN >20 V przez 1 kΩ, TMR 5,2 s/µF).
- ADI LTC3115-1 rew. C: opis pinów FE20, prąd histerezy RUN 500 nA i filtr RUN 1000 pF.
- AOS AO4292E rew. 1.1 (2023): VDS 100 V, VGS ±20 V, VGS(th) 1,6–2,7 V, RDS(on) ≤23/33 mΩ (10/4,5 V), Ciss 1,2 nF; AO4264E rew. 1.1 dla porównania.
- Energizer L91 (karta EBC-8915AP-D9X): „Max Rev Current: 2 uA”, praca −40…+60 °C; nowsza karta L91GL0618 i podręcznik Li/FeS2 (12004-A) nie podają liczby, tylko zakaz ładowania.
- ROHM RB168MM-40 (2022, rew. 003): VF ≤0,65 V przy 1 A, IR ≤0,55 µA przy 40 V (25 °C), wykresy VF–IF i VR–IR, IFSM 40 A; RB168MM-60 ma IR do 1,5 µA, więc nie jest lepsza.
- Littelfuse, zaciski 5x20 mm do druku, seria 111 501 (rozstaw 17,8 mm, otwory 1,17 mm, do 10 A).
- Wio SX1262 for XIAO: schemat Seeed „Wio-SX1262 for XIAO V1.0” ([files.seeedstudio.com](https://files.seeedstudio.com/products/SenseCAP/Wio_SX1262/Schematic_Diagram_Wio-SX1262_for_XIAO.pdf)): J1 1 DIO1, 2 BUSY, 3 RST, 4 NSS, 5 RF_SW1, 6 i 7 niepodłączone; J2 1 VIN, 2 GND, 3 3V3, 4 MOSI, 5 MISO, 6 SCK, 7 niepodłączony. Model STEP Seeed (2024-09-23): rzędy 15,24 mm, otwór Ø 2,2 mm na osi 0,84 mm od skrajnego rzędu. Zgodne z [zleceniem L0](../l0-diagnostic/ZLECENIE.md#połączenia-wio).
- Diodes 2N7002 (DS11303 rew. 40-2), Nexperia 2N7002 (rew. 7, 2011), onsemi BSS138LT1/D (rew. 8, 2013, kopia LCSC; IDSS ≤0,1 µA przy 25 V i ≤0,5 µA przy 50 V w 25 °C, ≤5 µA w 150 °C, próg bramki 0,5–1,5 V przy 1 mA). onsemi BSS138LT1/D rew. 15 (wrzesień 2026, przeczytana przy przeglądzie): próg bramki 0,85–1,5 V przy 1 mA, IDSS jak w rew. 8. Minimum progu decyduje o zapasie Q5 i Q10 przy wyłączonej stacji, więc rachunek zostaje z niższym 0,5 V z rew. 8 jako zapasem.
- Nexperia BSS84AK (rew. 1, 2011): IDSS ≤1 µA w 25 °C i ≤2 µA w 150 °C przy −50 V, próg −1,1…−2,1 V przy −250 µA.
- Hongjiacheng (R+O) SMBJ33CA (kopia LCSC) i Littelfuse SMBJ33CA: VRWM 33 V, VBR 36,7–40,6 V, VC 53,3 V przy 11,26/11,3 A; IR ≤5 i ≤1 µA przy 33 V.
- Nexperia BAV199 (wydanie 1 września 2020, kopia LCSC): piny, VR 75 V ciągle, VRRM 85 V, IR ≤5/80 nA (25/150 °C), VF ≤0,9 V przy 1 mA; BAS116H (rew. 3, 2011): rys. 1 VF–IF, rys. 3 IR–T. onsemi BAT54H: rys. 2 VF przy 0,1 mA.
- Espressif ESP32-S3 Datasheet v2.2: tabela 5-1 (bez granic dla pinów I/O), VIL od −0,3 V.
- TI LM7480-Q1 SNOSD95C 7.5: HGATE źródło 39–75 µA, ściąganie ≥168 mA (warunek V(OV) > V(OVR)), napęd 10–14,5 V; 9.3.2.2 R1 w szeregu z C_dVdT.
- E-Switch PV6 (8.28.2025): bez podświetlenia (s. 5) gwint M16 × 1 13,0 mm, korpus 14,0 mm, końcówki 17,5 ± 0,5 mm w rozstawie 9,4 mm; z podświetleniem (s. 2) 16,5 i 20,0 mm; głowica Ø18 × 1,5 mm, otwór 16 mm, panel 1–10 mm, IP65, −40…85 °C ([configured-product-images.s3.amazonaws.com](https://configured-product-images.s3.amazonaws.com/Datasheets/PV6.pdf)).
- E-Switch 100SP1T8B13M1QEH, rysunek ST111027 rew. D: tuleja 15/32-32 UNS-2A, 11,38 mm, dźwignia 18,00 mm, korpus 12,70 × 6,86 mm i 8,89 mm głębokości, końcówki 4,70 mm, otwór w panelu Ø11,91 mm z noskiem 1,65 × 0,79 mm, położenie 1 zwiera 2–3, −40…85 °C ([configured-product-images.s3.amazonaws.com](https://configured-product-images.s3.amazonaws.com/2D/specs/100SP1T8B13M1QEH.pdf)); katalog serii 100: opcja tulei B4 bez gwintu.
- CW Industries GT-4X (GT-4R): płytka 40,5 × 17 × 0,8 mm, otwór Ø12,2 mm 27 mm od końca z zawiasem, klapka 16,2 mm szeroka i 27,65 mm wysoka zamknięta, na przełączniki z tuleją 12 mm (15/32") i dźwignią 17,5 mm.
- TI TPD4E1U06 (SLVSBQ9D, 2017): DCK (SC-70-6) 1 D1+, 2 GND, 3 D2+, 4 D2−, 5 NC, 6 D1−; VRWM 5,5 V, upływ ≤10 nA przy 2,5 V. TECH PUBLIC TPD4E1U06DCKR (karta z LCSC C2987062): SOT-363, 6 D1−, 5 NC, 4 D2−, 2 GND, 3 D2+, pin 1 opisany „D2−” (D1+ według schematu); VRWM 5,5 V, VBR ≥6,5 V, upływ ≤10 nA przy 2,5 V, IEC 61000-4-2 ±15 kV. TI TPD1E10B09 (2023): DPY, dwukierunkowa, VRWM ±9 V, upływ ≤100 nA przy 5 V. ADI LTC2955 rew. A: PB z podciągnięciem 900 kΩ, napięcie otwartego wejścia 3,0–5,5 V, próg 0,6–1,0 V, zakres ±36 V, ±25 kV HBM.
- Hammond BH4AAW (rysunek): 61,25 × 57 × 14,57 mm, długość wewnętrzna 53,11 mm, podkładka klejąca od spodu.

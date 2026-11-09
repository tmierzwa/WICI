# WICI R02: obudowa i panel stacji

**Materiał do projektu płytki v2 i do wydania (porządek 2026-10-29, F119).** Płytki R02 nie projektuje się przed pilotażem: stacja pilotażowa ma płytkę v2 ([elektronika](../../docs/spec/elektronika.md#stacja-pilotażowa)), a o płytce wyrobu rozstrzyga krok 8 planu ([koncepcja 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)). Plik jest materiałem do obudowy stacji pilotażowej i wydania: wybór skrzynki, panel, okno ekranu i układ panelu przejmuje [obudowa](../obudowa/README.md) (`zalozenia.py`). Obrys płyty bazowej i odniesienia do toru RF dotyczą archiwalnej płytki R02.

**Status: 2026-10-08, propozycja przed przymiarką. Nie zamawiać.** Dokument wybiera obudowę i części panelu oraz wyznacza z nich obrys płyty bazowej i ograniczenia dla layoutu. Nie zależy od prób T3–T5. Ekran (D15) przyjęto jak na N1: Sharp LS027B7DH01A (62,8 × 42,82 × 1,64 mm, pole aktywne 58,8 × 35,28 mm). Zamiennik o innym obrysie zmienia tylko okno i strefę pod ekranem.

Wymagania: [elektronika](../../docs/archiwum/elektronika-r02.md#płytka-stacji-r02-wymagania) (obudowa IP40 bez wentylacji, ≤1 kg z ogniwami, powłoka ochronna, odporność ESD) i [BOM stacji](../../docs/spec/bom-stacji.csv) (przyciski, koszyk, złącza). Sposób użycia: [karta obsługi](../../docs/obsluga/karta-stacji.html). Gospodarz sam wkłada ogniwa, więc dostęp do ogniw nie wymaga otwierania obudowy głównej. Ceny i stany magazynowe sprawdzono 2026-10-08 w DigiKey i TME. Pozycje oznaczone „do sprawdzenia” nie mają jeszcze potwierdzenia z karty producenta albo stanu magazynowego.

## Obudowa

| | **Hammond 1599KBAT** (propozycja) | Bopla BOS 801 | OKW DATEC-CONTROL L (A9079207) |
|---|---|---|---|
| Kształt | płaska skrzynka z wgłębieniem we froncie na folię panelu; z tyłu pokrywa z klapką ogniw i otworami do zawieszenia na ścianie | ręczna, jeden koniec ścięty | ręczna, z głowicą ekranu |
| Wymiary zewnętrzne | 220 × 140 × 40 mm | 196 × 100 × 40 mm | 266 × 90/144 × 60 mm |
| Wnętrze | 213,6 × 133,6 × 33 mm | około 180 × 82 mm użytkowe | według rysunku OKW |
| Front | wgłębienie 206,25 × 126,5 × 1,0 mm na folię | okno 61,5 × 25 mm, za niskie dla pola aktywnego 35,3 mm | wgłębienie ekranu 66 × 99 mm |
| Ogniwa | 4 × AA w koszyku Hammond BH4AAW za klapką w pokrywie | wbudowana komora 4 × AA z klapką | komora 4 × AA (A9178128) z klapką |
| Materiał | ABS, UL94 V-0 | ABS, UL94 do sprawdzenia | ABS, UL94 HB |
| Masa pustej | około 300 g | około 205 g | brak w danych |
| Dostępność | DigiKey: 2 sztuki w magazynie i 448 w fabryce (4 tygodnie), 21,52 USD; koszyk BH4AAW 5,97 USD | TME, stan niepewny, około 28–31 USD | brak w DigiKey i TME; tylko na zapytanie |

**Propozycja: Hammond 1599KBAT.**
- Front 206 × 126 mm mieści ekran, cztery przyciski dla dłoni w rękawicach w rozstawie 32 mm, osłoniętą CISZĘ i wyłącznik główny.
- Tworzywo ma klasę palności V-0, a części są u dystrybutorów.
- Masa z ogniwami litowymi (około 60 g), płytką, ekranem, przyciskami i złączami wynosi około 0,5–0,65 kg, czyli poniżej celu 1 kg.

Bopla BOS 801 przy szerokości 100 mm nie mieści czterech przycisków dla dłoni w rękawicach, a jej okno jest za niskie. OKW ma tworzywo HB, kształt ręczny i nie ma jej u dystrybutorów. Jeśli Hammond odpadnie przy przymiarce, zostaje dowolna obudowa V-0 do zawieszenia na ścianie z wciskaną komorą ogniw Bopla BE 60 (4 × AA, IP40; DigiKey 17 sztuk, 13,81 USD). Takachi LD-4 odpada, bo pracuje tylko do −10 °C.

**Nazwy stron (jak u Hammonda):** **skrzynka** („1599K Box”) ma front ze wgłębieniem na folię i ściany, a **pokrywa** („1599KBAT Lid”) to tył z klapką ogniw. Pokrywę przykręca się od tyłu czterema śrubami M3 × 12 z łbem stożkowym w mosiężne wkładki w słupkach skrzynki, więc front zostaje gładki. W tym pliku „front” to zewnętrzna strona dna skrzynki, z panelem.

**Koszyk i płytka (model STEP, 2026-11-09):** koszyk ogniw (14,57 mm wysokości) leży na klapce pokrywy, pod płytką. Płytka v2 na słupkach skrzynki z tulejkami 6 mm leży 10,5 mm za wewnętrzną powierzchnią frontu, a wierzch koszyka jest 6,3 mm pod jej spodem (4,8 mm, jeśli koszyk oprze się na obrzeżu klapki). Nad koszykiem spód płytki ma tylko końcówki wyprowadzeń THT. Pokrywę zakłada się klapką po lewej, patrząc od frontu; obrócona o 180° stawia koszyk pod modułem radia ([płytka v2, montaż](../plytka-v2/README.md#montaż-w-obudowie)). Do potwierdzenia na przymiarce.

## Elementy panelu

| Funkcja | Kandydat 1 | Kandydat 2 | Uwagi |
|---|---|---|---|
| GÓRA, DÓŁ, OK, WSTECZ | E-Switch PV6F240SS (płaski, stal nierdzewna, bez podświetlenia, SPST-NO, końcówki lutowane): otwór Ø16 mm, 1 000 000 cykli mechanicznych, IP65, −40…85 °C; DigiKey PL 2026-11-09: 718 sztuk, 43,07 zł przy 10 sztukach (TME: brak, 19 tygodni). Wersja z końcówką -341 ma niebieski pierścień i nie pasuje | APEM AV091003C900: otwór Ø19,2 mm, IP65; DigiKey 439 sztuk, 51,30 USD | metalowe przyciski montowane w panelu, równo z folią, połączone z płytką wiązką z wtykiem JST XH (J10 płytki v2); ESD i filtr RC przy wejściu na płytkę. Przyciski lutowane na płytce (B3F z nasadkami, Multimec 5G) odrzucono: wiążą wysokość płytki z frontem z dokładnością ±0,3 mm, a nasadka B32-1310 w otworze Ø16 trze narożnikami o ściankę ([płytka v2, front w wariancie 2](../plytka-v2/README.md#front-w-wariancie-2-2026-11-09)) |
| CISZA z osłoną | przełącznik dźwigniowy E-Switch 100SP1T8B13M1QEH (SPDT ON-ON, gwintowana tuleja 15/32-32 długości 11,38 mm, dźwignia 18 mm, końcówki lutowane, uszczelnienie epoksydowe, −40…85 °C; DigiKey PL 2026-11-09: 2267 sztuk, 20,24 zł przy 10 sztukach) z klapką CW Industries GT-4R (otwór Ø12,2 mm, zawias u góry) | Bulgin 3900 (otwór Ø12,2 mm, IP67) z osłoną TG1-RED; DigiKey 773 sztuki, 18,30 USD | położenie przełącznika jest stanem CISZY, odczytywanym przy starcie; zamknięta klapka ma 27,65 mm nad panelem, a otwarta 43 mm, więc najbliższy przycisk stoi ≥20 mm dalej. GT-4R pasuje tylko na tuleję 15/32" (12 mm); dawny przełącznik na płytce (100SP1T1B4M2QE) miał tuleję bez gwintu. Dźwignia 18 mm przy 17,5 mm w opisie osłony: do przymiarki |
| Wyłącznik główny | E-Switch PV6F240SS, jak przyciski nawigacji | AV | w kolumnie z boku, w linii rzędu nawigacji, ≥30 mm od niego; głowica wystaje 1,5 mm nad folię jak w przyciskach (zagłębienie w folii 0,2 mm jest niewykonalne). Przed przypadkowym wyłączeniem chroni przytrzymanie 2 s i napis „WYŁĄCZ: TRZYMAJ 2 s” o wysokości ≥3,2 mm |
| Przycisk przygotowania | przycisk SMD na płytce (np. E-Switch TL1105 albo C&K PTS645, do sprawdzenia) | inny producent | naciska się go rysikiem przez otwór Ø3–4 mm pod numerowaną naklejką serwisową; przy otworze montażowym płytki, żeby się nie uginała; w promieniu 10 mm żadnych ścieżek ani padów widocznych przez otwór |
| Naklejka serwisowa | numerowana naklejka VOID około 22 × 12 mm na otworze przycisku przygotowania, co najmniej 3 mm kleju wokół otworu | pokrywa około 25 × 20 mm na śrubie plombowej z plombą ołowianą (do oceny przy wydaniu) | przyjęte dla pilotażu ([F113](../../docs/review.md)): naklejka tylko ujawnia wejście, a każde wejście zapisuje stacja ([tryb przygotowania](../../docs/spec/oprogramowanie.md#tryb-przygotowania-i-naklejka-serwisowa)) |
| Dioda alarmu | dioda 5 mm na płytce, osadzona kołnierzem, świeci przez otwór Ø5,5 mm we froncie (płytka v2: Kingbright WP7113ID, 0,95 mm pod frontem) | dioda panelowa Ø5 mm | widoczna z drugiego końca pomieszczenia; napis ALARM pod diodą i kratką, nad zawiasem osłony CISZY |
| Brzęczyk | na płytce, za kratką siedmiu otworów Ø1,5 mm we froncie obok diody (środek (191,5; 20), rozstaw 3 mm) | | ≥20 mm od toru RF; na płytce v2 otwór dźwiękowy 1,4 mm od środka kratki |

## Złącza

| Funkcja | Kandydat 1 | Kandydat 2 | Uwagi |
|---|---|---|---|
| 12 V, IP67, kluczowane | Switchcraft EN3, 2 styki (EN3P2FX: DigiKey 419 sztuk, 12,34 USD; EN3P2F16X: 1636 sztuk, 13,01 USD) | gniazdo M8 albo M12 kodowane A (Binder, Amphenol LTW, Lumberg; do sprawdzenia) | EN3 ma szczelność IP68 tylko z wtykiem albo zatyczką; otwór Ø15,5 mm ze ścięciem 14,8 mm. Wtyk EN3C2M i zatyczka z tej samej rodziny. Styk 1 = +12 V, zapisany w BOM i na karcie |
| Antena SMA-F | gniazdo krawędziowe na płytce, przechodzące przez otwór w ścianie, z nakrętką na ścianie | gniazdo przepustowe SMA z krótkim przewodem do płytki | wybór zależy od toru RF i stosu ([tor RF](tor-rf.md)); nakrętka na ścianie przejmuje moment od przewodu antenowego, który inaczej obciążałby lutowanie. Konkretne MPN do sprawdzenia |
| USB-C | gniazdo USB 2.0 z nogami obudowy przewlekanymi (np. GCT USB4105-GF-A; do sprawdzenia) | Würth albo Amphenol ICC (do sprawdzenia) | zatyczka silikonowa na uwięzi; gniazdo ≤1 mm za otworem w ścianie, żeby wszedł wtyk z typową osłoną |
| Koszyk 4 × AA | Hammond BH4AAW (61,25 × 57 × 14,6 mm, przewody) | Keystone albo MPD 4 × AA z osłoniętym stykiem dodatnim (do sprawdzenia) | zwykłe koszyki nie mają klucza mechanicznego. Wymaganie BOM „kluczowanie przeciw odwrotnemu włożeniu” spełnia osłonięty styk dodatni, a resztę ochrona elektroniczna w torze ogniw ([zasilanie](zasilanie.md)). Odwrócenie jednego ogniwa z czterech daje 3 V zamiast 6 V, nie odwrotną polaryzację. Zakres temperatur koszyka sprawdza się do −20 °C |

## Okno ekranu i podświetlenie

Panel Sharp jest odblaskowy i nie ma podświetlenia od tyłu, więc wymagane podświetlenie krawędziowe leży przed panelem. Od frontu warstwy są takie:
1. folia panelu z poliestru 0,175–0,25 mm, matowa, z nadrukiem PL, UK i EN, wypełniająca wgłębienie frontu;
2. wycięcie we froncie około 61,5 × 38 mm, czyli pole aktywne z marginesem ≥1 mm;
3. szybka z poliwęglanu albo PMMA 1–1,5 mm, przyklejona od środka; to ona przenosi nacisk, nie szkło panelu;
4. płytka światłowodowa 0,5–1 mm z 2–4 diodami na dłuższej krawędzi, ukrytymi pod nieprzezroczystym brzegiem folii;
5. panel na ramce z pianki 0,5 mm.

Szybka, światłowód i panel razem mają ≤4 mm, a szczeliny powietrzne ≤0,5 mm, żeby paralaksa i podwójny obraz nie pogorszyły czytelności. Matowa powierzchnia szybki ogranicza odblaski lamp sufitowych. Taśma FPC panelu schodzi do złącza na płytce bez ostrego zagięcia. Zasady zginania są w opisie N1 ([płytka nośna](../dev-bench/plytka-nosna.md)). Gotowych płytek światłowodowych do 2,7-calowego panelu Sharp jeszcze nie znaleziono. Jeśli ich nie będzie, wycina się płytkę z PMMA z nadrukiem punktowym. Podświetlenie zasila sterownik prądowy z szyny 5 V ([zasilanie](zasilanie.md)).

## Układ panelu

Współrzędne w milimetrach od zewnętrznego lewego górnego narożnika frontu Hammond 1599KBAT (220 × 140 mm), patrząc od frontu. X rośnie w prawo, Y w dół. Na ścianie stacja wisi poziomo, a przewody wychodzą dołem.

```text
 0         40          80          120         160         200    220
 +------------------------------------------------------------------+ 0
 | o                                                              o |   o = śruba pokrywy M3
 |   +--- światłowód, diody ---+                    (*) ALARM  ::: brzęczyk
 |   |  OKNO EKRANU 61,5 × 38  |       LOGO        (178,5; 20) (191,5; 20)
 |   |  środek (52, 42)        |    (126; 30,5)                     |
 |   |                         |    nazwa (126, 48)                 |
 |   +-------------------------+                     [CISZA z osłoną]
 |   OK = TAK  WSTECZ = NIE (52, 71)                  (185, 62)      |
 |                                                                  |
 |  [WSTECZ]  [GÓRA]   [DÓŁ]    [OK]                 ((WYŁĄCZNIK))  |
 |  (30, 98)  (62, 98) (94, 98) (126, 98)            (185, 98)      |
 | o                       [NAKLEJKA SERWISOWA (151, 116)]          o |
 +------------------------------------------------------------------+ 140
   dolna ściana: USB-C (x 60), 12 V EN3 (x 110), SMA (x 170)
```

- WSTECZ jest po lewej, OK po prawej, bo na ekranie OK znaczy TAK, a WSTECZ znaczy NIE. GÓRA i DÓŁ leżą obok siebie pod ekranem.
- Rozstaw 32 mm przy otworach Ø16 mm zostawia ≥16 mm między przyciskami dla palców w rękawicach.
- CISZA i wyłącznik główny stoją w osobnej kolumnie, ≥30 mm od rzędu nawigacji, żeby nie nacisnąć ich przypadkiem. Wyłącznik leży w linii rzędu nawigacji.
- Dioda alarmu jest w prawym górnym rogu, a obok niej kratka brzęczyka; wspólny napis ALARM jest pod nimi, nad zawiasem osłony CISZY.
- Front w wariancie 2 wybrał właściciel 2026-11-09 ([płytka v2](../plytka-v2/README.md#front-w-wariancie-2-2026-11-09)).
- SMA można przenieść na górną ścianę, jeśli przewód antenowy przychodzi z góry. Decyduje o tym rysunek instalacji.
- Klapka ogniw jest w pokrywie (z tyłu), więc do wymiany ogniw zdejmuje się stację ze ściany albo odwraca na stole. Zgadza się to z procedurą z karty (wymiana po komunikacie `mozna_wyjac`). Na klapce: piktogram „+ / −” i napis o przytrzymaniu wyłącznika przez 2 s.

## Płyta bazowa: obrys i ograniczenia

Sprawdzone na modelu STEP Hammonda (2026-11-09) przy płytce v2, do potwierdzenia na przymiarce. Szczegóły i odrzucone warianty: [płytka v2, dopasowanie do obudowy](../plytka-v2/README.md#dopasowanie-do-obudowy-2026-11-09).

- **Obrys:** 200 × 120 mm z narożnikami R4 i wycięciami 12 × 12 mm na słupki śrub pokrywy. Płytka zajmuje obszar frontu x 10–210 mm i y 10–130 mm; w jej płaszczyźnie ściany są 6,3 mm dalej (pochylenie ścian: wewnętrzna krawędź 3,7–3,9 mm od zewnętrznej). Płytka tej wielkości opłaca się tylko jako dwuwarstwowa płyta bazowa. To kolejny argument za podziałem na płytę bazową i mały czterowarstwowy moduł MCU+RF ([architektura](architektura.md#podział-na-płytki)).
- **Mocowanie:** do słupków skrzynki, otwory nieplaterowane według [lekcji](lekcje.md#zasady-layoutu), z jednym otworem ≤25 mm od przycisku przygotowania (v2: 15,6 mm). Skrzynka ma osiem słupków Ø4,75 mm, wysokich na 4,5 mm, w siatce x 20/80/140/200 i y 30/110, z otworem Ø2,36 mm na 4,6 mm głębokości pod wkręt samogwintujący #4; pod otworem front ma 2,9 mm. Słupki (20, 30) i (80, 30) leżą pod oknem ekranu i szlifuje się je na równo z frontem, więc płytka v2 ma sześć otworów Ø3,5 mm. Na każdym słupku tulejka dystansowa 6 mm (otwór 3,2 mm) i wkręt #4 × 7/16" (11,1 mm) z tępym końcem typu B; najdłuższy dopuszczalny wkręt to 12,0 mm pod łbem, bo dłuższy wejdzie we front pod folią. Pokrywa ma słupki w tej samej siatce, ale płytki nie dotykają (16,4 mm pod nią). Uzasadnienie: [płytka v2](../plytka-v2/README.md#dopasowanie-do-obudowy-2026-11-09).
- **Strefa nad koszykiem ogniw:** od spodu elementy ≤3 mm, bez odsłoniętej miedzi i punktów testowych. Przewody koszyka idą do kluczowanego złącza 2-stykowego przy ochronie toru ogniw.
- **Narożniki:** bez miedzi w odległości 2 mm od ściany skrzynki, ze względu na ESD od szczeliny folii.
- **Przyciski panelowe:** wszystkie elementy sterujące są panelowe i przechodzą przez płytkę: pod każdym przyciskiem PV6, wyłącznikiem i przełącznikiem CISZY płytka v2 ma otwór Ø20 mm i 1 mm wolnego pola wokół z obu stron. Korpus PV6 sięga 16,5 mm za folię, a końcówki 18,5 mm, czyli 3,4 mm pod spód płytki; przełącznik CISZY sięga 17,4 mm za wewnętrzną powierzchnię frontu. Przewody idą do złączy JST XH na spodzie (J10 przyciski, J3 wyłącznik, J11 CISZA).
- **Ekran:** strefa 64 × 45 mm pod modułem bez elementów wyższych niż około 1 mm. Złącze FPC po stronie taśmy panelu, diody podświetlenia przy górnej krawędzi okna.
- **Złącza na dolnej krawędzi:** USB-C 0–1 mm od wewnętrznej ściany, na języku płytki. Wysokość osi złącza nad płytką musi się zgadzać ze środkiem otworu w ścianie. Ściana ma tam 3,8 mm, więc otwór 13,2 × 7,2 mm przepuszcza osłonę wtyku (do 12,5 × 6,6 mm). EN3 i SMA są w ścianie i łączą się z płytką przewodami. Tył EN3 (kołnierz Ø20,6 mm, korpus Ø14 mm i kubki lutownicze, razem 13,1 mm za ścianą według biuletynu Switchcraft 602) przechodzi przez płaszczyznę płytki, więc płytka ma pod nim wycięcie. Elementy ESD i TVS leżą ≤10 mm od każdego złącza, przed elementami szeregowymi.
- **Przycisk przygotowania:** (151, 116), w osi otworu pod naklejką serwisową.
- **Powłoka ochronna:** maskuje się złącza, przyciski, złącze FPC, złącze koszyka, pola programowania i strefy otworów montażowych.
- **Ciepło:** stacja traci poniżej 0,5 W, więc wystarczy trzymać przetwornice z dala od ekranu, bo kontrast panelu zależy od temperatury.

## Następne kroki

1. Zrobione 2026-11-09: model STEP Hammond 1599KBAT (słupki, klapka, odstęp płytki od koszyka) i dopasowanie płytki v2 ([płytka v2](../plytka-v2/README.md#dopasowanie-do-obudowy-2026-11-09)).
2. Zamówić próbki do przymiarki 1:1 (krok 5 [kolejności prac](README.md#kolejność-prac)): dwie obudowy, przyciski PV6F240SS, gniazdo EN3 z wtykiem, przełącznik 100SP1T8B13M1QEH z klapką GT-4R, koszyk BH4AAW.
3. Rozstrzygnąć pozycje do sprawdzenia: SMA krawędziowe albo przepustowe, model USB-C, koszyk z osłoniętym stykiem i drugi dostawca złącza 12 V.

## Źródła

- Hammond 1599KBAT, rysunek: https://www.hammfg.com/files/parts/pdf/1599KBKBAT.pdf; seria 1599: https://www.farnell.com/datasheets/2995475.pdf; koszyk BH4AAW: https://www.hammfg.com/files/parts/pdf/BH4AAW.pdf
- Bopla BOS 801: https://www.bopla.de/fileadmin/product_data/Alle_BOS/34801001_BOS-801.pdf; BE 60: https://www.bopla.de/en/enclosure-technology/cable-glands-general-accessories/battery-compartments/battery-compartments-black-plastic-ip-40-din-en-60529/be-60
- OKW DATEC-CONTROL L: https://www.okw.com/en/drawings-pdf/00007906.pdf
- Takachi LD: https://www.takachi-enclosure.com/assets/attachments/images/ld_catalog.pdf
- E-Switch PV6: https://configured-product-images.s3.amazonaws.com/Datasheets/PV6.pdf; APEM AV: https://www.farnell.com/datasheets/1817214.pdf
- E-Switch 100SP1T8B13M1QEH, rysunek ST111027: https://configured-product-images.s3.amazonaws.com/2D/specs/100SP1T8B13M1QEH.pdf
- CW Industries GT-4R: https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/7159/GT-4R.pdf; Bulgin, przełączniki dźwigniowe: https://www.bulgin.com/products/pub/media/bulgin/data/A_Toggle%20Switch.pdf
- Switchcraft EN3, biuletyn 602: https://static.chipdip.ru/lib/314/DOC012314485.pdf

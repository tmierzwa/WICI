# WICI R02: obudowa i panel stacji

**Status: 2026-10-08, propozycja przed przymiarką. Nie zamawiać.** Dokument wybiera obudowę i części panelu oraz wyznacza z nich obrys płyty bazowej i ograniczenia dla layoutu. Nie zależy od prób T3–T5. Ekran (D15) przyjęto jak na N1: Sharp LS027B7DH01A (62,8 × 42,82 × 1,64 mm, pole aktywne 58,8 × 35,28 mm). Zamiennik o innym obrysie zmienia tylko okno i strefę pod ekranem.

Wymagania: [elektronika](../../docs/spec/elektronika.md#płytka-stacji-r02-wymagania) (obudowa IP40 bez wentylacji, ≤1 kg z ogniwami, powłoka ochronna, odporność ESD) i [BOM stacji](../../docs/spec/bom-stacji.csv) (przyciski, koszyk, złącza). Sposób użycia: [karta obsługi](../../docs/spec/karta.md). Opiekun sam wkłada ogniwa, więc dostęp do ogniw nie wymaga otwierania obudowy głównej. Ceny i stany magazynowe sprawdzono 2026-10-08 w DigiKey i TME. Pozycje oznaczone „do sprawdzenia” nie mają jeszcze potwierdzenia z karty producenta albo stanu magazynowego.

## Obudowa

| | **Hammond 1599KBAT** (propozycja) | Bopla BOS 801 | OKW DATEC-CONTROL L (A9079207) |
|---|---|---|---|
| Kształt | płaska skrzynka z wgłębieniem w pokrywie na folię panelu; w podstawie otwory do zawieszenia na ścianie | ręczna, jeden koniec ścięty | ręczna, z głowicą ekranu |
| Wymiary zewnętrzne | 220 × 140 × 40 mm | 196 × 100 × 40 mm | 266 × 90/144 × 60 mm |
| Wnętrze | 213,6 × 133,6 × 33 mm | około 180 × 82 mm użytkowe | według rysunku OKW |
| Front | wgłębienie 206,25 × 126,5 × 1,0 mm na folię | okno 61,5 × 25 mm, za niskie dla pola aktywnego 35,3 mm | wgłębienie ekranu 66 × 99 mm |
| Ogniwa | 4 × AA w koszyku Hammond BH4AAW za klapką w podstawie | wbudowana komora 4 × AA z klapką | komora 4 × AA (A9178128) z klapką |
| Materiał | ABS, UL94 V-0 | ABS, UL94 do sprawdzenia | ABS, UL94 HB |
| Masa pustej | około 300 g | około 205 g | brak w danych |
| Dostępność | DigiKey: 2 sztuki w magazynie i 448 w fabryce (4 tygodnie), 21,52 USD; koszyk BH4AAW 5,97 USD | TME, stan niepewny, około 28–31 USD | brak w DigiKey i TME; tylko na zapytanie |

**Propozycja: Hammond 1599KBAT.**
- Front 206 × 126 mm mieści ekran, cztery przyciski dla dłoni w rękawicach w rozstawie 32 mm, osłoniętą CISZĘ i wyłącznik główny.
- Tworzywo ma klasę palności V-0, a części są u dystrybutorów.
- Masa z ogniwami litowymi (około 60 g), płytką, ekranem, przyciskami i złączami wynosi około 0,5–0,65 kg, czyli poniżej celu 1 kg.

Bopla BOS 801 przy szerokości 100 mm nie mieści czterech przycisków dla dłoni w rękawicach, a jej okno jest za niskie. OKW ma tworzywo HB, kształt ręczny i nie ma jej u dystrybutorów. Jeśli Hammond odpadnie przy przymiarce, zostaje dowolna obudowa V-0 do zawieszenia na ścianie z wciskaną komorą ogniw Bopla BE 60 (4 × AA, IP40; DigiKey 17 sztuk, 13,81 USD). Takachi LD-4 odpada, bo pracuje tylko do −10 °C.

**Ryzyko Hammonda:** koszyk ogniw (14,6 mm wysokości) leży w podstawie, pod płytką. Płytka przykręcona do słupków pokrywy około 12 mm za frontem zostawia około 19 mm nad dnem. Nad koszykiem spód płytki może więc mieć tylko elementy niższe niż około 3 mm. Potwierdza się to na modelu STEP Hammonda i na przymiarce.

## Elementy panelu

| Funkcja | Kandydat 1 | Kandydat 2 | Uwagi |
|---|---|---|---|
| GÓRA, DÓŁ, OK, WSTECZ | E-Switch PV6F240SS-341: otwór Ø16 mm, 1 000 000 cykli mechanicznych, IP65; DigiKey 3633 sztuk, 15,60 USD | APEM AV091003C900: otwór Ø19,2 mm, IP65; DigiKey 439 sztuk, 51,30 USD | metalowe przyciski montowane w panelu, połączone z płytką krótką wiązką z kluczowanym wtykiem; ESD i filtr RC przy wejściu na płytkę. Wariant przycisków lutowanych na płytce (APEM Multimec 5G z nasadkami 15 mm) wiąże wysokość płytki z frontem z dokładnością ±0,3 mm i wymaga wczesnej przymiarki |
| CISZA z osłoną | przełącznik dźwigniowy CW Industries GTS z klapką GT-4R; klapka DigiKey 3301 sztuk, 5,72 USD | Bulgin 3900 (otwór Ø12,2 mm, IP67) z osłoną TG1-RED; DigiKey 773 sztuki, 18,30 USD | położenie przełącznika jest stanem CISZY, odczytywanym przy starcie; klapka wystaje 25–35 mm nad panel, więc najbliższy przycisk stoi ≥20 mm dalej. Otwór przełącznika GTS do sprawdzenia |
| Wyłącznik główny | PV6 w innym kolorze albo z symbolem | AV | zagłębiony około 3 mm w pierścieniu folii, ≥30 mm od rzędu nawigacji; wyłączenie i tak wymaga przytrzymania 2 s |
| Przycisk przygotowania | przycisk SMD na płytce (np. E-Switch TL1105 albo C&K PTS645, do sprawdzenia) | inny producent | naciska się go rysikiem przez otwór Ø3–4 mm pod plombowaną pokrywą; przy otworze montażowym płytki, żeby się nie uginała; w promieniu 10 mm żadnych ścieżek ani padów widocznych przez otwór |
| Pokrywa serwisowa | płytka około 25 × 20 mm na jednej śrubie plombowej (łeb z otworem poprzecznym) wkręconej w mosiężną wkładkę | | drut plombowy przez łeb i ucho pokrywy, plomba ołowiana albo plastikowa obrotowa; tańsza odmiana to naklejka VOID na łbie. Pokrywa daje dostęp tylko do otworu przycisku, nie do płytki |
| Dioda alarmu | dioda na płytce ze światłowodem albo dioda panelowa Ø5 mm | | widoczna z drugiego końca pomieszczenia |
| Brzęczyk | na płytce, za otworami w folii albo ścianie | | ≥20 mm od toru RF |

## Złącza

| Funkcja | Kandydat 1 | Kandydat 2 | Uwagi |
|---|---|---|---|
| 12 V, IP67, kluczowane | Switchcraft EN3, 2 styki (EN3P2FX: DigiKey 419 sztuk, 12,34 USD; EN3P2F16X: 1636 sztuk, 13,01 USD) | gniazdo M8 albo M12 kodowane A (Binder, Amphenol LTW, Lumberg; do sprawdzenia) | EN3 ma szczelność IP68 tylko z wtykiem albo zatyczką; otwór Ø15,5 mm ze ścięciem 14,8 mm. Wtyk EN3C2M i zatyczka z tej samej rodziny. Styk 1 = +12 V, zapisany w BOM i na karcie |
| Antena SMA-F | gniazdo krawędziowe na płytce, przechodzące przez otwór w ścianie, z nakrętką na ścianie | gniazdo przepustowe SMA z krótkim przewodem do płytki | wybór zależy od toru RF i stosu ([tor RF](tor-rf.md)); nakrętka na ścianie przejmuje moment od przewodu antenowego, inaczej obciąża lutowanie. Konkretne MPN do sprawdzenia |
| USB-C | gniazdo USB 2.0 z nogami obudowy przewlekanymi (np. GCT USB4105-GF-A; do sprawdzenia) | Würth albo Amphenol ICC (do sprawdzenia) | zatyczka silikonowa na uwięzi; gniazdo ≤1 mm za otworem w ścianie, żeby wszedł wtyk z typową osłoną |
| Koszyk 4 × AA | Hammond BH4AAW (61,25 × 57 × 14,6 mm, przewody) | Keystone albo MPD 4 × AA z osłoniętym stykiem dodatnim (do sprawdzenia) | zwykłe koszyki nie mają klucza mechanicznego. Wymaganie BOM „kluczowanie przeciw odwrotnemu włożeniu” spełnia osłonięty styk dodatni, a resztę ochrona elektroniczna w torze ogniw ([zasilanie](zasilanie.md)). Odwrócenie jednego ogniwa z czterech daje 3 V zamiast 6 V, nie odwrotną polaryzację. Zakres temperatur koszyka sprawdza się do −20 °C |

## Okno ekranu i podświetlenie

Panel Sharp jest odblaskowy i nie ma podświetlenia od tyłu, więc wymagane podświetlenie krawędziowe leży przed panelem. Od frontu warstwy są takie:
1. folia panelu z poliestru 0,175–0,25 mm, matowa, z nadrukiem PL, UK i EN, wypełniająca wgłębienie pokrywy;
2. wycięcie w pokrywie około 61,5 × 38 mm, czyli pole aktywne z marginesem ≥1 mm;
3. szybka z poliwęglanu albo PMMA 1–1,5 mm, przyklejona od środka; to ona przenosi nacisk, nie szkło panelu;
4. płytka światłowodowa 0,5–1 mm z 2–4 diodami na dłuższej krawędzi, ukrytymi pod nieprzezroczystym brzegiem folii;
5. panel na ramce z pianki 0,5 mm.

Szybka, światłowód i panel razem mają ≤4 mm, a szczeliny powietrzne ≤0,5 mm, żeby paralaksa i podwójny obraz nie pogorszyły czytelności. Matowa powierzchnia szybki ogranicza odblaski lamp sufitowych. Taśma FPC panelu schodzi do złącza na płytce bez ostrego zagięcia. Zasady zginania są w opisie N1 ([płytka nośna](../dev-bench/plytka-nosna.md)). Gotowe płytki światłowodowe do 2,7-calowego panelu Sharp trzeba dopiero znaleźć; inaczej wycina się PMMA z nadrukiem punktowym. Podświetlenie zasila sterownik prądowy z szyny 5 V ([zasilanie](zasilanie.md)).

## Układ panelu

Współrzędne w milimetrach od zewnętrznego lewego górnego narożnika pokrywy Hammond 1599KBAT (220 × 140 mm). X rośnie w prawo, Y w dół. Na ścianie stacja wisi poziomo, a przewody wychodzą dołem.

```text
 0         40          80          120         160         200    220
 +------------------------------------------------------------------+ 0
 | o                                                              o |   o = śruba pokrywy M3
 |   +--- światłowód, diody ---+                     (*) ALARM (185, 22)
 |   |  OKNO EKRANU 61,5 × 38  |                                    |
 |   |  środek (52, 42)        |                     [CISZA z osłoną]
 |   |                         |                     (185, 58)      |
 |   +-------------------------+                                    |
 |                                                                  |
 |  [WSTECZ]  [GÓRA]   [DÓŁ]    [OK]                                |
 |  (30, 98)  (62, 98) (94, 98) (126, 98)           ((WYŁĄCZNIK))   |
 |                                                  (185, 100)      |
 | o                                [POKRYWA SERWISOWA (150, 122)] o |
 +------------------------------------------------------------------+ 140
   dolna ściana: USB-C (x 60), 12 V EN3 (x 110), SMA (x 170)
```

- WSTECZ jest po lewej, OK po prawej, bo na ekranie OK znaczy TAK, a WSTECZ znaczy NIE. GÓRA i DÓŁ leżą obok siebie pod ekranem.
- Rozstaw 32 mm przy otworach Ø16 mm zostawia ≥16 mm między przyciskami dla palców w rękawicach.
- CISZA i wyłącznik główny stoją w osobnej kolumnie, ≥30 mm od rzędu nawigacji, żeby nie nacisnąć ich przypadkiem.
- Dioda alarmu jest w prawym górnym rogu.
- SMA można przenieść na górną ścianę, jeśli przewód antenowy przychodzi z góry; decyduje rysunek instalacji.
- Klapka ogniw jest w podstawie, więc do wymiany ogniw zdejmuje się stację ze ściany albo odwraca na stole. To zgadza się z procedurą z karty (wymiana po komunikacie `mozna_wyjac`). Na klapce: piktogram „+ / −” i napis o przytrzymaniu wyłącznika przez 2 s.

## Płyta bazowa: obrys i ograniczenia

Wstępnie, do potwierdzenia na modelu STEP Hammonda:

- **Obrys:** 200 × 120 mm z narożnikami R4 i wycięciami 12 × 12 mm na słupki śrub pokrywy. Płytka zajmuje obszar pokrywy x 10–210 mm i y 10–130 mm. Płytka tej wielkości opłaca się tylko jako dwuwarstwowa płyta bazowa. To kolejny argument za podziałem na płytę bazową i mały czterowarstwowy moduł MCU+RF ([architektura](architektura.md#podział-na-płytki)).
- **Mocowanie:** do słupków pokrywy, 4–6 otworów nieplaterowanych Ø3,2 mm według [lekcji](lekcje.md#zasady-layoutu), z jednym otworem ≤25 mm od przycisku przygotowania. Rozmieszczenie słupków w pokrywie Hammond (siatka 80 mm) bierze się z modelu STEP.
- **Strefa nad koszykiem ogniw:** od spodu elementy ≤3 mm, bez odsłoniętej miedzi i punktów testowych. Przewody koszyka idą do kluczowanego złącza 2-stykowego przy ochronie toru ogniw.
- **Narożniki:** bez miedzi w odległości 2 mm od ściany pokrywy, ze względu na ESD od szczeliny folii.
- **Przyciski panelowe:** strefa Ø20–24 mm wolna od wysokich elementów wokół osi każdego przycisku na pozycjach z rysunku. Wokół wspornika osłony CISZY strefa 30 × 40 mm.
- **Ekran:** strefa 64 × 45 mm pod modułem bez elementów wyższych niż około 1 mm. Złącze FPC po stronie taśmy panelu, diody podświetlenia przy górnej krawędzi okna.
- **Złącza na dolnej krawędzi:** USB-C, EN3 i SMA 0–1 mm od wewnętrznej ściany. Wysokość osi złącza nad płytką musi się zgadzać ze środkiem otworu w ścianie. Elementy ESD i TVS leżą ≤10 mm od każdego złącza, przed elementami szeregowymi.
- **Przycisk przygotowania:** około (150, 122), w osi otworu pod pokrywą serwisową.
- **Powłoka ochronna:** maskuje się złącza, przyciski, złącze FPC, złącze koszyka, pola programowania i strefy otworów montażowych.
- **Ciepło:** stacja traci poniżej 0,5 W, więc wystarczy trzymać przetwornice z dala od ekranu, bo kontrast panelu zależy od temperatury.

## Następne kroki

1. Pobrać model STEP Hammond 1599KBAT i sprawdzić położenie i wysokość słupków pokrywy, otwór klapki ogniw oraz odstęp płytki od koszyka.
2. Zamówić próbki do przymiarki 1:1 (krok 5 [kolejności prac](README.md#kolejność-prac)): dwie obudowy, przyciski PV6, gniazdo EN3 z wtykiem, przełącznik GTS z klapką GT-4R, koszyk BH4AAW.
3. Rozstrzygnąć pozycje do sprawdzenia: SMA krawędziowe albo przepustowe, model USB-C, koszyk z osłoniętym stykiem i drugi dostawca złącza 12 V.

## Źródła

- Hammond 1599KBAT, rysunek: https://www.hammfg.com/files/parts/pdf/1599KBKBAT.pdf; seria 1599: https://www.farnell.com/datasheets/2995475.pdf; koszyk BH4AAW: https://www.hammfg.com/files/parts/pdf/BH4AAW.pdf
- Bopla BOS 801: https://www.bopla.de/fileadmin/product_data/Alle_BOS/34801001_BOS-801.pdf; BE 60: https://www.bopla.de/en/enclosure-technology/cable-glands-general-accessories/battery-compartments/battery-compartments-black-plastic-ip-40-din-en-60529/be-60
- OKW DATEC-CONTROL L: https://www.okw.com/en/drawings-pdf/00007906.pdf
- Takachi LD: https://www.takachi-enclosure.com/assets/attachments/images/ld_catalog.pdf
- E-Switch PV6: https://configured-product-images.s3.amazonaws.com/Datasheets/PV6.pdf; APEM AV: https://www.farnell.com/datasheets/1817214.pdf
- CW Industries GT-4R: https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/7159/GT-4R.pdf; Bulgin, przełączniki dźwigniowe: https://www.bulgin.com/products/pub/media/bulgin/data/A_Toggle%20Switch.pdf
- Switchcraft EN3, biuletyn 602: https://static.chipdip.ru/lib/314/DOC012314485.pdf

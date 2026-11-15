# Wnioski z prób L0 (2026-11-14) dla specyfikacji WICI-Link

Raport dla prac nad normatywną specyfikacją protokołu ([wici-link.md](../../../docs/spec/wici-link.md), [transport.md](../../../docs/spec/transport.md), [odbior.md](../../../docs/spec/odbior.md)). Zbiera tylko to, co z prób przy stole dotyczy tekstu specyfikacji: co potwierdzono na sprzęcie, gdzie zachowanie odbiega od tego, co tekst zakłada, i czego próby nie rozstrzygają. Szczegóły i dowody: [l0-zestaw-2026-11-14.md](l0-zestaw-2026-11-14.md).

Sprzęt: dwa prototypy l0 (stacja schronienia i przekaźnik z FRAM), dwa zestawy XIAO (root i druga stacja albo drugi przekaźnik), podsłuch na RAK4631. Program z `main` `8dd305f2`. Wszystko na jednym stole, plan sieci wymusza skoki.

## 1. Potwierdzone na sprzęcie

- **Dokładnie raz.** W około 200 zgłoszeniach (łańcuchy 2 i 3 skoków, dwie stacje za jednym przekaźnikiem, 6 zaników zasilania przekaźnika w trakcie przekazywania, cisza radiowa przekaźnika, węzeł wrogi przy 10%) żadne zgłoszenie nie zginęło i żadne nie zostało przyjęte dwa razy. Zanik zasilania tuż po HACK, przed przekazaniem dalej: koperta wyszła z FRAM po starcie i doszła.
- **Dług ciszy przetrwa zanik zasilania.** Po każdym starcie przekaźnik odczytał dług z dziennika (1,1–2,9 s) i odczekał go przed nadaniem.
- **HACK na każdym skoku w czasie.** Koniec DATA → koniec HACK: przekaźnik l0 96–108 ms, root XIAO 101–118 ms, stacja l0 w dół 102–117 ms; żaden powyżej 200 ms w żadnej próbie. Odmowy HACK pojawiły się tylko pod węzłem wrogim (kanał zajęty przy CAD), nadawca ponowił.
- **Trzy skoki.** Każda koperta zgłoszenia przeszła A → C → B → root z HACK na każdym skoku.
- **Cisza radiowa.** Przekaźnik w ciszy nie nadał żadnej ramki (DATA, HACK, BEACON) przez 30 min, a przyjmował do kolejki bez HACK.
- **Fałszywe BEACON-y są tanie.** Przy 158 BEACON-ach z błędnymi podpisami od losowych nadawców przekaźnik sprawdzał podpis 8 razy w 30 min.

## 2. Gdzie zachowanie odbiega od założeń tekstu

### 2.1 Pojemność przekaźnika decyduje o W10

Kolejka przekaźnika ma 4 miejsca: każdy sąsiad najwyżej jedno miejsce K1, K2 najwyżej 2, jedno miejsce zarezerwowane dla K1 innych sąsiadów. Gdy ruch płynie naraz w górę (zgłoszenia) i w dół (RECEIVED, PRZECZYTANE, decyzje), przekaźnik odrzuca bez HACK około połowy pierwszych kopii DATA, a nadawcy ponawiają.

| Ruch | Czas |
|---|---|
| 50 zgłoszeń z jednej stacji przez jeden przekaźnik (W10) | 13 min 2 s, przy progu 15 min |
| to samo bez przekaźnika (XIAO, jeden skok, 2026-11-03) | około 5,5 min |
| 50 zgłoszeń z dwóch stacji przez jeden przekaźnik | 10,5 min |
| po ciszy przekaźnika: 30 stacji, 150 zgłoszeń (emulator, sesja programu) | 75–110 min |

Wniosek dla specyfikacji: W10 przy jednym źródle i jednym przekaźniku mieści się z małym zapasem, a przy pełnej sieci za jednym przekaźnikiem warunek nie jest wykazany. Tekst powinien wiązać W10 i pojemność kolejki przekaźnika z liczbą stacji za przekaźnikiem albo podawać ją jako ograniczenie planu sieci. Sesja programu dodała licznik odrzuceń przy pełnej kolejce (PR #216) i rozmiar kolejki rozstrzygnie po danych. Zwiększenie kolejki zmienia mapę FRAM.

### 2.2 Ramka w kolejce wygasa po 30 min, a cisza może trwać dłużej

Przekaźnik trzyma ramkę najwyżej 30 min (`MAX_HOLD_S`). W ciszy trwającej 30 min z trzech kopert przyjętych od stacji dwie wygasły na kilkanaście sekund przed zdjęciem ciszy. Cisza dłuższa niż 30 min zawsze kończy się pustą kolejką. Powrót opiera się wtedy tylko na ponowieniach stacji: po 1, 2 i 5 min, a dalej co 15 min ±20%. W próbie ostatnie z 5 zgłoszeń doszło 10 min po ciszy, a może to być do 18 min.

Wniosek dla specyfikacji: tekst o ciszy przekaźnika powinien mówić, co przekaźnik trzyma i jak długo, oraz jak stacja wraca po ciszy rodzica. Sesja programu przygotowuje przyspieszenie: po HACK bieżącego rodzica w ciągu 10 s, po jego BEACON-ie w ciągu 0–120 s, najwyżej raz na 5 min, bo nagrany BEACON można powtórzyć. To zachowanie protokołu, więc wymaga zapisu w specyfikacji, razem z ograniczeniem częstotliwości.

### 2.3 Root nie może być sąsiadem dynamicznym

Każda stacja musi mieć klucz roota w `priority_keys`, żeby sprawdzać podpis epoki w BEACON-ach (wici-link.md, reguła 1). Dzięki temu stacja, która słyszy roota, uznaje go za dobrego kandydata dynamicznego. Root zna jednak tylko sąsiadów ze swojego planu i takiej stacji nie potwierdzi. Po trzech skokach bez HACK do rodzica z planu stacja przechodzi więc na roota, traci 3 próby i wraca. W próbach dało to od 59 do 157 ramek bez HACK. Poprawka (PR #214): root jest rodzicem tylko z planu, jako rodzic z planu albo zapasowy. Wymaga wpisu w wici-link.md, regule 2.

Pytanie szersze: czy kandydatem dynamicznym może być tylko sąsiad, który ma stację w swoim planie. Kryterium ogólne zamiast wyjątku dla roota.

### 2.4 Droga w dół za pierwszym przekaźnikiem idzie rozsyłaniem

Root zna drogi w dół według planu (`behind`). Przekaźnik zna je tylko do swoich sąsiadów, a ramkę do dalszej stacji rozsyła. W trzech skokach każde RECEIVED dla A szło od B jako rozsyłana DATA (16 rozesłań na 10 zgłoszeń), a C przekazywało je do A. Przy 15 skokach i wielu stacjach każda ramka w dół za pierwszym przekaźnikiem staje się rozsyłaniem. Do sprawdzenia z budżetem rozsyłania i ze sprawdzeniem pełnego zakresu: czy przekaźnik powinien uczyć się dróg w dół (np. z `behind` podanego przez rodzica albo z ruchu w górę).

### 2.5 Kryteria odbioru wymagają liczników, których program nie podaje

Kryterium „Wrogi węzeł” w odbior.md wymaga między innymi:
- ramki z błędnym tagiem pary odrzucone przed kolejką i portem USB, „licznik”;
- udziały K1/K2 i BEACON w oknie godzinnym;
- najwyżej jedno gniazdo K1 na sąsiada;
- RAM i FRAM ±5%.

Program nie wypisuje licznika odrzuceń po tagu pary ani udziałów klas w kolejce przekaźnika, więc próba nie może tego wykazać. Specyfikacja kryteriów powinna wskazywać źródło każdej wielkości (polecenie i pole) albo zmienić je na pomiar z podsłuchu.

## 3. Drobne sprawy w tekstach

- Każda próba ponowienia stacji jest nową kopertą (nowe uszczelnienie): 5 zgłoszeń w ciszy dało 25 różnych kopert. Stanowisko i tak przyjmuje każde zgłoszenie raz. Warto, żeby tekst o ponowieniach mówił to wprost, bo od tego zależą rachunki obciążenia.
- `failed` w `APP` liczy nieudane próby, nie zgłoszenia. Jedno zgłoszenie z kilkoma próbami podnosi go kilka razy. Tekst używający słowa „nieudane” powinien rozróżniać próbę i zgłoszenie.
- Procedura prób oczekiwała wiersza `loratx` przy nadaniu; v3 go nie wypisuje (tylko ramki RNode). Poprawione w procedurze.

## 4. Czego próby nie rozstrzygają

- **Węzeł wrogi przy 50% przez 2 h** (punkt 2 warunku przyjęcia D21): niewykonane. Wykonano tylko wersję przy 10% w eterze po 30 min; oba przebiegi 20/20.
- **Energia** (W23): wymaga płytki v2.
- **Zasięg i warunki terenowe:** wszystko na jednym stole; wszystkie urządzenia słyszały się nawzajem.
- **Pełny zakres protokołu:** najwięcej 3 skoki i 2 stacje schronienia. Zachowania z punktów 2.1, 2.2 i 2.4 rosną z liczbą stacji i skoków; ocena dla 15 skoków i rozsyłań wymaga emulatora.
- **Udział innych systemów w kanale:** podsłuch słyszy tylko ramki w profilu sieci; pomiar zajętości kanału odbiornikiem SDR: [kanal-nesdr-2026-11-14.md](kanal-nesdr-2026-11-14.md).

## 5. Odpowiedź specyfikacji 0.53 i skutek dla planów prób

Specyfikacja 0.53 (WICI-DEC-017) przyjęła z punktów 2.1–2.3: kandydatem dynamicznym jest tylko sąsiad, którego klucz stacja ma jako klucz sąsiada; klucz roota trzymany tylko do podpisu epoki tego nie daje. Przygotowanie ma odrzucać plan, w którym klucze sąsiadów nie są parami. Przyspieszone ponowienie jest regułą protokołu, a jego wartości sprawdzi emulator. O rozmiarze kolejki przekaźnika zdecyduje właściciel po danych z licznika odrzuceń i z emulatora.

Skutek dla planów: program ma jedną listę `priority_keys`, więc reguła par musi wyznaczać rolę klucza roota z planu. Wersja 0.54 (rozdział 6, sprawdzenie całego planu) robi to bez nowego pola. Klucz roota jest kluczem sąsiada tylko u stacji, dla której root jest rodzicem z planu albo zapasowym. U pozostałych stacji służy tylko do sprawdzania podpisu epoki, nie wymaga pary i nie daje kandydata dynamicznego. Stacja rozróżnia to sama z `network`, tak jak przy wyborze rodzica po PR #214. Plany z tych prób przechodzą: A i C mają klucz roota i rodzica B, a root ma klucz B. Każda stacja ma mieć klucz roota z urzędu. Krok 4 procedury w README dostał zdanie, które to wyjaśnia.

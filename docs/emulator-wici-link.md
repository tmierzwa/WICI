# Emulator WICI-Link: wyniki z 2026-11-05

Sprawdzenie czterech rozstrzygnięć o drogach w łańcuchach (WICI-DEC-009) prawdziwym kodem stacji i roota, zanim trafią do firmware. Opis i założenia są w [README emulatora](../tests/native/wici_emulator/README.md).

**Co ten raport dowodzi.** Logikę i obciążenie przy założonym kanale. Nie dowodzi działania radia. Najmocniejsze ograniczenie: straty ramek są niezależne, bez serii, więc w terenie ponowienia wypadną gorzej. Odwrotnie działa brak efektu przechwycenia, który zawyża kolizje. Wartości trzeba przeliczyć po próbie przy stole i krótkim łańcuchu.

## Rozstrzygnięcia wobec wyników

| Rozstrzygnięcie | Wynik | Co dalej |
|---|---|---|
| Przekaźnik uczy się dróg w dół z ruchu w górę | potwierdzone, z kosztem: wolniejsza droga w górę. Gorszy wynik przy łączach zapasowych to [zapętlenie kolejki przekaźnika](#pytanie-c-łącza-zapasowe), nie uczenie | do decyzji: koszt i poprawka kolejki |
| Próby na przemian i ramka rozsyłana zostaje rozsyłana | potwierdzone | bez zmian |
| **Zmiana rodzica po około 30 min** | próg działa fałszywie w zdrowej sieci przy każdym ziarnie, ale [nie pogarsza to RECEIVED](#pytanie-a-próg-zmiany-rodzica); ważniejsza okazała się reguła zerowania licznika | **do decyzji** |
| **Zmiana rodzica jako wyjście z porzucania** | **działa tylko u stacji tuż pod porzucającą**, przy ruchu z dalszych stacji 12 z 50 zgłoszeń po 12 h, obecny kod 9; [próbka przekaźnika](#pytanie-b-próbka-przekaźnika) pomaga przy zwykłym porzucaniu, nie przy selektywnym | **przyjąć jawnie jako ograniczenie albo otworzyć ponownie** |
| Blokada opuszczonego rodzica około 2 h | potwierdzona | bez zmian |
| Budżet rozsyłania około 0,7 s na stację | limit 25% potwierdzony przy stacjach słyszących się wzajemnie; w łańcuchach zbyt ostrożny | do decyzji: czy skalować go inaczej |

Liczby to mediana z 5 ziaren, w nawiasie najmniejsza i największa wartość. Sieć ma 15 skoków, a próba to 50 zgłoszeń po 174 B w 5 min, chyba że napisano inaczej. „Rozstrzygnięcia” to wszystkie cztery razem: nauka dróg, próby na przemian, zmiana po 1800 s, blokada 7200 s, budżet 700 ms na stację.

## Kalibracja

Jedno rozsyłanie w pustym łańcuchu 15 skoków, 1000 prób na wartość. Wzór p¹⁵ nie zna emulatora, więc zgodność sprawdza model kanału i tor rozsyłania.

| Skuteczność skoku | Dotarło | Wzór |
|---|---|---|
| 95% | 46,3% | 46,3% |
| 90% | 19,8% | 20,6% |
| 80% | 3,4% | 3,5% |

Kopia kodu po nałożeniu łatki, z wyłączonymi przełącznikami, daje wynik identyczny co do bajtu z `firmware/src`.

## 1. Pięćdziesiąt zgłoszeń

Łańcuch bez łączy zapasowych. Czasy do przyjęcia na stanowisku i do RECEIVED na stacji, w sekundach.

| Skąd | Skok | Konfiguracja | RECEIVED | Przyjęcie, maks. | RECEIVED, mediana | RECEIVED, maks. | Ramki rozsyłane |
|---|---|---|---|---|---|---|---|
| koniec | 80% | obecny kod | 48/50 | 1545 | 9848 | 37441 | 7609 |
| koniec | 80% | rozstrzygnięcia | 50/50 | 1899 | 5085 | 9922 | 1273 |
| koniec | 90% | obecny kod | 50/50 | 732 | 4286 | 13132 | 2838 |
| koniec | 90% | rozstrzygnięcia | 50/50 | 1079 | 2207 | 4530 | 605 |
| koniec | 95% | obecny kod | 50/50 | 619 | 2751 | 8186 | 1952 |
| koniec | 95% | rozstrzygnięcia | 50/50 | 782 | 1936 | 4203 | 487 |
| cała sieć | 80% | obecny kod | 47/50 | 1013 | 3806 | 40113 | 1682 |
| cała sieć | 80% | rozstrzygnięcia | 50/50 | 1388 | 1128 | 5599 | 346 |
| cała sieć | 90% | obecny kod | 50/50 | 507 | 2791 | 12308 | 801 |
| cała sieć | 90% | rozstrzygnięcia | 50/50 | 760 | 740 | 3979 | 274 |
| cała sieć | 95% | obecny kod | 50/50 | 489 | 1990 | 9008 | 654 |
| cała sieć | 95% | rozstrzygnięcia | 50/50 | 612 | 640 | 3094 | 200 |

Rozstrzygnięcia skracają najdłuższe RECEIVED 2–7 razy i tną rozsyłanie 3–6 razy. **Koszt: zgłoszenie dochodzi na stanowisko 1,2–1,5 raza później**, a kanał jest zajęty 2–3,5 raza dłużej, bo RECEIVED idzie jednoadresowo z HACK na każdym skoku, zamiast rozsyłaniem bez HACK. Przy końcu łańcucha i 90% próg 15 min przyjęcia mieściło 5 z 5 ziaren na obecnym kodzie, a 2 z 5 po rozstrzygnięciach.

Żadna konfiguracja nie daje przy 15 skokach RECEIVED do 30 min, których próba T5 wymaga na referencyjnym A–B–stanowisko: najlepszy wynik to około 52 min. To nie jest wymóg dla 15 skoków, ale trzeba to nazwać przy pełnym zakresie.

**Łącza zapasowe zmieniają obraz.** Przy łączach co dwa skoki o skuteczności 70% obecne rozsyłanie działa dobrze i przewaga nauki znika, a przy końcu łańcucha i 80% nauka jest gorsza: mediana RECEIVED 6412 [2333..7036] wobec 2724 [2290..3796] s, przyjęcie maks. 3654 wobec 1502 s. Rozrzut wskazuje na dwa tryby pracy. Hipotezę o „ostatnia wygrywa” [obalono](#pytanie-c-łącza-zapasowe): przyczyną jest milknący przekaźnik, a jednoliniowa poprawka usuwa ten wynik.

## 2. Zmiana rodzica i poprawa drogi w dół

Łącza zapasowe 70%, przerwa w łączu stacji w połowie łańcucha do jej rodzica z planu, 10 kolejnych zgłoszeń od tej stacji i od końca.

| Skok | Konfiguracja | RECEIVED, maks. (s) | Ramki rozsyłane |
|---|---|---|---|
| 80% | obecny kod | 3515 [708..6289] | 212 |
| 80% | nauka | 2593 [788..2868] | 47 |
| 80% | nauka + na przemian | 636 [445..1654] | 109 |
| 90% | obecny kod | 3372 [2737..5993] | 190 |
| 90% | nauka | 740 [345..4237] | 31 |
| 90% | nauka + na przemian | 336 [327..764] | 86 |
| 95% | obecny kod | 680 [485..3090] | 185 |
| 95% | nauka | 662 [650..710] | 23 |
| 95% | nauka + na przemian | 385 [288..759] | 87 |

Wszystkie 10 zgłoszeń domknięte w każdej konfiguracji. Na obecnym kodzie przekaźniki znają tylko sąsiadów, a po rozstrzygnięciach mają pełną drogę, która omija przerwane łącze. Próby na przemian kosztują 2–4 razy więcej ramek rozsyłanych niż sama nauka i skracają najgorszy przypadek 2–4 razy; **to potwierdza rozstrzygnięcie**.

## 3. Stacja daje HACK i porzuca ruch

Stacja w połowie łańcucha, 90%, łącza zapasowe 70%, 12 h.

| Czyje zgłoszenia | Konfiguracja | RECEIVED | Mediana (s) | Maks. (s) | Zmiany rodzica |
|---|---|---|---|---|---|
| stacja tuż pod nią | obecny kod | 9/50 [6..15] | 22342 | 26701 | 0 |
| stacja tuż pod nią | rozstrzygnięcia | 50/50 | 3740 | 7645 | 1 |
| wszystkie poniżej | obecny kod | 9/50 [6..30] | 13056 | 37237 | 0 |
| wszystkie poniżej | rozstrzygnięcia | 50/50 [47..50] | 3838 | 6699 | 12 |
| **tylko koniec łańcucha** | obecny kod | 9/50 [8..16] | 17661 | 37822 | 0 |
| **tylko koniec łańcucha** | rozstrzygnięcia | **12/50 [0..28]** | 25766 | 37415 | 13 |

Wyjście działa, gdy stacja tuż pod porzucającą ma własną otwartą wiadomość. Bez niej ruch dalszych stacji stoi: rodzica zmienia stacja na końcu łańcucha, której rodzic działa poprawnie, a stacja pod porzucającą nie ma żadnego sygnału. Ograniczenie było znane z analizy („przekaźnik bez własnego ruchu nie ma sygnału”); emulator pokazuje, że przy pełnym zakresie **zostaje jedna awaria odcinająca całą dalszą część łańcucha na godziny**, mimo działającego rodzica zapasowego. Stacje czekają wtedy na alarm i ludzi. Zgłoszenia, które dotarły na obecnym kodzie, dotarły późno i przypuszczalnie po przypadkowych trzech porażkach z rzędu u tej stacji; tego osobno nie sprawdzono.

## 4. Czas 30 min i blokada 2 h wobec opóźnień kolejek

**Sieć bez żadnej awarii**, łącza zapasowe 70%, zgłoszenia z całej sieci, próba na zmianę z budżetem. Każda zmiana rodzica to fałszywy alarm.

| Próg | Skok | Fałszywe zmiany | Stacje poza planem na końcu | RECEIVED, maks. (s) |
|---|---|---|---|---|
| bez zmiany | 90% | 0 | 0 | 3259 |
| **30 min** | 80% | **4 [3..7]** | 5 | 4547 |
| **30 min** | 90% | **3 [1..6]** | 3 | 3649 |
| **30 min** | 95% | **4 [2..5]** | 4 | 3587 |
| 60 min | 80% | 0 [0..1] | 1 | 4932 |
| 60 min | 90%, 95% | 0 [0..0] | 0 | 3259, 3184 |
| 90 min | wszystkie | 0 [0..0] | 0–1 | 4932, 3259, 3184 |

Pod nasyceniem z łączami zapasowymi (90%, 181 zgłoszeń w godzinę): 20 [13..35] zmian przy 30 min, 7 [1..8] przy 60 min, 0 [0..4] przy 90 min.

Przyczyna leży w czasach, które już są w kodzie: stacja po HACK ponawia po 10 min, a potem co 30–60 min (`RESEND_MIN_S`, `RESEND_MAX_S`), a stanowisko po przekazaniu przekaźnikowi czeka 35 min (`CUSTODY_S`). Zdrowa stacja z jednym zgubionym RECEIVED milczy więc dłużej niż 30 min: najdłuższa cisza bez zmiany rodzica to 2834 [2086..3179] s, pod nasyceniem 5276 [3833..9068] s. **Próg 30 min jest krótszy od zwykłego odstępu ponowienia.** Porównanie z innymi progami i poprawką kolejki jest w [drugiej turze](#pytanie-a-próg-zmiany-rodzica). Fałszywa zmiana przy łączach zapasowych 70% kosztuje mało (najdłuższe RECEIVED o około 12% dłużej), przy 90–95%, ale przenosi stację na słabsze łącze na 2 h.

Wyższy próg opóźnia wyjście z prawdziwego porzucania, przy zgłoszeniach od stacji tuż pod porzucającą:

| Próg | Mediana RECEIVED (s) | Maks. (s), najgorsze ziarno |
|---|---|---|
| 30 min | 3740 | 7645, 10957 |
| 60 min | 5368 | 6861, 31214 |
| 90 min | 6529 | 8416, 32743 |

**Blokada.** Zgłoszenia co 12 min przez 10 h od stacji pod porzucającą, próg 30 min:

| Blokada | RECEIVED | Zmiany rodzica | Maks. (s) |
|---|---|---|---|
| bez zmiany rodzica | 7/50 [2..10] | 0 | 22177 |
| 0 | 28/50 [21..46] | 11 | 19662 |
| 30 min | 49/50 [45..49] | 6 | 7991 |
| **2 h** | **49/50 [47..49]** | 3 | 5478 |
| 4 h | 49/50 [24..49] | 2 | 3930 |

Bez blokady stacja wraca do porzucającej przy każdym jej HACK. Rozstrzygnięcie 2 h wytrzymało: dłuższa blokada daje niewiele, a w jednym ziarnie wypada gorzej. Blokada ma jeden koszt widoczny przy powrocie stanowiska (punkt 6).

## 5. Nasycenie i zakleszczenie

Każda stacja zgłasza przez godzinę, potem brak nowych zgłoszeń, razem 9 h. Dwa obciążenia: 181 i 901 zgłoszeń.

| Skok | Zgłoszeń | Konfiguracja | RECEIVED | Najdłuższa przerwa bez HACK (s) |
|---|---|---|---|---|
| 80% | 181 | obecny kod | 67 [53..77] | 443 |
| 80% | 181 | rozstrzygnięcia | 181 | 440 [268..3088] |
| 90% | 181 | obecny kod | 136 [94..163] | 282 |
| 90% | 181 | rozstrzygnięcia | 181 | 398 |
| 95% | 181 | obecny kod | 181 | 1031 [883..2100] |
| 95% | 181 | rozstrzygnięcia | 181 | 18 [18..444] |
| 80–95% | 901 | obecny kod | 160–198 | do 578 |
| 80–95% | 901 | rozstrzygnięcia | 277–336 | do 553 |

**Zakleszczenia nie ma.** Dopóki są otwarte zgłoszenia, sieć robi postęp: w przebiegach z ziarnem 1 przy obciążeniu co najmniej 41 HACK na 10 min, a dłuższe przerwy (do 3088 s) wypadają po opróżnieniu kolejek, gdy czeka się na ponowienie 30–60 min. Przy 901 zgłoszeniach sieć po prostu ma za małą przepustowość: po 9 h stanowisko ma 352–448 przyjęć. Pula 60% czasu kanału odmawia tu tysięcy razy (`budget_refused`), bez blokady węzłów. To nie jest dowód braku zakleszczenia dla każdej topologii; drzewo z rozgałęzieniami sprawdzono w [drugiej turze](#najlepszy-zestaw-w-drzewie).

## 6. Fala BEACON-ów po wyłączeniu stanowiska

Stanowisko wyłączone na 2 h, wszystkie stacje mają otwarte zgłoszenie, potem powrót z nową epoką. 90%.

| Łącza zapasowe | Konfiguracja | BEACON-y w 1. godzinie | W czasie 2 h przerwy | W godzinę po powrocie | Zmiany rodzica | Poza planem na końcu | RECEIVED |
|---|---|---|---|---|---|---|---|
| nie | obecny kod | 68 | 243 | 57 | 0 | 0 | 11/15 |
| nie | rozstrzygnięcia | 68 | 243 | 75 | 0 | 0 | 15/15 |
| tak | obecny kod | 65 | 587 | 76 | 804 | 0 | 15/15 |
| tak | rozstrzygnięcia | 65 | 401 | 79 | 424 | 3 | 15/15 |
| tak | próg 90 min | 65 | 583 | 66 | 691 | 11 | 15/15 |

W najgorszej konfiguracji to średnio około 20 BEACON-ów na stację na godzinę, czyli 0,15% czasu nadawania przy limicie 2% i odstępie co najmniej 60 s. Żaden BEACON nie przepadł przy sprawdzaniu podpisu. **Rozstrzygnięciom to nie przeczy.** Jedna uwaga: stanowisko wyłączone na dłużej niż próg zmienia rodzica wszystkim stacjom z otwartą wiadomością, a po powrocie zdrowi rodzice są zablokowani. Przy progu 90 min 11 z 15 stacji jest po godzinie jeszcze poza planem.

## 7. Budżet rozsyłania

Po jednej wiadomości 50 B do każdej stacji bez znanej drogi i równolegle 10 zgłoszeń. Zajętość kanału to udział czasu z ramką w eterze, średnio w przebiegu; 90%.

| Topologia | Stacje | Budżet | Zajętość kanału | Kolizje | Do wszystkich, mediana / maks. (s) | Przyjęcie zgłoszeń, maks. (s) |
|---|---|---|---|---|---|---|
| słyszą się | 50 | brak | 37,0% | 3918 | 314 / 617 | 62 |
| słyszą się | 50 | 0,7 s | 21,9% | 2499 | 875 / 1576 | 30 |
| słyszą się | 100 | brak | **62,5%** | 78374 | 1130 / 3114 | 106 |
| słyszą się | 100 | 0,7 s | **26,4%** | 36012 | 3220 / 6230 | 45 |
| łańcuchy | 50 | brak | 14,5% | 1472 | 214 / 2599 | 173 |
| łańcuchy | 50 | 0,7 s | 15,2% | 1028 | 919 / 2964 | 88 |
| łańcuchy | 100 | brak | 19,4% | 5753 | 297 / 4979 | 179 |
| łańcuchy | 100 | 0,7 s | 12,6% | 4100 | 3505 / 10226 | 70 |

Dla stacji słyszących się wzajemnie budżet trzyma około 25% i bez niego przy 100 stacjach kanał się dławi: **rozstrzygnięcie potwierdzone**. W łańcuchach, gdzie rozsyłanie zajmuje wiele domen kolizji po kolei, budżet wydłuża medianę 4–12 razy, a poprawia głównie przyjmowanie zgłoszeń. Łączny czas rośnie z kwadratem liczby stacji: 100 wiadomości po 70 s to prawie 2 h, a w 3 z 5 ziaren po 4 h jedna stacja jest nadal bez wiadomości. Dotyczy to tylko stacji bez znanej drogi, więc zwykły RECEIVED rzadko tu trafia, ale rozsyłany masowo komunikat już tak.

## 8. Wrogi węzeł przyciągający drogi

Przejęta stacja obok trzech stacji w połowie łańcucha, z prawdziwymi kluczami. Daje HACK i porzuca. 90%, łącza zapasowe 70%, zgłoszenia od stacji poniżej niej, 8 h.

**Fałszywy `src` koperty** co 30–60 s, cudze numery przez trzech sąsiadów:

| Konfiguracja | RECEIVED | Mediana (s) | Maks. (s) | Drogi przejęte przez napastnika (z 21) |
|---|---|---|---|---|
| obecny kod | 50/50 | 5419 | 9403 | 0 |
| nauka | 50/50 | 6411 | 11775 | 9 [6..9] |
| nauka + na przemian | 50/50 | 5469 | 11355 | 10 [9..11] |
| rozstrzygnięcia | 50/50 | 6095 | 9555 | 9 [7..11] |

Napastnik przejmuje około połowy dróg u swoich sąsiadów, bo przekaźnik nie sprawdzi koperty; tak miało być po wycofaniu reguły „tylko plan”. **Nie odcina jednak ruchu**: prawdziwy ruch w górę od ofiary odkręca drogę, a próba rozsyłaniem omija napastnika. Koszt to najwyżej około 25% czasu.

**Fałszywie niska ranga** przez podpisany BEACON, a stacja obok traci rodzica z planu:

| Konfiguracja | RECEIVED | Maks. (s) | Rodzic stacji na końcu |
|---|---|---|---|
| obecny kod | 47/50 [41..50] | 26949 | napastnik w większości ziaren |
| nauka | 39/50 [38..45] | 28041 | napastnik w większości ziaren |
| nauka + na przemian | 45/50 [35..49] | 27557 | napastnik |
| rozstrzygnięcia | 50/50 | 13058 | zapasowy |

Wyjście po czasie działa także tu. Bez niego napastnik trzyma stację godzinami, a sama nauka dróg w tej próbie pogarsza wynik. Liczy się nadal, że atak trwa około 3,6 h, a nie minuty.

## Druga tura: reakcja na brak postępu i łącza zapasowe

Właściciel zlecił sprawdzenie trzech pytań, zanim zdecyduje. Rekomendacje na końcu tej części to ocena autora raportu, nie rozstrzygnięcie. Firmware jest bez zmian; wszystkie warianty żyją w `variant.patch` i w skrócie stacji emulatora. Razem 1901 przebiegów: parametry dobierano na ziarnach 1–5, sprawdzono na 101–110, a wybranych kandydatów bez dalszego strojenia na 201–210. To miało znaczenie: **ziarna 1–5 pokazały próg 60 min i „2 próby” lepiej, niż wypadły na nowych ziarnach**.

**Wnioski.**

- **Pytanie A.** Próg 60 lub 90 min nie jest lepszy od 30 min, bo ma długi ogon. Różnicę robi reguła zerowania: licznik „2 próby” zerowany tylko odpowiedzią na tę wiadomość wychodzi z porzucania w 3620 [3307..3793] s przy tylu fałszywych zmianach co 30 min, a RECEIVED mieści się przy nich w rozrzucie między ziarnami.
- **Pytanie B.** Próbka przekaźnika podnosi wynik przy zwykłym porzucaniu z około 12 do 50 z 50, ale **węzeł, który przepuszcza próbki i porzuca resztę, unieważnia ją całkowicie**. Wymaga też nowego rodzaju wiadomości i kosztuje około 3,3 razy więcej czasu nadawania przy wyłączonym stanowisku.
- **Pytanie C.** Hipoteza „ostatnia wygrywa” jest **obalona**. Przyczyną jest milknący przekaźnik: ramki z gniazd K1 bez znanej drogi czekają przy limicie 25% na siebie nawzajem do 30 min. Poprawka jednej linii bez zmiany bajtów usuwa dwumodalność i uczenie z ruchu nie jest podważone.

### Pytanie C: łącza zapasowe

Koniec łańcucha, łącza zapasowe 70%, nauka dróg, próby na przemian i budżet. Ziarna 1–5. „Najdłuższa cisza” to najdłuższy czas bez żadnego nadania u jednej stacji w chwili odmowy z dziennika czasu nadawania.

| Skok | Konfiguracja | RECEIVED, mediana (s) | RECEIVED, maks. (s) | Najdłuższa cisza (s) | Odmowy dziennika |
|---|---|---|---|---|---|
| 80% | obecny kod | 2724 [2290..3796] | 6423 | 2 | 55 |
| 80% | bez poprawki | **6412 [2333..7036]** | 8139 | 1363 [197..1776] | 10938 |
| 80% | bez „ostatnia wygrywa” (nauka tylko brakującej drogi) | **5406 [4941..6482]** | 8034 | 1680 [1013..1762] | 8148 |
| 80% | bez dziennika czasu nadawania (tylko próba przyczyny) | 2448 [2252..2817] | 4273 | 0 | 0 |
| 80% | **z poprawką** | **2484 [2398..5419]** | 5887 | 598 [573..1275] | 4109 |
| 90% | obecny kod | 1938 [1796..2630] | 5723 | 2 | 42 |
| 90% | bez poprawki | 2307 [2203..5630] | 6599 | 809 [2..1065] | 3109 |
| 90% | **z poprawką** | **2279 [1950..2356]** | 3280 | 2 | 165 |
| 95% | obecny kod | 2579 [1645..2703] | 4887 | 2 | 28 |
| 95% | bez poprawki | 2244 [1965..4726] | 4671 | 1075 [2..1621] | 3072 |
| 95% | **z poprawką** | **2156 [2003..2190]** | 3777 | 2 | 182 |

**Hipoteza nie wytrzymała.** Bez „ostatnia wygrywa” mediana nadal wynosi 5406 s, a cisza jest nawet dłuższa. Łącza 70% nie są też słabym wyborem: dają dwa skoki jedną ramką, więc skuteczność na skok jest podobna jak przy 80%.

**Co pokazuje zapis przebiegu** (ziarno 2, 80%). Stacja 7 nie nadaje niczego przez około 25 min, od około 2100 s do 3600 s: ani DATA, ani HACK. Jej dziennik stoi na 1151 s z 2160 s puli, więc to nie wyczerpana pula 60%. Licznik odmów tej stacji rośnie w tym czasie z 83 do 1293, u sąsiedniej stacji 8 do 515, a u pozostałych do 3000 s wynosi 0–8. W jej kolejce (widać gniazda 0 i 2) są ramki `ACKREQ|DOWN` z następnym skokiem BROADCAST. Rozkład przyczyny:

1. Przekaźnik bez drogi do stacji zamienia ramkę w dół na rozsyłanie. Po nauce dróg zdarza się to często, bo droga znika po trzech seriach bez HACK (`routes_.forget` w `Relay::timeout`).
2. `Relay::prepare` traktuje taką ramkę jako K2 (`activePriority_ = k1 && next != BROADCAST`), choć leży w gnieździe K1.
3. `contendedK2` widzi w innym gnieździe ramkę K1, więc przy puli powyżej 25% radio odmawia. Druga ramka bez drogi trafia na to samo: czekają na siebie nawzajem.
4. Stacja nie daje też HACK, co pasuje do pełnej kolejki. Ramki wygasają po 30 min. Dzieci ponawiają i zmieniają rodziców, a to dopiero zużywa ich pule do 60%, stąd druga fala ciszy.

Stąd dwa tryby: to, czy w danym ziarnie kolejka zapełni się samymi takimi ramkami przy puli ponad 25%, zależy od przypadku.

**Poprawka bez zmiany bajtów:** ramka z gniazda K1 zachowuje pierwszeństwo K1 także bez znanej drogi (`k1flood=1`). Na ziarnach 101–110 przy 80%: mediana 2445 [2325..5117] s wobec 4773 [2246..5803] s bez poprawki i 2278 [2087..2560] s na obecnym kodzie; najdłużej 6206 s wobec 6889 s na obecnym kodzie. **Uczenie z ruchu nie jest podważone**, ale nie jest też za darmo:

- Zgłoszenie dochodzi później: najdłużej 1605 s wobec 839 s przy 90% i 1175 s wobec 691 s przy 95%, czyli przy łączach zapasowych do 1,9 raza, więcej niż 1,2–1,5 raza z pierwszej tury. Kanał jest zajęty około 1,3–1,8 raza dłużej.
- Przy 80% zostaje jeden prawdziwy limit: w części ziaren pośrednie przekaźniki dochodzą do puli 60% (cisza do 1182 s, mediana do 5117 s). To już obciążenie, nie zapętlenie.

**Koszt i zastrzeżenia poprawki.** Zmienia regułę „rozsyłanie to K2” dla ramek, które przyszły jednoadresowo w gnieździe K1, więc trzeba ją wpisać do specyfikacji i kryterium próby wrogiego węzła. Sprawdzono, czy nie otwiera ataku: sąsiad podsuwający co 10–12 s ramki w dół do numeru bez drogi daje z poprawką medianę 2460 [2294..2629] s i ciszę 599 s, a bez niej 4733 [2270..8867] s i 1234 s. Poprawka tu pomaga, bo sama cisza jest celem ataku. **Mechanizm jest też w obecnym firmware:** ten sam atak na niezmieniony kod daje ciszę do 465 s i medianę 2684 s wobec 1867 s bez napastnika (ziarna 201–210); tego przebiegu nie rozbierano na zapisie. Inny wariant poprawki, w którym `contendedK2` liczy tylko ramki K1 ze znaną drogą, zachowałby regułę o K2, ale go nie sprawdzono.

Liczby z rozdziałów 1–8 policzono bez poprawki. W łańcuchu bez łączy zapasowych prawie nie ma różnicy (koniec łańcucha, 90%: mediana 2178 s wobec 2207 s), a przy łączach zapasowych trzeba czytać ten rozdział.

### Pytanie A: próg zmiany rodzica

Próg w próbach: stacja liczy nadania z HACK bez uwierzytelnionej wiadomości od odbiorcy i **przed następnym nadaniem** zmienia rodzica, więc to nadanie idzie już nową drogą. Przy odstępach 10 min, potem 30–60 min, „2 próby” to 40–70 min od pierwszego HACK, „3 próby” 70–130 min, „4 próby” 100–190 min. Custody stanowiska po przekazaniu to 35 min, więc N=1 (10 min) nie wchodzi w grę. „4 próby” odpadły na ziarnach 1–5 (26/50 przy porzucaniu). Wszystkie warianty z poprawką kolejki, nauką, próbami na przemian, budżetem i blokadą 2 h. Porzucanie: stacja w połowie, 90%, 12 h.

Ziarna 101–110:

| Reguła | Fałszywe zmiany w zdrowej sieci, 80 / 90 / 95% | Pod nasyceniem, 90 / 80% | Porzucanie, stacja pod nią: mediana RECEIVED (s) | RECEIVED tam | RECEIVED, wszystkie poniżej |
|---|---|---|---|---|---|
| 30 min | 4 / 4 / 4 | 7 [0..15] / 34 [26..49] | 3746 [3419..**16493**] | 50 | 50 [45..50] |
| 60 min | 0 / 0 / 0 | 0 [0..7] / 11 [8..12] | 11656 [5290..**40067**] | 50 [**12**..50] | 50 |
| 2 próby, zeruje każda wiadomość | 0 / 0 / 0 | 1 [0..7] / 10 [8..13] | 9702 [3461..**36033**] | 50 [**12**..50] | 50 [44..50] |
| 3 próby, zeruje każda wiadomość | 0 / 0 / 0 | 0 / 5 [0..6] | 9702 [833..**41351**] | 46 [**12**..50] | 47 [4..50] |
| **2 próby, zeruje tylko odpowiedź na tę wiadomość** | 4 / 2 / 3 | 6 [0..12] / 22 [18..28] | **3685 [3317..3996]** | **50** | 50 [45..50] |

Przyczyna ogona, z zapisu ziarna 4: jedno zgłoszenie przypadkiem przechodzi przez rodzica zapasowego, wraca jego RECEIVED i **zeruje liczniki wszystkich pozostałych wiadomości**. Stacja zostaje przy porzucającym rodzicu na godziny. Niski próg 30 min zdąża częściej przed takim przypadkiem, wyższe nie. Dlatego próg 60 min, który na ziarnach 1–5 dawał 5368 s, na nowych daje medianę 11656 s; 90 min (tylko ziarna 1–5) ma 6529 [6257..30006] s i ten sam ogon.

Kandydaci na ziarnach 201–210, bez strojenia:

| Reguła | Fałszywe zmiany w zdrowej sieci, 80 / 90 / 95% | Pod nasyceniem, 90 / 80% | Pierwsza zmiana u stacji pod porzucającą (s) | Mediana RECEIVED (s) | Wszystkie poniżej: RECEIVED, maks. (s) |
|---|---|---|---|---|---|
| 30 min | 4 / 3 / 5 | 9 [0..14] / 35 [27..47] | 1887 [1800..10180] | 3762 [3276..11673] | 50 [44..50], 7374 |
| 2 próby, ta wiadomość | 4 / 3 / 2 | 6 [0..8] / 26 [18..34] | 2567 [2512..2727] | **3620 [3307..3793]** | 50 [44..50], 10136 |
| 3 próby, ta wiadomość | **0 / 0 / 0** | **0 [0..4]** / 13 [11..22] | 4651 [4430..4958] | 6182 [5887..6351] | **36 [31..50]**, 16404 |

**Wpływ na RECEIVED i czas dotarcia mieści się w rozrzucie między ziarnami** i to trzeba skorygować wobec pierwszej tury, która mówiła o wyniku przeczącym 30 min. Fałszywe zmiany są, ale RECEIVED maks. przy 90% to 3601, 3759 i 3662 s, pod nasyceniem 4183, 4939 i 4233 s, przy 80% 14530, 14894 i 16660 s, a przyjęcie zgłoszeń jest identyczne (829 s). Ceną jest 3–5 stacji z 15 na rodzicu zapasowym przez 2 h, co przy założonych 70% prawie nie boli. **Emulator nie widzi, co to znaczy na realnym łączu zapasowym**, które może być znacznie gorsze, ani strat seriami, które wydłużą ciszę i zwiększą liczbę fałszywych zmian, szczególnie przy liczeniu na jedną wiadomość. Bez łącza zapasowego zmiana niczego nie daje: rodzic z planu zostaje jako podłoga.

Przy wyłączonym stanowisku 2 h ruch tylko z końca łańcucha daje poza planem przy powrocie 1, 2 i 2 stacje; wszystkie wiadomości domknięte po 660, 360 i 660 s. Wrogi węzeł z niską rangą: RECEIVED maks. 16940, 9765 i 11008 s; z fałszywym `src`: 10122, 10729 i 10942 s.

### Pytanie B: próbka przekaźnika

Przekaźnik, który przekazał ruch w górę i przez 20 min nie widział powrotu, wysyła własną uwierzytelnioną wiadomość najwyżej co 30 min i dalej działa jak stacja z otwartą wiadomością, z progiem „2 próby”. Dwa warianty sygnału: każda ramka w dół albo tylko uwierzytelniona wiadomość do tej stacji. Porzucanie przy ruchu **tylko z końca łańcucha**, 90%, 12 h, ziarna 1–5, licznik zerowany każdą wiadomością.

| Co robi porzucający | Gdzie | Bez próbki | Próbka, powrót to ramka w dół | Próbka, powrót to własna wiadomość |
|---|---|---|---|---|
| porzuca wszystko | blisko roota | 17 [7..26] | **50** (mediana 6411 s, 15 zmian) | 50 (6590 s, 21 zmian) |
| porzuca wszystko | w środku | 9 [5..13] | **50** (6324 s, 7 zmian) | 50 (6290 s, 7 zmian) |
| porzuca wszystko | blisko końca | 11 [9..24] | **50** (8715 s, 3 zmiany) | 50 (8618 s, 3 zmiany) |
| **przepuszcza własny ruch dziecka, porzuca resztę** | blisko roota | 21 [13..22] | **18 [3..30]**, 73 zmiany | 11 [10..14], 80 zmian |
| to samo | w środku | 9 [1..19] | **9 [3..17]**, 34 zmiany | 7 [2..12], 36 zmian |
| to samo | blisko końca | 33 [17..50] | 42 [24..50] | 32 [19..50] |
| porzuca wszystko i podsuwa ramki w dół | w środku | 18 [5..21] | **9 [5..20]**, tylko 2 próbki | 50 [50..50], 37 próbek |

Na ziarnach 201–210, z licznikiem na wiadomość: blisko roota 13 [2..22] → 50 [27..50], w środku 12 [6..18] → 50, blisko końca 16 [10..27] → 50; mediana w środku 6537 [5352..34151] s.

**Ten wiersz unieważnia pomysł wobec przejętego węzła.** Taki węzeł nie musi czytać treści: wystarczy mu porównać `src` koperty z nadawcą ramki. Jego dziecko dostaje odpowiedzi, więc nie ma powodu odejść, a ruch z dalszych stacji ginie. Próbka nie poprawia wtedy niczego, a przy roocie i w środku łańcucha mnoży zmiany rodzica u zdrowych stacji do około 20 razy. Sygnał „ramka w dół” pada przy tym od jednej podrobionej ramki na 5 min, bo przekaźnik nie sprawdzi koperty; sygnał „własna wiadomość” jest odporny, ale nadaje więcej (do 325 próbek na 12 h). **Próbka działa tylko na awarię lub zwykłe porzucanie, nie na atak.**

**Wyłączone stanowisko.** Ruch tylko z końca łańcucha.

| Przerwa | Konfiguracja | Czas nadawania wszystkich w przerwie (s) | Zmiany rodzica | Poza planem przy powrocie / po 1 h / po 2 h | Wszystko domknięte po powrocie (s) |
|---|---|---|---|---|---|
| 2 h | bez próbki | 392 [342..435] | 1 | 2 / 1 / 0 | 1080 [240..1320] |
| 2 h | próbka | **1309 [1212..1379]** | **11** | **12 / 11 / 2** | 1020 [420..2520] |
| 4 h | bez próbki | 613 [567..661] | 3 | 1 / 1 / 0 | 300 [120..3240] |
| 4 h | próbka | **2137 [2014..2216]** | **25** | 3 / 5 / 3 | 1380 [480..3000] |

Cały łańcuch próbkuje naraz i zmienia rodziców kaskadowo, ale kanał to wytrzymuje: 1309 s na 15 stacji przez 2 h to około 1,2% czasu nadawania na stację. Powrót nie jest wyraźnie wolniejszy po 2 h; po 4 h mediana to 1380 s wobec 300 s, przy dużym rozrzucie. Kosztem jest godzina na rodzicach zapasowych po usunięciu awarii, której te stacje nie miały.

**Obciążenie.** Przy 15 skokach i powodzi zgłoszeń (181 i 901 na godzinę) próbek jest 0, bo przekaźnik stale widzi ruch w dół. Przy 80% 2 [0..5] i do 3 zmian rodzica. Wrogi węzeł wywołujący próbki fałszywym ruchem w bezczynnej sieci: 116 [102..119] próbek na 8 h u stacji między nim a rootem, zajętość 7,0% wobec 5,2%, bez zmian rodzica i bez wpływu na RECEIVED. To koszt ograniczony limitem częstości.

**Jakiej wiadomości użyć.** Żaden istniejący rodzaj nie pasuje:

- `TEST` (rodzaj 5 w SA1) trafia na panel dyżurnego jako osobna pozycja do PRZECZYTANE (`panel.py`), a brak odpowiedzi po 30 min włącza na stacji alarm `brak_potwierdzenia` (`Station::alarm`). Zaśmieca panel i fałszywie alarmuje dokładnie wtedy, gdy łańcuch ma kłopot.
- `TYPE_PROOF` idzie do stanowiska bez żadnej odpowiedzi, więc niczego nie sprawdza.

Potrzebny byłby nowy rodzaj: wolna wartość typu koperty (2–15 zarezerwowane) albo typu SA1, plus odpowiedź stanowiska z pominięciem panelu i obsługa po stronie stacji. Układ bajtów istniejących ramek zostaje, ale to zmiana protokołu i dwóch programów, plus nowy stan w przekaźniku (w emulatorze `Net::noteTraffic`). **To koszt do doliczenia do decyzji.** Emulator używa wiadomości 40 B bez wpisu w panelu, czyli rodzaju, którego dziś nie ma.

### Najlepszy zestaw w drzewie

Poprawka kolejki, nauka, próby na przemian, budżet, blokada 2 h, „2 próby, ta wiadomość”. Dwa pnie po 15 skoków z czterema odgałęzieniami po 5 stacji, razem 50; dzieci jednego rodzica słyszą się wzajemnie. Godzina zgłoszeń, potem bez nowych, razem 8 h. Trzy ziarna. Przy 61 zgłoszeniach wszystko domknięte w każdej konfiguracji z zestawem (najdłużej 90–806 s), bez odmów dziennika. Przy 301 zgłoszeniach, czyli ponad przepustowością:

| Skok, łącza zapasowe | Konfiguracja | RECEIVED | Maks. (s) | Najdłuższa cisza (s) | Najmniej HACK na 10 min pod obciążeniem |
|---|---|---|---|---|---|
| 80%, nie | obecny kod | 39 [38..39] | 31830 | 900 | 115 [98..172] |
| 80%, nie | zestaw | 301 [299..301] | 27492 | 1124 | 97 [67..115] |
| 80%, tak | obecny kod | 301 [267..301] | 30796 | 603 | 255 |
| 80%, tak | zestaw bez poprawki | 301 | 24260 | 1596 | 216 |
| 80%, tak | zestaw | 301 | 18838 | 740 | 184 |
| 90%, nie | obecny kod | 181 [153..226] | 31932 | 598 | 185 |
| 90%, nie | zestaw | 301 | 9547 | 595 | 417 |
| 90%, tak | obecny kod | 301 | 14287 | 592 | 552 |
| 90%, tak | zestaw bez poprawki | 301 | 10656 | 1344 | 290 |
| 90%, tak | zestaw | 301 | 9481 | 578 | 428 |

**Zakleszczenia w drzewie nie ma**: co najmniej 67 HACK na 10 min przy każdym obciążeniu i dojście do końca. To jeden kształt drzewa i trzy ziarna, więc nie dowód dla każdej topologii. Cisza do około 600 s to pula 60% przy przeciążeniu, a nie opisane wyżej zapętlenie. Zmian rodzica jest dużo (44–183), bo odpowiedź na pojedynczą wiadomość pod przeciążeniem przychodzi po godzinach.

### Ocena autora raportu (nie rozstrzygnięcie)

1. **Pytanie C: poprawić kolejkę K1**, niezależnie od reszty. Mechanizm jest w obecnym firmware i daje się wywołać z zewnątrz. Najpierw osobna zmiana i sprawdzenie wariantu z `contendedK2`.
2. **Pytanie A: „2 próby, ta wiadomość”**. Daje najwęższe wyjście przy fałszywych zmianach na poziomie 30 min i nie ma ogona. Argument przeciw: liczy na jedną wiadomość, więc na realnych łączach ze stratami seriami może przenosić stacje częściej niż tu. Jeżeli pomiar łącza zapasowego wypadnie źle, „3 próby, ta wiadomość” ma w zdrowej sieci 0 zmian, ale wyjście około 1,7 raza dłuższe i tylko 36/50 przy ruchu z wielu stacji pod porzucającym. Wartość trzeba przeliczyć po próbie przy stole.
3. **Pytanie B: nie wdrażać teraz.** Pomaga tylko przy zwykłym porzucaniu, a tam, gdzie porzucanie jest najbardziej prawdopodobne, czyli przy przejętej stacji, węzeł omija ją jednym porównaniem. Do tego nowy rodzaj wiadomości i godzina na zapasowych po każdej dłuższej przerwie stanowiska. Zostaje jawne ograniczenie: **stacja pod porzucającą bez własnego ruchu odcina dalszą część łańcucha na godziny** (około 12/50 po 12 h), a wyjściem są alarm `brak_potwierdzenia` i ludzie. Dla przejętego węzła, który działa selektywnie, **żaden ze sprawdzonych wariantów nie działa** i emulator nie znalazł takiego, który by działał.

**Czego ta tura nie widzi:** strat seriami, zmian skuteczności w czasie i realnej jakości łącza zapasowego (założone 70%), efektu przechwycenia, kodu stacji i stanowiska poza skrótem. Stoper, licznik prób i próbka są częścią skrótu stacji, nie firmware. Liczby pochodzą z clang na macOS.

### Wybór poprawki kolejki K1

Właściciel zdecydował, że poprawka kolejki K1 wejdzie przed próbą przy stole, jako osobna zmiana, przed nauką dróg. Porównano dwa warianty bez zmiany bajtów w eterze:

- **Wariant pierwszy (`k1flood=1`):** ramka z gniazda K1 bez znanej drogi zachowuje pierwszeństwo K1. Zmienia regułę „rozsyłanie to K2”.
- **Wariant drugi (`k1routed=1`):** `contendedK2` liczy tylko czekające ramki K1 ze znaną drogą. Ramka K1 bez drogi wychodzi jako K2 jak dotąd, ale nie blokuje innych ramek przy limicie 25%. Reguła „rozsyłanie to K2” zostaje.

**Wniosek: wariant drugi działa porównywalnie z pierwszym i pod atakiem nie jest gorszy.** Ziarna 1–5 i nowe 301–310, 1260 przebiegów działania i 720 przebiegów ataku. Obraz „bez nauki” to obecne drogi, „z nauką” to zestaw przyjęty przez właściciela (drogi z ruchu, intencje na przemian, budżet rozsyłania, 2 próby zerowane odpowiedzią na tę wiadomość).

**Łącza zapasowe 70%, ruch z końca łańcucha, z nauką dróg.** Mediana po ziarnach i zakres; „wysokie ziarna” to ziarna z medianą domknięcia powyżej 3000 s, czyli drugi garb rozkładu.

| Skok | Kod | Mediana domknięcia (s) | Wysokie ziarna z 15 | Najdłuższa cisza przekaźnika (s) | Odmowy dziennika |
|---|---|---|---|---|---|
| 80% | obecny | 5196 [2273..6696] | 11 | 1781 | 7287 [166..16779] |
| 80% | wariant pierwszy | 2455 [2287..5471] | 1 | 1275 | 4343 [139..10089] |
| 80% | wariant drugi | 2515 [2285..4770] | 3 | 1061 | 3883 [375..6921] |
| 90% | obecny | 2374 [1990..6158] | 7 | 1652 | 4585 [163..10464] |
| 90% | wariant pierwszy | 2243 [1950..2356] | 0 | 725 | 166 [129..2348] |
| 90% | wariant drugi | 2179 [1990..2278] | 0 | 510 | 170 [133..1132] |
| 95% | obecny | 2587 [1722..6378] | 7 | 1786 | 1977 [128..12642] |
| 95% | wariant pierwszy | 2044 [1722..2190] | 0 | 2 | 163 [128..230] |
| 95% | wariant drugi | 2035 [1720..2290] | 0 | 708 | 171 [128..1166] |

Przy 90% i 95% oba warianty usuwają dwumodalność. Przy 80% oba zostawiają pojedyncze wysokie ziarna (1 i 3 z 15); przy tej liczbie ziaren to różnica w granicach przypadku, ale nie dowód równości. Żaden nie usuwa ciszy do zera przy 80%, bo łańcuch dochodzi tam do puli 60% z samego ruchu.

**Pozostałe próby** (mediana w grupie ziaren 1–5 i w grupie 301–310):

- **Z nauką dróg, cała sieć:** bez różnic między kodami w RECEIVED; cisza przekaźnika przy obu wariantach 9 s lub mniej, przy obecnym do 1539 s.
- **Z nauką dróg, nasycenie 80%:** najdłuższe domknięcie 17 000–17 800 s przy obecnym, 15 000–15 200 s przy pierwszym, 12 700–13 100 s przy drugim. Przy 90%: 6621–7995, 4675–6208, 5009–5792 s.
- **Z nauką dróg, drzewo:** 50 stacji, 15 skoków. Wszystkie zgłoszenia domknięte w każdym przebiegu. Przy ponad przepustowości najdłuższa cisza spada z 1395–1769 s do 575–767 s przy obu wariantach.
- **Bez nauki dróg:** wariant drugi nie pogarsza niczego ponad rozrzut między ziarnami; łańcuch bez łączy zapasowych i cała sieć dają te same przedziały. W drzewie przy skoku 80% i ponad przepustowości, gdzie 8 h nie wystarcza na domknięcie, na 15 ziarnach wyglądał nieco gorzej (najgorsze ziarno 232 z 301 wobec 267 obecnego). Sprawdzono to na 30 dalszych ziarnach (401–430): średnio 291,9 domkniętych wobec 291,6 obecnego i 290,9 pierwszego, różnice między kodami w jednym ziarnie od −40 do +50, więc to rozrzut, nie skutek poprawki. Tu dwumodalności nie ma w obecnym kodzie, bo plan zna drogi. Przed nauką dróg poprawka daje więc niewiele (mniej odmów pod atakiem niżej). Jest potrzebna dla nauki dróg, a wcześniej nie szkodzi.

**Atak: sąsiad z poprawnym tagiem pary podsuwa ramki K1 w dół do numerów bez drogi.** Napastnik jest zwykłą stacją na łańcuchu, poza tym przekazuje uczciwie, i rotuje cele między sąsiadami. Łańcuch 15 skoków z łączami zapasowymi 70%, skok 90%, 4 h, 50 zgłoszeń; ramka co 2 s, ruch z końca łańcucha. Napastnik przestrzega długu ciszy, więc 2 s to blisko górnej granicy; węzeł ignorujący dług nie był sprawdzany.

| Obraz | Kod | Domknięte z 50 | Rozsyłań łącznie | Kanał zajęty | Rozsyłania ponad 25% przy czekającej K1 ze znaną drogą | Odmowy ramek jednoadresowych | Stacji z wyczerpaną pulą |
|---|---|---|---|---|---|---|---|
| bez nauki | obecny | 49 [48..50] | 36 188 | 45% | 0 | 457 | 3 |
| bez nauki | wariant pierwszy | 49 [48..50] | 36 227 | 46% | 52 [32..64] | 592 | 4 |
| bez nauki | wariant drugi | 49 [48..50] | 36 635 | 46% | 0 | 331 | 2 |
| z nauką | obecny | **18 [16..22]** | 13 976 | 42% | 0 | **10 024** | 5 |
| z nauką | wariant pierwszy | 50 | 36 189 | 45% | 27 [17..74] | 400 | 2 |
| z nauką | wariant drugi | 50 | 35 894 | 45% | 0 | 376 | 2 |

- **Czy `k1flood=1` rozsyła ponad limit 25% kosztem cudzego K1:** tak, ale niewiele. We wszystkich próbach ataku najwyżej 97 ramek, około 15 s nadawania na 4 h. Odmów ramek jednoadresowych ma w medianie więcej niż wariant drugi w każdej próbie z ramką co 2 s (35–592 wobec 13–378). Wariant drugi z definicji nie rozsyła ponad limit, gdy czeka K1 ze znaną drogą.
- **Obecny kod z nauką dróg** pod tym atakiem domyka tylko 18 z 50 zgłoszeń. Sama nauka dróg bez poprawki jest więc podatna, a każdy wariant to usuwa.
- **Wyczerpanie puli 60% nie zależy od wariantu.** Gdy żadna K1 ze znaną drogą nie czeka, rozsyłanie może dojść do 60% w każdym kodzie. Przy ramce co 2 s dochodzi do tej granicy w obu wariantach najwyżej 5 stacji, każda łącznie do 1780 s z 4 h; w obecnym kodzie z nauką dróg 6 stacji i do 3710 s.
- **Ramka co 10 s** nie wyczerpuje puli u nikogo i wszystkie kody domykają 50 z 50, przy kanale zajętym około 20% wobec 3–6% bez ataku.

**Limity pierścienia i puli.**

| Sieć | Ramka napastnika | Rozsyłań (bez ataku) | Kanał zajęty (bez ataku) | Najwięcej rozsyłań stacji na 120 s | Wyczerpana pula | Domknięte, mediana (s) |
|---|---|---|---|---|---|---|
| 15 skoków, 4 h | co 10 s | 15 000 (300) | 19% (3%) | 13 | nikt | 50 z 50, 28–34 |
| 15 skoków, 4 h | co 2 s | 34 000–39 000 (300) | 42–45% (3%) | 37 | 1–2 stacje | 46–50 z 50, 40–165 |
| 100 słyszących się, 2 h | co 10 s | 31 000 (1980) | 66% (7%) | 14 | nikt | 20 z 20, 58–69 |
| 100 słyszących się, 2 h | co 2 s | 32 000 (1980) | 68% (7%) | 16 | nikt | 20 z 20, 109–121 |

Tabela to ruch z całej sieci, mediany dla wszystkich kodów i obu obrazów. Pierścień rozsyłania (256 pozycji na 120 s) **nigdy nie jest granicą**: najwięcej 40 rozsyłań na 120 s we wszystkich próbach, bo wcześniej hamuje dług ciszy. W łańcuchu ogranicza obciążenie pula 60%. Przy 100 stacjach pula też nie działa, bo każda stacja nadaje za mało, żeby ją osiągnąć: **jeden sąsiad zajmuje około dwóch trzecich kanału całej sieci, a hamuje go tylko dostęp do kanału**. Zgłoszenia dochodzą: mediana domknięcia rośnie z 3 do 121 s bez nauki dróg i z 9 do 109 s z nauką. Ta słabość istnieje w obecnym kodzie i jest taka sama w obu wariantach; poprawka K1 jej nie zmienia. Budżet rozsyłania stanowiska (`flood=700`) nie dotyczy tej ścieżki, bo rozsyłają stacje. Nie jest to część tego wyboru, ale wymaga decyzji przed siecią tej gęstości.

**Wybór:** wariant drugi spełnia warunek właściciela. Usuwa dwumodalność i ciszę przy łączach zapasowych tak samo jak pierwszy (przy 80% oba częściowo), pod atakiem daje wynik nie gorszy, nie rozsyła ponad limit i zachowuje regułę „rozsyłanie to K2”. Pod atakiem z ramką co 2 s, gdy napastnik stoi blisko roota, bez nauki dróg oba warianty dają minimalnie mniej domkniętych od obecnego kodu (46–47 wobec 48 z 50, w granicach rozrzutu). Poprawka idzie osobną zmianą w firmware; przełączniki w `variant.patch` zostają do czasu jej scalenia.

**Czego ta próba nie widzi:** poza ograniczeniami całego raportu (straty seriami, przechwycenie, założone 70%) tylko jeden napastnik i tylko jeden kształt celów; 100 stacji to skrajny przypadek, w którym każda słyszy każdą bez strat zależnych od odległości.

### Rozsyłanie w dół tylko od rodzica

Właściciel wybrał do sprawdzenia regułę przeciw zalewowi przez sąsiada z tagiem pary: przekaźnik rozsyła ramkę w dół bez drogi tylko wtedy, gdy przyszła od rodzica planowego albo zapasowego. Kopii od innych sąsiadów nie przekazuje i nie oznacza jako widzianych. Odbiorca nadal przyjmuje kopię od każdego sąsiada, bo reguła dotyczy tylko przekazywania. Rozsyłania w górę tor przekaźnika i tak nie przyjmuje.

Reguła to `floodparent=1` na kodzie z poprawką K1 (`k1routed=1`). Dodatkowo `floodparent=2` dopuszcza bieżącego rodzica, także dynamicznego, a `floodparent=3` to kontrola pułapki. 1180 przebiegów, ziarna 1–5 i 301–305, dla martwego rodzica w łańcuchu dalsze 401–430. Tabele podają medianę; „bez nauki” to obecne drogi, „z nauką” to zestaw przyjęty przez właściciela.

**Wniosek: reguła wyraźnie zmniejsza zalew i nie psuje doręczenia, dopóki kopia od rodzica może dojść. Psuje je, gdy jedyna droga obejścia prowadzi przez sąsiada spoza rodziców planowego i zapasowego: 24 z 24 spada do 4 z 24. Dopuszczenie bieżącego rodzica przywraca doręczenie w tej próbie i nie osłabia reguły w próbach ataku.**

**Atak: ramka co 2 s do numerów bez drogi.**

| Sieć i obraz | Kanał zajęty, bez reguły → z regułą | Doręczone w dół | Domknięte zgłoszenia | Mediana domknięcia (s) | Najdłuższe domknięcie (s) |
|---|---|---|---|---|---|
| 15 skoków, napastnik w środku, bez nauki | 45,6% → 25,1% | 56 → 60 z 60 | 48 → 50 z 50 | 137 → 43 | 10 008 → 4835 |
| to samo, z nauką | 45,1% → 24,9% | 60 → 60 z 60 | 50 → 50 z 50 | 47 → 36 | 3357 → 619 |
| 15 skoków, napastnik przy roocie, bez nauki | 42,7% → 32,1% | 56 → 60 z 60 | 45 → 50 z 50 | 703 → 101 | 9612 → 5742 |
| to samo, z nauką | 43,0% → 31,9% | 60 → 60 z 60 | 50 → 50 z 50 | 107 → 81 | 3781 → 968 |
| 100 stacji, bez nauki | 68,5% → 26,3% | 92 → 100 ze 100 | 1 → 20 z 20 | 246 → 8 | 246 → 1590 |
| to samo, z nauką | 67,5% → 28,8% | 60 → 100 ze 100 | 1 → 20 z 20 | 55 → 4452 | 55 → 6442 |
| 100 stacji, ramki rozsyłane wprost, bez nauki | 68,3% → 30,7% | 90 → 100 ze 100 | 1 → 20 z 20 | 527 → 10 | 527 → 1589 |
| to samo, z nauką | 67,7% → 34,9% | 54 → 100 ze 100 | 1 → 20 z 20 | 901 → 4450 | 901 → 6434 |

Mediana i najdłuższe domknięcie przy 100 stacjach bez reguły dotyczą tylko jednego domkniętego zgłoszenia, więc nie są porównywalne. 4450 s z nauką to skutek budżetu rozsyłania stanowiska przy 100 wiadomościach w dół: tyle samo jest bez ataku i bez reguły (4523 s).

- **Reguła nie zatrzymuje napastnika wobec jego własnych dzieci.** Bez ataku 15 skoków zajmuje 5% kanału, a z atakiem i regułą nadal 25–32%. Przy ramce co 10 s: 21% → 10%.
- **Cisza przekaźnika** spada: przy 15 skokach i napastniku przy roocie z 418–419 s do 2 s. Przy 100 stacjach i ramkach rozsyłanych wprost reguła ma ciszę 516–596 s (najwyżej 719 s), a bez reguły 0 s. Przyczyna z zapisu przebiegu jest w drugiej turze niżej.

**Bez ataku** reguła nie zmienia wyniku w łańcuchu: 60 z 60 w dół i 50 z 50 zgłoszeń przy skoku 90% i 80%, ta sama zajętość w granicach rozrzutu. Przy 100 stacjach bez nauki dróg kanał spada z 39% do 19%, a z nauką z 26% do 22%, doręczenie bez zmian.

**Przypadki, które mogą regułę zepsuć.** Doręczone w dół, mediana i zakres po ziarnach.

| Próba | Obraz | Bez reguły | Rodzic planowy lub zapasowy | Także bieżący rodzic |
|---|---|---|---|---|
| Martwy rodzic, łańcuch z zapasowymi, 30 ziaren, razem z 840 | bez nauki | 533 | 537 | nie liczono |
| to samo | z nauką | 634 | 641 | nie liczono |
| Martwy rodzic, 100 stacji | oba | 2 z 2 | 2 z 2 | 2 z 2 |
| **Martwy rodzic, jedyne obejście przez sąsiedni łańcuch, bez ruchu w górę** | bez nauki | 23 [17..24] z 24 | **4 [4..4]** | 24 [18..24] |
| to samo | z nauką | 24 [18..24] z 24 | **4 [4..4]** | 24 [17..24] |
| **Martwy rodzic, to samo obejście, ruch w górę** | bez nauki | 11 [7..20] z 24 | **4 [4..4]** | 9 [4..19] |
| to samo | z nauką | 16 [9..23] z 24 | **7 [5..8]** | 14 [7..23] |
| Zmiana rodzica z blokadą 2 h, łańcuch, raz | oba | 32 z 32 | 32 z 32 | 32 z 32 |
| Zmiana rodzica z blokadą 2 h, łańcuch, dwa razy | oba | 32 z 32 | 32 z 32 | 32 z 32 |
| Zmiana rodzica, obejście przez sąsiedni łańcuch | bez nauki | 21 z 24 | 21 z 24 | 20 z 24 |
| to samo | z nauką | 24 z 24 | 24 z 24 | 24 z 24 |

- **Martwy rodzic w łańcuchu:** na pierwszych 10 ziarnach reguła wyglądała gorzej (19 wobec 16 z 28), ale na 30 dalszych różnica znika. Rozrzut między ziarnami przewyższa różnicę: domknięte zgłoszenia 1021 wobec 1017 bez nauki, 1046 wobec 1107 z nauką, z 1500.
- **Obejście:** dwa łańcuchy po 12 skoków bez rodziców zapasowych, stacja 6 pierwszego martwa, jedno łącze ze stacji 7 do stacji 5 drugiego. Reguła ścisła odrzuca kopię z tego łącza, więc 4 z 24 to tylko sama stacja 7. Bieżący rodzic zmienia się po BEACON-ach także bez ruchu w górę, dlatego drugi tryb działa w obu próbach. Domknięte zgłoszenia z ruchem w górę: 9 → 0 → 7 bez nauki, 9 → 7 → 11 z nauką.
- **Sieć z rodzicem zapasowym nie ma tego problemu.** Konfiguracja, która daje każdej stacji działającego rodzica zapasowego, nie dochodzi do tej próby, ale awaria dwóch sąsiednich stacji już do niej doprowadza; pomiar jest w drugiej turze niżej.

**Pułapka z oznaczaniem jako widziane: nie ma przebiegu, w którym prawdziwa kopia ginie z tego powodu.**

Miara to kopia od rodzica uznana za widzianą, choć ta stacja jej nie przekazała. W 320 przebiegach reguły ścisłej i 320 z bieżącym rodzicem wynosi 0. Kontrola działa: gdy odrzucona kopia jest oznaczana (tryb 3), ta sama miara daje 65 102 kopie w 51 ze 100 przebiegów, a w próbie z 15 skokami najdłuższe doręczenie rośnie do 8851 s. Na kodzie przed przeglądem [#187](https://github.com/tmierzwa/WICI/pull/187) były dwa pojedyncze przypadki (jeden z regułą w 30 dalszych ziarnach martwego rodzica, jeden bez reguły w głównej macierzy), oba znacznikiem zapisanym przez sam przekaźnik przed nadaniem, które się nie odbyło. Po poprawce nie ma ani jednego.

**Inna strata, której reguła dokłada:** kopia od rodzica, która trafia na pełną kolejkę K2, nie jest ponawiana, a kopie od innych sąsiadów już jej nie zastąpią. Przy 100 stacjach bez nauki kopii nieprzekazanych po usłyszeniu od rodzica jest 11 709 z 82 498 wobec 3834 ze 136 176 bez reguły. Doręczenie zostaje 100 ze 100, bo tam każdy słyszy wszystkich. Przy 15 skokach to 238 wobec 204 z około 9000 i bez skutku dla doręczenia.

**Ocena autora raportu, nie rozstrzygnięcie:** reguła jest warta wdrożenia, ale z dopuszczeniem bieżącego rodzica. Ścisła wersja traci obejście przez rodzica dynamicznego, które protokół przewiduje, a próby ataku nie pokazują żadnej przewagi nad wersją z bieżącym rodzicem. Argument przeciw: napastnik, który podsunie niską rangę i zostanie czyimś bieżącym rodzicem, dostaje też prawo rozsyłania wobec tej stacji. Rozsyłać może on i tak wobec swoich dzieci, a tej kombinacji nie mierzono.

**Czego ta próba nie widzi:**
- Reguła odmawia ramce jednoadresowej bez HACK, więc sąsiad po trzech próbach wstrzymuje tę stację. Pomiar jest w drugiej turze niżej.
- Jeden napastnik, jeden kształt obejścia, jedna głębokość. Straty seriami i przechwycenie są poza modelem, jak w całym raporcie, a łącze obejścia ma założone 70%.
- Wynik dotyczy poprawki K1 z [#187](https://github.com/tmierzwa/WICI/pull/187), która jest już w main; wcześniej był to przełącznik `k1routed=1` w `variant.patch`.

### Rozsyłanie od rodzica: druga tura

Właściciel wybrał wersję z bieżącym rodzicem (`floodparent=2`). Przed zmianą firmware sprawdzono trzy rzeczy, których pierwsza tura nie mierzyła. 720 przebiegów, ziarna 1–5 i 301–305, te same dwa obrazy dróg i poprawka K1 (`k1routed=1`). Tabele podają medianę z 10 ziaren.

**Wniosek: wersja z bieżącym rodzicem ma jeden koszt wobec ścisłej, dokładnie ten przewidziany: napastnik, który zostanie bieżącym rodzicem stacji, rozsyła przez nią. Kanał jest wtedy zajęty w 22–26% zamiast 13–15%, wobec 43–47% bez reguły; doręczenie i domknięte zgłoszenia są takie same jak w wersji ścisłej. Odmowa ramki jednoadresowej bez HACK zdarza się tylko przy starej drodze z nauki i nie zepsuła doręczenia. Cisza przy 100 stacjach to pula 60% u dzieci napastnika.**

**Napastnik jako bieżący rodzic.** Napastnik z tagiem pary ogłasza fałszywie niską rangę i uczciwie przekazuje ruch. Ofiara traci łącze do rodzica planowego i zapasowego, więc po trzech nieudanych próbach przechodzi na napastnika jako rodzica dynamicznego. Potem napastnik co 2 s podsuwa ofierze i jej dwóm sąsiadom ramki do numerów bez drogi. W wariancie „porzuca” napastnik dodatkowo daje HACK i porzuca ruch. Kolejność w komórkach: bez reguły → reguła ścisła → także bieżący rodzic.

| Próba | Obraz | Ofiara pod napastnikiem | Kanał zajęty | Doręczone w dół z 60 | Domknięte z 50 | Najdłuższe domknięcie (s) |
|---|---|---|---|---|---|---|
| 15 skoków, ofiara 8, bez ataku | bez nauki | 87% | 6,1% → 6,5% → 6,2% | 60 → 60 → 60 | 50 → 50 → 50 | 4834 → 4835 → 4121 |
| 15 skoków, ofiara 8, atak co 2 s | bez nauki | 16% → 66% → 63% | 46,6% → 13,8% → 22,0% | 58 → 60 → 60 | 46 → 50 → 50 | 10 004 → 5957 → 5348 |
| to samo | z nauką | 16% → 67% → 71% | 46,7% → 13,5% → 22,9% | 60 → 60 → 60 | 50 → 50 → 50 | 5967 → 2768 → 3285 |
| 15 skoków, ofiara 3, atak co 2 s | bez nauki | 13% → 49% → 59% | 43,1% → 14,9% → 25,9% | 53 → 59 → 59 | 39 → 49 → 50 | 10 966 → 7073 → 6199 |
| to samo | z nauką | 14% → 54% → 51% | 43,5% → 14,4% → 24,9% | 59 → 60 → 60 | 50 → 50 → 50 | 8870 → 2833 → 4043 |
| 15 skoków, ofiara 8, atak, porzuca | bez nauki | 87% | 47,8% → 14,4% → 25,9% | 55 → 58 → 58 | 30 → 30 → 29 | 7788 → 6342 → 5841 |
| to samo | z nauką | 37–39% | 46,4% → 15,7% → 24,2% | 59 → 60 → 60 | 35 → 36 → 36 | 8911 → 7880 → 7582 |
| 100 stacji, 8 ofiar, atak co 2 s | bez nauki | 14% → 15% → 24% | 68,6% → 46,3% → 46,2% | 83 → 100 → 100 ze 100 | 0 → 17 → 17 z 20 | 0 → 4045 → 3994 |

- **Koszt wersji z bieżącym rodzicem** to około 8–11 punktów zajętości kanału, gdy napastnik naprawdę jest rodzicem ofiary. Ofiara rozsyła wtedy jego ramki do swojego poddrzewa, czyli robi to samo, co reguła i tak pozwala dzieciom napastnika. Doręczenie, domknięte zgłoszenia i ich mediana nie różnią się od wersji ścisłej ponad rozrzut.
- **Porzucanie ruchu** jest groźniejsze od rozsyłania i reguła na nie nie działa: 29–36 z 50 zgłoszeń we wszystkich trybach. Na to odpowiada zmiana rodzica po braku odpowiedzi, nie ta reguła.
- **Przy 100 stacjach** ofiary są pod napastnikiem tylko przez 14–24% czasu; przyczyny nie rozbierano. Oba tryby reguły dają tu ten sam wynik. Obraz z nauką dróg jest w tym kształcie zepsuty już bez ataku i bez reguły (1 z 20 domkniętych, bo ofiary odcięte od roota zostają z drogą wprost), więc go tu nie podano. Surowe liczby są w pliku wyników.

**Odmowa ramki jednoadresowej bez HACK.** Reguła odmawia, gdy ramka w dół przychodzi od sąsiada spoza rodziców, a odbiorca nie ma drogi do adresata. Wtedy nadawca po trzech próbach wstrzymuje odbiorcę, zapomina drogę i następną próbę rozsyła. Rodzica zmieniłby tylko wtedy, gdyby odbiorca był jego bieżącym rodzicem, bo `Table::hopResult` liczy porażki tylko do rodzica.

We wszystkich próbach z rodzicami planowymi i zapasowymi taka odmowa nie wystąpiła ani razu. Bez nauki dróg stara droga przez obcego sąsiada w ogóle nie powstaje, bo `Table::learn` przyjmuje tylko drogę zgodną z planem. Próba wstawia więc starą drogę wprost: w łańcuchu stacja 2 dostaje drogę do stacji 12 przez stację 5 (dodatkowe łącze 70%), a stacja 5 traci swoją drogę do 12. W sieci 100 stacji root dostaje drogę do ośmiu swoich dzieci przez osiem stacji z drugiego poziomu. Stara droga wraca przed każdą z czterech serii wiadomości w dół. Kolejność: bez reguły → ścisła → z bieżącym rodzicem.

| Próba (z nauką) | Odmowy | Rundy bez HACK u nadawcy | Zapomniane drogi | Zmiany rodzica z tego powodu | Doręczone w dół | Mediana / najdłużej (s) |
|---|---|---|---|---|---|---|
| 15 skoków, stara droga w stacji 2 | 0 → 5 → 5 | 0 → 3 → 3 | 0 → 3 → 3 | 0 → 0 → 0 | 4 → 4 → 4 z 4 | 17 / 29 → 25 / 215 → 25 / 203 |
| 100 stacji, stara droga w roocie | 0 → 10 → 10 | 0 | 0 | 0 | 32 → 32 → 32 z 32 | 29 / 414 → 14 / 414 → 14 / 414 |

- W łańcuchu odmowa kosztuje rundę trzech prób i wstrzymanie stacji 5 u stacji 2; najdłuższe doręczenie (mediana po ziarnach) rośnie z 29 do 215 s. Potem stacja 2 zapomina drogę, wiadomość idzie rozsyłaniem od rodzica i dochodzi.
- Root ma własną obsługę porażki (`Root::transmit`, trzy porażki zapominają drogę), więc odmowa nie daje tam rundy przekaźnika, a doręczenie jest nawet szybsze, bo kopia nie krąży przez obcą stację.
- Bez reguły ta sama stara droga daje HACK i rozsyłanie od obcej stacji, więc wiadomość też dochodzi. Odmowa zmienia tylko to, kto rozsyła.

**Cisza przy 100 stacjach z ramkami rozsyłanymi wprost: pula 60% u dzieci napastnika, nie wada reguły.** Zapis przebiegu (ziarno 1, bez nauki, reguła ścisła, `trace=1`) pokazuje odmowy z dziennika czasu nadawania tylko u stacji 50 i 99, czyli jedynych dzieci napastnika (stacja 1 jest ich rodzicem planowym). Stacja 50 przekazała 1491 ramek napastnika i dostała 1483 odmowy, wszystkie dla tych samych ramek rozsyłanych (ruch przekazywany). Odmowy przychodzą od 78. do 123. minuty, gdy pula 60% w oknie godziny jest wyczerpana. Stacja nie nadaje wtedy nic, bo nie ma nic innego do nadania, i stąd 514 s „ciszy”.

Bez reguły każda ze 100 stacji przekazuje ramkę napastnika (średnio 184 razy na stację w 2 h), ale kanał zajęty w 68% nie pozwala żadnej dojść do puli; napastnik nadał 353 ramki zamiast 2530. Z regułą przekazują tylko jego dzieci, kanał jest wolniejszy, więc napastnik nadaje częściej, a dzieci wyczerpują pulę. To jest pula w roli, do której jest: zatrzymuje stację, która stała się wzmacniaczem. Ani jedna odmowa nie dotyczyła ramki własnej, HACK-u ani BEACON-u.

**Dwie sąsiednie awarie.** Łańcuch 15 skoków z rodzicami zapasowymi, stacje 8 i 9 martwe, jedynym wyjściem stacji 10 jest łącze 70% do stacji 7, ruch w górę tylko z końca łańcucha. Doręczone w dół z 24 i domknięte zgłoszenia z 50:

| Obraz | Bez reguły | Reguła ścisła | Także bieżący rodzic |
|---|---|---|---|
| bez nauki, w dół | 11 [7..14] | 4 [3..4] | 8 [5..13] |
| bez nauki, domknięte | 7 [0..18] | 0 [0..0] | 4 [1..13] |
| z nauką, w dół | 12 [8..18] | 6 [5..7] | 11 [7..16] |
| z nauką, domknięte | 5 [0..24] | 12 [1..23] | 7 [2..12] |

Reguła ścisła traci tu to samo obejście co przy dwóch łańcuchach: stacja 7 nie jest rodzicem planowym ani zapasowym stacji 10. Wersja z bieżącym rodzicem jest w granicach rozrzutu od wyniku bez reguły. Rozrzut domkniętych zgłoszeń jest duży we wszystkich trybach, bo całe zaplecze wisi na jednym łączu 70%.

**Czego ta próba nie widzi:**
- Odmowy u nadawcy, którego bieżącym rodzicem jest odmawiający. Taki układ wymaga starej drogi w górę łańcucha i ramki w dół od innego rodzica niż bieżący; w próbach nie powstał, a skutek wynika tylko z kodu (`Table::hopResult`).
- Dziecka napastnika, które samo jest przekaźnikiem. Przy wyczerpanej puli ono też odmówi ruchu przekazywanego swoich dzieci; w sieci 100 stacji dzieci napastnika nie mają dzieci.
- Napastnika, który jednocześnie podsuwa niską rangę wielu stacjom w głębokiej sieci, i ofiar z pełną tablicą sąsiadów w łańcuchu.
- Granice modelu z całego raportu: brak strat seriami i przechwycenia, łącza obejścia 70% założone.

### Obie tury na kodzie po przeglądzie #187

Przegląd [#187](https://github.com/tmierzwa/WICI/pull/187) poprawił poprawkę K1: przy limicie 25% liczy się tylko ramka K1, która może teraz wyjść jednoadresowo, według tej samej reguły co wybór ramki do nadania (`Relay::nextHop`). W `variant.patch` reguła rozsyłania od rodzica siedzi teraz w tej samej funkcji. Obie tury powtórzono na tych samych ziarnach (1900 przebiegów); tabele wyżej podają już nowe liczby.

**Wniosek: żaden wniosek o regule się nie zmienił.** 1593 z 1900 przebiegów dało wynik identyczny co do bajtu, wszystkie przebiegi 100 stacji też. Różnice są głównie w kolumnie bez reguły pod atakiem i przy martwym rodzicu, w granicach rozrzutu między ziarnami.

- **Cisza w wersji z bieżącym rodzicem** spadła tam, gdzie zostawała: napastnik porzucający ruch, z nauką dróg, ofiara 8 z 232 do 2 s, ofiara 3 z 299 do 2 s. Jedyna zmiana kodu to liczenie czekających K1, więc tę ciszę dawała ramka K1, której przekaźnik nie mógł nadać, czyli błąd z przeglądu; zapisu przebiegu tu nie rozbierano.
- **Martwy rodzic w łańcuchu, 30 ziaren:** doręczone w dół 518 → 533 bez reguły i 527 → 537 z regułą (bez nauki), 626 → 634 i 639 → 641 (z nauką). Domknięte 967 → 1021 i 983 → 1017 bez nauki, 1075 → 1046 i 1145 → 1107 z nauką.
- **Pułapka z oznaczaniem:** dwa pojedyncze przypadki sprzed poprawki zniknęły.
- **Bez reguły pod atakiem** najdłuższe domknięcie zmienia się w obie strony o kilkadziesiąt procent (na przykład 1587 → 3357 s i 4384 → 3781 s z nauką). Mediany zmieniają się o kilka sekund, a doręczenie o jedną wiadomość.

## Wrażliwość na założenia

Słyszalny drugi sąsiad (mniej ukrytych nadajników) i nasłuch mylący się w 0% albo 10% przypadków, 90%, 50 zgłoszeń: zmiany mniejsze niż rozrzut między ziarnami, wnioski te same. Na przykład koniec łańcucha po rozstrzygnięciach: RECEIVED maks. 4298, 4549 i 4409 s przy 4530 s dla założeń podstawowych. Nie sprawdzono: strat seriami i efektu przechwycenia, na które model nie ma parametru z pomiaru.

## Czego emulator nie sprawdził

- Strat seriami, zmian skuteczności w czasie i niesymetrycznych łączy.
- Awarii zasilania i restartów stacji w trakcie, choć stan FRAM jest prawdziwy.
- Ciszy radiowej, dwóch tożsamości odbiorcy, rzeczywistej kolejki REPLY, STATUS i BULLETIN.
- Dwuczęściowych zgłoszeń 222 B w macierzy; emulator je obsługuje, ale raport liczy 174 B.
- Budżet rozsyłania liczono na szeregu równoległych łańcuchów, a drzewa pod obciążeniem na jednym kształcie.
- Obieg stacji i stanowiska to skrót kodu produkcyjnego, nie ten kod.

## Powtórzenie

```bash
python3 tests/native/wici_emulator/run.py matrix /tmp/emu wyniki.jsonl
```

685 przebiegów, kilka minut na wielu rdzeniach. Druga tura to 1901 przebiegów, około 20 min na 18 rdzeniach, i cztery pliki wyników:

```bash
python3 tests/native/wici_emulator/run.py pytania /tmp/emu pytania.jsonl
```

Wybór poprawki kolejki K1 to 1980 przebiegów, około 10 min, i dwa pliki wyników:

```bash
python3 tests/native/wici_emulator/run.py k1 /tmp/emu k1.jsonl
```

Rozsyłanie tylko od rodzica to 1180 przebiegów i dwa pliki wyników:

```bash
python3 tests/native/wici_emulator/run.py regula_rodzica /tmp/emu regula.jsonl
```

Druga tura reguły to 720 przebiegów, około 11 min na 18 rdzeniach:

```bash
python3 tests/native/wici_emulator/run.py regula_rodzica_2 /tmp/emu regula2.jsonl
```

Zapis pojedynczego przebiegu (ramki, odbiory, zmiany rodzica, migawki dróg i dziennika) daje `trace=1` na stderr. Ten sam plik wykonywalny daje te same wyniki co do bajtu. Liczby tego raportu pochodzą z clang na macOS; zgodności z innym kompilatorem nie sprawdzano.

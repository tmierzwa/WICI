# Emulator WICI-Link: wyniki z 2026-11-05

Sprawdzenie czterech rozstrzygnięć o drogach w łańcuchach (WICI-DEC-009) prawdziwym kodem stacji i roota, zanim trafią do firmware. Opis i założenia są w [README emulatora](../tests/native/wici_emulator/README.md).

**Co ten raport dowodzi.** Logikę i obciążenie przy założonym kanale. Nie dowodzi działania radia. Najmocniejsze ograniczenie: straty ramek są niezależne, bez serii, więc w terenie ponowienia wypadną gorzej. Odwrotnie działa brak efektu przechwycenia, który zawyża kolizje. Wartości trzeba przeliczyć po próbie przy stole i krótkim łańcuchu.

## Rozstrzygnięcia wobec wyników

| Rozstrzygnięcie | Wynik | Co dalej |
|---|---|---|
| Przekaźnik uczy się dróg w dół z ruchu w górę | potwierdzone w łańcuchu, z dwoma kosztami: wolniejsza droga w górę i gorszy wynik przy łączach zapasowych 70% i skuteczności 80% | do decyzji: czy koszt jest do przyjęcia |
| Próby na przemian i ramka rozsyłana zostaje rozsyłana | potwierdzone | bez zmian |
| **Zmiana rodzica po około 30 min** | **wynik przeczy wartości 30 min**: próg działa fałszywie w zdrowej sieci przy każdym ziarnie | **otworzyć ponownie** |
| **Zmiana rodzica jako wyjście z porzucania** | **działa tylko u stacji tuż pod porzucającą**, przy ruchu z dalszych stacji 12 z 50 zgłoszeń po 12 h, obecny kod 9 | **otworzyć ponownie albo przyjąć jawnie jako ograniczenie** |
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

**Łącza zapasowe zmieniają obraz.** Przy łączach co dwa skoki o skuteczności 70% obecne rozsyłanie działa dobrze i przewaga nauki znika, a przy końcu łańcucha i 80% nauka jest gorsza: mediana RECEIVED 6412 [2333..7036] wobec 2724 [2290..3796] s, przyjęcie maks. 3654 wobec 1502 s. Rozrzut wskazuje na dwa tryby pracy. Przyczyny nie potwierdzono; hipoteza: rodzice skaczą między łączem z planu a słabym zapasowym, a „ostatnia wygrywa” prowadzi ruch przez słabe łącze.

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

Przyczyna leży w czasach, które już są w kodzie: stacja po HACK ponawia po 10 min, a potem co 30–60 min (`RESEND_MIN_S`, `RESEND_MAX_S`), a stanowisko po przekazaniu przekaźnikowi czeka 35 min (`CUSTODY_S`). Zdrowa stacja z jednym zgubionym RECEIVED milczy więc dłużej niż 30 min: najdłuższa cisza bez zmiany rodzica to 2834 [2086..3179] s, pod nasyceniem 5276 [3833..9068] s. **Próg 30 min jest krótszy od zwykłego odstępu ponowienia.** Fałszywa zmiana przy łączach zapasowych 70% kosztuje mało (najdłuższe RECEIVED o około 12% dłużej), przy 90–95%, ale przenosi stację na słabsze łącze na 2 h.

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

**Zakleszczenia nie ma.** Dopóki są otwarte zgłoszenia, sieć robi postęp: w przebiegach z ziarnem 1 przy obciążeniu co najmniej 41 HACK na 10 min, a dłuższe przerwy (do 3088 s) wypadają po opróżnieniu kolejek, gdy czeka się na ponowienie 30–60 min. Przy 901 zgłoszeniach sieć po prostu ma za małą przepustowość: po 9 h stanowisko ma 352–448 przyjęć. Pula 60% czasu kanału odmawia tu tysięcy razy (`budget_refused`), bez blokady węzłów. To nie jest dowód braku zakleszczenia dla każdej topologii: sprawdzono łańcuch, bez rozgałęzień pod obciążeniem.

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

## Wrażliwość na założenia

Słyszalny drugi sąsiad (mniej ukrytych nadajników) i nasłuch mylący się w 0% albo 10% przypadków, 90%, 50 zgłoszeń: zmiany mniejsze niż rozrzut między ziarnami, wnioski te same. Na przykład koniec łańcucha po rozstrzygnięciach: RECEIVED maks. 4298, 4549 i 4409 s przy 4530 s dla założeń podstawowych. Nie sprawdzono: strat seriami i efektu przechwycenia, na które model nie ma parametru z pomiaru.

## Czego emulator nie sprawdził

- Strat seriami, zmian skuteczności w czasie i niesymetrycznych łączy.
- Awarii zasilania i restartów stacji w trakcie, choć stan FRAM jest prawdziwy.
- Ciszy radiowej, dwóch tożsamości odbiorcy, rzeczywistej kolejki REPLY, STATUS i BULLETIN.
- Dwuczęściowych zgłoszeń 222 B w macierzy; emulator je obsługuje, ale raport liczy 174 B.
- Rozgałęzionych drzew pod obciążeniem; budżet rozsyłania liczono na szeregu równoległych łańcuchów.
- Obieg stacji i stanowiska to skrót kodu produkcyjnego, nie ten kod.

## Powtórzenie

```bash
python3 tests/native/wici_emulator/run.py matrix /tmp/emu wyniki.jsonl
```

685 przebiegów, kilka minut na wielu rdzeniach. Ten sam plik wykonywalny daje te same wyniki co do bajtu. Liczby tego raportu pochodzą z clang na macOS; zgodności z innym kompilatorem nie sprawdzano.

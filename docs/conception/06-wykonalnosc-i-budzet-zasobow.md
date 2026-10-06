# 06. Wykonalność i budżet zasobów

## Ocena wykonania

| Część | Obecny dowód | Co blokuje uznanie za działającą |
|---|---|---|
| Format P1, SA1, transakcja OSP | wykonywalny model i przypadki graniczne | firmware, integracja bibliotek, odcięcia fizycznego nośnika |
| Kontroler USB R01.3 | źródła CAD, raporty ERC/DRC, eksporty | poprawka toru zegara/zasilania dla suspend USB, dopasowanie części i pomiary całego modemu; HOLD |
| Modemy TI i ST | wspólny kontrakt, kandydaci układów | dwa layouty RF, rejestry, firmware, emisje i próba mieszana |
| Strona i pakiety START | kontrakt API i układ pakietu | implementacja, budowa offline, macierz urządzeń i test użytkowy |
| Zasilanie A/B, przetwornica i ładowarka | opisy konstrukcji i obliczenia | pełne projekty wykonawcze, zabezpieczenia, udary, termika i bezpieczeństwo |
| Sieć i odbiorca pomocy | scenariusze i warunki odbioru | rzeczywiste miejsca, działający przekaźnik, dyżur i próba terenowa |

Koncepcja jest technicznie testowalna. Koszt i czas jej doprowadzenia do wdrożenia pozostają otwarte. Odtworzenie projektu przez początkującą osobę powinno obejmować odebrane płytki i prosty montaż końcowy. RF oraz 230 V wymagają kompetencji i wyposażenia; obecny pakiet nie daje jeszcze bezpiecznej instrukcji samodzielnego wykonania całego zestawu.

## Budżet czasu antenowego

Dla datagramu B bajtów w P1: liczba fragmentów `n = ceil(B/86)`, liczba bajtów w eterze `B + 29n`, czas TX `t = 8(B + 29n)/4800`. Dług ciszy wynosi `12t`; cykl jednego nadajnika bez dodatkowych opóźnień `13t`. Obliczenie nie obejmuje rampowania, CCA, kolizji, ponowień ani ruchu Reticulum/LXMF.

| Datagram B | Fragmenty | Bajty w eterze | TX [s] | TX + cisza [s] | Pełne cykle w 30 min |
|---:|---:|---:|---:|---:|---:|
| 100 | 2 | 158 | 0,263 | 3,423 | 525 |
| 250 | 3 | 337 | 0,562 | 7,302 | 246 |
| 500 | 6 | 674 | 1,123 | 14,603 | 123 |
| 600 | 7 | 803 | 1,338 | 17,398 | 103 |

To przepustowość idealnego nadajnika na poziomie datagramów modemu, nie liczba zgłoszeń aplikacji. Dla 600 B wynosi około 34,5 B/s użytecznych danych wejściowych modemu. Każdy przekaźnik zużywa własny czas TX na przekazanie zgłoszeń, odpowiedzi i ruchu sterującego. Sąsiedzi współdzielą kanał; nie można sumować ich przepustowości jak niezależnych kabli.

Przykład obciążenia: 100 datagramów po 600 B zajmuje jednemu nadajnikowi około 1740 s cykli, czyli 29 min. To ilustracja małego zapasu czasu, jeśli 50 zgłoszeń i ich potwierdzenia wymagałyby takiego ruchu przez jeden przekaźnik. Rzeczywiste potwierdzenia mają inną długość, a transmisja obejmuje dodatkowe pakiety. Wynik dla 50 zgłoszeń trzeba zmierzyć, nie wywnioskować z tabeli.

LXMF może przejść od pojedynczego pakietu do przesyłania zasobu dla większej wiadomości. Limit treści SA1 480 B nie daje limitu jednego pakietu radiowego. Dodatkowo istnieją zestawienie łącza, ogłoszenia tras, potwierdzenia i ponowienia. Zwykły interfejs KISS ma w obecnym kodzie timeout kontroli przepływu 5 s; P1 może wymagać ponad 16 s samej ciszy. Wymagany adapter nie jest zatem kosmetyczną konfiguracją. [LXMessage](https://github.com/markqvist/LXMF/blob/master/LXMF/LXMessage.py), [KISSInterface](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py), [kontrakt adaptera](../spec/radio.md).

Adapter 900 s nie zmienia timeoutów linku i zasobu. Pakiet może czekać w kolejce dłużej niż pozwala stos, jeszcze przed pierwszym TX. [Kontrprzykład z przypiętego kodu](../review.md).

Próba musi policzyć wszystkie bajty i czas TX każdego węzła, zarówno podczas zimnego zestawienia trasy, jak i ruchu ustalonego. Mierzyć opóźnienie do RECEIVED, wiek kolejki, odrzuty, retransmisje i poprawność po restarcie. Kolizja ukrytych nadajników jest możliwa mimo CCA. Fragmentacja zwiększa ryzyko utraty całego datagramu.

## Zasięg

Strata swobodnej przestrzeni dla 869,525 MHz i 1 km wynosi około 91,23 dB. Przykład: 13 dBm na złączu, dwie anteny po 2,15 dBi i po 1 dB straty przewodów dają około −75,93 dBm u odbiorcy. Względem **niezmierzonego celu** czułości −110 dBm jest to 34,07 dB zapasu w tym modelu.

Przykład nie obejmuje ścian, metalu, terenu, zaniku wielodrogowego, odstrojenia anteny, zakłóceń i rzeczywistej czułości. Nie jest dowodem 1 km w mieście. Anteny przy oknie lub drzwiach muszą przejść próbę w docelowej pozycji. Wynik zapisać z układem miejsc, przewodami, rewizjami i warunkami. Najpierw zmienić położenie anteny lub dodać przekaźnik; zmiana profilu P1 wymaga jawnej rewizji całej sieci.

## Energia: dwa niezależne zasoby

Założenia [modelu](../../software/reference/wyniki.json): 35 W AC dla stacji, sprawność 0,85, 8 W poboru własnego przetwornicy i 1,7 W strat diod. Moc pobierana wynosi `35/0,85 + 8 + 1,7 = 50,88 W`. Stacja zużywa około 1221 Wh przez dobę; z rezerwą 20% około 1465 Wh.

Telefony: 50 × 5 Wh przy sprawności 0,8 = 312,5 Wh ze źródeł ładowarki; z rezerwą 375 Wh. **5 Wh na osobę jest częściowym doładowaniem, nie pełnym ładowaniem każdego telefonu.** Osiem portów daje maksymalnie 60 W na wyjściu. Pobór własny ładowarki i straty przewodów trzeba zmierzyć.

Przy założeniu 12 V, 60 Ah i 50% wykorzystania jeden akumulator daje 360 Wh. Jest to model, nie ocena sprawności dowolnego akumulatora samochodowego.

| Zasób | Energia z rezerwą | Liczba założonych akumulatorów 360 Wh |
|---|---:|---:|
| Stacja, pula wymieniana przez A/B | 1465 Wh | 5 |
| Telefony, osobna pula C | 375 Wh | 2 |
| Łączny ekwiwalent energii, przed podziałem | 1840 Wh | 6 |

Przy sztywnym przydzieleniu osobnych akumulatorów do obu pul zaokrąglenia dają **7 sztuk modelowych**, mimo łącznego ekwiwalentu 6. Wspólny zapas może być przydzielany kolejno, ale wymaga planu i znajomości pozostałej energii. Litery A/B/C oznaczają wejścia, nie obietnicę pracy dobowej z trzech akumulatorów. Nie przyjmować, że rozruchowy akumulator zachowuje modelową pojemność lub może zostać rozładowany bez wpływu na użycie pojazdu.

Wpływ znalezionego komputera, przy tych samych stratach i rezerwie, dla samej stacji:

| Moc AC | Pobór wejściowy | Energia 24 h z rezerwą | Ekwiwalenty 360 Wh |
|---:|---:|---:|---:|
| 15 W | 27,35 W | 788 Wh | 3 |
| 35 W | 50,88 W | 1465 Wh | 5 |
| 60 W | 80,29 W | 2312 Wh | 7 |

Dobór oszczędnego hosta i pomiar poboru mają większy wpływ na zapas niż sama moc radia. Nie gwarantować 24 h dla dowolnego PC. Gniazdo zapalniczki ogranicza prąd i możliwą moc AC; nominalne 150 W wymaga odpowiednich zacisków oraz przewodów. Każde pojedyncze źródło A lub B musi samodzielnie utrzymać dozwolone obciążenie.

## Wykonanie, koszt i wielkość serii

[BOM stacji](../../bom.csv) jest listą kandydatów, nie ofertą produkcyjną. Oddzielić koszt jednego zestawu, koszt znalezionych zasobów i koszt uruchomienia projektu. Przetwornica z transformatorem, zabezpieczenia, przewody i obudowy mogą kosztować więcej niż sama elektronika radiowa.

Do wyceny prototypu i 1000 sztuk przygotować ten sam zakres: kompletacja elementów, PCB/montaż, transformator i uzwojenia, obudowa, antena, wiązki i bezpieczniki, pendrive, kontrola każdej sztuki oraz straty produkcyjne. Osobno wycenić projekt i kwalifikację dwóch wykonań, oprzyrządowanie, badania oraz poprawki po próbach. Rozdzielić cenę netto/brutto, transport i założenia walutowe. Poprosić co najmniej dwóch niezależnych wykonawców o identyczny zakres.

Niekomercyjny cel nie usuwa kosztu części ani badań. Koszt jednostkowy po kwalifikacji nie jest kosztem pierwszego działającego zestawu. Przed ofertami i pełnymi projektami wykonawczymi dokładna kwota byłaby pozorną precyzją.

# WICI: próby pierwszych sztuk v2

Plan prób dwóch prototypów na [płytce v2](README.md) z obrazem [`v2`](../../firmware/docs/prototyp-l0-i-xiao.md#prototyp-płytki-v2-v2) (od `v2-0.8`). Płytki jeszcze nie ma (schemat bez ścieżek, [Przed ścieżkami i zamówieniem](README.md#przed-ścieżkami-i-zamówieniem)). Plan powstał wcześniej, żeby obie sztuki sprawdzić w jednym przejściu, kiedy tylko wrócą z montażu.

Próby mają trzy cele:

- warunek 2 przed pracą w terenie ([odbiór](../../docs/spec/odbior.md#minimum-pilotażu)): pomiar ogniw i 12 V, szacunek godzin pracy z ogniw, `wymien_ogniwa`, alarmy 12 V i wyłączanie działają na płytce, a nie tylko w testach na komputerze; po nim znikają znaki ◆ z [karty obsługi](../../docs/obsluga/karta-stacji.html); w tym samym przejściu warunek 3 (ZAMKNIJ ZDARZENIE z menu stacji);
- stałe i progi programu, przyjęte 2026-11-18 jako szacunki, zastąpione pomiarem;
- decyzje o poprawkach płytki przed zamówieniem pozostałych 6 stacji ([Na pierwszych sztukach v2](README.md#na-pierwszych-sztukach-v2)) i próba T6 „Tor zasilania stacji pilotażowej” na każdym egzemplarzu ([odbiór, próby](../../docs/spec/odbior.md#próby)).

Wymagania i progi są w specyfikacji, a ten plan mówi tylko, jak i w jakiej kolejności je sprawdzić. Wiersze T6, tabelę [stanów zasilania 12 V](../../docs/spec/elektronika.md#stany-zasilania-12-v) i listę pomiarów z README płytki ten plan przywołuje, a nie przepisuje.

## Przed płytką v2

Część stałych da się zmierzyć już teraz, bez płytki v2. Wyniki trafiają do `firmware/src/cells.h` przed pierwszym uruchomieniem v2, więc próby 9 i 10 sprawdzają już poprawione stałe.

| Pomiar | Na czym | Do czego |
|---|---|---|
| sprawność LTC3115-1 przy 3,3 V: 30, 60 i 150 mA przy 4,0, 6,0 i 7,3 V | [płytka testowa przetwornicy](../przetwornica-3v3/README.md#pomiar) | `EFFICIENCY_PERCENT` (dziś 78%), Z11 w [projekcie zasilania](../r02/zasilanie.md) |
| start ESP32-S3 i panelu z Burst Mode przy 4 V na wejściu | płytka testowa i L0 pinem 3V3 do VOUT, bez USB ([opis](README.md#przed-ścieżkami-i-zamówieniem)) | czy PWM od startu (`CONVERTER`), zanim wejdzie do płytki |
| pobór DevKitC przez 3V3 bez USB, w pracy i w lekkim uśpieniu (`NAP`) | jedna DevKitC z zasilacza laboratoryjnego | `AWAKE_UA` i `SLEEP_UA` (dziś 45 i 3 mA), decyzja o R24 |

## Przyrządy

- zasilacz laboratoryjny 0–15 V z ograniczeniem prądu (wejście ogniw i wejście 12 V);
- zasilacz do 36 V na 24 V, 33 V i odwrotną polaryzację do 33 V (próba 12);
- dwa multimetry, w tym jeden z zakresem µA (prąd w gałęzi ogniw, stan wyłączony);
- oscyloskop (V_AA po nadawaniu, +3V3 i PWM_SYNC, KILL, INT, EXTCOMIN);
- laptop z aplikacją stanowiska i portem diagnostyki; ładowarka USB bez danych;
- komplety ogniw Li-FeS2 AA: dwa świeże z różnych partii i jeden zużyty do około 4,4 V pod obciążeniem;
- do ustalenia przed próbą 12: przekaźnik sterowany skryptem do serii zaników (0,2–5 s, po 10 razy, 100 odcięć), źródło ujemnego impulsu do −53,3 V i grzanie do 45 i 60 °C (komora albo osłona z grzałką i termometrem).

## Zasady

- Sztuki mają numery 1 i 2 na sitodruku albo naklejce. Każdy wynik podaje numer sztuki.
- Na porcie diagnostyki zapis do pliku przez całą próbę. Podłączony laptop wstrzymuje czuwanie (powód `usb`), więc w próbach poboru i w próbie 10 odczyt jest krótki i rzadki albo dopiero na końcu (`LOG`, pierścień zdarzeń `power`).
- Dowody idą do `hardware/plytka-v2/evidence/<próba>-RRRR-MM-DD.md`: osoba, data, przyrządy, numer sztuki, wersja obrazu z `INFO`, przebieg, wynik, odchylenia. Obok są surowe logi.
- Kolejność: próby 1–11 na obu sztukach, potem próba 12 najpierw na sztuce 1. Próby z odwrotną polaryzacją, 33 V i ujemnym impulsem mogą uszkodzić płytkę, więc idą na końcu, po zapisaniu wyników czynności.
- Każdy wynik poza kryterium zapisuje się, zanim zmieni się program albo płytkę. Wynik rozstrzyga poprawkę zapisaną przy pomiarze w README płytki albo w tabeli [Co zmienia wynik](#co-zmienia-wynik).

## Próby

| # | Próba | Przebieg | Kryterium | Zapis |
|---|---|---|---|---|
| 1 | Pierwsze włączenie | bez DevKitC i Wio w gniazdach (J5/J6, J8/J9): rezystancja VSYS, +3V3 i VCTL do masy; zasilacz na wejście ogniw 6,0 V z limitem 300 mA (prąd włączania około 250 mA, [README](README.md#na-pierwszych-sztukach-v2)), przycisk włączenia; potem bez ogniw 13 V na J2 (łącznik załącza przy 11,6–12,3 V, a samo podłączenie włącza stację zboczem ON około 9 V, bez przycisku) | brak zwarć; po włączeniu +3V3 3,2–3,4 V, VSYS i VCTL zgodne z [torem zasilania](README.md#tor-zasilania); podłączenie 13 V włącza stację samo; przytrzymanie 5–19 s wyłącza bez MCU; prąd w stanie wyłączonym zapisany | napięcia, prądy, czas przytrzymania; `uruchomienie-RRRR-MM-DD.md` |
| 2 | Program i piny | pierwsze wgranie `pio run -e v2 -t upload` przez złącze USB DevKitC, zanim moduł trafi do gniazd (czysty moduł nie ma okna 10 s po starcie); potem DevKitC i Wio w gniazdach, następne wgrania przez gniazdo USB-C płytki w oknie 10 s po starcie; złącze USB DevKitC przy włożonym module tylko przy odłączonym zasilaniu stacji ([elektronika](../../docs/spec/elektronika.md)), bo inaczej szynę 3V3 zasilają dwa źródła; `INFO`, `RADIO`, `FRAM`, `POWER`, `STANDBY`, `SCREEN` | `radio_ok`, `fram_ok`, `journal_ok` `true`; `fw` `v2-0.8` albo nowszy; ekran i przyciski działają; `POWER` ma `samples` > 0 po minucie | wyjścia poleceń |
| 3 | Dokładność pomiaru | ogniwa: 13 V na J2 (bez 13 V średnia poniżej 4,0 V wyłącza stację), zasilacz na wejściu ogniw 4,0, 4,4, 5,0, 6,0 i 7,3 V; 12 V: zasilacz ogniw 6,0 V (bez ogniw przy niskim 12 V stacja nie ma 3,3 V, a dzielnik 12 V działa tylko przy włączonej stacji), na J2 8,0, 10,5, 12,0, 12,4, 14,8, 16, 24 i 33 V (zakres ADC do 36 V); przy każdym napięciu woltomierz na zaciskach i `POWER` (`mv_aa_last`, `mv_12v`) oraz `VTEST` po co najmniej 2 min | błąd każdego odczytu wobec woltomierza ≤2% (cel z [odbioru](../../docs/spec/odbior.md#próby)) | tabela: napięcie, woltomierz, odczyt, błąd; `pomiar-RRRR-MM-DD.md` |
| 4 | Źródło i progi łącznika | zasilacz ogniw 6,0 V i 12 V na J2; 12 V w dół od 13 V co 0,1 V do odcięcia i w górę do załączenia, krokiem co 2 min (źródło program ocenia z ostatniego pomiaru 12 V, co minutę); to samo od 16 V w górę do OVP i z powrotem do ponownego załączenia; po każdym kroku `POWER`, ekran i napięcie VSYS (równe ogniwom bez diody albo 12 V) | progi łącznika według [stanów zasilania 12 V](../../docs/spec/elektronika.md#stany-zasilania-12-v) i [elektroniki](../../docs/spec/elektronika.md#zasilanie-stacji); każdy krok, w którym `source` nie zgadza się ze stanem łącznika na VSYS, zapisany ([niżej](#do-rozstrzygnięcia-w-próbie-4)) | napięcia odcięcia, załączenia, OVP i powrotu po OVP każdej sztuki, `POWER`; `progi-RRRR-MM-DD.md` |
| 5 | Alarmy zasilania | przy pracy z ogniw (12 V odłączone, 0 V) podłączenie 9,0 V, 11,0 V i 24 V, za każdym razem od 0 V i z napięciem ustawionym przed podłączeniem (podłączenie poniżej 11,5 V nie załącza łącznika, [stany zasilania 12 V](../../docs/spec/elektronika.md#stany-zasilania-12-v)); 12 V 13 V bez ogniw; potem z 13 V odłączonym zasilacz ogniw w dół do 4,3 V i z powrotem do 4,7 V, każdy krok co najmniej 6 min (alarm ogniw liczy się ze średniej z 5 pomiarów); alarm po OK trzymany co najmniej 16 min; przy każdym stanie ekran, dioda, brzęczyk, PRZEKAZANIE ZMIANY, `POWER`, zdarzenie `power` w aplikacji stanowiska, `LOG` | 0 V: bez alarmu; 9,0 i 11,0 V: `odlaczone_12v`; 24 V: `za_wysokie_12v`; 13 V bez ogniw: `wymien_ogniwa`; poniżej 4,4 V: `wymien_ogniwa`, po OK przypomnienie co 15 min, zejście przy 4,6 V; alarmy 12 V bez przypomnienia; OK wycisza, dioda i wpis trwają do usunięcia przyczyny; każda zmiana daje jedno zdarzenie `power` | zdjęcia ekranu, `POWER`, `LOG`, eksport zdarzeń; `alarmy-RRRR-MM-DD.md` |
| 6 | Pomiar po nadawaniu | prawdziwe ogniwa: komplet około 4,8 V pod obciążeniem (powyżej progu zejścia alarmu 4,6 V), bez 12 V, zimne (lodówka, jeśli to możliwe; inaczej w temperaturze pokojowej z adnotacją); oscyloskop na zaciskach ogniw (J1; dzielnik pomiaru jest podłączony tylko na czas pomiaru) i PWM_SYNC; tryb przygotowania, `TXPKT 2 255` (seria bez `CONDUCTED` ma limit czasu, [polecenia](../../firmware/docs/polecenia.md)) | napięcie ogniw wraca do wartości sprzed nadawania przed upływem 2 s od końca ramki; `alarm` nie zmienia się od samego nadawania | przebiegi oscyloskopu, `POWER` przed i po |
| 7 | Przetwornica przy nadawaniu | zasilacz ogniw 4,4 V i 4,05 V (najgorszy przypadek z [README](README.md#przed-ścieżkami-i-zamówieniem)), bez 12 V; włączenie stacji przy każdym z tych napięć; oscyloskop na +3V3 i PWM_SYNC; tryb przygotowania, `TXPKT 2 255` w `CONVERTER auto`, `pwm` i `burst` | +3V3 ≥3,2 V przy nadawaniu z 4,4 V ([T6 „Tor zasilania”](../../docs/spec/odbior.md#próby)); przy 4,05 V start i nadawanie bez spadku do progu nadzorcy FRAM 2,7 V; PWM_SYNC wysoki przed pierwszym symbolem ramki; spadek i tętnienia w trzech trybach zapisane | przebiegi, `CONVERTER`; `przetwornica-RRRR-MM-DD.md` |
| 8 | Wyłączanie | naciśnięcie wyłącznika 0,5, 1,5 i 2,5 s w pracy i w czuwaniu; włączenie z przytrzymaniem przycisku; start z zasilaczem ogniw 3,9 V bez 12 V; Q11 odlutowany na sztuce 1 (potem wraca); oscyloskop na INT i KILL | 0,5 i 1,5 s nic nie robią; 2,5 s: `wylaczanie`, `mozna_wyjac` i brak zasilania; przytrzymanie przy włączaniu nie wyłącza; 3,9 V: wyłączenie zaraz po pierwszym pomiarze, `LOG` z powodem `cells`; bez Q11: `nie_wylaczona`, jeden wpis w `LOG`, KILL co 5 s, a przytrzymanie wyłącznika 5–19 s wyłącza stację; po każdym wyłączeniu ponowne włączenie bez utraty kolejki i zegara | przebiegi INT i KILL, `LOG`, `SCREEN`; `wylaczanie-RRRR-MM-DD.md` |
| 9 | Stałe szacunku godzin | amperomierz w szereg z zasilaczem ogniw 6,0 V, bez 12 V: praca bez uśpienia (`PREP 1`), czuwanie bez ruchu (udział z `STANDBY`), nadawanie (tryb przygotowania, `EMC 6 255` jak w [pomiarze prądu Wio](../xiao-wici/evidence/prad-wio-2026-11-17.md)); potem woltomierz na zaciskach świeżego i zużytego kompletu z obciążeniem i bez niego | prąd z ogniw w każdym stanie zapisany wobec stałych z [opisu szacunku](../../firmware/docs/prototyp-l0-i-xiao.md#szacunek-godzin-pracy-z-ogniw); `avg_mw` w `POWER` po co najmniej 2 h czuwania (średnia wykładnicza z wagą 1/30) wobec V × I z mierników; bez progu zaliczenia: stałe w `cells.h` zmieniają się na zmierzone | prądy, `POWER`, `STANDBY`; `stale-ogniw-RRRR-MM-DD.md` |
| 10 | Szacunek na ogniwach | świeży komplet, praca jako przekaźnik przy ruchu jak w [„Praca na ogniwach”](../../docs/spec/odbior.md#próby), w temperaturze pokojowej, do `wymien_ogniwa`, potem do wyłączenia; `hours` z ekranu raz dziennie i co 2 h ostatniego dnia; potem wymiany: (a) przy 13 V na J2 ten sam komplet wyjęty i włożony z powrotem w pracy; (b) świeży komplet po wyłączeniu, bez 12 V; (c) świeży komplet po wyłączeniu z ogniw, włożony przy podłączonym 13 V | ≥48 h na ogniwach (minimum pilotażu); od `wymien_ogniwa` do wyłączenia ≥1 h; różnica między `hours` po pierwszej dobie a rzeczywistym czasem do `wymien_ogniwa` zapisana; (a) nie zeruje licznika; (b) i (c) zerują (`new_sets`) | `hours` w czasie, `POWER` i `LOG` na końcu, liczniki `STANDBY`; `ogniwa-48h-RRRR-MM-DD.md` |
| 11 | Czuwanie, USB i ZAMKNIJ ZDARZENIE | punkty 1–7 z [Pętli czuwania, co wymaga pomiaru](../../firmware/docs/prototyp-l0-i-xiao.md#pętla-czuwania-v2); ZAMKNIJ ZDARZENIE z menu stacji z kolejką i skrzynką pełną | kryteria punktów 1–7; po ZAMKNIJ ZDARZENIE kolejka i skrzynka puste, tożsamość i klucze zostają ([„Zamknięcie zdarzenia”](../../docs/spec/odbior.md#próby), część stacji) | `STANDBY`, `INFO`, `SCREEN`, `STORE`; `czuwanie-RRRR-MM-DD.md` |
| 12 | Tor zasilania T6 | cały wiersz [„Tor zasilania stacji pilotażowej”](../../docs/spec/odbior.md#próby), wszystkie wiersze [stanów zasilania 12 V](../../docs/spec/elektronika.md#stany-zasilania-12-v) i pomiary z [Na pierwszych sztukach v2](README.md#na-pierwszych-sztukach-v2) (C50, EN/UVLO, prąd wyłączenia, +3V3 od tyłu, ujemne napięcie na GPIO4 i GPIO5, KILL i RUN na ciepło, upływ D7, próg ON, impuls przy 16 V) | kryteria wiersza T6 i README płytki, na każdej sztuce | raport na sztukę; `tor-zasilania-<n>-RRRR-MM-DD.md` |

Warunek 2 przed pracą w terenie spełniają próby 3–10 na obu sztukach, a po nim znaki ◆ znikają z karty obsługi ([odbiór](../../docs/spec/odbior.md#minimum-pilotażu)). Warunek 3 spełnia ZAMKNIJ ZDARZENIE w próbie 11.

## Do rozstrzygnięcia w próbie 4

Program rozpoznaje źródło po napięciu 12 V, a nie po stanie łącznika ([pomiar](../../firmware/docs/prototyp-l0-i-xiao.md#pomiar-ogniw-i-12-v)). Progi programu (10,5, 12,4 i 17 V) leżą na skrajach pasm z [elektroniki](../../docs/spec/elektronika.md#zasilanie-stacji), więc w trzech pasmach program może się nie zgadzać z łącznikiem:

- **załączenie:** łącznik załącza przy 11,6–12,3 V, a program uznaje 12 V dopiero od 12,4 V. Przy pracy z ogniw i źródle 11,6–12,4 V (np. akumulator 12,2 V) stacja pracuje z 12 V, a program pokazuje ogniwa i `odlaczone_12v`, liczy energię z ogniw, a przy słabych ogniwach (średnia poniżej 4,0 V) wyłącza stację, która ma zasilanie. To pasmo leży w zakresie pracy 11,3–16 V;
- **odcięcie:** łącznik odcina przy 10,6–11,3 V, a program uznaje ogniwa dopiero poniżej 10,5 V. Gdy sztuka odcina np. przy 11,0 V, przy 10,5–11,0 V ekran pokazuje 12 V bez `odlaczone_12v`, energia z ogniw się nie liczy, a wyłączenie przy 4,0 V nie zadziała;
- **OVP:** próg OVP ma tolerancję 16,32–17,30 V ([Na pierwszych sztukach v2](README.md#na-pierwszych-sztukach-v2)), a program ma 17 V. Gdy sztuka odcina przy 16,5 V, przy 16,5–17 V program pokazuje 12 V bez alarmu. Gdy odcina przy 17,2 V, przy 17,0–17,2 V pokazuje `za_wysokie_12v`, choć wejście jeszcze działa.

Próba 4 mierzy rzeczywiste progi obu sztuk. Pasmo załączenia leży w zwykłej pracy, więc decyzja właściciela jest potrzebna niezależnie od wyniku. Możliwe kierunki: rozpoznanie po napięciu ogniw (przy pracy z 12 V ogniwa nie są obciążone, więc ich napięcie rośnie), progi programu na drugim skraju pasm albo pozostawienie jako znane ograniczenie. Pomiar VSYS wymagałby zmiany płytki: wolnego pinu ADC nie ma ([przydział pinów](README.md#przydział-pinów)).

## Co zmienia wynik

| Wynik | Zmiana |
|---|---|
| sprawność, prądy pracy, czuwania i nadawania (przed płytką i próba 9) | stałe w `firmware/src/cells.h`, tabela stałych w [opisie szacunku](../../firmware/docs/prototyp-l0-i-xiao.md#szacunek-godzin-pracy-z-ogniw), model energii w `software/reference/obliczenia.py` |
| napięcie świeżego i zużytego kompletu (próba 9) | `FRESH_STEP_MV` (dziś 0,4 V) i `ABSENT_MV` |
| V_AA po nadawaniu (próba 6) | przerwa po nadawaniu w `power.h` (dziś 2 s) |
| błąd ADC powyżej 2% (próba 3) | poprawka przelicznika w `power.h` albo dzielnika na płytce (wariant z README) |
| progi łącznika (próba 4) | decyzja z [Do rozstrzygnięcia w próbie 4](#do-rozstrzygnięcia-w-próbie-4) |
| +3V3 poniżej 3,2 V przy nadawaniu albo przy starcie (próba 7) | PWM od startu albo wcześniej przed nadawaniem (`sx1262_link.cpp`) |
| szacunek po dobie różni się od rzeczywistego czasu (próba 10) | stałe albo waga średniej (`AVERAGE_WEIGHT`); różnica zapisana w opisie szacunku |
| pomiary z README płytki (próba 12) | poprawki zapisane przy każdym pomiarze w [Na pierwszych sztukach v2](README.md#na-pierwszych-sztukach-v2) |

Licencja dokumentacji: CC-BY-4.0 według [LICENSE.md](../../LICENSE.md).

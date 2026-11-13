# L0: odbiór dwóch płytek i pierwsze uruchomienie programu stacji

Procedura dla właściciela, po odbiorze dwóch zmontowanych prototypów L0 od wykonawcy. P001 przeszła u wykonawcy pełne próby (2026-11-01). P002 jest zmontowana, ale bez prób. Instrukcja dla wykonawcy, z tabelą usterek, jest w [MONTAZ-I-TESTY.md](MONTAZ-I-TESTY.md); kody prób w nawiasach (np. E3) odsyłają do niej.

Ta procedura pomija pomiary oscyloskopem. Wykonawca zrobił je na P001, a P002 ma ten sam projekt. P002 ma jednak własny, ręcznie lutowany adapter radia, a długość jego przewodów wpływa na całą magistralę danych ekranu, pamięci i radia. To przyjęte ryzyko: P002 sprawdza się pod tym względem tylko działaniem, w 15-minutowej próbie wszystkiego naraz (etap 2, krok 12).

Etapy:

- **0.** Przygotowanie laptopa i partnera radiowego.
- **1.** P001: krótkie sprawdzenie po transporcie, około 30 minut. Przy okazji sprawdza laptop i narzędzia na płytce, o której wiadomo, że działa.
- **2.** P002: pełny odbiór programem diagnostycznym, około 2,5 godziny.
- **3.** Program stacji na obu płytkach i pierwsza łączność między nimi, około 1 godziny. **Etap 3 czeka na odpowiedź sesji oprogramowania** (początek etapu 3).

Nie przechodź do następnego etapu, dopóki poprzedni nie jest zaliczony.

## Zasady

- **STOP** oznacza: odłącz przewód USB od płytki, nic nie poprawiaj sam, zrób zdjęcie i zapisz wynik ostatniego polecenia do analizy. Zawsze STOP, gdy coś parzy, pachnie spalenizną, dymi albo port USB pojawia się i znika co kilka sekund.
- **ZAPISZ** oznacza: zapisz wynik w pliku `~/WICI-L0/wyniki.md` (wartość, nie tylko „OK”). Logi i pliki JSON narzędzia zapisują same w `~/WICI-L0/results/`.
- Płytka leży na suchym, nieprzewodzącym podłożu (drewno, karton, mata). Pod płytką nie może być narzędzi, śrubek ani skrawków drutu.
- Zasilanie tylko przez gniazdo micro-USB DevKitC z napisem **USB**. Drugie gniazdo, **UART**, nie ma konsoli tego programu. Przewód musi przenosić dane, a nie tylko ładować. Nic innego nie zasila płytki.
- Zworki: założone na JP1, JP2 i na listwie przy module radiowym Wio (punkt pomiaru prądu radia). Na JP3, jeśli jest wlutowana, zworki nie ma. Bez zworki przy Wio nie wolno włączać zasilania: radio zasilałoby się wtedy przez linie sygnałowe.
- Antena jest zatrzaśnięta w gnieździe Wio przed każdym włączeniem. Radio nadające bez anteny może się uszkodzić.
- **DevKitC zostaje w gniazdach.** Wchodzi także obrócony o 180°, a wtedy zwiera swoje 3,3 V do masy. Wyjmuje się go tylko na moje polecenie.
- Panel ekranu wisi na taśmie, więc płytki nie odwraca się przy włączonym zasilaniu. Wszystkie pomiary są od góry.
- Płytkę trzyma się za krawędzie.

## 0. Przygotowanie

### Laptop

W Terminalu, jeden raz:

```bash
mkdir -p ~/WICI-L0 && cd ~/WICI-L0
```

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r ~/Work/WICI/implementacja/hardware/l0-diagnostic/requirements.txt
```

Folder `~/WICI-L0` jest poza repozytorium, więc kopie pamięci, logi i środowisko Pythona nie trafią przypadkiem do commita.

Wszystkie polecenia niżej używają tego jednego środowiska, także do budowania i wgrywania programów. Środowiska `.venv-pio` w repozytorium i `.venv` w `hardware/radio-pair` wskazują na stare położenie repozytorium i nie działają. Python musi być w wersji 3.14 (jest z Homebrew); PlatformIO dla programu stacji odrzuca 3.15. Pierwsze budowanie każdego programu pobiera narzędzia i trwa kilka minut. Jeśli pierwsze polecenie budujące skończy się `FAILED`, powtórz je raz; drugi `FAILED`: STOP.

W każdym nowym oknie Terminala najpierw:

```bash
cd ~/WICI-L0 && L0D=~/Work/WICI/implementacja/hardware/l0-diagnostic
```

Lista portów USB (pokazuje, pod jaką nazwą zgłosiła się płytka):

```bash
.venv/bin/python $L0D/tools/radio_test.py --list
```

Nazwy mają postać `/dev/cu.usbmodem…`. Niżej `PORT`, `PORT_P001`, `PORT_P002` i `PORT_XIAO` zastępujesz nazwą z tej listy. Nazwa może się zmienić po każdym resecie, wgraniu programu albo przełożeniu przewodu, więc wtedy sprawdź listę jeszcze raz.

Pojedyncze polecenie do płytki z programem diagnostycznym:

```bash
.venv/bin/python $L0D/tools/diagnose.py --port PORT --command INFO
```

W miejsce `INFO` wpisuje się inne polecenia: `STATUS`, `RDID`, `LCD 2`, `LED 1` itd. Polecenia z odstępem bierze się w cudzysłów, na przykład `--command "LCD 2"`. Narzędzie wypisuje odpowiedź płytki. Linia `NIEZALICZONE / NIEUKOŃCZONE` oznacza błąd.

Konsola, czyli rozmowa z płytką na żywo (potrzebna przy przyciskach i ciszy radiowej):

```bash
.venv/bin/pio device monitor --port PORT --baud 115200 --echo
```

Polecenie wpisuje się wielkimi literami (`STATUS`, nie `status`) i zatwierdza Enterem. Konsolę zamyka Ctrl+C. Przed uruchomieniem `diagnose.py` albo `radio_test.py` na tym samym porcie konsolę trzeba zamknąć.

### Partner radiowy XIAO

Próby radia potrzebują partnera: jednego z dwóch zestawów XIAO, z anteną, z programem `pair-0.4`. Program stacji `xiao`, który ma teraz, wróci na niego na końcu etapu 3. Zestaw XIAO i tak traci tożsamość przy każdym odłączeniu zasilania, więc nic się nie traci.

```bash
cd ~/Work/WICI/implementacja/hardware/radio-pair && ~/WICI-L0/.venv/bin/pio run --target upload --upload-port PORT_XIAO; cd ~/WICI-L0
```

Program stacji na XIAO zwykle nie daje się nadpisać bez trybu wgrywania, więc gdy wgranie nie rusza: przytrzymaj przycisk B (BOOT) na XIAO, podłącz USB, puść BOOT, sprawdź listę portów (nazwa może być nowa) i spróbuj jeszcze raz. Sprawdzenie: otwórz konsolę na `PORT_XIAO` i wpisz `INFO`. Odpowiedź ma się zaczynać od `INFO pair-0.4`, a liczba po MAC ma być `1`. `0` albo `ERR begin -2` znaczy, że XIAO nie widzi radia: odłącz USB i dociśnij moduł Wio na złączu XIAO. ZAPISZ.

### Oznaczenie płytek

Oznacz płytki markerem jako P001 i P002, na przykład przy krawędzi. Jeśli nie wiesz, która jest która, rozstrzygnie to MAC w pierwszym `INFO`, porównany z raportem wykonawcy.

### Przyrządy i punkty pomiarowe

Wystarczy multimetr (2D15P w trybie miernika napięcia i rezystancji). Oscyloskop nie jest potrzebny.

Pomiary robi się od góry w pustych otworach **J1**. To rząd ośmiu otworów z napisem J1 (gniazdo Arduino, którego w L0 nie obsadzono). Pierwszy otwór ma kwadratowy pad, pozostałe okrągłe. Licząc od kwadratowego:

- **czwarty otwór (J1.4):** +3,3 V;
- **piąty (J1.5):** +5 V;
- **szósty (J1.6):** masa.

Sondę wkłada się w otwór, nie przykłada obok. **Napięcia mierzy się tak:** przy odłączonym USB włóż obie sondy w otwory, podłącz USB, odczytaj wynik, odłącz USB i dopiero wtedy wyjmij sondy. Sonda, która ześlizgnęłaby się na sąsiedni otwór pod napięciem, mogłaby zewrzeć +5 V z +3,3 V.

Jeśli miernik pokaże wynik z minusem, sondy są zamienione: liczy się wartość bez znaku.

## 1. P001: sprawdzenie po transporcie

1. **Oględziny bez zasilania.** Przewody między Wio a płytką są całe i przylutowane, antena zatrzaśnięta, zworki na miejscu, DevKitC wsunięty równo w oba gniazda. Delikatnie potrząśnij płytką nad białą kartką: nic nie może wypaść (kulka cyny, skrawek drutu). Zrób zdjęcie płytki z góry i z dołu.
2. **Pomiary bez zasilania, jako wzorzec dla P002.** Zakres rezystancji, czarna sonda w J1.6:
   - czerwona w J1.4 (+3,3 V);
   - czerwona w J1.5 (+5 V);
   - czerwona na wierzchu pinu DevKitC z napisem **9** na module: rezystor resetu radia R12, około 1 kΩ.

   Wynik może przez kilka sekund rosnąć, bo ładują się kondensatory: zapisz wartość po 10 sekundach. ZAPISZ wszystkie trzy.
3. **Włączenie.** Podłącz USB do gniazda **USB** DevKitC. Po 20 sekundach lista portów ma pokazać nowy port.
4. **`INFO`.** Oczekiwane: `INFO l0-0.5 <MAC> 1 …`. MAC to identyfikator modułu DevKitC. Liczba zaraz po MAC musi być `1`: radio i pamięć FRAM odpowiadają, a sterowanie ekranem i brzęczykiem jest uruchomione. MAC porównaj z raportem wykonawcy. Inna wersja niż `l0-0.5`: STOP. ZAPISZ MAC i całą linię.
5. **`STATUS` i `RDID`.** `RDID` ma dać `FRAM_ID MB85RS4MT …`. Linia z `ERR` oznacza STOP.
6. **Napięcia,** sposobem z punktu „Przyrządy”, czarna sonda w J1.6. J1.4 (+3,3 V): 3,2–3,4 V. J1.5 (+5 V): 4,4–5,25 V; to napięcie z portu USB laptopa za diodą na DevKitC i zasila tylko brzęczyk, więc bywa niższe niż 5 V. Poza zakresem: STOP. ZAPISZ.
7. **Ekran.** Kolejno `--command "LCD 0"` (biały), `"LCD 1"` (czarny), `"LCD 2"` (szachownica), `"LCD 3"` (siatka), `"LCD 4"` (tekst). Każda plansza ma być pełna, bez pasów i brakujących pikseli. Zrób zdjęcie szachownicy.
8. **Dioda i brzęczyk.** `"LED 1"` (świeci), `"LED 0"`, `"BUZZ 1"` (wysoki ton), `"BUZZ 0"`.
9. **Przyciski.** Otwórz konsolę na `PORT_P001`. Naciśnij kolejno GÓRA, DÓŁ, OK, WSTECZ i przycisk przygotowania. Po każdym ma się pojawić linia `INPUT …`; kilka linii na jedno naciśnięcie jest normalne.
10. **Przełącznik CISZA.** Nadal w konsoli: `STATUS` w jednym położeniu przełącznika, potem w drugim. W położeniu CISZA ma być `silence=1`, w drugim `silence=0`. Sprawdź, czy położenie CISZA jest oznaczone markerem; jeśli nie, oznacz to, w którym `silence=1`. Zamknij konsolę.
11. **Radio z XIAO, 20 pakietów w każdą stronę,** około 3 minut. L0 i XIAO stoją 2–3 m od siebie, oba z antenami, CISZA wyłączona:

    ```bash
    .venv/bin/python $L0D/tools/radio_test.py --a PORT_P001 --b PORT_XIAO --version-a l0-0.5 --version-b pair-0.4 --count 20
    ```

    Oczekiwane: 40 linii `… OK` (po 20 z każdej strony), potem `Raport: …` i `WYNIK: PRÓBA SKRÓCONA - bez kwalifikacji`. Ten wynik jest poprawny: „bez kwalifikacji” znaczy tylko, że pełna próba ma 100 pakietów. Linia `BŁĄD`, `Test zatrzymany` albo `NEGATYWNY`: STOP. ZAPISZ ścieżkę raportu; siłę sygnału odczytam z niego.

Wszystko zaliczone: P001 przetrwała transport, a laptop, przewody i partner XIAO działają. Od teraz P001 jest wzorcem: gdy coś na P002 wygląda inaczej, porównujesz z P001.

## 2. P002: pełny odbiór

### Bez zasilania

1. **Oględziny,** jak w P001. Porównaj obie płytki obok siebie: te same elementy w tych samych miejscach, przewody Wio w tych samych punktach, DevKitC ustawiony tak samo (gniazda micro-USB w tę samą stronę). Luty błyszczące, bez kulek cyny między sąsiednimi pinami. Zdjęcia z góry i z dołu.
2. **Pomiary bez zasilania,** te same co w P001, krok 2:
   - J1.4 i J1.5 wobec J1.6: poniżej 100 Ω to zwarcie, STOP. Wynik wyraźnie niższy niż na P001 (na przykład o połowę) wyjaśnij przed włączeniem.
   - Pin **9** DevKitC wobec J1.6: około 1 kΩ, jak na P001. Kilka do 10 kΩ znaczy, że wykonawca nie wymienił R12; wtedy STOP, bo bez tego radio nie wystartuje.

   ZAPISZ.

### Pierwsze zasilanie

3. **10 sekund.** Podłącz USB, policz do dziesięciu, odłącz. Od razu dotknij palcem kolejno: modułu Wio, DevKitC, małych układów przy złączu ekranu. Nic nie może parzyć. Parzy: STOP.
4. **Minuta.** To samo przez minutę. Może być letnie, nic nie może parzyć.
5. **Który program jest na DevKitC.** Podłącz USB, odczekaj 20 sekund i wyślij `INFO`. Brak odpowiedzi (`Brak INFO z L0`) powtórz raz po kolejnych 20 sekundach.
   - Odpowiedź `INFO l0-0.5 …`: program jest wgrany, przejdź do kroku 7.
   - Inna odpowiedź albo dwa razy brak: krok 6.
6. **Wgranie programu diagnostycznego.** Najpierw kopia fabrycznej pamięci DevKitC (około 2 minut), potem wgranie ze źródeł:

   ```bash
   mkdir -p backups && .venv/bin/python -m esptool --chip esp32s3 --port PORT_P002 read_flash 0 0x800000 backups/P002-fabryczny.bin
   ```

   ```bash
   shasum -a 256 backups/P002-fabryczny.bin
   ```

   ```bash
   cd $L0D && ~/WICI-L0/.venv/bin/pio run -t upload --upload-port PORT_P002; cd ~/WICI-L0
   ```

   ZAPISZ sumę kontrolną kopii. Gdy port się nie pojawia albo wgranie nie rusza: przytrzymaj BOOT na DevKitC, naciśnij i puść RST, puść BOOT, sprawdź listę portów i powtórz. Po wgraniu naciśnij RST, odczekaj 20 sekund i wróć do kroku 5.

   Plik `images/l0-full.bin` w katalogu programu to stara wersja `l0-0.4`: nie wgrywaj go.
7. **`INFO`, `STATUS`, `RDID`** jak w P001. Liczba po MAC ma być `1`. Jest `0` albo pojawia się `ERR`: STOP; tabela w [MONTAZ-I-TESTY.md, „Diagnoza”](MONTAZ-I-TESTY.md#diagnoza) mówi, co to znaczy; zapisz wynik. ZAPISZ MAC.
8. **Napięcia** jak w P001: J1.4 3,2–3,4 V, J1.5 4,4–5,25 V. Porównaj z wynikami P001. ZAPISZ.

### Próby

9. **Restarty (E1).** Pięć razy przycisk RST na DevKitC i pięć razy odłączenie i podłączenie USB. Po każdym odczekaj 20 sekund, sprawdź listę portów, potem `INFO` i `STATUS`:
   - pierwsza liczba po MAC: `1`;
   - druga liczba (przyczyna restartu): `1` albo `0`. Na macOS samo otwarcie portu (każde `diagnose.py`, `radio_test.py`, konsola) restartuje płytkę przez USB, a ta wersja ESP-IDF zgłasza taki restart jako `0`; dlatego `0` jest normalne, a trzecia liczba zmienia się przy każdym poleceniu. Wartości od `4` do `9`: STOP;
   - trzecia (losowy numer startu): inna niż poprzednio;
   - w `STATUS` brak `ERR`.

   ZAPISZ dziesięć linii `INFO`.
10. **Ekran, dioda, brzęczyk, przyciski, CISZA (E5)** jak w P001, kroki 7–10. Dodatkowo `--command "PAUSE 10000"`: przez 10 sekund obraz ma zostać bez zmian.
11. **Pamięć FRAM z zachowaniem danych po wyłączeniu (E3).** Zapis całej pamięci, około 5 minut:

    ```bash
    .venv/bin/python $L0D/tools/diagnose.py --port PORT_P002 --fram-write 12345678
    ```

    Oczekiwane: pięć linii `FRAM_PASS … 0 …` (zero błędów) i `FRAM_DONE … WRITE`, bez `NIEZALICZONE`. Potem odłącz USB na co najmniej 60 sekund, podłącz, odczekaj 20 sekund, sprawdź port na liście i odczytaj bez zapisu:

    ```bash
    .venv/bin/python $L0D/tools/diagnose.py --port PORT_P002 --fram-verify 12345678
    ```

    Oczekiwane: `FRAM_PASS 4 0 …` i `FRAM_DONE … VERIFY`. Ta próba musi być przed krokiem 12, bo następna nadpisuje część pamięci.
12. **15 minut pracy wszystkiego naraz (E6).** Ekran, pamięć i radio dzielą jedną magistralę danych, więc to najważniejsza próba P002. XIAO 2–3 m od P002, CISZA wyłączona na P002:

    ```bash
    .venv/bin/python $L0D/tools/diagnose.py --port PORT_P002 --mixed --peer PORT_XIAO
    ```

    Przez cały czas plansze na ekranie mają się zmieniać bez pasów i zawieszeń; zerknij co kilka minut. Oczekiwane na końcu: 200 linii `… OK`, `WYNIK: POZYTYWNY` i `SPI + radio zakończone`. `BŁĄD`, `NEGATYWNY` albo `NIEZALICZONE`: STOP. ZAPISZ ostatnie linie.
13. **Radio P002 z P001, 100 pakietów w każdą stronę (R1, R2),** około 10 minut. Obie płytki po restarcie przyciskiem RST, 2–3 m od siebie, porty sprawdzone na liście:

    ```bash
    .venv/bin/python $L0D/tools/radio_test.py --a PORT_P002 --b PORT_P001 --version-a l0-0.5 --version-b l0-0.5 --count 100
    ```

    Oczekiwane: 200 linii `… OK` i `WYNIK: POZYTYWNY`. ZAPISZ ścieżkę raportu. Z raportu porównam siłę sygnału w obie strony: duża różnica wskazywałaby na błąd w przełączaniu nadawania i odbioru w adapterze. Próby nie powtarza się do skutku: każdy przebieg idzie do wyników.
14. **Blokada nadawania w ciszy (R3).** Dwie konsole w dwóch oknach Terminala: jedna na `PORT_P002`, druga na `PORT_P001`.
    - P002 w położeniu CISZA. W konsoli P002: `TX WICI-SILENCE-01`. Oczekiwane: `BLOCKED SILENCE`, a w konsoli P001 nic nie przychodzi.
    - P002 w drugim położeniu. W konsoli P002: `TX WICI-SILENCE-02`. W konsoli P001 ma się pojawić odbiór z tym tekstem.
    - P002 znów w położeniu CISZA. W konsoli P001: `TX WICI-SILENCE-03`. W konsoli P002 ma się pojawić odbiór: cisza blokuje nadawanie, nie odbiór.

    `ERR cooldown` to nie usterka: płytka pilnuje przerwy między nadaniami. Odczekaj kilka sekund i powtórz.

Wszystko zaliczone: P002 jest odebrana. Panelu ekranu nie przyklejaj. Jeśli wykonawca już go przykleił, nie próbuj go odklejać.

## 3. Program stacji na obu płytkach

**Pamięć po próbach diagnostycznych.** Próby zostawiają w całej FRAM wzór testowy, także w ostatnich 512 B, gdzie program stacji trzyma barierę migracji. Taką barierę uznaje za uszkodzoną, więc pierwszy start stacji jest bez dziennika: `"journal_ok":false`, `"store_ok":false`, dioda pamięci zgaszona, w logu `migration barrier corrupt or unavailable`. Na ekranie jest alarm pamięci, który nie znika sam. To jest spodziewane. Naprawia to ZNISZCZ DANE z panelu (krok 3). Działa to od programu z PR 210 (`8dd305f2` w `main`); sprawdzone 13.11.2026 na P001 i P002.

Płytki są w tym momencie sprawdzone, więc błąd na tym etapie to najpewniej błąd programu, a nie płytki. Wtedy zapisz pełną odpowiedź i przekaż ją sesji oprogramowania.

1. **Wersja programu.** Program buduje się z aktualnego `main`, w czystym repozytorium:

   ```bash
   cd ~/Work/WICI/implementacja && git branch --show-current && git status --short && git log -1 --format=%h
   ```

   Oczekiwane: `main`, brak listy zmienionych plików, skrót commita nie starszy niż `8dd305f2` (wcześniejszy program nie dopuszcza ZNISZCZ DANE przy uszkodzonej barierze). ZAPISZ skrót. Inna gałąź albo zmienione pliki: wyjaśnij przed budowaniem.
2. **Wgranie, najpierw na P001:**

   ```bash
   cd ~/Work/WICI/implementacja/firmware && ~/WICI-L0/.venv/bin/pio run -e l0 -t upload --upload-port PORT_P001; cd ~/WICI-L0
   ```

   Po wgraniu płytka zgłasza **dwa** porty USB. Konsola to port kończący się na `1` (P001: `/dev/cu.usbmodem80456B2D2FB81`, P002: `/dev/cu.usbmodem80456B2F11501`), port kończący się na `3` służy do danych laptopa. Otwórz konsolę:

   ```bash
   .venv/bin/pio device monitor --port PORT_P001 --baud 115200 --echo
   ```

   Po otwarciu konsoli program sam wysyła linie JSON z `INFO`, `RADIO`, `FRAM` i `JOURNAL`. Nic nie przychodzi także po wpisaniu `INFO`: zamknij konsolę i otwórz drugi port.
3. **ZNISZCZ DANE.** Na panelu P001:
   - alarm pamięci: OK;
   - wybór języka: OK;
   - poczekaj na alarm BRAK ŁĄCZNOŚCI (kilkanaście sekund) i naciśnij OK;
   - ekran główny: OK (otwiera się menu);
   - DÓŁ trzy razy do STAN, OK;
   - DÓŁ do USŁUGI, OK;
   - DÓŁ do ZNISZCZ DANE, OK;
   - GÓRA, DÓŁ, GÓRA, OK.

   Każdy inny przycisk zaczyna sekwencję od nowa, WSTECZ wychodzi. Stacja sama się restartuje; konsola może zgubić port, wtedy otwórz ją jeszcze raz. Oczekiwane w `INFO`: `"journal_ok":true`, `"store_ok":true`, dioda pamięci świeci, w logu `store: ok` albo `store: new`. `"journal_resets":1` jest spodziewane (resztki wzoru poniżej obszaru kasowania): przed pierwszym nadaniem stacja odczeka najdłuższy możliwy dług ciszy. Po restarcie ekran „STACJA NIE MA TWOJEGO ADRESU…” jest spodziewany: stacja nie jest skonfigurowana. ZAPISZ `INFO` przed i po. Bez `journal_ok` i `store_ok` po kasowaniu: STOP, przekaż log sesji oprogramowania.
4. **Start stacji (próba 1 z [opisu prototypu](../../firmware/docs/prototyp-l0-i-xiao.md#stacja-l0-l0)).** W konsoli kolejno:
   - `INFO`: `radio_ok`, `p1_ok`, `fram_ok`, `journal_ok` mają wartość `true`, `profile` ma wartość `"LoRa"`;
   - `RADIO`: `version` to `SX1261 V2D 2D02`, `device_errors` zero, `busy` `false`, `busy_timeouts` 0; `rxen` `true`, bo stacja stoi w odbiorze (`state` `RX`); po `RESET` jest `false`, a `device_errors` `0x0020` (start oscylatora przed konfiguracją) znika po `CONFIG`;
   - `VERIFY`: `mismatches` 0;
   - `FREQ`, `SLEEP` (`boosted` `true`), `RESET`, `CONFIG`: zapisz odpowiedzi; po `CONFIG` `INFO` ma znów pokazać `p1_ok` `true`.

   Ekran ma pokazywać ekran stacji, bez alarmu „RADIO: AWARIA”. Zrób zdjęcie. Odpowiedź niezgodna z oczekiwaną: przerwij etap, nie wgrywaj programu na P002 i zapisz zapis konsoli do analizy.
5. **To samo na P002** (kroki 2–4), dopiero gdy P001 przeszła krok 4.
6. **Łączność między płytkami (próba 2).** Obie płytki 2–3 m od siebie, CISZA wyłączona, konsola na każdej:
   - na obu tryb przygotowania, potrzebny do poleceń pomiarowych: przytrzymaj PRZYGOT przez 3 sekundy. Krótki pisk to przełączenie, długi to odmowa. Przytrzymanie przełącza tryb, więc sprawdź `BTN` (`"prep":true`) i nie trzymaj drugi raz na tej samej płytce. `PREP 1` z konsoli też działa, ale czeka na OK, a OK może trafić do menu zamiast do potwierdzenia;
   - na P002 (odbiornik) `RX 20`;
   - na P001 (nadajnik) `TXPKT 11 20`, czyli 11 ramek po 20 bajtów. Następną serię wolno wysłać po około 10 sekundach (`INFO` pokazuje pozostały czas w `tx_wait_ms`). Odpowiedź `silence debt pending` znaczy, że seria poszła za wcześnie: odczekaj i powtórz. `busy: STOP first`: wpisz `STOP` i powtórz. Wyślij 9 serii, razem 99 ramek;
   - na P002 `RXPER`: `rx_ok` 99 (dopuszczalna 1 strata), `missing` 0 albo 1, `rx_bad` 0. Pojedyncze `rx_bad` przy `rx_ok` 99 i `missing` 0 to obca ramka innej długości (najpewniej własna ramka Reticulum stacji), a nie strata. `reordered` 8 jest poprawne, bo każda seria numeruje ramki od zera. ZAPISZ całą odpowiedź;
   - potem odwrotnie: `RX 20` na P001, serie na P002, `RXPER` na P001.
7. **Cisza (próba 3).** Na odbiorniku `RX 20`. Nadajnik w położeniu CISZA: `TXPKT 11 20` ma dać błąd `radio silence`, a `RXPER` na odbiorniku `rx_ok` 0. Przełącznik z powrotem, znów `RX 20` i `TXPKT 11 20`: stacja sama odczeka około 10 s (`tx_wait_ms` w odpowiedzi), potem `rx_ok` 11. Na koniec `PREP 0` na obu płytkach (bez przycisku) i `BTN`: `"prep":false`, `"silence":false`.
8. **Partner XIAO z powrotem na program stacji:**

   ```bash
   cd ~/Work/WICI/implementacja/firmware && ~/WICI-L0/.venv/bin/pio run -e xiao -t upload --upload-port PORT_XIAO; cd ~/WICI-L0
   ```

   Z obrazu `pair` wgrywa się bez przycisku B. Potem XIAO ma nowe porty (`/dev/cu.usbmodem44B176AD28A01` to konsola); `INFO` ma pokazać `"rns_state":"running"` i `"store_ok":true`.

### Powrót do programu diagnostycznego

Gdy trzeba wrócić z programu stacji do diagnostycznego: przytrzymaj BOOT na DevKitC, naciśnij i puść RST, puść BOOT, sprawdź listę portów (nazwa będzie inna), potem:

```bash
cd $L0D && ~/WICI-L0/.venv/bin/pio run -t upload --upload-port PORT; cd ~/WICI-L0
```

## 4. Wyniki

Odbiór 13.11.2026, wszystko zaliczone:

- P001 po transporcie: rezystancje, zasilanie, panel, przyciski, CISZA, radio z XIAO 20/20 (około −42 dBm);
- P002: FRAM bez błędów, próba mieszana 4464 cykle bez błędów, radio 100/100, łączność z P001 100/100 w obie strony, cisza blokuje nadawanie;
- program stacji z PR 210 na obu: ZNISZCZ DANE naprawia pamięć po diagnostyce (`journal_resets` 1), próba 1 bez niezgodności, łączność 99/99 w obie strony (jedno `rx_bad` na P001, obca ramka), cisza blokuje nadawanie, po jej zdjęciu 11/11;
- XIAO z powrotem na programie stacji.

Logi i raporty JSON z odbioru są w [evidence/odbior-2026-11-13/](evidence/odbior-2026-11-13/README.md), bez kopii fabrycznej pamięci i bez danych wykonawcy.

Dalsze próby programu stacji mają własne procedury i wymagają innego sprzętu:

- próby 4–8 z [opisu prototypu](../../firmware/docs/prototyp-l0-i-xiao.md#stacja-l0-l0) (moc, częstotliwość, limit czasu nadawania): tłumik, miernik mocy, odbiornik SDR;
- [krok 4 z radiem RNode](../../firmware/docs/prototyp-l0-i-xiao.md#krok-4-interfejs-lora-z-radiem-rnode): RAK4631 i dwa laptopy;
- [próby przy stole](../xiao-wici/README.md) z prototypami L0 w roli stacji.

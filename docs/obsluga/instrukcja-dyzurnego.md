# WICI: instrukcja dyżurnego stanowiska odbiorczego

Dla dyżurnych stanowiska odbiorczego: strażaków OSP i pracowników gminy. Stanowisko odbiorcze wyznacza wójt (burmistrz, prezydent miasta). Na ekranie stacji w punkcie stanowisko nazywa się „odbiorcą”. Skrót OSP oznacza tu tylko ochotniczą straż pożarną.

**Dotyczy.** Stacja stanowiska: oprogramowanie stacji WICI w konfiguracji węzła stanowiska, obrazy `bench-n1-0.1` i `bench-b-0.1` (specyfikacja 0.5), sprzęt: stacja deweloperska na płytce nośnej N1. Aplikacja i panel dyżurnego: według [specyfikacji stanowiska](../spec/stanowisko-osp.md). **Aplikacji stanowiska jeszcze nie zbudowano.** Nazwy w panelu (PRZECZYTANE, stany 3–6, kwarantanna, ZAMKNIJ ZDARZENIE) pochodzą ze specyfikacji, nie z kodu. Kroki oznaczone ◆ (łączenie zgłoszeń w sprawy, ćwiczenie) prowadzi się na papierze, bo panel ich nie ma. Wersja robocza do ćwiczenia przy stole.

Karta obsługi stacji w punkcie: [karta-stacji.html](karta-stacji.html). Napisy w cudzysłowach są tekstami z ekranu stacji (`firmware/src/ui_texts.h`).

## Zasady stałe

- System nie zastępuje numeru 112. Zgłoszenie zagrożenia życia, które da się przekazać telefonem, przekaż telefonem.
- Nie dysponujesz siłami służb. Przekazujesz zgłoszenie i zapisujesz, kto potwierdził.
- Stan zgłoszenia nie jest obietnicą przyjazdu.
- Komunikat o ewakuacji wysyłasz tylko razem z potwierdzeniem drugim kanałem (radio publiczne, goniec z upoważnieniem).
- Ani stacja, ani panel nie wykonują działań automatycznie na podstawie komunikatu.
- Przez radio nie idą nazwiska, ani od punktów, ani od Ciebie. Nie wpisuj nazwisk ani informacji o zdrowiu konkretnej osoby do odpowiedzi i komunikatów. Gdy nazwisko jest naprawdę potrzebne (np. poszukiwanie osoby), ustal je drugim kanałem (goniec, PMR, telefon) i zapisz tylko w rejestrze papierowym. Nie proś punktu o wpisanie nazwiska w zgłoszeniu.
- Nie zapisuj w tej instrukcji kluczy, haseł ani danych mieszkańców.

## 1. Uruchomienie stanowiska

1. Sprawdź, czy stacja stanowiska ma podłączoną antenę, zasilanie i przewód USB do komputera.
2. Włącz stację stanowiska. Wybierz język: GÓRA/DÓŁ, OK.
3. Odczytaj ekran stacji stanowiska:
   - wiersz 1: „RADIO WŁĄCZONE” (do 1 min). „RADIO: AWARIA” albo „BRAK ŁĄCZNOŚCI”: przejdź do [awarii](#8-awaria-stanowiska-i-powrót-bez-duplikatów);
   - wiersz 2: „KOMPUTER [czas] TEMU”. „BRAK KOMPUTERA” znaczy, że komputer nie przesłał jeszcze żadnego pakietu;
   - wiersz 3: zasilanie „12 V: [x] V” (oprogramowanie 0.1 jeszcze nie mierzy napięcia i pokazuje „12 V: 0,0 V”).
4. Włącz komputer stanowiska z podłączonym nośnikiem stanowiska.
5. Uruchom aplikację stanowiska.
6. Otwórz kopertę z hasłem stanowiska. Wpisz hasło.
7. Wpisz numer otwartej koperty do dziennika.
8. Zaloguj się do panelu własnym kontem. Nie pracuj na cudzym koncie.
9. Porównaj zegar komputera z telefonem w sieci komórkowej. Różnica ponad 1 min: ustaw zegar i wpisz to do dziennika.
10. Sprawdź w panelu stan węzła: połączenie ze stacją, czas od ostatniego pakietu z radia, wiadomości w drodze i w oczekiwaniu.
11. Sprawdź, czy ekran stacji stanowiska pokazuje teraz „KOMPUTER [czas] TEMU”.
12. Wpisz do rejestru godzinę uruchomienia i swoje nazwisko.

Aplikacja pracuje bez przerwy od początku zdarzenia. Na początku kolejnych dyżurów wykonaj tylko kroki 3, 8, 9 i 10, a potem przeczytaj [przekazanie zmiany](#7-rejestr-i-przekazanie-zmiany).

### Komputer zapasowy

1. Komputer zapasowy stoi przy stanowisku, wyłączony, z tym samym pakietem stanowiska.
2. Drugi nośnik z kopią bazy leży przy komputerze zapasowym.
3. Przełączenie na komputer zapasowy opisuje [awaria stanowiska](#8-awaria-stanowiska-i-powrót-bez-duplikatów). Cel: przyjmowanie zgłoszeń wraca w ciągu 15 min.

## 2. Odczyt zgłoszeń i stany potwierdzeń

Panel sortuje zgłoszenia według pilności, potem czasu odbioru. Pilność „ZAGROŻENIE ŻYCIA” włącza alarm dźwiękowy.

Każde zgłoszenie zawiera:

| Pole | Skąd |
|---|---|
| nazwa stacji `WICI-xxxxxx` | tożsamość stacji; nr i nazwę punktu odczytaj z [tabeli punktów](#tabela-punktów) |
| adres i wejście | zapisane w stacji przed kryzysem |
| rodzaj potrzeby | jeden z 10 (lista niżej) |
| liczba osób | 1–999 ze stacji |
| pilność | „ZAGROŻENIE ŻYCIA”, „PILNE – KILKA GODZIN”, „W CIĄGU DOBY” |
| opis | pusty, gotowa fraza (po polsku) albo własny tekst wpisany przyciskami (wielkie litery, bez tłumaczenia, czasem z literówkami albo po ukraińsku) |
| czas | czas odbioru według zegara komputera stanowiska; stacja nie podaje czasu utworzenia |
| krótki numer | 4 cyfry; razem z nazwą stacji jednoznacznie wskazuje zgłoszenie |

Rodzaje potrzeb w kolejności z ekranu stacji: 0 POMOC MEDYCZNA, 1 LEKI I SPRZĘT MED., 2 EWAKUACJA, TRANSPORT, 3 WODA PITNA, 4 ŻYWNOŚĆ, 5 OGRZEWANIE, ENERGIA, 6 SANITARNE, HIGIENA, 7 ZAGROŻENIE BUDYNKU, 8 POSZUKIWANIE, INFO, 9 INNE.

### Trzy poziomy potwierdzenia

| Poziom | Twoje działanie w panelu | Ekran w punkcie | Kiedy |
|---|---|---|---|
| 1. zapisane | brak; aplikacja potwierdza sama po zapisie | „ODBIORCA ZAPISAŁ” | od razu po odbiorze |
| 2. odczytane | PRZECZYTANE | „ODBIORCA PRZECZYTAŁ” | od razu po przeczytaniu; przy „ZAGROŻENIE ŻYCIA” najpóźniej 30 min po zapisie, inaczej punkt dostaje alarm i wysyła gońca |
| 3. rozstrzygnięte | stan 3 | „POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)” | podmiot dysponujący siłami potwierdził skierowanie pomocy; wpisz, kto (podmiot, funkcja), jakim kanałem i o której |
| | stan 4 | „PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)” | przekazałeś zgłoszenie, ale nie masz potwierdzenia skierowania pomocy |
| | stan 5 z odpowiedzią | „ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ” | nikt nie może teraz pomóc; odpowiedź mówi, co punkt ma zrobić |
| | stan 6 | „ZAMKNIĘTE” | potrzeba ustała albo sprawa zakończona |

Punkt dostaje alarm „BRAK POTWIERDZENIA…”, gdy nie ma poziomu 1 po: 15 min („ZAGROŻENIE ŻYCIA”), 1 h („PILNE – KILKA GODZIN”), 6 h („W CIĄGU DOBY”), 30 min (TEST). Wtedy wysyła gońca z formularzem, jeśli droga jest bezpieczna.

Postępowanie przy każdym zgłoszeniu:

1. Przeczytaj zgłoszenie.
2. Naciśnij PRZECZYTANE.
3. Wpisz zgłoszenie do rejestru.
4. Zgłoszenie nietypowe (np. wezwanie wielu służb w jedno miejsce) albo opis niezrozumiały: dopytaj odpowiedzią albo drugim kanałem.
5. Przekaż zgłoszenie według [tabeli przekazań](#tabela-przekazań).
6. Nadaj stan 4 albo 3. Potwierdzenie przyszło w ciągu kilku minut: nadaj od razu stan 3, bez stanu 4.
7. Potwierdzenie przyszło później: nadaj stan 3 jako kolejną decyzję.
8. Wpisz decyzję i osobę, która potwierdziła, do rejestru.

Zasady:

- Własna ocena, że pomoc „pewnie wyjedzie”, nie wystarcza do stanu 3.
- Każda wiadomość zajmuje wspólny kanał radiowy na kilkadziesiąt sekund. Na jedno zgłoszenie wysyłaj PRZECZYTANE i zwykle jedną decyzję. Nie zmieniaj stanu bez potrzeby.
- Panel nie wyśle stanu 5 bez odpowiedzi.
- Zmiana w punkcie (liczba osób, pilność, „POTRZEBA USTAŁA”) przychodzi jako nowa wersja tego samego zgłoszenia. Panel pokazuje wersje razem; każdą potwierdzasz osobno.
- Kto potwierdził skierowanie pomocy, zostaje w bazie i w rejestrze. Ta informacja nie idzie radiem do punktu.

## 3. Łączenie powtarzających się potrzeb ◆

Panel łączy tylko wersje jednego zgłoszenia. Zgłoszeń z różnych punktów o tę samą potrzebę nie łączy. Łącz je w rejestrze:

1. Zauważ powtarzającą się potrzebę (np. „WODA PITNA” z kilku punktów jednej miejscowości).
2. Załóż w rejestrze jedną sprawę z numerem `S-nn`.
3. Dopisz do sprawy nazwę stacji, krótki numer i liczbę osób każdego zgłoszenia.
4. Przekaż adresatowi jedną zbiorczą wiadomość: rodzaj potrzeby, łączna liczba osób, lista adresów.
5. Każdemu zgłoszeniu nadaj stan osobno (PRZECZYTANE, potem 4 albo 3).
6. Nowe zgłoszenie tej samej potrzeby dopisz do otwartej sprawy.

Punkty nie widzą spraw: każdy dostaje stan swojego zgłoszenia.

## 4. Odpowiedź do punktu i komunikat ogólny

### Odpowiedź do jednego punktu

Odpowiedź wysyła się zawsze do konkretnego zgłoszenia.

1. Otwórz zgłoszenie w panelu.
2. Wpisz odpowiedź: najwyżej 96 bajtów (96 znaków bez polskich liter, mniej z nimi).
3. Pisz po polsku, krótko, w trybie rozkazującym.
4. Wyślij.
5. Wpisz treść i godzinę do rejestru.

Do punktu, który nie przysłał zgłoszenia, nie wysyłasz wiadomości radiem. Użyj drugiego kanału (goniec, PMR) albo, gdy sprawa dotyczy wszystkich, komunikatu ogólnego.

### Komunikat ogólny

1. Wysyłaj tylko na polecenie wójta lub sztabu kryzysowego. Wpisz, kto polecił.
2. Wpisz treść: najwyżej 192 bajty, po polsku.
3. Wyślij. Panel wysyła komunikat osobno do każdej stacji i pokazuje postęp. Dla 50 stacji trwa to około 8,5 min (LoRa) albo 12 min (P1).
4. Wpisz treść, godzinę i osobę polecającą do rejestru.

Nie wysyłaj komunikatów, które mogą poczekać.

### Ewakuacja

Każdy komunikat ma na ekranie stacji stopkę „NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA”. Gospodarze nie wykonają nakazu wyjścia na podstawie samego komunikatu.

1. Uzgodnij z wójtem drugi kanał: komunikat w radiu publicznym albo gońcy z upoważnieniem.
2. Upewnij się, że drugi kanał działa równolegle.
3. Dopiero wtedy wyślij komunikat.
4. Wpisz do rejestru oba kanały i godziny.

Zagrożenie na miejscu (pożar, dym, CO, zalanie, zawalenie, polecenie służb na miejscu) nie czeka na potwierdzenie. Gospodarz wyprowadza ludzi od razu.

## 5. Zgłoszenia z nieznanych urządzeń

Zgłoszenie od stacji spoza listy zaufanych trafia do kwarantanny. Panel oznacza je jako niezaufane („do weryfikacji”). Punkt nie dostaje „ODBIORCA ZAPISAŁ”.

1. Nie przekazuj takiego zgłoszenia służbom.
2. Potwierdź je drugim kanałem: goniec, PMR, telefon, służby na miejscu.
3. Potwierdzone: zatwierdź w panelu tę jedną wiadomość. Nadawca nie staje się zaufany.
4. Traktuj zgłoszenie dalej jako niesprawdzone źródło.
5. Niepotwierdzone: odrzuć w panelu.
6. Wpisz weryfikację i jej wynik do rejestru.

Alarm „możliwe przejęcie stacji” (wiadomość od stacji usuniętej z listy):

1. Nie zatwierdzaj wiadomości bez potwierdzenia drugim kanałem u gospodarza punktu.
2. Zawiadom organizatora sieci.

Dodanie stacji do listy (np. stacja zastępcza w punkcie):

1. Weź kartę stacji (plik albo QR).
2. Porównaj odcisk z ekranem stacji albo z ewidencją.
3. Poproś drugiego zalogowanego dyżurnego o zgodę.
4. Dodaj stację. Nigdy na podstawie samej wiadomości radiowej.

Usunięcie stacji z listy (zaginęła, skradziona, gospodarz zgłasza przejęcie):

1. Usuń stację w panelu. Zgoda drugiego dyżurnego nie jest potrzebna.
2. Wpisz powód do rejestru.

## 6. Przekazywanie zgłoszeń służbom

Przekazujesz według gminnego planu zarządzania kryzysowego. Nie zlecasz służbom działań i nie kierujesz siłami.

1. Znajdź rodzaj potrzeby w [tabeli przekazań](#tabela-przekazań).
2. Przekaż zgłoszenie wskazanemu adresatowi wskazaną drogą łączności. Podaj: nazwę stacji i krótki numer, adres i wejście, rodzaj potrzeby, liczbę osób, pilność, opis.
3. Wpisz do rejestru: komu, którą drogą, o której.
4. Nadaj stan 4.
5. Gdy adresat potwierdzi skierowanie pomocy, wpisz: kto potwierdził (podmiot, funkcja osoby), jakim kanałem, o której.
6. Nadaj stan 3.
7. Nikt nie może pomóc: nadaj stan 5 z odpowiedzią, co punkt ma zrobić.

## 7. Rejestr i przekazanie zmiany

### Rejestr

Prowadź papierowy rejestr przez cały czas zdarzenia. Panel prowadzi osobno dziennik działań pod Twoim kontem. Jeden wiersz rejestru to jedno zdarzenie:

| Czas | Treść (stacja, nr, potrzeba, osoby, pilność; albo inne zdarzenie) | Decyzja (stan, komu przekazano, kto potwierdził) | Osoba (dyżurny, podpis) |
|---|---|---|---|
| | | | |

Wpisuj też: uruchomienie, zmianę zegara, otwarcie koperty, komunikaty, kwarantannę, ciszę radiową, awarie, kopie bazy, przekazanie zmiany.

### Przekazanie zmiany

1. Otwórz w panelu przekazanie zmiany.
2. Wykonaj kopię bazy na drugi nośnik. Sprawdź godzinę ostatniej kopii w panelu.
3. Przekaż następcy: otwarte zgłoszenia, zgłoszenia bez PRZECZYTANE, sprawy w stanie 4 bez potwierdzenia, otwarte sprawy `S-nn`, kwarantannę, niewysłane odpowiedzi i komunikaty, ciszę radiową, zasilanie, awarie.
4. Wpisz przekazanie do rejestru. Podpiszcie oboje.
5. Wyloguj się.

Odchodząc od komputera, zablokuj ekran. Panel blokuje się sam po 5 min.

### Eksport rejestru w otwartym formacie

Panel zapisuje rejestr w pliku CSV (UTF-8), który otworzy każdy arkusz kalkulacyjny. Jeden wiersz to jedno zdarzenie: odbiór, decyzja, odpowiedź, komunikat, przekazanie, kwarantanna, cisza, kopia bazy, przekazanie zmiany.

1. Na koniec każdej doby wybierz w panelu eksport rejestru.
2. Plik zapisuje się na nośniku stanowiska.
3. Zapis na inny nośnik wymaga zgody drugiego zalogowanego dyżurnego.
4. Sprawy `S-nn` z rejestru papierowego nie trafiają do pliku. Przy zamknięciu zdarzenia przekaż gminie także rejestr papierowy.

## 8. Awaria stanowiska i powrót bez duplikatów

Sieć przekazuje ruch także bez komputera. Punkty ponawiają niepotwierdzone zgłoszenia, a aplikacja nie przyjmuje tego samego zgłoszenia dwa razy.

### Komputer zawiesił się albo nie startuje

1. Wyłącz komputer stanowiska.
2. Przełóż nośnik stanowiska do komputera zapasowego.
3. Przełóż przewód USB stacji do komputera zapasowego.
4. Uruchom aplikację. Wpisz hasło stanowiska.
5. Zaloguj się.
6. Sprawdź zegar (rozdział 1, krok 9).
7. Czekaj na zaległe zgłoszenia. Przyjdą same; aplikacja nie przyjmie ich dwa razy.
8. Wpisz awarię i godzinę powrotu do rejestru. Cel: 15 min.

### Stacja stanowiska uszkodzona

1. Podłącz stację zapasową do tej samej anteny, zasilania i przewodu USB.
2. Sprawdź ekran: „RADIO WŁĄCZONE”, „KOMPUTER [czas] TEMU”.
3. Punkty niczego nie zmieniają: tożsamość odbiorcy jest na komputerze.

### Ekran stacji stanowiska: „BRAK KOMPUTERA” albo „KOMPUTER [czas] TEMU” ponad 8 h

1. Sprawdź przewód USB.
2. Sprawdź, czy aplikacja działa.

### Nośnik stanowiska uszkodzony

1. Wezwij osobę utrzymującą system.
2. Odtworzenie bazy z kopii wymaga zgody dwóch zalogowanych dyżurnych.
3. Aplikacja poprosi o potwierdzenie zegara. Porównaj z telefonem. Potwierdź przy różnicy do 1 min.
4. Aplikacja zapyta o liczbę odzyskań od daty kopii. Policz je w rejestrze. Wpisz to odzyskanie do rejestru.
5. Odtwórz z rejestru papierowego zgłoszenia i decyzje z czasu po ostatniej kopii. Punkty, które dostały „ODBIORCA ZAPISAŁ”, ich nie ponowią.
6. W razie wątpliwości zapytaj punkt drugim kanałem.

### Brak zasilania

1. Laptop pracuje z akumulatora.
2. Uruchom agregat albo stację zasilania przed wyczerpaniem akumulatora.
3. Agregat tylko na zewnątrz, z dala od wejść i wlotów powietrza: tlenek węgla zabija bez ostrzeżenia.

### Podejrzenie przejęcia stanowiska

1. Zawiadom wójta i organizatora sieci.
2. O przełączeniu punktów na klucz zapasowy odbiorcy decyduje wójt. Polecenie idzie do gospodarzy tylko słownie albo przez gońców, nigdy komunikatem radiowym.
3. Grozi przejęcie: uruchom w panelu ZNISZCZ DANE. Zniszcz fizycznie oba nośniki. Wpisz to do rejestru.

## 9. Tryb ćwiczebny i zgłoszenia testowe

### TEST z punktu

TEST to próbne zgłoszenie ze stacji punktu. Panel pokazuje je osobno i nie wlicza do potrzeb.

1. Sprawdź, czy adres i wejście są zrozumiałe.
2. Naciśnij PRZECZYTANE. Kilka TEST możesz potwierdzić razem, po sprawdzeniu adresu każdego.
3. Wpisz TEST do rejestru.
4. Stany 3–6 dla TEST nadawaj tylko w uzgodnionym ćwiczeniu.

Wiele stacji włącza się naraz i kanał jest zajęty: wyślij komunikat z prośbą o wstrzymanie TEST. Gospodarze wstrzymują TEST ręcznie (TEST → WSTRZYMAJ).

### Ćwiczenie ◆

Panel nie ma osobnego trybu ćwiczebnego. W ćwiczeniu:

1. Ogłoś ćwiczenie komunikatem. Treść zaczynaj od słowa ĆWICZENIE.
2. Poproś punkty o zgłoszenia jako TEST.
3. Każdy wpis w rejestrze oznacz literą Ć.
4. Nie przekazuj zgłoszeń ćwiczebnych służbom, chyba że plan ćwiczenia stanowi inaczej. Wtedy każde przekazanie zaczynaj od słowa ĆWICZENIE.
5. Po ćwiczeniu ogłoś koniec ćwiczenia komunikatem.

Ćwiczenie całej sieci ze stanowiskiem i gońcem odbywa się raz w roku. Grafik obejmuje co najmniej 4 dyżurnych; każdy przechodzi szkolenie i ćwiczenie.

### Test roczny wszystkich punktów

Raz w roku dyżurny i gospodarze sprawdzają wszystkie stacje w gminie. Test można połączyć z ćwiczeniem całej sieci. Używa tylko istniejących funkcji: komunikatu, TEST i PRZECZYTANE.

1. Gmina powiadamia gospodarzy o rozpoczęciu testu zwykłą drogą (telefon, SMS). Wpisz godzinę powiadomienia do rejestru.
2. Wyślij komunikat „ĆWICZENIE – TEST ROCZNY”. Stacja odbierze go po włączeniu.
3. Gospodarz albo zastępca włącza stację według karty, z kompletu ćwiczebnego albo ze źródła 12 V, i wysyła TEST. Komplet kryzysowy zostaje zamknięty.
4. Każdy TEST potwierdź (PRZECZYTANE) i wpisz z literą Ć: punkt, godzinę odbioru, uwagi (np. adres niezrozumiały, ponowienia).
5. Test trwa 2 h od powiadomienia, chyba że gmina ustali inaczej. Punkt bez TEST w tym czasie ma w tabeli „nie”; gmina ustala przyczynę (stacja, antena, ogniwa, brak obsady).
6. Wypełnij tabelę [wyniku testu rocznego](#wynik-testu-rocznego). Kopię dostaje gmina i komenda powiatowa PSP.

## 10. Cisza radiowa

Ciszę radiową poleca wójt albo wynika ona z nakazu w stanie nadzwyczajnym.

1. Wpisz polecenie, kto polecił i godzinę do rejestru.
2. Wyślij komunikat o ciszy do punktów.
3. Wyślij gońców do punktów według planu.
4. Polecenie obejmuje stanowisko: po rozesłaniu komunikatu włącz przełącznik CISZA na stacji stanowiska. Ekran: „CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC”.
5. Wpisz godzinę włączenia.

W ciszy stanowisko odbiera, ale nie potwierdza zgłoszeń. Pilne sprawy idą gońcem.

Odwołanie ciszy:

1. Wyłącz przełącznik CISZA na stacji stanowiska.
2. Wyślij komunikat o odwołaniu.
3. Wyślij gońców.
4. Wpisz godzinę do rejestru.

## 11. Zamknięcie zdarzenia

Gmina jest administratorem danych. Zamknięcie wykonuje się na polecenie gminy po odwołaniu stanu kryzysowego.

1. Wpisz polecenie gminy do rejestru.
2. Uruchom w panelu ZAMKNIJ ZDARZENIE. Aplikacja zapisze zaszyfrowane archiwum dla gminy, razem z rejestrem w CSV, i usunie treść zgłoszeń.
3. Przekaż gminie archiwum i rejestr papierowy. Wpisz w rejestrze, kto przyjął.
4. Przekaż polecenie zamknięcia do punktów: słownie, przez gońca albo pisemnie, nigdy komunikatem radiowym. Gospodarz zamyka zdarzenie na stacji: STAN → USŁUGI → ZAMKNIJ ZDARZENIE, potem GÓRA, DÓŁ, GÓRA, OK.
5. Wpisz do rejestru, które punkty potwierdziły zamknięcie.
6. Gmina potwierdza, że archiwum da się odczytać: wpisz w panelu, kto i kiedy potwierdził.
7. Podłącz drugi nośnik z kopiami bazy. Wykonaj w panelu zadanie „usuń kopie”.
8. Wpisz usunięcie kopii do rejestru.

Tożsamość odbiorcy, karty stacji i klucze odbioru zostają. Stanowisko jest gotowe do następnego użycia.

## Do wypełnienia przez gminę

### Tabela przekazań

Drogi łączności bez sieci publicznych: radiotelefon służbowy, łącze satelitarne, goniec, PMR na ustalonym kanale.

| Rodzaj potrzeby | Adresat | Droga łączności (bez sieci publicznych) | Kto potwierdza skierowanie pomocy |
|---|---|---|---|
| 0 POMOC MEDYCZNA | | | |
| 1 LEKI I SPRZĘT MED. | | | |
| 2 EWAKUACJA, TRANSPORT | | | |
| 3 WODA PITNA | | | |
| 4 ŻYWNOŚĆ | | | |
| 5 OGRZEWANIE, ENERGIA | | | |
| 6 SANITARNE, HIGIENA | | | |
| 7 ZAGROŻENIE BUDYNKU | | | |
| 8 POSZUKIWANIE, INFO | | | |
| 9 INNE | | | |

### Tabela punktów

| Stacja `WICI-xxxxxx` | Nr i nazwa punktu | Adres i wejście | Gospodarz i zastępcy (funkcje) | Trasa gońca |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

### Wynik testu rocznego

Data testu: ........ Godzina powiadomienia: ........ Dyżurny: ........

| Punkt (nr i nazwa) | Odpowiedział (tak/nie) | Czas od powiadomienia do TEST | Uwagi |
|---|---|---|---|
| | | | |
| | | | |
| | | | |

Kopia: gmina, komenda powiatowa PSP.

### Grafik dyżurnych (co najmniej 4 osoby)

| Data | Zmiana (od–do) | Dyżurny | Drugi dyżurny (zgody dwóch osób) | Podpis |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |

### Kontakty

| Rola | Funkcja lub nazwa | Droga łączności | Uwagi |
|---|---|---|---|
| wójt (burmistrz) | | | |
| sztab kryzysowy | | | |
| stanowisko kierowania PSP | | | |
| dyspozytornia medyczna | | | |
| Policja | | | |
| służby gminy | | | |
| organizator sieci | | | |
| osoba utrzymująca system | | | |
| administrator danych (gmina) | | | |
| sąsiednie stanowisko lub powiat | | | |

Kanał PMR stanowiska i godziny nasłuchu: ____________________

---

Licencja: [CC BY 4.0](../../LICENSES/CC-BY-4.0.txt).

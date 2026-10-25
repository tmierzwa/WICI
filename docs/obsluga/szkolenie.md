# WICI: program szkolenia gospodarzy punktów i dyżurnych

Szkolenie wprowadzające przed pracą stacji w terenie: 2 godziny, na prawdziwych stacjach i stanowisku odbiorczym. Do [ćwiczenia przy stole](../spec/odbior.md#minimum-pilotażu) nie jest potrzebne. Docelowe czasy szkoleń w wydaniu (gospodarz 3 h z kursem pierwszej pomocy, dyżurny 4 h, coroczne odświeżenie 2 h) podaje [koncepcja, rozdział 02](../concept/02-scenariusze-i-organizacja.html#instrukcja-i-cwiczenie).

Nazwy przycisków, ekranów, potrzeb i stopni pilności są takie jak w [karcie obsługi stacji](karta-stacji.html), [instrukcji dyżurnego](instrukcja-dyzurnego.md) i tabeli tekstów ekranu ([oprogramowanie](../spec/oprogramowanie.md#teksty-ekranu)). Znak ◆ oznacza czynność, której oprogramowanie albo panel jeszcze nie obsługuje; ćwiczy się ją na papierze albo pomija. Aplikacji stanowiska jeszcze nie zbudowano.

Wersja robocza 0.1. CC BY 4.0.

## 1. Co uczestnik umie po szkoleniu

**Gospodarz punktu**

- Włącza stację i odczytuje ekran główny: radio, kontakt z odbiorcą, baterie, zgłoszenia czekające, nowe wiadomości.
- Wysyła zgłoszenie z samą kartą obsługi, do 15 minut od włączenia stacji.
- Rozumie trzy potwierdzenia z karty: doszło („ODBIORCA ZAPISAŁ”), przeczytane („ODBIORCA PRZECZYTAŁ”), decyzja (np. „POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)”).
- Wie, kiedy i jak użyć procedury zastępczej: formularz papierowy, goniec, krótkofalówka PMR.
- Wymienia baterie ◆, wysyła TEST, włącza i wyłącza ciszę radiową.
- Wykonuje przegląd co kwartał według listy z karty.

**Dyżurny stanowiska odbiorczego**

- Uruchamia stanowisko i przechodzi na komputer zapasowy ([instrukcja, 1](instrukcja-dyzurnego.md#1-uruchomienie-stanowiska)).
- Odczytuje zgłoszenia i nadaje stany: PRZECZYTANE, potem stany 3–6 ([instrukcja, 2](instrukcja-dyzurnego.md#2-odczyt-zgłoszeń-i-stany-potwierdzeń)).
- Prowadzi rejestr i przekazuje zmianę bez utraty zgłoszeń ([instrukcja, 7](instrukcja-dyzurnego.md#7-rejestr-i-przekazanie-zmiany)).
- Przekazuje zgłoszenia według tabeli przekazań gminy ([instrukcja, 6](instrukcja-dyzurnego.md#6-przekazywanie-zgłoszeń-służbom)).
- Wysyła odpowiedź do punktu i komunikat ogólny; ewakuację potwierdza drugim kanałem ([instrukcja, 4](instrukcja-dyzurnego.md#4-odpowiedź-do-punktu-i-komunikat-ogólny)).
- Rozpoznaje zgłoszenie z nieznanego urządzenia ([instrukcja, 5](instrukcja-dyzurnego.md#5-zgłoszenia-z-nieznanych-urządzeń)) i wie, jak zamyka się zdarzenie ([instrukcja, 11](instrukcja-dyzurnego.md#11-zamknięcie-zdarzenia)).

## 2. Organizacja

- **Grupa:** do 14 osób: gospodarze z zastępcami (3 osoby na punkt) i co najmniej 4 dyżurnych. Prowadzą dwie osoby, po jednej na ścieżkę.
- **Miejsce:** remiza OSP ze stanowiskiem odbiorczym. Dwie sale albo sala i garaż, żeby gospodarze nie widzieli ekranu dyżurnych.
- **Sprzęt:** 3–4 stacje (jedna na 2–3 osoby), stanowisko odbiorcze i komputer zapasowy, baterie ćwiczebne, 2 krótkofalówki PMR, stoper.
- **Sieć szkoleniowa:** stacje szkoleniowe mają w karcie odbiorcy stanowisko szkoleniowe zamiast stanowiska gminy, więc zgłoszenia ćwiczebne mogą mieć prawdziwe rodzaje potrzeb. Na stacjach przypisanych do stanowiska gminy ćwiczy się tylko TEST i [ćwiczenie](instrukcja-dyzurnego.md#ćwiczenie-) z instrukcji dyżurnego ◆.
- **Materiały:** karta obsługi (PL; UK i EN dla osób, które ich potrzebują), instrukcja dyżurnego, tabela przekazań gminy ([wzór](instrukcja-dyzurnego.md#tabela-przekazań)), formularze papierowe zgłoszenia (ostatnia strona karty), lista obecności, arkusz sprawdzianu, ankieta.
- **Bezpieczeństwo:** każde zgłoszenie jest ćwiczebne. Nikt nie wzywa służb w ramach szkolenia. Przy prawdziwym zagrożeniu przerywamy i dzwonimy pod 112. W zgłoszeniach nie ma nazwisk.
- **Język:** szkolenie po polsku. Osoba posługująca się ukraińskim dostaje kartę UK i tłumacza albo osobę wspierającą z grupy.

## 3. Przebieg (120 minut)

| Czas | Kto | Treść | Metoda |
|---|---|---|---|
| 0:00–0:25 | wszyscy | Po co jest system i czego nie robi: nie zastępuje 112, nie alarmuje, nic nie dzieje się automatycznie. Role: gospodarz, dyżurny, decydent gminy. Rodzaje potrzeb i stopnie pilności. Trzy potwierdzenia. Dane osobowe: liczby, nie nazwiska. Sieć szkoleniowa. | krótkie wprowadzenie, karta w ręku, pokaz jednego zgłoszenia od wysłania do decyzji |
| 0:25–1:40 | ścieżki | Gospodarze: sekcja 4. Dyżurni: sekcja 5. | ćwiczenia praktyczne |
| 1:40–1:55 | wszyscy | Próba wspólna: każdy gospodarz wysyła 3 zgłoszenia, dyżurni je przyjmują i nadają stany; jedno wyłączenie stanowiska na 3 minuty; jeden komunikat ogólny. | ćwiczenie, prowadzący mierzy czas |
| 1:55–2:00 | wszyscy | Pytania, ankieta, lista obecności. | – |

## 4. Ścieżka gospodarza (75 minut)

| Min. | Blok | Ćwiczenie |
|---|---|---|
| 10 | Włączenie stacji ([karta, strona 1, punkt 1](karta-stacji.html)); co znaczą wiersze ekranu głównego. | Każdy włącza stację i mówi, co widzi. |
| 15 | Pierwsze zgłoszenie krok po kroku według karty. | Każdy wysyła jedno zgłoszenie. Prowadzący nie podpowiada, tylko obserwuje. |
| 15 | Zgłoszenia różnych rodzajów i pilności; INNE z opisem: gotowe zdanie albo WŁASNY TEKST. | Karty sytuacji (np. „brak wody dla 40 osób na 6 godzin”), w parach. |
| 15 | Brak potwierdzenia: po jakim czasie stacja piszczy (tabela pilności w karcie), kiedy goniec, kiedy krótkofalówka PMR; formularz papierowy. | Prowadzący wyłącza stanowisko; gospodarze stosują procedurę zastępczą. |
| 10 | Wymiana baterii ◆ (ćwiczebne a kryzysowe), TEST, cisza radiowa. | Wymiana baterii na czas. |
| 5 | Przegląd co kwartał według listy z karty; papierowy dziennik stacji. | Lista wypełniona na jednej stacji. |
| 5 | Sprawdzian (sekcja 6). | – |

## 5. Ścieżka dyżurnego (75 minut)

| Min. | Blok | Ćwiczenie |
|---|---|---|
| 10 | Uruchomienie stanowiska, zasilanie awaryjne, komputer zapasowy, koperty z hasłami ([instrukcja, 1](instrukcja-dyzurnego.md#1-uruchomienie-stanowiska)). | Uruchomienie od zera; przejście na komputer zapasowy. |
| 15 | Odczyt zgłoszeń, nadawanie stanów, łączenie powtarzających się potrzeb ◆ ([instrukcja, 2–3](instrukcja-dyzurnego.md#2-odczyt-zgłoszeń-i-stany-potwierdzeń)). | Prowadzący wysyła serię 10 zgłoszeń z dwóch stacji. |
| 10 | Rejestr: co, kiedy, kto, decyzja; eksport rejestru do pliku CSV ([instrukcja, 7](instrukcja-dyzurnego.md#eksport-rejestru-w-otwartym-formacie)). | Uzupełnienie rejestru dla serii. |
| 15 | Tabela przekazań gminy: kto jest adresatem każdej potrzeby i jak do niego dotrzeć bez sieci. Dyżurny nie dysponuje siłami, tylko przekazuje i zapisuje, kto potwierdził. | Przekazanie 3 zgłoszeń przez radiotelefon OSP do „stanowiska kierowania” (prowadzący). |
| 10 | Odpowiedź do punktu i komunikat ogólny; ewakuacja tylko z potwierdzeniem drugim kanałem. | Komunikat do wszystkich stacji. |
| 5 | Zgłoszenie z nieznanego urządzenia: kwarantanna, sprawdzenie drugim kanałem. | Prowadzący podsyła zgłoszenie z nieznanej stacji. |
| 5 | Przekazanie zmiany; awaria stanowiska i powrót bez duplikatów; zamknięcie zdarzenia i archiwum dla gminy. | Przekazanie zmiany przy otwartych zgłoszeniach. |
| 5 | Sprawdzian (sekcja 6). | – |

## 6. Sprawdzian i zaliczenie

| Kto | Zadanie | Zaliczone, gdy |
|---|---|---|
| Gospodarz | Stacja wyłączona, baterie wyjęte. Uczestnik z samą kartą włącza stację i wysyła zgłoszenie podane przez prowadzącego. | zgłoszenie poprawne, do 15 minut, bez pomocy |
| Gospodarz | Trzy pytania: co znaczy alarm „ODBIORCA NIE PRZECZYTAŁ OD 30 MIN”; co robisz, gdy ktoś potrzebuje karetki, a telefon działa; czy wpisujesz nazwiska. | 3 z 3 poprawne |
| Dyżurny | Seria 10 zgłoszeń, w tym jedno z nieznanej stacji i jedno powtórzone; potem przekazanie zmiany. | rejestr bez braków; zgłoszenie z nieznanej stacji w kwarantannie; zmiennik pracuje dalej bez pytań |

Kto nie zaliczy, powtarza ćwiczenie od razu albo na następnym spotkaniu. Czas pierwszego zgłoszenia trafia do raportu z pilotażu bez nazwisk. Próg 15 minut dotyczy szkolenia; [odbiór](../spec/odbior.md#próby) („Obsługa według karty”) wymaga więcej: start i TEST do 5 minut, zgłoszenie dla 50 osób do 2 minut.

## 7. Po szkoleniu

- Listę obecności i arkusze sprawdzianu przechowuje organizator szkolenia, bo zawierają dane osobowe uczestników. Kopię listy dostaje gmina.
- Zaświadczenie na prośbę uczestnika.
- Ankieta (3 pytania): co było niejasne na karcie, co zmienić w szkoleniu, czy czujesz się gotowy obsłużyć punkt sam (tak, raczej tak, nie). Uwagi do karty zgłasza się w repozytorium.
- Odświeżenie: 30 minut przy corocznym ćwiczeniu całej sieci ([instrukcja, 9](instrukcja-dyzurnego.md#9-tryb-ćwiczebny-i-zgłoszenia-testowe)) i po każdej zmianie oprogramowania, która zmienia obsługę. Nowy gospodarz lub zastępca dostaje 30-minutowy instruktaż i sprawdzian z sekcji 6.

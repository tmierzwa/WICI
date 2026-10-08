# WICI: instrukcja opiekuna

Instrukcja jest dla opiekuna schronienia i zastępców. Uzupełnia [kartę obsługi](karta.md), która leży przy stacji i prowadzi przez uruchomienie i zgłoszenie. Tu są tematy, które nie mieszczą się na karcie ([koncepcja, rozdział 02](../concept/02-scenariusze-i-organizacja.html#instrukcja-i-cwiczenie)). Napisy w cudzysłowach są cytatami z tabeli [Teksty ekranu](oprogramowanie.md#teksty-ekranu); wersje UK i EN instrukcji używają kolumn UK i EN tej tabeli. Instrukcja opisuje odebrany zestaw, którego jeszcze nie zbudowano. W instrukcji nie zapisuje się kluczy, haseł ani danych mieszkańców.

## Twoja rola

- Uruchamiasz stację, sprawdzasz adres i wykonujesz TEST według karty.
- Przyjmujesz potrzeby mieszkańców, łączysz powtarzalne w jedno zgłoszenie, ustalasz pilność i wysyłasz zgłoszenie przyciskami albo z panelu laptopa.
- Pilnujesz potwierdzeń i alarmów, a przy braku potwierdzenia wysyłasz gońca z formularzem.
- Pilnujesz energii stacji i, na poziomie 3, źródeł laptopa, routera i ładowarki.
- Prowadzisz papierowy dziennik: czas, krótki numer zgłoszenia, decyzja odbiorcy, przekazanie zmiany.

Stacja nie decyduje o pomocy. Decyzję podejmuje dyżurny w OSP, czyli stanowisku odbiorczym wyznaczonym przez wójta. WICI nie zastępuje numeru 112: jeśli telefon działa, dzwoń 112.

## Adres i wejście

Adres schronienia zapisano w stacji przed kryzysem. Przy uruchomieniu stacja pyta „ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE”.

- Adres się zgadza: OK. Stacja dołącza go do każdego zgłoszenia.
- Adres jest błędny albo stacja pokazuje „STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO”: wysyłaj zgłoszenia tylko formularzem przez gońca i zgłoś błąd osobie utrzymującej system. Adresu nie da się zmienić w schronieniu, bo stacja przyjmuje go tylko w trybie przygotowania.
- Jeśli stacja ma listę kilku obiektów, najpierw wybierz właściwy przyciskami GÓRA i DÓŁ i potwierdź OK; stacja zapyta wtedy o adres tego obiektu. WSTECZ przy pytaniu o adres wraca do listy. Gdy żaden obiekt z listy nie pasuje, naciśnij WSTECZ na liście i postępuj jak przy błędnym adresie.

Miejsce w budynku (piętro, sala) nie należy do adresu. Na poziomie 1 wybierz pasującą gotową frazę albo przekaż je gońcem. W panelu laptopa i na stronie mieszkańca wpisuje się je na początku opisu.

## Odbiorca, kontakt i zastępstwo

„RADIO WŁĄCZONE” znaczy tylko, że stacja odbiera i może nadawać. Kontakt z odbiorcą pokazuje „OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU” w STAN, a na ekranie głównym w skrócie „KONTAKT [czas] TEMU”. Długi czas bez kontaktu nie jest awarią: OSP odzywa się, gdy ma coś do przekazania. Po włączeniu stacji bez zegara RTC ekran pokazuje „KONTAKT >[czas] TEMU”, bo stacja nie wie, jak długo była wyłączona.

Kanał zastępczy wskazuje plan sieci: goniec z formularzem, radiotelefon PMR446 na ustalonym kanale i w ustalonych godzinach nasłuchu, służby na miejscu. Zapisz kanał i trasę gońca na pierwszej stronie dziennika.

**ODBIORCA ZAPASOWY** (STAN → USŁUGI) przełącza stację na zapasową tożsamość OSP. Wybierz go wyłącznie na polecenie przekazane słownie albo przez gońca z upoważnieniem wójta, nigdy na podstawie wiadomości na ekranie. Stacja pyta „PRZEŁĄCZYĆ NA ODBIORCĘ ZAPASOWEGO? TYLKO NA POLECENIE GOŃCA LUB SŁOWNE. NIEODWRACALNE”; potwierdzenie to GÓRA, DÓŁ, GÓRA, OK. Po przełączeniu stacja sama wysyła ponownie niepotwierdzone zgłoszenia. Wpisz polecenie i godzinę do dziennika.

**OGŁOŚ ADRES** (STAN → USŁUGI) rozgłasza adres stacji w sieci od razu, zamiast czekać na zwykłe ogłoszenie. Użyj go po zmianie miejsca anteny albo gdy OSP prosi o to przez gońca. Ekran odpowiada „ADRES ZOSTANIE OGŁOSZONY”. W ciszy radiowej ogłoszenie czeka na jej koniec. Gdy ekran pokaże „STACJA NIE MOŻE NADAWAĆ – ADRES NIE OGŁOSZONY. FORMULARZ + GONIEC”, stacja nie wyśle radiem także zgłoszeń: wysyłaj je formularzem przez gońca i zgłoś błąd osobie utrzymującej system.

**WYCISZ DŹWIĘK** (STAN → USŁUGI) wyłącza zwykły sygnał dźwiękowy nowej wiadomości. Alarmów (brak potwierdzenia, brak odczytu, wymiana ogniw) nie da się wyciszyć. Ta sama pozycja pokazuje wtedy **WŁĄCZ DŹWIĘK**. Wyciszenie przetrwa wyłączenie stacji. Gdy dźwięk jest wyciszony, pokazują to STAN, PRZEKAZANIE ZMIANY i ekran główny przy pustej kolejce. Przekazując dyżur, sprawdź, czy dźwięk jest włączony.

## Zgłoszenie i jego stany

Przed wysłaniem:

1. Zbierz potrzeby od mieszkańców ustnie albo z kolejki w panelu (poziom 3). Osoby bez telefonu, niewidome i niesłyszące zgłaszają potrzebę Tobie; odczytaj im odpowiedzi.
2. Połącz powtarzalne potrzeby w jedno zgłoszenie: jedno zgłoszenie „woda pitna, 40 osób” zamiast czterdziestu. Każde zgłoszenie zajmuje wspólny kanał radiowy na kilkadziesiąt sekund.
3. Ustal pilność: „ZAGROŻENIE ŻYCIA” tylko przy bezpośrednim zagrożeniu, „PILNE – KILKA GODZIN”, „W CIĄGU DOBY”. Pilność nie przesądza o wysłaniu ludzi; decyduje dyżurny.
4. Nie wpisuj nazwisk ani danych o zdrowiu konkretnej osoby. Wystarczą kategoria, liczba osób i krótki opis.

Przy zagrożeniu życia najpierw udziel pierwszej pomocy. Jeśli działa telefon, dzwoń 112, a gdy droga jest bezpieczna, wyślij gońca do najbliższej jednostki PSP lub OSP albo zespołu ratownictwa medycznego. Zgłoszenie radiowe wysyłasz równolegle.

Stany na ekranie:

| Ekran | Co znaczy | Co robisz |
|---|---|---|
| „ZAPISANE W STACJI – CZEKA NA WYSŁANIE” | zgłoszenie jest trwale zapisane w stacji, jeszcze nie wysłane | zapisz krótki numer w dzienniku |
| „ZAPISANE – NIE WYJDZIE DO KOŃCA CISZY” | zapis w ciszy radiowej | pilne zgłoszenie przekaż gońcem |
| „WYSYŁANIE – PRÓBA [n], NASTĘPNA ZA [m] MIN” | stacja ponawia wysyłkę | czekaj; nie wysyłaj tego samego drugi raz |
| „ODBIORCA ZAPISAŁ” | OSP zapisała zgłoszenie | to jeszcze nie decyzja o pomocy |
| „ODBIORCA PRZECZYTAŁ” | dyżurny przeczytał zgłoszenie | czekaj na decyzję |
| „POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)” | dyżurny zdecydował o pomocy | nie podawaj mieszkańcom godziny przyjazdu |
| „PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)” | zgłoszenie trafiło do służby, która może pomóc | czekaj na dalsze informacje |
| „ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ” | dyżurny nie ma teraz środków | przeczytaj odpowiedź w WIADOMOŚCI i wykonaj instrukcję |
| „ZAMKNIĘTE” | sprawa zakończona | wpisz do dziennika |

Zmiana potrzeby: WIADOMOŚCI → własne zgłoszenie → „ZMIEŃ LICZBĘ OSÓB”, „ZMIEŃ PILNOŚĆ” albo „POTRZEBA USTAŁA”. Każda zmiana jest nową wersją tego samego zgłoszenia, z tym samym krótkim numerem. „ANULUJ WYSYŁKĘ” działa tylko przed „ODBIORCA ZAPISAŁ”; później użyj „POTRZEBA USTAŁA”, bo odbiorca o anulowaniu by się nie dowiedział.

Krótki numer i nazwa stacji `WICI-xxxxxx` (STAN) jednoznacznie wskazują zgłoszenie. Podawaj je gońcowi i w rozmowie przez PMR446.

## Alarmy

| Alarm | Kiedy | Co robisz |
|---|---|---|
| „BRAK POTWIERDZENIA OD [n] MIN – WYŚLIJ GOŃCA Z FORMULARZEM” | brak „ODBIORCA ZAPISAŁ” po 15 min (zagrożenie życia), 1 h (pilne), 6 h (w ciągu doby) albo 30 min (TEST) | wypełnij formularz w dwóch egzemplarzach i wyślij gońca; zgłoszenie radiowe zostaje w kolejce |
| „ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – WYŚLIJ GOŃCA Z FORMULARZEM” | tylko zagrożenie życia: brak „ODBIORCA PRZECZYTAŁ” 30 min po „ODBIORCA ZAPISAŁ” | goniec z formularzem; dyżurny może być zajęty albo nieobecny |
| „WYMIEŃ OGNIWA W CIĄGU 1 H” | niskie napięcie ogniw | [energia](#energia-stacji) |
| „12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO I PRZYTRZYMAJ OK” | źródło 12 V spadło do 11,5 V | stacja pracuje z ogniw; podłącz naładowane źródło |

OK wycisza dźwięk alarmu; napis i dioda zostają do usunięcia przyczyny. Dźwięk wraca przy nowym alarmie. Alarmów krytycznych nie da się wyłączyć: nie wyjmuj ogniw, żeby uciszyć stację, bo przestaje wtedy przekazywać wiadomości innych schronień.

## Komunikaty od odbiorcy

Odpowiedzi i komunikaty od OSP przychodzą po polsku. Każdy komunikat ma stopkę „NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA”. Nakazu wyjścia, ewakuacji ani zmiany miejsca nie wykonuj na podstawie samego komunikatu: potwierdź go w odbiorniku radiowym z zestawu (Polskie Radio Program 1, fale długie 225 kHz lub FM) albo u gońca z upoważnieniem wójta.

Gdy komunikat prosi o wstrzymanie TEST, wybierz TEST → WSTRZYMAJ („TEST WSTRZYMANY PRZEZ ODBIORCĘ”). TEST → WZNÓW wybierasz dopiero po kolejnym komunikacie albo w uzgodnionym oknie.

## Cisza radiowa

Ciszę radiową poleca wójt albo wynika ona z nakazu w stanie nadzwyczajnym; polecenie przychodzi komunikatem z OSP i przez gońca. Włącz przełącznik CISZA pod osłoną i wpisz polecenie do dziennika. Ekran pokazuje „CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC”. Stacja odbiera i zapisuje, ale niczego nie nadaje, także wiadomości innych schronień. Pilne potrzeby przekazuj gońcem. Ciszę wyłączasz ręcznie, dopiero gdy organ ją odwoła.

Wyjątek dla pojedynczego zgłoszenia ustawia się tylko w panelu laptopa i tylko wtedy, gdy polecenie ciszy wprost go dopuszcza. Przy włączonym przełączniku CISZA wyjątku nie ma. Wyjątek zwykle nie zadziała przez przekaźniki, które same są w ciszy, więc nie zastępuje gońca.

## Energia stacji

Stacja ma dwa komplety ogniw litowych AA: kryzysowy w zamkniętym opakowaniu i ćwiczebny do TEST i przeglądów.

- W kryzysie stacja pracuje z kompletu kryzysowego. Komplet ćwiczebny jest rezerwą tylko wtedy, gdy po włożeniu i minucie pracy STAN pokazuje „OGNIWA: [x] V” z wartością co najmniej 5,6 V (próg do potwierdzenia w T6).
- Gdy masz źródło 12 V (akumulator 12 V, akumulator LiFePO4 z BMS, wyjście 12 V stacji zasilania), podłącz je przewodem z zestawu; ogniwa zostają rezerwą. Stacja przełącza źródła bez restartu.
- Po „WYMIEŃ OGNIWA W CIĄGU 1 H” podłącz najpierw 12 V i wtedy wymień ogniwa. Bez 12 V przytrzymaj wyłącznik główny 2 s, poczekaj na „MOŻNA WYJĄĆ OGNIWA” i wymień cały komplet (+ do znaku +). Nie mieszaj ogniw różnych typów ani różnego stopnia rozładowania.
- Ogniwa alkaliczne i NiMH są tylko awaryjne: na mrozie tracą większość pojemności.

„OGNIWA: OKOŁO [x] H PRACY” w STAN to szacunek. Licz z zapasem, zwłaszcza w zimnym pomieszczeniu.

## Laptop, router i strona (poziomy 2–3)

Dołączasz je, gdy stacja już działa; stacja pracuje dalej przez cały czas. Kolejność podłączenia podaje [projekt](projekt.md#dołączenie-laptopa-i-routera-poziomy-23).

- Zaloguj się do panelu hasłem z numerowanej koperty przy stacji. Po otwarciu koperty hasło zmienia osoba utrzymująca system; wpisz numer koperty do dziennika.
- Wi-Fi i adres strony: przy routerze z zestawu, sprawdzonym w przygotowaniu, obowiązuje plakat przy stacji (sieć, hasło, adres). Przy innym routerze pokaż mieszkańcom kod QR z ekranu laptopa.
- Zgłoszenie z telefonu trafia najpierw do Twojej kolejki w panelu i nie wychodzi radiem samo. Sprawdź je, połącz z powtarzalnymi, ustal pilność i zatwierdź.
- Mieszkaniec dostaje lokalny numer zgłoszenia („ZAPISZ NUMER [xxxx] – PODAJ GO OPIEKUNOWI, ABY SPRAWDZIĆ STAN”). Gdy straci dostęp na telefonie, sprawdź stan po tym numerze w panelu.
- Brak energii: najpierw wyłącz laptop i router. Stacja pracuje dalej z ogniw lub 12 V.

### Kolejność i wymiana źródeł (poziom 3)

- Źródła A i B zasilają laptop i router, źródło C ładowarkę telefonów. Nie łącz plusów akumulatorów bezpośrednio.
- Zasilacze laptopa i routera podłączaj przy wyłączniku DC w pozycji 0, potem źródło A i C; włącz wyłącznik DC dopiero przy co najmniej 12,4 V na woltomierzach.
- Wymieniaj źródło A/B na zakładkę: podłącz nowe do wolnego wejścia, dopiero potem odłącz stare. Wymieniaj przed 11,5 V; ostrzeżenie włącza się przy 11,8 V, a akumulator rozruchowy pojazdu wymieniaj już przy około 12,2 V.
- Po odłączeniu podnapięciowym podłącz naładowane źródło i naciśnij RESTART.
- Wymiana źródła C przerywa tylko ładowanie telefonów.

## Przekazanie zmiany

Zmiana trwa najwyżej 12 h. Przed zejściem ze zmiany otwórz STAN → PRZEKAZANIE ZMIANY: otwarte i niepotwierdzone zgłoszenia, nieprzeczytane wiadomości, energia, cisza i wyciszenie dźwięku. Przekaż następcy ostatnie odpowiedzi odbiorcy, dostępne źródła energii, awarie i kanał zastępczy. Wpisz przekazanie do dziennika i podpisz. Nie kasuj niepotwierdzonych zgłoszeń.

## Koniec zdarzenia i zniszczenie danych

**ZAMKNIJ ZDARZENIE** wykonuje się po odwołaniu stanu kryzysowego, na polecenie gminy, z panelu laptopa. Operacja zapisuje zaszyfrowane archiwum dla administratora danych i usuwa zgłoszenia z laptopa i stacji. Tożsamość stacji i karta OSP zostają, więc stacja jest gotowa do następnego użycia. Potem odłóż stację do skrzynki i zgłoś zużycie ogniw organizatorowi sieci.

**ZNISZCZ DANE** (STAN → USŁUGI) uruchamiasz tylko przy groźbie przejęcia stacji lub laptopa, także na polecenie OSP przekazane słownie albo przez gońca, nigdy na podstawie wiadomości radiowej. Ekran „NIEODWRACALNE – STACJA PRZESTANIE DZIAŁAĆ; TYLKO PRZY GROŹBIE PRZEJĘCIA”, potwierdzenie GÓRA, DÓŁ, GÓRA, OK. Stacja przestaje działać na stałe. Pamięć USB zestawu zniszcz fizycznie, bo samo usunięcie plików jej nie chroni. Wpisz zdarzenie do dziennika.

## Bezpieczeństwo w schronieniu

- Nie uruchamiaj silnika pojazdu ani agregatu w schronieniu, w garażu, przy wejściu ani przy wlotach powietrza: tlenek węgla zabija bez ostrzeżenia. Pojazd jako źródło 12 V stoi na zewnątrz, kilka metrów od wejść; przewód nie może trzymać otwartych drzwi.
- Bateryjny czujnik tlenku węgla z zestawu poziomu 3 umieść w pomieszczeniu z ludźmi. Przy alarmie wyprowadź ludzi na świeże powietrze i wyślij zgłoszenie z kategorią „ZAGROŻENIE BUDYNKU”.
- Akumulatory stawiaj na tacy, z dala od dróg ewakuacyjnych. Nie ładuj akumulatorów w pomieszczeniu z ludźmi. Gaśnica stoi przy stacji; zapisz jej miejsce w dzienniku.
- Nie podchodź do anteny zewnętrznej i nie podłączaj jej podczas burzy. Antenę zapasową wystawiasz przez okno tylko wtedy, gdy nie ma zamontowanej; przewodu nie prowadź przez drzwi hermetyczne, gazoszczelne ani przeciwpożarowe.

## Gdy coś nie działa

Najpierw ustal, czego dotyczy błąd: strony, laptopa, stacji, trasy radiowej, odbiorcy czy zasilania. Pełną tabelę podaje [koncepcja, rozdział 02](../concept/02-scenariusze-i-organizacja.html#zachowanie-w-scenariuszach-awarii).

| Objaw | Działanie |
|---|---|
| długo „WYSYŁANIE – PRÓBA [n] …” | sprawdź przewód antenowy i złącze; zapytaj sąsiednie schronienie przez PMR446, czy jego stacja działa; pilne zgłoszenie przez gońca |
| „KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO” albo „BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ + GONIEC” | formularz i goniec; zgłoś błąd osobie utrzymującej system |
| „STACJA NIE MOŻE NADAWAĆ – ADRES NIE OGŁOSZONY. FORMULARZ + GONIEC” po OGŁOŚ ADRES | stacja nie wyśle radiem żadnego zgłoszenia: formularz i goniec; zgłoś błąd osobie utrzymującej system |
| stacja uruchomiła się ponownie | sprawdź ekran i zatwierdź proponowany TEST; kolejka zostaje w stacji |
| laptop się zawiesił lub odłączył | stacja pracuje dalej; po powrocie laptopa sprawdź stan zgłoszeń w panelu |
| stacja uszkodzona | goniec i PMR446; zgłoś organizatorowi sieci potrzebę stacji zapasowej |

Nie uruchamiaj drugiej stacji z tą samą tożsamością i nie resetuj routera znalezionego na miejscu bez zgody właściciela.

# WICI: instrukcja gospodarza

Instrukcja jest dla gospodarza schronienia i zastępców. Uzupełnia [kartę obsługi](../obsluga/karta-stacji.html), która leży przy stacji i prowadzi przez uruchomienie i zgłoszenie. Tu są tematy, które nie mieszczą się na karcie ([koncepcja, rozdział 02](../concept/02-scenariusze-i-organizacja.html#instrukcja-i-cwiczenie)).

Napisy w cudzysłowach są cytatami z tabeli [Teksty ekranu](oprogramowanie.md#teksty-ekranu). Wersje UK i EN instrukcji używają kolumn UK i EN tej tabeli.

Instrukcja opisuje odebrany zestaw, którego jeszcze nie zbudowano. W instrukcji nie zapisuje się kluczy, haseł ani danych mieszkańców.

## Twoja rola

- Uruchamiasz stację, sprawdzasz adres i wykonujesz TEST według karty.
- Przyjmujesz potrzeby mieszkańców, łączysz powtarzalne w jedno zgłoszenie, ustalasz pilność i wysyłasz zgłoszenie przyciskami albo z panelu laptopa.
- Pilnujesz potwierdzeń i alarmów, a przy braku potwierdzenia wysyłasz gońca z formularzem, jeśli droga jest bezpieczna ([goniec](#goniec)).
- Pilnujesz energii stacji i, na poziomie 3, źródeł laptopa, routera i ładowarki.
- Prowadzisz papierowy dziennik: czas, krótki numer zgłoszenia, decyzja odbiorcy, przekazanie zmiany.

Stacja nie decyduje o pomocy. Zgłoszenia przyjmuje odbiorca, czyli stanowisko odbiorcze wyznaczone przez wójta. Jego dyżurny przekazuje je służbom, które dysponują siłami, i odsyła odpowiedź. Skrót OSP oznacza w tej instrukcji tylko ochotniczą straż pożarną. WICI nie zastępuje numeru 112: jeśli telefon działa, dzwoń 112.

## Adres i wejście

Adres schronienia zapisano w stacji przed kryzysem. Przy uruchomieniu stacja pyta „ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE”.

- Adres się zgadza: OK. Stacja dołącza go do każdego zgłoszenia.
- Adres jest błędny albo stacja pokazuje „STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO”: wysyłaj zgłoszenia tylko formularzem przez gońca, jeśli droga jest bezpieczna ([goniec](#goniec)), i zgłoś błąd osobie utrzymującej system. Adresu nie da się zmienić w schronieniu, bo stacja przyjmuje go tylko w trybie przygotowania.
- Jeśli stacja ma listę kilku obiektów, najpierw wybierz właściwy przyciskami GÓRA i DÓŁ i potwierdź OK. Stacja zapyta wtedy o adres tego obiektu. WSTECZ przy pytaniu o adres wraca do listy. Gdy żaden obiekt z listy nie pasuje, naciśnij WSTECZ na liście i postępuj jak przy błędnym adresie.

Miejsce w budynku (piętro, sala) nie należy do adresu. Na poziomie 1 wybierz pasującą gotową frazę albo wpisz je przyciskami jako „WŁASNY TEKST” (na przykład „PIĘTRO 2 SALA 14”). W panelu laptopa i na stronie mieszkańca wpisuje się je na początku opisu.

## Odbiorca, kontakt i zastępstwo

„RADIO WŁĄCZONE” znaczy tylko, że stacja odbiera i może nadawać. Kontakt z odbiorcą pokazuje „OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU” w STAN, a na ekranie głównym w skrócie „KONTAKT [czas] TEMU”. Długi czas bez kontaktu nie jest awarią: odbiorca odzywa się, gdy ma coś do przekazania. Po włączeniu ekran może pokazywać „KONTAKT >[czas] TEMU”: stacja nie wie, jak długo była wyłączona.

Kanał zastępczy wskazuje plan sieci: goniec z formularzem, radiotelefon PMR446 na ustalonym kanale i w ustalonych godzinach nasłuchu, służby na miejscu. Zapisz kanał i trasę gońca na pierwszej stronie dziennika.

**KLUCZ ZAPASOWY** (STAN → USŁUGI) przełącza stację na zapasowy klucz tego samego odbiorcy, np. gdy skradziono komputer stanowiska i odbiorca pracuje dalej na komputerze zapasowym. Nie przełącza stacji do innego odbiorcy: gdy odbiorca przestaje działać, a zgłoszenia przejmuje ktoś inny, obowiązuje kanał zastępczy z planu sieci. Wybierz KLUCZ ZAPASOWY wyłącznie na polecenie przekazane słownie albo przez gońca z upoważnieniem wójta, nigdy na podstawie wiadomości na ekranie. Stacja pyta „PRZEŁĄCZYĆ NA KLUCZ ZAPASOWY ODBIORCY? TYLKO NA POLECENIE SŁOWNE LUB PRZEZ GOŃCA. NIEODWRACALNE”. Potwierdź: GÓRA, DÓŁ, GÓRA, OK. Po przełączeniu stacja sama wysyła ponownie niepotwierdzone zgłoszenia. Wpisz polecenie i godzinę do dziennika.

**OGŁOŚ ADRES** (STAN → USŁUGI) rozgłasza adres stacji w sieci od razu, zamiast czekać na zwykłe ogłoszenie. Użyj go po zmianie miejsca anteny albo gdy odbiorca prosi o to przez gońca. Ekran odpowiada „ADRES ZOSTANIE OGŁOSZONY”. W ciszy radiowej ogłoszenie czeka na jej koniec. Gdy ekran pokaże „STACJA NIE NADAJE – ADRES NIE OGŁOSZONY. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA”, stacja nie wyśle radiem także zgłoszeń: wysyłaj je formularzem przez gońca, jeśli droga jest bezpieczna ([goniec](#goniec)), i zgłoś błąd osobie utrzymującej system.

**WYCISZ DŹWIĘK** (STAN → USŁUGI) wyłącza zwykły sygnał dźwiękowy nowej wiadomości. Alarmów z tabeli [Alarmy](#alarmy) nie da się wyciszyć tą pozycją. Ta sama pozycja pokazuje wtedy **WŁĄCZ DŹWIĘK**. Wyciszenie przetrwa wyłączenie stacji. Gdy dźwięk jest wyciszony, pokazują to STAN, PRZEKAZANIE ZMIANY i ekran główny przy pustej kolejce. Przekazując dyżur, sprawdź, czy dźwięk jest włączony.

## Zgłoszenie i jego stany

Przed wysłaniem:

1. Zbierz potrzeby od mieszkańców ustnie albo z kolejki w panelu (poziom 3). Osoby bez telefonu, niewidome i niesłyszące zgłaszają potrzebę Tobie; przekaż im odpowiedzi: przeczytaj na głos albo pokaż zapisane.
2. Połącz powtarzalne potrzeby w jedno zgłoszenie: jedno zgłoszenie „woda pitna, 40 osób” zamiast czterdziestu. Każde zgłoszenie zajmuje wspólny kanał radiowy na kilkadziesiąt sekund.
3. Ustal pilność: „ZAGROŻENIE ŻYCIA” tylko przy bezpośrednim zagrożeniu, „PILNE – KILKA GODZIN”, „W CIĄGU DOBY”. Pilność nie przesądza o wysłaniu ludzi; decyduje podmiot dysponujący siłami, któremu dyżurny przekazuje zgłoszenie.
4. Nie wpisuj nazwisk ani danych o zdrowiu konkretnej osoby. Wystarczą kategoria, liczba osób i krótki opis.

Przy zagrożeniu życia najpierw udziel pierwszej pomocy. Jeśli działa telefon, dzwoń 112. Jeśli nie działa, a droga jest bezpieczna, wyślij gońca do najbliższej jednostki PSP lub OSP albo stacji pogotowia. Gdy droga nie jest bezpieczna, postępuj według części [Goniec](#goniec). Zgłoszenie radiowe wysyłasz równolegle.

Stany na ekranie:

| Ekran | Co znaczy | Co robisz |
|---|---|---|
| „ZAPISANE W STACJI – CZEKA NA WYSŁANIE” | zgłoszenie jest trwale zapisane w stacji, jeszcze nie wysłane | zapisz krótki numer w dzienniku |
| „ZAPISANE – NIE WYJDZIE DO KOŃCA CISZY” | zapis w ciszy radiowej | pilne zgłoszenie przekaż gońcem, jeśli droga jest bezpieczna |
| „WYSYŁANIE – PRÓBA [n], NASTĘPNA ZA [m] MIN” | stacja ponawia wysyłkę | czekaj; nie wysyłaj tego samego drugi raz |
| „ODBIORCA ZAPISAŁ” | odbiorca zapisał zgłoszenie | to jeszcze nie decyzja o pomocy |
| „ODBIORCA PRZECZYTAŁ” | dyżurny przeczytał zgłoszenie | czekaj na decyzję |
| „POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)” | służba, która dysponuje siłami, potwierdziła odbiorcy, że kieruje pomoc | nie podawaj mieszkańcom godziny przyjazdu |
| „PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)” | odbiorca przekazał zgłoszenie służbie; skierowanie pomocy nie jest jeszcze potwierdzone | czekaj na dalsze informacje; przy pogorszeniu zmień pilność |
| „ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ” | dyżurny nie ma teraz środków | przeczytaj odpowiedź w WIADOMOŚCI i wykonaj instrukcję |
| „ZAMKNIĘTE” | sprawa zakończona | wpisz do dziennika |

Zmiana potrzeby: WIADOMOŚCI → własne zgłoszenie → „ZMIEŃ LICZBĘ OSÓB”, „ZMIEŃ PILNOŚĆ” albo „POTRZEBA USTAŁA”. Każda zmiana jest nową wersją tego samego zgłoszenia, z tym samym krótkim numerem. „ANULUJ WYSYŁKĘ” jest w menu tylko do pierwszej wysyłki, czyli dopóki ekran pokazuje „ZAPISANE W STACJI – CZEKA NA WYSŁANIE” albo, w ciszy radiowej, „ZAPISANE – NIE WYJDZIE DO KOŃCA CISZY”. Po pierwszej wysyłce pozycja znika z menu, także po kolejnych zmianach. Wtedy użyj „POTRZEBA USTAŁA”, bo zgłoszenie mogło już dotrzeć, a odbiorca nie dowiedziałby się o anulowaniu.

Krótki numer i nazwa stacji `WICI-xxxxxx` (STAN) jednoznacznie wskazują zgłoszenie. Podawaj je gońcowi i w rozmowie przez PMR446.

## Alarmy

| Alarm | Kiedy | Co robisz |
|---|---|---|
| „BRAK POTWIERDZENIA OD [n] MIN – GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA” | brak „ODBIORCA ZAPISAŁ” po 15 min (zagrożenie życia), 1 h (pilne), 6 h (w ciągu doby) albo 30 min (TEST) | oceń drogę; wypełnij formularz w dwóch egzemplarzach i wyślij gońca albo, gdy wyjść nie można, postępuj według części [Goniec](#goniec); zgłoszenie radiowe zostaje w kolejce |
| „ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA” | tylko zagrożenie życia: brak „ODBIORCA PRZECZYTAŁ” 30 min po „ODBIORCA ZAPISAŁ” | jak wyżej; dyżurny może być zajęty albo nieobecny |
| „RADIO: AWARIA” | układ radiowy stacji nie działa (stacja sprawdza go przy starcie i co 10 s) | zgłoszenia zapisują się w stacji, ale nie wychodzą radiem: pilne formularzem i gońcem, jeśli droga jest bezpieczna ([goniec](#goniec)); zgłoś błąd osobie utrzymującej system; nie wyłączaj stacji, bo gdy układ znów zadziała, wraca do pracy sama |
| „BRAK ŁĄCZNOŚCI” w wierszu 1 albo „BRAK ŁĄCZNOŚCI – ZGŁOSZENIA NIE WYCHODZĄ. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA” na ekranie alarmu | usterka stacji: radio działa, ale oprogramowanie sieciowe stacji nie wystartowało (stacja sprawdza je przy włączeniu). To nie jest długi brak kontaktu z odbiorcą („KONTAKT [czas] TEMU”), który awarią nie jest | zgłoszenia zapisują się w stacji, ale nie wychodzą radiem: pilne formularzem i gońcem, jeśli droga jest bezpieczna ([goniec](#goniec)); zgłoś błąd osobie utrzymującej system; alarm zostaje do ponownego włączenia stacji |
| „WYMIEŃ OGNIWA W CIĄGU 1 H” | niskie napięcie ogniw | [energia](#energia-stacji) |
| „12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO 12 V” | źródło 12 V spadło do 11,5 V albo podłączone źródło ma za niskie napięcie | stacja pracuje z ogniw; podłącz naładowane źródło 12 V, a stacja przełączy się na nie sama, gdy napięcie wróci do 12,4 V. Przytrzymanie OK tylko wycisza alarm |
| „12 V ODŁĄCZONE – ZA WYSOKIE NAPIĘCIE (24 V?). STACJA PRACUJE Z OGNIW” | źródło ma napięcie powyżej 17 V, np. instalacja 24 V wozu strażackiego albo ciężarówki | stacja odcięła to wejście bez uszkodzeń i pracuje z ogniw; odłącz źródło 24 V i podłącz źródło 12 V. Wejście wraca samo, gdy napięcie spadnie poniżej progu. Przytrzymanie OK tylko wycisza alarm |

OK wycisza dźwięk alarmu. Napis i dioda zostają do usunięcia przyczyny. Dźwięk wraca przy nowym alarmie. Alarmów krytycznych nie da się wyłączyć: nie wyjmuj ogniw, żeby uciszyć stację, bo przestaje wtedy przekazywać wiadomości innych schronień.

## Goniec

Goniec niesie formularz do odbiorcy albo do najbliższej jednostki PSP lub OSP, gdy radio nie wystarcza. Wysyłasz go tylko wtedy, gdy droga jest bezpieczna. Ocenia to gospodarz, nie stacja. Tekst alarmu nie jest poleceniem wyjścia.

- Nie wysyłaj gońca przy pożarze, zalaniu, zawaleniu, skażeniu, ostrzale, alarmie o zagrożeniu, zakazie wychodzenia ani w ciemności bez latarki.
- Gońcem jest dorosła, sprawna osoba, najlepiej dwie. Idzie trasą zapisaną na pierwszej stronie dziennika. Zapisz godzinę wyjścia, krótki numer zgłoszenia i spodziewaną godzinę powrotu. Gdy goniec nie wraca w ustalonym czasie, nie wysyłaj następnego tą samą trasą bez nowej oceny.
- **Wyjście niemożliwe.** Nikogo nie wysyłaj. Jeśli stacja potwierdziła zapis („ZAPISANE W STACJI – CZEKA NA WYSŁANIE”), nie ma ciszy radiowej i żadnego z alarmów wymienionych niżej, zgłoszenie zostaje w kolejce i stacja dalej je ponawia. Nie wysyłaj go drugi raz. Po „KOLEJKA PEŁNA”, „BŁĄD PAMIĘCI STACJI”, „RADIO: AWARIA”, „BRAK ŁĄCZNOŚCI”, „STACJA NIE NADAJE – ADRES NIE OGŁOSZONY” albo w ciszy radiowej zgłoszenie nie wychodzi przez radio, nawet jeśli stacja je zapisała: zachowaj formularz papierowy i przekaż jego treść przez PMR446. Wywołaj odbiorcę albo sąsiednie schronienie przez PMR446 na kanale z planu sieci. Sąsiednie schronienie może przekazać zgłoszenie dalej. Wpisz do dziennika godzinę, alarm i powód. Oceniaj drogę ponownie: przy zagrożeniu życia co 15 min, w innych sprawach przy każdej zmianie sytuacji.

## Komunikaty od odbiorcy

Odpowiedzi i komunikaty od odbiorcy przychodzą po polsku. Każdy komunikat ma stopkę „NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA”. Nakazu wyjścia, ewakuacji ani zmiany miejsca nie wykonuj na podstawie samego komunikatu: potwierdź go w radiu (odbiornik z zestawu: Polskie Radio Program 1, fale długie 225 kHz lub FM) albo u gońca z upoważnieniem wójta. Przejęty komputer odbiorcy mógłby nadać fałszywy nakaz.

**Zagrożenie na miejscu nie czeka na potwierdzenie.** Weryfikacja dotyczy tylko polecenia, które przyszło radiem. Nie wstrzymuje działań wynikających z zagrożenia w obiekcie lub tuż obok ani procedur obiektu. Przy pożarze, dymie, alarmie czujnika CO, zalaniu, zagrożeniu zawaleniem albo na polecenie służb na miejscu wyprowadź ludzi od razu. Postępuj według instrukcji bezpieczeństwa pożarowego obiektu i poleceń zarządcy obiektu albo kierującego działaniem ratowniczym. Najpierw wyprowadź dzieci i osoby wymagające pomocy, nie używaj wind ([KG PSP, „Bezpieczna ewakuacja”](https://www.gov.pl/web/kgpsp/bezpieczna-ewakuacja-)).

**Brak drugiego kanału.** Gdy odbiornik nie odbiera, a goniec nie może wyjść ani dojść, nie wychodź na podstawie samego komunikatu. Przygotuj ludzi do wyjścia (osoby wymagające pomocy, okrycia, latarki, lista obecnych), próbuj potwierdzić co 15 min (radio publiczne, PMR446 z odbiorcą lub sąsiednim schronieniem) i zapisuj w dzienniku godzinę komunikatu i każdej próby. Jeśli w tym czasie pojawi się zagrożenie na miejscu, działaj jak wyżej.

Gdy komunikat prosi o wstrzymanie TEST, wybierz TEST → WSTRZYMAJ („TEST WSTRZYMANY PRZEZ ODBIORCĘ”). TEST → WZNÓW wybierasz dopiero po kolejnym komunikacie albo w uzgodnionym oknie.

## Cisza radiowa

Ciszę radiową poleca wójt albo wynika ona z nakazu w stanie nadzwyczajnym. Polecenie przychodzi komunikatem od odbiorcy i przez gońca. Włącz przełącznik CISZA pod osłoną i wpisz polecenie do dziennika. Ekran pokazuje „CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC”. Stacja odbiera i zapisuje, ale niczego nie nadaje, także wiadomości innych schronień. Pilne potrzeby przekazuj gońcem, jeśli droga jest bezpieczna ([goniec](#goniec)). Ciszę wyłączasz ręcznie, dopiero gdy wójt (albo inny organ, który ją polecił) ją odwoła.

Wyjątek dla pojedynczego zgłoszenia ustawia się tylko w panelu laptopa i tylko wtedy, gdy polecenie ciszy wprost go dopuszcza. Przy włączonym przełączniku CISZA wyjątku nie ma. Wyjątek zwykle nie zadziała przez przekaźniki, które same są w ciszy, więc nie zastępuje gońca.

## Energia stacji

Stacja ma dwa komplety ogniw litowych AA: kryzysowy w zamkniętym opakowaniu i ćwiczebny do TEST i przeglądów.

- W kryzysie stacja pracuje z kompletu kryzysowego. Komplet ćwiczebny jest rezerwą tylko wtedy, gdy po włożeniu i minucie pracy STAN pokazuje „OGNIWA: [x] V” z wartością co najmniej 5,6 V (wartość robocza).
- Gdy masz źródło 12 V (akumulator 12 V, akumulator LiFePO4 z BMS, wyjście 12 V stacji zasilania), podłącz je przewodem z zestawu. Ogniwa zostają rezerwą. Stacja przełącza źródła bez restartu. Gdy ekran pokazuje „12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE…”, podłącz naładowane źródło; przy „…ZA WYSOKIE NAPIĘCIE (24 V?)…” odłącz źródło 24 V i podłącz 12 V. Stacja przełączy się na nie sama, gdy jego napięcie wynosi co najmniej 12,4 V; przytrzymanie OK tylko wycisza alarm.
- Po „WYMIEŃ OGNIWA W CIĄGU 1 H” podłącz najpierw 12 V i wtedy wymień ogniwa. Bez 12 V przytrzymaj wyłącznik główny 2 s, poczekaj na „MOŻNA WYJĄĆ OGNIWA” i wymień cały komplet (+ do znaku +). Nie mieszaj ogniw różnych typów ani różnego stopnia rozładowania.
- Po włączeniu stacja może od razu pokazać alarm braku potwierdzenia albo braku odczytu dla zgłoszeń, które czekały przed wyłączeniem, bo nie wie, jak długo była wyłączona. Liczba minut w alarmie jest wtedy najmniejszą możliwą. Potwierdź OK i oceń sytuację jak przy każdym takim alarmie: jeśli stacja była wyłączona tylko na czas wymiany ogniw, poczekaj na potwierdzenie odbiorcy; jeśli dłużej, postępuj według tabeli [Alarmy](#alarmy).
- Ogniwa alkaliczne i NiMH są tylko awaryjne: na mrozie tracą większość pojemności.

„OGNIWA: OKOŁO [x] H PRACY” w STAN to szacunek. Licz z zapasem, zwłaszcza w zimnym pomieszczeniu.

## Laptop, router i strona (poziomy 2–3)

Dołączasz je, gdy stacja już działa; stacja pracuje dalej przez cały czas. Kolejność podłączenia podaje [projekt](projekt.md#dołączenie-laptopa-i-routera-poziomy-23).

- Zaloguj się do panelu hasłem z numerowanej koperty przy stacji. Po otwarciu koperty hasło zmienia osoba utrzymująca system. Wpisz numer koperty do dziennika.
- Laptop przynosi ktoś na miejscu. Panel prowadzi przez kolejne drogi: strona dla telefonów, tryb kiosku, system Linux z pamięci USB, inny laptop. System Linux z pamięci USB uruchamiasz tylko za zgodą właściciela laptopa (klawisz menu startowego: tabela na pamięci USB). Gdy trzeba wziąć inny laptop, najpierw prywatny albo Mac, potem laptop z Linuksem, na końcu laptop firmowy. Zmiana laptopa nie gubi danych: kopia jest na pamięci USB, a nowy laptop otwiera ją po Twoim zalogowaniu.
- Wi-Fi i adres strony: wpisz w panelu nazwę i hasło sieci Wi-Fi routera obiektu. Pokaż mieszkańcom dwa kody QR z ekranu laptopa (sieć i adres) albo wydrukuj z panelu plakat. Laptop połącz z gniazdem LAN routera, nie WAN. Telefony łączą się z siecią, którą wskaże panel (zwykle główną, bo gościnna często nie widzi laptopa).
- Gdy telefony nie mogą się połączyć, włącz tryb kiosku: mieszkańcy zgłaszają się po kolei na ekranie laptopa. Panel gospodarza jest wtedy zablokowany do czasu ponownego logowania. Nie zostawiaj laptopa bez nadzoru: to zwykle cudzy laptop z otwartą sesją właściciela.
- Przed oddaniem laptopa właścicielowi wybierz w panelu „Oddaj laptop”: aplikacja zapisuje ostatnią kopię na pamięci USB i usuwa dane z dysku.
- Zgłoszenie z telefonu trafia najpierw do Twojej kolejki w panelu i nie wychodzi radiem samo. Sprawdź je, połącz z powtarzalnymi, ustal pilność i zatwierdź.
- Mieszkaniec dostaje lokalny numer zgłoszenia („ZAPISZ NUMER [xxxx] – PODAJ GOSPODARZOWI DO SPRAWDZENIA STANU”). Gdy straci dostęp na telefonie, sprawdź stan po tym numerze w panelu.
- Brak energii: najpierw wyłącz laptop i router. Stacja pracuje dalej z ogniw lub 12 V.

### Stacja zasilania (poziom 3)

- Laptop, router i ładowarkę telefonów zasila kupiona stacja zasilania. Stacja WICI może brać 12 V ze stacji zasilania, ale po jej wyczerpaniu pracuje dalej z ogniw.
- Sprawdź na wyświetlaczu stacji zasilania stan naładowania, włącz wyjście 230 V według instrukcji producenta, potem podłącz zasilacze laptopa i routera oraz ładowarkę telefonów.
- Ładuj stację zasilania albo wymieniaj ją na naładowaną, zanim pokaże stan krytyczny. Ładowanie z pojazdu albo agregatu tylko na zewnątrz, kilka metrów od wejść i wlotów powietrza.
- Wyczerpanie stacji zasilania wyłącza laptop, router i ładowanie telefonów, ale nie łączność.

## Przekazanie zmiany

Zmiana trwa najwyżej 12 h. Przed zejściem ze zmiany otwórz STAN → PRZEKAZANIE ZMIANY: otwarte i niepotwierdzone zgłoszenia, nieprzeczytane wiadomości, energia, cisza i wyciszenie dźwięku. Przekaż następcy ostatnie odpowiedzi odbiorcy, dostępne źródła energii, awarie i kanał zastępczy. Wpisz przekazanie do dziennika i podpisz. Nie kasuj niepotwierdzonych zgłoszeń.

## Koniec zdarzenia i zniszczenie danych

**ZAMKNIJ ZDARZENIE** wykonuje się po odwołaniu stanu kryzysowego, tylko na polecenie gminy przekazane słownie, przez gońca albo pisemnie, nigdy na podstawie wiadomości radiowej. Na stacji wybierz STAN → USŁUGI → ZAMKNIJ ZDARZENIE. Ekran pokazuje „ZAMKNĄĆ ZDARZENIE? ZGŁOSZENIA I WIADOMOŚCI ZNIKNĄ ZE STACJI. TYLKO NA POLECENIE GMINY”. Potwierdź: GÓRA, DÓŁ, GÓRA, OK. Stacja usuwa zgłoszenia i wiadomości, także niewysłane. Gdy pracujesz z laptopem (poziomy 2–3), uruchom operację w panelu zamiast w menu stacji. Panel zapisuje zaszyfrowane archiwum dla administratora danych, a stacja pyta „LAPTOP: ZAMKNĄĆ ZDARZENIE? …” i czeka na OK. Po zamknięciu zdarzenia poproś zarządcę o zmianę hasła Wi-Fi routera obiektu, jeśli mieszkańcy korzystali ze strony. Tożsamość stacji, karta odbiorcy i adres zostają, więc stacja jest gotowa do następnego użycia. Wpisz polecenie i godzinę do dziennika. Dziennik papierowy przekaż gminie. Potem odłóż stację do skrzynki i zgłoś zużycie ogniw organizatorowi sieci.

**ZNISZCZ DANE** (STAN → USŁUGI) uruchamiasz tylko przy groźbie przejęcia stacji lub laptopa: gdy sam ją widzisz albo gdy odbiorca powiadomi o niej słownie lub przez gońca. Nigdy na podstawie wiadomości radiowej. Ekran pokazuje „GROŹBA PRZEJĘCIA? USUNIĘCIE DANYCH NIEODWRACALNE. START BEZ KONFIGURACJI”. Potwierdź: GÓRA, DÓŁ, GÓRA, OK. Z laptopem: zaloguj się w panelu, wybierz zakładkę „Zestaw” → ZNISZCZ DANE i potwierdź dwa razy. Laptop od razu usuwa dane zestawu, a stacja pyta „LAPTOP: ZNISZCZYĆ DANE? …” i czeka na OK. Jeśli nie możesz się zalogować, zniszcz dane na stacji. Pamięć USB zestawu zniszcz fizycznie, bo samo usunięcie plików jej nie chroni. Stacja traci tożsamość i konfigurację; do pracy wraca dopiero po ponownym przygotowaniu przez osobę utrzymującą system. Do tego czasu zgłoszenia wysyłasz formularzem przez gońca, jeśli droga jest bezpieczna ([goniec](#goniec)). Wpisz zdarzenie do dziennika.

## Bezpieczeństwo w schronieniu

- Nie uruchamiaj silnika pojazdu ani agregatu w schronieniu, w garażu, przy wejściu ani przy wlotach powietrza: tlenek węgla zabija bez ostrzeżenia. Pojazd jako źródło 12 V stoi na zewnątrz, kilka metrów od wejść. Przewód nie może trzymać otwartych drzwi.
- Bateryjny czujnik tlenku węgla z zestawu poziomu 3 umieść w pomieszczeniu z ludźmi. Przy alarmie wyprowadź ludzi na świeże powietrze i wyślij zgłoszenie z kategorią „ZAGROŻENIE BUDYNKU”.
- Akumulatory stawiaj na tacy, z dala od dróg ewakuacyjnych. Nie ładuj akumulatorów w pomieszczeniu z ludźmi. Gaśnica stoi przy stacji. Zapisz jej miejsce w dzienniku.
- Nie podchodź do anteny zewnętrznej i nie podłączaj jej podczas burzy. Antenę zapasową wystawiasz przez okno tylko wtedy, gdy nie ma zamontowanej. Przewodu nie prowadź przez drzwi hermetyczne, gazoszczelne ani przeciwpożarowe.

## Gdy coś nie działa

Najpierw ustal, czego dotyczy błąd: strony, laptopa, stacji, trasy radiowej, odbiorcy czy zasilania. Pełną tabelę podaje [koncepcja, rozdział 02](../concept/02-scenariusze-i-organizacja.html#zachowanie-w-scenariuszach-awarii).

| Objaw | Działanie |
|---|---|
| długo „WYSYŁANIE – PRÓBA [n] …” | sprawdź przewód antenowy i złącze; zapytaj sąsiednie schronienie przez PMR446, czy jego stacja działa; pilne zgłoszenie przez gońca, jeśli droga jest bezpieczna |
| „KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO” albo „BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA” | formularz i goniec ([goniec](#goniec)); zgłoś błąd osobie utrzymującej system |
| „STACJA NIE NADAJE – ADRES NIE OGŁOSZONY. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA” po OGŁOŚ ADRES | stacja nie wyśle radiem żadnego zgłoszenia: formularz i goniec ([goniec](#goniec)); zgłoś błąd osobie utrzymującej system |
| stacja uruchomiła się ponownie | sprawdź ekran i zatwierdź proponowany TEST; kolejka zostaje w stacji; po wyłączeniu zasilania alarm braku potwierdzenia może przyjść od razu ([energia](#energia-stacji)) |
| laptop się zawiesił lub odłączył | stacja pracuje dalej; po powrocie laptopa sprawdź stan zgłoszeń w panelu |
| stacja uszkodzona | goniec ([goniec](#goniec)) i PMR446; zgłoś organizatorowi sieci potrzebę stacji zapasowej |

Nie uruchamiaj drugiej stacji z tą samą tożsamością i nie resetuj routera znalezionego na miejscu bez zgody właściciela.

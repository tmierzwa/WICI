# WICI: instrukcja dyżurnego

Instrukcja jest dla dyżurnych stanowiska odbiorczego, czyli stanowiska wyznaczonego przez wójta (burmistrza, prezydenta miasta) do przyjmowania zgłoszeń schronień. Na ekranie stacji i w instrukcji opiekuna stanowisko nazywa się „odbiorcą”. Skrót OSP oznacza w tej instrukcji tylko ochotniczą straż pożarną, także wtedy, gdy to jej jednostka prowadzi stanowisko. Budowę stanowiska, panel i postępowanie przy awarii opisuje [stanowisko odbiorcze](stanowisko-osp.md); tu są czynności dyżurnego. Napisy z ekranu stacji w cudzysłowach są cytatami z tabeli [Teksty ekranu](oprogramowanie.md#teksty-ekranu). Instrukcja opisuje stanowisko po odbiorze technicznym; takiego stanowiska jeszcze nie zbudowano. W instrukcji nie zapisuje się kluczy, haseł ani danych mieszkańców.

## Twoja rola

- Czytasz zgłoszenia schronień i potwierdzasz ich przeczytanie.
- Oceniasz, kto może pomóc, i przekazujesz zgłoszenie służbom zdolnym do pomocy (PSP, OSP, PRM, Policja, służby komunalne) według gminnego planu zarządzania kryzysowego. Nie zlecasz im działań i sam nie kierujesz sił.
- Odsyłasz schronieniu stan sprawy: przekazanie, potwierdzone skierowanie pomocy albo odpowiedź z instrukcją, gdy nikt nie może teraz pomóc.
- Rozsyłasz komunikaty na polecenie wójta lub sztabu kryzysowego.
- Pilnujesz listy zaufanych stacji i kwarantanny; reagujesz na podejrzenie przejęcia.
- Prowadzisz papierowy dziennik zgłoszeń i decyzji.

Stan zgłoszenia nie jest obietnicą przyjazdu. WICI nie zastępuje numeru 112: zgłoszenie zagrożenia życia, które da się przekazać telefonem, przekazujesz telefonem.

## Początek dyżuru

1. Sprawdź, czy stacja stanowiska jest włączona i podłączona do anteny, zasilania i komputera. Ekran stacji pokazuje „RADIO WŁĄCZONE” i „KOMPUTER [czas] TEMU”; „BRAK KOMPUTERA” znaczy, że komputer nie przesłał jeszcze żadnego pakietu.
2. Aplikacja stanowiska pracuje bez przerwy od początku zdarzenia; panel pokazuje to po zalogowaniu. Tylko gdy aplikacja nie działa (początek zdarzenia, po awarii lub restarcie komputera), włącz komputer z podłączonym nośnikiem stanowiska i uruchom aplikację. Aplikacja pyta o hasło stanowiska z numerowanej, zaklejonej koperty przy stanowisku. Numer otwartej koperty wpisz do dziennika; hasło zmienia potem osoba utrzymująca system.
3. Zaloguj się do panelu własnym kontem. Każde działanie trafia do dziennika działań pod Twoim kontem; nie pracuj na cudzym.
4. Sprawdź w panelu stan węzła: połączenie ze stacją, czas od ostatniego pakietu z radia, intencje w drodze i w oczekiwaniu. Długi czas bez ruchu nie jest awarią, jeśli schronienia nie wysyłają zgłoszeń.
5. Przeczytaj przekazanie zmiany: otwarte zgłoszenia, sprawy przekazane bez potwierdzenia skierowania pomocy, niewysłane odpowiedzi, kwarantannę i godzinę ostatniej kopii bazy.

## Zgłoszenie i decyzja

Panel sortuje zgłoszenia według pilności, potem czasu odbioru. Zgłoszenie z pilnością „ZAGROŻENIE ŻYCIA” włącza alarm dźwiękowy. Każde zgłoszenie ma nazwę stacji `WICI-xxxxxx`, adres i wejście, kategorię, liczbę osób, pilność i krótki opis. Przy przekazaniu telefonicznym lub przez gońca podawaj nazwę stacji i czterocyfrowy krótki numer zgłoszenia.

Schronienie widzi „ODBIORCA ZAPISAŁ”, gdy tylko aplikacja zapisze zgłoszenie; nie wymaga to Twojego działania. Dalsze stany zależą od Ciebie:

| Twoje działanie | Ekran w schronieniu | Kiedy |
|---|---|---|
| PRZECZYTANE | „ODBIORCA PRZECZYTAŁ” | od razu po przeczytaniu; przy zagrożeniu życia w ciągu 30 min, inaczej schronienie dostaje alarm i wysyła gońca, jeśli droga jest bezpieczna |
| stan 4 | „PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)” | przekazałeś zgłoszenie służbie, która może pomóc, ale nie masz jeszcze potwierdzenia, że skierowała pomoc |
| stan 3 | „POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)” | podmiot, który dysponuje siłami (np. stanowisko kierowania PSP, dyspozytor medyczny, służba gminy), potwierdził ci skierowanie pomocy; panel wymaga wpisania, kto potwierdził (podmiot i funkcja osoby), jakim kanałem i o której |
| stan 5 z odpowiedzią | „ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ” | nikt nie może teraz pomóc; odpowiedź mówi, co schronienie ma zrobić (np. użyć kanału zastępczego) |
| stan 6 | „ZAMKNIĘTE” | potrzeba ustała albo sprawa jest zakończona |

- Przekazanie (stan 4) i potwierdzone skierowanie pomocy (stan 3) to dwa różne stany. Własna ocena, że pomoc „pewnie wyjedzie”, nie wystarcza do stanu 3. Gdy potwierdzenie przychodzi w ciągu kilku minut od przekazania, wyślij od razu stan 3 bez stanu 4; gdy przyjdzie później, wyślij stan 3 jako kolejną decyzję.
- Źródło i czas potwierdzenia zostają w bazie stanowiska i w dzienniku papierowym; nie idą radiem do schronienia.
- Każda wiadomość zajmuje wspólny kanał radiowy na kilkadziesiąt sekund, a cała sieć przenosi od kilkudziesięciu do około 120 zgłoszeń na godzinę. Na zgłoszenie wysyłaj PRZECZYTANE i zwykle jedną decyzję; drugą (potwierdzone skierowanie po przekazaniu) tylko wtedy, gdy potwierdzenie przyszło później. Nie zmieniaj stanu bez potrzeby.
- Panel nie wyśle stanu 5 bez odpowiedzi. Odpowiedź ma najwyżej 96 bajtów: 96 znaków bez polskich liter, mniej z nimi, bo polska litera zajmuje 2 bajty.
- W odpowiedziach i komunikatach nie wpisuj nazwisk ani informacji o zdrowiu konkretnej osoby.
- Zmiana zgłoszenia w schronieniu (liczba osób, pilność, „potrzeba ustała”) przychodzi jako nowa wersja tego samego zgłoszenia; panel pokazuje je razem, a każdą wersję potwierdza się osobno.
- Nietypowe zgłoszenie (np. wezwanie wielu służb w jedno miejsce) potwierdź drugim kanałem przed przekazaniem służbom.

## TEST

TEST to próbne zgłoszenie ze stacji schronienia. Panel pokazuje go osobno i nie wlicza do potrzeb. Sprawdź, czy adres i wejście są zrozumiałe, i odpowiedz PRZECZYTANE; kilka TEST możesz potwierdzić razem, po sprawdzeniu adresu każdego. Stany 3–6 dla TEST wysyła się tylko w uzgodnionym ćwiczeniu.

Gdy wiele stacji włącza się naraz i kanał jest zajęty, wyślij komunikat z prośbą o wstrzymanie TEST. Opiekunowie wstrzymują TEST ręcznie; stacja nie robi tego sama.

## Komunikaty

Komunikat rozsyłasz na polecenie wójta lub sztabu kryzysowego, po polsku, do 192 bajtów (polska litera zajmuje 2 bajty). Panel wysyła go osobno do każdej stacji i pokazuje postęp; dla 50 stacji trwa to około 12 minut, więc nie wysyłaj komunikatów, które mogą poczekać.

Każdy komunikat ma na ekranie stacji stopkę „NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA”. Opiekunowie nie wykonają nakazu wyjścia, ewakuacji ani zmiany miejsca na podstawie samego komunikatu. Taki nakaz uzgodnij z wójtem tak, aby równolegle poszedł przez radio publiczne albo gońców z upoważnieniem. Weryfikacja nie wstrzymuje ewakuacji z powodu zagrożenia na miejscu: przy pożarze, dymie, alarmie czujnika CO, zalaniu, zagrożeniu zawaleniem albo na polecenie służb na miejscu opiekun wyprowadza ludzi od razu według procedur obiektu ([instrukcja opiekuna](instrukcja.md#komunikaty-od-odbiorcy)).

## Zaufanie i kwarantanna

- **Kwarantanna.** Zgłoszenie od stacji spoza listy zaufanych trafia do kwarantanny i nie dostaje „ODBIORCA ZAPISAŁ”. Zanim je zatwierdzisz, potwierdź je drugim kanałem: goniec, PMR446, telefon, służby na miejscu. Zatwierdzenie dotyczy tylko tej jednej wiadomości. Po zatwierdzeniu traktuj zgłoszenie jako niesprawdzone źródło.
- **Dodanie do listy** (np. stacja zastępcza ze schronienia albo stacja usunięta przez pomyłkę) wymaga karty stacji, porównania odcisku z ekranem stacji albo z ewidencją i zgody dwóch zalogowanych dyżurnych. Nie dodawaj stacji na podstawie samej wiadomości radiowej.
- **Usunięcie z listy.** Gdy stacja zaginęła, została skradziona albo opiekun zgłasza jej przejęcie, usuń ją z listy w panelu i wpisz powód do dziennika; zgoda drugiego dyżurnego nie jest potrzebna. Jej nowe wiadomości trafiają potem do kwarantanny z alarmem „możliwe przejęcie stacji”. Takiej wiadomości nie zatwierdzaj bez potwierdzenia drugim kanałem u opiekuna schronienia.

## Cisza radiowa

Ciszę radiową poleca wójt albo wynika ona z nakazu w stanie nadzwyczajnym. Przekaż ją schronieniom komunikatem i gońcami; rozesłanie komunikatu do 50 stacji trwa około 12 minut. Jeśli polecenie obejmuje też stanowisko, włącz przełącznik CISZA na stacji stanowiska dopiero po rozesłaniu i wpisz godzinę do dziennika. W ciszy stanowisko odbiera, ale nie potwierdza zgłoszeń; pilne sprawy idą gońcem. Odwołanie ciszy przekazujesz tak samo: komunikatem po wyłączeniu przełącznika i gońcami.

## Przekazanie zmiany

Przed zejściem ze zmiany otwórz w panelu przekazanie zmiany i wykonaj kopię bazy na drugi nośnik (panel pokazuje godzinę ostatniej kopii). Przekaż następcy otwarte zgłoszenia, zgłoszenia bez PRZECZYTANE, sprawy przekazane bez potwierdzenia skierowania pomocy, kwarantannę, niewysłane odpowiedzi i komunikaty, stan zasilania i awarie. Wpisz przekazanie do dziennika i podpisz. Wyloguj się; nie zostawiaj panelu otwartego na swoim koncie.

## Awarie

| Objaw | Działanie |
|---|---|
| komputer zawiesił się lub nie startuje | sieć dalej przekazuje ruch, a schronienia ponawiają zgłoszenia. Przełóż nośnik stanowiska do komputera zapasowego, uruchom aplikację z hasłem stanowiska i zaloguj się; cel: ≤15 min. Zaległe zgłoszenia przyjdą same; aplikacja nie przyjmie ich dwa razy |
| ekran stacji pokazuje „BRAK KOMPUTERA” albo „KOMPUTER [czas] TEMU” z czasem ponad 8 h (komputer ogłasza adres co 6 h ±20%, więc krótsza cisza jest normalna) | sprawdź przewód USB i to, czy aplikacja działa; panel pokazuje wtedy brak połączenia ze stacją |
| stacja stanowiska uszkodzona | podłącz stację zapasową do tej samej anteny, zasilania i przewodu USB. Tożsamość odbiorcy jest na komputerze, więc schronienia niczego nie zmieniają |
| nośnik stanowiska uszkodzony | wezwij osobę utrzymującą system; odtworzenie z kopii bazy. Zgłoszenia przyjęte po ostatniej kopii i decyzje wysłane po niej odtwarzasz z dziennika papierowego, bo schronienia, które dostały „ODBIORCA ZAPISAŁ”, ich nie ponowią |
| brak zasilania | laptop pracuje z akumulatora; uruchom agregat albo stację zasilania i przełącz źródło przed wyczerpaniem akumulatora |
| dużo zgłoszeń w kwarantannie albo wiadomości od stacji usuniętej z listy | możliwa próba podszycia; nie zatwierdzaj bez drugiego kanału; zawiadom organizatora sieci |

**Podejrzenie przejęcia stanowiska** (kradzież komputera lub nośnika, ktoś obcy przy działającym komputerze): zawiadom wójta i organizatora sieci. O przełączeniu schronień na klucz zapasowy odbiorcy (KLUCZ ZAPASOWY) decyduje wójt; polecenie idzie do opiekunów wyłącznie słownie albo przez gońców, nigdy komunikatem radiowym. Klucz zapasowy należy do tego samego stanowiska: osoba utrzymująca system wczytuje tożsamość zapasową z obu kopert od organizatora sieci na komputer zapasowy z nowym nośnikiem i pustą bazą. Zanim aplikacja zacznie przyjmować zgłoszenia, ta sama osoba wczytuje karty zaufanych stacji z ewidencji (zatwierdzasz to razem z drugim dyżurnym) i zakłada od nowa konta dyżurnych z nowymi hasłami; potem aplikacja ogłasza nowy adres. Schronienia po przełączeniu wysyłają niepotwierdzone zgłoszenia ponownie; otwarte sprawy odtwarzasz z dziennika papierowego. Gdy stanowisko nie może dalej pracować i zgłoszenia ma przejąć inne stanowisko, schronienia przechodzą na kanał zastępczy z planu sieci; wydanie 0.5 nie przełącza stacji do innego odbiorcy. Gdy grozi przejęcie stanowiska, uruchom w panelu ZNISZCZ DANE i zniszcz fizycznie oba nośniki; zapisz to w dzienniku.

## Koniec zdarzenia

ZAMKNIJ ZDARZENIE wykonuje się na polecenie gminy po odwołaniu stanu kryzysowego. Operacja zapisuje zaszyfrowane archiwum dla administratora danych i usuwa treść zgłoszeń. Tożsamość odbiorcy, karty stacji i klucze odbioru zostają, więc stanowisko jest gotowe do następnego użycia. Dziennik papierowy przekaż administratorowi danych według planu gminy.

## Bezpieczeństwo stanowiska

- Komputer stanowiska nie łączy się z siecią. Nie podłączaj do niego Wi-Fi, przewodu sieciowego, telefonu ani obcych pamięci USB; jedyne połączenia to stacja i nośnik stanowiska.
- Odchodząc od komputera, zablokuj ekran; panel blokuje się sam po 5 minutach.
- Nie uruchamiaj agregatu w pomieszczeniu, w garażu, przy wejściu ani przy wlotach powietrza: tlenek węgla zabija bez ostrzeżenia.
- Nie podchodź do anteny i masztu podczas burzy.

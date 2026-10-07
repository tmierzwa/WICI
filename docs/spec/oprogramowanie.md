# WICI: oprogramowanie

## Podział oprogramowania

**Oprogramowanie układowe stacji** zawiera port microReticulum z włączonym transportem, moduł LXMF (LXMRouter) z jedną tożsamością stacji, sterownik P1, trwałą kolejkę i skrzynkę odbiorczą w pamięci FRAM, interfejs ekranu i przycisków, protokół USB do laptopa oraz układ nadzorujący (watchdog). Stacja jest jedynym węzłem sieci w schronieniu i działa bez laptopa. Wersje referencyjne protokołu: Reticulum `e40191b` i LXMF `c3ff2d6`. Implementację LXMF dla mikrokontrolera (z istniejących projektów albo własną, zgodną z wersją referencyjną) wybiera się w D14 po T3. [microReticulum](https://github.com/attermann/microReticulum), [LXMF](https://github.com/markqvist/LXMF).

LXMF pakuje wiadomości, szyfruje je przez Reticulum, wyszukuje trasę, potwierdza dostarczenie na poziomie transportu i ponawia wysyłkę. Tych mechanizmów nie implementuje się drugi raz. Stan DELIVERED w LXMF nie oznacza zatwierdzonej transakcji w bazie OSP. Kolejka intencji jest w FRAM i stacja odtwarza ją po restarcie. Lista oczekujących wiadomości w pamięci LXMF nie jest trwałą kolejką.

**Aplikacja laptopa** (`station-web`, poziomy 2–3) zawiera serwer lokalnej strony, jedną bazę SQLite i panel opiekuna lub dyżurnego. Nie uruchamia Reticulum ani LXMF i nie ma tożsamości sieciowej; wiadomości przekazuje stacji [protokołem USB](#protokół-usb-laptopstacja). Odłączenie laptopa nie przerywa pracy stacji. Restart strony nie zmienia kolejki stacji. Stanowisko OSP to stacja z laptopem; transakcja przyjęcia zgłoszenia i RECEIVED odbywa się w SQLite aplikacji OSP.

NomadNet i narzędzia Reticulum w Pythonie nie są częścią wydania. Mogą służyć w laboratorium do prób zgodności (T3) jako osobne węzły z własną tożsamością. Nie wolno wymagać od mieszkańców instalacji klienta. [NomadNet](https://github.com/markqvist/NomadNet).

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik. Treść do 480 B, bez załączników. Limit 480 B jest przejściowy: docelowo każda wiadomość SA1 mieści się po kodowaniu w jednym pakiecie okazjonalnym LXMF, około 284 B dla wersji referencyjnych ([koncepcja, rozdział 05](../conception/05-projekt-koncepcyjny-komunikacji.html#rozmiar-wiadomosci-a-sposob-dostarczenia)). Wartość wpisuje się tu po zamknięciu D01, a limity pól `text` i `location` zmniejsza się tak, by zmieścił się przypadek najgorszy po kodowaniu. JSON zawiera jedną tablicę; swobodne obiekty są odrzucane. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`. Teksty nie mogą zawierać znaków sterujących ani formatujących Unicode (kategorie Cc i Cf), w tym znaków C1, znaków zmiany kierunku pisma i niewidocznych znaków formatujących. Zwykłe polskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |
| TEST = 5 | `[1,5,id,revision,category,people,location,text,urgency]` |

`id`: 32 małe cyfry szesnastkowe, czyli 16 losowych bajtów. `revision`: 0–65 535. `category`: 0–9 = 0 pomoc medyczna (zagrożenie życia lub zdrowia); 1 leki stałe i sprzęt medyczny (tlen, insulina, dializy); 2 ewakuacja i transport, w tym osób leżących i z niepełnosprawnością; 3 woda pitna; 4 żywność, w tym dla niemowląt; 5 ogrzewanie, energia, paliwo; 6 sanitarne i higiena; 7 bezpieczeństwo obiektu (pożar, CO, zalanie, uszkodzenie); 8 informacja i poszukiwanie osób; 9 inne. `people`: 1–65 535. `location`: 1–64 B, dokładny adres i miejsce wejścia. `text` zgłoszenia i odpowiedzi: do 96 B; komunikatu: do 192 B. `urgency`: 2 = bezpośrednie zagrożenie życia lub zdrowia; 1 = pilne, w ciągu kilku godzin; 0 = w ciągu doby; podwyższenie zatwierdza opiekun. Przy pilności 2 opiekun równolegle udziela pierwszej pomocy i – gdy droga jest bezpieczna – wysyła gońca do najbliższej jednostki PSP/OSP lub zespołu ratownictwa medycznego. WICI nie zastępuje numeru 112. `event`: 1–2 147 483 647, bez zawijania licznika; nowy komunikat po wyczerpaniu licznika dostaje nowe id. `state`: 1 = zapisane u odbiorcy (na ekranie „ZAPISANE U ODBIORCY”), 2 = przeczytane, 3 = pomoc skierowana, 4 = przekazane innemu podmiotowi (PSP, PRM, powiat), 5 = obecnie brak możliwości pomocy – użyj kanału zastępczego, 6 = zamknięte (potrzeba ustała).

RECEIVED zawsze oznacza pierwsze przyjęcie, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2–6; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli OSP ma już nowszy status, wysyła też najnowszy STATUS. Źródło ignoruje starsze wartości event dla tej samej pary id i revision. Nowszy STATUS może zmienić stan na dowolny z 2–6; po stanie 6 (zamknięte) zgłoszenie zmienia się tylko nową rewizją. REPLY ma numerację event niezależną od STATUS. BULLETIN jest numerowany w obrębie swojego id.

TEST ma tablicę, limity i walidację REQUEST. Sprawdza całą drogę zgłoszenia: transport, zapis w OSP i obecność dyżurnego. Stacja proponuje go na ekranie po uruchomieniu, restarcie oraz zmianie anteny lub odbiorcy i wysyła na polecenie opiekuna z menu lub panelu; nigdy cyklicznie. Propozycja: TEST startowy (po uruchomieniu i restarcie) wychodzi z losowym opóźnieniem 0–15 min od polecenia, aby wiele stacji włączonych naraz nie zajęło kanału. Kolejność uruchamiania stacji ustala plan gminy. OSP może wstrzymać TEST komunikatem BULLETIN; opiekun nie wysyła wtedy TEST do odwołania, a oczekujący TEST może anulować przed nadaniem. Pojemność sieci gminy w zgłoszeniach na godzinę wyznacza się w T5; obliczenie z [rozdziału 06](../conception/06-wykonalnosc-i-budzet-zasobow.html) daje dla jednego przekaźnika najwyżej około 140 zgłoszeń na godzinę przy zerowych stratach. Zgłoszenia wysyłane podczas prób i ćwiczeń również mają typ TEST. TEST startowy zawiera rzeczywisty adres i wejście schronienia, aby dyżurny mógł potwierdzić, że są zrozumiałe. OSP przyjmuje TEST jak REQUEST: weryfikacja nadawcy, kwarantanna nieznanej stacji, deduplikacja, jedna transakcja i RECEIVED po COMMIT. Klucz odbioru nie zależy od typu; REQUEST i TEST o tym samym id i revision to konflikt treści. Stanowisko OSP pokazuje TEST osobno od kolejki potrzeb i nie wlicza go do potrzeb. Dyżurny odpowiada wiadomością STATUS ze state=2. Wartości state 3–6 dla TEST są dopuszczalne tylko w uzgodnionym ćwiczeniu i oznaczają decyzję ćwiczebną bez wysłania pomocy. Stacja pokazuje TEST na ekranie i w panelu opiekuna, nie jako zgłoszenie mieszkańca.

Zmiana danych zgłoszenia tworzy nową rewizję (revision). Każda rewizja zawiera pełną lokalizację i treść, więc odbiorca nie potrzebuje wcześniej przekazanych danych o budynku. Stanowisko pokazuje rewizje jako jedno zgłoszenie, ale każdą potwierdza się osobno. Przez radio nie wysyła się imion, numerów PESEL, danych dokumentów ani tokenów strony. Dyżurny nie wpisuje nazwisk ani informacji o zdrowiu do REPLY i BULLETIN. Typ stanu obiektu (MELDUNEK) nie jest częścią SA1 0.5 – rozstrzyga D18.

Zgłoszenie z przycisków (poziom 1) tworzy stacja: `category` i `urgency` z menu, `people` 1–999 z przycisków, `location` z adresu zapisanego podczas przygotowania, `text` pusty albo jedna z gotowych fraz z konfiguracji (każda ≤96 B UTF-8, zapisana po polsku; ekran pokazuje jej tłumaczenie z konfiguracji w wybranym języku, a dyżurny otrzymuje wersję polską). `urgency` = 2 wymaga dodatkowego potwierdzenia. Ekran i panel pokazują krótki numer zgłoszenia: pierwsze 16 bitów `id` modulo 10 000, jako cztery cyfry. Numer ten razem z nazwą stacji `WICI-xxxx` wystarcza, by przekazać zgłoszenie telefonicznie lub przez gońca; przy niejednoznaczności dyżurny podaje adres.

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zgłoszenie z przycisków | zgłoszenie + intencja wysyłki w FRAM stacji |
| Zgłoszenie ze strony | w SQLite laptopa: zgłoszenie + token dostępu + intencja przekazania; w stacji: zgłoszenie + intencja wysyłki, idempotentnie po id i revision |
| Przyjęcie w OSP | zweryfikowane zgłoszenie + tożsamość nadawcy + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS |

FRAM stacji: dziennik z rekordami zawierającymi numer, długość, CRC-32 i znacznik zatwierdzenia; rekord bez znacznika po restarcie jest odrzucany. Zapis jest zatwierdzony (COMMIT stacji) po zapisaniu znacznika. Przed wyłączeniem przy niskim napięciu ogniw stacja kończy bieżący zapis. SQLite laptopa: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone. Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią oznacza konflikt; dane nie są nadpisywane.

Przed zapisem funkcja zwrotna odbioru sprawdza `signature_validated`, zaufanie do nadawcy i limit rozmiaru. Stacja przyjmuje RECEIVED, STATUS, REPLY i BULLETIN wyłącznie od przypiętej tożsamości OSP; inne odrzuca i liczy w diagnostyce. Nazwa wyświetlana i pole JSON nie nadają uprawnień. W OSP REQUEST i TEST nieznanej stacji trafiają do kwarantanny i czekają na decyzję dyżurnego. Kwarantanna jest zapisem trwałym, ale nie przyjęciem: RECEIVED wysyła się dopiero po zatwierdzeniu nadawcy przez dyżurnego. Zgłoszenie z kwarantanny nie jest traktowane jak zgłoszenie ze zweryfikowanego schronienia. Kartę OSP zapisuje się w stacji tylko podczas przygotowania, po przytrzymaniu przycisku konfiguracji na stacji; nigdy przez radio.

Proces kolejki wysyła RECEIVED i każde inne potwierdzenie aplikacyjne dopiero po COMMIT. Brak miejsca, uszkodzenie bazy lub dziennika FRAM albo błąd fsync blokują komunikat „zapisane lokalnie”. Stacja i aplikacja nie tworzą automatycznie pustego magazynu w miejsce uszkodzonego. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. [Trwałość SQLite](https://sqlite.org/atomiccommit.html).

Wysyłanie: najwyżej jedna aktywna wiadomość aplikacji do danego odbiorcy. LXMF ponawia aktywną próbę. Po błędzie LXMF lub braku RECEIVED stacja ponawia intencję po 1, 2 i 5 minutach, a następnie co 15 minut z losowym przesunięciem ±20%; po 6 godzinach odstęp rośnie do 60 minut. Nigdy nie ponawia równolegle z wciąż aktywną wysyłką. Intencja nie jest usuwana automatycznie; po 6 godzinach bez RECEIVED ekran zaleca procedurę zastępczą. Nowa wiadomość LXMF może mieć inny skrót (hash); id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji OSP. Kolejność w kolejce stacji: RECEIVED i STATUS, potem REPLY i BULLETIN, potem REQUEST z `urgency` = 2, potem pozostałe REQUEST i TEST według czasu COMMIT. Nie oznacza to priorytetu w całej sieci.

Limity: kolejka wychodząca stacji do 128 intencji, skrzynka odbiorcza do 128 wiadomości (najpierw usuwa się najstarsze przeczytane BULLETIN), dziennik zdarzeń stacji jako bufor pierścieniowy 32 KiB. Pełna kolejka blokuje nowe zgłoszenie komunikatem „KOLEJKA PEŁNA – NIE WYSŁANO”; nigdy nie daje pozornego „zapisane lokalnie”. Aplikacja laptopa odmawia zapisu, gdy wolne miejsce spada poniżej 100 MB, a jej dziennik ma rotację do 10 MB. Wybór odbiorcy zastępczego nie jest częścią wydania; obowiązuje procedura zastępcza z [koncepcji](../conception/02-scenariusze-i-organizacja.html#siec-i-odbiorca-zastepczy).

## API lokalnej strony (poziomy 2–3)

| Adres | Działanie |
|---|---|
| `GET /` | informacje, formularz, komunikaty |
| `POST /api/request` | walidacja i trwały zapis w kolejce opiekuna; 201 dopiero po COMMIT; nie wysyła radiem |
| `GET /api/request/<token>` | treść i status tylko własnego zgłoszenia |
| `POST /api/request/<token>` | zmiana własnego zgłoszenia; tworzy nową rewizję |
| `GET /operator` | logowanie opiekuna |
| `GET /api/operator/queue` | kolejka lokalna; wymaga uwierzytelnienia |
| `POST /api/operator/approve` | sprawdzenie zgłoszenia mieszkańca, połączenie z powtarzalnym, ustalenie pilności i przekazanie do wysyłki |
| `POST /api/operator/test` | wysłanie TEST |
| `POST /api/operator/announce` | jednorazowe ogłoszenie adresu stacji |
| `POST /api/operator/status` | decyzja OSP; tylko rola OSP |
| `POST /api/operator/reply` | odpowiedź REPLY do zgłoszenia; tylko rola OSP |
| `POST /api/operator/bulletin` | komunikat BULLETIN; tylko rola OSP |
| `POST /api/operator/quarantine` | zatwierdzenie lub odrzucenie nadawcy z kwarantanny; tylko rola OSP |
| `POST /api/operator/configure` | adres schronienia, karta OSP i gotowe frazy; tylko podczas przygotowania, po przytrzymaniu przycisku konfiguracji na stacji |
| `POST /api/operator/export` | operacja PRZENIEŚ STACJĘ |
| `POST /api/operator/import` | przyjęcie paczki z operacji PRZENIEŚ STACJĘ na nowym laptopie lub stacji zapasowej |
| `POST /api/operator/silence` | włączenie lub wyłączenie ciszy radiowej; pojedyncze zgłoszenie wyjęte spod ciszy operacyjnej, gdy polecenie to dopuszcza |
| `POST /api/operator/destroy` | operacja ZNISZCZ DANE; podwójne potwierdzenie; tylko przy bezpośrednim zagrożeniu przejęciem lub na polecenie OSP |
| `GET /health` | stan strony, zapisu i połączenia ze stacją; czas od ostatniego kontaktu z OSP, wiek najstarszej intencji, liczniki odrzutów i restartów stacji |

Token mieszkańca: 32 losowe bajty, przechowywany jako skrót, niepublikowany na listach. Hasła opiekuna i zastępcy są generowane lokalnie i przechowywane jako skróty z solą. Zastępcy mają te same uprawnienia; hasła zastępców leżą w zaklejonych kopertach przy stacji. Stacja poziomu 1 nie ma kont: obsługę ogranicza fizyczny dostęp. Mieszkańcy nie zakładają kont, nie wyrażają zgód i nie akceptują regulaminu. Strona nie wyświetla przed formularzem żadnych okien formalnych. Pod formularzem jest odnośnik „Informacja o danych” (obowiązek informacyjny, uzupełniony plakatem przy stacji; administrator i podstawa według D13) oraz informacja, że świadome wprowadzenie w błąd fałszywym zgłoszeniem może stanowić wykroczenie (art. 66 § 1 pkt 1 Kodeksu wykroczeń). Po wysłaniu strona pokazuje, że zgłoszenie czeka na sprawdzenie przez opiekuna. Żądanie POST wymaga treści JSON, tokenu CSRF sesji i dozwolonego nagłówka Origin. Obowiązują limity rozmiaru i częstości żądań. Strona nie wczytuje zasobów z internetu i nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności w sieci lokalnej, dlatego strona zbiera minimum danych osobowych. Radio szyfruje osobno.

Router zapewnia DHCP. Laptop jest klientem sieci LAN i wyświetla adres `http://IP:8080` oraz kod QR, aktualizowany po zmianie adresu IP. Główna sieć Wi-Fi musi przepuszczać ruch do LAN. Laptop ani stacja nie uruchamiają własnego serwera DHCP, DNS ani portalu przechwytującego (captive portal). Reguła zapory sieciowej pakietu START musi dopuszczać wyłącznie lokalny port strony na wybranym interfejsie; jej dodanie może wymagać uprawnień administratora.

## Protokół USB laptop–stacja

Interfejs danych CDC (w ESP32-S3 przez kontroler USB-OTG i TinyUSB, nie przez USB-Serial-JTAG) przenosi wiersze UTF-8 JSON do 1024 B, każdy z numerem `seq`. Kontrakt jest wersjonowany (`"usb":1`) i zamyka go decyzja D17.

| Kierunek | Wiadomość | Znaczenie |
|---|---|---|
| laptop → stacja | `submit` z `id`, `revision` i tablicą SA1 | intencja wysyłki; stacja odpowiada `stored` dopiero po COMMIT w FRAM albo `rejected` z przyczyną |
| laptop → stacja | `test`, `announce`, `silence`, `configure`, `export`, `destroy` | polecenia jak w API strony; `configure` tylko w trybie przygotowania |
| stacja → laptop | `event` | RECEIVED, STATUS, REPLY i BULLETIN od przypiętej OSP oraz zmiany stanu radia; laptop potwierdza `ack` po COMMIT w SQLite |
| stacja → laptop (OSP) | `incoming` | zweryfikowane SA1 z adresem nadawcy i wynikiem sprawdzenia podpisu; aplikacja OSP zapisuje je w transakcji i dopiero potem przekazuje RECEIVED przez `submit` |
| obie strony | `sync` z ostatnim potwierdzonym `seq` | odtworzenie stanu po ponownym połączeniu |

`submit` jest idempotentny: ten sam `id` i `revision` z tą samą treścią daje to samo `stored`, a z inną treścią `rejected` z powodu konfliktu. Stacja przechowuje niepotwierdzone `event` w FRAM, aż laptop odpowie `ack`. W OSP stacja zapisuje każde zweryfikowane `incoming` w FRAM przed przekazaniem i trzyma je tam do `ack` od aplikacji OSP, także gdy laptop OSP jest odłączony; limit 128 wiadomości, jak skrzynki odbiorczej. Po zapełnieniu stacja OSP nie przyjmuje do zapisu nowych REQUEST i TEST i liczy odrzuty w diagnostyce. Nie wysyła dla nich RECEIVED, bo RECEIVED zawsze wymaga COMMIT w SQLite aplikacji OSP, więc źródło ponawia wysyłkę według swojego harmonogramu. Ekran stacji OSP pokazuje liczbę oczekujących `incoming`. Laptop przechowuje intencję przekazania w SQLite, aż dostanie `stored`. Odłączenie przewodu w dowolnym momencie nie gubi ani nie podwaja zgłoszenia.

## Ekran i przyciski stacji

Ekran graficzny pokazuje stale: stan radia (RADIO GOTOWE, CZEKA NA POŁĄCZENIE, CISZA), osobny znacznik „KONTAKT Z ODBIORCĄ” tylko wtedy, gdy w ostatnich 60 min nadeszło RECEIVED lub STATUS od OSP, źródło i napięcie zasilania, czas od ostatniej odpowiedzi OSP, czas oczekiwania najstarszego niewysłanego zgłoszenia i liczbę nowych wiadomości. Czasy liczy się od lokalnego licznika stacji, nie od zegara kalendarzowego; zegar kalendarzowy przekazany przez laptop nie jest zaufany. Naciśnięcie dowolnego przycisku włącza podświetlenie ekranu na 30 s ([elektronika](elektronika.md)). Nowa wiadomość od OSP daje sygnał dźwiękowy, który można wyciszyć w menu STAN. Do oceny: STAN pokazuje odchyłkę częstotliwości oszacowaną z odebranych ramek.

Przyciski: GÓRA, DÓŁ, OK, WSTECZ, duże i wyczuwalne, obsługiwane w rękawicach. Osobny przełącznik CISZA ma osłonę przed przypadkowym przełączeniem. Przycisk konfiguracji jest wewnątrz obudowy.

| Menu | Działanie |
|---|---|
| ZGŁOSZENIE | kategoria 0–9 z piktogramem → liczba osób → pilność → gotowa fraza lub brak → potwierdzenie; ekran pokazuje stan i krótki numer |
| WIADOMOŚCI | statusy własnych zgłoszeń, odpowiedzi (REPLY) i komunikaty (BULLETIN) ze źródłem i czasem od odbioru |
| TEST | wysłanie TEST i wynik |
| STAN | radio, liczniki, energia, wersja, nazwa `WICI-xxxx` |
| JĘZYK / МОВА / LANGUAGE | polski, ukraiński, angielski; etykieta zawsze w trzech językach |
| ZNISZCZ DANE | przytrzymanie OK i WSTECZ przez 5 s, potem potwierdzenie; wyłącznie przy bezpośrednim zagrożeniu przejęciem lub na polecenie OSP |

Zmiana zgłoszenia przyciskami tworzy nową rewizję, jak na stronie. Swobodny opis wpisuje się tylko w panelu laptopa.

## Tryby kryzysowe

Formalności i uzgodnienia załatwia się przed użyciem. Żadna z poniższych funkcji nie blokuje przyjęcia zgłoszenia.

**Ogłoszenia adresu.** Stacja ogłasza swój adres LXMF przy starcie i na polecenie opiekuna (menu lub panel), nigdy cyklicznie. Nazwa wyświetlana ma postać `WICI-xxxx` (4 cyfry szesnastkowe skrótu tożsamości) i nie zawiera adresu ani nazwy miejsca. Emisje transportu Reticulum, np. zapytania o trasę, pozostają i liczy się je w próbie T3.

**Cisza radiowa.** Polecenie ciszy radiowej wydaje wójt (od wprowadzenia stanu wojennego i w czasie wojny jako organ obrony cywilnej) na podstawie decyzji wojewody lub organów wojskowych albo wynika ono z nakazu wydanego w stanie nadzwyczajnym. Do schronień przekazuje je OSP komunikatem BULLETIN i gońcem; ciszę odwołuje ten sam organ. Opiekun włącza ją przełącznikiem CISZA na stacji albo w panelu. Przełącznik na stacji ma pierwszeństwo przed panelem. Sterownik P1 nic nie nadaje, łącznie z ruchem przekazywanym. Odbiór, zapis i kolejka działają dalej. Wyłączenie ciszy jest wyłącznie ręczne, po odwołaniu przez organ. Wyjątek dla pojedynczego zgłoszenia dotyczy wyłącznie ciszy operacyjnej, gdy polecenie wprost go dopuszcza; nie dotyczy zakazu używania urządzeń nadawczych w stanie wojennym lub wyjątkowym – wtedy podstawową procedurą jest goniec. Stacja zapisuje wyjątek w dzienniku zdarzeń, a opiekun w dzienniku papierowym. Fizyczną pewność ciszy daje wyłączenie zasilania stacji; wtedy stacja także nie odbiera.

**Szyfrowanie w spoczynku.** Na laptopie baza i eksporty są szyfrowane kluczem zapisanym na pamięci USB zestawu. Stacja przechowuje klucz tożsamości, kartę OSP, adres i kolejkę; na poziomie 1 nie ma tam danych osobowych. Oprogramowanie układowe włącza ochronę odczytu pamięci mikrokontrolera (np. APPROTECT w nRF52840, szyfrowanie pamięci flash w ESP32-S3). Wykonanie z nRF52840 wymaga rewizji 3 (kod wykonania Fx0) z APPROTECT według Nordic IN-141 i MDK ≥8.40.2; starsze rewizje mają znane obejście ochrony (IN-133). Rekordy w FRAM są szyfrowane kluczem przechowywanym w chronionej pamięci MCU, więc wylutowanie FRAM nie ujawnia kolejki ani karty OSP. Start nie wymaga hasła. W systemach Windows i macOS baza leży na dysku laptopa, więc po odłączeniu pamięci USB jest nieczytelna. W Linuksie baza i klucz są na tej samej pamięci. W każdym systemie zabranie laptopa razem z pamięcią USB daje dostęp do danych. Szyfrowanie chroni więc tylko przed utratą samego laptopa; przed przejęciem całego stanowiska chroni wyłącznie ZNISZCZ DANE albo zniszczenie pamięci. Kandydatem jest SQLCipher Community Edition (licencja BSD-3-Clause, wymaga dołączenia informacji o prawach autorskich) z biblioteką Pythona [sqlcipher3](https://pypi.org/project/sqlcipher3/) (licencja zlib), która ma gotowe pakiety dla macOS (Intel i ARM), Windows x64 i Linuksa x86_64. To pierwsza zależność bazy spoza biblioteki standardowej. Wymaga przypięcia wersji, sprawdzenia, czy nie osłabia gwarancji trwałości z tej specyfikacji (tryb dziennika, fsync), oraz powtórzenia prób odcięcia zasilania. Ostateczny wybór, także wobec zaszyfrowanego wolumenu, zapada w D13. [SQLCipher](https://www.zetetic.net/sqlcipher/license/).

**ZNISZCZ DANE.** Operację wykonuje się wyłącznie przy bezpośrednim zagrożeniu przejęciem lub na polecenie OSP; fakt zapisuje się w dzienniku papierowym. Po podwójnym potwierdzeniu laptop zatrzymuje przekazywanie, usuwa klucz, a następnie bazę i eksporty. Na stacji ta sama operacja z menu albo z panelu najpierw usuwa z pamięci MCU klucz szyfrowania FRAM (kryptograficzne wymazanie), potem nadpisuje klucz tożsamości oraz w FRAM kartę OSP, adres, kolejkę i skrzynkę; FRAM nadpisuje się bajt po bajcie bez ryzyka pozostawienia kopii. Nadpisanie pamięci flash i SSD nie gwarantuje usunięcia, dlatego decyduje usunięcie klucza. Instrukcja nakazuje dodatkowo fizyczne zniszczenie pamięci USB. Operacja jest nieodwracalna i trwa najwyżej 1 minutę.

**Języki i dostępność.** Ekran stacji i strona mieszkańca są dostępne po polsku, ukraińsku i angielsku. Wybór języka nie wymaga przeładowania ani połączenia z internetem. Kategorie mają piktogramy i są przesyłane jako liczby, więc dyżurny widzi kategorię, liczbę osób i lokalizację niezależnie od języka opisu. Litery ukraińskie zajmują w UTF-8 po 2 B, tak jak polskie znaki diakrytyczne, więc opis zgłoszenia mieści około 48 takich znaków. Formularz pokazuje pozostały limit w bajtach. Strona używa semantycznego HTML, działa z czytnikiem ekranu i przy powiększeniu tekstu do 200%.

## Pakiet USB

```text
USB/
  INSTRUKCJA.html
  START-WINDOWS.exe
  START-MAC-INTEL.app/
  START-MAC-ARM.app/
  linux-x86_64/                 # obraz startowy, system plików tylko do odczytu
  runtime/<platform>/          # interpreter i wszystkie biblioteki
  app/                         # strona, panel, program startowy, protokół USB do stacji
  firmware/                    # obrazy oprogramowania stacji obu wykonań; tylko do przygotowania
  drivers/<platform>/
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, skróty, polecenie budowy, lista plików
  keys/                        # klucz szyfrowania bazy tego laptopa; nie trafia do kopii publicznych
  export/                      # kopia przeniesionej stacji
```

W Linuksie stan znajduje się na osobnej partycji ext4 pamięci USB, a w systemach Windows i macOS na dysku laptopa, w katalogu aplikacji. Aktywna baza nie może leżeć na exFAT. Aplikacja nie zapewnia automatycznej wspólnej bazy między systemami.

PRZENIEŚ STACJĘ zatrzymuje nowe zgłoszenia i wysyłkę, eksportuje ze stacji przez laptop tożsamość, konfigurację i kolejkę, a stara stacja przestaje nadawać. Stacja zapasowa importuje paczkę. Bazę laptopa kopiuje się osobno przez API kopii zapasowych SQLite i sprawdza jej integralność. Obu stacji z tą samą tożsamością nie wolno używać jednocześnie. W razie utraty stacji przed eksportem uzgadnia się z OSP nową tożsamość. [API kopii](https://www.sqlite.org/backup.html).

Pakiet START utrzymuje komputer w stanie pracy podczas działania strony. Uśpienie laptopa wyłącza tylko stronę i panel; stacja pracuje dalej. Po wznowieniu aplikacja wykonuje `sync` ze stacją.

Przed dystrybucją pakiety muszą zostać zbudowane i przetestowane na każdej architekturze. W schronieniu nie instaluje się pakietów przez pip. Po próbie zgodności wydanie przypina dokładne archiwa lub commity wraz z ich skrótami. Podczas uruchamiania nie pobiera się wersji `latest`.

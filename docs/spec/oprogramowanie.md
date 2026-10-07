# WICI: oprogramowanie

## Podział oprogramowania

**Oprogramowanie układowe stacji** zawiera port microReticulum z włączonym transportem, moduł LXMF (LXMRouter) z jedną tożsamością stacji, sterownik P1, trwałą kolejkę i skrzynkę odbiorczą w pamięci FRAM, interfejs ekranu i przycisków, protokół USB do laptopa oraz układ nadzorujący (watchdog). Stacja jest jedynym węzłem sieci w schronieniu i działa bez laptopa. Wersje referencyjne protokołu: Reticulum `e40191b` i LXMF `c3ff2d6`. Implementację LXMF dla mikrokontrolera (z istniejących projektów albo własną, zgodną z wersją referencyjną) wybiera się w D14 po T3. [microReticulum](https://github.com/attermann/microReticulum), [LXMF](https://github.com/markqvist/LXMF).

LXMF pakuje wiadomości, szyfruje je przez Reticulum, wyszukuje trasę, potwierdza dostarczenie na poziomie transportu i ponawia wysyłkę. Tych mechanizmów nie implementuje się drugi raz. Stan DELIVERED w LXMF nie oznacza zatwierdzonej transakcji w bazie OSP. Kolejka intencji jest w FRAM i stacja odtwarza ją po restarcie. Lista oczekujących wiadomości w pamięci LXMF nie jest trwałą kolejką.

Konfiguracja LXMF: wyłącznie dostarczenie okazjonalne (OPPORTUNISTIC), bez przejścia na DIRECT, Resource ani propagację; treść, która się nie mieści, jest błędem już przy tworzeniu intencji. Bez znaczków pracy (brak `stamp_cost`). Ratchety rozstrzyga D01; jeśli zostaną włączone, ich klucze są w FRAM.

**Aplikacja laptopa** (`station-web`, poziomy 2–3) zawiera serwer lokalnej strony, jedną bazę SQLite i panel opiekuna lub dyżurnego. Nie uruchamia Reticulum ani LXMF i nie ma tożsamości sieciowej; wiadomości przekazuje stacji [protokołem USB](#protokół-usb-laptopstacja). Odłączenie laptopa nie przerywa pracy stacji. Restart strony nie zmienia kolejki stacji. Stanowisko OSP to stacja z laptopem; transakcja przyjęcia zgłoszenia i RECEIVED odbywa się w SQLite aplikacji OSP ([stanowisko dyżurnego](#stanowisko-dyżurnego-osp)).

NomadNet i narzędzia Reticulum w Pythonie nie są częścią wydania. Mogą służyć w laboratorium do prób zgodności (T3) jako osobne węzły z własną tożsamością. Nie wolno wymagać od mieszkańców instalacji klienta. [NomadNet](https://github.com/markqvist/NomadNet).

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik, bez załączników. Cała treść po kodowaniu ma najwyżej 256 B (decyzja robocza, do potwierdzenia w D01 i T3; zastępuje przejściowe 480 B), więc każda wiadomość SA1 mieści się w jednym pakiecie okazjonalnym LXMF, około 284 B dla wersji referencyjnych ([koncepcja, rozdział 05](../conception/05-projekt-koncepcyjny-komunikacji.html#rozmiar-wiadomosci-a-sposob-dostarczenia)). Przypadki najgorsze przy limitach pól poniżej: REQUEST i TEST 222 B, BULLETIN 246 B, REPLY 156 B, STATUS 59 B, RECEIVED 50 B; zgłoszenie z przycisków 220 B. JSON zawiera jedną tablicę; swobodne obiekty są odrzucane. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`. Teksty SA1 nie mogą zawierać znaków U+0022 (`"`) i U+005C (`\`); formularz, panel i ekran zamieniają je na „ ” i `/`, więc tekst nigdy nie wymaga sekwencji ucieczki. Teksty nie mogą też zawierać znaków z kategorii Unicode Cc, Cf, Cs, Co, Cn, Zl i Zp (m.in. znaków C1, znaków zmiany kierunku pisma, niewidocznych znaków formatujących, surogatów, znaków prywatnych i nieprzypisanych, separatorów wiersza i akapitu). Wymagana jest normalizacja NFC; tekst w innej postaci jest odrzucany. Zwykłe polskie i ukraińskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |
| TEST = 5 | `[1,5,id,revision,category,people,location,text,urgency]` |

`id`: 32 małe cyfry szesnastkowe, czyli 16 losowych bajtów z CSPRNG. Tworzy go ten, kto tworzy zgłoszenie SA1: stacja dla zgłoszeń z przycisków i TEST z menu ([model zaufania](#model-zaufania-i-kluczy)), aplikacja laptopa (CSPRNG systemu operacyjnego) dla zgłoszeń z panelu i zgłoszeń mieszkańców zatwierdzonych przez opiekuna, aplikacja OSP dla BULLETIN; RECEIVED, STATUS i REPLY powtarzają `id` zgłoszenia. Zgłoszenie mieszkańca przed zatwierdzeniem nie ma `id` SA1, tylko lokalny identyfikator strony ([strona mieszkańca](#strona-mieszkańca)). `revision`: 0–65 535. `category`: 0–9 = 0 pomoc medyczna (zagrożenie życia lub zdrowia); 1 leki stałe i sprzęt medyczny (tlen, insulina, dializy); 2 ewakuacja i transport, w tym osób leżących i z niepełnosprawnością; 3 woda pitna; 4 żywność, w tym dla niemowląt; 5 ogrzewanie, energia, paliwo; 6 sanitarne i higiena; 7 bezpieczeństwo obiektu (pożar, CO, zalanie, uszkodzenie); 8 informacja i poszukiwanie osób; 9 inne (wymaga frazy lub opisu). `people`: 1–65 535. `location`: 1–64 B, dokładny adres i miejsce wejścia w krótkiej postaci (ulica, numer, wejście; miejscowość tylko wtedy, gdy ta sama ulica występuje w gminie więcej niż raz); `configure` odrzuca dłuższy adres. Miejsce w budynku („gdzie w budynku”) nie należy do `location`: panel i strona dopisują je na początku `text` i liczą do jego limitu. `text` zgłoszenia i odpowiedzi: do 96 B; komunikatu: do 192 B. `urgency`: 2 = bezpośrednie zagrożenie życia lub zdrowia („ZAGROŻENIE ŻYCIA”); 1 = pilne, w ciągu kilku godzin („PILNE – KILKA GODZIN”); 0 = w ciągu doby („W CIĄGU DOBY”); podwyższenie zatwierdza opiekun. Przy pilności 2 opiekun równolegle udziela pierwszej pomocy i – gdy droga jest bezpieczna – wysyła gońca do najbliższej jednostki PSP/OSP lub zespołu ratownictwa medycznego. WICI nie zastępuje numeru 112. `event`: 1–2 147 483 647, bez zawijania licznika; nowy komunikat po wyczerpaniu licznika dostaje nowe id. `state` (teksty ekranu w tabeli [Teksty ekranu](#teksty-ekranu)): 1 = „odbiorca zapisał”, 2 = „odbiorca przeczytał”, 3 = „pomoc skierowana” (decyzja, nie godzina przyjazdu), 4 = „przekazane dalej” (PSP, pogotowie, powiat), 5 = „odbiorca nie może teraz pomóc” – zawsze razem z REPLY z instrukcją (np. użyj kanału zastępczego), 6 = „zamknięte” (potrzeba ustała).

RECEIVED zawsze oznacza pierwsze przyjęcie, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2–6; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli OSP ma już nowszy status, wysyła też najnowszy STATUS. Źródło ignoruje starsze wartości event dla tej samej pary id i revision. Stacja ignoruje STATUS dla id, którego nie ma w jej kolejce ani dzienniku. Nowszy STATUS może zmienić stan na dowolny z 2–6; po stanie 6 (zamknięte) zgłoszenie zmienia się tylko nową rewizją. REPLY ma numerację event niezależną od STATUS. BULLETIN jest numerowany w obrębie swojego id. Żaden BULLETIN nie wywołuje działania automatycznego stacji; każdy komunikat na ekranie ma stopkę `stopka_komunikatu`.

TEST ma tablicę, limity i walidację REQUEST. Sprawdza całą drogę zgłoszenia: transport, zapis w OSP i obecność dyżurnego. Stacja proponuje go na ekranie po uruchomieniu, restarcie oraz zmianie anteny lub odbiorcy i wysyła na polecenie opiekuna z menu lub panelu; nigdy cyklicznie. Stacja z zegarem RTC nie proponuje TEST po wymianie ogniw, jeśli ostatni kontakt z odbiorcą był według RTC mniej niż 6 h wcześniej; stacja bez RTC nie zna czasu wyłączenia i proponuje TEST po każdym włączeniu ([czas](#trwałość-i-potwierdzenia)). TEST startowy (proponowany po uruchomieniu i restarcie) wychodzi z losowym opóźnieniem w oknie 50 s × liczba stacji w sieci od polecenia, aby wiele stacji włączonych naraz nie zajęło kanału; liczbę stacji zapisuje `configure` (bez niej okno wynosi 15 min, co wystarcza tylko dla sieci do 18 stacji). Ekran pokazuje `test_zaplanowany`, a WSTECZ anuluje. Kolejność uruchamiania stacji ustala w planie organizator sieci (zwykle samorząd gminy). OSP może poprosić o wstrzymanie TEST komunikatem BULLETIN. Stacja nie rozpoznaje go automatycznie: opiekun po przeczytaniu komunikatu wybiera TEST → WSTRZYMAJ, co anuluje TEST oczekujący na nadanie i do odwołania pokazuje `test_wstrzymany`; TEST → WZNÓW odwołuje wstrzymanie. TEST ma najniższy priorytet w kolejce stacji.

Pola TEST startowego i TEST z menu: `category` = 9, `people` = 1, `urgency` = 0, `location` = adres stacji, `text` = „test”. Alarm TEST nie zależy od pilności: `brak_potwierdzenia` po 30 min od `test_wyslany` bez RECEIVED. Zgłoszenia wysyłane podczas prób i ćwiczeń również mają typ TEST. TEST startowy zawiera rzeczywisty adres i wejście schronienia, aby dyżurny mógł potwierdzić, że są zrozumiałe. OSP przyjmuje TEST jak REQUEST: weryfikacja nadawcy, kwarantanna nieznanej stacji, deduplikacja, jedna transakcja i RECEIVED po COMMIT. Klucz odbioru nie zależy od typu; REQUEST i TEST o tym samym id i revision to konflikt treści. Stanowisko OSP pokazuje TEST osobno od kolejki potrzeb i nie wlicza go do potrzeb. Dyżurny odpowiada wiadomością STATUS ze state=2. Wartości state 3–6 dla TEST są dopuszczalne tylko w uzgodnionym ćwiczeniu i oznaczają decyzję ćwiczebną bez wysłania pomocy. Stacja pokazuje TEST na ekranie i w panelu opiekuna, nie jako zgłoszenie mieszkańca.

**Pojemność.** Pojemność ogranicza najbardziej obciążony węzeł, zwykle stacja OSP i przekaźnik obok niej, i dotyczy całej sieci, a nie pojedynczego przekaźnika. Model bez strat ([rozdział 06](../conception/06-wykonalnosc-i-budzet-zasobow.html)): OSP przyjmuje około 121 zgłoszeń na godzinę z RECEIVED i dwoma STATUS; przekaźnik przed OSP około 68 na godzinę. Dodanie przekaźników nie zwiększa tego limitu; zwiększa go tylko drugi odbiorca albo podział sieci. BULLETIN wysyła się osobno do każdej stacji: dla 50 stacji to około 12 min pracy nadajnika OSP (nadawanie z obowiązkową ciszą), i tyle samo trwa rozesłanie polecenia ciszy. Pojemność rzeczywistą wyznacza T5.

Zmiana danych zgłoszenia tworzy nową rewizję (revision). Każda rewizja zawiera pełną lokalizację i treść, więc odbiorca nie potrzebuje wcześniej przekazanych danych o budynku. Stanowisko pokazuje rewizje jako jedno zgłoszenie, ale każdą potwierdza się osobno. Przez radio nie wysyła się imion, numerów PESEL, danych dokumentów ani tokenów strony. Dyżurny nie wpisuje nazwisk ani informacji o zdrowiu do REPLY i BULLETIN. Typ stanu obiektu (MELDUNEK) nie jest częścią SA1 0.5 – rozstrzyga D18.

Zgłoszenie z przycisków (poziom 1) tworzy stacja: `category` i `urgency` z menu (pilność bez wartości domyślnej), `people` 1–999 z listy gotowych wartości lub wpisu cyfra po cyfrze, `location` z adresu zapisanego podczas przygotowania, `text` pusty albo jedna z gotowych fraz z konfiguracji (każda ≤96 B UTF-8, zapisana po polsku; ekran pokazuje jej tłumaczenie z konfiguracji w wybranym języku, a dyżurny otrzymuje wersję polską). Kategoria 9 wymaga frazy. `urgency` = 2 wymaga dodatkowego potwierdzenia. `configure` odrzuca adres i frazę, jeśli najgorsze zgłoszenie z przycisków przekroczyłoby limit 256 B. Domyślna lista fraz: osoba na wózku; osoba leżąca – potrzebne nosze; dializy – termin dziś; insulina na 1 dzień; niemowlę – mleko modyfikowane; osoba niewidoma lub niesłysząca; tlen na wyczerpaniu; dziecko bez opieki; czujnik CO alarmuje; woda w budynku; potrzeba ustała. Ekran i panel pokazują krótki numer zgłoszenia: pierwsze 16 bitów `id` modulo 10 000, jako cztery cyfry. Cztery cyfry powtarzają się już przy kilkudziesięciu zgłoszeniach (około 4% przy 30), dlatego numer jest unikalny w obrębie stacji: stacja losuje `id` ponownie, dopóki krótki numer nie różni się od numerów zgłoszeń w jej kolejce i dzienniku zdarzenia, a nowe `id` z laptopa o zajętym numerze odrzuca (`rejected`, przyczyna `numer_zajety`) i laptop losuje nowe. Numer ten razem z nazwą stacji `WICI-xxxxxx` jednoznacznie wskazuje zgłoszenie przy przekazaniu telefonicznym lub przez gońca.

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zgłoszenie z przycisków | zgłoszenie + intencja wysyłki w FRAM stacji |
| Zgłoszenie ze strony | w SQLite laptopa: zgłoszenie mieszkańca + skrót tokenu dostępu, w kolejce opiekuna |
| Zatwierdzenie przez opiekuna | w SQLite laptopa: zgłoszenie SA1 z nowym `id` + powiązanie ze zgłoszeniami mieszkańców + intencja przekazania; w stacji: zgłoszenie + intencja wysyłki, idempotentnie po kluczu wiadomości |
| Przyjęcie w OSP | zweryfikowane zgłoszenie + tożsamość nadawcy + klucz odbioru + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS (przy stanie 5 także intencja REPLY) |

FRAM stacji: dziennik rekordów szyfrowanych AEAD (AES-128-CCM w nRF52840 z CC310; AES-128-GCM lub ChaCha20-Poly1305 w ESP32-S3) ze znacznikiem uwierzytelnienia 16 B. Nonce = epoka klucza (32 b) ‖ 64-bitowy numer rekordu dziennika; numer nigdy się nie powtarza i po starcie jest odtwarzany jako maksimum + 1. Dane uwierzytelnione to nagłówek rekordu (numer, typ, długość, wersja). Rekord z błędnym znacznikiem traktuje się jak uszkodzony. Transakcja wielorekordowa ma jeden znacznik zatwierdzenia na ostatnim rekordzie; zapis jest zatwierdzony (COMMIT stacji) po zapisaniu tego znacznika, a rekordy bez niego są po restarcie odrzucane. Kompaktowanie dziennika jest odporne na zanik zasilania. Klucz FRAM (KEK) leży w dedykowanej stronie pamięci flash MCU poza systemem plików, kasowanej z weryfikacją. Podmiana całej zawartości FRAM starszym obrazem (rollback) pozostaje ryzykiem szczątkowym ([rozdział 07](../conception/07-zagrozenia-i-odpornosc.html)). Przed wyłączeniem przy niskim napięciu ogniw stacja kończy bieżący zapis i pokazuje `wylaczanie`, a potem `mozna_wyjac`. SQLite laptopa: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone. Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią oznacza konflikt; dane nie są nadpisywane.

Przed zapisem funkcja zwrotna odbioru sprawdza `signature_validated`, zaufanie do nadawcy i limit rozmiaru. Stacja przyjmuje RECEIVED, STATUS, REPLY i BULLETIN wyłącznie od aktywnej tożsamości przypiętej OSP ([klucz OSP](#model-zaufania-i-kluczy)); inne odrzuca i liczy w diagnostyce. Nazwa wyświetlana i pole JSON nie nadają uprawnień. W OSP REQUEST i TEST nieznanej stacji trafiają do kwarantanny i czekają na decyzję dyżurnego ([model zaufania](#model-zaufania-i-kluczy)). Kwarantanna jest zapisem trwałym, ale nie przyjęciem: RECEIVED wysyła się dopiero po zatwierdzeniu wiadomości przez dyżurnego. Zgłoszenie z kwarantanny nie jest traktowane jak zgłoszenie ze zweryfikowanego schronienia. Kartę OSP zapisuje się w stacji tylko w trybie przygotowania, po przytrzymaniu przycisku konfiguracji na stacji; nigdy przez radio.

Proces kolejki wysyła RECEIVED i każde inne potwierdzenie aplikacyjne dopiero po COMMIT. Brak miejsca, uszkodzenie bazy lub dziennika FRAM albo błąd fsync blokują komunikat `zapisane_w_stacji`; stacja pokazuje wtedy `blad_pamieci`. Stacja i aplikacja nie tworzą automatycznie pustego magazynu w miejsce uszkodzonego. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. [Trwałość SQLite](https://sqlite.org/atomiccommit.html).

**Wysyłanie.** Intencja jest aktywna od przekazania do LXMF do stanu DELIVERED albo FAILED. LXMF ponawia aktywną próbę (odstępy ponowień LXMF: [radio](radio.md)). Po DELIVERED stacja czeka na RECEIVED 10 min, potem ponawia intencję co 30–60 min z losowym przesunięciem ±20%. Po FAILED ponawia po 1, 2, 5 i 15 min, każdy odstęp ±20%; po 6 h co 60 min. Nigdy nie ponawia równolegle z wciąż aktywną wysyłką tej samej intencji. Intencja w oczekiwaniu nie blokuje następnych; stacja przekazuje do LXMF najwyżej 2 własne wiadomości jednocześnie. STATUS lub REPLY od aktywnej tożsamości OSP także kończy ponawianie danej pary (id, revision). Nienadana starsza rewizja jest oznaczana jako zastąpiona. Nieodesłany STATUS dla tego samego (odbiorca, id, revision) zastępuje się nowszym. Intencja nie jest usuwana automatycznie; po czasie zależnym od pilności ekran podaje alarm braku potwierdzenia ([ekran](#ekran-i-przyciski-stacji)). Nowa wiadomość LXMF może mieć inny skrót (hash); id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji OSP. Kolejność w kolejce stacji: RECEIVED i STATUS, potem REPLY i BULLETIN, potem REQUEST z `urgency` = 2, potem pozostałe REQUEST według czasu COMMIT, na końcu TEST. Nie oznacza to priorytetu w całej sieci. Kolejka P1 ma własne priorytety: potwierdzenia pakietów i zapytania o trasę, potem dane, na końcu ogłoszenia.

**Czas.** Stacja utrzymuje w FRAM licznik czasu pracy (zapis co 60 s) i używa go jako monotonicznego zegara Reticulum i LXMF między restartami. Wszystkie czasy na ekranie liczy się od tego licznika, nie od zegara kalendarzowego; zegar kalendarzowy przekazany przez laptop nie jest zaufany. Licznik nie rośnie, gdy stacja jest wyłączona. Bez RTC stacja po włączeniu nie wie, jak długo była wyłączona: do pierwszej nowej wiadomości od OSP pokazuje `ostatni_kontakt_ponad`, czyli dolne oszacowanie (czas pracy przed wyłączeniem i po włączeniu), zamiast `ostatni_kontakt`. Alarmy liczą czas pracy, więc wyłączenie stacji je wstrzymuje. Licznik należy do tożsamości stacji i przechodzi z nią w PRZENIEŚ STACJĘ; stacja docelowa przyjmuje większą z dwóch wartości, aby jej ogłoszenia nie wyglądały na starsze od wcześniejszych (do potwierdzenia w T3). OSP ignoruje znacznik czasu LXMF i używa czasu lokalnego odbioru.

Limity: kolejka wychodząca stacji do 128 intencji, skrzynka odbiorcza do 128 wiadomości (najpierw usuwa się najstarsze przeczytane BULLETIN), dziennik zdarzeń stacji jako bufor pierścieniowy 32 KiB. Pełna kolejka blokuje nowe zgłoszenie komunikatem `kolejka_pelna`; nigdy nie daje pozornego `zapisane_w_stacji`. Aplikacja laptopa odmawia zapisu, gdy wolne miejsce spada poniżej 100 MB, a jej dziennik ma rotację do 10 MB. Wybór odbiorcy zastępczego nie jest częścią wydania; obowiązuje procedura zastępcza z [koncepcji](../conception/02-scenariusze-i-organizacja.html#siec-i-odbiorca-zastepczy).

**Pojemności stosu.** Tablica tras i tożsamości mieści co najmniej 256 wpisów z buforowanym ogłoszeniem, a lista skrótów pakietów co najmniej 4096 wpisów. Wpisu OSP i zaufanych stacji nigdy się nie usuwa; poza nimi usuwa się wpis najdawniej używany. Przy pełnych 32-bajtowych skrótach, jak w implementacji referencyjnej, sama lista skrótów zajęłaby 128 KiB, a tablica tras z ogłoszeniami około 78 KiB, czyli razem około 81% RAM nRF52840. Dlatego:

- lista skrótów pakietów w RAM przechowuje pierwsze 8 B skrótu (4096 × 8 B = 32 KiB); prawdopodobieństwo fałszywego duplikatu przy 4096 wpisach jest rzędu 10⁻¹², a lista jest lokalna i nie zmienia protokołu;
- pełne wpisy tablicy tras, tożsamości i buforowane ogłoszenia leżą w FRAM; RAM zawiera indeks skrótów celu (256 × 16 B) i pamięć podręczną ostatnio używanych wpisów.

Zapas RAM ≥30% mierzy się przy tych pojemnościach i tym podziale. Jeśli microReticulum nie pozwala na taki podział bez głębokich zmian, wykonanie A przechodzi na MCU z większą pamięcią (D14).

**Pamięć FRAM według roli.** Rozmiar rekordu treści: ≤256 B SA1 + nagłówek + znacznik 16 B.

| Zawartość | Rola stacji | Rola OSP |
|---|---|---|
| kolejka wychodząca | 128 intencji | ≥512 intencji; BULLETIN zapisany raz z mapą odbiorców |
| skrzynka odbiorcza | 128 wiadomości | – |
| `incoming` | – | 128 miejsc (podział w [modelu zaufania](#model-zaufania-i-kluczy)) |
| tablica tras, tożsamości, ogłoszenia | ≥256 wpisów | ≥256 wpisów |
| najwyższy event na id, klucze odbioru | tak | tak |
| dziennik zdarzeń | 32 KiB | 32 KiB |
| karty zaufanych stacji (klucz 64 B, skrót adresu, nazwa, stan) | – | ≥256 wpisów, ≈38 KiB |
| licznik czasu pracy, dziennik długu ciszy | tak | tak |
| suma | ≈205 KiB | ≈403 KiB |

Każda stacja ma FRAM 4 Mbit (512 KiB). Rola OSP nie mieści się w 256 KiB, a stacja zapasowa i wymiana stacji między rolami wymagają jednego wykonania. W roli stacji 2 Mbit byłyby zajęte w 80%, co zostawia za mało miejsca na kompaktowanie dziennika odporne na zanik zasilania; kompaktowanie wymaga wolnego miejsca co najmniej na największą transakcję i nowy nagłówek dziennika. Rozmiary rekordów są założeniem [modelu](../../software/reference/wyniki.json) (zajętość 40% w roli stacji i 79% w roli OSP).

## API lokalnej strony (poziomy 2–3)

Sieć lokalna (LAN) widzi tylko adresy mieszkańca. Panel opiekuna i dyżurnego nasłuchuje wyłącznie na 127.0.0.1, czyli jest dostępny tylko z ekranu laptopa.

| Adres | Dostęp | Działanie |
|---|---|---|
| `GET /` | LAN | informacje, formularz, komunikaty |
| `POST /api/request` | LAN | walidacja i trwały zapis w kolejce opiekuna; 201 dopiero po COMMIT; nie wysyła radiem |
| `GET /api/request/<lid>` | LAN | treść i status tylko własnego zgłoszenia; `<lid>` to lokalny identyfikator strony (16 losowych bajtów, 32 cyfry szesnastkowe), nie krótki numer; wymaga tokenu w ciasteczku |
| `POST /api/request/<lid>` | LAN | zmiana własnego zgłoszenia; przed zatwierdzeniem zmienia wpis w kolejce opiekuna, po zatwierdzeniu wraca do kolejki opiekuna jako zmiana, z której opiekun tworzy nową rewizję |
| `GET /operator` | 127.0.0.1 | logowanie opiekuna lub dyżurnego |
| `GET /api/operator/queue` | 127.0.0.1 | kolejka lokalna; wymaga uwierzytelnienia |
| `POST /api/operator/approve` | 127.0.0.1 | sprawdzenie zgłoszenia mieszkańca, połączenie z powtarzalnym, ustalenie pilności i przekazanie do wysyłki |
| `POST /api/operator/test` | 127.0.0.1 | wysłanie TEST |
| `POST /api/operator/announce` | 127.0.0.1 | jednorazowe ogłoszenie adresu stacji |
| `POST /api/operator/status` | 127.0.0.1 | decyzja OSP; stan 5 tylko razem z REPLY; tylko rola OSP |
| `POST /api/operator/reply` | 127.0.0.1 | odpowiedź REPLY do zgłoszenia; tylko rola OSP |
| `POST /api/operator/bulletin` | 127.0.0.1 | komunikat BULLETIN, osobno do każdej stacji; tylko rola OSP |
| `POST /api/operator/quarantine` | 127.0.0.1 | zatwierdzenie pojedynczej wiadomości (nadawca, id, revision) bez dodania nadawcy do zaufanych albo jej odrzucenie; tylko rola OSP |
| `POST /api/operator/trust` | 127.0.0.1 | dodanie zaufanej stacji z karty stacji (klucz 64 B, odcisk porównany z ekranem stacji lub z kartą w ewidencji); zgoda dwóch zalogowanych osób i potwierdzenie przyciskiem na stacji OSP w ciągu 30 s; działa także poza trybem przygotowania; tylko rola OSP |
| `POST /api/operator/revoke` | 127.0.0.1 | unieważnienie tożsamości stacji; potwierdzenie przyciskiem na stacji OSP w ciągu 30 s; działa także poza trybem przygotowania; cofnięcie tylko w trybie przygotowania; tylko rola OSP |
| `POST /api/operator/configure` | 127.0.0.1 | adres schronienia (≤64 B), karta OSP (tożsamość główna i zapasowa), gotowe frazy, liczba stacji w sieci (okno TEST startowego) i opcjonalna lista adresów obiektów; tylko w trybie przygotowania |
| `POST /api/operator/export` | 127.0.0.1 | operacja PRZENIEŚ STACJĘ; tylko w trybie przygotowania |
| `POST /api/operator/import` | 127.0.0.1 | przyjęcie paczki z operacji PRZENIEŚ STACJĘ na nowym laptopie lub stacji zapasowej; tylko w trybie przygotowania |
| `POST /api/operator/silence` | 127.0.0.1 | włączenie lub wyłączenie ciszy radiowej; wyjątek dla pojedynczego zgłoszenia tylko przy ciszy operacyjnej ustawionej z panelu; wymaga potwierdzenia przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/destroy` | 127.0.0.1 | operacja [ZNISZCZ DANE](#tryby-kryzysowe); podwójne potwierdzenie i potwierdzenie przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/close` | 127.0.0.1 | operacja [ZAMKNIJ ZDARZENIE](#model-zaufania-i-kluczy) |
| `GET /health` | 127.0.0.1 | stan strony, zapisu i połączenia ze stacją; czas od ostatniego kontaktu z OSP, wiek najstarszej intencji, liczniki odrzutów i restartów stacji |

Token mieszkańca: 32 losowe bajty w ciasteczku `HttpOnly`, `SameSite=Strict`, nigdy w ścieżce URL; baza przechowuje tylko jego skrót. Mieszkańcy nie zakładają kont, nie wyrażają zgód i nie akceptują regulaminu. Strona nie wyświetla przed formularzem żadnych okien formalnych. Pod formularzem jest odnośnik „Informacja o danych” (obowiązek informacyjny, uzupełniony plakatem przy stacji; administrator i podstawa według D13) oraz informacja, że świadome wprowadzenie w błąd fałszywym zgłoszeniem może stanowić wykroczenie (art. 66 § 1 pkt 1 Kodeksu wykroczeń). Żądanie POST wymaga treści JSON, tokenu CSRF sesji i dozwolonego nagłówka Origin. Obowiązują limity rozmiaru i częstości żądań. Strona nie wczytuje zasobów z internetu i nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności w sieci lokalnej, dlatego strona zbiera minimum danych osobowych. Radio szyfruje osobno.

Hasła opiekuna, zastępców i dyżurnych generuje się podczas przygotowania, offline, jako co najmniej 5 słów z listy. Skróty Argon2id lub scrypt zapisuje się w pliku kont na pamięci USB zestawu (dla stanowiska OSP: na stałym laptopie), z limitem 5 prób logowania na minutę; panel nowo uruchomionego laptopa wczytuje konta z tej pamięci i nie każe ustawiać haseł. Zastępcy mają te same uprawnienia co opiekun. Hasła leżą w numerowanych zaklejonych kopertach przy stacji; koperty sprawdza się w przeglądzie kwartalnym, a po otwarciu koperty hasło się zmienia. Dziennik działań operatora jest tylko do dopisywania. Stacja poziomu 1 nie ma kont: obsługę ogranicza fizyczny dostęp.

Router zapewnia DHCP z rezerwacją stałego adresu IP laptopa i szyfrowanie WPA2 lub WPA3 z hasłem z plakatu; izolacja klientów jest włączona, a dzienniki DHCP wyłączone lub czyszczone przy [zamknięciu zdarzenia](#model-zaufania-i-kluczy). Laptop jest klientem sieci LAN i wyświetla adres `http://IP:8080` oraz kod QR. Główna sieć Wi-Fi musi przepuszczać ruch do LAN. Laptop ani stacja nie uruchamiają własnego serwera DHCP, DNS ani portalu przechwytującego (captive portal). Reguła zapory sieciowej pakietu START musi dopuszczać wyłącznie lokalny port strony na wybranym interfejsie; jej dodanie może wymagać uprawnień administratora. Dziennik aplikacji nie zapisuje treści zgłoszeń, tokenów, adresów IP ani MAC.

## Strona mieszkańca

Plakat przy stacji, przygotowany wcześniej, podaje nazwę sieci Wi-Fi, hasło i adres strony; dotyczy routera i adaptera sprawdzonych w przygotowaniu (rezerwację DHCP przypisuje się adresowi MAC adaptera USB–Ethernet z zestawu). Przy innym routerze obowiązuje kod QR na ekranie laptopa. Formularz pokazuje adres obiektu bez możliwości zmiany i pyta tylko „gdzie w budynku”; odpowiedź trafia na początek opisu i liczy się do jego limitu. Licznik pod opisem pokazuje `zostalo_znakow`, przeliczone z limitu bajtów. Panel opiekuna pokazuje przy opisie ostrzeżenie `nie_wpisuj_nazwisk`.

Po wysłaniu strona pokazuje lokalny numer zgłoszenia (cztery cyfry, unikalne w laptopie) i tekst `zapisz_numer`, a następnie stan: `czeka_na_opiekuna`, `opiekun_polaczyl` (gdy opiekun dołączył je do zgłoszenia SA1, także połączonego z innymi) albo `nie_wyslane`, potem etapy zgłoszenia SA1 z tabeli [Teksty ekranu](#teksty-ekranu), te same co na ekranie stacji. Dostęp do zgłoszenia daje tylko ciasteczko z tokenem; numer służy do rozmowy z opiekunem, który sprawdza stan w panelu. Po utracie ciasteczka (inna przeglądarka, tryb prywatny) mieszkańca obsługuje opiekun.

## Protokół USB laptop–stacja

Interfejs danych CDC (w ESP32-S3 przez kontroler USB-OTG i TinyUSB, nie przez USB-Serial-JTAG) przenosi wiersze UTF-8 JSON do 1024 B, każdy z numerem `seq`. Kontrakt jest wersjonowany (`"usb":1`) i zamyka go decyzja D17.

| Kierunek | Wiadomość | Znaczenie |
|---|---|---|
| laptop → stacja | `submit` z `to` (skrót adresu odbiorcy), `id`, `revision` i tablicą SA1 | intencja wysyłki; stacja odpowiada `stored` dopiero po COMMIT w FRAM albo `rejected` z przyczyną; `"resend":true` ponownie uaktywnia zakończoną intencję |
| laptop → stacja | `test`, `announce`, `silence`, `configure`, `export`, `import`, `destroy`, `close` | polecenia jak w API strony; `configure`, `export`, `import` i aktualizacja oprogramowania tylko w trybie przygotowania; `destroy` i `silence` wymagają potwierdzenia przyciskiem na stacji w ciągu 30 s |
| laptop → stacja (OSP) | `trust`, `revoke` | dodanie karty zaufanej stacji i unieważnienie tożsamości w magazynie kart stacji OSP (FRAM); oba wymagają potwierdzenia przyciskiem na stacji w ciągu 30 s, działają także poza trybem przygotowania; cofnięcie unieważnienia tylko w trybie przygotowania |
| stacja → laptop | `event` | RECEIVED, STATUS, REPLY i BULLETIN od aktywnej tożsamości OSP oraz zmiany stanu radia; laptop potwierdza `ack` po COMMIT w SQLite |
| stacja → laptop (OSP) | `incoming` | zweryfikowane SA1 z adresem nadawcy i wynikiem sprawdzenia podpisu; aplikacja OSP zapisuje je w transakcji i dopiero potem przekazuje RECEIVED przez `submit` |
| obie strony | `sync` z `boot` i kursorem (numer rekordu FRAM) | odtworzenie stanu po ponownym połączeniu |

Każda strona podaje `boot`, losowy identyfikator sesji, więc restart drugiej strony jest rozpoznawalny. Idempotencja opiera się na kluczu wiadomości, nie na `seq`: klucz to (to, typ, id, revision, event), a dla BULLETIN (to, id, event). Ten sam klucz z tą samą treścią daje to samo `stored`, z inną treścią `rejected` z powodu konfliktu. Źródłem prawdy jest skrzynka stacji; `sync` przesyła kursor numeru rekordu FRAM. Niepełny wiersz sprzed ponownego połączenia jest odrzucany. Stacja przechowuje niepotwierdzone `event` w FRAM, aż laptop odpowie `ack`. Stacja OSP sama odpowiada zapisanym RECEIVED i najnowszym STATUS na powtórzony REQUEST lub TEST o znanym kluczu odbioru. Stacja zapisuje w dzienniku zdarzeń każde polecenie USB.

W OSP stacja zapisuje każde zweryfikowane `incoming` w FRAM przed przekazaniem i trzyma je tam do `ack` od aplikacji OSP, także gdy laptop OSP jest odłączony. Kolejka `incoming` ma 128 miejsc i deduplikację po (nadawca, id, revision, skrót treści); co najmniej 96 miejsc jest zarezerwowanych dla stacji z kart, a nieznani nadawcy zajmują łącznie najwyżej 16 miejsc i najwyżej 2 na nadawcę. Po zapełnieniu stacja OSP nie przyjmuje do zapisu nowych REQUEST i TEST i liczy odrzuty w diagnostyce. Nie wysyła dla nich RECEIVED, bo RECEIVED zawsze wymaga COMMIT w SQLite aplikacji OSP, więc źródło ponawia wysyłkę według swojego harmonogramu. Ekran stacji OSP pokazuje liczbę oczekujących `incoming` (`incoming_osp`). Laptop przechowuje intencję przekazania w SQLite, aż dostanie `stored`. Odłączenie przewodu w dowolnym momencie nie gubi ani nie podwaja zgłoszenia.

## Model zaufania i kluczy

**Tożsamość i losowość.** Tożsamość stacji generuje sama stacja podczas przygotowania. Źródło losowości: w nRF52840 TRNG układu CC310; w ESP32-S3 `bootloader_random_enable()` (źródło SAR ADC) przy generowaniu kluczy i zasilaniu DRBG, z wyłączonym Wi-Fi i Bluetooth. Klucze i `id` tworzone w stacji pochodzą z CSPRNG z ziarnem ≥256 b; `id` tworzone w laptopie pochodzą z CSPRNG systemu operacyjnego. Próba T2: testy zdrowia źródła entropii (NIST SP 800-90B) i brak powtórzeń `id` w 10⁶ próbek.

**Karty.** W trybie przygotowania stacja eksportuje przez USB kartę stacji: pełny klucz publiczny tożsamości (64 B), skrót adresu LXMF, nazwę `WICI-xxxxxx`, adres schronienia i odcisk do odczytu z ekranu. OSP importuje kartę (plik lub QR) po porównaniu odcisku z ekranem stacji. Karta OSP zawiera dwie tożsamości OSP, główną i zapasową, każdą ze skrótem adresu i pełnym kluczem publicznym (64 B) ([klucz OSP](#model-zaufania-i-kluczy)). Stacja rejestruje klucze z kart przy starcie, więc weryfikacja podpisu nie zależy od odebrania ogłoszenia.

**Zaufanie w OSP.** Karty zaufanych stacji i stan „unieważniona” przechowuje stacja OSP w FRAM; to ona decyduje, czy wiadomość trafia do `incoming` jako zaufana, do kwarantanny, czy jest odrzucana. Aplikacja OSP trzyma kopię kart do wyświetlania i ewidencji, ale nie jest źródłem decyzji. Zatwierdzenie w kwarantannie dotyczy pojedynczej wiadomości i nie dodaje nadawcy do zaufanych. Dodanie zaufanej stacji wymaga karty stacji, zgody dwóch osób i potwierdzenia przyciskiem na stacji OSP (`trust`). Wiadomość z nieznanym kluczem (SOURCE_UNKNOWN) OSP zapisuje jako „do weryfikacji”, wysyła zapytanie o trasę i sprawdza podpis po nadejściu ogłoszenia. Kwarantanna w SQLite mieści najwyżej 4 wiadomości na nadawcę i 256 łącznie; nadmiar jest odrzucany. Tożsamość stacji może mieć stan „unieważniona”: jej wiadomości są odrzucane (nie trafiają do kwarantanny) i liczone, a panel podaje alarm „możliwe przejęcie stacji”.

**Klucz OSP.** Karta OSP zawiera dwie tożsamości: główną i zapasową, każdą z własnym kluczem publicznym i własnym adresem LXMF. Stacja przyjmuje wiadomości i wysyła zgłoszenia wyłącznie do tożsamości aktywnej; po przygotowaniu aktywna jest główna. Przełączenie na zapasową jest czynnością lokalną: opiekun wybiera STAN → USŁUGI → ODBIORCA ZAPASOWY, potwierdza `odbiorca_zapasowy` sekwencją GÓRA, DÓŁ, GÓRA, OK. Panel i USB nie mają tego polecenia. Polecenie przełączenia przychodzi wyłącznie słownie lub przez gońca, nigdy radiem, bo przejęta OSP mogłaby je nadać. Przełączenie jest nieodwracalne poza trybem przygotowania. Po nim stacja odrzuca wiadomości od tożsamości głównej, a niepotwierdzone intencje wysyła ponownie, z tym samym `id` i `revision`, do adresu zapasowego. Tożsamość zapasową generuje się offline podczas przygotowania, a jej klucz prywatny trafia do zaplombowanej koperty u organizatora sieci jako paczka zaszyfrowana kluczem publicznym stacji zapasowej OSP (format jak w PRZENIEŚ STACJĘ); kopertę przechowuje się osobno od tej stacji. Po utracie lub przejęciu stanowiska głównego stacja zapasowa OSP wczytuje paczkę operacją `import` w trybie przygotowania; ponieważ adres się zmienia, ogłasza go od razu po imporcie. Utrata stacji zapasowej OSP wymaga nowej tożsamości zapasowej i nowych kart OSP we wszystkich stacjach (D08). Nowego klucza stacja nigdy nie przyjmuje przez radio. Rotację klucza OSP i nową kopertę zapasową określa plan kart (D08). Pakiety okazjonalne nie mają poufności przyszłej: przejęcie klucza OSP ujawnia wcześniej nagrane zgłoszenia ([rozdział 07](../conception/07-zagrozenia-i-odpornosc.html)).

**Powtórzenia.** OSP zachowuje trwale klucze odbioru (nadawca, id, revision, skrót treści) także po usunięciu treści. Stacja przechowuje w FRAM najwyższy event na id także po usunięciu treści ze skrzynki, więc nagrana wcześniej wiadomość OSP nie cofa stanu. Pełna ochrona przed powtórzeniem wiadomości OSP po usunięciu ze skrzynki jest wymaganiem do D01; format SA1 0.5 się nie zmienia.

**Polecenia USB.** `configure`, `export`, `import` i aktualizacja oprogramowania działają wyłącznie w trybie przygotowania, włączanym przyciskiem pod plombowaną pokrywą serwisową (dostęp tylko do tego przycisku, bez dostępu do płytki; zerwanie plomby zapisuje się w ewidencji, a po przeglądzie zakłada się nową). Paczka eksportu jest szyfrowana kluczem publicznym stacji docelowej (AEAD, np. X25519 + ChaCha20-Poly1305) i nigdy nie zawiera jawnego klucza prywatnego. Po potwierdzonym imporcie stacja źródłowa trwale usuwa swoją tożsamość. `destroy` i `silence` przez USB wymagają potwierdzenia przyciskiem na stacji w ciągu 30 s. Każde polecenie USB trafia do dziennika zdarzeń stacji.

**Dane osobowe.** Kolejka stacji może zawierać dane o zdrowiu: pole `text` z panelu oraz kategorie 0–1 przy małej liczbie osób. Panel ostrzega `nie_wpisuj_nazwisk`.

| Miejsce | Zapisuje | Nie zapisuje |
|---|---|---|
| stacja (każdy poziom) | tylko wiadomości SA1, klucze i dziennik zdarzeń | IP, MAC, telefonu, nazwiska |
| laptop schronienia (poziomy 2–3) | SA1 + skrót tokenu + czas | IP, MAC, telefonu, nazwiska |
| laptop OSP | SA1 + adres nadawcy + czas odbioru + klucze odbioru + dziennik działań dyżurnych | IP, MAC, telefonu, nazwiska |

**ZAMKNIJ ZDARZENIE.** Po zakończeniu zdarzenia operacja eksportuje zaszyfrowane archiwum dla administratora danych (klucz publiczny z D13), a potem usuwa zgłoszenia, tokeny, eksporty i dzienniki z danymi na laptopie, kolejkę i skrzynkę na stacji oraz treść wiadomości w OSP. Tożsamości i klucze odbioru (ze skrótem SHA-256 treści i wysłanym potwierdzeniem) zostają. Próba w T2 i T8.

## Ekran i przyciski stacji

Ekran graficzny ma wysokość wersalików ≥4 mm, najwyżej 5 wierszy po ≤20 znaków i wysoki kontrast. Pełne teksty stanu nie mieszczą się razem na 5 wierszach, więc ekran główny używa krótkich form z tabeli, po jednym wierszu:

1. stan radia: `radio_wlaczone`;
2. kontakt z odbiorcą: `kontakt_krotki` albo `kontakt_ponad_krotki` (brak świeżego kontaktu nie jest awarią);
3. zasilanie: `zasilanie_aa` albo `zasilanie_12v`;
4. najstarsze niewysłane zgłoszenie: `kolejka_krotki` (pusty wiersz przy pustej kolejce);
5. nowe wiadomości: `nowe_krotki`.

W ciszy radiowej wiersze 1–3 zajmuje pełny tekst `cisza`, a wiersze 4–5 pokazują zasilanie i kolejkę. Aktywny alarm zajmuje cały ekran do potwierdzenia. Pełne teksty (`ostatni_kontakt`, `ogniwa_czas`) pokazuje STAN. `[czas]` podaje się w minutach do 99 MIN, potem w godzinach (H), od 48 H w dobach (D, do 99 D), aby krótkie formy mieściły się w 20 znakach. Do oceny: STAN pokazuje odchyłkę częstotliwości oszacowaną z odebranych ramek. Osoby niewidome zgłaszają przez opiekuna.

Podświetlenie ([elektronika](elektronika.md)): pierwsze naciśnięcie przy zgaszonym ekranie tylko zapala światło; każde naciśnięcie przedłuża je o 30 s; przy otwartej wiadomości świeci ≥60 s. Dioda „NOWA WIADOMOŚĆ / ALARM” miga do odczytu.

**Alarmy.** Brak potwierdzenia od odbiorcy uruchamia alarm `brak_potwierdzenia` po czasie zależnym od pilności: 2 → 15 min, 1 → 1 h, 0 → 6 h. TEST ma osobny próg 30 min ([TEST](#wiadomości-sa1)). Dla pilności 2 drugi alarm `brak_odczytu` następuje, gdy po „odbiorca zapisał” w ciągu 30 min nie przyjdzie „odbiorca przeczytał” (brzmienie do potwierdzenia w T1). Sygnał dźwiękowy alarmu powtarza się do potwierdzenia przyciskiem OK na ekranie alarmu. Potwierdzenie gasi dźwięk tego alarmu; ekran alarmu wraca po każdym wybudzeniu ekranu, a dioda i wpis w PRZEKAZANIE ZMIANY pozostają do usunięcia przyczyny. Dźwięk wraca przy nowym zdarzeniu (alarm innego zgłoszenia, drugi alarm pilności 2), a `wymien_ogniwa` przypomina dźwiękiem co 15 min. Cisza radiowa daje jeden sygnał przy włączeniu, potem tylko stały tekst i diodę, bo może trwać dni, a ciągły dźwięk w schronieniu skłaniałby do wyjęcia ogniw. Alarmów krytycznych (brak potwierdzenia, brak odczytu, `wymien_ogniwa`, cisza) nie da się wyłączyć ani ukryć; wyciszenie zwykłego sygnału nowej wiadomości jest widoczne stale jako `dzwiek_wyciszony`.

**Start.** Radio i przekazywanie ruchu uruchamiają się niezależnie od ekranu i przycisków; gotowość radiowa (≤60 s) nie czeka na żadną decyzję opiekuna, bo przekaźnik może pracować bez obsługi. Po włączeniu wyłącznikiem głównym pierwszy ekran to wybór języka; po restarcie przez watchdog albo po przełączeniu źródła stacja używa języka zapisanego w FRAM i wraca do ekranu, na którym była. Po wyborze języka stacja pokazuje `radio_wlaczone` i kontrolę adresu `adres_kontrola`; przy NIE lub braku adresu pokazuje `adres_brak`. Opcjonalnie stacja ma listę adresów obiektów wczytaną przy przygotowaniu, z wyborem przyciskami. Potem stacja proponuje TEST startowy; OK go planuje (`test_zaplanowany`, `test_wyslany`). Bez reakcji opiekuna TEST nie wychodzi. W trybie przygotowania ekran stale pokazuje `tryb_przygotowania`.

Przyciski: GÓRA, DÓŁ, OK, WSTECZ, duże i wyczuwalne, obsługiwane w rękawicach. Osobny przełącznik CISZA ma osłonę przed przypadkowym przełączeniem. Przycisk konfiguracji (tryb przygotowania) jest pod plombowaną pokrywą serwisową; pola programowania pozostają wewnątrz obudowy.

| Menu | Działanie |
|---|---|
| ZGŁOSZENIE | kreator: kategoria 0–9 z piktogramem → liczba osób → pilność (bez wartości domyślnej) → gotowa fraza lub brak (kategoria 9: fraza obowiązkowa) → podsumowanie; po wysłaniu ekran pokazuje etap i krótki numer |
| WIADOMOŚCI | etapy własnych zgłoszeń, odpowiedzi (REPLY) i komunikaty (BULLETIN) ze źródłem i czasem od odbioru; przy własnym zgłoszeniu: ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA, ANULUJ WYSYŁKĘ |
| TEST | wysłanie TEST i wynik; WSTRZYMAJ i WZNÓW na prośbę odbiorcy z komunikatu |
| STAN | radio, liczniki, energia (`ogniwa_napiecie`, `ogniwa_czas`, napięcie 12 V), `ostatni_kontakt`, wersja, nazwa `WICI-xxxxxx`; PRZEKAZANIE ZMIANY; USŁUGI: ogłoszenie adresu, wyciszenie dźwięku, ODBIORCA ZAPASOWY, ZNISZCZ DANE |
| JĘZYK/МОВА/LANGUAGE | polski, ukraiński, angielski; etykieta zawsze w trzech językach, bez spacji wokół ukośników (19 znaków) |

**Kreator zgłoszenia.** WSTECZ cofa o jeden krok; przytrzymanie WSTECZ przez 2 s pokazuje `porzucic`. Liczba osób: lista „1, 2, 5, 10, 20, 50, 100, INNA”; INNA to wpis cyfra po cyfrze (setki, dziesiątki, jednostki), przytrzymanie przycisku przyspiesza zmianę, domyślnie stoi ostatnio użyta wartość. Pilność wybiera się z etykiet `pilnosc_2`, `pilnosc_1`, `pilnosc_0`; pilność 2 wymaga potwierdzenia `pilnosc_2_potw`. Podsumowanie pokazuje piktogram i kategorię, liczbę osób, pilność słownie, frazę, adres i `podsumowanie_klawisze`. Po 3 min bezczynności szkic zostaje zapisany, a stacja wraca do ekranu głównego. Po wysłaniu ekran pokazuje kolejne etapy z tabeli.

**Własne zgłoszenie.** ZMIEŃ LICZBĘ OSÓB i ZMIEŃ PILNOŚĆ tworzą nową rewizję, jak na stronie. POTRZEBA USTAŁA tworzy nową rewizję z frazą „potrzeba ustała”. ANULUJ WYSYŁKĘ jest dostępne tylko przed „odbiorca zapisał”: oznacza intencję jako anulowaną i zapisuje to w dzienniku zdarzeń. Jeżeli zgłoszenie dotarło do OSP przed anulowaniem albo po nim dotrze z wcześniejszej próby, odbiorca o anulowaniu nie wie; dlatego po „odbiorca zapisał” zamiast ANULUJ jest tylko POTRZEBA USTAŁA. Swobodny opis wpisuje się tylko w panelu laptopa.

**PRZEKAZANIE ZMIANY** (STAN) pokazuje otwarte i niepotwierdzone zgłoszenia, nieprzeczytane wiadomości, energię, ciszę i wyciszenie dźwięku.

**ODBIORCA ZAPASOWY** (STAN → USŁUGI) przełącza stację na tożsamość zapasową OSP z karty, tylko na polecenie przekazane słownie lub przez gońca ([klucz OSP](#model-zaufania-i-kluczy)); pokazuje `odbiorca_zapasowy` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK.

**ZNISZCZ DANE** (STAN → USŁUGI) pokazuje `zniszcz_ostrzezenie` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Nigdy nie uruchamia się na podstawie wiadomości radiowej; polecenie OSP przychodzi tylko słownie lub przez gońca. T8: brak przypadkowego uruchomienia w 10 próbach w rękawicach.

### Teksty ekranu

Jedyna kanoniczna lista tekstów stacji i strony mieszkańca; inne dokumenty cytują teksty tylko z niej, a T1 sprawdza zgodność. Ekran łamie tekst na wiersze ≤20 znaków; tekst dłuższy niż 5 wierszy dzieli się na kolejne ekrany (do sprawdzenia w T1). [x], [n], [m], [mm], [czas] i [xxxx] to wartości wstawiane przez stację. W tekście ciągłym dokumentów dopuszczalne są małe litery w cudzysłowie. Słowo „OKOŁO” pisze się w całości, bo „OK.” myliłoby się z przyciskiem. Kolumny UK i EN są tłumaczeniem roboczym: przed T1 sprawdza je osoba, dla której ukraiński lub angielski jest językiem ojczystym, a T8 z osobą ukraińskojęzyczną; zmiana brzmienia nie może wydłużyć krótkich form ponad 20 znaków. Jednostki `[czas]`: MIN / H / D po polsku i angielsku, ХВ / ГОД / Д po ukraińsku. Napięcie w wersji EN ma kropkę dziesiętną. „ПРИБЛИЗНО” i „ABOUT” pisze się w całości jak „OKOŁO”. Karta obsługi ([karta](karta.md)) cytuje teksty z tej tabeli.

| ID | Ekran PL | Ekran UK | Ekran EN | Znaczenie |
|---|---|---|---|---|
| `radio_wlaczone` | RADIO WŁĄCZONE | РАДІО УВІМКНЕНО | RADIO ON | stacja odbiera i może nadawać |
| `cisza` | CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC | РАДІОТИША – СТАНЦІЯ НЕ ПЕРЕДАЄ. ТЕРМІНОВО: ПОСИЛЬНИЙ | RADIO SILENCE – NOT TRANSMITTING. URGENT: RUNNER | wiersze 1–3 ekranu głównego w ciszy radiowej |
| `ostatni_kontakt` | OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU | ОСТАННІЙ ЗВ'ЯЗОК З ОДЕРЖУВАЧЕМ: [czas] ТОМУ | LAST CONTACT WITH RECIPIENT: [czas] AGO | STAN: czas od ostatniej uwierzytelnionej wiadomości od aktywnej tożsamości OSP (RECEIVED, STATUS, REPLY lub BULLETIN); brak świeżego kontaktu nie jest awarią |
| `ostatni_kontakt_ponad` | OSTATNI KONTAKT Z ODBIORCĄ: PONAD [czas] TEMU | ОСТАННІЙ ЗВ'ЯЗОК З ОДЕРЖУВАЧЕМ: ПОНАД [czas] ТОМУ | LAST CONTACT WITH RECIPIENT: OVER [czas] AGO | STAN po włączeniu bez RTC: dolne oszacowanie |
| `kontakt_krotki` | KONTAKT [czas] TEMU | ЗВ'ЯЗОК [czas] ТОМУ | CONTACT [czas] AGO | ekran główny, wiersz 2 |
| `kontakt_ponad_krotki` | KONTAKT >[czas] TEMU | ЗВ'ЯЗОК >[czas] ТОМУ | CONTACT >[czas] AGO | ekran główny, wiersz 2, po włączeniu bez RTC |
| `zasilanie_aa` | OGNIWA: OKOŁO [x] H | БАТАРЕЇ: ЩЕ [x] ГОД | CELLS: ABOUT [x] H | ekran główny, wiersz 3, praca z ogniw |
| `zasilanie_12v` | 12 V: [x] V | 12 В: [x] В | 12 V: [x] V | ekran główny, wiersz 3, praca z 12 V; napięcie z jednym miejscem po przecinku |
| `ogniwa_napiecie` | OGNIWA: [x] V | БАТАРЕЇ: [x] В | CELLS: [x] V | STAN: napięcie kompletu ogniw z jednym miejscem po przecinku (filtrowana średnia z okresów odbioru); próg kompletu ćwiczebnego z [instrukcji](instrukcja.md#energia-stacji) |
| `kolejka_krotki` | CZEKA [n]: OD [czas] | ЧЕКАЮТЬ [n]: [czas] | WAITING [n]: [czas] | ekran główny, wiersz 4: liczba niewysłanych zgłoszeń i wiek najstarszego |
| `nowe_krotki` | NOWE WIADOMOŚCI: [n] | НОВИХ ПОВІДОМЛ.: [n] | NEW MESSAGES: [n] | ekran główny, wiersz 5 |
| `zapisane_w_stacji` | ZAPISANE W STACJI – CZEKA NA WYSŁANIE | ЗБЕРЕЖЕНО В СТАНЦІЇ – ЧЕКАЄ НА ВІДПРАВЛЕННЯ | SAVED IN STATION – WAITING TO SEND | COMMIT w FRAM stacji |
| `wysylanie` | WYSYŁANIE – PRÓBA [n], NASTĘPNA ZA [m] MIN | ВІДПРАВЛЕННЯ – СПРОБА [n], НАСТУПНА ЧЕРЕЗ [m] ХВ | SENDING – ATTEMPT [n], NEXT IN [m] MIN | intencja w ponawianiu |
| `zapisane_w_ciszy` | ZAPISANE – NIE WYJDZIE DO KOŃCA CISZY | ЗБЕРЕЖЕНО – НЕ ВІДПРАВИТЬСЯ ДО КІНЦЯ ТИШІ | SAVED – NOT SENT UNTIL SILENCE ENDS | zgłoszenie zapisane w ciszy radiowej |
| `stan_1` | ODBIORCA ZAPISAŁ | ОДЕРЖУВАЧ ЗБЕРІГ | RECIPIENT SAVED IT | RECEIVED, state 1 |
| `stan_2` | ODBIORCA PRZECZYTAŁ | ОДЕРЖУВАЧ ПРОЧИТАВ | RECIPIENT READ IT | state 2 |
| `stan_3` | POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU) | ДОПОМОГУ НАПРАВЛЕНО (РІШЕННЯ, НЕ ЧАС ПРИБУТТЯ) | HELP DISPATCHED (DECISION, NOT ARRIVAL TIME) | state 3 |
| `stan_4` | PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT) | ПЕРЕДАНО ДАЛІ (ПОЖЕЖНІ / ШВИДКА / ПОВІТ) | FORWARDED (FIRE SERVICE / AMBULANCE / COUNTY) | state 4 |
| `stan_5` | ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ | ОДЕРЖУВАЧ ЗАРАЗ НЕ МОЖЕ ДОПОМОГТИ – ЧИТАЙТЕ ВІДПОВІДЬ | RECIPIENT CANNOT HELP NOW – READ THE REPLY | state 5, zawsze z REPLY |
| `stan_6` | ZAMKNIĘTE | ЗАКРИТО | CLOSED | state 6 |
| `brak_potwierdzenia` | BRAK POTWIERDZENIA OD [n] MIN – WYŚLIJ GOŃCA Z FORMULARZEM | НЕМАЄ ПІДТВЕРДЖЕННЯ [n] ХВ – ВІДПРАВТЕ ПОСИЛЬНОГО З ФОРМОЮ | NO CONFIRMATION FOR [n] MIN – SEND A RUNNER WITH THE FORM | alarm krytyczny; 15 min / 1 h / 6 h według pilności, 30 min dla TEST |
| `brak_odczytu` | ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – WYŚLIJ GOŃCA Z FORMULARZEM | ОДЕРЖУВАЧ НЕ ПРОЧИТАВ 30 ХВ – ВІДПРАВТЕ ПОСИЛЬНОГО З ФОРМОЮ | NOT READ BY RECIPIENT FOR 30 MIN – SEND A RUNNER WITH THE FORM | alarm krytyczny, tylko pilność 2; brzmienie do potwierdzenia w T1 |
| `dzwiek_wyciszony` | DŹWIĘK WYCISZONY | ЗВУК ВИМКНЕНО | SOUND MUTED | zwykły sygnał wyciszony |
| `test_zaplanowany` | TEST ZAPLANOWANY ZA OKOŁO [mm] MIN – NIE WYŁĄCZAJ. WSTECZ = ANULUJ | ТЕСТ ЗАПЛАНОВАНО ПРИБЛИЗНО ЧЕРЕЗ [mm] ХВ – НЕ ВИМИКАЙТЕ. НАЗАД = СКАСУВАТИ | TEST SCHEDULED IN ABOUT [mm] MIN – DO NOT SWITCH OFF. BACK = CANCEL | TEST startowy w losowym oknie |
| `test_wyslany` | TEST WYSŁANY – CZEKA NA ODBIORCĘ | ТЕСТ ВІДПРАВЛЕНО – ЧЕКАЄ НА ОДЕРЖУВАЧА | TEST SENT – WAITING FOR RECIPIENT | TEST nadany, brak RECEIVED |
| `test_wstrzymany` | TEST WSTRZYMANY PRZEZ ODBIORCĘ | ТЕСТ ПРИЗУПИНЕНО НА ПРОХАННЯ ОДЕРЖУВАЧА | TEST PAUSED AT RECIPIENT'S REQUEST | opiekun wybrał TEST → WSTRZYMAJ po komunikacie OSP |
| `adres_kontrola` | ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE | АДРЕСА: [x] – ЦЕ ЦЕ МІСЦЕ? OK = ТАК / НАЗАД = НІ | ADDRESS: [x] – IS THIS THE PLACE? OK = YES / BACK = NO | kontrola adresu przy starcie |
| `adres_brak` | STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO | СТАНЦІЯ НЕ МАЄ ВАШОЇ АДРЕСИ – ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | STATION DOES NOT HAVE YOUR ADDRESS – USE THE PAPER FORM | odpowiedź NIE albo brak adresu |
| `porzucic` | PORZUCIĆ ZGŁOSZENIE? OK = TAK | СКАСУВАТИ ЗАЯВКУ? OK = ТАК | DISCARD REQUEST? OK = YES | przytrzymanie WSTECZ 2 s w kreatorze |
| `pilnosc_2` | ZAGROŻENIE ŻYCIA | ЗАГРОЗА ЖИТТЮ | DANGER TO LIFE | urgency 2 |
| `pilnosc_1` | PILNE – KILKA GODZIN | ТЕРМІНОВО – КІЛЬКА ГОДИН | URGENT – A FEW HOURS | urgency 1 |
| `pilnosc_0` | W CIĄGU DOBY | ПРОТЯГОМ ДОБИ | WITHIN A DAY | urgency 0 |
| `pilnosc_2_potw` | ZAGROŻENIE ŻYCIA: 1) UDZIEL PIERWSZEJ POMOCY 2) DZIAŁA TELEFON? 112 3) BEZPIECZNA DROGA? GONIEC. OK = WYŚLIJ TEŻ RADIEM | ЗАГРОЗА ЖИТТЮ: 1) НАДАЙТЕ ПЕРШУ ДОПОМОГУ 2) ПРАЦЮЄ ТЕЛЕФОН? 112 3) БЕЗПЕЧНА ДОРОГА? ПОСИЛЬНИЙ. OK = НАДІСЛАТИ ТАКОЖ ПО РАДІО | DANGER TO LIFE: 1) GIVE FIRST AID 2) PHONE WORKS? 112 3) SAFE ROUTE? RUNNER. OK = ALSO SEND BY RADIO | potwierdzenie pilności 2 |
| `podsumowanie_klawisze` | OK = WYŚLIJ, WSTECZ = POPRAW | OK = НАДІСЛАТИ, НАЗАД = ВИПРАВИТИ | OK = SEND, BACK = EDIT | ostatnie wiersze podsumowania |
| `kolejka_pelna` | KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO | ЧЕРГА ПОВНА – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | QUEUE FULL – REQUEST NOT SAVED. USE THE PAPER FORM | 128 intencji w kolejce |
| `blad_pamieci` | BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ + GONIEC | ПОМИЛКА ПАМ'ЯТІ СТАНЦІЇ – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ФОРМА + ПОСИЛЬНИЙ | STATION MEMORY ERROR – REQUEST NOT SAVED. FORM + RUNNER | błąd zapisu FRAM |
| `ogniwa_czas` | OGNIWA: OKOŁO [x] H PRACY | БАТАРЕЇ: ПРИБЛИЗНО [x] ГОД РОБОТИ | CELLS: ABOUT [x] H OF OPERATION | szacowany czas pracy |
| `wymien_ogniwa` | WYMIEŃ OGNIWA W CIĄGU 1 H | ЗАМІНІТЬ БАТАРЕЇ ПРОТЯГОМ 1 ГОД | REPLACE CELLS WITHIN 1 H | alarm krytyczny |
| `wylaczanie` | WYŁĄCZANIE – CZEKAJ, ZAPISUJĘ | ВИМКНЕННЯ – ЗАЧЕКАЙТЕ, ЗБЕРІГАЮ | SWITCHING OFF – WAIT, SAVING | kończenie zapisu przed wyłączeniem |
| `mozna_wyjac` | MOŻNA WYJĄĆ OGNIWA | МОЖНА ВИЙНЯТИ БАТАРЕЇ | CELLS CAN BE REMOVED | zapis zakończony |
| `odlaczone_12v` | 12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO I PRZYTRZYMAJ OK | 12 В ВІДКЛЮЧЕНО – ЗАНИЗЬКА НАПРУГА. ПІДКЛЮЧІТЬ ЗАРЯДЖЕНЕ ДЖЕРЕЛО І УТРИМУЙТЕ OK | 12 V DISCONNECTED – VOLTAGE TOO LOW. CONNECT A CHARGED SOURCE AND HOLD OK | zatrzask podnapięciowy 12 V; praca z ogniw |
| `tryb_przygotowania` | TRYB PRZYGOTOWANIA | РЕЖИМ ПІДГОТОВКИ | PREPARATION MODE | stały pasek w trybie przygotowania |
| `odbiorca_zapasowy` | PRZEŁĄCZYĆ NA ODBIORCĘ ZAPASOWEGO? TYLKO NA POLECENIE GOŃCA LUB SŁOWNE. NIEODWRACALNE | ПЕРЕМКНУТИ НА РЕЗЕРВНОГО ОДЕРЖУВАЧА? ЛИШЕ ЗА УСНИМ НАКАЗОМ АБО ЧЕРЕЗ ПОСИЛЬНОГО. НЕЗВОРОТНО | SWITCH TO BACKUP RECIPIENT? ONLY ON A SPOKEN ORDER OR BY RUNNER. IRREVERSIBLE | przed sekwencją GÓRA, DÓŁ, GÓRA, OK |
| `incoming_osp` | DO ZAPISU W PANELU: [n] | ДО ЗБЕРЕЖЕННЯ В ПАНЕЛІ: [n] | TO SAVE IN PANEL: [n] | stacja OSP: wiadomości `incoming` bez `ack` |
| `zniszcz_ostrzezenie` | NIEODWRACALNE – STACJA PRZESTANIE DZIAŁAĆ; TYLKO PRZY GROŹBIE PRZEJĘCIA | НЕЗВОРОТНО – СТАНЦІЯ ПЕРЕСТАНЕ ПРАЦЮВАТИ; ЛИШЕ ПРИ ЗАГРОЗІ ЗАХОПЛЕННЯ | IRREVERSIBLE – STATION WILL STOP WORKING; ONLY IF CAPTURE THREATENS | przed sekwencją GÓRA, DÓŁ, GÓRA, OK |
| `stopka_komunikatu` | NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA | НАКАЗ ВИЙТИ АБО ЕВАКУЮВАТИСЯ? ПІДТВЕРДІТЬ ПО СУСПІЛЬНОМУ РАДІО АБО В ПОСИЛЬНОГО | ORDER TO LEAVE OR EVACUATE? CONFIRM ON PUBLIC RADIO OR WITH THE RUNNER | stopka każdego BULLETIN |
| `czeka_na_opiekuna` | CZEKA NA OPIEKUNA | ЧЕКАЄ НА КООРДИНАТОРА | WAITING FOR THE WARDEN | strona: zgłoszenie zapisane w laptopie |
| `opiekun_polaczyl` | OPIEKUN POŁĄCZYŁ ZE ZGŁOSZENIEM NR [xxxx] | КООРДИНАТОР ОБ'ЄДНАВ ІЗ ЗАЯВКОЮ № [xxxx] | WARDEN MERGED IT WITH REQUEST NO. [xxxx] | strona: połączone z powtarzalnym |
| `nie_wyslane` | NIE WYSŁANE – PODEJDŹ DO OPIEKUNA | НЕ ВІДПРАВЛЕНО – ПІДІЙДІТЬ ДО КООРДИНАТОРА | NOT SENT – SEE THE WARDEN | strona: opiekun nie przekazał zgłoszenia |
| `zapisz_numer` | ZAPISZ NUMER [xxxx] – PODAJ GO OPIEKUNOWI, ABY SPRAWDZIĆ STAN | ЗАПИШІТЬ НОМЕР [xxxx] – НАЗВІТЬ ЙОГО КООРДИНАТОРУ, ЩОБ ПЕРЕВІРИТИ СТАН | NOTE NUMBER [xxxx] – GIVE IT TO THE WARDEN TO CHECK THE STATUS | strona: po wysłaniu, z lokalnym numerem |
| `zostalo_znakow` | ZOSTAŁO OKOŁO [n] ZNAKÓW | ЗАЛИШИЛОСЯ ПРИБЛИЗНО [n] ЗНАКІВ | ABOUT [n] CHARACTERS LEFT | strona i panel: licznik pod opisem, z limitu bajtów |
| `nie_wpisuj_nazwisk` | NIE WPISUJ NAZWISK | НЕ ВПИСУЙТЕ ПРІЗВИЩ | DO NOT ENTER SURNAMES | strona i panel: ostrzeżenie przy opisie |
| `odpowiedzi_po_polsku` | – | ВІДПОВІДІ ВІД ОДЕРЖУВАЧА НАДХОДЯТЬ ПОЛЬСЬКОЮ | REPLIES FROM THE RECIPIENT ARRIVE IN POLISH | WIADOMOŚCI w wersji UK i EN, nad każdą odpowiedzią i komunikatem; zdanie karty UK i EN |

Pozycje menu, nazwy przycisków i etykiety kategorii są częścią tej listy. Krótkie formy ekranu głównego, pozycje menu i etykiety kategorii mają ≤20 znaków po wstawieniu największych wartości w każdym języku; T1 sprawdza to dla PL, UK i EN.

| PL | UK | EN |
|---|---|---|
| GÓRA / DÓŁ / OK / WSTECZ (przyciski) | ВГОРУ / ВНИЗ / OK / НАЗАД | UP / DOWN / OK / BACK |
| ZGŁOSZENIE | ЗАЯВКА | REQUEST |
| WIADOMOŚCI | ПОВІДОМЛЕННЯ | MESSAGES |
| TEST | ТЕСТ | TEST |
| WSTRZYMAJ | ПРИЗУПИНИТИ | PAUSE |
| WZNÓW | ВІДНОВИТИ | RESUME |
| STAN | СТАН | STATUS |
| USŁUGI | СЕРВІС | SERVICES |
| PRZEKAZANIE ZMIANY | ПЕРЕДАЧА ЗМІНИ | SHIFT HANDOVER |
| ODBIORCA ZAPASOWY | РЕЗЕРВНИЙ ОДЕРЖУВАЧ | BACKUP RECIPIENT |
| ZNISZCZ DANE | ЗНИЩИТИ ДАНІ | DESTROY DATA |
| ZMIEŃ LICZBĘ OSÓB | КІЛЬКІСТЬ ЛЮДЕЙ | CHANGE PEOPLE COUNT |
| ZMIEŃ PILNOŚĆ | ЗМІНИТИ ТЕРМІНОВІСТЬ | CHANGE URGENCY |
| POTRZEBA USTAŁA | ПОТРЕБА ЗНИКЛА | NEED RESOLVED |
| ANULUJ WYSYŁKĘ | СКАСУВАТИ ВІДПРАВКУ | CANCEL SENDING |
| INNA (liczba osób) | ІНША | OTHER |

Etykiety kategorii na ekranie, obok piktogramu (pełny opis kategorii: [wiadomości SA1](#wiadomości-sa1)):

| Kategoria | PL | UK | EN |
|---|---|---|---|
| 0 | POMOC MEDYCZNA | МЕДИЧНА ДОПОМОГА | MEDICAL HELP |
| 1 | LEKI I SPRZĘT MED. | ЛІКИ, МЕДОБЛАДНАННЯ | MEDICINES, EQUIPMENT |
| 2 | EWAKUACJA, TRANSPORT | ЕВАКУАЦІЯ, ТРАНСПОРТ | EVACUATION/TRANSPORT |
| 3 | WODA PITNA | ПИТНА ВОДА | DRINKING WATER |
| 4 | ŻYWNOŚĆ | ХАРЧУВАННЯ | FOOD |
| 5 | OGRZEWANIE, ENERGIA | ОПАЛЕННЯ, ЕНЕРГІЯ | HEATING, POWER |
| 6 | SANITARNE, HIGIENA | САНІТАРІЯ, ГІГІЄНА | SANITATION, HYGIENE |
| 7 | ZAGROŻENIE BUDYNKU | ЗАГРОЗА БУДІВЛІ | BUILDING HAZARD |
| 8 | POSZUKIWANIE, INFO | ПОШУК ЛЮДЕЙ, ІНФО | MISSING PEOPLE, INFO |
| 9 | INNE | ІНШЕ | OTHER |

Domyślne gotowe frazy ([zgłoszenie z przycisków](#wiadomości-sa1)): do SA1 trafia zawsze wersja polska, a ekran pokazuje tłumaczenie w wybranym języku.

| PL (wysyłane) | UK (ekran) | EN (ekran) |
|---|---|---|
| osoba na wózku | людина на візку | wheelchair user |
| osoba leżąca – potrzebne nosze | лежача людина – потрібні ноші | bedridden person – stretcher needed |
| dializy – termin dziś | діаліз – сьогодні | dialysis due today |
| insulina na 1 dzień | інсуліну на 1 день | insulin left for 1 day |
| niemowlę – mleko modyfikowane | немовля – потрібна суміш | infant – formula needed |
| osoba niewidoma lub niesłysząca | незряча або нечуюча людина | blind or deaf person |
| tlen na wyczerpaniu | кисень закінчується | oxygen running out |
| dziecko bez opieki | дитина без опіки | unaccompanied child |
| czujnik CO alarmuje | датчик CO спрацював | CO alarm sounding |
| woda w budynku | вода в будівлі | water in the building |
| potrzeba ustała | потреба зникла | need resolved |

## Stanowisko dyżurnego OSP

Stanowisko to stała stacja WICI i stały laptop z pakietem START (nie „znaleziony”) z pełnym szyfrowaniem dysku (hasło albo TPM+PIN), osobnymi kontami dyżurnych i blokadą ekranu po 5 min. Każde działanie dyżurnego trafia do dziennika działań przypisanego do konta.

Panel dyżurnego:

- sortuje zgłoszenia według pilności, potem czasu odbioru; zgłoszenie z pilnością 2 uruchamia alarm dźwiękowy;
- „PRZECZYTANE” jednym przyciskiem wysyła STATUS ze state=2;
- pokazuje TEST osobno i pozwala potwierdzić kilka TEST zbiorczo, po sprawdzeniu adresu każdego;
- nie wyśle stanu 5 bez REPLY z instrukcją;
- ma widok kwarantanny z wiadomościami „do weryfikacji” i licznikiem odrzuconych wiadomości od tożsamości unieważnionych (alarm „możliwe przejęcie stacji”);
- wysyła BULLETIN osobno do każdej stacji i pokazuje postęp rozsyłania ([pojemność](#wiadomości-sa1)).

Plan stanowiska nazywa konkretnie drugi kanał: goniec, PMR446 z ustalonym kanałem i godzinami nasłuchu, służby na miejscu.

## Tryby kryzysowe

Formalności i uzgodnienia załatwia się przed użyciem. Żadna z poniższych funkcji nie blokuje przyjęcia zgłoszenia.

**Ogłoszenia adresu.** Stacja ogłasza swój adres LXMF przy starcie (z losowym opóźnieniem 0–120 s), na polecenie opiekuna (STAN → USŁUGI lub panel) i automatycznie, gdy intencja do OSP nie dostała potwierdzenia transportowego po 2 próbach LXMF, najwyżej raz na 30 min. Stacja OSP ogłasza adres co 6 h ±20% i po restarcie. W ciszy radiowej nie ma ogłoszeń. Tablicę tras, znane tożsamości i buforowane ogłoszenia stacja zapisuje w FRAM i odtwarza po restarcie. Próba T3 i T5: zimny start po restarcie przekaźnika i przejście z trasy A–OSP na A–B–OSP bez ręcznego ogłoszenia. Nazwa wyświetlana ma postać `WICI-xxxxxx` (6 cyfr szesnastkowych skrótu tożsamości) i nie zawiera adresu ani nazwy miejsca. Emisje transportu Reticulum, np. zapytania o trasę, pozostają i liczy się je w próbie T3. Każda stacja z włączonym transportem retransmituje ogłoszenia innych stacji, więc przy zimnym starcie sieci N stacji kanał przenosi rzędu N² ogłoszeń, a każda stacja zużywa na nie część własnego długu ciszy. Model bez strat daje dla 50 stacji 2500 nadań ogłoszeń, około 21 min czasu kanału w jednym obszarze kolizji i około 5,6 min długu ciszy w każdej stacji. Limit ogłoszeń na interfejsie P1 wynosi początkowo 2% czasu nadawania (domyślna wartość Reticulum); przy nim 50 ogłoszeń przechodzi przez jeden skok w około 21 min. Razem z zapytaniami o trasę do OSP (0,6–8,6 min) i wymianą TEST (około 3,3 min) zimny start 50 stacji zajmuje 61–80% okna TEST startowego, 30 stacji 40–52% ([wyniki modelu](../../software/reference/wyniki.json), [koncepcja, rozdział 06](../conception/06-wykonalnosc-i-budzet-zasobow.html#pojemnosc-sieci)). Sieć powyżej około 30 stacji w jednym obszarze kolizji uruchamia się etapami według planu sieci. Ostateczny limit ogłoszeń i podział na etapy ustala T5 z próbą skali.

**Cisza radiowa.** Polecenie ciszy radiowej wydaje wójt (od wprowadzenia stanu wojennego i w czasie wojny jako organ obrony cywilnej) na podstawie decyzji wojewody lub organów wojskowych albo wynika ono z nakazu wydanego w stanie nadzwyczajnym. Do schronień przekazuje je OSP komunikatem BULLETIN i gońcem; ciszę odwołuje ten sam organ. Opiekun włącza ją przełącznikiem CISZA na stacji albo w panelu. Przełącznik na stacji ma pierwszeństwo przed panelem. Sterownik P1 nic nie nadaje, łącznie z ruchem przekazywanym i ogłoszeniami. Odbiór, zapis i kolejka działają dalej; ekran pokazuje stale `cisza`, a nowe zgłoszenie `zapisane_w_ciszy`. Wyłączenie ciszy jest wyłącznie ręczne, po odwołaniu przez organ. Wyjątek dla pojedynczego zgłoszenia ustawia się tylko z panelu (poziom 2) i tylko przy ciszy operacyjnej ustawionej z panelu, gdy polecenie wprost go dopuszcza; przełącznik CISZA na stacji wyklucza wyjątek. Wyjątek obejmuje całą wymianę tej jednej pary (id, revision): zapytanie o trasę, pakiet zgłoszenia, jego ponowienia i potwierdzenia pakietów dla przychodzących RECEIVED i STATUS; ogłoszeń nie obejmuje. Działa tylko wtedy, gdy cała droga do OSP nadaje: przy ciszy w całej sieci przekaźniki też milczą, więc w praktyce tylko przy bezpośrednim połączeniu z OSP, która sama nie jest w ciszy. Panel pokazuje to ograniczenie przed ustawieniem wyjątku. Wyjątek nie dotyczy zakazu używania urządzeń nadawczych w stanie wojennym lub wyjątkowym – wtedy podstawową procedurą jest goniec. Stacja zapisuje wyjątek w dzienniku zdarzeń, a opiekun w dzienniku papierowym. Fizyczną pewność ciszy daje wyłączenie zasilania stacji; wtedy stacja także nie odbiera.

**Szyfrowanie w spoczynku.** Na laptopie baza i eksporty są szyfrowane kluczem bazy = KDF(plik na pamięci USB zestawu, sekret w magazynie systemowym: DPAPI lub TPM w Windows, Keychain w macOS). Stacja przechowuje klucz tożsamości, kartę OSP, adres, kolejkę i skrzynkę; kolejka może zawierać dane o zdrowiu ([dane osobowe](#model-zaufania-i-kluczy)). Oprogramowanie układowe włącza ochronę odczytu pamięci mikrokontrolera (np. APPROTECT w nRF52840, szyfrowanie pamięci flash w ESP32-S3). Wykonanie z nRF52840 wymaga rewizji 3 (kod wykonania Fx0) z APPROTECT według Nordic IN-141 i MDK ≥8.40.2; starsze rewizje mają znane obejście ochrony (IN-133). Rekordy w FRAM są szyfrowane AEAD kluczem (KEK) przechowywanym w chronionej pamięci MCU ([trwałość](#trwałość-i-potwierdzenia)), więc wylutowanie FRAM nie ujawnia kolejki ani karty OSP. Start nie wymaga hasła. W systemach Windows i macOS baza leży na dysku laptopa, więc po odłączeniu pamięci USB jest nieczytelna. W Linuksie baza i plik klucza są na tej samej pamięci; odpowiednik magazynu systemowego do oceny. W każdym systemie zabranie działającego laptopa razem z pamięcią USB daje dostęp do danych. Szyfrowanie chroni więc tylko przed utratą samego laptopa; przed przejęciem całego stanowiska chroni wyłącznie ZNISZCZ DANE albo zniszczenie pamięci. Kandydatem jest SQLCipher Community Edition (licencja BSD-3-Clause, wymaga dołączenia informacji o prawach autorskich) z biblioteką Pythona [sqlcipher3](https://pypi.org/project/sqlcipher3/) (licencja zlib), która ma gotowe pakiety dla macOS (Intel i ARM), Windows x64 i Linuksa x86_64. To pierwsza zależność bazy spoza biblioteki standardowej. Wymaga przypięcia wersji, sprawdzenia, czy nie osłabia gwarancji trwałości z tej specyfikacji (tryb dziennika, fsync), oraz powtórzenia prób odcięcia zasilania. Ostateczny wybór, także wobec zaszyfrowanego wolumenu, zapada w D13. [SQLCipher](https://www.zetetic.net/sqlcipher/license/).

**ZNISZCZ DANE.** Jedyna definicja operacji. Wykonuje się ją wyłącznie przy groźbie przejęcia stacji lub stanowiska, także na polecenie OSP przekazane słownie lub przez gońca, nigdy na podstawie wiadomości radiowej; fakt zapisuje się w dzienniku papierowym. Na stacji (STAN → USŁUGI albo panel z potwierdzeniem przyciskiem na stacji) operacja najpierw usuwa KEK z pamięci MCU (kryptograficzne wymazanie), potem klucz tożsamości oraz w FRAM kartę OSP, adres, kolejkę, skrzynkę, `incoming` i dziennik zdarzeń. Dziennik długu ciszy zostaje ([radio](radio.md)). Na laptopie operacja zatrzymuje przekazywanie, usuwa wpis klucza z magazynu systemowego, a następnie bazę i eksporty. Nadpisanie pamięci flash i SSD nie gwarantuje usunięcia, dlatego decyduje usunięcie klucza; wobec odczytu samej pamięci USB skuteczne jest tylko jej fizyczne zniszczenie, które nakazuje instrukcja. Operacja jest nieodwracalna, stacja przestaje działać, a całość trwa najwyżej 1 minutę.

**Języki i dostępność.** Ekran stacji i strona mieszkańca są dostępne po polsku, ukraińsku i angielsku. Język wybiera się na pierwszym ekranie po starcie; poza kreatorem zgłoszenia przytrzymanie WSTECZ przez 3 s otwiera wybór języka. Wybór języka nie wymaga przeładowania ani połączenia z internetem. Odpowiedzi i komunikaty od odbiorcy przychodzą po polsku. Kategorie mają piktogramy i są przesyłane jako liczby, więc dyżurny widzi kategorię, liczbę osób i lokalizację niezależnie od języka opisu. Litery ukraińskie zajmują w UTF-8 po 2 B, tak jak polskie znaki diakrytyczne, więc opis zgłoszenia mieści około 48 takich znaków. Strona używa semantycznego HTML, działa z czytnikiem ekranu i przy powiększeniu tekstu do 200%.

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
  firmware/                    # podpisane obrazy oprogramowania stacji obu wykonań; tylko w trybie przygotowania
  drivers/<platform>/
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, skróty, polecenie budowy, lista plików; podpisany
  keys/                        # plik klucza bazy tego laptopa; nie trafia do kopii publicznych
  export/                      # zaszyfrowana paczka przeniesionej stacji
```

W Linuksie stan znajduje się na osobnej partycji ext4 pamięci USB, a w systemach Windows i macOS na dysku laptopa, w katalogu aplikacji. Aktywna baza nie może leżeć na exFAT. Aplikacja nie zapewnia automatycznej wspólnej bazy między systemami.

PRZENIEŚ STACJĘ (tylko w trybie przygotowania) wymaga sprawnej stacji źródłowej: zatrzymuje nowe zgłoszenia i wysyłkę, eksportuje ze stacji przez laptop tożsamość, licznik czasu pracy, konfigurację i kolejkę w paczce zaszyfrowanej kluczem publicznym stacji docelowej ([model zaufania](#model-zaufania-i-kluczy)), a stara stacja przestaje nadawać i po potwierdzonym imporcie usuwa tożsamość. Stacja zapasowa importuje paczkę. Bazę laptopa kopiuje się osobno przez API kopii zapasowych SQLite i sprawdza jej integralność. Obu stacji z tą samą tożsamością nie wolno używać jednocześnie. Nie ma wcześniejszej kopii tożsamości, bo dwie stacje z tą samą tożsamością nie mogą istnieć jednocześnie. Uszkodzona lub utracona stacja nie daje się przenieść: stacja zapasowa dostaje nową tożsamość, nową kartę stacji przekazuje się do OSP (`trust`), a starą tożsamość OSP unieważnia (`revoke`). Stacja zapasowa w zestawie OSP służy więc do kontrolowanej wymiany sprawnej stacji i do wczytania tożsamości zapasowej OSP. [API kopii](https://www.sqlite.org/backup.html).

**Aktualizacja oprogramowania stacji.** Obraz jest podpisany kluczem wydania (Ed25519 lub ECDSA-P256; MCUboot w nRF52840, Secure Boot V2 w ESP32-S3); klucz wydania jest przechowywany offline, a podpis składa się po odtworzeniu kompilacji (T7). Program rozruchowy odrzuca obraz bez podpisu i starszy od zainstalowanego (anti-rollback); nie ma DFU ani UF2 bez podpisu. Aktualizacja odbywa się przez USB z laptopa z pakietem START, tylko w trybie przygotowania (przycisk pod plombowaną pokrywą serwisową), bez otwierania obudowy głównej. ESP32-S3: szyfrowanie flash w trybie Release, eFuse wyłączające JTAG, tryb bezpiecznego pobierania. Konsola UART i logi diagnostyczne są wyłączone w wydaniu. `build-manifest.json` jest podpisany (Ed25519 lub minisign), a odcisk klucza jest na karcie przeglądu. Podpis START dla Windows (Authenticode) i macOS (Developer ID, notaryzacja) – do oceny kosztu.

Pakiet START utrzymuje komputer w stanie pracy podczas działania strony. Uśpienie laptopa wyłącza tylko stronę i panel; stacja pracuje dalej. Po wznowieniu aplikacja wykonuje `sync` ze stacją.

Przed dystrybucją pakiety muszą zostać zbudowane i przetestowane na każdej architekturze. W schronieniu nie instaluje się pakietów przez pip. Po próbie zgodności wydanie przypina dokładne archiwa lub commity wraz z ich skrótami. Podczas uruchamiania nie pobiera się wersji `latest`.

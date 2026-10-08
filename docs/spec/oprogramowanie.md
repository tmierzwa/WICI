# WICI: oprogramowanie

## Podział oprogramowania

**Oprogramowanie układowe stacji** zawiera port microReticulum z włączonym transportem, moduł LXMF (LXMRouter) z jedną tożsamością stacji, interfejs radiowy jako interfejs Reticulum (w pilotażu LoRa, [profil](radio.md#profil-lora-pilotażu); w wariancie zapasowym P1), rejestr zgłoszeń, kolejkę i skrzynkę odbiorczą w pamięci FRAM, interfejs ekranu i przycisków, [protokół USB](protokol-usb.md) do laptopa oraz układ nadzorujący (watchdog). Stacja jest jedynym węzłem sieci w schronieniu i działa bez laptopa. Stacja stanowiska ma to samo oprogramowanie w konfiguracji węzła stanowiska: przekazuje ruch i łączy radio z komputerem stanowiska ([stanowisko odbiorcze](stanowisko-osp.md)). Wersje referencyjne protokołu: Reticulum `e40191b` i LXMF `c3ff2d6`. Implementację LXMF dla mikrokontrolera (z istniejących projektów albo własną, zgodną z wersją referencyjną) wybiera się w D14 po T3. [microReticulum](https://github.com/attermann/microReticulum), [LXMF](https://github.com/markqvist/LXMF).

LXMF pakuje wiadomości, szyfruje je przez Reticulum, wyszukuje trasę, potwierdza dostarczenie na poziomie transportu i ponawia wysyłkę. Tych mechanizmów nie implementuje się drugi raz. Stan DELIVERED w LXMF nie oznacza zatwierdzonej transakcji w bazie stanowiska odbiorczego. Kolejka intencji jest w FRAM i stacja odtwarza ją po restarcie. Lista oczekujących wiadomości w pamięci LXMF nie jest trwałą kolejką.

Konfiguracja LXMF: wyłącznie dostarczenie okazjonalne (OPPORTUNISTIC), bez przejścia na DIRECT, Resource ani propagację; treść, która się nie mieści, jest błędem już przy tworzeniu intencji. Bez znaczków pracy (brak `stamp_cost`). Ratchety rozstrzyga D01; jeśli zostaną włączone, ich klucze są w FRAM.

**Aplikacja laptopa** (`station-web`, poziomy 2–3) zawiera serwer lokalnej strony, jedną bazę SQLite i panel opiekuna. Nie uruchamia Reticulum ani LXMF i nie ma tożsamości sieciowej; wiadomości przekazuje stacji [protokołem USB](protokol-usb.md). Poziomy 2–3 dochodzą po pilotażu; w pilotażu laptop łączy się ze stacją tylko w trybie przygotowania. Odłączenie laptopa nie przerywa pracy stacji. Restart strony nie zmienia kolejki stacji. Na stanowisku odbiorczym tożsamość odbiorcy, Reticulum, LXMF i baza działają na komputerze stanowiska, a przyjęcie zgłoszenia i wysłanie RECEIVED odbywają się w SQLite aplikacji stanowiska ([stanowisko odbiorcze](stanowisko-osp.md), D19).

NomadNet i narzędzia Reticulum w Pythonie nie są częścią wydania; Reticulum i LXMF w Pythonie uruchamia tylko aplikacja stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). NomadNet i narzędzia mogą służyć w laboratorium do prób zgodności (T3) jako osobne węzły z własną tożsamością. Nie wolno wymagać od mieszkańców instalacji klienta. [NomadNet](https://github.com/markqvist/NomadNet).

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik, bez załączników. Cała treść po kodowaniu ma najwyżej 256 B (decyzja robocza, do potwierdzenia w D01 i T3; zastępuje przejściowe 480 B), więc każda wiadomość SA1 mieści się w jednym pakiecie okazjonalnym LXMF, około 284 B dla wersji referencyjnych ([koncepcja, rozdział 05](../concept/05-projekt-koncepcyjny-komunikacji.html#rozmiar-wiadomosci-a-sposob-dostarczenia)). Przypadki najgorsze przy limitach pól poniżej: REQUEST i TEST 222 B, BULLETIN 246 B, REPLY 156 B, STATUS 59 B, RECEIVED 50 B; zgłoszenie z przycisków 220 B. JSON zawiera jedną tablicę; swobodne obiekty są odrzucane. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`. Teksty SA1 nie mogą zawierać znaków U+0022 (`"`) i U+005C (`\`); formularz, panel i ekran zamieniają je na „ ” i `/`, więc tekst nigdy nie wymaga sekwencji ucieczki. Teksty nie mogą też zawierać znaków z kategorii Unicode Cc, Cf, Cs, Co, Cn, Zl i Zp (m.in. znaków C1, znaków zmiany kierunku pisma, niewidocznych znaków formatujących, surogatów, znaków prywatnych i nieprzypisanych, separatorów wiersza i akapitu). Wymagana jest normalizacja NFC; tekst w innej postaci jest odrzucany. Zwykłe polskie i ukraińskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |
| TEST = 5 | `[1,5,id,revision,category,people,location,text,urgency]` |

`id`: 32 małe cyfry szesnastkowe, czyli 16 losowych bajtów z CSPRNG. Tworzy go ten, kto tworzy zgłoszenie SA1: stacja dla zgłoszeń z przycisków i TEST z menu ([model zaufania](#model-zaufania-i-kluczy)), aplikacja laptopa (CSPRNG systemu operacyjnego) dla zgłoszeń z panelu i zgłoszeń mieszkańców zatwierdzonych przez opiekuna, aplikacja stanowiska dla BULLETIN; RECEIVED, STATUS i REPLY powtarzają `id` zgłoszenia. Zgłoszenie mieszkańca przed zatwierdzeniem nie ma `id` SA1, tylko lokalny identyfikator strony ([strona mieszkańca](#strona-mieszkańca)). `revision`: 0–65 535. `category`: 0–9 = 0 pomoc medyczna (zagrożenie życia lub zdrowia); 1 leki stałe i sprzęt medyczny (tlen, insulina, dializy); 2 ewakuacja i transport, w tym osób leżących i z niepełnosprawnością; 3 woda pitna; 4 żywność, w tym dla niemowląt; 5 ogrzewanie, energia, paliwo; 6 sanitarne i higiena; 7 bezpieczeństwo obiektu (pożar, CO, zalanie, uszkodzenie); 8 informacja i poszukiwanie osób; 9 inne (wymaga frazy lub opisu). `people`: 1–65 535. `location`: 1–64 B, dokładny adres i miejsce wejścia w krótkiej postaci (ulica, numer, wejście; miejscowość tylko wtedy, gdy ta sama ulica występuje w gminie więcej niż raz); `configure` odrzuca dłuższy adres. Miejsce w budynku („gdzie w budynku”) nie należy do `location`: panel i strona dopisują je na początku `text` i liczą do jego limitu. `text` zgłoszenia i odpowiedzi: do 96 B; komunikatu: do 192 B. `urgency`: 2 = bezpośrednie zagrożenie życia lub zdrowia („ZAGROŻENIE ŻYCIA”); 1 = pilne, w ciągu kilku godzin („PILNE – KILKA GODZIN”); 0 = w ciągu doby („W CIĄGU DOBY”); podwyższenie zatwierdza opiekun. Przy pilności 2 opiekun równolegle udziela pierwszej pomocy i – gdy droga jest bezpieczna – wysyła gońca do najbliższej jednostki PSP/OSP lub zespołu ratownictwa medycznego. WICI nie zastępuje numeru 112. `event`: 1–2 147 483 647, bez zawijania licznika. RECEIVED ma zawsze 1. Dla STATUS, REPLY i BULLETIN aplikacja stanowiska nadaje wartość max(ostatnia wartość tego licznika + 1, liczba sekund od 2026-01-01 00:00 UTC według zegara komputera stanowiska), osobno dla STATUS danego `id`, REPLY danego `id` i wszystkich BULLETIN tej tożsamości odbiorcy. Dzięki składnikowi czasu numeracja rośnie także po odtworzeniu bazy stanowiska z wcześniejszej kopii; aplikacja nie startuje, gdy zegar komputera jest wcześniejszy niż czas ostatniego nadanego `event` w bazie ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Wartość starcza do 2094 roku. `state` (teksty ekranu w tabeli [Teksty ekranu](#teksty-ekranu)): 1 = „odbiorca zapisał”, 2 = „odbiorca przeczytał”, 3 = „pomoc skierowana”: podmiot, który dysponuje siłami (np. stanowisko kierowania PSP, dyspozytor medyczny, służba gminy), potwierdził stanowisku odbiorczemu skierowanie pomocy; to decyzja, nie godzina przyjazdu, 4 = „przekazane dalej” (PSP, pogotowie, powiat): stanowisko przekazało zgłoszenie, ale nie ma potwierdzenia skierowania pomocy, 5 = „odbiorca nie może teraz pomóc” – zawsze razem z REPLY z instrukcją (np. użyj kanału zastępczego), 6 = „zamknięte” (potrzeba ustała).

RECEIVED zawsze oznacza pierwsze przyjęcie danej rewizji, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2–6; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli stanowisko odbiorcze ma już nowszy status, wysyła też najnowszy STATUS. Liczniki event mają klucze (tożsamość odbiorcy, typ, `id`) dla STATUS i REPLY oraz (tożsamość odbiorcy, BULLETIN) dla komunikatów; numer rewizji nie jest częścią klucza. Przyjęcie, kolejność i wiadomości spóźnione opisuje [cykl życia zgłoszenia](#cykl-życia-zgłoszenia). Każdy BULLETIN ma nowe `id`, a poprawka komunikatu jest nowym komunikatem. Żaden BULLETIN nie wywołuje działania automatycznego stacji; każdy komunikat na ekranie ma stopkę `stopka_komunikatu`.

TEST ma tablicę, limity i walidację REQUEST. Sprawdza całą drogę zgłoszenia: transport, zapis na stanowisku i obecność dyżurnego. Stacja proponuje go na ekranie po uruchomieniu, restarcie oraz zmianie anteny lub odbiorcy i wysyła na polecenie opiekuna z menu lub panelu; nigdy cyklicznie. Stacja z zegarem RTC nie proponuje TEST po wymianie ogniw, jeśli ostatni kontakt z odbiorcą był według RTC mniej niż 6 h wcześniej; stacja bez RTC nie zna czasu wyłączenia i proponuje TEST po każdym włączeniu ([czas](#trwałość-i-potwierdzenia)). TEST startowy (proponowany po uruchomieniu i restarcie) wychodzi z losowym opóźnieniem w oknie 50 s × liczba stacji w sieci od polecenia, aby wiele stacji włączonych naraz nie zajęło kanału; liczbę stacji zapisuje `configure` (bez niej okno wynosi 15 min, co wystarcza tylko dla sieci do 18 stacji). Ekran pokazuje `test_zaplanowany`, a WSTECZ anuluje. Kolejność uruchamiania stacji ustala w planie organizator sieci (zwykle samorząd gminy). Odbiorca może poprosić o wstrzymanie TEST komunikatem BULLETIN. Stacja nie rozpoznaje go automatycznie: opiekun po przeczytaniu komunikatu wybiera TEST → WSTRZYMAJ, co anuluje TEST oczekujący na nadanie i do odwołania pokazuje `test_wstrzymany`; TEST → WZNÓW odwołuje wstrzymanie. TEST ma najniższy priorytet w kolejce stacji.

Pola TEST startowego i TEST z menu: `category` = 9, `people` = 1, `urgency` = 0, `location` = adres stacji, `text` = „test”. Alarm TEST nie zależy od pilności: `brak_potwierdzenia` po 30 min od `test_wyslany` bez RECEIVED. Zgłoszenia wysyłane podczas prób i ćwiczeń również mają typ TEST; wyjątek: próby odbioru w sieci próbnej bez rzeczywistego odbiorcy (odbiór, „Obciążenie sieci” i „Ruch mieszany z dyżurnym”) używają REQUEST. TEST startowy zawiera rzeczywisty adres i wejście schronienia, aby dyżurny mógł potwierdzić, że są zrozumiałe. Odbiorca przyjmuje TEST jak REQUEST: weryfikacja nadawcy, kwarantanna nieznanej stacji, deduplikacja, jedna transakcja i RECEIVED po COMMIT. Klucz odbioru nie zależy od typu; REQUEST i TEST o tym samym id i revision to konflikt treści. Stanowisko odbiorcze pokazuje TEST osobno od kolejki potrzeb i nie wlicza go do potrzeb. Dyżurny odpowiada wiadomością STATUS ze state=2. Wartości state 3–6 dla TEST są dopuszczalne tylko w uzgodnionym ćwiczeniu i oznaczają decyzję ćwiczebną bez wysłania pomocy. Stacja pokazuje TEST na ekranie i w panelu opiekuna, nie jako zgłoszenie mieszkańca.

**Pojemność.** Pojemność ogranicza najbardziej obciążony węzeł, zwykle stacja stanowiska i przekaźnik obok niej, i dotyczy całej sieci, a nie pojedynczego przekaźnika. Model bez strat w profilu LoRa SF7 ([rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html#pojemnosc-sieci)): stanowisko przyjmuje około 164 zgłoszeń na godzinę z RECEIVED i dwoma STATUS, przekaźnik przed stanowiskiem około 95 na godzinę (w wariancie zapasowym P1: 121 i 68). Dodanie przekaźników nie zwiększa tego limitu; zwiększa go tylko drugi odbiorca albo podział sieci. BULLETIN wysyła się osobno do każdej stacji: dla 50 stacji to około 8,5 min pracy nadajnika stanowiska z obowiązkową ciszą (P1: około 12 min), i tyle samo trwa rozesłanie polecenia ciszy. Pojemność rzeczywistą wyznacza T5.

Zmiana danych zgłoszenia tworzy nową rewizję (revision). Każda rewizja zawiera pełną lokalizację i treść, więc odbiorca nie potrzebuje wcześniej przekazanych danych o budynku. Stanowisko pokazuje rewizje jako jedno zgłoszenie, ale każdą potwierdza się osobno. Przez radio nie wysyła się imion, numerów PESEL, danych dokumentów ani tokenów strony. Dyżurny nie wpisuje nazwisk ani informacji o zdrowiu do REPLY i BULLETIN. Typ stanu obiektu (MELDUNEK) nie jest częścią SA1 0.5 – rozstrzyga D18.

Zgłoszenie z przycisków (poziom 1) tworzy stacja: `category` i `urgency` z menu (pilność bez wartości domyślnej), `people` 1–999 z listy gotowych wartości lub wpisu cyfra po cyfrze, `location` z adresu zapisanego podczas przygotowania (przy liście obiektów: z obiektu wybranego po włączeniu; rewizja zachowuje lokalizację zgłoszenia), `text` pusty albo jedna z gotowych fraz z konfiguracji (każda ≤96 B UTF-8, zapisana po polsku; ekran pokazuje jej tłumaczenie z konfiguracji w wybranym języku, a dyżurny otrzymuje wersję polską). Kategoria 9 wymaga frazy. `urgency` = 2 wymaga dodatkowego potwierdzenia. `configure` odrzuca adres i frazę, jeśli najgorsze zgłoszenie z przycisków przekroczyłoby limit 256 B. Domyślna lista fraz: osoba na wózku; osoba leżąca – potrzebne nosze; dializy – termin dziś; insulina na 1 dzień; niemowlę – mleko modyfikowane; osoba niewidoma lub niesłysząca; tlen na wyczerpaniu; dziecko bez opieki; czujnik CO alarmuje; woda w budynku; potrzeba ustała. Ekran i panel pokazują krótki numer zgłoszenia: pierwsze 16 bitów `id` modulo 10 000, jako cztery cyfry. Cztery cyfry powtarzają się już przy kilkudziesięciu zgłoszeniach (około 4% przy 30), dlatego numer jest unikalny w obrębie stacji: stacja losuje `id` ponownie, dopóki krótki numer nie różni się od numerów zgłoszeń w jej kolejce i dzienniku zdarzenia, a nowe `id` z laptopa o zajętym numerze odrzuca (`rejected`, przyczyna `numer_zajety`) i laptop losuje nowe. Numer ten razem z nazwą stacji `WICI-xxxxxx` jednoznacznie wskazuje zgłoszenie przy przekazaniu telefonicznym lub przez gońca.

## Cykl życia zgłoszenia

Stacja prowadzi dla każdego własnego `id` (REQUEST i TEST) jeden wpis w rejestrze zgłoszeń ([pamięć FRAM](#pamięć-fram)). Wpis ma dwie niezależne części: **wysyłkę najnowszej rewizji** i **decyzję odbiorcy**. Historia rewizji zostaje w dzienniku zdarzeń, a w rejestrze tylko najnowsza rewizja z pełną treścią, bo każda rewizja zawiera pełną lokalizację i treść.

| Pole wpisu | Znaczenie |
|---|---|
| `r_max`, treść | najnowsza rewizja i jej tablica SA1 |
| `r_rcv` | najwyższa rewizja potwierdzona RECEIVED albo wiadomością STATUS lub REPLY tej rewizji; −1, gdy żadna |
| etap | etap wysyłki `r_max`: `zapisane`, `wysylanie`, `dostarczone` (LXMF DELIVERED bez RECEIVED), `odebrane`, `anulowane` |
| decyzja | stan 2–6 i rewizja z ostatniego przyjętego STATUS; 0, gdy brak |
| `status_hi`, `reply_hi` | najwyższy przyjęty `event` STATUS i REPLY tego `id` od aktywnej tożsamości odbiorcy |
| czasy | COMMIT każdej niepotwierdzonej rewizji, RECEIVED `r_max`, ostatnia zmiana (czas pracy stacji) |

**Wiadomości przychodzące.** Stacja sprawdza najpierw podpis, aktywną tożsamość odbiorcy i format ([trwałość](#trwałość-i-potwierdzenia)). Wiadomość odrzucona albo pominięta nie zmienia stanu; trafia tylko do liczników diagnostyki i dziennika zdarzeń.

| Wiadomość | Przyjęta, gdy | Skutek |
|---|---|---|
| RECEIVED (`id`, r) | `id` jest w rejestrze i r ≤ `r_max` | `r_rcv` = max(`r_rcv`, r); przy r = `r_max` etap `odebrane` i koniec ponowień; RECEIVED dla zgłoszenia anulowanego otwiera je ponownie jako `odebrane`, bo odbiorca o anulowaniu nie wie |
| STATUS (`id`, r, e, s) | jak wyżej i e > `status_hi` | `status_hi` = e, decyzja = (s, r); działa też jak RECEIVED rewizji r |
| REPLY (`id`, r, e) | jak wyżej i e > `reply_hi` | `reply_hi` = e, odpowiedź do skrzynki; działa też jak RECEIVED rewizji r |
| BULLETIN (`id`, e) | (`id`, e) nie ma wśród 64 ostatnio przyjętych komunikatów i e > (najwyższy przyjęty `event` komunikatu − 86 400) | komunikat do skrzynki, para do pamięci ostatnich komunikatów |
| wiadomość dla `id` spoza rejestru albo z r > `r_max` | nigdy | pominięta |
| STATUS lub REPLY z e ≤ licznika | nigdy | pominięta jako powtórzenie albo spóźniona |

Decyzją wyświetlaną jest zawsze ta z najwyższym `event`, niezależnie od rewizji; dyżurny decyduje o zgłoszeniu jako całości. Liczniki należą do aktywnej tożsamości odbiorcy: po przełączeniu na KLUCZ ZAPASOWY stacja zaczyna je od zera dla tożsamości zapasowej, a wiadomości od głównej odrzuca.

**Czynności lokalne:**

| Czynność | Warunek | Skutek |
|---|---|---|
| nowe zgłoszenie (przyciski, `submit`, TEST) | wolny wpis w rejestrze i wolne miejsce w kolejce | wpis z r = 0, etap `zapisane`, intencja wysyłki |
| nowa rewizja (ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA, `submit` z r > `r_max`) | zgłoszenie nieanulowane | `r_max` = r, etap `zapisane`; intencja poprzedniej rewizji kończy się: nienadana od razu, nadawana po zakończeniu bieżącej próby LXMF, bez dalszych ponowień; decyzja zostaje i jest wyświetlana pod etapem nowej rewizji |
| ANULUJ WYSYŁKĘ | `r_rcv` = −1 | etap `anulowane`, intencja zakończona, wpis do dziennika zdarzeń |
| KLUCZ ZAPASOWY | – | intencje rewizji bez RECEIVED wracają do kolejki z tym samym `id` i `revision`, z nowym celem; liczniki od zera |

**Ekran.** Przy zgłoszeniu w WIADOMOŚCIACH i w PRZEKAZANIU ZMIANY stacja pokazuje: przy etapie `zapisane` tekst `zapisane_w_stacji` (w ciszy `zapisane_w_ciszy`), przy `wysylanie` i `dostarczone` tekst `wysylanie`, a pod nim stan z decyzji, jeśli jest; przy etapie `odebrane` stan z decyzji (`stan_2`–`stan_6`) albo `stan_1`, gdy decyzji jeszcze nie ma. Zgłoszenie anulowane znika z listy otwartych zgłoszeń.

**Alarmy.** `brak_potwierdzenia` uruchamia się, gdy `r_max` nie ma RECEIVED, a od COMMIT najstarszej rewizji nowszej niż `r_rcv` minął czas zależny od pilności `r_max` (2 → 15 min, 1 → 1 h, 0 → 6 h; TEST 30 min). `brak_odczytu` uruchamia się przy pilności 2, gdy 30 min po RECEIVED `r_max` nie przyszedł STATUS tej rewizji. Wyłączenie stacji zatrzymuje liczenie ([czas](#czas)).

**Wektory prób** (T2; stan po ostatniej wiadomości, `id` X w rejestrze z `r_max` = 1, `r_rcv` = −1, wszystkie wiadomości od aktywnej tożsamości):

| Sekwencja wiadomości | Wynik |
|---|---|
| RECEIVED(X,0), RECEIVED(X,1) | `r_rcv` = 1, etap `odebrane`, ekran `stan_1` |
| STATUS(X,0,e=10,s=3), RECEIVED(X,1) | decyzja 3, etap `odebrane`, ekran `stan_3` |
| STATUS(X,1,e=10,s=2), STATUS(X,0,e=9,s=3) | drugi pominięty; decyzja 2 |
| STATUS(X,1,e=10,s=6), STATUS(X,1,e=10,s=6) | drugi pominięty jako powtórzenie |
| RECEIVED(X,2) | pominięty (r > `r_max`) |
| REPLY(X,1,e=5), STATUS(X,1,e=4,s=5) | oba przyjęte (osobne liczniki); decyzja 5, odpowiedź w skrzynce |
| STATUS(X,0,e=10,s=6), potem nowa rewizja 2 | decyzja 6 zostaje, etap `zapisane`; ekran `zapisane_w_stacji` i pod nim `stan_6`, do RECEIVED rewizji 2 |
| ANULUJ (przed RECEIVED), potem RECEIVED(X,1) | wpis otwarty ponownie, etap `odebrane`, ekran `stan_1`; opiekun wysyła POTRZEBA USTAŁA |
| STATUS(Y,0,e=3,s=3) dla Y spoza rejestru | pominięty |
| BULLETIN(B,e=100), BULLETIN(B,e=100) | drugi pominięty |
| BULLETIN(B1,e=200 000), BULLETIN(B2,e=100 000) | drugi pominięty (starszy o ponad dobę) |

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zgłoszenie z przycisków | zgłoszenie + intencja wysyłki w FRAM stacji |
| Zgłoszenie ze strony | w SQLite laptopa: zgłoszenie mieszkańca + skrót tokenu dostępu, w kolejce opiekuna |
| Zatwierdzenie przez opiekuna | w SQLite laptopa: zgłoszenie SA1 z nowym `id` + powiązanie ze zgłoszeniami mieszkańców + intencja przekazania; w stacji: zgłoszenie + intencja wysyłki, idempotentnie po kluczu wiadomości |
| Przyjęcie na stanowisku | zweryfikowane zgłoszenie + tożsamość nadawcy + klucz odbioru + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS (przy stanie 3 także źródło i czas potwierdzenia skierowania pomocy, przy stanie 4 komu i kiedy przekazano, przy stanie 5 intencja REPLY) |

**Zapis w FRAM.** Każdy magazyn ma stałe gniazda ([pamięć FRAM](#pamięć-fram)). Rekord gniazda ma nagłówek (magazyn, gniazdo, wersja formatu, generacja klucza, numer zapisu, długość), treść i znacznik zatwierdzenia (CRC-32 rekordu i stała 4 B). Zapis do gniazda, które ma zatwierdzoną treść, nigdy nie nadpisuje jej bezpośrednio: każda zmiana, także zmiana jednego pola i zmiana kilku gniazd naraz (np. nowa rewizja i zakończenie poprzedniej intencji, wiadomość w skrzynce i zdarzenie dla laptopa), przechodzi przez rekord transakcji. Rekord transakcji (dziennik zapisu z wyprzedzeniem) zawiera pełne nowe bajty wszystkich zmienianych gniazd i własny znacznik; dopiero po jego zatwierdzeniu (COMMIT stacji) stacja przepisuje bajty do gniazd i oznacza transakcję jako wykonaną. Po restarcie zatwierdzony, niewykonany rekord transakcji jest wykonywany ponownie (zapis jest idempotentny), a niezatwierdzony odrzucany; gniazda zachowują wtedy poprzednią treść. Są dwa rekordy transakcji używane na zmianę, więc zanik w czasie zapisu nowego nie niszczy poprzedniego. Największa transakcja ma ≤2 KiB. Zapis idzie seriami SPI po ≤256 B; przy zegarze SPI pamięci ≥8 MHz seria trwa ≤0,3 ms. Po sygnale zaniku zasilania stacja kończy bieżącą serię, zwalnia linię CS pamięci i nie zaczyna następnej; ten czas wchodzi do budżetu zaniku zasilania ([elektronika](elektronika.md#zanik-zasilania-i-zapis)). Poprawność nie zależy od tego, czy zdąży się zapisać cała transakcja: zanik przed znacznikiem odrzuca niezatwierdzoną transakcję, co jest dopuszczalne, bo `zapisane_w_stacji` i `stored` pojawiają się dopiero po COMMIT. Przed wyłączeniem przy niskim napięciu ogniw stacja kończy bieżący zapis i pokazuje `wylaczanie`, a potem `mozna_wyjac`.

**Szyfrowanie rekordów FRAM** jest wymagane przed wydaniem, nie przed pilotażem (F99): na poziomie 1 kolejka zawiera tylko frazy z przycisków, a dane o zdrowiu tylko pośrednio przez kategorie. Każdy rekord gniazda i rekord transakcji jest szyfrowany w całości jako jeden szyfrogram AEAD (AES-128-GCM albo ChaCha20-Poly1305 w ESP32-S3; AES-128-CCM w nRF52840 z CC310) ze znacznikiem 16 B i własnym nonce; dane uwierzytelnione to nagłówek rekordu (z magazynem i gniazdem, więc rekordu nie da się przenieść do innego gniazda). Rekord z błędnym znacznikiem traktuje się jak uszkodzony. Jawne zostają tylko dziennik długu ciszy, licznik czasu pracy, ustawienia ekranu, rekord rezerwacji numerów zapisu i znacznik postępu zmiany klucza.

- **Klucz.** Klucz szyfrowania generacji g to HKDF-SHA-256(KEK, „WICI FRAM” ‖ g). KEK (32 B) leży w dedykowanej stronie pamięci flash MCU poza systemem plików, chronionej szyfrowaniem flash albo APPROTECT, kasowanej z weryfikacją. Generacja klucza (32 b; nie mylić z epoką pierścienia zdarzeń USB) zaczyna się od 1 przy utworzeniu KEK; nowy KEK (i generacja 1) powstaje po ZNISZCZ DANE i po imporcie PRZENIEŚ STACJĘ, a nowa generacja tego samego KEK po ZAMKNIJ ZDARZENIE. Zmiana klucza przepisuje wszystkie rekordy pod nowy klucz w operacji wznawianej po zaniku zasilania: generacja w nagłówku mówi, którym kluczem zaszyfrowano dany rekord, a jawny znacznik postępu – do którego gniazda doszła operacja; stary klucz istnieje do jej zakończenia.
- **Nonce** (96 b) = generacja klucza (32 b) ‖ numer zapisu (64 b). Numer zapisu rośnie przy każdym zapisie szyfrowanym (rekord transakcji, gniazdo, także przepisanie tego samego gniazda), jest w nagłówku rekordu i nigdy się nie powtarza dla jednego klucza; ponowne wykonanie zatwierdzonej transakcji po restarcie zapisuje te same szyfrogramy z rekordu transakcji, więc nie tworzy nowego nonce. Stacja rezerwuje numery blokami po 1024: przed użyciem pierwszego numeru bloku zapisuje i zatwierdza w jawnym rekordzie rezerwacji (dwie kopie) górną granicę bloku. Po restarcie zaczyna od granicy ostatniej zatwierdzonej rezerwacji, więc numer użyty w przerwanym zapisie (także rekordu potem odrzuconego) nie wróci. Przepisanie rekordu pod nowy klucz używa nowych numerów. 64 b numeru nie wyczerpie się w życiu stacji (przy zapisie co 0,65 s: ponad 10¹¹ lat). Wymagania wynikają z NIST SP 800-38D (jednorazowość nonce dla jednego klucza).
- Podmiana całej zawartości FRAM starszym obrazem (rollback) pozostaje ryzykiem szczątkowym ([rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)).

**SQLite** laptopa i aplikacji stanowiska: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone. Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią oznacza konflikt; dane nie są nadpisywane.

Przed zapisem funkcja zwrotna odbioru sprawdza `signature_validated`, zaufanie do nadawcy i limit rozmiaru. Stacja przyjmuje RECEIVED, STATUS, REPLY i BULLETIN wyłącznie od aktywnej tożsamości przypiętego odbiorcy ([klucz odbiorcy](#model-zaufania-i-kluczy)); inne odrzuca i liczy w diagnostyce. Nazwa wyświetlana i pole JSON nie nadają uprawnień. Na stanowisku REQUEST i TEST nieznanej stacji trafiają do kwarantanny i czekają na decyzję dyżurnego ([model zaufania](#model-zaufania-i-kluczy)). Kwarantanna jest zapisem trwałym, ale nie przyjęciem: RECEIVED wysyła się dopiero po zatwierdzeniu wiadomości przez dyżurnego. Zgłoszenie z kwarantanny nie jest traktowane jak zgłoszenie ze zweryfikowanego schronienia. Kartę odbiorcy zapisuje się w stacji tylko w trybie przygotowania, po przytrzymaniu przycisku konfiguracji na stacji; nigdy przez radio.

Proces kolejki wysyła RECEIVED i każde inne potwierdzenie aplikacyjne dopiero po COMMIT. Brak miejsca, uszkodzenie bazy lub dziennika FRAM albo błąd fsync blokują komunikat `zapisane_w_stacji`; stacja pokazuje wtedy `blad_pamieci`. Stacja i aplikacja nie tworzą automatycznie pustego magazynu w miejsce uszkodzonego. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. [Trwałość SQLite](https://sqlite.org/atomiccommit.html).

### Wysyłanie

Stany intencji i wpisu rejestru opisuje [cykl życia zgłoszenia](#cykl-życia-zgłoszenia). Intencja jest aktywna od przekazania do LXMF do stanu DELIVERED albo FAILED. W jednej aktywnej wysyłce LXMF stacji wykonuje najwyżej 2 próby dostarczenia, z odstępem nie krótszym niż [odstęp ponowienia](radio.md#ponowienia-i-limity-prób) dla liczby skoków. Po DELIVERED stacja czeka na RECEIVED 10 min, potem ponawia intencję co 30–60 min z losowym przesunięciem ±20%. Po FAILED ponawia po 1, 2, 5 i 15 min, każdy odstęp ±20%; po 6 h co 60 min. Nigdy nie ponawia równolegle z wciąż aktywną wysyłką tej samej intencji. Intencja w oczekiwaniu nie blokuje następnych; stacja przekazuje do LXMF najwyżej 2 własne wiadomości jednocześnie. STATUS lub REPLY od aktywnej tożsamości odbiorcy także kończy ponawianie danej pary (id, revision). Nienadana starsza rewizja jest oznaczana jako zastąpiona. Nieodesłany STATUS dla tego samego (odbiorca, id, revision) zastępuje się nowszym. Intencja nie jest usuwana automatycznie; po czasie zależnym od pilności ekran podaje alarm braku potwierdzenia ([ekran](#ekran-i-przyciski-stacji)). Nowa wiadomość LXMF może mieć inny skrót (hash); id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji u odbiorcy. Kolejność w kolejce stacji: RECEIVED i STATUS, potem REPLY i BULLETIN, potem REQUEST z `urgency` = 2, potem pozostałe REQUEST według czasu COMMIT, na końcu TEST. Nie oznacza to priorytetu w całej sieci. Kolejka interfejsu radiowego ma własne priorytety: potwierdzenia pakietów i zapytania o trasę, potem dane, na końcu ogłoszenia ([dostęp do kanału](radio.md#dostęp-do-kanału)).

### Czas

Stacja utrzymuje w FRAM licznik czasu pracy i używa go jako monotonicznego zegara Reticulum i LXMF między restartami. Licznik zapisuje się co 60 s. Przy starcie stacja przyjmuje wartość zapisaną + 60 s i od razu ją zapisuje, zanim nada pierwszą ramkę albo utworzy rekord. Dzięki temu czas po restarcie nigdy nie jest mniejszy od czasu użytego przed restartem, także gdy zanik nastąpił tuż przed zaplanowanym zapisem; ceną jest przesunięcie licznika do przodu o ≤60 s na każdy restart. Znaczniki czasu w rekordach, ogłoszeniach i zdarzeniach USB pochodzą z tego licznika. Wszystkie czasy na ekranie liczy się od tego licznika, nie od zegara kalendarzowego; zegar kalendarzowy przekazany przez laptop nie jest zaufany. Licznik nie rośnie, gdy stacja jest wyłączona. Bez RTC stacja po włączeniu nie wie, jak długo była wyłączona: do pierwszej nowej wiadomości od odbiorcy pokazuje `ostatni_kontakt_ponad`, czyli dolne oszacowanie (czas pracy przed wyłączeniem i po włączeniu), zamiast `ostatni_kontakt`. Alarmy liczą czas pracy, więc wyłączenie stacji je wstrzymuje. Licznik należy do tożsamości stacji i przechodzi z nią w PRZENIEŚ STACJĘ; stacja docelowa przyjmuje większą z dwóch wartości + 60 s, aby jej ogłoszenia nie wyglądały na starsze od wcześniejszych (do potwierdzenia w T3). Odbiorca ignoruje znacznik czasu LXMF i używa czasu lokalnego odbioru.

Limity magazynów stacji i zasady zwalniania miejsca są w tabeli [pamięci FRAM](#pamięć-fram). Pełny rejestr blokuje nowe zgłoszenie komunikatem `kolejka_pelna`; nigdy nie daje pozornego `zapisane_w_stacji`. Aplikacja laptopa odmawia zapisu, gdy wolne miejsce spada poniżej 100 MB, a jej dziennik ma rotację do 10 MB.

**Tożsamość zapasowa a odbiorca zastępczy.** Wydanie 0.5 rozróżnia dwie sytuacje. **Tożsamość zapasowa** należy do tego samego stanowiska odbiorczego: odpowiedzialność i dyżurni się nie zmieniają, zmienia się klucz i adres LXMF, np. po przejęciu komputera stanowiska. Stacja przełącza się na nią usługą KLUCZ ZAPASOWY ([klucz odbiorcy](#model-zaufania-i-kluczy)); to jest część wydania. **Odbiorca zastępczy** to inne stanowisko, które przejmuje odpowiedzialność za zgłoszenia, np. sąsiedniej gminy. Nie należy do wydania: stacja nie ma jego karty i nie przełącza się na niego, a zgłoszenia idą wtedy procedurą zastępczą z [koncepcji](../concept/02-scenariusze-i-organizacja.html#siec-i-odbiorca-zastepczy) (goniec, PMR446, służby na miejscu).

### Pojemności stosu

Tablica tras i tożsamości mieści co najmniej 256 wpisów z buforowanym ogłoszeniem, a lista skrótów pakietów co najmniej 4096 wpisów. Wpisów tożsamości głównej i zapasowej odbiorcy nigdy się nie usuwa; w konfiguracji węzła stanowiska chronione są wpisy celów osiągalnych przez interfejs USB. Poza nimi usuwa się wpis najdawniej używany. Przy pełnych 32-bajtowych skrótach, jak w implementacji referencyjnej, sama lista skrótów zajęłaby 128 KiB, a tablica tras z ogłoszeniami około 78 KiB, czyli razem około 81% RAM nRF52840. Dlatego:

- lista skrótów pakietów w RAM przechowuje pierwsze 8 B skrótu (4096 × 8 B = 32 KiB); prawdopodobieństwo fałszywego duplikatu przy 4096 wpisach jest rzędu 10⁻¹², a lista jest lokalna i nie zmienia protokołu;
- pełne wpisy tablicy tras, tożsamości i buforowane ogłoszenia leżą w FRAM; RAM zawiera indeks skrótów celu (256 × 16 B) i pamięć podręczną ostatnio używanych wpisów.

Zapas RAM ≥30% mierzy się przy tych pojemnościach i tym podziale, z LXMF, poleceniem `RNS` na płytce. W pilotażu (ESP32-S3, 512 KiB SRAM) pomiar należy do minimum pilotażu i blokuje T3 na stacjach pilotażowych (D14). Dla wydania na nRF52840 odtworzenie ruchu w programie węzła zbudowanym jako 32-bitowy daje 4,5% wolnej RAM w szczycie i 13,5% w stanie ustalonym, jeszcze bez LXMF ([pamięć RAM](../../firmware/README.md#pamięć-ram)): indeks magazynów portu zajmuje około 233 B na cel zamiast 16 B. Warunek nie jest tam spełniony. Przed decyzją o R02 po pilotażu D14 porównuje MCU z większą pamięcią (koszt, pobór wobec W23, dostępność, port microReticulum) z głęboką przebudową portu (zwarty indeks w microStore i Transport, odchudzenie obrazu o około 20 KB, utrzymanie łat).

### Pamięć FRAM

Każdy magazyn ma stałą liczbę gniazd o stałym rozmiarze; nie ma dziennika dopisywanego i kompaktowania. Zwolnienie gniazda to zapis rekordu „wolne” w zwykłej transakcji. Rekord gniazda mieści ≤256 B SA1, pola stanu, nagłówek, znacznik zatwierdzenia i znacznik AEAD 16 B, stąd gniazdo 512 B. Stacja ma jedną rolę; stan odbiorcy przechowuje komputer stanowiska (D19).

| Magazyn | Gniazda × rozmiar | Razem | Gdy brak miejsca |
|---|---|---|---|
| konfiguracja (`configure`) | 2 × 8 KiB (A/B) | 16 KiB | nowa konfiguracja zastępuje starszą kopię; zatwierdzenie przełącza wskaźnik |
| rejestr własnych zgłoszeń z intencjami ([cykl](#cykl-życia-zgłoszenia)) | 256 × 512 B | 128 KiB | zwalnia się najstarszy wpis zamknięty: z decyzją 6, anulowany bez RECEIVED albo TEST z RECEIVED. Gdy takiego nie ma, nowe zgłoszenie dostaje `kolejka_pelna`. Każdy wpis ma najwyżej jedną aktywną intencję, więc aktywnych intencji jest najwyżej 256 |
| skrzynka odbiorcza (REPLY, BULLETIN) | 128 × 512 B | 64 KiB | zwalnia się kolejno: najstarszy przeczytany BULLETIN, najstarszy przeczytany REPLY zgłoszenia zamkniętego, najstarszy nieprzeczytany BULLETIN (licznik w diagnostyce). REPLY zgłoszenia otwartego nie jest usuwany; gdy nie ma innego miejsca, wiadomość nie jest przyjęta (bez dowodu dostarczenia, więc odbiorca ponowi) |
| zbiór powtórzeń BULLETIN | 64 wpisy | 2 KiB | najstarszy wpis ([okno](#cykl-życia-zgłoszenia)) |
| pierścień zdarzeń USB ([protokół](protokol-usb.md#synchronizacja)) | 256 × 32 B | 8 KiB | nadpisuje najstarszy wpis niezależnie od `ack` |
| dziennik zdarzeń stacji (diagnostyka) | pierścień | 32 KiB | nadpisuje najstarszy wpis |
| licznik czasu, dług ciszy, rezerwacja nonce, ustawienia ekranu | dwie kopie | 4 KiB | stały rozmiar |
| rekord transakcji (pełne nowe bajty zmienianych gniazd) | 2 × 2 KiB | 4 KiB | stały rozmiar; największa transakcja ≤2 KiB łącznie z nagłówkiem |
| tablice stosu: trasy, tożsamości, ogłoszenia ([pojemności](#pojemności-stosu)) | ≥256 wpisów | ≤128 KiB | najdawniej używany wpis poza chronionymi |
| **suma** | | **≈386 KiB** | 75% z 512 KiB |

Każda stacja ma FRAM 4 Mbit (512 KiB) z zegarem SPI ≥8 MHz. Pamięć 2 Mbit nie mieści tabeli. Stacja w konfiguracji węzła stanowiska używa tylko konfiguracji, tablic stosu, dziennika i liczników. Wcześniejsza zajętość z [modelu](../../software/reference/wyniki.json) (≈205 KiB, 40%) zakładała zwarte rekordy i dziennik z kompaktowaniem; tabela powyżej ją zastępuje.

**Długa praca bez laptopa.** Żaden magazyn nie zależy od `ack` laptopa ani od odbiorcy: pierścienie nadpisują, a rejestr i skrzynka zwalniają gniazda wpisów zamkniętych. Stacja pracująca tygodniami bez laptopa nie wypełnia pamięci, dopóki zgłoszenia są zamykane; gdy odbiorca milczy, rejestr zapełnia się najwyżej 256 wpisami i wtedy zgłasza `kolejka_pelna`. Sprawdza to próba [długiej pracy bez laptopa](odbior.md#próby).

## API lokalnej strony (poziomy 2–3)

Sieć lokalna (LAN) widzi tylko adresy mieszkańca. Panel opiekuna nasłuchuje wyłącznie na 127.0.0.1, czyli jest dostępny tylko z ekranu laptopa. Panel dyżurnego należy do aplikacji stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#panel-dyżurnego)).

| Adres | Dostęp | Działanie |
|---|---|---|
| `GET /` | LAN | informacje, formularz, komunikaty |
| `POST /api/request` | LAN | walidacja i trwały zapis w kolejce opiekuna; 201 dopiero po COMMIT; nie wysyła radiem |
| `GET /api/request/<lid>` | LAN | treść i status tylko własnego zgłoszenia; `<lid>` to lokalny identyfikator strony (16 losowych bajtów, 32 cyfry szesnastkowe), nie krótki numer; wymaga tokenu w ciasteczku |
| `POST /api/request/<lid>` | LAN | zmiana własnego zgłoszenia; przed zatwierdzeniem zmienia wpis w kolejce opiekuna, po zatwierdzeniu wraca do kolejki opiekuna jako zmiana, z której opiekun tworzy nową rewizję |
| `GET /operator` | 127.0.0.1 | logowanie opiekuna |
| `GET /api/operator/queue` | 127.0.0.1 | kolejka lokalna; wymaga uwierzytelnienia |
| `POST /api/operator/approve` | 127.0.0.1 | sprawdzenie zgłoszenia mieszkańca, połączenie z powtarzalnym, ustalenie pilności i przekazanie do wysyłki |
| `POST /api/operator/test` | 127.0.0.1 | wysłanie TEST |
| `POST /api/operator/announce` | 127.0.0.1 | jednorazowe ogłoszenie adresu stacji |
| `POST /api/operator/configure` | 127.0.0.1 | adres schronienia (≤64 B), karta odbiorcy (tożsamość główna i zapasowa), gotowe frazy, liczba stacji w sieci (okno TEST startowego) i opcjonalna lista adresów obiektów (do 8, każdy ≤64 B) albo konfiguracja węzła stanowiska (`osp_node`, kod dostępu sieci); tylko w trybie przygotowania |
| `POST /api/operator/export` | 127.0.0.1 | operacja PRZENIEŚ STACJĘ; tylko w trybie przygotowania |
| `POST /api/operator/import` | 127.0.0.1 | przyjęcie paczki z operacji PRZENIEŚ STACJĘ na nowym laptopie lub stacji zapasowej; tylko w trybie przygotowania |
| `POST /api/operator/silence` | 127.0.0.1 | włączenie lub wyłączenie ciszy radiowej; wyjątek dla pojedynczego zgłoszenia tylko przy ciszy operacyjnej ustawionej z panelu; wymaga potwierdzenia przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/destroy` | 127.0.0.1 | operacja [ZNISZCZ DANE](#tryby-kryzysowe); podwójne potwierdzenie i potwierdzenie przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/close` | 127.0.0.1 | operacja [ZAMKNIJ ZDARZENIE](#model-zaufania-i-kluczy) |
| `GET /health` | 127.0.0.1 | stan strony, zapisu i połączenia ze stacją; czas od ostatniego kontaktu z odbiorcą, wiek najstarszej intencji, liczniki odrzutów i restartów stacji |

Token mieszkańca: 32 losowe bajty w ciasteczku `HttpOnly`, `SameSite=Strict`, nigdy w ścieżce URL; baza przechowuje tylko jego skrót. Mieszkańcy nie zakładają kont, nie wyrażają zgód i nie akceptują regulaminu. Strona nie wyświetla przed formularzem żadnych okien formalnych. Pod formularzem jest odnośnik „Informacja o danych” (obowiązek informacyjny, uzupełniony plakatem przy stacji; administrator i podstawa według D13) oraz informacja, że świadome wprowadzenie w błąd fałszywym zgłoszeniem może stanowić wykroczenie (art. 66 § 1 pkt 1 Kodeksu wykroczeń). Żądanie POST wymaga treści JSON, tokenu CSRF sesji i dozwolonego nagłówka Origin. Obowiązują limity rozmiaru i częstości żądań. Strona nie wczytuje zasobów z internetu i nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności w sieci lokalnej, dlatego strona zbiera minimum danych osobowych. Radio szyfruje osobno.

Hasła opiekuna, zastępców i dyżurnych generuje się podczas przygotowania, offline, jako co najmniej 5 słów z listy. Skróty Argon2id lub scrypt zapisuje się w pliku kont na pamięci USB zestawu (dla stanowiska odbiorczego: na nośniku stanowiska), z limitem 5 prób logowania na minutę; panel nowo uruchomionego laptopa wczytuje konta z tej pamięci i nie każe ustawiać haseł. Zastępcy mają te same uprawnienia co opiekun. Hasła leżą w numerowanych zaklejonych kopertach przy stacji (hasła dyżurnych i hasło stanowiska: przy stanowisku odbiorczym); koperty sprawdza się w przeglądzie kwartalnym, a po otwarciu koperty hasło się zmienia. Dziennik działań operatora jest tylko do dopisywania. Stacja poziomu 1 nie ma kont: obsługę ogranicza fizyczny dostęp.

Router zapewnia DHCP z rezerwacją stałego adresu IP laptopa i szyfrowanie WPA2 lub WPA3 z hasłem z plakatu; izolacja klientów jest włączona, a dzienniki DHCP wyłączone lub czyszczone przy [zamknięciu zdarzenia](#model-zaufania-i-kluczy). Laptop jest klientem sieci LAN i wyświetla adres `http://IP:8080` oraz kod QR. Główna sieć Wi-Fi musi przepuszczać ruch do LAN. Laptop ani stacja nie uruchamiają własnego serwera DHCP, DNS ani portalu przechwytującego (captive portal). Reguła zapory sieciowej pakietu START musi dopuszczać wyłącznie lokalny port strony na wybranym interfejsie; jej dodanie może wymagać uprawnień administratora. Dziennik aplikacji nie zapisuje treści zgłoszeń, tokenów, adresów IP ani MAC.

## Strona mieszkańca

Plakat przy stacji, przygotowany wcześniej, podaje nazwę sieci Wi-Fi, hasło i adres strony; dotyczy routera i adaptera sprawdzonych w przygotowaniu (rezerwację DHCP przypisuje się adresowi MAC adaptera USB–Ethernet z zestawu). Przy innym routerze obowiązuje kod QR na ekranie laptopa. Formularz pokazuje adres obiektu bez możliwości zmiany i pyta tylko „gdzie w budynku”; odpowiedź trafia na początek opisu i liczy się do jego limitu. Licznik pod opisem pokazuje `zostalo_znakow`, przeliczone z limitu bajtów. Panel opiekuna pokazuje przy opisie ostrzeżenie `nie_wpisuj_nazwisk`.

Po wysłaniu strona pokazuje lokalny numer zgłoszenia (cztery cyfry, unikalne w laptopie) i tekst `zapisz_numer`, a następnie stan: `czeka_na_opiekuna`, `opiekun_polaczyl` (gdy opiekun dołączył je do zgłoszenia SA1, także połączonego z innymi) albo `nie_wyslane`, potem etapy zgłoszenia SA1 z tabeli [Teksty ekranu](#teksty-ekranu), te same co na ekranie stacji. Dostęp do zgłoszenia daje tylko ciasteczko z tokenem; numer służy do rozmowy z opiekunem, który sprawdza stan w panelu. Po utracie ciasteczka (inna przeglądarka, tryb prywatny) mieszkańca obsługuje opiekun.

## Protokół USB laptop–stacja

Pełny kontrakt (wersja `"usb":2`: koperta wiadomości, schematy poleceń i odpowiedzi, przyczyny odmów, limity czasu, synchronizacja z epoką i migawką, transfery w częściach, PRZENIEŚ STACJĘ i przykładowe przebiegi) jest w [protokole USB](protokol-usb.md); zamyka go D17. Interfejs danych CDC (w ESP32-S3 przez kontroler USB-OTG i TinyUSB, nie przez USB-Serial-JTAG) przenosi wiersze JSON do 1024 B. Stacja w konfiguracji węzła stanowiska używa tego protokołu tylko w trybie przygotowania; poza nim interfejs danych przenosi pakiety Reticulum do komputera stanowiska ([radio](radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)).

Zasady wiążące resztę specyfikacji: źródłem prawdy o zgłoszeniach i wiadomościach jest stacja; stacja odpowiada `stored` dopiero po COMMIT w FRAM; idempotencja opiera się na kluczu (`id`, `revision`), nie na numerze wiersza; nic w stacji nie czeka na laptop, a luka w pierścieniu zdarzeń prowadzi do migawki stanu. Laptop przechowuje intencję przekazania w SQLite, aż dostanie `stored`. Odłączenie przewodu w dowolnym momencie nie gubi ani nie podwaja zgłoszenia.

## Model zaufania i kluczy

**Tożsamość i losowość.** Tożsamość stacji generuje sama stacja podczas przygotowania. Źródło losowości: w nRF52840 TRNG układu CC310; w ESP32-S3 `bootloader_random_enable()` (źródło SAR ADC) przy generowaniu kluczy i zasilaniu DRBG, z wyłączonym Wi-Fi i Bluetooth. Klucze i `id` tworzone w stacji pochodzą z CSPRNG z ziarnem ≥256 b; `id` tworzone w laptopie pochodzą z CSPRNG systemu operacyjnego. Próba T2: testy zdrowia źródła entropii (NIST SP 800-90B) i brak powtórzeń `id` w 10⁶ próbek.

**Karty.** W trybie przygotowania stacja eksportuje przez USB kartę stacji: pełny klucz publiczny tożsamości (64 B), skrót adresu LXMF, nazwę `WICI-xxxxxx`, adres schronienia i odcisk do odczytu z ekranu. Aplikacja stanowiska importuje kartę (plik lub QR) po porównaniu odcisku z ekranem stacji. Karta odbiorcy zawiera dwie tożsamości odbiorcy, główną i zapasową, każdą ze skrótem adresu i pełnym kluczem publicznym (64 B) ([klucz odbiorcy](#model-zaufania-i-kluczy)). Stacja rejestruje klucze z kart przy starcie, więc weryfikacja podpisu nie zależy od odebrania ogłoszenia.

**Zaufanie na stanowisku.** Listę zaufanych stacji z ich kartami przechowuje baza aplikacji stanowiska na komputerze stanowiska; na jej podstawie aplikacja decyduje, czy wiadomość jest przyjmowana jako zaufana, czy trafia do kwarantanny ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Zatwierdzenie w kwarantannie dotyczy pojedynczej wiadomości i nie dodaje nadawcy do zaufanych. Dodanie stacji do listy wymaga karty stacji i zgody dwóch zalogowanych dyżurnych; usunięcie wykonuje jeden. Wiadomość z nieznanym kluczem (SOURCE_UNKNOWN) stanowisko zapisuje jako „do weryfikacji”, wysyła zapytanie o trasę i sprawdza podpis po nadejściu ogłoszenia. Kwarantanna w SQLite mieści najwyżej 4 wiadomości na nadawcę i 256 łącznie; nadmiar jest odrzucany. Wiadomości stacji usuniętej z listy trafiają do kwarantanny tak samo, ale są liczone (z powtórzeniami), a panel pokazuje przy nich alarm „możliwe przejęcie stacji”.

**Klucz odbiorcy.** Karta odbiorcy zawiera dwie tożsamości: główną i zapasową, każdą z własnym kluczem publicznym i własnym adresem LXMF. Stacja przyjmuje wiadomości wyłącznie od tożsamości aktywnej i tylko do niej wysyła zgłoszenia; po przygotowaniu aktywna jest główna. Obie należą do tego samego stanowiska odbiorczego ([tożsamość zapasowa a odbiorca zastępczy](#trwałość-i-potwierdzenia)). Przełączenie na zapasową jest czynnością lokalną: opiekun wybiera STAN → USŁUGI → KLUCZ ZAPASOWY, potwierdza `klucz_zapasowy` sekwencją GÓRA, DÓŁ, GÓRA, OK. Panel i USB nie mają tego polecenia. Polecenie przełączenia przychodzi wyłącznie słownie lub przez gońca, nigdy radiem, bo przejęte stanowisko mogłoby je nadać. Przełączenie jest nieodwracalne poza trybem przygotowania. Po nim stacja odrzuca wiadomości od tożsamości głównej, a niepotwierdzone intencje wysyła ponownie, z tym samym `id` i `revision`, do adresu zapasowego. Tożsamość zapasową generuje się offline podczas przygotowania stanowiska. Jej klucz prywatny trafia do zaplombowanej koperty u organizatora sieci jako paczka zaszyfrowana (AEAD) kluczem wyprowadzonym Argon2id z hasła tożsamości zapasowej (co najmniej 6 słów z listy); hasło leży w drugiej kopercie, przechowywanej w innym miejscu niż paczka i niż stanowisko. Po utracie lub przejęciu komputera lub nośnika z tożsamością główną aplikacja stanowiska na przygotowanym komputerze wczytuje paczkę z hasłem; ponieważ adres się zmienia, ogłasza go od razu po wczytaniu. Utrata którejkolwiek koperty wymaga nowej tożsamości zapasowej i nowych kart odbiorcy we wszystkich stacjach (D08). Nowego klucza stacja nigdy nie przyjmuje przez radio. Rotację klucza odbiorcy i nową kopertę zapasową określa plan kart (D08). Pakiety okazjonalne nie mają poufności przyszłej: przejęcie klucza odbiorcy ujawnia wcześniej nagrane zgłoszenia ([rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)).

**Powtórzenia.** Odbiorca zachowuje trwale klucze odbioru (nadawca, id, revision, skrót treści) także po usunięciu treści. Stacja przechowuje w rejestrze zgłoszeń najwyższy `event` STATUS i REPLY dla każdego `id`, a dla BULLETIN zbiór ostatnich komunikatów z oknem czasu ([cykl życia](#cykl-życia-zgłoszenia)); nagrana wcześniej wiadomość odbiorcy nie cofa więc stanu ani nie wraca do skrzynki. Po zwolnieniu wpisu rejestru zamkniętego zgłoszenia wiadomości dla jego `id` są pomijane jako dotyczące `id` spoza rejestru. Tak określona ochrona spełnia wymaganie powtórzeń z D01; format SA1 0.5 się nie zmienia.

**Polecenia USB.** `configure`, `export`, `import` i aktualizacja oprogramowania działają wyłącznie w trybie przygotowania, włączanym przyciskiem pod plombowaną pokrywą serwisową (dostęp tylko do tego przycisku, bez dostępu do płytki; zerwanie plomby zapisuje się w ewidencji, a po przeglądzie zakłada się nową). Paczka eksportu jest szyfrowana kluczem publicznym stacji docelowej (X25519 + HKDF-SHA-256 + ChaCha20-Poly1305) i nigdy nie zawiera jawnego klucza prywatnego. Stacja źródłowa przestaje nadawać po eksporcie, a tożsamość usuwa dopiero po potwierdzeniu importu przez stację docelową; stany i odtwarzanie po przerwaniu są w [protokole USB](protokol-usb.md#przeniesienie-stacji). `destroy`, `close` i `silence` przez USB wymagają potwierdzenia przyciskiem na stacji w ciągu 30 s. Każde polecenie USB trafia do dziennika zdarzeń stacji.

**Dane osobowe.** Kolejka stacji może zawierać dane o zdrowiu: pole `text` z panelu oraz kategorie 0–1 przy małej liczbie osób. Panel ostrzega `nie_wpisuj_nazwisk`.

| Miejsce | Zapisuje | Nie zapisuje |
|---|---|---|
| stacja (każdy poziom) | tylko wiadomości SA1, klucze i dziennik zdarzeń | IP, MAC, telefonu, nazwiska |
| laptop schronienia (poziomy 2–3) | SA1 + skrót tokenu + czas | IP, MAC, telefonu, nazwiska |
| komputer stanowiska | SA1 + adres nadawcy + czas odbioru + klucze odbioru + dziennik działań dyżurnych | IP, MAC, telefonu, nazwiska |

**ZAMKNIJ ZDARZENIE.** Po zakończeniu zdarzenia operacja eksportuje zaszyfrowane archiwum dla administratora danych (klucz publiczny z D13), a potem usuwa zgłoszenia, tokeny, eksporty i dzienniki z danymi na laptopie, kolejkę i skrzynkę na stacji oraz treść wiadomości na stanowisku. Tożsamości i klucze odbioru (ze skrótem SHA-256 treści i wysłanym potwierdzeniem) zostają. Próba w T2 i T8.

## Ekran i przyciski stacji

Ekran graficzny ma najwyżej 5 wierszy po ≤20 znaków, wysoki kontrast i wysokość wersalików ≥3,5 mm. W stacji pilotażowej daje to panel z pamięcią 2,7" (LS027B7DH01, 400 × 240, szerokość 58,8 mm) z krojem o stałej szerokości w komórce 20 × 40 px; wcześniejszy cel 4 mm wymagałby ≤17 znaków w wierszu (F80). Czytelność 3,5 mm w świetle dziennym, przy świetle latarki i z odległości 50 cm sprawdza T8 w pilotażu; większy panel albo krój skondensowany dla wydania rozstrzyga D15. Pełne teksty stanu nie mieszczą się razem na 5 wierszach, więc ekran główny używa krótkich form z tabeli, po jednym wierszu:

1. stan radia: `radio_wlaczone`, a gdy układ radiowy nie odpowiada albo nie przechodzi kontroli przy starcie, `radio_awaria` (stacja zapisuje dalej zgłoszenia, alarm jak przy `brak_potwierdzenia`);
2. kontakt z odbiorcą: `kontakt_krotki` albo `kontakt_ponad_krotki` (brak świeżego kontaktu nie jest awarią);
3. zasilanie: `zasilanie_aa` albo `zasilanie_12v`;
4. najstarsze niewysłane zgłoszenie: `kolejka_krotki` (pusty wiersz przy pustej kolejce);
5. nowe wiadomości: `nowe_krotki`.

W ciszy radiowej wiersze 1–3 zajmuje pełny tekst `cisza`, a wiersze 4–5 pokazują zasilanie i kolejkę. Aktywny alarm zajmuje cały ekran do potwierdzenia. Pełne teksty (`ostatni_kontakt`, `ogniwa_czas`) pokazuje STAN. `[czas]` podaje się w minutach do 99 MIN, potem w godzinach (H), od 48 H w dobach (D, do 99 D), aby krótkie formy mieściły się w 20 znakach. Do oceny: STAN pokazuje odchyłkę częstotliwości oszacowaną z odebranych ramek. Osoby niewidome zgłaszają przez opiekuna.

Podświetlenie ([elektronika](elektronika.md)): pierwsze naciśnięcie przy zgaszonym ekranie tylko zapala światło; każde naciśnięcie przedłuża je o 30 s; przy otwartej wiadomości świeci ≥60 s. Dioda „NOWA WIADOMOŚĆ / ALARM” miga krótkimi błyskami (w modelu energii około 1% czasu, [elektronika](elektronika.md)) do odczytu nowej wiadomości, do usunięcia przyczyny alarmu i przez cały czas ciszy radiowej.

**Alarmy.** Brak potwierdzenia od odbiorcy uruchamia alarm `brak_potwierdzenia` po czasie zależnym od pilności: 2 → 15 min, 1 → 1 h, 0 → 6 h. TEST ma osobny próg 30 min ([TEST](#wiadomości-sa1)). Teksty alarmów każą wysłać gońca tylko wtedy, gdy droga jest bezpieczna; ocenę drogi i postępowanie, gdy wyjście jest niemożliwe, opisuje [instrukcja opiekuna](instrukcja.md#goniec). Dla pilności 2 drugi alarm `brak_odczytu` następuje, gdy po „odbiorca zapisał” w ciągu 30 min nie przyjdzie „odbiorca przeczytał” (brzmienie do potwierdzenia w T1). Sygnał dźwiękowy alarmu powtarza się do potwierdzenia przyciskiem OK na ekranie alarmu. Potwierdzenie gasi dźwięk tego alarmu; ekran alarmu wraca po każdym wybudzeniu ekranu, a dioda i wpis w PRZEKAZANIE ZMIANY pozostają do usunięcia przyczyny. Dźwięk wraca przy nowym zdarzeniu (alarm innego zgłoszenia, drugi alarm pilności 2), a `wymien_ogniwa` przypomina dźwiękiem co 15 min. Cisza radiowa nie daje sygnału dźwiękowego, także przy włączeniu: włącza ją opiekun przełącznikiem CISZA, a stan pokazują stały tekst i dioda. Cisza może trwać dni, a dźwięk w schronieniu skłaniałby do wyjęcia ogniw. Alarmów krytycznych (brak potwierdzenia, brak odczytu, `radio_awaria`, `wymien_ogniwa`, cisza) nie da się wyłączyć ani ukryć; wyciszenie zwykłego sygnału nowej wiadomości jest widoczne stale jako `dzwiek_wyciszony`.

**Start.** Radio i przekazywanie ruchu uruchamiają się niezależnie od ekranu i przycisków; gotowość radiowa (≤60 s) nie czeka na żadną decyzję opiekuna, bo przekaźnik może pracować bez obsługi. Po włączeniu wyłącznikiem głównym pierwszy ekran to wybór języka; po restarcie przez watchdog albo po przełączeniu źródła stacja używa języka zapisanego w FRAM i wraca do ekranu, na którym była. Po wyborze języka stacja pokazuje `radio_wlaczone` i kontrolę adresu `adres_kontrola`; przy NIE lub braku adresu pokazuje `adres_brak`. Opcjonalnie stacja ma listę adresów obiektów (do 8) wczytaną przy przygotowaniu: po wyborze języka opiekun wybiera obiekt z listy przyciskami, potem stacja pokazuje kontrolę adresu tego obiektu; NIE wraca do listy, a WSTECZ na liście (żaden obiekt) daje `adres_brak`. Wybór przetrwa restart i wyłączenie. Potem stacja proponuje TEST startowy; OK go planuje (`test_zaplanowany`, `test_wyslany`). Bez reakcji opiekuna TEST nie wychodzi. W trybie przygotowania ekran stale pokazuje `tryb_przygotowania`.

**Węzeł stanowiska.** Stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)) po wyborze języka pokazuje na ekranie głównym `radio_wlaczone`, `komputer_osp` albo `komputer_brak` oraz zasilanie; nie kontroluje adresu i nie proponuje TEST. Menu ma tylko STAN i JĘZYK. STAN pokazuje radio, liczniki (także pakiety USB w obu kierunkach), energię, wersję i nazwę `WICI-xxxxxx`; USŁUGI mają tylko WYCISZ DŹWIĘK i ZNISZCZ DANE. PRZEKAZANIE ZMIANY, OGŁOŚ ADRES i KLUCZ ZAPASOWY nie występują, bo stacja nie ma zgłoszeń ani adresu LXMF. CISZA działa jak w każdej stacji.

Przyciski: GÓRA, DÓŁ, OK, WSTECZ, duże i wyczuwalne, obsługiwane w rękawicach. Osobny przełącznik CISZA ma osłonę przed przypadkowym przełączeniem. Przycisk konfiguracji (tryb przygotowania) jest pod plombowaną pokrywą serwisową; pola programowania pozostają wewnątrz obudowy.

| Menu | Działanie |
|---|---|
| ZGŁOSZENIE | kreator: kategoria 0–9 z piktogramem → liczba osób → pilność (bez wartości domyślnej) → gotowa fraza lub brak (kategoria 9: fraza obowiązkowa) → podsumowanie; po wysłaniu ekran pokazuje etap i krótki numer |
| WIADOMOŚCI | etapy własnych zgłoszeń, odpowiedzi (REPLY) i komunikaty (BULLETIN) ze źródłem i czasem od odbioru; przy własnym zgłoszeniu: ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA, ANULUJ WYSYŁKĘ |
| TEST | wysłanie TEST i wynik; WSTRZYMAJ i WZNÓW na prośbę odbiorcy z komunikatu |
| STAN | radio, liczniki, energia (`ogniwa_napiecie`, `ogniwa_czas`, napięcie 12 V), `ostatni_kontakt`, wersja, nazwa `WICI-xxxxxx`; PRZEKAZANIE ZMIANY; USŁUGI: OGŁOŚ ADRES, WYCISZ DŹWIĘK (po wyciszeniu WŁĄCZ DŹWIĘK), KLUCZ ZAPASOWY, ZNISZCZ DANE |
| JĘZYK/МОВА/LANGUAGE | polski, ukraiński, angielski; etykieta zawsze w trzech językach, bez spacji wokół ukośników (19 znaków) |

**Kreator zgłoszenia.** WSTECZ cofa o jeden krok; przytrzymanie WSTECZ przez 2 s pokazuje `porzucic`. Liczba osób: lista „1, 2, 5, 10, 20, 50, 100, INNA”; INNA to wpis cyfra po cyfrze (setki, dziesiątki, jednostki), przytrzymanie przycisku przyspiesza zmianę, domyślnie stoi ostatnio użyta wartość. Pilność wybiera się z etykiet `pilnosc_2`, `pilnosc_1`, `pilnosc_0`; pilność 2 wymaga potwierdzenia `pilnosc_2_potw`. Podsumowanie pokazuje piktogram i kategorię, liczbę osób, pilność słownie, frazę, adres i `podsumowanie_klawisze`. Po 3 min bezczynności szkic zostaje zapisany, a stacja wraca do ekranu głównego. Po wysłaniu ekran pokazuje kolejne etapy z tabeli.

**Własne zgłoszenie.** ZMIEŃ LICZBĘ OSÓB i ZMIEŃ PILNOŚĆ tworzą nową rewizję, jak na stronie. POTRZEBA USTAŁA tworzy nową rewizję z frazą „potrzeba ustała”. ANULUJ WYSYŁKĘ jest dostępne tylko przed „odbiorca zapisał”: oznacza intencję jako anulowaną i zapisuje to w dzienniku zdarzeń. Jeżeli zgłoszenie dotarło do odbiorcy przed anulowaniem albo po nim dotrze z wcześniejszej próby, odbiorca o anulowaniu nie wie; dlatego po „odbiorca zapisał” zamiast ANULUJ jest tylko POTRZEBA USTAŁA. Swobodny opis wpisuje się tylko w panelu laptopa.

**PRZEKAZANIE ZMIANY** (STAN) pokazuje otwarte i niepotwierdzone zgłoszenia, nieprzeczytane wiadomości, energię, ciszę i wyciszenie dźwięku.

**KLUCZ ZAPASOWY** (STAN → USŁUGI) przełącza stację na tożsamość zapasową tego samego odbiorcy z karty, tylko na polecenie przekazane słownie lub przez gońca ([klucz odbiorcy](#model-zaufania-i-kluczy)); pokazuje `klucz_zapasowy` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Nie służy do przejścia do innego stanowiska (odbiorcy zastępczego).

**ZNISZCZ DANE** (STAN → USŁUGI) pokazuje `zniszcz_ostrzezenie` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Nigdy nie uruchamia się na podstawie wiadomości radiowej; polecenie odbiorcy przychodzi tylko słownie lub przez gońca. T8: brak przypadkowego uruchomienia w 10 próbach w rękawicach.

### Teksty ekranu

Jedyna kanoniczna lista tekstów stacji i strony mieszkańca; inne dokumenty cytują teksty tylko z niej, a T1 sprawdza zgodność. Ekran łamie tekst na wiersze ≤20 znaków; tekst dłuższy niż 5 wierszy dzieli się na kolejne ekrany (do sprawdzenia w T1). [x], [n], [m], [mm], [czas] i [xxxx] to wartości wstawiane przez stację. W tekście ciągłym dokumentów dopuszczalne są małe litery w cudzysłowie. Słowo „OKOŁO” pisze się w całości, bo „OK.” myliłoby się z przyciskiem. Kolumny UK i EN są tłumaczeniem roboczym: przed T1 sprawdza je osoba, dla której ukraiński lub angielski jest językiem ojczystym, a T8 z osobą ukraińskojęzyczną; zmiana brzmienia nie może wydłużyć krótkich form ponad 20 znaków. Jednostki `[czas]`: MIN / H / D po polsku i angielsku, ХВ / ГОД / Д po ukraińsku. Napięcie w wersji EN ma kropkę dziesiętną. „ПРИБЛИЗНО” i „ABOUT” pisze się w całości jak „OKOŁO”. Karta obsługi ([karta](karta.md)) cytuje teksty z tej tabeli.

| ID | Ekran PL | Ekran UK | Ekran EN | Znaczenie |
|---|---|---|---|---|
| `radio_wlaczone` | RADIO WŁĄCZONE | РАДІО УВІМКНЕНО | RADIO ON | stacja odbiera i może nadawać |
| `radio_awaria` | RADIO: AWARIA | РАДІО: НЕСПРАВНЕ | RADIO: FAULT | wiersz 1 ekranu głównego, gdy układ radiowy nie działa; zgłoszenia są zapisywane, ale nie wychodzą |
| `jezyk_pl` | POLSKI | POLSKI | POLSKI | ekran wyboru języka, zawsze w tym języku |
| `jezyk_uk` | УКРАЇНСЬКА | УКРАЇНСЬКА | УКРАЇНСЬКА | ekran wyboru języka, zawsze w tym języku |
| `jezyk_en` | ENGLISH | ENGLISH | ENGLISH | ekran wyboru języka, zawsze w tym języku |
| `cisza` | CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC | РАДІОТИША – СТАНЦІЯ НЕ ПЕРЕДАЄ. ТЕРМІНОВО: ПОСИЛЬНИЙ | RADIO SILENCE – NOT TRANSMITTING. URGENT: RUNNER | wiersze 1–3 ekranu głównego w ciszy radiowej |
| `ostatni_kontakt` | OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU | ОСТАННІЙ ЗВ'ЯЗОК З ОДЕРЖУВАЧЕМ: [czas] ТОМУ | LAST CONTACT WITH RECIPIENT: [czas] AGO | STAN: czas od ostatniej uwierzytelnionej wiadomości od aktywnej tożsamości odbiorcy (RECEIVED, STATUS, REPLY lub BULLETIN); brak świeżego kontaktu nie jest awarią |
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
| `stan_3` | POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU) | ДОПОМОГУ НАПРАВЛЕНО (РІШЕННЯ, НЕ ЧАС ПРИБУТТЯ) | HELP DISPATCHED (DECISION, NOT ARRIVAL TIME) | state 3: skierowanie sił potwierdzone przez podmiot, który nimi dysponuje |
| `stan_4` | PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT) | ПЕРЕДАНО ДАЛІ (ПОЖЕЖНИКИ / ШВИДКА / ПОВІТ) | FORWARDED (FIRE SERVICE / AMBULANCE / COUNTY) | state 4: przekazane, bez potwierdzenia skierowania pomocy |
| `stan_5` | ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ | ОДЕРЖУВАЧ ЗАРАЗ НЕ МОЖЕ ДОПОМОГТИ – ЧИТАЙТЕ ВІДПОВІДЬ | RECIPIENT CANNOT HELP NOW – READ THE REPLY | state 5, zawsze z REPLY |
| `stan_6` | ZAMKNIĘTE | ЗАКРИТО | CLOSED | state 6 |
| `brak_potwierdzenia` | BRAK POTWIERDZENIA OD [n] MIN – GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA | НЕМАЄ ПІДТВЕРДЖЕННЯ [n] ХВ – ПОСИЛЬНИЙ З ФОРМОЮ, ЯКЩО ДОРОГА БЕЗПЕЧНА | NO CONFIRMATION FOR [n] MIN – RUNNER WITH THE FORM IF THE ROUTE IS SAFE | alarm krytyczny; 15 min / 1 h / 6 h według pilności, 30 min dla TEST |
| `brak_odczytu` | ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA | ОДЕРЖУВАЧ НЕ ПРОЧИТАВ УЖЕ 30 ХВ – ПОСИЛЬНИЙ З ФОРМОЮ, ЯКЩО ДОРОГА БЕЗПЕЧНА | NOT READ BY RECIPIENT FOR 30 MIN – RUNNER WITH THE FORM IF THE ROUTE IS SAFE | alarm krytyczny, tylko pilność 2; brzmienie do potwierdzenia w T1 |
| `dzwiek_wyciszony` | DŹWIĘK WYCISZONY | ЗВУК ВИМКНЕНО | SOUND MUTED | zwykły sygnał wyciszony; ekran główny, wiersz 4 przy pustej kolejce, oraz STAN i PRZEKAZANIE ZMIANY |
| `adres_ogloszony` | ADRES ZOSTANIE OGŁOSZONY | АДРЕСУ БУДЕ ОГОЛОШЕНО | ADDRESS WILL BE ANNOUNCED | po OGŁOŚ ADRES (STAN → USŁUGI); w ciszy radiowej ogłoszenie wychodzi po jej odwołaniu |
| `adres_nie_ogloszony` | STACJA NIE NADAJE – ADRES NIE OGŁOSZONY. FORMULARZ; GONIEC, JEŚLI DROGA BEZPIECZNA | СТАНЦІЯ НЕ ПЕРЕДАЄ – АДРЕСУ НЕ ОГОЛОШЕНО. ФОРМА; ПОСИЛЬНИЙ, ЯКЩО ДОРОГА БЕЗПЕЧНА | STATION NOT TRANSMITTING – ADDRESS NOT ANNOUNCED. FORM; RUNNER IF THE ROUTE IS SAFE | po OGŁOŚ ADRES, gdy stos sieciowy stacji nie działa; żadne zgłoszenie nie wyjdzie radiem |
| `test_zaplanowany` | TEST ZAPLANOWANY ZA OKOŁO [mm] MIN – NIE WYŁĄCZAJ. WSTECZ = ANULUJ | ТЕСТ ЗАПЛАНОВАНО ПРИБЛИЗНО ЧЕРЕЗ [mm] ХВ – НЕ ВИМИКАЙТЕ. НАЗАД = СКАСУВАТИ | TEST SCHEDULED IN ABOUT [mm] MIN – DO NOT SWITCH OFF. BACK = CANCEL | TEST startowy w losowym oknie |
| `test_wyslany` | TEST WYSŁANY – CZEKA NA ODBIORCĘ | ТЕСТ ВІДПРАВЛЕНО – ЧЕКАЄ НА ОДЕРЖУВАЧА | TEST SENT – WAITING FOR RECIPIENT | TEST nadany, brak RECEIVED |
| `test_wstrzymany` | TEST WSTRZYMANY PRZEZ ODBIORCĘ | ТЕСТ ПРИЗУПИНЕНО НА ПРОХАННЯ ОДЕРЖУВАЧА | TEST PAUSED AT RECIPIENT'S REQUEST | opiekun wybrał TEST → WSTRZYMAJ po komunikacie odbiorcy |
| `adres_kontrola` | ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE | АДРЕСА: [x] – ЦЕ ЦЕ МІСЦЕ? OK = ТАК / НАЗАД = НІ | ADDRESS: [x] – IS THIS THE PLACE? OK = YES / BACK = NO | kontrola adresu przy starcie |
| `adres_brak` | STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO | СТАНЦІЯ НЕ МАЄ ВАШОЇ АДРЕСИ – ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | STATION DOES NOT HAVE YOUR ADDRESS – USE THE PAPER FORM | odpowiedź NIE albo brak adresu |
| `porzucic` | PORZUCIĆ ZGŁOSZENIE? OK = TAK | СКАСУВАТИ ЗАЯВКУ? OK = ТАК | DISCARD REQUEST? OK = YES | przytrzymanie WSTECZ 2 s w kreatorze |
| `pilnosc_2` | ZAGROŻENIE ŻYCIA | ЗАГРОЗА ЖИТТЮ | DANGER TO LIFE | urgency 2 |
| `pilnosc_1` | PILNE – KILKA GODZIN | ТЕРМІНОВО – КІЛЬКА ГОДИН | URGENT – A FEW HOURS | urgency 1 |
| `pilnosc_0` | W CIĄGU DOBY | ПРОТЯГОМ ДОБИ | WITHIN A DAY | urgency 0 |
| `pilnosc_2_potw` | ZAGROŻENIE ŻYCIA: 1) UDZIEL PIERWSZEJ POMOCY 2) DZIAŁA TELEFON? 112 3) BEZPIECZNA DROGA? GONIEC. OK = WYŚLIJ TEŻ RADIEM | ЗАГРОЗА ЖИТТЮ: 1) НАДАЙТЕ ПЕРШУ ДОПОМОГУ 2) ПРАЦЮЄ ТЕЛЕФОН? 112 3) БЕЗПЕЧНА ДОРОГА? ПОСИЛЬНИЙ. OK = НАДІСЛАТИ ТАКОЖ ПО РАДІО | DANGER TO LIFE: 1) GIVE FIRST AID 2) PHONE WORKS? 112 3) SAFE ROUTE? RUNNER. OK = ALSO SEND BY RADIO | potwierdzenie pilności 2 |
| `podsumowanie_klawisze` | OK = WYŚLIJ, WSTECZ = POPRAW | OK = НАДІСЛАТИ, НАЗАД = ВИПРАВИТИ | OK = SEND, BACK = EDIT | ostatnie wiersze podsumowania |
| `kolejka_pelna` | KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO | ЧЕРГА ПОВНА – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | QUEUE FULL – REQUEST NOT SAVED. USE THE PAPER FORM | 128 intencji w kolejce |
| `blad_pamieci` | BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ; GONIEC, JEŚLI DROGA BEZPIECZNA | ПОМИЛКА ПАМ'ЯТІ СТАНЦІЇ – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ФОРМА; ПОСИЛЬНИЙ, ЯКЩО ДОРОГА БЕЗПЕЧНА | STATION MEMORY ERROR – REQUEST NOT SAVED. FORM; RUNNER IF THE ROUTE IS SAFE | błąd zapisu FRAM |
| `ogniwa_czas` | OGNIWA: OKOŁO [x] H PRACY | БАТАРЕЇ: ПРИБЛИЗНО [x] ГОД РОБОТИ | CELLS: ABOUT [x] H OF OPERATION | szacowany czas pracy |
| `wymien_ogniwa` | WYMIEŃ OGNIWA W CIĄGU 1 H | ЗАМІНІТЬ БАТАРЕЇ ПРОТЯГОМ 1 ГОД | REPLACE CELLS WITHIN 1 H | alarm krytyczny |
| `wylaczanie` | WYŁĄCZANIE – CZEKAJ, ZAPISUJĘ | ВИМКНЕННЯ – ЗАЧЕКАЙТЕ, ЗБЕРІГАЮ | SWITCHING OFF – WAIT, SAVING | kończenie zapisu przed wyłączeniem |
| `mozna_wyjac` | MOŻNA WYJĄĆ OGNIWA | МОЖНА ВИЙНЯТИ БАТАРЕЇ | CELLS CAN BE REMOVED | zapis zakończony |
| `odlaczone_12v` | 12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO I PRZYTRZYMAJ OK | 12 В ВІДКЛЮЧЕНО – ЗАНИЗЬКА НАПРУГА. ПІДКЛЮЧІТЬ ЗАРЯДЖЕНЕ ДЖЕРЕЛО І УТРИМУЙТЕ OK | 12 V DISCONNECTED – VOLTAGE TOO LOW. CONNECT A CHARGED SOURCE AND HOLD OK | zatrzask podnapięciowy 12 V; praca z ogniw |
| `tryb_przygotowania` | TRYB PRZYGOTOWANIA | РЕЖИМ ПІДГОТОВКИ | PREPARATION MODE | stały pasek w trybie przygotowania |
| `klucz_zapasowy` | PRZEŁĄCZYĆ NA KLUCZ ZAPASOWY ODBIORCY? TYLKO NA POLECENIE SŁOWNE LUB PRZEZ GOŃCA. NIEODWRACALNE | ПЕРЕМКНУТИ НА РЕЗЕРВНИЙ КЛЮЧ ОДЕРЖУВАЧА? ЛИШЕ ЗА УСНИМ НАКАЗОМ АБО ЧЕРЕЗ ПОСИЛЬНОГО. НЕЗВОРОТНО | SWITCH TO RECIPIENT'S BACKUP KEY? ONLY ON A SPOKEN ORDER OR ONE BROUGHT BY A RUNNER. IRREVERSIBLE | przed sekwencją GÓRA, DÓŁ, GÓRA, OK |
| `komputer_osp` | KOMPUTER [czas] TEMU | ПК [czas] ТОМУ | COMPUTER [czas] AGO | węzeł stanowiska, ekran główny, wiersz 2: czas od ostatniego pakietu od komputera stanowiska |
| `komputer_brak` | BRAK KOMPUTERA | НЕМАЄ ЗВ'ЯЗКУ З ПК | NO COMPUTER | węzeł stanowiska, ekran główny, wiersz 2: brak pakietu od komputera od startu stacji |
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
| OGŁOŚ ADRES | ОГОЛОСИТИ АДРЕСУ | ANNOUNCE ADDRESS |
| WYCISZ DŹWIĘK | ВИМКНУТИ ЗВУК | MUTE SOUND |
| WŁĄCZ DŹWIĘK | УВІМКНУТИ ЗВУК | UNMUTE SOUND |
| PRZEKAZANIE ZMIANY | ПЕРЕДАЧА ЗМІНИ | SHIFT HANDOVER |
| KLUCZ ZAPASOWY | РЕЗЕРВНИЙ КЛЮЧ | BACKUP KEY |
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

## Stanowisko odbiorcze

Stanowisko, aplikację stanowiska, panel dyżurnego, zestaw i postępowanie przy awarii opisuje rozdział [stanowisko odbiorcze](stanowisko-osp.md) (D19). Stanowisko składa się ze stacji w konfiguracji węzła stanowiska i obowiązkowego komputera z Reticulum i LXMF w Pythonie, tożsamością odbiorcy i bazą, z drugim komputerem w zapasie.

## Tryby kryzysowe

Formalności i uzgodnienia załatwia się przed użyciem. Żadna z poniższych funkcji nie blokuje przyjęcia zgłoszenia.

**Ogłoszenia adresu.** Stacja ogłasza swój adres LXMF przy starcie (z losowym opóźnieniem 0–120 s), na polecenie opiekuna (STAN → USŁUGI lub panel) i automatycznie, gdy intencja do odbiorcy nie dostała potwierdzenia transportowego po 2 próbach LXMF, najwyżej raz na 30 min. Aplikacja stanowiska ogłasza adres odbiorcy co 6 h ±20%, po starcie i po ponownym połączeniu ze stacją; stacja w konfiguracji węzła stanowiska nie ma adresu LXMF i go nie ogłasza. W ciszy radiowej nie ma ogłoszeń. Tablicę tras, znane tożsamości i buforowane ogłoszenia stacja zapisuje w FRAM i odtwarza po restarcie. Próba T3 i T5: zimny start po restarcie przekaźnika i przejście z trasy A–stanowisko na A–B–stanowisko bez ręcznego ogłoszenia. Nazwa wyświetlana ma postać `WICI-xxxxxx` (6 cyfr szesnastkowych skrótu tożsamości) i nie zawiera adresu ani nazwy miejsca. Emisje transportu Reticulum, np. zapytania o trasę, pozostają i liczy się je w próbie T3. Każda stacja z włączonym transportem retransmituje ogłoszenia innych stacji, więc przy zimnym starcie sieci N stacji kanał przenosi rzędu N² ogłoszeń, a każda stacja zużywa na nie część własnego długu ciszy. Limit ogłoszeń interfejsu radiowego (`announce_cap` Reticulum) wynosi 2%: czas nadawania ogłoszeń, własnych i przekazywanych, nie przekracza 2% czasu zegarowego interfejsu; ogłoszenia ponad limit czekają w kolejce ogłoszeń, a nowsze ogłoszenie tego samego celu zastępuje starsze. Limit liczy się osobno od budżetu kanału i długu ciszy ([dostęp do kanału](radio.md#dostęp-do-kanału)). Ogłoszenie trwa w LoRa SF7 0,359 s (w P1 0,513 s). Model bez strat daje dla 50 stacji 2500 nadań ogłoszeń: około 15 min czasu kanału w jednym obszarze kolizji (P1 21 min) i około 3,6 min długu ciszy w każdej stacji (50 × 0,359 s × 12). Przy limicie 2% 50 ogłoszeń przechodzi przez jeden skok w około 15 min (P1 21 min). Oszacowanie zimnego startu w [wynikach modelu](../../software/reference/wyniki.json) jest liczone dla P1 i dla LoRa daje zapas: razem z zapytaniami o trasę do odbiorcy i wymianą TEST zimny start 50 stacji zajmuje w P1 61–80% okna TEST startowego, 30 stacji 40–52% ([koncepcja, rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html#pojemnosc-sieci)). Sieć powyżej około 30 stacji w jednym obszarze kolizji uruchamia się etapami według planu sieci. Ostateczny limit ogłoszeń i podział na etapy ustala T5 z próbą skali.

**Cisza radiowa.** Polecenie ciszy radiowej wydaje wójt (od wprowadzenia stanu wojennego i w czasie wojny jako organ obrony cywilnej) na podstawie decyzji wojewody lub organów wojskowych albo wynika ono z nakazu wydanego w stanie nadzwyczajnym. Do schronień przekazuje je odbiorca komunikatem BULLETIN i gońcem; ciszę odwołuje ten sam organ. Opiekun włącza ją przełącznikiem CISZA na stacji albo w panelu. Przełącznik na stacji ma pierwszeństwo przed panelem. Interfejs radiowy nic nie nadaje, łącznie z ruchem przekazywanym i ogłoszeniami. Odbiór, zapis i kolejka działają dalej; ekran pokazuje stale `cisza`, a nowe zgłoszenie `zapisane_w_ciszy`. Wyłączenie ciszy jest wyłącznie ręczne, po odwołaniu przez organ. Wyjątek dla pojedynczego zgłoszenia ustawia się tylko z panelu (poziom 2) i tylko przy ciszy operacyjnej ustawionej z panelu, gdy polecenie wprost go dopuszcza; przełącznik CISZA na stacji wyklucza wyjątek. Wyjątek obejmuje całą wymianę tej jednej pary (id, revision): zapytanie o trasę, pakiet zgłoszenia, jego ponowienia i potwierdzenia pakietów dla przychodzących RECEIVED i STATUS; ogłoszeń nie obejmuje. Działa tylko wtedy, gdy cała droga do odbiorcy nadaje: przy ciszy w całej sieci przekaźniki też milczą, więc w praktyce tylko przy bezpośrednim połączeniu ze stanowiskiem odbiorczym, które samo nie jest w ciszy. Panel pokazuje to ograniczenie przed ustawieniem wyjątku. Wyjątek nie dotyczy zakazu używania urządzeń nadawczych w stanie wojennym lub wyjątkowym – wtedy podstawową procedurą jest goniec. Stacja zapisuje wyjątek w dzienniku zdarzeń, a opiekun w dzienniku papierowym. Fizyczną pewność ciszy daje wyłączenie zasilania stacji; wtedy stacja także nie odbiera.

**Szyfrowanie w spoczynku.** Na laptopie baza i eksporty są szyfrowane losowym kluczem danych, opakowanym kluczem = KDF(plik na pamięci USB zestawu, sekret w magazynie systemowym: DPAPI lub TPM w Windows, Keychain w macOS) i drugi raz kluczem z hasła odtworzenia (Argon2id); hasło odtworzenia pozwala przenieść bazę na inny komputer ([protokół USB](protokol-usb.md#przeniesienie-stacji)). Stacja przechowuje klucz tożsamości, kartę odbiorcy, adres, kolejkę i skrzynkę; kolejka może zawierać dane o zdrowiu ([dane osobowe](#model-zaufania-i-kluczy)). Oprogramowanie układowe włącza ochronę odczytu pamięci mikrokontrolera (np. APPROTECT w nRF52840, szyfrowanie pamięci flash w ESP32-S3). Wykonanie z nRF52840 wymaga rewizji 3 (kod wykonania Fx0) z APPROTECT według Nordic IN-141 i MDK ≥8.40.2; starsze rewizje mają znane obejście ochrony (IN-133). Rekordy w FRAM są szyfrowane AEAD kluczem (KEK) przechowywanym w chronionej pamięci MCU ([trwałość](#trwałość-i-potwierdzenia)), więc wylutowanie FRAM nie ujawnia kolejki ani karty odbiorcy; wymagane przed wydaniem, nie przed pilotażem. Start nie wymaga hasła. W systemach Windows i macOS baza leży na dysku laptopa, więc po odłączeniu pamięci USB jest nieczytelna. W Linuksie baza i plik klucza są na tej samej pamięci; odpowiednik magazynu systemowego do oceny. W każdym systemie zabranie działającego laptopa razem z pamięcią USB daje dostęp do danych. Szyfrowanie chroni więc tylko przed utratą samego laptopa; przed przejęciem całego stanowiska chroni wyłącznie ZNISZCZ DANE albo zniszczenie pamięci. Kandydatem jest SQLCipher Community Edition (licencja BSD-3-Clause, wymaga dołączenia informacji o prawach autorskich) z biblioteką Pythona [sqlcipher3](https://pypi.org/project/sqlcipher3/) (licencja zlib), która ma gotowe pakiety dla macOS (Intel i ARM), Windows x64 i Linuksa x86_64. To pierwsza zależność bazy spoza biblioteki standardowej. Wymaga przypięcia wersji, sprawdzenia, czy nie osłabia gwarancji trwałości z tej specyfikacji (tryb dziennika, fsync), oraz powtórzenia prób odcięcia zasilania. Ostateczny wybór, także wobec zaszyfrowanego wolumenu, zapada w D13. [SQLCipher](https://www.zetetic.net/sqlcipher/license/).

**ZNISZCZ DANE.** Jedyna definicja operacji. Wykonuje się ją wyłącznie przy groźbie przejęcia stacji lub stanowiska, także na polecenie odbiorcy przekazane słownie lub przez gońca, nigdy na podstawie wiadomości radiowej; fakt zapisuje się w dzienniku papierowym. Na stacji (STAN → USŁUGI albo panel z potwierdzeniem przyciskiem na stacji) operacja najpierw usuwa KEK z pamięci MCU (kryptograficzne wymazanie), potem klucz tożsamości oraz w FRAM kartę odbiorcy, adres, kolejkę, skrzynkę i dziennik zdarzeń. Dziennik długu ciszy zostaje ([radio](radio.md)). Na laptopie operacja zatrzymuje przekazywanie, usuwa wpis klucza z magazynu systemowego, a następnie bazę i eksporty. Nadpisanie pamięci flash i SSD nie gwarantuje usunięcia, dlatego decyduje usunięcie klucza; wobec odczytu samej pamięci USB skuteczne jest tylko jej fizyczne zniszczenie, które nakazuje instrukcja. Operacja jest nieodwracalna, stacja przestaje działać, a całość trwa najwyżej 1 minutę. Na komputerze stanowiska operację opisuje [stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska).

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
  firmware/                    # podpisane obrazy oprogramowania stacji (w pilotażu tylko ESP32-S3); tylko w trybie przygotowania
  drivers/<platform>/
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, skróty, polecenie budowy, lista plików; podpisany
  keys/                        # plik klucza bazy tego laptopa; nie trafia do kopii publicznych
  export/                      # zaszyfrowana paczka przeniesionej stacji
```

Pakiet stanowiska ma te same zasady budowy (przypięte wersje, podpisany manifest, interpreter i biblioteki w `runtime/`, źródła i licencje, bez instalowania przez pip), ale nie ma `keys/`, `export/` ani programów START, bo klucz nośnika pochodzi z hasła stanowiska. Zamiast strony i protokołu USB do stacji zawiera aplikację stanowiska z Reticulum `e40191b` i LXMF `c3ff2d6` w Pythonie, ich licencje i źródła oraz konfigurację interfejsu KISS ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Stan aplikacji stanowiska leży na nośniku stanowiska, nie na pamięci pakietu.

W Linuksie stan znajduje się na osobnej partycji ext4 pamięci USB, a w systemach Windows i macOS na dysku laptopa, w katalogu aplikacji. Aktywna baza nie może leżeć na exFAT. Aplikacja nie zapewnia automatycznej wspólnej bazy między systemami.

PRZENIEŚ STACJĘ (tylko w trybie przygotowania) wymaga sprawnej stacji źródłowej. Przenosi tożsamość, licznik czasu pracy, konfigurację, rejestr zgłoszeń i skrzynkę w paczce zaszyfrowanej kluczem przeniesienia stacji docelowej; kroki, potwierdzenia i postępowanie po przerwaniu opisuje [protokół USB](protokol-usb.md#przeniesienie-stacji). W każdej chwili nadaje najwyżej jedna z dwóch stacji. Bazę laptopa kopiuje się osobno przez API kopii zapasowych SQLite i sprawdza jej integralność. Nie ma wcześniejszej kopii tożsamości, bo dwie stacje z tą samą tożsamością nie mogą istnieć jednocześnie. Uszkodzona lub utracona stacja nie daje się przenieść: stacja zapasowa dostaje nową tożsamość, nową kartę stacji dyżurni dodają do listy zaufanych w aplikacji stanowiska, a starą tożsamość z niej usuwają. Stacja stanowiska nie ma tożsamości odbiorcy, więc nie wymaga PRZENIEŚ STACJĘ: zastępuje ją dowolna stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)). [API kopii](https://www.sqlite.org/backup.html).

### Aktualizacja oprogramowania stacji

Obraz przychodzi przez USB z laptopa (transfer `firmware`, [protokół USB](protokol-usb.md#transfery-dzielone-na-części)), tylko w trybie przygotowania (przycisk pod plombowaną pokrywą serwisową), bez otwierania obudowy głównej. Nie ma DFU, UF2 ani pobierania przez UART bez podpisu. Klucz wydania jest przechowywany offline, a podpis składa się po odtworzeniu kompilacji (T7).

| Element | ESP32-S3 (pilotaż) | nRF52840 (opcja wydania, D14) |
|---|---|---|
| podpis obrazu | Secure Boot V2, RSA-3072 PSS (jedyny schemat V2 w ESP32-S3); do 3 skrótów kluczy w eFuse, nieużyte gniazda unieważnione przy przygotowaniu | MCUboot, Ed25519 albo ECDSA-P256 |
| gniazda obrazu | dwa gniazda OTA (`ota_0`, `ota_1`) po 3 MiB w pamięci flash 8 MiB + `otadata`; obraz ≤3 MiB | gniazdo główne i zapasowe MCUboot w pamięci wewnętrznej albo zewnętrznej (do D14) |
| szyfrowanie flash, JTAG | szyfrowanie flash w trybie Release, eFuse wyłączające JTAG, tryb bezpiecznego pobierania | APPROTECT (rewizja 3, IN-141) |
| ochrona przed cofnięciem | `secure_version` w eFuse: 16 kroków na całe życie układu | licznik bezpieczeństwa MCUboot |

Przebieg: stacja zapisuje obraz do nieaktywnego gniazda, sprawdza SHA-256 i podpis, oznacza gniazdo jako oczekujące i odpowiada `ok`; restart wykonuje dopiero po potwierdzeniu przyciskiem OK. Nowy obraz startuje jako niepotwierdzony. Potwierdza się sam po teście startowym: odczyt i kontrola FRAM, kontrola układu radiowego, start stosu i ekranu, w ≤120 s. Zanik zasilania albo restart przed potwierdzeniem przywraca poprzedni obraz (wycofanie programu rozruchowego); zanik w czasie zapisu do gniazda zostawia stary obraz bez zmian, a laptop zaczyna transfer od nowa. Format rekordów FRAM ma wersję w nagłówku: nowy obraz czyta rekordy starszej wersji i do potwierdzenia zapisuje wszystkie rekordy, także nowe, w starym formacie; na nowy format przechodzi dopiero po potwierdzeniu. Wycofanie nie zastaje więc danych w formacie, którego stary obraz nie zna.

Ochrona przed cofnięciem: program rozruchowy odrzuca obraz o `secure_version` niższym od zapisanego w eFuse. Wartość podnosi się tylko w wydaniu, które usuwa podatność, i dopiero po potwierdzeniu obrazu, nigdy w zwykłej aktualizacji, bo liczba kroków jest ograniczona. Zwykła aktualizacja może więc wrócić do starszej wersji tej samej klasy bezpieczeństwa. Aplikacja laptopa odrzuca obraz starszy od zainstalowanego, chyba że osoba utrzymująca system wybierze przywrócenie wprost.

Oprogramowanie pilotażu jest dziś budowane jako Arduino (platforma pioarduino). Biblioteki ESP-IDF w Arduino są skompilowane z góry i nie pozwalają włączyć Secure Boot V2, szyfrowania flash ani wycofania obrazu, więc obraz z tymi funkcjami buduje się w ESP-IDF z Arduino jako komponentem. Wymagane przed wydaniem. W pilotażu obraz wgrywa zespół projektu na stacje, które pozostają jego własnością; zabezpieczenia obrazu nie należą do [minimum pilotażu](odbior.md#minimum-pilotażu), a przegląd stacji pilotażowych sprawdza wersję obrazu i plombę pokrywy serwisowej.

Konsola UART i logi diagnostyczne są wyłączone w wydaniu. `build-manifest.json` jest podpisany (Ed25519 lub minisign), a odcisk klucza jest na karcie przeglądu. Podpis START dla Windows (Authenticode) i macOS (Developer ID, notaryzacja) – do oceny kosztu.

Pakiet START utrzymuje komputer w stanie pracy podczas działania strony. Uśpienie laptopa wyłącza tylko stronę i panel; stacja pracuje dalej. Po wznowieniu aplikacja wykonuje `sync` ze stacją.

Przed dystrybucją pakiety muszą zostać zbudowane i przetestowane na każdej architekturze. W schronieniu nie instaluje się pakietów przez pip. Po próbie zgodności wydanie przypina dokładne archiwa lub commity wraz z ich skrótami. Podczas uruchamiania nie pobiera się wersji `latest`.

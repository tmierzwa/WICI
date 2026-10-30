# WICI: oprogramowanie

## Podział oprogramowania

**Oprogramowanie układowe stacji** (program stacji) zawiera:

- rdzeń Reticulum stacji z włączonym transportem i LXMF z jedną tożsamością stacji ([zakres rdzenia](../../firmware/reticulum-core.md); w programie stacji od etapów rdzenia 6-3 i 6-4);
- interfejs radiowy jako interfejs Reticulum (LoRa, [profil](radio.md#profil-lora-pilotażu); wstrzymany wariant P1 opisuje [archiwum](../archiwum/README.md));
- rejestr zgłoszeń, kolejkę i skrzynkę odbiorczą w pamięci FRAM;
- interfejs ekranu i przycisków;
- [protokół USB](protokol-usb.md) do laptopa;
- układ nadzorujący (watchdog).

Stacja jest jedynym węzłem sieci w schronieniu i działa bez laptopa. Stacja stanowiska ma to samo oprogramowanie w konfiguracji węzła stanowiska: przekazuje ruch i łączy radio z komputerem stanowiska ([stanowisko odbiorcze](stanowisko-osp.md)).

Wersje referencyjne protokołu: Reticulum `e40191b` i LXMF `c3ff2d6`. Stos Reticulum i LXMF na mikrokontrolerze to własny rdzeń zgodny z tymi wersjami w podzbiorze, którego WICI używa; zastępuje port w programie stacji od etapów rdzenia 6-3 i 6-4 ([kryteria odbioru](../../firmware/reticulum-core.md#kryteria-odbioru)). Obrazy z portem [microReticulum](https://github.com/attermann/microReticulum) zostają do etapu rdzenia 6-5; microReticulum służy też w próbach jako druga implementacja, nie jako wzorzec. Źródło formatu wiadomości: [LXMF](https://github.com/markqvist/LXMF).

LXMF pakuje wiadomości, szyfruje je przez Reticulum, wyszukuje trasę, potwierdza dostarczenie na poziomie transportu i ponawia wysyłkę. Tych mechanizmów nie implementuje się drugi raz. Stan DELIVERED w LXMF nie oznacza zatwierdzonej transakcji w bazie stanowiska odbiorczego. Kolejka intencji jest w FRAM i stacja odtwarza ją po restarcie. Lista oczekujących wiadomości w pamięci LXMF nie jest trwałą kolejką.

Konfiguracja LXMF: wyłącznie dostarczenie okazjonalne (OPPORTUNISTIC), bez przejścia na DIRECT, Resource ani propagację; treść, która się nie mieści, jest błędem już przy tworzeniu intencji. Bez znaczków pracy (brak `stamp_cost`). Ratchety rozstrzyga D01; jeśli zostaną włączone, ich klucze są w FRAM.

**Aplikacja laptopa** (`station-web`, poziomy 2–3) zawiera serwer lokalnej strony, jedną bazę SQLite i panel gospodarza. Nie uruchamia Reticulum ani LXMF i nie ma tożsamości sieciowej; wiadomości przekazuje stacji [protokołem USB](protokol-usb.md). Poziomy 2–3 dochodzą po pilotażu; w pilotażu laptop łączy się ze stacją tylko w trybie przygotowania. Odłączenie laptopa nie przerywa pracy stacji. Restart strony nie zmienia kolejki stacji. Na stanowisku odbiorczym tożsamość odbiorcy, Reticulum, LXMF i baza działają na komputerze stanowiska, a przyjęcie zgłoszenia i wysłanie RECEIVED odbywają się w SQLite aplikacji stanowiska ([stanowisko odbiorcze](stanowisko-osp.md), D19).

NomadNet i narzędzia Reticulum w Pythonie nie są częścią wydania; Reticulum i LXMF w Pythonie uruchamia tylko aplikacja stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). NomadNet i narzędzia mogą służyć w laboratorium do prób zgodności (T3) jako osobne węzły z własną tożsamością. Nie wolno wymagać od mieszkańców instalacji klienta. NomadNet to [klient sieci Reticulum](https://github.com/markqvist/NomadNet) w terminalu.

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik, bez załączników. Cała treść po kodowaniu ma najwyżej 256 B (decyzja robocza, do potwierdzenia w D01 i T3; zastępuje przejściowe 480 B). Dzięki temu każda wiadomość SA1 mieści się w jednym pakiecie okazjonalnym LXMF (dla wersji referencyjnych około 284 B) ([koncepcja, rozdział 05](../concept/05-projekt-koncepcyjny-komunikacji.html#rozmiar-wiadomosci-a-sposob-dostarczenia)). Przypadki najgorsze przy limitach pól poniżej: REQUEST i TEST 222 B, BULLETIN 246 B, REPLY 156 B, STATUS 59 B, RECEIVED 50 B; zgłoszenie z przycisków 220 B.

JSON zawiera jedną tablicę. Swobodne obiekty są odrzucane. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`. Teksty SA1 nie mogą zawierać znaków U+0022 (`"`) i U+005C (`\`). Formularz, panel i ekran zamieniają je na „ ” i `/`, więc tekst nigdy nie wymaga sekwencji ucieczki. Teksty nie mogą też zawierać znaków z kategorii Unicode Cc, Cf, Cs, Co, Cn, Zl i Zp (m.in. znaków C1, znaków zmiany kierunku pisma, niewidocznych znaków formatujących, surogatów, znaków prywatnych i nieprzypisanych, separatorów wiersza i akapitu). Wymagana jest normalizacja NFC; tekst w innej postaci jest odrzucany. Zwykłe polskie i ukraińskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |
| TEST = 5 | `[1,5,id,revision,category,people,location,text,urgency]` |

`id`: 32 małe cyfry szesnastkowe, czyli 16 losowych bajtów z CSPRNG. Tworzy go ten, kto tworzy zgłoszenie SA1:

- stacja dla zgłoszeń z przycisków i TEST z menu ([model zaufania](#model-zaufania-i-kluczy));
- aplikacja laptopa (CSPRNG systemu operacyjnego) dla zgłoszeń z panelu i zgłoszeń mieszkańców zatwierdzonych przez gospodarza;
- aplikacja stanowiska dla BULLETIN.

RECEIVED, STATUS i REPLY powtarzają `id` zgłoszenia. Zgłoszenie mieszkańca przed zatwierdzeniem nie ma `id` SA1, tylko lokalny identyfikator strony ([strona mieszkańca](#strona-mieszkańca)).

`revision`: 0–65 535.

`category` przyjmuje wartości 0–9:

- 0 pomoc medyczna (zagrożenie życia lub zdrowia);
- 1 leki stałe i sprzęt medyczny (tlen, insulina, dializy);
- 2 ewakuacja i transport, w tym osób leżących i z niepełnosprawnością;
- 3 woda pitna;
- 4 żywność, w tym dla niemowląt;
- 5 ogrzewanie, energia, paliwo;
- 6 sanitarne i higiena;
- 7 bezpieczeństwo obiektu (pożar, CO, zalanie, uszkodzenie);
- 8 informacja i poszukiwanie osób;
- 9 inne (wymaga frazy lub opisu).

`people`: 1–65 535.

`location`: 1–64 B, dokładny adres i miejsce wejścia w krótkiej postaci (ulica, numer, wejście; miejscowość tylko wtedy, gdy ta sama ulica występuje w gminie więcej niż raz). `configure` odrzuca dłuższy adres. Miejsce w budynku („gdzie w budynku”) nie należy do `location`: panel i strona dopisują je na początku `text` i liczą do jego limitu.

`text` zgłoszenia i odpowiedzi: do 96 B; komunikatu: do 192 B.

`urgency`:

- 2 = bezpośrednie zagrożenie życia lub zdrowia („ZAGROŻENIE ŻYCIA”);
- 1 = pilne, w ciągu kilku godzin („PILNE – KILKA GODZIN”);
- 0 = w ciągu doby („W CIĄGU DOBY”).

Podwyższenie pilności zatwierdza gospodarz. Przy pilności 2 gospodarz równolegle udziela pierwszej pomocy i, gdy droga jest bezpieczna, wysyła gońca do najbliższej jednostki PSP/OSP lub zespołu ratownictwa medycznego. WICI nie zastępuje numeru 112.

`event`: 1–2 147 483 647, bez zawijania licznika. RECEIVED ma zawsze 1. Dla STATUS, REPLY i BULLETIN aplikacja stanowiska nadaje `event` = max(ostatnia wartość licznika + 1, sekundy od 2026-01-01 00:00 UTC według zegara komputera stanowiska + P), osobno dla STATUS danego `id`, REPLY danego `id` i wszystkich BULLETIN tej tożsamości odbiorcy. P to trwałe przesunięcie numeracji w bazie stanowiska (początkowo 0), stosowane do wszystkich liczników, także tworzonych po odzyskaniu dla zgłoszeń odtworzonych z dziennika papierowego. Składnik czasu sprawia, że po odtworzeniu bazy z wcześniejszej kopii numery nadal rosną, o ile zegar jest poprawny; baza z kopii nie zna numerów nadanych po jej wykonaniu, więc P dodaje zapas. Odzyskanie po odtworzeniu kopii ustawia P = P z kopii + 86 400 s × (1 + liczba wcześniejszych odzyskań od daty kopii według dziennika) ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Kontrola zegara przy starcie porównuje zegar z zapisanym rzeczywistym czasem ostatniego nadania (bez P), nie z numerem `event`, więc przesunięcie nie blokuje zwykłego restartu. Zakres licznika wystarcza do 2094 roku.

`state` (teksty ekranu w tabeli [Teksty ekranu](#teksty-ekranu)):

- 1 = „odbiorca zapisał”;
- 2 = „odbiorca przeczytał”;
- 3 = „pomoc skierowana”: podmiot, który dysponuje siłami (np. stanowisko kierowania PSP, dyspozytor medyczny, służba gminy), potwierdził stanowisku odbiorczemu skierowanie pomocy (to decyzja, nie godzina przyjazdu);
- 4 = „przekazane dalej” (PSP, pogotowie, powiat): stanowisko przekazało zgłoszenie, ale nie ma potwierdzenia skierowania pomocy;
- 5 = „odbiorca nie może teraz pomóc”, zawsze razem z REPLY z instrukcją (np. użyj kanału zastępczego);
- 6 = „zamknięte” (potrzeba ustała).

RECEIVED zawsze oznacza pierwsze przyjęcie danej rewizji, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2–6; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli stanowisko odbiorcze ma już nowszy status, wysyła też najnowszy STATUS. Liczniki event mają klucze (tożsamość odbiorcy, typ, `id`) dla STATUS i REPLY oraz (tożsamość odbiorcy, BULLETIN) dla komunikatów; numer rewizji nie jest częścią klucza. Przyjęcie, kolejność i wiadomości spóźnione opisuje [cykl życia zgłoszenia](#cykl-życia-zgłoszenia). Każdy BULLETIN ma nowe `id`, a poprawka komunikatu jest nowym komunikatem. Żaden BULLETIN nie wywołuje działania automatycznego stacji; każdy komunikat na ekranie ma stopkę `stopka_komunikatu`.

TEST ma tablicę, limity i walidację REQUEST. Sprawdza całą drogę zgłoszenia: transport, zapis na stanowisku i obecność dyżurnego. Stacja proponuje go na ekranie po uruchomieniu, restarcie oraz zmianie anteny lub odbiorcy. Wysyła go na polecenie gospodarza z menu lub panelu, nigdy cyklicznie. Stacja z zegarem RTC nie proponuje TEST po wymianie ogniw, jeśli ostatni kontakt z odbiorcą był według RTC mniej niż 6 h wcześniej. Stacja bez RTC nie zna czasu wyłączenia i proponuje TEST po każdym włączeniu ([czas](#czas)).

TEST startowy (proponowany po uruchomieniu i restarcie) wychodzi z losowym opóźnieniem w oknie 50 s × liczba stacji w sieci od polecenia, aby wiele stacji włączonych naraz nie zajęło kanału. Liczbę stacji zapisuje `configure`. Bez niej okno wynosi 15 min, co wystarcza tylko dla sieci do 18 stacji. Ekran pokazuje `test_zaplanowany`, a WSTECZ anuluje. Kolejność uruchamiania stacji ustala w planie organizator sieci (zwykle samorząd gminy).

Odbiorca może poprosić o wstrzymanie TEST komunikatem BULLETIN. Stacja nie rozpoznaje takiej prośby automatycznie. Gospodarz po przeczytaniu komunikatu wybiera TEST → WSTRZYMAJ, co anuluje TEST oczekujący na nadanie i do odwołania pokazuje `test_wstrzymany`. TEST → WZNÓW odwołuje wstrzymanie. TEST ma najniższy priorytet w kolejce stacji.

Pola TEST startowego i TEST z menu: `category` = 9, `people` = 1, `urgency` = 0, `location` = adres stacji, `text` = „test”. Alarm TEST nie zależy od pilności: `brak_potwierdzenia` po 30 min od `test_wyslany` bez RECEIVED. Zgłoszenia wysyłane podczas prób i ćwiczeń również mają typ TEST; wyjątek: próby odbioru w sieci próbnej bez rzeczywistego odbiorcy (odbiór, „Obciążenie sieci” i „Ruch mieszany z dyżurnym”) używają REQUEST. TEST startowy zawiera rzeczywisty adres i wejście schronienia, aby dyżurny mógł potwierdzić, że są zrozumiałe. Odbiorca przyjmuje TEST jak REQUEST: weryfikacja nadawcy, kwarantanna nieznanej stacji, deduplikacja, jedna transakcja i RECEIVED po COMMIT. Klucz odbioru nie zależy od typu; REQUEST i TEST o tym samym id i revision to konflikt treści. Stanowisko odbiorcze pokazuje TEST osobno od kolejki potrzeb i nie wlicza go do potrzeb. Dyżurny odpowiada wiadomością STATUS ze state=2. Wartości state 3–6 dla TEST są dopuszczalne tylko w uzgodnionym ćwiczeniu i oznaczają decyzję ćwiczebną bez wysłania pomocy. Stacja pokazuje TEST na ekranie i w panelu gospodarza, nie jako zgłoszenie mieszkańca.

**Pojemność.** Pojemność ogranicza najbardziej obciążony węzeł, zwykle stacja stanowiska i przekaźnik obok niej, i dotyczy całej sieci, a nie pojedynczego przekaźnika. Model bez strat w profilu LoRa SF7 ([rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html#pojemnosc-sieci)): stanowisko przyjmuje około 164 zgłoszeń na godzinę z RECEIVED i dwoma STATUS, przekaźnik przed stanowiskiem około 95 na godzinę. Dodanie przekaźników nie zwiększa tego limitu; zwiększa go tylko drugi odbiorca albo podział sieci. BULLETIN wysyła się osobno do każdej stacji: dla 50 stacji to około 8,5 min pracy nadajnika stanowiska z obowiązkową ciszą, i tyle samo trwa rozesłanie polecenia ciszy. Pojemność rzeczywistą wyznacza T5.

Zmiana danych zgłoszenia tworzy nową rewizję (revision). Każda rewizja zawiera pełną lokalizację i treść, więc odbiorca nie potrzebuje wcześniej przekazanych danych o budynku. Stanowisko pokazuje rewizje jako jedno zgłoszenie, ale każdą potwierdza się osobno. Przez radio nie wysyła się imion, numerów PESEL, danych dokumentów ani tokenów strony. Dyżurny nie wpisuje nazwisk ani informacji o zdrowiu do REPLY i BULLETIN. Typ stanu obiektu (MELDUNEK) nie jest częścią SA1 0.5; rozstrzyga o nim D18.

Zgłoszenie z przycisków (poziom 1) tworzy stacja:

- `category` i `urgency` z menu (pilność bez wartości domyślnej);
- `people` 1–999 z listy gotowych wartości lub wpisu cyfra po cyfrze;
- `location` z adresu zapisanego podczas przygotowania (przy liście obiektów: z obiektu wybranego po włączeniu; rewizja zachowuje lokalizację zgłoszenia);
- `text` pusty, jedna z gotowych fraz z konfiguracji albo własny tekst do 48 znaków wpisany przyciskami ([wpis tekstu](#ekran-i-przyciski-stacji)).

Każda gotowa fraza ma ≤96 B UTF-8 i jest zapisana po polsku. Ekran pokazuje jej tłumaczenie z konfiguracji w wybranym języku, a dyżurny otrzymuje wersję polską. 48 znaków po najwyżej 2 B mieści się w limicie 96 B, a własny tekst trafia do dyżurnego tak, jak go wpisano. Kategoria 9 wymaga frazy albo własnego tekstu. `urgency` = 2 wymaga dodatkowego potwierdzenia. `configure` odrzuca adres i frazę, jeśli najgorsze zgłoszenie z przycisków przekroczyłoby limit 256 B. Domyślna lista fraz: osoba na wózku; osoba leżąca – potrzebne nosze; dializy – termin dziś; insulina na 1 dzień; niemowlę – mleko modyfikowane; osoba niewidoma lub niesłysząca; tlen na wyczerpaniu; dziecko bez opieki; czujnik CO alarmuje; woda w budynku; potrzeba ustała.

Ekran i panel pokazują krótki numer zgłoszenia: pierwsze 16 bitów `id` modulo 10 000, jako cztery cyfry. Cztery cyfry powtarzają się już przy kilkudziesięciu zgłoszeniach (około 4% przy 30), dlatego numer jest unikalny w obrębie stacji: stacja losuje `id` ponownie, dopóki krótki numer nie różni się od numerów wpisów w rejestrze zgłoszeń i w pamięci zwolnionych wpisów, a nowe `id` z laptopa o zajętym numerze odrzuca (`rejected`, przyczyna `numer_zajety`) i laptop losuje nowe. Numer ten razem z nazwą stacji `WICI-xxxxxx` jednoznacznie wskazuje zgłoszenie przy przekazaniu telefonicznym lub przez gońca.

## Cykl życia zgłoszenia

Stacja prowadzi dla każdego własnego `id` (REQUEST i TEST) jeden wpis w rejestrze zgłoszeń ([pamięć FRAM](#pamięć-fram)). Wpis ma dwie niezależne części: **wysyłkę najnowszej rewizji** i **decyzję odbiorcy**. Historia rewizji zostaje w dzienniku zdarzeń, a w rejestrze tylko najnowsza rewizja z pełną treścią, bo każda rewizja zawiera pełną lokalizację i treść.

| Pole wpisu | Znaczenie |
|---|---|
| `r_max`, treść | najnowsza rewizja i jej tablica SA1 |
| `r_rcv` | najwyższa rewizja potwierdzona RECEIVED albo wiadomością STATUS lub REPLY tej rewizji; −1, gdy żadna |
| etap | etap wysyłki `r_max`: `zapisane`, `wysylanie`, `dostarczone` (LXMF DELIVERED bez RECEIVED), `odebrane`, `anulowane` |
| decyzja | stan 2–6 i rewizja z ostatniego przyjętego STATUS; 0, gdy brak |
| `status_hi`, `reply_hi` | najwyższy przyjęty `event` STATUS i REPLY tego `id` od aktywnej tożsamości odbiorcy |
| `nadane` | znacznik jednokrotnego zapisu: zatwierdzony w FRAM przed pierwszym przekazaniem którejkolwiek rewizji do LXMF i nigdy nie kasowany; od niego zależy ANULUJ WYSYŁKĘ |
| czasy | COMMIT każdej niepotwierdzonej rewizji, RECEIVED `r_max`, ostatnia zmiana (czas dla obsługi, [czas](#czas)) |

**Wiadomości przychodzące.** Stacja sprawdza najpierw podpis, aktywną tożsamość odbiorcy i format ([trwałość](#trwałość-i-potwierdzenia)). Wiadomość odrzucona albo pominięta nie zmienia stanu; trafia tylko do liczników diagnostyki i dziennika zdarzeń.

| Wiadomość | Przyjęta, gdy | Skutek |
|---|---|---|
| RECEIVED (`id`, r) | `id` jest w rejestrze i r ≤ `r_max` | `r_rcv` = max(`r_rcv`, r); przy r = `r_max` etap `odebrane` i koniec ponowień; zgłoszenia anulowanego nigdy nie nadano, więc RECEIVED dla niego jest pomijany i liczony w diagnostyce |
| STATUS (`id`, r, e, s) | jak wyżej i e > `status_hi` | `status_hi` = e, decyzja = (s, r); działa też jak RECEIVED rewizji r |
| REPLY (`id`, r, e) | jak wyżej i e > `reply_hi` | `reply_hi` = e, odpowiedź do skrzynki; działa też jak RECEIVED rewizji r |
| BULLETIN (`id`, e) | (`id`, e) nie ma wśród 64 zapamiętanych komunikatów, e > `bulletin_floor` i e > (najwyższy przyjęty `event` komunikatu − 86 400) | komunikat do skrzynki, para do zbioru powtórzeń; gdy zbiór jest pełny, wypada para o najmniejszym e, a `bulletin_floor` = to e |
| wiadomość dla `id` spoza rejestru albo z r > `r_max` | nigdy | pominięta |
| STATUS lub REPLY z e ≤ licznika | nigdy | pominięta jako powtórzenie albo spóźniona |

Decyzją wyświetlaną jest zawsze ta z najwyższym `event`, niezależnie od rewizji; dyżurny decyduje o zgłoszeniu jako całości. `bulletin_floor` (początkowo 0) zapisuje się razem ze zbiorem powtórzeń, więc komunikat, który wypadł ze zbioru, nie zostanie przyjęty ponownie, niezależnie od czasu i stanu skrzynki. Ochrona przed odtworzeniem jest więc pełna, a jej ceną jest odrzucenie prawdziwego komunikatu, który dotrze później niż 64 nowsze; trafia on do licznika pominiętych BULLETIN w diagnostyce. Okno 86 400 nie chroni przed powtórzeniem, tylko nie pokazuje komunikatów starszych o ponad dobę od najnowszego. Liczniki, zbiór powtórzeń BULLETIN i `bulletin_floor` należą do aktywnej tożsamości odbiorcy: po przełączeniu na KLUCZ ZAPASOWY stacja zaczyna je od zera dla tożsamości zapasowej, a wiadomości od głównej odrzuca.

**Czynności lokalne:**

| Czynność | Warunek | Skutek |
|---|---|---|
| nowe zgłoszenie (przyciski, `submit`, TEST) | wolny wpis w rejestrze i wolne miejsce w kolejce | wpis z r = 0, etap `zapisane`, intencja wysyłki |
| nowa rewizja (ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA, `submit` z r > `r_max`) | zgłoszenie nieanulowane | `r_max` = r, etap `zapisane`; intencja poprzedniej rewizji kończy się: nienadana od razu, nadawana po zakończeniu bieżącej próby LXMF, bez dalszych ponowień; decyzja zostaje i jest wyświetlana pod etapem nowej rewizji |
| ANULUJ WYSYŁKĘ | `nadane` nie jest ustawione (żadna rewizja nie została przekazana do LXMF; także w ciszy radiowej) | etap `anulowane`, intencja zakończona, wpis do dziennika zdarzeń; po pierwszym przekazaniu do LXMF odbiorca mógł zgłoszenie dostać, więc zamiast anulowania jest tylko POTRZEBA USTAŁA |
| KLUCZ ZAPASOWY | – | intencje rewizji bez RECEIVED wracają do kolejki z tym samym `id` i `revision`, z nowym celem; liczniki od zera |
| zwolnienie wpisu | wpis zamknięty (niżej) i brak wolnego wpisu dla nowego zgłoszenia | osobna transakcja przed utworzeniem nowego wpisu: gniazdo „wolne”, (`id`, `r_max`) do pamięci zwolnionych wpisów, zdarzenie `released` |

**Wpis zamknięty** nie ma aktywnej intencji i spełnia jeden z warunków: (a) etap `odebrane`, `r_rcv` = `r_max` i decyzja 6 z rewizji `r_max`; (b) etap `anulowane` (zgłoszenie nigdy nie wyszło ze stacji, więc odbiorca go nie ma); (c) TEST z etapem `odebrane` i `r_rcv` = `r_max`. Decyzja 6 ze starszej rewizji nie zamyka wpisu, bo nowa rewizja (np. „potrzeba wróciła”) czeka na nową decyzję. Zwalnia się wpis zamknięty o najdawniejszej ostatniej zmianie. Wiadomość dla zwolnionego `id` jest pomijana jak dla `id` spoza rejestru, a `submit` z tym `id` nie tworzy go ponownie ([protokół USB](protokol-usb.md#polecenia-laptopa)).

**Ekran.** Przy zgłoszeniu w WIADOMOŚCIACH i w PRZEKAZANIU ZMIANY stacja pokazuje: przy etapie `zapisane` tekst `zapisane_w_stacji` (w ciszy `zapisane_w_ciszy`), przy `wysylanie` i `dostarczone` tekst `wysylanie`, a pod nim stan z decyzji, jeśli jest; przy etapie `odebrane` stan z decyzji (`stan_2`–`stan_6`) albo `stan_1`, gdy decyzji jeszcze nie ma. Zgłoszenie anulowane znika z listy otwartych zgłoszeń.

**Alarmy.** `brak_potwierdzenia` uruchamia się, gdy `r_max` nie ma RECEIVED, a od COMMIT najstarszej rewizji nowszej niż `r_rcv` minął czas zależny od pilności `r_max` (2 → 15 min, 1 → 1 h, 0 → 6 h; TEST 30 min od pierwszego nadania, nie od COMMIT, bo TEST startowy czeka na nadanie losowo długo, do 50 s × liczba stacji; TEST przed pierwszym nadaniem nie alarmuje). `brak_odczytu` uruchamia się przy pilności 2, gdy 30 min po RECEIVED `r_max` nie przyszedł STATUS tej rewizji. Wyłączenie stacji zatrzymuje liczenie, a po włączeniu zasilania próg odliczania sprzed włączenia jest przekroczony ([czas](#czas)).

**Wektory prób** (T2; stan po ostatniej wiadomości, `id` X w rejestrze z `r_max` = 1, `r_rcv` = −1, wszystkie wiadomości od aktywnej tożsamości):

| Sekwencja wiadomości | Wynik |
|---|---|
| RECEIVED(X,0), RECEIVED(X,1) | `r_rcv` = 1, etap `odebrane`, ekran `stan_1` |
| STATUS(X,0,e=10,s=3), RECEIVED(X,1) | decyzja 3, etap `odebrane`, ekran `stan_3` |
| STATUS(X,1,e=10,s=2), STATUS(X,0,e=9,s=3) | drugi pominięty; decyzja 2 |
| STATUS(X,1,e=10,s=6), STATUS(X,1,e=10,s=6) | drugi pominięty jako powtórzenie |
| RECEIVED(X,2) | pominięty (r > `r_max`) |
| REPLY(X,1,e=5), STATUS(X,1,e=4,s=5) | oba przyjęte (osobne liczniki); decyzja 5, odpowiedź w skrzynce |
| STATUS(X,0,e=10,s=6), potem nowa rewizja 2 | decyzja 6 zostaje, etap `zapisane`; ekran `zapisane_w_stacji` i pod nim `stan_6`, do RECEIVED rewizji 2; wpis nie jest zamknięty |
| X nadany (`nadane` ustawione), dowód i RECEIVED utracone, potem ANULUJ | ANULUJ niedostępne w menu (USB: `too_late`), jest tylko POTRZEBA USTAŁA; wpis nie jest zamknięty, więc późny RECEIVED(X,1) daje etap `odebrane` i ekran `stan_1` także przy pełnym rejestrze |
| nowe zgłoszenie Z w ciszy radiowej, ANULUJ, potem 255 kolejnych wpisów i nowe zgłoszenie | Z zamknięty i może być zwolniony |
| STATUS(Y,0,e=3,s=3) dla Y spoza rejestru | pominięty |
| BULLETIN(B,e=100), BULLETIN(B,e=100) | drugi pominięty |
| BULLETIN(B1,e=200 000), BULLETIN(B2,e=100 000) | drugi pominięty (starszy o ponad dobę) |
| BULLETIN(B1,e=1000) … BULLETIN(B65,e=1064), usunięcie B1 ze skrzynki, BULLETIN(B1,e=1000) po dobie | ostatni pominięty (e ≤ `bulletin_floor` = 1000) |
| 256 wpisów w rejestrze, wpis X: STATUS(X,1,e=10,s=6), RECEIVED(X,1), potem nowa rewizja 2, RECEIVED(X,2), potem nowe zgłoszenie | X nie jest zwolniony; nowe zgłoszenie zwalnia inny wpis zamknięty albo dostaje `kolejka_pelna` |
| 256 wpisów, X jedynym wpisem zamkniętym (decyzja 6 z `r_max`), nowe zgłoszenie, potem STATUS(X,1,e=11,s=2) | X zwolniony i w pamięci zwolnionych wpisów; STATUS pominięty |

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zgłoszenie z przycisków | zgłoszenie + intencja wysyłki w FRAM stacji |
| Zgłoszenie ze strony | w SQLite laptopa: zgłoszenie mieszkańca + skrót tokenu dostępu, w kolejce gospodarza |
| Zatwierdzenie przez gospodarza | w SQLite laptopa: zgłoszenie SA1 z nowym `id` + powiązanie ze zgłoszeniami mieszkańców + intencja przekazania; w stacji: zgłoszenie + intencja wysyłki, idempotentnie po kluczu wiadomości |
| Przyjęcie na stanowisku | zweryfikowane zgłoszenie + tożsamość nadawcy + klucz odbioru + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS (przy stanie 3 także źródło i czas potwierdzenia skierowania pomocy, przy stanie 4 komu i kiedy przekazano, przy stanie 5 intencja REPLY) |

**Zapis w FRAM.** Każdy magazyn ma stałe gniazda ([pamięć FRAM](#pamięć-fram)). Rekord gniazda ma nagłówek (magazyn, gniazdo, wersja formatu, generacja klucza, numer zapisu, długość), treść i znacznik zatwierdzenia (CRC-32 rekordu i stała 4 B). Zapis do gniazda, które ma zatwierdzoną treść, nigdy nie nadpisuje jej bezpośrednio. Każda zmiana przechodzi przez rekord transakcji, także zmiana jednego pola i zmiana kilku gniazd naraz (np. nowa rewizja i zakończenie poprzedniej intencji, wiadomość w skrzynce i zdarzenie dla laptopa).

Rekord transakcji (dziennik zapisu z wyprzedzeniem) zawiera pełne nowe bajty wszystkich zmienianych gniazd i własny znacznik. Dopiero po jego zatwierdzeniu (COMMIT stacji) stacja przepisuje bajty do gniazd i oznacza transakcję jako wykonaną. Po restarcie zatwierdzony, niewykonany rekord transakcji jest wykonywany ponownie (zapis jest idempotentny), a niezatwierdzony odrzucany; gniazda zachowują wtedy poprzednią treść. Są dwa rekordy transakcji używane na zmianę, więc zanik w czasie zapisu nowego nie niszczy poprzedniego. Największa transakcja ma ≤4 KiB. Najgorszy przypadek to REPLY z usunięciem innej wiadomości ze skrzynki: dwa gniazda skrzynki, wpis rejestru i dwa bloki pierścienia zdarzeń, razem 5 × 512 B = 2,5 KiB plus nagłówek transakcji, poniżej 4 KiB.

Dziennik zdarzeń stacji (diagnostyka) jest poza transakcjami: jego wpis może przepaść przy zaniku zasilania, a stan magazynów nie. Tablice stosu zapisują zmianę wpisu w wolnym gnieździe bez rekordu transakcji ([wyjątki](#pamięć-fram)). Zapisy większe opisuje [osobny podrozdział](#zapisy-większe-niż-transakcja).

Zapis idzie seriami SPI po ≤256 B. Przy zegarze SPI pamięci ≥8 MHz seria trwa ≤0,3 ms. Po sygnale zaniku zasilania stacja kończy bieżącą serię, zwalnia linię CS pamięci i nie zaczyna następnej. Ten czas wchodzi do budżetu zaniku zasilania ([elektronika](elektronika.md#zanik-zasilania-i-zapis)). Poprawność nie zależy od tego, czy zdąży się zapisać cała transakcja: zanik przed znacznikiem odrzuca niezatwierdzoną transakcję, co jest dopuszczalne, bo `zapisane_w_stacji` i `stored` pojawiają się dopiero po COMMIT. Przed wyłączeniem przy niskim napięciu ogniw stacja kończy bieżący zapis i pokazuje `wylaczanie`, a potem `mozna_wyjac`.

**Szyfrowanie rekordów FRAM** jest wymagane przed wydaniem, nie przed pilotażem (F99): na poziomie 1 kolejka zawiera tylko frazy z przycisków, a dane o zdrowiu tylko pośrednio przez kategorie. Każdy rekord gniazda (także blok pierścienia albo zbioru, [pamięć FRAM](#pamięć-fram)) i rekord transakcji jest szyfrowany w całości jako jeden szyfrogram AEAD (AES-128-GCM albo ChaCha20-Poly1305 w ESP32-S3; AES-128-CCM w nRF52840 z CC310) ze znacznikiem 16 B i własnym nonce; dane uwierzytelnione to nagłówek rekordu (z magazynem i gniazdem, więc rekordu nie da się przenieść do innego gniazda). Rekord z błędnym znacznikiem traktuje się jak uszkodzony. Narzut rekordu: nagłówek 24 B (magazyn 1 B, gniazdo 2 B, wersja formatu 1 B, generacja klucza 4 B, numer zapisu 8 B, długość 2 B, zarezerwowane 6 B), znacznik AEAD 16 B i znacznik zatwierdzenia 8 B, razem 48 B; treść gniazda 512 B ma więc ≤464 B. Jawne zostają tylko dziennik długu ciszy, licznik czasu pracy, wersja formatu FRAM (`fram_format`), ustawienia ekranu, rekord rezerwacji numerów zapisu i znacznik postępu zmiany klucza. Tablice stosu są dziś jawne: to znana luka do wydania ([wyjątki](#pamięć-fram)).

- **Klucz.** Klucz szyfrowania generacji g to HKDF-SHA-256(KEK, „WICI FRAM” ‖ g). KEK (32 B) leży w osobnej stronie pamięci flash MCU poza systemem plików, chronionej szyfrowaniem flash albo APPROTECT, kasowanej z weryfikacją. Generacja klucza (32 b; nie mylić z epoką pierścienia zdarzeń USB) zaczyna się od 1 przy utworzeniu KEK; nowy KEK (i generacja 1) powstaje po ZNISZCZ DANE i po imporcie PRZENIEŚ STACJĘ, a nowa generacja tego samego KEK po ZAMKNIJ ZDARZENIE. Zmiana klucza przepisuje wszystkie rekordy pod nowy klucz w operacji wznawianej po zaniku zasilania: generacja w nagłówku mówi, którym kluczem zaszyfrowano dany rekord, a jawny znacznik postępu mówi, do którego gniazda doszła operacja; stary klucz istnieje do jej zakończenia.
- **Nonce** (96 b) = generacja klucza (32 b) ‖ numer zapisu (64 b). Numer zapisu rośnie przy każdym zapisie szyfrowanym (rekord transakcji, gniazdo, także przepisanie tego samego gniazda), jest w nagłówku rekordu i nigdy się nie powtarza dla jednego klucza; ponowne wykonanie zatwierdzonej transakcji po restarcie zapisuje te same szyfrogramy z rekordu transakcji, więc nie tworzy nowego nonce. Stacja rezerwuje numery blokami po 1024: przed użyciem pierwszego numeru bloku zapisuje i zatwierdza w jawnym rekordzie rezerwacji (dwie kopie) górną granicę bloku. Po restarcie zaczyna od granicy ostatniej zatwierdzonej rezerwacji, więc numer użyty w przerwanym zapisie (także rekordu potem odrzuconego) nie wróci. Przepisanie rekordu pod nowy klucz używa nowych numerów. 64 b numeru nie wyczerpie się w życiu stacji (przy zapisie co 0,65 s: ponad 10¹¹ lat). Wymagania wynikają z NIST SP 800-38D (jednorazowość nonce dla jednego klucza).
- Podmiana całej zawartości FRAM starszym obrazem (rollback) pozostaje ryzykiem szczątkowym ([rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)).

**SQLite** aplikacji stanowiska: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone; baza laptopa pracuje w pamięci procesu, a jej trwałość daje zaszyfrowana migawka po `fsync` ([pakiet USB](#pakiet-usb)). Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią oznacza konflikt; dane nie są nadpisywane.

Przed zapisem funkcja zwrotna odbioru sprawdza `signature_validated`, zaufanie do nadawcy i limit rozmiaru. Stacja przyjmuje RECEIVED, STATUS, REPLY i BULLETIN wyłącznie od aktywnej tożsamości przypiętego odbiorcy ([klucz odbiorcy](#model-zaufania-i-kluczy)); inne odrzuca i liczy w diagnostyce. Nazwa wyświetlana i pole JSON nie nadają uprawnień. Na stanowisku REQUEST i TEST nieznanej stacji trafiają do kwarantanny i czekają na decyzję dyżurnego ([model zaufania](#model-zaufania-i-kluczy)). Kwarantanna jest zapisem trwałym, ale nie przyjęciem: RECEIVED wysyła się dopiero po zatwierdzeniu wiadomości przez dyżurnego. Zgłoszenie z kwarantanny nie jest traktowane jak zgłoszenie ze zweryfikowanego schronienia. Kartę odbiorcy zapisuje się w stacji tylko w trybie przygotowania, po przytrzymaniu przycisku konfiguracji na stacji; nigdy przez radio.

### Dowód dostarczenia po COMMIT

Aplikacja stanowiska kończy intencję REPLY i BULLETIN po LXMF DELIVERED, czyli po dowodzie dostarczenia pakietu od stacji ([wysyłka](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Stacja wysyła więc dowód dla wiadomości SA1 dopiero po rozstrzygnięciu: po COMMIT w FRAM albo po trwałym odrzuceniu (powtórzenie, wiadomość spóźniona, obcy klucz, zły format). Wiadomość, której nie przyjęto z braku miejsca, i wiadomość przerwana zanikiem zasilania przed COMMIT nie dostają dowodu, więc stanowisko ją ponawia. W implementacji referencyjnej LXMF `c3ff2d6` `delivery_packet()` wywołuje `packet.prove()` przed przetworzeniem wiadomości i funkcją zwrotną aplikacji ([LXMRouter.py](https://github.com/markqvist/LXMF/blob/c3ff2d6/LXMF/LXMRouter.py#L1995)), więc implementacja na MCU wybrana w D14 musi pozwalać wstrzymać dowód do decyzji aplikacji; inaczej SA1 potrzebuje osobnego potwierdzenia aplikacyjnego odpowiedzi i komunikatów, co zmienia format i wraca do D01. Na stanowisku wczesny dowód dla REQUEST i TEST nie szkodzi, bo stacja kończy ponawianie dopiero po RECEIVED.

Proces kolejki wysyła RECEIVED i każde inne potwierdzenie aplikacyjne dopiero po COMMIT. Brak miejsca, uszkodzenie bazy lub dziennika FRAM albo błąd fsync blokują komunikat `zapisane_w_stacji`; stacja pokazuje wtedy `blad_pamieci`. Stacja i aplikacja nie tworzą automatycznie pustego magazynu w miejsce uszkodzonego. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. Trwałość opisuje dokumentacja SQLite ([atomic commit](https://sqlite.org/atomiccommit.html)).

### Wysyłanie

Stany intencji i wpisu rejestru opisuje [cykl życia zgłoszenia](#cykl-życia-zgłoszenia). Intencja jest aktywna od przekazania do LXMF do stanu DELIVERED albo FAILED. W jednej aktywnej wysyłce LXMF stacji wykonuje się najwyżej 2 próby dostarczenia, z odstępem nie krótszym niż [odstęp ponowienia](radio.md#ponowienia-i-limity-prób) dla liczby skoków. Po pierwszym DELIVERED stacja czeka na RECEIVED 10 min, potem ponawia intencję co losowe 30–60 min (rozkład równomierny, bez dodatkowego przesunięcia). Po FAILED ponawia po 1, 2 i 5 min, potem co 15 min, każdy odstęp ±20%, a od 6 h po pierwszej próbie co 60 min ±20% (`firmware/src/station.cpp`, `retryDelayS`). Nigdy nie ponawia równolegle z wciąż aktywną wysyłką tej samej intencji. Intencja w oczekiwaniu nie blokuje następnych. Stacja przekazuje do LXMF najwyżej 2 własne wiadomości jednocześnie.

STATUS lub REPLY od aktywnej tożsamości odbiorcy także kończy ponawianie danej pary (id, revision). Nienadana starsza rewizja jest oznaczana jako zastąpiona. Intencja nie jest usuwana automatycznie. Po czasie zależnym od pilności ekran pokazuje alarm braku potwierdzenia ([ekran](#ekran-i-przyciski-stacji)). Nowa wiadomość LXMF może mieć inny skrót (hash), a id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji u odbiorcy.

Kolejka stacji zawiera tylko REQUEST i TEST. Kolejność: REQUEST z `urgency` = 2, potem pozostałe REQUEST według czasu COMMIT, na końcu TEST. Nie oznacza to priorytetu w całej sieci. Aplikacja stanowiska wysyła swoje wiadomości w kolejności RECEIVED i STATUS, potem REPLY i BULLETIN, a nieodesłany STATUS dla tego samego (odbiorca, `id`, `revision`) zastępuje nowszym ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Kolejka interfejsu radiowego ma własne priorytety: potwierdzenia pakietów i zapytania o trasę, potem dane K0 i K1, potem dane K2, na końcu ogłoszenia ([dostęp do kanału](radio.md#dostęp-do-kanału)).

### Czas

Stacja utrzymuje w FRAM licznik czasu pracy i używa go jako monotonicznego zegara Reticulum i LXMF między restartami. Licznik zapisuje się co 60 s. Przy starcie stacja przyjmuje wartość zapisaną + 60 s i od razu ją zapisuje, zanim nada pierwszą ramkę albo utworzy rekord. Dzięki temu czas po restarcie nigdy nie jest mniejszy od czasu użytego przed restartem, także gdy zanik nastąpił tuż przed zaplanowanym zapisem. Ceną jest przesunięcie licznika do przodu o ≤60 s na każdy restart. Z tego licznika pochodzą znaczniki czasu stosu (ogłoszenia, Reticulum, LXMF). **Czas dla obsługi** (ekran, alarmy, `last_contact`) to licznik minus suma przeskoków restartów S, zapisywana razem z licznikiem (przy każdym starcie S rośnie o te same 60 s). Po restarcie czas dla obsługi zaczyna się od ostatniej zapisanej wartości, więc różnica dwóch takich czasów nigdy nie przekracza rzeczywistego czasu pracy między nimi; ujemną różnicę (zdarzenie po ostatnim zapisie przed zanikiem) traktuje się jak 0. Czasy w rejestrze, skrzynce, `at` zdarzeń USB i ostatni kontakt z odbiorcą zapisuje się w czasie dla obsługi, nie w surowym liczniku, więc różnica z czasem bieżącym nie zawiera przeskoków restartów. Wszystkie czasy na ekranie liczy się od czasu dla obsługi, nie od zegara kalendarzowego; zegar kalendarzowy przekazany przez laptop nie jest zaufany. Licznik nie rośnie, gdy stacja jest wyłączona.

Bez RTC stacja po włączeniu nie wie, jak długo była wyłączona: do pierwszej nowej wiadomości od odbiorcy pokazuje `ostatni_kontakt_ponad`, czyli dolne oszacowanie (czas dla obsługi przed wyłączeniem i po włączeniu, zaokrąglony w dół), zamiast `ostatni_kontakt`. Przykład: kontakt przy czasie dla obsługi 120 s, ostatni zapis przy 120 s, restart sekundę później: po 5 min pracy ekran pokazuje „PONAD 5 MIN”, a nie „PONAD 6 MIN”, jak dałby surowy licznik. Alarmy liczą czas dla obsługi, więc wyłączenie stacji je wstrzymuje, a każdy restart może je opóźnić o ≤60 s, nigdy przyspieszyć. Dlatego po włączeniu zasilania (nie po restarcie programowym ani przez watchdog, które stacja rozpoznaje po niewyzerowanej przy starcie pamięci RAM) stacja bez RTC uznaje próg `brak_potwierdzenia` i `brak_odczytu` każdego zgłoszenia REQUEST, którego odliczanie trwało przed włączeniem, za przekroczony i alarmuje od razu; `[n]` w tekście alarmu jest wtedy dolnym oszacowaniem, jak `ostatni_kontakt_ponad`. Błąd idzie w stronę ostrożności: po krótkiej wymianie ogniw gospodarz potwierdza zbędny alarm OK, a zgłoszenie z zagrożeniem życia po kilkugodzinnym wyłączeniu nie czeka kolejnych 15 min. Reguła obowiązuje do pierwszej przyjętej wiadomości od odbiorcy o tym zgłoszeniu (RECEIVED, STATUS, REPLY); nowa rewizja jej nie znosi, gdy starsza niepotwierdzona rewizja pochodzi sprzed włączenia. TEST jest pominięty, bo po włączeniu stacja i tak proponuje nowy. Zgłoszenia utworzone po włączeniu mają zwykłe progi.

Licznik i S należą do tożsamości stacji i przechodzą z nią w PRZENIEŚ STACJĘ; stacja docelowa przyjmuje większą z dwóch wartości licznika + 60 s (ten sam opis w [protokole USB](protokol-usb.md#przeniesienie-stacji)), aby jej ogłoszenia nie wyglądały na starsze od wcześniejszych (do potwierdzenia w T3), i S = S źródłowej + (nowy licznik − licznik źródłowej), więc czas dla obsługi przeniesionych rekordów się nie zmienia. Odbiorca ignoruje znacznik czasu LXMF i używa czasu lokalnego odbioru.



### Pojemności stosu

Tablica tras i tożsamości mieści co najmniej 256 wpisów z buforowanym ogłoszeniem, a lista skrótów pakietów co najmniej 4096 wpisów. Wpisów tożsamości głównej i zapasowej odbiorcy nigdy się nie usuwa; w konfiguracji węzła stanowiska chronione są wpisy celów osiągalnych przez interfejs USB. Poza nimi usuwa się wpis najdawniej używany. Przy pełnych 32-bajtowych skrótach, jak w implementacji referencyjnej, sama lista skrótów zajęłaby 128 KiB, a tablica tras z ogłoszeniami około 78 KiB, czyli razem około 81% RAM nRF52840. Dlatego:

- lista skrótów pakietów w RAM przechowuje pierwsze 8 B skrótu (4096 × 8 B = 32 KiB); prawdopodobieństwo, że nowy pakiet zostanie fałszywie uznany za duplikat, wynosi przy 4096 wpisach około 2·10⁻¹⁶ (4096 / 2⁶⁴), a lista jest lokalna i nie zmienia protokołu;
- pełne wpisy tablicy tras, tożsamości i buforowane ogłoszenia leżą w FRAM, w gniazdach po 568 B z jednym gniazdem zapasowym. Zmiana wpisu trafia do wolnego gniazda ([wyjątki](#pamięć-fram) od gniazda 512 B, transakcji i szyfrowania). RAM zawiera indeks 257 × 24 B i bufor jednego gniazda, bez pamięci podręcznej wpisów ([rdzeń](../../firmware/reticulum-core.md)). Indeks (skrót celu, czas ostatniego użycia wpisu i trasy) służy do wypierania i wygasania tras bez czytania FRAM.

Zapas RAM ≥30% mierzy się przy tych pojemnościach i tym podziale, z LXMF, poleceniem `RNS` na płytce. W pilotażu (ESP32-S3, 512 KiB SRAM) pomiar należy do minimum pilotażu i blokuje T3 na stacjach pilotażowych (D14). Dla wydania na nRF52840 odtworzenie ruchu w programie węzła zbudowanym jako 32-bitowy daje 3,5% wolnej RAM w szczycie i 12,5% w stanie ustalonym, jeszcze bez LXMF ([pamięć RAM](../../firmware/README.md#pamięć-ram)): indeks magazynów portu zajmuje około 233 B na cel zamiast 24 B. Z portem warunek nie jest tam spełniony. Rdzeń stacji ma zwarty indeks i cel ≤56 KB RAM statycznie z LXMF ([budżet](../../firmware/reticulum-core.md#wymagania-konstrukcyjne)); przed decyzją o wydaniu (stacja WICI) D14 rozstrzyga pomiar rdzenia na płytce, a gdy nie wystarczy, MCU z większą pamięcią (koszt, pobór wobec W23, dostępność).

### Pamięć FRAM

Każdy magazyn ma stałą liczbę gniazd o stałym rozmiarze; nie ma dziennika dopisywanego i kompaktowania. Zwolnienie gniazda to zapis rekordu „wolne” w zwykłej transakcji. Rekord gniazda mieści ≤256 B SA1, pola stanu, nagłówek, znacznik zatwierdzenia i znacznik AEAD 16 B (narzut 48 B, [szyfrowanie](#trwałość-i-potwierdzenia)), stąd gniazdo 512 B. Wyjątkiem są tablice stosu (gniazda 568 B, opis pod tabelą). Małe wpisy (zdarzenia USB, zwolnione wpisy, zbiór powtórzeń BULLETIN) leżą w blokach 512 B po 16 wpisów 24 B (384 B treści); blok jest jednym rekordem i jednym szyfrogramem, a dodanie wpisu to transakcja przepisująca cały blok z nowym numerem zapisu. Stacja ma jedną rolę; stan odbiorcy przechowuje komputer stanowiska (D19).

| Magazyn | Gniazda × rozmiar | Razem | Gdy brak miejsca |
|---|---|---|---|
| konfiguracja (`configure`) | 2 × 8 KiB (A/B); kopia: nagłówek 24 B, długość dokumentu 2 B, SHA-256 dokumentu 32 B, dokument ≤7680 B, dopełnienie, znacznik AEAD 16 B i znacznik zatwierdzenia 8 B na końcu | 16 KiB | nowa konfiguracja zastępuje starszą kopię; zatwierdzenie przełącza wskaźnik |
| rejestr własnych zgłoszeń z intencjami ([cykl](#cykl-życia-zgłoszenia)) | 256 × 512 B | 128 KiB | zwalnia się [wpis zamknięty](#cykl-życia-zgłoszenia) o najdawniejszej ostatniej zmianie; decyzja 6 zamyka wpis tylko dla rewizji `r_max` bez aktywnej intencji. Gdy takiego nie ma, nowe zgłoszenie dostaje `kolejka_pelna`. Każdy wpis ma najwyżej jedną aktywną intencję, więc aktywnych intencji jest najwyżej 256 |
| pamięć zwolnionych wpisów (`id`, `revision`, `ev`, krótki numer 14 b i znacznik anulowania 1 b w 2 B; bez treści) | 16 bloków × 16 wpisów | 8 KiB | najstarszy wpis; `tomb_floor` rośnie ([niepewny wynik](protokol-usb.md#niepewny-wynik-polecenia)); czyszczona przy ZAMKNIJ ZDARZENIE |
| skrzynka odbiorcza (REPLY, BULLETIN) | 128 × 512 B | 64 KiB | zwalnia się kolejno: najstarszy przeczytany BULLETIN, najstarszy przeczytany REPLY zgłoszenia zamkniętego, najstarszy nieprzeczytany BULLETIN (licznik w diagnostyce). REPLY zgłoszenia otwartego nie jest usuwany; gdy nie ma innego miejsca, wiadomość nie jest przyjęta i nie dostaje dowodu dostarczenia, więc odbiorca ponowi ([dowód po COMMIT](#dowód-dostarczenia-po-commit)) |
| zbiór powtórzeń BULLETIN z `bulletin_floor` | 4 bloki × 16 wpisów | 2 KiB | wpis o najmniejszym `event`, który staje się `bulletin_floor` ([cykl](#cykl-życia-zgłoszenia)) |
| pierścień zdarzeń USB ([protokół](protokol-usb.md#synchronizacja)) | 16 bloków × 16 wpisów | 8 KiB | nadpisuje najstarszy wpis niezależnie od `ack` |
| dziennik zdarzeń stacji (diagnostyka) | pierścień 64 bloków × 512 B | 32 KiB | nadpisuje najstarszy blok |
| licznik czasu, dług ciszy, rezerwacja nonce, `fram_format`, ustawienia ekranu | dwie kopie | 4 KiB | stały rozmiar |
| wejścia w tryb przygotowania ([naklejka serwisowa](#tryb-przygotowania-i-naklejka-serwisowa)) | pierścień 10 rekordów × 24 B w jawnym obszarze | 240 B | najstarszy rekord; licznik wejść tylko rośnie, ZNISZCZ DANE i ZAMKNIJ ZDARZENIE go nie kasują |
| rekord transakcji (pełne nowe bajty zmienianych gniazd) | 2 × 4 KiB | 8 KiB | stały rozmiar; największa transakcja ≤4 KiB łącznie z nagłówkiem |
| tablice stosu: trasy, tożsamości, ogłoszenia ([pojemności](#pojemności-stosu)) | ≥256 wpisów (257 gniazd × 568 B) | ≤143 KiB | najdawniej używany wpis poza chronionymi |
| **suma** | | **≈413 KiB** | 81% z 512 KiB |

**Tablice stosu: wyjątki.** Tablice stosu są pamięcią podręczną protokołu Reticulum (Python zapisuje je co kilka godzin i przy wyjściu), nie stanem zgłoszeń, więc mają trzy jawne wyjątki od zasad tego podrozdziału:

- gniazdo 568 B zamiast 512 B: wpis z buforowanym ogłoszeniem (do 465 B, z kluczem publicznym i skrótem losowym wewnątrz) potrzebuje nagłówka 64 B, ratchetu 32 B i CRC; mniejsze gniazdo wymagałoby dzielenia ogłoszenia na dwa gniazda;
- zapis bez rekordu transakcji: zmiana wpisu trafia do wolnego gniazda (gniazd jest o jedno więcej niż wpisów), a stare gniazdo jest unieważniane dopiero po zatwierdzeniu nowego. Zanik zasilania zostawia starą albo nową treść wpisu. Z dwóch zatwierdzonych kopii jednego celu montowanie zostawia nowszą i unieważnia starszą. Zmiana obejmuje zawsze jedno gniazdo, więc rekord transakcji nie jest potrzebny;
- rekordy jawne (CRC-32 bez AEAD): to znana luka do [szyfrowania rekordów](#trwałość-i-potwierdzenia) przed wydaniem (F99). Planowany format: nagłówek rekordu jak wyżej z magazynem i gniazdem jako danymi uwierzytelnionymi, znacznik AEAD 16 B, a numer zapisu brany z rezerwacji bloków, więc rozdarty zapis nie powtarza nonce; gniazdo urośnie wtedy o narzut rekordu.

**Rekordy uszkodzone.** Rekord z błędnym znacznikiem zatwierdzenia (albo AEAD), magazynem, gniazdem lub wersją formatu jest uszkodzony; stacja liczy go w diagnostyce (`diag`) i nigdy nie traktuje jak wolnego miejsca ani nowej stacji. Skutki według magazynu:

| Uszkodzony rekord | Zachowanie |
|---|---|
| meta (epoka, wskaźnik konfiguracji, cisza) albo rekord formatu | magazyny nie startują: `blad_pamieci`, radio i przekazywanie ruchu działają dalej; naprawa tylko przez ZNISZCZ DANE i ponowne przygotowanie |
| aktywna kopia konfiguracji | stacja bez konfiguracji (`not_configured`), dopóki nowa `configure` nie zastąpi kopii |
| gniazdo rejestru albo skrzynki | gniazdo wyłączone z użycia do ZAMKNIJ ZDARZENIE; pozostałe wpisy działają |
| blok pierścienia zdarzeń | wpisy przepadły; stacja losuje nową epokę ([protokół USB](protokol-usb.md#synchronizacja)), więc laptop pobiera migawkę |
| blok pamięci zwolnionych wpisów | wpisy przepadły; `tomb_floor` rośnie za bieżący numer zdarzenia, więc laptop nie ponawia niepewnych `submit` ([niepewny wynik](protokol-usb.md#niepewny-wynik-polecenia)) |
| blok zbioru powtórzeń BULLETIN | wpisy przepadły; `bulletin_floor` rośnie do najwyższego przyjętego `event`, więc żaden starszy komunikat nie wraca |
| gniazdo tablic stosu (trasa, tożsamość, ogłoszenie) | wpis przepada, a gniazdo wraca do puli wolnych (to pamięć podręczna: cel ogłosi się znowu); licznik `table_corrupt` w diagnostyce. Wpis odbiorcy z karty stacja odtwarza z kluczy karty przy następnym zgłoszeniu |

Blok uszkodzony stacja zapisuje od nowa (pusty) zwykłą transakcją przy porządkowaniu pamięci. Utraconego klucza tożsamości stacja nie zastępuje nowym ([tożsamość](#model-zaufania-i-kluczy)).

Każda stacja ma FRAM 4 Mbit (512 KiB) z zegarem SPI ≥8 MHz. Pamięć 2 Mbit nie mieści magazynów z tabeli. Stacja w konfiguracji węzła stanowiska używa tylko konfiguracji, tablic stosu, dziennika i liczników.

**Długa praca bez laptopa.** Żaden magazyn nie zależy od `ack` laptopa ani od odbiorcy: pierścienie nadpisują, a rejestr i skrzynka zwalniają gniazda wpisów zamkniętych. Stacja pracująca tygodniami bez laptopa nie wypełnia pamięci, dopóki zgłoszenia są zamykane; gdy odbiorca milczy, rejestr zapełnia się najwyżej 256 wpisami i wtedy zgłasza `kolejka_pelna`. Sprawdza to próba [długiej pracy bez laptopa](odbior.md#próby).

Pełny rejestr blokuje nowe zgłoszenie komunikatem `kolejka_pelna`; nigdy nie daje pozornego `zapisane_w_stacji`. Aplikacja laptopa odmawia zapisu, gdy wolne miejsce spada poniżej 100 MB, a jej dziennik ma rotację do 10 MB.

### Zapisy większe niż transakcja

Zwykła transakcja (rekord transakcji ≤4 KiB) obejmuje każdą zmianę zatwierdzonych gniazd w czasie pracy. Trzy operacje są większe i mają własne mechanizmy; każda kończy się zwykłą transakcją, która jako jedyna decyduje o wyniku:

| Operacja | Gdzie powstają nowe dane | Publikacja | Przerwanie przed publikacją |
|---|---|---|---|
| `configure` (dokument ≤7680 B) | bezpośrednio w nieaktywnej kopii konfiguracji (A albo B), bo jej treść nie jest używana; kopia ma własny SHA-256 i znacznik zatwierdzenia | zwykła transakcja wskaźnika aktywnej kopii z `config_seq` | wskaźnik wskazuje starą kopię; niedokończona kopia jest ignorowana i nadpisywana przy następnej konfiguracji |
| import PRZENIEŚ STACJĘ (≤256 KiB) | w stacji docelowej w stanie `receiving` rejestr, skrzynka, pamięć zwolnionych wpisów i zbiór powtórzeń są puste; odszyfrowane części trafiają wprost do ich gniazd pod nowym kluczem FRAM, jako rekordy z pierwszymi 6 B `mid` w zarezerwowanym polu nagłówka | po sprawdzeniu całej paczki (rozmiar, SHA-256, AEAD każdej części, treść) jedna transakcja ustawia stan `imported`, tożsamość, licznik czasu i nową epokę; dopiero wtedy rekordy z `mid` stają się stanem stacji | po restarcie w stanie `receiving` stacja zwalnia gniazda z `mid` i czeka na ponowny import |
| czyszczenie (ZAMKNIJ ZDARZENIE, ZNISZCZ DANE, `retire`) | – | najpierw transakcja znacznika czyszczenia (od tej chwili stacja traktuje czyszczone magazyny jako puste), potem zwalnianie gniazd po kolei. ZAMKNIJ ZDARZENIE czyści rejestr, skrzynkę, pamięć zwolnionych wpisów i pierścień zdarzeń, a zachowuje zbiór powtórzeń BULLETIN i `bulletin_floor`, aby komunikaty sprzed zamknięcia nie wróciły; ZNISZCZ DANE i `retire` czyszczą wszystko poza długiem ciszy, rezerwacją numerów zapisu, rekordem formatu FRAM (`fram_format`) i rekordami wejść w tryb przygotowania ([ZNISZCZ DANE](#tryby-kryzysowe)) | czyszczenie jest wznawiane po restarcie od znacznika; bez znacznika stan się nie zmienia |

## API lokalnej strony (poziomy 2–3)

Sieć lokalna (LAN) widzi tylko adresy mieszkańca. Panel gospodarza nasłuchuje wyłącznie na 127.0.0.1, czyli jest dostępny tylko z ekranu laptopa. Panel dyżurnego należy do aplikacji stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#panel-dyżurnego)).

| Adres | Dostęp | Działanie |
|---|---|---|
| `GET /` | LAN | informacje, formularz, komunikaty |
| `POST /api/request` | LAN | walidacja i trwały zapis w kolejce gospodarza; 201 dopiero po COMMIT (na laptopie: po `fsync` zaszyfrowanej migawki); nie wysyła radiem |
| `GET /api/request/<lid>` | LAN | treść i status tylko własnego zgłoszenia; `<lid>` to lokalny identyfikator strony (16 losowych bajtów, 32 cyfry szesnastkowe), nie krótki numer; wymaga tokenu w ciasteczku |
| `POST /api/request/<lid>` | LAN | zmiana własnego zgłoszenia; przed zatwierdzeniem zmienia wpis w kolejce gospodarza, po zatwierdzeniu wraca do kolejki gospodarza jako zmiana, z której gospodarz tworzy nową rewizję |
| `GET /operator` | 127.0.0.1 | logowanie gospodarza |
| `GET /api/operator/queue` | 127.0.0.1 | kolejka lokalna; wymaga uwierzytelnienia |
| `POST /api/operator/approve` | 127.0.0.1 | sprawdzenie zgłoszenia mieszkańca, połączenie z powtarzalnym, ustalenie pilności i przekazanie do wysyłki |
| `POST /api/operator/test` | 127.0.0.1 | wysłanie TEST |
| `POST /api/operator/announce` | 127.0.0.1 | jednorazowe ogłoszenie adresu stacji |
| `POST /api/operator/configure` | 127.0.0.1 | adres schronienia (≤64 B), karta odbiorcy (tożsamość główna i zapasowa), gotowe frazy, liczba stacji w sieci (okno TEST startowego) i opcjonalna lista adresów obiektów (do 8, każdy ≤64 B) albo konfiguracja węzła stanowiska (`role` = `wezel`, kod dostępu sieci); tylko w trybie przygotowania |
| `POST /api/operator/export` | 127.0.0.1 | operacja PRZENIEŚ STACJĘ; tylko w trybie przygotowania |
| `POST /api/operator/import` | 127.0.0.1 | przekazanie paczki PRZENIEŚ STACJĘ do stacji zapasowej (krok 3 [przeniesienia](protokol-usb.md#przeniesienie-stacji)); tylko w trybie przygotowania. Baza laptopa przechodzi osobno, przez kopię na pamięci USB |
| `POST /api/operator/revision` | 127.0.0.1 | nowa rewizja zgłoszenia (ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA): `submit` z wyższą `revision` |
| `POST /api/operator/cancel` | 127.0.0.1 | ANULUJ WYSYŁKĘ (`cancel`); po przekazaniu do LXMF stacja odpowiada `too_late` |
| `POST /api/operator/read` | 127.0.0.1 | oznaczenie wiadomości skrzynki jako przeczytanej (`mark_read`) |
| `GET /api/operator/card` | 127.0.0.1 | karta stacji (`card`) i stan stacji (`status`); karta tylko w trybie przygotowania |
| `POST /api/operator/silence` | 127.0.0.1 | włączenie lub wyłączenie ciszy radiowej; wyjątek dla pojedynczego zgłoszenia tylko przy ciszy operacyjnej ustawionej z panelu; wymaga potwierdzenia przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/destroy` | 127.0.0.1 | operacja [ZNISZCZ DANE](#tryby-kryzysowe); podwójne potwierdzenie i potwierdzenie przyciskiem na stacji w ciągu 30 s |
| `POST /api/operator/close` | 127.0.0.1 | operacja [ZAMKNIJ ZDARZENIE](#model-zaufania-i-kluczy) |
| `GET /health` | 127.0.0.1 | stan strony, zapisu i połączenia ze stacją; czas od ostatniego kontaktu z odbiorcą, wiek najstarszej intencji, liczniki odrzutów i restartów stacji |

Token mieszkańca: 32 losowe bajty w ciasteczku `HttpOnly`, `SameSite=Strict`, nigdy w ścieżce URL; baza przechowuje tylko jego skrót. Mieszkańcy nie zakładają kont, nie wyrażają zgód i nie akceptują regulaminu. Strona nie wyświetla przed formularzem żadnych okien formalnych. Pod formularzem jest odnośnik „Informacja o danych” (obowiązek informacyjny, uzupełniony plakatem przy stacji; administrator i podstawa według D13) oraz informacja, że świadome wprowadzenie w błąd fałszywym zgłoszeniem może stanowić wykroczenie (art. 66 § 1 pkt 1 Kodeksu wykroczeń). Żądanie POST wymaga treści JSON, tokenu CSRF sesji i dozwolonego nagłówka Origin. Obowiązują limity rozmiaru i częstości żądań. Strona nie wczytuje zasobów z internetu i nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności w sieci lokalnej, dlatego strona zbiera minimum danych osobowych. Radio szyfruje osobno.

Hasła gospodarza, zastępców i dyżurnych generuje się podczas przygotowania, offline, jako co najmniej 5 słów z listy. Na laptopie lista ma 4096 słów bez polskich liter (laptop przyniesiony na miejscu może nie mieć polskiego układu klawiatury), więc każde słowo daje 12 bitów: hasło konta z 5 słów ma 60 bitów, a hasło odtworzenia z 6 słów 72 bity. Lista powstaje powtarzalnie ze słownika odmian SJP.PL i częstości słów w napisach filmowych (FrequencyWords), bez słów wulgarnych, obraźliwych, o śmierci, przemocy i chorobie, bez nazw własnych i bez wołania o pomoc; jest na licencji CC BY-SA 4.0 (`software/laptop/build/slowa/`). Na laptopie plik kont na pamięci USB zestawu (`keys/konta.json`) zawiera dla każdego konta losową sól i klucz danych opakowany kluczem z PBKDF2-HMAC-SHA256 (kryptografia systemu, co najmniej 600 000 iteracji); poprawne odpakowanie jest sprawdzeniem hasła, więc osobnego skrótu do logowania nie ma. Wielkość liter, odstępy i postać Unicode hasła nie mają znaczenia, bo hasło to słowa przepisywane z koperty. Na stanowisku odbiorczym skróty haseł leżą na nośniku stanowiska według [stanowiska](stanowisko-osp.md#komputer-i-aplikacja-stanowiska). Logowanie ma limit 5 nieudanych prób na minutę; panel nowo uruchomionego laptopa wczytuje konta z tej pamięci i nie każe ustawiać haseł.

Pamięć bez kont to nowy zestaw: przy przygotowaniu panel tworzy konto gospodarza, konta zastępców i hasło odtworzenia i pokazuje każde hasło jeden raz, z numerem koperty, do przepisania albo wydruku. Po otwarciu koperty osoba utrzymująca system, zalogowana w panelu, nadaje temu kontu nowe hasło do nowej koperty; stare przestaje działać. Gdy plik kont jest uszkodzony albo zginął, hasło odtworzenia otwiera kopię bazy, a panel tworzy nowe konta i nowe hasło odtworzenia. Czynności na stacji, logowania, nowe hasła i oddanie laptopa trafiają do dziennika w zaszyfrowanej bazie, więc wymagają zalogowania. Zastępcy mają te same uprawnienia co gospodarz. Hasła leżą w numerowanych zaklejonych kopertach przy stacji (hasła dyżurnych i hasło stanowiska: przy stanowisku odbiorczym); koperty sprawdza się w przeglądzie kwartalnym, a po otwarciu koperty hasło się zmienia. Dziennik działań operatora jest tylko do dopisywania. Stacja poziomu 1 nie ma kont: obsługę ogranicza fizyczny dostęp.

### Sieć lokalna i zapora

Laptop i router pochodzą z miejsca uruchomienia i nie są wcześniej przygotowane (D04). Router obiektu zapewnia DHCP i szyfrowanie WPA2 lub WPA3. Główna sieć Wi-Fi musi przepuszczać ruch do LAN, a izolacja telefonów od siebie jest dopuszczalna. Laptop jest klientem sieci LAN, najlepiej przez kabel. Aplikacja:

- wybiera interfejs z prywatnym adresem IPv4 i bramą (przy kilku: przewodowy);
- udostępnia stronę mieszkańca tylko na tym interfejsie, na porcie 8080 (gdy zajęty: na innym wolnym);
- pokazuje kod QR sieci Wi-Fi (`WIFI:T:WPA;S:…;P:…;;`, nazwa i hasło wpisane w panelu) oraz kod QR adresu `http://IP:8080`, także jako plakat A4 do wydruku.

Po zmianie adresu kody odświeżają się same. Panel pokazuje liczbę połączonych telefonów i rozpoznaje: brak przewodu, brak adresu, profil sieci publicznej w Windows, brak reguły zapory i brak połączeń po kilku minutach. Do każdego stanu podaje jedno zdanie, co zrobić dalej.

Telefony korzystają z głównej sieci Wi-Fi budynku, bo sieć gościnna zwykle nie widzi laptopa. Zarządca zgadza się na to pisemnie przy przygotowaniu obiektu i zmienia hasło Wi-Fi po zdarzeniu. Gdy laptop jest w sieci gościnnej (przez Wi-Fi), a telefony go w niej widzą, aplikacja proponuje ją jako pierwszą. Stacja, laptop i router nie muszą stać obok siebie: router jest tam, gdzie zamontował go zarządca, a laptop łączy się z nim kablem albo przez Wi-Fi. Gdy telefony w schronieniu nie mają zasięgu routera, zostaje tryb kiosku. Laptop ani stacja nie uruchamiają własnego serwera DHCP, DNS ani portalu przechwytującego (captive portal). Dziennik aplikacji nie zapisuje treści zgłoszeń, tokenów, adresów IP ani MAC.

Zapora Windows domyślnie blokuje połączenia przychodzące, a zgoda wymaga uprawnień administratora; zapora macOS i typowych dystrybucji Linuksa domyślnie ich nie blokuje. Aplikacja w Windows przed nasłuchem w LAN sprawdza, czy istnieje reguła WICI; bez niej nie otwiera portu, bo anulowany alert zapory zostawia reguły blokujące dla interpretera (`pythonw.exe` z pamięci USB), a reguły blokujące mają pierwszeństwo. Na żądanie gospodarza uruchamia przez okno UAC systemowe `netsh` z regułą tylko dla portu, na którym faktycznie słucha strona, i tylko dla sieci lokalnej (`localport=<port> remoteip=localsubnet`, wszystkie profile), bez ścieżki programu, bo litera dysku pamięci USB się zmienia; ten sam krok usuwa reguły blokujące, które Windows utworzył dla interpretera z bieżącej ścieżki pamięci (rozpoznane po ścieżce programu, bo nie mają nazwy WICI). Przy zamknięciu aplikacja proponuje usunięcie reguły. Bez uprawnień administratora panel mówi wprost, że telefony się nie połączą, i proponuje [tryb kiosku](#tryb-kiosku), a za zgodą właściciela laptopa system Linux z pamięci USB. Aplikacja nie obchodzi zapory bez zgody administratora.

## Strona mieszkańca

Nazwę sieci Wi-Fi, hasło i adres strony podają kody QR na ekranie laptopa albo plakat wydrukowany z panelu na miejscu ([sieć lokalna](#sieć-lokalna-i-zapora)). Formularz pokazuje adres obiektu bez możliwości zmiany i pyta tylko „gdzie w budynku”; odpowiedź trafia na początek opisu i liczy się do jego limitu. Licznik pod opisem pokazuje `zostalo_znakow`, przeliczone z limitu bajtów. Panel gospodarza pokazuje przy opisie ostrzeżenie `nie_wpisuj_nazwisk`.

Po wysłaniu strona pokazuje lokalny numer zgłoszenia (cztery cyfry, unikalne w laptopie) i tekst `zapisz_numer`, a następnie stan: `czeka_na_opiekuna`, `opiekun_polaczyl` (gdy gospodarz dołączył je do zgłoszenia SA1, także połączonego z innymi) albo `nie_wyslane`, potem etapy zgłoszenia SA1 z tabeli [Teksty ekranu](#teksty-ekranu), te same co na ekranie stacji. Dostęp do zgłoszenia daje tylko ciasteczko z tokenem; numer służy do rozmowy z gospodarzem, który sprawdza stan w panelu. Po utracie ciasteczka (inna przeglądarka, tryb prywatny) mieszkańca obsługuje gospodarz.


### Tryb kiosku

Gdy telefony nie mogą połączyć się z laptopem (zapora bez administratora, brak routera, izolacja Wi-Fi od LAN), strona mieszkańca działa w trybie kiosku na ekranie laptopa, pod adresem lokalnym, bez sieci i bez uprawnień administratora. Mieszkańcy zgłaszają się po kolei przy laptopie. Po wysłaniu strona pokazuje lokalny numer zgłoszenia i `zapisz_numer`, a po potwierdzeniu wraca do pustego formularza dla następnej osoby; nie trzyma ciasteczka mieszkańca, więc stan sprawdza się w rozmowie z gospodarzem po numerze. Tryb kiosku nie daje dostępu do panelu gospodarza: panel jest pod innym adresem lokalnym (inna nazwa hosta, osobne ciasteczka) i na czas kiosku wymaga ponownego logowania. Odnośnik START działa tylko raz, więc historia przeglądarki go nie zdradza; każde uruchomienie START dostaje od działającej aplikacji nowy odnośnik. Laptop jest zwykle laptopem właściciela z jego zalogowaną sesją, dlatego aplikacja otwiera stronę kiosku w osobnym oknie przeglądarki bez innych kart (tryb aplikacji, gdy przeglądarka go ma), a przy laptopie stale jest gospodarz albo zastępca.

## Protokół USB laptop–stacja

Pełny kontrakt (wersja `"usb":2`: koperta wiadomości, schematy poleceń i odpowiedzi, przyczyny odmów, limity czasu, synchronizacja z epoką i migawką, transfery w częściach, PRZENIEŚ STACJĘ i przykładowe przebiegi) jest w [protokole USB](protokol-usb.md); zamyka go D17. Interfejs danych CDC (w ESP32-S3 przez kontroler USB-OTG i TinyUSB, nie przez USB-Serial-JTAG) przenosi wiersze JSON do 1024 B. Stacja w konfiguracji węzła stanowiska używa tego protokołu tylko w trybie przygotowania; poza nim interfejs danych przenosi pakiety Reticulum do komputera stanowiska ([radio](radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)).

Zasady wiążące resztę specyfikacji: źródłem prawdy o zgłoszeniach i wiadomościach jest stacja; stacja odpowiada `stored` dopiero po COMMIT w FRAM; idempotencja opiera się na kluczu (`id`, `revision`), nie na numerze wiersza; nic w stacji nie czeka na laptop, a luka w pierścieniu zdarzeń prowadzi do migawki stanu. Laptop przechowuje intencję przekazania w SQLite, aż dostanie `stored`. Odłączenie przewodu w dowolnym momencie nie gubi ani nie podwaja zgłoszenia.

## Model zaufania i kluczy

**Tożsamość i losowość.** Tożsamość stacji generuje sama stacja przy pierwszym starcie z pustą pamięcią albo po ZNISZCZ DANE, zanim wyda kartę w trybie przygotowania. Rekord formatu FRAM ma znacznik zapisanej tożsamości; brak klucza przy tym znaczniku to uszkodzenie pamięci, nie nowa stacja: stos nie startuje i stacja nie nadaje (diagnostyka `identity_lost`), bo nowy klucz zmieniłby adres znany odbiorcy. Naprawa to ZNISZCZ DANE i ponowne przygotowanie z nową kartą u odbiorcy. Źródło losowości: w nRF52840 TRNG układu CC310; w ESP32-S3 `bootloader_random_enable()` (źródło SAR ADC) przy generowaniu kluczy i zasilaniu DRBG, z wyłączonym Wi-Fi i Bluetooth. Klucze i `id` tworzone w stacji pochodzą z CSPRNG z ziarnem ≥256 b; `id` tworzone w laptopie pochodzą z CSPRNG systemu operacyjnego. Próba T2: testy zdrowia źródła entropii (NIST SP 800-90B) i brak powtórzeń `id` w 10⁶ próbek.

**Karty.** W trybie przygotowania stacja eksportuje przez USB kartę stacji: pełny klucz publiczny tożsamości (64 B), skrót adresu LXMF, nazwę `WICI-xxxxxx` (sześć cyfr szesnastkowych, wielkimi literami, np. `WICI-4CBAAD`; aplikacje porównują nazwy bez rozróżniania wielkości liter), adres schronienia i odcisk do odczytu z ekranu. Aplikacja stanowiska importuje kartę (plik lub QR) po porównaniu odcisku z ekranem stacji. Karta odbiorcy zawiera dwie tożsamości odbiorcy, główną i zapasową, każdą ze skrótem adresu i pełnym kluczem publicznym (64 B) ([klucz odbiorcy](#model-zaufania-i-kluczy)). Aplikacja stanowiska eksportuje ją jako plik JSON `{"wici":"karta-odbiorcy","v":1,"main":{"lxmf":…,"key":…},"backup":{"lxmf":…,"key":…}}` (pola `main` i `backup` jak `receiver` w [protokole USB](protokol-usb.md#transfery-dzielone-na-części)); aplikacja laptopa rozpoznaje plik po polach `wici` i `v` i odrzuca inny z komunikatem. Stacja rejestruje klucze z kart przy starcie, więc weryfikacja podpisu nie zależy od odebrania ogłoszenia.

**Zaufanie na stanowisku.** Listę zaufanych stacji z ich kartami przechowuje baza aplikacji stanowiska na komputerze stanowiska; na jej podstawie aplikacja decyduje, czy wiadomość jest przyjmowana jako zaufana, czy trafia do kwarantanny ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Zatwierdzenie w kwarantannie dotyczy pojedynczej wiadomości i nie dodaje nadawcy do zaufanych. Dodanie stacji do listy wymaga karty stacji i zgody dwóch zalogowanych dyżurnych; usunięcie wykonuje jeden. Wiadomość z nieznanym kluczem (SOURCE_UNKNOWN) stanowisko zapisuje jako „do weryfikacji”, wysyła zapytanie o trasę i sprawdza podpis po nadejściu ogłoszenia. Kwarantanna w SQLite mieści najwyżej 4 wiadomości na nadawcę i 256 łącznie; nadmiar jest odrzucany. Wiadomości stacji usuniętej z listy trafiają do kwarantanny tak samo, ale są liczone (z powtórzeniami), a panel pokazuje przy nich alarm „możliwe przejęcie stacji”.

**Klucz odbiorcy.** Karta odbiorcy zawiera dwie tożsamości: główną i zapasową, każdą z własnym kluczem publicznym i własnym adresem LXMF. Stacja przyjmuje wiadomości wyłącznie od tożsamości aktywnej i tylko do niej wysyła zgłoszenia; po przygotowaniu aktywna jest główna. Obie należą do tego samego stanowiska odbiorczego (różnicę wobec odbiorcy zastępczego opisuje akapit niżej). Przełączenie na zapasową jest czynnością lokalną: gospodarz wybiera STAN → USŁUGI → KLUCZ ZAPASOWY, potwierdza `klucz_zapasowy` sekwencją GÓRA, DÓŁ, GÓRA, OK. Panel i USB nie mają tego polecenia. Polecenie przełączenia przychodzi wyłącznie słownie lub przez gońca, nigdy radiem, bo przejęte stanowisko mogłoby je nadać. Przełączenie jest nieodwracalne poza trybem przygotowania. Po nim stacja odrzuca wiadomości od tożsamości głównej, a niepotwierdzone intencje wysyła ponownie, z tym samym `id` i `revision`, do adresu zapasowego. Tożsamość zapasową generuje się offline podczas przygotowania stanowiska. Jej klucz prywatny trafia do zaplombowanej koperty u organizatora sieci jako paczka zaszyfrowana (AEAD) kluczem wyprowadzonym Argon2id z hasła tożsamości zapasowej (co najmniej 6 słów z listy); hasło leży w drugiej kopercie, przechowywanej w innym miejscu niż paczka i niż stanowisko. Po utracie albo przejęciu komputera lub nośnika z tożsamością główną aplikacja stanowiska na przygotowanym komputerze wczytuje paczkę z hasłem; ponieważ adres się zmienia, ogłasza go od razu po wczytaniu. Utrata którejkolwiek koperty wymaga nowej tożsamości zapasowej i nowych kart odbiorcy we wszystkich stacjach (D08). Nowego klucza stacja nigdy nie przyjmuje przez radio. Rotację klucza odbiorcy i nową kopertę zapasową określa plan kart (D08). Pakiety okazjonalne nie mają poufności przyszłej: przejęcie klucza odbiorcy ujawnia wcześniej nagrane zgłoszenia ([rozdział 07](../concept/07-zagrozenia-i-odpornosc.html)).

**Tożsamość zapasowa a odbiorca zastępczy.** Wydanie 0.5 rozróżnia dwie sytuacje. **Tożsamość zapasowa** należy do tego samego stanowiska odbiorczego: odpowiedzialność i dyżurni się nie zmieniają, zmienia się klucz i adres LXMF, np. po przejęciu komputera stanowiska. Stacja przełącza się na nią usługą KLUCZ ZAPASOWY ([klucz odbiorcy](#model-zaufania-i-kluczy)); to jest część wydania. **Odbiorca zastępczy** to inne stanowisko, które przejmuje odpowiedzialność za zgłoszenia, np. sąsiedniej gminy. Nie należy do wydania: stacja nie ma jego karty i nie przełącza się na niego, a zgłoszenia idą wtedy procedurą zastępczą z [koncepcji](../concept/02-scenariusze-i-organizacja.html#siec-i-odbiorca-zastepczy) (goniec, PMR446, służby na miejscu).

**Powtórzenia.** Odbiorca zachowuje trwale klucze odbioru (nadawca, id, revision, skrót treści) także po usunięciu treści. Stacja przechowuje w rejestrze zgłoszeń najwyższy `event` STATUS i REPLY dla każdego `id`, a dla BULLETIN zbiór ostatnich komunikatów z oknem czasu ([cykl życia](#cykl-życia-zgłoszenia)); nagrana wcześniej wiadomość odbiorcy nie cofa więc stanu ani nie wraca do skrzynki. Po zwolnieniu wpisu rejestru zamkniętego zgłoszenia wiadomości dla jego `id` są pomijane jako dotyczące `id` spoza rejestru. Tak określona ochrona spełnia wymaganie powtórzeń z D01; format SA1 0.5 się nie zmienia.

**Polecenia USB.** `configure`, `export`, `import` i aktualizacja oprogramowania działają wyłącznie w trybie przygotowania, włączanym przyciskiem pod numerowaną naklejką serwisową, z zapisem każdego wejścia w FRAM ([tryb przygotowania](#tryb-przygotowania-i-naklejka-serwisowa)). Paczka eksportu jest szyfrowana jednorazowym kluczem przeniesienia stacji docelowej (`target_key`; X25519 + HKDF-SHA-256 + ChaCha20-Poly1305) i nigdy nie zawiera jawnego klucza prywatnego. Stacja źródłowa przestaje nadawać po eksporcie, a tożsamość usuwa dopiero po potwierdzeniu importu przez stację docelową; stany i odtwarzanie po przerwaniu są w [protokole USB](protokol-usb.md#przeniesienie-stacji). `destroy`, `close` i `silence` przez USB wymagają potwierdzenia przyciskiem na stacji w ciągu 30 s. Każde polecenie USB trafia do dziennika zdarzeń stacji.

**Dane osobowe.** Kolejka stacji może zawierać dane o zdrowiu: pole `text` z panelu albo z wpisu przyciskami oraz kategorie 0–1 przy małej liczbie osób. Panel i ekran wpisu stacji ostrzegają `nie_wpisuj_nazwisk`.

| Miejsce | Zapisuje | Nie zapisuje |
|---|---|---|
| stacja (każdy poziom) | tylko wiadomości SA1, klucze i dziennik zdarzeń | IP, MAC, telefonu, nazwiska |
| laptop schronienia (poziomy 2–3) | SA1 + skrót tokenu + czas | IP, MAC, telefonu, nazwiska |
| komputer stanowiska | SA1 + adres nadawcy + czas odbioru + klucze odbioru + dziennik działań dyżurnych | IP, MAC, telefonu, nazwiska |

**ZAMKNIJ ZDARZENIE.** Po zakończeniu zdarzenia operacja eksportuje zaszyfrowane archiwum dla administratora danych (klucz publiczny z D13), a potem usuwa zgłoszenia, tokeny, eksporty i dzienniki z danymi na laptopie, kolejkę i skrzynkę na stacji oraz treść wiadomości na stanowisku. Tożsamości i klucze odbioru (ze skrótem SHA-256 treści i wysłanym potwierdzeniem) zostają. Na stacji operację uruchamia polecenie `close` z laptopa albo gospodarz z menu STAN → USŁUGI → ZAMKNIJ ZDARZENIE ([ekran](#ekran-i-przyciski-stacji)), więc zamknięcie zdarzenia w punktach nie wymaga laptopa. Próba w T2 i T8.

### Tryb przygotowania i naklejka serwisowa

Przycisk trybu przygotowania jest za otworem Ø3–4 mm we froncie, zaklejonym numerowaną naklejką VOID (plombą naklejaną); otwór daje dostęp tylko do przycisku, nie do płytki ani pól programowania. Przycisk naciska się rysikiem po przebiciu naklejki. Naklejka tylko ujawnia wejście, więc stacja sama zapisuje każde wejście w tryb przygotowania ([F113](../review.md)):

1. **Zapis przed włączeniem.** Wejście (przytrzymanie przycisku 3 s albo polecenie `PREP` w konsoli diagnostycznej programu stacji) najpierw zapisuje w jawnym obszarze FRAM rekord wejścia: numer wejścia (licznik, który tylko rośnie) i licznik czasu pracy. Dopiero po poprawnym zapisie z odczytem kontrolnym tryb zaczyna działać i brzęczyk daje krótki sygnał; bez zapisu stacja zostaje poza trybem, daje długi sygnał, wpisuje odmowę do dziennika zdarzeń i wyłącza dziennik FRAM (STAN pokazuje licznik „?”).
2. **Zmiany w wejściu.** Zatwierdzona konfiguracja (`configure`) dopisuje do rekordu bieżącego wejścia znacznik zmiany i pierwsze 16 bitów SHA-256 dokumentu konfiguracji (adres, karta odbiorcy, frazy, lista obiektów, rola). `export`, `import` i obraz oprogramowania dostają własne znaczniki wraz z ich implementacją.
3. **Trwałość.** Rekordy leżą w osobnym pierścieniu 10 rekordów 24 B ([pamięć FRAM](#pamięć-fram)), poza pierścieniem dziennika zdarzeń, więc zdarzenia diagnostyczne ich nie nadpisują. ZNISZCZ DANE i ZAMKNIJ ZDARZENIE ich nie kasują. Rekord z błędnym CRC mógł być najnowszym wejściem, więc licznik jest wtedy niepewny („?”). Następne wejście dostaje numer po najnowszym poprawnym rekordzie (albo 1) i znacznik `prep_restarted`, który przechodzi na kolejne wejścia; uszkodzone rekordy są czyszczone, a różnicę wobec ewidencji wykrywa przegląd. Nieudany zapis zmiany po zatwierdzonej konfiguracji też wyłącza dziennik FRAM, więc STAN pokazuje „?” zamiast nieprawdziwego „bez zmian”.
4. **Ekran.** STAN i PRZEKAZANIE ZMIANY pokazują `przygotowanie_wejscia` (liczba wejść i czas od ostatniego; `przygotowanie_wejscia_bez_czasu`, gdy wejść nie było albo czas jest nieznany po ZNISZCZ DANE) oraz zmianę ostatniego wejścia: `przygotowanie_konfiguracja` z 4 cyframi szesnastkowymi SHA-256 albo `przygotowanie_bez_zmian`. Konsola diagnostyczna podaje to samo poleceniem `JOURNAL` (`prep_entries`, `prep_at_s`, `prep_changes`, `prep_config_sha`, `prep_restarted`, `prep_corrupt`).
5. **Ewidencja.** Po każdej obsłudze osoba utrzymująca system zakłada nową naklejkę i wpisuje do ewidencji jej numer, stan licznika wejść i 4 cyfry SHA-256 konfiguracji z ekranu. Gospodarz w przeglądzie kwartalnym porównuje naklejkę, licznik i skrót z ewidencją; naruszona naklejka, wyższy licznik albo inny skrót oznaczają nieuzgodnione wejście i zgłoszenie do osoby utrzymującej system, która sprawdza konfigurację i kartę odbiorcy przed dalszą pracą stacji.

## Ekran i przyciski stacji

Ekran graficzny ma najwyżej 5 wierszy po ≤20 znaków, wysoki kontrast i wysokość wersalików ≥3,5 mm. W stacji pilotażowej daje to panel z pamięcią 2,7" (LS027B7DH01, 400 × 240, szerokość 58,8 mm) z krojem o stałej szerokości w komórce 20 × 40 px; wcześniejszy cel 4 mm wymagałby ≤17 znaków w wierszu (F80). Czytelność 3,5 mm w świetle dziennym, przy świetle latarki i z odległości 50 cm sprawdza T8 w pilotażu; większy panel albo krój skondensowany dla wydania rozstrzyga D15. Pełne teksty stanu nie mieszczą się razem na 5 wierszach, więc ekran główny używa krótkich form z tabeli, po jednym wierszu:

1. stan radia: `radio_wlaczone`, a gdy układ radiowy nie odpowiada albo nie przechodzi kontroli, `radio_awaria` (stacja zapisuje dalej zgłoszenia, alarm jak przy `brak_potwierdzenia`). Kontrola jest przy starcie i co 10 s w pracy, gdy radio nie nadaje. Obejmuje odpowiedź układu (identyfikacja albo stan) i ustawienie, które po resecie układu wraca do wartości innej niż ustawiona przez stację. W obrazach `bench-*` (wstrzymany wariant P1, [archiwum](../archiwum/README.md)) to numer części i słowo synchronizacji. W LoRa (SX1262) słowo synchronizacji RNode równe jest wartości domyślnej, więc kontrola sprawdza tryb pracy (`GetStatus`) i rodzaj pakietu (`GetPacketType` = LoRa; po resecie GFSK), co potwierdza implementacja interfejsu LoRa. Układ, który stracił konfigurację, dostaje ją od nowa. Układ po poleceniu diagnostycznym (reset, wyłączenie, zapis rejestru w trybie przygotowania) czeka na ponowną konfigurację. Brak ruchu w eterze nie jest awarią. Gdy radio działa, a stos sieciowy stacji nie działa, wiersz 1 to `brak_lacznosci`: zgłoszenia nie wychodzą, alarm jak przy `radio_awaria`. Stos nie działa, gdy jego stan jest inny niż praca i zatrzymanie przez ZNISZCZ DANE: nieudany samotest, brak zdrowego ziarna dla nowej tożsamości, FRAM, dziennik albo magazyn niedostępne, utrata tożsamości, nieudany start. Przy obu awariach naraz wiersz 1 to `radio_awaria` (przyczyna sprzętowa, sprawdzana co 10 s), a alarm `brak_lacznosci` przychodzi osobno;
2. kontakt z odbiorcą: `kontakt_krotki` albo `kontakt_ponad_krotki` (brak świeżego kontaktu nie jest awarią);
3. zasilanie: `zasilanie_aa` albo `zasilanie_12v`;
4. najstarsze niewysłane zgłoszenie: `kolejka_krotki` (pusty wiersz przy pustej kolejce);
5. nowe wiadomości: `nowe_krotki`.

W ciszy radiowej wiersze 1–3 zajmuje pełny tekst `cisza`, a wiersze 4–5 pokazują zasilanie i kolejkę. Aktywny alarm zajmuje cały ekran do potwierdzenia. Pełne teksty (`ostatni_kontakt`, `ogniwa_czas`) pokazuje STAN. `[czas]` podaje się w minutach do 99 MIN, potem w godzinach (H), od 48 H w dobach (D, do 99 D), aby krótkie formy mieściły się w 20 znakach. Do oceny: STAN pokazuje odchyłkę częstotliwości oszacowaną z odebranych ramek. Osoby niewidome zgłaszają przez gospodarza.

Podświetlenie ([elektronika](elektronika.md)): pierwsze naciśnięcie przy zgaszonym ekranie tylko zapala światło; każde naciśnięcie przedłuża je o 30 s; przy otwartej wiadomości świeci ≥60 s. Dioda „NOWA WIADOMOŚĆ / ALARM” miga krótkimi błyskami (w modelu energii około 1% czasu, [elektronika](elektronika.md)) do odczytu nowej wiadomości, do usunięcia przyczyny alarmu i przez cały czas ciszy radiowej.

**Alarmy.** Brak potwierdzenia od odbiorcy uruchamia alarm `brak_potwierdzenia` po czasie zależnym od pilności: 2 → 15 min, 1 → 1 h, 0 → 6 h. TEST ma osobny próg 30 min ([TEST](#wiadomości-sa1)). Teksty alarmów każą wysłać gońca tylko wtedy, gdy droga jest bezpieczna. Ocenę drogi i postępowanie, gdy wyjście jest niemożliwe, opisuje [instrukcja gospodarza](instrukcja.md#goniec). Dla pilności 2 drugi alarm `brak_odczytu` następuje, gdy po „odbiorca zapisał” w ciągu 30 min nie przyjdzie „odbiorca przeczytał” (brzmienie do potwierdzenia w T1).

Sygnał dźwiękowy alarmu powtarza się do potwierdzenia przyciskiem OK na ekranie alarmu. Potwierdzenie gasi dźwięk tego alarmu. Ekran alarmu wraca po każdym wybudzeniu ekranu, a dioda i wpis w PRZEKAZANIU ZMIANY pozostają do usunięcia przyczyny. Ekran alarmu przykrywa też wybór języka po włączeniu (po OK stacja wraca do wyboru), podaje bieżący czas od zapisu i schodzi sam, gdy przyczyna ustąpi przed potwierdzeniem. Dźwięk wraca przy nowym zdarzeniu (alarm innego zgłoszenia, drugi alarm pilności 2, nowa rewizja potwierdzonego zgłoszenia, np. wyższa pilność), a `wymien_ogniwa` przypomina dźwiękiem co 15 min. Cisza radiowa nie daje sygnału dźwiękowego, także przy włączeniu: włącza ją gospodarz przełącznikiem CISZA, a stan pokazują stały tekst i dioda. Cisza może trwać dni, a dźwięk w schronieniu skłaniałby do wyjęcia ogniw.

Magazyn, który nie wystartował albo zatrzymał się po błędzie zapisu FRAM, daje alarm `blad_pamieci` jak `radio_awaria` (ekran do OK, dioda do restartu). Alarmy zgłoszeń liczą się wtedy dalej z indeksu w RAM. Stos sieciowy, który nie wystartował, daje alarm `brak_lacznosci` jak `radio_awaria` (ekran do OK, dioda do restartu). Kolejność ekranów alarmu: `radio_awaria`, `blad_pamieci`, `brak_lacznosci`. Alarmów krytycznych (brak potwierdzenia, brak odczytu, `radio_awaria`, `brak_lacznosci`, `blad_pamieci`, `wymien_ogniwa`, cisza) nie da się wyłączyć ani ukryć. Wyciszenie zwykłego sygnału nowej wiadomości jest widoczne stale jako `dzwiek_wyciszony`.

**Start.** Radio i przekazywanie ruchu uruchamiają się niezależnie od ekranu i przycisków. Gotowość radiowa (≤60 s) nie czeka na żadną decyzję gospodarza, bo przekaźnik może pracować bez obsługi. Po włączeniu wyłącznikiem głównym pierwszy ekran to wybór języka. Po restarcie przez watchdog albo po przełączeniu źródła stacja używa języka zapisanego w FRAM i wraca do ekranu, na którym była.

Po wyborze języka stacja pokazuje `radio_wlaczone` i kontrolę adresu `adres_kontrola`. Przy NIE lub braku adresu pokazuje `adres_brak`, a do następnego wyboru języka ZGŁOSZENIE w menu pokazuje `adres_brak` zamiast kreatora (zmiany istniejących zgłoszeń i TEST działają). Opcjonalnie stacja ma listę adresów obiektów (do 8) wczytaną przy przygotowaniu. Wtedy po wyborze języka gospodarz wybiera obiekt z listy przyciskami, a potem stacja pokazuje kontrolę adresu tego obiektu. NIE wraca do listy, a WSTECZ na liście (żaden obiekt) daje `adres_brak`. Wybór przetrwa restart i wyłączenie.

Potem stacja proponuje TEST startowy; OK go planuje (`test_zaplanowany`, `test_wyslany`). Bez reakcji gospodarza TEST nie wychodzi. W trybie przygotowania ekran stale pokazuje `tryb_przygotowania`.

**Węzeł stanowiska.** Stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)) po wyborze języka pokazuje na ekranie głównym `radio_wlaczone`, `komputer_osp` albo `komputer_brak` oraz zasilanie; nie kontroluje adresu i nie proponuje TEST. Menu ma tylko STAN i JĘZYK. STAN pokazuje radio, liczniki (także pakiety USB w obu kierunkach), energię, wejścia w tryb przygotowania, wersję i nazwę `WICI-xxxxxx`; USŁUGI mają tylko WYCISZ DŹWIĘK i ZNISZCZ DANE. PRZEKAZANIE ZMIANY, OGŁOŚ ADRES, KLUCZ ZAPASOWY i ZAMKNIJ ZDARZENIE nie występują, bo stacja nie ma zgłoszeń ani adresu LXMF. CISZA działa jak w każdej stacji.

Przyciski: GÓRA, DÓŁ, OK, WSTECZ, duże i wyczuwalne, obsługiwane w rękawicach. Osobny przełącznik CISZA ma osłonę przed przypadkowym przełączeniem. Przycisk konfiguracji (tryb przygotowania) jest za otworem pod numerowaną naklejką serwisową ([tryb przygotowania](#tryb-przygotowania-i-naklejka-serwisowa)); pola programowania pozostają wewnątrz obudowy.

| Menu | Działanie |
|---|---|
| ZGŁOSZENIE | kreator: kategoria 0–9 z piktogramem → liczba osób → pilność (bez wartości domyślnej) → gotowa fraza, WŁASNY TEKST lub brak (kategoria 9: fraza albo własny tekst obowiązkowe) → podsumowanie; po wysłaniu ekran pokazuje etap i krótki numer |
| WIADOMOŚCI | etapy własnych zgłoszeń, odpowiedzi (REPLY) i komunikaty (BULLETIN) ze źródłem i czasem od odbioru; przy własnym zgłoszeniu: ZMIEŃ LICZBĘ OSÓB, ZMIEŃ PILNOŚĆ, POTRZEBA USTAŁA, ANULUJ WYSYŁKĘ |
| TEST | wysłanie TEST i wynik; WSTRZYMAJ i WZNÓW na prośbę odbiorcy z komunikatu |
| STAN | radio, liczniki, energia (`ogniwa_napiecie`, `ogniwa_czas`, napięcie 12 V), `ostatni_kontakt`, wejścia w tryb przygotowania (`przygotowanie_wejscia` i zmiana ostatniego wejścia), wersja, nazwa `WICI-xxxxxx`; PRZEKAZANIE ZMIANY; USŁUGI: OGŁOŚ ADRES, WYCISZ DŹWIĘK (po wyciszeniu WŁĄCZ DŹWIĘK), KLUCZ ZAPASOWY, ZAMKNIJ ZDARZENIE, ZNISZCZ DANE |
| JĘZYK/МОВА/LANGUAGE | polski, ukraiński, angielski; etykieta zawsze w trzech językach, bez spacji wokół ukośników (19 znaków) |

**Kreator zgłoszenia.** WSTECZ cofa o jeden krok. Przytrzymanie WSTECZ przez 2 s pokazuje `porzucic` (poza ekranem wpisu tekstu, niżej). Liczba osób: lista z liczbą i rzeczownikiem (`osoby_1`, `osoby_2`, `osoby_5`): „1 OSOBA, 2 OSOBY, 5 OSÓB, 10 OSÓB, 20 OSÓB, 50 OSÓB, 100 OSÓB, INNA LICZBA”, bez osobnego tytułu, żeby lista mieściła 5 wierszy. INNA LICZBA to wpis cyfra po cyfrze (setki, dziesiątki, jednostki). Przytrzymanie przycisku przyspiesza zmianę, a domyślnie stoi ostatnio użyta wartość. Pilność wybiera się z etykiet `pilnosc_2`, `pilnosc_1`, `pilnosc_0`. Pilność 2 wymaga potwierdzenia `pilnosc_2_potw`. Podsumowanie pokazuje piktogram i kategorię, liczbę osób, pilność słownie, frazę, adres i `podsumowanie_klawisze`.

Po 3 min bezczynności szkic zostaje zapisany, a stacja wraca do ekranu głównego. Tak samo wraca każdy inny ekran poza głównym, wyborem języka, alarmem i pytaniem polecenia USB (pytanie kończy się po 30 s odmową `not_confirmed`). Zmiana własnego zgłoszenia z WIADOMOŚCI (nowa rewizja) nie nadpisuje szkicu. Szkic wraca po wysłaniu albo porzuceniu rewizji. Ekran wyniku po wysłaniu zamyka się po bezczynności tak jak po OK, więc wysłane zgłoszenie nie wraca jako szkic. Nierozpoczęty szkic dostaje ostatnio użytą liczbę osób, także po rewizji. Po wysłaniu ekran pokazuje kolejne etapy z tabeli.

**Wpis tekstu.** WŁASNY TEKST to ostatnia pozycja listy fraz. Wpis ma dwa poziomy:

- na liście GÓRA i DÓŁ wybierają pozycję listy GOTOWE, SPACJA i grup znaków z tabeli [Grupy znaków wpisu](#teksty-ekranu), a OK otwiera grupę;
- w grupie GÓRA i DÓŁ wybierają znak (znacznik `^` pod znakiem, jak przy INNA LICZBA), OK go dopisuje i wraca do listy na tej samej grupie, a WSTECZ wraca do listy bez dopisania.

WSTECZ na liście usuwa ostatni znak, a przy pustym tekście wraca do listy fraz. Przytrzymanie WSTECZ na liście usuwa kolejne znaki (po 0,5 s co 150 ms, bez wyjścia z wpisu) i na tym ekranie nie pokazuje `porzucic`. SPACJA nie dopisuje spacji na początku ani drugiej z rzędu. GOTOWE usuwa spację z końca i przechodzi do podsumowania, a przy pustym tekście wraca do listy fraz. Kursor listy staje po wejściu na pierwszej grupie liter. Język ekranu wybiera alfabet: przy polskim i angielskim grupy PL, przy ukraińskim grupy UK. Cyfry i znaki interpunkcyjne są wspólne. Tekst ma najwyżej 48 znaków. Po ostatnim wolnym miejscu stacja nie dopisuje znaku.

Ekran pokazuje u góry koniec wpisanego tekstu z kursorem `_` (przy pustym tekście ostrzeżenie `nie_wpisuj_nazwisk`), pod nim `wpis_wolne`, a w dwóch dolnych wierszach listę albo grupę ze znacznikiem. Przy pełnym ostatnim wierszu kursor pojawia się dopiero z następnym znakiem, żeby wiersz nie pokazywał samego kursora. Na ekranie wpisu powrót do ekranu głównego następuje po 10 min bezczynności zamiast 3 min. Szkic z tekstem zostaje. Po alarmie albo pytaniu polecenia USB wpis wraca na tę samą pozycję listy i grupy. Tekst ginie przy restarcie stacji (watchdog, restart programowy, wyłączenie), bo szkic jest tylko w RAM. WSTECZ z podsumowania wraca do wpisu. Zmiana liczby osób albo pilności zachowuje własny tekst. Podpowiadanie słów ze słownika stacji rozważa się po zmierzeniu czasu wpisu w T8.

**Własne zgłoszenie.** ZMIEŃ LICZBĘ OSÓB i ZMIEŃ PILNOŚĆ tworzą nową rewizję, jak na stronie. POTRZEBA USTAŁA tworzy nową rewizję z frazą „potrzeba ustała”. ANULUJ WYSYŁKĘ jest dostępne tylko dopóty, dopóki zgłoszenie nie wyszło ze stacji (ekran `zapisane_w_stacji` albo `zapisane_w_ciszy` od utworzenia): oznacza intencję jako anulowaną i zapisuje to w dzienniku zdarzeń. Zgłoszenie, które stacja choć raz nadała, mogło dotrzeć do odbiorcy, nawet bez potwierdzenia, a odbiorca o anulowaniu by nie wiedział; dlatego po pierwszym nadaniu zamiast ANULUJ jest tylko POTRZEBA USTAŁA. Opis wpisany przyciskami nie zmienia się w rewizji; inny opis wymaga nowego zgłoszenia albo panelu laptopa.

**PRZEKAZANIE ZMIANY** (STAN) pokazuje najpierw stan stacji: ciszę, `radio_awaria`, `brak_lacznosci`, `blad_pamieci`, `adres_brak` po odpowiedzi NIE, nieprzeczytane wiadomości, energię, wyciszenie dźwięku i wejścia w tryb przygotowania (licznik i zmianę ostatniego wejścia, do porównania z ewidencją), a potem otwarte i niepotwierdzone zgłoszenia od najstarszego. Zgłoszenia, które nie mieszczą się w tekście, liczy ostatni wiersz „+N”.

**KLUCZ ZAPASOWY** (STAN → USŁUGI) przełącza stację na tożsamość zapasową tego samego odbiorcy z karty, tylko na polecenie przekazane słownie lub przez gońca ([klucz odbiorcy](#model-zaufania-i-kluczy)); pokazuje `klucz_zapasowy` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Nie służy do przejścia do innego stanowiska (odbiorcy zastępczego).

**ZAMKNIJ ZDARZENIE** (STAN → USŁUGI) pokazuje `zamknij_ostrzezenie` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Wykonuje to samo co potwierdzone polecenie `close` z laptopa ([ZAMKNIJ ZDARZENIE](#model-zaufania-i-kluczy)): w jednej transakcji nowa epoka zdarzeń i para (stara epoka, bieżący `head`) zapamiętana jak dla `close`, potem czyszczenie rejestru, skrzynki, pamięci zwolnionych wpisów i pierścienia zdarzeń. Niewysłane i niepotwierdzone zgłoszenia też znikają, a ich wysyłka się kończy. Gospodarz wykonuje operację tylko na polecenie gminy po odwołaniu stanu kryzysowego, przekazane słownie, przez gońca albo pisemnie; nigdy na podstawie wiadomości radiowej. Laptop podłączony później dostaje `snap_required` z przyczyną `epoch`. Po zamknięciu stacja wraca do ekranu głównego; tożsamość, karta odbiorcy, adres, frazy, dług ciszy, licznik wejść w tryb przygotowania, zbiór powtórzeń BULLETIN i `bulletin_floor` zostają.

**ZNISZCZ DANE** (STAN → USŁUGI) pokazuje `zniszcz_ostrzezenie` i wymaga sekwencji GÓRA, DÓŁ, GÓRA, OK. Nigdy nie uruchamia się na podstawie wiadomości radiowej; polecenie odbiorcy przychodzi tylko słownie lub przez gońca. T8: brak przypadkowego uruchomienia w 10 próbach w rękawicach.

### Teksty ekranu

Jedyna kanoniczna lista tekstów stacji i strony mieszkańca; inne dokumenty cytują teksty tylko z niej, a T1 sprawdza zgodność. Ekran łamie tekst na wiersze ≤20 znaków; tekst dłuższy niż 5 wierszy dzieli się na kolejne ekrany (do sprawdzenia w T1). [x], [n], [m], [mm], [czas] i [xxxx] to wartości wstawiane przez stację. W tekście ciągłym dokumentów dopuszczalne są małe litery w cudzysłowie. Słowo „OKOŁO” pisze się w całości, bo „OK.” myliłoby się z przyciskiem. Kolumny UK i EN są tłumaczeniem roboczym: przed T1 sprawdza je osoba, dla której ukraiński lub angielski jest językiem ojczystym, a T8 z osobą ukraińskojęzyczną; zmiana brzmienia nie może wydłużyć krótkich form ponad 20 znaków. Jednostki `[czas]`: MIN / H / D po polsku i angielsku, ХВ / ГОД / Д po ukraińsku. Napięcie w wersji EN ma kropkę dziesiętną. „ПРИБЛИЗНО” i „ABOUT” pisze się w całości jak „OKOŁO”. Karta obsługi ([karta](../obsluga/karta-stacji.html)) cytuje teksty z tej tabeli.

| ID | Ekran PL | Ekran UK | Ekran EN | Znaczenie |
|---|---|---|---|---|
| `radio_wlaczone` | RADIO WŁĄCZONE | РАДІО УВІМКНЕНО | RADIO ON | stacja odbiera i może nadawać |
| `radio_awaria` | RADIO: AWARIA | РАДІО: НЕСПРАВНЕ | RADIO: FAULT | wiersz 1 ekranu głównego, gdy układ radiowy nie działa; zgłoszenia są zapisywane, ale nie wychodzą |
| `brak_lacznosci` | BRAK ŁĄCZNOŚCI | НЕМАЄ ЗВ'ЯЗКУ | NO COMMUNICATION | wiersz 1 ekranu głównego, gdy stos sieciowy stacji nie działa (usterka stacji, nie brak kontaktu z odbiorcą); zgłoszenia są zapisywane, ale nie wychodzą |
| `jezyk_pl` | POLSKI | POLSKI | POLSKI | ekran wyboru języka, zawsze w tym języku |
| `jezyk_uk` | УКРАЇНСЬКА | УКРАЇНСЬКА | УКРАЇНСЬКА | ekran wyboru języka, zawsze w tym języku |
| `jezyk_en` | ENGLISH | ENGLISH | ENGLISH | ekran wyboru języka, zawsze w tym języku |
| `cisza` | CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC | РАДІОТИША – СТАНЦІЯ НЕ ПЕРЕДАЄ. ТЕРМІНОВО: ПОСИЛЬНИЙ | RADIO SILENCE – NOT TRANSMITTING. URGENT: RUNNER | wiersze 1–3 ekranu głównego w ciszy radiowej |
| `ostatni_kontakt` | OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU | ОСТАННІЙ КОНТАКТ З ОДЕРЖУВАЧЕМ: [czas] ТОМУ | LAST CONTACT WITH RECIPIENT: [czas] AGO | STAN: czas od ostatniej uwierzytelnionej wiadomości od aktywnej tożsamości odbiorcy (RECEIVED, STATUS, REPLY lub BULLETIN); brak świeżego kontaktu nie jest awarią |
| `ostatni_kontakt_ponad` | OSTATNI KONTAKT Z ODBIORCĄ: PONAD [czas] TEMU | ОСТАННІЙ КОНТАКТ З ОДЕРЖУВАЧЕМ: ПОНАД [czas] ТОМУ | LAST CONTACT WITH RECIPIENT: OVER [czas] AGO | STAN po włączeniu bez RTC: dolne oszacowanie |
| `kontakt_krotki` | KONTAKT [czas] TEMU | КОНТАКТ [czas] ТОМУ | CONTACT [czas] AGO | ekran główny, wiersz 2 |
| `kontakt_ponad_krotki` | KONTAKT >[czas] TEMU | КОНТАКТ >[czas] ТОМУ | CONTACT >[czas] AGO | ekran główny, wiersz 2, po włączeniu bez RTC |
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
| `brak_potwierdzenia_bez_czasu` | BRAK POTWIERDZENIA – CZAS OCZEKIWANIA NIEZNANY. GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA | НЕМАЄ ПІДТВЕРДЖЕННЯ – ЧАС ОЧІКУВАННЯ НЕВІДОМИЙ. ПОСИЛЬНИЙ З ФОРМОЮ, ЯКЩО ДОРОГА БЕЗПЕЧНА | NO CONFIRMATION – WAITING TIME UNKNOWN. RUNNER WITH THE FORM IF THE ROUTE IS SAFE | po restarcie, gdy czas przerwy zasilania jest nieznany; nie zmienia progów alarmu |
| `brak_odczytu` | ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – GONIEC Z FORMULARZEM, JEŚLI DROGA BEZPIECZNA | ОДЕРЖУВАЧ НЕ ПРОЧИТАВ УЖЕ 30 ХВ – ПОСИЛЬНИЙ З ФОРМОЮ, ЯКЩО ДОРОГА БЕЗПЕЧНА | NOT READ BY RECIPIENT FOR 30 MIN – RUNNER WITH THE FORM IF THE ROUTE IS SAFE | alarm krytyczny, tylko pilność 2; brzmienie do potwierdzenia w T1 |
| `dzwiek_wyciszony` | DŹWIĘK WYCISZONY | ЗВУК ВИМКНЕНО | SOUND MUTED | zwykły sygnał wyciszony; ekran główny, wiersz 4 przy pustej kolejce, oraz STAN i PRZEKAZANIE ZMIANY |
| `adres_ogloszony` | ADRES ZOSTANIE OGŁOSZONY | АДРЕСУ БУДЕ ОГОЛОШЕНО | ADDRESS WILL BE ANNOUNCED | po OGŁOŚ ADRES (STAN → USŁUGI); w ciszy radiowej ogłoszenie wychodzi po jej odwołaniu |
| `adres_nie_ogloszony` | STACJA NIE NADAJE – ADRES NIE OGŁOSZONY. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA | СТАНЦІЯ НЕ ПЕРЕДАЄ – АДРЕСУ НЕ ОГОЛОШЕНО. ФОРМА. ПОСИЛЬНИЙ, ЯКЩО ДОРОГА БЕЗПЕЧНА | STATION NOT TRANSMITTING – ADDRESS NOT ANNOUNCED. FORM. RUNNER IF THE ROUTE IS SAFE | po OGŁOŚ ADRES, gdy stos sieciowy stacji nie działa; żadne zgłoszenie nie wyjdzie radiem |
| `test_zaplanowany` | TEST ZAPLANOWANY ZA OKOŁO [mm] MIN – NIE WYŁĄCZAJ. WSTECZ = ANULUJ | ТЕСТ ЗАПЛАНОВАНО ПРИБЛИЗНО ЧЕРЕЗ [mm] ХВ – НЕ ВИМИКАЙТЕ. НАЗАД = СКАСУВАТИ | TEST SCHEDULED IN ABOUT [mm] MIN – DO NOT SWITCH OFF. BACK = CANCEL | TEST startowy w losowym oknie |
| `test_wyslany` | TEST WYSŁANY – CZEKA NA ODBIORCĘ | ТЕСТ ВІДПРАВЛЕНО – ЧЕКАЄ НА ОДЕРЖУВАЧА | TEST SENT – WAITING FOR RECIPIENT | TEST nadany, brak RECEIVED |
| `test_wstrzymany` | TEST WSTRZYMANY PRZEZ ODBIORCĘ | ТЕСТ ПРИЗУПИНЕНО НА ПРОХАННЯ ОДЕРЖУВАЧА | TEST PAUSED AT RECIPIENT'S REQUEST | gospodarz wybrał TEST → WSTRZYMAJ po komunikacie odbiorcy |
| `adres_kontrola` | ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE | АДРЕСА: [x] – ЦЕ ЦЕ МІСЦЕ? OK = ТАК / НАЗАД = НІ | ADDRESS: [x] – IS THIS THE PLACE? OK = YES / BACK = NO | kontrola adresu przy starcie |
| `adres_brak` | STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO | СТАНЦІЯ НЕ МАЄ ВАШОЇ АДРЕСИ – ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | STATION DOES NOT HAVE YOUR ADDRESS – USE THE PAPER FORM | odpowiedź NIE albo brak adresu |
| `porzucic` | PORZUCIĆ ZGŁOSZENIE? OK = TAK | СКАСУВАТИ ЗАЯВКУ? OK = ТАК | DISCARD REQUEST? OK = YES | przytrzymanie WSTECZ 2 s w kreatorze |
| `osoby_1` | [n] OSOBA | [n] ОСОБА | [n] PERSON | kreator, lista liczby osób: liczba z rzeczownikiem w liczbie pojedynczej (PL: 1; UK: 1, 21, 31…) |
| `osoby_2` | [n] OSOBY | [n] ОСОБИ | [n] PEOPLE | jak wyżej: PL i UK 2–4, 22–24…, bez 12–14; EN każda liczba poza 1 |
| `osoby_5` | [n] OSÓB | [n] ОСІБ | [n] PEOPLE | jak wyżej: pozostałe liczby (5, 10, 20, 50, 100…) |
| `pilnosc_2` | ZAGROŻENIE ŻYCIA | ЗАГРОЗА ЖИТТЮ | DANGER TO LIFE | urgency 2 |
| `pilnosc_1` | PILNE – KILKA GODZIN | ТЕРМІНОВО – КІЛЬКА ГОДИН | URGENT – A FEW HOURS | urgency 1 |
| `pilnosc_0` | W CIĄGU DOBY | ПРОТЯГОМ ДОБИ | WITHIN A DAY | urgency 0 |
| `pilnosc_2_potw` | ZAGROŻENIE ŻYCIA: 1) UDZIEL PIERWSZEJ POMOCY 2) DZIAŁA TELEFON? 112 3) BEZPIECZNA DROGA? GONIEC. OK = WYŚLIJ TEŻ RADIEM | ЗАГРОЗА ЖИТТЮ: 1) НАДАЙТЕ ПЕРШУ ДОПОМОГУ 2) ПРАЦЮЄ ТЕЛЕФОН? 112 3) БЕЗПЕЧНА ДОРОГА? ПОСИЛЬНИЙ. OK = НАДІСЛАТИ ТАКОЖ ПО РАДІО | DANGER TO LIFE: 1) GIVE FIRST AID 2) PHONE WORKS? 112 3) SAFE ROUTE? RUNNER. OK = ALSO SEND BY RADIO | potwierdzenie pilności 2 |
| `podsumowanie_klawisze` | OK = WYŚLIJ, WSTECZ = POPRAW | OK = НАДІСЛАТИ, НАЗАД = ВИПРАВИТИ | OK = SEND, BACK = EDIT | pierwsze wiersze podsumowania; przy dłuższej treści wskaźnik dalszego ciągu |
| `kolejka_pelna` | KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO | ЧЕРГА ПОВНА – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ | QUEUE FULL – REQUEST NOT SAVED. USE THE PAPER FORM | 256 wpisów rejestru zajętych i żaden nie jest [zamknięty](#cykl-życia-zgłoszenia) |
| `blad_pamieci` | BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA | ПОМИЛКА ПАМ'ЯТІ СТАНЦІЇ – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ФОРМА. ПОСИЛЬНИЙ, ЯКЩО ДОРОГА БЕЗПЕЧНА | STATION MEMORY ERROR – REQUEST NOT SAVED. FORM. RUNNER IF THE ROUTE IS SAFE | błąd zapisu FRAM; także ekran alarmu, gdy magazyn nie wystartował albo się zatrzymał |
| `brak_lacznosci_alarm` | BRAK ŁĄCZNOŚCI – ZGŁOSZENIA NIE WYCHODZĄ. FORMULARZ. GONIEC, JEŚLI DROGA BEZPIECZNA | НЕМАЄ ЗВ'ЯЗКУ – ЗАЯВКИ НЕ ВІДПРАВЛЯЮТЬСЯ. ФОРМА. ПОСИЛЬНИЙ, ЯКЩО ДОРОГА БЕЗПЕЧНА | NO COMMUNICATION – REQUESTS NOT SENT. FORM. RUNNER IF THE ROUTE IS SAFE | ekran alarmu `brak_lacznosci` (stos sieciowy stacji nie działa); wiersz 1 ekranu głównego ma krótki tekst `brak_lacznosci` |
| `ogniwa_czas` | OGNIWA: OKOŁO [x] H PRACY | БАТАРЕЇ: ПРИБЛИЗНО [x] ГОД РОБОТИ | CELLS: ABOUT [x] H OF OPERATION | szacowany czas pracy |
| `wymien_ogniwa` | WYMIEŃ OGNIWA W CIĄGU 1 H | ЗАМІНІТЬ БАТАРЕЇ ПРОТЯГОМ 1 ГОД | REPLACE CELLS WITHIN 1 H | alarm krytyczny |
| `wylaczanie` | WYŁĄCZANIE – CZEKAJ, ZAPISUJĘ | ВИМКНЕННЯ – ЗАЧЕКАЙТЕ, ЗБЕРІГАЮ | SWITCHING OFF – WAIT, SAVING | kończenie zapisu przed wyłączeniem |
| `mozna_wyjac` | MOŻNA WYJĄĆ OGNIWA | МОЖНА ВИЙНЯТИ БАТАРЕЇ | CELLS CAN BE REMOVED | zapis zakończony |
| `odlaczone_12v` | 12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO I PRZYTRZYMAJ OK | 12 В ВІДКЛЮЧЕНО – ЗАНИЗЬКА НАПРУГА. ПІДКЛЮЧІТЬ ЗАРЯДЖЕНЕ ДЖЕРЕЛО І УТРИМУЙТЕ OK | 12 V DISCONNECTED – VOLTAGE TOO LOW. CONNECT A CHARGED SOURCE AND HOLD OK | odcięcie podnapięciowe 12 V z histerezą (powrót sam przy ≥12,4 V); praca z ogniw. Tekst do zmiany w programie stacji: bez „PRZYTRZYMAJ OK” |
| `tryb_przygotowania` | -- TRYB SERWISOWY -- | - СЕРВІСНИЙ РЕЖИМ - | -- SERVICE MODE -- | stały pasek w inwersji (pierwszy wiersz) w trybie przygotowania; kreski wyróżniają go od treści ekranu, w UK pojedyncze, bo podwójne przekroczyłyby 20 znaków |
| `przygotowanie_wejscia` | TRYB SERWISOWY: WEJŚCIA [n], OSTATNIE [czas] TEMU | СЕРВІСНИЙ РЕЖИМ: ВХОДІВ [n], ОСТАННІЙ [czas] ТОМУ | SERVICE MODE: ENTRIES [n], LAST [czas] AGO | STAN i PRZEKAZANIE ZMIANY: licznik wejść w tryb przygotowania i czas od ostatniego ([naklejka serwisowa](#tryb-przygotowania-i-naklejka-serwisowa)) |
| `przygotowanie_wejscia_bez_czasu` | TRYB SERWISOWY: WEJŚCIA [n] | СЕРВІСНИЙ РЕЖИМ: ВХОДІВ [n] | SERVICE MODE: ENTRIES [n] | jak wyżej, gdy wejść nie było albo czas od wejścia jest nieznany (po ZNISZCZ DANE) |
| `przygotowanie_konfiguracja` | OSTATNIE WEJŚCIE: NOWA KONFIGURACJA [xxxx] | ОСТАННІЙ ВХІД: НОВА КОНФІГУРАЦІЯ [xxxx] | LAST ENTRY: NEW CONFIGURATION [xxxx] | ostatnie wejście zapisało konfigurację; [xxxx] to pierwsze 4 cyfry szesnastkowe jej SHA-256 |
| `przygotowanie_bez_zmian` | OSTATNIE WEJŚCIE: BEZ ZMIAN | ОСТАННІЙ ВХІД: БЕЗ ЗМІН | LAST ENTRY: NO CHANGES | ostatnie wejście nie zmieniło konfiguracji |
| `klucz_zapasowy` | PRZEŁĄCZYĆ NA KLUCZ ZAPASOWY ODBIORCY? TYLKO NA POLECENIE SŁOWNE LUB PRZEZ GOŃCA. NIEODWRACALNE | ПЕРЕМКНУТИ НА РЕЗЕРВНИЙ КЛЮЧ ОДЕРЖУВАЧА? ЛИШЕ ЗА УСНИМ НАКАЗОМ АБО ЧЕРЕЗ ПОСИЛЬНОГО. НЕЗВОРОТНО | SWITCH TO RECIPIENT'S BACKUP KEY? ONLY ON A SPOKEN ORDER OR ONE BROUGHT BY A RUNNER. IRREVERSIBLE | przed sekwencją GÓRA, DÓŁ, GÓRA, OK |
| `komputer_osp` | KOMPUTER [czas] TEMU | ПК [czas] ТОМУ | COMPUTER [czas] AGO | węzeł stanowiska, ekran główny, wiersz 2: czas od ostatniego pakietu od komputera stanowiska |
| `komputer_brak` | BRAK KOMPUTERA | НЕМАЄ ЗВ'ЯЗКУ З ПК | NO COMPUTER | węzeł stanowiska, ekran główny, wiersz 2: brak pakietu od komputera od startu stacji |
| `zamknij_ostrzezenie` | ZAMKNĄĆ ZDARZENIE? ZGŁOSZENIA I WIADOMOŚCI ZNIKNĄ ZE STACJI. TYLKO NA POLECENIE GMINY | ЗАКРИТИ ПОДІЮ? ЗАЯВКИ Й ПОВІДОМЛЕННЯ ЗНИКНУТЬ ЗІ СТАНЦІЇ. ЛИШЕ ЗА НАКАЗОМ ГМІНИ | CLOSE THE EVENT? REQUESTS AND MESSAGES WILL BE REMOVED FROM THE STATION. ONLY ON THE MUNICIPALITY'S ORDER | przed sekwencją GÓRA, DÓŁ, GÓRA, OK (STAN → USŁUGI → ZAMKNIJ ZDARZENIE) |
| `zniszcz_ostrzezenie` | GROŹBA PRZEJĘCIA? USUNIĘCIE DANYCH NIEODWRACALNE. START BEZ KONFIGURACJI | ЗАГРОЗА ЗАХОПЛЕННЯ? ВИДАЛЕННЯ ДАНИХ НЕЗВОРОТНЕ. СТАРТ БЕЗ КОНФІГУРАЦІЇ | CAPTURE THREAT? DATA DELETION IS IRREVERSIBLE. RESTART WITHOUT CONFIGURATION | przed sekwencją GÓRA, DÓŁ, GÓRA, OK |
| `pytanie_cisza_wlacz` | LAPTOP: WŁĄCZYĆ CISZĘ RADIOWĄ? OK = TAK / WSTECZ = NIE | НОУТБУК: УВІМКНУТИ РАДІОТИШУ? OK = ТАК / НАЗАД = НІ | LAPTOP: TURN RADIO SILENCE ON? OK = YES / BACK = NO | potwierdzenie `silence` z panelu ([protokół USB](protokol-usb.md#polecenia-laptopa)) |
| `pytanie_cisza_wyjatek` | LAPTOP: WŁĄCZYĆ CISZĘ RADIOWĄ Z WYJĄTKIEM ZGŁOSZENIA NR [xxxx]? OK = TAK / WSTECZ = NIE | НОУТБУК: УВІМКНУТИ РАДІОТИШУ, КРІМ ЗАЯВКИ № [xxxx]? OK = ТАК / НАЗАД = НІ | LAPTOP: TURN RADIO SILENCE ON EXCEPT REQUEST NO. [xxxx]? OK = YES / BACK = NO | potwierdzenie `silence` z wyjątkiem dla jednego zgłoszenia |
| `pytanie_cisza_wylacz` | LAPTOP: WYŁĄCZYĆ CISZĘ RADIOWĄ? TYLKO PO ODWOŁANIU. OK = TAK / WSTECZ = NIE | НОУТБУК: ВИМКНУТИ РАДІОТИШУ? ЛИШЕ ПІСЛЯ СКАСУВАННЯ. OK = ТАК / НАЗАД = НІ | LAPTOP: TURN RADIO SILENCE OFF? ONLY AFTER IT IS LIFTED. OK = YES / BACK = NO | potwierdzenie `silence` z `"on":false` |
| `pytanie_zamknij` | LAPTOP: ZAMKNĄĆ ZDARZENIE? ZGŁOSZENIA I WIADOMOŚCI ZNIKNĄ ZE STACJI. OK = TAK / WSTECZ = NIE | НОУТБУК: ЗАКРИТИ ПОДІЮ? ЗАЯВКИ Й ПОВІДОМЛЕННЯ ЗНИКНУТЬ ЗІ СТАНЦІЇ. OK = ТАК / НАЗАД = НІ | LAPTOP: CLOSE THE EVENT? REQUESTS AND MESSAGES WILL BE REMOVED FROM THE STATION. OK = YES / BACK = NO | potwierdzenie `close` (ZAMKNIJ ZDARZENIE) |
| `pytanie_zniszcz` | LAPTOP: ZNISZCZYĆ DANE? NIEODWRACALNE – STACJA PRZESTANIE DZIAŁAĆ. OK = TAK / WSTECZ = NIE | НОУТБУК: ЗНИЩИТИ ДАНІ? НЕЗВОРОТНО – СТАНЦІЯ ПЕРЕСТАНЕ ПРАЦЮВАТИ. OK = ТАК / НАЗАД = НІ | LAPTOP: DESTROY DATA? IRREVERSIBLE – STATION WILL STOP WORKING. OK = YES / BACK = NO | potwierdzenie `destroy` |
| `odcisk_klucza` | ODCISK KLUCZA STACJI: [x] – PORÓWNAJ Z LAPTOPEM. OK = ZAMKNIJ | ВІДБИТОК КЛЮЧА СТАНЦІЇ: [x] – ПОРІВНЯЙТЕ З НОУТБУКОМ. OK = ЗАКРИТИ | STATION KEY FINGERPRINT: [x] – COMPARE WITH THE LAPTOP. OK = CLOSE | odcisk przy `card` w trybie przygotowania; [x] to 4 grupy po 4 cyfry szesnastkowe |
| `stopka_komunikatu` | NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA | НАКАЗ ВИЙТИ АБО ЕВАКУЮВАТИСЯ? ПІДТВЕРДІТЬ ПО СУСПІЛЬНОМУ РАДІО АБО В ПОСИЛЬНОГО | ORDER TO LEAVE OR EVACUATE? CONFIRM ON PUBLIC RADIO OR WITH THE RUNNER | stopka każdego BULLETIN |
| `czeka_na_opiekuna` | CZEKA NA GOSPODARZA | ЧЕКАЄ НА КООРДИНАТОРА | WAITING FOR THE WARDEN | strona: zgłoszenie zapisane w laptopie |
| `opiekun_polaczyl` | GOSPODARZ POŁĄCZYŁ ZE ZGŁOSZENIEM NR [xxxx] | КООРДИНАТОР ОБ'ЄДНАВ ІЗ ЗАЯВКОЮ № [xxxx] | WARDEN MERGED IT WITH REQUEST NO. [xxxx] | strona: połączone z powtarzalnym |
| `nie_wyslane` | NIE WYSŁANE – PODEJDŹ DO GOSPODARZA | НЕ ВІДПРАВЛЕНО – ПІДІЙДІТЬ ДО КООРДИНАТОРА | NOT SENT – SEE THE WARDEN | strona: gospodarz nie przekazał zgłoszenia |
| `zapisz_numer` | ZAPISZ NUMER [xxxx] – PODAJ GOSPODARZOWI DO SPRAWDZENIA STANU | ЗАПИШІТЬ НОМЕР [xxxx] – НАЗВІТЬ ЙОГО КООРДИНАТОРУ, ЩОБ ПЕРЕВІРИТИ СТАН | NOTE NUMBER [xxxx] – GIVE IT TO THE WARDEN TO CHECK THE STATUS | strona: po wysłaniu, z lokalnym numerem |
| `zostalo_znakow` | ZOSTAŁO OKOŁO [n] ZNAKÓW | ЗАЛИШИЛОСЯ ПРИБЛИЗНО [n] ЗНАКІВ | ABOUT [n] CHARACTERS LEFT | strona i panel: licznik pod opisem, z limitu bajtów |
| `nie_wpisuj_nazwisk` | NIE WPISUJ NAZWISK | НЕ ВПИСУЙТЕ ПРІЗВИЩ | DO NOT ENTER SURNAMES | strona, panel i ekran wpisu stacji przy pustym tekście: ostrzeżenie przy opisie |
| `wpis_wolne` | WOLNE ZNAKI: [n] | ВІЛЬНІ ЗНАКИ: [n] | CHARS LEFT: [n] | ekran wpisu tekstu stacji: wolne miejsce z 48 znaków |
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
| ZAMKNIJ ZDARZENIE | ЗАКРИТИ ПОДІЮ | CLOSE EVENT |
| ZNISZCZ DANE | ЗНИЩИТИ ДАНІ | DESTROY DATA |
| ZMIEŃ LICZBĘ OSÓB | КІЛЬКІСТЬ ЛЮДЕЙ | CHANGE PEOPLE COUNT |
| ZMIEŃ PILNOŚĆ | ЗМІНИТИ ТЕРМІНОВІСТЬ | CHANGE URGENCY |
| POTRZEBA USTAŁA | ПОТРЕБА ЗНИКЛА | NEED RESOLVED |
| ANULUJ WYSYŁKĘ | СКАСУВАТИ ВІДПРАВКУ | CANCEL SENDING |
| INNA LICZBA (liczba osób) | ІНША КІЛЬКІСТЬ | OTHER NUMBER |
| WŁASNY TEKST (lista fraz) | СВІЙ ТЕКСТ | OWN TEXT |
| GOTOWE (wpis tekstu) | ГОТОВО | DONE |
| SPACJA (wpis tekstu) | ПРОБІЛ | SPACE |

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

Grupy znaków wpisu tekstu, po pozycjach GOTOWE i SPACJA. Ekran pokazuje grupę ze spacjami między znakami. Grupy PL obejmują też Q, V i X (wyrazy obce, nazwy), grupy UK apostrof.

| Grupa | PL i EN | UK |
|---|---|---|
| 1 | AĄBCĆ | АБВГҐ |
| 2 | DEĘFG | ДЕЄЖЗ |
| 3 | HIJKL | ИІЇЙК |
| 4 | ŁMNŃO | ЛМНОП |
| 5 | ÓPQRS | РСТУФ |
| 6 | ŚTUVW | ХЦЧШЩ |
| 7 | XYZŹŻ | ЬЮЯ' |
| 8 | 01234 | 01234 |
| 9 | 56789 | 56789 |
| 10 | .,-?/ | .,-?/ |

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

**Ogłoszenia adresu.** Stacja ogłasza swój adres LXMF przy starcie (z losowym opóźnieniem 0–120 s), na polecenie gospodarza (STAN → USŁUGI lub panel) i automatycznie, gdy intencja do odbiorcy nie dostała potwierdzenia transportowego po 2 próbach LXMF, najwyżej raz na 30 min. Aplikacja stanowiska ogłasza adres odbiorcy co 6 h ±20%, po starcie i po ponownym połączeniu ze stacją; stacja w konfiguracji węzła stanowiska nie ma adresu LXMF i go nie ogłasza. W ciszy radiowej nie ma ogłoszeń. Tablicę tras, znane tożsamości i buforowane ogłoszenia stacja zapisuje w FRAM i odtwarza po restarcie. Próba T3 i T5: zimny start po restarcie przekaźnika i przejście z trasy A–stanowisko na A–B–stanowisko bez ręcznego ogłoszenia. Nazwa wyświetlana ma postać `WICI-xxxxxx` (6 cyfr szesnastkowych skrótu tożsamości) i nie zawiera adresu ani nazwy miejsca. Emisje transportu Reticulum, np. zapytania o trasę, pozostają i liczy się je w próbie T3.

Każda stacja z włączonym transportem retransmituje ogłoszenia innych stacji, więc przy zimnym starcie sieci N stacji kanał przenosi rzędu N² ogłoszeń, a każda stacja zużywa na nie część własnego długu ciszy. Limit ogłoszeń interfejsu radiowego (`announce_cap` Reticulum) wynosi 2%: czas nadawania ogłoszeń, własnych i przekazywanych, nie przekracza 2% czasu zegarowego interfejsu. Reticulum liczy czas nadawania z przepływności zadeklarowanej przez interfejs, dlatego interfejs LoRa deklaruje przepływność odpowiadającą rzeczywistemu czasowi nadawania ogłoszenia (wartość ustala T3). Ogłoszenia ponad limit czekają w kolejce ogłoszeń, a nowsze ogłoszenie tego samego celu zastępuje starsze. Limit 2% liczy sam czas nadawania. Czas kanału ogłoszeń (z długiem ciszy) wlicza się do wspólnej puli z K2, najwyżej 60% ([dostęp do kanału](radio.md#dostęp-do-kanału)).

Ogłoszenie trwa w LoRa SF7 0,359 s. Model bez strat daje dla 50 stacji 2500 nadań ogłoszeń. To około 15 min czasu kanału w jednym obszarze kolizji i około 3,9 min nadawania z ciszą w każdej stacji (50 × 0,359 s × 13). Przy limicie 2% 50 ogłoszeń przechodzi przez jeden skok w około 15 min. Razem z zapytaniami o trasę do odbiorcy (0,4–7,2 min) i wymianą TEST (około 2,4 min) zimny start 50 stacji zajmuje w LoRa SF7 18–25 min, czyli 43–59% okna TEST startowego, a 30 stacji 28–38% ([wyniki modelu](../../software/reference/wyniki.json), `cold_start_announces_lora_sf7`; [koncepcja, rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html#pojemnosc-sieci)). Sieć powyżej około 30 stacji w jednym obszarze kolizji uruchamia się etapami według planu sieci. Ostateczny limit ogłoszeń i podział na etapy ustala T5 z próbą skali.

**Cisza radiowa.** Polecenie ciszy radiowej wydaje wójt (od wprowadzenia stanu wojennego i w czasie wojny jako organ obrony cywilnej) na podstawie decyzji wojewody lub organów wojskowych albo wynika ono z nakazu wydanego w stanie nadzwyczajnym. Do schronień przekazuje je odbiorca komunikatem BULLETIN i gońcem. Ciszę odwołuje ten sam organ. Gospodarz włącza ją przełącznikiem CISZA na stacji albo w panelu. Przełącznik na stacji ma pierwszeństwo przed panelem. Interfejs radiowy nic nie nadaje, łącznie z ruchem przekazywanym i ogłoszeniami. Odbiór, zapis i kolejka działają dalej. Ekran pokazuje stale `cisza`, a nowe zgłoszenie `zapisane_w_ciszy`. Wyłączenie ciszy jest wyłącznie ręczne, po odwołaniu przez organ.

Wyjątek dla pojedynczego zgłoszenia ustawia się tylko z panelu (poziom 2) i tylko przy ciszy operacyjnej ustawionej z panelu, gdy polecenie wprost go dopuszcza. Przełącznik CISZA na stacji wyklucza wyjątek. Wyjątek obejmuje całą wymianę tej jednej pary (id, revision), czyli najnowszej rewizji zgłoszenia w chwili potwierdzenia na stacji: zapytanie o trasę, pakiet zgłoszenia, jego ponowienia i potwierdzenia pakietów dla przychodzących RECEIVED i STATUS tej rewizji. Nie obejmuje ogłoszeń, REPLY ani nowej rewizji (dla niej gospodarz ustawia wyjątek ponownie). Poleceń diagnostycznych i pomiarowych stacji cisza nie przepuszcza nigdy.

Wyjątek działa tylko wtedy, gdy cała droga do odbiorcy nadaje. Przy ciszy w całej sieci przekaźniki też milczą, więc w praktyce działa tylko przy bezpośrednim połączeniu ze stanowiskiem odbiorczym, które samo nie jest w ciszy. Panel pokazuje to ograniczenie przed ustawieniem wyjątku. Wyjątek nie dotyczy zakazu używania urządzeń nadawczych w stanie wojennym lub wyjątkowym; wtedy podstawową procedurą jest goniec. Stacja zapisuje wyjątek w dzienniku zdarzeń, a gospodarz w dzienniku papierowym. Fizyczną pewność ciszy daje wyłączenie zasilania stacji; wtedy stacja także nie odbiera.

**Szyfrowanie w spoczynku.** Na laptopie baza, jej kopia na pamięci USB i eksporty są szyfrowane losowym kluczem danych: AES-256-CBC z HMAC-SHA256, szyfrowanie, potem uwierzytelnienie. Szyfr pochodzi z kryptografii systemu (Windows CNG, macOS CommonCrypto, Linux libcrypto), więc format jest ten sam na każdym systemie. Klucz danych jest opakowany osobno dla każdego konta kluczem = PBKDF2(hasło konta, plik `keys/zestaw.key` z pamięci USB zestawu i sól). Dzięki temu inny laptop otwiera kopię zwykłym logowaniem gospodarza albo zastępcy, a sama pamięć USB bez hasła nie wystarcza. Plik kont i opakowania leżą jednak na tej pamięci, więc kto ją zabierze, może zgadywać hasła poza aplikacją, bez limitu prób. Kopię chroni wtedy siła hasła (5 słów z listy 4096 słów, 60 bitów) i liczba iteracji PBKDF2, a limit 5 prób na minutę chroni tylko logowanie w panelu.

Kolejne opakowanie daje samo hasło odtworzenia z koperty ([protokół USB](protokol-usb.md#przeniesienie-stacji)). Leży ono w pliku kont i w nagłówku każdej kopii, więc utrata pliku kont nie odbiera danych. Klucz danych nie trafia na dysk laptopa, jest tylko w pamięci działającej aplikacji. Dlatego aplikacja nie używa magazynu systemowego (DPAPI, Keychain), który nie miałby czego chronić (2026-10-21). Zmiana hasła konta wymienia tylko jego opakowanie.

Stacja przechowuje klucz tożsamości, kartę odbiorcy, adres, kolejkę i skrzynkę. Kolejka może zawierać dane o zdrowiu ([dane osobowe](#model-zaufania-i-kluczy)). Oprogramowanie układowe włącza ochronę odczytu pamięci mikrokontrolera (np. APPROTECT w nRF52840, szyfrowanie pamięci flash w ESP32-S3). Wykonanie z nRF52840 wymaga rewizji 3 (kod wykonania Fx0) z APPROTECT według Nordic IN-141 i MDK ≥8.40.2. Starsze rewizje mają znane obejście ochrony (IN-133). Rekordy w FRAM są szyfrowane AEAD kluczem (KEK) przechowywanym w chronionej pamięci MCU ([trwałość](#trwałość-i-potwierdzenia)), więc wylutowanie FRAM nie ujawnia kolejki ani karty odbiorcy. To szyfrowanie jest wymagane przed wydaniem, nie przed pilotażem.

Panel otwiera bazę dopiero po zalogowaniu, bo klucz danych odpakowuje hasło konta. Otwarta baza SQLite pracuje w pamięci procesu. Na dysk laptopa i na pamięć USB trafiają wyłącznie zaszyfrowane migawki, więc na dysku cudzego laptopa nie ma bazy w postaci jawnej także po awarii bez „Oddaj laptop”. Migawka to serializacja SQLite zapisywana do dwóch plików na zmianę, z numerem pokolenia i historią sesji w danych uwierzytelnianych MAC, z `fsync`, a w macOS z `F_FULLFSYNC` (zapis kopii w [pakiecie USB](#pakiet-usb)). Migawka jest trwałym zapisem w rozumieniu tej specyfikacji: zmiana jest potwierdzona dopiero po `fsync` migawki na dysku. Zabranie działającego laptopa z zalogowanym panelem daje dostęp do danych. Przed przejęciem całego stanowiska chroni wyłącznie ZNISZCZ DANE albo zniszczenie pamięci. SQLCipher i zaszyfrowany wolumen odrzucono 2026-10-21 (zależność spoza biblioteki standardowej albo uprawnienia administratora). Ostateczne parametry zapadają w D13.

**ZNISZCZ DANE.** To jedyna definicja tej operacji w specyfikacji. Wykonuje się ją wyłącznie przy groźbie przejęcia stacji lub stanowiska, także na polecenie odbiorcy przekazane słownie lub przez gońca, nigdy na podstawie wiadomości radiowej. Fakt zapisuje się w dzienniku papierowym, bo dziennik w bazie znika razem z nią.

Na stacji (STAN → USŁUGI albo panel z potwierdzeniem przyciskiem na stacji) program stacji zatrzymuje stos, zeruje w FRAM cały obszar magazynów (tożsamość, konfigurację z kartą odbiorcy i adresem, rejestr, kolejkę, skrzynkę, tablice stosu, pierścień zdarzeń USB) oraz kasuje dziennik zdarzeń stacji, licznik czasu pracy i ustawienia ekranu, a potem restartuje stację (`Store::destroy`, `firmware/src/store.cpp`, `journal.cpp`). Zostają: dług ciszy ([radio](radio.md)), rezerwacja numerów zapisu, rekord formatu FRAM (`fram_format`) i rekordy wejść w tryb przygotowania, bo bez nich naklejka serwisowa nie ujawniałaby wejść. Po wprowadzeniu szyfrowania rekordów FRAM operacja usuwa najpierw KEK z pamięci MCU (kryptograficzne wymazanie); program pilotażu go jeszcze nie ma.

Na laptopie operacja zatrzymuje przekazywanie, zamyka bazę (klucz danych znika z pamięci aplikacji) i usuwa zaszyfrowane migawki i eksporty z dysku. Kopie i pliki kont usuwa z pamięci USB, jeśli pod jej ścieżką jest nadal pamięć tego zestawu. Migawka zapisywana w chwili operacji nie trafia już na pamięć. W panelu operację uruchamia zalogowane konto w zakładce „Zestaw”, po dwóch potwierdzeniach. Podłączona stacja dostaje `destroy` i pyta o OK ([protokół USB](protokol-usb.md)), a laptop niszczy swoje dane od razu, bez czekania na przycisk, i do ponownego uruchomienia nie otwiera ani nie tworzy zestawu. Bez podłączonej stacji panel podaje, jak zniszczyć dane z jej menu.

Nadpisanie pamięci flash i SSD nie gwarantuje usunięcia, dlatego decyduje usunięcie klucza. Wobec odczytu samej pamięci USB skuteczne jest tylko jej fizyczne zniszczenie, które nakazuje instrukcja. Operacja usuwa też licznik czasu pracy i ustawienia ekranu. Jest nieodwracalna, a całość trwa najwyżej 1 minutę. Potem stacja restartuje bez konfiguracji: bez kodu IFAC nie nadaje (przekazywanie ruchu także stoi), a do pracy wraca tylko przez tryb przygotowania z nową konfiguracją, jako nowa stacja z nową tożsamością i kartą. Na komputerze stanowiska operację opisuje [stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska).

**Języki i dostępność.** Ekran stacji i strona mieszkańca są dostępne po polsku, ukraińsku i angielsku. Język wybiera się na pierwszym ekranie po starcie; poza kreatorem zgłoszenia przytrzymanie WSTECZ przez 3 s otwiera wybór języka. Wybór języka nie wymaga przeładowania ani połączenia z internetem. Odpowiedzi i komunikaty od odbiorcy przychodzą po polsku. Kategorie mają piktogramy i są przesyłane jako liczby, więc dyżurny widzi kategorię, liczbę osób i lokalizację niezależnie od języka opisu. Litery ukraińskie zajmują w UTF-8 po 2 B, tak jak polskie znaki diakrytyczne, więc opis zgłoszenia mieści około 48 takich znaków. Strona używa semantycznego HTML, działa z czytnikiem ekranu i przy powiększeniu tekstu do 200%.

## Pakiet USB

```text
USB/
  INSTRUKCJA.html
  START-WINDOWS.exe
  START-MAC.app/               # jeden dla Apple Silicon i Intel; wybiera środowisko po procesorze
  START-LINUX.sh, START-LINUX.desktop
  linux-x86_64/                 # obraz startowy, system plików tylko do odczytu
  runtime/python314.zip        # wspólna biblioteka standardowa wszystkich systemów, przycięta do używanych modułów
  runtime/<platform>/          # interpreter, potrzebne moduły binarne, plik ._pth
  app/                         # strona, panel, program startowy, protokół USB do stacji
  firmware/                    # podpisane obrazy oprogramowania stacji (w pilotażu tylko ESP32-S3); tylko w trybie przygotowania
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, skróty, polecenie budowy, lista plików; podpisany
  keys/                        # zestaw.key i konta.json: opakowania klucza danych dla kont i hasła odtworzenia; nie trafia do kopii publicznych
  kopia/                       # zaszyfrowana kopia bazy laptopa: kopia-a, kopia-b, odrzucone w konflikcie konflikt-*
  export/                      # zaszyfrowana paczka przeniesionej stacji
```

Pamięć ma system plików FAT32, bo czytają go wszystkie systemy i oprogramowanie UEFI. Bez obrazu startowego Linuksa pakiet zajmuje około 84 MB, z czego około 81 MB to interpretery czterech środowisk (Windows x64, macOS arm64 i x86_64, Linux x86_64). Budowa przerywa się powyżej 90 MB. Pakiet START uruchamia się z pamięci bez instalowania i bez uprawnień administratora. Na każdym systemie kopiuje środowisko swojego systemu (około 20 MB z 81 MB interpreterów pakietu) do katalogu użytkownika i uruchamia aplikację z dysku (ponownie, gdy pamięć ma inną budowę). Pamięć jest więc potrzebna przy starcie i logowaniu, przy zapisie kopii i przy „Oddaj laptop”, a nie przez cały czas pracy: laptop z dwoma portami USB-C, z których jeden zajmuje ładowarka, obsługuje stację, a pamięć wkłada się na chwilę.

Na Linuksie podstawową drogą jest `sh START-LINUX.sh` w terminalu otwartym w katalogu pamięci. GNOME nie uruchamia plików `.desktop` z katalogu, FAT z opcją `showexec` nie pozwala oznaczyć ich jako wykonywalne, a terminal pokazuje błędy. `START-LINUX.desktop` (z terminalem) zostaje dla menedżerów plików, które go uruchamiają. Błędy startu i nieudane otwarcie przeglądarki aplikacja pokazuje sama w oknie systemowym (z adresem panelu) i kończy się wtedy kodem 3. Programy START pokazują własny komunikat tylko przy innym niezerowym kodzie. START-MAC kończy się 2 s po uruchomieniu aplikacji w tle, żeby macOS nie uznawał go za wciąż otwarty i kolejne kliknięcie uruchamiało nowy START.

Pamięć zapisuje się bez znacznika kwarantanny macOS. Archiwum pobrane przeglądarką i rozpakowane na Macu przenosi znacznik na pliki. Wtedy macOS uruchamia START-MAC z kopii tymczasowej (App Translocation), bez reszty pamięci, a START-MAC pokazuje polecenie naprawy. Pamięć przygotowaną na Macu oczyszcza się ze znacznika przed wydaniem poleceniem `xattr -dr com.apple.quarantine` na jej katalogu głównym. Obsługiwane systemy: Windows 10 i 11 x64, macOS od 10.15 (Intel) i od 11 (Apple Silicon), Linux x86_64 z glibc ≥2.17.

Pakiet stanowiska ma te same zasady budowy (przypięte wersje, podpisany manifest, interpreter i biblioteki w `runtime/`, źródła i licencje, bez instalowania przez pip), ale nie ma `keys/`, `export/` ani programów START, bo klucz nośnika pochodzi z hasła stanowiska. Zamiast strony i protokołu USB do stacji zawiera aplikację stanowiska z Reticulum `e40191b` i LXMF `c3ff2d6` w Pythonie, ich licencje i źródła oraz konfigurację interfejsu KISS ([stanowisko odbiorcze](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)). Stan aplikacji stanowiska leży na nośniku stanowiska, nie na pamięci pakietu.

Zaszyfrowane migawki bazy leżą na dysku laptopa, w katalogu stanu użytkownika, a nie na exFAT ani FAT32. W Linuksie z pamięci USB leżą na osobnej partycji ext4 tej pamięci. Każdy zestaw ma osobny podkatalog `baza/` nazwany od skrótu klucza danych, więc dwa zestawy na jednym laptopie nie nadpisują sobie migawek. Kopia na pamięci USB (FAT32) jest drugą kopią, nie jedyną.

Laptop jest przyniesiony na miejscu, wraca do właściciela i może zostać wymieniony w trakcie zdarzenia (D04). Dlatego aplikacja zapisuje też zaszyfrowaną kopię bazy na pamięci USB zestawu:

- serializacja SQLite w pamięci;
- szyfrowanie;
- zapis do jednego z dwóch plików na zmianę (`kopia-a`, `kopia-b`; zawsze do tego, w którym nie leży ostatnio zapisana kopia) z numerem pokolenia i historią sesji objętymi MAC;
- `fsync` pliku i katalogu.

Historia sesji to lista uruchomień aplikacji z pokoleniem, od którego każde zaczęło; zmiana nagłówka bez klucza jest wykrywana. Uszkodzony albo przerwany zapis zostawia poprzednią kopię w drugim pliku.

Migawki są łączone: zmiany, które przyjdą w trakcie zapisu migawki, obejmuje następna. Każde żądanie czeka na pierwszą migawkę, która je obejmuje, więc przy wielu telefonach naraz nie powstaje kolejka pełnych zapisów. Potwierdzenie zmiany (np. 201 dla zgłoszenia) czeka tylko na migawkę na dysku. Kopię na pamięci USB, zwykle wolniejszej, aplikacja zapisuje w tle zaraz po każdej migawce na dysku (zmiany z czasu tego zapisu obejmuje następna kopia). Przed „Oddaj laptop” oraz ZAMKNIJ ZDARZENIE aplikacja czeka, aż pamięć będzie miała wszystkie zmiany. Wyrwanie pamięci w trakcie zapisu zostawia na niej poprzednią pełną kopię w drugim pliku. Zmian, których pamięć jeszcze nie ma, nie traci się, bo są w migawce na dysku. Panel pokazuje czas ostatniej kopii na pamięci i ostrzega, gdy zapis się nie udaje.

Aplikacja działa z kopii środowiska na dysku, więc wyjęcie pamięci jej nie zamyka (wcześniej, przy pracy z pamięci, macOS zamykał ją od razu: próba z obrazem dysku FAT32, 2026-10-21). Bez pamięci kopia na pamięci przestaje być aktualna i panel pokazuje jej wiek; dane czekają w migawce na dysku. Ponowne włożenie pamięci i START kontynuują zapis kopii, także pod inną literą dysku albo innym punktem montowania. Gdy aplikacja działa dalej, ponowny START z pamięci przekazuje jej nową ścieżkę, a ona przenosi tam zapis kopii, jeśli najnowsza kopia na tej pamięci jest kopią, którą obecna sesja kontynuuje; kopia zapisana w międzyczasie na innym laptopie zostaje do wyboru przy następnym starcie. Przed każdym zapisem i usunięciem plików na pamięci zalogowana aplikacja sprawdza, że pod tą ścieżką jest pamięć zestawu z chwili logowania (skrót SHA-256 pliku `keys/zestaw.key`); na innej pamięci nic nie zapisuje ani nie usuwa i ostrzega w panelu.

Przy starcie aplikacja porównuje migawkę na dysku z kopią na pamięci i pracuje na tej, która jest kontynuacją drugiej (ta sama historia sesji i nowsze pokolenie albo późniejsza sesja zaczęta od co najmniej tak nowego pokolenia), więc laptop, który wrócił po awarii z własną, starszą bazą, nie nadpisuje nowszej i nie rozdwaja historii. Gdy żadna nie jest kontynuacją drugiej, panel każe wybrać, a odrzuconą zapisuje na pamięci USB jako `konflikt-…`; nowe pokolenia są wyższe od każdej znalezionej kopii, także odrzuconej. Kopię otwiera logowanie gospodarza albo zastępcy. Pamięć z kluczem zestawu albo z kopią, ale bez pliku kont, panel pokazuje jako uszkodzoną i otwiera tylko hasłem odtworzenia; nowego zestawu na pamięci z kopią nie tworzy, bo nowy klucz danych nadpisałby kopie, których nikt już nie otworzy. Polecenie „Oddaj laptop” w panelu zapisuje ostatnią kopię na pamięci USB i dopiero wtedy usuwa z dysku migawki i eksporty, tak jak ZNISZCZ DANE na laptopie, ale bez naruszania kopii i kont na pamięci; bez pamięci USB odmawia, bo dane zostałyby tylko na tym laptopie.

PRZENIEŚ STACJĘ (tylko w trybie przygotowania) wymaga sprawnej stacji źródłowej. Przenosi tożsamość, licznik czasu pracy, konfigurację, rejestr zgłoszeń, pamięć zwolnionych wpisów, skrzynkę i zbiór powtórzeń BULLETIN w paczce zaszyfrowanej kluczem przeniesienia stacji docelowej; kroki, potwierdzenia i postępowanie po przerwaniu opisuje [protokół USB](protokol-usb.md#przeniesienie-stacji). W każdej chwili nadaje najwyżej jedna z dwóch stacji. Baza laptopa przechodzi przez zaszyfrowaną kopię na pamięci USB, opisaną wyżej. Nie ma wcześniejszej kopii tożsamości, bo dwie stacje z tą samą tożsamością nie mogą istnieć jednocześnie. Uszkodzona lub utracona stacja nie daje się przenieść: stacja zapasowa dostaje nową tożsamość, nową kartę stacji dyżurni dodają do listy zaufanych w aplikacji stanowiska, a starą tożsamość z niej usuwają. Stacja stanowiska nie ma tożsamości odbiorcy, więc nie wymaga PRZENIEŚ STACJĘ: zastępuje ją dowolna stacja w konfiguracji węzła stanowiska ([stanowisko odbiorcze](stanowisko-osp.md#stacja-stanowiska)). [Serializacja SQLite](https://www.sqlite.org/c3ref/serialize.html).

### Aktualizacja oprogramowania stacji

Obraz przychodzi przez USB z laptopa (transfer `firmware`, [protokół USB](protokol-usb.md#transfery-dzielone-na-części)), tylko w trybie przygotowania (przycisk pod naklejką serwisową, wejście zapisane w FRAM), bez otwierania obudowy głównej. Nie ma DFU, UF2 ani pobierania przez UART bez podpisu. Klucz wydania jest przechowywany offline, a podpis składa się po odtworzeniu kompilacji (T7).

| Element | ESP32-S3 (pilotaż) | nRF52840 (opcja wydania, D14) |
|---|---|---|
| podpis obrazu | Secure Boot V2, RSA-3072 PSS (jedyny schemat V2 w ESP32-S3); do 3 skrótów kluczy w eFuse, nieużyte gniazda unieważnione przy przygotowaniu | MCUboot, Ed25519 albo ECDSA-P256 |
| gniazda obrazu | dwa gniazda OTA (`ota_0`, `ota_1`) po 3 MiB w pamięci flash 8 MiB + `otadata`; obraz ≤3 MiB | gniazdo główne i zapasowe MCUboot w pamięci wewnętrznej albo zewnętrznej (do D14) |
| szyfrowanie flash, JTAG | szyfrowanie flash w trybie Release, eFuse wyłączające JTAG, tryb bezpiecznego pobierania | APPROTECT (rewizja 3, IN-141) |
| ochrona przed cofnięciem | `secure_version` w eFuse: 16 kroków na całe życie układu | licznik bezpieczeństwa MCUboot |

Przebieg: stacja zapisuje obraz do nieaktywnego gniazda, sprawdza SHA-256 i podpis, oznacza gniazdo jako oczekujące i odpowiada `ok`. Restart wykonuje dopiero po potwierdzeniu przyciskiem OK. Nowy obraz startuje jako niepotwierdzony. Potwierdza się sam po teście startowym: odczyt i kontrola FRAM, kontrola układu radiowego, start stosu i ekranu, w ≤120 s. Zanik zasilania albo restart przed potwierdzeniem przywraca poprzedni obraz (wycofanie programu rozruchowego). Zanik w czasie zapisu do gniazda zostawia stary obraz bez zmian, a laptop zaczyna transfer od nowa.

Format rekordów FRAM ma wersję w nagłówku. Nowy obraz czyta rekordy starszej wersji i do potwierdzenia zapisuje wszystkie rekordy, także nowe, w starym formacie. Na nowy format przechodzi dopiero po potwierdzeniu. Wycofanie nie zastaje więc danych w formacie, którego stary obraz nie zna. Bieżąca wersja formatu (`fram_format`) leży w jawnym rekordzie obok licznika czasu, a podpisany nagłówek obrazu podaje najwyższą wersję, którą obraz czyta. Po potwierdzeniu i przejściu na nowy format stacja odrzuca przy `xfer_commit` każdy obraz, który tej wersji nie czyta (`rejected` z `format`), także przy przywróceniu wprost. Wydanie 0.5 nie ma migracji formatu wstecz. Powrót do takiego obrazu wymaga ZNISZCZ DANE i ponownego przygotowania stacji.

Ochrona przed cofnięciem: program rozruchowy odrzuca obraz o `secure_version` niższym od zapisanego w eFuse. Wartość podnosi się tylko w wydaniu, które usuwa podatność, i dopiero po potwierdzeniu obrazu, nigdy w zwykłej aktualizacji, bo liczba kroków jest ograniczona. Zwykła aktualizacja może więc wrócić do starszej wersji tej samej klasy bezpieczeństwa, jeśli czyta bieżący format FRAM. Aplikacja laptopa odrzuca obraz starszy od zainstalowanego, chyba że osoba utrzymująca system wybierze przywrócenie wprost.

Oprogramowanie pilotażu jest dziś budowane jako Arduino (platforma pioarduino). Biblioteki ESP-IDF w Arduino są skompilowane z góry i nie pozwalają włączyć Secure Boot V2, szyfrowania flash ani wycofania obrazu, więc obraz z tymi funkcjami buduje się w ESP-IDF z Arduino jako komponentem. Taki obraz jest wymagany przed wydaniem. W pilotażu obraz wgrywa zespół projektu na stacje, które pozostają jego własnością; zabezpieczenia obrazu nie należą do [minimum pilotażu](odbior.md#minimum-pilotażu), a przegląd stacji pilotażowych sprawdza wersję obrazu, naklejkę serwisową i licznik wejść w tryb przygotowania.

Konsola UART i logi diagnostyczne są wyłączone w wydaniu. `build-manifest.json` jest podpisany (Ed25519 lub minisign), a odcisk klucza jest na karcie przeglądu. Klucz podpisu manifestu jest w menedżerze haseł projektu, a podpis składa CI przy tagu wydania, tylko z chronionego środowiska z wymaganym zatwierdzeniem. Przed pilotażem poziomów 2–3 START-MAC.app ma podpis Developer ID z notaryzacją, a START-WINDOWS.exe podpis Authenticode z programu SignPath Foundation dla projektów otwartych (wydawca w certyfikacie: SignPath Foundation; plik ma zasób z nazwą i wersją produktu).

Pakiet START utrzymuje komputer w stanie pracy podczas działania strony, z włączonym ekranem: na cudzym laptopie wygaszony ekran zwykle kończy się blokadą hasłem właściciela. Uśpienie laptopa wyłącza tylko stronę i panel; stacja pracuje dalej. Po wznowieniu aplikacja wykonuje `sync` ze stacją.

Przed dystrybucją pakiety muszą zostać zbudowane i przetestowane na każdej architekturze. W schronieniu nie instaluje się pakietów przez pip. Po próbie zgodności wydanie przypina dokładne archiwa lub commity wraz z ich skrótami. Podczas uruchamiania nie pobiera się wersji `latest`.

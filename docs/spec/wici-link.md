# WICI-Link: protokół łącza sieci stacji

**Stan: implementacja przed próbą D21, 2026-11-01.** Nośnik radiowy dla [szwu transportu](transport.md). Obowiązuje dopiero po rozstrzygnięciu D21 ([warunek przyjęcia](transport.md#warunek-przyjęcia)).

## Założenia

WICI-Link jest protokołem łącza i tras dla zamkniętej sieci jednej gminy (albo jej części), w której:

- wszystkie stacje i tożsamości odbiorcy są znane z planu sieci i kart z przygotowania, a klucze nigdy nie przychodzą przez radio;
- ruch płynie tylko między stacjami schronień a stanowiskiem odbiorczym, w obie strony; schronienia nie piszą do siebie nawzajem;
- stacje stoją w stałych miejscach, a trasy można zmierzyć przed kryzysem (krok 5);
- każda włączona stacja przekazuje ruch innych (W23).

Protokół używa profilu LoRa pilotażu bez zmian ([radio](radio.md#profil-lora-pilotażu)) i wszystkich reguł [dostępu do kanału](radio.md#dostęp-do-kanału): długu ciszy 12t zapisanego w FRAM, wolnego kanału przez 50 ms i CAD przed nadaniem, limitu 10% i klas K0–K2. Protokół nie używa ramek RNode. Koperta ([transport](transport.md)) o długości do 164 B mieści się w jednej ramce; dłuższa wiadomość SA1 jest dzielona na dwie szyfrowane części.

## Ramka

```
 0       1        3        5        7       8        10      11
 +-------+--------+--------+--------+-------+--------+-------+-----------+-----------+--------+------------+
 | ver/t | net_id | l_src  | l_dst  | hops  | seq    | opts  | ładunek   | podpis    | MAC(8) | tag pary(8) |
 +-------+--------+--------+--------+-------+--------+-------+-----------+-----------+--------+------------+
                                                                          tylko DATA            tylko unicast
 ver/t: bity 7–6 wersja (2), bity 5–3 typ, bity 2–0 flagi (bit 0 ACKREQ, bit 1 DOWN, bit 2 zarezerwowany, musi być 0)
 net_id: numer sieci z przygotowania (u16, big-endian, jak wszystkie pola)
 l_src, l_dst: numery stacji nadającej i następnego skoku (0xFFFF = wszyscy sąsiedzi; 0 i 0xFFFF nie są numerami stacji)
 hops: bity 7–4 liczba wykonanych skoków, bity 3–0 limit skoków (TTL, 1–15)
 seq: numer ramki nadawcy łącza (u16, rośnie o 1, zawija się)
 opts: 0; każda inna wartość jest odrzucana (miejsce na jawnie wersjonowane rozszerzenie)
 podpis: Ed25519 pochodzenia, 64 B (tylko DATA, przenoszony bez zmian przez każdy skok)
 MAC: pierwsze 8 B HMAC-SHA-256(K_link, wszystkie wcześniejsze bajty)
 tag pary: pierwsze 8 B HMAC-SHA-256(K_hop, "WICI hop v1" ‖ wszystkie wcześniejsze bajty), tylko gdy l_dst ≠ 0xFFFF
```

Ramka LoRa ma najwyżej 255 B, więc koperta w DATA ma 25–164 B (`MAX_PAYLOAD` = 255 − 11 − 64 − 8 − 8).

| Typ | Kod | Ładunek | Ramka w eterze | Czas TX (SF7) |
|---|---|---|---|---|
| DATA | 0 | koperta, potem podpis pochodzenia | 91 B + koperta (rozsyłana: 83 B + koperta), 116–255 B | 215–419 ms |
| HACK | 1 | brak; potwierdza `seq` ramki DATA od `l_src` | 27 B, zawsze z tagiem pary | 87 ms |
| BEACON | 2 | `root`, `rank`, `epoch`, `parent` (u16), flagi (1 B; bit 0 zarezerwowany, pozostałe 0), podpis epoki korzenia (64 B), podpis nadawcy (64 B) | 156 B, bez tagu pary | 276 ms |
| 3–7 | | zarezerwowane | | |

Czasy liczy `lora::frameAirMs` z narastaniem nadajnika. Odbiorca odrzuca ramkę o błędnym MAC lub tagu, nieznanej wersji, nieznanym typie, niezerowym `opts` lub bicie 2, `hops` > TTL, ACKREQ przy `l_dst` = 0xFFFF oraz DATA rozsyłaną bez DOWN.

**Klucze łącza.** `K_link = HKDF-SHA-256(ikm = klucz sieci z przygotowania, salt = net_id, info = "WICI link v2", L = 32)`; jest wspólny dla sieci. Każdy numerowany węzeł ma klucze X25519 sąsiadów z `priority_keys` (najwyżej 50). Para wyprowadza wspólny sekret jak koperta (`envelope::deriveKey`, ECDH X25519 i HKDF) z numerami pary w kolejności rosnącej, a potem `K_hop = HMAC-SHA-256(sekret, "WICI hop v1")`. Węzeł sprawdza tag przed jakimkolwiek przetwarzaniem ramki jednoadresowej; ramkę od sąsiada bez klucza pary odrzuca. Sam klucz sieci nie pozwala więc podszyć się pod `l_src` sąsiada, sfałszować HACK ani dostać się do kolejki przekaźnika ramką jednoadresową. Rozsyłane DATA i BEACON-y niosą tylko MAC sieci; ich treść chronią podpisy.

**Podpisy Ed25519** (klucze tożsamości z kart; każda dziedzina ma własną etykietę):

| Podpis | Treść | Kto podpisuje |
|---|---|---|
| pochodzenia (K1) | `"WICI K1 origin v1"` ‖ `net_id` ‖ cała zaszyfrowana koperta | nadawca koperty: stacja albo tożsamość odbiorcy |
| epoki | `"WICI root epoch v1"` ‖ `net_id` ‖ `root` ‖ `epoch` | korzeń; przekaźniki przenoszą go bez zmian |
| BEACON | `"WICI route beacon v1"` ‖ `net_id` ‖ nadawca ‖ pierwsze 73 B ładunku BEACON | nadawca BEACON-u |

**Słowo synchronizacji.** Profil pilotażu używa 0x12. Do rozważenia przed T4: własne słowo synchronizacji sieci WICI, żeby radio w ogóle nie zgłaszało ramek Meshtastic, MeshCore i LoRaWAN na tym samym kanale. Nie zmniejsza to kolizji, ale ogranicza pracę procesora i liczbę ramek do odrzucenia.

## Trasy

### Drzewo do odbiorcy

Sieć tworzy drzewo zakorzenione w węźle radiowym stanowiska odbiorczego (`root`). Każda stacja ma **rodzica**, czyli następny skok w stronę odbiorcy.

1. **Rodzic z planu.** Dokument konfiguracji podaje rodzica z planu sieci i opcjonalnie rodzica zapasowego, wybranych na podstawie pomiaru tras (kroki 3 i 5). To podstawowy tryb pracy w pilotażu. Stacja bez wpisów `priority_keys` (Ed25519 i X25519) dla korzenia, rodzica i rodzica zapasowego nie uruchamia łącza.
2. **Przełączenie.** Po 3 kolejnych nieudanych próbach (brak HACK) do rodzica z planu stacja przechodzi na rodzica zapasowego, a gdy go nie ma albo też zawiódł 3 razy, wybiera sąsiada o najmniejszym koszcie `rank` + koszt łącza z ważnych BEACON-ów. Nowy dynamiczny rodzic musi być lepszy od obecnego o co najmniej 1,5 jednostki ETX (24/16). Dynamiczny rodzic po 3 porażkach jest pomijany do pierwszego HACK od niego. Do rodzica z planu stacja wraca po HACK od niego; rodzica z planu i zapasowego rozważa ponownie po jego nowym BEACON-ie.
3. **Koszt łącza** w szesnastych częściach ETX: `256 / p` + kara SNR, gdzie `p` to średnia wykładnicza skuteczności HACK (w szesnastych, waga nowej próby 1/4), a kara SNR to 1/16 na każdy dB poniżej 0 dB ramki BEACON, najwyżej 32/16.
4. **Ranga.** `rank` korzenia to 0; stacja ogłasza `rank` rodzica + koszt łącza do niego. Dynamiczny rodzic musi mieć rangę niższą od najniższej rangi tej stacji w bieżącej epoce i nie może wskazywać tej stacji jako rodzica. Rodzic z planu i zapasowy mogą mieć wyższą rangę (np. po awarii), ale też nie mogą wskazywać tej stacji. BEACON starszy niż 90 min nie wskazuje rodzica.
5. **Limit skoków.** Pole `hops` pozwala na najwyżej 15 skoków. Domyślny limit sieci to 7; plan sieci ma go ustawiać, a do tego czasu stacje używają 7. Reguła planowania pilotażu z [rozdziału 02](../concept/02-scenariusze-i-organizacja.html) (najwyżej 2 przeskoki do stanowiska, dopóki T5 nie sprawdzi dłuższych łańcuchów) dotyczy planu, nie protokołu.

Tablica sąsiadów (16 wpisów) jest miękkim stanem w RAM. Nowy sąsiad nie wypiera rodzica z planu ani zapasowego; rodzic z planu i zapasowy wypierają najdawniej słyszanego sąsiada dynamicznego.

### BEACON

Stacja z ustaloną rangą i rodzicem, a także korzeń, nadaje BEACON 1–5 s po starcie, potem dwa razy co 120 s, potem co 24–36 min (30 min ±20%), oraz po zmianie rodzica lub rangi (najwyżej raz na 60 s). Przy 50 stacjach to około 8 s czasu nadawania na godzinę w całym obszarze kolizji. BEACON-y wliczają się do limitu ogłoszeń 2% czasu nadawania i do wspólnej puli z K2 ([dostęp do kanału](radio.md#dostęp-do-kanału)). W ciszy radiowej stacja nie nadaje BEACON-ów.

`epoch` to trwały licznik startów korzenia (u16). Stacja przyjmuje BEACON dopiero po sprawdzeniu podpisu epoki kluczem korzenia i podpisu nadawcy kluczem sąsiada z `priority_keys`. Po zmianie epoki stacja czyści tablicę sąsiadów i liczy rangę od nowa. Starszą epokę odrzuca jako powtórkę, chyba że bieżącej nie słyszała od 90 min: wtedy przyjmuje ją, bo wymieniony lub wyczyszczony korzeń liczy starty od nowa.

Każde sprawdzenie Ed25519 zajmuje pętlę stacji ([czas HACK](#implementacja)). BEACON nie ma tagu pary, więc posiadacz klucza sieci może je wysyłać bez ograniczeń; stacja sprawdza więc podpisy BEACON-ów najwyżej raz na 1 s czasu radia, a resztę pomija. Token epoki identyczny z już sprawdzonym nie jest sprawdzany drugi raz.

### Ruch w górę i w dół

- **W górę** (do odbiorcy): stacja wysyła DATA do rodzica; każdy przekaźnik przekazuje ją swojemu rodzicowi.
- **W dół** (od odbiorcy): przekaźnik zapamiętuje, przez którego sąsiada (`l_src`, sprawdzony tagiem pary) przyszła ramka DATA w górę od stacji `src` koperty, ale tylko gdy ma ona poprawny podpis pochodzenia tej stacji. Korzeń zapamiętuje drogę dopiero po HACK od laptopa, czyli po uwierzytelnieniu koperty na stanowisku. Odbiorca zna więc drogę do stacji po pierwszej przyjętej od niej kopercie. Ramkę z flagą DOWN do tej stacji przekaźnik wysyła temu sąsiadowi. Tablica ma 256 wpisów, jest w FRAM i wraca po restarcie; przy pełnej tablicy nowy wpis wypiera kolejne wpisy po kolei. Korzeń usuwa drogę po 3 kolejnych ramkach w dół do tej stacji bez HACK.
- **Brak wpisu:** przekaźnik bez drogi do celu rozsyła ramkę w dół do wszystkich sąsiadów (`l_dst` = 0xFFFF) bez ACKREQ, z limitem skoków. Przed nadaniem zapisuje w FRAM tożsamość koperty (`src`, `dst`, `ctr`, rodzaj); ten sam węzeł nie rozsyła jej drugi raz w oknie 120 s, także po restarcie, a powtórne kopie odrzuca. Pełny pierścień świeżych tożsamości blokuje kolejne rozsyłanie. Rozsyłanie jest jednorazową próbą: zanik zasilania między zapisem a nadaniem może ją stracić, a ponowienie należy do intencji SA1 z nowym licznikiem koperty. Przekaźnik nigdy nie oddaje ramki sąsiadowi, od którego ją dostał.

### Potwierdzenie na każdym skoku

1. Jednoadresowa ramka DATA ma flagę ACKREQ. Odbiorca skoku odpowiada HACK z tym samym `seq`, adresowanym do `l_src`, dopiero po trwałym przyjęciu: przekaźnik po zapisie i odczycie kontrolnym ramki w kolejce w FRAM, cel po zapisie części koperty albo po trwałym, idempotentnym przyjęciu SA1 i oknie powtórzeń, korzeń po HACK od laptopa (po zapisie w SQLite). Brak miejsca lub błąd zapisu oznacza brak HACK. HACK potwierdza przejęcie odpowiedzialności za bajty na jednym skoku, nie przyjęcie SA1; dla WICI-Link `e2e_ack = false`, więc `Bearer::confirm()` nie steruje HACK.
2. HACK musi skończyć się najpóźniej 200 ms po końcu ramki DATA. Wychodzi po samym CAD, bez okna 50 ms, także w trakcie długu ciszy i przed czekającą DATA; jego czas nadawania z dwunastokrotnością dolicza się do długu i jest zapisany w FRAM przed nadaniem (bez zapisu nie ma HACK). Udział nadawania w długim czasie pozostaje więc 1/13 (około 7,7%). HACK nie wychodzi, gdy dług z nim przekroczyłby dług odczekiwany po utracie rekordu (10 056 ms) albo gdy nie zdąży przed terminem.
3. Nadawca czeka na HACK 600 ms od końca swojego nadania. Bez HACK ponawia tę samą ramkę (ten sam `seq`) po długu ciszy i losowym 0,5–2 s, najwyżej 3 razy na rodzica. Własną ramkę stacja kieruje potem do rodzica wybranego przez tablicę tras (zapasowego) na kolejne 3 próby, a gdy to nie pomoże, zgłasza `Failed` do szwu. Ramka przekazywana zostaje w trwałej kolejce i wychodzi do bieżącego rodzica.
4. Węzeł rozpoznaje powtórzoną kopertę po (`net_id`, `src`, `dst`, `ctr`, rodzaj) i skrócie ładunku z podpisem, także po zmianie `l_src`, `seq` i MAC. Koperta wciąż w kolejce albo przekazana w ostatniej godzinie dostaje ponowny HACK, ale nie jest przekazywana drugi raz; inny ładunek o tej samej tożsamości jest odrzucany. Cel rozpoznaje powtórzenie po oknie powtórzeń i nie przyjmuje SA1 drugi raz. Ponowne HACK-i za już przyjęte kopie są ograniczone do jednego na 5 s na węzeł, bo każdy kosztuje dług ciszy, a nagraną ramkę może powtórzyć każdy słuchacz. Wyjątek: pierwsza powtórka ramki K1 przyjętej bez HACK (niżej) dostaje HACK bez tego ograniczenia.

Kolejka przekaźnika ma 4 ramki. Po HACK przekaźnik trzyma ramkę do HACK z następnego skoku, a po restarcie wznawia nadawanie z FRAM z nowym `seq`. Ramka bez doręczenia przez 30 min wygasa i zostaje zapisana jako przekazana; nadawca musi wznowić intencję SA1. Ramka DATA bez ACKREQ (zgłoszenie z wyjątku ciszy, rozsyłanie) jest przekazywana jedną próbą bez HACK.

Ponowienie na skoku ogranicza ponowienia przez cały łańcuch: przy 95% skuteczności jednego nadania i trzech próbach jeden skok przechodzi z prawdopodobieństwem 99,99%. Ponowienia intencji SA1 (10 min po doręczeniu, potem co 30–60 min) zostają bez zmian i działają nad nośnikiem.

## Klasy czasu kanału

Reguły podziału czasu z [radio](radio.md#dostęp-do-kanału) zostają, z jedną zmianą znaczenia klas, możliwą dzięki jawnym numerom stacji w kopercie:

- **K0:** własne ramki DATA stacji, HACK.
- **K1:** przekazywane jednoadresowe ramki DATA do odbiorcy albo od odbiorcy z poprawnym podpisem pochodzenia. Dla ruchu w górę przekaźnik sprawdza klucz Ed25519 numeru `src` z `priority_keys`, dla ruchu w dół klucz tożsamości odbiorcy z karty. Podpis obejmuje całą kopertę, więc zmiana jawnego nadawcy lub odbiorcy unieważnia dowód.
- **K2:** pozostałe przekazywane ramki, w tym rozsyłanie bez wpisu w tablicy (nawet podpisane); BEACON-y w puli ogłoszeń.

**Przyjęcie do kolejki.** Ed25519 trwa dłużej niż termin HACK, więc przekaźnik przyjmuje ramkę najpierw jako K2, bez weryfikacji, tylko gdy pozostaną wolne co najmniej dwa z czterech gniazd, i od razu odpowiada HACK. Podpis sprawdza później; ważny podpis zapisuje przy ramce w FRAM (z CRC i COMMIT) i podnosi ją do K1. Gdy dwa gniazda K2 są zajęte, jednoadresowa ramka z ACKREQ może zająć zarezerwowane gniazdo tylko po sprawdzeniu podpisu, i to najwyżej jedno gniazdo na zweryfikowanego nadawcę. Ta ramka nie dostaje HACK od razu; dostaje go powtórka nadawcy. Brak klucza albo zły podpis oznacza K2. K1 wychodzi przed K2, a wybór gniazda w klasie rotuje. Po restarcie każdy podpis jest sprawdzany ponownie (klucz mógł się zmienić). Przejęta stacja z własnym kluczem podpisu może więc zająć najwyżej dwa gniazda (dwa przyjęte jako K2 i podniesione do K1), a dwa pozostają dla innych zweryfikowanych nadawców.

**Dziennik czasu nadawania.** Przed przekazaniem ramki do radia stacja zapisuje w FRAM koszt każdej przekazywanej DATA i każdego BEACON-u: 13 × czas TX w puli i czas TX BEACON-u w limicie ogłoszeń, zaokrąglone w górę do 100 ms. Siedem przedziałów po 10 min obejmuje co najmniej ostatnie 3600 s. Tranzyt razem z BEACON-ami nie przekracza 60% czasu kanału, a BEACON-y 2% czasu nadawania w tym oknie. K1 ma pierwszeństwo w kolejce, lecz podlega wspólnemu limitowi. Gdy w kolejce czeka K1, ramka K2 może wyjść tylko, jeśli *łączny* koszt tranzytu i BEACON-ów nie przekroczy 25%. Odmowa lub nieudane nadanie po zapisie zostawia koszt, a cofnięcie zegara nie przywraca zużytego czasu. Klasę („własna”, „tranzyt”, „K2 przy czekającym K1”, „BEACON”) podaje koordynator stacji.

Wspólny `K_link` sam nie wystarcza do zajęcia gniazda K1 ani do zajęcia kolejki ramką jednoadresową. Próba „Wrogi węzeł” i W10 na docelowym sprzęcie pozostają warunkami odbioru D21.

## Cisza radiowa

W ciszy radiowej (W19) stacja nie nadaje żadnej ramki: DATA, HACK ani BEACON, także przekazywanej. Kolejka SA1 zostaje, a przekaźnik nadal przyjmuje ramki do trwałej kolejki (bez HACK). Jedno zgłoszenie wyjęte spod ciszy wychodzi jako DATA bez ACKREQ, bez oczekiwania na HACK, najwyżej 3 razy co 60 s, bo potwierdzenie i tak przyjdzie od odbiorcy po zniesieniu ciszy albo gońcem; przekaźniki przekazują je jedną próbą.

## Budżet czasu

Model jak w [rozdziale 06](../concept/06-wykonalnosc-i-budzet-zasobow.html): SF7, 125 kHz, CR 4/5, preambuła 24 symbole, nagłówek jawny, CRC; czas kanału = 13 × czas TX. Na jeden skok jednej części koperty przypada DATA (215–419 ms) i HACK (87 ms). Wartości W10 poniżej powstały przed dodaniem tagu pary (8 B na DATA i HACK) i wymagają przeliczenia w `software/reference/obliczenia.py` oraz pomiaru D21.

| Przekaźnik przed stanowiskiem | Reticulum/LXMF (dziś) | WICI-Link |
|---|---|---|
| czas kanału na jedno zgłoszenie z RECEIVED | 20,1–21,1 s | wymaga przeliczenia z tagiem pary |
| 50 zgłoszeń (W10, bez strat) | 16,8–17,6 min | wymaga przeliczenia z tagiem pary |
| 50 zgłoszeń z PRZECZYTANE i decyzją | około 32,3 min | wymaga osobnego przeliczenia dla v2 |

Wąskim gardłem pozostaje przekaźnik obok stanowiska, którego obciążenie nie zależy od długości łańcucha za nim. Opóźnienie rośnie o około 0,5–5 s na skok, zależnie od długu ciszy przekaźnika. Wartości W10 są modelem bez kolizji i odroczeń; do potwierdzenia na sprzęcie.

## Zagrożenia

| Zagrożenie | Skutek | Ochrona |
|---|---|---|
| Węzeł bez klucza sieci | zakłócanie kanału | ramki odrzucane przed przetwarzaniem; kolizje bez ochrony (pasmo bez ochrony, D11) |
| Powtórzenie nagranej ramki (bez klucza) | podwójne przekazanie, dług ciszy z HACK | pierścień przekazanych kopert (1 h), okna powtórzeń celu, jeden ponowny HACK na 5 s; ponowne rozsyłanie blokuje pierścień 120 s. Pierścień ma 224 wpisy, a pula 60% pozwala na więcej przekazań na godzinę, więc starsza koperta może zostać przekazana drugi raz (do próby przeciążeniowej); cel nie przyjmie jej drugi raz |
| Posiadacz samego klucza sieci podrabia `l_src`, HACK albo ramkę jednoadresową | błędna trasa, fałszywy sukces skoku, zajęcie kolejki | tag pary sprawdzany przed routingiem; grupa nie ma klucza pary |
| Posiadacz klucza sieci wysyła rozsyłane DATA lub BEACON-y | zajęcie gniazd K2 rozsyłaniem, praca procesora | rozsyłanie tylko w dół, bez ACKREQ, K2 i bez weryfikacji podpisu; BEACON bez ważnych podpisów odrzucony, sprawdzanie najwyżej raz na 1 s |
| Przejęta stacja podrabia zgłoszenie lub potwierdzenie SA1 | brak: nie ma klucza pary odbiorca–nadawca | koperta z kluczem pary z kart |
| Przejęta stacja wysyła kopertę z przewidzianym cudzym licznikiem | odrzucenie prawdziwej koperty na przekaźnikach do 1 h | ponowienie SA1 nowym licznikiem; ryzyko szczątkowe |
| Węzeł z kluczem sieci zalewa kanał | wypieranie ruchu WICI | klasy K0–K2, pula 60%, limit ogłoszeń; próba „Wrogi węzeł” |
| Przejęta stacja z własnym kluczem podpisu ogłasza fałszywie niską rangę (przyciąga ruch i go porzuca) | utrata ruchu przez ten węzeł | rodzic z planu ma pierwszeństwo; zmiana rodzica tylko po nieudanych próbach; brak RECEIVED wywołuje ponowienie intencji i alarm; dyżurny widzi w diagnostyce zmiany rodziców; ryzyko szczątkowe, tej samej klasy co przekaźnik Reticulum, który porzuca pakiety |
| Powtórzenie starego BEACON-u tej samej epoki | nieaktualna ranga sąsiada | podpis nie ma znacznika czasu; plan ma pierwszeństwo, porażki wyłączają rodzica; ryzyko szczątkowe |
| Przejęcie klucza prywatnego odbiorcy | odczyt zapisanego ruchu, podrabianie odpowiedzi | klucz zapasowy z kart (D08); brak poufności przyszłej w pilotażu |

## Implementacja

Kod w `firmware/src/wici_*.cpp`; testy natywne z sanitizerami w `tests/native/wici_*_check.cpp`, uruchamiane przez `tests/test_envelope_cross_language.py`, oraz `tests/test_radio_link_host.py` dla toru radia.

| Moduł | Zadanie |
|---|---|
| `wici_link` | kodek ramki, MAC sieci, HACK, przepisanie nagłówka przy przekazaniu |
| `wici_hop_auth` | tag pary na wyjściu i wejściu radia |
| `wici_origin`, `wici_epoch`, `wici_beacon` | podpisy pochodzenia, epoki i BEACON-u |
| `wici_relay`, `wici_seen` | trwała kolejka przekaźnika i pierścień przekazanych kopert |
| `wici_hop` | przyjęcie do kolejki, HACK, K1, wybór następnego skoku, ponowienia |
| `wici_route`, `wici_flood`, `wici_seq` | trasy i BEACON-y, pierścień rozsyłania, `seq` łącza |
| `wici_destination` | odbiór koperty na stacji docelowej |
| `wici_radio` | koordynator stacji (własne SA1, przekaźnik, BEACON, czasy 600 ms i 0,5–2 s) |
| `wici_gateway` | korzeń: most radio–KISS USB, HACK od laptopa najwyżej 200 ms po odbiorze |
| `wici_airtime` | dziennik czasu nadawania |
| `wici_record` | wspólny zapis rekordów FRAM |

**FRAM** (luka 0x044000–0x047FFF przed systemem plików; 64 B wolne):

| Adres | Rozmiar | Zawartość |
|---|---|---|
| 0x044000–0x04417F | 2 × 128 B | tożsamość stacji (`framfs`) |
| 0x044180–0x0441BF | 2 × 32 B | rezerwacja `seq` blokami 64 |
| 0x0441C0–0x0441FF | 64 B | wolne |
| 0x044200–0x044F7F | 192 × 18 B | pierścień rozsyłania, część A |
| 0x044F80–0x044FFF | 4 × 32 B | okna powtórzeń kopert (dwóch odbiorców) |
| 0x045000–0x0459FF | 4 × 2 × 320 B | kolejka przekaźnika |
| 0x045A00–0x045E7F | 64 × 18 B | pierścień rozsyłania, część B |
| 0x045E80–0x045FFF | 2 × 192 B | część koperty od głównego odbiorcy |
| 0x046000–0x0468FF | 2 × 1152 B | drogi w dół |
| 0x046900–0x047DFF | 224 × 24 B | pierścień przekazanych kopert |
| 0x047E00–0x047F7F | 2 × 192 B | część koperty od zapasowego odbiorcy |
| 0x047F80–0x047FFF | 2 × 64 B | dziennik czasu nadawania |

Każdy rekord ma CRC-16 i końcowy bajt COMMIT zapisywany na końcu, po wyzerowaniu go, oraz odczyt kontrolny. Rekordy dwukopiowe mają numer pokolenia; przerwany zapis zostawia poprzednią kopię. Uszkodzony zatwierdzony rekord blokuje start łącza (bezpieczna odmowa); każdy niepewny zapis wyłącza moduł do ponownego odczytu FRAM i nie daje HACK. Rekordy zapisane pod innymi numerami po zmianie przygotowania nie blokują startu: rezerwacja `seq` i zużyty czas nadawania przechodzą dalej, stare drogi w dół i obce wpisy rozsyłania są pomijane, a ramki w kolejce, których nie da się uwierzytelnić bieżącym kluczem i numerami, są usuwane. Usunięcie z kolejki zapisuje najpierw wpis „przekazane” w pierścieniu, potem trwały rekord pusty; zanik między nimi kończy się przy następnym przeglądzie kolejki, bez drugiego nadania. Rezerwacja `seq` pomija po restarcie niewykorzystaną resztę bloku; błędny zapis wyłącza nadawanie. Czasy trwałe biorą monotoniczny licznik pracy stacji.

**Cel i korzeń.** Stacja schronienia przyjmuje koperty tylko od głównego i zapasowego numeru odbiorcy, po jednej oczekującej części na każdego. Po restarcie kończy przerwane czyszczenie części, gdy okno powtórzeń dowodzi przyjęcia SA1. Korzeń przekazuje do USB (KISS) tylko ramki po sprawdzeniu tagu i MAC; HACK od laptopa nadaje tylko dla ostatniej przekazanej ramki DATA, ze zgodnym `l_src` i `seq`, przed upływem 200 ms od końca odbioru. Odłączenie USB kasuje oczekiwanie. Stanowisko zapisuje kopertę w SQLite przed odesłaniem HACK i nie wysyła na tej ścieżce LXMF ani kopii. Ramkę w dół od laptopa korzeń odsyła laptopowi jako echo dopiero po faktycznym nadaniu; echo rozsyłania bez HACK stanowisko traktuje jako nieudane doręczenie.

**Czas HACK (szacunek do pomiaru D21).** Między końcem odbioru a nadaniem HACK przekaźnik wykonuje około pięciu HMAC/SHA-256 po ramce (tag pary, trzy sprawdzenia MAC, skrót koperty), zapis i odczyt kontrolny 320 B FRAM, budowę HACK z tagiem i CAD. To około 2–5 ms na nRF52840 (64 MHz) i około 1–2 ms na ESP32-S3 (240 MHz) przy SPI FRAM 8 MHz; cel dodaje AEAD i zapis SA1 w `Store`. Przy 87 ms nadawania zostaje zapas względem 200 ms (tor radia odmawia HACK, gdy od końca odbioru minęło więcej niż 200 − 87 − 20 ms). Termin zależy więc od opóźnienia pętli: weryfikacja Ed25519 (około 10 mln instrukcji, około 0,15–0,3 s na nRF52840 i 0,04–0,1 s na ESP32-S3) i podpis (około połowy tego) blokują pętlę przy podniesieniu ramki do K1, odbiorze BEACON-u, nadaniu BEACON-u i przyjęciu własnego SA1. Ramka zakończona w tym czasie nie dostaje HACK i jest ponawiana przez nadawcę.

**RAM** (stacja): kolejka 4 × 255 B, pierścień przekazanych kopert 5376 B, pierścień rozsyłania 4608 B, drogi w dół 1 KiB, sąsiedzi 16 × 20 B, klucze par do 50 × 32 B, dwie własne ramki 2 × 255 B, okna powtórzeń i części kopert; razem około 14 KiB plus bufor składania do 256 B na stosie. Okna powtórzeń dla wielu stacji po stronie stanowiska są w SQLite.

## Otwarte pytania

1. Czy HACK można zastąpić potwierdzeniem biernym (nadawca słyszy, jak rodzic przekazuje ramkę dalej), jak w protokołach zbierania danych w sieciach czujników? Oszczędza to jedną ramkę na skok, ale nie działa na ostatnim skoku i przy rodzicu w długu ciszy.
2. Czy zapis FRAM i odpowiedź HACK mieszczą się w 200 ms na docelowym prototypie, także gdy pętla wykonuje Ed25519? Termin wymaga pomiaru na każdym MCU.
3. Własne słowo synchronizacji sieci WICI (wyżej).
4. Czy obecne progi SNR i średniej skuteczności HACK dają stabilne trasy w pomiarze T5; wartości progów ustala T5.
5. Czy pomiar W10 potwierdzi model v2 z `software/reference/obliczenia.py` po przeliczeniu z tagiem pary?

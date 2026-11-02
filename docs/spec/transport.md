# Warstwa transportu: szew, koperta i nośniki

**Stan: implementacja przed próbą D21, 2026-11-02.** Numerowana konfiguracja uruchamia WICI-Link v3 na surowym SX1262; konfiguracja bez numerów uruchamia Reticulum. Warunek przyjęcia D21 nadal wymaga próby przy stole na docelowym sprzęcie ([kryteria](#warunek-przyjęcia)).

## Po co

Wybór stosu sieciowego ma wpływ na licencję, umowy z gminą, zgodność (D20) i zapas czasu w W10. Dziś aplikacja stacji (SA1, kolejka w FRAM, trzy potwierdzenia) prawie nie zależy od stosu, ale bezpieczeństwo, adresy i karty stacji zależą od Reticulum i LXMF. Ten dokument wyznacza granicę między nimi tak, aby:

1. aplikacja WICI i jej bezpieczeństwo nie zależały od nośnika;
2. stacja mogła używać własnego protokołu łącza [WICI-Link](wici-link.md) albo innego nośnika bez zmian w logice stacji;
3. stanowisko odbiorcze mogło jednocześnie odbierać ruch z kilku nośników, np. sieci WICI, węzła Meshtastic lub MeshCore podłączonego przez USB i łącza IP do powiatu;
4. jeden zestaw prób sprawdzał każdy nośnik według tych samych kryteriów.

## Warstwy

| Warstwa | Odpowiada za | Gdzie |
|---|---|---|
| Aplikacja SA1 | sześć typów wiadomości, cykl życia zgłoszenia, trzy potwierdzenia (W06), kolejka i rejestr w FRAM, deduplikacja po (nadawca, `id`, `revision`) | `station.cpp`, `store`, `sa1`, `ui`; aplikacja stanowiska |
| Koperta WICI | uwierzytelnienie i poufność od końca do końca, ochrona przed powtórzeniem, podział na części, adresy stacji z kart | nowa, w stacji (C++) i na stanowisku (Python) |
| Szew nośnika | wysłanie, odbiór, zdarzenia doręczenia, cisza radiowa, stan | `station::Services` w stacji, `bearers.Bearers` na stanowisku |
| Nośnik | trasy, przekazywanie, potwierdzenia na łączu, dostęp do kanału | WICI-Link, Reticulum (obecny rdzeń), Meshtastic, MeshCore, IP |
| Warstwa fizyczna | modulacja, sterownik radia | własny sterownik SX1262 albo oprogramowanie obcego węzła |

Zasada: **nośnik niczego nie gwarantuje aplikacji poza próbą dostarczenia bajtów**. Autentyczność nadawcy, poufność treści i potwierdzenie przyjęcia zgłoszenia zapewniają koperta i SA1. Słabsze bezpieczeństwo nośnika (np. kanał Meshtastic bez uwierzytelnienia, MeshCore z AES-ECB i 2-bajtowym MAC) wpływa wtedy na metadane i odporność na zalew, ale nie pozwala podrobić zgłoszenia ani potwierdzenia.

## Koperta WICI

### Klucze

Każda stacja i każda tożsamość odbiorcy (główna i zapasowa) ma statyczną parę kluczy wygenerowaną w urządzeniu przy przygotowaniu. Koperta używa pierwszych 32 B (X25519) istniejącego klucza prywatnego i publicznego tożsamości Reticulum; HKDF z etykietą „WICI env v1” oddziela klucz koperty od kluczy stosu. Klucz publiczny trafia na kartę stacji albo kartę odbiorcy ([protokół USB](usb-protocol.md)); w karcie numerowanej jest też jawnie podany jako `x25519`, równy pierwszym 32 B pełnego klucza `key`. Kluczy nie przyjmuje się przez radio (bez zmian względem D08).

Numerowany dokument `configure` nadaje `net_id` sieci i niepowtarzalny numer u16 stacji oraz obu tożsamości odbiorcy (`network`); karta odbiorcy wiąże numer, `net_id` i pełny klucz, a `priority_keys` podaje klucze Ed25519 i X25519 sąsiadów oraz, opcjonalnie, stacje, które plan sieci stawia za każdym z nich (`behind`, [drogi w dół](wici-link.md#ruch-w-górę-i-w-dół)). Stacja i przygotowanie na laptopie (`configdoc.py`) odrzucają dokument, w którym którykolwiek klucz X25519 albo Ed25519 karty odbiorcy lub `priority_keys` ma mały rząd (lista w `config.cpp`, `SMALL_ORDER`; bit 255 pomijany): taki klucz X25519 daje zerowy wspólny sekret, a z takim kluczem Ed25519 podrobiony podpis przechodzi dla każdej wiadomości. Rejestr kart na stanowisku odrzuca duplikat numeru z innym kluczem. Konfiguracja bez `network` zachowuje 16-bajtowe adresy Reticulum i nie używa koperty.

Klucz pary nadawca A → odbiorca B:

```
ss      = X25519(sk_A, pk_B)                    (ss = 0 → odmowa)
K_A→B   = HKDF-SHA-256(ikm = ss, salt = net_id ‖ 0x01,
                       info = "WICI env v1" ‖ id_A ‖ id_B ‖ pk_A ‖ pk_B, L = 32)
```

Kierunek B → A ma osobny klucz (zamienione `id` i `pk` w `info`), więc liczniki obu stron nigdy nie dzielą nonce. `net_id`, `id_A` i `id_B` koduje się jako u16 BE; `pk_A` i `pk_B` to surowe klucze X25519 po 32 B; numery 0x0000 i 0xFFFF są odrzucane. Stacja używa przypiętej biblioteki Crypto, stanowisko przypiętego pakietu `cryptography` (48.0.1).

Pilotaż nie ma poufności przyszłej (forward secrecy): przejęty klucz prywatny odbiorcy odsłania zapisany wcześniej ruch, tak jak dziś przy pakietach okazjonalnych LXMF. Wymiana kluczy następuje przez USB przy przeglądzie (D08). Rotacja przez radio jest poza pilotażem.

### Format

```
 0      1      3      5             9                         n-16      n
 +------+------+------+-------------+-------------------------+---------+
 | kind | src  | dst  | ctr (u32 BE)| szyfrogram (ChaCha20)    | tag(16) |
 +------+------+------+-------------+-------------------------+---------+
 kind: bity 7–6 wersja (1), bity 5–4 część (0 = całość, 1 = 1/2, 2 = 2/2, 3 odrzucane), bity 3–0 rodzaj (0 = SA1; 1–15 zarezerwowane i odrzucane)
 src, dst: numery stacji z planu sieci (u16, 0x0000 i 0xFFFF odrzucane, src ≠ dst)
 nonce (12 B) = src ‖ dst ‖ kind ‖ 0x000000 ‖ ctr
 AAD = kind ‖ src ‖ dst ‖ ctr
```

Narzut koperty: 25 B (9 B nagłówka i 16 B znacznika); koperta ma 25–281 B, część najwyżej 128 B treści. Odbiorca ujawnia treść dopiero po sprawdzeniu znacznika. Numery stacji są jawne. Przekaźnik widzi nadawcę i odbiorcę od końca do końca, ale ich nie uwierzytelnia; klasę K1 przydziela ramce do odbiorcy albo od niego, najwyżej jedno gniazdo na sąsiada uwierzytelnionego tagiem pary ([klasy czasu](wici-link.md#klasy-czasu-kanału)). TEST startowy jest wiadomością SA1 (rodzaj 0). Analiza ruchu jest przyjęta w [rozdziale 07](../concept/07-zagrozenia-i-odpornosc.html): nagłówek Reticulum także ujawnia cel, a rozmiar ujawnia typ SA1.

### Licznik i powtórzenia

- Nadawca rezerwuje `ctr` blokami po 64 wartości: przed użyciem wartości `c` trwale zapisana granica wynosi co najmniej `c + 1`. Po restarcie zaczyna od zapisanej granicy i pomija resztę bloku. Wartość nigdy się nie powtarza; po 2³² − 1 para wymaga nowych kluczy. Nieudany zapis granicy wyłącza szyfrowanie do ponownego odczytu.
- Stacja trzyma granicę w FRAM dla każdej z dwóch tożsamości odbiorcy; granica nie maleje także po zmianie klucza lub numeru. Stanowisko trzyma osobną granicę dla każdego klucza (`env_send`, SHA-256 klucza) w SQLite.
- Odbiorca przyjmuje kopertę tylko wtedy, gdy `ctr` jest większy od największego przyjętego albo mieści się w oknie 64 ostatnich wartości i nie był przyjęty. Stan okna (największy `ctr` i maska) zapisuje w FRAM stacji albo SQLite stanowiska w tej samej transakcji co przyjęcie wiadomości SA1.
- Powtórka z bitem przyjęcia w trwałym oknie dostaje ponowny HACK bez ponownego przyjęcia. Licznik starszy niż okno jest odrzucany bez HACK, bo brak bitu nie dowodzi wcześniejszego przyjęcia; nowa intencja SA1 potrzebuje nowego licznika.
- Deduplikacja SA1 po (nadawca, `id`, `revision`) zostaje. Koperta odrzuca powtórzenie pakietu, SA1 odrzuca ponowienie tej samej wiadomości.

**Rekordy FRAM stacji.** Granica (0x044100), okno (0x044F80) i czekająca część (0x045E80, 0x047E00) mają po dwie kopie: magia, numer pokolenia, odcisk klucza (pierwsze 8 B SHA-256 klucza koperty pary), CRC-16/CCITT-FALSE i końcowy bajt COMMIT. Zapis zeruje COMMIT, zapisuje treść, ustawia COMMIT = 0xA5 i czyta całość kontrolnie. Przy starcie kopia pusta (same 0x00 albo 0xFF) albo z COMMIT = 0x00 (przerwany zapis) jest pomijana; każdy inny COMMIT, zła magia, CRC albo treść blokują start, zamiast cofnąć się do starszej kopii. Okno i część z innym odciskiem należą do innego klucza i są pomijane. Przed pierwszym zapisaniem znacznika tożsamości stacja zapisuje w każdym pustym gnieździe odbiorcy rekord początkowy granicy (bez numerów i odcisku, granica 0). Obie kopie granicy puste przy zapisanej tożsamości oznaczają utratę stanu i blokują szyfrowanie zamiast zacząć od 0; obszar kasuje tylko ZNISZCZ DANE razem z tożsamością.

**Okna stanowiska.** `env_replay` i `env_parts` w SQLite są kluczowane przez (sieć, nadawca, odbiorca), bez odcisku klucza.

**PRZENIEŚ STACJĘ.** Zaszyfrowana migawka 256 KiB obejmuje tożsamość, klucze koperty, zatwierdzone granice rezerwacji `ctr` i okna powtórzeń dla odbioru. Po imporcie stacja docelowa zaczyna nadawanie od przeniesionej granicy (nawet jeśli część zarezerwowanych wartości nie została użyta); nie zeruje licznika ani okien. Źródłowa przestaje nadawać przed utworzeniem paczki, zgodnie z [krokami przeniesienia](usb-protocol.md#przeniesienie-stacji). Brak któregokolwiek z tych pól albo niepewna granica blokuje aktywację z tą samą tożsamością; wymaga nowych kluczy i kart. Oprogramowanie obsługuje wznowienie po przerwaniu USB, wycofanie i trwałe oznaczenie wycofanej lub wyłączonej stacji. Próba zaniku zasilania na sprzęcie docelowym pozostaje warunkiem D21.

**Odtworzenie stanowiska z kopii.** Starsza kopia SQLite może mieć niższą granicę rezerwacji `ctr` niż ostatnio użyta z tą samą tożsamością odbiorcy. Odtworzone stanowisko nie nadaje kopert pod tymi kluczami (`env_send_guard`), dopóki przygotowanie nie aktywuje nowej tożsamości odbiorcy i nowych kart. Zapasowa tożsamość odbiorcy nie ma granicy poza bazą stanowiska, które ją aktywuje, więc paczka zapasowa jest jednorazowa: pierwsza aktywacja oznacza paczkę jako użytą przed założeniem nośnika, a każda następna zaczyna z `env_send_guard` ([tożsamość zapasowa](stanowisko-osp.md#komputer-i-aplikacja-stanowiska)).

### Podział na części

Gdy koperta przekracza `max_payload` nośnika, nadawca dzieli jawny tekst SA1 na dwie części (pierwsza ma ⌈n/2⌉ B) i każdą szyfruje jako osobną kopertę z tym samym `ctr` oraz polem `część` 1 albo 2 (bity części w `kind` zmieniają nonce). Wiadomość SA1 ma najwyżej 256 B ([SA1](oprogramowanie.md)), więc dwie części wystarczają dla każdego nośnika z `max_payload` ≥ 153 B (128 B treści i 25 B narzutu); nośnik z mniejszym `max_payload` nie spełnia kontraktu.

Odbiorca zapisuje pierwszą uwierzytelnioną część trwale (FRAM stacji albo SQLite stanowiska) przed potwierdzeniem jej odbioru na łączu. Druga część może nadejść w dowolnej kolejności; po złożeniu odbiorca zatwierdza SA1 i okno `ctr` w jednej transakcji, a potem usuwa czekającą część. Do tego czasu `ctr` pozostaje nieprzyjęty. Powtórzenie zapisanej części dostaje ponowne potwierdzenie łącza bez ponownego zapisu; sprzeczna treść części jest odrzucana. Czekająca część wygasa, gdy od jej zapisu minęło ponad 120 s albo zegar odbiorcy cofnął się przed chwilę zapisu; następna część zaczyna wtedy składanie od nowa. Po restarcie odbiorca wznawia składanie. Potwierdzenie części nie oznacza przyjęcia SA1 ani zakończenia intencji nadawcy.

Pojemność: stacja ma jedną czekającą wiadomość na tożsamość odbiorcy i odrzuca część z innym `ctr`, dopóki czekająca nie wygaśnie; stanowisko trzyma do czterech czekających wiadomości na stację i 256 łącznie. Całość pod licznikiem, który ma czekającą część, stacja odrzuca, a stanowisko przyjmuje. Wektory `tests/test_envelope_cross_language.py` sprawdzają oba przebiegi.

### Rozmiary

| Wiadomość SA1 | Treść | Koperta | Części przy WICI-Link (`max_payload` 228 B) |
|---|---|---|---|
| REQUEST typowe | 174 B | 199 B | 1 |
| REQUEST największe | 222 B | 247 B | 2 |
| BULLETIN największy | 246 B | 271 B | 2 |
| REPLY największe | 156 B | 181 B | 1 |
| STATUS | 59 B | 84 B | 1 |
| RECEIVED | 50 B | 75 B | 1 |

Dla porównania: typowe zgłoszenie jako pakiet okazjonalny LXMF ma dziś 403 B i zajmuje dwie ramki ([rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html)).

## Szew nośnika

Nie ma wspólnego interfejsu nośnika w C++. Każda strona ma jeden szew:

- **Stacja** (`station::Services`, `firmware/src/station.h`). Ścieżkę wybiera konfiguracja. Bez `network` aplikacja wysyła przez Reticulum kontraktem `bearer::LegacyBearer` (`firmware/src/bearer.h`: `radioReady`, `busy`, `sendReady`, `send`, `address`; adres LXMF 16 B, dowód LXMF jako zdarzenie doręczenia). Z `network` wysyła kopertę przez `numberedReady` i `sendNumbered`, które `main.cpp` łączy z koordynatorem WICI-Link (`wici_radio::Shelter`); odebraną kopertę `wici_destination` oddaje aplikacji. Zdarzenie doręczenia oznacza HACK następnego skoku dla każdej części.
- **Stanowisko** (`software/laptop/wici/stanowisko/bearers.py`). `Bearers` łączy nośniki `wici` (węzeł stanowiska przez KISS USB, `wici_stos.py`) i `reticulum` (`stos.py`). Każdy ma `start`, `stop`, `announce`, `status(now)` (`online`, `since_rx`, `dropped`), `send` oraz `outcome` (prawda po doręczeniu, fałsz po porażce, brak wyniku w toku). Odpowiedź idzie nośnikiem wskazanym przez dyżurnego, inaczej nośnikiem ostatniej świeżej uwierzytelnionej wiadomości od stacji (zapisanym w transakcji przyjęcia), inaczej głównym (`wici`). Po porażce na wybranym nośniku próbuje drugiego; WICI-Link, który nie może nieść odpowiedzi, od razu oddaje ją Reticulum.

Kolumny tabeli [nośników](#nośniki) (`max_payload`, `hop_ack`, `e2e_ack`, `airtime_classes`, `radio_silence`) opisują właściwości nośnika, nie pola w kodzie.

Reguły kontraktu:

1. **Doręczenie na nośniku nie jest potwierdzeniem aplikacji.** HACK i dowód LXMF sterują tylko ponowieniami. Zgłoszenie jest przyjęte dopiero po RECEIVED (W06).
2. **Dowód po zapisie.** Cel WICI-Link wysyła HACK dopiero po trwałym zapisie skutku SA1 i okna powtórzeń (stacja: `wici_destination`; stanowisko: transakcja SQLite przed HACK). Reticulum wysyła dowód po transakcji aplikacji (PROVE_APP).
3. **Cisza i klasy czasu w nośniku stacji.** Oba nośniki stacji egzekwują ciszę radiową (W19) i klasy czasu kanału z [radio.md](radio.md). Nośnik bez nich (Meshtastic, MeshCore) może działać tylko na stanowisku, a próba „Wrogi węzeł” nie może być dla niego zaliczona.
4. **Odbiór niepewny.** Koperta, której nie da się odszyfrować kluczem żadnej znanej pary, jest odrzucana i liczona. Nie trafia do kwarantanny SA1, bo nie ma uwierzytelnionego nadawcy. Kwarantanna dotyczy dalej stacji z kluczem spoza listy zaufanych, ale z poprawną kopertą.
5. **Jeden nośnik radiowy na stację.** Układ SX1262 odbiera jednocześnie tylko jeden profil, a Meshtastic i MeshCore są całymi programami, nie bibliotekami. Kilka nośników naraz obsługuje tylko stanowisko odbiorcze (niżej).

## Nośniki

| Nośnik | Rola | `max_payload` | `hop_ack` / `e2e_ack` | `airtime_classes` / `radio_silence` | Uwagi |
|---|---|---|---|---|---|
| [WICI-Link](wici-link.md) | domyślny w stacji (po D21) | 228 B | tak / nie | tak / tak | własny protokół łącza; licencja MIT |
| Reticulum (rdzeń stacji) | obecny; zapasowy do rozstrzygnięcia D21 | 492 B | nie / tak (dowód) | tak / tak | adapter wokół `rns_node`; licencja Reticulum |
| Meshtastic (węzeł przez USB) | tylko stanowisko, po pilotażu | 227 B (PKI) | tak / tak (DM) | nie / nie | kanał bez uwierzytelnienia; ruch oznaczany jako niezweryfikowany, chyba że koperta ma klucz z karty |
| MeshCore (węzeł przez USB) | tylko stanowisko, po pilotażu | 184 B | nie / tak | nie / nie | `RAW_CUSTOM` dla koperty; domyślny budżet nadawania 50% wymaga ustawienia na ≤10% |
| IP (MQTT lub HTTPS) | stanowisko ↔ powiat, gdy działa internet | 64 KiB | — / tak | — / — | poza siecią radiową; ta sama koperta |
| Pamięć (symulator, testy) | testy i symulator | dowolne | konfigurowalne | konfigurowalne | wzorzec do prób zgodności |

Wartości `max_payload` dla Meshtastic i MeshCore pochodzą ze źródeł tych projektów sprawdzonych 2026-11-01 (ramka 255 B, nagłówek Meshtastic 16 B, narzut PKI 12 B; ładunek MeshCore 184 B) i trzeba je potwierdzić w adapterze.

### Stanowisko odbiorcze z kilkoma nośnikami

Aplikacja stanowiska ma jeden rejestr i jedną kolejkę odpowiedzi, a pod nimi listę nośników. W pilotażu numerowane stanowisko może uruchomić WICI-Link i równoległy port Reticulum (`--reticulum-port`); wybór ostatniego uwierzytelnionego nośnika dla każdej stacji zapisuje w tej samej migawce bazy co przyjęcie wiadomości. Odpowiedź wraca tym nośnikiem, chyba że dyżurny wskaże inny w panelu. Ruch z nośnika obcego bez koperty WICI (np. wiadomość tekstowa z sieci Meshtastic) trafi do osobnej skrzynki „niezweryfikowane”, bez RECEIVED i bez wpisu do rejestru zgłoszeń. Tę skrzynkę i jej obsługę opisze aplikacja stanowiska po pilotażu.

### Integracja w górę

Wymiana ze służbami i systemami gminy nie należy do szwu nośnika. To osobne adaptery aplikacji stanowiska: REQUEST ↔ OASIS EDXL-RM (zapotrzebowanie na zasoby), BULLETIN ↔ OASIS CAP, ewentualnie EMSI (ISO/TR 22351). Mapowanie pól opisze osobny dokument po pilotażu.

## Zgodność i próby

- Każdy nośnik przechodzi te same próby z [odbioru](odbior.md): W10, deduplikacja i powtórzenia, zimny start, zanik zasilania przy zapisie, „Wrogi węzeł” (tylko nośniki z `airtime_classes`), cisza radiowa (tylko z `radio_silence`). Próby uruchamia się na nośniku pamięciowym w CI i na sprzęcie przy stole.
- Próby zaniku obejmują przeniesienie tożsamości z zarezerwowanym `ctr`, restart po potwierdzeniu pierwszej części, restart przekaźnika po HACK i przed przekazaniem oraz ponowienie po wygaśnięciu składania. Wektory sprawdzają, że żaden z tych przebiegów nie powtarza pary (klucz, nonce) ani nie daje podwójnego przyjęcia SA1.
- Wektory koperty (klucze, nonce, szyfrogramy, części) generuje implementacja w Pythonie i sprawdza implementacja w C++, tak jak dziś wektory Reticulum (`tests/vectors/`).
- Każdy wariant obrazu stacji z innym nośnikiem radiowym jest osobną konfiguracją w rozumieniu D20 i wymaga własnych badań. Wariantów utrzymuje się jak najmniej.

## Warunek przyjęcia

D21 rozstrzyga się po próbie przy stole na dwóch zestawach RAK4631 i prototypie (kroki 2 i 4), na tych samych kryteriach dla WICI-Link i obecnego rdzenia:

1. W10: 50/50 RECEIVED przez jeden przekaźnik w czasie poniżej 15 min;
2. „Wrogi węzeł”: 20/20 zgłoszeń z RECEIVED w 30 min, utrzymane udziały klas;
3. pobór w budżecie W23 i zapas RAM ≥30% (D14);
4. zimny start i zanik zasilania bez utraty i bez podwójnego przyjęcia, także między HACK a przekazaniem oraz po potwierdzeniu pierwszej części;
5. przeniesienie stacji bez ponownego użycia (klucz, nonce), a rozsyłanie awaryjne bez pętli i przekroczenia limitu K2.

Dodatkowymi stacjami w kryteriach 1 i 2 oraz w pomiarze czasu HACK mogą być dwa zestawy XIAO ESP32-S3 z Wio-SX1262 z obrazem `xiao` ([procedura przy stole](../../hardware/xiao-wici/README.md)), a RAK4631 z narzędziem surowego LoRa [`lora-raw`](../../hardware/lora-raw/README.md) (nie z firmware RNode, które dokłada do ramek własny nagłówek) służą wtedy jako podsłuch kanału i węzeł wrogi. Zestaw XIAO trzyma obraz FRAM w PSRAM, więc nie zastępuje prototypu w kryteriach 3 i 4 ani stacji na płytce v2 w energii, zapasie RAM i zaniku zasilania; przekaźnik w próbach zaniku zasilania jest prototypem.

Jeżeli WICI-Link nie spełni warunku, zostaje rdzeń Reticulum, a ten dokument wraca do archiwum. Rozważane wcześniej oparcie stacji na rozwidleniu Meshtastic nie jest drogą zapasową, bo wymaga największych zmian i przenosi na zespół odpowiedzialność za cały obcy program (D20, CRA).

## Kolejność prac

**Stan wykonania, 2026-11-02.** Numerowane obrazy stacji łączą kopertę C++,
trwałe liczniki i okna powtórzeń, kolejkę przekaźnika, trasowanie, koordynator
skoku oraz surowe ramki SX1262 z CAD i trwałym długiem. Korzeń przekazuje
uwierzytelnione ramki do KISS i dopuszcza HACK z laptopa tylko po trwałym
przyjęciu koperty; echo ramki wychodzącej powstaje po faktycznym TX, nie po
przyjęciu do harmonogramu. Aplikacja stanowiska ma numerowany nośnik KISS,
trwałe przyjęcie fragmentów w SQLite, rezerwację liczników przed wysyłką i
blokadę wysyłki po odtworzeniu starszej kopii. Wyjątek od ciszy nadaje
niepotwierdzaną ramkę najwyżej trzy razy z trwałym licznikiem prób.
Numerowany przekaźnik ma trwały limit 60% dla całego ruchu tranzytowego i
BEACON-ów oraz 2% czasu nadawania dla BEACON-ów, z priorytetem K1 w kolejce.
Wspólny limit obejmuje również K1. K1 dostaje jednoadresowa ramka z kopertą
do odbiorcy albo od niego, od sąsiada uwierzytelnionego tagiem pary (WICI-Link
v3 nie ma podpisu pochodzenia na DATA, D21 wariant D). Dwa miejsca są
zarezerwowane dla K1, a jeden sąsiad może zająć najwyżej jedno miejsce K1.
Drogi w dół przekaźnik uczy się tylko według planu sieci (`behind`). Przy
czekającym K1 limit 25% dotyczy zachowawczo całego tranzytu i BEACON-ów.

Pozostałe do zamknięcia D21: sprzętowe próby rozsyłania awaryjnego, pomiar
200 ms HACK, W10, „Wrogi węzeł”, zaniki zasilania oraz budżet energii. Dwie płytki
XIAO ESP32-S3 + Wio SX1262 przeszły [próbę toru radia przy stole](../../hardware/radio-pair/evidence/table-2026-11-01.md)
(100/100 w każdym kierunku) na programie diagnostycznym i
[próbę surowych ramek WICI](../../hardware/radio-pair/evidence/wici-raw-2026-11-01.md)
(19, 44 i 255 B bez zmiany bajtów). Formalna próba D21
na dwóch RAK4631 i prototypie pozostaje nierozstrzygnięta.

1. Szew nośnika (`LegacyBearer`) wokół obecnego `rns_node`, bez zmiany zachowania; próby jak dziś. Przed przełączeniem na numery u16: rozszerzenie kart i `configure` o `net_id` i numery obu końców, z kontrolą ich zgodności.
2. Koperta w Pythonie z wektorami, potem w C++; próby różnicowe i rozszerzenie kontraktu PRZENIEŚ STACJĘ o liczniki oraz okna powtórzeń.
3. WICI-Link w C++ ([specyfikacja](wici-link.md)) i nośnik pamięciowy z symulacją wielu skoków, trwałą kolejką po HACK, składaniem części i rozsyłaniem awaryjnym.
4. Aplikacja stanowiska: nośnik WICI-Link przez KISS i warstwa wielu nośników.
5. Przeliczenie rozdziału 06 i próba przy stole według warunku przyjęcia.

# WICI: protokół USB laptop–stacja

Rozdział jest samodzielnym kontraktem implementacyjnym protokołu między aplikacją laptopa (poziomy 2–3) albo laptopem osoby utrzymującej system (tryb przygotowania) a stacją. Zamyka decyzję D17 po stronie specyfikacji; próby są w [odbiorze](odbior.md) (wiersze „Protokół USB”, „Laptop i USB”, „Przeniesienie”, „Aktualizacja oprogramowania”). Kod stanowiska deweloperskiego (`firmware/src/usbproto.cpp`, kontrakt `"usb":1`) jest prototypem wcześniejszej wersji; obowiązuje ten rozdział, a różnice wymienia [przegląd](../review.md) (F101).

W pilotażu protokół służy tylko w trybie przygotowania: konfiguracja, karta stacji, PRZENIEŚ STACJĘ i aktualizacja oprogramowania. Aplikacja laptopa w schronieniu (poziomy 2–3) dochodzi po pilotażu i używa tego samego kontraktu.

## Zasady

- **Źródło prawdy.** Stan zgłoszeń, skrzynki i konfiguracji przechowuje stacja w FRAM. Laptop przechowuje kopię i własne dane (zgłoszenia mieszkańców, tokeny), a stacji przekazuje tylko intencje. Laptop nie ma tożsamości Reticulum.
- **Bezpieczeństwo przy powtórzeniu.** Każde polecenie zmieniające stan jest idempotentne po kluczu treści (tabela niżej), nie po numerze `seq`. Laptop po utracie odpowiedzi wysyła to samo polecenie ponownie, z nowym `seq`.
- **Brak pozornego sukcesu.** Stacja odpowiada `stored` albo `ok` dopiero po zatwierdzeniu zapisu w FRAM (COMMIT). Laptop potwierdza `ack` dopiero po COMMIT w SQLite.
- **Laptop jest opcjonalny.** Nic w stacji nie czeka na laptop i nic nie rośnie bez niego bez ograniczenia: zdarzenia dla laptopa mają stały pierścień, a luka w nim prowadzi do migawki stanu ([synchronizacja](#synchronizacja)).

## Warstwa przesyłu

| Parametr | Wartość |
|---|---|
| Interfejs | drugi interfejs CDC ACM stacji („dane”); pierwszy to diagnostyka ([radio](radio.md#usb-do-laptopa)) |
| Sesja | od otwarcia portu przez hosta (ustawienie DTR) do jego zamknięcia albo odłączenia przewodu |
| Wiersz | jeden obiekt JSON w UTF-8, zakończony LF (0x0A); CR przed LF jest pomijany |
| Długość | najwyżej 1024 B bez LF; dłuższy wiersz albo bajt NUL: cały wiersz odrzucony (`too_long`) |
| Kodowanie JSON | bez zbędnych spacji; liczby całkowite 0…2³²−1; ciągi bez sekwencji `\u`, z wyjątkiem tablicy SA1, która ma własne reguły ([SA1](oprogramowanie.md#wiadomości-sa1)) |
| Pola | wszystkie wymagane pola muszą wystąpić; pole nieznane albo złego typu daje `invalid` z nazwą pola w `detail` |
| Dane binarne | base64 (RFC 4648, z dopełnieniem), najwyżej 512 B po zdekodowaniu w jednym wierszu |
| Skróty | małe cyfry szesnastkowe: `id` 32 znaki, adres LXMF 32 znaki, SHA-256 64 znaki, `boot` i `epoch` 16 znaków |

Niepełny wiersz z poprzedniej sesji jest odrzucany. Stacja przetwarza wiersze po kolei i na każde polecenie wysyła dokładnie jedną odpowiedź końcową (`stored`, `ok`, `rejected`, `data`, `snap_end`); polecenia z potwierdzeniem przyciskiem mają przed nią odpowiedź pośrednią `pending`.

## Koperta

Każdy wiersz w obu kierunkach:

```json
{"usb":2,"seq":17,"type":"submit","re":0, ...}
```

| Pole | Typ | Znaczenie |
|---|---|---|
| `usb` | liczba | wersja kontraktu; ten rozdział to wersja 2 |
| `seq` | liczba 1…2³²−1 | numer wiersza nadawcy w sesji, rosnący o 1; nowa sesja zaczyna od 1 |
| `type` | ciąg | typ wiadomości z tabel niżej |
| `re` | liczba | tylko w odpowiedzi: `seq` polecenia, na które odpowiada |

**Wersje.** Każda zmiana schematu, nowe pole albo nowy typ oznacza nową wersję. Stacja przyjmuje tylko wersje z listy w `hello`; inna wersja w poleceniu daje `rejected` z `contract`, a stacja nie zmienia stanu. Laptop, który nie zna żadnej wersji z listy, pokazuje „niezgodna wersja stacji” i nie wysyła poleceń.

## Polecenia laptopa

| `type` | Pola | Tryb | Odpowiedź | Klucz powtórzenia |
|---|---|---|---|---|
| `sync` | `boot`, `epoch` (albo `""`), `cursor` | każdy | `sync_ok` albo `snap_required` | sesja |
| `ack` | `epoch`, `cursor` | każdy | brak | `cursor` (zbiorczo) |
| `snapshot` | `epoch` | każdy | `snap_begin`, `snap`…, `snap_end` | sesja |
| `submit` | `id`, `revision`, `sa1` | zwykły | `stored` albo `rejected` | (`id`, `revision`) |
| `cancel` | `id` | zwykły | `ok` albo `rejected` | `id` |
| `test` | `nonce` | zwykły | `stored` albo `rejected` | `nonce` |
| `announce` | brak | zwykły | `ok` albo `rejected` | łączone w 30 s |
| `silence` | `on`, opcjonalnie `exception_id` | zwykły | `pending`, potem `ok` albo `rejected` | stan docelowy |
| `mark_read` | `msg` (numer wiadomości z `snap` lub `event`) | zwykły | `ok` | `msg` |
| `status` | brak | każdy | `status` | – |
| `close` | brak | zwykły | `pending`, potem `ok` albo `rejected` | stan docelowy |
| `destroy` | brak | każdy | `pending`, potem `ok` albo `rejected` | stan docelowy |
| `card` | brak | przygotowania | `card` | – |
| `xfer_begin` | `op`, dalsze pola według `op` | przygotowania | `ok` z `xfer` albo `rejected` | (`op`, `sha256`) |
| `xfer_part` | `xfer`, `offset`, `data` | przygotowania | `ok` z `next` | (`xfer`, `offset`) |
| `xfer_read` | `xfer`, `offset`, `length` (≤512) | przygotowania | `data` | (`xfer`, `offset`) |
| `xfer_commit` | `xfer` | przygotowania | `ok` z wynikiem albo `rejected` | `xfer` |
| `xfer_abort` | `xfer` | przygotowania | `ok` | `xfer` |
| `migrate` | `step`, dalsze pola według kroku | przygotowania | `ok` albo `rejected` | (`step`, skrót paczki) |

„Tryb przygotowania” włącza przycisk pod plombowaną pokrywą serwisową; stacja pokazuje wtedy stale `tryb_przygotowania`. Polecenie z kolumny „przygotowania” poza tym trybem daje `prep_required`. Stacja w konfiguracji węzła stanowiska używa tego protokołu tylko w trybie przygotowania; poza nim interfejs danych przenosi pakiety Reticulum w ramkach KISS ([radio](radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)), a polecenia `submit`, `cancel`, `test`, `announce`, `mark_read` i `close` dają tam `role`.

**`submit`.** `sa1` to tablica REQUEST albo TEST zgodna z [SA1](oprogramowanie.md#wiadomości-sa1); `id` i `revision` muszą być równe polom tablicy. Stacja wysyła wiadomość zawsze do aktywnej tożsamości odbiorcy, więc laptop nie podaje adresu. Reguły:

- nowe `id`: wymaga wolnego krótkiego numeru (inaczej `numer_zajety`, laptop losuje nowe `id`) i wolnego miejsca w rejestrze i kolejce (inaczej `full`);
- `revision` większa od najnowszej znanej dla `id`: nowa rewizja według [cyklu życia](oprogramowanie.md#cykl-życia-zgłoszenia);
- ta sama `revision` i ta sama treść: `stored` z `"duplicate":true`; inna treść: `conflict`;
- `revision` mniejsza od najnowszej: `stale`;
- zgłoszenie zamknięte lokalnie (anulowane): `closed`.

Odpowiedź `stored`: `{"id":…,"revision":…,"number":"0427","duplicate":false}`; `number` to krótki numer zgłoszenia.

**`cancel`** (ANULUJ WYSYŁKĘ z panelu) działa tylko przed pierwszym RECEIVED dla `id`; później `too_late`, a panel proponuje rewizję „potrzeba ustała”.

**`test`** tworzy TEST jak z menu stacji. `nonce` (16 cyfr szesnastkowych losowanych przez laptop) chroni przed podwójnym TEST przy powtórzeniu polecenia: stacja pamięta ostatnie 8 wartości `nonce` z `id` utworzonego TEST i na powtórzenie odpowiada tym samym `stored`.

**`silence`, `close`, `destroy`** wymagają potwierdzenia przyciskiem OK na stacji w ciągu 30 s. Stacja od razu odpowiada `pending` z `"confirm_s":30`, pokazuje pytanie na ekranie i po potwierdzeniu wykonuje operację; bez potwierdzenia odpowiada `not_confirmed`. `silence` z `"on":false` przy przełączniku CISZA w położeniu „cisza” daje `silence_switch`. `exception_id` (wyjątek dla pojedynczego zgłoszenia) wolno podać tylko przy `"on":true` i tylko gdy ciszę ustawiono z panelu; zasady wyjątku są w [trybach kryzysowych](oprogramowanie.md#tryby-kryzysowe). `close` to ZAMKNIJ ZDARZENIE po stronie stacji: laptop wysyła je dopiero po zapisaniu zaszyfrowanego archiwum; stacja usuwa rejestr, kolejkę, skrzynkę i pierścień zdarzeń, losuje nowe `epoch` i odpowiada `ok` z nowym `epoch`. `destroy` to [ZNISZCZ DANE](oprogramowanie.md#tryby-kryzysowe).

**`card`** zwraca kartę stacji: `{"name":"WICI-3fa21c","lxmf":…,"key":<128 cyfr szesnastkowych: klucz publiczny 64 B>,"address":[…],"fingerprint":"…"}`. Odcisk (pierwsze 8 B SHA-256 klucza w grupach po 4 cyfry) stacja pokazuje jednocześnie na ekranie.

## Wiadomości stacji

| `type` | Pola | Kiedy |
|---|---|---|
| `hello` | `boot`, `contracts` (lista obsługiwanych wersji), `name`, `fw`, `role` (`stacja` albo `wezel`), `prep`, `configured`, `epoch`, `head`, `min`, `migration` | pierwszy wiersz po otwarciu portu; także po `rejected` z `contract` |
| `sync_ok` | `re`, `epoch`, `from`, `head` | kursor laptopa mieści się w pierścieniu; stacja zaczyna wysyłać zdarzenia od `from` |
| `snap_required` | `re`, `epoch`, `head`, `min`, `reason` (`epoch`, `gap`, `ahead`) | kursor laptopa nie pozwala na przyrostową synchronizację |
| `snap_begin`, `snap`, `snap_end` | migawka ([synchronizacja](#synchronizacja)) | odpowiedź na `snapshot` |
| `event` | `epoch`, `ev`, `at`, `kind` i pola rodzaju | zmiana stanu w stacji |
| `stored`, `ok`, `pending`, `data`, `status`, `card` | według polecenia | odpowiedź |
| `rejected` | `re`, `reason`, opcjonalnie `detail` | odmowa; stan stacji bez zmian |

Pola `hello`: `epoch` to bieżąca epoka pierścienia zdarzeń, `head` numer ostatniego zdarzenia, `min` najstarszego zachowanego, `migration` stan [przeniesienia](#przeniesienie-stacji) (`none`, `export`, `imported`, `retired`).

**Rodzaje zdarzeń** (`kind`):

| `kind` | Pola | Znaczenie |
|---|---|---|
| `own` | `id`, `revision`, `sa1`, `origin` (`buttons`, `usb`) | nowa rewizja zgłoszenia albo TEST zapisana w stacji, także utworzona przyciskami; rejestr trzyma treść tylko najnowszej rewizji, więc zdarzenie rewizji już zastąpionej wychodzi z `"superseded":true` i bez `sa1` |
| `stage` | `id`, `revision`, `stage`, `attempt`, `next_s`, `decision`, `event` | zmiana etapu wysyłki według [cyklu życia](oprogramowanie.md#cykl-życia-zgłoszenia): `stored`, `sending`, `delivered`, `received`, `superseded`, `cancelled` |
| `msg` | `msg`, `from`, `sa1`, `lost` | wiadomość od aktywnej tożsamości odbiorcy przyjęta do skrzynki (REPLY, BULLETIN; RECEIVED i STATUS zmieniają wpis rejestru i dają zdarzenie `stage` z polami `decision` i `event`); `msg` to numer w skrzynce; `"lost":true` i brak `sa1`, gdy wiadomość usunięto ze skrzynki, zanim zdarzenie wyszło |
| `radio` | `silence`, `silence_source` (`switch`, `panel`), `exception_id` | zmiana ciszy radiowej |
| `power` | `source` (`aa`, `12v`), `mv_aa`, `mv_12v`, `alarm` (`none`, `wymien_ogniwa`, `odlaczone_12v`) | zmiana źródła albo alarm energii |
| `station` | `what` (`restart`, `config`, `receiver_backup`, `prep`), `detail` | restart (z przyczyną), nowa konfiguracja, przełączenie na KLUCZ ZAPASOWY, tryb przygotowania |

`at` to czas pracy stacji w sekundach ([czas](oprogramowanie.md#czas)), nie czas kalendarzowy.

**Odmowy** (`reason`): `contract`, `too_long`, `seq`, `unknown_type`, `invalid`, `role`, `prep_required`, `not_configured`, `full`, `numer_zajety`, `conflict`, `stale`, `closed`, `too_late`, `memory`, `not_confirmed`, `silence_switch`, `busy`, `size`, `hash`, `signature`, `version`, `migration`. Znaczenie dla panelu i ekranu:

| `reason` | Panel laptopa pokazuje |
|---|---|
| `full` | `kolejka_pelna` |
| `memory` | `blad_pamieci`; intencja zostaje w SQLite laptopa |
| `numer_zajety` | nic; laptop losuje nowe `id` i ponawia |
| `conflict`, `stale`, `closed`, `too_late` | opis błędu z `id`; laptop nie ponawia |
| `prep_required`, `role`, `not_configured` | opis stanu stacji |
| `not_confirmed`, `silence_switch` | „nie potwierdzono na stacji” albo „przełącznik CISZA na stacji” |

## Limity czasu

| Sytuacja | Wartość |
|---|---|
| Odpowiedź stacji na polecenie bez potwierdzenia przyciskiem | ≤1 s (zapis FRAM trwa milisekundy); laptop czeka 3 s |
| Odpowiedź końcowa po `pending` | laptop czeka 35 s |
| `xfer_commit` dla `configure` i `import` | laptop czeka 10 s |
| `xfer_commit` dla `firmware` (sprawdzenie podpisu obrazu) | laptop czeka 60 s |
| Ponowienie zdarzeń przez stację bez `ack` | po 5 s od ostatniego wysłania, od `cursor` + 1 |
| Najwyżej zdarzeń w drodze bez `ack` | 8 |
| Laptop bez odpowiedzi w limicie | zamyka i otwiera port (nowa sesja), potem `sync` i ponowienie niepotwierdzonych poleceń |
| Otwarty transfer `xfer` bez części | stacja porzuca go po 60 s albo z końcem sesji |

Polecenie bez odpowiedzi w limicie traktuje się jak niewykonane, dopóki ponowienie po kluczu powtórzenia nie da odpowiedzi; dzięki kluczom ponowienie nie podwaja zgłoszenia ani TEST.

## Synchronizacja

**Pierścień zdarzeń.** Stacja zapisuje każde zdarzenie w pierścieniu w FRAM na 256 wpisów, w tej samej transakcji co zmianę stanu, której dotyczy. Wpis zawiera numer `ev`, czas, rodzaj i odwołanie do rekordu (rejestru zgłoszeń albo skrzynki); treść SA1 stacja czyta z tego rekordu przy wysyłaniu. Nowy wpis nadpisuje najstarszy niezależnie od `ack`, więc laptop nie jest potrzebny do pracy stacji. `ev` rośnie o 1 w obrębie epoki; `min` to najstarszy zachowany wpis.

**Epoka.** `epoch` to 8 losowych bajtów. Stacja losuje nową epokę przy utworzeniu tożsamości, po ZAMKNIJ ZDARZENIE, po ZNISZCZ DANE, po imporcie PRZENIEŚ STACJĘ, po odtworzeniu uszkodzonego pierścienia i gdy `ev` osiągnie 2³²−1. Nowa epoka zaczyna od `ev` = 1.

**Kursor laptopa** to para (`epoch`, `cursor`): ostatnie zdarzenie zatwierdzone w SQLite. `ack` jest zbiorczy: potwierdza wszystkie zdarzenia z `ev` ≤ `cursor`. Laptop zapisuje kursor w tej samej transakcji co skutki zdarzeń, więc restart laptopa nigdy nie pomija zdarzenia; zdarzenie powtórzone po restarcie laptop rozpoznaje po (`epoch`, `ev`) i pomija.

**Decyzja po `sync`:**

| Warunek | Odpowiedź stacji |
|---|---|
| `epoch` równe bieżącemu i `min` − 1 ≤ `cursor` ≤ `head` | `sync_ok` z `from` = `cursor` + 1 |
| `epoch` inne albo puste (nowy laptop, nowa baza, ZAMKNIJ ZDARZENIE) | `snap_required`, `reason` = `epoch` |
| `cursor` < `min` − 1 (laptop odłączony dłużej, niż mieści pierścień) | `snap_required`, `reason` = `gap` |
| `cursor` > `head` (baza laptopa nowsza niż stacja: podmieniona FRAM albo inna stacja z tą samą nazwą) | `snap_required`, `reason` = `ahead`; panel pokazuje ostrzeżenie |

Kursor nie jest numerem rekordu FRAM, więc porządkowanie pamięci stacji go nie zmienia.

**Migawka.** Na `snapshot` stacja wysyła `snap_begin` (`epoch`, `head`, `count`), potem po jednym wierszu `snap` na każdy wpis rejestru zgłoszeń i każdą wiadomość skrzynki, potem `snap_end` (`epoch`, `head`). Wiersz `snap` zgłoszenia: `{"item":"request","id":…,"revision":…,"sa1":[…],"stage":…,"decision":…,"status_event":…,"reply_event":…,"number":…}`; wiadomości: `{"item":"msg","msg":…,"from":…,"received_at":…,"read":…,"sa1":[…]}`. Migawkę stacja buduje z jednego, spójnego stanu: zmiany w czasie migawki dostają zwykłe zdarzenia z `ev` > `head`. Laptop stosuje migawkę w jednej transakcji SQLite dopiero po `snap_end`: zastępuje kopię stanu stacji, zachowuje własne dane mieszkańców i ustawia kursor (`epoch`, `head`). Przerwana migawka nie zmienia bazy laptopa.

**Powiązanie laptopa ze stacją.** Baza laptopa zapisuje nazwę i adres LXMF stacji z pierwszego `hello` po konfiguracji. Stacja o innym adresie wymaga potwierdzenia w panelu („inna stacja”) i zawsze migawki; dane mieszkańców pozostają przy zgłoszeniach, które już mają `id` SA1 tej drugiej stacji, tylko jako historia.

## Transfery dzielone na części

Dane większe niż jeden wiersz przechodzą przez transfer: konfiguracja (`configure`), paczka PRZENIEŚ STACJĘ (`export`, `import`), obraz oprogramowania (`firmware`) i odczyt pełnej konfiguracji (`config_get`). Naraz otwarty jest najwyżej jeden transfer; `xfer_begin` porzuca niezakończony poprzedni.

| `op` | Kierunek | Pola `xfer_begin` | Największy rozmiar | Zatwierdzenie |
|---|---|---|---|---|
| `configure` | do stacji | `size`, `sha256` | 8 KiB | pełna kontrola i zapis w drugiej kopii konfiguracji, przełączenie kopii jednym zapisem znacznika (konfiguracja nigdy nie jest łączona z poprzednią) |
| `import` | do stacji | `size`, `sha256` | 256 KiB | według [przeniesienia](#przeniesienie-stacji) |
| `firmware` | do stacji | `size`, `sha256`, `version` | rozmiar gniazda obrazu ([aktualizacja](oprogramowanie.md#aktualizacja-oprogramowania-stacji)) | sprawdzenie podpisu i wersji, oznaczenie gniazda jako oczekującego |
| `export` | ze stacji | `target_key` | 256 KiB | według [przeniesienia](#przeniesienie-stacji) |
| `config_get` | ze stacji | brak | 8 KiB | – |

Zapis: `xfer_begin` → `ok` z `xfer` (8 cyfr szesnastkowych) i `"max_part":512`; potem `xfer_part` z kolejnymi `offset` od 0 (`offset` musi być równy `next` z poprzedniej odpowiedzi; część powtórzona z mniejszym `offset` i tą samą treścią daje `ok`, z inną treścią `invalid`); na końcu `xfer_commit`. Stacja sprawdza łączny rozmiar (`size`) i SHA-256 (`hash`), potem treść; każdy błąd daje `rejected` i zostawia poprzedni stan bez zmian. Odczyt: `xfer_begin` → `ok` z `xfer`, `size` i `sha256`; potem `xfer_read` → `data` z `offset` i `data`.

**Dokument `configure`** to obiekt JSON z kompletną konfiguracją:

| Pole | Typ i limit | Znaczenie |
|---|---|---|
| `role` | `stacja` albo `wezel` | stacja schronienia albo węzeł stanowiska |
| `addresses` | lista 1–8 ciągów, każdy 1–64 B | adres schronienia albo lista obiektów; pierwszy jest domyślny; tylko `stacja` |
| `receiver` | `{"main":{"lxmf":…,"key":…},"backup":{"lxmf":…,"key":…}}` | karta odbiorcy z pełnymi kluczami publicznymi (64 B, 128 cyfr szesnastkowych); tylko `stacja` |
| `stations` | 1–1000 | liczba stacji w sieci (okno TEST startowego); tylko `stacja` |
| `phrases` | lista 0–11 trójek [PL, UK, EN], każdy tekst ≤96 B | gotowe frazy; do SA1 trafia PL; tylko `stacja` |
| `ifac` | 32 cyfry szesnastkowe | kod dostępu sieci |
| `radio` | `{"profile":"lora-sf7"}` | profil radiowy ([radio](radio.md)) |

Stacja przy zatwierdzeniu sprawdza każdy tekst według reguł SA1 i odrzuca konfigurację, w której najgorsze zgłoszenie z przycisków (najdłuższy adres, najdłuższa fraza, `people` = 999) przekroczyłoby 256 B po kodowaniu (`invalid`, `detail` = `worst_request`). Odpowiedź `ok` podaje `worst_request` (bajty) i numer konfiguracji `config_seq`. Zmiana `role` restartuje stację po odpowiedzi, bo stos buduje interfejsy przy starcie.

## Przeniesienie stacji

PRZENIEŚ STACJĘ przenosi tożsamość, licznik czasu pracy, konfigurację, rejestr zgłoszeń i skrzynkę ze sprawnej stacji źródłowej na stację zapasową. W każdej chwili najwyżej jedna z nich nadaje z tą tożsamością. Obie stacje są w trybie przygotowania i każdy stan zapisują trwale w FRAM, więc zanik zasilania albo odłączenie przewodu w dowolnym kroku pozwala wznowić albo wycofać operację.

| Krok | Polecenie (stacja) | Skutek | Stan po kroku |
|---|---|---|---|
| 1 | `migrate` `"step":"receive_key"` (docelowa) | stacja pusta (bez tożsamości albo po ZNISZCZ DANE i ponownym przygotowaniu) tworzy parę kluczy przeniesienia X25519 i zwraca klucz publiczny; ekran pokazuje jego odcisk | docelowa: `receiving` |
| 2 | `xfer_begin` `"op":"export"` z `target_key` (źródłowa) | porównanie odcisku z ekranem stacji docelowej przyciskiem OK na źródłowej; stacja przestaje nadawać (także ruch przekazywany i ogłoszenia), zatrzymuje kolejkę i przyciski zgłoszeń, losuje klucz paczki `k` i wydaje paczkę zaszyfrowaną dla `target_key` | źródłowa: `export` |
| 3 | `xfer_begin` `"op":"import"` … `xfer_commit` (docelowa) | odszyfrowanie, kontrola, zapis wszystkich danych pod własnym kluczem FRAM i nową epoką, jedna transakcja; potwierdzenie importu HMAC(`k`, „imported” ‖ skrót paczki) | docelowa: `imported`, nie nadaje |
| 4 | `migrate` `"step":"retire"` z potwierdzeniem importu (źródłowa) | sprawdzenie potwierdzenia; usunięcie tożsamości i danych jak w ZNISZCZ DANE, z zachowaniem długu ciszy; potwierdzenie wycofania HMAC(`k`, „retired” ‖ skrót paczki) | źródłowa: `retired` |
| 5 | `migrate` `"step":"activate"` z potwierdzeniem wycofania (docelowa) | sprawdzenie potwierdzenia, start nadawania z przeniesioną tożsamością | docelowa: zwykła praca |

Paczka: nagłówek (wersja, skrót tożsamości, klucz efemeryczny X25519, skrót paczki), potem części po 512 B, każda szyfrowana AEAD (ChaCha20-Poly1305) kluczem z X25519 i HKDF, z numerem części w nonce. Klucz `k` jest wewnątrz zaszyfrowanej paczki, więc znają go tylko obie stacje; służy wyłącznie do potwierdzeń HMAC. Stacja źródłowa w stanie `export` nie zmienia danych, więc może wydać tę samą paczkę ponownie. Paczka nigdy nie zawiera jawnego klucza prywatnego. Licznik czasu pracy stacji docelowej przyjmuje większą z dwóch wartości ([czas](oprogramowanie.md#czas)).

**Wznowienie i wycofanie:**

| Przerwanie | Postępowanie |
|---|---|
| przed krokiem 3 albo z niepewnym wynikiem kroku 3 | najpierw `migrate` `"step":"abort"` na docelowej: usuwa zaimportowane dane, jeśli są, i zwraca potwierdzenie HMAC(`k`, „aborted” ‖ skrót paczki); dopiero z tym potwierdzeniem `abort` na źródłowej przywraca zwykłą pracę i unieważnia `k`. Gdy docelowa nie odpowiada, źródłowa wraca do pracy dopiero po ZNISZCZ DANE na docelowej, potwierdzonym przyciskiem i wpisanym do dziennika; tak dwie stacje nigdy nie mają naraz aktywnej tej samej tożsamości |
| po kroku 3, przed 4 | powtórzyć krok 4; docelowa nie nadaje, dopóki nie dostanie potwierdzenia wycofania |
| źródłowa uległa awarii po kroku 3 | `migrate` `"step":"activate"` z `"forced":true` na docelowej, z potwierdzeniem przyciskiem OK na niej i wpisem w dzienniku zdarzeń; osoba utrzymująca system odłącza źródłową od anteny i zasilania, a przy ponownym uruchomieniu wykonuje na niej ZNISZCZ DANE |
| po kroku 4, przed 5 | powtórzyć krok 5 (potwierdzenie wycofania zapisuje źródłowa) |

Źródłowa w stanie `export` albo `retired` i docelowa w stanie `imported` pokazują na ekranie `tryb_przygotowania` i nie wychodzą z trybu przygotowania, dopóki operacja się nie zakończy albo nie zostanie wycofana. Uszkodzonej stacji nie da się przenieść: stacja zapasowa dostaje nową tożsamość, a stanowisko odbiorcze zmienia listę zaufanych stacji ([model zaufania](oprogramowanie.md#model-zaufania-i-kluczy)).

**Baza laptopa** przechodzi osobno, kopią przez API kopii SQLite. Klucz bazy laptopa jest kluczem danych opakowanym dwa razy: kluczem z pliku na pamięci USB zestawu i sekretu magazynu systemowego (DPAPI/TPM, Keychain) oraz kluczem z hasła odtworzenia (co najmniej 6 słów z listy, Argon2id), które leży w kopercie przy stacji razem z hasłami panelu. Na nowym komputerze aplikacja otwiera kopię hasłem odtworzenia i opakowuje klucz danych sekretem nowego magazynu systemowego; hasło odtworzenia zmienia potem osoba utrzymująca system. Bez kopii bazy nowy laptop odtwarza stan zgłoszeń SA1 migawką ze stacji; tracone są tylko dane mieszkańców i tokeny strony.

## Przebiegi

**Pierwsze połączenie (stacja skonfigurowana, nowa baza laptopa):**

```text
S→L {"usb":2,"seq":1,"type":"hello","boot":"9c…","contracts":[2],"role":"stacja","prep":false,"configured":true,"epoch":"51…","head":214,"min":1,"migration":"none",…}
L→S {"usb":2,"seq":1,"type":"sync","boot":"a0…","epoch":"","cursor":0}
S→L {"usb":2,"seq":2,"type":"snap_required","re":1,"epoch":"51…","head":214,"min":1,"reason":"epoch"}
L→S {"usb":2,"seq":2,"type":"snapshot","epoch":"51…"}
S→L snap_begin, 37 × snap, snap_end (head 214)
L    jedna transakcja SQLite: kopia stanu i kursor (51…, 214)
L→S {"usb":2,"seq":3,"type":"ack","epoch":"51…","cursor":214}
```

**Utrata odpowiedzi `stored`:** laptop wysyła `submit` (`id` X, `revision` 0), stacja zapisuje i odpowiada `stored`, przewód zostaje odłączony, zanim odpowiedź dotrze. Po ponownym połączeniu: `hello`, `sync` z zapisanym kursorem, `sync_ok`, zdarzenie `own` dla X, potem ponowiony `submit` X/0 → `stored` z `"duplicate":true`. W stacji jest jedno zgłoszenie.

**Restart obu stron:** stacja wraca z nowym `boot` i tym samym `epoch`, laptop z kursorem z SQLite. `sync` → `sync_ok` od kursora; zdarzenia z czasu restartu przychodzą po kolei; niepotwierdzone polecenia laptop ponawia.

**Laptop odłączony przez kilka dni:** stacja wygenerowała 900 zdarzeń, pierścień trzyma 256. `sync` z kursorem sprzed odłączenia → `snap_required` z `gap` → migawka.

**Odrzucenie i ponowne połączenie:** `submit` przy pełnej kolejce → `rejected` `full`; panel pokazuje `kolejka_pelna`, intencja zostaje w SQLite oznaczona jako odrzucona, a opiekun używa formularza papierowego. Laptop nie ponawia automatycznie odmowy `full`; opiekun może wysłać ją ponownie, gdy kolejka się zwolni.

**Konfiguracja:** `xfer_begin` `configure` (`size` 5120, `sha256`), 10 × `xfer_part`, `xfer_commit` → `ok` z `worst_request` 220 i `config_seq` 3; zdarzenie `station` `config`.

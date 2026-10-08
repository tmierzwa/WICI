# WICI: protokół USB laptop–stacja

Rozdział jest samodzielnym kontraktem implementacyjnym protokołu między aplikacją laptopa (poziomy 2–3) albo laptopem osoby utrzymującej system (tryb przygotowania) a stacją. Zamyka decyzję D17 po stronie specyfikacji; próby są w [odbiorze](odbior.md) (wiersze „Protokół USB”, „Laptop i USB”, „Przeniesienie”, „Aktualizacja oprogramowania”). Kod stanowiska deweloperskiego (`firmware/src/usbproto.cpp`) realizuje wersję 2 bez przeniesienia i aktualizacji oprogramowania; różnice wymienia [przegląd](../review.md) (F107).

W pilotażu protokół służy tylko w trybie przygotowania: konfiguracja, karta stacji, PRZENIEŚ STACJĘ i aktualizacja oprogramowania. Aplikacja laptopa w schronieniu (poziomy 2–3) dochodzi po pilotażu i używa tego samego kontraktu.

## Zasady

- **Źródło prawdy.** Stan zgłoszeń, skrzynki i konfiguracji przechowuje stacja w FRAM. Laptop przechowuje kopię i własne dane (zgłoszenia mieszkańców, tokeny), a stacji przekazuje tylko intencje. Laptop nie ma tożsamości Reticulum.
- **Bezpieczeństwo przy powtórzeniu.** Każde polecenie zmieniające stan jest idempotentne po kluczu treści (tabela niżej), nie po numerze `seq`. Laptop po utracie odpowiedzi wysyła to samo polecenie ponownie, z nowym `seq`. Klucz powtórzenia obowiązuje w obrębie jednej epoki ([synchronizacja](#synchronizacja)), dopóki stacja pamięta jego skutek; kiedy tej pamięci zabraknie, laptop nie ponawia automatycznie, tylko pokazuje wynik jako nieznany ([niepewny wynik](#niepewny-wynik-polecenia)).
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

**Numeracja wierszy.** Wiersz, z którego nie da się odczytać `seq` (za długi, nie JSON, `seq` poza zakresem), dostaje `rejected` bez pola `re`. Każdy wiersz z poprawnym `seq` zużywa ten numer, także odrzucony z powodu `contract`. Wiersz z numerem innym niż poprzedni + 1 dostaje `seq` i nie jest wykonywany, a stacja liczy dalej od numeru laptopa: następny wiersz z numerem o 1 większym jest przyjmowany. Laptop po odmowie `seq` ponawia polecenie z nowym numerem (klucz powtórzenia chroni przed podwójnym skutkiem).

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

**Wersje.** Każda zmiana schematu, nowe pole albo nowy typ oznacza nową wersję. Wyjątek: wersja 2 jest projektem do pierwszego wydania (stanowisko deweloperskie realizuje ją bez przeniesienia i aktualizacji), więc do tego czasu poprawki tego rozdziału jej numeru nie zmieniają. Stacja przyjmuje tylko wersje z listy w `hello`; inna wersja w poleceniu daje `rejected` z `contract`, a stacja nie zmienia stanu. Laptop, który nie zna żadnej wersji z listy, pokazuje „niezgodna wersja stacji” i nie wysyła poleceń.

## Polecenia laptopa

| `type` | Pola | Tryb | Odpowiedź | Klucz powtórzenia |
|---|---|---|---|---|
| `sync` | `boot`, `epoch` (albo `""`), `cursor` | każdy | `sync_ok` albo `snap_required` | sesja |
| `ack` | `epoch`, `cursor` | każdy | brak | `cursor` (zbiorczo) |
| `snapshot` | `epoch` | każdy | `snap_begin`, `snap`…, `snap_end` | sesja |
| `submit` | `id`, `revision`, `sa1` | zwykły | `stored` albo `rejected` | (`id`, `revision`) |
| `cancel` | `id` | zwykły | `ok` albo `rejected`; dla zwolnionego `id` `ok` z `"released":true`, gdy wpis zwolniono jako anulowany, inaczej `too_late` | `id` |
| `test` | `nonce` | zwykły | `stored` albo `rejected` | `nonce` |
| `announce` | brak | zwykły | `ok` albo `rejected` | łączone w 30 s |
| `silence` | `on`, opcjonalnie `exception_id` | zwykły | `pending`, potem `ok` albo `rejected` | stan docelowy |
| `mark_read` | `msg` (numer wiadomości z `snap` lub `event`) | zwykły | `ok` | `msg` |
| `status` | brak | każdy | `status` | – |
| `close` | `epoch`, `head` | zwykły | `pending`, potem `ok` albo `rejected` | (`epoch`, `head`) |
| `destroy` | brak | każdy | `pending`, potem `ok` albo `rejected` | stan docelowy |
| `card` | brak | przygotowania | `card` | – |
| `xfer_begin` | `op`, dalsze pola według `op` | przygotowania | `ok` z `xfer` albo `rejected`; `export` najpierw `pending` | (`op`, `sha256`), dla `export` (`op`, `mid`) |
| `xfer_part` | `xfer`, `offset`, `data` | przygotowania | `ok` z `next` | (`xfer`, `offset`) |
| `xfer_read` | `xfer`, `offset`, `length` (≤512) | przygotowania | `data` | (`xfer`, `offset`) |
| `xfer_commit` | `xfer` | przygotowania | `ok` z wynikiem albo `rejected` | `xfer` |
| `xfer_abort` | `xfer` | przygotowania | `ok` | `xfer` |
| `migrate` | `step`, dalsze pola według kroku ([przeniesienie](#przeniesienie-stacji)) | przygotowania | `ok` albo `rejected`; przy krokach z przyciskiem najpierw `pending` | (`step`, `mid`) |

„Tryb przygotowania” włącza przycisk pod plombowaną pokrywą serwisową; stacja pokazuje wtedy stale `tryb_przygotowania`. Polecenie z kolumny „przygotowania” poza tym trybem daje `prep_required`. Stacja w konfiguracji węzła stanowiska używa tego protokołu tylko w trybie przygotowania; poza nim interfejs danych przenosi pakiety Reticulum w ramkach KISS ([radio](radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)), a polecenia `submit`, `cancel`, `test`, `announce`, `mark_read` i `close` dają tam `role`.

**`submit`.** `sa1` to tablica REQUEST albo TEST zgodna z [SA1](oprogramowanie.md#wiadomości-sa1); `id` i `revision` muszą być równe polom tablicy. Stacja wysyła wiadomość zawsze do aktywnej tożsamości odbiorcy, więc laptop nie podaje adresu. Reguły:

- nowe `id`: wymaga wolnego krótkiego numeru (inaczej `numer_zajety`, laptop losuje nowe `id`) i wolnego miejsca w rejestrze i kolejce (inaczej `full`);
- `revision` większa od najnowszej znanej dla `id`: nowa rewizja według [cyklu życia](oprogramowanie.md#cykl-życia-zgłoszenia);
- ta sama `revision` i ta sama treść: `stored` z `"duplicate":true`; inna treść: `conflict`;
- `revision` mniejsza od najnowszej: `stale`;
- zgłoszenie zamknięte lokalnie (anulowane): `closed`;
- `id` z wpisem zwolnionym z rejestru (w pamięci zwolnionych wpisów, [pamięć FRAM](oprogramowanie.md#pamięć-fram)): ta sama `revision` daje `stored` z `"duplicate":true` i `"released":true`, większa `closed`, mniejsza `stale`. Pamięć zwolnionych wpisów nie przechowuje treści, więc odpowiedź `released` potwierdza tylko, że klucz (`id`, `revision`) był zapisany; zgodności przesłanej treści stacja wtedy nie sprawdza i nie odpowiada `conflict`. Laptop ponawia zawsze treść ze swojej intencji, więc w poprawnym działaniu treść jest ta sama. Stacja nigdy nie tworzy ponownie wpisu dla `id` z tej pamięci.

Odpowiedź `stored`: `{"id":…,"revision":…,"number":"0427","duplicate":false}`; `number` to krótki numer zgłoszenia.

**`cancel`** (ANULUJ WYSYŁKĘ z panelu) działa tylko, dopóki żadna rewizja `id` nie została przekazana do LXMF ([cykl życia](oprogramowanie.md#cykl-życia-zgłoszenia)); później `too_late`, a panel proponuje rewizję „potrzeba ustała”.

**`test`** tworzy TEST jak z menu stacji. `nonce` (16 cyfr szesnastkowych losowanych przez laptop) chroni przed podwójnym TEST przy powtórzeniu polecenia: stacja pamięta ostatnie 8 wartości `nonce` z `id` utworzonego TEST i na powtórzenie odpowiada tym samym `stored`.

**`silence`, `close`, `destroy`** wymagają potwierdzenia przyciskiem OK na stacji w ciągu 30 s. Stacja od razu odpowiada `pending` z `"confirm_s":30`, pokazuje pytanie na ekranie i po potwierdzeniu wykonuje operację; bez potwierdzenia odpowiada `not_confirmed`. `silence` z `"on":false` przy przełączniku CISZA w położeniu „cisza” daje `silence_switch`. `exception_id` (wyjątek dla pojedynczego zgłoszenia) wolno podać tylko przy `"on":true` i tylko gdy ciszę ustawiono z panelu; zasady wyjątku są w [trybach kryzysowych](oprogramowanie.md#tryby-kryzysowe). `exception_id` musi wskazywać wpis rejestru (inaczej `invalid` z `exception_id`); wyjątek obejmuje parę (`id`, `r_max` z chwili potwierdzenia), a pytanie na ekranie (`pytanie_cisza_wyjatek`) podaje krótki numer zgłoszenia. Nowa rewizja tego zgłoszenia nie jest objęta wyjątkiem; laptop ustawia go ponownie. Pytania pozostałych poleceń to `pytanie_cisza_wlacz`, `pytanie_cisza_wylacz`, `pytanie_zamknij` i `pytanie_zniszcz` ([teksty ekranu](oprogramowanie.md#teksty-ekranu)). `close` to ZAMKNIJ ZDARZENIE po stronie stacji: laptop wysyła je dopiero po zapisaniu zaszyfrowanego archiwum, z `epoch` i `head` stanu, który zarchiwizował, i tylko bez niepotwierdzonych poleceń `submit`. Stacja sprawdza warunek dopiero po potwierdzeniu przyciskiem i w tej samej transakcji co usunięcie: `epoch` musi być bieżącą epoką, a po `head` nie może być zdarzenia, które zmienia dane (`own`, `msg` ani `stage` z etapem `received`, `cancelled`, `released` albo nową decyzją); zdarzenia samego postępu wysyłki (`stage` z `sending` i `delivered`), `radio`, `power` i `station` nie blokują. Inaczej stacja odpowiada `stale` i laptop synchronizuje się i archiwizuje ponownie, więc dane przyjęte po archiwizacji nigdy nie znikają. Stacja usuwa rejestr, kolejkę, skrzynkę, pamięć zwolnionych wpisów i pierścień zdarzeń, losuje nowe `epoch`, zapamiętuje parę (stary `epoch`, `head`) i odpowiada `ok` z nowym `epoch`. Ponowione `close` z zapamiętaną parą daje to samo `ok` z `"duplicate":true`, bez drugiego usunięcia. `destroy` to [ZNISZCZ DANE](oprogramowanie.md#tryby-kryzysowe).

**`card`** zwraca kartę stacji: `{"name":"WICI-3fa21c","lxmf":…,"key":<128 cyfr szesnastkowych: klucz publiczny 64 B>,"address":[…],"fingerprint":"…"}`. Odcisk (pierwsze 8 B SHA-256 klucza w grupach po 4 cyfry) stacja pokazuje jednocześnie na ekranie (`odcisk_klucza`, OK albo WSTECZ zamyka).

## Wiadomości stacji

| `type` | Pola | Kiedy |
|---|---|---|
| `hello` | `boot`, `contracts` (lista obsługiwanych wersji), `name`, `lxmf` (adres LXMF stacji, 32 cyfry szesnastkowe; pusty w konfiguracji węzła stanowiska i przed pierwszą konfiguracją), `fw`, `role` (`stacja` albo `wezel`), `prep`, `configured`, `epoch`, `head`, `min`, `migration` | pierwszy wiersz po otwarciu portu; także po `rejected` z `contract` |
| `sync_ok` | `re`, `epoch`, `from`, `head` | kursor laptopa mieści się w pierścieniu; stacja zaczyna wysyłać zdarzenia od `from` |
| `snap_required` | `re`, `epoch`, `head`, `min`, `reason` (`epoch`, `gap`, `ahead`) | kursor laptopa nie pozwala na przyrostową synchronizację |
| `snap_begin`, `snap`, `snap_end` | migawka ([synchronizacja](#synchronizacja)) | odpowiedź na `snapshot` |
| `event` | `epoch`, `ev`, `at`, `kind` i pola rodzaju | zmiana stanu w stacji |
| `stored`, `ok`, `pending`, `data`, `status`, `card` | według polecenia | odpowiedź |
| `rejected` | `re`, `reason`, opcjonalnie `detail` | odmowa; stan stacji bez zmian |

Pola `hello`: `epoch` to bieżąca epoka pierścienia zdarzeń, `head` numer ostatniego zdarzenia, `min` najstarszego zachowanego, `migration` stan [przeniesienia](#przeniesienie-stacji) (`none`, `receiving`, `export`, `imported`, `retired`).

**Pola decyzji** (w `stage` i w wierszu `snap` zgłoszenia): `decision` to liczba 0 (brak decyzji) albo stan 2–6 z ostatniego przyjętego STATUS, `decision_rev` rewizja tego STATUS (0, gdy `decision` = 0), `status_event` najwyższy przyjęty `event` STATUS (0, gdy brak).

**Odpowiedź `status`:**

| Pole | Znaczenie |
|---|---|
| `role`, `prep`, `configured`, `config_seq`, `fw`, `secure_version`, `fram_format` | rola, tryb przygotowania, konfiguracja i wersje (`fram_format`: [wersja formatu FRAM](oprogramowanie.md#aktualizacja-oprogramowania-stacji)) |
| `uptime` | licznik czasu pracy w sekundach ([czas](oprogramowanie.md#czas)) |
| `register`, `intents`, `inbox`, `unread` | zajęte wpisy rejestru (z 256), aktywne intencje, zajęte gniazda skrzynki (z 128), nieprzeczytane wiadomości |
| `receiver`, `last_contact`, `last_contact_lower` | aktywna tożsamość odbiorcy (`main`, `backup`); sekundy czasu dla obsługi ([czas](oprogramowanie.md#czas)) od ostatniej przyjętej wiadomości odbiorcy albo `null`, a `last_contact_lower` = `true`, gdy to dolne oszacowanie po restarcie |
| `silence`, `silence_source`, `exception_id`, `exception_revision` | cisza radiowa jak w zdarzeniu `radio` |
| `power` | `source`, `mv_aa`, `mv_12v`, `alarm` jak w zdarzeniu `power` |
| `migration`, `mid` | stan przeniesienia i jego identyfikator (pusty poza przeniesieniem) |
| `diag` | liczniki diagnostyki: odrzucone wiadomości, odrzucone pakiety K2, długie odroczenia CCA, restarty przez watchdog, BULLETIN pominięte |

**Rodzaje zdarzeń** (`kind`):

| `kind` | Pola | Znaczenie |
|---|---|---|
| `own` | `id`, `revision`, `sa1`, `origin` (`buttons`, `usb`) | nowa rewizja zgłoszenia albo TEST zapisana w stacji, także utworzona przyciskami; rejestr trzyma treść tylko najnowszej rewizji, więc zdarzenie rewizji już zastąpionej wychodzi z `"superseded":true` i bez `sa1` |
| `stage` | `id`, `revision`, `stage`, `attempt`, `next_s`, `decision`, `decision_rev`, `status_event` | zmiana etapu wysyłki według [cyklu życia](oprogramowanie.md#cykl-życia-zgłoszenia): `stored`, `sending`, `delivered`, `received`, `superseded`, `cancelled`, `released` (wpis zwolniony z rejestru) |
| `msg` | `msg`, `from`, `sa1`, `lost` | wiadomość od aktywnej tożsamości odbiorcy przyjęta do skrzynki (REPLY, BULLETIN; RECEIVED i STATUS zmieniają wpis rejestru i dają zdarzenie `stage` z polami `decision`, `decision_rev` i `status_event`); `msg` to numer w skrzynce; `"lost":true` i brak `sa1`, gdy wiadomość usunięto ze skrzynki, zanim zdarzenie wyszło |
| `radio` | `silence`, `silence_source` (`switch`, `panel`), `exception_id`, `exception_revision` (`null` bez wyjątku) | zmiana ciszy radiowej |
| `power` | `source` (`aa`, `12v`), `mv_aa`, `mv_12v`, `alarm` (`none`, `wymien_ogniwa`, `odlaczone_12v`) | zmiana źródła albo alarm energii |
| `station` | `what` (`restart`, `config`, `receiver_backup`, `prep`), `detail` | restart (z przyczyną), nowa konfiguracja, przełączenie na KLUCZ ZAPASOWY, tryb przygotowania |

`at` to czas dla obsługi w sekundach ([czas](oprogramowanie.md#czas)), nie czas kalendarzowy; po restarcie może się cofnąć o ≤60 s względem zdarzeń sprzed restartu.

**Odmowy** (`reason`): `contract`, `too_long`, `seq`, `unknown_type`, `invalid`, `role`, `prep_required`, `not_configured`, `full`, `numer_zajety`, `conflict`, `stale`, `closed`, `too_late`, `memory`, `not_confirmed`, `silence_switch`, `busy`, `size`, `hash`, `signature`, `version`, `format`, `migration`. Znaczenie dla panelu i ekranu:

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

### Niepewny wynik polecenia

Laptop zapisuje przy każdym niepotwierdzonym `submit` epokę i swój kursor (`epoch`, C) z chwili pierwszego wysłania. Stacja przy zwolnieniu wpisu z rejestru zapisuje `id`, `revision` i numer zdarzenia `released` w pamięci zwolnionych wpisów (256 ostatnich w epoce, [pamięć FRAM](oprogramowanie.md#pamięć-fram)). `tomb_floor` to najmniejszy numer zdarzenia, od którego pamięć jest kompletna: 1, dopóki nic z niej nie wypadło, potem numer `released` najstarszego zachowanego wpisu. Po ponownym połączeniu laptop rozstrzyga:

| Sytuacja | Postępowanie laptopa |
|---|---|
| ta sama epoka i `sync_ok` | zdarzenia od C + 1 pokazują `own` dla (`id`, `revision`), jeśli zapis nastąpił; ponowienie jest bezpieczne (stacja odpowie z wpisu albo z pamięci zwolnionych) |
| ta sama epoka, migawka, `tomb_floor` ≤ C + 1 | `id` z `revision` co najmniej równą wysłanej w migawce albo wśród zwolnionych: zapis nastąpił (wcześniej albo z nowszą rewizją); poza nimi: zapisu nie było, ponowienie jest bezpieczne |
| ta sama epoka, migawka, `tomb_floor` > C + 1 albo inna epoka | wynik nieznany: laptop nie ponawia, a panel pokazuje wynik „nieznany” z `id` i krótkim numerem; opiekun sprawdza zgłoszenie na ekranie stacji i w razie potrzeby tworzy nowe (nowe `id`) |

Migawka zawiera zwolnione wpisy jako wiersze `{"item":"released","id":…,"revision":…,"ev":…,"number":…}`, a `snap_begin` pole `tomb_floor`. Krótki numer zwolnionego wpisu pozostaje zajęty, dopóki wpis jest w pamięci zwolnionych wpisów.

**`test` i `cancel`.** Wpis TEST w rejestrze przechowuje `nonce`, a zdarzenie `own` i wiersz `snap` TEST mają pole `nonce`; laptop rozpoznaje więc zapis po `nonce` tak jak `submit` po `id`. Po zwolnieniu wpisu TEST pamięć 8 ostatnich `nonce` nie wystarcza do rozstrzygnięcia, więc przy luce laptop nie ponawia TEST automatycznie, tylko pokazuje wynik „nieznany”; podwójny TEST jest nieszkodliwy, a brakujący opiekun widzi na ekranie stacji. `cancel` jest bezpieczny do ponowienia zawsze: dla wpisu anulowanego daje `ok`, dla `id` zwolnionego jako anulowany `ok` z `"released":true` (pamięć zwolnionych wpisów ma znacznik anulowania), a dla zgłoszenia, które stacja już nadała, także zwolnionego, `too_late`.

## Synchronizacja

**Pierścień zdarzeń.** Stacja zapisuje każde zdarzenie w pierścieniu w FRAM na 256 wpisów (16 bloków po 16 wpisów, [pamięć FRAM](oprogramowanie.md#pamięć-fram)), w tej samej transakcji co zmianę stanu, której dotyczy. Wpis (24 B) zawiera numer `ev`, czas, rodzaj, odwołanie do rekordu (gniazdo rejestru zgłoszeń albo skrzynki z generacją gniazda 2 B i rewizją; dla `released` numer wpisu w pamięci zwolnionych) i pola rodzaju bez treści SA1. Generacja gniazda rośnie przy każdym ponownym zajęciu gniazda; gdy przy wysyłaniu zdarzenia nie zgadza się z gniazdem, zdarzenie wychodzi z `"lost":true` i bez `sa1`, a `id` laptop bierze z wcześniejszego zdarzenia albo z migawki. Wpis pamięci zwolnionych przeżywa każde zdarzenie pierścienia, które na niego wskazuje, bo obie struktury mają 256 wpisów, a zwolnienie zawsze daje zdarzenie; treść SA1 stacja czyta z tego rekordu przy wysyłaniu. Nowy wpis nadpisuje najstarszy niezależnie od `ack`, więc laptop nie jest potrzebny do pracy stacji. `ev` rośnie o 1 w obrębie epoki; `min` to najstarszy zachowany wpis.

**Epoka.** `epoch` to 8 losowych bajtów. Stacja losuje nową epokę przy utworzeniu tożsamości, po ZAMKNIJ ZDARZENIE, po ZNISZCZ DANE, po imporcie PRZENIEŚ STACJĘ i po odtworzeniu uszkodzonego bloku pierścienia ([rekordy uszkodzone](oprogramowanie.md#pamięć-fram)). Nowa epoka zaczyna od `ev` = 1, z wyjątkiem odtworzenia pierścienia: wtedy numeracja biegnie dalej od najwyższego numeru, który mógł być w uszkodzonym bloku, bo numery zdarzeń wskazuje też pamięć zwolnionych wpisów, a rejestr i skrzynka zostają. `ev` nie osiąga 2³²−1 w życiu stacji (przy zdarzeniu co sekundę to 136 lat); przy tej wartości stacja odmawia zapisu (`memory`).

**Kursor laptopa** to para (`epoch`, `cursor`): ostatnie zdarzenie zatwierdzone w SQLite. `ack` jest zbiorczy: potwierdza wszystkie zdarzenia z `ev` ≤ `cursor`. Laptop zapisuje kursor w tej samej transakcji co skutki zdarzeń, więc restart laptopa nigdy nie pomija zdarzenia; zdarzenie powtórzone po restarcie laptop rozpoznaje po (`epoch`, `ev`) i pomija.

**Decyzja po `sync`:**

| Warunek | Odpowiedź stacji |
|---|---|
| `epoch` równe bieżącemu i `min` − 1 ≤ `cursor` ≤ `head` | `sync_ok` z `from` = `cursor` + 1 |
| `epoch` inne albo puste (nowy laptop, nowa baza, ZAMKNIJ ZDARZENIE) | `snap_required`, `reason` = `epoch` |
| `cursor` < `min` − 1 (laptop odłączony dłużej, niż mieści pierścień) | `snap_required`, `reason` = `gap` |
| `cursor` > `head` (baza laptopa nowsza niż stacja: podmieniona FRAM albo inna stacja z tą samą nazwą) | `snap_required`, `reason` = `ahead`; panel pokazuje ostrzeżenie |

Kursor nie jest numerem rekordu FRAM, więc porządkowanie pamięci stacji go nie zmienia.

**Migawka.** Na `snapshot` stacja wysyła `snap_begin` (`epoch`, `head`, `count`, `tomb_floor`), potem po jednym wierszu `snap` na każdy wpis rejestru zgłoszeń, każdy zwolniony wpis i każdą wiadomość skrzynki, potem `snap_end` (`epoch`, `head`). Wiersz `snap` zgłoszenia: `{"item":"request","id":…,"revision":…,"sa1":[…],"stage":…,"decision":…,"decision_rev":…,"status_event":…,"reply_event":…,"number":…}`; wiadomości: `{"item":"msg","msg":…,"from":…,"received_at":…,"read":…,"sa1":[…]}`. Migawkę stacja buduje z jednego, spójnego stanu: zmiany w czasie migawki dostają zwykłe zdarzenia z `ev` > `head`. Laptop stosuje migawkę w jednej transakcji SQLite dopiero po `snap_end`: zastępuje kopię stanu stacji, zachowuje własne dane mieszkańców i ustawia kursor (`epoch`, `head`). Przerwana migawka nie zmienia bazy laptopa.

**Powiązanie laptopa ze stacją.** Baza laptopa zapisuje nazwę i adres LXMF stacji (pola `name` i `lxmf`) z pierwszego `hello` po konfiguracji. Stacja o innym adresie wymaga potwierdzenia w panelu („inna stacja”) i zawsze migawki; dane mieszkańców pozostają przy zgłoszeniach, które już mają `id` SA1 tej drugiej stacji, tylko jako historia.

## Transfery dzielone na części

Dane większe niż jeden wiersz przechodzą przez transfer: konfiguracja (`configure`), paczka PRZENIEŚ STACJĘ (`export`, `import`), obraz oprogramowania (`firmware`) i odczyt pełnej konfiguracji (`config_get`). Naraz otwarty jest najwyżej jeden transfer; `xfer_begin` porzuca niezakończony poprzedni.

| `op` | Kierunek | Pola `xfer_begin` | Największy rozmiar | Zatwierdzenie |
|---|---|---|---|---|
| `configure` | do stacji | `size`, `sha256` | 7680 B (kopia konfiguracji 8 KiB z narzutem, [pamięć FRAM](oprogramowanie.md#pamięć-fram)) | pełna kontrola i zapis w drugiej kopii konfiguracji, przełączenie kopii zwykłą transakcją wskaźnika ([zapis kopii A/B](oprogramowanie.md#zapisy-większe-niż-transakcja); konfiguracja nigdy nie jest łączona z poprzednią) |
| `import` | do stacji | `size`, `sha256`, `mid` | 256 KiB | według [przeniesienia](#przeniesienie-stacji) |
| `firmware` | do stacji | `size`, `sha256`, `version` | rozmiar gniazda obrazu ([aktualizacja](oprogramowanie.md#aktualizacja-oprogramowania-stacji)) | sprawdzenie podpisu, wersji i obsługiwanego formatu FRAM (`format`), oznaczenie gniazda jako oczekującego |
| `export` | ze stacji | `target_key`, `mid` | 256 KiB | według [przeniesienia](#przeniesienie-stacji) |
| `config_get` | ze stacji | brak | 7680 B | – |

Zapis: `xfer_begin` → `ok` z `xfer` (8 cyfr szesnastkowych) i `"max_part":512`; potem `xfer_part` z kolejnymi `offset` od 0 (`offset` musi być równy `next` z poprzedniej odpowiedzi; część powtórzona z mniejszym `offset` i tą samą treścią daje `ok`, z inną treścią `invalid`); na końcu `xfer_commit`. Stacja sprawdza łączny rozmiar (`size`) i SHA-256 (`hash`), potem treść; każdy błąd daje `rejected` i zostawia poprzedni stan bez zmian. Odczyt: `xfer_begin` → `ok` z `xfer`, `size` i `sha256`; potem `xfer_read` → `data` z `offset` i `data`.

**Dokument `configure`** to obiekt JSON z kompletną konfiguracją, kodowany jak wiersze protokołu (UTF-8, bez sekwencji `\u`), więc limit 7680 B mieści konfigurację największą według tabeli (około 4,5 KB):

| Pole | Typ i limit | Znaczenie |
|---|---|---|
| `role` | `stacja` albo `wezel` | stacja schronienia albo węzeł stanowiska |
| `addresses` | lista 1–8 ciągów, każdy 1–64 B | adres schronienia albo lista obiektów; pierwszy jest domyślny; tylko `stacja` |
| `receiver` | `{"main":{"lxmf":…,"key":…},"backup":{"lxmf":…,"key":…}}` | karta odbiorcy z pełnymi kluczami publicznymi (64 B, 128 cyfr szesnastkowych); tylko `stacja` |
| `stations` | 1–1000 | liczba stacji w sieci (okno TEST startowego); tylko `stacja` |
| `phrases` | lista 0–11 trójek [PL, UK, EN], każdy tekst ≤96 B | gotowe frazy; do SA1 trafia PL; tylko `stacja` |
| `ifac` | 32 cyfry szesnastkowe | kod dostępu sieci |
| `radio` | `{"profile":…}`: `lora-sf7` ([profil LoRa pilotażu](radio.md#profil-lora-pilotażu)) albo `p1` ([profil P1](radio.md#profil-p1-do-prototypu): stanowiska deweloperskie i wariant zapasowy) | profil radiowy; inny niż profil układu radiowego stacji daje `invalid` z `radio` |

Stacja przy zatwierdzeniu sprawdza każdy tekst według reguł SA1 i odrzuca konfigurację, w której najgorsze zgłoszenie z przycisków (najdłuższy adres, najdłuższa fraza, `people` = 999) przekroczyłoby 256 B po kodowaniu (`invalid`, `detail` = `worst_request`). Przy limitach pól z tej tabeli (adres ≤64 B, fraza ≤96 B) najgorsze zgłoszenie ma 220 B, więc ta odmowa chroni tylko przed przyszłą zmianą limitów; wcześniej działają odmowy `addresses` i `phrases`. Odpowiedź `ok` podaje `worst_request` (bajty) i numer konfiguracji `config_seq`. Zmiana `role` restartuje stację po odpowiedzi, bo stos buduje interfejsy przy starcie.

## Przeniesienie stacji

PRZENIEŚ STACJĘ przenosi tożsamość, licznik czasu pracy, konfigurację, rejestr zgłoszeń, pamięć zwolnionych wpisów, skrzynkę i zbiór powtórzeń BULLETIN ze sprawnej stacji źródłowej na stację zapasową. W każdej chwili najwyżej jedna z nich nadaje z tą tożsamością. Obie stacje są w trybie przygotowania i każdy stan zapisują trwale w FRAM, więc zanik zasilania albo odłączenie przewodu w dowolnym kroku pozwala wznowić albo wycofać operację.

**Klucze i potwierdzenia.** Stacja docelowa w kroku 1 losuje identyfikator przeniesienia `mid` (16 B) i parę kluczy przeniesienia X25519 (`target_key`). Stacja źródłowa w kroku 2 losuje raz dla danego `mid` parę efemeryczną X25519 (`eph`), zapisuje ją w FRAM ze stanem `export` i używa jej przy każdym ponownym wydaniu paczki, i wyznacza klucz potwierdzeń `k` = HKDF-SHA-256(X25519(`eph`, `target_key`), „WICI migrate” ‖ `mid`); docelowa wyznacza ten sam `k` z własnego klucza prywatnego i publicznego `eph`. `eph` nie jest tajny: jest w nagłówku paczki, a źródłowa podaje go też w odpowiedzi na `status` przeniesienia. Docelowa zna więc `k` także wtedy, gdy paczka do niej nie dotarła. Potwierdzenia „imported” i „retired” to HMAC-SHA-256(`k`, nazwa ‖ `mid` ‖ skrót paczki), a „aborted” zawsze HMAC-SHA-256(`k`, „aborted” ‖ `mid`), bo docelowa może nie mieć paczki albo mieć ją tylko częściowo. Laptop, który poda fałszywy `eph`, dostaje potwierdzenie, którego źródłowa nie przyjmie, więc operacja pozostaje bezpieczna.

| Krok | Polecenie (stacja) | Skutek | Stan po kroku |
|---|---|---|---|
| 1 | `migrate` `"step":"receive_key"` (docelowa) | stacja pusta (bez tożsamości albo po ZNISZCZ DANE i ponownym przygotowaniu) losuje `mid` i `target_key`; odpowiedź `ok` z `mid`, `key` i `fingerprint`; ekran pokazuje odcisk | docelowa: `receiving` |
| 2 | `xfer_begin` `"op":"export"` z `target_key` i `mid` (źródłowa) | porównanie odcisku z ekranem stacji docelowej przyciskiem OK na źródłowej (`pending`); stacja przestaje nadawać (także ruch przekazywany i ogłoszenia), zatrzymuje kolejkę i przyciski zgłoszeń, wyznacza `k` i wydaje paczkę zaszyfrowaną dla `target_key` | źródłowa: `export` |
| 3 | `xfer_begin` `"op":"import"` z `mid` … `xfer_commit` (docelowa) | odszyfrowanie, kontrola i zapis etapami z publikacją jednym znacznikiem ([import](oprogramowanie.md#zapisy-większe-niż-transakcja)); odpowiedź `ok` z `confirm` = potwierdzenie „imported” | docelowa: `imported`, nie nadaje |
| 4 | `migrate` `"step":"retire"` z `mid` i `confirm` (źródłowa) | sprawdzenie potwierdzenia; usunięcie tożsamości i danych jak w ZNISZCZ DANE, z zachowaniem długu ciszy; odpowiedź `ok` z `confirm` = potwierdzenie „retired” | źródłowa: `retired` |
| 5 | `migrate` `"step":"activate"` z `mid` i `confirm` (docelowa) | sprawdzenie potwierdzenia, usunięcie klucza prywatnego przeniesienia, start nadawania z przeniesioną tożsamością | docelowa: zwykła praca, `none` |

**Pola `migrate`:**

| `step` | Stacja | Pola | Odpowiedź |
|---|---|---|---|
| `receive_key` | docelowa | brak | `ok` z `mid`, `key`, `fingerprint`; powtórzenie w stanie `receiving` zwraca te same wartości |
| `status` | każda | brak | `ok` z `migration`, `mid`, `eph` (źródłowa w stanie `export`), `package` (skrót paczki albo pusty) |
| `retire` | źródłowa | `mid`, `confirm` | `ok` z `confirm` |
| `activate` | docelowa | `mid` i `confirm` albo `"forced":true` | przy `forced` najpierw `pending`; `ok`; stacja pamięta `mid` ostatniego zakończonego przeniesienia, więc powtórzenie daje `ok` z `"duplicate":true` |
| `abort` | docelowa | `mid`, `eph` (pusty przed krokiem 2) | przy stanie `imported` najpierw `pending`; `ok` z `confirm` = potwierdzenie „aborted”, a przy pustym `eph` `ok` bez `confirm`. Stacja zapisuje w FRAM wynik (`mid`, `confirm`) w tej samej transakcji, w której usuwa dane importu i klucz prywatny przeniesienia, więc ponowiony `abort` z tym samym `mid` zwraca to samo potwierdzenie |
| `abort` | źródłowa | `mid` i `confirm` albo `"forced":true` | przy `forced` najpierw `pending`; `ok`; stacja pamięta `mid` ostatniego wycofanego przeniesienia, więc ponowienie po utracie odpowiedzi daje `ok` z `"duplicate":true` |

Nieznany `mid` albo krok niezgodny ze stanem daje `migration`, błędne potwierdzenie `signature`. Paczka: nagłówek (wersja, `mid`, skrót tożsamości, `eph`, skrót paczki), potem części po 512 B, każda szyfrowana AEAD (ChaCha20-Poly1305) kluczem HKDF-SHA-256(X25519(`eph`, `target_key`), „WICI migrate pkg” ‖ `mid`), oddzielonym od `k` innym ciągiem HKDF, z numerem części w nonce. Stacja źródłowa w stanie `export` nie zmienia danych, więc może wydać tę samą paczkę ponownie. Paczka nigdy nie zawiera jawnego klucza prywatnego. Licznik czasu pracy stacji docelowej przyjmuje większą z dwóch wartości ([czas](oprogramowanie.md#czas)).

**Wznowienie i wycofanie:**

| Przerwanie | Postępowanie |
|---|---|
| po kroku 1, przed krokiem 2 | `abort` na docelowej z `mid` i pustym `eph`: usuwa klucz przeniesienia i wraca do `none`; źródłowa nic nie zmieniła |
| po kroku 2, przed krokiem 3 albo z niepewnym wynikiem kroku 3 | laptop odczytuje `eph` ze źródłowej (`migrate` `"step":"status"`), potem `abort` na docelowej z `mid` i `eph`: usuwa dane importu, jeśli są (w stanie `imported` po potwierdzeniu przyciskiem), usuwa klucz prywatny przeniesienia, więc paczki nie da się już odszyfrować, i zwraca potwierdzenie „aborted”. Dopiero z nim `abort` na źródłowej przywraca zwykłą pracę i unieważnia `k`. Gdy docelowa nie odpowiada albo straciła klucz przeniesienia (np. po ZNISZCZ DANE), źródłowa wraca do pracy przez `abort` z `"forced":true` dopiero po ZNISZCZ DANE na docelowej, potwierdzonym przyciskiem na źródłowej i wpisanym do dziennika; tak dwie stacje nigdy nie mają naraz aktywnej tej samej tożsamości |
| po kroku 3, przed 4 | powtórzyć krok 4; docelowa nie nadaje, dopóki nie dostanie potwierdzenia wycofania |
| źródłowa uległa awarii po kroku 3 | `activate` z `"forced":true` na docelowej, z potwierdzeniem przyciskiem OK na niej i wpisem w dzienniku zdarzeń; osoba utrzymująca system odłącza źródłową od anteny i zasilania, a przy ponownym uruchomieniu wykonuje na niej ZNISZCZ DANE |
| po kroku 4, przed 5 | powtórzyć krok 5 (potwierdzenie wycofania zapisuje źródłowa); źródłowa w stanie `retired` nie przyjmuje `abort`, a laptop nie wysyła `abort` do docelowej, gdy `status` źródłowej podaje `retired` |

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

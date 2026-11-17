# WICI: Stos Reticulum, rdzeń i port

Część opisu oprogramowania stacji; spis części jest w [README](../README.md).

## Stos Reticulum

Pierwszy etap próby T3 ([odbiór](../../docs/spec/odbior.md), wiersz „Stos na MCU”): port microReticulum w obrazach `bench-a`, `bench-n1` i `bench-b`, interfejs P1 jako interfejs Reticulum, tożsamość i tablice w FRAM, warstwa aplikacji na pakietach Reticulum. Bez LXMF (następny etap). Kod: `src/rns_node.cpp` (węzeł: start, interfejs P1, IFAC, tożsamości odbiorcy z karty, cisza z wyjątkiem, wysyłanie z potwierdzeniem, stan), `src/p1iface.cpp` (kolejka radiowa, limity, maskowanie IFAC; bez stosu i Arduino), `src/framfs.cpp` (system plików i rekord tożsamości w FRAM), `src/rns_framfs.h` (adapter do microStore), `src/pkthash.h` (lista skrótów 8 B), `src/rns_announce.h` (kiedy ogłaszać), `src/kiss.cpp` (ramki KISS interfejsu USB węzła stanowiska; bez stosu i Arduino), `src/host/node_host.cpp` (ten sam węzeł na komputerze z emulatorem P1).

Własny rdzeń pod tą samą warstwą `rns_node` ([zakres rdzenia](../reticulum-core.md)) zastępuje port od etapu rdzenia 6-3 w obrazach `bench-a`, `bench-n1` i `l0`, od etapu rdzenia 6-4 w `bench-b`; opis portu w tym rozdziale dotyczy obrazów z portem ([wybór stosu](#wybór-stosu-port-albo-rdzeń)), które usuwa etap rdzenia 6-5.

Próba odporności `tests/test_rns_hostile.py` (`tests/native/rns_stress.cpp`) uruchamia stos przez `rnsnode` z ASan i UBSan. Ruch pochodzi od węzła z kluczem sieci, zegar jest symulowany, a w zapisie FRAM występują zaniki zasilania. Trzy awarie z przeglądu 2026-10-21 poprawiają łaty `0005`–`0007`, a zachowanie niezdefiniowane przy małym MTU w żądaniu łącza łata `0008`; wszystkie zostają w próbie jako próby regresji (`--defect`). Generator tej próby buduje pakiety prymitywami rdzenia (`lib/reticulum_core`) dla stacji na porcie i na rdzeniu, a klucze, skróty losowe i IV bierze tylko z `--seed`. Zegar portu sprawdza osobny plik `tests/native/rns_stress_port.cpp`, budowany tylko ze stacją na porcie. Generator zapisuje swoje datagramy (`--dump`), a `tests/test_rns_differential.py` (`GeneratorTrafficTests`, `tools/rns_differential.py --stress-dump`) sprawdza w Reticulum w Pythonie, że ruch niemutowany jest poprawny: kod IFAC, rozpakowanie, podpisy ogłoszeń, szyfrowanie do węzłów generatora i do stacji (klucz stacji próbnej z FRAM) oraz dowody. Pakiety z 128 i więcej skokami `Packet.unpack` ma odrzucić, a datagramy ponad MTU nie mogą przejść IFAC. Wynik próby podaje też liczbę datagramów generatora według rodzaju (`"generated"`).

Na ESP32-S3 (`bench-b-port`, `l0-port`) port wchodzi do obrazu w tej samej konfiguracji, z dwiema różnicami wynikającymi z portu. Po pierwsze, pamięć stosu pochodzi ze sterty ESP-IDF zamiast z puli TLSF o stałym rozmiarze (port na ESP32 nie kompiluje własnego `tlsf.c`, bo ESP-IDF ma TLSF w ROM), więc `RNS` podaje pulę 0, a tablice ogranicza tylko ich pojemność. Po drugie, generator liczb losowych biblioteki Crypto bierze `esp_random()` i zapisuje ziarno w NVS ESP-IDF (na nRF52840 korzysta tylko z TRNG, bez zapisu ziarna). Na obu MCU przed utworzeniem tożsamości stacja wmieszuje w ten generator 32 B z generatora stacji (HMAC-DRBG z 48 B źródła sprzętowego, na ESP32-S3 przy włączonym `bootloader_random_enable`). Obraz kompiluje się i łączy; RAM stosu na ESP32-S3 nie był mierzony.

### Zależności i licencje

Obrazy z rdzeniem dołączają z tej listy tylko Crypto; rdzeń jest na licencji Reticulum ([LICENSE.md](../../LICENSE.md)). Pozostałe biblioteki są w obrazach z portem. Źródła pobiera `tools/stack_deps.py` (skrypt przed kompilacją w `platformio.ini`) z przypiętych commitów do `.pio/stack`, sprawdza commit i nakłada łaty z `patches/`. Bez rozwiązywania zależności przez PlatformIO, bo menedżer bibliotek dobierał nieprzypięte wersje (Crypto z rejestru, microStore z gałęzi głównej). `python3 tools/stack_deps.py --list` wypisuje tabelę.

| Biblioteka | Wersja, commit | Licencja | Uwagi |
|---|---|---|---|
| [microReticulum](https://github.com/attermann/microReticulum) | 0.5.0, `40fa628` | Apache-2.0 | dołącza TLSF (BSD-3-Clause, Matthew Conte) i heatshrink (ISC, Scott Vokes); bez pliku NOTICE |
| [microStore](https://github.com/attermann/microStore) | 0.1.7, `0f28567` | Apache-2.0 w LICENSE, MIT w `library.json` | niespójność u autora; przyjęto Apache-2.0 jako warunek ostrzejszy |
| [Crypto](https://github.com/attermann/Crypto) (fork rweather/arduinolibs) | `984dc89` | MIT | Southern Storm Software |
| [MsgPack](https://github.com/hideakitai/MsgPack) | 0.4.2, `1f552c3` | MIT | |
| [ArxContainer](https://github.com/hideakitai/ArxContainer), [ArxTypeTraits](https://github.com/hideakitai/ArxTypeTraits), [DebugLog](https://github.com/hideakitai/DebugLog) | 0.7.0 `d6affcd`, 0.3.2 `702de9c`, 0.8.4 `b581f7d` | MIT | |
| [ArduinoJson](https://github.com/bblanchon/ArduinoJson) | 7.4.2, `733bc4e` | MIT | |

Licencje zależności są zgodne z MIT kodu WICI i nie dodają ograniczeń użycia. Obraz z nimi trzeba rozpowszechniać z tekstami licencji i informacją o autorach (Apache-2.0, MIT, BSD-3-Clause, ISC); łaty WICI mają licencję zmienianych plików (Apache-2.0, `REUSE.toml`, `LICENSES/Apache-2.0.txt`) i opis zmian w nagłówku każdej łaty.

**Otwarta kwestia (F26, F08).** microReticulum jest przekładem implementacji referencyjnej Reticulum na C++: zachowuje jej strukturę, nazwy i algorytmy, a w komentarzach ma dosłowne fragmenty kodu Pythona. Reticulum ma licencję MIT z dodatkowymi ograniczeniami (F08). Jeśli port jest utworem zależnym od Reticulum, obraz stacji z portem podlega także tym ograniczeniom, tak jak pakiet START, i nie jest oprogramowaniem otwartym w rozumieniu OSI; sama licencja Apache-2.0 portu tego nie rozstrzyga. Repozytorium nie dołącza kodu portu (tylko łaty i commit), więc źródła WICI pozostają na MIT. Propozycja rozstrzygnięcia (port traktowany ostrożnie jak utwór zależny, tekst licencji Reticulum w obrazach, zapytanie do autora portu) jest w [przeglądzie, F26](../../docs/review.md#f26-licencja-portu-microreticulum); decyzja przed D14.

### Łaty

| Łata | Zmiana | Powód |
|---|---|---|
| `0001-pool-without-full-walk` | `pool_malloc` bez `tlsf_walk_pool` i `tlsf_check` przy każdym przydziale (zostają z `-DRNS_DEBUG_HEAP`); liczniki zajętości i szczytu puli (bloki z nagłówkami TLSF i struktura sterująca) | przegląd całej puli przy każdym `new` czynił przetwarzanie ogłoszenia kwadratowym; liczniki do pomiaru RAM |
| `0002-short-packet-hashes` | z `-DRNS_SHORT_PACKET_HASHES` lista skrótów pakietów to `pkthash::ShortHashList` | 4096 × 8 B w RAM (specyfikacja, „Pojemności stosu”) zamiast pełnych skrótów w kontenerach |
| `0003-build-without-neighbor-probing` | licznik sond tylko z `RNS_NEIGHBOR_PROBING` | kompilacja z wyłączonymi sondami sąsiadów |
| `0004-memory-fixed-width-includes` | `Memory.h` dołącza `<cstddef>` i `<cstdint>` | GCC z Ubuntu 26.04 nie dociąga ich przez `<memory>`; bez tego program `host` się nie kompiluje |
| `0005-held-announce-after-loop` | odłożone ogłoszenie wraca do `_announce_table` po pętli retransmisji w `Transport::jobs`, bez przycinania tablicy w pętli | usunięcie i wstawienie wpisu w pętli po tej tablicy unieważniało iterator (odczyt zwolnionej pamięci przy zwykłym ruchu: ogłoszenie i zaraz zapytanie o trasę do tego celu) |
| `0006-short-announce` | `Identity::validate_announce` odrzuca ogłoszenie krótsze niż klucz, skróty, ratchet i podpis | Ed25519 czytał poza buforem; implementacja referencyjna zwraca wtedy fałsz |
| `0007-unpad-empty` | `PKCS7::inplace_unpad` zgłasza wyjątek dla pustych danych i dopełnienia dłuższego niż dane | token 48 B z poprawnym HMAC bez szyfrogramu dawał odczyt przed buforem; implementacja referencyjna zgłasza wyjątek |
| `0008-link-request-small-mtu` | MTU z sygnalizacji w żądaniu łącza poniżej 84 B traktowane jak brak sygnalizacji (`Type::Reticulum::MTU`) | przy takim MTU MDU łącza wychodzi ≤ 0 i trafia do `uint16_t` (zachowanie niezdefiniowane); ta sama wartość co przy wyjątku obok |
| microStore `0001-keep-pinned-keys` | limit liczby rekordów (`max_recs`) pomija klucze przypięte przez `microStore::pinned_key` (`src/rns_node.cpp`: skróty celów głównej i zapasowej tożsamości odbiorcy z konfiguracji, w węźle stanowiska cele ogłoszone przez komputer stanowiska) | specyfikacja, „Pojemności stosu”: wpisów odbiorcy nigdy się nie usuwa; wygaśnięcie TTL i jawne usunięcie działają dalej |

Kompilacja: C++17 z wyjątkami i RTTI (wymóg portu). Pliki z `.pio/stack` kompilują się z `-w` (ostrzeżenia zależności nie są ostrzeżeniami WICI; kod WICI kompiluje się z `-Wall` bez ostrzeżeń) i z `-Os`. Rdzeń Adafruit kompiluje z `-Ofast`, a z tą opcją stos zajmował 254 KB flash więcej (rozwinięte pętle Curve25519 i kontenerów). Wpływu `-Os` na czas podpisu i weryfikacji ogłoszenia na nRF52840 nie zmierzono (lista prób na sprzęcie niżej).

### Interfejs P1

`P1Interface` w `rns_node.cpp` (klasa `RNS::InterfaceImpl`, `HW_MTU` 500, tryb FULL) nad łączem stanowiska (`measure::Bench`: dług ciszy, CCA, odroczenia, fragmentacja). Część bez stosu w `p1iface.cpp`:

- **Kolejka radiowa 4 datagramy.** Pakiet od stosu wchodzi tylko przy wolnym miejscu. Przy pełnej kolejce interfejs odmawia (liczniki `q_full`), a `rnsnode::send` od razu zwraca 0, więc warstwa aplikacji wie o zajętości i ponawia według harmonogramu. Kolejność: dowody i pakiety do celów PLAIN (zapytania o trasę) przed danymi, ogłoszenia na końcu ([radio](../../docs/spec/radio.md#dostęp-do-kanału), punkt 6; [interfejs P1](../../docs/archiwum/p1-radio.md#interfejs-p1-w-stosie-reticulum)). Datagram w nadawaniu zostaje w kolejce do końca serii, więc pakiet przyjęty w trakcie go nie zastępuje (błąd znaleziony w próbie zgodności, test regresji w `tests/test_rns_units.py`). Cisza całkowita (przełącznik albo `silence` bez wyjątku) odmawia stosowi każdego pakietu i opróżnia kolejkę (`silenced`). Datagram, który był już w łączu, odpada razem z serią (`tx_failed`). Cisza z wyjątkiem przepuszcza tylko pakiety wyjęte przez stację: wysłane przez `rnsnode::send` (wiadomość zgłoszenia i zapytanie o trasę) oraz dowody RECEIVED i STATUS tej pary (id, revision). Ogłoszenia czekają na liście. Łącze przyjmuje wtedy tylko datagramy od stosu: `P1TX`, `TXPKT` i `TXCW` milczą przy każdej ciszy. Przy pełnej kolejce interfejs odmawia przed liczeniem podpisu IFAC.
- **Przepływność deklarowana 271 bit/s**: datagram 600 B (1 362 ms nadawania w 7 ramkach) z długiem ciszy 12 × TX. Stos używa jej do limitów czasu i kosztu ogłoszeń.
- **Klasy ruchu K0–K2** ([dostęp do kanału](../../docs/spec/radio.md#dostęp-do-kanału), punkt 6; czas kanału = czas TX + dług ciszy, przesuwne okno 60 min w minutowych przedziałach). K0: własne pakiety, dowody, zapytania o trasę i odpowiedzi; przekazywane zapytania o trasę najwyżej 1 na cel na 60 s i łącznie 5% (`pr_limited`), odpowiedzi na zapytania łącznie 5%, ponad to odrzucane (`pr_resp_limited`). K1: przekazywane dane do aktywnej tożsamości odbiorcy z karty (`rnsnode::setReceivers`), w węźle stanowiska z interfejsu USB i do celów ogłoszonych przez komputer. K2: pozostałe przekazywane dane, razem z ogłoszeniami najwyżej 60% czasu kanału (`k2_pool`), bez ostatniego miejsca w kolejce (`k2_slot`), jeden cel najwyżej 25%, gdy czeka K0 albo K1 (`k2_dest`).
- **Osobny limit ogłoszeń.** Ogłoszenia przekazywane (hops > 0) mają 2% przepływności deklarowanej (`announce_cap` Reticulum): ogłoszenie 202 B co około 5 min. Ponad limit czekają na liście 4 ogłoszeń (jedno na cel, nowsze zastępuje starsze, najmniej skoków najpierw, 3 h życia jak `QUEUED_ANNOUNCE_LIFE`), piąte odpada z licznikiem. Własne ogłoszenia (hops = 0) i odpowiedzi na zapytania o trasę (kontekst PATH_RESPONSE) omijają limit jak w Reticulum, gdzie limit dotyczy tylko ogłoszeń bez przypisanego interfejsu; częstość własnych ustala `rns_announce.h`. microReticulum nie przetwarza kolejki ogłoszeń interfejsu (`process_announce_queue` wyłączone w porcie), dlatego limit jest w interfejsie.
- **IFAC 16 B z `config.ifac`.** Klucz jak `Reticulum._add_interface` z `passphrase` = 32 cyfry szesnastkowe klucza i `ifac_size` = 128 bitów; podpis Ed25519 i maska HKDF jak `Transport.transmit` i `inbound` w e40191b (port nie ma IFAC). Pakiet bez kodu albo z błędnym kodem odpada przed stosem (`ifac_missing`, `ifac_invalid`). Same zera w konfiguracji (stacja przed przygotowaniem) wyłączają interfejs: nie nadaje i odrzuca odbiór (`offline`). Wektor z Reticulum w Pythonie sprawdza test jednostkowy.
- **Dowody.** Cel `wici.sa1` stacji ma `PROVE_APP`: dowód transportowy wychodzi dopiero po decyzji warstwy aplikacji, czyli po COMMIT albo po trwałym odrzuceniu (powtórzenie, zły format, obcy adresat, nadawca spoza zaufania), jak wymaga [dowód po COMMIT](../../docs/spec/oprogramowanie.md#dowód-dostarczenia-po-commit). Wiadomość, której nie przyjęto z braku miejsca albo przez błąd zapisu, dowodu nie dostaje, więc nadawca ją ponawia.

### Węzeł stanowiska

Decyzja D19 ([stanowisko odbiorcze](../../docs/spec/stanowisko-osp.md#stacja-stanowiska)): tożsamość odbiorcy, Reticulum i LXMF w Pythonie oraz baza zgłoszeń działają na komputerze stanowiska, a stacja stanowiska jest zwykłą stacją w konfiguracji węzła stanowiska (konfiguracja z `"role":"wezel"` przez `xfer_begin` z operacją `configure` w trybie przygotowania). Zmiana tej konfiguracji restartuje stację, bo stos buduje interfejsy przy starcie. W tej konfiguracji:

- **Stos** ma drugi interfejs Reticulum `USB` (na rdzeniu drugi interfejs transportu, [wybór stosu](#wybór-stosu-port-albo-rdzeń); w porcie `UsbInterface` w `rns_node.cpp`, `HW_MTU` 500, tryb FULL, deklarowane 1 Mbit/s, żeby limit ogłoszeń nie wstrzymywał ogłoszeń sieci do komputera) i nie ma celu `wici.sa1`: adres jest zerowy, stacja się nie ogłasza, `send` i `ANNOUNCE` odmawiają. Tożsamość stacji służy tylko transportowi; nazwa `WICI-xxxxxx` pochodzi z niej jak zwykle. Transport przekazuje ruch także bez komputera.
- **Ramki KISS** (`src/kiss.cpp`, [radio](../../docs/spec/radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)): ramka danych FEND 0x00 … FEND z FESC, jeden pakiet do 500 B. Polecenia TXDELAY, P, SLOTTIME, TXTAIL i inne są pomijane (`usb_cmds`); tylko port roota WICI-Link przyjmuje dodatkowo ramki z poleceniem 0x02 (HACK bez nauki drogi, `Port::acceptCommand`). Polecenie 0x0F z wartością 1 od komputera włącza kontrolę przepływu (`usb_flow`). Pakiet od komputera trafia do bufora 8 × 500 B i od razu dostaje ramkę gotowości FEND 0x0F 0x01 FEND (jak RNode, `usb_ready`). Przy pełnym buforze gotowość czeka na wolne miejsce, a pakiet ponad bufor odpada (`usb_rx_drop`; za długi: `usb_rx_large`). Niepełna ramka po 100 ms bez bajtu przepada jak w Reticulum. Z bufora pakiet idzie do stosu dopiero, gdy kolejka P1 ma miejsce, więc w czasie długu ciszy czeka w stacji, a komputer na gotowość (Reticulum w Pythonie zwalnia blokadę sam po 5 s).
- **Do komputera:** pakiety, które transport kieruje do interfejsu USB, stacja koduje do bufora 1 KiB. Pętla stacji zapisuje z niego do CDC bez blokowania tyle, ile pokazuje `availableForWrite()`, i usuwa z bufora tylko bajty przyjęte przez `write()`. Dzięki temu zapis częściowy na ESP32 nie ucina ramki; to ta sama funkcja `drain()` co dla protokołu laptop–stacja. Ramka, która się nie mieści, albo pakiet przy zamkniętym porcie przepada (`usb_tx_drop`), a ponowienie zapewnia LXMF komputera i stacji.
- **Interfejs danych CDC** przenosi ramki KISS poza trybem przygotowania i protokół laptop–stacja w trybie przygotowania (zmiana konfiguracji, oprogramowania); przejście między nimi zamyka i otwiera obie strony. Bufor KISS (około 5 KB) powstaje tylko w węźle stanowiska: na rdzeniu na stercie w `begin()`, w porcie w puli stosu.
- **Tablice.** Cele ogłoszone przez komputer (ogłoszenie z interfejsu USB, do 8, najnowsze zastępują najstarsze; `usb_pinned`) są chronione w pełnych tablicach tras i znanych tożsamości jak w specyfikacji „Pojemności stosu”. Na rdzeniu ochrona trwa, dopóki trasa celu idzie przez USB, także po restarcie (z tras w FRAM). W porcie (`microStore::pinned_key`, łata 0001) lista jest w RAM: po restarcie wpisy wracają z FRAM, a ochronę odnawia ogłoszenie komputera, który ogłasza adres po każdym ponownym połączeniu ze stacją.
- **Klasa K1** to pakiety z interfejsu USB i do celów ogłoszonych przez komputer ([interfejs P1](#interfejs-p1)). IFAC dotyczy tylko P1: pakiet z USB dostaje kod przy nadaniu, pakiet z P1 bez poprawnego kodu odpada przed stosem.
- **Ekran** pokazuje kontakt z komputerem (`komputer_osp`, `komputer_brak`), menu STAN i JĘZYK ([ekrany](aplikacja.md#ekrany-stacji)); rejestr, skrzynka i zdarzenia do laptopa są puste (zmiany ciszy i trybu przygotowania idą tylko do dziennika), więc w FRAM pracują tylko tablice stosu, dziennik i konfiguracja.

Program na komputerze z `--node` zastępuje port CDC pseudoterminalem (nazwa w zdarzeniu `ready`), który KISSInterface Reticulum otwiera jak port szeregowy; [próba](#próba-zgodności-z-reticulum) `tools/rns_osp_node.py` łączy go emulowanym P1 ze zwykłą stacją.

### Tożsamość i tablice w FRAM

| Obszar | Adres | Treść |
|---|---|---|
| rekord tożsamości | 0x44000 | 2 sloty × 128 B: znacznik, numer, klucz prywatny 64 B (X25519 + Ed25519), CRC-16; zapis do starszego slotu z odczytem kontrolnym |
| system plików stosu (port) | 0x48000–0x7FDFF | nagłówek, 320 węzłów × 96 B, tablica przydziału 2 B na blok, 1 523 bloki × 128 B (194 944 B danych) |
| bariera przeniesienia | 0x7FE00–0x7FFFF | dwa rekordy po 256 B; niepewny lub aktywny stan przeniesienia blokuje nadawanie przed startem stosu |

Rdzeń Reticulum (obrazy z rdzeniem i `host`; [reticulum-core.md](../reticulum-core.md)) nie używa systemu plików. W tym samym obszarze od 0x48000 ma tablicę znanych celów i tras (`lib/reticulum_core/src/table.h`): 257 gniazd po 568 B (145 976 B). Gniazdo zawiera znacznik zatwierdzenia, numer gniazda i zapisu, cel, ratchet z czasem przyjęcia i emisji, trasę (skoki, następny skok, wygaśnięcie, ostatnie użycie), czas ostatniego użycia wpisu, ogłoszenie trasy do 465 B i CRC-32. Klucz publiczny i skrót losowy są częścią ogłoszenia, a bez ogłoszenia leżą w tym samym miejscu same. W RAM jest indeks 257 × 24 B (cel, czas ostatniego użycia wpisu i trasy) i bufor jednego gniazda.

Zmiana wpisu idzie do wolnego gniazda, a stare jest unieważniane po zatwierdzeniu nowego. Z dwóch zatwierdzonych kopii jednego celu montowanie zostawia nowszą i unieważnia starszą (próby zaniku zasilania w `tests/test_rnscore.py`). Montowanie czyta tylko nagłówki gniazd (znacznik, wersja formatu, numer gniazda). CRC sprawdza każdy pełny odczyt wpisu, a gniazdo z błędną treścią wraca do wolnych (licznik `table_corrupt`). Przy przejściu z portu na rdzeń albo z powrotem drugi stos widzi obszar jako nowy: rdzeń pomija gniazda bez znacznika i wersji formatu, a port formatuje system plików. Tożsamość zostaje.

Tożsamość stacji jest też tożsamością transportu. System plików portu (`framfs.cpp`) trzyma pliki magazynów microStore (Bitcask): tablicę tras, znane tożsamości i buforowane ogłoszenia; w RAM zostaje kopia tablicy przydziału oraz skrót nazwy, długość i pierwszy blok każdego węzła (6 296 B). Zapis nie jest transakcyjny: montowanie odrzuca węzły z błędnym CRC i zerwanym łańcuchem i zwalnia bloki bez właściciela (testy zaniku zasilania w `tests/test_rns_units.py`); w obszarze jest tylko stan odtwarzalny z ogłoszeń. Zegar stosu to czas pracy z dziennika FRAM (`OS::setTimeOffset`), więc wiek tras liczy się dalej po restarcie.

Lista skrótów pakietów (4096 × 8 B, 32 KiB) jest w RAM i nie trafia do FRAM: po restarcie pusta lista może przyjąć ponownie pakiet sprzed restartu, a powtórzenia wiadomości odrzuca warstwa aplikacji po kluczu (id, revision, event).

Rekord formatu magazynu ma znacznik zapisanej tożsamości: przy starcie bez klucza w FRAM i ze znacznikiem stos nie startuje (`identity_lost` w `RNS`), bo nowa tożsamość po błędzie pamięci zmieniłaby adres stacji znany odbiorcy; bez znacznika stos tworzy tożsamość i ustawia znacznik. ZNISZCZ DANE (`destroy` przez USB albo z menu USŁUGI) zatrzymuje stos bez dalszych zapisów (`rnsnode::halt`), a magazyn kasuje konfigurację, rekordy, znacznik, oba sloty tożsamości i obszar tablic stosu; po 0,5 s stacja restartuje (stan w RAM należał do skasowanych rekordów) i ma nową tożsamość. `REBOOT` zapisuje tablice przed restartem.

### Różnice wobec specyfikacji i Reticulum

| Różnica | Koszt i skutek |
|---|---|
| indeks magazynów microStore (Bitcask) w RAM | pełne wpisy tras, tożsamości i ogłoszeń są w FRAM, ale każdy wpis ma w RAM węzeł mapy z kluczem (wektor 16 B) i położeniem 16 B w dwóch magazynach, plus obiekty kontenerów stosu: 233 B na cel przy 32-bitowych wskaźnikach zamiast 24 B ze specyfikacji („Pojemności stosu”); dane w RAM rosną liniowo z liczbą celów |
| lista skrótów pakietów nie jest zapisywana | jak wyżej; specyfikacja tego nie wymaga |
| lista ogłoszeń czekających na limit: 4 wpisy (Reticulum: kolejka do 4096) | przy napływie wielu nowych celów większość retransmisji odpada (odtworzenie 256 ogłoszeń: 268 odrzuceń); dalsze stacje poznają trasę zapytaniem o trasę; liczbę wpisów i limit ustala T5 |
| tablica ogłoszeń do retransmisji: 16 wpisów (port: 100, Reticulum: bez limitu) | mniejszy szczyt RAM (−16 KB); przy limicie 2% więcej retransmisji i tak nie wyjdzie |
| sondy sąsiadów portu wyłączone | brak dodatkowego ruchu; funkcja nie istnieje w Reticulum |
| limit ogłoszeń w interfejsie, nie w transporcie | zachowanie jak `announce_cap` dla ogłoszeń przekazywanych; własne ogłoszenia i odpowiedzi o trasę bez limitu jak w Reticulum |
| usuwanie wpisów tras | port ustawiał `RNS_PATH_TABLE_MAX` tylko dla dawnej tablicy w RAM (`cull_path_table`), a magazyn tras w FRAM nie miał limitu; `rns_node.cpp` ustawia go przez `Transport::path_table_maxsize`. Przy pełnej tablicy (256 tras, 256 znanych tożsamości) odpada najstarszy wpis poza celami odbiorcy z konfiguracji, a w węźle stanowiska poza celami ogłoszonymi przez komputer (łata microStore 0001; [próba zgodności](#próba-zgodności-z-reticulum), krok 7) |
| skróty 8 B | fałszywy duplikat z prawdopodobieństwem rzędu 4096 / 2^64 na pakiet |
| zegar stosu | port odrzuca przesunięcie czasu powyżej 2^32 ms (około 49 dni pracy); do sprawdzenia przed pilotażem |

### Próba zgodności z Reticulum

`tools/rns_interop.py` uruchamia Reticulum e40191b w Pythonie z interfejsem UDP (ten sam klucz IFAC) i program `host` (`pio run -e host`): ten sam węzeł, interfejs P1, IFAC i tablice FRAM (plik) co obraz, z emulatorem łącza P1 (ramki P1, czas nadawania z modelu ramki, dług ciszy 12 × rezerwacja ramek pełnej długości, jak w łączu stacji). `tests/test_rns_stack.py` robi to samo jako test, gdy podano `WICI_PIO` i `WICI_RNS_PYTHON`.

```bash
python3 -m venv .venv-rns && .venv-rns/bin/pip install "git+https://github.com/markqvist/Reticulum@e40191b"
```

```bash
cd firmware && ../.venv-pio/bin/pio run -e host && ../.venv-rns/bin/python tools/rns_interop.py --program .pio/build/host/program --fill 256
```

Wynik (2026-10-08, ostatni przebieg na kodzie z tego commitu, z `--fill 256`): wszystkie 20 sprawdzeń zaliczone.

| Sprawdzenie | Wynik |
|---|---|
| ogłoszenie stacji widoczne w Pythonie (z danymi aplikacji) | tak |
| ogłoszenie z Pythona widoczne w stacji | tak |
| pakiet okazjonalny stacja → Python, dowód transportowy w stacji | tak; od ogłoszenia stacji do pakietu w Pythonie 6,1 s (ogłoszenie i pakiet, każde z długiem 12 × TX) |
| pakiet okazjonalny Python → stacja, dowód w Pythonie | tak; RTT dowodu 4,9 s |
| pakiet odrzucony przez warstwę aplikacji bez dowodu | tak (`PacketReceipt` w Pythonie kończy się `FAILED`) |
| datagram bez IFAC i z błędnym IFAC odrzucony przed stosem | tak, oba policzone |
| 256 dodatkowych ogłoszeń przy celu Pythona przypiętym jako odbiorca: tablica tras pełna (256 celów, limit `RNS_PATH_TABLE_MAX`), lista skrótów 4096 | tak |
| po restarcie programu z tym samym plikiem FRAM: ta sama tożsamość, trasa i tożsamość celu odbiorcy z FRAM, tablica w limicie (256 tras), pakiet bez nowego ogłoszenia, dowód | tak |
| krok 7, nowa pamięć FRAM i tablice po 6 wpisów: cel odbiorcy i 9 dalszych ogłoszeń; odpada najstarszy cel bez ochrony, odbiorca zostaje (trasa i tożsamość) | tak; bez przypięcia odbiorcy odpada (próba kontrolna) |
| krok 8: tożsamość odbiorcy z klucza karty (`receiver`) znana bez ogłoszenia; w ciszy z wyjątkiem ogłoszenie odmówione, a pakiet do odbiorcy z karty wychodzi i dostaje dowód | tak |

Domyślny limit potwierdzenia w Reticulum dla jednego skoku przez szybki interfejs wynosi 12 s; dowód po datagramie 600 B przez P1 może przyjść dopiero po długu ciszy nadawcy i odbiorcy (16,3 s każdy), więc nadawca w Pythonie musi ustawić dłuższy limit (próba: 120 s). Stacja liczy limit według wzoru z [interfejsu P1](../../docs/archiwum/p1-radio.md#interfejs-p1-w-stosie-reticulum) (`rnsnode::send`): co najmniej 60 s, więcej przy wielu skokach, długu i pełnej kolejce. To potwierdza uwagę F02 o limitach czasu po stronie odbiorcy i laptopa.

**Węzeł stanowiska** (`tools/rns_osp_node.py`, druga klasa w `tests/test_rns_stack.py`): dwa programy `host` połączone emulowanym P1 przez UDP, stacja i węzeł stanowiska (`--node`), a w Pythonie Reticulum e40191b jako komputer stanowiska: KISSInterface z `flow_control = Yes` i `bitrate = 24` na pseudoterminalu węzła, bez transportu i interfejsów sieciowych, cel `wici.sa1` w miejscu adresu odbiorcy. Wynik (2026-10-08, kod z tego commitu, dług 12 × TX): wszystkie 12 sprawdzeń zaliczone.

| Sprawdzenie | Wynik |
|---|---|
| węzeł bez adresu (`ready`: same zera) i bez ogłoszenia (`announce` odmawia) | tak |
| komputer włącza kontrolę przepływu (KISS 0x0F 1; cztery polecenia konfiguracji pominięte) | tak |
| ogłoszenie komputera przez węzeł i P1 widoczne w stacji; cel komputera chroniony w tablicach węzła, cel stacji nie | tak; 1,0 s |
| ogłoszenie stacji przez węzeł widoczne w komputerze | tak |
| pakiet okazjonalny stacja → komputer, dowód w stacji | tak |
| pakiet okazjonalny komputer → stacja, dowód w komputerze; limit 184,7 s z samej konfiguracji (`bitrate = 24`: 500 B × 8 / 24 + 6 s + 2 × 6 s), bez `set_timeout` i zmian w kodzie Reticulum; bez opcji `bitrate` limit wynosi 21,3 s ([stanowisko odbiorcze, czasy](../../docs/spec/stanowisko-osp.md#komputer-i-aplikacja-stanowiska)) | tak |
| seria 6 pakietów z komputera: kolejka KISS w Pythonie pusta po 0,27 s (bez blokady 5 s), 6 gotowości, bez odrzutów; wszystkie w stacji po 25 s długu ciszy | tak |

**Węzeł stanowiska na rdzeniu** (`tools/rns_osp_node.py --lxmf`, klasa `OspNodeCoreTests` w `tests/test_rns_stack.py`, etap rdzenia 4b): te same sprawdzenia na dwóch programach `host`, z celem stacji `lxmf.delivery` i komputerem jako odbiorcą z karty stacji (SA1 w wiadomościach LXMF, `tools/sa1_lxmf.py`, wspólne z `rns_interop.py`). Komputer to nadal zwykły Reticulum z LXMF w Pythonie. Dodatkowo:

- cel komputera chroniony po restarcie węzła (z tras przez USB w FRAM),
- zalew z USB w trakcie zgłoszenia stacji przez P1: ogłoszenia z błędnym podpisem (różne cele) i śmieci KISS (ramki ponad 500 B, nieznane polecenia, błędne sekwencje, ramki bez końca), ramka co 20 ms zapisywana w port obok interfejsu Reticulum.

Wynik (2026-10-23, dług 12 × TX): wszystkie 18 sprawdzeń zaliczone. W czasie zalewu (252 ogłoszenia, 125 ramek śmieci):

- węzeł zweryfikował 18 podpisów,
- 234 ogłoszenia odpadły bez żetonu (`usb_ann_limited`),
- w obiegu `loop()` była najwięcej jedna operacja asymetryczna (`loop_ops_max` programu `host`),
- kroki P1 szły dalej,
- zgłoszenie dotarło do komputera z potwierdzeniem.

**Łącze LoRa (etap L7 planu interfejsu LoRa)**: `host` i `host-port` z `--link lora` wysyłają przez UDP ramki w eterze z nagłówkiem RNode (`loraframe`: podział datagramu, składanie), jedna ramka w jednym datagramie UDP; czas nadawania i dług ciszy 12t z czasu łącza (`LinkTiming`), jak w P1. Trzy próby w `tests/test_rns_stack_lora.py` (zadanie `interop-lora` w CI):

- `tools/rnode_emulator.py` to radio RNode dla `RNodeInterface` Reticulum w Pythonie: pseudoterminal z protokołem szeregowym RNode czytanym z `RNodeInterface.py` (wykrycie 0x46, firmware 1.86, platforma 0x90 bez ekranu, echo ustawień w 0,25 s, dane KISS w obie strony, bez kontroli przepływu). Pakiety zamienia na ramki firmware RNode i z powrotem (`tools/rnode_framing.py`, ten sam wzorzec sprawdza `tests/test_loraframe.py`), także z trzecią ramką z samym nagłówkiem przy 508 B; pakiet ponad 508 B przepada jak w RNode.
- `tools/rns_interop.py --link lora`: `RNodeInterface` (IFAC 16 B, ten sam klucz) przez emulator do `host-port` i do `host` (z `--lxmf`). Kroki jak w P1 oraz B (największe datagramy w dwóch ramkach, ogłoszenia i pakiety z dowodem w obie strony), J (para ramek 509 B wstrzyknięta przez UDP: druga ramka ma 256 B, stacja ją odrzuca i liczy w `lora_bad_length`, a pierwsza część przepada po 1 s), D (po pakiecie cisza co najmniej 12t, czyli czas nadawania i dług z czasu łącza).
- `tools/rns_osp_node.py --lxmf --link lora`: węzeł stanowiska i stacje na wspólnym emulowanym medium, komputer z `LXMRouter` za USB przy `bitrate = 41` (kryterium ≤41 b/s, 4000 / 95,71). Pakiet z USB 493–500 B odpada przed radiem i jest liczony (`too_large`); ramki bez IFAC nie dochodzą do komputera; wiadomość LXMF do stacji dostaje dowód przed jakimkolwiek ponowieniem (przebieg 2026-10-30: jedna próba, dowód po 5,8 s, następna próba byłaby po 201,1 s, trzy próby na ponowienie, odstęp z samego `bitrate`); wiadomości SA1 w rodzaju RECEIVED i STATUS ze stacji do komputera przez jeden i dwa skoki (stacja – przekaźnik – węzeł) i LXMF z komputera przez dwa skoki z dowodem; przy odłączonym komputerze węzeł przekazuje ogłoszenia dwóch stacji, które się nie słyszą. Program `host` nie ma warstwy aplikacji stacji, więc RECEIVED i STATUS to treści SA1 wysłane poleceniem `send`, nie wiadomości z `station.cpp`.

Ograniczenia próby:

- Emulator RNode i ramkowanie stacji pochodzą z tego samego odczytania źródła firmware RNode (commit `56775c51`). Próba dowodzi współpracy z `RNodeInterface` i spójności obu stron, a nie zgodności z prawdziwym firmware w eterze; tę da próba sprzętowa z RAK4631.
- Emulator nie opóźnia pakietów czasem nadawania: ciszę 12t stosuje strona stacji, a po stronie komputera łącze jest tylko przejściówką.
- BULLETIN do 50 stacji: 50 wiadomości LXMF do jednej stacji, wysyłanych jak aplikacja stanowiska ([Wysyłka](../../docs/spec/stanowisko-osp.md): najwyżej 4 w drodze, następna po DELIVERED albo FAILED), sprawdzenie `bulletin_50_paced`: 50/50 DELIVERED i `usb_rx_drop` 0. Surowa seria 50 pakietów z komputera gubiłaby pakiety (czas kanału jednego pakietu, około 5 s, przekracza 5 s blokady interfejsu KISS w Pythonie), ale tak aplikacja nie wysyła, a przy 4 wiadomościach w drodze bufor USB węzła (8 slotów) wystarcza. Czas i liczba prób są w wynikach (`bulletin_paced`; przebieg 2026-10-30: 50/50 dostarczonych po jednej próbie, 0 odrzutów, 308,6 s); wymaganie T5 (≤12 min dla 50 stacji) rozstrzyga próba na sprzęcie, nie ten emulator.

Wymagają sprzętu (stanowisko A, dwie płytki albo płytka i Reticulum w Pythonie z modemem P1):

- te same sprawdzenia przez CC1120: ramki P1 w eterze zamiast emulatora, CCA i odroczenia przy ruchu stosu, dług ciszy z dziennika FRAM między pakietami;
- czas podpisu i weryfikacji ogłoszenia, odszyfrowania pakietu i dowodu na nRF52840 przy `-Os` (watchdog 60 s, pętla stacji), czas zapisu tablicy tras do FRAM przy 1 MHz;
- RAM w czasie pracy: wolna sterta po starcie i przy pełnych tablicach (`RNS`: `pool_used`, `pool_peak`), zapas stosów zadań (FreeRTOS `uxTaskGetStackHighWaterMark`), alokacje TinyUSB i newlib poza pulą;
- restart przez watchdog i zanik zasilania w trakcie zapisu tablic (montowanie z naprawą), zimny start trasy po restarcie przekaźnika (`odbior.md`);
- ogłoszenia w ciszy radiowej (żadne nie wychodzi), opóźnienie ogłoszenia startowego, ogłoszenie po 2 nieudanych próbach;
- ograniczenie wierszy stosu w dzienniku zdarzeń (najwyżej 10 na minutę, liczba pominiętych w następnym oknie) przy powtarzającym się błędzie stosu;
- dwie stacje z transportem: przekazywanie ogłoszeń z limitem 2%, trasa A–B–stanowisko;
- węzeł stanowiska: KISS przez interfejs CDC z Reticulum w Pythonie na komputerze (`availableForWrite()` w TinyUSB na nRF52840 i ESP32-S3, odłączenie i ponowne podłączenie komputera, wartość `bitrate` komputera z T3), RAM puli z buforem KISS przy pełnych tablicach.

### Wybór stosu: port albo rdzeń

Program węzła na komputerze ma dwa warianty z tym samym `src/host/node_host.cpp` i interfejsem `rns_node.h`: `host-port` na porcie microReticulum i `host` na rdzeniu Reticulum stacji (`lib/reticulum_core`, [reticulum-core.md](../reticulum-core.md)), w którym `src/rns_node_core.cpp` zastępuje `src/rns_node.cpp`.

Po etapach rdzenia 1 i 2 `host` ma tożsamość i adres, interfejs P1 z kodem dostępu IFAC z rdzenia (ta sama kolejka, klasy ruchu i cisza co w porcie), ogłoszenia (własne i przyjmowane, z polem ratchetu), pakiety do stacji z dowodem, wysyłanie z szyfrowaniem do ratchetu i potwierdzeniem, tablicę znanych celów i tras w FRAM ([tablice w FRAM](#tożsamość-i-tablice-w-fram)) oraz zapytania o trasę (odpowiedzi dla celu stacji i celów z trasą, własne zapytania przy nieznanym celu) i przekazywanie (pakiety HEADER_2, dowody według tablicy odwrotnej, retransmisja ogłoszeń). Odebrany datagram czeka w kolejce odbioru (4 miejsca, licznik `rx_queue_full`), a jeden obieg `loop()` wykonuje najwyżej jeden krok odbioru: sprawdzenie IFAC albo pakiet w transporcie. Ogłoszenia po tanich odrzuceniach, tuż przed weryfikacją podpisu, przechodzą przez limit 3 naraz i 1 na sekundę (licznik `ann_limited`). Pakiety do celu stacji, tuż przed odszyfrowaniem, przechodzą przez osobny limit 4 naraz i 1 na sekundę (licznik `rx_limited`); pakiet bez żetonu nie dostaje dowodu, jak utracony.

Od etapu rdzenia 4b węzeł stanowiska na rdzeniu ma interfejs USB (drugi interfejs transportu, ramki KISS jak w porcie, bez IFAC). Bufor KISS powstaje w `begin()` tylko w tej konfiguracji, a krok odbioru z USB idzie na zmianę z krokiem P1. Ogłoszenia z USB mają osobny limit weryfikacji (8 naraz, 1 na sekundę, `usb_ann_limited`). Do 8 celów samego komputera (trasa przez USB o 1 skoku) jest chronionych w tablicy i w klasie K1, dopóki ich trasa idzie przez USB, także po restarcie. Pakiet z USB z flagą IFAC odpada jak w Pythonie; krok USB bez pracy asymetrycznej nie wstrzymuje retransmisji. Po `halt()` stos nie startuje ponownie aż do restartu.

Od etapu rdzenia 3 cel stacji to `lxmf.delivery` (port zostaje przy `wici.sa1`). Ogłoszenie bez danych z warstwy aplikacji ma dane jak `LXMRouter` z nazwą `WICI-xxxxxx`. `send()` wyjmuje SA1 z zastępczej koperty warstwy aplikacji i wysyła je jako wiadomość LXMF z podpisem stacji do celu `lxmf.delivery` odbiorcy (z klucza karty). Przyjęta wiadomość SA1 z poprawnym podpisem znanego nadawcy wraca do warstwy aplikacji w takiej samej kopercie. Wiadomości od nadawcy spoza karty i inne dane do stacji są trwale odrzucane z dowodem i liczone według powodu (`lxmf_rej_sender`, `lxmf_rej_shape`, `lxmf_rej_stamp`, `lxmf_rej_signature`, razem `lxmf_rejected`). Zły podpis odbiorcy z karty i wiadomość ze znaczkiem pracy dają wpis w dzienniku najwyżej raz na godzinę. Znacznik czasu wiadomości stacji to licznik pracy w sekundach, więc zwykły klient LXMF pokaże datę z 1970 roku.

`tests/test_rns_stack.py` uruchamia na rdzeniu `tools/rns_interop.py` w krokach, które rdzeń już ma (`--steps`), a `tests/test_rns_hostile.py` te same scenariusze wrogiego ruchu co na porcie. `tests/test_rns_differential.py` (`tools/rns_differential.py`) podaje ten sam ruch, także zmutowany, rdzeniowi i Reticulum w Pythonie jako tej samej stacji i porównuje pakiety wychodzące i trasy.

Oba stosy czytają ten sam rekord klucza w FRAM, więc stacja zachowuje tożsamość przy przejściu z portu na rdzeń i z powrotem (adres to cel tej tożsamości: `wici.sa1` na porcie, `lxmf.delivery` na rdzeniu); rdzeń zapisuje nowy klucz X25519 już przycięty (RFC 7748), bo port używa zapisanego klucza bez przycięcia. Sprawdza to `tests/test_rns_stack_choice.py` (z `WICI_PIO`).

Od etapów rdzenia 6-3 i 6-4 obrazy `bench-a`, `bench-n1`, `bench-b` i `l0` są na rdzeniu, a ten sam program stacji z portem budują `bench-a-port`, `bench-n1-port`, `bench-b-port` i `l0-port`. Rdzeń jest kompilowany bez wyjątków i RTTI (C++17), obrazy z portem z nimi (`custom_stack = port` w `platformio.ini`, `tools/stack_deps.py`). Obrazy z portem CI tylko kompiluje, a próby portu na komputerze idą na `host-port`; port usuwa etap rdzenia 6-5.

### Przejście na rdzeń i powrót do portu

Obrazy z rdzeniem mają nowe wersje (`version` w `INFO`): `bench-a-0.2`, `bench-n1-0.2`, `bench-b-0.2` i `l0-0.6`; obrazy z portem zostają przy `bench-a-0.1`, `bench-n1-0.1`, `bench-b-0.1`, a `l0-port` ma `l0-0.7`, więc wersja mówi, który stos działa. Wcześniejsze obrazy prototypu bez interfejsu LoRa to `l0-0.3` (rdzeń) i `l0-0.2` (port).

**Przejście.** Wgrać obraz z rdzeniem (`pio run -e bench-a -t upload`). Tożsamość stacji zostaje, bo oba stosy czytają ten sam rekord klucza w FRAM. Adres to cel tej tożsamości, więc zmienia się z `wici.sa1` na `lxmf.delivery`, a odbiorca poznaje go z pierwszego ogłoszenia. Rdzeń widzi obszar tablic po porcie jako nowy ([tablice w FRAM](#tożsamość-i-tablice-w-fram)), więc znane cele i trasy budują się od nowa z ogłoszeń. Tożsamości odbiorców z karty stacji zostają w konfiguracji. Dziennik, magazyny i konfiguracja nie zmieniają układu. Wiadomości w drodze w chwili przełączenia stacja ponawia jako LXMF, a powtórzenie odrzuca odbiorca po identyfikatorze i rewizji. Start jest dłuższy o samotest rdzenia ([samotest](#samotest-rdzenia-na-płytce); na nRF52840 około 1,1–1,5 s przed ekranem). Na ESP32-S3 port zapisywał ziarno generatora w NVS. Rdzeń bierze losowość z generatora stacji, a wpis w NVS zostaje bez znaczenia.

**Powrót do portu.** Do etapu rdzenia 6-5 to obraz `*-port` z tego samego commita (`pio run -e bench-a-port -t upload`). Tożsamość zostaje, adres wraca do `wici.sa1`, a port nie znajduje nagłówka swojego systemu plików i formatuje obszar tablic, więc tablice budują się od nowa. Po etapie rdzenia 6-5 w `main` nie ma obrazów z portem: obraz `*-port` buduje się z podpisanego znacznika git z adnotacją na ostatnim commicie `main` z tymi obrazami (nazwę znacznika podaje etap rdzenia 6-5), czyli `git checkout <znacznik>`, a potem `pio run -e bench-a-port -t upload`. Budowa pobiera port i jego biblioteki z przypiętych commitów (`tools/stack_deps.py`), więc wymaga, żeby te repozytoria były dostępne.

**Próby na płytkach przed wydaniem i przed etapem rdzenia 6-5** (warunek odbioru obrazów z rdzeniem; etapy rdzenia 6-3 i 6-4 scalono przed nimi; na obrazach końcowych po etapie rdzenia 6-4: `bench-a`, `bench-n1`, `bench-b` i `l0` z rdzeniem; wynik w Issue z etykietą `próba`; dla pilotażu te same próby na prototypie przez LoRa: [próby rdzenia na prototypie](prototyp-l0-i-xiao.md#próby-rdzenia-na-prototypie)):

1. [Samotest rdzenia](#samotest-rdzenia-na-płytce) na DK, płytce v1 z obrazem `bench-n1` i prototypie (`board_selftest.py`): `selftest_ok`, `entropy_ok`, czasy `validate`, `sign` i `token_decrypt`; z nich wynika, czy limity weryfikacji (3 naraz, 1 na sekundę) i kolejka odbioru (4) zostają.
2. RAM w czasie pracy przy pełnej tablicy (256 celów: ogłoszenia z Reticulum w Pythonie przez węzeł stanowiska na USB albo przez P1 z drugiej płytki): wolna sterta i zapas stosów zadań; zapas ≥30% na nRF52840 i ESP32-S3.
3. Dwie płytki przez P1 (CC1120 albo S2-LP): ogłoszenia, pakiet, dowód, zgłoszenie z RECEIVED, dług ciszy z dziennika między pakietami.
4. Płytka jako węzeł stanowiska z Reticulum i LXMF w Pythonie na komputerze: SA1 w obie strony, kontrola przepływu KISS, odłączenie i ponowne podłączenie USB.
5. Przejście i powrót: płytka po pracy na porcie z wypełnioną tablicą, potem obraz z rdzeniem: ta sama nazwa i tożsamość, `table_corrupt`, pierwsze zgłoszenie dostarczone; potem obraz `*-port` i znów rdzeń.
6. Zanik zasilania i restart przez watchdog w trakcie zapisu tablicy: stacja startuje, wpis odbiorcy zostaje.
7. Przekaźnik A–B–stanowisko na P1 z transportem przez 24 h z okresowymi zgłoszeniami: bez restartów, RAM i liczniki stabilne (`RNS`).
8. `bench-b`: start stosu i rola węzła stanowiska na ESP32-S3 z S2-LP.

### Samotest rdzenia na płytce

Próby na komputerze nie obejmują trzech rzeczy, od których zależy rdzeń na płytce. AES-256 na ESP32-S3 liczy moduł sprzętowy przez ESP-IDF (biblioteka Crypto, `AESEsp32.cpp`). Curve25519 i Ed25519 liczą na płytkach na limbach 32-bitowych i są skompilowane kompilatorem płytki (ARM GCC 7.2 z `-Ofast` i `-Os`, Xtensa GCC 14.2). Czasu operacji nie da się zmierzyć bez układu. Obrazy z rdzeniem (`WICI_RNS_CORE`: `bench-a`, `bench-n1`, `bench-b`, `l0`) mają więc samotest (`src/core_selftest.cpp`) na wektorach z Reticulum w Pythonie (`tests/vectors/reticulum.json`; `tests/test_rnscore.py` sprawdza, że to te same wartości i że samotest przechodzi na komputerze):

- **Przy starcie, przed `rnsnode::begin`:** odszyfrowanie i szyfrowanie tokenu (klucz efemeryczny i IV z wektora, więc wynik bajt w bajt), podpis (deterministyczny) i weryfikacja podpisu poprawnego. To obejmuje każdy prymityw rdzenia: X25519, Ed25519, AES-256-CBC w obie strony, SHA-256, SHA-512, HMAC i HKDF. Przy niezgodności stos nie startuje: dziennik dostaje wpis `rns not started: core selftest <próba> failed`, a `INFO` podaje `rns_state: "selftest_failed"`. Przy zgodności dziennik dostaje `core selftest ok <ms>`. Szacunek dla nRF52840 z danych biblioteki Crypto (Cortex-M3 84 MHz, przeskalowane do 64 MHz; [crypto.html](https://rweather.github.io/arduinolibs/crypto.html)): około 1,1 s (3 × Curve25519, podpis, weryfikacja), a z kluczem publicznym liczonym potem w `begin` około 1,5 s. Tyle dłużej czekają ekran (`display.begin` jest po `beginStack`) i obsługa radia w pętli; na ESP32-S3 krócej.
- **Na polecenie `RNS SELFTEST`:** te same próby oraz odrzucenie podpisu zmienionej wiadomości, klucz publiczny z prywatnego (start stosu), przyjęcie i złożenie ogłoszenia, klucz i kod IFAC; przy każdej czas w µs z `micros()`. Na nRF52840 rozdzielczość `micros()` w rdzeniu Adafruit to około 1 ms (takt FreeRTOS), a przy włączonym liczniku DWT (debugger) wartość zawija się po około 67 s; pojedynczy wynik z takim zawinięciem jest błędny, dlatego narzędzie podaje medianę trzech przebiegów.
- **Test zdrowia źródła entropii** przed ziarnem generatora stacji (`drbg::healthy`, w duchu NIST SP 800-90B: test powtórzeń i test proporcji przy założonych 4 b entropii na bajt). Źródła na obu płytkach dają wyjście już przetworzone, więc test wykrywa źródło zablokowane, nie słabe. Odczyt jest powtarzany do trzech razy; na nRF52840 czekanie na bajt jest ograniczone (około 100 ms), więc źródło, które nie odpowiada, nie zatrzymuje startu. Przy niezdrowym odczycie dziennik dostaje wpis przy każdym starcie (`entropy source failed health test` albo `entropy source not responding`), generator dostaje ziarno, ale stos nie tworzy nowej tożsamości (`rns not started: no healthy seed for a new identity`, `rns_state: "entropy_failed"`); zapisana tożsamość działa dalej. Dotyczy wszystkich obrazów, także z portem; wynik jest w `entropy_ok` w `INFO`.

Nieudany samotest, brak zdrowego ziarna i nieudany start stosu są widoczne w dzienniku (`LOG`), w `INFO` (`rns_state`) i na ekranie stacji: każdy stan stosu inny niż `running` i `halted` daje alarm `brak_lacznosci` ([oprogramowanie.md](../../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji)).

Pomiar na płytce (**niewykonany**; wynik w Issue z etykietą `próba`, z plikiem JSON z narzędzia). Wymagania: `pyserial` (`python3 -m pip install pyserial`) i PlatformIO (`pio` w `PATH` albo ścieżka w `WICI_PIO`, np. `WICI_PIO=~/.platformio/penv/bin/pio`).

1. Port diagnostyki to pierwszy interfejs CDC: na nRF52840 „WICI diagnostyka”, na prototypie (ESP32-S3, TinyUSB) interfejsy mogą się zgłaszać jako „TinyUSB CDC” i „CDC2”. `pio device list` pokazuje oba; port diagnostyki ma niższy numer `usbmodem` (np. `/dev/cu.usbmodem1101` przed `…1103` na macOS) i odpowiada na `INFO`. Obraz z rdzeniem wgrać i uruchomić jednym poleceniem:

   ```bash
   python3 firmware/tools/board_selftest.py -e bench-a --port /dev/cu.usbmodem1101 --upload
   ```

   Na płytce v1 ze stanowiskiem `-e bench-n1`, na stanowisku B `-e bench-b`, na prototypie `-e l0` (wgrywanie przez USB-OTG jak w [opisie prototypu](prototyp-l0-i-xiao.md#stacja-l0-l0)). Narzędzie wysyła `INFO`, `LOG 30`, `RNS` i trzy razy `RNS SELFTEST`, wypisuje zgodność i medianę czasu każdej próby, `rns_state`, `entropy_ok` i czas samotestu przy starcie, i zapisuje wszystkie wiersze konsoli w `selftest-<env>-<czas>.json`.
2. Zapisać w raporcie: plik JSON, wersję obrazu (`version`), commit, płytkę (DK, płytka v1 z `bench-n1` albo prototyp i numer egzemplarza), `rns_state` (`running`), `entropy_ok`, czas samotestu przy starcie (`core selftest ok <ms>`), czy `selftest_ok` jest `true` w każdym przebiegu, wpisy `rns …`, `core selftest …` i `entropy …` z dziennika oraz czasy `validate`, `validate_reject`, `sign`, `token_decrypt`, `token_encrypt` i `public_key`. Szacunek do porównania na nRF52840: weryfikacja około 0,4 s, podpis około 0,26 s, `Curve25519` około 0,14 s.

### Pamięć RAM

Pomiar dla obrazu `bench-a` z portem (od etapu rdzenia 6-3 `bench-a-port`; nRF52840, 256 KiB RAM) przy pojemnościach ze specyfikacji: 257 celów w tablicy tras i znanych tożsamości (256 ogłoszeń z Reticulum w Pythonie i jego własne; pomiar sprzed limitu 256 wpisów, więc z zapasem jednego celu), 4096 skrótów na liście skrótów pakietów. RAM statyczna z kompilacji (`arm-none-eabi-size`), stosy zadań z rdzenia Adafruit i `main.cpp`, pula stosu z liczników łaty 0001 (bloki z nagłówkami TLSF i struktura sterująca). Pulę zmierzono w programie węzła zbudowanym jako 32-bitowy (i386, te same rozmiary typów co ARM) przez `tools/rns_ram32.py`, który odtwarza datagramy nagrane w próbie zgodności (`rns_interop.py --fill 256 --capture`); program 64-bitowy na komputerze daje tylko górne ograniczenie (166 904 B szczytu, 154 792 B w stanie ustalonym).

| Pozycja | B | Uwagi |
|---|---|---|
| RAM nRF52840 | 262 144 | |
| obszar SoftDevice S140 | 24 576 | 0x20000000–0x20005FFF zarezerwowane przez bootloader i skrypt linkera, choć Bluetooth nie działa |
| RAM aplikacji | 237 568 | PlatformIO podaje 248 832 B z opisu płytki; skrypt linkera daje mniej |
| statyczna (`.data`, `.bss`, `.noinit`) | 100 908 | magazyny stacji 19 288 (indeksy rejestru, skrzynki i zdarzeń, konfiguracja z frazami), bufor ekranu 12 056, łącze 7 292, ekran i konsola 3 308, protokół USB 2 344 (z kolejką wyjściową 1 025); stos (z interfejsem USB węzła stanowiska), w tym lista skrótów 4096 × 8 B (32 784), kopia tablicy przydziału i skrótów nazw systemu plików FRAM (6 296), obiekty magazynów (1 456) |
| stos główny (MSP) | 2 048 | skrypt linkera |
| stosy zadań FreeRTOS | 24 784 | stacja 16 384, pętla rdzenia 4 096, wywołania zwrotne 3 072, USB 800, bloki zadań około 430 |
| pula stosu na starcie | 17 176 | puste tablice; w tym struktura sterująca TLSF, kolejka i lista ogłoszeń interfejsu P1 |
| pula stosu, stan ustalony przy pełnych tablicach | 77 164 | 233 B na cel w RAM: indeks magazynów microStore i obiekty kontenerów stosu |
| pula stosu, szczyt przy pełnych tablicach | 100 620 | przetwarzanie 256 ogłoszeń w tempie 3 na sekundę; z tablicą ogłoszeń 100 wpisów (domyślna portu) szczyt wynosił 116 572 B i nie mieścił się w RAM, stąd `RNS_ANNOUNCE_TABLE_MAX=16` |
| pula skonfigurowana (`RNS_HEAP_POOL_BUFFER_SIZE`) | 106 496 | szczyt i 6%; zostaje 3 332 B sterty na inne przydziały (TinyUSB, newlib), do sprawdzenia na płytce |

**Zapas** (RAM niezajęty wobec 256 KiB, obszar SoftDevice liczony jako zajęty): 237 568 − 100 908 − 2 048 − 24 784 = 109 828 B zostaje na pulę i resztę sterty. Przy szczycie puli wolne jest 9 208 B, czyli **3,5%**; w stanie ustalonym 32 664 B, czyli **12,5%**. Próg D14 to 30% (78 643 B). Brakuje 69 435 B w szczycie i 45 979 B w stanie ustalonym, jeszcze bez LXMF. Pula zmierzona przed F107; wiadomości do dwóch własnych naraz i tożsamości odbiorcy z karty dokładają w niej niewiele (dwa wpisy znanych tożsamości), co ma potwierdzić pomiar na płytce.

**Węzeł stanowiska** bierze z puli przy starcie bufor KISS (`kiss::Port`, 5 112 B na ARM: 8 × 500 B od komputera, 1 KiB do komputera, liczniki) i nie ma celu `wici.sa1`. Przy zmierzonym szczycie puli zostałoby w niej około 0,8 KB, więc węzeł stanowiska na nRF52840 zależy od D14 tak samo jak LXMF; szczyt w konfiguracji węzła trzeba zmierzyć na płytce (`RNS`). Stacja w schronieniu bufora nie ma (statycznie dochodzi 200 B: lista celów komputera i stan interfejsu).

**Wniosek dla D14.** Obraz stacji ze stosem w tym kształcie nie spełnia warunku zapasu RAM ≥30% na nRF52840. Podział ze specyfikacji (pełne wpisy w FRAM, w RAM indeks 257 × 24 B) jest spełniony tylko co do wpisów: indeks magazynów portu (mapa haszująca z kluczem jako wektor i położeniem 16 B, dwa magazyny) i obiekty kontenerów stosu dają 233 B na cel zamiast 24 B, czyli około 60 KB przy 256 celach. Zejście do 30% wymagałoby dwóch zmian naraz. Pierwsza to zwarty indeks w porcie (tablica posortowanych skrótów i położeń, około 6 KB), czyli zmiana microStore i Transport, a więc głęboka zmiana portu. Druga to odchudzenie obrazu stacji o około 20 KB ([odłożone zmiany](#rozmiar-i-wydajność): pas ekranu −9,6 KB, frazy z FRAM na żądanie −3,2 KB, lista konsoli −1 KB). Do tego LXMF dołoży router, bufor wiadomości i własne tablice. Według [specyfikacji](../../docs/spec/oprogramowanie.md#trwałość-i-potwierdzenia) („Pojemności stosu”) taki wynik jest przesłanką do D14: przed projektem wykonania A porównuje się MCU z większą pamięcią (np. nRF5340, RP2350, STM32U5) z głęboką przebudową portu opisaną wyżej. Pomiar na płytce (polecenie `RNS`) ma potwierdzić liczby z odtworzenia.

System plików FRAM przy pełnych tablicach: 135 680 B z 195 456 B (69%), 8 plików.

**Obrazy na rdzeniu** (od etapów rdzenia 6-3 i 6-4 `bench-a`, `bench-n1`, `bench-b` i `l0`). Pomiar na płytce niewykonany. RAM statyczna z kompilacji:

- 112 276 B na nRF52840 (`bench-n1` 112 488 B),
- 159 136 B na ESP32-S3 (`l0`; `bench-b` 159 176 B; etap rdzenia 4b, z samotestem i z etapu rdzenia 2: tablicą znanych celów w FRAM, zapytaniami o trasę i przekazywaniem).

Rdzeń nie ma puli stosu. W RAM zostaje indeks tablicy. LXMF z etapu rdzenia 3 dokłada 768 B: dane wysyłanej wiadomości (355 B), kopertę przyjętej (338 B), cele odbiorcy w warstwie aplikacji i liczniki odrzuceń. Najgłębsza ścieżka stosu w `rnsnode::loop()` to dowód z kodem IFAC (około 3,7 KB). Odbiór wiadomości SA1 (`packetHook` z kopią wpisu nadawcy z FRAM, `lxmfReceiveSa1` z buforem danych podpisanych 383 B i weryfikacją Ed25519) to około 3,5 KB, plus stos warstwy aplikacji nad `packetHook`. Na nRF próg zapasu 30% (statyczna do około 132 KB przy stosach zadań jak w tabeli wyżej) jest spełniony z nadwyżką około 20 KB.

Flash (pomiar jak wyżej, `main` 31f3f06 z etapami rdzenia 6-3 i 6-4; liczby zmieniają się z każdą zmianą źródeł): `bench-a` 408 420 B z 815 104 B (50,1%), `bench-n1` 417 496 B (51,2%), `l0` 626 561 B, `bench-b` 627 185 B. Bez wyjątków i RTTI obraz zajmuje o 6 640 B mniej na nRF52840 i o 3 528 B mniej na ESP32-S3 (`l0`) niż ten sam obraz z nimi. Bez wyjątków kompiluje się cały obraz z rdzeniem: kod WICI, biblioteka Crypto, biblioteki płytek, a na ESP32-S3 także rdzeń Arduino-ESP32, który domyślnie ma `-fexceptions` (`[core]` w `platformio.ini`). Żadna jednostka kompilowana w obrazie nie wymaga wyjątków (biblioteki ESP-IDF są dołączane gotowe). Wyjątków używa tylko `src/rns_node.cpp` portu.

Flash obrazu z portem (`bench-a`, od etapu rdzenia 6-3 `bench-a-port`): 603 900 B z 815 104 B (74,1%); stos dokłada około 324 KB, w tym Curve25519 i Ed25519, kontenery C++17 z wyjątkami (tablice odwijania `.ARM.extab` i `.ARM.exidx` 27 KB), MsgPack i ArduinoJson.

Port i rdzeń w tych samych obrazach (budowa z 2026-10-23 po etapie rdzenia 4b, RAM statyczna i flash według PlatformIO):

| Obraz | RAM statyczna, port | RAM statyczna, rdzeń | Flash, port | Flash, rdzeń |
|---|---|---|---|---|
| `bench-a` (nRF52840) | 101 268 B | 112 276 B | 617 972 B (75,8%) | 413 972 B (50,8%) |
| `bench-n1` (nRF52840) | 101 492 B | 112 488 B | 622 416 B (76,4%) | 423 096 B (51,9%) |
| `bench-b` (ESP32-S3) | 148 264 B | 159 176 B | 876 925 B (26,2%) | 629 985 B (18,8%) |
| `l0` (ESP32-S3) | 148 248 B | 159 136 B | 877 177 B (26,2%) | 629 393 B (18,8%) |

RAM statyczna portu nie obejmuje jego puli: na nRF52840 pula TLSF (106 496 B) i na ESP32-S3 sterta ESP-IDF są przydzielane w czasie pracy. Od etapu rdzenia 6-3 obrazy z rdzeniem są bez wyjątków i RTTI, więc bez tablic odwijania (wyżej).

### Co zostaje na etap LXMF

- LXMF na stacji (na rdzeniu zrobione w etapie rdzenia 3, `rns_node_core.cpp`; w obrazach `bench-a`, `bench-n1` i `l0` od etapu rdzenia 6-3, w `bench-b` od etapu rdzenia 6-4): wiadomość jako jeden pakiet okazjonalny (D01) z podpisem nadawcy i adresem LXMF zamiast koperty `["WICI",1,od,do,…]`; odstęp ponowienia LXMF co najmniej max(60 s, 2 × skoki × 13 × czas TX największego datagramu + dług ciszy + czas opróżnienia kolejki P1) i najwyżej 2 próby LXMF na ponowienie ([interfejs P1](../../docs/archiwum/p1-radio.md#interfejs-p1-w-stosie-reticulum), F02). Adres LXMF w `card` i `hello` jest już liczony z tożsamości stacji.
- Uwierzytelnienie nadawcy (na rdzeniu od etapu rdzenia 3): zaufanie do odbiorcy po kluczu z karty zamiast adresu w treści koperty; rozpoznanie ruchu od odbiorcy po nadawcy.
- Szyfrowanie rekordów FRAM (AEAD, generacja klucza w nagłówku gniazda, F99) z kluczem KEK w chronionej pamięci MCU, bezpieczny rozruch; PRZENIEŚ STACJĘ (`migrate`, `export`, `import`) i aktualizacja oprogramowania czekają na te klucze.
- Pamięć: LXMF dokłada router i bufor wiadomości; budżet z tabeli wyżej (D14).
- Energia i ekran zasilania: pomiar ogniw i 12 V (`power` w `status` podaje dziś stałe `12v` bez napięć), przypomnienie `wymien_ogniwa`.

## Rozmiar i wydajność

Obiekty statyczne `bench-a` (`arm-none-eabi-nm --size-sort`, po F107): magazyny stacji 19 288 B (indeksy rejestru 256 wpisów, skrzynki 128 wpisów, pamięci zwolnionych wpisów i pierścienia zdarzeń, konfiguracja z frazami i kluczami karty), bufor ekranu 12 056 B (240 wierszy × 50 B i mapa zmian), łącze `measure::Bench` 7 288 B (składanie 8 prób × 600 B), ekran z konsolą 3 300 B, bufor poleceń diagnostyki 1 400 B, protokół USB 1 248 B, warstwa aplikacji 848 B. Listy ekranu biorą numer, kategorię, etap i próby z indeksu w RAM; treść czyta się z FRAM tylko dla otwartej pozycji (z pamięcią podręczną do nowej rewizji). Rejestr jest przeglądany co 100 ms, sprzątanie po ZAMKNIJ ZDARZENIE (`maintain`) idzie w tym samym takcie po jednej transakcji.

Odłożone (z szacunkiem zysku; każde wymaga osobnej zmiany i testów):

| Zmiana | Zysk | Koszt |
|---|---|---|
| frazy z konfiguracji czytane z FRAM na żądanie | −3,2 KB RAM | ekran czyta 97 B na wiersz listy |
| bufor ekranu jako pas jednego wiersza tekstu (48 × 50 B) zamiast całej ramki | −9,6 KB RAM | panel pamięta obraz; każdy wiersz trzeba rysować i wysyłać od razu |
| lista konsoli bez czasu (czas z indeksu przy sortowaniu) | −1 KB RAM | sortowanie z odczytem indeksu |
| mniejszy font (16 × 32 px) | −10 KB flash | wersaliki 2,8 mm, poniżej wymagania ≥3,5 mm |

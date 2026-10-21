# Własny rdzeń Reticulum stacji: zakres

Stan: projekt do przeglądu, 2026-10-21. Rdzeń zastępuje port microReticulum pod warstwą `rnsnode` (`src/rns_node.h`) stacji. Port zostaje w repozytorium jako łaty i przypięty commit: służy stanowisku do czasu przejścia i jest drugą implementacją w próbach różnicowych.

## Dlaczego

Przegląd portu z 2026-10-21 (dwa przejścia, fuzzing z sanitizerami) znalazł błędy, które pozwalają jednym pakietem od węzła z kluczem sieci (IFAC) wyłączyć stację, uszkodzenie pamięci przy zwykłym ruchu, czyszczenie tablic po 49,7 dniach licznika i odczyty magazynu bez sprawdzenia klucza i CRC. Klucz IFAC jest wspólny dla sieci, więc jedna przejęta stacja go zdradza ([odbiór](../docs/spec/odbior.md), wiersz „Wrogi węzeł”); stos musi sam znosić wrogi ruch.

Do tego:

- autor portu nie odpowiada od 2026-08-02 i nie łączy zmian od 2026-07-20 (w tym zgłoszeń WICI #94–#96), a twórca Reticulum zrezygnował z publicznego wsparcia (`MIRROR.md` w repozytorium Reticulum), więc poprawki i zgodność i tak utrzymuje WICI;
- WICI używa około jednej trzeciej portu (około 6 tys. z 19 tys. wierszy kodu), a łącza i zasoby portu są osiągalne z eteru;
- indeks magazynów portu zajmuje około 233 B RAM na cel zamiast 16 B ze [specyfikacji](../docs/spec/oprogramowanie.md#pojemności-stosu); na nRF52840 zostaje 3,5–12,5% RAM wobec wymaganych 30% ([pamięć RAM](README.md#pamięć-ram)), a README nazywa poprawkę głęboką przebudową portu;
- LXMF na stacji i tak trzeba napisać: port go nie ma.

Rozważone i odrzucone: utrzymywanie utwardzonego portu (ten sam koszt LXMF, brak rozwiązania RAM, nieznana reszta błędów w kodzie, którego WICI nie potrzebuje), Meshtastic (kanał bez uwierzytelnienia nadawcy i treści, potwierdzenia bez uwierzytelnienia w wersji stabilnej, brak radia FSK dla P1, nie jest biblioteką, brak zgodności z D19), MeshCore (MAC 2 B, AES-ECB, brak zgodności z D19). Inne implementacje Reticulum nie mają dojrzałej wersji na MCU z LXMF.

## Zakres protokołu

Wersje referencyjne bez zmian: Reticulum `e40191b` i LXMF `c3ff2d6` ([oprogramowanie](../docs/spec/oprogramowanie.md#podział-oprogramowania)). Format na łączu jest ten sam od Reticulum 1.0. Rdzeń implementuje podzbiór, którego WICI używa; zachowanie w tym podzbiorze jest takie jak w implementacji referencyjnej, a każde odstępstwo jest wpisane w tabeli różnic.

| W rdzeniu | Poza rdzeniem |
|---|---|
| tożsamość: X25519 + Ed25519, skrót, podpis i weryfikacja (z odrzuceniem S ≥ L), szyfrowanie do tożsamości (token AES-256-CBC + HMAC-SHA256, efemeryczny X25519, HKDF) | łącza (Link), zasoby (Resource), kanały i bufory |
| pakiet: HEADER_1 i HEADER_2, flagi, kontekst, skrót pakietu, IFAC (już w `p1iface`) | ratchety przy wysyłaniu (D01; odczyt pola w ogłoszeniu tak) |
| cele SINGLE IN i OUT (`wici.sa1`), PLAIN `rnstransport.path.request` | propagacja LXMF, znaczki pracy, DIRECT |
| ogłoszenia: tworzenie, weryfikacja, retransmisja z PATHFINDER_R i lokalnymi powtórkami, odpowiedzi na zapytania o trasę | tunele, zdalne zarządzanie, instancja współdzielona, odkrywanie interfejsów (1.1), czarne listy |
| transport: przekazywanie HEADER_2, tablica tras, zapytania o trasę ze znacznikami, lista skrótów pakietów (8 B, `pkthash.h`), tablica odwrotna dla dowodów | przekazywanie ruchu łączy innych węzłów (pakiety łączy odpadają z licznikiem) |
| dowody jawne z decyzją aplikacji (PROVE_APP) i potwierdzenia wysłanych pakietów | |
| LXMF: jedna wiadomość w jednym pakiecie okazjonalnym, podpis nadawcy, pola WICI, dowód po COMMIT ([dowód po COMMIT](../docs/spec/oprogramowanie.md#dowód-dostarczenia-po-commit)) | |
| interfejs USB węzła stanowiska: ogłoszenia, zapytania o trasę i ruch do celów komputera ([radio](../docs/spec/radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)) | |

Pakiety łączy i zasobów nie występują w sieci WICI, bo stacje i komputer stanowiska używają tylko dostarczenia okazjonalnego. Wiersze specyfikacji, które jeszcze mówią o łączach i zasobach (`odbior.md`, T3: udział łączy i zasobów; `radio.md`: zestawianie łącza), trzeba z nią uzgodnić.

## Wymagania konstrukcyjne

- **Pamięć bez sterty po starcie.** Wszystkie tablice mają stały rozmiar i powstają przy starcie; przetwarzanie pakietu nie przydziela pamięci. Brak wycieku i brak wyczerpania puli wynikają z konstrukcji, a nie z pomiaru.
- **Budżet RAM.** Na nRF52840 (237 568 B RAM aplikacji, próg 30% = 78 643 B wolne) obraz bez stosu zajmuje dziś około 60 372 B statycznie (100 908 B bez listy skrótów, kopii systemu plików FRAM i obiektów magazynów), 24 784 B stosów zadań i 2 048 B MSP ([pamięć RAM](README.md#pamięć-ram)). Na rdzeń z LXMF zostaje więc najwyżej 71 721 B. Cel: **≤ 60 KB statycznie**, w tym lista skrótów 32 768 B, kopia przydziału systemu plików FRAM 6 296 B, indeks tras i tożsamości 256 × 16 B, bufory pakietów, tablica retransmisji ogłoszeń 16 wpisów, tablica odwrotna i LXMF dla 2 własnych wiadomości. Około 12 KB zapasu na pomyłki szacunku.
- **Pełne wpisy w FRAM** w gniazdach o stałym rozmiarze z CRC i kluczem w rekordzie (bez magazynu typu Bitcask): odczyt sprawdza klucz i CRC, zapis jest dwufazowy jak rekordy `journal.h`, uszkodzone gniazdo jest pomijane i zwalniane. Wpisy odbiorcy i celów komputera są przypięte.
- **Jeden zegar.** Rdzeń bierze czas monotoniczny w ms od `rnsnode` (licznik pracy z dziennika FRAM, [czas](../docs/spec/oprogramowanie.md#czas)); nie czyta zegara systemowego ani `millis()`. Czas w ogłoszeniach pochodzi z tego licznika.
- **Wejście sprawdzane przed kryptografią.** Jeden parser z jawną długością minimalną dla każdego typu i kontekstu pakietu; pakiet poza wzorcem odpada z licznikiem przed weryfikacją podpisu czy deszyfrowaniem. Limity pracy na pakiet i na sekundę (weryfikacje podpisu, zapytania o trasę na interfejs jak w Reticulum 1.2).
- **Wszystkie tablice ograniczone** (trasy, tożsamości, retransmisje, tablica odwrotna, oczekujące zapytania o trasę, potwierdzenia), z zasadą wypierania opisaną przy każdej.
- **Kryptografia** z przypiętej biblioteki Crypto (Curve25519, Ed25519, AES-256, SHA-256), HKDF i HMAC w rdzeniu, porównania w stałym czasie, klucze X25519 przycinane przy wczytaniu, kasowanie kluczy w RAM przy `halt()`.
- **C++17 bez wyjątków i RTTI**, wynik jako kod błędu. Przestrzeń nazw inna niż `RNS`, żeby rdzeń i port mogły być w jednym programie prób.

## Kryteria odbioru

Rdzeń zastępuje port w obrazach dopiero, gdy na rdzeniu przechodzą:

1. Wektory z Reticulum i LXMF w Pythonie na przypiętych commitach: skrót pakietu, token, ogłoszenie, IFAC, dowód, wiadomość LXMF (generowane skryptem, zapisane w testach).
2. Próby różnicowe: ten sam ruch (także z mutacjami) do rdzenia i do Reticulum w Pythonie daje tę samą decyzję (przyjęty, przekazany, odrzucony) i te same pakiety wychodzące w podzbiorze z tabeli zakresu.
3. `tests/test_rns_stack.py` (zgodność z Reticulum w Pythonie przez emulowane P1 i przez USB węzła stanowiska), rozszerzone o LXMF w obie strony.
4. `tests/test_rns_hostile.py` bez żadnej znanej usterki, z kampanią fuzzingu co najmniej 1 h przy każdej zmianie rdzenia, oraz celowe uszkodzenia rekordów FRAM.
5. Praca 60 dni na zegarze symulowanym z wrogim ruchem z wiersza „Wrogi węzeł”: wpisy odbiorcy zachowane, RAM bez zmian, FRAM w granicach ±5%.
6. Pomiar RAM na nRF52840 (`bench-a`) i ESP32-S3 (`l0`) z LXMF: zapas ≥ 30%.

## Etapy

| Etap | Treść | Wyjście |
|---|---|---|
| R0 | wektory z Pythona, szkielet rdzenia, środowisko `host` z wyborem stosu (port albo rdzeń) | wektory przechodzą dla tożsamości, pakietu i tokenu |
| R1 | ogłoszenia, cele, przyjmowanie i dowody pakietów do stacji | `rns_interop.py` w części bez przekazywania przechodzi na rdzeniu |
| R2 | transport: przekazywanie, tablica tras w FRAM, zapytania o trasę, tablica odwrotna | próby różnicowe dla transportu; `test_rns_hostile.py` bez awarii |
| R3 | LXMF jednym pakietem z dowodem po COMMIT | wymiana LXMF z komputerem stanowiska w obie strony |
| R4 | interfejs USB węzła stanowiska, przypięte cele komputera | `rns_osp_node.py` przechodzi na rdzeniu |
| R5 | odporność: limity, 60 dni, uszkodzenia FRAM, pomiar RAM na płytkach | kryteria odbioru 1–6 |
| R6 | przełączenie obrazów na rdzeń, port tylko w próbach różnicowych | obrazy bez portu |

Szacunek: rdzeń 5–7 tys. wierszy C++ i testy, 2–4 miesiące jednej osoby; liczba do weryfikacji po R1.

## Licencja i autorstwo

Rdzeń powstaje przy znajomości kodu implementacji referencyjnej, więc traktuje się go ostrożnie jak utwór zależny od Reticulum, tak jak port ([F26](../docs/review.md#f26-licencja-portu-microreticulum)): obrazy dołączają tekst licencji Reticulum z notą autora. Kod rdzenia w repozytorium ma tę samą uwagę w nagłówkach. Każda funkcja rdzenia wskazuje w komentarzu funkcję implementacji referencyjnej, której zachowanie odtwarza; za każdą zmianę odpowiada osoba, która ją przegląda i umie ją obronić. Warunek licencji Reticulum o zbiorach do trenowania AI a pisanie kodu z pomocą modelu: do oceny prawnej przed R6.

## Do rozstrzygnięcia

- Uzgodnienie koncepcji przed specyfikacją: zasada „stos i biblioteki zamiast własnych odpowiedników” ([koncepcja 03](../docs/concept/03-dostepne-rozwiazania.html)), D14 i F10 w [przeglądzie](../docs/review.md) oraz wiersze o łączach i zasobach w `odbior.md` i `radio.md`.
- Ratchety (D01): bez nich rdzeń jest mniejszy; z nimi klucze w FRAM i dodatkowe próby.
- Czy port na stanowisku dostaje do czasu R6 trzy poprawki awarii (token 48 B, krótkie ogłoszenie, `_announce_table` w `Transport::jobs`), żeby `test_rns_hostile.py` sprawdzał dalsze scenariusze także na porcie.

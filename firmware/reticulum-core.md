# Własny rdzeń Reticulum stacji: zakres

Stan: przyjęty 2026-10-22 ([koncepcja, rozdział 03](../docs/concept/03-dostepne-rozwiazania.html#czego-nie-budowac-drugi-raz)). Rdzeń zastępuje port microReticulum pod warstwą `rnsnode` (`src/rns_node.h`) stacji. Port zostaje w repozytorium jako łaty i przypięty commit: służy stanowisku do czasu przejścia i jest drugą implementacją w próbach różnicowych.

## Dlaczego

Przegląd portu z 2026-10-21 (dwa przejścia, fuzzing z sanitizerami) pokazał, że port jest młodym projektem, jeszcze niedojrzałym do zastosowań krytycznych. Stacja WICI musi sama znosić wrogi ruch od węzła z kluczem sieci (IFAC): klucz jest wspólny dla sieci, więc jedna przejęta stacja go zdradza ([odbiór](../docs/spec/odbior.md), wiersz „Wrogi węzeł”). Scenariusze tej próby są w `tests/test_rns_hostile.py`.

Do tego:

- WICI używa około jednej trzeciej portu (około 6 tys. z 19 tys. wierszy kodu), a pozostała część i tak jest osiągalna z eteru;
- indeks magazynów portu zajmuje około 233 B RAM na cel zamiast 16 B ze [specyfikacji](../docs/spec/oprogramowanie.md#pojemności-stosu); na nRF52840 zostaje 3,5–12,5% RAM wobec wymaganych 30% ([pamięć RAM](README.md#pamięć-ram));
- LXMF na stacji i tak trzeba napisać: port go nie ma;
- poprawki i zgodność z przypiętymi wersjami Reticulum i LXMF utrzymuje WICI niezależnie od wyboru.

Rozważone i odrzucone: utrzymywanie utwardzonego portu (ten sam koszt LXMF, brak rozwiązania RAM, utrzymanie dużej części kodu, której WICI nie potrzebuje), Meshtastic (kanał bez uwierzytelnienia nadawcy i treści, potwierdzenia bez uwierzytelnienia w wersji stabilnej, brak radia FSK dla P1, nie jest biblioteką, brak zgodności z D19), MeshCore (MAC 2 B, AES-ECB, brak zgodności z D19). Inne implementacje Reticulum nie mają dojrzałej wersji na MCU z LXMF.

## Zakres protokołu

Wersje referencyjne bez zmian: Reticulum `e40191b` i LXMF `c3ff2d6` ([oprogramowanie](../docs/spec/oprogramowanie.md#podział-oprogramowania)). Format na łączu jest ten sam od Reticulum 1.0. Rdzeń implementuje podzbiór, którego WICI używa; zachowanie w tym podzbiorze jest takie jak w implementacji referencyjnej, a każde odstępstwo jest wpisane w tabeli różnic.

| W rdzeniu | Poza rdzeniem |
|---|---|
| tożsamość: X25519 + Ed25519, skrót, podpis i weryfikacja (z odrzuceniem S ≥ L), szyfrowanie do tożsamości (token AES-256-CBC + HMAC-SHA256, efemeryczny X25519, HKDF) | łącza (Link), zasoby (Resource), kanały i bufory |
| pakiet: HEADER_1 i HEADER_2, flagi, kontekst, skrót pakietu, IFAC (już w `p1iface`) | własne ratchety przy odbiorze (rotacja i klucze w FRAM; D01) |
| cele SINGLE IN i OUT (`wici.sa1`), PLAIN `rnstransport.path.request` | propagacja LXMF, znaczki pracy, DIRECT |
| ogłoszenia: tworzenie, weryfikacja, retransmisja z PATHFINDER_R i lokalnymi powtórkami, odpowiedzi na zapytania o trasę | tunele, zdalne zarządzanie, instancja współdzielona, odkrywanie interfejsów (1.1), czarne listy |
| transport: przekazywanie HEADER_2, tablica tras, zapytania o trasę ze znacznikami, lista skrótów pakietów (8 B, `pkthash.h`), tablica odwrotna dla dowodów | przekazywanie ruchu łączy innych węzłów (pakiety łączy odpadają z licznikiem) |
| dowody jawne z decyzją aplikacji (PROVE_APP) i potwierdzenia wysłanych pakietów | |
| LXMF: jedna wiadomość w jednym pakiecie okazjonalnym, podpis nadawcy, pola WICI, dowód po COMMIT ([dowód po COMMIT](../docs/spec/oprogramowanie.md#dowód-dostarczenia-po-commit)) | |
| interfejs USB węzła stanowiska: ogłoszenia, zapytania o trasę i ruch do celów komputera ([radio](../docs/spec/radio.md#interfejs-reticulum-przez-usb-węzeł-stanowiska)) | |

Pakiety łączy i zasobów nie występują w sieci WICI, bo stacje i komputer stanowiska używają tylko dostarczenia okazjonalnego. Wiersze specyfikacji, które jeszcze mówią o łączach i zasobach (`odbior.md`, T3: udział łączy i zasobów; `radio.md`: zestawianie łącza), trzeba z nią uzgodnić.

### Tabela różnic

Odstępstwa rdzenia od Reticulum w Pythonie w podzbiorze z tabeli zakresu. Każde dotyczy wejścia, którego zgodny nadawca nie wyśle, albo tylko własnego wyjścia stacji.

| Miejsce | Python | Rdzeń | Dlaczego |
|---|---|---|---|
| ogłoszenie przyjmowane (`validateAnnounce`) | sprawdza dane każdej długości | odrzuca dane dłuższe niż 481 B (MTU bez nagłówka HEADER_1) | stały bufor danych podpisanych; takiego ogłoszenia nie złoży `Packet.pack`, więc zgodny nadawca go nie wyśle |
| ogłoszenie własne (`buildAnnounce`) | składa dane do 481 B | składa do 465 B | węzeł transportowy w Pythonie przekazuje ogłoszenie jako nowy pakiet HEADER_2 przez `Packet.pack`, więc dane 466–481 B nie przechodzą dalej niż o jeden skok |
| pakiet własny (`pack`) | składa pakiet z pustymi danymi, z liczbą skoków ≥ 128 i z kontekstem LRPROOF dla dowolnego celu | odmawia | odbiorca takiego pakietu nie przyjmie (`unpack`, `send`); łącza są poza rdzeniem |
| nowy klucz tożsamości (`rns_node_core.cpp`) | zapisuje losowe bajty klucza X25519 | zapisuje klucz już przycięty (RFC 7748) | ten sam klucz dla Pythona i rdzenia; port używa zapisanego klucza bez przycięcia |

## Wymagania konstrukcyjne

- **Pamięć bez sterty po starcie.** Wszystkie tablice mają stały rozmiar i powstają przy starcie; przetwarzanie pakietu nie przydziela pamięci. Brak wycieku i brak wyczerpania puli wynikają z konstrukcji, a nie z pomiaru.
- **Budżet RAM.** Na nRF52840 (237 568 B RAM aplikacji, próg 30% = 78 643 B wolne) obraz bez stosu zajmuje dziś około 60 372 B statycznie (100 908 B bez listy skrótów, kopii systemu plików FRAM i obiektów magazynów), 24 784 B stosów zadań i 2 048 B MSP ([pamięć RAM](README.md#pamięć-ram)). Z tego zostaje 71 721 B, ale warstwa `rnsnode`, która zostaje przy rdzeniu, ma jeszcze kolejkę P1 z listą ogłoszeń (około 3 KB) i bufor KISS 5 112 B, więc na rdzeń z LXMF zostaje około 63 600 B. Cel: **≤ 56 KB statycznie**, w tym lista skrótów 32 768 B, kopia przydziału systemu plików FRAM 6 296 B, indeks tras i tożsamości 256 × 16 B, bufory pakietów, tablica retransmisji ogłoszeń 16 wpisów, tablica odwrotna i LXMF dla 2 własnych wiadomości. Około 7 KB zapasu na pomyłki szacunku; przekroczenie celu oznacza mniejszą listę skrótów albo indeks, nie mniejszy próg 30%.
- **Pełne wpisy w FRAM** w gniazdach o stałym rozmiarze z CRC i kluczem w rekordzie (bez magazynu typu Bitcask): odczyt sprawdza klucz i CRC, zapis jest dwufazowy jak rekordy `journal.h`, uszkodzone gniazdo jest pomijane i zwalniane. Wpisy odbiorcy i celów komputera są przypięte.
- **Jeden zegar.** Rdzeń bierze czas monotoniczny w ms od `rnsnode` (licznik pracy z dziennika FRAM, [czas](../docs/spec/oprogramowanie.md#czas)); nie czyta zegara systemowego ani `millis()`. Dzisiejszy port tego nie spełnia: przerwa między kompaktowaniami microStore biegnie zegarem `millis()`, którego sieć prób nie symuluje. Czas w ogłoszeniach pochodzi z tego licznika.
- **Wejście sprawdzane przed kryptografią.** Jeden parser z jawną długością minimalną dla każdego typu i kontekstu pakietu; pakiet poza wzorcem odpada z licznikiem przed weryfikacją podpisu czy deszyfrowaniem. Limity pracy na pakiet i na sekundę (weryfikacje podpisu, zapytania o trasę na interfejs jak w Reticulum 1.2). Token z kluczem efemerycznym niskiego rzędu (wspólny sekret zerowy) odrzuca rdzeń, jak Python; licznik takich odrzuceń dodaje `rnsnode` przy podłączeniu rdzenia.
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
| R1 | ogłoszenia (z polem ratchetu), cele, szyfrowanie do klucza ratchetu z ogłoszenia, przyjmowanie i dowody pakietów do stacji | `rns_interop.py` w części bez przekazywania przechodzi na rdzeniu |
| R2 | transport: przekazywanie, tablica tras w FRAM, zapytania o trasę, tablica odwrotna | próby różnicowe dla transportu; `test_rns_hostile.py` bez awarii |
| R3 | LXMF jednym pakietem z dowodem po COMMIT | wymiana LXMF z komputerem stanowiska w obie strony |
| R4 | interfejs USB węzła stanowiska, przypięte cele komputera | `rns_osp_node.py` przechodzi na rdzeniu |
| R5 | odporność: limity, 60 dni, uszkodzenia FRAM, pomiar RAM na płytkach | kryteria odbioru 1–6 |
| R6 | przełączenie obrazów na rdzeń, port tylko w próbach różnicowych | obrazy bez portu |

Szacunek: rdzeń 5–7 tys. wierszy C++ i testy, 2–4 miesiące jednej osoby; liczba do weryfikacji po R1.

## Licencja i autorstwo

Rdzeń powstaje przy znajomości kodu implementacji referencyjnej, więc jest utworem zależnym od Reticulum, a nie niezależną implementacją protokołu ([podręcznik Reticulum, „Brandolini's Reference”](https://reticulum.network/manual/brandolinis.html), stan 2026-10-22). Zasady:

- **Licencja.** Kod rdzenia jest w `firmware/lib/reticulum_core/` na [licencji Reticulum](../LICENSES/LicenseRef-Reticulum.txt) z notą „Copyright (c) 2016-2026 Mark Qvist” i notą zmian WICI ([LICENSE.md](../LICENSE.md), `REUSE.toml`), nie na MIT. Obrazy z rdzeniem dołączają tekst tej licencji, tak jak obrazy z portem ([F26](../docs/review.md#f26-licencja-portu-microreticulum)). Warunek o systemach szkodzących ludziom nie koliduje z łącznością alarmową straży pożarnej, gmin i zarządzania kryzysowego; włączenie obrazu do systemu służb, które mogą użyć siły (wojsko, WOT, policja), wymaga wcześniej oceny prawnej tego warunku.
- **Autor.** Autorem rdzenia jest Tomek Mierzwa ([@tmierzwa](https://github.com/tmierzwa)): decyduje, co powstaje, przegląda każdą zmianę przed scaleniem i odpowiada za każdy wiersz. Kod powstaje z pomocą asystenta AI (Claude), co commity zapisują wierszem `Co-Authored-By`. Zmiany są małe (jeden PR na krok etapu), żeby przegląd był rzeczywisty; decyzje projektowe i odrzucone warianty są zapisane w PR.
- **Pochodzenie.** Każda funkcja rdzenia wskazuje w komentarzu funkcję implementacji referencyjnej (plik i funkcja na przypiętym commicie), której zachowanie odtwarza. Rdzeń nie przedstawia się jako implementacja „od zera”.
- **Warunek o AI.** Kodu Reticulum i LXMF nie używa się do trenowania modeli: konto, z którego pracuje asystent, ma wyłączone użycie rozmów i sesji do trenowania (sprawdzone 2026-10-22, „Help improve our AI models”). Na koncie konsumenckim Anthropic dwa wyjątki zostają mimo wyłączenia: rozmowa z oceną odpowiedzi (kciuk w górę lub w dół) i rozmowa oznaczona do przeglądu bezpieczeństwa mogą służyć do trenowania, więc w sesjach z kodem Reticulum lub LXMF nie ocenia się odpowiedzi. Podręcznik Reticulum dopuszcza pomoc narzędzi uczenia maszynowego przy pisaniu kodu; warunek zakazuje wprowadzania kodu do zbiorów treningowych. Uruchamianie Reticulum w Pythonie do wektorów i prób zgodności jest zwykłym użyciem programu. Publikacja kodu rdzenia w publicznym repozytorium jest dozwolona licencją; pobranie go do zbioru treningowego przez kogoś trzeciego jest naruszeniem tej osoby.
- **Ocena licencji (2026-10-22).** Ocena autora projektu na podstawie źródeł pierwotnych, nie opinia prawna; nie blokuje R1.
  - *Autorstwo.* Utworem jest przejaw działalności twórczej o indywidualnym charakterze (art. 1 ust. 1 ustawy o prawie autorskim, Dz.U. 2025 poz. 24), a twórcą według doktryny może być tylko człowiek; oryginalność wymaga swobodnych i twórczych wyborów; postać podyktowana regułami technicznymi bez swobody twórczej nie jest utworem ([TSUE C-833/18 Brompton](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62018CJ0833), pkt 23–24), a funkcjonalność i format danych programu nie są chronione ([TSUE C-406/10 SAS Institute](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62010CJ0406), sentencja pkt 1). Tomek Mierzwa jest autorem tego, co wyraża jego wybory (zakres, konstrukcja, decyzje z przeglądów i zmiany po nich); kod asystenta bez takich wyborów i części podyktowane protokołem prawdopodobnie nie są niczyim utworem. Licencja rdzenia opiera się na prawach Marka Qvista do implementacji referencyjnej i na twórczym wkładzie autora; tam, gdzie prawa nie ma, licencja niczego nie przenosi i nikomu nie szkodzi. Zapis decyzji w PR i przegląd każdej zmiany są zarazem dowodem wkładu człowieka.
  - *Warunek o AI.* Jak w punkcie „Warunek o AI” wyżej.
  - *Jeden obraz.* MIT nie ogranicza łączenia; Apache-2.0 (pkt 4) pozwala nadać całości dodatkowe warunki, jeśli części na Apache-2.0 zachowują swoje; licencja Reticulum łączenia nie zabrania. Obraz z rdzeniem dołącza teksty i noty wszystkich licencji i jako całość nie jest oprogramowaniem otwartym w rozumieniu OSI, jak obraz z portem. Rdzenie Arduino w obrazach są na LGPL-2.1 (arduino-esp32) i LGPL-2.1-or-later (Adafruit nRF52): przy łączeniu statycznym odbiorca musi móc ponownie zlinkować program ze zmienioną biblioteką (źródła WICI i rdzenia są publiczne), a warunki całości muszą pozwalać na zmiany do własnego użytku i inżynierię wsteczną do usuwania błędów (licencja Reticulum na to pozwala), więc uznajemy je za zgodne. Licencje SDK producentów (Nordic, Espressif) zostają do sprawdzenia przed D14 ([LICENSE.md](../LICENSE.md)).

## Do rozstrzygnięcia

- Ratchety (D01): rdzeń szyfruje do klucza ratchetu z ogłoszenia celu od R1 (decyzja 2026-10-22: poufność wsteczna dla wiadomości do telefonów i do komputera stanowiska z LXMF, które ogłaszają ratchety domyślnie; `LXMRouter.register_delivery_identity`). Otwarte: własne ratchety stacji przy odbiorze (rotacja, klucze w FRAM, dodatkowe próby).

Rozstrzygnięte 2026-10-22: koncepcja uzgodniona z rdzeniem ([rozdział 03](../docs/concept/03-dostepne-rozwiazania.html#czego-nie-budowac-drugi-raz), F117 w [przeglądzie](../docs/review.md)); port na stanowisku i w próbach sprzętu pilotażu dostaje poprawki WICI, żeby `test_rns_hostile.py` sprawdzał na nim dalsze scenariusze.

# WICI-Link: protokół łącza sieci stacji

**Stan: implementacja przed próbą D21, 2026-11-01.** Nośnik radiowy dla [szwu transportu](transport.md). Obowiązuje dopiero po rozstrzygnięciu D21 ([warunek przyjęcia](transport.md#warunek-przyjęcia)).

## Założenia

WICI-Link jest protokołem łącza i tras dla zamkniętej sieci jednej gminy (albo jej części), w której:

- wszystkie stacje i tożsamości odbiorcy są znane z planu sieci i kart z przygotowania, a klucze nigdy nie przychodzą przez radio;
- ruch płynie tylko między stacjami schronień a stanowiskiem odbiorczym, w obie strony; schronienia nie piszą do siebie nawzajem;
- stacje stoją w stałych miejscach, a trasy można zmierzyć przed kryzysem (krok 5);
- każda włączona stacja przekazuje ruch innych (W23).

Protokół używa profilu LoRa pilotażu bez zmian ([radio](radio.md#profil-lora-pilotażu)) i wszystkich reguł [dostępu do kanału](radio.md#dostęp-do-kanału): długu ciszy 12t zapisanego w FRAM, wolnego kanału przez 50 ms i CAD przed nadaniem, limitu 10% i klas K0–K2. Koperta o długości do 172 B mieści się w jednej ramce LoRa; dłuższa wiadomość SA1 jest dzielona na dwie szyfrowane części. Protokół nie używa ramek RNode.

## Ramka

```
 0       1        3        5        7       8        10      11          n-8      n
 +-------+--------+--------+--------+-------+--------+-------+-----------+--------+
 | ver/t | net_id | l_src  | l_dst  | hops  | seq    | opts  | ładunek i podpis DATA | MAC(8) |
 +-------+--------+--------+--------+-------+--------+-------+-----------+--------+
 ver/t: bity 7–6 wersja (2), bity 5–3 typ, bity 2–0 flagi (bit 0 ACKREQ, bit 1 DOWN, bit 2 zarezerwowany)
 net_id: numer sieci z przygotowania (u16)
 l_src, l_dst: numery stacji nadającej i następnego skoku (0xFFFF = wszyscy sąsiedzi)
 hops: bity 7–4 liczba wykonanych skoków, bity 3–0 limit skoków (TTL)
 seq: numer ramki nadawcy łącza (u16, rośnie o 1, zawija się)
 opts: 0 w wersji 2; każda inna wartość jest odrzucana (miejsce na jawnie wersjonowane rozszerzenie)
 MAC: HMAC-SHA-256(K_link, bajty 0..n-9) obcięty do 8 B
```

Nagłówek ma 11 B, MAC 8 B. DATA niesie także 64 B podpisu Ed25519 po zaszyfrowanej kopercie. Największa ramka LoRa ma 255 B, więc `max_payload` nośnika DATA wynosi 172 B. HACK nie ma podpisu. BEACON niesie podpis epoki korzenia (64 B) i podpis pól trasy nadawcy (64 B); weryfikacja obu odbywa się poza ścieżką HACK.

**Klucz sieci.** `K_link = HKDF-SHA-256(ikm = klucz sieci z przygotowania, salt = net_id, info = "WICI link v2", L = 32)`. Stacja odrzuca ramkę bez poprawnego MAC przed dalszym przetwarzaniem. MAC 8 B daje prawdopodobieństwo przyjęcia podrobionej ramki 2⁻⁶⁴ na próbę. Klucz sieci jest wspólny, więc autentyczność treści zapewnia koperta, a uprawnienie do K1 podpis pochodzenia ([zagrożenia](#zagrożenia)).

**Słowo synchronizacji.** Profil pilotażu używa 0x12. Do rozważenia przed T4: własne słowo synchronizacji sieci WICI, żeby radio w ogóle nie zgłaszało ramek Meshtastic, MeshCore i LoRaWAN na tym samym kanale. Nie zmniejsza to kolizji, ale ogranicza pracę procesora i liczbę ramek do odrzucenia.

### Typy ramek

| Typ | Kod | Ładunek | Rozmiar ramki | Czas TX (SF7) |
|---|---|---|---|---|
| DATA | 0 | koperta WICI i podpis Ed25519 | 83 B + koperta | 195 B (część typowego zgłoszenia): model 329 ms |
| HACK | 1 | brak (potwierdza `seq` z `l_src` ramki DATA) | 19 B | 71 ms (z 3 ms narastania) |
| BEACON | 2 | `root`, `rank`, `epoch`, `parent`, flagi (9 B), podpis epoki (64 B), podpis nadawcy (64 B) | 156 B | według `lora::frameAirMs(156)` |
| 3–7 | | zarezerwowane | | |

## Trasy

### Drzewo do odbiorcy

Sieć tworzy drzewo zakorzenione w stacji stanowiska odbiorczego (`root`). Każda stacja ma **rodzica**, czyli następny skok w stronę odbiorcy.

1. **Rodzic z planu.** Przy przygotowaniu stacja dostaje w dokumencie konfiguracji rodzica z planu sieci i opcjonalnie rodzica zapasowego, wybranych na podstawie pomiaru tras (kroki 3 i 5). To podstawowy tryb pracy w pilotażu.
2. **Rodzic wybrany samodzielnie.** Gdy rodzic z planu nie odpowiada (3 nieudane próby na kolejnych ramkach DATA), stacja przechodzi na rodzica zapasowego, a gdy go nie ma, wybiera sąsiada z najmniejszym kosztem z ostatnich ramek BEACON. Koszt = `rank` sąsiada + koszt łącza. Koszt łącza liczy się z odsetka potwierdzonych prób (ETX, w jednostkach 1/16) i z SNR; nowy rodzic musi być lepszy o co najmniej 1,5 jednostki ETX (histereza). Do rodzica z planu stacja wraca, gdy znów potwierdza ramki.
3. **Ranga.** `rank` odbiorcy to 0. Stacja ogłasza `rank` = `rank` rodzica + koszt łącza do niego. Dynamiczny rodzic musi mieć rangę niższą od najniższej własnej rangi w tej epoce i nie wskazywać stacji jako rodzica. Skonfigurowany rodzic z planu lub zapasowy może mieć wyższą rangę po awarii, ale jego BEACON wymaga osobnego podpisu i nie może wskazywać tej stacji jako rodzica. Po nowym poprawnym BEACON od planowanego sąsiada stacja może go ponownie wybrać. Przy zmianie rodzica przelicza własną rangę.
4. **Limit skoków.** Pole `hops` pozwala na najwyżej 15 skoków. Domyślny limit sieci to 7 i ustawia się go w planie sieci. Reguła planowania pilotażu z [rozdziału 02](../concept/02-scenariusze-i-organizacja.html) (najwyżej 2 przeskoki do stanowiska, dopóki T5 nie sprawdzi dłuższych łańcuchów) dotyczy planu, nie protokołu.

### BEACON

Każda stacja z ustaloną rangą nadaje BEACON co 30 min ±20%, po zmianie rodzica lub rangi (najwyżej raz na 60 s) oraz trzy razy w pierwszych 5 min po starcie, z losowym opóźnieniem. Przy 50 stacjach to około 8 s czasu nadawania na godzinę w całym obszarze kolizji. BEACON-y wliczają się do limitu ogłoszeń 2% czasu zegarowego i do wspólnej puli z K2 ([dostęp do kanału](radio.md#dostęp-do-kanału)). W ciszy radiowej stacja nie nadaje BEACON-ów.

`epoch` nadaje korzeń i zwiększa go przy każdym starcie. Korzeń podpisuje (`net_id`, `root`, `epoch`); przekaźniki przenoszą ten podpis bez zmian. Każdy nadawca podpisuje ponadto swoje pola BEACON i token epoki. Stacja wymaga kluczy Ed25519 korzenia oraz sąsiadów w `priority_keys` i przyjmuje rangę tylko po weryfikacji obu podpisów. Po zmianie epoki przelicza rangę od nowa.

### Ruch w górę i w dół

- **W górę** (do odbiorcy): stacja wysyła DATA do rodzica. Każdy przekaźnik przekazuje ją swojemu rodzicowi.
- **W dół** (od odbiorcy): każdy przekaźnik zapamiętuje, przez którego sąsiada przyszła ostatnia ramka DATA w górę od danej stacji (numer `src` z koperty, sąsiad z `l_src`). Ramkę DATA z flagą DOWN do tej stacji przekazuje temu sąsiadowi. Tablica ma do 256 wpisów po 4 B, jest zapisywana w FRAM i odtwarzana po restarcie, tak jak dziś tablica tras. Odbiorca zna drogę do każdej stacji po jej pierwszym TEST startowym.
- **Brak wpisu:** przekaźnik bez wpisu dla celu w dół rozsyła ramkę do wszystkich sąsiadów (`l_dst` = 0xFFFF) z limitem skoków. Każdy węzeł przekazuje daną kopertę najwyżej raz w oknie 120 s, rozpoznając ją po (`src`, `dst`, `ctr`, `kind`) koperty, a nie po `l_src` i `seq`, które zmieniają się na każdym skoku. Powtórne kopie odrzuca i liczy. Rozsyłana DATA ma wyłączony ACKREQ: wielu sąsiadów nie odpowiada HACK jednocześnie, a ponowienie całej intencji pozostaje po stronie SA1. Każde rozsyłanie podlega TTL, limitowi K2 i licznikowi diagnostycznemu; wyczerpana pula K2 odracza je do następnego okna.

### Potwierdzenie na każdym skoku

1. Jednoadresowa ramka DATA ma flagę ACKREQ. Przekaźnik odpowiada HACK z tym samym `seq`, adresowanym do `l_src`, dopiero po trwałym zapisie ramki w kolejce przekazywania w FRAM. Celem jest trwały odbiór poprawnej koperty: po jej uwierzytelnieniu zapisuje ją lub jej część w FRAM stacji albo SQLite stanowiska i dopiero wtedy odpowiada HACK. Brak miejsca lub błąd zapisu oznacza brak HACK. HACK potwierdza przejęcie odpowiedzialności za bajty na jednym skoku, nie przyjęcie SA1; dla WICI-Link `e2e_ack = false`, więc `Bearer::confirm()` nie steruje HACK.
2. HACK wychodzi najpóźniej 200 ms po końcu ramki DATA, po samym CAD, bez okna 50 ms. Może wyjść w trakcie długu ciszy stacji; jej czas nadawania z dwunastokrotnością dolicza się do długu. Udział nadawania w długim czasie pozostaje więc 1/13 (około 7,7%).
3. Nadawca czeka na HACK 600 ms. Bez HACK ponawia ramkę po swoim długu ciszy i losowym 0,5–2 s, najwyżej 3 razy na rodzica, potem próbuje rodzica zapasowego (najwyżej 3 razy). Dla własnej ramki zgłasza wtedy `Failed` do szwu; ramka przyjęta wcześniej od innego węzła pozostaje w trwałej kolejce do ponowienia po odzyskaniu trasy.
4. Stacja rozpoznaje powtórzoną kopertę także po zmianie `l_src`, `seq` i MAC. Jeśli ramka jest nadal w trwałej kolejce albo została przekazana w ostatniej godzinie, może ponowić HACK najwyżej raz na 5 s; nie przekazuje koperty drugi raz. Cel rozpoznaje powtórzenie części koperty po (`src`, `dst`, `ctr`, `kind`) i potwierdza zapisany już fragment bez podwójnego przyjęcia SA1.

Kolejka przekazywania ma najwyżej 4 ramki. Po HACK przekaźnik zachowuje ramkę do HACK z następnego skoku; po restarcie wznawia nadawanie z FRAM. Wyczerpanie prób lub brak trasy odracza ją; po 30 minutach bez doręczenia gniazdo wygasa, a nadawca musi wznowić intencję SA1. Gdy nie może przyjąć kolejnej ramki trwale, nie wysyła HACK do poprzedniego skoku. Dla rozsyłania awaryjnego bez ACKREQ przekazanie jest jednorazową próbą, a ponowienie zapewnia intencja SA1.

Moduł kolejki D21 (`firmware/src/wici_relay.cpp`) rezerwuje 0x045000–0x0459FF FRAM: cztery gniazda po dwie kopie 320 B, CRC i końcowy znacznik COMMIT. `STORED` albo `DUPLICATE` oznacza, że bajty są po zapisie i odczycie kontrolnym; pozostałe wyniki zabraniają HACK. Usunięcie zapisuje trwały rekord pusty, więc po zaniku zasilania nie wraca starsza kopia ramki. Niepewny zapis blokuje kolejne przyjęcia do ponownego odczytu FRAM. Koordynator łączy moduł z radiem; limit 200 ms wymaga pomiaru na prototypie.

Moduł tras D21 (`firmware/src/wici_route.cpp`) rezerwuje 0x046000–0x0468FF FRAM dla dwóch kopii tablicy 256 dróg w dół, z CRC, COMMIT i związaniem z siecią, numerem stacji oraz korzeniem. Niepewny zapis blokuje korzystanie z tablicy do ponownego odczytu FRAM. Beacony i koszty są miękkim stanem w RAM, resetowanym po zmianie epoki. Koszt łącza łączy SNR ramki BEACON (po jednym szesnastym za dB poniżej 0 dB, najwyżej 32/16) z przybliżeniem ETX z kolejnych wyników HACK (średnia wykładnicza sukcesu w szesnastych). Testy natywne sprawdzają zanik zapisu, odtworzenie, zgodność sieci, ścisłą rangę, koszt i zmianę rodzica. Harmonogram beaconów i połączenie z radiem są aktywne; progi kosztu wymagają pomiaru na sprzęcie D21.

Pierścień `firmware/src/wici_seen.cpp` w 0x046900–0x047DFF zachowuje 224 ostatnio przekazanych tożsamości kopert przez 3600 s według (`net_id`, identyfikator koperty, skrót pełnego ładunku). Przy starcie odczytuje i sprawdza 5376 B do RAM, aby nie wykonywać 256 odczytów FRAM przed każdym HACK. Przed zwolnieniem gniazda przekaźnik zapisuje w nim wynik przekazania; po restarcie `read()` nie wydaje ponownie ramki, której wpis już trwa. Zanik zapisu pierścienia pozostawia gniazdo zajęte, a zanik zapisu pustego gniazda pozostawia trwały wpis „przekazane”. Ponowienie tej samej koperty z innym adresem skoku, sekwencją i MAC pozostaje rozpoznaną powtórką; ponowny HACK jest ograniczony do jednego na 5 s. Inny ładunek o tej samej tożsamości koperty jest odrzucany. `wici_link::forward` sprawdza MAC wejścia, adres tego skoku i TTL, a następnie przepisuje tylko nagłówek łącza, zachowując szyfrogram; numer `seq` dostaje z trwałego licznika. Pierścień jest ograniczony: po 224 nowszych wpisach najstarsza pozycja może zostać wyparta przed 3600 s; limity czasu kanału mają utrzymać rzeczywistą liczbę poniżej tego progu, co wymaga próby przeciążeniowej.

`firmware/src/wici_destination.cpp` łączy uwierzytelnienie ramki łącza, AEAD koperty, dwa trwałe bufory części i dwa okna powtórzeń po stronie schronienia. Dla całości albo drugiej części wydaje HACK dopiero po trwałym i idempotentnym przyjęciu SA1 przez wywołującego oraz zapisie okna; dla pierwszej części po zapisie FRAM. Po restarcie kończy przerwane opróżnienie bufora, jeśli okno dowodzi przyjęcia. Test natywny obejmuje dwuczęściową kopertę z drugą częścią najpierw, restart, powtórkę, zmianę sposobu podziału pod tym samym licznikiem i ramkę z błędnym MAC. Aplikacja stanowiska nie wykonuje już wysyłki LXMF ani kopii na synchronicznej ścieżce `receive_envelope_frame`, by nie opóźniać HACK; termin 200 ms i tak wymaga pomiaru na sprzęcie. Numerowany obraz wywołuje adapter z surowego odbioru radia.

`measure::Bench` ma osobny tryb jednej surowej ramki SX1262, który wymaga zarejestrowanego odbiorcy ramki. Wywołuje go z czasem końca odbioru, RSSI i SNR przed diagnostyką USB. Zwykła DATA zachowuje okno 50 ms, CAD i trwały dług. Metoda `linkSendHack` omija oczekiwanie na dług i okno, ale wymaga wolnego CAD, sprawdza znacznik końca odbioru względem limitu 200 ms i przed TX zapisuje w dzienniku dotychczasowy pozostały dług oraz czas HACK z narastaniem i jego dwunastokrotnością. Po TX pozostawia dotychczasowy dług i nowy dług HACK, nawet gdy w kolejce czeka DATA. Gdy suma przekroczyłaby największy dług odczekiwany po utracie rekordu (10 056 ms dla LoRa), HACK nie wychodzi; dzięki temu niepewny start nadal odczekuje wystarczająco długo. Przy odmowie zapisu nie nadaje. Test hosta sprawdza surowe 255 B bez ramki RNode, pojedyncze 19 B HACK, dwa HACK podczas długu, odłożoną DATA, ciszę, spóźniony HACK, wolny zapis FRAM i wyczerpany budżet długu. Numerowany obraz włącza ten tryb; limit HACK pozostaje do pomiaru na sprzęcie.

`firmware/src/wici_radio.cpp` łączy odbiorcę i przekaźnik stacji z wyjściem `Air`: po sprawdzeniu MAC próbuje HACK tylko po trwałym przyjęciu, dopiero potem uczy tras i planuje przekazanie. Czas 600 ms liczy od zakończenia faktycznego TX; po braku HACK, odmowie radia albo nieudanym TX odczekuje losowo 0,5–2 s. Po restarcie odczytuje kolejkę i odtwarza trasy w dół. Test natywny z sanitizerem obejmuje odrębny numer odbiorcy i korzenia, odmowę HACK/DATA, ponowienie identycznej ramki, potwierdzenie i restart. Numerowany obraz łączy `Air` z `Bench`; kontrakt migracji tożsamości i licznika kopert jest zaimplementowany, a zaniki zasilania wymagają próby na docelowym sprzęcie.

`firmware/src/wici_gateway.cpp` przygotowuje korzeń do portu KISS: przekazuje do USB tylko ramki po poprawnym MAC, a HACK z laptopa przyjmuje wyłącznie dla ostatniej ramki DATA, którą port KISS przyjął do wysłania, ze zgodnym źródłem i `seq` oraz przed upływem 200 ms od końca odbioru radiowego. Odłączenie USB kasuje oczekiwanie. Moduł nie odpowiada sam za SQLite; aplikacja stanowiska musi zapisać kopertę trwale przed odesłaniem HACK. Test natywny sprawdza brak USB, błędny MAC, obcy i spóźniony HACK, odmowę radia i wyzerowanie po odłączeniu. Numerowany obraz łączy go z aktywnym portem USB i zadaniem radiowym. Echo wychodzącej ramki do laptopa następuje po faktycznym TX.

`firmware/src/wici_seq.cpp` rezerwuje numery `seq` blokami 64 w dwóch rekordach 32 B FRAM przy 0x044180. Po restarcie pomija niewykorzystaną resztę bloku; błąd lub niepewny zapis wyłącza dalsze nadawanie do ponownego odczytu FRAM. Numer na łączu jest u16 i zawija się po 65536 ramkach; potwierdzony limit czasu kanału musi zapewnić, że jedno źródło nie wykona pełnego obrotu w oknie powtórzeń 3600 s. Nadawca ponawiający tę samą ramkę na skoku zachowuje jej `seq`.

`firmware/src/wici_hop.cpp` łączy kolejkę, tablicę tras i licznik sekwencji dla ruchu tranzytowego. Wydaje HACK dopiero po trwałym przyjęciu, zachowuje tę samą ramkę i `seq` przy ponowieniu, sprawdza uwierzytelniony HACK od właściwego następnego węzła, a po restarcie kończy zapis pustego gniazda przerwany po znaczniku „przekazane”. Trasę w dół uczy poza terminem HACK tylko z ramki z poprawnym podpisem pochodzenia; klucz łącza sam nie nadaje uprawnienia do aktualizacji trasy. Bez trasy rozsyła najwyżej raz według trwałego pierścienia tożsamości kopert. Pierścień `firmware/src/wici_flood.cpp` ma 256 rekordów po 18 B, w dwóch wolnych lukach FRAM: 0x044200–0x044F7F i 0x045A00–0x045E7F. Rekord zawiera sieć, dziewięciobajtową tożsamość koperty, czas, CRC i końcowy COMMIT. Zapis i odczyt kontrolny następują przed próbą nadania, a świeży pierścień pełny blokuje kolejne rozsyłanie. Jeśli zasilanie zaniknie po znaczniku, lecz przed TX, ta konkretna koperta może nie wyjść. Numerowany nośnik stanowiska traktuje echo rozsyłania bez HACK jako nieudane doręczenie, więc następna próba SA1 używa nowego licznika koperty. Koordynator stacji włącza rozsyłanie dla numerowanej sieci. To reguła najwyżej jednej próby, a nie gwarancja dostarczenia pojedynczej rozsyłanej ramki. Test pamięciowy obejmuje restart po HACK, późną powtórkę, zmianę sąsiada, ruch w dół, rozsyłanie i zanik między znacznikiem a TX. Numerowany obraz wywołuje moduł z odbioru radia i łączy go z harmonogramem 600 ms, CAD oraz trwałym długiem.

Ponowienie na skoku ogranicza ponowienia przez cały łańcuch: przy 95% skuteczności jednego nadania i trzech próbach jeden skok przechodzi z prawdopodobieństwem 99,99%. Ponowienia intencji SA1 (10 min po doręczeniu, potem co 30–60 min) zostają bez zmian i działają nad nośnikiem.

## Klasy czasu kanału

Reguły podziału czasu z [radio](radio.md#dostęp-do-kanału) zostają, z jedną zmianą znaczenia klas, możliwą dzięki jawnym numerom stacji w kopercie:

- **K0:** własne ramki DATA stacji, HACK.
- **K1:** przekazywane ramki DATA skierowane do odbiorcy albo od odbiorcy, z poprawnym podpisem pochodzenia. Nadawca podpisuje `"WICI K1 origin v1" ‖ net_id (u16 BE) ‖ pełna zaszyfrowana koperta`. Dla ruchu w górę przekaźnik sprawdza klucz Ed25519 numeru źródła z przygotowania; dla ruchu w dół klucz aktywnego odbiorcy z karty. Podpis obejmuje kopertę, więc zmiana jawnego nadawcy lub odbiorcy unieważnia dowód. Przekaźnik zachowuje podpis przy każdym skoku i odnawia tylko MAC łącza.
- **K2:** pozostałe przekazywane ramki, w tym rozsyłanie awaryjne bez wpisu w tablicy; BEACON-y w puli ogłoszeń.

Numerowany przekaźnik odkłada przychodzącą ramkę do K2 bez weryfikacji Ed25519 w terminie HACK i zostawia dwa z czterech trwałych gniazd wolne dla dalszych przyjęć. Weryfikacja podpisu poza terminem HACK może podnieść ją do K1; dopuszczona jest najwyżej jedna oczekująca ramka K1 od jednego zweryfikowanego nadawcy. Metadane nadawcy są zapisane z CRC i znacznikiem COMMIT. K1 jest wybierane przed K2, a wybór gniazda rotuje; powtórkę już przyjętej ramki potwierdza również przy pełnej kolejce. Brak klucza albo zły podpis kwalifikuje ramkę do K2. Dziennik `wici_airtime` zapisuje przed przekazaniem do radia koszt wszystkich przekazywanych DATA oraz BEACON-ów w dwóch kopiach FRAM (0x047F80–0x047FFF). Klasę „własna”, „tranzyt”, „K2 przy czekającym K1” albo „BEACON” przekazuje koordynator stacji. Siedem dziesięciominutowych przedziałów zachowuje wszystkie nadania z ostatnich 3600 s, czasem dłużej, a koszt zaokrągla w górę do 100 ms. Ruch tranzytowy razem z BEACON-ami nie przekracza 60% czasu kanału, a BEACON-y 2% czasu nadawania w tym oknie. K1 ma pierwszeństwo w kolejce, lecz także podlega wspólnemu limitowi. Gdy K1 czeka bez dostępnej trasy, K2 może wyjść tylko do 25% *łącznego* kosztu tranzytu i BEACON-ów. Nieudane przyjęcie przez radio zostawia zarezerwowany koszt. Pełna próba „Wrogi węzeł” pozostaje do pomiaru.

Wspólny `K_link` sam nie wystarcza do zajęcia gniazda K1: podrobiony numer bez podpisu jest K2. Przejęta stacja z własnym kluczem podpisu może zająć jedno gniazdo K1 oraz dwa K2, pozostawiając co najmniej jedno gniazdo dla innego zweryfikowanego nadawcy. Próba „Wrogi węzeł” i W10 na docelowym sprzęcie pozostają warunkami odbioru D21.

## Cisza radiowa

W ciszy radiowej (W19) stacja nie nadaje żadnej ramki: DATA, HACK ani BEACON, także przekazywanej. Kolejka SA1 zostaje. Jedno zgłoszenie wyjęte spod ciszy wychodzi jako DATA bez oczekiwania na HACK (ACKREQ wyłączony), najwyżej 3 razy co 60 s, bo potwierdzenie i tak przyjdzie od odbiorcy po zniesieniu ciszy albo gońcem.

## Budżet czasu

Model jak w [rozdziale 06](../concept/06-wykonalnosc-i-budzet-zasobow.html): SF7, 125 kHz, CR 4/5, preambuła 24 symbole, nagłówek jawny, CRC; czas kanału = 13 × czas TX. Podpis powoduje podział typowego zgłoszenia na dwie ramki po 195 B; RECEIVED zajmuje 158 B, HACK 19 B.

| Przekaźnik przed stanowiskiem | Reticulum/LXMF (dziś) | WICI-Link |
|---|---|---|
| czas kanału na jedno zgłoszenie z RECEIVED | 20,1–21,1 s | 14,74 s typowe; 15,67 s przy największym REQUEST |
| 50 zgłoszeń (W10, bez strat) | 16,8–17,6 min | 12,29 min typowe; 13,06 min przy największym REQUEST |
| 50 zgłoszeń z PRZECZYTANE i decyzją | około 32,3 min | wymaga osobnego przeliczenia dla v2 |

Wąskim gardłem pozostaje przekaźnik obok stanowiska, którego obciążenie nie zależy od długości łańcucha za nim. Opóźnienie rośnie o około 0,5–5 s na skok, zależnie od długu ciszy przekaźnika. Wartości W10 są modelem bez kolizji i odroczeń, policzonym w `software/reference/obliczenia.py`; do potwierdzenia na sprzęcie.

## Pamięć

Nowe struktury w RAM stacji: tablica sąsiadów (16 × około 10 B), tablica dróg w dół (256 × 4 B, kopia w FRAM), pierścień przekazanych kopert (224 × 24 B = 5376 B, kopia w FRAM), cztery buforowane ramki (4 × 255 B), pierścień rozsyłania (256 × 18 B = 4608 B, kopia w FRAM) oraz dwa okna powtórzeń kopert po 32 B w RAM, z dwiema kopiami po 32 B na odbiorcę w FRAM. Stacja schronienia odbiera koperty tylko od głównego i zapasowego numeru odbiorcy; okna dla wielu stacji po stronie stanowiska są w SQLite. `firmware/src/envelope_replay.cpp` zajmuje 0x044F80–0x044FFF (128 B), z CRC, COMMIT i odciskiem wyprowadzonego klucza koperty. Po połączeniu modułów będzie to około 16 KiB plus metadane i bufor składania do 256 B na stosie. `firmware/src/envelope_parts.cpp` ma po jednej trwałej części na każdego z dwóch odbiorców, po dwie kopie 192 B w 0x045E80–0x045FFF i 0x047E00–0x047F7F. Pierwsza część dostaje HACK dopiero po zapisie i odczycie kontrolnym; przy drugiej moduł tylko składa treść, a wywołujący musi utrwalić efekt SA1 i okno powtórzeń przed HACK, potem zapisać trwały pusty rekord. Po tych strukturach w luce FRAM 0x044000–0x047FFF zajęte jest 16 320 z 16 384 B; pozostaje 64 B. Numerowany obraz wywołuje te moduły i łączy odbiór SA1 ze `Store`. Próbę zaniku między SA1 i oknem powtórzeń, stos zadania oraz czas HACK trzeba zmierzyć na sprzęcie D21.

## Zagrożenia

| Zagrożenie | Skutek | Ochrona |
|---|---|---|
| Węzeł bez klucza sieci | zakłócanie kanału | ramki odrzucane przed przetwarzaniem; kolizje bez ochrony (pasmo bez ochrony, D11) |
| Powtórzenie nagranej ramki | podwójne przekazanie | pamięć (`l_src`, `seq`) na skoku i (`src`, `dst`, `ctr`, `kind`) przy rozsyłaniu; okno licznika koperty; deduplikacja SA1 |
| Węzeł z kluczem sieci (przejęta stacja) podrabia zgłoszenie lub potwierdzenie | brak: nie ma klucza pary | koperta z kluczem pary z kart |
| Węzeł z kluczem sieci zalewa kanał | wypieranie ruchu WICI | klasy K0–K2, pula 60%, limit ogłoszeń; próba „Wrogi węzeł” |
| Węzeł z kluczem sieci ogłasza fałszywie niską rangę (przyciąga ruch i go porzuca) | utrata ruchu przez ten węzeł | rodzic z planu ma pierwszeństwo; zmiana rodzica tylko po nieudanych próbach; brak RECEIVED wywołuje ponowienie intencji i alarm; dyżurny widzi w diagnostyce zmiany rodziców; ryzyko szczątkowe, tej samej klasy co przekaźnik Reticulum, który porzuca pakiety |
| Przejęcie klucza prywatnego odbiorcy | odczyt zapisanego ruchu, podrabianie odpowiedzi | klucz zapasowy z kart (D08); brak poufności przyszłej w pilotażu |

## Otwarte pytania

1. Czy HACK można zastąpić potwierdzeniem biernym (nadawca słyszy, jak rodzic przekazuje ramkę dalej), jak w protokołach zbierania danych w sieciach czujników? Oszczędza to jedną ramkę na skok, ale nie działa na ostatnim skoku i przy rodzicu w długu ciszy.
2. Czy zapis FRAM i odpowiedź HACK mieszczą się w 200 ms na docelowym prototypie? Rozmieszczenie kolejki i buforów jest już zaimplementowane; termin wymaga pomiaru.
3. Własne słowo synchronizacji sieci WICI (wyżej).
4. Czy obecne progi SNR i średniej sukcesu HACK dają stabilne trasy w pomiarze T5; wartości progów ustala T5.
5. Czy pomiar W10 potwierdzi model v2 z `software/reference/obliczenia.py`, zwłaszcza zapas 1,94 min przy największym REQUEST?

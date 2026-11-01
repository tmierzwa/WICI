# WICI-Link: protokół łącza sieci stacji

**Stan: projekt do przeglądu (D21), 2026-11-01.** Nośnik radiowy dla [szwu transportu](transport.md). Obowiązuje dopiero po rozstrzygnięciu D21 ([warunek przyjęcia](transport.md#warunek-przyjęcia)).

## Założenia

WICI-Link jest protokołem łącza i tras dla zamkniętej sieci jednej gminy (albo jej części), w której:

- wszystkie stacje i tożsamości odbiorcy są znane z planu sieci i kart z przygotowania, a klucze nigdy nie przychodzą przez radio;
- ruch płynie tylko między stacjami schronień a stanowiskiem odbiorczym, w obie strony; schronienia nie piszą do siebie nawzajem;
- stacje stoją w stałych miejscach, a trasy można zmierzyć przed kryzysem (krok 5);
- każda włączona stacja przekazuje ruch innych (W23).

Protokół używa profilu LoRa pilotażu bez zmian ([radio](radio.md#profil-lora-pilotażu)) i wszystkich reguł [dostępu do kanału](radio.md#dostęp-do-kanału): długu ciszy 12t zapisanego w FRAM, wolnego kanału przez 50 ms i CAD przed nadaniem, limitu 10% i klas K0–K2. Jedna koperta mieści się w jednej ramce LoRa, więc protokół nie potrzebuje podziału datagramu na ramki RNode.

## Ramka

```
 0       1        3        5        7       8        10                  n-8      n
 +-------+--------+--------+--------+-------+--------+-------------------+--------+
 | ver/t | net_id | l_src  | l_dst  | hops  | seq    | ładunek           | MAC(8) |
 +-------+--------+--------+--------+-------+--------+-------------------+--------+
 ver/t: bity 7–6 wersja (1), bity 5–3 typ, bity 2–0 flagi (bit 0 ACKREQ, bit 1 DOWN, bit 2 zarezerwowany)
 net_id: numer sieci z przygotowania (u16)
 l_src, l_dst: numery stacji nadającej i następnego skoku (0xFFFF = wszyscy sąsiedzi)
 hops: bity 7–4 liczba wykonanych skoków, bity 3–0 limit skoków (TTL)
 seq: numer ramki nadawcy łącza (u16, rośnie o 1, zawija się)
 MAC: HMAC-SHA-256(K_link, bajty 0..n-9) obcięty do 8 B
```

Nagłówek ma 11 B, MAC 8 B, razem 19 B narzutu. Największa ramka LoRa ma 255 B, więc `max_payload` nośnika wynosi 236 B.

**Klucz sieci.** `K_link = HKDF-SHA-256(ikm = klucz sieci z przygotowania, salt = net_id, info = "WICI link v1", L = 32)`. Pełni tę samą rolę co dziś kod dostępu sieci (IFAC 16 B): stacja odrzuca ramkę bez poprawnego MAC przed jakimkolwiek dalszym przetwarzaniem, a stacja bez klucza sieci nie nadaje i nie przekazuje. MAC 8 B daje prawdopodobieństwo przyjęcia podrobionej ramki 2⁻⁶⁴ na próbę. Klucz sieci jest wspólny, więc przejęta stacja go zdradza; dlatego autentyczność treści zapewnia koperta, a nie łącze ([zagrożenia](#zagrożenia)).

**Słowo synchronizacji.** Profil pilotażu używa 0x12. Do rozważenia przed T4: własne słowo synchronizacji sieci WICI, żeby radio w ogóle nie zgłaszało ramek Meshtastic, MeshCore i LoRaWAN na tym samym kanale. Nie zmniejsza to kolizji, ale ogranicza pracę procesora i liczbę ramek do odrzucenia.

### Typy ramek

| Typ | Kod | Ładunek | Rozmiar ramki | Czas TX (SF7) |
|---|---|---|---|---|
| DATA | 0 | koperta WICI | 19 B + koperta | 218 B (typowe zgłoszenie): 360 ms |
| HACK | 1 | brak (potwierdza `seq` z `l_src` ramki DATA) | 19 B | 68 ms |
| BEACON | 2 | `root` (u16), `rank` (u16), `epoch` (u16), `parent` (u16), flagi (u8) | 28 B | 83 ms |
| 3–7 | | zarezerwowane | | |

## Trasy

### Drzewo do odbiorcy

Sieć tworzy drzewo zakorzenione w stacji stanowiska odbiorczego (`root`). Każda stacja ma **rodzica**, czyli następny skok w stronę odbiorcy.

1. **Rodzic z planu.** Przy przygotowaniu stacja dostaje w dokumencie konfiguracji rodzica z planu sieci i opcjonalnie rodzica zapasowego, wybranych na podstawie pomiaru tras (kroki 3 i 5). To podstawowy tryb pracy w pilotażu.
2. **Rodzic wybrany samodzielnie.** Gdy rodzic z planu nie odpowiada (3 nieudane próby na kolejnych ramkach DATA), stacja przechodzi na rodzica zapasowego, a gdy go nie ma, wybiera sąsiada z najmniejszym kosztem z ostatnich ramek BEACON. Koszt = `rank` sąsiada + koszt łącza. Koszt łącza liczy się z odsetka potwierdzonych prób (ETX, w jednostkach 1/16) i z SNR; nowy rodzic musi być lepszy o co najmniej 1,5 jednostki ETX (histereza). Do rodzica z planu stacja wraca, gdy znów potwierdza ramki.
3. **Ranga.** `rank` odbiorcy to 0. Stacja ogłasza `rank` = `rank` rodzica + koszt łącza do niego. Stacja nie wybiera na rodzica sąsiada, którego `parent` to ona sama, ani sąsiada z `rank` większym od własnego o więcej niż jeden pełny skok (zapobieganie pętlom). Ramka DATA, która wraca do stacji, która już ją przekazała (ten sam `src` i `ctr` koperty), jest odrzucana i liczona jako pętla.
4. **Limit skoków.** Pole `hops` pozwala na najwyżej 15 skoków. Domyślny limit sieci to 7 i ustawia się go w planie sieci. Reguła planowania pilotażu z [rozdziału 02](../concept/02-scenariusze-i-organizacja.html) (najwyżej 2 przeskoki do stanowiska, dopóki T5 nie sprawdzi dłuższych łańcuchów) dotyczy planu, nie protokołu.

### BEACON

Każda stacja z ustaloną rangą nadaje BEACON co 30 min ±20%, po zmianie rodzica lub rangi (najwyżej raz na 60 s) oraz trzy razy w pierwszych 5 min po starcie, z losowym opóźnieniem. Przy 50 stacjach to około 8 s czasu nadawania na godzinę w całym obszarze kolizji. BEACON-y wliczają się do limitu ogłoszeń 2% czasu zegarowego i do wspólnej puli z K2 ([dostęp do kanału](radio.md#dostęp-do-kanału)). W ciszy radiowej stacja nie nadaje BEACON-ów.

`epoch` nadaje odbiorca i zwiększa go przy każdym starcie stanowiska. Stacja przyjmuje rangę tylko z bieżącej albo nowszej epoki; po zmianie epoki przelicza rangę od nowa.

### Ruch w górę i w dół

- **W górę** (do odbiorcy): stacja wysyła DATA do rodzica. Każdy przekaźnik przekazuje ją swojemu rodzicowi.
- **W dół** (od odbiorcy): każdy przekaźnik zapamiętuje, przez którego sąsiada przyszła ostatnia ramka DATA w górę od danej stacji (numer `src` z koperty, sąsiad z `l_src`). Ramkę DATA z flagą DOWN do tej stacji przekazuje temu sąsiadowi. Tablica ma do 256 wpisów po 4 B, jest zapisywana w FRAM i odtwarzana po restarcie, tak jak dziś tablica tras. Odbiorca zna drogę do każdej stacji po jej pierwszym TEST startowym.
- **Brak wpisu:** przekaźnik bez wpisu dla celu w dół rozsyła ramkę do wszystkich sąsiadów (`l_dst` = 0xFFFF) z limitem skoków, a każda stacja przekazuje taką ramkę najwyżej raz (pamięć `seq` i nadawcy łącza). To tryb awaryjny, liczony w diagnostyce.

### Potwierdzenie na każdym skoku

1. Ramka DATA ma flagę ACKREQ. Następny skok odpowiada ramką HACK z tym samym `seq`, adresowaną do `l_src`, gdy przyjmie ramkę do swojej kolejki radiowej albo, jeśli jest celem, po przyjęciu koperty przez warstwę wyżej.
2. HACK wychodzi najpóźniej 200 ms po końcu ramki DATA, po samym CAD, bez okna 50 ms. Może wyjść w trakcie długu ciszy stacji; jej czas nadawania z dwunastokrotnością dolicza się do długu. Udział nadawania w długim czasie pozostaje więc 1/13 (około 7,7%).
3. Nadawca czeka na HACK 600 ms. Bez HACK ponawia ramkę po swoim długu ciszy i losowym 0,5–2 s, najwyżej 3 razy na rodzica, potem próbuje rodzica zapasowego (najwyżej 3 razy), potem zgłasza `Failed` do szwu.
4. Stacja odbierająca powtórzoną ramkę (ten sam `l_src` i `seq` w ciągu 120 s) wysyła HACK ponownie, ale nie przekazuje ramki drugi raz.

Ponowienie na skoku zastępuje ponowienie przez cały łańcuch: przy 95% skuteczności jednego nadania i trzech próbach jeden skok przechodzi z prawdopodobieństwem 99,99%, więc skuteczność łańcucha prawie nie spada z jego długością. Ponowienia intencji SA1 (10 min po doręczeniu, potem co 30–60 min) zostają bez zmian i działają nad nośnikiem.

## Klasy czasu kanału

Reguły podziału czasu z [radio](radio.md#dostęp-do-kanału) zostają, z jedną zmianą znaczenia klas, możliwą dzięki jawnym numerom stacji w kopercie:

- **K0:** własne ramki DATA stacji, HACK.
- **K1:** przekazywane ramki DATA, których koperta ma `dst` albo `src` równe aktywnej tożsamości odbiorcy z karty. W Reticulum przekaźnik nie odróżniał ruchu od odbiorcy do schronień od ruchu obcego, więc ten ruch był w K2. Teraz cały ruch sieci WICI do odbiorcy i od niego jest w K1.
- **K2:** pozostałe przekazywane ramki, w tym rozsyłanie awaryjne bez wpisu w tablicy; BEACON-y w puli ogłoszeń.

## Cisza radiowa

W ciszy radiowej (W19) stacja nie nadaje żadnej ramki: DATA, HACK ani BEACON, także przekazywanej. Kolejka SA1 zostaje. Jedno zgłoszenie wyjęte spod ciszy wychodzi jako DATA bez oczekiwania na HACK (ACKREQ wyłączony), najwyżej 3 razy co 60 s, bo potwierdzenie i tak przyjdzie od odbiorcy po zniesieniu ciszy albo gońcem.

## Budżet czasu

Model jak w [rozdziale 06](../concept/06-wykonalnosc-i-budzet-zasobow.html): SF7, 125 kHz, CR 4/5, preambuła 24 symbole, nagłówek jawny, CRC; czas kanału = 13 × czas TX. Ramki: zgłoszenie typowe 218 B, RECEIVED 94 B, STATUS 103 B, HACK 19 B.

| Przekaźnik przed stanowiskiem | Reticulum/LXMF (dziś) | WICI-Link |
|---|---|---|
| czas kanału na jedno zgłoszenie z RECEIVED | 20,1–21,1 s | około 8,8 s |
| 50 zgłoszeń (W10, bez strat) | 16,8–17,6 min | około 7,3 min |
| 50 zgłoszeń z PRZECZYTANE i decyzją | około 32,3 min | około 12,9 min |

Przy łańcuchu 5 skoków w jednym obszarze kolizji 50 zgłoszeń z RECEIVED zajmuje łącznie około 2,8 min czasu nadawania wszystkich stacji. Wąskim gardłem pozostaje przekaźnik obok stanowiska, którego obciążenie nie zależy od długości łańcucha za nim. Opóźnienie rośnie o około 0,5–5 s na skok, zależnie od długu ciszy przekaźnika. Wartości są modelem bez kolizji i odroczeń, do potwierdzenia na sprzęcie; przed przyjęciem D21 trzeba je dodać do `software/reference/obliczenia.py`.

## Pamięć

Nowe struktury w RAM stacji: tablica sąsiadów (16 × 12 B), tablica dróg w dół (256 × 4 B, kopia w FRAM), pamięć powtórzeń łącza (256 × 4 B), okna liczników koperty (256 × 12 B, kopia w FRAM). Razem około 5,3 KiB, mniej niż tablica tras i lista skrótów pakietów rdzenia Reticulum (256 × 24 B i 4096 × 8 B). Pomiar na płytce w kroku 4 (D14).

## Zagrożenia

| Zagrożenie | Skutek | Ochrona |
|---|---|---|
| Węzeł bez klucza sieci | zakłócanie kanału | ramki odrzucane przed przetwarzaniem; kolizje bez ochrony (pasmo bez ochrony, D11) |
| Powtórzenie nagranej ramki | podwójne przekazanie | pamięć `seq` łącza; okno licznika koperty; deduplikacja SA1 |
| Węzeł z kluczem sieci (przejęta stacja) podrabia zgłoszenie lub potwierdzenie | brak: nie ma klucza pary | koperta z kluczem pary z kart |
| Węzeł z kluczem sieci zalewa kanał | wypieranie ruchu WICI | klasy K0–K2, pula 60%, limit ogłoszeń; próba „Wrogi węzeł” |
| Węzeł z kluczem sieci ogłasza fałszywie niską rangę (przyciąga ruch i go porzuca) | utrata ruchu przez ten węzeł | rodzic z planu ma pierwszeństwo; zmiana rodzica tylko po nieudanych próbach; brak RECEIVED wywołuje ponowienie intencji i alarm; dyżurny widzi w diagnostyce zmiany rodziców; ryzyko szczątkowe, tej samej klasy co przekaźnik Reticulum, który porzuca pakiety |
| Przejęcie klucza prywatnego odbiorcy | odczyt zapisanego ruchu, podrabianie odpowiedzi | klucz zapasowy z kart (D08); brak poufności przyszłej w pilotażu |

## Otwarte pytania

1. Czy HACK można zastąpić potwierdzeniem biernym (nadawca słyszy, jak rodzic przekazuje ramkę dalej), jak w protokołach zbierania danych w sieciach czujników? Oszczędza to jedną ramkę na skok, ale nie działa na ostatnim skoku i przy rodzicu w długu ciszy.
2. Czy przekaźnik ma przechowywać przekazywane ramki w FRAM do potwierdzenia na następnym skoku (D06)?
3. Własne słowo synchronizacji sieci WICI (wyżej).
4. Czy koszt łącza liczyć z ETX, SNR czy obu; wartości progów ustala T5.
5. Zapis w `software/reference/obliczenia.py` i przeliczenie W10, zimnego startu i pojemności z rozdziału 06.

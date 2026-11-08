# Emulator WICI-Link

Wiele węzłów z prawdziwym kodem stacji i roota z `firmware/src` na jednym komputerze, z zegarem wirtualnym i modelem kanału. Służy do sprawdzenia logiki i obciążenia dróg w łańcuchach do 15 skoków, zanim zmieni się kod stacji. **Nie dowodzi niczego o radiu**: wyniki obowiązują tylko przy założeniach niżej, które pomiary (próba przy stole, krótki łańcuch) mają dopiero zastąpić. Wyniki z 2026-11-05 są w [raporcie](../../../docs/emulator-wici-link.md).

```bash
python3 firmware/tools/stack_deps.py
```
```bash
python3 tests/native/wici_emulator/run.py build /tmp/emu
```
```bash
/tmp/emu/wici_emulator_base koniec seed=1 p=900
```
```bash
python3 tests/native/wici_emulator/run.py matrix /tmp/emu wyniki.jsonl
```

Pierwsze polecenie pobiera przypięte biblioteki (emulator potrzebuje tylko Crypto). Ten sam plik wykonywalny z tym samym ziarnem daje ten sam wynik co do bajtu. Sprawdza to `tests/test_wici_emulator.py`, pod ASan i UBSan.

## Co jest czym

| Plik | Zawartość |
|---|---|
| `emulator.h`, `emulator.cpp` | radio, kanał, skrót stanowiska i stacji |
| `scenarios.cpp` | scenariusze, wynik jako jeden wiersz JSON na przebieg |
| `variant.patch` | rozstrzygnięcia z 2026-11-05 jako łatka na kopię `firmware/src` |
| `run.py` | budowanie obu plików wykonywalnych i macierz przebiegów raportu |

**Prawdziwy kod:** `wici_radio`, `wici_destination`, `wici_hop`, `wici_route`, `wici_flood`, `wici_relay`, `wici_seen`, `wici_seq`, `wici_link`, `wici_gateway`, `wici_epoch`, `wici_beacon`, `wici_hop_auth`, `wici_airtime`, `kiss`, koperta i kryptografia. Każdy węzeł ma własny obraz FRAM w RAM, własne klucze i liczy tagi pary oraz podpisy naprawdę.

**Skrót, nie kod produkcyjny:**

- `Radio` to odpowiednik `Bench` i `WiciAir` (`measure.cpp`, `main.cpp`): dług ciszy 12t, 50 ms wolnego kanału, CAD, odroczenie 100–1000 ms, najwyżej 30 odroczeń, zatrzymanie kanału do terminu HACK, ścieżka HACK z limitami długu i terminu 200 ms.
- `Laptop` to skrót `WiciStos` i `Wysylka`: jedno zgłoszenie do roota naraz, cztery wiadomości w toku, trzy próby, ponowienia 60/120/300/900 s, 35 min po przekazaniu przekaźnikowi, `contact` i `accepted`, limit powtórnych HACK.
- Obieg stacji w `Net::pollApp` to skrót `Station`: dwie wiadomości w toku, 60 s, 10 min po HACK, potem 30–60 min, po porażce 60/120/300/900 s.

## Warianty rozstrzygnięć

`variant.patch` dodaje do kopii kodu przełączniki (`wici_variant.h`, `Table::leaveParent`, `Root::setFloodNext`). W firmware ich nie ma. Plik `wici_emulator_base` powstaje z niezmienionego `firmware/src`, a `wici_emulator_variant` z kopii po łatce. Z wyłączonymi przełącznikami oba dają wynik identyczny co do bajtu (test), więc różnica w wynikach pochodzi z przełączników. Łatka, która przestanie pasować do firmware, przerywa budowanie (`patch --fuzz=0`).

| Parametr | Rozstrzygnięcie | Gdzie działa |
|---|---|---|
| `learn=1` | drogi w dół z ruchu w górę, ostatnia wygrywa, droga sąsiada do samego siebie nie ustępuje, root uczy się po uwierzytelnieniu koperty, bez planu `behind` | `wici_route`, `wici_hop` |
| `alternate=1` | intencje na przemian: droga, rozsyłanie; ramka rozsyłana zostaje rozsyłana poza ostatnim skokiem do sąsiada | `wici_gateway`, `wici_hop`, skrót stanowiska |
| `leave=1800 hold=7200` | otwarta wiadomość po HACK bez wiadomości od odbiorcy: zmiana rodzica, a opuszczony nie wraca przez blokadę | `wici_route`, skrót stacji |
| `flood=700` | budżet rozsyłania stanowiska na stację | skrót stanowiska |

Próby z drugiej tury raportu, też tylko tu:

| Parametr | Co robi | Gdzie działa |
|---|---|---|
| `k1flood=1` | ramka z gniazda K1 bez znanej drogi zachowuje pierwszeństwo K1 przy limicie 25% (poprawka bez zmiany bajtów) | `wici_hop` |
| `k1routed=1` | przy limicie 25% liczą się tylko czekające ramki K1 ze znaną drogą; ramka K1 bez drogi zostaje K2 (poprawka bez zmiany bajtów) | `wici_hop` |
| `floodparent=1\|2\|3` | ramka w dół wychodzi rozsyłaniem tylko od rodzica. 1: planowy lub zapasowy; 2: także bieżący; 3: kontrola pułapki, odrzucona kopia oznaczona jako widziana | `wici_hop` |
| `sticky=1` | nauka tylko brakującej drogi zamiast „ostatnia wygrywa” (próba przyczyny) | `wici_route` |
| `nopool=1` | bez dziennika czasu nadawania (tylko próba przyczyny, nie do firmware) | `Radio` |
| `leaven=N`, `permessage=1` | zmiana rodzica przed nadaniem, gdy N nadań dostało HACK i nic nie wróciło; `permessage`: licznik zeruje tylko odpowiedź na tę wiadomość | skrót stacji |
| `probe=S`, `probeevery=S`, `probemode=1\|2` | próbka przekaźnika po S sekundach bez powrotu; tryb 1: powrót to każda ramka w dół, tryb 2: tylko własna uwierzytelniona wiadomość | skrót stacji, `Net::noteTraffic` |
| `hole=I`, `selective=1\|2`, `fake=1\|2` | gdzie stoi porzucający; 1: przepuszcza własny ruch dziecka i porzuca resztę, 2: uczciwy; `fake`: podsuwa ramki w dół (1 do końca łańcucha, 2 co 10 s do numeru bez drogi) | `Net::deliver`, `Net::pollFakeDown` |
| `trace=1` | zapis przebiegu na stderr | `Net::traceAir` |

Dodatkowe scenariusze: `przerwa` (stanowisko wyłączone, ruch tylko z końca łańcucha) i `drzewo` (50 stacji, dwa pnie po 15 skoków z odgałęzieniami) oraz `atak_k1` (sąsiad podsuwa ramki K1 do numerów bez drogi co `fakeevery` sekund; z `n` wszyscy się słyszą, `fromend=1` to ruch tylko z końca łańcucha) i `regula_rodzica` (te same ataki z ruchem w dół; `downrounds`, `downevery`, `dead`, `moved`, `leaves`, `two=1` z `bridge`: dwa łańcuchy z jednym łączem obejścia, `fakebroadcast=1`: ramki rozsyłane wprost; `evilparent=I`: napastnik z fałszywie niską rangą zostaje rodzicem dynamicznym stacji I po odcięciu jej rodzica planowego i zapasowego, w sieci słyszącej się I ofiar; `evildrop=1`: napastnik porzuca ruch po HACK; `stale=1|N`: nadawca dostaje starą drogę przez sąsiada, dla którego nie jest rodzicem, a sąsiad tej drogi nie ma; `dead2=1`: gaśnie też stacja za `dead`, a jedynym wyjściem jest łącze nad awarię).

Pozostałe parametry: `seed`, `p` (skuteczność łącza w promilach), `hops`, `reports`, `spread`, `hours`, `n`, `skip` (łącza co dwa skoki i rodzic zapasowy, w promilach), `sense` (2: stacja słyszy też drugiego sąsiada, choć go nie odbierze), `miss`.

## Założenia modelu kanału

Żadne nie pochodzi z pomiaru tego modelu; miejsca w kodzie to `Assumptions` w `emulator.h` i `Net::stepAir`.

| Założenie | Wartość | Skutek |
|---|---|---|
| Czas ramki | `lora::frameAirMs` z firmware (profil SF7, 125 kHz) | obliczony, nie założony |
| Skuteczność ramki na łączu | `p` niezależnie dla każdej ramki i każdego odbiornika, HACK też | **brak strat seriami**; prawdziwe łącze ma je na pewno, więc ponowienia wypadną tu lepiej niż w terenie |
| Kolizja | każde nałożenie niszczy obie ramki u odbiornika, bez efektu przechwycenia | pesymistyczne |
| Zasięg | łańcuch: słychać tylko sąsiadów (`sense=1`), więc stacje i, i+2 są wobec siebie ukryte | pesymistyczne dla kolizji |
| Nasłuch | ramka w toku niezauważona z prawdopodobieństwem 2% | do pomiaru |
| Opóźnienia | CAD 6 ms, HACK stacji 25 ms po odbiorze, root 5 ms, USB 3 ms, przyjęcie na stanowisku 40 ms, sprawdzenie BEACON-u 200 ms, obieg pętli 10 ms | szacunki, D21 ma je zmierzyć |
| SNR | 0 dB, koszt łącza tylko ze skuteczności HACK | ranga bez kary SNR |
| Awarie zasilania, cisza, dwie tożsamości odbiorcy | nie ma | poza zakresem |
| Treść | zgłoszenie 174 B, RECEIVED 50 B (`typical_request`, `received` w `software/reference/wyniki.json`) | jedna ramka; największe zgłoszenie (222 B, dwie części) tylko przez parametr `Net::report` |

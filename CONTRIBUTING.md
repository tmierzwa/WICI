# Współpraca przy WICI

Projekt jest prototypem. Zmiany mają upraszczać wykonanie, usuwać zależność od jednego dostawcy i zwiększać niezawodność; wygląd i dodatkowe funkcje nie są priorytetem. Najcenniejszym wkładem są zgłoszone błędy w obliczeniach, założeniach i kontraktach oraz raporty z prób fizycznych.

## Jak zgłosić zmianę

1. Dla większej zmiany otwórz [Issue](https://github.com/tmierzwa/WICI/issues/new/choose): problem, proponowany zakres i warunek sprawdzenia. Małe poprawki można wysłać bezpośrednio jako pull request.
2. Pracuj w swojej gałęzi. Opisz, co zmienia PR i jak to sprawdzono; wymagane punkty podaje szablon PR.
3. Parametry i kontrakty stacji zmieniaj w `docs/spec/`. Potrzeby, uzasadnienia, opcje i analizę wykonalności utrzymuj w [docs/concept](docs/concept/index.html). Aktualizuj powiązane wymagania i próby; odróżniaj założenie od pomiaru. Nie twórz drugiej pełnej kopii specyfikacji.
4. Zmiana kodu kontraktów wymaga przypadku, który pokazuje problem, i wyniku odpowiednich testów. Raport aktualizuj dopiero po ich wykonaniu.
5. Zmiana CAD płytki R02 wymaga aktualnych raportów ERC/DRC i dowodów w `checks/` według [opisu projektu](hardware/r02/README.md) i [lekcji](hardware/r02/lekcje.md). Zmiana elektryczna wymaga nowej rewizji. Nie zmieniaj historycznych raportów na wyniki nowych prób. Zmiana płytki nośnej N1 idzie przez `hardware/dev-bench/tools/design.py` i generatory, z nowymi `checks/erc.json` i `checks/drc.json`; plików w `cad/` nie poprawia się ręcznie.
6. Raport z prób fizycznych podaje rewizję, elementy, warunki, metodę i wynik; użyj szablonu „Raport z próby”. Nie oznaczaj niewykonanych prób jako zaliczonych. Sam CI nie zwalnia statusu HOLD. Raporty zostają w Issues z etykietą `próba`; po przyjęciu opiekun repozytorium wpisuje wynik w kolumnie „Stan” [odbioru](docs/spec/odbior.md) z odnośnikiem do Issue. Propozycję rozstrzygnięcia decyzji zgłasza się szablonem „Decyzja”.

## Od czego zacząć

Oprogramowanie stacji w [firmware/](firmware/README.md) działa na stanowiskach A i B (ze stosem Reticulum z portu microReticulum, bez LXMF; jeszcze nie uruchomione na sprzęcie), a płytki R02 jeszcze nie ma. Zadania, które można wykonać teraz:

1. Zmontować płytkę nośną N1, uruchomić obraz `bench-n1` albo `bench-b` według [uruchomienia](hardware/dev-bench/uruchomienie.md) i zgłosić raport z kroków A1–A5 albo B1–B4. Kod oprogramowania układowego trafia do `firmware/` (licencja MIT); ramka P1 jest już w `firmware/src/p1frame.cpp`.
2. Uruchomić obraz ze stosem na płytkach rozwojowych nRF52840 i ESP32-S3 i wymienić pakiety z implementacją Reticulum w Pythonie przez łącze P1; na komputerze ta wymiana już przechodzi z emulatorem łącza ([próba zgodności](firmware/README.md#próba-zgodności-z-reticulum)). To pierwsza część T3; w raporcie podaj zapas RAM zmierzony poleceniem `RNS` i listę prób na sprzęcie z tej sekcji.
3. Rozszerzyć emulator łącza P1 programu `host` (`firmware/src/host/node_host.cpp`: czas TX z modelu ramki, dług ciszy 12×; kolejka do 4 datagramów jest w interfejsie P1) o CCA, odroczenia i kolizje między kilkoma węzłami ([radio.md](docs/spec/radio.md)).
4. Dodać do modelu protokół USB laptop–stacja (D17) i dziennik FRAM z długiem ciszy.
5. Zbudować [stanowisko deweloperskie](hardware/dev-bench/README.md) A lub B z kupnych płytek i wykonać na nim pierwsze pomiary P1 poleceniami pomiarowymi z [radio.md](docs/spec/radio.md); wynik jest wejściem do projektu płytki [R02](hardware/r02/README.md).

Przed pracą otwórz Issue lub skomentuj istniejące, aby nie dublować wysiłku.

## Kontrole przed PR

Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py --pull-request
```

**Nie odświeżaj `manifest.json`.** Sumy kontrolne całego repozytorium odświeża opiekun repozytorium po scaleniu i przed wydaniem; w PR prowadziłyby do konfliktów między równoległymi zmianami. Kontrola z `--pull-request` sprawdza wszystko poza zgodnością tego pliku. Dowody związane z treścią zmiany odświeżasz sam:

- zmiana `software/reference/obliczenia.py`: uruchom go, aby zaktualizować `wyniki.json`, a po testach zaktualizuj `weryfikacja.json`;
- zmiana plików w `hardware/r02/`: odśwież raporty i dowody w `checks/` tej rewizji według jej README; nie zmieniaj historycznych raportów.

Nie odświeżaj sum w odpowiedzi na nieznany błąd CI; najpierw ustal, co się zmieniło. Nowy plik musi mieć licencję: nagłówek `SPDX-License-Identifier` albo wpis w [REUSE.toml](REUSE.toml); CI sprawdza to poleceniem `reuse lint`.

## Pochodzenie wkładu (DCO)

Każdy commit w PR kończy się wierszem `Signed-off-by: Imię Nazwisko <email>` (`git commit -s`). Oznacza on zgodę na [Developer Certificate of Origin 1.1](https://developercertificate.org/): masz prawo przesłać ten materiał na licencji właściwej dla ścieżki. Nie wymagamy CLA ani przeniesienia praw autorskich.

Nie dodawaj kluczy, danych mieszkańców, kopii prywatnych rozmów ani materiałów producenta bez uprawnień do dystrybucji. Lokalny `reference-private/` nie należy do wydania. Dla nowej biblioteki lub footprintu zapisz źródło, wersję, modyfikacje i licencję.

Jeżeli korzystasz z narzędzi AI, napisz o tym w opisie PR i sprawdź wynik tak, jakby był Twój: odpowiadasz za każdy wiersz.

## Decyzje i przeglądy

Na razie projekt ma jednego opiekuna repozytorium ([@tmierzwa](https://github.com/tmierzwa)). Opiekun repozytorium scala PR, zamyka decyzje D01–D19 z [planu weryfikacji](docs/concept/08-plan-weryfikacji-i-decyzje.html) i wydaje wersje. Decyzja zapada w Issue lub PR, z uzasadnieniem i dowodem wymaganym w tabeli decyzji; zmiana decyzji wymaga nowego dowodu, nie samej dyskusji.

Zmiany krytyczne dla bezpieczeństwa ludzi (przetwornica 230 V i ochrona PE, ochrona portów telefonów przed przepięciem, zabezpieczenia akumulatorów, budżet czasu nadawania) wymagają, oprócz opiekuna repozytorium, przeglądu przez osobę z odpowiednimi kwalifikacjami. Dopóki taka osoba nie dołączy do projektu, te części pozostają opisem do prób i mają status HOLD.

Główna gałąź jest chroniona: scalenie wymaga przejścia CI. Wydania mają tagi `v*` i paczkę źródłową z pełną kontrolą manifestu. Reguła repozytorium nie pozwala przesunąć ani usunąć tagu `v*`, także administratorom; poprawka wydania dostaje nowy numer, np. `v0.5.1`.

## Licencje

Wkład pozostaje pod licencją właściwą dla ścieżki w [LICENSE.md](LICENSE.md): kod MIT, konstrukcja CERN-OHL-P-2.0, dokumentacja CC-BY-4.0. Cel projektu jest niekomercyjny; wybrane otwarte licencje nie zabraniają zastosowań komercyjnych. Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md); podatności zgłaszaj według [SECURITY.md](SECURITY.md).

## In English

Contributions in English are welcome; documentation stays in Polish, and maintainers will help with translation. In short:

- Open an issue for larger changes; small fixes can go straight to a pull request.
- Run the three checks above with `--pull-request`. **Do not refresh `manifest.json`**; the maintainer does it after merging. Refresh only the evidence your change affects (calculation results, hardware evidence).
- Sign off every commit (`git commit -s`, [DCO 1.1](https://developercertificate.org/)). No CLA.
- Keep assumptions separate from measurements; never mark an unperformed test as passed.
- Safety-critical parts (230 V inverter, phone over-voltage protection, batteries, transmit budget) need review by a qualified person and stay on HOLD until then.
- Disclose AI assistance in the PR; you are responsible for every line.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

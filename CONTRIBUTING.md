# Współpraca przy WICI

Projekt jest prototypem. Zmiany mają upraszczać wykonanie, usuwać zależność od jednego dostawcy i zwiększać niezawodność; wygląd i dodatkowe funkcje nie są priorytetem. Najcenniejszym wkładem są zgłoszone błędy w obliczeniach, założeniach i kontraktach oraz raporty z prób fizycznych.

## Jak zgłosić zmianę

1. Dla większej zmiany otwórz [Issue](https://github.com/tmierzwa/WICI/issues/new/choose): problem, proponowany zakres i warunek sprawdzenia. Małe poprawki można wysłać bezpośrednio jako pull request.
2. Pracuj w swojej gałęzi. Opisz, co zmienia PR i jak to sprawdzono; wymagane punkty podaje szablon PR.
3. Parametry i kontrakty stacji zmieniaj w `docs/spec/`. Potrzeby, uzasadnienia, opcje i analizę wykonalności utrzymuj w [docs/conception](docs/conception/index.html). Aktualizuj powiązane wymagania i próby; odróżniaj założenie od pomiaru. Nie twórz drugiej pełnej kopii specyfikacji.
4. Zmiana kodu kontraktów wymaga przypadku, który pokazuje problem, i wyniku odpowiednich testów. Raport aktualizuj dopiero po ich wykonaniu.
5. Zmiana CAD wymaga aktualnych ERC/DRC, eksportów i kontroli paczki według [procedury odtworzenia](hardware/radio-test-r01/odtworzenie.md). Zmiana elektryczna wymaga nowej rewizji. Nie zmieniaj historycznych raportów na wyniki nowych prób.
6. Raport z prób fizycznych podaje rewizję, elementy, warunki, metodę i wynik; użyj szablonu „Raport z próby”. Nie oznaczaj niewykonanych prób jako zaliczonych. Sam CI nie zwalnia statusu HOLD. Raporty zostają w Issues z etykietą `próba`; po przyjęciu opiekun repozytorium wpisuje wynik w kolumnie „Stan” [odbioru](docs/spec/odbior.md) z odnośnikiem do Issue. Propozycję rozstrzygnięcia decyzji zgłasza się szablonem „Decyzja”.

## Od czego zacząć

Nie ma jeszcze oprogramowania stacji ani płytki R02. Zadania, które można wykonać teraz:

1. Przenieść ramkę P1 (CRC, fragmentacja, składanie) do C/C++ i sprawdzić ją na wektorach z [modelu](software/reference/reference.py). Kod oprogramowania układowego trafia do `firmware/` (licencja MIT).
2. Uruchomić microReticulum na płytkach rozwojowych nRF52840 i ESP32-S3 i wymienić pakiety z implementacją Reticulum w Pythonie. To pierwsza część T3; w raporcie podaj przypięte commity i zapas RAM.
3. Opisać i zbudować emulator ograniczeń P1: czas TX, dług ciszy 12×, CCA i kolejka do 4 datagramów ([radio.md](docs/spec/radio.md)).
4. Dodać do modelu protokół USB laptop–stacja (D17) i dziennik FRAM z długiem ciszy.
5. Zbudować stanowisko R01.3 do pomiarów P1 (T4) z zasilacza laboratoryjnego ([sprzęt](hardware/radio-test-r01/README.md)).

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
- zmiana plików w `hardware/radio-test-r01/`: wykonaj `python3 hardware/radio-test-r01/tools/check_bundle.py`; zmiana eksportów wymaga też `verify_fabrication.py`.

Nie odświeżaj sum w odpowiedzi na nieznany błąd CI; najpierw ustal, co się zmieniło. Nowy plik musi mieć licencję: nagłówek `SPDX-License-Identifier` albo wpis w [REUSE.toml](REUSE.toml); CI sprawdza to poleceniem `reuse lint`.

## Pochodzenie wkładu (DCO)

Każdy commit w PR kończy się wierszem `Signed-off-by: Imię Nazwisko <email>` (`git commit -s`). Oznacza on zgodę na [Developer Certificate of Origin 1.1](https://developercertificate.org/): masz prawo przesłać ten materiał na licencji właściwej dla ścieżki. Nie wymagamy CLA ani przeniesienia praw autorskich.

Nie dodawaj kluczy, danych mieszkańców, kopii prywatnych rozmów ani materiałów producenta bez uprawnień do dystrybucji. Lokalny `reference-private/` nie należy do wydania. Dla nowej biblioteki lub footprintu zapisz źródło, wersję, modyfikacje i licencję.

Jeżeli korzystasz z narzędzi AI, napisz o tym w opisie PR i sprawdź wynik tak, jakby był Twój: odpowiadasz za każdy wiersz.

## Decyzje i przeglądy

Na razie projekt ma jednego opiekuna repozytorium ([@tmierzwa](https://github.com/tmierzwa)). Opiekun repozytorium scala PR, zamyka decyzje D01–D18 z [planu weryfikacji](docs/conception/08-plan-weryfikacji-i-decyzje.html) i wydaje wersje. Decyzja zapada w Issue lub PR, z uzasadnieniem i dowodem wymaganym w tabeli decyzji; zmiana decyzji wymaga nowego dowodu, nie samej dyskusji.

Zmiany krytyczne dla bezpieczeństwa ludzi (przetwornica 230 V i ochrona PE, ochrona portów telefonów przed przepięciem, zabezpieczenia akumulatorów, budżet czasu nadawania) wymagają, oprócz opiekuna repozytorium, przeglądu przez osobę z odpowiednimi kwalifikacjami. Dopóki taka osoba nie dołączy do projektu, te części pozostają opisem do prób i mają status HOLD.

Główna gałąź jest chroniona: scalenie wymaga przejścia CI. Wydania mają tagi `v*` i paczkę źródłową z pełną kontrolą manifestu.

## Licencje

Wkład pozostaje pod licencją właściwą dla ścieżki w [LICENSE.md](LICENSE.md): kod MIT, konstrukcja CERN-OHL-P-2.0, dokumentacja CC-BY-4.0. Cel projektu jest niekomercyjny; wybrane otwarte licencje nie zabraniają zastosowań komercyjnych. Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md); podatności zgłaszaj według [SECURITY.md](SECURITY.md).

## In English

Contributions in English are welcome; documentation stays in Polish, and maintainers will help with translation. In short:

- Open an issue for larger changes; small fixes can go straight to a pull request.
- Run the three checks above with `--pull-request`. **Do not refresh `manifest.json`**; the maintainer does it after merging. Refresh only the evidence your change affects (calculation results, hardware bundle).
- Sign off every commit (`git commit -s`, [DCO 1.1](https://developercertificate.org/)). No CLA.
- Keep assumptions separate from measurements; never mark an unperformed test as passed.
- Safety-critical parts (230 V inverter, phone over-voltage protection, batteries, transmit budget) need review by a qualified person and stay on HOLD until then.
- Disclose AI assistance in the PR; you are responsible for every line.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

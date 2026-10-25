# Współpraca przy WICI

Projekt jest na etapie projektowania prototypu. Najbliższy cel to wymiana zgłoszeń na gotowych płytkach ESP32-S3 z SX1262 oraz próby w terenie. Zmiany mają upraszczać wykonanie, usuwać zależność od jednego dostawcy i zwiększać niezawodność; wygląd i dodatkowe funkcje nie są priorytetem. Najcenniejszym wkładem są zgłoszone błędy w obliczeniach, założeniach i kontraktach oraz raporty z prób fizycznych.

## Jak zgłosić zmianę

1. Przy większej zmianie otwórz [Issue](https://github.com/tmierzwa/WICI/issues/new/choose) i opisz w nim problem, proponowany zakres i warunek sprawdzenia. Małe poprawki można wysłać bezpośrednio jako zgłoszenie zmiany (pull request, PR).
2. Pracuj w swojej gałęzi. Opisz, co zmienia PR i jak go sprawdzono. Wymagane punkty są w szablonie PR.
3. Parametry i kontrakty stacji zmieniaj w `docs/spec/`. Potrzeby, uzasadnienia, opcje i analizę wykonalności utrzymuj w [docs/concept](docs/concept/index.html). Aktualizuj powiązane wymagania i próby; odróżniaj założenie od pomiaru. Nie twórz drugiej pełnej kopii specyfikacji.
4. Zmiana kodu kontraktów wymaga przypadku testowego, który pokazuje problem, oraz wyniku odpowiednich testów. Raport aktualizuj dopiero po ich wykonaniu.
5. Zmiana CAD płytki R02 wymaga aktualnych raportów ERC/DRC i dowodów w `checks/` według [opisu projektu](hardware/r02/README.md) i [lekcji](hardware/r02/lekcje.md). Zmiana elektryczna wymaga nowej rewizji. Nie zmieniaj historycznych raportów na wyniki nowych prób. Zmiana płytki nośnej N1 idzie przez `hardware/dev-bench/tools/design.py` i generatory, z nowymi `checks/erc.json` i `checks/drc.json`; plików w `cad/` nie poprawia się ręcznie.
6. Raport z prób fizycznych podaje rewizję, elementy, warunki, metodę i wynik; użyj szablonu „Raport z próby”. Nie oznaczaj niewykonanych prób jako zaliczonych. Samo przejście CI nie zdejmuje statusu HOLD. Raporty zostają w Issues z etykietą `próba`. Po przyjęciu raportu opiekun repozytorium wpisuje wynik w kolumnie „Stan” [odbioru](docs/spec/odbior.md) z odnośnikiem do Issue. Propozycję rozstrzygnięcia decyzji zgłasza się szablonem „Decyzja”.

## Od czego zacząć

Oprogramowanie stacji w [firmware/](firmware/README.md) jest skompilowane dla stanowisk deweloperskich A i B oraz stacji L0, ze stosem Reticulum. Od etapów R6-3 i R6-4 stos opiera się na rdzeniu stacji z LXMF ([reticulum-core.md](firmware/reticulum-core.md)). Oprogramowania nie uruchomiono jeszcze na sprzęcie. Pilotaż używa gotowej płytki ESP32-S3 z układem LoRa SX1262, a płytka R02 jest wstrzymana do decyzji po pilotażu.

### Małe zadania bez sprzętu

Każde wymaga tylko Pythona 3.12 i edytora. Recenzję wykonuje opiekun repozytorium. Przy zadaniu 3 także druga osoba ze znajomością danego języka, jeśli jest dostępna.

1. **Kontrola cytatów z ekranu.** Wejście: tabela [Teksty ekranu](docs/spec/oprogramowanie.md#teksty-ekranu) (czyta ją `firmware/tools/ui_texts.py`) oraz karty i instrukcje w `docs/spec/`. Wynik: test w `tests/`, który sprawdza, że każdy cytat wielkimi literami w cudzysłowie „…” (w karcie UK «…», w karcie EN “…”) występuje w kolumnie właściwego języka tabeli, z wartościami w nawiasach kwadratowych. Kryterium przyjęcia: test przechodzi w `python3 -m unittest discover -s tests` bez nowych zależności, a znalezione niezgodności są poprawione w tym samym PR albo opisane w Issue.
2. **Model ruchu mieszanego.** Wejście: `software/reference/obliczenia.py` i wiersz „Ruch mieszany z dyżurnym” w [odbiorze](docs/spec/odbior.md). Wynik: obliczenie czasu nadawania przekaźnika B dla 50 zgłoszeń, 5 rewizji, PRZECZYTANE i jednej decyzji na rewizję oraz jednego komunikatu, zapisane w `wyniki.json`. Obok P1 model ma już wartości dla LoRa SF7 (`lora_pilot` w `wyniki.json`, przybliżenie: 55 rewizji po cyklu z dwoma STATUS, bez komunikatu); dokładne obliczenie ma objąć oba profile. Kryterium przyjęcia: testy modelu przechodzą, `weryfikacja.json` jest odświeżony według [kontroli przed PR](#kontrole-przed-pr), a dokładny wynik z komunikatem zastępuje przybliżenia ruchu mieszanego w odbiorze i rozdziale 06.
3. **Przegląd karty obsługi prostym językiem.** Wejście: [karta](docs/obsluga/karta-stacji.html) w wersji PL, UK lub EN. Wynik: Issue albo PR z poprawkami zdań, które są niejasne dla osoby bez przygotowania technicznego. Kryterium przyjęcia: cytaty z ekranu zmieniają się tylko razem z tabelą tekstów ekranu, krótkie formy mają nadal ≤20 znaków (`tests/test_ui_texts.py`), a każda zmiana ma krótkie uzasadnienie.

### Zadania ze sprzętem i integracją stosu

Pilotaż używa gotowej płytki ESP32-S3 z układem LoRa SX1262 ([profil LoRa](docs/spec/radio.md#profil-lora-pilotażu)). Zadania 1–2 są pierwsze w kolejności prac. Zadania 3–7 dotyczą wariantu zapasowego P1 i stanowisk deweloperskich A/B. Nadal pomagają w próbach stosu (T1–T3), ale nie blokują pilotażu.

1. **Interfejs LoRa w oprogramowaniu stacji.** Dodać do `firmware/` interfejs SX1262 dla stosu: format w eterze zgodny z RNode, po każdym nadaniu cisza 12t, IFAC. Uruchomić go na gotowej płytce ESP32-S3 + SX1262 i wymienić pakiety z implementacją Reticulum w Pythonie przez RNode. To pierwsza część T3 dla pilotażu. W raporcie podaj płytkę, zapas RAM zmierzony poleceniem `RNS` i wynik wymiany.
2. **Etap 0: pomiar tłumienia tras.** Gotowymi urządzeniami LoRa z deklaracją zgodności UE zmierzyć tłumienie na rzeczywistych parach miejsc przy SF7 i SF8, według [planu prób](docs/concept/08-plan-weryfikacji-i-decyzje.html). Nie wymaga własnego sprzętu ani oprogramowania stacji.
3. Wariant zapasowy P1: zmontować płytkę nośną N1, uruchomić obraz `bench-n1` albo `bench-b` według [uruchomienia](hardware/dev-bench/uruchomienie.md) i zgłosić raport z kroków A1–A5 albo B1–B4. Kod oprogramowania układowego trafia do `firmware/` (licencja MIT); ramka P1 jest już w `firmware/src/p1frame.cpp`.
4. Wariant zapasowy P1: uruchomić obraz ze stosem na płytkach rozwojowych nRF52840 i ESP32-S3 i wymienić pakiety z implementacją Reticulum w Pythonie przez łącze P1; na komputerze ta wymiana już przechodzi z emulatorem łącza ([próba zgodności](firmware/README.md#próba-zgodności-z-reticulum)). W raporcie podaj zapas RAM zmierzony poleceniem `RNS` i listę prób na sprzęcie z tej sekcji.
5. Rozszerzyć emulator łącza P1 programu `host` (`firmware/src/host/node_host.cpp`: czas TX z modelu ramki, dług ciszy 12×; kolejka do 4 datagramów jest w interfejsie P1) o CCA, odroczenia i kolizje między kilkoma węzłami ([radio.md](docs/spec/radio.md)).
6. Dodać do modelu protokół USB laptop–stacja (D17) i dziennik FRAM z długiem ciszy.
7. Wariant zapasowy P1: zbudować [stanowisko deweloperskie](hardware/dev-bench/README.md) A lub B z kupnych płytek i wykonać na nim pierwsze pomiary P1 poleceniami pomiarowymi z [radio.md](docs/spec/radio.md); wynik służy do porównania z LoRa.

Przed pracą otwórz Issue lub skomentuj istniejące, żeby nie dublować pracy.

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

Każdy commit w PR kończy się wierszem `Signed-off-by: Imię Nazwisko <email>` (`git commit -s`). Oznacza on zgodę na [Developer Certificate of Origin 1.1](https://developercertificate.org/): masz prawo przesłać ten materiał na licencji właściwej dla ścieżki (w `firmware/lib/reticulum_core/` to [licencja Reticulum](LICENSES/LicenseRef-Reticulum.txt), która nie jest licencją open source w rozumieniu OSI; podpis odnosi się do niej). Nie wymagamy CLA ani przeniesienia praw autorskich. CI sprawdza podpis w każdym commicie PR poza commitami scalającymi (`tools/check_dco.py`). Brakujący podpis dodaj poleceniem `git rebase --signoff <gałąź bazowa>` i ponownie wypchnij gałąź.

Nie dodawaj kluczy, danych mieszkańców, kopii prywatnych rozmów ani materiałów producenta bez uprawnień do dystrybucji. Lokalny `reference-private/` nie należy do wydania. Dla nowej biblioteki lub footprintu zapisz źródło, wersję, modyfikacje i licencję.

Jeżeli korzystasz z narzędzi AI, napisz o tym w opisie PR i sprawdź wynik tak, jakby był Twój: odpowiadasz za każdy wiersz.

## Podpisy kluczem i scalanie

`Signed-off-by` (DCO) jest deklaracją, nie dowodem tożsamości. Commity na gałęzi `main` są dodatkowo podpisane kryptograficznie:

- PR scala się wyłącznie przez „Squash and merge”; inne sposoby scalania są w repozytorium wyłączone. GitHub tworzy wtedy jeden commit podpisany swoim kluczem (znacznik „Verified”), więc commity w PR nie muszą mieć podpisu kluczem; podpis DCO jest w nich wymagany.
- Reguła repozytorium dla `main` przyjmuje tylko podpisane commity i nie ma wyjątków, także dla administratorów. Niepodpisany commit trafia na `main` wyłącznie przez PR.
- Opiekun repozytorium podpisuje swoje commity kluczem SSH albo GPG zapisanym w GitHubie jako klucz podpisujący. Kontrybutorom to zalecamy, ale nie wymagamy.
- Zmiany przygotowane przez narzędzia AI w chmurze (np. Claude Code) nie mają podpisu kluczem, bo środowisko nie ma klucza autora. Trafiają do repozytorium przez PR, a podpis DCO składa autor, który zlecił zmianę i za nią odpowiada.

Podpisywanie kluczem SSH (Git 2.34 lub nowszy):

```sh
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git log --show-signature -1   # sprawdzenie; GitHub pokazuje „Verified”, gdy klucz jest dodany jako signing key
```

## Decyzje i przeglądy

Na razie projekt ma jednego opiekuna repozytorium ([@tmierzwa](https://github.com/tmierzwa)); poza GitHubem kontakt: [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl). Opiekun repozytorium scala PR, zamyka decyzje D01–D20 z [planu weryfikacji](docs/concept/08-plan-weryfikacji-i-decyzje.html) i wydaje wersje. Decyzja zapada w Issue lub PR, z uzasadnieniem i dowodem wymaganym w tabeli decyzji; zmiana decyzji wymaga nowego dowodu, nie samej dyskusji.

Zmiany krytyczne dla bezpieczeństwa ludzi (przetwornica 230 V i ochrona PE, ochrona portów telefonów przed przepięciem, zabezpieczenia akumulatorów, budżet czasu nadawania) wymagają, oprócz opiekuna repozytorium, przeglądu przez osobę z odpowiednimi kwalifikacjami. Dopóki taka osoba nie dołączy do projektu, te części pozostają opisem do prób i mają status HOLD.

Główna gałąź jest chroniona regułą repozytorium bez wyjątków, także dla administratorów: każda zmiana, w tym odświeżenie `manifest.json` przez opiekuna, trafia na `main` przez PR scalany „Squash and merge” po przejściu kontroli `publication` i `dco`. Historia jest liniowa, commity są podpisane, a gałęzi nie można nadpisać ani usunąć. Na `main` i w PR kontrola pomija sumy `manifest.json`, które opiekun odświeża osobnym PR po scaleniu. Pełna kontrola manifestu i paczka źródłowa powstają dopiero przy tagu `v*`. Akcje GitHub muszą pochodzić od GitHuba i być przypięte do SHA; Dependabot raz w miesiącu proponuje ich aktualizację. Skanowanie sekretów odrzuca push z rozpoznanym kluczem. Wydania mają tagi `v*` i paczkę źródłową z pełną kontrolą manifestu. Reguła repozytorium nie pozwala przesunąć ani usunąć tagu `v*`, także administratorom; poprawka wydania dostaje nowy numer, np. `v0.5.1`.

## Licencje

Wkład pozostaje pod licencją właściwą dla ścieżki w [LICENSE.md](LICENSE.md): kod MIT, konstrukcja CERN-OHL-P-2.0, dokumentacja CC-BY-4.0. Projekt jest otwarty; licencje dopuszczają zastosowania komercyjne. Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md); podatności zgłaszaj według [SECURITY.md](SECURITY.md).

## In English

Contributions in English are welcome; documentation stays in Polish, and maintainers will help with translation. Contact outside GitHub: [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl). In short:

- Open an issue for larger changes; small fixes can go straight to a pull request.
- Run the three checks above with `--pull-request`. **Do not refresh `manifest.json`**; the maintainer does it after merging. Refresh only the evidence your change affects (calculation results, hardware evidence).
- Sign off every commit (`git commit -s`, [DCO 1.1](https://developercertificate.org/)); CI rejects unsigned commits (`tools/check_dco.py`). No CLA.
- Pull requests are merged with "Squash and merge" only, so `main` gets a commit signed by GitHub; `main` accepts signed commits only and no direct pushes, maintainers included. Signing your own commits with an SSH or GPG key is recommended, not required.
- Keep assumptions separate from measurements; never mark an unperformed test as passed.
- Safety-critical parts (230 V inverter, phone over-voltage protection, batteries, transmit budget) need review by a qualified person and stay on HOLD until then.
- Disclose AI assistance in the PR; you are responsible for every line.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="media/logo/WICI-na-ciemnym.svg"><img src="media/logo/WICI-na-jasnym.svg" alt="WICI" width="320"></picture></p>

<h1 align="center">Łączność awaryjna, gdy milkną telefony</h1>

Gdy nie ma prądu, zasięgu komórkowego ani internetu, ludzie w schronieniu nadal muszą dać znać, że brakuje wody, ktoś potrzebuje lekarza albo trzeba kogoś przewieźć. **WICI to otwarty projekt stacji radiowej do takich krótkich zgłoszeń i odpowiedzi.** Stacje mają stać tam, gdzie w kryzysie gromadzą się ludzie, i łączyć się ze stanowiskiem odbiorczym, które wyznacza gmina.

Gospodarz schronienia wybiera na ekranie stacji kategorię potrzeby i liczbę osób, a stacja wysyła zgłoszenie radiem. Na ekranie widać potem, czy odbiorca zgłoszenie zapisał, czy dyżurny je przeczytał i czy zapadła decyzja o pomocy. Każda włączona stacja przekazuje też wiadomości sąsiednich stacji, więc zgłoszenia docierają dalej niż zasięg jednego radia.

<p align="center"><img src="hardware/obudowa/render/stacja-materialy-web.jpg" alt="Wizualizacja koncepcyjna stacji WICI: obudowa naścienna z ekranem, czterema przyciskami, diodą alarmu, przełącznikiem CISZA z osłoną i wyłącznikiem; przewody 12 V i anteny wychodzą dołem" width="820"></p>
<p align="center"><sub>Wizualizacja koncepcyjna stacji według dzisiejszych założeń; <a href="hardware/obudowa/README.md">obudowa i render</a>, <a href="hardware/obudowa/render/stacja-materialy.png">pełna rozdzielczość</a>.</sub></p>

Stację można wypróbować w przeglądarce. [Symulator](https://wici.net.pl/symulator/) uruchamia ten sam program, który ma działać w prawdziwej stacji, razem z ćwiczeniami dla gospodarza i stanowiskiem odbiorczym. Uwagi można zgłosić przyciskiem „Zgłoś uwagę” w symulatorze albo [formularzem](https://github.com/tmierzwa/WICI/issues/new?template=uwaga-symulator.yml).

**Projekt jest na etapie prototypu (wersja 0.5). Dwa prototypy stacji są w montażu, a żadnej stacji nie sprawdzono jeszcze w terenie.** Dokumentacja, obliczenia i kod są otwarte. Pełny opis pomysłu, scenariuszy i ograniczeń jest na stronie [wici.net.pl](https://wici.net.pl/).

## Jak to ma działać

Stacja ma ekran, przyciski, antenę i ogniwa AA. Na ogniwach ma pracować co najmniej 48 godzin, a ze źródła 12 V dłużej. Zasięg i czas pracy trzeba jeszcze potwierdzić pomiarami.

W schronieniu stacja działa sama, bez komputera. Później będzie można podłączyć do niej laptop z wygodniejszym panelem, a przez router Wi-Fi udostępnić mieszkańcom lokalną stronę do zgłoszeń z telefonu, bez instalowania aplikacji. Na stanowisku odbiorczym komputer jest obowiązkowy: dyżurny przyjmuje na nim zgłoszenia i przekazuje je służbom.

Sieć trzeba przygotować z gminą i służbami przed kryzysem: zamontować anteny, sprawdzić trasy radiowe i uzgodnić dyżury. WICI ma uzupełniać lokalny system ochrony ludności. Nie zastępuje numeru 112 ani organizacji pomocy.

Pilotaż ma się odbyć na stacjach z ESP32-S3 i radiem LoRa SX1262, w profilu LoRa SF7 na kanale 869,525 MHz. Własny profil radiowy P1 (układy CC1120 i S2-LP), stanowiska deweloperskie i projekt własnej płytki R02 wstrzymano 8 października 2026 r. (F99); opisuje je [archiwum](docs/archiwum/README.md).

## Gdzie jesteśmy

Stan na 29 października 2026 r. Plan ma osiem kroków, a każdy ma warunek wejścia i wynik ([kolejność prac](docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)).

- **Krok 1, radia testowe: wykonany.** Dwa gotowe zestawy Seeed 102010611 (XIAO ESP32-S3 z Wio SX1262) wymieniły przy stole 100 ze 100 ramek w obie strony. W budynku, przy mocy 0 dBm, trasa około 20 m przez dwie ściany też dała 100/100, a dwie trudniejsze trasy były na granicy zasięgu tego profilu ([wyniki](hardware/radio-pair/evidence/range-r0-2026-10-10.txt)). Zestawy są wolne i nie są dalej narzędziem planu.
- **Krok 2, radia RNode: sprzęt zamówiony.** 29 października autor zamówił dwa zestawy RAK19007 z RAK4631 (nRF52840 i SX1262). Dostaną oficjalny firmware RNode ([radia RNode](hardware/rnode/README.md)) i posłużą z Reticulum w Pythonie na dwóch laptopach: do wymiany pakietów przy stole (krok 2), do pomiaru zasięgu (kroki 3 i 5) i do sprawdzenia zgodności prototypu (krok 4). Opcję RAK4631 w narzędziu `rnodeconf` autor RNode oznaczył jako eksperymentalną. Wersję pasma (868 MHz) sprawdzi się przy odbiorze.
- **Krok 4, prototyp na płytce v1: w montażu.** Pięć płytek v1 (dawniej N1) z JLCPCB, części, panele i moduły autor kupił sam ([zamówienie](hardware/dev-bench/przed-produkcja.md#zamówienie-2026-10-10-l0)). Dwie płytki z zamontowanym SMD są u wykonawcy, [pw-lab.pl](https://pw-lab.pl/), który montuje i uruchamia je według [zlecenia](hardware/l0-diagnostic/ZLECENIE.md) i [instrukcji z diagnozą usterek](hardware/l0-diagnostic/MONTAZ-I-TESTY.md); trzy płytki są gołe. Najpierw powstanie jeden prototyp z programem diagnostycznym `l0-0.5`, drugi dopiero po udanym uruchomieniu pierwszego. Montaż pierwszego zaczął się 27 października i pokazał, że taśma panelu nie mieści się w obrysie płytki (F118). Panel mocuje się poza obrysem. Poprawiony projekt v1.1 jest na `main`; nie jest do zamówienia, bo służy jako baza dla v2.
- **Program stacji.** Obrazy stacji mają własny rdzeń Reticulum z LXMF ([opis](firmware/reticulum-core.md)). Rdzeń jest domyślny, a port microReticulum zostaje w osobnych obrazach `*-port` do etapu rdzenia 6-5, który go usunie. Sprawdzono go na komputerze (zgodność z Reticulum i LXMF w Pythonie, fuzzing), ale nie na płytce. Próby 1–8 na płytkach są warunkiem pilotażu i wydania, ale nie scalania zmian. Obraz `l0` (`l0-0.6`, z portem `l0-port`, `l0-0.7`) ma własny sterownik SX1262 w profilu LoRa pilotażu, polecenia pomiarowe i tryb pracy do badań EMC ([opis](firmware/README.md#stacja-l0-l0)); na płytce jeszcze nie działał. Interfejs LoRa w stosie Reticulum, zgodny z radiem RNode, przechodzi próby na komputerze z `RNodeInterface` przez emulator radia ([zgłoszenie 22](https://github.com/tmierzwa/WICI/issues/22)); próba z radiem RNode na prototypie jest w kroku 4. Brakuje funkcji potrzebnych przed pierwszymi stacjami w terenie ([zgłoszenie 23](https://github.com/tmierzwa/WICI/issues/23)).
- **Kroki 5–8.** Stacje pilotażowe powstaną na płytce v2 z linii prototypu (ESP32-S3-DevKitC, Wio SX1262, panel Sharp, FRAM, przyciski) z dodanym torem zasilania z ogniw AA i z 12 V: osiem stacji zamawianych w pełni zmontowanych w JLC, z modułami, obudową i anteną poza zamówieniem. Przed pracą w terenie zespół bada je według norm zharmonizowanych (D20). Projekt v2 zaczyna się po kroku 4. Pomiar w gminie (krok 5) wymaga gminy pilotażowej i wskazanych budynków. Pilotaż trwa co najmniej 3 miesiące, w tym zimę. O wyrobie, czyli stacji WICI, decyduje się po pilotażu.

Zakres prototypu (przygotowany do wyceny, dziś podstawa zlecenia montażu) i zasady wyboru dokumentów opisują [dokumenty przygotowania testów](output/README.md). Instrukcje bieżących prób są w katalogu [hardware](hardware/README.md).

### Kolejność prac

| Krok | Co | Stan |
|---|---|---|
| 1. Radia testowe | wstępna próba radia | wykonany |
| 2. Radia RNode przy stole | RNode na dwóch RAK4631, Reticulum na laptopach, `rnprobe` | czeka na zestawy |
| 3. Pomiar ogólny | zasięg na własnym terenie, SF7 i SF8, 13 dBm | po kroku 2 |
| 4. Prototyp na płytce v1 | odbiór, program stacji, interfejs LoRa, zgodność z RNode, próby 1–8 rdzenia | w montażu |
| 5. Pomiar w gminie | trzy połączenia, dzień i wieczór | wymaga gminy i kroku 3 |
| 6. Stacje pilotażowe na płytce v2 | projekt v2, 8 stacji, badania zgodności | po kroku 4 |
| 7. Pilotaż | ćwiczenie przy stole, potem ≥3 miesiące pracy | po kroku 6 |
| 8. Wyrób | stacja WICI | decyzja po pilotażu |

Kroki 3 i 4 idą równolegle. Do gminy nie jedzie się z niesprawdzonym sprzętem, więc gmina wchodzi w kroku 5. Pełny opis, z warunkami wejścia i wynikami, jest w [rozdziale 08 koncepcji](docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac).

## Partnerzy projektu

- [pw-lab.pl](https://pw-lab.pl/): montaż, testy oraz diagnoza usterek prototypu stacji.

Firmy, gminy i organizacje, które chcą pomóc sprzętem, próbami albo wiedzą, mogą pisać na [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl).

## Jak możesz pomóc

Najbliższy cel to radia RNode przy stole i pomiar zasięgu, a równolegle odbiór prototypu i pierwsza wymiana zgłoszeń z radiem RNode. Potem próby w prawdziwych miejscach. Przyda się doświadczenie w radiu i antenach, w programowaniu ESP32-S3 i SX1262 oraz w organizacji pomocy w gminie.

Można też pomóc bez sprzętu: sprawdzić obliczenia zasięgu, energii i ruchu radiowego, uprościć kartę obsługi albo poprawić tłumaczenia, zwłaszcza ukraińskie.

Konkretne zadania opisuje [CONTRIBUTING.md](CONTRIBUTING.md#od-czego-zacząć). Jeśli chcesz podjąć któreś z nich albo zgłosić błąd, otwórz [zgłoszenie (Issue)](https://github.com/tmierzwa/WICI/issues). Drobne poprawki możesz od razu przesłać jako PR.

## Co jest w repozytorium

| Katalog | Zawartość |
|---|---|
| [docs/concept](docs/concept/index.html) | Koncepcja: potrzeby, scenariusze, dostępne rozwiązania, architektura, wykonalność, zagrożenia, plan prób i otwarte decyzje; [strona online](https://wici.net.pl/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji, warunki odbioru i lista części |
| [firmware](firmware/README.md) | Program stacji ze stosem Reticulum (własny rdzeń z LXMF) dla prototypu (`l0`: ESP32-S3-DevKitC-1 + Wio-SX1262 na płytce v1, profil LoRa); obrazy `bench-*` wstrzymanego wariantu (stanowiska deweloperskie, profil P1) i obrazy `*-port` z portem microReticulum; skompilowane, jeszcze nie uruchomione na sprzęcie |
| [software/reference](software/reference/README.md) | Model wiadomości i potwierdzeń z testami; obliczenia zasięgu, energii i czasu nadawania |
| [software/laptop](software/laptop/README.md) | Aplikacja laptopa z pamięci USB (Windows, macOS, Linux): przygotowanie stacji przez USB (etap 1) i zaszyfrowana baza (etap 2, warstwa bazy); [plan](software/laptop/PLAN.md) kolejnych etapów |
| [software/simulator](software/simulator/README.md) | Symulator stacji w przeglądarce: obraz bench-b oprogramowania stacji (te same źródła i flagi) na wirtualnej płytce ESP32-S3 z emulacją S2-LP, FRAM i Sharp, węzeł i stanowisko odbiorcze, panel płytki v1 (dawniej N1) i dawnej płytki R02 w skali, ćwiczenia gospodarza; [online](https://wici.net.pl/symulator/) |
| [hardware](hardware/README.md) | Radia testowe (`radio-pair`), program diagnostyczny prototypu (`l0-diagnostic`), płytka v1 prototypu (`dev-bench`), obudowa oraz projekt R02 (wstrzymany; materiał do płytki v2 i do wyrobu) |
| [media/film](media/film/README.md) | Dwa filmy o projekcie: około 4,5 min i 60 s |
| [media/infografika](media/infografika/README.md) | Infografika do mediów społecznościowych: post i Stories (PL, EN) |
| [media/logo](media/logo/README.md) | Znak WICI i ikony |
| [tools](docs/development.md) | Kontrola repozytorium i tworzenie paczki źródłowej |

Do sprawdzenia repozytorium wystarczy Python 3.12 lub nowszy:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

W zgłoszeniu zmiany (PR) użyj `python3 tools/verify_repository.py --pull-request` ([szczegóły](CONTRIBUTING.md#kontrole-przed-pr)). Środowisko CAD opisuje [docs/development.md](docs/development.md).

## Kto za tym stoi

Projekt prowadzi na razie jedna osoba: [@tmierzwa](https://github.com/tmierzwa). Gminy, służby, krótkofalowcy i media mogą pisać na [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl). Sprawy techniczne najlepiej zgłaszać w [Issues](https://github.com/tmierzwa/WICI/issues).

Duża część analiz, obliczeń i dokumentacji powstała z pomocą asystenta AI (Claude). Takie commity mają wiersz `Co-Authored-By`. Autor przegląda każdą zmianę. Obliczenia i założenia prawne czekają na niezależny przegląd, a wyniki modelu trzeba potwierdzić pomiarami.

## Licencje

Projekt jest otwarty, a licencje dopuszczają zastosowania komercyjne. Kod jest na licencji MIT, konstrukcja na CERN-OHL-P-2.0, a dokumentacja na CC-BY-4.0.

Wyjątkiem jest rdzeń Reticulum stacji (`firmware/lib/reticulum_core/`). Jako utwór zależny od Reticulum jest na [licencji Reticulum](LICENSES/LicenseRef-Reticulum.txt). Ta licencja dodaje do warunków MIT zakaz użycia w systemach, których funkcją jest celowe szkodzenie ludziom, i zakaz użycia przy tworzeniu zbiorów do trenowania AI, więc nie jest licencją open source w rozumieniu OSI. Obraz stacji z rdzeniem podlega jej jako całość.

Szczegóły są w [LICENSE.md](LICENSE.md). Podatności zgłaszaj prywatnie według [SECURITY.md](SECURITY.md). Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md).

## In English

WICI is an open project for an emergency radio station for shelters in Poland. It is meant to carry short requests for help when power, mobile networks and the internet are down. A station with a screen, buttons and AA cells would send requests, show acknowledgements and decisions, and relay neighbouring stations' messages. The receiving post needs a computer and an agreed procedure for passing requests to emergency services.

The project is at the **prototype stage (0.5)**: two prototypes are being assembled by a contractor, and no station has been field-tested. The plan has eight steps. Two RNode radios (RAK4631) were ordered on 29 October 2026 for bench tests and range measurements with Reticulum on two laptops; next come the prototype on the v1 board, a measurement in a municipality, eight pilot stations on a v2 board (ESP32-S3 module with an SX1262 LoRa radio) and a pilot of at least three months, including winter. The project's own FSK profile and custom board were put on hold on 8 October 2026. Range and battery life remain to be measured. Code, hardware and documentation are under permissive licences; the station's Reticulum core is under the Reticulum License, which is not OSI open source (see [LICENSE.md](LICENSE.md)).

One person currently maintains the project with AI assistance. Project partner: [pw-lab.pl](https://pw-lab.pl/), assembly, testing and fault diagnosis of the station prototype. Help with radio, firmware, civil protection, field testing and independent review is welcome. Documentation is in Polish; issues and pull requests in English are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english). Contact: [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl).

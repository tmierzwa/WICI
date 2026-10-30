<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="media/logo/WICI-na-ciemnym.svg"><img src="media/logo/WICI-na-jasnym.svg" alt="WICI" width="320"></picture></p>

<h1 align="center">Łączność awaryjna, gdy milkną telefony</h1>

Gdy nie ma prądu, zasięgu komórkowego ani internetu, ludzie w schronieniu nadal muszą dać znać, że brakuje wody, ktoś potrzebuje lekarza albo trzeba kogoś przewieźć. **WICI to otwarty projekt stacji radiowej do takich krótkich zgłoszeń i odpowiedzi.** Stacje mają stać tam, gdzie w kryzysie gromadzą się ludzie, i łączyć się ze stanowiskiem odbiorczym, które wyznacza gmina.

Gospodarz schronienia wybiera na ekranie stacji kategorię potrzeby i liczbę osób, a stacja wysyła zgłoszenie radiem. Na ekranie widać potem, czy odbiorca zgłoszenie zapisał, czy dyżurny je przeczytał i czy zapadła decyzja o pomocy. Każda włączona stacja przekazuje też wiadomości sąsiednich stacji, więc zgłoszenia docierają dalej niż zasięg jednego radia.

<p align="center"><img src="hardware/obudowa/render/stacja-materialy-web.jpg" alt="Wizualizacja koncepcyjna stacji WICI: obudowa naścienna z ekranem, czterema przyciskami, diodą alarmu, przełącznikiem CISZA z osłoną i wyłącznikiem; przewody 12 V i anteny wychodzą dołem" width="820"></p>
<p align="center"><sub>Wizualizacja koncepcyjna stacji według dzisiejszych założeń; <a href="hardware/obudowa/README.md">obudowa i render</a>, <a href="hardware/obudowa/render/stacja-materialy.png">pełna rozdzielczość</a>.</sub></p>

Stację można wypróbować w przeglądarce. [Symulator](https://wici.net.pl/symulator/) uruchamia ten sam program, który ma działać w prawdziwej stacji, razem z ćwiczeniami dla gospodarza i stanowiskiem odbiorczym. Uwagi można zgłosić przyciskiem „Zgłoś uwagę” w symulatorze albo [formularzem](https://github.com/tmierzwa/WICI/issues/new?template=uwaga-symulator.yml).

**Projekt jest na etapie prototypu (wersja 0.5). Żadnej stacji jeszcze nie zbudowano ani nie sprawdzono w terenie.** Dokumentacja, obliczenia i kod są otwarte. Pełny opis pomysłu, scenariuszy i ograniczeń jest na stronie [wici.net.pl](https://wici.net.pl/).

## Jak to ma działać

Stacja ma ekran, przyciski, antenę i ogniwa AA. Na ogniwach ma pracować co najmniej 48 godzin, a ze źródła 12 V dłużej. Zasięg i czas pracy trzeba jeszcze potwierdzić pomiarami.

W schronieniu stacja działa sama, bez komputera. Później będzie można podłączyć do niej laptop z wygodniejszym panelem, a przez router Wi-Fi udostępnić mieszkańcom lokalną stronę do zgłoszeń z telefonu, bez instalowania aplikacji. Na stanowisku odbiorczym komputer jest obowiązkowy: dyżurny przyjmuje na nim zgłoszenia i przekazuje je służbom.

Sieć trzeba przygotować z gminą i służbami przed kryzysem: zamontować anteny, sprawdzić trasy radiowe i uzgodnić dyżury. WICI ma uzupełniać lokalny system ochrony ludności. Nie zastępuje numeru 112 ani organizacji pomocy.

Pilotaż ma się odbyć na gotowych płytkach ESP32-S3 z radiem LoRa SX1262, w profilu LoRa SF7 na kanale 869,525 MHz. Własny profil radiowy P1 (układy CC1120 i S2-LP) zostaje wariantem zapasowym, a projekt własnej płytki stacji R02 czeka na decyzje po pilotażu.

## Gdzie jesteśmy

Stan na 24 października 2026 r.:

- **Para radiowa R0.** Dwa gotowe zestawy Seeed 102010611 wymieniły przy stole 100 ze 100 ramek w obie strony. W budynku, przy mocy 0 dBm, trasa około 20 m przez dwie ściany też dała 100/100, a dwie trudniejsze trasy były na granicy zasięgu tego profilu ([wyniki](hardware/radio-pair/evidence/range-r0-2026-10-10.txt)). Następne są próby w terenie.
- **Prototyp L0.** Płytki N1 z JLCPCB, części, panele i moduły na dwa prototypy autor kupił sam ([zamówienie](hardware/dev-bench/przed-produkcja.md#zamówienie-2026-10-10-l0)). Dotarły i czekają na montaż. Montuje je i uruchamia [pw-lab.pl](https://pw-lab.pl/) według [zlecenia](hardware/l0-diagnostic/ZLECENIE.md) i [instrukcji z diagnozą usterek](hardware/l0-diagnostic/MONTAZ-I-TESTY.md). Najpierw powstanie jeden L0 z programem diagnostycznym `l0-0.5`, a drugi dopiero po udanym uruchomieniu pierwszego.
- **Oprogramowanie stacji.** Obraz `l0` (`l0-0.3`) ma własny sterownik SX1262 w profilu LoRa pilotażu, polecenia pomiarowe i tryb pracy do badań EMC ([opis](firmware/README.md#stacja-l0-l0), [etap 1](https://github.com/tmierzwa/WICI/issues/21)). Przechodzi testy na komputerze z modelem układu, ale na płytce jeszcze nie działał. Do zrobienia są interfejs LoRa w stosie Reticulum ([etap 2](https://github.com/tmierzwa/WICI/issues/22)) i funkcje potrzebne przed pierwszymi stacjami w terenie ([etap 3](https://github.com/tmierzwa/WICI/issues/23)).
- **Rdzeń Reticulum.** Od 22 października powstaje [własny rdzeń Reticulum stacji](firmware/reticulum-core.md) z LXMF. Jego etapy R0–R5 przechodzą na komputerze próby zgodności z Reticulum i LXMF w Pythonie. Od etapów R6-3 i R6-4 rdzeń zastępuje port microReticulum we wszystkich obrazach stacji. Port zostaje w osobnych obrazach `*-port` do etapu R6-5, który go usunie. Obrazów z rdzeniem nie uruchomiono jeszcze na płytce.
- **Płytka stacji pilotażowej.** Z [czterech porównanych kandydatów](docs/archiwum/elektronika-r02.md#porównanie-kandydatów) najlepiej wypada RAK3312 na płytce bazowej RAK19007. Do podłączenia elementów stacji potrzebny jest przy niej ekspander wyprowadzeń. Żaden kandydat nie ma jeszcze podpisanej deklaracji zgodności UE producenta ([dokumenty](docs/archiwum/elektronika-r02.md#dokumenty-zgodności-kandydatów)). 21 października wysłano do RAK zapytanie o deklarację dla RAK3312 i RAK19007, raporty z badań radiowych i stanowisko wobec EN 18031. Płytka zostanie wybrana po próbach na dwóch L0.

Zakres prototypu L0 (przygotowany do wyceny, dziś podstawa zlecenia montażu) i zasady wyboru dokumentów opisują [dokumenty przygotowania testów](output/README.md). Instrukcje bieżących prób są w katalogu [hardware](hardware/README.md).

Przed pilotażem zostają: montaż i próby L0, interfejs LoRa w stosie, próby rdzenia na płytkach i usunięcie portu (R6-5), aplikacja stanowiska odbiorczego oraz próby sprzętu i obsługi. Trzeba też ustalić, co obejmują deklaracje zgodności UE kupionych płytek i na jakich warunkach można prowadzić próby w terenie.

### Kolejność prac

Po przeglądzie z 8 października 2026 r. przyjęto taką [kolejność prac](docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac):

1. Etap 0: pomiar tłumienia tras gotowymi urządzeniami 868 MHz (w tym LoRa SF7 i SF8) oraz ćwiczenie przy stole z gminą i odbiorcą, bez własnego sprzętu.
2. Stacja na gotowej płytce ESP32-S3 z układem LoRa SX1262: interfejs radiowy, Reticulum i LXMF, trwała kolejka w pamięci FRAM, ekran i przyciski.
3. Aplikacja stanowiska z Reticulum i LXMF w Pythonie.
4. Pilotaż: 6–8 stacji pilotażowych w 3 miejscach, przez co najmniej 3 miesiące, w tym zimą.
5. Po pilotażu: decyzje o własnej płytce R02, drugim wykonaniu, ocenie zgodności, poziomach 2–3 (laptop, router) i szyfrowaniu FRAM.

## Partnerzy projektu

- [pw-lab.pl](https://pw-lab.pl/): montaż, testy oraz diagnoza usterek prototypu stacji.

Firmy, gminy i organizacje, które chcą pomóc sprzętem, próbami albo wiedzą, mogą pisać na [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl).

## Jak możesz pomóc

Najbliższy cel to pierwsza wymiana zgłoszeń między stacjami a stanowiskiem odbiorczym, a potem próby w prawdziwych miejscach. Przyda się doświadczenie w radiu i antenach, w programowaniu ESP32-S3 i SX1262 oraz w organizacji pomocy w gminie.

Można też pomóc bez sprzętu: sprawdzić obliczenia zasięgu, energii i ruchu radiowego, uprościć kartę obsługi albo poprawić tłumaczenia, zwłaszcza ukraińskie.

Konkretne zadania opisuje [CONTRIBUTING.md](CONTRIBUTING.md#od-czego-zacząć). Jeśli chcesz podjąć któreś z nich albo zgłosić błąd, otwórz [Issue](https://github.com/tmierzwa/WICI/issues). Drobne poprawki możesz od razu przesłać jako PR.

## Co jest w repozytorium

| Katalog | Zawartość |
|---|---|
| [docs/concept](docs/concept/index.html) | Koncepcja: potrzeby, scenariusze, dostępne rozwiązania, architektura, wykonalność, zagrożenia, plan prób i otwarte decyzje; [strona online](https://wici.net.pl/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji, warunki odbioru i lista części |
| [firmware](firmware/README.md) | Oprogramowanie stacji ze stosem Reticulum (własny rdzeń z LXMF) dla stanowisk deweloperskich A (nRF52840-DK + CC1120EM, na przewodach i na N1) i B (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 na N1) oraz dla L0 (ESP32-S3-DevKitC-1 + Wio-SX1262 na N1, profil LoRa); skompilowane, jeszcze nie uruchomione na sprzęcie |
| [software/reference](software/reference/README.md) | Model wiadomości i potwierdzeń z testami; obliczenia zasięgu, energii i czasu nadawania |
| [software/laptop](software/laptop/README.md) | Aplikacja laptopa z pamięci USB (Windows, macOS, Linux): przygotowanie stacji przez USB (etap 1) i zaszyfrowana baza (etap 2, warstwa bazy); [plan](software/laptop/PLAN.md) kolejnych etapów |
| [software/simulator](software/simulator/README.md) | Symulator stacji w przeglądarce: obraz bench-b oprogramowania stacji (te same źródła i flagi) na wirtualnej płytce ESP32-S3 z emulacją S2-LP, FRAM i Sharp, węzeł i stanowisko odbiorcze, panel R02 i N1 w skali, ćwiczenia gospodarza; [online](https://wici.net.pl/symulator/) |
| [hardware](hardware/README.md) | Testy radiowe R0, diagnostyka prototypu L0, projekt płytki nośnej N1 stanowiska deweloperskiego i rozpoczęty projekt płytki stacji R02 (wstrzymany do decyzji po pilotażu) |
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

Projekt prowadzi na razie jedna osoba: [@tmierzwa](https://github.com/tmierzwa). Gminy, służby, krótkofalowcy i media mogą pisać na [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl). Sprawy techniczne najlepiej zgłaszać w Issues.

Duża część analiz, obliczeń i dokumentacji powstała z pomocą asystenta AI (Claude). Takie commity mają wiersz `Co-Authored-By`. Autor przegląda każdą zmianę. Obliczenia i założenia prawne czekają na niezależny przegląd, a wyniki modelu trzeba potwierdzić pomiarami.

## Licencje

Projekt jest otwarty, a licencje dopuszczają zastosowania komercyjne. Kod jest na licencji MIT, konstrukcja na CERN-OHL-P-2.0, a dokumentacja na CC-BY-4.0.

Wyjątkiem jest rdzeń Reticulum stacji (`firmware/lib/reticulum_core/`). Jako utwór zależny od Reticulum jest na [licencji Reticulum](LICENSES/LicenseRef-Reticulum.txt). Ta licencja dodaje do warunków MIT zakaz użycia w systemach, których funkcją jest celowe szkodzenie ludziom, i zakaz użycia przy tworzeniu zbiorów do trenowania AI, więc nie jest licencją open source w rozumieniu OSI. Obraz stacji z rdzeniem podlega jej jako całość.

Szczegóły są w [LICENSE.md](LICENSE.md). Podatności zgłaszaj prywatnie według [SECURITY.md](SECURITY.md). Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md).

## In English

WICI is an open project for an emergency radio station for shelters in Poland. It is meant to carry short requests for help when power, mobile networks and the internet are down. A station with a screen, buttons and AA cells would send requests, show acknowledgements and decisions, and relay neighbouring stations' messages. The receiving post needs a computer and an agreed procedure for passing requests to emergency services.

The project is at the **prototype design stage (0.5)**. No station has been built or field-tested. The planned pilot uses off-the-shelf ESP32-S3 boards with an SX1262 LoRa radio; the custom board and the project's own FSK profile are deferred until after the pilot. Range and battery life remain to be measured. Code, hardware and documentation are under permissive licences; the station's Reticulum core is under the Reticulum License, which is not OSI open source (see [LICENSE.md](LICENSE.md)).

One person currently maintains the project with AI assistance. Project partner: [pw-lab.pl](https://pw-lab.pl/), assembly, testing and fault diagnosis of the station prototype. Help with radio, firmware, civil protection, field testing and independent review is welcome. Documentation is in Polish; issues and pull requests in English are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english). Contact: [kontakt@wici.net.pl](mailto:kontakt@wici.net.pl).

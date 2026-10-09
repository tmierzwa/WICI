<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="media/logo/WICI-na-ciemnym.svg"><img src="media/logo/WICI-na-jasnym.svg" alt="WICI" width="320"></picture></p>

<h1 align="center">Łączność awaryjna, gdy milkną telefony</h1>

Gdy nie ma prądu, zasięgu komórkowego ani internetu, jak przekazać służbom, że w schronieniu brakuje wody, ktoś potrzebuje lekarza albo transportu? **WICI to otwarty projekt stacji radiowej do krótkich zgłoszeń i odpowiedzi.** Sieć ma łączyć miejsca, w których gromadzą się ludzie, ze stanowiskiem odbiorczym wyznaczonym przez gminę.

Opiekun schronienia wybiera na ekranie kategorię potrzeby i liczbę osób, a stacja wysyła zgłoszenie radiem. Ekran ma rozróżniać trwały zapis u odbiorcy, odczyt przez dyżurnego i decyzję o pomocy. Każda włączona stacja ma też przekazywać wiadomości sąsiadów, wydłużając drogę do odbiorcy.

**To projekt prototypu 0.5. Stacji jeszcze nie zbudowano ani nie sprawdzono w terenie.** Dokumentacja, obliczenia i kod są otwarte; poniżej opisujemy plan prac i możliwości współpracy.

Podstawowy zestaw to stacja z ekranem, przyciskami, anteną i ogniwami AA. Cel: co najmniej 48 godzin pracy na ogniwach i dłuższa praca ze źródła 12 V. Pilotaż planujemy na gotowej płytce ESP32-S3 z radiem LoRa SX1262. Zasięg i czas pracy muszą zostać potwierdzone pomiarami.

W schronieniu stacja ma działać samodzielnie. Laptop może później dodać wygodniejszy panel, a router Wi-Fi umożliwi korzystanie z lokalnej strony do zgłoszeń z telefonów, bez instalowania aplikacji. Na stanowisku odbiorczym komputer jest obowiązkowy: dyżurny przyjmuje na nim zgłoszenia i przekazuje je służbom.

Sieć trzeba przygotować razem z gminą i służbami przed kryzysem: zamontować anteny, sprawdzić trasy radiowe i uzgodnić dyżury. WICI ma uzupełniać lokalny system ochrony ludności. Nie zastępuje numeru 112 ani organizacji pomocy.

## Gdzie jesteśmy

Stan przygotowania testów na 9 października 2026 r.:

- **R0:** zamówione dwa zestawy Seeed 102010611 do pierwszego testu pary radiowej; czekamy na dostawę.
- **L0:** zapytanie o wycenę jednego prototypu wysłane do trzech firm; czekamy na oferty. Nie zlecono jeszcze wykonania.
- Programy diagnostyczne R0 i L0 są skompilowane i sprawdzone testami automatycznymi. Próby na rzeczywistym sprzęcie pozostają do wykonania.

Zakres przekazany do wyceny i zasady wyboru dokumentów są w [dokumentach przygotowania testów](output/README.md). Instrukcje bieżących prób opisuje [hardware](hardware/README.md).

W repozytorium są:

- [koncepcja](https://tmierzwa.github.io/WICI/);
- specyfikacja stacji;
- model obliczeniowy z testami;
- projekt płytki nośnej stanowiska deweloperskiego (N1) i rozpoczęty projekt płytki stacji R02 (wstrzymany);
- oprogramowanie stacji skompilowane dla stanowisk deweloperskich A i B, ze stosem Reticulum (bez LXMF); nie uruchomiono go jeszcze na sprzęcie.

Do wykonania pozostają interfejs LoRa, integracja LXMF na stacji, aplikacja stanowiska odbiorczego oraz próby sprzętu i obsługi.

Po przeglądzie z 8 października 2026 r. przyjęliśmy następującą [kolejność prac](docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac):

1. Etap 0: pomiar tłumienia tras gotowymi urządzeniami 868 MHz (w tym LoRa SF7 i SF8) oraz ćwiczenie przy stole z gminą i odbiorcą, bez własnego sprzętu.
2. Stacja na gotowej płytce ESP32-S3 z układem LoRa SX1262: interfejs radiowy, Reticulum i LXMF, trwała kolejka w pamięci FRAM, ekran i przyciski.
3. Aplikacja stanowiska z Reticulum i LXMF w Pythonie.
4. Pilotaż: 6–8 stacji pilotażowych, 3 miejsca, co najmniej 3 miesiące z zimą.
5. Po pilotażu: decyzje o własnej płytce R02, drugim wykonaniu, ocenie zgodności, poziomach 2–3 (laptop, router) i szyfrowaniu FRAM.

Wybrany profil pilotażu to LoRa SF7 na kanale 869,525 MHz. Zakres deklaracji zgodności UE kupionych płytek i warunki prób terenowych trzeba ustalić przed pilotażem. Własny profil P1 (CC1120, S2-LP) zostaje wariantem zapasowym. Projekt płytki R02 jest wstrzymany do decyzji po pilotażu.

## Jak możesz pomóc

Najbliższy cel to pierwsza wymiana zgłoszeń między stacjami i stanowiskiem odbiorczym, a następnie próby w rzeczywistych miejscach. Przydadzą się doświadczenie w radiu i antenach, oprogramowaniu ESP32-S3 i SX1262 oraz organizacji pomocy w gminie.

Można też pomóc bez sprzętu: sprawdzić obliczenia zasięgu, energii i ruchu radiowego albo uprościć kartę obsługi i poprawić tłumaczenia, zwłaszcza ukraińskie.

Konkretne zadania opisuje [CONTRIBUTING.md](CONTRIBUTING.md#od-czego-zacząć). Jeśli chcesz podjąć jedno z nich lub wskazać błąd, otwórz [Issue](https://github.com/tmierzwa/WICI/issues). Drobne poprawki możesz od razu przesłać jako PR.

## Co jest w repozytorium

| Katalog | Zawartość |
|---|---|
| [docs/concept](docs/concept/index.html) | Koncepcja: potrzeby, scenariusze, dostępne rozwiązania, architektura, wykonalność, zagrożenia, plan prób i otwarte decyzje; [strona online](https://tmierzwa.github.io/WICI/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji, warunki odbioru i lista części |
| [firmware](firmware/README.md) | Oprogramowanie stacji dla stanowisk deweloperskich A (nRF52840-DK + CC1120EM, na przewodach i na N1) i B (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 na N1); skompilowane, jeszcze nie uruchomione na sprzęcie |
| [software/reference](software/reference/README.md) | Model wiadomości i potwierdzeń z testami; obliczenia zasięgu, energii i czasu nadawania |
| [hardware](hardware/README.md) | Testy radiowe R0, diagnostyka prototypu L0, projekt nośnej N1 i dokumentacja przyszłej płytki R02 (wstrzymanej do decyzji po pilotażu) |
| [media/film](media/film/README.md) | Dwa filmy o projekcie: około 4,5 min i 60 s |
| [media/infografika](media/infografika/README.md) | Infografika do mediów społecznościowych (PL, EN) |
| [media/logo](media/logo/README.md) | Znak WICI i ikony |
| [tools](docs/development.md) | Kontrola repozytorium i tworzenie paczki źródłowej |

Sprawdzenie repozytorium wymaga tylko Pythona 3.12 lub nowszego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

W zgłoszeniu zmiany (PR) użyj `python3 tools/verify_repository.py --pull-request` ([szczegóły](CONTRIBUTING.md#kontrole-przed-pr)). Środowisko CAD opisuje [docs/development.md](docs/development.md).

## Kto za tym stoi

Na razie projekt prowadzi jedna osoba: [@tmierzwa](https://github.com/tmierzwa). Duża część analiz, obliczeń i dokumentacji powstała z pomocą asystenta AI (Claude); takie commity mają wiersz `Co-Authored-By`.

Autor przegląda każdą zmianę. Obliczenia i założenia prawne czekają na niezależny przegląd; wyniki modelu wymagają potwierdzenia pomiarami.

Projekt jest niekomercyjny i otwarty. Kod jest na licencji MIT, konstrukcja na CERN-OHL-P-2.0, a dokumentacja na CC-BY-4.0. Szczegóły są w [LICENSE.md](LICENSE.md). Podatności zgłaszaj prywatnie według [SECURITY.md](SECURITY.md). Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md).

## In English

WICI is an open-source project for an emergency radio station for shelters in Poland. It is designed to send short requests for help when power, mobile networks and the internet are down. A station with a screen, buttons and AA cells would send requests, show acknowledgements and decisions, and relay neighbouring stations’ messages. The receiving post needs a computer and an agreed procedure for passing requests to emergency services.

The project is at the **prototype design stage (0.5)**. No station has been built or field-tested. The planned pilot uses off-the-shelf ESP32-S3 boards with an SX1262 LoRa radio; the custom board and the project's own FSK profile are deferred until after the pilot. Range and battery life remain to be measured.

One person currently maintains the project with AI assistance. Help with radio, firmware, civil protection, field testing and independent review is welcome. Documentation is in Polish; issues and pull requests in English are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english).

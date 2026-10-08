<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="media/logo/WICI-na-ciemnym.svg"><img src="media/logo/WICI-na-jasnym.svg" alt="WICI" width="320"></picture></p>

<h1 align="center">Łączność awaryjna, gdy milkną telefony</h1>

Gdy przez wiele godzin nie ma prądu, zasięgu komórkowego ani internetu, ludzie w schronieniu nie mają jak powiedzieć służbom, że potrzebują lekarza, wody albo transportu. WICI to otwarty, społeczny projekt prostej stacji radiowej, która pozwala przekazać takie zgłoszenie i dostać odpowiedź.

**Włączam stację, wystawiam antenę i jestem w sieci.** Antenę montuje się wcześniej, a sieć sprawdza w terenie razem ze służbami, zanim przyjdzie kryzys.

- **Sama stacja** to małe pudełko z ekranem, kilkoma przyciskami i bateriami AA. Opiekun schronienia wybiera, czego brakuje i ilu osób to dotyczy, a stacja wysyła krótką wiadomość do stanowiska odbiorczego wyznaczonego przez gminę. Stanowisko przyjmuje zgłoszenia i przekazuje je służbom. Często prowadzi je ochotnicza straż pożarna (OSP); w dokumentach skrót OSP oznacza jednak tylko straż, a nie samo stanowisko. Na ekranie widać, czy zgłoszenie dotarło i czy ktoś je przeczytał.
- **Każda włączona stacja przekazuje dalej wiadomości sąsiadów**, więc sieć sięga dalej niż pojedyncze radio.
- **Później można dołączyć stary laptop**, który daje wygodniejszy panel, oraz **domowy router**: wtedy mieszkańcy zgłaszają potrzeby zwykłą stroną w telefonie, bez instalowania aplikacji.

Stacja nadaje na częstotliwości 869,525 MHz, dostępnej bez pozwolenia radiowego, ma pracować co najmniej dwie doby na bateriach AA i kilka tygodni z akumulatora samochodowego 12 V. WICI nie zastępuje służb ani numeru 112. Ma uzupełniać lokalny system ochrony ludności i być przygotowana razem ze służbami przed kryzysem, a nie w jego trakcie.

## Gdzie jesteśmy

Projekt jest na etapie **projektu prototypu (wersja 0.5)**. Mamy:
- [koncepcję](https://tmierzwa.github.io/WICI/);
- specyfikację stacji;
- model obliczeniowy z testami;
- projekt płytki nośnej stanowiska deweloperskiego (N1) i rozpoczęty projekt płytki stacji R02 (wstrzymany);
- oprogramowanie stacji skompilowane dla stanowisk deweloperskich A i B, ze stosem Reticulum (bez LXMF); nie uruchomiono go jeszcze na sprzęcie.

Nie zbudowaliśmy jeszcze stacji ani nie przeprowadziliśmy prób w terenie, więc to jeszcze nie jest urządzenie do użycia.

Po przeglądzie praktycznym (2026-10-08) zawęziliśmy zakres przed pilotażem ([kolejność prac](docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)):
1. Etap 0: pomiar tłumienia tras gotowymi urządzeniami 868 MHz (w tym LoRa SF7 i SF8) oraz ćwiczenie przy stole z gminą i odbiorcą, bez własnego sprzętu.
2. Oprogramowanie stacji na gotowej płytce ESP32-S3 z układem LoRa SX1262: interfejs LoRa, stos, kolejka FRAM, ekran i przyciski.
3. Aplikacja stanowiska z Reticulum i LXMF w Pythonie.
4. Pilotaż: 6–8 stacji pilotażowych, 3 miejsca, co najmniej 3 miesiące z zimą.
5. Po pilotażu: decyzje o własnej płytce R02, drugim wykonaniu, ocenie zgodności, poziomach 2–3 (laptop, router) i szyfrowaniu FRAM.

Radio pilotażu to LoRa SF7 na gotowych modułach z deklaracją zgodności UE. Własny profil P1 (CC1120, S2-LP) zostaje wariantem zapasowym. Projekt płytki R02 jest wstrzymany do decyzji po pilotażu.

Najważniejsze pytania, na które odpowiedzą dopiero próby:
- Czy sygnał przejdzie 1 km w zabudowie? Model daje dla LoRa SF7 dodatni zapas na 1 km we wszystkich trzech badanych układach anten, a dla P1 ujemny; rozstrzygnie to pomiar w etapie 0.
- Czy oprogramowanie sieci ([Reticulum](https://github.com/markqvist/Reticulum) i [LXMF](https://github.com/markqvist/LXMF)) będzie stabilne w małym mikrokontrolerze? W nRF52840 odtworzenie na komputerze zostawia tylko 4,5% wolnej pamięci RAM w szczycie wobec wymaganych 30% ([pomiar](firmware/README.md#pamięć-ram)), dlatego pilotaż używa ESP32-S3 (512 KiB SRAM).
- Czy stacja rzeczywiście wytrzyma co najmniej dwie doby na bateriach? Dla ESP32-S3 zależy to od zmierzonego prądu mikrokontrolera.

Pełna lista prób jest w [warunkach odbioru](docs/spec/odbior.md), z osobnym [minimum pilotażu](docs/spec/odbior.md#minimum-pilotażu), a otwarte sprawy w [przeglądzie technicznym](docs/review.md).

## Jak możesz pomóc

Szukamy osób, które znają się na:
- **radiu i elektronice:** pomiary tras, anteny, LoRa;
- **oprogramowaniu układowym:** ESP32-S3, SX1262, microReticulum;
- **ochronie ludności i pracy służb:** czy to rozwiązanie pasuje do rzeczywistych procedur;
- **testach w terenie:** łączność radiowa, krótkofalarstwo;
- **prostym języku i tłumaczeniach:** zwłaszcza na ukraiński.

Dobrym początkiem jest lista zadań w [CONTRIBUTING.md](CONTRIBUTING.md#od-czego-zacząć). Uwagi i pytania można zgłaszać w [Issues](https://github.com/tmierzwa/WICI/issues). Każde wskazanie błędu w obliczeniach lub założeniach jest cenne.

## Co jest w repozytorium

| Katalog | Zawartość |
|---|---|
| [docs/concept](docs/concept/index.html) | Koncepcja: potrzeby, scenariusze, dostępne rozwiązania, architektura, wykonalność, zagrożenia, plan prób i otwarte decyzje; [strona online](https://tmierzwa.github.io/WICI/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji, warunki odbioru i lista części |
| [firmware](firmware/README.md) | Oprogramowanie stacji dla stanowisk deweloperskich A (nRF52840-DK + CC1120EM, na przewodach i na N1) i B (ESP32-S3-DevKitC-1 + X-NUCLEO-S2868A2 na N1); skompilowane, jeszcze nie uruchomione na sprzęcie |
| [software/reference](software/reference/README.md) | Model wiadomości i potwierdzeń z testami; obliczenia zasięgu, energii i czasu nadawania |
| [hardware](hardware/r02/README.md) | Projekt płytki stacji R02 (rozpoczęty, wstrzymany do decyzji po pilotażu) i [stanowisko deweloperskie](hardware/dev-bench/README.md) z płytek rozwojowych i płytką nośną N1 |
| [media/film](media/film/README.md) | Dwa filmy o projekcie: około 4,5 min i 60 s |
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

Na razie projekt prowadzi jedna osoba ([@tmierzwa](https://github.com/tmierzwa)) i chętnie przyjmie towarzystwo. Duża część analiz, obliczeń i dokumentacji powstała z pomocą asystenta AI (Claude); takie commity mają wiersz `Co-Authored-By`. Autor przegląda każdą zmianę, ale nikt z zewnątrz jeszcze nie sprawdził obliczeń ani założeń prawnych. Traktuj wyniki jak hipotezy do sprawdzenia.

Projekt jest niekomercyjny i otwarty. Kod jest na licencji MIT, konstrukcja na CERN-OHL-P-2.0, a dokumentacja na CC-BY-4.0. Szczegóły są w [LICENSE.md](LICENSE.md). Podatności zgłaszaj prywatnie według [SECURITY.md](SECURITY.md). Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md).

## In English

WICI is a community, open-source design for an emergency radio station for shelters, for when power, mobile networks and the internet are down. The station is a small box with a screen, buttons and AA cells. It sends short requests for help to emergency services over a licence-free 869.525 MHz radio and relays its neighbours' traffic whenever it is on. A laptop and a Wi-Fi router can be added later for a fuller panel and a web page for residents' phones.

The project is at the **prototype design stage (0.5)**: nothing has been built or field-tested yet. The pilot will use ready ESP32-S3 boards with a LoRa SX1262 radio; the custom board and the own FSK profile wait until after the pilot. It is currently run by one person with AI assistance, and help is very welcome, especially with radio, firmware, civil protection and field testing. Documentation is in Polish; issues and pull requests in English are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english).

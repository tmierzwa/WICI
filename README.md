# WICI: stacja łączności awaryjnej

Niekomercyjny projekt otwartej stacji łączności dla schronienia z około 50 osobami. Podstawą jest samodzielna stacja z ekranem i przyciskami: włączam stację, wystawiam antenę i jestem w sieci. Opiekun wysyła przyciskami krótkie zgłoszenia, które radio przekazuje przez inne stacje do odbiorcy w gminie. Ten odbiorca to centrum zarządzania kryzysowego gminy lub punkt wskazany przez wójta; w dokumentach jego rolę oznacza skrót OSP. Każda włączona stacja przekazuje też ruch innych stacji. W modelu stacja pracuje kilka dni na ogniwach AA, a ze źródła 12 V tygodniami. Znaleziony laptop dodaje wygodny panel, a router stronę, przez którą mieszkańcy zgłaszają potrzeby z telefonów. Telefony są ładowane z osobnego akumulatora. WICI uzupełnia system ochrony ludności. Odbiorcę zgłoszeń, status nadawania w stanach nadzwyczajnych i ochronę danych uzgadnia się z gminą przed użyciem, aby podczas alarmu nic formalnego nie blokowało pracy.

**Stan: projekt prototypu 0.5; kontroler R01.3 (stanowisko laboratoryjne P1): HOLD.** Są specyfikacja stacji, schemat i PCB stanowiska, eksporty i model kontraktów. Nie ma płytki stacji R02, ukończonego modułu RF, oprogramowania układowego, aplikacji ani gotowej pamięci USB. Nie wykonano prób fizycznych. To nie jest wydanie do użycia podczas awarii.

> **Bezpieczeństwo.** Przetwornica 230 V wytwarza napięcie zagrażające życiu, a akumulatory mogą spowodować pożar. Silnik pojazdu lub agregat pracujący w schronieniu, garażu albo przy wlocie powietrza zabija tlenkiem węgla. Opis przetwornicy nie jest instrukcją do samodzielnego wykonania; bez kwalifikacji i badań bezpieczeństwa nie wolno jej budować ani podłączać do ludzi i urządzeń. Projekt nie jest certyfikowanym urządzeniem, a licencje wyłączają wszelką gwarancję.

WICI używa [Reticulum](https://github.com/markqvist/Reticulum) i [LXMF](https://github.com/markqvist/LXMF). Są to odrębne projekty; ich kod nie jest dołączony.

| Katalog | Zawartość |
|---|---|
| [docs/conception](docs/conception/index.html) | Potrzeby i poziomy zestawu, scenariusze, dostępne rozwiązania, analiza opcji, architektura, wykonalność, odporność oraz plan prób i otwarte decyzje D01–D17; [strona online](https://tmierzwa.github.io/WICI/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji w pięciu rozdziałach, warunki odbioru i BOM stacji |
| [hardware](hardware/radio-test-r01/README.md) | Kontroler R01.3 w KiCad jako stanowisko laboratoryjne P1: BOM, raporty i paczka kandydata |
| [software/reference](software/reference/README.md) | Model ramek, wiadomości i transakcji OSP; obliczenia |
| [media/film](media/film/README.md) | Film o projekcie: 4 min oraz 60 s w pionie na Reels i TikTok; animacje i narracja do odtworzenia |
| [tools](docs/development.md) | Kontrola repozytorium i tworzenie paczki źródłowej |

[Przegląd techniczny](docs/review.md) wskazuje m.in. niesprawdzoną dojrzałość stosu Reticulum na mikrokontrolerze, ujemny zapas łącza przy niskich antenach i niezamkniętą zgodność czasów Reticulum/LXMF z P1.

Cel 1 km w zabudowie, ≥48 h przekaźnika na ogniwach AA, 24 godziny pełnego zestawu z wymianą źródeł 12 V i zgodność dwóch dostawców radia wymagają prób. Model Okumury-Haty daje przy antenach na wysokości okien ujemny zapas łącza na 1 km w mieście (od −0,7 do −7,3 dB, jeszcze bez zapasu na zaniki); sieć planuje się z wysoko umieszczonymi antenami i przekaźnikami. Kanał 869,525 MHz jest współdzielony z LoRaWAN i Meshtastic, więc wybór kanału zależy od pomiaru w miejscach pilotażu. Przed przekazaniem zestawu innym gotowa konfiguracja wymaga oceny zgodności z dyrektywą RED. Przetwornica 230 V i ładowarka są opisami konstrukcyjnymi; nie mają odebranych PCB. [Lista prób i braków](docs/spec/odbior.md).

## Sprawdzenie repozytorium

Python 3.12; poniższe kontrole nie wymagają dodatkowych bibliotek. Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

CI uruchamia te same kontrole oraz sprawdzenie oznaczeń licencji narzędziem [REUSE](https://reuse.software/). Nie wykonuje prób elektrycznych ani nowych ERC/DRC. [Środowisko i odtwarzanie plików](docs/development.md), [pełna procedura CAD i eksportu](hardware/radio-test-r01/odtworzenie.md).

## Współpraca i licencje

Zgłoszenia błędów i propozycje: [Issues](https://github.com/tmierzwa/WICI/issues). Zasady zmian, wymagane dowody i sposób podejmowania decyzji: [CONTRIBUTING.md](CONTRIBUTING.md). Podatności bezpieczeństwa zgłaszaj prywatnie według [SECURITY.md](SECURITY.md). Obowiązuje [kodeks postępowania](CODE_OF_CONDUCT.md).

Własny kod: MIT. Konstrukcja i CAD: CERN-OHL-P-2.0. Dokumentacja użytkowa: CC-BY-4.0. Biblioteki KiCad: CC-BY-SA-4.0 z wyjątkiem KiCad. Dokładne ścieżki, pochodzenie i pełne teksty: [LICENSE.md](LICENSE.md). Licencje pozwalają także na użycie komercyjne; niekomercyjny jest cel projektu.

Kod: [tmierzwa/WICI](https://github.com/tmierzwa/WICI). Publikacja repozytorium nie znosi statusu HOLD sprzętu.

## Jak powstała dokumentacja

Projekt prowadzi jedna osoba. Duża część analiz, obliczeń, dokumentacji i kodu modelu powstała z pomocą asystenta AI (Claude); takie commity mają w opisie wiersz `Co-Authored-By`. Autor przegląda i zatwierdza każdą zmianę, ale [przegląd techniczny](docs/review.md) jest wewnętrzny. Obliczeń nie sprawdził niezależny inżynier, a założeń prawnych nie sprawdził prawnik. Każdy wynik traktuj jako hipotezę do sprawdzenia; zgłoszenia błędów są najcenniejszym wkładem.

## In English

WICI is a non-commercial, open design of an emergency communication station for a shelter of about 50 people in Poland: a self-contained station with a screen, buttons and AA cells that sends short reports over a narrowband 869.525 MHz radio (Reticulum/LXMF on the microcontroller) to a municipal crisis desk and relays other stations' traffic whenever it is on. A laptop adds an operator panel and, with a Wi-Fi router, a local web page for residents' phones. It is a **prototype design (0.5); no hardware has been built or tested, and the R01.3 lab controller is on HOLD**. Documentation is in Polish; issues and pull requests in English are welcome. Code: MIT; hardware: CERN-OHL-P-2.0; documents: CC-BY-4.0. Much of the analysis was written with AI assistance and has not been independently reviewed. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english).

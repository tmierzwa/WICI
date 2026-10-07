# WICI — stacja łączności awaryjnej

Niekomercyjny projekt otwartej stacji dla schronienia z około 50 osobami. WICI uzupełnia system ochrony ludności, a nie go zastępuje: odbiorcę zgłoszeń, status nadawania w stanach nadzwyczajnych i ochronę danych uzgadnia się z gminą przed użyciem, tak aby podczas alarmu nic formalnego nie blokowało pracy. Znaleziony laptop i router udostępniają stronę przez Wi-Fi. Radio przekazuje krótkie zgłoszenia przez inne stacje do OSP. Telefony są ładowane z osobnego akumulatora.

**Stan: projekt prototypu 0.4; kontroler USB R01.3 — HOLD.** Jest schemat, PCB, eksporty i model kontraktów. Nie ma ukończonego modułu RF, oprogramowania układowego, aplikacji ani gotowej pamięci USB. Nie wykonano prób fizycznych. To nie jest wydanie do użycia podczas awarii.

> **Bezpieczeństwo.** Przetwornica 230 V wytwarza napięcie zagrażające życiu, a akumulatory mogą spowodować pożar. Opis przetwornicy nie jest instrukcją do samodzielnego wykonania; bez kwalifikacji i badań bezpieczeństwa nie wolno jej budować ani podłączać do ludzi i urządzeń. Projekt nie jest certyfikowanym urządzeniem, a licencje wyłączają wszelką gwarancję.

WICI używa [Reticulum](https://github.com/markqvist/Reticulum) i [LXMF](https://github.com/markqvist/LXMF). Są to odrębne projekty; ich kod nie jest dołączony.

| Katalog | Zawartość |
|---|---|
| [docs/conception](docs/conception/index.html) | Potrzeby, scenariusze, analiza opcji, architektura, wykonalność i odporność; [strona online](https://tmierzwa.github.io/WICI/) |
| [docs/spec](docs/README.md) | Specyfikacja stacji w pięciu rozdziałach, warunki odbioru i BOM stacji |
| [hardware](hardware/radio-test-r01/README.md) | Edytowalny kontroler KiCad, BOM, raporty i paczka kandydata |
| [software/reference](software/reference/README.md) | Model ramek, wiadomości i transakcji OSP; obliczenia |
| [tools](docs/development.md) | Kontrola repozytorium i tworzenie paczki źródłowej |

[Przegląd techniczny](docs/review.md) wskazuje m.in. konieczną poprawkę prądu wstrzymania USB (suspend) kontrolera oraz niezamkniętą zgodność czasów Reticulum/LXMF z P1.

Cel 1 km w zabudowie, 24 godziny z wymianą źródeł 12 V i zgodność dwóch dostawców radia wymagają prób. Model Okumury-Haty wskazuje, że przy antenach na wysokości okien 1 km w mieście jest na granicy budżetu łącza lub poza nią; sieć planuje się z wysoko umieszczonymi antenami i przekaźnikami. Kanał 869,525 MHz jest współdzielony z LoRaWAN i Meshtastic, więc wybór kanału zależy od pomiaru w miejscach pilotażu. Przed przekazaniem zestawu innym gotowa konfiguracja wymaga oceny zgodności z dyrektywą RED. Przetwornica 230 V i ładowarka są opisami konstrukcyjnymi; nie mają odebranych PCB. [Lista prób i braków](docs/spec/odbior.md).

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

Projekt prowadzi jedna osoba. Duża część analiz, obliczeń, dokumentacji i kodu modelu powstała z pomocą asystenta AI (Claude); takie commity mają w opisie wiersz `Co-Authored-By`. Autor przegląda i zatwierdza każdą zmianę, ale [przegląd techniczny](docs/review.md) jest wewnętrzny. Obliczeń nie sprawdził niezależny inżynier, a założeń prawnych — prawnik. Każdy wynik traktuj jako hipotezę do sprawdzenia; zgłoszenia błędów są najcenniejszym wkładem.

## In English

WICI is a non-commercial, open design of an emergency communication station for a shelter of about 50 people in Poland: a local web page over Wi-Fi, a durable report queue and a narrowband 869.525 MHz radio carrying short messages over Reticulum/LXMF to a municipal crisis desk. It is a **prototype design (0.4); no hardware has been built or tested, and the USB controller is on HOLD**. Documentation is in Polish; issues and pull requests in English are welcome. Code: MIT; hardware: CERN-OHL-P-2.0; documents: CC-BY-4.0. Much of the analysis was written with AI assistance and has not been independently reviewed. See [CONTRIBUTING.md](CONTRIBUTING.md#in-english).

# WICI — stacja łączności awaryjnej

Niekomercyjny projekt otwartej stacji dla schronienia z około 50 osobami. Znaleziony laptop i router udostępniają stronę przez Wi-Fi. Radio przekazuje krótkie zgłoszenia przez inne stacje do OSP. Telefony są ładowane z osobnego akumulatora.

**Stan: projekt prototypu 0.4; kontroler USB R01.3 — HOLD.** Jest schemat, PCB, eksporty i model kontraktów. Nie ma ukończonego modułu RF, firmware, aplikacji ani gotowego pendrive'a. Nie wykonano prób fizycznych. To nie jest wydanie do użycia podczas awarii.

WICI używa [Reticulum](https://github.com/markqvist/Reticulum) i [LXMF](https://github.com/markqvist/LXMF). Są to odrębne projekty; ich kod nie jest dołączony.

| Katalog | Zawartość |
|---|---|
| [docs/conception](docs/conception/index.html) | Potrzeby, scenariusze, analiza opcji, architektura, wykonalność i odporność |
| [docs/spec](docs/README.md) | Specyfikacja stacji w pięciu rozdziałach, warunki odbioru i BOM stacji |
| [hardware](hardware/radio-test-r01/README.md) | Edytowalny kontroler KiCad, BOM, raporty i paczka kandydata |
| [software/reference](software/reference/README.md) | Model ramek, wiadomości i transakcji OSP; obliczenia |
| [tools](docs/development.md) | Kontrola repozytorium i tworzenie paczki źródłowej |

[Przegląd techniczny](docs/review.md) wskazuje m.in. konieczną poprawkę suspend USB kontrolera oraz niezamkniętą zgodność czasów Reticulum/LXMF z P1.

Cel 1 km w zabudowie, 24 godziny z wymianą źródeł 12 V i zgodność dwóch dostawców radia wymagają prób. Przetwornica 230 V i ładowarka są opisami konstrukcyjnymi; nie mają odebranych PCB. [Lista prób i braków](docs/spec/odbior.md).

## Sprawdzenie repozytorium

Python 3.12; poniższe kontrole nie wymagają dodatkowych bibliotek. Uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
python3 tools/verify_repository.py
```

CI uruchamia te same kontrole. Nie wykonuje prób elektrycznych ani nowych ERC/DRC. [Środowisko i odtwarzanie plików](docs/development.md), [pełna procedura CAD i eksportu](hardware/radio-test-r01/odtworzenie.md).

## Współpraca i licencje

Zgłoszenia błędów i propozycje: [Issues](https://github.com/tmierzwa/WICI/issues). Zasady zmian i wymagane dowody: [CONTRIBUTING.md](CONTRIBUTING.md).

Własny kod: GPL-3.0-or-later. Konstrukcja i CAD: CERN-OHL-P-2.0. Dokumentacja użytkowa: CC-BY-4.0. Biblioteki KiCad: CC-BY-SA-4.0 z wyjątkiem KiCad. Dokładne ścieżki, pochodzenie i pełne teksty: [LICENSE.md](LICENSE.md). Licencje pozwalają także na użycie komercyjne; niekomercyjny jest cel projektu.

Kod: [tmierzwa/WICI](https://github.com/tmierzwa/WICI). Publikacja repozytorium nie znosi statusu HOLD sprzętu.

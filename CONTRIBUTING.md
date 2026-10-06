# Współpraca przy WICI

Projekt jest prototypem. Zmiany mają upraszczać wykonanie, usuwać zależność od jednego dostawcy i zwiększać niezawodność. Wygląd i dodatkowe funkcje nie są priorytetem.

1. Dla większej zmiany otwórz [Issue](https://github.com/tmierzwa/WICI/issues): problem, proponowany zakres i warunek sprawdzenia. Małe poprawki można wysłać bezpośrednio jako pull request.
2. Pracuj w swojej gałęzi. Opisz, co zmienia PR i czym zostało sprawdzone.
3. Parametry i kontrakty stacji zmieniaj w `docs/spec/`. Potrzeby, uzasadnienia, opcje i analizę wykonalności utrzymuj w [docs/conception](docs/conception/README.md). Aktualizuj powiązane wymagania i próby; odróżniaj założenie od pomiaru. Nie twórz drugiej pełnej kopii specyfikacji.
4. Zmiana kodu kontraktów wymaga przypadku, który pokazuje problem, i wyniku odpowiednich testów. Raport zaktualizuj dopiero po ich wykonaniu.
5. Zmiana CAD wymaga aktualnych ERC/DRC, eksportów i kontroli paczki według [procedury odtworzenia](hardware/radio-test-r01/odtworzenie.md). Zmiana elektryczna wymaga nowej rewizji. Nie zmieniaj historycznych raportów na wyniki nowych prób.
6. Raport z prób fizycznych podaje rewizję, elementy, warunki, metodę i wynik. Nie oznaczaj niewykonanych prób jako zaliczonych. Sam CI nie zwalnia statusu HOLD.

Przed PR uruchom z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 -m unittest discover -s tests -v
```

Po zmianie publicznych plików przejrzyj `git diff` i listę plików w indeksie. Następnie:

```sh
git add <pliki-zmiany>
python3 tools/release.py --refresh
python3 tools/verify_repository.py
git add manifest.json
```

Jeżeli zmieniasz narzędzia lub dokumenty wewnątrz `hardware/radio-test-r01/`, przed odświeżeniem głównego manifestu wykonaj `python3 hardware/radio-test-r01/tools/check_bundle.py`. Zmiana eksportów wymaga też `verify_fabrication.py`. Nie odświeżaj sum w odpowiedzi na nieznany błąd CI; najpierw ustal, co się zmieniło.

Nie dodawaj kluczy, danych mieszkańców, kopii prywatnych rozmów ani materiałów producenta bez uprawnień do dystrybucji. Lokalny `reference-private/` nie należy do wydania. Dla nowej biblioteki lub footprintu zapisz źródło, wersję, modyfikacje i licencję.

Wkład pozostaje pod licencją właściwą dla ścieżki w [LICENSE.md](LICENSE.md). Przesyłaj materiały, do których masz prawo udzielić tej licencji. Nie wymagamy CLA. Cel projektu jest niekomercyjny; wybrane otwarte licencje nie zabraniają zastosowań komercyjnych.

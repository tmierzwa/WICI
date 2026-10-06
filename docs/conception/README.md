# WICI — koncepcja systemu

Cel: przekazać krótkie zgłoszenie ze schronienia do miejsca zdolnego udzielić pomocy, gdy nie działa internet ani sieć komórkowa. Mieszkaniec używa przeglądarki telefonu. Opiekun może przyjąć zgłoszenie osoby bez telefonu. Stacja zachowuje dane lokalnie i przekazuje je radiem, także przez inne stacje.

Zakres bazowy: jeden budynek, około 50 osób, praca przez 24 godziny z wymianą źródeł energii, sąsiednie stacje około 1 km od siebie w zabudowie. Laptop, router, ich zasilacze i akumulatory pochodzą z lokalnego zasobu. Zestaw WICI dostarcza radio, oprogramowanie offline, połączenia, zasilanie i osobną ładowarkę telefonów.

## Dokumenty

| Dokument | Pytanie, na które odpowiada |
|---|---|
| [01. Potrzeby i wymagania](01-potrzeby-i-wymagania.md) | Co musi działać i jak to rozpoznać? |
| [02. Scenariusze i organizacja](02-scenariusze-i-organizacja.md) | Kto obsługuje stację i kto faktycznie pomaga? |
| [03. Dostępne rozwiązania](03-dostepne-rozwiazania.md) | Co można wykorzystać zamiast budować od początku? |
| [04. Analiza opcji](04-analiza-opcji.md) | Dlaczego taki podział systemu i kiedy zmienić wybór? |
| [05. Projekt koncepcyjny komunikacji](05-projekt-koncepcyjny-komunikacji.md) | Jak przechodzą dane, potwierdzenia i decyzje? |
| [06. Wykonalność i zasoby](06-wykonalnosc-i-budzet-zasobow.md) | Czy wystarczy zasięgu, czasu antenowego, energii i części? |
| [07. Zagrożenia i odporność](07-zagrozenia-i-odpornosc.md) | Co się psuje, jak to wykryć i co działa dalej? |
| [08. Weryfikacja i decyzje](08-plan-weryfikacji-i-decyzje.md) | Jakie próby rozstrzygają, czy koncepcję można wdrażać? |
| [Źródła](zrodla.md) | Na jakich materiałach oparto analizę? |

## Jak czytać ustalenia

- **Wymaganie**: cel użytkowy projektu. Nie oznacza osiągniętej właściwości.
- **Wybór bazowy**: rozwiązanie przyjęte w [specyfikacji 0.4](../README.md), oczekujące na wykonanie i odbiór.
- **Założenie obliczeniowe**: liczba do oszacowania zasobów. Wymaga zastąpienia pomiarem.
- **Propozycja próby lub organizacji**: uzupełnienie koncepcji do zatwierdzenia przed pilotażem.
- **Dowód**: wynik wskazanej próby na określonej konfiguracji. Nie przenosi się automatycznie na inne części lub warunki.

Parametry wykonawcze, ramki, API i warunki odbioru należą do `docs/spec/`. Ta część wyjaśnia potrzeby, wybory i ich granice; nie tworzy drugiej specyfikacji. Jeśli próba wymusi zmianę parametru, aktualizuje się specyfikację oraz powiązaną analizę.

## Ocena obecnego stanu

Koncepcja nadaje się do budowy prototypów i sprawdzania hipotez. Nie ma jeszcze dowodu łączności 1 km, działania całego stosu radiowego, pracy dobowej ani bezpieczeństwa własnej przetwornicy. Kontroler USB R01.3 pozostaje HOLD; moduły RF, firmware, aplikacja i pakiety START nie są ukończone. Wyniki modelu i CAD nie zastępują prób sprzętu.

[Aktualne ustalenia przeglądu](../review.md) obejmują konkretny problem suspend USB, budżet ogranicznika ładowarki oraz kontrprzykład czasowy stosu sieciowego.

Pierwsze rozstrzygnięcia: trwałe przyjęcie zgłoszenia przez OSP, rzeczywisty koszt radiowy LXMF, zgodność dwóch modemów, zasilanie bez resetu i dostępność dyżurnego z możliwością działania. Bez odbiorcy zdolnego pomóc sprawna sieć jedynie przenosi dane.

Rygor oznacza jawne założenia, próby odtwarzalne, rozpoznawalne awarie i warunki przerwania pracy. Projekt nie deklaruje kwalifikacji wojskowej, odporności na celowe zagłuszanie ani certyfikacji środowiskowej.

Licencje: [mapa projektu](../../LICENSE.md). Analizy są na CC-BY-4.0; opis konstrukcji komunikacji w rozdziale 05 jest na CERN-OHL-P-2.0.

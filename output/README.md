# Dokumenty przygotowania testów

## Dokumenty zapisane w repozytorium

- [Zakres prototypu L0 do wyceny](pdf/WICI-L0-zakres-prototypu.pdf): końcowy dokument z 9 października 2026 r., identyczny bajtowo z `ZAKRES-PROTOTYPU.pdf` w końcowej paczce RFQ. Zapytania wysłano do trzech firm; wykonanie nie zostało jeszcze zlecone.
- [Treść zakresu L0](text/WICI-L0-zakres-prototypu.txt): tekst wyodrębniony z powyższego PDF do przeszukiwania i porównania. To transkrypcja, nie generator odtwarzający układ PDF.
- [Pierwszy test LoRa na macOS](pdf/WICI-pierwszy-test-LoRa-macOS.pdf): wcześniejsza instrukcja już zapisana w repozytorium. Zawiera lokalną ścieżkę autora; dostosować ją do miejsca pobrania projektu. Bieżąca instrukcja R0 jest w [instrukcji partnera radiowego](../hardware/l0-diagnostic/reference/R0-INSTRUKCJA.txt).

Aktualny zakres i procedura odbioru sprzętu są w [instrukcji L0](../hardware/l0-diagnostic/README.md). Diagnostyka L0 jest gotowa do rozpoczęcia prób; wyniki sprzętowe pozostają niepotwierdzone. Status zamówień jest w [głównym README](../README.md#gdzie-jesteśmy).

## Wcześniejsze pliki lokalne

Siedem wcześniejszych PDF-ów pozostaje lokalnie i jest pominiętych w Git przez wskazanie ich nazw w `.gitignore`:

- `WICI-L0-zakres-i-odbior.pdf` i `WICI-L0-zakres-i-odbior-Q2.pdf`: zastąpione krótszym końcowym zakresem prototypu.
- `WICI-L0-review-i-koszt-Q2.pdf`: raport przeglądu wcześniejszej paczki, z opisem zmian i warunkami sprzed przygotowania programu L0.
- `WICI-kontrola-przed-wycena-2026-10-08.pdf` i `WICI-kwalifikacja-prototypu-LoRa-2026-10-08.pdf`: wcześniejsze kontrole i kwalifikacja poprzedzające końcową paczkę.
- `WICI-plan-zakupow-i-testow-PL-2026-10-08.pdf`: wcześniejszy plan obejmujący RNode, N1/P1 i większy budżet; nie jest aktualnym zakresem zamówienia jednej sztuki L0.
- `WICI-nastepny-etap-oprogramowania-LoRa.pdf`: wcześniejszy plan dalszego oprogramowania; nie uwzględnia przygotowanej diagnostyki L0 i nie zastępuje bieżącej procedury testów.

Nie usuwa się tych plików lokalnie. Do ofert i bieżących testów należy używać dokumentów wskazanych powyżej, aby uniknąć równoległych wersji zakresu.

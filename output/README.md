# Dokumenty przygotowania testów

## Dokumenty zapisane w repozytorium

- [Zakres prototypu L0 do wyceny](pdf/WICI-L0-zakres-prototypu.pdf): końcowy dokument z 9 października 2026 r., identyczny bajtowo z `ZAKRES-PROTOTYPU.pdf` w końcowej paczce RFQ. Zapytania wysłano do trzech firm; płytki i części autor zamówił sam 2026-10-10 ([przed-produkcja.md](../hardware/dev-bench/przed-produkcja.md#zamówienie-2026-10-10-l0)), a montaż i uruchomienie wykonuje zewnętrzny wykonawca według [zlecenia](../hardware/l0-diagnostic/ZLECENIE.md). Dokument pozostaje zakresem prób i odbioru L0.
- [Treść zakresu L0](text/WICI-L0-zakres-prototypu.txt): tekst wyodrębniony z powyższego PDF do przeszukiwania i porównania. To transkrypcja, nie generator odtwarzający układ PDF.
- [Zlecenie montażu i uruchomienia L0](pdf/WICI-L0-zlecenie.pdf): brief dla zewnętrznego wykonawcy, wydruk [ZLECENIE.md](../hardware/l0-diagnostic/ZLECENIE.md) przez `python3 tools/doc_pdf.py hardware/l0-diagnostic/ZLECENIE.md output/pdf/WICI-L0-zlecenie.pdf` (pakiet Python `markdown` i Chrome albo Chromium). Po zmianie źródła PDF generuje się ponownie; `tools/doc_pdf.py` zapisuje sumy źródła i wydruku w [zrodla.json](pdf/zrodla.json), a `tools/verify_repository.py` odrzuca wydruk starszy niż źródło.
- [Montaż, uruchomienie i próby L0](pdf/WICI-L0-montaz-i-testy.pdf): instrukcja dla wykonawcy z diagnozą usterek, wydruk [MONTAZ-I-TESTY.md](../hardware/l0-diagnostic/MONTAZ-I-TESTY.md) tym samym poleceniem `tools/doc_pdf.py`.
- [Pierwszy test LoRa na macOS](pdf/WICI-pierwszy-test-LoRa-macOS.pdf): wcześniejsza instrukcja już zapisana w repozytorium. Zawiera lokalną ścieżkę autora, którą trzeba dostosować do miejsca, w którym leży pobrany projekt. Bieżąca instrukcja R0 jest w [instrukcji partnera radiowego](../hardware/l0-diagnostic/reference/R0-INSTRUKCJA.txt).

Aktualny zakres i procedura odbioru sprzętu są w [instrukcji L0](../hardware/l0-diagnostic/README.md). Diagnostyka L0 jest gotowa do prób, ale wyniki na sprzęcie nie są jeszcze potwierdzone. Status zamówień jest w [głównym README](../README.md#gdzie-jesteśmy).

Do ofert i bieżących testów należy używać tylko dokumentów wskazanych wyżej, żeby nie krążyły równoległe wersje zakresu.

# Przygotowanie repozytorium do publikacji

Wersja specyfikacji pozostaje 0.4, kontroler R01.3. Nie zmieniono parametrów ani CAD. Zmiany dotyczą organizacji i kontroli wydania:

- Rozdziały specyfikacji są w `docs/spec/`; usunięto dwie pełne kopie. Model, testy i obliczenia przeniesiono do `software/reference/` bez zmiany kodu i wyników.
- Dodano instrukcje środowiska, współpracy, mapę licencji oraz CI.
- Eksporter tworzy teraz także PDF montażowy, PDF schematu, informacje licencyjne i ZIP kontrolera. ZIP źródeł tworzy się osobnym poleceniem do ignorowanego `dist/`.
- Kontrola ZIP odrzuca puste archiwum, brakujące lub dodatkowe wpisy, duplikaty i stare bajty. Tryb CI jest tylko do odczytu, również z Python `-O`.
- Usunięto prywatne metadane eksportu rozmowy. Etykiety katalogów roboczych w DSN i XML są względne; ich przed/po sumy są w `hardware/radio-test-r01/checks/publication-paths.json`. Dane połączeń i geometria pozostają bez zmian.

Historia w `docs/history/` zachowuje zakres wcześniejszych kontroli. Jej liczby i polecenia odnoszą się do stanu sprzed reorganizacji. Bieżąca kontrola to `tools/verify_repository.py` i CI dla aktualnego commita.

Repozytorium można publikować jako eksperymentalny projekt otwarty. Sprzęt pozostaje **HOLD**. Nadal potrzebne są rzeczywiste przymierzenie USB-B, SW1 i IDC, próby USB, moduł RF, firmware oraz próby zasilania i radia. Publikacja ani zielone CI nie potwierdzają gotowości stacji do akcji ratowniczej.

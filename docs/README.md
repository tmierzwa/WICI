# Dokumentacja WICI

Zacznij od [koncepcji systemu](conception/index.html): potrzeby i wymagania, scenariusze pracy, dostępne rozwiązania, analiza opcji, architektura komunikacji, wykonalność, zagrożenia i plan prób. Dokumenty są po polsku. Oddzielają wymagania od dowodów i wskazują decyzje pozostające do zamknięcia.

Specyfikacja stacji 0.4 obejmuje pięć rozdziałów i BOM stacji, wymienione poniżej. Parametry, kontrakty, warunki odbioru i kandydatów części zmienia się w tych plikach. Uzasadnienia i powiązane analizy utrzymuje się w `docs/conception/`.

| Rozdział | Zakres |
|---|---|
| [Projekt](spec/projekt.md) | Połączenia, wymagania i użycie odebranego zestawu |
| [Radio](spec/radio.md) | Profil P1, ramki, USB i adapter Reticulum |
| [Oprogramowanie](spec/oprogramowanie.md) | Wiadomości SA1, SQLite, strona i plan pakietów offline |
| [Elektronika](spec/elektronika.md) | Zasilanie A/B, ładowarka i przetwornica |
| [Odbiór](spec/odbior.md) | Próby, warunki zaliczenia i niezrealizowane części |
| [BOM stacji](spec/bom-stacji.csv) | Wymagania minimalne części i kandydaci od dwóch producentów, ze stanem kwalifikacji |

Wykonany kontroler ma osobne [źródła i dokumentację sprzętową](../hardware/radio-test-r01/README.md). Jego BOM nie zastępuje [BOM całej stacji](spec/bom-stacji.csv). Wyniki obliczeń są w [modelu](../software/reference/README.md).

[Narzędzia i tworzenie paczek](development.md). Bieżąca kontrola repozytorium: `tools/verify_repository.py` i CI dla aktualnego commita.

[Aktualne ustalenia przeglądu technicznego](review.md): poprawione rozbieżności, konkretne przeszkody i warunki ich zamknięcia.

Status: prototyp; sprzęt HOLD. Instrukcje użycia stacji opisują docelowy odebrany zestaw. Nie są instrukcją uruchomienia gotowego produktu.

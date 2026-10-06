# Dokumentacja WICI

Zacznij od [koncepcji systemu](conception/README.md): potrzeby i wymagania, scenariusze pracy, dostępne rozwiązania, analiza opcji, architektura komunikacji, wykonalność, zagrożenia i plan prób. Dokumenty są po polsku. Oddzielają wymagania od dowodów i wskazują decyzje pozostające do zamknięcia.

Specyfikacja stacji 0.4 obejmuje pięć rozdziałów poniżej. Parametry, kontrakty i warunki odbioru zmienia się w tych plikach. Uzasadnienia i powiązane analizy utrzymuje się w `docs/conception/`.

| Rozdział | Zakres |
|---|---|
| [Projekt](spec/projekt.md) | Połączenia, wymagania i użycie odebranego zestawu |
| [Radio](spec/radio.md) | Profil P1, ramki, USB i adapter Reticulum |
| [Oprogramowanie](spec/oprogramowanie.md) | Wiadomości SA1, SQLite, strona i plan pakietów offline |
| [Elektronika](spec/elektronika.md) | Zasilanie A/B, ładowarka i przetwornica |
| [Odbiór](spec/odbior.md) | Próby, warunki zaliczenia i niezrealizowane części |

Wykonany kontroler ma osobne [źródła i dokumentację sprzętową](../hardware/radio-test-r01/README.md). Jego BOM nie zastępuje [BOM całej stacji](../bom.csv). Wyniki obliczeń są w [modelu](../software/reference/README.md).

[Narzędzia i tworzenie paczek](development.md). Bieżąca kontrola repozytorium: `tools/verify_repository.py` i CI dla aktualnego commita.

Status: prototyp; sprzęt HOLD. Instrukcje użycia stacji opisują docelowy odebrany zestaw. Nie są instrukcją uruchomienia gotowego produktu.

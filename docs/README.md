# Dokumentacja WICI

Zacznij od [koncepcji systemu](conception/index.html): potrzeby i wymagania, scenariusze pracy, dostępne rozwiązania, analiza opcji, architektura komunikacji, wykonalność, zagrożenia i plan prób. Dokumenty są po polsku, oddzielają wymagania od dowodów i wskazują otwarte decyzje.

Specyfikacja stacji 0.5 składa się z pięciu rozdziałów, karty obsługi i BOM stacji. Parametry, kontrakty, warunki odbioru i kandydatów części zmienia się w tych plikach, a uzasadnienia i analizy w `docs/conception/`.

| Rozdział | Zakres |
|---|---|
| [Projekt](spec/projekt.md) | Poziomy zestawu, połączenia, przygotowanie i użycie odebranego zestawu |
| [Radio](spec/radio.md) | Profil P1, ramki, interfejs P1 w stosie, USB do laptopa, dwa wykonania stacji |
| [Oprogramowanie](spec/oprogramowanie.md) | Oprogramowanie stacji i laptopa, wiadomości SA1, protokół USB, ekran i przyciski, pakiety offline |
| [Elektronika](spec/elektronika.md) | Zasilanie stacji, wymagania płytki R02, zasilanie A/B, ładowarka i przetwornica |
| [Odbiór](spec/odbior.md) | Próby z grupami T1–T8, warunki zaliczenia i niezrealizowane części |
| [Karta obsługi](spec/karta.md) | Tekst dwustronnej karty obsługi stacji i pola formularza papierowego |
| [BOM stacji](spec/bom-stacji.csv) | Wymagania minimalne części i kandydaci od dwóch producentów, ze stanem kwalifikacji |

Kontroler R01.3, w 0.5 stanowisko laboratoryjne P1, ma osobne [źródła i dokumentację sprzętową](../hardware/radio-test-r01/README.md). Jego BOM nie zastępuje [BOM całej stacji](spec/bom-stacji.csv). Wyniki obliczeń są w [modelu](../software/reference/README.md).

[Narzędzia i tworzenie paczek](development.md). Bieżąca kontrola repozytorium: `tools/verify_repository.py` i CI dla aktualnego commita.

[Aktualne ustalenia przeglądu technicznego](review.md): poprawione rozbieżności, konkretne przeszkody i warunki ich zamknięcia.

W specyfikacji skrót OSP oznacza rolę stanowiska odbiorczego wyznaczonego przez wójta (burmistrza, prezydenta miasta); typowo pełni ją jednostka ochotniczej straży pożarnej z grafikiem dyżurów na czas kryzysu, a także gminne centrum zarządzania kryzysowego lub stanowisko gminnego zespołu zarządzania kryzysowego ([koncepcja, rozdział 02](conception/02-scenariusze-i-organizacja.html#miejsce-w-systemie-ochrony-ludnosci)).

Status: prototyp; sprzęt HOLD. Instrukcje użycia opisują docelowy odebrany zestaw, a nie gotowy produkt.

# Dokumenty obsługi WICI

Dokumenty dla ludzi, którzy obsługują system: opiekunów punktów i dyżurnych stanowiska odbiorczego. Licencja CC BY 4.0 (reszta `docs/spec/` jest na CERN-OHL-P-2.0).

| Plik | Dla kogo | Zawartość |
|---|---|---|
| [karta-stacji.html](karta-stacji.html) | opiekun punktu (sołtys, nauczyciel, strażak OSP) | karta obsługi stacji do druku dwustronnego i laminowania: wersje PL, UK i EN, każda na jednej kartce A4 (strona 1: najważniejsze, strona 2: gdy trzeba); na końcu formularz papierowy zgłoszenia w dwóch egzemplarzach |
| [instrukcja-dyzurnego.md](instrukcja-dyzurnego.md) | dyżurny stanowiska odbiorczego (strażak OSP, pracownik gminy) | uruchomienie, potwierdzenia, odpowiedzi i komunikaty, kwarantanna, przekazywanie służbom, rejestr, awarie, ćwiczenia, cisza radiowa, zamknięcie zdarzenia; tabele do wypełnienia przez gminę |
| [szkolenie.md](szkolenie.md) | prowadzący szkolenie, gmina | program 2-godzinnego szkolenia opiekunów i dyżurnych przed pracą stacji w terenie: cele, organizacja, przebieg, ścieżki opiekuna i dyżurnego, sprawdzian, po szkoleniu |

Tematy obsługi spoza karty (adres, alarmy, energia, poziomy 2–3, koniec zdarzenia) są w [instrukcji opiekuna](../spec/instrukcja.md).

## Wersja

Dokumenty dotyczą oprogramowania stacji WICI ze specyfikacji 0.5, obrazów `bench-n1-0.1` i `bench-b-0.1`, oraz stacji deweloperskiej na płytce nośnej N1. Napisy w cudzysłowach są tekstami ekranu z `firmware/src/ui_texts.h` (stan z 2026-10-12, z wpisem WŁASNY TEKST). Zmiana tekstów ekranu wymaga zmiany karty.

Status: wersja robocza do ćwiczenia przy stole. Znak ◆ oznacza czynność, której oprogramowanie jeszcze nie obsługuje (karta: pomiar energii i wyłączanie przyciskiem; instrukcja: także części panelu dyżurnego). Aplikacji stanowiska jeszcze nie zbudowano. Wersje ukraińska i angielska wymagają sprawdzenia przez native speakera.

## Druk

1. Otwórz `karta-stacji.html` w przeglądarce.
2. Drukuj: A4, pionowo, skala 100%, bez nagłówków i stopek przeglądarki, dwustronnie z obracaniem wzdłuż dłuższej krawędzi.
3. Strony 1–2: PL, 3–4: UK, 5–6: EN, 7: formularz (drukuj jednostronnie, w wielu kopiach).
4. Po wydruku, przed laminowaniem, wpisz ręcznie na stronie 1 dane punktu: nr i nazwę, adres, stanowisko odbiorcze, zastępców, miejsce radiotelefonu PMR i cel gońca.

Układ karty: krój bezszeryfowy, czarno-biały, tekst co najmniej 9 pt, stałe zasady 10,4 pt. Każda strona mieści się na A4 przy marginesach 9 mm; po zmianie treści sprawdź to wydrukiem do PDF (7 stron).

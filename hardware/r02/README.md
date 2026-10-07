# WICI R02: płytka stacji

**Status: projekt rozpoczęty 2026-10-07. Nie ma jeszcze schematu ani PCB. HOLD: nie zamawiać.**

R02 jest pierwszą drukowaną płytką projektu i jedyną, którą WICI projektuje: samodzielna stacja z mikrokontrolerem, torem radiowym P1, pamięcią FRAM, ekranem, przyciskami i własnym zasilaniem z ogniw i z wejścia 12 V. Powstaje w dwóch wykonaniach o wspólnym zachowaniu: A (nRF52840 + CC1120) i B (ESP32-S3 + S2-LP). Do czasu R02 oprogramowanie i próby T1–T4 prowadzi się na [stanowisku deweloperskim](../dev-bench/README.md) z płytek rozwojowych i modułów producentów. Wcześniejszy kontroler R01.3 (STM32F103, modem USB) nie jest częścią R02; jego ustalenia i lekcje są w [lekcje.md](lekcje.md), a pliki CAD w historii Git.

## Źródła wymagań

| Dokument | Co wyznacza dla R02 |
|---|---|
| [Elektronika](../../docs/spec/elektronika.md#płytka-stacji-r02-wymagania) | zasilanie z ogniw i 12 V, progi, pomiar, pobór, szyna 5 V ekranu, tabela wymagań płytki: MCU, zegar, FRAM, ekran, przyciski, ESD, programowanie, nadzór, USB, ochrona odgromowa, temperatura, obudowa |
| [Radio](../../docs/spec/radio.md) | profil P1, moc 13 dBm, TCXO ±0,5 ppm z budżetem ±2,0 ppm, czułość ≤−110 dBm na złączu z pełnym torem wejściowym, dwa wykonania RF, USB do laptopa, polecenia pomiarowe |
| [Oprogramowanie](../../docs/spec/oprogramowanie.md#ekran-i-przyciski-stacji) | ekran, przyciski, dioda alarmu, brzęczyk, tryb przygotowania pod plombowaną pokrywą, dwa interfejsy CDC |
| [BOM stacji](../../docs/spec/bom-stacji.csv) | kandydaci części od dwóch producentów ze stanem kwalifikacji; R02 nie dodaje części bez wpisu w BOM |
| [Odbiór](../../docs/spec/odbior.md) | próby T4 (radio), T6 (energia i bezpieczeństwo), T7 (odtworzenie i dostawcy) i ich warunki zaliczenia |
| [Lekcje z R01.3](lekcje.md) | tor RF według referencji producenta, zasilanie i USB, zasady layoutu, mechanika, proces kontroli, kolejność uruchomienia |

## Wejścia, które muszą być zamknięte przed schematem

- **D14 (MCU):** T3 na stanowisku deweloperskim, z zapasem RAM ≥30% dla obu rodzin; bez tego nie wiadomo, czy wykonanie A w ogóle powstaje.
- **D15 (ekran):** wybór Sharp LS027B7DH01 albo zamiennika i złącze wspólne dla obu wykonań.
- **D10 (P1 wobec LoRa):** wyniki T4 ze stanowiska: czułość toru producenta, harmoniczne, blokowanie LTE 800 i GSM 900 z filtrem SAW i bez niego; od nich zależy, czy R02 ma przełącznik RF i osobny tor odbiorczy.
- **Zasilanie poziomu 1:** liczba ogniw, przetwornica i sterownik wyłącznika według [elektroniki](../../docs/spec/elektronika.md); kandydaci w BOM.
- **Obudowa:** wymiary, położenie ekranu, przycisków, złączy i plombowanej pokrywy serwisowej, bo wyznaczają obrys i otwory płytki.

## Kolejność prac

1. **Architektura płytki.** Podział na bloki: zasilanie (ogniwa, 12 V, suma diodowa, przetwornica 3V3, szyna 5 V, nadzór), MCU, tor RF, FRAM, ekran i wejścia, USB-C, ochrona. Decyzja do podjęcia: dwa osobne projekty PCB (A i B) ze wspólnymi arkuszami schematu, albo płytka nośna ze wspólnymi blokami i wymiennym modułem MCU+RF. Druga droga upraszcza kwalifikację dwóch dostawców (W14), ale dodaje złącze w torze zasilania i sygnałów.
2. **Stos warstw.** Cztery warstwy. Tor RF przenosi się z referencji producenta razem z jej stosem i geometrią, nie jako przerysowane ścieżki na innym stosie ([lekcje](lekcje.md#tor-rf)). Stos zapisuje się jawnie w PCB i w `checks/stackup.json` i potwierdza u wykonawcy przed zamówieniem.
3. **Schemat.** Każdy blok z kandydatami z BOM; przegląd elektryczny względem kart katalogowych, osobny od ERC: zegary i ich piny sterujące, prądy w stanach wyłączenia, pojemność za regulatorami, progi komparatorów, ochrona wejść.
4. **Layout.** Zasady z [lekcji](lekcje.md#zasady-layoutu); jawne reguły w `.kicad_dru`; zero wyjątków DRC; obrys i otwory według obudowy.
5. **Przegląd i mechanika.** ERC i DRC 0 z `--severity-all`; przegląd przez drugą osobę; wydruk 1:1 z kreską 50 mm i przymiarka rzeczywistych złączy, przycisków, ekranu i obudowy; wynik zapisany w `checks/`.
6. **Eksport i paczka.** Gerbery, wiercenia PTH/NPTH, pozycje, BOM z MPN, pasta, rysunek montażowy, NOTICE i teksty licencji; porównanie eksportów z geometrią PCB; `status.json` i manifest sum z trybem `--check`.
7. **Zamówienie.** Po zamknięciu listy `przed-produkcja.md` tej rewizji: po 2–4 sztuki każdego wykonania; montaż QFN i elementów RF 0402 zlecony.
8. **Uruchomienie.** Kolejność z [lekcji](lekcje.md#uruchomienie), potem próby T4 i T6 z [odbioru](../../docs/spec/odbior.md); każdy egzemplarz z własnym zapisem.

## Struktura folderu

Docelowo: `cad/` (projekt KiCad 10.0.6, reguły `.kicad_dru`, lokalne biblioteki z zapisanym pochodzeniem), `checks/` (raporty ERC/DRC, stos, dowody przeglądu, `status.json`, manifest sum), `fabrication/` (paczka danej rewizji), `bom.csv`, `polaczenia.md`, `uruchomienie.md`, `przed-produkcja.md`. Materiały producentów i importy referencji trzyma się lokalnie w `reference-private/`, poza Git i paczką źródłową ([.gitignore](../../.gitignore)).

Narzędzia eksportu i kontroli pisze się dla R02 od nowa; skrypty R01.3 (eksport Gerberów, porównanie eksportów z geometrią przez gerbonara, arkusz 1:1 w ReportLab, kontrola paczki) są w historii Git w commicie `ea32e7c` jako wzór. Licencje według [LICENSE.md](../../LICENSE.md): własny projekt CERN-OHL-P-2.0, biblioteki KiCad CC-BY-SA-4.0 z wyjątkiem KiCad, skrypty MIT.

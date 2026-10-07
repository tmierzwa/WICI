# Znak WICI

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="WICI-na-ciemnym.svg"><img src="WICI-na-jasnym.svg" alt="Znak WICI" width="320"></picture></p>

Napis w otwartym kroju Nunito Sans Black (SIL Open Font License 1.1). Kropki nad literami I wystają ponad napis jak dwa węzły sieci, a między nimi biegnie sygnał z impulsem. Wszystkie litery są w krzywych, więc pliki nie wymagają fontu.

| Plik | Zastosowanie |
|---|---|
| [WICI-na-ciemnym.svg](WICI-na-ciemnym.svg), [.png](WICI-na-ciemnym.png) | ciemne tło: napis biały, sygnał żółty `#f4d345` |
| [WICI-na-jasnym.svg](WICI-na-jasnym.svg), [.png](WICI-na-jasnym.png) | jasne tło: napis `#0f1216`, sygnał przyciemniony do `#c99a00`, bo jasny żółty znika na białym |
| [ikona.svg](ikona.svg), `ikona-512.png` | ikona: dwie kropki i sygnał na kwadracie w kolorze tła filmu `#0f1216` |
| `ikona-180.png` | ikona na ekranie głównym iPhone'a (`apple-touch-icon` stron) |
| `ikona-32.png` | favicon dla przeglądarek bez obsługi SVG |
| [favicon.svg](favicon.svg) | favicon stron: kropki i sygnał na własnym ciemnym kafelku, ten sam wygląd w każdej przeglądarce i motywie |
| [fonts/](fonts/OFL.txt) | font Nunito Sans (wersja zmienna z [Google Fonts](https://github.com/google/fonts/tree/main/ofl/nunitosans)) i tekst jego licencji; potrzebny tylko do odtworzenia znaku |

PNG znaku mają 2400 × 1047 px i przezroczyste tło. Znak jest na górze [głównego README](../../README.md), a ikony i favicon na [stronach koncepcji](../../docs/conception/index.html).

## Użycie

- **Minimalny rozmiar:** znak ma co najmniej 32 px wysokości. Przy 24 px linia sygnału jest jeszcze widoczna, ale impuls zlewa się w kreskę. Poniżej 32 px używaj ikony albo favicony.
- **Pole ochronne:** wokół znaku zostaw wolne miejsce co najmniej na średnicę kropki.
- **Kolory:** używaj tylko dwóch par z tabeli. Sygnał zawsze ma kolor akcentu, a napis i kropki zawsze ten sam kolor.
- **Kształt:** nie składaj nazwy fontem i nie zmieniaj proporcji. Zmiany wprowadzaj w `znak.py` i generuj pliki od nowa.

## Konstrukcja

Skrypt ustawia wersję zmienną fontu na grubość 900 (Black), szerokość 100, rozmiar optyczny 12 i wysokość liter 500. Wymiary są w jednostkach fontu: 1000 na em, wersalik ma 705.

- **Litery:** W, C i oba I pochodzą bez zmian z Nunito Sans Black. Odstęp W–I jest z fontu. Dwie pary są poprawione na oko: krągłe C stoi 34 jednostki bliżej pierwszego I, a drugie I stoi 14 jednostek bliżej C, bo otwarcie C samo daje światło. Światło między literami wynosi 74–77 jednostek.
- **Kropki:** to koła o średnicy 1,06 szerokości pnia I, czyli 195 jednostek. Koło tej samej szerokości co prostokąt wygląda na mniejsze, stąd ta nadwyżka. Nad I jest 70 jednostek światła, podobnie jak między literami.
- **Sygnał:** ma grubość 52 jednostek. Biegnie pod kropkami i wchodzi do ich środków, więc nigdzie nie kończy się płasko na krągłej krawędzi.
- **Impuls:** stoi w połowie odcinka między kropkami, a jego szczyt kończy się równo z górą kropek. Dzięki temu znak ma u góry jedną równą krawędź. Wysokość i szerokość impulsu wynikają z promienia kropki.
- **Ikona:** ma te same kropki i impuls. Linia jest w niej grubsza względem kropek, żeby była widoczna przy 32 px.
- **Favicon:** impuls jest uproszczony do jednego wysokiego zęba, bo przy 16 px pełny impuls zlewa się w plamę. Kropki są mniejsze niż w ikonie, żeby nie zlewały się z zębem. Favicon ma własny ciemny kafelek, bo Safari kładzie faviconę SVG na jasnym tle i nie stosuje w niej ciemnego motywu.

## Odtworzenie

Wymagania: biblioteka Cairo (`brew install cairo`) i `pip install fonttools cairosvg`. Font jest w katalogu `fonts/`, więc skrypt działa w każdym systemie bez instalowania fontu.

```sh
python3 media/logo/znak.py
```

Skrypt zapisuje wszystkie pliki z tabeli obok siebie, niezależnie od katalogu, z którego go uruchomisz. Z dołączonym fontem daje pliki identyczne z tymi w repozytorium.

## Licencja

Znak i ikony: CC-BY-4.0. Skrypt `znak.py`: MIT. Litery pochodzą z kroju Nunito Sans (© The Nunito Sans Project Authors), zamienione na krzywe; licencja SIL OFL 1.1 pozwala używać kroju w znakach i rozpowszechniać litery w krzywych. Sam font w `fonts/` pozostaje na OFL 1.1. Do wersji 0.5 znak używał kroju Avenir Next, którego licencja z macOS nie obejmuje rozpowszechniania kształtów liter. Szczegóły w [LICENSE.md](../../LICENSE.md).

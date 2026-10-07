# Znak WICI

Napis w kroju Avenir Next Heavy, tym samym co tytuł filmu. Kropki nad literami I wystają ponad napis jak dwa węzły sieci, a między nimi biegnie sygnał z impulsem. Wszystkie litery są w krzywych, więc pliki nie wymagają fontu.

| Plik | Zastosowanie |
|---|---|
| [WICI-na-ciemnym.svg](WICI-na-ciemnym.svg), [.png](WICI-na-ciemnym.png) | ciemne tło: napis biały, sygnał żółty `#f4d345` |
| [WICI-na-jasnym.svg](WICI-na-jasnym.svg), [.png](WICI-na-jasnym.png) | jasne tło: napis `#0f1216`, sygnał przyciemniony do `#c99a00`, bo jasny żółty znika na białym |
| [ikona.svg](ikona.svg), `ikona-512.png` | ikona: dwie kropki i sygnał na kwadracie w kolorze tła filmu `#0f1216` |
| `ikona-180.png` | ikona na ekranie głównym iPhone'a (`apple-touch-icon` stron) |
| `ikona-32.png` | favicon dla przeglądarek bez obsługi SVG |
| [favicon.svg](favicon.svg) | favicon stron: same kropki i sygnał bez tła; kropki ciemne na jasnej karcie, białe na ciemnej |

PNG znaku mają 2400 × 1071 px i przezroczyste tło. Znak jest na górze [głównego README](../../README.md), a ikony i favicon na [stronach koncepcji](../../docs/conception/index.html).

## Użycie

- **Minimalny rozmiar:** znak ma co najmniej 32 px wysokości. Przy 24 px linia sygnału jest jeszcze widoczna, ale impuls zlewa się w kreskę. Poniżej 32 px używaj ikony albo favicony.
- **Pole ochronne:** wokół znaku zostaw wolne miejsce co najmniej na średnicę kropki.
- **Kolory:** używaj tylko dwóch par z tabeli. Sygnał zawsze ma kolor akcentu, a napis i kropki zawsze ten sam kolor.
- **Kształt:** nie składaj nazwy fontem i nie zmieniaj proporcji. Zmiany wprowadzaj w `znak.py` i generuj pliki od nowa.

## Konstrukcja

Wymiary są w jednostkach fontu: 1000 na em, wersalik ma 708.

- **Litery:** W, C i oba I pochodzą bez zmian z Avenir Next Heavy. Odstęp W–I jest z fontu. Dwie pary są poprawione na oko: krągłe C stoi 24 jednostki bliżej pierwszego I, a drugie I stoi 14 jednostek bliżej C, bo otwarcie C samo daje światło.
- **Kropki:** to koła o średnicy 1,06 szerokości pnia I, czyli 254 jednostki. Koło tej samej szerokości co prostokąt wygląda na mniejsze, stąd ta nadwyżka. Nad I jest 70 jednostek światła, podobnie jak między literami (52–76).
- **Sygnał:** ma grubość 52 jednostek. Biegnie pod kropkami i wchodzi do ich środków, więc nigdzie nie kończy się płasko na krągłej krawędzi.
- **Impuls:** stoi w połowie odcinka między kropkami, a jego szczyt kończy się równo z górą kropek. Dzięki temu znak ma u góry jedną równą krawędź. Wysokość i szerokość impulsu wynikają z promienia kropki.
- **Ikona:** ma te same kropki i impuls. Linia jest w niej grubsza względem kropek, żeby była widoczna przy 32 px.
- **Favicon:** impuls jest uproszczony do jednego wysokiego zęba, bo przy 16 px pełny impuls zlewa się w plamę.

## Odtworzenie

Wymagania: macOS z fontem Avenir Next, biblioteka Cairo (`brew install cairo`) i `pip install fonttools cairosvg`.

```sh
python3 media/logo/znak.py
```

Skrypt zapisuje wszystkie pliki z tabeli obok siebie, niezależnie od katalogu, z którego go uruchomisz. Z fontem z macOS 26 daje pliki identyczne z tymi w repozytorium.

## Licencja

Znak i ikony: CC-BY-4.0. Skrypt `znak.py`: MIT. Litery pochodzą z kroju Avenir Next (Monotype), zamienione na krzywe. Szczegóły w [LICENSE.md](../../LICENSE.md).

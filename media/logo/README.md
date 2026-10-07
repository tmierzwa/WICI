# Znak WICI

Napis w kroju Avenir Next Heavy, tym samym co tytuł filmu. Kropki nad literami I wystają ponad napis jak dwa węzły sieci, a między nimi biegnie sygnał z impulsem. Wszystkie litery są w krzywych, więc pliki nie wymagają fontu.

| Plik | Zastosowanie |
|---|---|
| [WICI-na-ciemnym.svg](WICI-na-ciemnym.svg), [.png](WICI-na-ciemnym.png) | ciemne tło: napis biały, sygnał żółty `#f4d345` |
| [WICI-na-jasnym.svg](WICI-na-jasnym.svg), [.png](WICI-na-jasnym.png) | jasne tło: napis `#0f1216`, sygnał przyciemniony do `#c99a00` |
| [ikona.svg](ikona.svg), `ikona-512.png`, `ikona-180.png`, `ikona-32.png` | dwie kropki i sygnał na kwadracie w kolorze tła filmu `#0f1216` |

PNG znaku mają przezroczyste tło i szerokość 2400 px.

## Konstrukcja

Jednostki to jednostki fontu (wersalik = 708).

- **Litery:** W, C i oba I pochodzą bez zmian z Avenir Next Heavy. Odstępy są optyczne, a nie z fontu: krągłe C stoi 24 jednostki bliżej pierwszego I, a drugie I stoi 14 jednostek bliżej C, bo otwarcie C samo daje światło.
- **Kropki:** to koła o średnicy 1,06 grubości pnia I. Koło tej samej szerokości co prostokąt wygląda na mniejsze, stąd ta nadwyżka. Nad I jest 70 jednostek światła, czyli mniej więcej tyle, ile między literami.
- **Sygnał:** ma grubość 52 jednostek i jest czytelny jeszcze przy znaku wysokim na 24 px. Biegnie pod kropkami i wchodzi do ich środków, więc nigdzie nie kończy się płasko na krągłej krawędzi.
- **Impuls:** stoi w połowie odcinka między kropkami, a jego szczyt kończy się równo z górą kropek. Dzięki temu znak ma u góry jedną równą krawędź.
- **Ikona:** ma te same kropki i impuls. Linia jest w niej grubsza względem kropek, żeby była widoczna przy 32 px.

## Odtworzenie

Wymagania: macOS z fontem Avenir Next, `pip install fonttools cairosvg`.

```sh
python3 znak.py
```

# Model kontraktów WICI 0.4

Kod wzorcowy sprawdza ramki P1, format SA1 i atomowy odbiór zgłoszenia w OSP. Nie jest aplikacją stacji, sterownikiem radia ani implementacją Reticulum.

Python 3.12, wyłącznie biblioteka standardowa. Z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 software/reference/obliczenia.py
```

Drugie polecenie zapisuje `wyniki.json` obok skryptu. Są to obliczenia z założeń, nie pomiary. Testy obejmują wszystkie długości datagramu 1–600 B, znany wektor CRC, błędy i duplikaty, sześć typów wiadomości oraz przerwanie transakcji bez ACK. [Zapis weryfikacji](weryfikacja.json) wiąże wynik 19 testów z sumami źródeł.

| Plik | Rola |
|---|---|
| [reference.py](reference.py) | Kodowanie, walidacja i model odbioru OSP |
| [schema.sql](schema.sql) | Schemat SQLite używany przez model |
| [test_reference.py](test_reference.py) | Przypadki akceptacyjne |
| [obliczenia.py](obliczenia.py) | Energia i oszacowania układów |
| [wyniki.json](wyniki.json) | Zapis wyników z założeniami |

Kontrakty: [radio](../../docs/spec/radio.md), [oprogramowanie](../../docs/spec/oprogramowanie.md). Licencja kodu i SQL: [MIT](../../LICENSES/MIT.txt); opisy i raporty: CC-BY-4.0.

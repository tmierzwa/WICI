# Model kontraktów WICI 0.5

Kod wzorcowy sprawdza ramki P1, format SA1, atomowy odbiór zgłoszenia w OSP z kwarantanną nieznanych nadawców oraz przyjmowanie RECEIVED, STATUS, REPLY i BULLETIN przez stację wyłącznie od przypiętej OSP. Nie jest oprogramowaniem stacji, aplikacją laptopa, sterownikiem radia ani implementacją Reticulum.

Python 3.12, wyłącznie biblioteka standardowa. Z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 software/reference/obliczenia.py
```

Drugie polecenie zapisuje `wyniki.json` obok skryptu. Są to obliczenia z założeń, nie pomiary. Testy obejmują wszystkie długości datagramu 1–600 B, znany wektor CRC, błędy i duplikaty, sześć typów wiadomości, przerwanie transakcji bez ACK, kwarantannę i zatwierdzenie nadawcy, zaufanie stacji do OSP oraz zmieszczenie zgłoszenia z przycisków w jednym pakiecie okazjonalnym. [Zapis weryfikacji](weryfikacja.json) wiąże wynik 24 testów z sumami źródeł.

| Plik | Rola |
|---|---|
| [reference.py](reference.py) | Kodowanie, walidacja, model odbioru OSP z kwarantanną i zaufanie stacji |
| [schema.sql](schema.sql) | Schemat SQLite używany przez model |
| [test_reference.py](test_reference.py) | Przypadki akceptacyjne |
| [obliczenia.py](obliczenia.py) | Energia stacji i poziomu 3, budżet W10 przekaźnika, rozmiary SA1, łącze radiowe i oszacowania układów |
| [wyniki.json](wyniki.json) | Zapis wyników z założeniami |

Kontrakty: [radio](../../docs/spec/radio.md), [oprogramowanie](../../docs/spec/oprogramowanie.md). Licencja kodu i SQL: [MIT](../../LICENSES/MIT.txt); opisy i raporty: CC-BY-4.0.

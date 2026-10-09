# R0 — test radia i zasięgu

Dwa zestawy Seeed 102010611, każdy XIAO ESP32S3 + Wio SX1262 z anteną.
Program `pair-0.2` jest diagnostyką surowego LoRa. Test zasięgu nie wymaga
zmiany firmware: odpowiedzią drugiej płytki steruje program na jej Macu.
Brak Reticulum/LXMF, przekazywania pakietów i wiadomości WICI.

Jeśli oba Maki mają internet i Tailscale, użyj [trybu online](ONLINE.md):
niezależne transmisje obu płytek, bieżący feedback i automatyczny koniec.
Poniżej pozostaje tryb offline na miejsca bez połączenia.

## Najpierw przy stole

Zanim rozdzielisz urządzenia, wgraj właściwy program i wykonaj test
100 pakietów w każdym kierunku na jednym Macu według
[instrukcji R0](../l0-diagnostic/reference/R0-INSTRUKCJA.txt).
Jej ścieżki obrazów dotyczą paczki L0; budowa bezpośrednio w tym katalogu:
`.venv/bin/pio run`, następnie `.venv/bin/pio run --target upload --upload-port PORT`.
Zachowaj kopię fabrycznej pamięci przed pierwszym wgraniem.
Nie wgrywaj obrazu L0 do XIAO.

## Dwa Maki — przygotowanie

Na każdym Macu pobierz tę samą wersję repozytorium. W Terminalu przejdź
poleceniem `cd` do `hardware/radio-pair` w pobranym projekcie. Polecenia niżej
wykonuj właśnie tam. Instalację zrób przed wyjściem, gdy masz internet:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/pair_test.py --list
```

Na każdym Macu podłącz jedną płytkę przewodem USB danych. Antenę podłącz
przy wyłączonym zasilaniu. Z wyniku `--list` przepisz właściwy port zamiast
`PORT`, np. `/dev/cu.usbmodem12301`. Numery portów mogą się zmienić.
Zamknij inne monitory portu USB. Wyłącz usypianie laptopów na czas próby,
nie zamykaj pokrywy; sprawdź akumulatory i zapas na powrót.
Test nie wymaga internetu, Wi-Fi, wspólnego zegara ani połączenia laptopów.
Potrzebne są dwie osoby i uzgodniony sposób ustalenia początku/końca próby.

Zrób najpierw krótką próbę tego trybu przy stole: na obu Macach użyj
`--count 3`. Trzy odebrane pakiety nie zaliczają pełnego testu.

## Jeden punkt pomiarowy

Ustaw jeden zestaw w stałym miejscu, drugi w punkcie P01. Podczas próby
nie przenoś urządzeń. Anteny ustaw tak samo w kolejnych punktach; laptop,
ciało i metalowe powierzchnie mogą zmieniać warunki odbioru.
W opisie wpisz rzeczywistą odległość, położenie obu urządzeń, wysokość
anten, ich orientację oraz przeszkody. W budynku zapisz piętra i pomieszczenia.

**Najpierw Mac B (odpowiadający):**

```sh
.venv/bin/python tools/range_test.py run --role B --port PORT --point P01 --notes 'B: punkt docelowy; uzupelnij polozenie, antene i przeszkody' --count 100
```

Poczekaj na `GOTOWE: radio i USB potwierdzone`. B pozostaje w nasłuchu.

**Następnie Mac A (inicjujący):**

```sh
.venv/bin/python tools/range_test.py run --role A --port PORT --point P01 --notes 'A: punkt bazowy; uzupelnij polozenie, antene i odleglosc do B' --count 100
```

A wysyła 100 numerowanych pakietów co 6 sekund. B na każdy odebrany
pakiet odpowiada raz, bez ponawiania. A kończy po około 10 minutach.
Na B dopiero potem naciśnij **Ctrl+C**, aby zamknąć i zapisać raport.
Brak odpowiedzi radiowej nie zatrzymuje próby; brak USB, restart lub błąd
urządzenia zatrzymuje ją i zapisuje przyczynę. Zatrzymanie A przed końcem
oznacza próbę nieukończoną. B nie ma automatycznego końca, ponieważ może
nie odebrać ostatnich pakietów; przed przejściem do kolejnego punktu
zatrzymaj B i uruchom oba programy od nowa z nową nazwą punktu.

## Zebranie wyników

Każdy Mac wypisuje nazwę swojego raportu i zapisuje go w `results/`:
JSON z identyfikatorem płytki, restartu, profilem i pakietami oraz JSONL
z czasami i surowymi odpowiedziami USB. Zachowaj oba pliki z każdego Maca.
Po próbie skopiuj raporty JSON A i B do jednego katalogu na jednym Macu.
Nie potrzeba robić tego w terenie. Przykład po nazwaniu kopii `P01-A.json`
i `P01-B.json`:

```sh
.venv/bin/python tools/range_test.py summarize --a results/P01-A.json --b results/P01-B.json --output results/P01-podsumowanie.json
```

Podsumowanie sprawdza zgodność punktu, sesji, profilu i dwóch różnych
płytek, potem porównuje dokładną treść wysłanych i odebranych pakietów.
Pokazuje A→B i B→A, straty, RSSI/SNR i błędy. `valid_trial=true` oznacza
poprawnie przeprowadzoną próbę, także przy stratach radiowych.
`passed=true` wymaga 100/100 w obu kierunkach i braku błędów.
`false` nie zawsze oznacza awarię — przeczytaj liczniki i przyczynę.

**Ważne dla interpretacji:** B odpowiada tylko po odebraniu A. Jeśli A→B
nie dochodzi, B wysyła mniej niż 100 odpowiedzi. Wynik 90/90 B→A nie jest
zaliczeniem 100/100. Brak odpowiedzi na A sam nie rozstrzyga, w którym
kierunku pakiet zginął; rozstrzygają logi obu Maców.
Aby zbadać oba kierunki ze 100 niezależnymi transmisjami, powtórz próbę
w tych samych położeniach, zamieniając role programów: dawny B uruchom jako
A, dawny A jako B. Daj nową nazwę punktu, np. `P01-odwrotnie`.

## Kolejność prób i decyzje

1. Próba przy stole: sprzęt/program działają, 100/100 w obu kierunkach.
2. Punkty w budynku: pokoje, piętra, piwnica, jeśli jest istotna dla WICI.
3. Punkty terenowe: stała baza i kolejne rzeczywiste miejsca użycia.
4. Powtórka punktów na granicy działania; powtórka z odwróconymi rolami.
5. Po błędzie USB lub restarcie popraw przyczynę i powtórz punkt.
   Po stratach RF zapisz wynik; sprawdź ustawienie/otoczenie i zrób osobną
   powtórkę. Nie usuwaj nieudanego pomiaru ani nie obniżaj progu pod wynik.

Wynik to lista sprawdzonych połączeń, nie uniwersalny zasięg w kilometrach.
Dotyczy anten zestawu i profilu 869,525 MHz, BW 125 kHz, SF7, CR4/5,
mocy 0 dBm. Nie kwalifikuje docelowej obudowy, innych anten, baterii,
sieci wielowęzłowej ani pełnej aplikacji WICI. Nie zmieniaj parametrów
radiowych w trakcie serii pomiarów.

Testy automatyczne narzędzia są wykonywane z rzeczywistym pyserial przez
symulowane porty PTY. Nie są pomiarem fizycznego USB ani zasięgu radia.

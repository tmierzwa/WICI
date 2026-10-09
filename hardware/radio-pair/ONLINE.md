# R0 — test zasięgu online przez Tailscale

Każdy Mac ma jedną płytkę R0 i dostęp do internetu. Tailscale jest już
zainstalowany; oba Maki muszą być połączone z tą samą siecią Tailscale
z możliwością połączenia między urządzeniami.

Mac A prowadzi próbę. Mac B dołącza. Programy uzgadniają kolejność przez
internet, a płytki **niezależnie nadają po 100 pakietów przez LoRa**.
B nadaje również wtedy, gdy nie odebrało poprzedniego pakietu A.
Na obu ekranach widać dla każdego pakietu odbiór/stratę oraz RSSI/SNR.
Jedna próba trwa co najmniej 10 minut; opóźnienia internetu wydłużają ją.
Nie wymaga synchronizacji zegarów Maców.

## 1. Przygotowanie przed wyjściem

Najpierw zalicz próbę radia przy stole według [instrukcji R0](README.md).
Program płytek pozostaje `pair-0.2`; tryb online uruchamia się na laptopach.
Na obu Macach pobierz tę samą aktualną wersję repozytorium i otwórz
Terminal w `hardware/radio-pair`:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/pair_test.py --list
```

Przepisz właściwy port USB każdego Maca zamiast `PORT_A` / `PORT_B`.
Podłącz anteny przy wyłączonym zasilaniu, używaj przewodów USB danych,
zostaw pokrywy otwarte i wyłącz usypianie na czas pomiaru.

W menu Tailscale znajdź **adres IPv4 Maca A**, np. `100.101.102.103`.
W poleceniach niżej zastąp `IP_MAC_A` rzeczywistym adresem.
Adres Maca A jest taki sam w obu poleceniach, również na Macu B.
Nie wpisuj publicznego adresu IP, nie przekierowuj portów routera.
Narzędzie akceptuje tylko zakres IPv4 Tailscale i adres lokalny do testów.
Szyfrowanie połączenia zapewnia Tailscale; sam protokół TCP nie ma TLS.

Utwórz klucz na Macu A:

```sh
.venv/bin/python tools/range_online.py --make-key secrets/range.key
```

Skopiuj plik `secrets/range.key` na Maca B, np. przez AirDrop, do tego
samego katalogu względem `hardware/radio-pair`. Klucz musi być identyczny.
Katalog `secrets/` jest ignorowany przez Git. Nie dodawaj klucza do logów
ani repozytorium. Jeśli plik już istnieje, generator go nie nadpisze.

## 2. Krótka próba przy stole na dwóch Macach

**Najpierw Mac A:**

```sh
.venv/bin/python tools/range_online.py --role A --address IP_MAC_A --key-file secrets/range.key --port PORT_A --point STOL --notes 'A: stol, antena pionowo' --count 3
```

Poczekaj na `Czekam na Mac B`.

**Następnie Mac B:**

```sh
.venv/bin/python tools/range_online.py --role B --address IP_MAC_A --key-file secrets/range.key --port PORT_B --point STOL --notes 'B: stol, antena pionowo, odleglosc 2-3 m' --count 3
```

Mac A czeka do 120 sekund na dołączenie B. Oba programy kończą się
automatycznie. Próba 3 pakietów sprawdza przygotowanie, ale nie zalicza
pełnego testu. Jeśli zapora macOS pyta o zgodę na połączenia przychodzące
Pythona, zezwól dla programu wykonującego test. W razie braku połączenia
sprawdź Tailscale na obu Macach, właściwy adres A, klucz i zaporę.
Nie wyłączaj zapory globalnie.

## 3. Punkty terenowe

Powtórz te same polecenia z `--count 100`, nazwą punktu np. `P01`
i rzeczywistymi opisami. **Nazwa punktu i liczba pakietów muszą być
identyczne na obu Macach.** Zapisz położenie, dystans, wysokość/orientację
anten, przeszkody, pomieszczenia/piętra. Podczas próby stój w miejscu.

Transmisje są naprzemienne A→B, B→A, z oknem odbioru minimum 3 sekundy
na pakiet. Internet potwierdza gotowość i przenosi odczyty USB; nie dostarcza
pakietu LoRa do płytki ani nie ponawia strat. Przy opóźnieniach internetowych
kolejne transmisje są odraczane, zamiast nakładać się na siebie.

Bieżący komunikat `ODEBRANO` wymaga jednego poprawnego potwierdzenia TX
z płytki nadawcy i jednego odbioru dokładnej treści przez USB płytki odbiorcy.
`STRATA / DUPLIKAT` nie jest błędem internetu. Brak potwierdzenia TX,
restart lub brak USB unieważnia próbę.

## 4. Wynik i przerwanie

Oba Maki zapisują w `results/`:

- lokalny raport JSON;
- surowe odpowiedzi USB JSONL z czasami;
- kopię odebranych zdarzeń partnera w `*-peer.json`;
- podsumowanie `*-summary.json`, jeśli uzgodniona próba została ukończona.

Podsumowanie daje osobne liczniki A→B i B→A, straty i RSSI/SNR.
`valid_trial=true` oznacza poprawną próbę także przy stratach LoRa.
`passed=true` wymaga 100/100 w obu kierunkach i braku błędów.
Zachowaj oryginalne lokalne logi **obu** Maców — kopia partnera obejmuje
zdarzenia przekazane przez kanał sterowania, nie zastępuje jego surowego logu.

Utrata internetu zatrzymuje kolejne transmisje, zapisuje błąd kategorii
`internet` i nie zalicza próby. Błąd USB partnera przekazany przed
rozłączeniem ma kategorię `peer-usb`, a lokalny błąd USB — `usb`. Logi USB pozostają lokalnie. Ctrl+C przerywa
próbę; partner również zatrzyma się po zamknięciu połączenia.
Jeżeli kanał internetowy nie działa, uruchom nową próbę
[offline](README.md) z nową nazwą punktu. Nie łącz wyników dwóch trybów
jako jednej próby i nie traktuj przerwanej sesji jako wyniku zasięgu.

Wynik dotyczy profilu R0 (SF7, 0 dBm) i użytych anten, a nie wszystkich
ustawień LoRa. Punkty na granicy działania powtórz. Ten test nie kwalifikuje
baterii, pełnej aplikacji WICI ani sieci wielowęzłowej.

Połączenie przez Tailscale:
[łączenie urządzeń](https://tailscale.com/docs/how-to/connect-to-devices).

# WICI: oprogramowanie stacji

**Stan programu stacji (krok 4 planu).** Pilotaż używa stacji z ESP32-S3 i układem LoRa SX1262: prototyp na płytce v1, potem stacje pilotażowe na płytce v2 ([plan](../docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)). Obraz [`l0`](docs/prototyp-l0-i-xiao.md#stacja-l0-l0) ma sterownik SX1262 w profilu LoRa z poleceniami pomiarowymi i [interfejs LoRa w stosie](docs/prototyp-l0-i-xiao.md#interfejs-lora-stosu): format w eterze zgodny z RNode, cisza 12t, IFAC ([profil LoRa](../docs/spec/radio.md#profil-lora-pilotażu)). Na komputerze przechodzi próbę zgodności z `RNodeInterface` przez emulator radia RNode; na sprzęcie nie był uruchomiony, więc następna jest [procedura kroku 4](docs/prototyp-l0-i-xiao.md#krok-4-interfejs-lora-z-radiem-rnode) z RAK4631. Środowisko `l0` to nazwa PlatformIO obrazu prototypu; w `hardware/l0-diagnostic` jest osobne środowisko `l0` programu diagnostycznego (inny program, wersje `l0-0.5`).

Tu jest to, czego potrzeba na co dzień: wybór środowiska, budowa i wgranie obrazu, testy. Resztę opisują [pliki w `docs/`](#opis-szczegółowy).

## Środowiska

Środowiska są zdefiniowane w [platformio.ini](platformio.ini). Domyślnie obrazy mają rdzeń Reticulum stacji; obrazy `*-port` mają port microReticulum i znikną w etapie rdzenia 6-5 ([wybór stosu](docs/stos.md#wybór-stosu-port-albo-rdzeń)).

| Środowisko | Sprzęt | Do czego | Stan |
|---|---|---|---|
| `l0`, `l0-port` | prototyp: ESP32-S3-DevKitC-1-N8R8 + Wio-SX1262 na płytce v1 | program stacji prototypu, profil LoRa, interfejs LoRa zgodny z RNode ([opis](docs/prototyp-l0-i-xiao.md#stacja-l0-l0)) | skompilowany; na prototypie jeszcze nie działał |
| `v2` | prototyp płytki v2: to samo z torem zasilania z ogniw i 12 V, wyłącznikiem i wykrywaniem laptopa | program stacji jak `l0`, pomiar 12 V, lekkie uśpienie `NAP` i [pętla czuwania](docs/prototyp-l0-i-xiao.md#pętla-czuwania-v2) ([opis](docs/prototyp-l0-i-xiao.md#prototyp-płytki-v2-v2)) | skompilowany; płytki v2 jeszcze nie ma |
| `xiao` | zestaw Seeed XIAO ESP32-S3 + Wio-SX1262 (bez ekranu i FRAM) | dodatkowe stacje w próbach przy stole ([opis](docs/prototyp-l0-i-xiao.md#zestaw-xiao-xiao), [procedura](../hardware/xiao-wici/README.md)) | używany w próbach przy stole od 2026-11-02 |
| `host`, `host-port` | komputer | węzeł stacji na komputerze: próby zgodności z Reticulum w Pythonie, próby wrogiego ruchu, emulator ([stos](docs/stos.md#próba-zgodności-z-reticulum)) | w CI |
| `bench-a`, `bench-n1`, `bench-b` i ich `*-port` | stanowiska deweloperskie A i B (nRF52840 + CC1120, ESP32-S3 + S2-LP) | wstrzymany profil P1 ([opis](docs/stanowiska-a-b.md), [archiwum](../docs/archiwum/README.md)) | wstrzymane 2026-10-08; nie dla prototypu |

Program diagnostyczny prototypu (`l0-0.5`) to inny program, w [hardware/l0-diagnostic](../hardware/l0-diagnostic/README.md), z własnym środowiskiem `l0`. Nie wgrywa się go z tego katalogu.

## Budowa, wgranie i testy

PlatformIO działa w osobnym środowisku Pythona 3.10–3.14 ([narzędzia](../docs/development.md#oprogramowanie-układowe)):

```bash
python3.14 -m venv .venv-pio && .venv-pio/bin/pip install platformio
cd firmware && ../.venv-pio/bin/pio run -e l0              # budowa obrazu prototypu
cd firmware && ../.venv-pio/bin/pio run -e l0 -t upload    # wgranie przez USB DevKitC
```

Samo `pio run` buduje domyślne `bench-a`, więc środowisko podaje się zawsze przez `-e`. Polecenia diagnostyki na porcie USB opisuje [lista poleceń](docs/polecenia.md#polecenia). Testy programu stacji na komputerze są w `tests/` w katalogu głównym (`python3 -m unittest discover -s tests -v`); część wymaga kompilatora C++, PlatformIO albo Reticulum w Pythonie i bez nich się pomija.

## Stacja L0 (l0)

Piny, sterownik SX1262, interfejs LoRa stosu, procedurę kroku 4 z radiem RNode i próby rdzenia na prototypie opisuje [plik o prototypie](docs/prototyp-l0-i-xiao.md#stacja-l0-l0). Ten obraz wgrywa się (`pio run -e l0 -t upload`), gdy prototyp przejdzie odbiór programem diagnostycznym.

## Jak działa program

Ruch idzie przez [stos Reticulum](docs/stos.md#stos-reticulum) z interfejsem P1 (w `l0` i `l0-port` z interfejsem LoRa), IFAC, tożsamością i tablicami w FRAM. Od etapów rdzenia 6-3 i 6-4 obrazy stacji mają rdzeń Reticulum stacji ([reticulum-core.md](reticulum-core.md)), który wysyła treść jako wiadomości LXMF z podpisem stacji. Ten sam program z portem microReticulum (pakiety okazjonalne z potwierdzeniem transportowym i zastępczą kopertą z adresem nadawcy bez podpisu) budują do etapu rdzenia 6-5 obrazy `*-port` ([wybór stosu](docs/stos.md#wybór-stosu-port-albo-rdzeń)).

Stacja ma jedną rolę (D19): w [konfiguracji węzła stanowiska](docs/stos.md#węzeł-stanowiska) przekazuje ruch i łączy radio z komputerem stanowiska drugim interfejsem Reticulum przez USB.

**Obrazy z rdzeniem są domyślne, ale nie przeszły jeszcze prób na płytkach.** Etapy rdzenia 6-3 i 6-4 są w `main` przed [próbami 1–8](docs/stos.md#przejście-na-rdzeń-i-powrót-do-portu); sprawdzenia na komputerze (testy, zgodność z Reticulum w Pythonie, fuzzing) nie zastępują prób kryptografii, RAM, radia, USB, zaniku zasilania i długiej pracy na płytce. Próby 1–8 są warunkiem pilotażu i wydania, ale nie scalania zmian. Obrazy `*-port` są wyjściem awaryjnym do etapu rdzenia 6-5, który usunie port.

## Rozmiar obrazów

Obrazy skompilowano w PlatformIO. Pomiar z 2026-10-24 (`main` 31f3f06 z etapami rdzenia 6-3 i 6-4):

- rdzeń Adafruit nRF52 1.7.0: `bench-a` 112 276 B RAM statycznej, 408 420 B flash; `bench-n1` 112 488 B RAM, 417 496 B flash;
- Arduino-ESP32 3.3.12: `l0` 159 136 B RAM z 327 680 B, 626 561 B flash; `bench-b` 159 176 B RAM, 627 185 B flash.

Obrazy z portem i podział są w [pomiarze RAM](docs/stos.md#pamięć-ram) i [przeglądzie rozmiaru](docs/stos.md#rozmiar-i-wydajność). **Żadnego obrazu nie uruchomiono na sprzęcie**: odpowiedzi poleceń, numery pinów, działanie SPI z modułem, przyjęcie rejestrów przez układ, USB i łącze radiowe trzeba sprawdzić na płytce według kroków opisanych niżej. Na hoście sprawdzono tylko:

- moduły bez Arduino, sterowniki S2-LP i SX1262 oraz ich sterowniki łącza z modelem układu, `measure::Bench` ze sterownikiem zastępczym, tablicę rejestrów S2-LP i zgodność pinów `bench-b` z [połączeniami](../hardware/dev-bench/polaczenia.md) (`tests/`);
- stos Reticulum z interfejsem P1 w programie na komputerze, z emulatorem łącza, wobec Reticulum w Pythonie ([próba zgodności](docs/stos.md#próba-zgodności-z-reticulum)).

## Opis szczegółowy

| Plik | Zawartość |
|---|---|
| [Prototyp L0, płytka v2 i zestaw XIAO](docs/prototyp-l0-i-xiao.md) | piny, sterownik SX1262, interfejs LoRa stosu, krok 4 z radiem RNode, próby rdzenia na prototypie, płytka v2, lekkie uśpienie, pętla czuwania, zestaw XIAO |
| [Stos Reticulum, rdzeń i port](docs/stos.md) | stos, zależności i łaty, węzeł stanowiska, tożsamość i tablice w FRAM, próba zgodności z Reticulum, wybór stosu, przejście na rdzeń, samotest, pamięć RAM, rozmiar i wydajność |
| [FRAM, ekran, protokół USB i warstwa aplikacji](docs/aplikacja.md) | dziennik i magazyny w FRAM, ekran i przyciski, przeglądy kodu, protokół USB laptop–stacja, warstwa aplikacji |
| [Narzędzia i polecenia diagnostyki](docs/polecenia.md) | PlatformIO i wgrywanie, polecenia na porcie diagnostyki, polecenia pomiarowe, tryb do badań EMC |
| [Stanowiska A i B (wstrzymane)](docs/stanowiska-a-b.md) | obrazy `bench-*`: okablowanie, płytka nośna N1, stanowisko B, rejestry profilu P1, łącze P1 |
| [Rdzeń Reticulum stacji](reticulum-core.md) | rdzeń z LXMF: wymagania, etapy, licencja i autorstwo |

## Następne kroki

1. Próby na sprzęcie według [opisu prototypu](docs/prototyp-l0-i-xiao.md#stacja-l0-l0) i [stanowisk](docs/stanowiska-a-b.md) (obraz nie był jeszcze uruchomiony na płytce), na płytce v1 także pomiar oscyloskopem przy J7 i U1 (ekran 1 i 2 MHz, FRAM 8 MHz, poziomy i zbocza); węzeł stanowiska z komputerem stanowiska przez USB.
2. Próby 1–8 rdzenia na płytkach z [listy](docs/stos.md#przejście-na-rdzeń-i-powrót-do-portu) na obrazach końcowych (warunek wydania i pilotażu na rdzeniu), potem usunięcie portu (etap rdzenia 6-5); z nich decyzja o pamięci (D14) i reszta [etapu LXMF](docs/stos.md#co-zostaje-na-etap-lxmf).
3. Próby stosu na sprzęcie z [listy](docs/stos.md#próba-zgodności-z-reticulum), których nie obejmują próby 1–8: płytka z Reticulum w Pythonie przez radio, czasy kryptografii przy `-Os`. Na prototypie to [krok 4 z radiem RNode](docs/prototyp-l0-i-xiao.md#krok-4-interfejs-lora-z-radiem-rnode) i [próby rdzenia przez LoRa](docs/prototyp-l0-i-xiao.md#próby-rdzenia-na-prototypie).
4. Stanowisko B (`bench-b`), w tej kolejności:
   - kroki B3–B4 na sprzęcie, w tym wyliczenie dwóch portów CDC, wgrywanie przez dotknięcie 1200 b/s i to, czy restart przez watchdog zadań daje `esp_reset_reason()` = TASK_WDT, a nie PANIC (od tego zależy wpis „restart by watchdog”);
   - wybór napędu SCK i MOSI (`DRIVE`) i zegara ekranu analizatorem na J11;
   - łącze między A i B: `TXPKT`/`RX`/`RXPER` w obie strony i `P1TX`/`P1RX` (potwierdzenie kolejności bajtów słowa synchronizacji w eterze; przy braku odbioru zamiana kolejności `REGW 33..36` w trybie przygotowania, `CONFIG` przywraca tablicę), `TXCW` z miernikiem częstotliwości i `FOFF`;
   - odbiór serii ramek bez przerw na B (`TXPKT 50 103 0` z A, `RXPER` na B przy odświeżanym ekranie STAN): sterownik odrzuca ramkę, gdy w kolejce RX jest już początek następnej (pętla stała dłużej niż około 20 ms); przy stratach odczyt tylko długości ramki z pozostawieniem reszty kolejki;
   - przesunięcie RSSI modułu (wpływa na próg CCA −100 dBm i `rssi_avg_dbm`), ustawienia AFC, AGC i odtwarzania zegara symboli przy pomiarze czułości (T4);
   - przegląd tablicy S2-LP w ST STSW-S2LP-DK (S2-LP DK GUI) dla P1, gdy narzędzie będzie dostępne; pomiar mocy i dobór PA_POWER oraz SMPS;
   - własne nazwy interfejsów CDC („WICI diagnostyka”, „WICI dane”) wymagają zmiany w rdzeniu Arduino-ESP32 (nazwy są stałe w `USBCDC.cpp`) albo własnych deskryptorów TinyUSB.
5. Prototyp (`l0`): punkty próby z [opisu](docs/prototyp-l0-i-xiao.md#stacja-l0-l0) (punkty 1–3 obrazem stacji, moc i częstotliwość, cykl pracy, czasy, brak emisji 2,4 GHz), potem [krok 4](docs/prototyp-l0-i-xiao.md#krok-4-interfejs-lora-z-radiem-rnode): wymiana z RAK4631 (potwierdza też preambułę i słowo synchronizacji, T3), CAD z sąsiednią stacją, progi CAD i RSSI dla CCA (T4). Wynik kroku 4 rozstrzyga, czy płytka v2 potrzebuje osobnej magistrali SPI dla radia.
6. Dioda alarmu i brzęczyk na płytce v1: jasność błysku 50 ms przy 1 mA i głośność sygnałów do oceny na płytce; przypomnienie `wymien_ogniwa` z pomiarem ogniw (tor zasilania z ogniw ma dopiero płytka v2).

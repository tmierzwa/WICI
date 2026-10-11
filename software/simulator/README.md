# Symulator stacji WICI

Stacja WICI w przeglądarce, do pokazów, szkolenia opiekunów i oceny projektu panelu. Online: [wici.net.pl/symulator](https://wici.net.pl/symulator/) (po publikacji `main`); lokalnie:

```sh
python3 -m http.server -d software/simulator/web 8000   # potem http://localhost:8000/
```

Strona nie ma zależności zewnętrznych i działa offline. Plik `index.html` otwarty bezpośrednio z dysku nie wczyta modułów (przeglądarki blokują je z `file://`), dlatego potrzebny jest serwer HTTP.

## Ten sam program co na płytce

Stacja i węzeł stanowiska w symulatorze to **obraz bench-b** (`firmware/platformio.ini`, `[env:bench-b]`: ESP32-S3 DevKitC + S2-LP na płytce nośnej N1), skompilowany z tych samych plików i flag:

| Co | Jak w symulatorze |
|---|---|
| Pliki `firmware/src` | dokładnie te, które wybiera `build_src_filter` środowiska bench-b (`build.py` czyta `platformio.ini`); bez zmian i bez `#ifdef` symulatora |
| Flagi | `build_flags` bench-b z `platformio.ini` (z `-DWICI_BENCH_B`, wersją, flagami stosu) i flagi C++ pre-skryptu stosu; do tego makra rdzenia Arduino-ESP32 (`ARDUINO`, `ARDUINO_ARCH_ESP32`, `ESP32`) |
| Stos Reticulum | microReticulum, microStore (z łatami WICI), Crypto, MsgPack, Arx*, DebugLog, ArduinoJson z commitów pinowanych w `firmware/tools/stack_deps.py` |
| Zastąpione pliki (`REPLACED`) | tylko warstwa MCU: `platform_esp32.cpp` → `hal/platform_sim.cpp` i `sharp_extcomin_esp32.cpp` → `hal/sharp_extcomin_sim.cpp`; ten sam interfejs `platform.h` (test to sprawdza) |
| Rdzeń Arduino-ESP32 i ROM | `hal/`: `Arduino.h`, `SPI.h`, `USB.h`, NVS, watchdog zadań, `esp_attr.h` (pamięć RTC niezerowana przy restarcie), AES akceleratora (`esp_aes_*`, FIPS-197) i TLSF (kopia ze stosu) |
| Układy na płytce | emulowane na magistrali SPI, więc ich sterowniki działają bez zmian: S2-LP (rejestry, FIFO, przerwania na GPIO, czasy pakietu z rejestrów MOD i PCKTCTRL, RSSI, kolizje), FRAM CY15B104Q, panel Sharp LS027B7DH01A (protokół bitowy, EXTCOMIN) |
| Czas | zegar wirtualny: każdy bajt SPI trwa 8/f, `delay` i oczekiwania zajmują czas, pętla programu stoi w czasie nadawania i rysowania ekranu jak na płytce |

`web/build.json` zapisuje listę plików, flagi, commity stosu i sumy SHA-256 wszystkich wejść; `tests/test_simulator.py` odrzuca obraz niezgodny z bieżącym `firmware/src`, `platformio.ini`, pinami lub łatami stosu, więc zmiana oprogramowania bez przebudowy symulatora nie przejdzie kontroli.

Modelami pozostają:

| Część | Model |
|---|---|
| Eter | tłumienie trasy stacja–węzeł (domyślnie 100 dB, suwak w *Warunkach*), zanik o rozkładzie normalnym σ = 4 dB na ramkę, moc z rejestrów S2-LP, czułość −112 dBm, kolizje ramek nakładających się w czasie |
| Komputer stanowiska | `post/post.cpp`: aplikacja na tym samym stosie (microReticulum, interfejs KISS do portu danych węzła, tożsamość główna i zapasowa, dowody `PROVE_ALL`), z modułami `sa1`, `store`, `framfs` z `firmware/src`. To model aplikacji stanowiska, nie sama aplikacja: ma włączony transport (microReticulum zakłada magazyny tożsamości i tras tylko w tym trybie) |
| Zasilanie | wyłącznik R02 albo wtyk USB N1; obraz bench-b nie mierzy napięcia (ekran podaje „12 V: 0,0 V”) |
| Człowiek | przycisk zmienia tylko poziom pinu; czy program go odczyta, zależy od programu |

Sieć ćwiczeniowa powstaje jak w terenie: stanowisko podaje kartę odbiorcy, węzeł i stacja są przygotowywane protokołem USB `"usb":2` (przytrzymanie przycisku przygotowania, `configure`, ponowne przytrzymanie), z kluczem sieci ćwiczeniowej (nie polowym). Stan po przygotowaniu (FRAM, NVS, dysk komputera stanowiska) jest obrazem, z którego startuje każde ćwiczenie.

## Zastosowania

- **Pokaz.** Praca swobodna: stacja jest włączona i ma trasę do stanowiska; *Dyżurny* odpowiada, wysyła komunikaty, podejmuje decyzje i przełącza tożsamość, *Warunki* zmieniają tłumienie, przerywają łącze, wyłączają węzeł i wprowadzają awarie (S2-LP, FRAM). Czas można przyspieszyć (×10, ×60) albo przeskoczyć (+1 min, +15 min, +1 h).
- **Szkolenie.** Osiem ćwiczeń według [karty obsługi](../../docs/spec/karta.md) i [instrukcji opiekuna](../../docs/spec/instrukcja.md): uruchomienie, pierwsze zgłoszenie, zmiana liczby osób, zagrożenie życia bez łączności, cisza radiowa, odpowiedź „nie może pomóc”, klucz zapasowy, zanik zasilania. Kroki sprawdza się tak jak człowiek: tekst odczytany z pikseli panelu, aplikacja stanowiska, położenie przełącznika.
- **Projekt panelu.** Układy R02 i N1 w milimetrach. R02 wygląda jak render koncepcyjny obudowy z 2026-10-11 (`hardware/obudowa/render/stacja.html`, gałąź `obudowa-szkielet`): czarna Hammond 1599KBAT, folia z logo i nadrukiem w trzech językach, kolumna ALARM–CISZA RADIOWA–WYŁĄCZNIK, złącza na dolnej ściance i pole SERWIS: przycisk przygotowania pod numerowaną naklejką VOID (pierwsze dotknięcie przebija naklejkę jak rysik w terenie; ekran pokazuje wtedy pasek TRYB SERWISOWY, `tryb_przygotowania` w oprogramowanie.md). Dalej: skala 1:1 z kalibracją kartą płatniczą, zasady panelu sprawdzane na żywo, przesuwanie elementów (układ Własny, eksport JSON), droga palca i czas ruchu z prawa Fittsa na tym samym przebiegu.
- **Uruchamianie.** *Konsola* to port diagnostyki USB płytki (`HELP`, `INFO`, `RNS`, `STORE`, `JOURNAL`, `SCREEN`, `VTEST`…) stacji albo węzła; *Dziennik* pokazuje restarty, ramki w eterze i zdarzenia stanowiska.

Klawiatura: ↑ GÓRA, ↓ DÓŁ, Enter OK, Backspace albo Esc WSTECZ; przytrzymanie działa jak na stacji.

## Obserwacje z obrazu bench-b

Symulator pokazuje zachowanie samego oprogramowania, także to, którego nie widać w testach modułów:

- Pętla programu stoi w czasie nadawania ramki (ogłoszenie ok. 0,6 s) i odświeżania ekranu (ok. 0,1 s przy SPI 1 MHz); krótsze naciśnięcie w tym czasie przepada. Ekran nadąża za naciśnięciem z opóźnieniem ok. 0,3 s.
- Ekran wyniku zgłoszenia pokazuje tekst `zapisz_numer`, przeznaczony na stronę mieszkańców.
- Limit 2 % czasu nadawania na ogłoszenia daje w węźle mniej więcej jedno przekazane ogłoszenie na 6 min; stanowisko poznaje nową stację dopiero z jej ogłoszenia.

## Pliki

| Plik | Zawartość |
|---|---|
| `build.py` | budowa obrazów: `web/wici-station.mjs` (stacja i węzeł), `web/wici-post.mjs` (komputer stanowiska), `web/build.json`; `--native` (program dla hosta), `--check`, `--sources` |
| `hal/` | wirtualna płytka: rdzeń Arduino-ESP32, emulatory układów, zastępcze pliki MCU, funkcje ROM |
| `post/post.cpp` | aplikacja komputera stanowiska na stosie Reticulum |
| `cli.cpp` | jedno urządzenie jako proces (polecenia płytki ze stdin, `run <µs>`) |
| `web/device.js`, `web/world.js`, `web/sim.js` | urządzenie (instancja WebAssembly, restarty z przeniesieniem FRAM, NVS i pamięci RTC), świat (eter, USB, przygotowanie), symulacja ćwiczeń |
| `web/index.html`, `app.js`, `app.css`, `layouts.js`, `scenarios.js` | strona, układy paneli i zasady, ćwiczenia |
| `test_scenarios.mjs` | przejście każdego ćwiczenia jego przykładowym przebiegiem na zbudowanych obrazach (Node) |

## Budowa i kontrola

```sh
emsdk install 3.1.74 && emsdk activate 3.1.74 && source emsdk_env.sh
python3 software/simulator/build.py           # web/*.mjs i web/build.json (stos pobierany do firmware/.pio/stack)
python3 software/simulator/build.py --check   # czy obrazy odpowiadają źródłom
node software/simulator/test_scenarios.mjs    # ćwiczenia na obrazach
python3 -m unittest tests.test_simulator -v
```

Test sprawdza aktualność obrazów, zgodność zestawu plików i flag z bench-b, interfejs zastąpionych plików, brak zaczepów symulatora w `firmware/src`, AES z wektorami FIPS-197, wszystkie ćwiczenia i zasady panelu.

Nowe ćwiczenie dopisuje się w `web/scenarios.js` razem z przykładowym przebiegiem (`solution`, działania jak w `Simulation.act`: `press`, `hold`, `wait`, `power`, `switch`, `link`, `loss`, `fault`, `post …`, `boot`); test sprawdza, że przebieg kończy ćwiczenie na prawdziwym oprogramowaniu.

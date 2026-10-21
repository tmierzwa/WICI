# Aplikacja laptopa WICI

Panel w przeglądarce do pracy ze stacją przez USB, uruchamiany z pamięci USB zestawu na Windows, macOS i Linuksie, bez instalowania. Obsługuje tryb przygotowania (konfigurację stacji i węzła stanowiska, odczyt konfiguracji i kartę stacji) oraz zestaw na pamięci USB: konta i hasła z kopert, logowanie, zaszyfrowaną bazę z dziennikiem, „Oddaj laptop” i ZNISZCZ DANE. Zakres, decyzje, rozmiar, laptop i router na miejscu oraz dalsze etapy opisuje [plan](PLAN.md); kontrakt ze stacją jest w [protokole USB](../../docs/spec/protokol-usb.md).

## Uruchomienie podczas pracy nad kodem

Wymagany Python 3.12 lub nowszy, bez dodatkowych pakietów. Z katalogu `software/laptop`:

```sh
python3 -m wici                      # wyszukuje stację na portach USB i otwiera panel
python3 -m wici --port /dev/ttyACM1  # wskazany port (Windows: COM5)
```

Bez płytki: stacja z symulatora (obraz firmware bench-b w WebAssembly, wymaga Node.js) z portem danych na TCP.

```sh
node dev/sim-station.mjs 7300        # w drugim terminalu; `prep` przytrzymuje przycisk przygotowania, `press OK` naciska OK
python3 -m wici --port tcp:127.0.0.1:7300
```

Uruchomiony ze źródeł panel trzyma konta i kopię bazy w katalogu `pamiec-usb` w katalogu stanu laptopa; `WICI_USB` wskazuje inny katalog jako pamięć zestawu, a `WICI_STATE` inny katalog stanu.

## Testy

```sh
python3 -m unittest tests.test_laptop -v   # z katalogu głównego repozytorium
```

Testy obejmują reguły dokumentu `configure` (także zgodność z regułą tekstu SA1 modelu wzorcowego), klienta protokołu, struktury kernel32, zaszyfrowaną bazę i zestaw, listę słów, zabezpieczenia panelu, budowę pamięci USB (z Pythonem 3.14) oraz pełne przygotowanie stacji i ZNISZCZ DANE na obrazie firmware (z Node.js). Workflow [Laptop](../../.github/workflows/laptop.yml) uruchamia je na Windows, macOS i Linuksie, a pamięć USB buduje i uruchamia przez START na każdym systemie.

## Pamięć USB

```sh
python3.14 build/build_usb.py --out ../../dist/wici-usb
```

Skrypt pobiera przypięte środowiska Pythona ([runtimes.json](build/runtimes.json), sprawdzane SHA-256), przycina je i składa drzewo pamięci z programami START, instrukcją i manifestem. Do `START-WINDOWS.exe` potrzebny jest MinGW-w64 (`x86_64-w64-mingw32-gcc`) albo gotowy plik podany przez `--windows-launcher`.

| Katalog | Zawartość |
|---|---|
| [wici/](wici/__init__.py) | aplikacja: port szeregowy, protokół, dokument `configure`, czynności, dziennik, zaszyfrowana baza, panel |
| [wici/ui/](wici/ui/index.html) | panel: HTML, CSS i JS bez bibliotek |
| [build/](build/build_usb.py) | budowa pamięci USB, programy START, instrukcja na pamięć |
| [build/slowa/](build/slowa/build_slowa.py) | budowa listy słów do haseł z kopert ([wici/slowa.txt](wici/slowa.txt)): przypięte źródła, wykluczenia, `--check` |
| [dev/](dev/sim-station.mjs) | stacja z symulatora na TCP |

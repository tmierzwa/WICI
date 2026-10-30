# Aplikacja laptopa WICI

Panel w przeglądarce do pracy ze stacją przez USB, uruchamiany z pamięci USB zestawu na Windows, macOS i Linuksie, bez instalowania. Obsługuje tryb przygotowania (konfigurację stacji i węzła stanowiska, odczyt konfiguracji i kartę stacji) oraz zestaw na pamięci USB: konta i hasła z kopert, logowanie, zaszyfrowaną bazę z dziennikiem, „Oddaj laptop” i ZNISZCZ DANE. Zakres, decyzje, rozmiar, laptop i router na miejscu oraz dalsze etapy opisuje [plan](PLAN.md); kontrakt ze stacją jest w [protokole USB](../../docs/spec/protokol-usb.md).

## Uruchomienie podczas pracy nad kodem

Wymagany Python 3.12 lub nowszy, bez dodatkowych pakietów. Z katalogu `software/laptop`:

```sh
python3 -m wici                      # wyszukuje stację na portach USB i otwiera panel
python3 -m wici --port /dev/ttyACM1  # wskazany port (Windows: COM5)
```

Bez płytki można użyć świata symulatora (obraz firmware bench-b w WebAssembly, wymaga Node.js) ze stacjami, węzłem i stanowiskiem. Port danych USB każdej stacji jest wystawiony na TCP, a strona świata ma ekrany i przyciski stacji, w tym przycisk przygotowania ([opis](../simulator/README.md#osobne-elementy)).

```sh
node ../simulator/swiat.mjs --card ../../dist/karta-odbiorcy.json   # w drugim terminalu; strona http://127.0.0.1:7380/
python3 -m wici --port tcp:127.0.0.1:7300
```

Kartę odbiorcy stanowiska świata wczytuje się w panelu, a kod dostępu sieci ćwiczeniowej podaje pierwszy wiersz wyjścia. Stację skonfigurowaną z góry daje `--station plik.json` (plik z „Zapisz do pliku” panelu).

Uruchomiony ze źródeł panel trzyma konta i kopię bazy w katalogu `pamiec-usb` w katalogu stanu laptopa. Zmienna `WICI_USB` wskazuje inny katalog jako pamięć zestawu, a `WICI_STATE` inny katalog stanu.

## Testy

```sh
python3 -m unittest tests.test_laptop -v   # z katalogu głównego repozytorium
```

Testy obejmują reguły dokumentu `configure` (także zgodność z regułą tekstu SA1 modelu wzorcowego), klienta protokołu, struktury kernel32, zaszyfrowaną bazę i zestaw, listę słów, zabezpieczenia panelu, budowę pamięci USB (z Pythonem 3.14) oraz pełne przygotowanie stacji i ZNISZCZ DANE na obrazie firmware (z Node.js). Workflow [Laptop](../../.github/workflows/laptop.yml) uruchamia je na Windows, macOS i Linuksie, a pamięć USB buduje i uruchamia przez START na każdym systemie.

## Aplikacja stanowiska odbiorczego

Podpakiet [wici/stanowisko/](wici/stanowisko/__init__.py) to aplikacja komputera stanowiska odbiorczego (dyżurni, decyzja D19): Reticulum `e40191b` i LXMF `c3ff2d6` w Pythonie z tożsamością odbiorcy, za stacją w konfiguracji węzła stanowiska. Powstaje etapami S1–S10 z [planu](PLAN.md); są stos (S1), przyjęcie zgłoszeń na schemacie i przejściach modelu wzorcowego ([software/reference](../reference/README.md), S2), wysyłka z intencjami w bazie, ponowieniami i numeracją `event` (S3) oraz nośnik stanowiska z hasłem stanowiska, kontami dyżurnych, zaszyfrowaną bazą i tożsamością, paczką zapasową i kartą odbiorcy (S4), kopia bazy co 5 min na dysku komputera (S5) i odtworzenie z kopii z trybem odzyskania (S6), bez panelu. Gdy zegar komputera wskazuje czas wcześniejszy niż ostatnie nadanie, aplikacja nie startuje i prosi o ustawienie zegara. Nie trafia do `wici.pyz` pamięci USB laptopa schronienia. Uruchomienie wymaga Pythona z przypiętymi Reticulum, LXMF i `pyserial` 3.5:

```sh
# z katalogu software/laptop; przygotowanie na komputerze bez sieci, paczka zapasowa poza nośnikiem
python -m wici.stanowisko przygotuj --nosnik /media/nosnik/wici --dyzurni 4 --paczka /media/koperta/paczka.json --karta karta.json
python -m wici.stanowisko start --nosnik /media/nosnik/wici --port /dev/ttyACM0   # pyta o hasło stanowiska
```

Test stosu za węzłem stanowiska na dwóch programach `host` firmware opisuje [tests/test_stanowisko.py](../../tests/test_stanowisko.py); w CI robi to zadanie `stanowisko` workflow Laptop.

## Pamięć USB

```sh
python3.14 build/build_usb.py --out ../../dist/wici-usb
```

Skrypt pobiera przypięte środowiska Pythona ([runtimes.json](build/runtimes.json), sprawdzane SHA-256), przycina je i składa drzewo pamięci z programami START, instrukcją i manifestem. Do `START-WINDOWS.exe` potrzebny jest MinGW-w64 (`x86_64-w64-mingw32-gcc`) albo gotowy plik podany przez `--windows-launcher`. Katalog `--out` jest zastępowany w całości, więc skrypt odmawia pracy, gdy katalog nie pochodzi z poprzedniej budowy (brak `build-manifest.json`) albo gdy są w nim konta lub kopia bazy (`keys/`, `kopia/`).

Pamięć zapisuje się bez znacznika kwarantanny macOS. Drzewo z archiwum pobranego przeglądarką (np. artefakt `wici-usb` z CI) oczyszcza się przed zapisem poleceniem `xattr -dr com.apple.quarantine <katalog>`. Inaczej macOS uruchomi START-MAC z kopii tymczasowej, bez reszty pamięci. Archiwum ZIP artefaktu nie zachowuje prawa wykonywania. Na pamięci FAT32 nadaje je montowanie, a przy próbie z dysku APFS albo ext4 trzeba wykonać `chmod +x` na `START-MAC.app/Contents/MacOS/START` i `runtime/*/bin/python3.14` (START-LINUX.sh i tak uruchamia się przez `sh`).

| Katalog | Zawartość |
|---|---|
| [wici/](wici/__init__.py) | aplikacja: port szeregowy, protokół, dokument `configure`, czynności, dziennik, zaszyfrowana baza, panel |
| [wici/ui/](wici/ui/index.html) | panel: HTML, CSS i JS bez bibliotek |
| [build/](build/build_usb.py) | budowa pamięci USB, programy START, instrukcja na pamięć |
| [build/licencje/](build/licencje/zrodla.json) | licencje bibliotek wkompilowanych w interpreter python-build-standalone i kodu wbudowanego w CPython, kopiowane do `licenses/` na pamięci; źródła i sumy w `zrodla.json` |
| [build/slowa/](build/slowa/build_slowa.py) | budowa listy słów do haseł z kopert ([wici/slowa.txt](wici/slowa.txt)): przypięte źródła, wykluczenia, `--check` |

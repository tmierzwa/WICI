# Aplikacja laptopa WICI: plan

Aplikacja działa na każdym znalezionym laptopie z Windows, macOS albo Linuksem, uruchamiana z pamięci USB zestawu, bez instalowania i bez internetu (decyzja z 2026-10-13: wariant A, wszystkie systemy od początku). Kontrakt ze stacją jest gotowy w [protokole USB](../../docs/spec/protokol-usb.md); wymagania strony, panelu i pakietu w [specyfikacji oprogramowania](../../docs/spec/oprogramowanie.md#api-lokalnej-strony-poziomy-23).

Plan rozpisuje, co jest zrobione (etap 1), jak aplikacja radzi sobie z różnymi systemami, ile zajmuje na pamięci USB, co dalej i co trzeba jeszcze rozstrzygnąć.

## Etap 1: zrobione

Narzędzie trybu przygotowania i fundament dla następnych etapów.

| Część | Co robi | Plik |
|---|---|---|
| Port szeregowy | Windows (kernel32 przez ctypes), macOS i Linux (termios), wyłącznie biblioteka standardowa | [serialport.py](wici/serialport.py) |
| Protokół `"usb":2` | wątek odczytu, `seq`, `pending` z przyciskiem, ponowienie po `seq`, transfery w częściach, wyszukiwanie stacji po `hello`, ponowne połączenie | [usbproto.py](wici/usbproto.py) |
| Dokument `configure` | reguły pól jak w firmware, tekst według SA1, zgodność adresu LXMF z kluczem, różne tożsamości odbiorcy | [configdoc.py](wici/configdoc.py) |
| Czynności przygotowania | odczyt i zapis konfiguracji, karta stacji, komunikaty po polsku | [prep.py](wici/prep.py) |
| Dziennik | SQLite, tylko dopisywanie (wyzwalacze), bez treści i bez kodu sieci | [store.py](wici/store.py) |
| Panel | HTTP tylko na 127.0.0.1, token w ciasteczku, kontrola Host i Origin, CSP; długie odpytywanie stanu | [web.py](wici/web.py), [ui/](wici/ui/index.html) |
| Start | jedna instancja, przeglądarka, blokada uśpienia, `--selftest` | [\_\_main\_\_.py](wici/__main__.py), [awake.py](wici/awake.py) |
| Pamięć USB | przypięte środowiska Pythona, przycinanie, wspólna biblioteka, START dla trzech systemów, manifest | [build/build_usb.py](build/build_usb.py) |
| Symulator | obraz firmware bench-b z portem danych na TCP: praca i testy bez płytki | [dev/sim-station.mjs](dev/sim-station.mjs) |
| Testy | jednostkowe, bezpieczeństwo panelu, budowa USB, pełne przygotowanie na obrazie firmware | [tests/test_laptop.py](../../tests/test_laptop.py) |
| CI | testy na Windows, macOS i Linuksie; pamięć USB budowana i uruchamiana przez START na każdym systemie; budżet rozmiaru | [.github/workflows/laptop.yml](../../.github/workflows/laptop.yml) |

Czego etap 1 celowo nie ma: PRZENIEŚ STACJĘ i aktualizacji oprogramowania (firmware jeszcze ich nie realizuje, [przegląd F107](../../docs/review.md)), logowania hasłami z kopert (narzędzie przygotowania obsługuje osoba utrzymująca system na własnym komputerze; panel opiekuna w etapie 2 je dostaje) oraz strony mieszkańca (etap 3).

## Systemy docelowe

| System | Środowisko na USB | Uwagi |
|---|---|---|
| Windows 10 i 11, x64 | python.org 3.14.8 embeddable (pliki podpisane przez PSF) | Windows 11 na ARM uruchamia je w emulacji x64 |
| macOS 11 i nowszy, Apple Silicon | python-build-standalone 3.14.8 aarch64 | jeden START-MAC.app dla obu procesorów |
| macOS 11 i nowszy, Intel | python-build-standalone 3.14.8 x86_64 | Maki zatrzymane na 10.15 do sprawdzenia (pytanie 2) |
| Linux x86_64, glibc ≥2.17 | python-build-standalone 3.14.8 x86_64 | działający system użytkownika |
| Linux z pamięci USB | ten sam program w obrazie startowym | etap 4, dla komputerów bez sprawnego systemu |

Poza zakresem: Windows 7 i 8.1 (Python 3.14 ich nie obsługuje), systemy 32-bitowe, Linux na ARM (dodatkowe około 30 MB, pytanie 2), ChromeOS, tablety.

## Architektura

Jeden proces Pythona z biblioteką standardową i bez zależności zewnętrznych. Panel to strona w przeglądarce, która i tak jest na każdym laptopie; ta sama technika posłuży stronie mieszkańca w etapie 3, więc nie ma drugiego interfejsu.

```text
przeglądarka ──HTTP 127.0.0.1──▶ web.py ──▶ prep.py ──▶ usbproto.Station ──▶ serialport ──USB CDC──▶ stacja
                                   │                         (wątek: hello, status, ponowne połączenie)
                                   └──▶ store.Journal (SQLite, katalog stanu systemu)
```

Stan: Windows `%LOCALAPPDATA%\WICI`, macOS `~/Library/Application Support/WICI`, Linux `~/.local/share/wici`; zmienna `WICI_STATE` wskazuje inny katalog (obraz startowy Linuksa: partycja ext4 pamięci USB, zgodnie ze specyfikacją).

Bezpieczeństwo panelu: inne strony otwarte w tej samej przeglądarce nie mogą sterować stacją. Bez tokenu z odnośnika START nie ma ciasteczka; nagłówek Host musi wskazywać 127.0.0.1 (chroni przed DNS rebinding); POST wymaga JSON i własnego Origin; CSP blokuje skrypty spoza aplikacji.

## Uniwersalność: problemy i rozwiązania

| Problem | Rozwiązanie | Gdzie sprawdzone |
|---|---|---|
| VID/PID stacji jeszcze nieprzydzielone, więc nie da się wybrać portu po identyfikatorze | aplikacja otwiera tylko porty USB CDC ACM (`/dev/ttyACM*`, `/dev/cu.usbmodem*`, porty `USBSER` z rejestru Windows) i czeka 2,5 s na `hello`; nic do nich nie wysyła. Port bez `hello` (diagnostyka, węzeł poza trybem przygotowania, cudze urządzenie) nie jest otwierany ponownie, dopóki nie zniknie albo opiekun nie kliknie „Szukaj ponownie”, bo otwarcie portu podnosi DTR, a to resetuje np. Arduino. Bufor wejściowy nie jest czyszczony po otwarciu, żeby nie zgubić `hello` | test na obrazie firmware; test pomijania portów |
| sterowniki | stacja ma dwa interfejsy CDC ACM z IAD: Windows 10+, macOS i Linux mają wbudowany sterownik | spec. [radio](../../docs/spec/radio.md#usb-do-laptopa); próba na płytce |
| pyserial i inne zależności | port szeregowy na bibliotece standardowej, około 260 wierszy; na Windows krótki odczyt (30 ms), bo bez `FILE_FLAG_OVERLAPPED` zapis czeka na trwający odczyt | struktury kernel32 w teście, pty w teście POSIX |
| 1200 Bd resetuje ESP32 z rdzeniem Arduino do programu rozruchowego | port zawsze 115200 Bd, DTR i RTS włączone | kod; próba na płytce |
| Linux: użytkownik spoza grupy `dialout` | panel rozpoznaje brak uprawnień i podaje dokładne polecenie; obraz startowy (etap 4) ma uprawnienia ustawione | panel |
| Linux: ModemManager sonduje porty ACM | `TIOCEXCL` po otwarciu; obraz startowy z regułą udev | próba na Ubuntu |
| pamięć FAT bez prawa wykonywania (Linux `showexec`, `noexec`) | START-LINUX.sh kopiuje raz środowisko do `~/.cache/wici/<wersja>` | CI: `chmod -x` i ponowny start |
| macOS: Apple Silicon i Intel | jeden START-MAC.app wybiera środowisko po `uname -m` i `sysctl.proc_translated` | CI na obu procesorach |
| Gatekeeper, SmartScreen, antywirus | pliki Windows podpisane przez PSF; START bez podpisu; instrukcja na USB podaje, jak uruchomić; podpisy wydawcy to pytanie 4 | do próby T1/T8 |
| stara albo inna przeglądarka | ES2017, bez bibliotek, bez CSS z ostatnich lat; fonty systemowe z cyrylicą | do macierzy D04 |
| drugi START | `instance.json` w katalogu stanu: drugi START otwiera panel działającej instancji; sprawdzenie omija proxy systemu (laptopy firmowe) | kod |
| dwie czynności naraz (dwa przyciski, dwie karty) | jedna czynność na stacji naraz: nowy transfer przerwałby trwający | test |
| port 8080 zajęty | dowolny wolny port; Windows bez SO_REUSEADDR, żeby nie współdzielić portu | kod |
| uśpienie laptopa | Windows SetThreadExecutionState, macOS caffeinate, Linux systemd-inhibit | kod |
| polskie i ukraińskie znaki, ścieżki | `-X utf8`, funkcje „W” Windows, JSON bez sekwencji `\u` | testy |
| pliki `._pth` | `._pth` obok interpretera wskazuje wspólną bibliotekę i włącza tryb izolowany (bez zmiennych środowiska i site-packages); CPython 3.14 czyta `._pth` na każdym systemie (`Modules/getpath.py`) | CI: autotest wypisuje użytą bibliotekę |

## Rozmiar na pamięci USB

Archiwa czterech środowisk mają razem 102 MB (po rozpakowaniu około 300 MB). Aplikacja potrzebuje ich niewielkiej części.

| Sposób | Zysk |
|---|---|
| jedna biblioteka standardowa dla wszystkich systemów, tylko moduły używane przez aplikację (ModuleFinder i pakiety używane wprost w całości), bajtkod `-OO` w ZIP | zmierzone: 320 modułów, 2,2 MB zamiast około 4 × 40 MB |
| z każdego środowiska tylko interpreter i potrzebne moduły binarne: bez Tcl/Tk, testów, nagłówków, pip, TLS, OpenSSL; bez `libpython`, bo interpreter python-build-standalone jest zlinkowany statycznie i zawiera ją w sobie | zmierzone: Linux 32,5 MB, macOS arm64 18,9 MB, macOS x86_64 19,8 MB, Windows 10,2 MB (zamiast 66, 38, 40 i 16 MB z `libpython` i OpenSSL) |
| aplikacja jako jeden ZIP ze źródłami | zmierzone: 36 KB |
| jeden START-MAC.app zamiast dwóch | jedna ikona i jedna instrukcja dla użytkownika |
| bez zewnętrznych bibliotek JS i CSS, fonty systemowe | panel: 47 KB z logo |

Zmierzona cała pamięć poza obrazem startowym Linuksa: 83,6 MB, z czego 81,6 MB to cztery interpretery. Szacunek przed pierwszym pomiarem (30–45 MB) nie uwzględniał, że interpretery python-build-standalone mają wkompilowane wszystkie moduły binarne. Rozmiar 84 MB przyjęty 2026-10-14. Budżet: 90 MB (`BUDGET` w build_usb.py; zadanie `size` w CI przerywa budowę po przekroczeniu), czyli zapas na drobne zmiany, a nie na nowe środowisko. SHA-256 bez OpenSSL zapewnia wbudowany moduł `_sha2`. Kompletność przyciętej biblioteki sprawdza `--selftest` na każdym systemie. Dwie luki znalezione w ten sposób przy budowie planu: `runpy` i `pkgutil` (start z ZIP) oraz `ctypes._layout` i `stringprep` (ładowane z kodu w C).

System plików pamięci: FAT32, bo czytają go wszystkie systemy i oprogramowanie UEFI (obraz startowy w etapie 4 może leżeć na tej samej partycji). Partycja ext4 na stan Linuksa dochodzi z obrazem startowym.

## Układ pamięci USB

```text
START-WINDOWS.exe        mały program w C: uruchamia runtime\windows\pythonw.exe app\wici.pyz
START-MAC.app/           skrypt wybierający runtime/macos-arm64 albo runtime/macos-x86_64
START-LINUX.sh, .desktop
INSTRUKCJA.html
app/wici.pyz             aplikacja (źródła)
runtime/python314.zip    wspólna biblioteka standardowa (bajtkod)
runtime/<system>/        interpreter, moduły binarne, ._pth
licenses/, sources/
build-manifest.json      wersje, adresy i SHA-256 archiwów, SHA-256 każdego pliku, rozmiary części
```

Specyfikacja ([Pakiet USB](../../docs/spec/oprogramowanie.md#pakiet-usb)) ma dwa programy START dla Maców; plan łączy je w jeden. Zmianę trzeba przenieść do specyfikacji (pytanie 5).

## Router Wi-Fi

Router potrzebny jest dopiero na poziomie 3 (strona mieszkańca). Poziomy 1 i 2 działają bez niego.

| Wariant | Ocena |
|---|---|
| **Router z zestawu, przygotowany centralnie** (rekomendacja) | mały router podróżny z OpenWrt, zasilany 5 V przez USB-C, z kopią konfiguracji wgraną w przygotowaniu: nazwa sieci i hasło z plakatu, pula DHCP ≥60, stały adres laptopa (rezerwacja dla adaptera USB–Ethernet z zestawu), izolacja klientów Wi-Fi, bez internetu, bez dzienników DHCP. Plakat i adres strony są wtedy znane z góry. Koszt: jeden router na schronienie i kwalifikacja 50 klientów (D04) |
| Router znaleziony w budynku | tylko gdy ktoś zna hasło administratora; każdy model ma inną konfigurację, więc aplikacja jej nie robi. Laptop łączy się kablem albo przez Wi-Fi, panel pokazuje adres i kod QR |
| Laptop jako punkt dostępu | odrzucony: Windows Mobile Hotspot obsługuje najwyżej 8 urządzeń, macOS wymaga połączenia z internetem do udostępniania, a specyfikacja zabrania laptopowi własnego DHCP |
| Konfiguracja routera z aplikacji (LuCI/ubus) | odrzucona na teraz: kod zależny od modelu i wersji OpenWrt; kopia konfiguracji wgrywana w przygotowaniu daje to samo bez kodu w aplikacji |

Co aplikacja dostanie w etapie 3: wybór interfejsu i adresu (lista adresów przez `getifaddrs` i `GetAdaptersAddresses` przez ctypes, bez zależności), nasłuch strony mieszkańca tylko na tym adresie, kod QR w panelu (własny koder, kilka KB) i kontrolę, czy telefon w sieci routera widzi stronę.

Największe ryzyko poziomu 3 na znalezionych laptopach to zapora Windows: pierwsze nasłuchiwanie w sieci lokalnej wywołuje okno zapory, a zgoda dla sieci publicznej wymaga uprawnień administratora. Bez nich strona mieszkańca na takim laptopie nie zadziała (pytanie 3). macOS pyta zwykłego użytkownika, a Linux zwykle nie ma włączonej zapory.

## Następne etapy

| Etap | Zakres | Zależy od |
|---|---|---|
| 2: panel opiekuna (poziom 2) | `sync`, migawka, zdarzenia i `ack` z kursorem w SQLite; `submit`, `cancel`, `test`, `announce`, `mark_read`; `silence`, `close`, `destroy` z potwierdzeniem przyciskiem; niepewny wynik polecenia; logowanie hasłami z kopert (scrypt z `hashlib`); przekazanie zmiany | firmware z pełnym kontraktem w2 |
| 2a: przygotowanie, ciąg dalszy | PRZENIEŚ STACJĘ (pięć kroków z wycofaniem), aktualizacja oprogramowania stacji z podpisanego obrazu | firmware (F107) |
| 3: strona mieszkańca (poziom 3) | formularz w trzech językach, tokeny, lokalne numery, kolejka opiekuna, router, kod QR | etap 2; decyzja o routerze |
| 4: wydanie | szyfrowanie bazy (SQLCipher albo zaszyfrowany wolumen, D13), ZNISZCZ DANE na laptopie, obraz startowy Linuksa, podpis manifestu, podpisy START (pytanie 4), macierz D04 na prawdziwych laptopach | D13, D04 |

## Próby na sprzęcie (do macierzy D04)

CI sprawdza budowę i start na czystych systemach, ale nie zastąpi prawdziwych laptopów i stacji:

1. Stacja pilotażowa przez USB na Windows 10, Windows 11, macOS Apple Silicon, macOS Intel, Ubuntu i Fedora: wykrycie, konfiguracja, karta, odłączenie przewodu w trakcie transferu.
2. Start z pamięci FAT32 na każdym z nich, w tym Linux z automatycznym montowaniem (`showexec`).
3. Laptop służbowy z kontem bez uprawnień administratora i z programem antywirusowym.
4. Najstarszy obsługiwany sprzęt: Windows 10 22H2 na laptopie z 4 GB RAM, Mac z 2017 roku z macOS 11 lub nowszym.

## Rozstrzygnięcia i odrzucone warianty

| Wybór | Uzasadnienie |
|---|---|
| Python z biblioteką standardową, bez pyserial | port szeregowy to około 260 wierszy; każda zależność to kolejne licencje, wersje i pliki na USB |
| python.org embeddable na Windows, python-build-standalone na macOS i Linuksie | embeddable ma pliki podpisane przez PSF (mniej fałszywych alarmów); dla macOS i Linuksa nie ma oficjalnego środowiska przenośnego |
| wspólna biblioteka standardowa przez `._pth` | jedna kopia zamiast czterech; zapasowo każdy system może mieć własną kopię w `lib/python314.zip` (+2,2 MB na system) |
| bajtkod biblioteki `-OO`, aplikacja jako źródła | biblioteka jest mniejsza; aplikacja zostaje czytelna i niezależna od wersji bajtkodu (36 KB) |
| panel w przeglądarce | przeglądarka jest na każdym laptopie; ten sam mechanizm obsłuży stronę mieszkańca |
| wyszukiwanie stacji po `hello` | działa przed przydziałem VID/PID i nie wysyła niczego do cudzych urządzeń |
| odrzucone: Electron, Tauri, Go, Web Serial, okno natywne | uzasadnienia w poprzedniej analizie: waga, drugi język, brak trwałego zapisu i magazynu kluczy, dwa interfejsy |
| odrzucone: osobna biblioteka standardowa na każdy system | +6,6 MB bez zysku dla użytkownika |
| odrzucone: kompresja binarek (UPX) | około −40 MB, ale skompresowane pliki wykonywalne często budzą alarmy antywirusów na Windows i psują podpisy na macOS |
| odrzucone na etap 1: własna kompilacja Pythona z mniejszą liczbą modułów | może zejść do około 50 MB, ale oznacza własny łańcuch kompilacji na trzy systemy i utratę gotowych, sprawdzanych kompilacji; na pamięci 8 GB różnica jest dla użytkownika niewidoczna |

## Pytania do rozstrzygnięcia

1. Gałąź `laptop-etap-1` jest w PR. Pierwszy przebieg CI zbudował prawdziwą pamięć USB i dał pomiar rozmiaru (84 MB, przyjęte); START uruchamia się w CI na każdym z czterech środowisk.
2. Minimalne systemy: macOS 11 czy także 10.15 dla starszych Maków z Intelem (trzeba sprawdzić cel wdrożenia python-build-standalone)? Linux na ARM: tak czy nie (+30 MB)?
3. Router: czy przyjąć router z zestawu przygotowany centralnie? Który model kwalifikować? Co z zaporą Windows na laptopach bez uprawnień administratora na poziomie 3?
4. Podpisy: certyfikat Authenticode (Windows) i Apple Developer ID z notaryzacją (99 USD rocznie) czy instrukcja „uruchom mimo to”? Kto przechowuje klucz podpisu manifestu (minisign lub Ed25519)?
5. Dokumenty: wariant A zamyka D04 w części „jakie systemy”. Zgodnie z kolejnością koncepcja, potem specyfikacja: czy dopisać decyzję do rozdziału 08 koncepcji, a potem zmienić „Pakiet USB” w specyfikacji (jeden START-MAC.app, wspólna biblioteka, FAT32)?
6. Nazwa stacji: firmware podaje `WICI-4CBAAD` (wielkie litery), specyfikacja `WICI-3fa21c`. Którą postać przyjąć?
7. Plik karty odbiorcy: aplikacja przyjmuje `{"main":…,"backup":…}` albo dowolny podzbiór dokumentu `configure`. Czy aplikacja stanowiska ma eksportować dokładnie ten format?
8. Licencje środowisk: na USB są pliki licencji Pythona. Środowiska zawierają też OpenSSL, SQLite, libffi, zlib i inne. Pełny zestaw licencji trzeba przejrzeć przed pierwszą dystrybucją.
9. Obraz startowy Linuksa (etap 4): na jakiej dystrybucji go oprzeć (Debian live z shim dla Secure Boot?) i jaki rozmiar jest akceptowalny (zwykle 1–1,5 GB)?
10. VID/PID stacji: specyfikacja wymaga legalnego przydziału przed wydaniem. Kiedy będzie, aplikacja otworzy tylko porty z tym identyfikatorem i przestanie sondować cudze urządzenia. Czy przydział (np. pid.codes dla projektów otwartych) jest już w planie?

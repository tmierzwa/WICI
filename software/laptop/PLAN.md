# Aplikacja laptopa WICI: plan

Aplikacja działa na każdym znalezionym laptopie z Windows, macOS albo Linuksem, uruchamiana z pamięci USB zestawu, bez instalowania i bez internetu (decyzja z 2026-10-13: wariant A, wszystkie systemy od początku). Zestaw nie ma laptopa, a laptopa nie przygotowuje się wcześniej: w kryzysie ktoś przynosi dowolny laptop, a gdy ten nie zadziała, sprawdza się następny (decyzja z 2026-10-14). Aplikacja robi więc sama wszystko, co da się zrobić na nieznanym, nieprzygotowanym laptopie, a resztę opisuje instrukcja. Kontrakt ze stacją opisuje [protokół USB](../../docs/spec/protokol-usb.md), a wymagania strony, panelu i pakietu są w [specyfikacji oprogramowania](../../docs/spec/oprogramowanie.md#api-lokalnej-strony-poziomy-23).

Plan rozpisuje, co jest zrobione (etap 1), jak aplikacja radzi sobie z różnymi systemami, ile zajmuje na pamięci USB, co dalej i co trzeba jeszcze rozstrzygnąć. Ostatnie części opisują luki wobec specyfikacji z 2026-10-30 i plan aplikacji stanowiska odbiorczego (komputer dyżurnych), której jeszcze nie ma ([Luki wobec specyfikacji](#luki-wobec-specyfikacji-z-2026-10-30), [Aplikacja stanowiska odbiorczego](#aplikacja-stanowiska-odbiorczego-plan-etapów)).

## Etap 1: zrobione

Narzędzie trybu przygotowania i podstawa następnych etapów.

| Część | Co robi | Plik |
|---|---|---|
| Port szeregowy | Windows (kernel32 przez ctypes), macOS i Linux (termios), wyłącznie biblioteka standardowa | [serialport.py](wici/serialport.py) |
| Protokół `"usb":2` | wątek odczytu, `seq`, `pending` z przyciskiem, ponowienie po `seq`, transfery w częściach, wyszukiwanie stacji po `hello`, ponowne połączenie | [usbproto.py](wici/usbproto.py) |
| Dokument `configure` | reguły pól jak w firmware, tekst według SA1, zgodność adresu LXMF z kluczem, różne tożsamości odbiorcy | [configdoc.py](wici/configdoc.py) |
| Czynności przygotowania | odczyt i zapis konfiguracji, karta stacji, komunikaty po polsku | [prep.py](wici/prep.py) |
| Dziennik | SQLite, tylko dopisywanie (wyzwalacze), bez treści i bez kodu sieci; w zaszyfrowanej bazie, więc czynności na stacji wymagają zalogowania; także logowania, nowe hasła i oddanie laptopa | [store.py](wici/store.py) |
| Zestaw i logowanie | pamięć zestawu to ta, z której działa START (albo `WICI_USB`); nowa pamięć: konta gospodarza i 0–5 zastępców oraz hasło odtworzenia, hasła pokazane raz z numerami kopert i wydrukiem; logowanie, wybór kopii przy konflikcie, odtworzenie hasłem odtworzenia z nowymi kontami, nowe hasło po otwarciu koperty, wylogowanie, „Oddaj laptop”; ponowny START z pamięci włożonej pod inną literą dysku przenosi tam zapis kopii; ZNISZCZ DANE: `destroy` do stacji w tle i od razu zniszczenie danych laptopa | [session.py](wici/session.py), [prep.py](wici/prep.py) |
| Baza laptopa | konta zestawu na pamięci USB (opakowanie klucza danych dla każdego konta i hasłem odtworzenia, limit prób), SQLite w pamięci, łączone zaszyfrowane migawki na dysku i w tle na pamięci USB, wybór kopii po historii sesji, konflikt, „Oddaj laptop”, ZNISZCZ DANE | [database.py](wici/database.py) |
| Panel | HTTP tylko na 127.0.0.1, token w ciasteczku, kontrola Host i Origin, CSP; długie odpytywanie stanu; ekrany zestawu, logowania i kopert, zakładka „Zestaw” ze stanem kopii i ZNISZCZ DANE | [web.py](wici/web.py), [ui/](wici/ui/index.html) |
| Start | jedna instancja, przeglądarka, blokada uśpienia, `--selftest` | [\_\_main\_\_.py](wici/__main__.py), [awake.py](wici/awake.py) |
| Pamięć USB | przypięte środowiska Pythona, przycinanie, wspólna biblioteka, START dla trzech systemów, manifest | [build/build_usb.py](build/build_usb.py) |
| Symulator | świat symulatora (stacje, węzeł, stanowisko) z portami danych stacji na TCP i stroną z ich przyciskami: praca i testy bez płytki | [simulator/swiat.mjs](../simulator/swiat.mjs) |
| Testy | jednostkowe, bezpieczeństwo panelu, budowa USB, pełne przygotowanie na obrazie firmware | [tests/test_laptop.py](../../tests/test_laptop.py) |
| CI | testy na Windows, macOS i Linuksie; pamięć USB budowana i uruchamiana przez START na każdym systemie; budżet rozmiaru | [.github/workflows/laptop.yml](../../.github/workflows/laptop.yml) |

Czego etap 1 celowo nie ma: PRZENIEŚ STACJĘ i aktualizacji oprogramowania (firmware jeszcze ich nie obsługuje, [przegląd F107](../../docs/review.md)) oraz strony mieszkańca (tryb kiosku w etapie 2, strona dla telefonów w etapie 3). Logowanie hasłami z kopert, kopia bazy na pamięci USB, „Oddaj laptop” i ZNISZCZ DANE z etapów 2 i 4 są już gotowe (tabela wyżej).

## Systemy docelowe

| System | Środowisko na USB | Uwagi |
|---|---|---|
| Windows 10 i 11, x64 | python.org 3.14.8 embeddable (pliki podpisane przez PSF) | Windows 11 na ARM uruchamia je w emulacji x64 |
| macOS 11 i nowszy, Apple Silicon | python-build-standalone 3.14.8 aarch64 | jeden START-MAC.app dla obu procesorów; cel wdrożenia interpretera: 11.0 |
| macOS 10.15 i nowszy, Intel | python-build-standalone 3.14.8 x86_64 | cel wdrożenia interpretera: 10.15 (`minos` w pliku); CI testuje macOS 15, najstarszy obsługiwany sprawdza się ręcznie przed każdym wydaniem |
| Linux x86_64, glibc ≥2.17 | python-build-standalone 3.14.8 x86_64 | działający system użytkownika |
| Linux z pamięci USB | ten sam program w obrazie startowym (Debian live z shim dla Secure Boot) | etap 4: komputery bez sprawnego systemu i laptopy z Windows bez uprawnień administratora |

Poza zakresem: Windows 7 i 8.1 (Python 3.14 ich nie obsługuje), systemy 32-bitowe, Linux na ARM (dodatkowe około 30 MB; odłożone 2026-10-14, dodanie to jeden wpis w runtimes.json), ChromeOS, tablety.

## Architektura

Jeden proces Pythona z biblioteką standardową i bez zależności zewnętrznych; szyfr i PBKDF2 pochodzą z kryptografii systemu przez ctypes ([syscrypto.py](wici/syscrypto.py)). Panel to strona w przeglądarce, a przeglądarka jest na każdym laptopie. Tej samej techniki użyje strona mieszkańca w etapie 3, więc drugi interfejs nie jest potrzebny.

```text
przeglądarka ──HTTP 127.0.0.1──▶ web.py ──▶ prep.py ──▶ usbproto.Station ──▶ serialport ──USB CDC──▶ stacja
                                   │                         (wątek: hello, status, ponowne połączenie)
                                   └──▶ session.Session ──▶ database.Database (SQLite w pamięci procesu)
                                                              ├──▶ zaszyfrowane migawki w katalogu stanu
                                                              └──▶ zaszyfrowana kopia i konta na pamięci USB zestawu
```

Stan: Windows `%LOCALAPPDATA%\WICI`, macOS `~/Library/Application Support/WICI`, Linux `~/.local/share/wici`; zmienna `WICI_STATE` wskazuje inny katalog (obraz startowy Linuksa: partycja ext4 pamięci USB, zgodnie ze specyfikacją). Zaszyfrowana kopia bazy po każdej zmianie trafia na pamięć USB zestawu.

Bezpieczeństwo panelu: inne strony otwarte w tej samej przeglądarce nie mogą sterować stacją. Bez tokenu z odnośnika START nie ma ciasteczka; nagłówek Host musi wskazywać 127.0.0.1 (chroni przed DNS rebinding); POST wymaga JSON (bez zapytania wstępnego CORS, na które panel nie odpowiada) i własnego Origin, jeśli żądanie go ma (drugi START nie wysyła); CSP blokuje skrypty spoza aplikacji.

## Uniwersalność: problemy i rozwiązania

| Problem | Rozwiązanie | Gdzie sprawdzone |
|---|---|---|
| VID/PID stacji jeszcze nieprzydzielone, więc nie da się wybrać portu po identyfikatorze | aplikacja otwiera tylko porty USB CDC ACM (`/dev/ttyACM*`, `/dev/cu.usbmodem*`, porty `USBSER` z rejestru Windows) i czeka 2,5 s na `hello`; nic do nich nie wysyła. Port bez `hello` (diagnostyka, węzeł poza trybem przygotowania, cudze urządzenie) nie jest otwierany ponownie, dopóki nie zniknie albo gospodarz nie kliknie „Szukaj ponownie”, bo otwarcie portu podnosi DTR, a to resetuje np. Arduino. Bufor wejściowy nie jest czyszczony po otwarciu, żeby nie zgubić `hello` | test na obrazie firmware; test pomijania portów |
| sterowniki | stacja ma dwa interfejsy CDC ACM z IAD: Windows 10+, macOS i Linux mają wbudowany sterownik | spec. [radio](../../docs/spec/radio.md#usb-do-laptopa); próba na płytce |
| pyserial i inne zależności | port szeregowy na bibliotece standardowej, około 260 wierszy; na Windows krótki odczyt (30 ms), bo bez `FILE_FLAG_OVERLAPPED` zapis czeka na trwający odczyt | struktury kernel32 w teście, pty w teście POSIX |
| 1200 Bd resetuje ESP32 z rdzeniem Arduino do programu rozruchowego | port zawsze 115200 Bd, DTR i RTS włączone | kod; próba na płytce |
| Linux: użytkownik spoza grupy `dialout` | panel rozpoznaje brak uprawnień i podaje dokładne polecenie (wymaga jednorazowo `sudo`); bez hasła administratora zostaje obraz startowy (etap 4, uprawnienia ustawione) albo inny laptop | panel |
| zapora Windows na stronie dla telefonów | [Laptop i router na miejscu](#laptop-i-router-na-miejscu) | do próby na czystym Windows 11 |
| Linux: ModemManager sonduje porty ACM | `TIOCEXCL` po otwarciu; obraz startowy z regułą udev | próba na Ubuntu |
| wyjęcie pamięci przy działającej aplikacji (macOS zamykał aplikację działającą z pamięci od razu) i pamięć FAT bez prawa wykonywania (Linux `showexec`, `noexec`) | każdy START kopiuje środowisko swojego systemu, wspólną bibliotekę i `wici.pyz` do katalogu podręcznego użytkownika (`~/.cache/wici`, `~/Library/Caches/WICI`, `%LOCALAPPDATA%\WICI\srodowisko`), do katalogu `<wersja>-<suma manifestu>`, i uruchamia aplikację stamtąd, z katalogiem roboczym w kopii i ścieżką pamięci w `WICI_USB`. Kopia powstaje w katalogu tymczasowym z manifestem na końcu i dostaje nazwę jednym przemianowaniem, więc przerwane kopiowanie nie zostawia niby pełnej kopii, a inna budowa nie usuwa środowiska działającej aplikacji. Wspólną część START-MAC i START-LINUX zawiera `runtime/kopia.sh`. Gdy kopiowanie się nie uda albo interpreter z kopii się nie uruchamia (katalog domowy z `noexec`, AppLocker albo antywirus blokujący programy z profilu użytkownika), START uruchamia aplikację z pamięci i ustawia `WICI_Z_PAMIECI=1`, żeby panel mógł prosić o niewyjmowanie pamięci. START-WINDOWS kończy się po 2 s działania aplikacji, żeby sam nie działał z pamięci. Kopie starszych budów zostają w katalogu podręcznym (około 20 MB na budowę) świadomie: laptop jest przypadkowy i tymczasowy, a usuwanie cudzych katalogów kopii mogłoby trafić w środowisko działającej aplikacji. GNOME Files nie uruchamia plików .desktop z katalogu, więc instrukcja zaczyna od terminala | CI: START na każdym systemie z biblioteką z kopii, `chmod -x`, przeniesienie katalogu pamięci przy działającej aplikacji, na macOS wysunięcie obrazu FAT32; test jednostkowy powrotu do pamięci (`kopia.sh`) |
| macOS: drugi START przez LaunchServices | START-MAC uruchamia Pythona w tle i kończy się, więc każde dwukrotne kliknięcie uruchamia nowy START (proces działający przez cały czas pracy panelu sprawiał, że następne kliknięcia nic nie robiły) | CI: `open` dwa razy |
| macOS: Apple Silicon i Intel | jeden START-MAC.app wybiera środowisko po `uname -m` i `sysctl.proc_translated` | CI na obu procesorach |
| Gatekeeper, SmartScreen, antywirus | pliki Windows podpisane przez PSF; przed pilotażem poziomów 2–3 START-MAC.app z Apple Developer ID i notaryzacją, START-WINDOWS.exe z podpisem przez program SignPath dla projektów otwartych; do tego czasu instrukcja na USB podaje, jak uruchomić | do próby T1/T8 |
| stara albo inna przeglądarka | ES2017, bez bibliotek, bez CSS z ostatnich lat; fonty systemowe z cyrylicą | do macierzy D04 |
| drugi START | `instance.json` w katalogu stanu: drugi START prosi działającą instancję o nowy jednorazowy odnośnik (`POST /api/ticket` z tokenem panelu) i otwiera nim panel; sprawdzenie omija proxy systemu (laptopy firmowe). Działająca instancja trzyma blokadę pliku `instance.lock` (system zwalnia ją także po zabiciu procesu), więc szybki drugi START czeka do 30 s na instancję, która się jeszcze uruchamia, zamiast startować drugą | test |
| błąd startu bez konsoli (pythonw, START-MAC.app) | aplikacja pokazuje okno systemu (MessageBoxW, osascript, zenity albo notify-send) z błędem startu albo z adresem panelu, gdy przeglądarka się nie otworzyła, i kończy się kodem 3; programy START pokazują własny komunikat tylko przy innych kodach | kod |
| dwie czynności naraz (dwa przyciski, dwie karty) | jedna czynność na stacji naraz: nowy transfer przerwałby trwający | test |
| port 8080 zajęty | dowolny wolny port; Windows bez SO_REUSEADDR, żeby nie współdzielić portu | kod |
| uśpienie laptopa i wygaszenie ekranu (blokada hasłem właściciela) | Windows SetThreadExecutionState, macOS caffeinate, Linux systemd-inhibit | kod |
| polskie i ukraińskie znaki, ścieżki | `-X utf8`, funkcje „W” Windows, JSON bez sekwencji `\u` | testy |
| pliki `._pth` | `._pth` obok interpretera wskazuje wspólną bibliotekę i włącza tryb izolowany (bez zmiennych środowiska i site-packages); CPython 3.14 czyta `._pth` na każdym systemie (`Modules/getpath.py`) | CI: autotest wypisuje użytą bibliotekę |

## Rozmiar na pamięci USB

Archiwa czterech środowisk mają razem 102 MB (po rozpakowaniu około 300 MB). Aplikacja potrzebuje ich niewielkiej części.

| Sposób | Zysk |
|---|---|
| jedna biblioteka standardowa dla wszystkich systemów, tylko moduły używane przez aplikację (ModuleFinder i pakiety używane wprost w całości), bajtkod `-OO` w ZIP | zmierzone: 320 modułów, 2,2 MB zamiast około 4 × 40 MB |
| z każdego środowiska tylko interpreter i potrzebne moduły binarne: bez Tcl/Tk, testów, nagłówków, pip, TLS, OpenSSL na Windows (AES i PBKDF2 daje system); bez `libpython`, bo interpreter python-build-standalone jest zlinkowany statycznie i zawiera ją w sobie | zmierzone: Linux 32,5 MB, macOS arm64 18,9 MB, macOS x86_64 19,8 MB, Windows 10,2 MB (zamiast 66, 38, 40 i 16 MB z `libpython` i OpenSSL) |
| aplikacja jako jeden ZIP ze źródłami | zmierzone 2026-10-21: 79 KB (z listą słów do haseł i panelem) |
| jeden START-MAC.app zamiast dwóch | jedna ikona i jedna instrukcja dla użytkownika |
| bez zewnętrznych bibliotek JS i CSS, fonty systemowe | panel: 69 KB z logo (przed kompresją w ZIP) |

Zmierzona cała pamięć poza obrazem startowym Linuksa: 83,6 MB, z czego 81,3 MB to cztery interpretery, 2,2 MB wspólna biblioteka, a reszta to aplikacja, START i licencje. Szacunek przed pierwszym pomiarem (30–45 MB) nie uwzględniał, że interpretery python-build-standalone mają wkompilowane wszystkie moduły binarne. Rozmiar 84 MB przyjęty 2026-10-14. Budżet: 90 MB (`BUDGET` w build_usb.py; zadanie `size` w CI przerywa budowę po przekroczeniu). Zapas wystarcza na drobne zmiany, nie na nowe środowisko. SHA-256 bez OpenSSL zapewnia wbudowany moduł `_sha2`. Kompletność przyciętej biblioteki sprawdza `--selftest` na każdym systemie. Przy budowie planu `--selftest` wykrył dwie luki: `runpy` i `pkgutil` (start z ZIP) oraz `ctypes._layout` i `stringprep` (ładowane z kodu w C).

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
runtime/kopia.sh         kopia środowiska i aplikacji na dysk (START-MAC, START-LINUX)
licenses/, sources/
keys/                    konta i plik zestawu (tworzy panel przy przygotowaniu)
kopia/                   zaszyfrowana kopia bazy (dwa pliki na zmianę)
build-manifest.json      wersje, adresy i SHA-256 archiwów, SHA-256 każdego pliku, rozmiary części
```

Ten układ opisuje też specyfikacja ([Pakiet USB](../../docs/spec/oprogramowanie.md#pakiet-usb)).

## Laptop i router na miejscu

Laptop i router są z obiektu albo przyniesione na miejscu (decyzje z 2026-10-14). Nic nie jest przygotowane wcześniej, więc aplikacja przechodzi kolejne ścieżki sama i przy każdej przeszkodzie mówi jednym zdaniem, co zrobić dalej.

| Ścieżka | Kiedy działa | Co robi aplikacja |
|---|---|---|
| 1. Strona dla telefonów przez router obiektu | macOS i Linux zwykle od razu; Windows, gdy użytkownik laptopa jest administratorem (zwykle na laptopie prywatnym) | wybiera interfejs z prywatnym adresem IPv4 i bramą, przy kilku ten na kablu; nasłuchuje tylko na nim, port 8080 (gdy zajęty: inny wolny); pokazuje kod QR sieci Wi-Fi (`WIFI:T:WPA;S:…;P:…;;`, nazwa i hasło wpisane raz z naklejki routera) i kod QR adresu, także jako plakat A4 do wydruku; odświeża kody po zmianie adresu; licznik połączonych telefonów |
| 2. Tryb kiosku: strona mieszkańca na ekranie laptopa | zawsze, gdy działa START | otwiera stronę mieszkańca pod adresem lokalnym; mieszkańcy zgłaszają się po kolei przy laptopie; bez sieci, routera, zapory i administratora. Po wysłaniu numer zgłoszenia, potem pusty formularz dla następnej osoby, bez ciasteczka mieszkańca. Panel gospodarza pod inną nazwą hosta (`localhost` i `127.0.0.1` mają osobne ciasteczka) i zablokowany do ponownego logowania na czas kiosku ([specyfikacja](../../docs/spec/oprogramowanie.md#tryb-kiosku)) |
| 3. Linux WICI z pamięci USB | Windows bez administratora, jeśli laptop pozwala uruchomić system z USB, i tylko za zgodą właściciela laptopa | obraz startowy etapu 4 z tą samą aplikacją; w Windows nic się nie zmienia i nic nie zostaje na dysku |
| 4. Następny laptop | gdy żadna ścieżka nie daje strony dla telefonów, a kiosk nie wystarcza | instrukcja podaje kolejność: laptop prywatny albo Mac, Linux, na końcu laptop firmowy |

**Windows.** Zapora Windows Defender jest domyślnie włączona i blokuje połączenia przychodzące, a nowa sieć dostaje zwykle profil „Publiczna”. Zgoda na połączenia wymaga uprawnień administratora. macOS ma zaporę aplikacji domyślnie wyłączoną, typowe dystrybucje Linuksa też (Fedora ma `firewalld`, ale jego domyślna strefa przepuszcza porty 1025–65535). Dlatego aplikacja na Windows:

- przed nasłuchem w sieci lokalnej sprawdza, czy jest reguła WICI. Bez niej nie otwiera portu, żeby nie wywołać alertu zapory, bo anulowanie alertu przez zwykłego użytkownika zapisuje reguły blokujące dla `pythonw.exe` z pamięci USB, a reguły blokujące mają pierwszeństwo;
- przyciskiem „Zezwól telefonom na połączenie” uruchamia przez UAC sam `netsh` (podpisany przez Microsoft) z regułą tylko dla portu, na którym słucha strona (zwykle 8080), nie programu, bo litera dysku pamięci się zmienia. Polecenie: `netsh advfirewall firewall add rule name="WICI strona mieszkańca" dir=in action=allow protocol=TCP localport=<port> remoteip=localsubnet profile=any`. Ten sam krok usuwa reguły blokujące, które Windows utworzył dla interpretera z bieżącej ścieżki pamięci. Rozpoznaje je po ścieżce programu, bo nie mają nazwy WICI;
- przy zamknięciu proponuje usunięcie reguły (drugie okno UAC), żeby laptop wrócił do właściciela bez zmian;
- bez administratora mówi wprost, że telefony się nie połączą, i proponuje ścieżki 2 i 3.

Stan wiedzy o systemach (sprawdzone 2026-10-20; źródła poza dokumentacją producenta zaznaczone):

| Twierdzenie | Źródło | Stan |
|---|---|---|
| anulowanie alertu zapory Windows tworzy reguły blokujące dla programu i alert już nie wraca | [Rebex](https://blog.rebex.net/beware-pressing-cancel-on-windows-firewall-security-alert), wątki Microsoft Tech Community; brak dokumentacji Microsoft | zgodne relacje, do próby |
| odczyt reguł (`netsh advfirewall firewall show rule`) działa bez uprawnień administratora | dokumentacja Microsoft wymaga podniesienia uprawnień tylko dla zmian | wniosek, do próby; od tego zależy sprawdzanie reguły przed nasłuchem |
| okno UAC dla `netsh` pokazuje wydawcę Microsoft | — | do próby |
| Windows Mobile Hotspot: najwyżej 8 urządzeń | Microsoft Q&A (odpowiedź społeczności), TP-Link, Thurrott | zgodne źródła wtórne |
| zapora macOS domyślnie wyłączona | cytat strony wsparcia Apple na forum Apple, poradniki | zgodne źródła wtórne |
| Ubuntu: `ufw` zainstalowany, domyślnie wyłączony | [help.ubuntu.com/community/UFW](https://help.ubuntu.com/community/UFW) | potwierdzone |
| Fedora Workstation: strefa `FedoraWorkstation` otwiera porty TCP i UDP 1025–65535 | [Fedora Magazine](https://fedoramagazine.org/control-the-firewall-at-the-command-line/), forum Fedory | potwierdzone |
| macOS 15: niepodpisanej aplikacji nie otworzy się klawiszem Control i kliknięciem; zostaje „Otwórz mimo to” w Ustawieniach systemowych, z hasłem | ogłoszenie Apple dla deweloperów (cytowane przez 9to5Mac, AppleInsider) | potwierdzone; hasło na laptopie bez uprawnień administratora do próby, co wzmacnia potrzebę notaryzacji |

Przed wykonaniem etapu 3 potrzebna jest próba na czystym Windows 11 (maszyna wirtualna) z kontem standardowym: alert i anulowanie, odczyt reguł, okno UAC, reguła portu i jej usunięcie.

**Diagnostyka w panelu:** brak kabla, kabel w gnieździe WAN, brak adresu IP, profil sieci „Publiczna”, brak reguły zapory, zero połączonych telefonów po kilku minutach.

**Instrukcja opisuje resztę:**

- kolejność dróg jak w tabeli;
- system Linux z pamięci USB tylko za zgodą właściciela laptopa;
- nadzór nad laptopem w trybie kiosku;
- „Oddaj laptop” przed zwrotem;
- zmiana hasła Wi-Fi przez zarządcę po zdarzeniu;
- kabel do gniazda LAN routera, nie WAN;
- laptop bez gniazda sieciowego łączy się z Wi-Fi routera i działa, jeśli router nie izoluje urządzeń od siebie (adapter USB–Ethernet przy pamięci USB to opcja, nie wymóg);
- telefony w sieci, którą wskaże panel (zwykle głównej, za zgodą zarządcy);
- routery domowe mają zwykle limit około 32 urządzeń, więc mieszkańcy korzystają kolejno;
- cudzego routera nie resetuje się;
- router zasilany ze stacji zasilania albo UPS;
- Android pyta o sieć bez internetu („pozostań połączony”), a gdy strona się nie otwiera, wyłącza się dane komórkowe (do potwierdzenia na kilku telefonach);
- tabela klawiszy menu startowego według producenta i co zrobić przy zablokowanym menu.

Laptop nie uruchamia własnego serwera DHCP, DNS ani portalu przechwytującego, zgodnie ze specyfikacją: strona otwiera się z kodu QR, więc działa z każdym routerem bez zmiany jego konfiguracji.

| Odrzucony wariant | Powód |
|---|---|
| laptop w zestawie stacji albo laptop przygotowany wcześniej | koszt; w kryzysie nie będzie skąd go wziąć |
| router z zestawu | koszt; wybrany router obiektu |
| stacja jako punkt dostępu Wi-Fi | wykonanie A (nRF52840) nie ma Wi-Fi, a D14 może wybrać MCU bez radia; zgodność pilotażu z deklaracją producenta modułu i droga do wydania zakładają wyłączone Wi-Fi; punkt dostępu wyklucza lekkie uśpienie, a sam odbiornik Wi-Fi ESP32-S3 pobiera 88 mA (karta katalogowa ESP32-S3 v2.2, tabela 5-7; nadawanie do 340 mA), więcej niż cały cel stacji ≤60 mA, od którego zależą 72 h; ESP-IDF 5.5 dopuszcza najwyżej 15 klientów punktu dostępu ESP32-S3 (`ESP_WIFI_MAX_CONN_NUM`), a schronienie ma około 50 mieszkańców; klucze stacji wystawione na obce telefony; stos Wi-Fi zabiera RAM potrzebny Reticulum |
| laptop jako punkt dostępu | Windows Mobile Hotspot obsługuje najwyżej 8 urządzeń, macOS wymaga połączenia z internetem do udostępniania, a specyfikacja zabrania laptopowi własnego DHCP |
| konfiguracja routera z aplikacji | każdy model i wersja oprogramowania routera jest inna |
| obejście zapory Windows bez zgody administratora, uruchamianie innego systemu bez zgody właściciela | to zabezpieczenia właściciela laptopa |

## Następne etapy

| Etap | Zakres | Zależy od |
|---|---|---|
| 2: panel gospodarza (poziom 2) i tryb kiosku | `sync`, migawka, zdarzenia i `ack` z kursorem w SQLite; `submit`, `cancel`, `test`, `announce`, `mark_read`; `silence`, `close`, `destroy` z potwierdzeniem przyciskiem; niepewny wynik polecenia; przekazanie zmiany; strona mieszkańca w trybie kiosku na ekranie laptopa (formularz w trzech językach, lokalne numery, kolejka gospodarza), bo działa na każdym laptopie bez sieci | firmware z pełnym kontraktem w2 |
| 2a: przygotowanie, ciąg dalszy | PRZENIEŚ STACJĘ (pięć kroków z wycofaniem), aktualizacja oprogramowania stacji z podpisanego obrazu | firmware (F107) |
| 3: strona dla telefonów (poziom 3) | wybór interfejsu i adresu (`getifaddrs`, `GetAdaptersAddresses` przez ctypes), nasłuch tylko na nim, tokeny mieszkańców, kody QR sieci i adresu (własny koder, kilka KB), plakat A4, reguła zapory Windows przez UAC, diagnostyka | etap 2; próba zapory na czystym Windows 11 |
| 4: wydanie | rozstrzygnięcie parametrów szyfrowania migawek w D13 (baza w pamięci już działa, bez SQLCipher i bez wolumenu wymagającego administratora), obraz startowy Linuksa (Debian live z shim; droga dla laptopów z Windows bez administratora), podpis manifestu w CI (pamięć USB i pakiet stanowiska jednym sposobem, decyzja autora 2026-10-30), podpisy START, macierz D04 na prawdziwych laptopach | D13, D04 |

Etap 2 stosuje kontrakt `"usb":2` w wersji z 2026-10-30: `sync` bez pola `boot` (stacja go nie sprawdza, więc laptop go nie wysyła i nie przechowuje), `mark_read` zawsze z `epoch` wziętym z `snap_begin` albo `event`, z którego pochodzi `msg`; odpowiedź `stale` nie jest ponawiana, tylko uruchamia `sync` i oznaczenie wiadomości jeszcze raz numerem z nowej epoki, jeśli wiadomość jest w migawce.

## Luki wobec specyfikacji z 2026-10-30

Porównanie kodu z [oprogramowaniem](../../docs/spec/oprogramowanie.md), [protokołem USB](../../docs/spec/protokol-usb.md), [stanowiskiem odbiorczym](../../docs/spec/stanowisko-osp.md) i [instrukcją dyżurnego](../../docs/obsluga/instrukcja-dyzurnego.md) (stan `main` z 2026-10-30).

| Wymaganie | Aplikacja | Stan kodu | Etap |
|---|---|---|---|
| START kopiuje środowisko swojego systemu (około 20 MB) i aplikację do katalogu użytkownika i uruchamia je z dysku; wyjęcie pamięci nie zamyka aplikacji | laptop schronienia | każdy START kopiuje środowisko i aplikację na dysk i uruchamia je stamtąd, ścieżkę pamięci podaje w `WICI_USB`; gdy kopia nie rusza, aplikacja działa z pamięci (`WICI_Z_PAMIECI=1`); wcześniej kopiował tylko START-LINUX.sh przy pamięci bez prawa wykonywania | L1: zrobione (#146) |
| `sync`: `boot` opcjonalne i tylko informacyjne | laptop schronienia | `sync` jeszcze nie istnieje (etap 2); firmware już przyjmuje `sync` bez `boot` | L2 |
| `mark_read` z `epoch`, `stale` dla innej epoki | laptop schronienia | `mark_read` jeszcze nie istnieje (etap 2); firmware i symulator już to mają (#139) | L2 |
| kopia bazy, tożsamości i pliku kont co 5 min na szyfrowany dysk komputera, trzy ostatnie, ciche ponowienie z wpisem w dzienniku, wiek najnowszej w przekazaniu zmiany | stanowisko | brak aplikacji | S5 |
| odzyskanie z kopii: P = P z kopii + 86 400 s × (1 + n) | stanowisko | brak aplikacji | S6 |
| „usuń kopie” i ZNISZCZ DANE obejmują też kopie na dysku komputera | stanowisko | S9: zrobione; na laptopie schronienia ZNISZCZ DANE już usuwa migawki z dysku | S9 |

Laptop schronienia nie ma poza tym żadnej luki z 2026-10-30: migawki na dysku i kopia na pamięci działają według [pakietu USB](../../docs/spec/oprogramowanie.md#pakiet-usb).

**L1: START z dysku (zrobione 2026-10-30, #146).** Każdy START (Windows, macOS, Linux) kopiuje środowisko swojego systemu, wspólną bibliotekę i `wici.pyz` do katalogu podręcznego użytkownika, nazwanego od wersji i sumy `build-manifest.json`, jak dziś START-LINUX.sh przy pamięci bez prawa wykonywania; kopię sprawdza po manifeście i robi ponownie tylko przy innej budowie. Aplikację uruchamia z kopii i podaje jej ścieżkę pamięci (zmienna `WICI_USB`, którą `usb_root()` już czyta). Testy: CI uruchamia START na każdym systemie, sprawdza w `--selftest`, że biblioteka pochodzi z kopii, a pamięć ze zmiennej; test działającej aplikacji po zmianie nazwy katalogu pamięci (wyjęcie). Wiersz o pamięci bez prawa wykonywania i próba 6 niżej zmieniają się razem z tym etapem.

## Aplikacja stanowiska odbiorczego: plan etapów

Aplikacji stanowiska nie ma: ani stosu (Reticulum `e40191b` i LXMF `c3ff2d6` w Pythonie), ani bazy, ani panelu dyżurnego. Do prób zgodności służą `firmware/tools/rns_osp_node.py` (Reticulum w Pythonie za węzłem stanowiska przez pseudoterminal) i model `software/simulator/post/post.cpp`, który symulator uruchamia zamiast aplikacji.

**Miejsce w kodzie.** Podpakiet `wici/stanowisko/` w tym samym pakiecie `wici`, z osobnym poleceniem startu (`python -m wici.stanowisko`) i osobnym celem budowy pakietu stanowiska. Używa wprost istniejących modułów: panel HTTP z kontrolą Host, Origin i CSP ([web.py](wici/web.py)), dziennik tylko do dopisywania ([store.py](wici/store.py)), szyfr ([syscrypto.py](wici/syscrypto.py)), hasła z listy słów ([passwords.py](wici/passwords.py)), blokada uśpienia i jedna instancja. Schemat odbioru przejmuje z modelu wzorcowego (`software/reference/schema.sql`, `OSPStore`), tak jak każe specyfikacja; model zostaje wzorcem, a testy stanowiska powtarzają jego przypadki akceptacyjne na kodzie aplikacji.

**Próby bez sprzętu.** Każdy etap ma testy jednostkowe w `tests/test_stanowisko*.py`. Od S1 test integracyjny uruchamia aplikację za programem `host-port` w konfiguracji węzła i stacją z rdzeniem (jak `rns_osp_node.py --lxmf`), w zadaniu CI z przypiętym Reticulum i LXMF (jak zadanie `rns` w `firmware.yml`). Symulator dostaje port danych węzła na TCP w S10, wtedy aplikacja zastępuje w nim model `post.cpp`.

| Etap | Zakres | Testy | Zależy od |
|---|---|---|---|
| S1: stos (zrobione, #147) | start Reticulum i LXMF z pakietu: jeden interfejs KISS z kontrolą przepływu i `bitrate` według [radio](../../docs/spec/radio.md#ponowienia-i-limity-prób), transport, AutoInterface i współdzielona instancja wyłączone, dostarczenie okazjonalne bez znaczków; tożsamość główna w katalogu stanu (na razie bez szyfrowania, plik z prawami 0600); ogłoszenie po starcie | konfiguracja wygenerowana z kodu; ogłoszenie dociera do stacji przez węzeł, wiadomość LXMF ze stacji dociera do aplikacji | rozstrzygnięcie 2 niżej |
| S2: przyjęcie (zrobione, #151) | baza SQLite na schemacie wzorcowym (`journal_mode=DELETE`, `synchronous=FULL`), przyjęcie REQUEST i TEST w jednej transakcji z RECEIVED po COMMIT (O01), deduplikacja i konflikt (O02), lista zaufanych i kwarantanna z limitami, alarm stacji usuniętej (O03), czas odbioru z zegara komputera | przypadki akceptacyjne modelu na kodzie aplikacji; przerwanie przed COMMIT bez RECEIVED; REQUEST ze stacji przez węzeł dostaje RECEIVED | S1 |
| S3: wysyłka (zrobione, #154) | intencje RECEIVED, STATUS, REPLY, BULLETIN w tej samej transakcji co zdarzenie; kolejność, najwyżej 4 w drodze, ponowienia 1, 2, 5, 15 min, potem co 15 min, po 6 h co 60 min (±20%); zastępowanie nieodesłanego STATUS; powtórzony REQUEST wysyła czekającą intencję od razu; numer `event` = max(licznik + 1, sekundy od 2026-01-01 + P); czas ostatniego nadania bez P i odmowa startu przy zegarze cofniętym | zegar wstrzykiwany w testach; ponowienia po FAILED; restart w trakcie wysyłki | S2 |
| S4: nośnik, konta i tożsamość zapasowa (zrobione, #155) | klucz danych nośnika opakowany kluczem z hasła stanowiska (PBKDF2, format pliku kont laptopa), baza w pamięci z zaszyfrowaną migawką na nośniku po każdej zmianie (jak laptop, przed każdą wysyłką), tożsamość zaszyfrowana kluczem danych, plik kont i pamięć Reticulum na nośniku; konta dyżurnych z listy słów, sprawdzenie hasła z limitem prób, dziennik działań tylko do dopisywania (blokada panelu po 5 min przechodzi do S7 razem z logowaniem w panelu). Przygotowanie stanowiska: tożsamość zapasowa tworzona tylko w pamięci i zapisana wyłącznie jako paczka zaszyfrowana kluczem z hasła tożsamości zapasowej (co najmniej 6 słów, ta sama funkcja wyprowadzenia klucza co nośnik) do kopert poza stanowiskiem (O10), karta odbiorcy z obiema tożsamościami; tożsamość zapasowa nie trafia na nośnik ani na dysk komputera | złe i dobre hasło, zmiana hasła przepakowuje tylko klucz, nośnik w drugim katalogu stanu (drugi komputer); paczka zapasowa otwiera się tylko swoim hasłem, a w katalogu stanu nie ma jej klucza | rozstrzygnięcie 3 |
| S5: kopie na dysku (#156) | co 5 min kopia bazy (API kopii SQLite, `PRAGMA integrity_check`), tożsamości i pliku kont na dysk komputera, w katalogu stanu, ze znacznikiem „kopia” w samej kopii; trzy ostatnie; nieudany zapis ponawiany po minucie i wpisany raz do dziennika działań (z wpisem o wznowieniu), bez komunikatu w panelu; kopia otwiera się samym hasłem stanowiska (opakowanie w nagłówku), a nowe hasło przepakowuje kopie; ten sam zapis na drugi nośnik i usuwanie kopii jako funkcje (`kopie.py`), a wiek najnowszej kopii w `/health`, w przekazaniu zmiany i kopia na drugi nośnik przy przekazaniu zmiany wchodzą do panelu w S7 | zegar wstrzykiwany; zapis przerwany w połowie zostawia trzy poprzednie; błąd zapisu nie przerywa przyjęć i nie daje alarmu | S4 |
| S6: odzyskanie (#157) | odtworzenie z najnowszej kopii z dysku, a bez niej z drugiego nośnika (`odtworz` na pusty nośnik); zgoda dwóch dyżurnych; tryb odzyskania: potwierdzenie zegara, liczba odzyskań n, w jednej transakcji P = P z kopii + 86 400 s × (1 + n), wpis w dzienniku i znacznik znika, potem nowa kopia i dopiero wysyłka; do końca odzyskania brak nadawania i kopii (trzy dobre kopie zostają); pytania o zegar i n zadaje panel (S7) | przykład z kopią 09:00 i STATUS 10:00; dwa odzyskania po sobie; restart po odzyskaniu nie jest blokowany | S5, S3 |
| S7: panel dyżurnego (#158) | panel na 127.0.0.1 z zabezpieczeniami panelu laptopa (wspólna klasa `web.SecureHandler`: Host, ciasteczko z jednorazowego odnośnika, POST w JSON z własnym Origin); logowanie kontem dyżurnego i blokada po 5 min bez aktywności; kolejka według pilności i czasu, alarm dźwiękowy przy pilności 2 do PRZECZYTANE albo wyciszenia, PRZECZYTANE, TEST osobno i zbiorczo po sprawdzeniu adresu każdego, stany 3–6 z regułami (3 ze źródłem i czasem, 4 z adresatem i czasem, oba tylko w bazie i dzienniku; 5 tylko razem z REPLY), REPLY, kwarantanna (zatwierdzenie pojedynczej wiadomości albo odrzucenie, alarm stacji usuniętej z liczbą wiadomości), lista zaufanych (dodanie z karty po porównaniu odcisku, za zgodą drugiego dyżurnego wpisaną w tym samym oknie; usunięcie przez jednego), stan węzła, ogłoszenie na polecenie, przekazanie zmiany z podsumowaniem i kopią na drugi nośnik, koniec trybu odzyskania, nowe hasła; odtworzenie z kopii zostaje poleceniem `odtworz` (S6), bo przy uszkodzonym nośniku aplikacja nie startuje | testy operacji bez HTTP (`Dyzur`) i HTTP z biletem, ciasteczkiem i Origin; reguły stanów; obejrzenie w przeglądarce | S3, S4 |
| S8: ogłoszenia i BULLETIN | ogłoszenie po starcie (stos), po ponownym połączeniu ze stacją, co 6 h ±20% i na polecenie (S7), nie w trybie odzyskania; BULLETIN z nowym `id` osobno do każdej zaufanej stacji, po RECEIVED i STATUS, najwyżej 4 w drodze, z postępem w panelu; zapisy ewidencji wysyłki (próba, DELIVERED) bez osobnej migawki (O06: przy 11 500 zgłoszeniach baza ma 5,8 MB, migawka 11 ms na M5 Pro) | zegar wstrzykiwany; komunikat do kilku stacji z postępem; brak migawki po samej ewidencji | S7 |
| S9: zakończenie (#160) | eksport rejestru do CSV (kolumny ze specyfikacji, bez kluczy i adresów LXMF), ZAMKNIJ ZDARZENIE (archiwum i usunięcie treści, także z intencji REPLY i BULLETIN w tabeli `outbox`), „usuń kopie” z dysku komputera i drugiego nośnika po potwierdzeniu odbioru archiwum, ZNISZCZ DANE: nośnik, kopie na dysku i drugi nośnik, jeśli podłączony, bez ostatniej migawki, potem koniec aplikacji. Do czasu D13 archiwum (baza i rejestr w zip) jest zaszyfrowane kluczem opakowanym nowym hasłem archiwum (6 słów, PBKDF2 jak nośnik), które panel pokazuje raz; otwiera je polecenie `archiwum`. Rejestr bierze zdarzenia z tabel modelu i z dziennika działań, który od S9 ma kolumny stacji, `id` i rewizji. Decyzje autora 2026-10-30: CSV zostaje jawny, ale ZAMKNIJ ZDARZENIE usuwa pliki CSV z nośnika; wiersz „cisza” z wpisu dyżurnego (polecenie, włączenie na węźle, odwołanie) z komunikatem BULLETIN o ciszy; archiwum na haśle archiwum do D13, potem klucz publiczny administratora | po każdej operacji brak plików z treścią w katalogach; CSV zgodny z nagłówkiem, bez kluczy i adresów LXMF; archiwum otwiera się tylko swoim hasłem; kopie sprzed zamknięcia nie wypadają z rotacji do „Usuń kopie”, a kopie i migawka po zamknięciu nie mają treści (`secure_delete`, `VACUUM`) | S5; archiwum: D13 |
| S10a: symulator (#161) | port danych węzła na TCP w `swiat.mjs` (`--stanowisko karta.json`, `--wezel`), stacje z kartą odbiorcy aplikacji, aplikacja zamiast `post.cpp` w świecie; `--port tcp:<host>:<port>` w aplikacji przez pseudoterminal (KISSInterface otwiera tylko port szeregowy), więc tylko macOS i Linux | TEST ze stacji świata przez węzeł do kwarantanny aplikacji, po zatwierdzeniu RECEIVED dostarczone (intencja kończy się na DELIVERED); w zadaniu `stanowisko` CI | S8 |
| S10b: pakiet (#162) | `build/build_stanowisko.py`: te same środowiska Pythona co pamięć USB (`runtimes.json`), cała biblioteka standardowa bez testów, Tk i IDLE (Reticulum ładuje moduły po nazwie), Reticulum i LXMF gitem przy przypiętym commicie sprawdzanym po identyfikatorze (jak `firmware/tools/stack_deps.py`), pyserial z PyPI z sumą SHA-256 (`build/stanowisko.json`), aplikacja jako pliki z modelem wzorcowym obok `wzorzec.py`, skrypty `stanowisko.sh` i `stanowisko.cmd`, licencje, archiwa źródeł i manifest; bez programów START | budowa pakietu Linuksa w CI, sprawdzenie stosu interpreterem z pakietu (kryptografia Reticulum, nie `cryptography`), `SimulatorTest` z aplikacją z pakietu; części budowy w `PackageTest` | S10a |
| S11: stan węzła z portu diagnostyki (#163) | aplikacja otwiera obok KISS drugi interfejs USB węzła (diagnostyka, ten sam przewód) i co kilka sekund wysyła tylko `INFO`: zmiana `silence` daje wiersz „cisza” w rejestrze i napis w panelu obok wpisów dyżurnego, a `radio_ok` i dług ciszy trafiają do widoku węzła; bez zmian w KISS, Reticulum i firmware (decyzja autora 2026-10-30); w symulatorze port diagnostyki węzła na TCP | fałszywy port; świat symulatora z przełącznikiem CISZA węzła | S9, S10a |

Kolejność: S1–S3 dają przyjmowanie i odpowiedzi, czyli rdzeń O01–O03; S4–S6 trwałość (O07, O10), od której zależy sens kopii z 2026-10-30; S7–S9 panel i zakończenie zdarzenia. Etap L1 (START z dysku) jest niezależny i może iść równolegle.

**Rozstrzygnięcia autora (2026-10-30), plan przyjęty:**

1. Komputer stanowiska i laptop schronienia to dwa rodzaje sprzętu. Komputer stanowiska jest kontrolowany i przygotowany zawczasu (pakiet stanowiska, pełne szyfrowanie dysku, nośnik USB SSD); zasada „dowolny laptop przyniesiony w kryzysie” dotyczy tylko laptopa schronienia. Kopia co 5 min na wewnętrzny dysk trafia więc na komputer stanowiska, nie na cudzy laptop.
2. Pakiet stanowiska zawiera Reticulum `e40191b`, LXMF `c3ff2d6` i `pyserial` 3.5 (BSD; importuje go interfejs KISS Reticulum) w przypiętych wersjach, ze źródłami i licencjami. Własny port szeregowy laptopa nie zastępuje `pyserial`, bo wymagałoby to zmiany kodu stosu (D19). W S1 do sprawdzenia, czy Reticulum z pakietu działa bez `cryptography` (wbudowane implementacje w Pythonie) i jakie ma tempo przy 164 zgłoszeniach/h.
3. Klucz nośnika wyprowadza PBKDF2-HMAC-SHA256 zamiast Argon2id, z numerem wersji formatu w pliku, żeby D13 mogło wymienić funkcję bez zmiany reszty. Przed S4 powstaje notatka ze źródłami do przeglądu: skąd PBKDF2 na każdym systemie z listy START (D04) i jak robi to [syscrypto.py](wici/syscrypto.py), liczba iteracji według aktualnych OWASP i NIST SP 800-132 z czasem na słabym laptopie, długość soli, entropia hasła stanowiska z listy słów, format pliku. Poprawka specyfikacji (Argon2id → PBKDF2) wchodzi w PR etapu S4.
4. Pozostałości kopii na SSD po ZNISZCZ DANE: ryzyko szczątkowe przyjęte i opisane w [stanowisku odbiorczym](../../docs/spec/stanowisko-osp.md#komputer-i-aplikacja-stanowiska), bez nowego kroku w instrukcji dyżurnego i bez osobnego klucza w magazynie systemowym.

## Próby na sprzęcie (do macierzy D04)

CI sprawdza budowę i start na czystych systemach, ale nie zastąpi prawdziwych laptopów i stacji:

1. Stacja pilotażowa przez USB na Windows 10, Windows 11, macOS Apple Silicon, macOS Intel, Ubuntu i Fedora: wykrycie, konfiguracja, karta, odłączenie przewodu w trakcie transferu.
2. Start z pamięci FAT32 na każdym z nich, w tym Linux z automatycznym montowaniem (`showexec`). Na macOS zanotować, czy pojawia się pytanie o dostęp do plików na woluminie wymiennym („Removable Volumes”), od której wersji systemu i czy po odmowie aplikacja pokazuje czytelny komunikat.
3. Laptop służbowy z kontem bez uprawnień administratora i z programem antywirusowym: tryb kiosku, komunikat o zaporze, uruchomienie Linuksa z USB.
4. Najstarszy obsługiwany sprzęt: Windows 10 22H2 na laptopie z 4 GB RAM, Mac z Intelem na macOS 10.15.
5. Ile przyniesionych laptopów pozwala uruchomić system z USB (menu startowe, Secure Boot, hasło BIOS-u): od tego zależy, jak często zadziała ścieżka 3.
6. Wyjęcie pamięci zestawu przy działającej aplikacji na prawdziwych laptopach z każdym systemem: aplikacja działa dalej z kopii na dysku (sprawdzone 2026-10-30 na macOS z obrazem dysku FAT32, w CI na każdym systemie przeniesieniem katalogu pamięci), ponowny START pod inną literą dysku przenosi zapis kopii, a pierwszy START ze zwykłej pamięci USB 2.0 trwa akceptowalnie (kopia około 20 MB).
7. Strona dla telefonów z kilkoma routerami domowymi i telefonami z Androidem i iOS, w tym telefon z włączonymi danymi komórkowymi.

## Rozstrzygnięcia i odrzucone warianty

| Wybór | Uzasadnienie |
|---|---|
| Python z biblioteką standardową, bez pyserial | port szeregowy to około 260 wierszy; każda zależność to kolejne licencje, wersje i pliki na USB |
| python.org embeddable na Windows, python-build-standalone na macOS i Linuksie | embeddable ma pliki podpisane przez PSF (mniej fałszywych alarmów); dla macOS i Linuksa nie ma oficjalnego środowiska przenośnego |
| wspólna biblioteka standardowa przez `._pth` | jedna kopia zamiast czterech; zapasowo każdy system może mieć własną kopię w `lib/python314.zip` (+2,2 MB na system) |
| bajtkod biblioteki `-OO`, aplikacja jako źródła | biblioteka jest mniejsza; aplikacja zostaje czytelna i niezależna od wersji bajtkodu (79 KB) |
| panel w przeglądarce | przeglądarka jest na każdym laptopie; ten sam mechanizm obsłuży stronę mieszkańca |
| wyszukiwanie stacji po `hello` | działa przed przydziałem VID/PID i nie wysyła niczego do cudzych urządzeń |
| odrzucone: Electron, Tauri, Go, Web Serial, okno natywne | uzasadnienia w poprzedniej analizie: waga, drugi język, brak trwałego zapisu i magazynu kluczy, dwa interfejsy |
| odrzucone: osobna biblioteka standardowa na każdy system | +6,6 MB bez zysku dla użytkownika |
| odrzucone: kompresja binarek (UPX) | około −40 MB, ale skompresowane pliki wykonywalne często budzą alarmy antywirusów na Windows i psują podpisy na macOS |
| odrzucone na etap 1: własna kompilacja Pythona z mniejszą liczbą modułów | może zejść do około 50 MB, ale oznacza własny łańcuch kompilacji na trzy systemy i utratę gotowych, sprawdzanych kompilacji; na pamięci 64 GB z zestawu różnica jest dla użytkownika niewidoczna |
| macOS od 10.15 (Intel) i od 11 (Apple Silicon) | tyle wymagają dołączone interpretery; starsze Maki z Intelem w gminach wciąż się zdarzają; najstarszy obsługiwany system sprawdzany ręcznie przed wydaniem (2026-10-14) |
| odłożone: Linux na ARM | laptopy w obiektach to prawie wyłącznie x86_64; +30 MB i runner ARM w CI (2026-10-14) |
| podpisy: Apple Developer ID z notaryzacją, Windows przez SignPath Foundation | na macOS 15 niepodpisanej aplikacji nie otworzy się prawym kliknięciem. Warunki SignPath ([signpath.org/terms](https://signpath.org/terms), sprawdzone 2026-10-14): licencje OSI dla wszystkich składników, bez części zamkniętych; podpis tylko z automatycznej budowy z repozytorium projektu; projekt utrzymywany i już wydany w podpisywanej postaci; wydawcą w certyfikacie jest „SignPath Foundation”; MFA i role autorów, recenzentów i zatwierdzających; sekcja „Code signing policy” na stronie pobierania; nazwa i wersja produktu w metadanych pliku (START-WINDOWS.exe potrzebuje zasobu VERSIONINFO); każde wydanie zatwierdzane ręcznie (2026-10-14) |
| klucz podpisu manifestu w 1Password, podpis w CI przy tagu wydania | wygoda wydań; podpis tylko z chronionego środowiska GitHub (`environment` z wymaganym zatwierdzeniem) i tylko dla tagów, żeby sam dostęp do repozytorium nie wystarczał do podpisania fałszywej pamięci (2026-10-14) |
| nazwa stacji wielkimi literami (`WICI-4CBAAD`) | tak działa firmware i ekran; czytelniej na małym ekranie i przy dyktowaniu; aplikacje porównują bez rozróżniania wielkości liter; specyfikacja poprawiona (2026-10-14) |
| plik karty odbiorcy `{"wici":"karta-odbiorcy","v":1,"main":{…},"backup":{…}}` | plik mówi, czym jest; wersja pozwala zmienić format; aplikacja odrzuca inne pliki z jasnym komunikatem (2026-10-14) |
| identyfikator USB z pid.codes (VID 0x1209) | darmowy dla otwartego sprzętu, niezależny od mikrokontrolera. Warunki ([pid.codes/howto](https://pid.codes/howto/), sprawdzone 2026-10-14): publiczne repozytorium z plikiem licencji, projekt płytki i oprogramowanie na uznanych licencjach otwartych (WICI: CERN-OHL-P i MIT); wniosek to pull request do `pidcodes/pidcodes.github.com` z plikami `org/<organizacja>/index.md` i `1209/<PID>/index.md` (pola `license` i `source`), PID spoza zakresów 0xxx i 1xxx; wniosek do akceptacji (2026-10-14) |
| obraz startowy: Debian live z shim | Secure Boot, długie wsparcie, około 1–1,5 GB (2026-10-14) |
| router obiektu, laptop przyniesiony na miejscu | [Laptop i router na miejscu](#laptop-i-router-na-miejscu) (2026-10-14) |
| baza w pamięci procesu, zaszyfrowane migawki na dysku (łączone, przed potwierdzeniem zmiany) i na pamięci USB (w tle, zaraz po migawce na dysku, na zmianę do dwóch plików), „Oddaj laptop” usuwa migawki z dysku | baza otwarta na FAT32 lub exFAT mogłaby się uszkodzić przy wyrwaniu pamięci albo zaniku zasilania, a jawna baza na dysku zostałaby u właściciela laptopa; kopia pozwala przejść na inny laptop, a dane nie zostają u właściciela laptopa (2026-10-14). Kopia w dwóch plikach na zmianę z numerem pokolenia i historią sesji objętymi MAC, `fsync` (macOS `F_FULLFSYNC`); wygrywa kopia, która jest kontynuacją drugiej, więc laptop wracający po awarii nie nadpisuje nowszej; rozeszłe kopie wybiera człowiek, odrzucona zostaje na pamięci (2026-10-21). Zmierzone 2026-10-21 na MacBooku: 1000 zgłoszeń po 300 B (0,35 MB), 15 wątków po 10 zgłoszeń: 150 zmian w 21 migawkach, potwierdzenie najwyżej 20 ms |
| kopię otwiera hasło logowania konta | klucz danych opakowany dla każdego konta kluczem z PBKDF2(hasło konta, `keys/zestaw.key` i sól); poprawne odpakowanie jest sprawdzeniem hasła, bez osobnego skrótu do logowania, który dawałby to samo zgadywanie poza aplikacją; logowanie i tak jest potrzebne, więc wymiana laptopa nie dodaje kroku, a sama pamięć USB nie wystarcza; kto ją zabierze, może zgadywać hasła poza aplikacją, więc ochronę daje siła hasła (5 słów) i liczba iteracji PBKDF2 (2026-10-21) |
| szyfr i PBKDF2 z kryptografii systemu | AES-256-CBC + HMAC-SHA256 i PBKDF2-HMAC-SHA256 z Windows CNG, macOS CommonCrypto i Linux libcrypto; 0 MB na pamięci, ten sam format wszędzie. Interpretery python-build-standalone ukrywają swoje OpenSSL: `ctypes.CDLL(None)` na macOS trafia do prywatnego `libboringssl` i miesza implementacje (sprawdzone 2026-10-21). Odrzucone: pakiet `cryptography` (+15–20 MB, od 49.0.0 bez Maców z Intelem), scrypt (na Windows +6 MB libcrypto) (2026-10-21) |
| lista 4096 słów bez polskich liter do haseł z kopert | laptop przyniesiony na miejscu może nie mieć polskiego układu klawiatury; 4096 zamiast 7776, bo druga połowa listy 7776 to słowa rzadkie i śmieci z napisów; 5 słów to 60 bitów, 6 słów 72 bity. Formy podstawowe ze słownika odmian SJP.PL (CC BY 4.0; w repozytorium [sjp-lematy.txt](build/slowa/sjp-lematy.txt), bo SJP.PL usuwa poprzednie wydanie po opublikowaniu nowego) według częstości samej formy w FrequencyWords (OpenSubtitles 2018, CC BY-SA 4.0), bez 20 000 najczęstszych słów angielskich i bez [wykluczonych](build/slowa/wykluczone.txt); cała lista przejrzana ręcznie (2026-10-21) |
| odrzucone: dziennik do jawnego CSV i wydruk dziennika z panelu | jawny plik łamie zasadę, że na cudzym laptopie i na pamięci USB są tylko zaszyfrowane dane; wydruk niepotrzebny, bo zdarzenia wpisuje się do dziennika papierowego, a historia jest w panelu (2026-10-21) |
| licencje bibliotek interpretera z pełnego archiwum PBS, przechowane w repozytorium | archiwum `install_only` ma tylko licencję CPythona, a interpreter zawiera statycznie OpenSSL, libffi, SQLite, expat, mpdecimal, zstd i inne; pełne archiwum (61–111 MB) pobiera się raz przy zmianie wersji, nie przy każdej budowie; licencji zstd brakuje w archiwum PBS, więc pochodzi z LICENSE.txt python.org (2026-10-21) |
| bez magazynu systemowego (DPAPI, Keychain) | klucz danych nie trafia na dysk laptopa, otwiera go tylko logowanie, więc magazyn nie miałby czego chronić, a dodałby kod dla każdego systemu (2026-10-21) |
| główna sieć Wi-Fi budynku za pisemną zgodą zarządcy, zmiana hasła po zdarzeniu | telefony w głównej sieci widzą komputery, drukarki i dyski budynku, a hasło z kodu QR zostaje znane; sieć gościnna zwykle nie widzi laptopa, więc jest pierwsza tylko wtedy, gdy telefony widzą w niej laptop (2026-10-21) |

## Do zrobienia po rozstrzygnięciach

1. Etap 2, baza i zestaw w panelu: gotowe w [database.py](wici/database.py) i [session.py](wici/session.py) z testami (2026-10-21). Zostaje: pomiar czasu do odpowiedzi 201 (zapis potwierdzony migawką na dysku) na laptopie z dyskiem HDD i na pamięci USB 2.0, próba wydruku kopert na kilku przeglądarkach.
2. Próba zapory na czystym Windows 11 (sekcja [Laptop i router na miejscu](#laptop-i-router-na-miejscu)).
3. Wnioski do SignPath i pid.codes po akceptacji (warunki w tabeli rozstrzygnięć). SignPath wymaga wcześniejszego wydania w podpisywanej postaci, więc pierwsze wydanie START-WINDOWS.exe jest bez podpisu; przed wnioskiem zasób VERSIONINFO i strona z „Code signing policy”.
4. Licencje środowisk przejrzane 2026-10-21: na pamięci są licencje bibliotek wkompilowanych w interpreter python-build-standalone i kodu wbudowanego w CPython ([build/licencje/](build/licencje/zrodla.json)); bez GPL i LGPL, więc bez obowiązku udostępnienia źródeł. Zostaje przed pierwszą dystrybucją: potwierdzić, że kod startowy MinGW-w64 w `START-WINDOWS.exe` nie wymaga informacji o autorach.
5. Stanowisko odbiorcze: PBKDF2-HMAC-SHA256 z wersją formatu zamiast Argon2id (rozstrzygnięcie 3 wyżej, etap S4); inną funkcję może wprowadzić D13.
6. Eksporty (2026-10-21): powstają w etapie 3 razem z ZAMKNIJ ZDARZENIE, po D13 (administrator danych i jego klucz publiczny), bo dziś baza ma tylko dziennik czynności, a jedynym wymaganym eksportem jest zaszyfrowane archiwum dla gminy. Ryzyko do sprawdzenia przed D13: szyfrowanie kluczem publicznym z kryptografii systemu; CommonCrypto w macOS go nie ma, a Curve25519 jest tylko w CryptoKit (Swift), więc format klucza gminy prawdopodobnie ECDH P-256 z Security.framework. ZNISZCZ DANE musi usuwać eksporty razem z migawkami.

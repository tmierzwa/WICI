# Aplikacja laptopa WICI: plan

Aplikacja działa na każdym znalezionym laptopie z Windows, macOS albo Linuksem, uruchamiana z pamięci USB zestawu, bez instalowania i bez internetu (decyzja z 2026-10-13: wariant A, wszystkie systemy od początku). Zestaw nie ma laptopa, a laptopa nie przygotowuje się wcześniej: w kryzysie ktoś przynosi dowolny laptop, a gdy ten nie zadziała, sprawdza się następny (decyzja z 2026-10-14). Aplikacja robi więc sama wszystko, co da się zrobić na nieznanym, nieprzygotowanym laptopie, a resztę opisuje instrukcja. Kontrakt ze stacją jest gotowy w [protokole USB](../../docs/spec/protokol-usb.md); wymagania strony, panelu i pakietu w [specyfikacji oprogramowania](../../docs/spec/oprogramowanie.md#api-lokalnej-strony-poziomy-23).

Plan rozpisuje, co jest zrobione (etap 1), jak aplikacja radzi sobie z różnymi systemami, ile zajmuje na pamięci USB, co dalej i co trzeba jeszcze rozstrzygnąć.

## Etap 1: zrobione

Narzędzie trybu przygotowania i fundament dla następnych etapów.

| Część | Co robi | Plik |
|---|---|---|
| Port szeregowy | Windows (kernel32 przez ctypes), macOS i Linux (termios), wyłącznie biblioteka standardowa | [serialport.py](wici/serialport.py) |
| Protokół `"usb":2` | wątek odczytu, `seq`, `pending` z przyciskiem, ponowienie po `seq`, transfery w częściach, wyszukiwanie stacji po `hello`, ponowne połączenie | [usbproto.py](wici/usbproto.py) |
| Dokument `configure` | reguły pól jak w firmware, tekst według SA1, zgodność adresu LXMF z kluczem, różne tożsamości odbiorcy | [configdoc.py](wici/configdoc.py) |
| Czynności przygotowania | odczyt i zapis konfiguracji, karta stacji, komunikaty po polsku | [prep.py](wici/prep.py) |
| Dziennik | SQLite, tylko dopisywanie (wyzwalacze), bez treści i bez kodu sieci; w zaszyfrowanej bazie, więc czynności na stacji wymagają zalogowania; także logowania, nowe hasła i oddanie laptopa | [store.py](wici/store.py) |
| Zestaw i logowanie | pamięć zestawu to ta, z której działa START (albo `WICI_USB`); nowa pamięć: konta gospodarza i 0–5 zastępców oraz hasło odtworzenia, hasła pokazane raz z numerami kopert i wydrukiem; logowanie, wybór kopii przy konflikcie, odtworzenie hasłem odtworzenia z nowymi kontami, nowe hasło po otwarciu koperty, wylogowanie, „Oddaj laptop”; ponowny START z pamięci włożonej pod inną literą dysku przenosi tam zapis kopii | [session.py](wici/session.py) |
| Baza laptopa | konta zestawu na pamięci USB (opakowanie klucza danych dla każdego konta i hasłem odtworzenia, limit prób), SQLite w pamięci, łączone zaszyfrowane migawki na dysku i w tle na pamięci USB, wybór kopii po historii sesji, konflikt, „Oddaj laptop”, ZNISZCZ DANE | [database.py](wici/database.py) |
| Panel | HTTP tylko na 127.0.0.1, token w ciasteczku, kontrola Host i Origin, CSP; długie odpytywanie stanu; ekrany zestawu, logowania i kopert, zakładka „Zestaw” ze stanem kopii | [web.py](wici/web.py), [ui/](wici/ui/index.html) |
| Start | jedna instancja, przeglądarka, blokada uśpienia, `--selftest` | [\_\_main\_\_.py](wici/__main__.py), [awake.py](wici/awake.py) |
| Pamięć USB | przypięte środowiska Pythona, przycinanie, wspólna biblioteka, START dla trzech systemów, manifest | [build/build_usb.py](build/build_usb.py) |
| Symulator | obraz firmware bench-b z portem danych na TCP: praca i testy bez płytki | [dev/sim-station.mjs](dev/sim-station.mjs) |
| Testy | jednostkowe, bezpieczeństwo panelu, budowa USB, pełne przygotowanie na obrazie firmware | [tests/test_laptop.py](../../tests/test_laptop.py) |
| CI | testy na Windows, macOS i Linuksie; pamięć USB budowana i uruchamiana przez START na każdym systemie; budżet rozmiaru | [.github/workflows/laptop.yml](../../.github/workflows/laptop.yml) |

Czego etap 1 celowo nie ma: PRZENIEŚ STACJĘ i aktualizacji oprogramowania (firmware jeszcze ich nie realizuje, [przegląd F107](../../docs/review.md)), logowania hasłami z kopert (narzędzie przygotowania obsługuje osoba utrzymująca system na własnym komputerze; panel gospodarza w etapie 2 je dostaje) oraz strony mieszkańca (tryb kiosku w etapie 2, strona dla telefonów w etapie 3).

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

Jeden proces Pythona z biblioteką standardową i bez zależności zewnętrznych; szyfr i PBKDF2 pochodzą z kryptografii systemu przez ctypes ([syscrypto.py](wici/syscrypto.py)). Panel to strona w przeglądarce, która i tak jest na każdym laptopie; ta sama technika posłuży stronie mieszkańca w etapie 3, więc nie ma drugiego interfejsu.

```text
przeglądarka ──HTTP 127.0.0.1──▶ web.py ──▶ prep.py ──▶ usbproto.Station ──▶ serialport ──USB CDC──▶ stacja
                                   │                         (wątek: hello, status, ponowne połączenie)
                                   └──▶ store.Journal (SQLite, katalog stanu systemu)
```

Stan: Windows `%LOCALAPPDATA%\WICI`, macOS `~/Library/Application Support/WICI`, Linux `~/.local/share/wici`; zmienna `WICI_STATE` wskazuje inny katalog (obraz startowy Linuksa: partycja ext4 pamięci USB, zgodnie ze specyfikacją). Zaszyfrowana kopia bazy po każdej zmianie trafia na pamięć USB (etap 2).

Bezpieczeństwo panelu: inne strony otwarte w tej samej przeglądarce nie mogą sterować stacją. Bez tokenu z odnośnika START nie ma ciasteczka; nagłówek Host musi wskazywać 127.0.0.1 (chroni przed DNS rebinding); POST wymaga JSON i własnego Origin; CSP blokuje skrypty spoza aplikacji.

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
| pamięć FAT bez prawa wykonywania (Linux `showexec`, `noexec`) | START-LINUX.sh kopiuje raz środowisko do `~/.cache/wici/<wersja>` | CI: `chmod -x` i ponowny start |
| macOS: Apple Silicon i Intel | jeden START-MAC.app wybiera środowisko po `uname -m` i `sysctl.proc_translated` | CI na obu procesorach |
| Gatekeeper, SmartScreen, antywirus | pliki Windows podpisane przez PSF; przed pilotażem poziomów 2–3 START-MAC.app z Apple Developer ID i notaryzacją, START-WINDOWS.exe z podpisem przez program SignPath dla projektów otwartych; do tego czasu instrukcja na USB podaje, jak uruchomić | do próby T1/T8 |
| stara albo inna przeglądarka | ES2017, bez bibliotek, bez CSS z ostatnich lat; fonty systemowe z cyrylicą | do macierzy D04 |
| drugi START | `instance.json` w katalogu stanu: drugi START prosi działającą instancję o nowy jednorazowy odnośnik (`POST /api/ticket` z tokenem panelu) i otwiera nim panel; sprawdzenie omija proxy systemu (laptopy firmowe) | kod |
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
| z każdego środowiska tylko interpreter i potrzebne moduły binarne: bez Tcl/Tk, testów, nagłówków, pip, TLS, OpenSSL na Windows (AES i PBKDF2 daje system); bez `libpython`, bo interpreter python-build-standalone jest zlinkowany statycznie i zawiera ją w sobie | zmierzone: Linux 32,5 MB, macOS arm64 18,9 MB, macOS x86_64 19,8 MB, Windows 10,2 MB (zamiast 66, 38, 40 i 16 MB z `libpython` i OpenSSL) |
| aplikacja jako jeden ZIP ze źródłami | zmierzone: 36 KB |
| jeden START-MAC.app zamiast dwóch | jedna ikona i jedna instrukcja dla użytkownika |
| bez zewnętrznych bibliotek JS i CSS, fonty systemowe | panel: 47 KB z logo |

Zmierzona cała pamięć poza obrazem startowym Linuksa: 83,6 MB, z czego 81,3 MB to cztery interpretery, 2,2 MB wspólna biblioteka, a reszta to aplikacja, START i licencje. Szacunek przed pierwszym pomiarem (30–45 MB) nie uwzględniał, że interpretery python-build-standalone mają wkompilowane wszystkie moduły binarne. Rozmiar 84 MB przyjęty 2026-10-14. Budżet: 90 MB (`BUDGET` w build_usb.py; zadanie `size` w CI przerywa budowę po przekroczeniu), czyli zapas na drobne zmiany, a nie na nowe środowisko. SHA-256 bez OpenSSL zapewnia wbudowany moduł `_sha2`. Kompletność przyciętej biblioteki sprawdza `--selftest` na każdym systemie. Dwie luki znalezione w ten sposób przy budowie planu: `runpy` i `pkgutil` (start z ZIP) oraz `ctypes._layout` i `stringprep` (ładowane z kodu w C).

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

- przed nasłuchem w sieci lokalnej sprawdza, czy jest reguła WICI; bez niej nie otwiera portu, żeby nie wywołać alertu zapory, bo anulowanie alertu przez zwykłego użytkownika zapisuje reguły blokujące dla `pythonw.exe` z pamięci USB, a reguły blokujące mają pierwszeństwo;
- przyciskiem „Zezwól telefonom na połączenie” uruchamia przez UAC sam `netsh` (podpisany przez Microsoft) z regułą tylko dla portu, na którym słucha strona (zwykle 8080), nie programu, bo litera dysku pamięci się zmienia: `netsh advfirewall firewall add rule name="WICI strona mieszkańca" dir=in action=allow protocol=TCP localport=<port> remoteip=localsubnet profile=any`; ten sam krok usuwa reguły blokujące, które Windows utworzył dla interpretera z bieżącej ścieżki pamięci (rozpoznane po ścieżce programu, bo nie mają nazwy WICI);
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

Próba na czystym Windows 11 (maszyna wirtualna) z kontem standardowym przed implementacją etapu 3: alert i anulowanie, odczyt reguł, okno UAC, reguła portu i jej usunięcie.

**Diagnostyka w panelu:** brak kabla, kabel w gnieździe WAN, brak adresu IP, profil sieci „Publiczna”, brak reguły zapory, zero połączonych telefonów po kilku minutach.

**Instrukcja opisuje resztę:** kolejność dróg jak w tabeli; system Linux z pamięci USB tylko za zgodą właściciela laptopa; nadzór nad laptopem w trybie kiosku; „Oddaj laptop” przed zwrotem; zmiana hasła Wi-Fi przez zarządcę po zdarzeniu; kabel do gniazda LAN routera, nie WAN; laptop bez gniazda sieciowego łączy się z Wi-Fi routera i działa, jeśli router nie izoluje urządzeń od siebie (adapter USB–Ethernet przy pamięci USB to opcja, nie wymóg); telefony w sieci, którą wskaże panel (zwykle głównej, za zgodą zarządcy); routery domowe mają zwykle limit około 32 urządzeń, więc mieszkańcy korzystają kolejno; cudzego routera nie resetuje się; router zasilany ze stacji zasilania albo UPS; Android pyta o sieć bez internetu („pozostań połączony”), a gdy strona się nie otwiera, wyłącza się dane komórkowe (do potwierdzenia na kilku telefonach); tabela klawiszy menu startowego według producenta i co zrobić przy zablokowanym menu.

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
| 2: panel gospodarza (poziom 2) i tryb kiosku | `sync`, migawka, zdarzenia i `ack` z kursorem w SQLite; `submit`, `cancel`, `test`, `announce`, `mark_read`; `silence`, `close`, `destroy` z potwierdzeniem przyciskiem; niepewny wynik polecenia; logowanie hasłami z kopert (PBKDF2 z kryptografii systemu); kopia bazy na pamięci USB z opakowaniem klucza dla każdego konta, dwoma plikami na zmianę i numerem pokolenia; „Oddaj laptop”; przekazanie zmiany; strona mieszkańca w trybie kiosku na ekranie laptopa (formularz w trzech językach, lokalne numery, kolejka gospodarza), bo działa na każdym laptopie bez sieci | firmware z pełnym kontraktem w2 |
| 2a: przygotowanie, ciąg dalszy | PRZENIEŚ STACJĘ (pięć kroków z wycofaniem), aktualizacja oprogramowania stacji z podpisanego obrazu | firmware (F107) |
| 3: strona dla telefonów (poziom 3) | wybór interfejsu i adresu (`getifaddrs`, `GetAdaptersAddresses` przez ctypes), nasłuch tylko na nim, tokeny mieszkańców, kody QR sieci i adresu (własny koder, kilka KB), plakat A4, reguła zapory Windows przez UAC, diagnostyka | etap 2; próba zapory na czystym Windows 11 |
| 4: wydanie | parametry szyfrowania migawek, baza w pamięci (D13; bez SQLCipher i bez wolumenu wymagającego administratora), ZNISZCZ DANE na laptopie, obraz startowy Linuksa (Debian live z shim; droga dla laptopów z Windows bez administratora), podpis manifestu w CI, podpisy START, macierz D04 na prawdziwych laptopach | D13, D04 |

## Próby na sprzęcie (do macierzy D04)

CI sprawdza budowę i start na czystych systemach, ale nie zastąpi prawdziwych laptopów i stacji:

1. Stacja pilotażowa przez USB na Windows 10, Windows 11, macOS Apple Silicon, macOS Intel, Ubuntu i Fedora: wykrycie, konfiguracja, karta, odłączenie przewodu w trakcie transferu.
2. Start z pamięci FAT32 na każdym z nich, w tym Linux z automatycznym montowaniem (`showexec`).
3. Laptop służbowy z kontem bez uprawnień administratora i z programem antywirusowym: tryb kiosku, komunikat o zaporze, uruchomienie Linuksa z USB.
4. Najstarszy obsługiwany sprzęt: Windows 10 22H2 na laptopie z 4 GB RAM, Mac z Intelem na macOS 10.15.
5. Ile przyniesionych laptopów pozwala uruchomić system z USB (menu startowe, Secure Boot, hasło BIOS-u): od tego zależy, jak często zadziała ścieżka 3.
6. Wyjęcie pamięci zestawu przy działającej aplikacji na Windows i Linuksie: czy aplikacja działa dalej (macOS zamyka ją od razu, próba z obrazem dysku FAT32 2026-10-21) i czy ponowny START pod inną literą dysku przenosi zapis kopii.
7. Strona dla telefonów z kilkoma routerami domowymi i telefonami z Androidem i iOS, w tym telefon z włączonymi danymi komórkowymi.

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
| odrzucone na etap 1: własna kompilacja Pythona z mniejszą liczbą modułów | może zejść do około 50 MB, ale oznacza własny łańcuch kompilacji na trzy systemy i utratę gotowych, sprawdzanych kompilacji; na pamięci 64 GB z zestawu różnica jest dla użytkownika niewidoczna |
| macOS od 10.15 (Intel) i od 11 (Apple Silicon) | tyle wymagają dołączone interpretery; starsze Maki z Intelem w gminach to realny przypadek; najstarszy obsługiwany system sprawdzany ręcznie przed wydaniem (2026-10-14) |
| odłożone: Linux na ARM | laptopy w obiektach to praktycznie tylko x86_64; +30 MB i runner ARM w CI (2026-10-14) |
| podpisy: Apple Developer ID z notaryzacją, Windows przez SignPath Foundation | na macOS 15 niepodpisanej aplikacji nie otworzy się prawym kliknięciem. Warunki SignPath ([signpath.org/terms](https://signpath.org/terms), sprawdzone 2026-10-14): licencje OSI dla wszystkich składników, bez części zamkniętych; podpis tylko z automatycznej budowy z repozytorium projektu; projekt utrzymywany i już wydany w podpisywanej postaci; wydawcą w certyfikacie jest „SignPath Foundation”; MFA i role autorów, recenzentów i zatwierdzających; sekcja „Code signing policy” na stronie pobierania; nazwa i wersja produktu w metadanych pliku (START-WINDOWS.exe potrzebuje zasobu VERSIONINFO); każde wydanie zatwierdzane ręcznie (2026-10-14) |
| klucz podpisu manifestu w 1Password, podpis w CI przy tagu wydania | wygoda wydań; podpis tylko z chronionego środowiska GitHub (`environment` z wymaganym zatwierdzeniem) i tylko dla tagów, żeby sam dostęp do repozytorium nie wystarczał do podpisania fałszywej pamięci (2026-10-14) |
| nazwa stacji wielkimi literami (`WICI-4CBAAD`) | tak działa firmware i ekran; czytelniej na małym ekranie i przy dyktowaniu; aplikacje porównują bez rozróżniania wielkości liter; specyfikacja poprawiona (2026-10-14) |
| plik karty odbiorcy `{"wici":"karta-odbiorcy","v":1,"main":{…},"backup":{…}}` | plik mówi, czym jest; wersja pozwala zmienić format; aplikacja odrzuca inne pliki z jasnym komunikatem (2026-10-14) |
| identyfikator USB z pid.codes (VID 0x1209) | darmowy dla otwartego sprzętu, niezależny od mikrokontrolera. Warunki ([pid.codes/howto](https://pid.codes/howto/), sprawdzone 2026-10-14): publiczne repozytorium z plikiem licencji, projekt płytki i oprogramowanie na uznanych licencjach otwartych (WICI: CERN-OHL-P i MIT); wniosek to pull request do `pidcodes/pidcodes.github.com` z plikami `org/<organizacja>/index.md` i `1209/<PID>/index.md` (pola `license` i `source`), PID spoza zakresów 0xxx i 1xxx; wniosek do akceptacji (2026-10-14) |
| obraz startowy: Debian live z shim | Secure Boot, długie wsparcie, około 1–1,5 GB (2026-10-14) |
| router obiektu, laptop przyniesiony na miejscu | [Laptop i router na miejscu](#laptop-i-router-na-miejscu) (2026-10-14) |
| baza w pamięci procesu, zaszyfrowane migawki na dysku (łączone, przed potwierdzeniem zmiany) i na pamięci USB (w tle, najpóźniej 5 s po zmianie), „Oddaj laptop” usuwa migawki z dysku | baza otwarta na FAT32 lub exFAT mogłaby się uszkodzić przy wyrwaniu pamięci albo zaniku zasilania, a jawna baza na dysku zostałaby u właściciela laptopa; kopia pozwala przejść na inny laptop, a dane nie zostają u właściciela laptopa (2026-10-14). Kopia w dwóch plikach na zmianę z numerem pokolenia i historią sesji objętymi MAC, `fsync` (macOS `F_FULLFSYNC`); wygrywa kopia, która jest kontynuacją drugiej, więc laptop wracający po awarii nie nadpisuje nowszej; rozeszłe kopie wybiera człowiek, odrzucona zostaje na pamięci (2026-10-21). Zmierzone 2026-10-21 na MacBooku: 1000 zgłoszeń po 300 B (0,35 MB), 15 wątków po 10 zgłoszeń: 150 zmian w 21 migawkach, potwierdzenie najwyżej 20 ms |
| kopię otwiera hasło logowania konta | klucz danych opakowany dla każdego konta kluczem z PBKDF2(hasło konta, `keys/zestaw.key` i sól); poprawne odpakowanie jest sprawdzeniem hasła, bez osobnego skrótu do logowania, który dawałby to samo zgadywanie poza aplikacją; logowanie i tak jest potrzebne, więc wymiana laptopa nie dodaje kroku, a sama pamięć USB nie wystarcza; kto ją zabierze, może zgadywać hasła poza aplikacją, więc ochronę daje siła hasła (5 słów) i liczba iteracji PBKDF2 (2026-10-21) |
| szyfr i PBKDF2 z kryptografii systemu | AES-256-CBC + HMAC-SHA256 i PBKDF2-HMAC-SHA256 z Windows CNG, macOS CommonCrypto i Linux libcrypto; 0 MB na pamięci, ten sam format wszędzie. Interpretery python-build-standalone ukrywają swoje OpenSSL: `ctypes.CDLL(None)` na macOS trafia do prywatnego `libboringssl` i miesza implementacje (sprawdzone 2026-10-21). Odrzucone: pakiet `cryptography` (+15–20 MB, od 49.0.0 bez Maców z Intelem), scrypt (na Windows +6 MB libcrypto) (2026-10-21) |
| lista 4096 słów bez polskich liter do haseł z kopert | laptop przyniesiony na miejscu może nie mieć polskiego układu klawiatury; 4096 zamiast 7776, bo druga połowa listy 7776 to słowa rzadkie i śmieci z napisów; 5 słów to 60 bitów, 6 słów 72 bity. Formy podstawowe ze słownika odmian SJP.PL (CC BY 4.0; w repozytorium [sjp-lematy.txt](build/slowa/sjp-lematy.txt), bo SJP.PL usuwa poprzednie wydanie po opublikowaniu nowego) według częstości samej formy w FrequencyWords (OpenSubtitles 2018, CC BY-SA 4.0), bez 20 000 najczęstszych słów angielskich i bez [wykluczonych](build/slowa/wykluczone.txt); cała lista przejrzana ręcznie (2026-10-21) |
| bez magazynu systemowego (DPAPI, Keychain) | klucz danych nie trafia na dysk laptopa, otwiera go tylko logowanie, więc magazyn nie miałby czego chronić, a dodałby kod dla każdego systemu (2026-10-21) |
| główna sieć Wi-Fi budynku za pisemną zgodą zarządcy, zmiana hasła po zdarzeniu | telefony w głównej sieci widzą komputery, drukarki i dyski budynku, a hasło z kodu QR zostaje znane; sieć gościnna zwykle nie widzi laptopa, więc jest pierwsza tylko wtedy, gdy telefony widzą w niej laptop (2026-10-21) |

## Do zrobienia po rozstrzygnięciach

1. Etap 2, baza i zestaw w panelu: gotowe w [database.py](wici/database.py) i [session.py](wici/session.py) z testami (2026-10-21). Zostaje: ZNISZCZ DANE razem z poleceniem `destroy` stacji i potwierdzeniem przyciskiem (w bazie jest już `Database.destroy`), eksporty, pomiar czasu 201 na laptopie z dyskiem HDD i na pamięci USB 2.0, próba wydruku kopert na kilku przeglądarkach.
2. Próba zapory na czystym Windows 11 (sekcja [Laptop i router na miejscu](#laptop-i-router-na-miejscu)).
3. Wnioski do SignPath i pid.codes po akceptacji (warunki w tabeli rozstrzygnięć). SignPath wymaga wcześniejszego wydania w podpisywanej postaci, więc pierwsze wydanie START-WINDOWS.exe jest bez podpisu; przed wnioskiem zasób VERSIONINFO i strona z „Code signing policy”.
4. Przegląd licencji środowisk (OpenSSL, SQLite, libffi, zlib i inne) przed pierwszą dystrybucją; lista słów (CC BY-SA 4.0) ma już plik w `licenses/` pakietu.
5. Stanowisko odbiorcze (stanowisko-osp.md) zakłada Argon2id, którego nie ma w bibliotece standardowej ani w kryptografii systemu; do rozstrzygnięcia w D13 razem z resztą szyfrowania.

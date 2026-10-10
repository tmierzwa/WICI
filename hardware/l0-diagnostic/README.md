# WICI — program diagnostyczny L0, l0-0.5

Obraz dla jednego prototypu biurkowego z paczki wyceny 2026-10-09:
ESP32-S3-DevKitC-1-N8R8 rev.1.1 + nośna N1 + Wio SX1262 +
Sharp LS027B7DH01A + FRAM CY15B104QN-50SXI albo MB85RS4MTPF-G-BCERE1 + panel.
Nie wgrywać do XIAO 102010611. Dla XIAO pozostaje osobny obraz R0 `pair-0.3`.
To diagnostyka połączeń i podzespołów, nie aplikacja WICI.

## Stan weryfikacji

Kompilacja L0 i R0 zakończona poprawnie. Testy hosta sprawdzają logikę,
raporty i USB przez pseudoporty szeregowe. Testy natywne wykonują rzeczywisty
kod firmware i sterowników na symulowanych GPIO/SPI, z sanitizacją pamięci. Nie potwierdzają działania fizycznego
sprzętu. Prototyp L0 nie został jeszcze zmontowany. R0 `pair-0.3` zaliczył próbę przy stole 2026-10-10.
`checks.json` i `SHA256SUMS.txt` zawierają wyniki i identyfikację plików.
Pole `ready=1` w INFO potwierdza inicjalizację radia, rozpoznanie FRAM i
konfigurację timerów LCD i brzęczyka; ekran nie ma kanału potwierdzania odbioru, wymaga oględzin.

## Przygotowanie wykonawcy

1. Montaż według paczki RFQ, w tym adapter Wio, antena, RXEN, odsprzęganie,
   rezystor resetu R12=1k i punkty pomiarowe. Zasilanie wyłącznie z USB.
   JP1/JP2 zwarte; źródła AA/12V odłączone. Nie zasłaniać punktów pomiarowych.
2. Przed podaniem napięcia: sprawdzić zwarcia, polaryzację, orientację LCD/FRAM,
   model pamięci i wszystkie połączenia z `reference/polaczenia-MCU-L0.csv`.
   Obraz akceptuje oba układy FRAM z BOM N1, CY15B104QN i MB85RS4MT (płytki z montażem
   JLCPCB z 2026-10-10 mają MB85RS4MTPF-G-BCERE1); `RDID` pokazuje, który jest wlutowany.
   Inna pamięć daje `ERR fram_id_unsupported` i blokuje próby FRAM.
3. Zapewnić multimetr i oscyloskop ≥3 kanały, ≥50MHz, sondy x10.
   Partner radiowy: jeden XIAO 102010611 z anteną i obrazem R0 `pair-0.3`.
   Klient ma zamówione dwa zestawy, termin ich udostępnienia ustalany osobno.
   Jeden Mac z dwoma USB wystarcza. Dwa komputery mogą służyć do ręcznych prób;
   do dołączonego automatycznego testu oba urządzenia podłączyć do jednego hosta.
4. Antenę podłączyć przed uruchomieniem radia. Podczas prób biurkowych
   ustawić urządzenia około 2–3m od siebie. Brak transmisji po samym starcie.

## Wgranie i USB

Używać złącza **USB/OTG (native USB)** DevKitC, przewodu micro-USB z transmisją
danych. Złącze USB/UART nie udostępnia konsoli tego obrazu. R0 używa USB-C.
Na DevKitC N8R8 obraz korzysta z 8MB flash; PSRAM nie jest potrzebny ani włączony.

Po rozpakowaniu paczki, w jej głównym katalogu:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/radio_test.py --list
```

Poniżej `PORT_L0` i `PORT_R0` zastąpić rzeczywistymi, różnymi nazwami
`/dev/cu.usbmodem...`. Nie kopiować tych nazw dosłownie.
Gdy urządzenie nie pojawia się: przytrzymać BOOT, nacisnąć i zwolnić RESET,
zwolnić BOOT i ponownie sprawdzić listę portów. Zamknąć inne monitory USB.

Przed pierwszym nadpisaniem zapisać kopię fabrycznej pamięci, lokalnie:

```sh
mkdir -p backups
.venv/bin/python -m esptool --chip esp32s3 --port PORT_L0 read_flash 0 0x800000 backups/l0-factory.bin
shasum -a 256 -c SHA256SUMS.txt
.venv/bin/python -m esptool --chip esp32s3 --port PORT_L0 write_flash 0x0 images/l0-full.bin
```

Nie wykonywać dodatkowego `erase_flash`. Po wgraniu nacisnąć RESET i ponownie
sprawdzić port; nazwa portu może się zmienić. Paczka zawiera też osobne obrazy
bootloader/partitions/boot_app0/firmware i ich adresy w `images/offsets.json`.
Plik `firmware.bin` jest aplikacją na adres 0x10000, a `l0-full.bin` kompletem
na adres 0x0. Nie używać tych adresów zamiennie.

Alternatywnie budować i wgrywać ze źródeł:

```sh
.venv/bin/pio run
.venv/bin/pio run --target upload --upload-port PORT_L0
```

Konsola: `.venv/bin/pio device monitor --port PORT_L0 --baud 115200`.
Każde polecenie zakończyć Enter. Monitor zamknąć przed uruchomieniem skryptów.
`INFO` musi zwrócić `INFO l0-0.5 ... 1 ... 869.525 125 7 5 0 1.8`.
Każdy kompletny rekord jest wysyłany od razu (`Serial.flush()`); w pierwszym teście R0 bez tego
część linii docierała do hosta dopiero przy następnym poleceniu, około 2,9 s później.
`STATUS` pokazuje stan podzespołów, wejść i testu. Każde polecenie jest poprzedzone
echem `CMD ...`; skrypt wymaga tego echa i kontroluje ciągłość identyfikatora startu.
STATUS i test FRAM można wykonać także wtedy, gdy inne peryferium jest niegotowe. `ERR` wymaga wyjaśnienia;
nie traktować go jako zaliczenia próby. Zmiana identyfikatora startu oznacza restart.

## Kolejność prób po montażu

Zapisuj wyniki pomiarów, zdjęcia plansz i przebiegi oscyloskopu obok logów USB.
Ocena końcowa wymaga wszystkich prób, nie tylko komunikatu skryptu.

| Próba | Co zrobić | Warunek potwierdzenia |
|---|---|---|
| E1 — start | Oględziny; włączenie i reset, INFO/STATUS | Poprawny montaż, brak zwarć, zgodny obraz/piny, inicjalizacja bez ERR |
| E2 — zasilanie | Pomiar 3V3, +5V_LCD i prądu; Wio przez POWER_BREAK | Napięcia mieszczą się w wymaganiach podzespołów; raport rzeczywistych wartości i prądu spoczynek/RX/TX; brak resetów i nadmiernego grzania |
| E3 — FRAM | Pełny zapis/weryfikacja, następnie odłączyć USB i zweryfikować bez zapisu | Wszystkie 5 wzorców, zero błędów, zgodne CRC; po zaniku zgodny ostatni wzorzec |
| E4 — ochrona przy zaniku | GUARD ERASE i kontrolowane odłączenie USB, jednoczesny pomiar 3V3/CS/GUARD | Przed zanikiem CS pamięci niski; bramka podnosi CS, zanim FRAM opuszcza dozwolone napięcie pracy; udokumentowany przebieg, bez wstecznego zasilania |
| E5 — ekran/panel | LCD 0..4, PAUSE 10000, każde wejście, LED i BUZZ | Wszystkie plansze poprawne; EXTCOMIN 1Hz/około50% trwa także podczas pauzy; 6 wejść odpowiada; LED świeci, buzzer brzmi |
| E6 — wspólne SPI | Automatyczny MIX, obserwacja przebiegów i ekranu | Pełne 15min, zero błędów FRAM, brak restartów/kolizji SPI, poprawny ekran i pakiety |
| R1/R2 — radio | Po restarcie 100 pakietów w każdą stronę bez retry | Wszystkie pakiety zgodne, raport RSSI/SNR, brak ERR/restartu |
| R3 — CISZA | Włączyć SW5, polecić TX; następnie wyłączyć i powtórzyć | `BLOCKED SILENCE`, brak odpowiadającego pakietu u partnera; po wyłączeniu odbiór wraca |

E2/E4: FRAM CY15B104QN i MB85RS4MT działają przy 1.8–3.6V; próg nadzorcy około 2.7V
ma zakończyć wybór pamięci wcześniej. Samo wykrycie zmiany GUARD nie wystarcza:
sondować **CS za bramką na U1.1**, nie tylko GPIO MCU. Oscyloskop nie może
podtrzymywać zasilania prototypu. Nie podłączać równocześnie drugiego źródła USB.
E4 sprawdza ochronę elektryczną; ten obraz nie zawiera aplikacyjnej transakcji COMMIT.
Prąd z E2 to wynik prototypu diagnostycznego, nie prognoza czasu pracy na baterii.

### Pamięć: pełny test i retencja

**FRAMTEST, GUARD i MIX niszczą zawartość FRAM.** Na tym etapie to pamięć testowa.
Start urządzenia nie zapisuje FRAM. Użyć tego samego seed przed i po zaniku:

```sh
.venv/bin/python tools/diagnose.py --port PORT_L0 --fram-write 12345678
```

Po zakończeniu odłączyć wszystkie źródła zasilania L0 na co najmniej 60s.
Podłączyć ponownie, ustalić aktualny port i wykonać wyłącznie odczyt:

```sh
.venv/bin/python tools/diagnose.py --port PORT_L0 --fram-verify 12345678
```

Wzorce: 00, FF, AA, 55 i wzorzec zależny od adresu/seed na całych 512KiB.
Host niezależnie wylicza CRC każdego wzorca i zapisuje powodzenie dopiero po
pełnej walidacji. Błędy i nieukończone próby zachowują log z wynikiem negatywnym.
Pełny test zastępuje poprzednią zawartość; wykonaj retencję **przed MIX/GUARD**.
Skrypty zachowują JSON w `results/`; wpis `physical_acceptance=false` celowo
pozostaje do osobnego odbioru pomiarów i oględzin.

### E4/E5: polecenia ręczne

`GUARD ERASE` rozpoczyna ciągłą transakcję zapisu z CS niskim, aż do zaniku
zasilania lub `STOP`. W tym trybie inne operacje SPI są zablokowane.
Wyzwolić oscyloskop spadkiem 3V3 i odłączyć USB. Do kolejnej próby wystartować
ponownie. Nie oczekiwać zachowania testowej zawartości po GUARD.

`LCD 0` = biały, `LCD 1` = czarny, `LCD 2` = szachownica,
`LCD 3` = siatka, `LCD 4` = tekst/inwersja. `PAUSE 10000` wstrzymuje główną
pętlę na 10s, ale sprzętowy MCPWM podtrzymuje EXTCOMIN; potwierdzić sondą J7.4.
`STATUS ext=1` nie jest pomiarem sygnału na LCD. `LED 1/0`, `BUZZ 1/0`
sterują wyjściami. Buzzer otrzymuje przebieg 2048Hz, nie stałe napięcie.
Maska `INPUT`: bity 0 UP, 1 DOWN, 2 OK, 3 BACK, 4 CISZA, 5 PREP;
aktywne wejście ustawia bit. Krótki styk może powodować kilka wpisów — bez debounce.

### E6: 15 minut LCD + FRAM + radio

Wgrać R0 do partnera, ustawić CISZA wyłączona. W tym trybie dostępne są tylko INFO, STATUS, HELP, STOP i TX; polecenia
zmieniające przebieg próby są zablokowane:

```sh
.venv/bin/python tools/diagnose.py --port PORT_L0 --mixed --peer PORT_R0
```

L0 co około200ms zmienia planszę i zapisuje/odczytuje ostatnie256B FRAM.
Host przesyła 100 numerowanych pakietów w każdą stronę co4.5s, bez ponowień.
Wymagane oba raporty: zakończenie MIX z zerem błędów i komplet poprawnych pakietów.
MIX raportuje czas, liczbę cykli/plansz i najdłuższy odstęp między cyklami.
Wymagane ≥900000ms, ≥900 cykli, tyle samo plansz co cykli, odstępy ≤1000ms.
Host odrzuca zakończenie otrzymane przed upływem 880s jego sesji radiowej
(20s tolerancji na otwarcie USB i uzgodnienie rozpoczętej już próby).
Równocześnie obejrzeć ekran i zarejestrować SPI; JSON nie wykryje błędnych pikseli
ani nie potwierdzi fizycznego zwalniania MISO. Przy niepowodzeniu skrypt próbuje wysłać STOP. Jeśli USB nie odpowiada, przed
kolejną próbą nacisnąć RESET.

### Radio po restarcie i CISZA

Po restarcie powtórzyć samą próbę radia (około10min):

```sh
.venv/bin/python tools/radio_test.py --a PORT_L0 --b PORT_R0 --version-a l0-0.5 --version-b pair-0.3 --count 100
```

CISZA: na L0 włączyć SW5, sprawdzić bit4 oraz `silence=1`; `TX WICI-SILENCE-01`
ma zwrócić `BLOCKED SILENCE`. W konsoli partnera nie może pojawić się ten pakiet.
Wyłączyć SW5 i powtórzyć TX z innym numerem — partner ma odebrać dokładną treść.
Sprawdzić też odbiór L0 przy CISZA: partner wysyła pakiet, L0 go odbiera.
To blokada programowa rozpoczęcia TX, nie fizyczny wyłącznik ani przerwanie
nadawania już rozpoczętego. Test nie potwierdza docelowej odległości terenowej.

PHY: 869.525MHz, BW125kHz, SF7, CR4/5, private0x12, CRC, preambuła8,
0dBm, TCXO1.8V. Program ogranicza odstęp TX do co najmniej13 czasów pakietu;
host do co najmniej3s. Nie zmieniać parametrów/mocy w próbie porównawczej.

## Źródła i odtwarzalność

Pinmapa jest kopią dokumentacji RFQ. Sterowniki Sharp/font/FRAM są wydzielone
z repozytorium WICI; L0 dodaje własny MCPWM i program diagnostyczny, bez zależności
od aplikacji. Licencje MIT i Bitstream Vera w `licenses/`. Biblioteka RadioLib7.6.0
jest pobierana przez PlatformIO i ma własną licencję MIT.

W katalogu `partner-r0/` paczki znajdują się również obraz i źródła R0.
Instrukcja wgrania partnera: `partner-r0/INSTRUKCJA.txt`.

Konfigurację MCPWM sprawdzono względem dokumentacji Espressif IDF4.4.7:
https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/peripherals/mcpwm.html
Zestaw XIAO/Wio: https://wiki.seeedstudio.com/wio_sx1262_with_xiao_esp32s3_kit/

Testy źródeł: `.venv/bin/python -m unittest discover -s tests -v` (test C++ wymaga clang++).
Kompilator ESP32 weryfikuje cały obraz. Natywny test symuluje podzespoły, a nie
ich rzeczywiste własności elektryczne, RF ani sprzętowy timer MCPWM.
Test przepływu firmware → pyserial → raport używa rzeczywistego kodu firmware
i skryptu, połączonych przez pseudoport szeregowy.

W repozytorium jest jedna implementacja testu radiowego:
`hardware/radio-pair/tools/pair_test.py`. `tools/radio_test.py` to mały adapter;
w paczce wspólny skrypt znajduje się w `partner-r0/tools/pair_test.py`.


Paczka oprogramowania jest budowana przez `tools/package.py` z wcześniej
zweryfikowanych źródeł i obrazów `.pio/build`. Skrypt odrzuca niezgodne SHA-256
źródeł, brak zaliczenia testów i obraz różny od zapisanego w `checks.json`.
Logi kompilacji i testów znajdują się w `evidence/`. Aby odtworzyć paczkę
w repozytorium po aktualnej kompilacji/testach i zapisaniu zgodnego `checks.json`:

```sh
.venv/bin/python tools/package.py --r0 ../radio-pair --boot-app0 /sciezka/do/framework-arduinoespressif32/tools/partitions/boot_app0.bin --output /sciezka/do/L0-program.zip
```

Nie pakować zmienionych źródeł ze starym obrazem. Nowe źródła wymagają ponownej
kompilacji, testów i aktualizacji dowodów weryfikacji.

# WICI — oprogramowanie

## Procesy

`START → rnsd + station-web`. Transport działa w osobnym rnsd z włączonym przekazywaniem. `station-web` zawiera serwer lokalnej strony, jedną bazę SQLite i instancję `LXMF.LXMRouter`. Biblioteka łączy się z lokalnym współdzielonym Reticulum. Restart strony nie wyłącza rnsd; awaria radia nie blokuje zapisu formularza.

LXMF wykonuje pakowanie wiadomości, szyfrowanie przez Reticulum, wyszukiwanie trasy, transportowe potwierdzenia i ponawianie. Nie implementujemy tych mechanizmów drugi raz. Jego stan DELIVERED nie oznacza transakcji w naszej bazie OSP. Kolejka intencji aplikacji zostaje w SQLite i jest odtwarzana po restarcie; nie traktujemy listy `pending_outbound` w pamięci LXMF jako trwałej kolejki. [LXMF](https://github.com/markqvist/LXMF), [LXMRouter](https://github.com/markqvist/LXMF/blob/master/LXMF/LXMRouter.py).

NomadNet udostępnia własny interfejs tekstowy i strony Micron. Można dodać go jako narzędzie operatora lub użyć jego funkcji węzła przechowywania, ale nie wymagać od mieszkańców instalacji klienta. Stronę dla telefonów nadal obsługuje lokalny HTTP. NomadNet uruchomiony obok ma inną tożsamość; nie współdzieli prywatnych katalogów bazy stacji. [NomadNet](https://github.com/markqvist/NomadNet).

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik. Treść do 480 B, bez załączników. JSON zawiera jedną tablicę; nie przyjmujemy swobodnych obiektów. Własny format nie zastępuje LXMF. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`; teksty bez znaków sterujących i formatujących Unicode (kategorie Cc i Cf), w tym C1, znaki zmiany kierunku pisma i niewidoczne znaki formatujące. Zwykłe polskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |

`id`: 32 małe znaki hex, czyli 16 losowych bajtów. `revision`: 0–65535. `category`: 0–4 = medyczne, ewakuacja, woda/żywność, wyposażenie, inne. `people`: 1–65535. `location`: 1–64 B, dokładny adres i miejsce wejścia. `text` zgłoszenia/odpowiedzi: do 96 B; komunikatu do 192 B. `urgency`: 0–2, podwyższenie zatwierdza opiekun. `event`: 1–2147483647, bez zawijania; nowy komunikat po wyczerpaniu licznika dostaje nowe id. `state`: 1 zapisane OSP, 2 przeczytane, 3 pomoc skierowana.

RECEIVED zawsze oznacza pierwsze przyjęcie, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2 lub 3; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli OSP ma już nowszy status, wysyła też najnowszy STATUS. Źródło ignoruje starsze event dla tej samej pary id/revision. REPLY ma osobny strumień event; nie konkuruje z numeracją STATUS. BULLETIN jest numerowany w obrębie swojego id.

Zmiana danych zgłoszenia tworzy nową revision. Każda revision zawiera całą lokalizację i treść; nie zależy od wcześniejszego profilu. Wersje są pokazywane jako jedno zgłoszenie, ale potwierdzane osobno. Nie wysyłamy imion, PESEL, dokumentów ani tokenów strony przez radio.

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zapis lokalny | zgłoszenie + token dostępu + intencja wysyłki |
| Przyjęcie OSP | zweryfikowane zgłoszenie + tożsamość nadawcy + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS |

SQLite: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone. Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią to błąd konfliktu, bez nadpisania.

Callback odbiorczy sprawdza `signature_validated`, zaufanie do nadawcy i limit wielkości przed zapisem. STATUS/REPLY/BULLETIN przyjmowane są wyłącznie z przypiętej tożsamości OSP. Nazwa wyświetlana i pole JSON nie nadają uprawnień. REQUEST nowej nieznanej stacji może trafić do kwarantanny operatora; nie udaje zweryfikowanego adresu schronienia.

Po COMMIT pracownik kolejki może wysłać RECEIVED. Przed COMMIT nie wysyła potwierdzenia aplikacyjnego. Brak miejsca, uszkodzenie bazy lub błąd fsync blokują komunikat „zapisane”. Nie tworzymy automatycznie pustej bazy zamiast uszkodzonej. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. [Trwałość SQLite](https://sqlite.org/atomiccommit.html).

Wysyłanie: najwyżej jedna aktywna wiadomość aplikacji do danego odbiorcy. LXMF ponawia aktywną próbę. Po jego błędzie lub braku RECEIVED aplikacja ponawia intencję po 1, 2, 5, następnie co 15 minut z losowym przesunięciem ±20%; nigdy równolegle z nadal aktywnym wysłaniem. Nowa wiadomość LXMF może mieć inny hash; id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji OSP. Potwierdzenia i statusy mają pierwszeństwo przed zwykłymi REQUEST w naszej kolejce; to nie daje gwarancji priorytetu całej sieci.

## API lokalnej strony

| Endpoint | Działanie |
|---|---|
| `GET /` | informacje, formularz, komunikaty |
| `POST /api/request` | walidacja i trwały zapis; 201 dopiero po COMMIT |
| `GET /api/request/<token>` | treść i status tylko własnego zgłoszenia |
| `GET /operator` | logowanie opiekuna |
| `GET /api/operator/queue` | kolejka lokalna; uwierzytelnienie wymagane |
| `POST /api/operator/approve` | zatwierdzenie pilności i wysyłki |
| `POST /api/operator/status` | decyzja OSP; tylko rola OSP |
| `POST /api/operator/export` | operacja PRZENIEŚ STACJĘ |
| `GET /health` | stan strony, zapisu, modemu i ostatniego kontaktu z OSP |

Token mieszkańca: 32 losowe bajty; przechowywany jako hash, nie publikowany w listach. Hasło operatora generowane lokalnie i przechowywane jako salted hash. Brak rejestracji kont mieszkańców. POST wymaga JSON, tokenu CSRF sesji i dozwolonego Origin; limity rozmiaru oraz częstości. Strona nie ładuje zasobów z internetu, nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności lokalnego odcinka, więc minimalizujemy dane osobowe; radio szyfruje osobno.

Router daje DHCP. Laptop jest klientem LAN i pokazuje `http://IP:8080` oraz QR, aktualizowany po zmianie IP. Główne Wi-Fi musi dopuszczać ruch do LAN. Bez własnego DHCP, DNS i captive portal. Firewall pakietu START musi dopuścić wyłącznie lokalny port strony na wybranym interfejsie; reguła może wymagać uprawnień systemowych.

## Pakiet USB

```text
USB/
  INSTRUKCJA.html
  START-WINDOWS.exe
  START-MAC-INTEL.app/
  START-MAC-ARM.app/
  linux-x86_64/                 # obraz startowy i read-only root
  runtime/<platform>/          # interpreter i wszystkie biblioteki
  app/                         # strona, launcher, worker LXMF
  drivers/<platform>/
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, hashe, komenda budowy, lista plików
  export/                      # kopia przeniesionej stacji
```

W Linuxie stan znajduje się na osobnej partycji ext4 USB. W Windows/macOS na dysku laptopa w katalogu aplikacji. Nie zapisujemy aktywnej bazy na exFAT i nie obiecujemy automatycznej wspólnej bazy między systemami.

PRZENIEŚ STACJĘ zatrzymuje nowe zgłoszenia i pracownika wysyłki, wykonuje kopię API SQLite, sprawdza jej integralność, eksportuje tożsamość oraz konfigurację i zatrzymuje starą instancję. Nowy laptop importuje pakiet. Nie używa się jednocześnie obu kopii. Utrata laptopa przed eksportem może utracić ostatnie lokalne dane. [API kopii](https://www.sqlite.org/backup.html).

Pakiet START utrzymuje komputer w stanie pracy podczas działania stacji, również przy restarcie samej strony. Uśpiony laptop nie jest przekaźnikiem. Ręczne wymuszenie uśpienia lub utrata USB wymagają obsługi suspend/resume modemu, zachowania kolejki i ponownego sprawdzenia trasy. Wyłączenie automatycznego usypiania nie zastępuje zgodności elektrycznej USB.

Pakiety muszą zostać zbudowane i przetestowane na każdej architekturze przed dystrybucją. To nie jest instrukcja instalowania pip w schronieniu. Wydanie przypina dokładne archiwa/commity i hashe po próbie zgodności. Nie pobiera `latest` przy uruchomieniu.

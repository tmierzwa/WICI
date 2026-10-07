# WICI: oprogramowanie

## Procesy

`START → rnsd + station-web`. Transport działa w osobnym rnsd z włączonym przekazywaniem. `station-web` zawiera serwer lokalnej strony, jedną bazę SQLite i instancję `LXMF.LXMRouter`. Biblioteka łączy się z lokalną, współdzieloną instancją Reticulum. Restart strony nie wyłącza rnsd; awaria radia nie blokuje zapisu formularza.

LXMF pakuje wiadomości, szyfruje je przez Reticulum, wyszukuje trasę, potwierdza dostarczenie na poziomie transportu i ponawia wysyłkę. Nie implementujemy tych mechanizmów drugi raz. Stan DELIVERED w LXMF nie oznacza zatwierdzonej transakcji w bazie OSP. Kolejka intencji aplikacji jest w SQLite i stacja odtwarza ją po restarcie. Lista `pending_outbound` w pamięci LXMF nie jest trwałą kolejką. [LXMF](https://github.com/markqvist/LXMF), [LXMRouter](https://github.com/markqvist/LXMF/blob/master/LXMF/LXMRouter.py).

NomadNet udostępnia własny interfejs tekstowy i strony Micron. Może służyć jako narzędzie opiekuna lub dyżurnego albo jako węzeł przechowywania. Nie wolno wymagać od mieszkańców instalacji klienta. Stronę dla telefonów obsługuje lokalny serwer HTTP. NomadNet uruchomiony obok ma osobną tożsamość i nie współdzieli prywatnych katalogów bazy stacji. [NomadNet](https://github.com/markqvist/NomadNet).

## Wiadomości SA1

LXMF `title` = `SA1`, `content` = UTF-8 JSON, `fields` = pusty słownik. Treść do 480 B, bez załączników. JSON zawiera jedną tablicę; swobodne obiekty są odrzucane. Kodowanie: bez zbędnych spacji, znaki Unicode bez zamiany na `\u`. Teksty nie mogą zawierać znaków sterujących ani formatujących Unicode (kategorie Cc i Cf), w tym znaków C1, znaków zmiany kierunku pisma i niewidocznych znaków formatujących. Zwykłe polskie litery są dozwolone. Limity tekstu są liczone w bajtach UTF-8. Narzut LXMF i Reticulum jest dodatkowy.

| Typ | Tablica |
|---|---|
| REQUEST = 0 | `[1,0,id,revision,category,people,location,text,urgency]` |
| RECEIVED = 1 | `[1,1,id,revision,1,1]` |
| STATUS = 2 | `[1,2,id,revision,event,state]` |
| REPLY = 3 | `[1,3,id,revision,event,text]` |
| BULLETIN = 4 | `[1,4,id,event,text]` |
| TEST = 5 | `[1,5,id,revision,category,people,location,text,urgency]` |

`id`: 32 małe cyfry szesnastkowe, czyli 16 losowych bajtów. `revision`: 0–65 535. `category`: 0–4 = medyczne, ewakuacja, woda/żywność, wyposażenie, inne. `people`: 1–65 535. `location`: 1–64 B, dokładny adres i miejsce wejścia. `text` zgłoszenia i odpowiedzi: do 96 B; komunikatu: do 192 B. `urgency`: 0–2, podwyższenie zatwierdza opiekun. `event`: 1–2 147 483 647, bez zawijania licznika; nowy komunikat po wyczerpaniu licznika dostaje nowe id. `state`: 1 = zapisane w OSP, 2 = przeczytane, 3 = pomoc skierowana.

RECEIVED zawsze oznacza pierwsze przyjęcie, event=1 i state=1. STATUS dopuszcza wyłącznie event ≥2 oraz state 2 lub 3; nie zastępuje RECEIVED ani nie powtarza jego event=1. Powtórzony REQUEST może ponownie dostać ten sam RECEIVED. Jeśli OSP ma już nowszy status, wysyła też najnowszy STATUS. Źródło ignoruje starsze wartości event dla tej samej pary id i revision. REPLY ma numerację event niezależną od STATUS. BULLETIN jest numerowany w obrębie swojego id.

TEST ma tablicę, limity i walidację REQUEST. Sprawdza całą drogę zgłoszenia: transport, zapis w OSP i obecność dyżurnego. Stacja wysyła go po uruchomieniu, restarcie, zmianie routera, anteny lub odbiorcy oraz na polecenie opiekuna; nigdy cyklicznie. Zgłoszenia wysyłane podczas prób i ćwiczeń również mają typ TEST. TEST startowy zawiera rzeczywisty adres i wejście schronienia, aby dyżurny mógł potwierdzić, że są zrozumiałe. OSP przyjmuje TEST jak REQUEST: weryfikacja nadawcy, kwarantanna nieznanej stacji, deduplikacja, jedna transakcja i RECEIVED po COMMIT. Klucz odbioru nie zależy od typu; REQUEST i TEST o tym samym id i revision to konflikt treści. Stanowisko OSP pokazuje TEST osobno od kolejki potrzeb i nie wlicza go do potrzeb. Dyżurny odpowiada wiadomością STATUS ze state=2. Wartość state=3 dla TEST jest dopuszczalna tylko w uzgodnionym ćwiczeniu i oznacza decyzję ćwiczebną bez wysłania pomocy. Stacja pokazuje TEST w panelu opiekuna, nie jako zgłoszenie mieszkańca.

Zmiana danych zgłoszenia tworzy nową rewizję (revision). Każda rewizja zawiera pełną lokalizację i treść i nie zależy od wcześniejszego profilu. Stanowisko pokazuje rewizje jako jedno zgłoszenie, ale każdą potwierdza się osobno. Przez radio nie wysyłamy imion, numerów PESEL, danych dokumentów ani tokenów strony.

## Trwałość i potwierdzenia

| Czynność | Jedna transakcja |
|---|---|
| Zapis lokalny | zgłoszenie + token dostępu + intencja wysyłki |
| Przyjęcie w OSP | zweryfikowane zgłoszenie + tożsamość nadawcy + intencja RECEIVED |
| Decyzja dyżurnego | nowe zdarzenie statusu + intencja STATUS |

SQLite: `journal_mode=DELETE`, `synchronous=FULL`, klucze obce włączone. Jedna baza, jeden właściciel zapisu, brak kopii roboczej na dwóch dyskach. Klucz odbioru: uwierzytelniony adres LXMF nadawcy + id + revision. Te same dane dają to samo potwierdzenie. Ta sama kombinacja z inną treścią oznacza konflikt; dane nie są nadpisywane.

Przed zapisem funkcja zwrotna odbioru sprawdza `signature_validated`, zaufanie do nadawcy i limit rozmiaru. Wiadomości STATUS, REPLY i BULLETIN są przyjmowane wyłącznie od przypiętej tożsamości OSP. Nazwa wyświetlana i pole JSON nie nadają uprawnień. REQUEST nieznanej stacji może trafić do kwarantanny, gdzie czeka na decyzję dyżurnego. Nie jest traktowany jak zgłoszenie ze zweryfikowanego schronienia.

Proces kolejki wysyła RECEIVED i każde inne potwierdzenie aplikacyjne dopiero po COMMIT. Brak miejsca, uszkodzenie bazy lub błąd fsync blokują komunikat „zapisane”. Stacja nie tworzy automatycznie pustej bazy w miejsce uszkodzonej. SQLite opiera trwałość na poprawnej pracy systemu plików i nośnika. [Trwałość SQLite](https://sqlite.org/atomiccommit.html).

Wysyłanie: najwyżej jedna aktywna wiadomość aplikacji do danego odbiorcy. LXMF ponawia aktywną próbę. Po błędzie LXMF lub braku RECEIVED aplikacja ponawia intencję po 1, 2 i 5 minutach, a następnie co 15 minut z losowym przesunięciem ±20%; nigdy równolegle z wciąż aktywną wysyłką. Nowa wiadomość LXMF może mieć inny skrót (hash); id zgłoszenia zostaje ten sam. Ponowna transmisja jest bezpieczna dzięki deduplikacji OSP. Potwierdzenia i statusy mają pierwszeństwo przed zwykłymi REQUEST w kolejce stacji; nie oznacza to priorytetu w całej sieci.

## API lokalnej strony

| Adres | Działanie |
|---|---|
| `GET /` | informacje, formularz, komunikaty |
| `POST /api/request` | walidacja i trwały zapis; 201 dopiero po COMMIT |
| `GET /api/request/<token>` | treść i status tylko własnego zgłoszenia |
| `GET /operator` | logowanie opiekuna |
| `GET /api/operator/queue` | kolejka lokalna; wymaga uwierzytelnienia |
| `POST /api/operator/approve` | zatwierdzenie pilności i wysyłki |
| `POST /api/operator/status` | decyzja OSP; tylko rola OSP |
| `POST /api/operator/export` | operacja PRZENIEŚ STACJĘ |
| `POST /api/operator/silence` | włączenie lub wyłączenie ciszy radiowej; pojedyncze zgłoszenie wyjęte spod ciszy |
| `POST /api/operator/destroy` | operacja ZNISZCZ DANE; podwójne potwierdzenie |
| `GET /health` | stan strony, zapisu, modemu i ostatniego kontaktu z OSP |

Token mieszkańca: 32 losowe bajty, przechowywany jako skrót, niepublikowany na listach. Hasło opiekuna jest generowane lokalnie i przechowywane jako skrót z solą. Mieszkańcy nie zakładają kont, nie wyrażają zgód i nie akceptują regulaminu. Strona nie wyświetla przed formularzem żadnych okien formalnych. Żądanie POST wymaga treści JSON, tokenu CSRF sesji i dozwolonego nagłówka Origin. Obowiązują limity rozmiaru i częstości żądań. Strona nie wczytuje zasobów z internetu i nie interpretuje treści zgłoszenia jako HTML. HTTP nie zapewnia poufności w sieci lokalnej, dlatego strona zbiera minimum danych osobowych. Radio szyfruje osobno.

Router zapewnia DHCP. Laptop jest klientem sieci LAN i wyświetla adres `http://IP:8080` oraz kod QR, aktualizowany po zmianie adresu IP. Główna sieć Wi-Fi musi przepuszczać ruch do LAN. Stacja nie uruchamia własnego serwera DHCP, DNS ani portalu przechwytującego (captive portal). Reguła zapory sieciowej pakietu START musi dopuszczać wyłącznie lokalny port strony na wybranym interfejsie; jej dodanie może wymagać uprawnień administratora.

## Tryby kryzysowe

Formalności i uzgodnienia załatwia się przed użyciem. Żadna z poniższych funkcji nie blokuje przyjęcia zgłoszenia.

**Emisje.** Stacja ogłasza swój adres LXMF przy starcie i na polecenie opiekuna, nigdy cyklicznie. Nazwa wyświetlana ma postać `WICI-xxxx` (4 cyfry szesnastkowe skrótu tożsamości) i nie zawiera adresu ani nazwy miejsca. Emisje transportu Reticulum, np. zapytania o trasę, pozostają i liczy się je w próbie T3.

**Cisza radiowa.** Opiekun włącza ją w panelu na polecenie uprawnionego organu. Adapter przestaje przekazywać ramki DATA do modemu, więc modem nic nie nadaje, łącznie z ruchem przekazywanym. Odbiór, zapis i kolejka działają dalej. Wyłączenie ciszy jest wyłącznie ręczne. Przy bezpośrednim zagrożeniu życia opiekun może wyjąć spod ciszy pojedyncze zgłoszenie, a stacja zapisuje tę decyzję w dzienniku. Fizyczną pewność ciszy daje odłączenie modemu od USB.

**Szyfrowanie w spoczynku.** Baza, tożsamość i eksporty są szyfrowane kluczem zapisanym na pamięci USB stacji. Start nie wymaga hasła. W systemach Windows i macOS baza leży na dysku laptopa, więc po odłączeniu pamięci USB jest nieczytelna. W Linuksie baza i klucz są na tej samej pamięci. W każdym systemie zabranie laptopa razem z pamięcią USB daje dostęp do danych. Szyfrowanie chroni więc tylko przed utratą samego laptopa; przed przejęciem całego stanowiska chroni wyłącznie ZNISZCZ DANE albo zniszczenie pamięci. Kandydatem jest SQLCipher Community Edition (licencja BSD-3-Clause, wymaga dołączenia informacji o prawach autorskich) z biblioteką Pythona [sqlcipher3](https://pypi.org/project/sqlcipher3/) (licencja zlib), która ma gotowe pakiety dla macOS (Intel i ARM), Windows x64 i Linuksa x86_64. To pierwsza zależność bazy spoza biblioteki standardowej. Wymaga przypięcia wersji, sprawdzenia, że nie osłabia gwarancji trwałości z tej specyfikacji (tryb dziennika, fsync), oraz powtórzenia prób odcięcia zasilania. Ostateczny wybór, także wobec zaszyfrowanego wolumenu, zapada w D13. [SQLCipher](https://www.zetetic.net/sqlcipher/license/).

**ZNISZCZ DANE.** Po podwójnym potwierdzeniu stacja zatrzymuje wysyłkę, usuwa klucz, a następnie bazę, tożsamość i eksporty. Nadpisanie pamięci flash i SSD nie gwarantuje usunięcia, dlatego decyduje usunięcie klucza. Instrukcja nakazuje dodatkowo fizyczne zniszczenie pamięci USB. Operacja jest nieodwracalna i trwa najwyżej 1 minutę.

**Języki i dostępność.** Strona mieszkańca jest dostępna po polsku, ukraińsku i angielsku. Wybór języka nie wymaga przeładowania ani połączenia z internetem. Kategorie mają piktogramy i są przesyłane jako liczby, więc dyżurny widzi kategorię, liczbę osób i lokalizację niezależnie od języka opisu. Litery ukraińskie zajmują w UTF-8 po 2 B, tak jak polskie znaki diakrytyczne, więc opis zgłoszenia mieści około 48 takich znaków. Formularz pokazuje pozostały limit w bajtach. Strona używa semantycznego HTML, działa z czytnikiem ekranu i przy powiększeniu tekstu do 200%.

## Pakiet USB

```text
USB/
  INSTRUKCJA.html
  START-WINDOWS.exe
  START-MAC-INTEL.app/
  START-MAC-ARM.app/
  linux-x86_64/                 # obraz startowy, system plików tylko do odczytu
  runtime/<platform>/          # interpreter i wszystkie biblioteki
  app/                         # strona, program startowy, proces LXMF
  drivers/<platform>/
  sources/                     # kod własny i źródła wymagane licencjami
  licenses/
  build-manifest.json          # wersje, skróty, polecenie budowy, lista plików
  keys/                        # klucz szyfrowania bazy tej stacji; nie trafia do kopii publicznych
  export/                      # kopia przeniesionej stacji
```

W Linuksie stan znajduje się na osobnej partycji ext4 pamięci USB, a w systemach Windows i macOS na dysku laptopa, w katalogu aplikacji. Aktywna baza nie może leżeć na exFAT. Stacja nie zapewnia automatycznej wspólnej bazy między systemami.

PRZENIEŚ STACJĘ zatrzymuje nowe zgłoszenia i proces wysyłki, wykonuje kopię bazy przez API kopii zapasowych SQLite, sprawdza jej integralność, eksportuje tożsamość oraz konfigurację i zatrzymuje starą instancję. Nowy laptop importuje pakiet. Obu kopii nie wolno używać jednocześnie. W razie utraty laptopa przed eksportem ostatnie lokalne dane mogą przepaść. [API kopii](https://www.sqlite.org/backup.html).

Pakiet START utrzymuje komputer w stanie pracy podczas działania stacji, również przy restarcie samej strony. Uśpiony laptop nie jest przekaźnikiem. Po ręcznym uśpieniu lub utracie połączenia USB stacja musi obsłużyć wstrzymanie i wznowienie modemu, zachować kolejkę i ponownie sprawdzić trasę. Wyłączenie automatycznego usypiania nie zastępuje zgodności elektrycznej USB.

Przed dystrybucją pakiety muszą zostać zbudowane i przetestowane na każdej architekturze. W schronieniu nie instaluje się pakietów przez pip. Po próbie zgodności wydanie przypina dokładne archiwa lub commity wraz z ich skrótami. Podczas uruchamiania nie pobiera się wersji `latest`.

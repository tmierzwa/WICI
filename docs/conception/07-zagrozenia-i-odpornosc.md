# 07. Zagrożenia i odporność

## Priorytet awarii

Najgroźniejsze są pozorne potwierdzenie, błędna informacja o skierowaniu pomocy oraz uszkodzenie zasilania z ryzykiem dla ludzi. Następnie: utrata trwałych danych, odcięcie jedynego przekaźnika/odbiorcy i długotrwałe przeciążenie. Awaria pojedynczego portu ładowania jest mniej krytyczna dla łączności, ponieważ ma osobne zasilanie.

Poniższa analiza opisuje mechanizmy ochrony i granice. Brak danych terenowych nie pozwala przypisać wiarygodnych częstości awarii ani liczbowego wskaźnika ryzyka.

| Awaria / zagrożenie | Skutek | Wykrycie i ograniczenie | Ryzyko pozostałe / próba |
|---|---|---|---|
| OSP zapisuje ACK przed danymi | źródło wierzy w zgłoszenie, którego nie ma | RECEIVED dopiero po COMMIT; intencja ACK w tej samej transakcji | fizyczny nośnik może łamać gwarancje; odcięcia zasilania T2 |
| Brak miejsca lub uszkodzenie bazy | utrata zgłoszeń albo fałszywy zapis | błąd zapisu widoczny; brak automatycznej pustej bazy; kontrola integralności i zasobów | granice logów/kolejki do ustalenia; T2 |
| Duplikaty lub powtórzone stare statusy | kilka działań dla jednej potrzeby lub cofnięcie informacji | nadawca + id + revision; monotoniczny event; konflikt nie nadpisuje | przejęcie zgłoszenia przez drugą OSP nie ma kontraktu; T2 |
| Zawieszenie strony | brak formularza | oddzielny rnsd; diagnostyka procesów i kontrolowane wznowienie | laptop pozostaje wspólnym punktem awarii; T1/T2 |
| Odłączenie USB / modem odrzuca dane | brak transmisji | oddzielny stan radia, liczniki odrzutów, trwała kolejka aplikacji | niesprawdzone zachowanie timeoutów LXMF; T3 |
| Zanik przekaźnika | podział sieci | pomiar kontaktu, alternatywne połączenie tylko jeśli istnieje, priorytet energii przekaźnika | jedna droga może odciąć całe schronienie; T5 |
| OSP działa, ale brak dyżurnego | trwałe przyjęcie bez działania | jawny odczyt/decyzja, uzgodnione zastępstwo i kontrola dyżuru | sama sieć nie zapewnia ludzi ani środków; T8 |
| Przeciążenie / ponowienia wielu stacji | rosnące opóźnienie pilnych potrzeb | ograniczone bufory, rozłożone ponowienia, małe wiadomości, monitorowanie wieku kolejki | brak gwarantowanego priorytetu eteru; T3/T5 |
| Ukryte nadajniki / zakłócenia | kolizje i utrata fragmentów | CCA i losowe odroczenie; właściwa antena; pomiar przy pracującym zasilaniu | brak odporności na celowe zagłuszanie; T4/T5/T6 |
| Restart zeruje budżet TX | przekroczenie warunków pracy nadajnika | trwały dług ciszy przed TX; niepoprawny dziennik blokuje TX, RX trwa | zużycie i przerwany zapis EEPROM wymagają próby; T4 |
| Rozładowanie obu A/B / udar nowego źródła | reset sieci i możliwa awaria elementów | kolejność podłączenia, każdy tor na pełne obciążenie, bezpieczniki i kwalifikacja udaru | diody nie są regulatorem i nie eliminują udaru; T6 |
| Awaria regulatora portu telefonu | przepięcie telefonu | niezależne porty, OVP i próba wymuszonej awarii bez telefonu | obecny crowbar nie jest odebraną ochroną; T6 |
| Przebicie / błędne PE własnej przetwornicy | porażenie lub pożar | ukończona ochrona AC, izolacja i badanie konfiguracji przez kompetentnego wykonawcę | zgodność nie wynika ze schematu ani modelu; HOLD, T6 |
| Utrata klucza / skopiowana tożsamość | brak zaufania albo podszycie | kontrolowana kopia, jedna aktywna instancja, procedura zmiany klucza | unieważnianie offline i odtworzenie po utracie do opracowania; T2/T8 |
| Obcy użytkownik w LAN | odczyt HTTP, nadużycie formularza lub panelu | minimalne dane, tokeny, logowanie opiekuna, walidacja i ograniczenia ruchu | HTTP nie chroni lokalnej poufności; T2 |

## Ochrona danych i zaufania

Zagrożenia obejmują przypadkowego użytkownika, osobę w tej samej sieci, podszycie pod OSP, kradzież laptopa i celowe zakłócanie radia. Bazowe szyfrowanie Reticulum nie rozwiązuje zagrożeń po obu końcach transmisji. Nie ma podstaw do deklaracji bezpiecznej pracy na przejętym komputerze.

Token ogranicza dostęp aplikacyjny do zgłoszenia, lecz przesyłany przez HTTP może zostać przechwycony. Hasło Wi-Fi nie zastępuje HTTPS. Na dysku przechowywane są dane i klucz stacji; bazowy projekt nie definiuje ich szyfrowania w spoczynku. Dlatego zbierać minimum, nie publikować zbiorczej listy potrzeb mieszkańców i ograniczać fizyczny dostęp do laptopa oraz kopii.

Przed pilotażem uzgodnić: osobę odpowiedzialną za dane, cel i czas przechowywania, zakres kopii, uprawnienia dyżurnych, usuwanie danych po zakończeniu pracy i postępowanie po kradzieży. Nie dodawać samowolnie sztywnego okresu retencji jako rzekomego wymogu prawnego. Eksport obejmuje sekret tożsamości i wymaga takiej samej ochrony jak stacja.

Karta OSP musi pochodzić z niezależnego potwierdzenia, a nie automatycznie z pierwszego napotkanego nadajnika. Nieznana stacja nie może sama nadać sobie adresu lub roli służby. Podpisany komunikat wymaga oznaczenia źródła i czasu odbioru; dyżurny nadal odpowiada za jego treść.

## Warunki użycia i odbudowa

Propozycja pilotażu: laptop i zasilanie w suchym, osłoniętym miejscu, antena na zewnątrz z ochroną przewodu i odciążeniem złącza. Droga przewodu nie może uniemożliwiać zamknięcia wymaganych drzwi ani tworzyć przeszkody ewakuacyjnej. Uzgodnić miejsce i sposób mocowania. Praca w wilgoci, mrozie, po upadku, podczas rozruchu silnika oraz w atmosferze wymagającej specjalnych zabezpieczeń nie jest zakwalifikowana.

Aktualny odbiór ładowarki przewiduje 40°C otoczenia. Nie daje to zakresu temperatur całej stacji. Przed wdrożeniem trzeba określić i zweryfikować zakres dla kompletu, wraz z obudową, kablami, wentylacją i ogniwami. Nie zakładać, że element o katalogowym zakresie temperatur nadaje ten zakres gotowej konstrukcji.

Minimalny zasób naprawczy na pilotaż: sprawdzony drugi host lub dostępny zamiennik, Ethernet/USB, bezpieczniki o właściwej wartości, antena/przewód i odczytywalna kopia wydania. Najpierw ustalić, czy błąd dotyczy strony, zapisu, modemu, trasy, odbiorcy czy zasilania. Ponowny start nie jest odpowiedzią na nieznany błąd bazy albo ochrony elektrycznej.

PRZENIEŚ STACJĘ zachowuje tożsamość i bazę przez kontrolowany eksport; stara instancja przestaje pracować. Po nagłej utracie bez kopii nie da się obiecać odzyskania ostatnich lokalnych zgłoszeń. Odbiorca może mieć dane przyjęte wcześniej, ale to nie jest kopia całej bazy schronienia. [Procedura w specyfikacji](../spec/oprogramowanie.md).

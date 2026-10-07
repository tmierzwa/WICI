# WICI: odbiór prototypu

Kolumna „Grupa” wskazuje grupę prób T1–T8 z [planu weryfikacji](../conception/08-plan-weryfikacji-i-decyzje.html#proby-i-pokrycie-wymagan); tam też jest pokrycie wymagań W01–W23.

| Próba | Grupa | Warunek zaliczenia | Stan |
|---|---|---|---|
| Kodowanie ramek | T3, T4 | niezależny wektor CRC; długości 1–600 B; odwrócona kolejność fragmentów; błędy CRC i konflikt duplikatu | model wykonywalny |
| Wiadomości SA1 | T2 | wszystkie 6 typów; `category` 0–9, `state` 1–6 (STATUS tylko 2–6); UTF-8; graniczne rozmiary; odrzucenie niepoprawnych typów i dodatkowych pól | model wykonywalny |
| OSP | T2 | duplikat po restarcie; konflikt treści; przerwanie przed COMMIT bez wysłania RECEIVED; odrębni nadawcy | model wykonywalny |
| Stacja samodzielna | T1, T8 | z ogniw, bez laptopa i routera: gotowość radiowa ≤60 s od włączenia; zgłoszenie przyciskami i TEST z RECEIVED i STATUS; REPLY i BULLETIN czytelne na ekranie; osoba spoza zespołu obsługuje stację według karty | niewykonana |
| Zapis w stacji | T2 | 1000 odcięć zasilania (wyjęcie ogniw przy braku 12 V) w trakcie zapisu: brak pozornego „zapisane”, brak utraty po „zapisane”, zachowany dług ciszy; pełna kolejka odmawia zapisu z komunikatem | niewykonana |
| Zaufanie | T2 | RECEIVED, STATUS, REPLY i BULLETIN od obcego klucza odrzucone i policzone; nieznany nadawca w OSP w kwarantannie bez RECEIVED do decyzji dyżurnego; karty OSP nie da się zmienić przez radio ani bez przycisku konfiguracji | niewykonana |
| Szyfrowanie | T2 | baza laptopa nieczytelna bez pamięci USB zestawu; start bez hasła; odczyt pamięci MCU przez złącze programowania zablokowany (nRF52840 w rewizji z utwardzonym APPROTECT); rekordy FRAM odczytane bezpośrednio z układu są zaszyfrowane kluczem z pamięci MCU | niewykonana |
| Stos na MCU | T3 | oba wykonania wymieniają ogłoszenia, trasy, pakiety okazjonalne i potwierdzenia z implementacją referencyjną Reticulum i LXMF; odsetek udanych linków i zasobów za N przekazanymi datagramami 500 B i za długiem ciszy zapisany wraz z efektywną przepływnością; zapas RAM ≥30% przy pełnej tablicy tras, zmierzony przed projektem R02; 24 h przekazywania ruchu próby T5 bez utraty zgłoszeń; restarty przez watchdog policzone i zapisane | niewykonana |
| Czułość | T4 | każde wykonanie: ≤−110 dBm przy PER ≤1% dla ramek 103 B, zmierzone na złączu antenowym stacji z pełnym torem wejściowym, w profilu P1; strona ST na stanowisku S2-LP (np. STEVAL-FKI868V2 + NUCLEO, do sprawdzenia) albo na R02; moc i częstotliwość w tolerancji P1 | niewykonana |
| Przekaźnik zawsze aktywny | T5 | stacja bez laptopa przekazuje ruch od chwili osiągnięcia gotowości, także po restarcie przez watchdog i po przełączeniu źródła | niewykonana |
| Praca na ogniwach | T6 | ≥48 h jako przekaźnik przy ruchu próby T5 na 4 ogniwach litowych AA (Li-FeS2) w 20 °C; wyjęcie ogniwa podczas zapisu kończy zapis dzięki podtrzymaniu zasilania; wynik w −10 °C zapisany; 100 podłączeń i odłączeń 12 V bez resetu; odłączenie 12 V przy 11,5 V z zatrzaskiem | niewykonana |
| ESD i piorun | T6 | wyładowania ESD na złączu anteny bez uszkodzenia stacji i laptopa; montaż anteny zgodny z warunkami ochrony odgromowej, sprawdzony w miejscu pilotażu | niewykonana |
| Odtworzenie | T7 | osoba spoza zespołu buduje ze źródeł paczkę, oprogramowanie stacji i aplikację; dwóch niezależnych wykonawców; skróty, BOM, licencje i wersje zgodne; raport różnic | niewykonana |
| Obsługa i organizacja | T8 | opiekun i zastępcy według karty; zgłoszenie ze strony trafia do kolejki opiekuna i wychodzi radiem dopiero po jego sprawdzeniu; zgłoszenie z kwarantanny potwierdzone drugim kanałem; formularz papierowy i dziennik zmiany; osoba bez telefonu zgłasza potrzebę; dyżurny odczytuje i odsyła decyzję; awaria OSP i kanał zastępczy; zapisane czasy czynności i błędy obsługi; ćwiczenie ciszy, ZNISZCZ DANE i gońca; odbiorca wpisany do planu gminy | niewykonana |
| Stacje mieszane | T4 | TI→ST, ST→TI, 10 000 pakietów każdego rozmiaru granicznego; brak różnic formatu | niewykonana |
| Niedopasowanie anteny | T4 | każde wykonanie stacji: 60 s nadawania z rozwartym i ze zwartym złączem antenowym; po próbie moc i widmo bez zmian | niewykonana |
| Kanał | T5 | pomiar zajętości podpasma 869,4–869,65 MHz w miejscach pilotażu w różnych porach doby; liczniki CCA i błędów CRC z pracy próbnej | niewykonana |
| Bramka LoRaWAN | T5 | tło RSSI i blokowanie odbiornika w pobliżu pracującej bramki LoRaWAN (869,525 MHz to kanał RX2, bramki do 27 dBm ERP); wynik i odległość w raporcie | niewykonana |
| Radio 1 km | T5 | dwie rzeczywiste lokalizacje, anteny na zewnątrz; wysokości, zyski anten, przewody i rewizje zapisane w raporcie; ≥99 ze 100 zgłoszeń z RECEIVED w 5 min przy ruchu jednej stacji, bez innych nadawców | niewykonana |
| Przekaźnik | T5 | 3 stacje, B bez laptopa na ogniwach; wymuszone odcięcie bezpośredniego połączenia A–OSP; przejście przez B i powrót RECEIVED | niewykonana |
| Obciążenie sieci | T5 | referencyjne A–B–OSP: 50 zgłoszeń łącznie z A w pierwszych 5 min; ≥99% z RECEIVED na A do 30 min od pierwszego lokalnego COMMIT; droga powrotna przez B; zapis utrzymany podczas braku trasy | niewykonana |
| Limit czasu nadawania | T4 | łączny czas nadawania, łącznie z restartami, ≤10% w dowolnym oknie godzinnym; przerwany zapis dziennika nigdy nie umożliwia nadawania bez budżetu; ruch przekazywany wliczony | niewykonana |
| Laptop i USB | T1 | zimny start offline na komputerach z macOS (Intel i ARM), Windows x64 oraz na obsługiwanym PC z Linuksem, bez pobierania zależności i bez instalowania sterowników; host nie usypia się podczas pracy strony; 100 odłączeń przewodu USB w trakcie przekazywania bez utraty i bez podwojenia zgłoszenia; uśpienie i odłączenie hosta nie zmienia pracy stacji; stacja nie zasila się z VBUS (VSYS niezależne); wykonanie A pobiera z VBUS tylko prąd PHY USB ≈2,5 mA; lista sprawdzonych hostów i routerów | niewykonana |
| Stanowisko R01.3 | T4 | strona TI; zasilanie z zasilacza laboratoryjnego; prąd udarowy; prąd wstrzymania USB nie jest dla stanowiska wymagany; dotyczy tylko stanowiska laboratoryjnego | niewykonana |
| Cisza radiowa | T4, T8 | po włączeniu przełącznikiem stacji lub w panelu brak jakiejkolwiek emisji stacji przez 1 h przy ruchu przychodzącym i przekazywanym; odbiór, zapis i kolejka działają; po wyłączeniu ciszy stacja wysyła zaległą kolejkę bez utraty; wyjątek dla pojedynczego zgłoszenia (tylko cisza operacyjna dopuszczająca wyjątek) zapisany w dzienniku | niewykonana |
| Zniszczenie danych | T2 | ZNISZCZ DANE w ≤1 min na laptopie i na stacji; na stacji najpierw usunięcie klucza FRAM (kryptograficzne wymazanie), potem nadpisanie; po operacji baza, tożsamość, karta OSP, kolejka i eksport nieczytelne także po odzyskaniu usuniętych plików z nośnika i odczycie pamięci FRAM | niewykonana |
| Przeniesienie | T2 | kompletna kopia, zatrzymanie starej stacji, zachowana tożsamość i kolejka na stacji zapasowej; baza laptopa przeniesiona osobno | niewykonana |
| Strona | T1, T2 | 50 podłączonych telefonów, 15 aktywnych (T1); brak dostępu do cudzego zgłoszenia (T2); odłączona stacja nie blokuje zapisu formularza; odnośnik „Informacja o danych” i pouczenie o art. 66 Kodeksu wykroczeń pod formularzem | niewykonana |
| Języki i dostępność | T1, T8 | zgłoszenie wysłane po polsku, ukraińsku i angielsku przez osoby spoza zespołu; obsługa czytnikiem ekranu i przy powiększeniu 200%; brak okien zgód przed formularzem | niewykonana |
| A/B | T6 | oba kierunki, napięcia 11,5 i 16 V, każdy tryb mocy, 100 zmian; brak resetów routera, laptopa i przetwornicy | niewykonana |
| Odłączenie podnapięciowe | T6 | wejścia A/B i C: ostrzeżenie przy 11,8 V, wyłączenie przy 11,5 V ±0,1 V na złączu niezależnie od prądu i temperatury diody; ponowne załączenie wyłącznie ręczne i nie niżej niż 12,4 V; brak samoczynnego załączenia po odbiciu napięcia akumulatora kwasowo-ołowiowego i LiFePO4 | niewykonana |
| Udar A/B | T6 | prąd i I²t poniżej limitu każdego elementu; brak uszkodzeń oraz zgrzewania styków | niewykonana |
| Ładowarka | T6 | 8 × 1,5 A przez 2 h w temperaturze otoczenia 40 °C; 4,75–5,25 V na każdym porcie; skok obciążenia 1,5 A → 0 A w 0 °C i 40 °C bez zadziałania zwieracza | niewykonana |
| Zwarcie portu | T6 | pozostałe porty, laptop, router i stacja pracują; zwarcie trwające godzinę nie uszkadza sekcji | niewykonana |
| Ochrona telefonu przed przepięciem (OVP) | T6 | wymuszone zwarcie VIN–VREG regulatora; VUSB nigdy nie przekracza 5,5 V; po odłączeniu regulatora uszkodzona sekcja pozostaje wyłączona | niewykonana |
| Przetwornica | T6 | 150 W obciążenia rezystancyjnego na odpowiednim źródle, 230 V ±5%, THD <5%; rzeczywiste zasilacze, rozruch i skoki obciążenia; podłączenie zasilacza pod napięciem bez uszkodzenia mostka; brak jednostronnego nasycenia rdzenia | niewykonana |
| Ochrona AC | T6 | izolacja, PE, prąd dotykowy, uziemienie i reakcja RCBO sprawdzone zgodnie z przyjętą normą i konfiguracją | niewykonana |
| Zgodność RED | T4, T6 | badania gotowej konfiguracji według EN 300 220-2, EN 301 489-1 i -3 (oraz -17, jeśli radio 2,4 GHz MCU nie jest trwale zablokowane, razem z EN 300 328), EN 62368-1, EN 62479 oraz EN 18031-1 i -2 (cyberbezpieczeństwo, rozporządzenie delegowane (UE) 2022/30); zgodność z RoHS i rozporządzeniem bateryjnym (UE) 2023/1542; deklaracja zgodności UE producenta przed przekazaniem zestawu innym | niewykonana |
| Ekran i zasilanie stacji | T6 | czytelność ekranu LCD w −20 °C; OVP i podłączanie pod napięciem wejścia 12 V bez uszkodzenia i resetu | niewykonana |
| Zakłócenia | T4, T6 | pomiar odbioru radiowego przy pracującej przetwornicy i w pełni obciążonej ładowarce oraz przy telefonie nadającym w pasmach LTE 800 i GSM 900 obok stacji; brak pogorszenia uniemożliwiającego próbę terenową | niewykonana |
| Praca dobowa | T6 | 24 h pełnej funkcjonalności z wymianą źródeł; zużycie energii (Wh) stacji, puli A/B i ładowarki zapisane osobno | niewykonana |

Próba obciążenia obejmuje zimny start trasy oraz osobno ruch ustalony. Odcięcie A–OSP musi być fizycznie skuteczne. Liczy się odbiór RECEIVED przez A; sam zapis ani stan LXMF DELIVERED nie wystarczają. Z 50 zgłoszeń wymagane jest 50/50; 49/50 to 98%. Większa liczba schronień, przekaźników i jednoczesnych nadawców wymaga nowego planu obciążenia; ta próba nie kwalifikuje sieci 1000 stacji.

Próba modelu transakcji nie zastępuje próby fizycznego odcięcia zasilania dysku i stacji. Po zbudowaniu aplikacji i oprogramowania stacji powtarza się ją na docelowych nośnikach i pamięci FRAM, odcinając zasilanie przed, podczas i po zapisie. Wersji nie zwalnia się do użytku w schronieniach na podstawie samych testów modelu w Pythonie.

Próbę OVP wykonuje się bez telefonu, z obciążeniem zastępczym i oscyloskopem o odpowiednim paśmie. Jeżeli zwieracz zabezpieczający nie utrzyma napięcia poniżej 5,5 V podczas impulsu, wymagana jest niezależna szybka ochrona szeregowa. Nie wolno zwiększać dopuszczalnego napięcia, aby zaliczyć próbę. Obecny zwieracz jest tylko kandydatem. Przed produkcją muszą też powstać schemat PE, projekt płytki, ostateczny dobór izolacji i pełna lista zakwalifikowanych zamienników.

## Braki do wydania

1. Płytka stacji R02 w dwóch wykonaniach, projekty torów RF z nastawami rejestrów i oprogramowanie układowe stacji: microReticulum, LXMF, sterownik P1, dziennik FRAM, ekran, przyciski i protokół USB (D14, D15, D16).
2. Schemat elektryczny i płytka drukowana przetwornicy, ostateczna ochrona AC oraz oprogramowanie układowe regulatora (poziom 3).
3. Płytka drukowana ładowarki z odebraną ochroną OVP dla dwóch wariantów portu (poziom 3).
4. Aplikacja laptopa z protokołem USB do stacji i trybami kryzysowymi (cisza radiowa, szyfrowanie bazy, ZNISZCZ DANE, wersje językowe), kompletne pakiety offline oraz manifest przypiętych zależności (D17).
5. Decyzje D01 (limit SA1 jako jeden pakiet okazjonalny wpisany do specyfikacji), D10 (progi kosztu, terminu i wyniku dla P1 wobec LoRa, ustalone przed zamówieniem RF) i D11 (kanał).
6. Uzgodnienia z gminą: odbiorca, status sieci w stanach nadzwyczajnych, administrator danych i ocena skutków dla ochrony danych (D07, D12, D13) oraz decyzja o typie MELDUNEK (D18).
7. Powyższe próby oraz wyceny rzeczywistych zestawień materiałowych (BOM) od niezależnych wykonawców.

Zgodność czasowa stosu na mikrokontrolerze i niezależność wszystkich wariantów pozostają otwarte.

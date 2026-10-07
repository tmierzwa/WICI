# WICI — odbiór prototypu

| Próba | Warunek zaliczenia | Stan |
|---|---|---|
| Kodowanie ramek | niezależny wektor CRC; długości 1–600 B; odwrócona kolejność fragmentów; błędy CRC i konflikt duplikatu | model wykonywalny |
| Komunikaty | wszystkie 6 typów; UTF-8; graniczne rozmiary; odrzucenie niepoprawnych typów i dodatkowych pól | model wykonywalny |
| OSP | duplikat po restarcie; konflikt treści; przerwanie przed COMMIT bez wysłania RECEIVED; odrębni nadawcy | model wykonywalny |
| Modemy mieszane | TI→ST, ST→TI, 10 000 pakietów każdego rozmiaru granicznego; brak różnic formatu | niewykonana |
| Niedopasowanie anteny | każdy modem: 60 s nadawania z rozwartym i ze zwartym złączem antenowym; po próbie moc i widmo bez zmian | niewykonana |
| Kanał | pomiar zajętości podpasma 869,4–869,65 MHz w miejscach pilotażu w różnych porach doby; liczniki CCA i błędów CRC z pracy próbnej | niewykonana |
| Radio 1 km | dwie rzeczywiste lokalizacje, anteny na zewnątrz, wysokości anten zapisane w raporcie; ≥99 ze 100 zgłoszeń z RECEIVED w 5 min przy pojedynczym ruchu | niewykonana |
| Przekaźnik | 3 stacje, wymuszone odcięcie bezpośredniego połączenia A–OSP; przejście przez B i powrót RECEIVED | niewykonana |
| Obciążenie sieci | referencyjne A–B–OSP: 50 zgłoszeń łącznie z A w pierwszych 5 min; ≥99% z RECEIVED na A do 30 min od pierwszego lokalnego COMMIT; droga powrotna przez B; zapis utrzymany podczas braku trasy | niewykonana |
| Limit czasu nadawania | łączny czas nadawania, łącznie z restartami, ≤10% w dowolnym oknie godzinnym; przerwany zapis EEPROM nigdy nie umożliwia nadawania bez budżetu | niewykonana |
| USB | zimny start offline na komputerach z macOS (Intel i ARM), Windows x64 oraz na obsługiwanym PC z Linuksem, bez pobierania zależności; cały modem ≤100 mA przed konfiguracją, po konfiguracji w przyznanym budżecie do 500 mA, w stanie wstrzymania ≤2,5 mA; prąd udarowy oraz 100 cykli wstrzymania i wznowienia bez utraty trwałej kolejki i bez obejścia długu ciszy | niewykonana |
| Cisza radiowa | po włączeniu brak jakiejkolwiek emisji modemu przez 1 h przy ruchu przychodzącym i przekazywanym; odbiór, zapis i kolejka działają; po wyłączeniu kolejka wysyła się bez utraty; wyjątek dla pojedynczego zgłoszenia zapisany w dzienniku | niewykonana |
| Zniszczenie danych | ZNISZCZ DANE w ≤1 min; po operacji baza, tożsamość i eksport nieczytelne także po odzyskaniu usuniętych plików z nośnika | niewykonana |
| Przeniesienie | kompletna kopia, zatrzymanie starej instancji, zachowana tożsamość i kolejka na nowym laptopie | niewykonana |
| Strona | 50 podłączonych telefonów, 15 aktywnych; dostęp tylko do własnego zgłoszenia; odłączony modem nie blokuje formularza | niewykonana |
| Języki i dostępność | zgłoszenie wysłane po polsku, ukraińsku i angielsku przez osoby spoza zespołu; obsługa czytnikiem ekranu i przy powiększeniu 200%; brak okien zgód przed formularzem | niewykonana |
| A/B | oba kierunki, napięcia 11,5 i 16 V, każdy tryb mocy, 100 zmian; brak resetów routera, modemu i przetwornicy | niewykonana |
| Odłączenie podnapięciowe | wejścia A/B i C: ostrzeżenie przy 11,8 V, wyłączenie przy 11,5 V ±0,1 V na złączu niezależnie od prądu i temperatury diody; ponowne załączenie wyłącznie ręczne i nie niżej niż 12,4 V; brak samoczynnego załączenia po odbiciu napięcia akumulatora kwasowo-ołowiowego i LiFePO4 | niewykonana |
| Udar A/B | prąd i I²t poniżej limitu każdego elementu; brak uszkodzeń oraz zgrzewania styków | niewykonana |
| Ładowarka | 8 × 1,5 A przez 2 h w temperaturze otoczenia 40 °C; 4,75–5,25 V na każdym porcie; skok obciążenia 1,5 A → 0 A w 0 °C i 40 °C bez zadziałania zwieracza | niewykonana |
| Zwarcie portu | pozostałe porty oraz stacja pracują; zwarcie trwające godzinę nie uszkadza sekcji | niewykonana |
| Ochrona telefonu przed przepięciem (OVP) | wymuszone zwarcie VIN–VREG regulatora; VUSB nigdy nie przekracza 5,5 V; po odłączeniu regulatora uszkodzona sekcja pozostaje wyłączona | niewykonana |
| Przetwornica | 150 W obciążenia rezystancyjnego na odpowiednim źródle, 230 V ±5%, THD <5%; rzeczywiste zasilacze, rozruch i skoki obciążenia; podłączenie zasilacza pod napięciem bez uszkodzenia mostka; brak jednostronnego nasycenia rdzenia | niewykonana |
| Ochrona AC | izolacja, PE, prąd dotykowy, uziemienie i reakcja RCBO sprawdzone zgodnie z przyjętą normą i konfiguracją | niewykonana |
| Zgodność RED | badania gotowej konfiguracji według EN 300 220-2, EN 301 489-1 i -3, EN 62368-1 oraz EN 62479; deklaracja zgodności przed przekazaniem zestawu innym | niewykonana |
| Zakłócenia | pomiar odbioru radiowego przy pracującej przetwornicy i w pełni obciążonej ładowarce oraz przy telefonie nadającym w pasmach LTE 800 i GSM 900 obok stacji; brak pogorszenia uniemożliwiającego próbę terenową | niewykonana |
| Praca dobowa | 24 h pełnej funkcjonalności z wymianą źródeł; zużycie energii (Wh) stacji i ładowarki zapisane osobno | niewykonana |

Próba obciążenia obejmuje zimny start trasy oraz osobno ruch ustalony. Odcięcie A–OSP musi być fizycznie skuteczne. Liczy się odbiór RECEIVED przez A, a nie sam zapis ani stan LXMF DELIVERED. Z 50 zgłoszeń wymagane jest 50/50; 49/50 to 98%. Większa liczba schronień, przekaźników i jednoczesnych nadawców wymaga nowego planu obciążenia; ta próba nie kwalifikuje sieci 1000 stacji.

Próba modelu transakcji nie jest próbą odcinania fizycznego zasilania dysku. Po zbudowaniu aplikacji powtarza się ją na docelowych nośnikach, odcinając zasilanie przed, podczas i po zapisie. Wersji nie zwalnia się do użytku w schronieniach na podstawie samych testów modelu w Pythonie.

Próbę OVP wykonuje się bez telefonu, z obciążeniem zastępczym i oscyloskopem o odpowiednim paśmie. Jeżeli zwieracz zabezpieczający nie utrzyma napięcia poniżej 5,5 V podczas impulsu, wymagana jest niezależna szybka ochrona szeregowa; nie zwiększa się dopuszczalnego napięcia, aby zaliczyć próbę. Obecny zwieracz jest kandydatem, a nie odebraną ochroną. Podobnie przed produkcją muszą powstać: schemat PE, projekt płytki, ostateczny dobór izolacji i pełna lista zakwalifikowanych zamienników.

## Braki do wydania

1. Projekty dwóch płytek RF z nastawami rejestrów, oprogramowanie układowe CDC/KISS oraz adapter czasowy Reticulum.
2. Schemat elektryczny i płytka drukowana przetwornicy, ostateczna ochrona AC oraz oprogramowanie układowe regulatora.
3. Płytka drukowana ładowarki z odebraną ochroną OVP dla dwóch wariantów portu.
4. Aplikacja strony i LXMF, kompletne pakiety offline oraz manifest przypiętych zależności.
5. Powyższe próby oraz wyceny rzeczywistych zestawień materiałowych (BOM) od niezależnych wykonawców.

W tym pakiecie są kontrakty do weryfikacji oraz obliczalne punkty wyjścia. Zgodność czasowa stosu i niezależność wszystkich wariantów nie są zamknięte. Braki sprzętowe nie są oznaczone jako zrealizowane.

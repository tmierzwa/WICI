# WICI — odbiór prototypu

| Próba | Warunek zaliczenia | Stan |
|---|---|---|
| Kodowanie ramek | niezależny wektor CRC; długości 1–600 B; odwrócona kolejność; błędy CRC i konflikt duplikatu | model wykonywalny |
| Komunikaty | wszystkie 5 typów; UTF-8; graniczne rozmiary; odrzucenie niepoprawnych typów i dodatkowych pól | model wykonywalny |
| OSP | duplikat po restarcie; konflikt treści; przerwanie przed COMMIT bez ACK; odrębni nadawcy | model wykonywalny |
| Modemy mieszane | TI→ST, ST→TI, 10 000 pakietów każdego rozmiaru granicznego; brak różnic formatu | niewykonana |
| Radio 1 km | rzeczywiste dwie lokalizacje, anteny na zewnątrz; ≥99 ze 100 zgłoszeń z RECEIVED w 5 min przy pojedynczym ruchu | niewykonana |
| Przekaźnik | 3 stacje, wymuszone odcięcie bezpośrednie A–OSP; przejście przez B i powrót ACK | niewykonana |
| Obciążenie sieci | 50 zgłoszeń rozłożonych w 5 min; ≥99% potwierdzonych w 30 min; zapis utrzymany podczas braku trasy | niewykonana |
| Limit TX | cały ruch i restarty w dowolnym godzinowym oknie ≤10%; przerwanie zapisu EEPROM nigdy nie umożliwia nadania bez budżetu | niewykonana |
| USB | zimny start bez internetu na macOS Intel/ARM, Windows x64 i wspieranym Linux PC; brak pobierania zależności | niewykonana |
| Przeniesienie | kompletna kopia, zatrzymanie starej instancji, zachowana tożsamość i kolejka na nowym laptopie | niewykonana |
| Strona | 50 podłączonych telefonów, 15 aktywnych; dostęp tylko do własnego zgłoszenia; modem odłączony nie blokuje formularza | niewykonana |
| A/B | oba kierunki, napięcia 11,5 i 16 V, każdy tryb mocy, 100 zmian; zero resetów routera/modemu/inwertera | niewykonana |
| Udar A/B | prąd i I²t poniżej limitu każdego elementu; brak uszkodzeń oraz zgrzewania styków | niewykonana |
| Ładowarka | 8 ×1,5 A przez 2 h przy 40°C otoczenia; 4,75–5,25 V na każdym porcie | niewykonana |
| Zwarcie portu | pozostałe porty oraz stacja pracują; zwarcie trwające godzinę nie uszkadza sekcji | niewykonana |
| OVP telefonu | wymuszone zwarcie VIN–VREG regulatora; VUSB nigdy nie przekracza 5,5 V; po odłączeniu regulatora uszkodzona sekcja pozostaje wyłączona | niewykonana |
| Przetwornica | 150 W obciążenia rezystancyjnego na odpowiednim źródle, 230 V ±5%, THD <5%; rzeczywiste zasilacze, rozruch i skoki obciążenia | niewykonana |
| Ochrona AC | izolacja, PE, prąd dotykowy, uziemienie i reakcja RCBO sprawdzone dla przyjętej normy i konfiguracji | niewykonana |
| Zakłócenia | pomiar odbioru radia przy pracującej przetwornicy i pełnej ładowarce; brak pogorszenia uniemożliwiającego próbę terenową | niewykonana |
| Praca dobowa | 24 h pełnej funkcji z wymianami źródeł; zapisany pobór Wh stacji i ładowarki osobno | niewykonana |

Próba modelu transakcji nie jest próbą odcinania fizycznego zasilania dysku. Po zbudowaniu aplikacji powtarza się ją na docelowych nośnikach, odcinając zasilanie przed, podczas i po zapisie. Nie zwalnia się wersji do schronień na podstawie samych testów Python.

Próbę OVP wykonuje się bez telefonu, na obciążeniu i oscyloskopie o odpowiednim paśmie. Jeżeli crowbar nie utrzyma 5,5 V podczas impulsu, wymagana jest niezależna szybka ochrona szeregowa; nie zwiększa się dopuszczalnego napięcia, aby zaliczyć próbę. Obecny crowbar jest kandydatem, nie odebraną ochroną. Podobnie przed produkcją musi powstać schemat PE, layout, ostateczny dobór izolacji i pełna lista zakwalifikowanych zamienników.

## Braki do wydania

1. Dwa layouty RF i ich nastawy rejestrów, firmware CDC/KISS oraz adapter czasowy Reticulum.
2. Schemat elektryczny i PCB przetwornicy, finalna ochrona AC oraz firmware regulatora.
3. PCB ładowarki z odebraną ochroną OVP dla dwóch wariantów portu.
4. Aplikacja strony i LXMF, kompletne pakiety offline oraz manifest przypiętych zależności.
5. Próby powyżej i ceny rzeczywistych BOM od niezależnych wykonawców.

W tym pakiecie są zamknięte kontrakty oraz obliczalne punkty wyjścia. Braki sprzętowe nie są oznaczone jako zrealizowane.

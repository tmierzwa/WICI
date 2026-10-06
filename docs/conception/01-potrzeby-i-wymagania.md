# 01. Potrzeby i wymagania

## Problem i granica systemu

Po utracie zasilania i publicznych sieci mieszkańcy potrzebują lokalnej informacji oraz sposobu zgłoszenia: gdzie są, czego brakuje i ilu osób dotyczy potrzeba. Odbiorca potrzebuje krótkiego, jednoznacznego zgłoszenia i możliwości odesłania decyzji. Samo wysłanie nie dowodzi, że ktoś je odczytał lub skierował pomoc.

WICI obejmuje lokalną stronę, kolejkę zgłoszeń, radio, przekaźniki i stanowisko odbiorcze. Organizacja pomocy, dostępność ludzi, transport, medycyna oraz wyposażenie schronienia pozostają poza technicznym systemem. Przed pilotażem muszą jednak zostać uzgodnione z odbiorcą.

Nie ma danych pozwalających obiecać, że w dowolnej społeczności znajdzie się sprawny komplet urządzeń. Przyjmujemy ponowne użycie sprzętu po sprawdzeniu na miejscu. Brak laptopa, jego zasilacza lub dostępu do konfiguracji routera jest rzeczywistą przeszkodą uruchomienia.

## Wymagania i ich pochodzenie

U = ustalenie użytkowe; S = warunek przyjęty w specyfikacji; P = propozycja organizacyjna tej koncepcji. Numery prób T1–T8 zdefiniowano w [planie weryfikacji](08-plan-weryfikacji-i-decyzje.md). Wszystkie właściwości sprzętowe i operacyjne w tabeli nadal wymagają wykazania.

| ID | Wymaganie | Pochodzenie | Sprawdzenie |
|---|---|---|---|
| W01 | Działać bez internetu i usług zewnętrznych; start bez pobierania bibliotek | U/S | T1, T2 |
| W02 | Obsłużyć około 50 mieszkańców: 50 telefonów połączonych z Wi-Fi, 15 aktywnych klientów strony | U/S | T1 |
| W03 | Pozwalać wysłać zgłoszenie z przeglądarki bez konta i instalacji; opiekun obsługuje osoby bez telefonu | U/S/P | T1, T8 |
| W04 | Zapewnić lokalną informację oraz krótkie zgłoszenia, odpowiedzi, statusy i komunikaty; bez głosu i obrazów przez radio | U/S | T1, T2 |
| W05 | Trwale zapisać zgłoszenie i intencję wysyłki przed pokazaniem „zapisane lokalnie” | S | T2 |
| W06 | Odróżnić zapis lokalny, trwały zapis OSP, odczyt i skierowanie pomocy; decyzję podejmuje człowiek | S | T2, T8 |
| W07 | Po restarcie odtworzyć kolejkę; ponowienia nie tworzą drugiego zgłoszenia u odbiorcy | S | T2 |
| W08 | Łączyć sąsiednie stacje w rzeczywistej zabudowie na około 1 km z anteną na zewnątrz, bez wymogu dachu | U/S | T5 |
| W09 | Przekazać zgłoszenie i odpowiedź przez działającą stację pośrednią | U/S | T5 |
| W10 | Przyjąć 50 zgłoszeń rozłożonych w 5 min i potwierdzić ≥99% w 30 min | S | T5 |
| W11 | Pracować 24 h z zasobem wymienianych źródeł 12 V; wymiana A/B nie resetuje stacji | U/S | T6 |
| W12 | Ładować telefony z osobnego źródła: 8 niezależnych portów USB-A 5 V / 1,5 A | U/S | T6 |
| W13 | Uruchamiać się na zakwalifikowanych PC i Mac; router zapewnia Wi-Fi, DHCP i dostęp do LAN | U/S | T1 |
| W14 | Nie zależeć od jednego dostawcy wykonania; zakwalifikować dwa niezależne warianty części krytycznych | U/S | T3, T4, T6 |
| W15 | Udostępniać źródła, kontrakty, BOM, pliki wykonawcze i instrukcję umożliwiające odtworzenie | U/S | T7 |
| W16 | Przyjmować status i komunikat wyłącznie od zaufanej tożsamości OSP; ograniczyć dane mieszkańców i dostęp do zgłoszeń | S | T2 |
| W17 | Spełnić warunki radiowe i bezpieczeństwo elektryczne gotowej konfiguracji | S | T4, T6 |
| W18 | Pokazywać stan awarii oraz umożliwiać obsługę przez opiekuna i zastępcę według krótkiej instrukcji | U/P | T8 |

W08–W10 są celami do odbioru, nie gwarancją zasięgu i terminowości w dowolnej sieci. W13 oznacza macierz sprawdzonych konfiguracji, nie obsługę każdego znalezionego urządzenia. W14 wymaga pełnych wykonanych alternatyw; zakup tego samego układu u dwóch sprzedawców nie wystarcza.

## Minimalna informacja

Zgłoszenie zawiera kategorię, liczbę osób, dokładną lokalizację i wejście, krótki opis, pilność oraz identyfikator i wersję. Adres musi umożliwiać dojazd bez wcześniejszego profilu budynku. W OSP musi dać się odróżnić nowe zgłoszenie od zmiany poprzedniego. Limity bajtów i format są w [specyfikacji oprogramowania](../spec/oprogramowanie.md).

Lokalnie potrzebne są: informacje opiekuna, komunikaty OSP, stan łączności i własnego zgłoszenia. Tablica ofert pomocy, zdjęcia, mapy oraz automatyczna ocena medyczna zwiększają zakres; nie są warunkiem pierwszego prototypu.

## Dane do zebrania przed pilotażem

| Obszar | Informacja konieczna do decyzji |
|---|---|
| Miejsce | adres i wejście, możliwość wyprowadzenia anteny, metalowe przeszkody, odległość do sąsiada i odbiorcy |
| Urządzenia | model/architektura laptopa, stan systemu i startu USB, oryginalny zasilacz, model routera i dostęp do panelu |
| Energia | rzeczywisty pobór kompletnej stacji, napięcie/stan/pojemność źródeł, dozwolony prąd gniazda i przewodów |
| Pomoc | kto pełni dyżur, jakie działania może zlecić, zastępstwo, drugi odbiorca i kanał awaryjny |
| Obsługa | opiekun i zastępca, dostępność poza godzinami pracy, miejsce urządzeń, papierowa instrukcja |

Brak limitu kosztu i danych zakupowych nie pozwala zamknąć ceny zestawu. Koszt należy oceniać razem z energią, wykonaniem i próbami; [metoda](06-wykonalnosc-i-budzet-zasobow.md) rozdziela te składniki.
